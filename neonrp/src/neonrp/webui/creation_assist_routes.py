"""``POST /api/v1/local/templates/<id>/creation/assist {addition, say, lang?}`` — the creation desk's "say it in one sentence"
(template/creation_assist.py): → {ok, reply, ops, preview, addition, problems, unsupported, steps}. Writes nothing;
the desk puts ``addition`` into the form when the creator confirms. 400 {error: empty | closed | bad_body} ·
404 · 503 {error: no_model}."""
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
