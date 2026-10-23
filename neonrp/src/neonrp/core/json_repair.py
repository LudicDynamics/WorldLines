"""Deterministic repair of LLM-malformed JSON.

deepseek (and LLMs generally) hand the engine JSON with a small, known set of
malformations: unescaped inner double quotes, JS-style ``"a" + prose + "b"``
concatenation, raw control chars inside strings, trailing commas, and smart
quotes used as string delimiters. This module is the shared pipeline that
heals what can be healed DETERMINISTICALLY and raises on the rest, so broken
JSON never lands on disk silently (the write boundary in
``neonrp.core.skills`` rejects the write and bounces the parse error back to
the model for a rewrite).

Contract:

- :func:`loads_repaired` — parse with progressive repair; raises
  :class:`JsonRepairError` when no pass yields valid JSON.
- :func:`repair_json` — same pipeline, returning the canonical
  ``json.dumps(obj, ensure_ascii=False, indent=2)`` serialization, so
  escaping is normalized even for input that already parses.

Passes are tried in order of increasing aggressiveness and the first
parseable candidate wins — well-formed input is never rewritten by a
heuristic. Genuinely ambiguous input (e.g. a value ENDING on a quoted
phrase: ``…又说 "别过来""`` — no algorithm can know where that string
ends) is not guessable and raises.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Double-quote lookalikes models emit as string delimiters: “ ” 〝 〞 ＂
_SMART_DOUBLE_QUOTES = "“”〝〞＂"


class JsonRepairError(ValueError):
    """Text could not be made parseable by any deterministic repair pass."""


def _repair_broken_strings(text: str) -> str:
    """Best-effort repair of JSON whose string VALUES were broken by the
    model. Two failure modes are healed:

    1. JS-style concatenation / bare prose between quoted segments, e.g.
       ``"speech": "台词A" + 动作旁白 + "台词B"`` — the inner quotes/``+`` are not
       legal JSON. We merge the run into one string (the prose becomes text).
    2. Raw newlines/tabs inside a string value (unescaped control chars).

    Heuristic: while inside a string, a ``"`` ends it ONLY when the next
    non-space char is JSON-structural (``,`` ``}`` ``]`` ``:`` or end). Any other
    following char means the quote was a spurious break, so we stay in the
    string, skip an optional ``+`` joiner and a re-opening quote, and continue.
    Returns the (possibly) repaired text; callers re-validate with
    ``json.loads``, so a bad guess is never worse than the status quo."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        if c == "\\":  # keep escape sequences verbatim
            out.append(text[i : i + 2])
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            nxt = text[j] if j < n else ""
            if nxt in ",}]:" or nxt == "":
                out.append('"')
                in_str = False
                i += 1
            else:
                # Spurious break: drop the quote, skip an optional `+` joiner and
                # a re-opening quote, and keep the prose as in-string text.
                k = j
                if k < n and text[k] == "+":
                    k += 1
                    while k < n and text[k] in " \t\r\n":
                        k += 1
                if k < n and text[k] == '"':
                    k += 1
                out.append(" ")
                i = k
            continue
        if c in "\n\r\t":  # escape raw control chars inside the string
            out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[c])
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Drop a ``,`` whose next non-whitespace char is ``}`` or ``]``.

    String-aware: commas inside string values are never touched, so a value
    like ``"a, }"`` survives intact."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1  # trailing comma — skip it
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _convert_structural_smart_quotes(text: str) -> str:
    """Convert smart double quotes to ``"`` in STRUCTURAL positions only.

    Models sometimes emit ``“key”: “value”`` — smart quotes as the string
    delimiters themselves. Outside any string, a quote can only legally open a
    string, so a smart quote there IS a delimiter and becomes ``"``. Inside a
    smart-delimited string, a smart quote closes it only when the next
    non-whitespace char is JSON-structural (same heuristic as
    :func:`_repair_broken_strings`); otherwise it is content and is preserved
    verbatim. Smart quotes inside ASCII-delimited strings are always content
    and are never touched — 「」/“” dialogue in values survives byte-for-byte.
    An ASCII ``"`` inside a smart-delimited string is content too and gets
    escaped so the converted string stays valid."""
    OUTSIDE, IN_ASCII, IN_SMART = 0, 1, 2
    state = OUTSIDE
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if state == OUTSIDE:
            if c == '"':
                state = IN_ASCII
                out.append(c)
            elif c in _SMART_DOUBLE_QUOTES:
                state = IN_SMART
                out.append('"')
            else:
                out.append(c)
            i += 1
            continue
        if state == IN_ASCII:
            if c == "\\" and i + 1 < n:
                out.append(text[i : i + 2])
                i += 2
                continue
            out.append(c)
            if c == '"':
                state = OUTSIDE
            i += 1
            continue
        # IN_SMART
        if c == "\\" and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if c in _SMART_DOUBLE_QUOTES:
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            nxt = text[j] if j < n else ""
            if nxt in ",}]:" or nxt == "":
                out.append('"')
                state = OUTSIDE
            else:
                out.append(c)  # content smart quote — preserve verbatim
            i += 1
            continue
        if c == '"':
            out.append('\\"')  # content ASCII quote inside a smart-delimited string
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _candidates(text: str) -> Iterable[str]:
    """Repair candidates in order of increasing aggressiveness."""
    repaired = _repair_broken_strings(text)
    yield repaired
    yield _strip_trailing_commas(text)
    yield _strip_trailing_commas(repaired)
    smart = _convert_structural_smart_quotes(text)
    if smart != text:
        yield smart
        smart_repaired = _repair_broken_strings(smart)
        yield smart_repaired
        yield _strip_trailing_commas(smart_repaired)


def _describe_parse_error(exc: json.JSONDecodeError, text: str) -> str:
    """Human/model-actionable description of a parse failure: line/col + snippet."""
    start = max(0, exc.pos - 40)
    end = min(len(text), exc.pos + 40)
    snippet = text[start:end].replace("\n", "\\n").replace("\r", "\\r")
    return (
        f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg} — "
        f"near: …{snippet}…"
    )


def loads_repaired(text: str) -> Any:
    """Parse ``text`` as JSON, healing known LLM malformations if needed.

    Raises :class:`JsonRepairError` (with the line/col/snippet of the
    ORIGINAL text's parse failure — positions the model can act on) when no
    deterministic repair pass yields valid JSON."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        original_error = exc
    seen = {text}
    for candidate in _candidates(text):
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise JsonRepairError(_describe_parse_error(original_error, text)) from original_error


def repair_json(text: str) -> str:
    """Parse-with-repair and return the canonical serialization
    (``json.dumps(obj, ensure_ascii=False, indent=2)``), normalizing escaping
    even for input that already parses. Raises :class:`JsonRepairError` when
    the text cannot be repaired."""
    return json.dumps(loads_repaired(text), ensure_ascii=False, indent=2)


# ── Last resort: one focused LLM repair request ─────────────────────────

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)

_LLM_REPAIR_SYSTEM_PROMPT = (
    "You are a JSON repair tool. The user gives you one broken JSON document "
    "and its parse error. Output ONLY the corrected JSON document — no prose, "
    "no code fences, no commentary. Change as little as possible and preserve "
    "ALL content verbatim; only fix the syntax. Dialogue quotes inside string "
    'values must become 「」/『』 or \\" escaped double quotes.'
)


def repair_json_with_llm(text: str, llm: Any, *, error: JsonRepairError | None = None) -> Any:
    """LAST-RESORT repair: one focused LLM request for JSON the deterministic
    passes couldn't heal (e.g. a value ending on a quoted phrase — genuinely
    ambiguous to any algorithm, but a language model can read the sentence).

    ``llm`` is any ``_LLMLike`` (``generate(system_prompt, user_prompt, tools)``,
    the :class:`neonrp.core.llm.LLMAdapter` shape). Exactly ONE request is made
    — no retries, no recursion. On success returns the parsed object; on ANY
    failure (bad reply, still-broken JSON, transport error) raises the original
    :class:`JsonRepairError` so callers keep their existing degraded path."""
    if error is None:
        try:
            return loads_repaired(text)
        except JsonRepairError as exc:
            error = exc
    user_prompt = f"Parse error: {error}\n\nBroken JSON document:\n{text}"
    try:
        raw = llm.generate(_LLM_REPAIR_SYSTEM_PROMPT, user_prompt, None)
    except Exception:
        raise error from None
    reply = raw if isinstance(raw, str) else (
        getattr(raw, "proposal_text", None) or getattr(raw, "raw_output", None) or ""
    )
    reply = str(reply).strip()
    fenced = _FENCE_RE.match(reply)
    if fenced:
        reply = fenced.group(1).strip()
    try:
        obj = json.loads(reply)
    except (ValueError, TypeError):
        raise error from None
    logger.info("[json-repair:llm] last-resort LLM repair recovered a JSON parse")
    return obj
