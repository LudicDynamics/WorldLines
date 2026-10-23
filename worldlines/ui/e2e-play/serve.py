"""浏览器游玩 e2e 的两个本地服务(不花额度、不连真模型):

    python3 worldlines/ui/e2e-play/serve.py --site <build_static 的 --out> [--port 8610] [--ai-port 8611]

- :8610  静态站(和 S3 上一样:就是一个目录)
- :8611  假的 ai.worldlines.gg(OpenAI 兼容 /v1/chat/completions,流式 / 非流式都答;CORS 只放行 :8610 那个 origin,
         和线上「只对 neonrp.worldlines.gg 放行」同一个形状)+ 假的 auth 续期(/v1/token/refresh)
         控制口:GET /_mock/state(收到了几次调用、带的什么头)· POST /_mock/mode {"mode": "ok" | "quota" | "claim" | "credits" | "hang"}
         + 假平台(identity / storage / data / chronicle / sns,同一个口;构建时 --platform 指到这里,页面和浏览器里的引擎都打它):
         /v1/me · /v1/resources(列 / 注册)· …/lease · …/upload-url · /_put/<文件> · …/complete · …/publish · …/withdraw ·
         /v1/records/…(空)· /v1/events:batch(收下);控制口 GET /_plat/state {steps, bodies, puts(base64)} · POST /_plat/reset({"all": true} = 连作品一起清)。
         浏览器里的引擎在 Service Worker 控制的 iframe 里,WebKit 下 Playwright 拦不到它的请求(10-21 create-art 实测),所以假平台放在这里。

额度用完的三种回法照 services/ai §3.1/§3.4:429 quota_exceeded · 403 claim_required(reason)· 402 insufficient_credits,都带 billing_url。
"""
from __future__ import annotations

import argparse
import functools
import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any

STATE: dict[str, Any] = {"mode": "ok", "calls": [], "refreshes": 0}
PLAT: dict[str, Any] = {"steps": [], "bodies": {}, "puts": {}, "works": {}}
LOCK = threading.Lock()
LINES = [
    "雨水顺着屋檐往下淌。门厅只点着一盏油灯,灯影里有人在等你开口。\n① 走近灯影 ② 先看看四周",
    "你往前走了两步,地板吱呀作响。灯影里的人抬起头,像是终于认出了你。\n① 问他是谁 ② 退回门口",
    "风从门缝里钻进来,油灯晃了一下。远处传来钟声,一共七下。\n① 数钟声 ② 继续往里走",
]


class Site(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
                      ".zip": "application/zip", ".webp": "image/webp", ".wasm": "application/wasm"}

    def log_message(self, *a: Any) -> None:
        pass

    def end_headers(self) -> None:
        # 和 CloudFront 上一样:页面 / manifest 不长缓存;带哈希的包可以
        p = self.path.split("?")[0]
        self.send_header("Cache-Control", "no-cache" if p.endswith((".html", "/", "manifest.json", "sw.js", "boot.js", "worker.js")) else "max-age=3600")
        super().end_headers()


class AI(BaseHTTPRequestHandler):
    origin = "http://127.0.0.1:8610"

    def log_message(self, *a: Any) -> None:
        pass

    def _cors(self) -> None:
        if (self.headers.get("Origin") or "") == self.origin:
            self.send_header("Access-Control-Allow-Origin", self.origin)
            self.send_header("Access-Control-Allow-Headers", self.headers.get("Access-Control-Request-Headers") or "authorization, content-type, accept, x-worldlines-product")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")

    def _json(self, obj: Any, status: int = 200) -> None:
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self._cors()
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _platform(self, method: str, raw: bytes) -> bool:
        """The fake platform (same shape as create.spec's old route): → True when the path was its."""
        import base64
        import re
        from urllib.parse import unquote, urlparse

        p = urlparse(self.path).path
        if p == "/_plat/state":
            with LOCK:
                self._json({"steps": PLAT["steps"], "bodies": PLAT["bodies"], "puts": {k: base64.b64encode(v).decode() for k, v in PLAT["puts"].items()}})
            return True
        if p == "/_plat/reset":   # {"all": true} = a fresh platform (each test starts with one: no works left from the last test)
            with LOCK:
                PLAT["steps"].clear()
                if json.loads(raw or b"{}").get("all"):
                    PLAT["bodies"].clear()
                    PLAT["puts"].clear()
                    PLAT["works"].clear()
            self._json({"ok": True})
            return True
        plat = p == "/v1/me" or p.startswith(("/_put/", "/v1/resources", "/v1/objects", "/v1/public/", "/v1/records", "/v1/events", "/api/"))
        if not plat:
            return False
        body = lambda: json.loads(raw or b"{}") if raw else {}  # noqa: E731
        with LOCK:
            PLAT["steps"].append(f"{method} {p}")
            works = PLAT["works"]
            if p.startswith("/_put/"):
                PLAT["puts"][unquote(p[6:])] = raw
                self.send_response(200)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return True
            if p == "/v1/me":
                return self._json({"user": {"id": "u-e2e", "official": False}}) or True
            if p == "/v1/resources" and method == "GET":
                return self._json({"resources": list(works.values())}) or True
            if p == "/v1/resources" and method == "POST":
                b = body()
                PLAT["bodies"]["register"] = b
                works[b["id"]] = {"id": b["id"], "title": b.get("title"), "meta": b.get("meta"), "status": "draft", "zone": None, "revision": 0, "review": {"state": "none"}}
                return self._json({"resource": {"id": b["id"]}}, 201) or True
            if p.startswith("/v1/records"):
                return self._json({"records": [], "next_cursor": None}) or True
            if p.startswith("/v1/events"):
                return self._json({"ok": True}) or True
            m = re.search(r"/hub/template/([^/]+)/([a-z-]+)", p)
            w = works.get(m.group(1)) if m else None
            if m and m.group(2) == "lease":
                return self._json({"lease_id": "L1"}, 201) or True
            if m and m.group(2) == "upload-url":
                files = body().get("files") or []
                host = f"http://{self.headers.get('Host')}"
                return self._json({"revision": 1, "uploads": [{"path": f["path"], "method": "PUT", "url": f"{host}/_put/{f['path']}", "headers": {}} for f in files]}) or True
            if m and m.group(2) == "complete":
                if w:
                    w.update(revision=1, meta=body().get("meta"))
                return self._json({"manifest": {"revision": 1}}) or True
            if m and m.group(2) == "publish":
                PLAT["bodies"]["publish"] = body()
                if w:
                    w.update(zone="curated", review={"state": "pending", "autopass_at": "2026-10-18T09:30:00Z", "held": False}, updated_at="2026-10-18T00:00:00Z")
                return self._json({"review": {"state": "pending"}, "resource": {**(w or {}), "zone": "curated"}}, 202) or True
            if m and m.group(2) == "withdraw":
                if w:
                    w["review"] = {"state": "none"}
                return self._json({"resource": w}) or True
        self._json({}, 404)
        return True

    def do_PUT(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        if not self._platform("PUT", self.rfile.read(n) if n else b""):
            self._json({"error": "not found"}, 404)

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._platform("DELETE", b""):
            self._json({"error": "not found"}, 404)

    def do_GET(self) -> None:  # noqa: N802
        if self._platform("GET", b""):
            return
        if self.path == "/_mock/state":
            with LOCK:
                return self._json({"mode": STATE["mode"], "calls": STATE["calls"], "refreshes": STATE["refreshes"]})
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if self._platform("POST", raw):
            return
        if self.path == "/_mock/mode":
            with LOCK:
                STATE["mode"] = json.loads(raw or b"{}").get("mode", "ok")
                STATE["sleep"] = float(json.loads(raw or b"{}").get("sleep", 15))
                if json.loads(raw or b"{}").get("reset"):
                    STATE["calls"] = []
            return self._json({"ok": True, "mode": STATE["mode"]})
        if self.path == "/v1/token/refresh":
            with LOCK:
                STATE["refreshes"] += 1
            return self._json({"access_token": f"tok-refreshed-{int(time.time())}", "refresh_token": "r-next", "expires_in": 900})
        if self.path == "/v1/systemone":  # Jev through the proxy: every question gets an even answer
            req = json.loads(raw or b"{}")
            with LOCK:
                STATE["calls"].append({"auth": self.headers.get("Authorization", ""), "product": self.headers.get("X-Worldlines-Product", ""),
                                       "origin": self.headers.get("Origin", ""), "jev": True, "mode": STATE["mode"], "at": time.time()})
            return self._json({"answers": {k: {"noul": 0.5} for k in (req.get("questions") or {})}})
        if self.path != "/v1/chat/completions":
            return self._json({"error": "not found"}, 404)
        req = json.loads(raw or b"{}")
        with LOCK:
            mode = STATE["mode"]
            STATE["calls"].append({"auth": self.headers.get("Authorization", ""), "product": self.headers.get("X-Worldlines-Product", ""),
                                   "origin": self.headers.get("Origin", ""), "stream": bool(req.get("stream")), "model": req.get("model"),
                                   "mode": mode, "at": time.time()})
            k = sum(1 for c in STATE["calls"] if c["mode"] == "ok" and not c.get("jev"))
        if mode == "hang":  # a provider that never answers in time (the engine's per-beat timeout must cut it)
            time.sleep(STATE.get("sleep", 15))
        if mode == "quota":
            return self._json({"error": {"code": "quota_exceeded", "message": "daily quota exceeded", "kind": "daily",
                                         "billing_url": "https://billing.worldlines.gg/subscribe?product=hub"}}, 429)
        if mode == "claim":
            return self._json({"error": {"code": "insufficient_credits", "reason": "claim_required", "message": "claim today's credits",
                                         "billing_url": "https://billing.worldlines.gg/claim?product=hub"}}, 402)
        if mode == "credits":
            return self._json({"error": {"code": "insufficient_credits", "message": "not enough credits",
                                         "billing_url": "https://billing.worldlines.gg/subscribe?product=hub"}}, 402)
        text = LINES[(k - 1) % len(LINES)]
        usage = {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}
        if req.get("stream"):
            chunks = [{"id": "m", "object": "chat.completion.chunk", "created": 1, "model": req.get("model"),
                       "choices": [{"index": 0, "delta": {"role": "assistant", "content": part}, "finish_reason": None}]}
                      for part in (text[: len(text) // 2], text[len(text) // 2:])]
            chunks.append({"id": "m", "object": "chat.completion.chunk", "created": 1, "model": req.get("model"),
                           "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage})
            b = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(b)))
            self._cors()
            self.end_headers()
            self.wfile.write(b)
            return
        self._json({"id": "m", "object": "chat.completion", "created": 1, "model": req.get("model"),
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}], "usage": usage})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--port", type=int, default=8610)
    ap.add_argument("--ai-port", type=int, default=8611)
    a = ap.parse_args()
    AI.origin = f"http://127.0.0.1:{a.port}"
    site = ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(Site, directory=a.site))
    ai = ThreadingHTTPServer(("127.0.0.1", a.ai_port), AI)
    threading.Thread(target=ai.serve_forever, daemon=True).start()
    print(f"site http://127.0.0.1:{a.port}/  ·  mock ai http://127.0.0.1:{a.ai_port}/v1", flush=True)
    site.serve_forever()


if __name__ == "__main__":
    main()
