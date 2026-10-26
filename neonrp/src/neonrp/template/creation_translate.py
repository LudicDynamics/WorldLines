"""The creation desk's 「用 AI 填其他语言」 (niko 10-25): the creator writes the four-language parts of the desk (the card's
title and pitch · the three truth questions) in one language, and the engine's agent writes the others — on its own
before 「存」 for the slots left empty, and again whenever the creator presses the button. The desk decides which slots
(the ones the creator typed are theirs, never sent as targets); this module only writes them.

    POST …/<template>/creation/translate {fields: {key: {lang: text}}, targets: {key: [lang]}, lang?}
      → {ok, fields: {key: {lang: text}}, missing: [[key, lang]]}

``key`` is the desk's own name for a slot (opaque here). The agent gets the template's own card in every language (its
setting and tone in each) and its glossary (each proper noun's name per language — a localized layer may rename people
and places entirely, so a name is looked up, not transliterated). Writes nothing; a model that does not answer in shape
is an error, never a crash. Nothing in here knows a world: the card and the glossary are data.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_KEYS = 60
MAX_CHARS = 8000    # all the source texts together (a card + three questions is well under 2000)
MAX_TERMS = 200


class TranslateError(ValueError):
    """``code``: bad_body · too_long · no_model · model · credits (the platform refused for money: ``extra.billing``) ·
    sign_in (a guest's call needs an account)."""

    def __init__(self, code: str, msg: str = "", extra: dict[str, Any] | None = None) -> None:
        super().__init__(msg or code)
        self.code, self.extra = code, extra or {}


def _stop(err: Any) -> None:
    """A money / sign-in refusal from ai.worldlines.gg (core/billing_stop: the marker in the error text) → its own error,
    so the desk can offer the top-up (or sign-in) instead of 「try again」."""
    from neonrp.core import billing_stop

    stop = billing_stop.remember((billing_stop.from_exception(err) if isinstance(err, BaseException) else None) or billing_stop.from_text(err))
    if stop is not None:
        raise TranslateError("sign_in" if stop.kind == "guest" else "credits", stop.code, {"billing": stop.to_dict()})


def ask(adapter: Any, system: str, user: str) -> str:
    """One call to the creator's model → its raw text; a failure is a TranslateError (credits · sign_in · model)."""
    try:
        out = adapter.generate(system, user)
    except Exception as exc:  # noqa: BLE001 — a failing model leaves the creator their own pen, never a crash
        _stop(exc)
        logger.warning("creation desk model call failed", exc_info=True)
        raise TranslateError("model", str(exc)[:200]) from exc
    if getattr(out, "error", None):
        _stop(str(out.error))
        raise TranslateError("model", str(out.error)[:200])
    return str(getattr(out, "raw_output", "") or getattr(out, "proposal_text", "") or "")


def _adapter() -> Any:
    """The creator's model (the creation provider — the browser engine's ``web`` one too); its own function so tests
    inject a stub."""
    from neonrp.template import creation_assist as CA

    try:
        return CA._adapter()
    except CA.AssistError as exc:
        raise TranslateError("no_model", str(exc)) from exc


def norm(fields: Any, targets: Any) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    """The request → (sources: key → {lang: text} with text, targets: key → the languages to write). A target needs a
    source; a language that already has the creator's text for that key is not a target."""
    from neonrp.template.i18n import LANGS

    if not isinstance(fields, dict) or not isinstance(targets, dict):
        raise TranslateError("bad_body", "fields and targets must be objects")
    src: dict[str, dict[str, str]] = {}
    for k, v in fields.items():
        if isinstance(v, dict):
            got = {lg: str(x).strip() for lg, x in v.items() if lg in LANGS and str(x or "").strip()}
            if got:
                src[str(k)] = got
    want: dict[str, list[str]] = {}
    for k, v in targets.items():
        k = str(k)
        lgs = [lg for lg in LANGS if isinstance(v, list) and lg in v and lg not in src.get(k, {})]
        if k in src and lgs:
            want[k] = lgs
    if len(want) > MAX_KEYS or sum(len(x) for k in want for x in src[k].values()) > MAX_CHARS:
        raise TranslateError("too_long", f"at most {MAX_KEYS} fields, {MAX_CHARS} characters")
    return src, want


def _setting(t: Any) -> dict[str, dict[str, str]]:
    """The template's own card per language: how the world is called and pitched to each language's players."""
    from neonrp.template import i18n as I

    out = {}
    for lg in I.langs(t):
        c = I.card(t, lg)
        row = {k: str(c.get(k) or "").strip() for k in ("title", "pitch") if str(c.get(k) or "").strip()}
        if row:
            out[lg] = row
    return out


def terms(t: Any) -> list[dict[str, str]]:
    """The glossary as {lang: name} rows (a list of spellings → its first)."""
    from neonrp.template import i18n as I

    rows = []
    for r in I.glossary(t)[:MAX_TERMS]:
        row = {}
        for lg in I.LANGS:
            v = r.get(lg)
            v = v[0] if isinstance(v, list) and v else v
            if isinstance(v, str) and v.strip():
                row[lg] = v.strip()
        if len(row) > 1:
            rows.append(row)
    return rows


def parse(raw: str, want: dict[str, list[str]]) -> dict[str, dict[str, str]] | None:
    """The model's answer → key → {lang: text}, only the asked keys and languages, non-empty; None = not JSON."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    d = d.get("fields") if isinstance(d.get("fields"), dict) else d
    out: dict[str, dict[str, str]] = {}
    for k, lgs in want.items():
        v = d.get(k)
        if not isinstance(v, dict):
            continue
        got = {lg: str(v[lg]).strip() for lg in lgs if isinstance(v.get(lg), (str, int, float)) and str(v[lg]).strip()}
        if got:
            out[k] = got
    return out


def translate(t: Any, fields: Any, targets: Any, *, lang: str = "", adapter: Any = None) -> dict[str, Any]:
    """Write the ``targets`` languages of ``fields`` → {ok, fields, missing}. Nothing to write = no model call."""
    from neonrp import prompts
    from neonrp.template import i18n as I

    src, want = norm(fields, targets)
    if not want:
        return {"ok": True, "fields": {}, "missing": []}
    lang = I.norm_lang(lang) or I.source_lang(t)
    items = [{"key": k, "from": src[k], "to": lgs} for k, lgs in want.items()]
    S, names = prompts.strings("creation_translate", lang), terms(t)
    user = str(S["user"]).format(setting=json.dumps(_setting(t), ensure_ascii=False),
                                 terms=json.dumps(names, ensure_ascii=False) if names else "-",
                                 items="\n".join(json.dumps(x, ensure_ascii=False) for x in items))
    got = parse(ask(adapter or _adapter(), str(S["system"]), user), want)
    if got is None:
        raise TranslateError("model", "the model did not answer in JSON")
    missing = [[k, lg] for k, lgs in want.items() for lg in lgs if lg not in got.get(k, {})]
    return {"ok": bool(got), "fields": got, "missing": missing}
