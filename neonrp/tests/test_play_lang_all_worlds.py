"""Every world plays in every language (10-16:「Hub 切到日文版,点灰橡宅,进去就变成英文」).

A run started in ``lang`` is in ``lang`` end to end: the run's own language, the opening and its choices, the world view
the model reads each turn (``sdk.render_pack``), the op list and the variable docs, the "where is this character" line
of the play page — no line in another language (proper nouns are the deep lint's job: test_template_i18n_worlds.py).
And the Hub hands its language to the local play page (another origin: it cannot read the Hub's storage)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from neonrp import template
from _paths import PRODUCT

ROOT = Path(__file__).resolve().parents[1]
TPLS = PRODUCT / "templates"
WORLDS = sorted(p.name[: -len(".template")] for p in TPLS.glob("*.template") if (p / "template.json").is_file())
LANGS = ("zh", "en", "ja", "ko")

_KANA, _HAN, _HANG = re.compile(r"[぀-ヿ]"), re.compile(r"[一-鿿]"), re.compile(r"[가-힯]")
_ZH_ONLY = re.compile(r"[你们这边吗呢么说过没给让该从对还]|的")  # Chinese function words: a Chinese sentence, even with a katakana name
_ID_LINE = re.compile(r"^[-*#\s]*[\w./:@+\-]+(\s+[\w./:@+\-]+)*\s*(true|false|\d+)?\s*$")  # ids, paths, flags, file lists


def _lang_of(line: str) -> str:
    k, h, g = len(_KANA.findall(line)), len(_HAN.findall(line)), len(_HANG.findall(line))
    if g >= 2 and g >= k:
        return "ko"
    if k >= 2:
        return "zh" if len(_ZH_ONLY.findall(line)) >= 3 else "ja"
    if h >= 4:
        return "zh"
    if h + k + g == 0 and len([w for w in re.findall(r"[A-Za-z]+", line) if len(w) >= 3]) >= 5:
        return "en"
    return ""


def _other(line: str, lang: str) -> str:
    """The other language a line is in ('' = this language, or nothing to tell)."""
    got = _lang_of(line)
    if lang == "ja" and got == "zh" and len(_ZH_ONLY.findall(line)) < 2:
        got = ""  # a kanji-only Japanese line
    return got if got != lang else ""


def foreign_lines(text: str, lang: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 16 or _ID_LINE.match(line) or line.endswith(".json") or ".json " in line:
            continue
        got = _other(line, lang)
        if got:
            out.append(f"[{got}] {line[:120]}")
    return out


def _build(tmp_path: Path, world: str, lang: str) -> Path:
    root = tmp_path / "run"
    template.build(template.load(TPLS / f"{world}.template"), root, lang=lang)
    return root


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("world", WORLDS)
def test_a_run_reads_in_its_own_language(tmp_path, world, lang):
    from neonrp.core import sdk
    from neonrp.core.adv import ops_lines
    from neonrp.core.output_lang import pick_opening, prompt_lang, resolve_output_lang
    from neonrp.core.paths import get_game_dir
    from neonrp.core.registry import load_registry

    import json

    root = _build(tmp_path, world, lang)
    assert resolve_output_lang(root) == lang and prompt_lang(root) == lang
    gs = json.loads((get_game_dir(root) / "meta" / "game-start.json").read_text(encoding="utf-8"))
    scene, choices = pick_opening(gs.get("startup"), lang)
    assert scene and _lang_of(scene) == lang, scene[:80]
    assert not [c for c in choices if _other(c, lang)], choices
    reg = load_registry(root)
    text = "\n".join([sdk.render_pack(sdk.pack(root)), ops_lines(reg, lang), *(v.doc for v in reg.variables.values() if v.doc)])
    bad = foreign_lines(text, lang)
    assert not bad, bad[:8]


@pytest.mark.parametrize("lang", LANGS)
def test_the_where_line_of_the_play_page_follows_the_run(tmp_path, lang):
    """/state souls[].where was a fixed Chinese 「就在你身边」 in every run (10-16)."""
    from neonrp import prompts

    s = prompts.strings("soul_where", lang)
    assert set(s) == {"here_at", "here", "away_active", "away"} and all("{place}" in s[k] for k in ("here_at", "away_active", "away"))
    for k, v in s.items():
        assert not _other(v, lang), (k, v)
    src = (ROOT / "src" / "neonrp" / "commands" / "web.py").read_text(encoding="utf-8")
    assert "就在你身边" not in src and "没注意到你来了" not in src


@pytest.mark.parametrize("pack", ["rpg", "werewolf", "monopoly"])
def test_every_op_doc_has_four_languages(pack):
    """The op list goes to the model each turn: a ko run read rpg's in English, werewolf / monopoly's were Chinese (10-16)."""
    import importlib

    mod = importlib.import_module(f"neonrp.packs.{pack}.pack")
    for a in mod.ACTIONS:
        assert a.doc and {"en", "ja", "ko"} <= set(a.doc_i18n), (pack, a.op)
        for lg in ("en", "ko"):
            assert not _HAN.search(a.doc_for(lg)), (pack, a.op, lg, a.doc_for(lg))


@pytest.mark.skipif(not (PRODUCT / "ui" / "app" / "hub" / "hub.js").is_file(), reason="the Hub source is not in the open repo")
def test_the_hub_hands_its_language_to_the_local_play_page():
    """The local play page (the engine's /local) is another origin than the Hub: it cannot read the Hub's wl.hub.lang,
    so every link / start into it carries ``lang`` (10-16: a ja Hub opened 灰橡宅 in English)."""
    js = (PRODUCT / "ui" / "app" / "hub" / "hub.js").read_text(encoding="utf-8")
    assert "/local?tpl=${" not in js  # every /local link is built with URLSearchParams({ tpl, lang })
    assert js.count("/local?${new URLSearchParams({ tpl: x.id, lang })}") == 2
    assert "avatar: 'current', output_lang: lang" in js
    builder = (PRODUCT / "ui" / "app" / "src" / "builder.js").read_text(encoding="utf-8")
    assert "localStorage.getItem('wl.hub.lang')" in builder


def test_a_save_keeps_the_language_it_was_built_in(tmp_path, monkeypatch):
    """Resuming a run asks for another language (a Japanese Hub continuing an English save — iOS 10-16: the opening
    stayed English and the narration would switch to Japanese): the run keeps its own language, the answer says so
    (``lang_kept``) for the page to offer a new run, and the saves list carries each run's language."""
    import json
    import shutil
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server
    from neonrp.core.output_lang import built_lang, resolve_output_lang

    store = tmp_path / "store"
    shutil.copytree(TPLS / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "slug": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(method, path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"{}")

        try:
            en = call("POST", "/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "en"})
            run = server.runtime.root
            assert built_lang(run) == "en" and "lang_kept" not in en
            call("POST", "/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "ja"})   # another run, so the next bind resumes
            back = call("POST", "/api/v1/play/session", {"slug": run.name, "output_lang": "ja"})
            assert back.get("lang_kept") is True and back["lang"] == "en" and back["lang_requested"] == "ja"
            assert server.runtime.root == run and resolve_output_lang(run) == "en"
            same = call("POST", "/api/v1/play/session", {"slug": run.name, "output_lang": "en"})
            assert "lang_kept" not in same
            rows = {s["session_id"]: s.get("lang") for s in call("GET", "/api/v1/play/saves")["saves"]}
            assert rows[run.name] == "en" and "ja" in rows.values()
        finally:
            server.shutdown()


@pytest.mark.skipif(not (PRODUCT / "ui" / "player" / "src").is_dir(), reason="the standard front end (ui/player) is not in the open repo")
def test_the_player_offers_a_new_run_when_a_save_keeps_its_language():
    src = (PRODUCT / "ui" / "player" / "src")
    app, i18n = (src / "app.js").read_text(encoding="utf-8"), (src / "i18n.js").read_text(encoding="utf-8")
    assert "r.lang_kept" in app and "function langKept" in app
    for key in ("langKept:", "langKeep:", "langNew:", "langNames:"):
        assert i18n.count(key) == 4, key


def test_werewolf_endings_and_engine_feedback_are_not_fixed_chinese():
    """werewolf's ending titles were 好人胜 / 狼人胜 in every run; the engine's refusals / audits / judge questions to the
    model are English in every run (the narrator writes in the run's language), a refusal the player sees is in theirs."""
    from neonrp import prompts
    from neonrp.packs.werewolf.pack import TRIGGERS

    for t in TRIGGERS.values():
        title = t["then"][0]["title"]
        assert isinstance(title, dict) and set(title) >= set(LANGS), title
    for lg in LANGS:
        s = prompts.strings("economy", lg)
        assert all(s[k] for k in ("rf_no_money", "rf_stock_low", "rf_have_only")), lg
    from test_prompt_i18n import _cjk_string_lines

    now = _cjk_string_lines()  # string literals with CJK (docstrings / comments aside)
    for f in ("core/turn_plan.py", "packs/rpg/atlas/fix.py", "packs/rpg/writers.py", "packs/rpg/atlas/__init__.py"):
        assert not now.get(f), f
