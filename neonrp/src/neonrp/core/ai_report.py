"""举报 AI 生成的内容(App Store 1.2,10-21):游玩页的一段叙事 / 一句台词、小手机里角色的一条消息 → 平台。

    POST /api/v1/report/ai {reason, note?, surface: play|phone, excerpt, turn?, soul?, msg_id?, template?, run?, lang?, client?}
    → {ok, id, sent, queued, message}            400 bad_reason / no_excerpt

The engine sends it for the page (the local engine, iOS's, the browser engine — the same route) to the platform's own
inbox for it — data's records inbox ``POST {DATA}/v1/records/hub/ai-report`` ``{"body": {kind, reason, surface, client,
note?, excerpt?, run_id?, turn?, soul_id?, template_id?, template_version?, lang (zh-CN …), client_version?, msg_id?, report_id?}}`` → 201
``{id, …}`` (platform feat/ai-report b45c8d7, docs/AI举报-1021.md; guests may write; any other field is a 422) — and, while
that inbox is not deployed yet (404 / 405) or refuses our body (422), to the play-feedback inbox
(``POST {DATA}/v1/feedback/hub``, docs/游玩反馈-1015.md's shape) as one turn — the reported text and who said it — with
the reason first in ``text`` (``[report:ai] reason=…``). ``WORLDLINES_REPORT_URL`` overrides the first. The run's id, its
template, the turn number and the character's sid ride along; the player's words and everything else of the run stay out.

Every report is written to ``~/.neonrp/reports/ai.jsonl`` first (sent or not). Not signed in to Worldlines (no token)
or the platform unreachable → ``sent: false, queued: true``; the queue is tried again on the next report and on
:func:`flush`. ``sent: false`` with ``body`` = the page may send it itself with its own token (a guest's, the Hub's) and
then says so — ``POST /api/v1/report/ai/done {id}`` takes it off the queue (:func:`done`), so it never goes twice.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REASONS = ("sexual", "violence", "hate", "harassment", "self_harm", "illegal", "minors", "spam", "other")
LOCALES = {"zh": "zh-CN", "en": "en-US", "ja": "ja-JP", "ko": "ko-KR"}
SURFACES = ("play", "phone")
MAX_EXCERPT = 500
MAX_NOTE = 500
QUEUE_MAX = 50
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def data_base() -> str:
    return os.environ.get("WORLDLINES_DATA_BASE", "https://data.worldlines.gg").rstrip("/")


def target_url() -> str:
    """The platform's AI-report inbox (data's records inbox, hub/ai-report)."""
    return os.environ.get("WORLDLINES_REPORT_URL", "").strip() or f"{data_base()}/v1/records/hub/ai-report"


def feedback_url() -> str:
    """Where it goes while that inbox is not deployed: the play-feedback inbox."""
    return f"{data_base()}/v1/feedback/hub"


def _dir() -> Path:
    return Path(os.environ.get("NEONRP_REPORT_DIR") or (Path.home() / ".neonrp" / "reports"))


def _T(lang: str) -> dict[str, Any]:
    from neonrp.prompts import strings

    return strings("ai_report", lang)


def _version() -> str:
    try:
        from neonrp import __version__

        v = str(__version__)
    except Exception:  # noqa: BLE001
        v = ""
    return v if re.match(r"^[A-Za-z0-9._+-]{1,40}$", v) else "0.0.0"


def _safe_id(v: Any) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-.")[:128]
    return s if s and _ID.match(s) else None


def _run_context(root: Path | None) -> dict[str, Any]:
    """The bound run: its id (the save) and its template."""
    if root is None:
        return {}
    out: dict[str, Any] = {"run": Path(root).name}
    try:
        from neonrp import template as TP

        v = TP.run_view(Path(root)) or {}
        t = v.get("template") or {}
        if t.get("id"):
            out["template"] = str(t["id"])
            if t.get("version"):
                out["template_version"] = str(t["version"])
    except Exception:  # noqa: BLE001
        pass
    return out


def build(body: dict[str, Any], *, root: Path | None = None, lang: str = "zh") -> dict[str, Any]:
    """The request → the record kept locally + the platform body. Raises ValueError(code) on what is wrong."""
    reason = str(body.get("reason") or "").strip()
    if reason not in REASONS:
        raise ValueError("bad_reason")
    excerpt = re.sub(r"\s+\n", "\n", str(body.get("excerpt") or "")).strip()[:MAX_EXCERPT]
    if not excerpt:
        raise ValueError("no_excerpt")
    surface = str(body.get("surface") or "play")
    surface = surface if surface in SURFACES else "play"
    note = str(body.get("note") or "").strip()[:MAX_NOTE]
    ctx = _run_context(root) if surface == "play" else {}
    run = str(body.get("run") or ctx.get("run") or "")
    tpl = str(body.get("template") or ctx.get("template") or "")
    soul = str(body.get("soul") or "")
    turn = body.get("turn")
    turn = int(turn) if isinstance(turn, (int, float)) and not isinstance(turn, bool) and turn >= 0 else None
    cl = body.get("client") if isinstance(body.get("client"), dict) else {}
    rid = f"ai-{uuid.uuid4().hex[:16]}"
    rec = {"id": rid, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kind": "ai_message", "reason": reason, "note": note,
           "surface": surface, "excerpt": excerpt, "run": run, "template": tpl, "turn": turn, "soul": soul,
           "msg_id": str(body.get("msg_id") or "")[:80], "lang": lang}
    head = f"[report:ai] reason={reason} surface={surface}" + (f" soul={soul}" if soul else "") + (f" turn={turn}" if turn is not None else "") \
        + (f" msg={rec['msg_id']}" if rec["msg_id"] else "") + f" id={rid}"
    text = (head + (f"\n{note}" if note else ""))[:1000]
    mode = str(cl.get("mode") or "local")
    # the AI-report inbox's fields (platform docs/AI举报-1021.md, feat/ai-report b45c8d7): anything else is a 422
    tv = ctx.get("template_version")
    msg = rec["msg_id"] if re.match(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", rec["msg_id"] or "") else ""
    record_body = {"body": {"kind": "ai_message", "reason": reason, "surface": surface,
                            "client": {"browser": "web"}.get(mode, mode) if mode in ("local", "browser", "ios") else "local",
                            **({"note": note} if note else {}), "excerpt": excerpt, **({"run_id": run} if run else {}),
                            **({"turn": min(turn, 100000)} if turn is not None else {}), **({"soul_id": soul} if soul else {}),
                            **({"template_id": tpl or "chat"} if tpl or surface == "phone" else {}),
                            **({"template_version": str(tv)} if tv else {}), "lang": LOCALES.get(lang, "zh-CN"), "client_version": _version(),
                            **({"msg_id": msg} if msg else {}), "report_id": rid}}
    feedback_body = {
        "text": text,
        "template": {"id": _safe_id(tpl) or ("chat" if surface == "phone" else "unknown"),
                     **({"version": ctx["template_version"]} if ctx.get("template_version") and re.match(r"^[A-Za-z0-9._+-]{1,40}$", ctx["template_version"]) else {})},
        "engine_version": _version(),
        **({"save_id": _safe_id(run)} if _safe_id(run) else {}),
        "client": {"mode": mode if mode in ("local", "browser", "ios") else "local", "version": "1.2",
                   **({"locale": str(cl["locale"])} if re.match(r"^[a-z]{2}(-[A-Z]{2})?$", str(cl.get("locale") or "")) else {}),
                   **{k: str(cl[k])[:120] for k in ("platform", "browser", "device") if cl.get(k)}},
        "turns": [{"n": turn if turn is not None else 0, "input": "", "output": excerpt if not soul else "",
                   "beats": [{"kind": "dialogue" if soul else "narration", "speaker": soul, "text": excerpt}], "options": []}],
    }
    return {"record": rec, "body": {"record": record_body, "feedback": feedback_body}}


def _append(name: str, row: dict[str, Any]) -> None:
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        with (d / name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("report not written locally", exc_info=True)


def _queue() -> list[dict[str, Any]]:
    try:
        rows = [json.loads(x) for x in (_dir() / "queue.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        return [r for r in rows if isinstance(r, dict)]
    except (OSError, ValueError):
        return []


def _save_queue(rows: list[dict[str, Any]]) -> None:
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "queue.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[-QUEUE_MAX:]), encoding="utf-8")
    except OSError:
        logger.warning("report queue not written", exc_info=True)


def _post(url: str, body: dict[str, Any], headers: dict[str, str], post: Any) -> int:
    if post is not None:
        return int(post(url, body, headers)[0])
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def _send(pb: dict[str, Any], token: str | None, *, post: Any = None) -> tuple[bool, str]:
    """(sent, why). The AI-report inbox first; not there yet (404 / 405) → the play-feedback inbox.
    ``post`` = a test seam ``(url, body, headers) → (status, body)``."""
    if not token:
        return False, "not_signed_in"
    from neonrp.core import worldlines_auth

    headers = {**worldlines_auth.headers(), "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        status = _post(target_url(), pb.get("record") or {}, headers, post) if pb.get("record") else 404
        if status in (404, 405, 422) and pb.get("feedback"):  # not deployed yet / its schema refused ours: never lose the report
            status = _post(feedback_url(), pb["feedback"], headers, post)
    except Exception as e:  # noqa: BLE001 — unreachable: keep it, try later
        return False, f"unreachable: {str(e)[:120]}"
    if status in (200, 201, 202):
        return True, ""
    if status in (401, 403):
        return False, "not_signed_in"
    if status in (400, 413, 415, 422):
        return False, f"rejected:{status}"  # the body is wrong: retrying will not help
    return False, f"status:{status}"


def done(rid: str) -> bool:
    """The page sent it itself (its own token): drop it from the queue so it does not go twice."""
    rows = _queue()
    keep = [r for r in rows if r.get("id") != rid]
    if len(keep) == len(rows):
        return False
    _save_queue(keep)
    _append("ai.jsonl", {"id": rid, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sent": True, "by": "page"})
    return True


def flush(*, token: str | None = None, post: Any = None) -> int:
    """Send what is queued (oldest first). Returns how many went out."""
    from neonrp.core import worldlines_auth

    rows = _queue()
    if not rows:
        return 0
    token = token if token is not None else worldlines_auth.access_token()
    keep, n = [], 0
    for r in rows:
        ok, why = _send(r.get("body") or {}, token, post=post)
        if ok:
            n += 1
            _append("ai.jsonl", {"id": r.get("id"), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sent": True, "late": True})
        elif not why.startswith("rejected"):
            keep.append(r)
    _save_queue(keep)
    return n


def submit(body: dict[str, Any], *, root: Path | None = None, lang: str | None = None, token: str | None = None,
           post: Any = None) -> dict[str, Any]:
    from neonrp.core import worldlines_auth

    lang = lang or str(body.get("lang") or "zh")
    lang = lang if lang in ("zh", "en", "ja", "ko") else "zh"
    T = _T(lang)
    built = build(body, root=root, lang=lang)
    rec, pb = built["record"], built["body"]
    token = token if token is not None else worldlines_auth.access_token()
    if token == "-":
        token = None
    ok, why = _send(pb, token, post=post)
    _append("ai.jsonl", {**rec, "sent": ok, **({"why": why} if why else {})})
    queued = False
    if not ok and not why.startswith("rejected"):
        _save_queue([*_queue(), {"id": rec["id"], "body": pb}])
        queued = True
    if ok:
        try:
            flush(token=token, post=post)
        except Exception:  # noqa: BLE001
            logger.debug("report queue flush failed", exc_info=True)
    out: dict[str, Any] = {"ok": True, "id": rec["id"], "sent": ok, "queued": queued,
                           "message": str(T["sent"] if ok else T["queued"])}
    if not ok:
        out["why"] = why
        out["body"] = pb  # the page may send it with its own token (a guest's / the Hub's)
    return out
