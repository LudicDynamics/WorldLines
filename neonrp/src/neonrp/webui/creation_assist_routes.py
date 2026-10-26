"""``POST /api/v1/local/templates/<id>/creation/assist {addition, say, lang?}`` — the creation desk's "say it in one sentence"
(template/creation_assist.py): → {ok, reply, ops, preview, addition, problems, unsupported, steps}. Writes nothing;
the desk puts ``addition`` into the form when the creator confirms. 400 {error: empty | closed | bad_body} ·
404 · 503 {error: no_model}.

``POST …/<id>/creation/translate {fields, targets, lang?}`` — the desk's 「用 AI 填其他语言」 (template/creation_translate.py):
→ {ok, fields, missing}. ``POST …/<id>/creation/write {addition, card?, targets, lang?}`` — the desk's AI on every text box
(template/creation_write.py): → {ok, fields, missing}. Both write nothing. 400 {error: bad_body | too_long} · 401 {error:
sign_in} · 402 {error: credits, billing} (the platform refused for money: the desk offers the top-up) · 404 · 502 {error:
model} · 503 {error: no_model}."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

LOCAL = "/api/v1/local/templates"


def post(h: Any, route: str) -> bool:
    from neonrp import template as TP
    from neonrp.template import creation_assist as CA

    tid = unquote(route[len(LOCAL) + 1:].partition("/")[0])
    found = TP.discover()
    if tid not in found:
        h._send_json({"ok": False, "error": "no such template"}, status=404)
        return True
    body = h._read_json_body() or {}
    add = body.get("addition") if body.get("addition") is not None else {}
    if not isinstance(add, dict):
        h._send_json({"ok": False, "error": "bad_body", "message": "addition must be an object"}, status=400)
        return True
    try:
        h._send_json(CA.assist(TP.load(found[tid]), add, str(body.get("say") or ""), lang=str(body.get("lang") or "zh")))
    except CA.AssistError as e:
        h._send_json({"ok": False, "error": e.code, "message": str(e)}, status=503 if e.code == "no_model" else 400)
    return True


def translate(h: Any, route: str) -> bool:
    from neonrp.template import creation_translate as CT

    return _desk_call(h, route, lambda t, b, lang: CT.translate(t, b.get("fields"), b.get("targets"), lang=lang))


def write(h: Any, route: str) -> bool:
    from neonrp.template import creation_write as CW

    return _desk_call(h, route, lambda t, b, lang: CW.write(t, {} if b.get("addition") is None else b["addition"], b.get("targets"), card=b.get("card"), lang=lang))


def _desk_call(h: Any, route: str, fn: Any) -> bool:
    from neonrp import template as TP
    from neonrp.template import creation_translate as CT

    tid = unquote(route[len(LOCAL) + 1:].partition("/")[0])
    found = TP.discover()
    if tid not in found:
        h._send_json({"ok": False, "error": "no such template"}, status=404)
        return True
    body = h._read_json_body() or {}
    try:
        h._send_json(fn(TP.load(found[tid]), body, str(body.get("lang") or "")))
    except CT.TranslateError as e:
        h._send_json({"ok": False, "error": e.code, "message": str(e)[:300], **e.extra},
                     status={"no_model": 503, "model": 502, "credits": 402, "sign_in": 401}.get(e.code, 400))
    return True
