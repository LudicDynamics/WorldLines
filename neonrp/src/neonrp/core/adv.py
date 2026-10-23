"""The ADV output shape, in three languages (抛弃 JSON;提示词 en / ja / zh 由引擎按世界语言切换).

Short definitions + an EXAMPLE OUTPUT, the way the reference spec is written. Templates append their
own op lines to the <ops> definition; everything else here is shared by every template.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from neonrp import prompts as _prompts

LANGS = ("zh", "en", "ja", "ko")

_HIRA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_HAN = re.compile(r"[\u4e00-\u9fff]")


def world_lang(root: Path) -> str:
    """zh | en | ja for the callers that only carry those three (a ko world reads as en, as before). New code uses
    ``output_lang.prompt_lang`` (keeps ko)."""
    v = world_lang_raw(root)
    return "en" if v == "ko" else v


_RUN_STAMP = re.compile(r"-\d{8}-\d{6}$")


def world_lang_raw(root: Path) -> str:
    """zh | en | ja | ko — manifest.json lang → playthrough lang → folder suffix → the lore text's script."""
    for cand in (root / "manifest.json", root / "playthrough.json"):
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k in ("lang", "language", "source_lang"):
            v = str(d.get(k) or "").lower()[:2]
            if v in LANGS or v == "ko":
                return v
    # a played copy is "<world>-YYYYMMDD-HHMMSS": the world's language suffix sits before the timestamp
    name = _RUN_STAMP.sub("", root.name.lower())
    for sfx, lang in (("-en", "en"), ("-ja", "ja"), ("-ko", "ko"), ("-zh", "zh")):
        if name.endswith(sfx):
            return lang
    try:
        text = next((p for p in (root / "game" / "lore").glob("*.md")), None)
        sample = text.read_text(encoding="utf-8")[:2000] if text else ""
    except OSError:
        sample = ""
    if not sample:  # no lore: the world's own one-line summary (the opening may carry all four languages)
        try:
            gs = json.loads((root / "game" / "meta" / "game-start.json").read_text(encoding="utf-8"))
            sample = " ".join(str(gs.get(k) or "") for k in ("summary", "name"))[:2000] if isinstance(gs, dict) else ""
        except (OSError, ValueError):
            sample = ""
    if _HIRA.search(sample):
        return "ja"
    if _HANGUL.search(sample):
        return "ko"
    if sample and len(_HAN.findall(sample)) < 20:
        return "en"
    return "zh"


# ── the run's language (an English line turned Elena and the narrator English) ──────
_LANG_NAMES = _prompts.by_lang("adv", "_LANG_NAMES")
_LANG_RULE = _prompts.by_lang("adv", "_LANG_RULE")
_SOUL_LANG = _prompts.by_lang("adv", "_SOUL_LANG")
_CROSS_LANG = _prompts.by_lang("adv", "_CROSS_LANG")


def run_lang(root: Path) -> str:
    """The language this run is played in: the run's explicit output_lang (bound when the player picked one), else the
    world's — ``output_lang.prompt_lang`` (one source for every prompt)."""
    from neonrp.core.output_lang import prompt_lang

    return prompt_lang(Path(root))


def lang_rule(root: Path, prompt_lang: str, *, soul: bool = False) -> str:
    """One sentence, in the prompt's own language, pinning the output to the run's language (not the player's line)."""
    pl = prompt_lang if prompt_lang in _LANG_RULE else "zh"
    name = _LANG_NAMES[pl].get(run_lang(root), _LANG_NAMES[pl]["zh"])
    return (_SOUL_LANG if soul else _LANG_RULE)[pl].format(name=name)


def narrate_lang_line(root: Path, prompt_lang: str) -> str:
    """The language line for the narrating calls (C3-2, 10-06): the run's language, and — when the player picked a
    language other than the one the world was written in — that the world's text is only material. Without it a
    Chinese-authored world narrated in Chinese even though the player chose ja / en / ko.
    Empty when the run is in the world's own language: those prompts stay exactly as they were."""
    pl = prompt_lang if prompt_lang in _LANG_RULE else "zh"
    run = run_lang(root)
    try:
        src = world_lang_raw(root)
    except Exception:  # noqa: BLE001
        src = run
    if not src or src == run or src not in _LANG_NAMES[pl]:
        return ""
    return lang_rule(root, pl) + " " + _CROSS_LANG[pl].format(name=_LANG_NAMES[pl].get(run, run), src=_LANG_NAMES[pl][src])


def soul_lang_line(root: Path) -> str:
    """The same for a character's own turn (C3-2, 10-06): an away character's lines are shown as she wrote them, so a
    Chinese-authored soul in a ko run wrote Chinese. Empty when the run is in the world's own language."""
    from neonrp.core.output_lang import prompt_lang

    pl = prompt_lang(Path(root))
    pl = pl if pl in _LANG_RULE else "zh"
    run = run_lang(root)
    try:
        src = world_lang_raw(root)
    except Exception:  # noqa: BLE001
        src = run
    if not src or src == run or src not in _LANG_NAMES[pl]:
        return ""
    return lang_rule(root, pl, soul=True) + " " + _CROSS_LANG[pl].format(name=_LANG_NAMES[pl].get(run, run), src=_LANG_NAMES[pl][src])


def lang_of_text(text: str, default: str = "zh") -> str:
    """The player's language, from one line (used to keep the reply in the player's language)."""
    if _HIRA.search(text or ""):
        return "ja"
    if _HANGUL.search(text or ""):
        return "ko"
    if text and not _HAN.search(text):
        return "en"
    return "zh" if text else default


# ── the spec, per language ────────────────────────────────────────────────────

SPEC: dict[str, dict[str, str]] = _prompts.by_lang("adv", "SPEC")

NONE_WORDS = ("无变化", "none", "变化なし", "変化なし", "no change", "无", "변화 없음", "없음")
_NONE_WORD = {"zh": "无变化", "en": "none", "ja": "変化なし", "ko": "변화 없음"}


DEFAULT_BLOCKS = ("lines", "ops", "options")  # cot is a pack's choice (不一定要以 cot 开头); the parser reads blocks in any order


def adv_format(lang: str, ops_lines: str, *, inline: bool = True, blocks: tuple[str, ...] = DEFAULT_BLOCKS,
               panels: dict[str, Any] | None = None) -> str:
    """The format section for a system prompt: definitions for the blocks this pack asks for, the template's op
    lines, and an example trimmed to the same blocks. ``panels`` = extra blocks a layer draws (formation …): name →
    doc (str or {lang: str}); shown to the player as a monospace card, never parsed as state."""
    s = SPEC.get(lang) or SPEC["zh"]
    parts = [s["head"]]
    none_word = _NONE_WORD.get(lang, "无变化")
    for b in blocks:
        if b == "ops":
            parts.append(s["ops"] + "\n" + ops_lines.rstrip() + "\n" + none_word)
        elif b in s:
            parts.append(s[b])
        elif panels and b in panels:
            doc = panels[b]
            parts.append(f"{b}:" + str(doc.get(lang) or doc.get("zh") or "" if isinstance(doc, dict) else doc))
    if inline and "lines" in blocks:
        parts.append(s["inline"])
    parts.append("\n" + s["example_title"] + "\n" + example_for(lang, blocks))
    return "\n".join(parts) + "\n"


def example_for(lang: str, blocks: tuple[str, ...]) -> str:
    """The EXAMPLE OUTPUT with only the requested blocks, in the requested order."""
    ex = (SPEC.get(lang) or SPEC["zh"])["example"]
    found = {m.group(1): m.group(0) for m in re.finditer(r"<(cot|lines|ops|options)>.*?</\1>", ex, re.DOTALL)}
    return "\n".join(found[b] for b in blocks if b in found)


# ── the <ops> lines, generated from the registry (不写死;pack 时从表里整理) ──

_VAR_LINE = _prompts.by_lang("adv", "_VAR_LINE")
_FIELD_HINT = _prompts.by_lang("adv", "_FIELD_HINT")


# the ops a state transition (core/turn_v3, prompts/transition) already teaches by name: variables, the open schema,
# files, places, people's whereabouts. Every other world-side op is the rule pack's own (pack_ops_lines).
GENERIC_STATE_OPS = frozenset({"set", "add", "flag", "new", "patch", "remove", "new_npc", "move", "move_to", "write", "edit",
                               "rm", "mkdir", "rmdir", "new_location", "new_town", "link", "unlink", "define"})


def ops_lines(reg: Any, lang: str, *, exclude: frozenset[str] = frozenset()) -> str:
    """One line per registered world-side op, rendered by kind: action → `op <fields>`, update → the variable line /
    `flag <key>` / `patch …`, tool and request → `[op <fields>]`. Docs come from the op's doc / doc_i18n. ``exclude``:
    ops left out (the variable line goes with ``set``)."""
    hints = _FIELD_HINT.get(lang) or {}
    lines: list[str] = []
    writable = [k for k, v in reg.variables.items() if not v.readonly]
    example_var = next((v for v in writable if v.startswith("player.")), writable[0] if writable else "x.y")
    var_line_done = "set" in exclude
    for a in reg.actions.values():
        if a.scope != "world" or not a.enabled or a.op in exclude:
            continue
        if a.op in ("set", "add"):
            if not var_line_done:
                lines.append((_VAR_LINE.get(lang) or _VAR_LINE["zh"]).format(var=example_var))
                var_line_done = True
            continue
        name = a.alias or a.op
        args = " ".join(f"<{hints.get(f, f)}>" for f in a.fields)
        head = f"{name} {args}".strip()
        if a.kind in ("tool", "request"):
            head = f"[{head}]" if a.waits() else f"[~{head}]"  # sync = [op] (the prose stops), async = [~op] (fired, not awaited)
        elif a.kind == "mode":
            head = f"[{name} …]…[/{name}]"  # a layer switch waits ([combat 山贼×3]交接[/combat])
        doc = a.doc_for(lang)
        lines.append(f"{head:<24} {doc}" if doc else head)
    return "\n".join(lines)


def pack_ops_lines(reg: Any, lang: str) -> str:
    """The rule pack's own state-changing ops (world-side actions and updates the state transition does not already
    teach — a phase, a vote, a trade …), one line each as in :func:`ops_lines`; '' when the pack has none. A state
    transition writes these as ops, never as a variable line (10-19: a table phase written as a variable is refused)."""
    from types import SimpleNamespace

    own = {k: a for k, a in reg.actions.items() if a.kind in ("action", "update")}
    return ops_lines(SimpleNamespace(actions=own, variables=reg.variables), lang, exclude=GENERIC_STATE_OPS)


# ── user-block headings (the parts of the user message the engine writes) ────

HEAD: dict[str, dict[str, str]] = _prompts.by_lang("adv", "HEAD")


def render_prev(prev: Any, lang: str) -> str:
    """The previous output shown back to the model, in its own shape (ADV blocks, never JSON for an ADV turn)."""
    fmt = str(getattr(prev, "fmt", "") or "")
    if fmt.startswith("adv"):
        ops = "\n".join(_op_line(o) for o in (getattr(prev, "ops", None) or [])) or _NONE_WORD.get(lang, NONE_WORDS[0])
        return f"<lines>\n{getattr(prev, 'narration', '')}\n</lines>\n<ops>\n{ops}\n</ops>"
    return json.dumps({"narration": getattr(prev, "narration", ""), "ops": getattr(prev, "ops", [])}, ensure_ascii=False)


def _op_line(o: dict[str, Any]) -> str:
    op = o.get("op")
    if op == "move_to":
        return f"move {o.get('who')} {o.get('to')}"
    if op == "add":
        d = o.get("delta")
        return f"{o.get('var')} {'+' if isinstance(d, (int, float)) and d >= 0 else ''}{d}"
    if op == "set":
        return f"{o.get('var')} {o.get('value')}"
    if op == "flag":
        return f"flag {o.get('key')}"
    if op == "need":
        return f"[ask {o.get('who')}]"
    if op == "new":
        return f"new {o.get('class')} {o.get('name')}"
    return " ".join([str(op)] + [str(v) for k, v in o.items() if k not in ("op", "await", "args") and not str(k).startswith("_")])


# ── prompt entries: the creator's layer, in manifest.json["prompt"] (< game/meta/prompt.json) ──────────
#
#   "prompt": {
#     "lang": "zh",
#     "rules":  {"zh": "…替换整段规则…"},               # optional: replaces the template's rules text
#     "voice":  "第二人称、克制…",                       # optional: replaces agents/world-agent/voice.md
#     "blocks": ["lines", "ops", "options"],           # optional: the ADV blocks asked for
#     "ops_docs": {"move_to": {"zh": "…", "en": "…"}},  # optional: per-op doc overrides
#     "examples": [{"user": "我推开门", "assistant": "<lines>\n一只手抓住了你的手腕。\n</lines>"}],  # 示例对话: sent as chat turns before the history
#     "entries": [                                     # 条目 (Yumina-style): what the model reads
#       {"id": "world", "text": "灰雾北境…", "when": "always"},                      # in the system prompt, after the voice
#       {"id": "tavern", "text": "河灯旅店的规矩…", "when": {"keyword": ["旅店", "米拉"]}},  # injected next to the player's line when matched
#       {"id": "post", "text": "台词短。", "when": "post"}                            # the very end of the system prompt (highest attention)
#     ]
#   }

def merge_prompt_spec(base: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """Layer one prompt spec over another: entries merge by id ({"id": x, "text": null} removes), ops_docs merge per op, the rest replaces."""
    out = dict(base)
    for k, v in p.items():
        if k == "entries" and isinstance(v, list):
            byid = {e.get("id"): e for e in out.get("entries", []) if isinstance(e, dict)}
            for e in v:
                if isinstance(e, dict):
                    if e.get("text") is None and e.get("id") in byid:
                        byid.pop(e["id"], None)
                    else:
                        byid[e.get("id") or f"e{len(byid)}"] = e
            out["entries"] = list(byid.values())
        elif k in ("player_gate", "place_fix") and isinstance(v, dict):  # per field, so a world can change one line of a template's setting
            out[k] = {**(out.get(k) or {}), **v}
        elif k == "ops_docs" and isinstance(v, dict):
            od = dict(out.get("ops_docs", {}))
            for op, doc in v.items():
                od[op] = {**(od.get(op) or {}), **(doc if isinstance(doc, dict) else {"zh": str(doc)})}
            out["ops_docs"] = od
        else:
            out[k] = v
    return out


def prompt_spec(root: Path) -> dict[str, Any]:
    """Three layers: the template pack's ``prompt`` (pack.json) < manifest.json["prompt"] < game/meta/prompt.json."""
    from neonrp.core.paths import get_data_dir_name

    out: dict[str, Any] = {}
    try:
        from neonrp.packs import resolve as _resolve_pack

        out = merge_prompt_spec(out, dict(_resolve_pack(root).prompt_spec or {}))
    except Exception:  # noqa: BLE001 — a world without a resolvable pack still gets its own entries
        pass
    for cand in (root / "manifest.json", root / get_data_dir_name(root) / "meta" / "prompt.json"):
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        p = d.get("prompt") if cand.name == "manifest.json" else d
        if isinstance(p, dict):
            out = merge_prompt_spec(out, p)
    return out


def _text_for(e: dict[str, Any], lang: str) -> str:
    t = e.get("text")
    if isinstance(t, dict):
        return str(t.get(lang) or t.get("zh") or next(iter(t.values()), ""))
    return str(t or "")


_PH_VAR = re.compile(r"\{([A-Za-z_][\w.]*)\}")


def _fill_vars(text: str, reg: Any) -> str:
    """Only registered variable names are replaced; anything else in braces stays as written."""
    def sub(m: "re.Match[str]") -> str:
        v = reg.variables.get(m.group(1)) if getattr(reg, "variables", None) else None
        return str(v.value) if v is not None and v.value is not None else m.group(0)
    return _PH_VAR.sub(sub, text)


def entries_for(spec: dict[str, Any], lang: str, *, texts: str = "", reg: Any = None) -> dict[str, list[str]]:
    """always / post / conditional entry texts. ``when`` is "always" | "post" | a condition in the triggers' IF grammar
    ({"keyword": …} is sugar for {"text": …}; {"at": "T001/inn"} · {"var": "town.alert", ">=": 3} · {"flag": …} ·
    {"entry": …, "prop": …} · {"any": […]} bind an entry to the world's schema). Conditional entries need ``reg``
    (the registry snapshot at pack time) and match keywords against ``texts`` (the player's line + recent narration)."""
    out: dict[str, list[str]] = {"always": [], "post": [], "keyword": []}
    for e in spec.get("entries") or []:
        if not isinstance(e, dict) or e.get("enabled") is False:
            continue
        when = e.get("when", "always")
        text = _text_for(e, lang).strip()
        if reg is not None and "{" in text:  # Template v3 named-prompt placeholders: {var.name} → its current value
            text = _fill_vars(text, reg)
        if not text:
            continue
        if when == "always":
            out["always"].append(text)
        elif when == "post":
            out["post"].append(text)
        elif isinstance(when, dict) and when:
            cond = dict(when)
            if "keyword" in cond:
                cond = {"text": cond.pop("keyword"), **({"in": cond["in"]} if "in" in cond else {})}
            if reg is None and set(cond) != {"text"} and set(cond) != {"text", "in"}:
                continue  # schema-bound entry without a registry: cannot judge
            if reg is None:
                kws = [cond["text"]] if isinstance(cond["text"], str) else list(cond["text"])
                if any(str(k).lower() in (texts or "").lower() for k in kws if k):
                    out["keyword"].append(text)
                continue
            from neonrp.core.triggers import _cond as _judge, snapshot

            snap = snapshot(reg)
            ok, _why = _judge(reg, cond, snap, snap, {"player": texts or "", "narration": texts or ""}, {})
            if ok:
                out["keyword"].append(text)
    return out


def assemble(root: Path, reg: Any, *, rules: str, lang: str, blocks: tuple[str, ...], tail: str = "", voice: str = "") -> str:
    """A world-side system prompt = rules (manifest may replace) + voice + always-on entries + the ADV format
    (ops lines from the registry, docs overridable per op) + tail + post entries."""
    spec = prompt_spec(root)
    r = spec.get("rules")
    if isinstance(r, dict):
        rules = str(r.get(lang) or r.get("zh") or rules)
    elif isinstance(r, str) and r.strip():
        rules = r
    v = spec.get("voice")
    if isinstance(v, dict):
        voice = str(v.get(lang) or v.get("zh") or voice)
    elif isinstance(v, str) and v.strip():
        voice = v
    if isinstance(spec.get("blocks"), list) and spec["blocks"]:
        blocks = tuple(str(b) for b in spec["blocks"])
    reg_view = reg
    if isinstance(spec.get("ops_docs"), dict):  # per-op doc overrides, without touching the registry
        import copy

        reg_view = copy.copy(reg)
        reg_view.actions = {k: copy.copy(a) for k, a in reg.actions.items()}
        for op, docs in spec["ops_docs"].items():
            if op in reg_view.actions and isinstance(docs, dict):
                a = reg_view.actions[op]
                a.doc_i18n = {**a.doc_i18n, **{str(k): str(x) for k, x in docs.items()}}
                if "zh" in docs:
                    a.doc = str(docs["zh"])
    ents = entries_for(spec, lang, reg=reg)
    ents = {**ents, "keyword": []}  # conditional entries are injected next to the player's line (turn_v3), not here
    voice_block = ((voice if voice.lstrip().startswith("#") else f"## 世界文风\n{voice}") + "\n\n") if voice else ""
    always = ("\n\n".join(ents["always"]) + "\n\n") if ents["always"] else ""
    post = ("\n\n" + "\n\n".join(ents["post"])) if ents["post"] else ""
    return rules + "\n\n" + voice_block + always + adv_format(lang, ops_lines(reg_view, lang), blocks=blocks) + "\n" + tail + post


# ── the world's own CONTEXT.md: the pack and the output format, written into the world folder ──────

_CONTEXT_DOC = _prompts.by_lang("adv", "_CONTEXT_DOC")


def context_doc(root: Path, reg: Any, lang: str | None = None) -> str:
    """CONTEXT.md for a world folder: the pack, the output format and the tag grammar, with this world's ops."""
    from neonrp.packs import resolve as _resolve_pack

    lang = lang or world_lang(root)
    spec = prompt_spec(root)
    blocks = tuple(spec.get("blocks") or _resolve_pack(root).blocks)
    doc = _CONTEXT_DOC.get(lang) or _CONTEXT_DOC["zh"]
    return doc.format(blocks=adv_format(lang, ops_lines(reg, lang), blocks=blocks).rstrip(), ops=ops_lines(reg, lang))


def write_context_doc(root: Path, reg: Any | None = None) -> Path:
    from neonrp.core.registry import load_registry

    p = Path(root) / "CONTEXT.md"
    p.write_text(context_doc(Path(root), reg or load_registry(Path(root))), encoding="utf-8")
    return p


# ── section markers: the output sections can be marked three ways; one engine setting picks which ──
SECTION_NAMES = ("cot", "lines", "ops", "options")
SECTION_STYLES = ("xml", "divider", "fence")
_STYLE_SAY = _prompts.inner_lang("adv", "_STYLE_SAY")


def restyle(text: str, style: str, lang: str = "zh") -> str:
    """Rewrite whole-line section markers <lines> … </lines> into the chosen style; everything else (requests, actions,
    engine messages) is untouched. The style sentence is added under the format heading when there is one."""
    if style not in ("divider", "fence") or not text:
        return text
    names = "|".join(SECTION_NAMES)
    if style == "divider":
        text = re.sub(rf"(?m)^[ \t]*<({names})>[ \t]*$", lambda m: f"=== {m.group(1)} ===", text)
        text = re.sub(rf"(?m)^[ \t]*</({names})>[ \t]*\n?", "", text)
    else:
        text = re.sub(rf"(?m)^[ \t]*<({names})>[ \t]*$", lambda m: f"```{m.group(1)}", text)
        text = re.sub(rf"(?m)^[ \t]*</({names})>[ \t]*$", "```", text)
    say = (_STYLE_SAY.get(style) or {}).get(lang) or _STYLE_SAY[style]["zh"]
    for head in ("## 输出格式", "## Output format", "## 出力形式"):
        i = text.find(head)
        if i >= 0:
            j = text.find("\n", text.find("\n", i) + 1)
            text = text[: j + 1] + say + "\n" + text[j + 1:] if j > 0 else text + "\n" + say
            break
    return text


# ── how an async op is marked: <map> (angle, default) or [~map] (square + tilde) ─────────────────────

ASYNC_MARKS = ("angle", "tilde")
_ASYNC_SAY = _prompts.inner_lang("adv", "_ASYNC_SAY")


def async_restyle(text: str, mark: str, fire: set[str] | frozenset[str], lang: str = "zh") -> str:
    """Rewrite the async ops the model is taught (<move player inn>…</move>, <flag paid>, <map>) into the chosen mark,
    and say once, under the format heading, which bracket waits. ``fire`` = op names (and aliases) the registry says
    are not awaited; engine messages (<say>, <event>, <roll 1d6>4</roll>) are never touched."""
    if not text or mark not in ASYNC_MARKS:
        return text
    if mark == "angle":  # the comparison arm: the taught form [~op …] back to <op …>
        text = re.sub(r"\[~\s*([A-Za-z_][\w.\-]*)([^\[\]\n]*)\]", lambda m: f"<{m.group(1)}{m.group(2).rstrip()}>", text)
    if mark == "tilde" and fire:
        names = "|".join(sorted((re.escape(n) for n in fire), key=len, reverse=True))
        nm = rf"(?:{names}|[A-Za-z_]\w*\.[\w.]+)"
        text = re.sub(rf"<({nm})((?:\s[^<>\n]*)?)>(.*?)</\1\s*>", lambda m: f"[~{m.group(1)}{m.group(2) or ''}]{m.group(3)}", text, flags=re.DOTALL)
        text = re.sub(rf"<({nm})((?:\s[^<>\n]*)?)\s*/?>", lambda m: f"[~{m.group(1)}{(m.group(2) or '').rstrip()}]", text)
    say = (_ASYNC_SAY.get(mark) or {}).get(lang) or _ASYNC_SAY[mark]["zh"]
    if say in text:
        return text
    for head in ("## 输出格式", "## Output format", "## 出力形式"):
        i = text.find(head)
        if i >= 0:
            j = text.find("\n", text.find("\n", i) + 1)
            return text[: j + 1] + say + "\n" + text[j + 1:] if j > 0 else text + "\n" + say
    return text
