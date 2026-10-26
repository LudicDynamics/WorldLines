"""创作台「用一句话说」e2e 的假模型(不花额度、不连真模型):OpenAI 兼容 /v1/chat/completions,按作者那句话([say] …)
和这是第几步(提示词里 [you] 出现几次)回固定的工具调用 —— read_form → propose → done。

    python3 worldlines/ui/app/e2e-create/fake_llm.py --port 8908

GET /_mock/state = 收到的调用(第几步、那句话)。"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

CALLS: list[dict[str, Any]] = []
LOCK = threading.Lock()

KEY = [{"op": "add", "sec": "clue", "row": {"name": "铁钥匙", "summary": "教堂地下室的钥匙,挂在杂货铺柜台后", "where": "T001/shop_general"}},
       {"op": "add", "sec": "rule", "row": {"doc": "拿到钥匙", "trigger": {"when": {"text": "player"}, "if": [{"text": "钥匙"}], "then": [{"to": "flag", "key": "has.key"}], "once": True}}},
       {"op": "add", "sec": "rule", "row": {"doc": "没钥匙进不去地下室", "trigger": {"when": {"entry": "T004/chapel", "event": "enter", "who": "player"},
                                                                        "if": [{"flag": "has.key", "is": False}], "then": [{"to": "narration", "text": "地下室的门锁着,你只能退回去。"}]}}}]
BOSS = [{"op": "add", "sec": "ending", "row": {"title": "雾吞小镇", "kind": "fail", "text": "雾没有退。"}},
        {"op": "add", "sec": "soul", "row": {"name": "老板", "persona": "河灯旅店的老板,嘴硬心软", "collect": "ending", "collect_ending": "#1", "rarity": "rare"}}]
LIES = [{"op": "add", "sec": "rule", "row": {"doc": "说谎记一次", "trigger": {"when": {"text": "player"}, "if": [{"text": "骗"}], "then": [{"to": "var", "var": "lied.elena", "add": 1}]}}}]
CHAIN = [{"op": "add", "sec": "rule", "row": {"doc": "第一次说谎", "trigger": {"when": {"text": "player"}, "if": [{"text": "骗"}, {"flag": "lied.1", "is": False}], "then": [{"to": "flag", "key": "lied.1"}], "once": True}}},
         {"op": "add", "sec": "rule", "row": {"doc": "第二次说谎", "trigger": {"when": {"text": "player"}, "if": [{"text": "骗"}, {"flag": "lied.1"}], "then": [{"to": "flag", "key": "lied.2"}], "once": True, "edge": True}}},
         {"op": "add", "sec": "rule", "row": {"doc": "第三次她走", "trigger": {"when": {"text": "player"}, "if": [{"text": "骗"}, {"flag": "lied.2"}],
                                                                   "then": [{"to": "narration", "text": "艾琳娜不再看你,转身走了。"}, {"to": "flag", "key": "left.elena"}], "once": True}}}]
NEAR = "用三个标记接力:每被骗一次设一个,第三个设上时她离开"
SCRIPT = {
    "拿到钥匙后才能进地下室": (KEY, {"reply": "钥匙放在杂货铺;没拿到时进教堂地下室会被挡回来。"}),
    "玩到坏结局可以带走老板": (BOSS, {"reply": "加了坏结局「雾吞小镇」,走到它就能带走老板。"}),
    "她被骗三次就会离开": (LIES, {"reply": "这个模板不能计数。", "unsupported": [{"what": "这个模板不开放「数值」,数不了三次", "nearest": NEAR}]}),
    NEAR: (CHAIN, {"reply": "用三个标记接力:第三次被骗时艾琳娜离开。"}),
}


def reply(user: str) -> str:
    say = user.split("[say] ", 1)[-1].split("\n", 1)[0].strip()
    step = user.count("[you]")
    ops, done = SCRIPT.get(say, ([], {"reply": "?"}))
    with LOCK:
        CALLS.append({"say": say, "step": step})
    if step == 0:
        return json.dumps({"tool": "read_form"})
    if step == 1:
        return json.dumps({"tool": "propose", "ops": ops}, ensure_ascii=False)
    return json.dumps({"tool": "done", **done}, ensure_ascii=False)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a: Any) -> None:
        pass

    def _send(self, body: bytes, ct: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        with LOCK:
            self._send(json.dumps({"calls": CALLS}, ensure_ascii=False).encode(), "application/json")

    def do_POST(self) -> None:  # noqa: N802
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        msgs = req.get("messages") or []
        text = reply(str(msgs[-1].get("content") if msgs else ""))
        if req.get("stream"):
            chunk = {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]}
            end = {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            return self._send(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\ndata: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode(), "text/event-stream")
        body = {"id": "x", "object": "chat.completion", "model": req.get("model") or "mock", "created": 0,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        self._send(json.dumps(body, ensure_ascii=False).encode(), "application/json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8908)
    ThreadingHTTPServer(("127.0.0.1", ap.parse_args().port), H).serve_forever()
