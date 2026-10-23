"""音乐库接进 NeonRP(10-15,niko「我们的 neonrp 请接上音乐库」;core/audio.py · worldlines/audio/)。

① 平台池:每个文件都在、哈希对得上、只有 CC0 / CC-BY(魔王魂 / Suno / licensed 一个都不带),CC-BY 的在 CREDITS 里署名
② 8 个官方世界都配了主题曲,lint 没有 audio.* 的 block
③ 不写也有声音:合约给主题曲、地名猜环境音;作者写了的优先(template places · location.json · 阶段 · 触发)
④ 情绪:掉血 / 掉理智 → tense,撑两拍再回落;血少 / 战斗 → crisis;最后一个阶段 → tense 打底
⑤ audio.cue 只在变化时发,和别的拍事件同一路(traces → beat_events → /events);GET engine/audio 给当前一份 + 鸣谢
⑥ lint:id 不存在 / 文件缺 → block;自带音频没署名:默认区 block、自由区 warn
⑦ 文件:URL 带内容哈希 → 一年 immutable;支持 Range(Safari / WKWebView 播媒体要它)
全部不调模型。"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import audio, beat_events, sdk
from neonrp.core.registry import load_registry

WORLDS = {"guixiang": "guixiang", "wuwu": "wuwu", "last-train": "firstsnow", "pct-house": "whitechapel",
          "stoneford-town": "emberglass", "kagura-island": "guixiang", "spice-witch": "wuwu", "neon-rebirth": "divergence"}


def _run(name: str, tmp_path: Path, tdir: Path | None = None) -> Path:
    dest = tmp_path / f"run-{name}"
    TP.build(TP.load(tdir or PRODUCT_TEMPLATES / f"{name}.template"), dest)
    return dest


def _copy(name: str, tmp_path: Path) -> Path:
    d = tmp_path / "store" / f"{name}.template"
    shutil.copytree(PRODUCT_TEMPLATES / f"{name}.template", d)
    return d


def _edit(p: Path, fn) -> None:
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply(root: Path, turn: int, ops: list | None = None, says: str = ""):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


# ── ① the pool ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_pool_files_hashes_and_licenses():
    d = audio.pool_dir()
    assert d is not None and d.name == "audio"
    tracks = audio.catalog()["tracks"]
    assert {t["kind"] for t in tracks} == {"music", "ambient", "sfx"}
    total = 0
    for t in tracks:
        b = (d / t["file"]).read_bytes()
        assert hashlib.sha256(b).hexdigest()[:10] == t["sha"], t["file"]
        assert t["bytes"] == len(b) and t["license"] in ("CC0-1.0", "CC-BY-4.0") and t["source"].startswith("https://")
        assert not t["id"].startswith("canvas-") and "maou" not in t["file"].lower() and "suno" not in t["title"].lower()
        total += len(b)
    assert total <= 22 * 1024 * 1024, "lead 10-15: 16–22 MB in the wheel"
    on_disk = {p.relative_to(d).as_posix() for p in d.rglob("*.mp3")}
    assert on_disk == {t["file"] for t in tracks}, "every file is catalogued, every entry has its file"
    credits = (d / "CREDITS.md").read_text(encoding="utf-8")
    for t in tracks:
        assert t["file"] in credits
        if t["license"] == "CC-BY-4.0":
            assert f"**{t['title']}** by {t['artist']}" in credits
    assert {t["id"] for t in tracks if t["license"] == "CC-BY-4.0"} == {"whitechapel", "city-night", "bell-church"}


def test_credits_put_cc_by_first():
    rows = audio.credits()
    assert [r["license"] for r in rows[:3]] == ["CC-BY-4.0"] * 3
    assert all(r["kind"] in ("music", "ambient") for r in rows)


# ── ② the eight official worlds ──────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,theme", sorted(WORLDS.items()))
def test_official_worlds_have_a_theme_and_lint_clean(name, theme):
    t = TP.load(PRODUCT_TEMPLATES / f"{name}.template")
    assert t.data["audio"]["theme"] == theme
    probs = [p for p in audio_problems(t) if p[0] == "block"]
    assert not probs, probs


def audio_problems(t):
    return TP._lint_audio(t)


def test_a_run_opens_with_its_theme(tmp_path):
    root = _run("guixiang", tmp_path)
    cue = audio.current(root)
    assert cue["mood"] == "calm" and cue["music"]["id"] == "guixiang"
    assert cue["music"]["url"].startswith("/api/v1/audio/music/guixiang.") and cue["music"]["url"].endswith(".mp3")
    assert cue["ambient"] is not None and cue["credits"]


# ── ③ defaults and the author's lines ────────────────────────────────────────────────────────────────────────────────

def test_without_audio_the_contract_and_the_place_decide(tmp_path):
    d = _copy("wuwu", tmp_path)
    _edit(d / "template.json", lambda j: j.pop("audio"))
    root = _run("wuwu", tmp_path, d)
    _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/berth7"}])
    cue = audio.current(root)
    assert cue["music"]["id"] == "tense", "mystery-trpg's default theme (catalog defaults)"
    assert cue["ambient"]["id"] == "harbor-waves", "7号码头 · dock → the harbour bed"


def test_moving_changes_the_bed_and_only_a_change_is_a_cue(tmp_path):
    root = _run("guixiang", tmp_path)
    r = _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/hall"}])
    assert r.audio and r.audio["ambient"]["id"] == "fireplace" and r.audio["music"]["id"] == "guixiang"
    assert not _apply(root, 2).audio, "nothing changed → no cue"
    r = _apply(root, 3, [{"op": "move_to", "who": "player", "to": "T001/well"}])
    assert r.audio["ambient"]["id"] == "cellar-drip", "老井 → the drip (a guess from the name)"


def test_location_json_audio_wins_and_inherits(tmp_path):
    d = _copy("wuwu", tmp_path)
    _edit(d / "world" / "game" / "locations" / "T001" / "location.json", lambda j: j.update(audio={"ambient": "storm", "bgm": "calm"}))
    root = _run("wuwu", tmp_path, d)
    _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/workshop"}])
    cue = audio.current(root)
    assert cue["ambient"]["id"] == "storm", "a line the author wrote (the town's) beats a guess from the name (工坊 → forge)"
    assert cue["music"]["id"] == "calm" and cue["by"] == "place", "the town's bgm reaches the places inside it"


def test_silence_rests_the_music(tmp_path):
    d = _copy("pct-house", tmp_path)
    _edit(d / "template.json", lambda j: j["audio"]["places"].update({"T001/cellar": {"bgm": "silence", "ambient": "none"}}))
    root = _run("pct-house", tmp_path, d)
    r = _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/cellar"}])
    assert r.audio["music"] is None and r.audio["ambient"] is None


def test_a_stage_and_a_trigger_steer_the_music(tmp_path):
    d = _copy("pct-house", tmp_path)

    def plot(j):
        j["stages"][1] = {"name": j["stages"][1] if isinstance(j["stages"][1], str) else j["stages"][1]["name"], "audio": {"bgm": "firstsnow"}}
        j["triggers"]["T.alarm"] = {"when": {"text": "player"}, "if": [{"text": ["警铃"]}], "once": True,
                                    "then": [{"to": "audio", "mood": "crisis", "ambient": "storm"}]}
    _edit(d / "plots" / "P01" / "plot.json", plot)
    assert not [p for p in TP.lint(TP.load(d), i18n=False)["problems"] if p["level"] == "block" and "audio" in (p["where"] + p["code"])]
    root = _run("pct-house", tmp_path, d)
    r = _apply(root, 1, says="我翻开了那本日记")
    assert r.stages and r.audio["music"]["id"] == "firstsnow" and r.audio["by"] == "stage"
    r = _apply(root, 2, says="楼下的警铃响了")
    assert r.audio["mood"] == "crisis" and r.audio["music"]["id"] == "crisis" and r.audio["ambient"]["id"] == "storm" and r.audio["by"] == "trigger"


def test_trigger_audio_is_validated():
    from neonrp.core import triggers

    assert any("audio needs" in p for p in triggers.validate(None, {"when": {"text": "player"}, "then": [{"to": "audio"}]}))
    assert any("calm | tense" in p for p in triggers.validate(None, {"when": {"text": "player"}, "then": [{"to": "audio", "mood": "loud"}]}))


# ── ④ mood ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_losing_hp_is_tense_for_a_couple_of_beats(tmp_path):
    root = _run("pct-house", tmp_path)
    hp = load_registry(root).variables["player.hp"].value
    r = _apply(root, 1, [{"op": "add", "var": "player.hp", "delta": -1}])
    assert r.audio["mood"] == "tense" and r.audio["music"]["id"] == "tense" and r.audio["by"] == "mood"
    assert not _apply(root, 2).audio and not _apply(root, 3).audio, f"held {audio.HOLD_BEATS} beats"
    r = _apply(root, 4)
    assert r.audio["mood"] == "calm" and r.audio["music"]["id"] == "whitechapel"
    r = _apply(root, 5, [{"op": "set", "var": "player.hp", "value": max(1, int(hp * 0.2))}])
    assert r.audio["mood"] == "crisis", "hp ≤ 30% → crisis"


def test_the_last_stage_is_tense(tmp_path):
    root = _run("last-train", tmp_path)
    reg = load_registry(root)
    last = int(reg.variables["P01.stage"].max)
    import neonrp.core.audio as A

    cue = A.compute(root, reg)
    assert cue["mood"] == "calm"
    reg.variables["P01.stage"].value = last
    assert A.compute(root, reg)["mood"] == "tense"


# ── ⑤ events ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_audio_cue_is_a_beat_event(tmp_path):
    root = _run("guixiang", tmp_path)
    r = _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/hall"}])
    tr = {"turn_seq": 1, "apply": {"beat": {"kind": "resolve"}, **r.to_dict(), "narration_plain": "…"}}
    evs = beat_events.from_traces([tr], root=root)[0]
    cue = next(d for k, d in evs if k == "audio.cue")
    assert cue["turn"] == 1 and cue["ambient"]["id"] == "fireplace" and cue["fade_ms"] > 0
    from neonrp.core import play_view
    from neonrp.webui.engine_routes import EngineRoutes

    assert "audio" in play_view.APPLY_KEYS and "audio.cue" in beat_events.EVENTS and "audio.cue" in EngineRoutes._STREAM_KINDS


# ── ⑥ lint ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_lint_unknown_ids_and_own_files(tmp_path):
    d = _copy("wuwu", tmp_path)
    _edit(d / "template.json", lambda j: j["audio"].update(theme="no-such-track", ambient="assets/audio/missing.mp3"))
    codes = {(p[1], p[2]) for p in TP._lint_audio(TP.load(d)) if p[0] == "block"}
    assert ("audio.ref", "audio.theme") in codes and ("audio.ref", "audio.ambient") in codes

    (d / "assets" / "audio").mkdir(parents=True)
    (d / "assets" / "audio" / "sea.mp3").write_bytes(b"ID3" + b"\x00" * 64)
    _edit(d / "template.json", lambda j: j["audio"].update(theme="wuwu", ambient="assets/audio/sea.mp3"))
    t = TP.load(d)
    assert t.zone == "reviewed"
    assert ("block", "audio.credits") in {(p[0], p[1]) for p in TP._lint_audio(t)}, "默认区: who made it must be said"
    _edit(d / "template.json", lambda j: j.update(zone="open"))
    assert ("warn", "audio.credits") in {(p[0], p[1]) for p in TP._lint_audio(TP.load(d))}, "自由区: a warning"
    (d / "assets" / "audio" / "CREDITS.md").write_text("sea.mp3 — mine, CC0", encoding="utf-8")
    _edit(d / "template.json", lambda j: j["audio"].update(credits="assets/audio/CREDITS.md"))
    assert not TP._lint_audio(TP.load(d))

    cue = audio.current(_run("wuwu", tmp_path, d))
    assert cue["template_credits"].startswith("sea.mp3")


# ── ⑦ files ──────────────────────────────────────────────────────────────────────────────────────────────────────────

class _H:
    """Just enough of a request handler for TemplateRoutes._send_media."""

    def __init__(self, headers: dict[str, str] | None = None):
        self.headers, self.wfile, self.status, self.sent = headers or {}, io.BytesIO(), None, {}

    def send_response(self, code):
        self.status = code

    def send_error(self, code, *_a):
        self.status = code

    def send_header(self, k, v):
        self.sent[k] = v

    def _cors_headers(self):
        pass

    def end_headers(self):
        pass


def _media(h: _H, p, immutable: bool) -> _H:
    from neonrp.webui.template_routes import TemplateRoutes

    TemplateRoutes._send_media(h, p, immutable=immutable)
    return h


def test_pool_urls_cache_and_ranges():
    t = audio.track("calm", "music")
    url = audio.pool_url(t)
    f, fresh = audio.pool_file(url[len("/api/v1/audio/"):])
    assert f is not None and fresh
    assert audio.pool_file("music/calm.0000000000.mp3")[1] is False, "a stale hash still plays, but revalidates"
    assert audio.pool_file("../catalog.json")[0] is None and audio.pool_file("music/nope.mp3")[0] is None
    full = _media(_H(), f, True)
    assert full.status == 200 and full.sent["Cache-Control"].endswith("immutable") and full.sent["Accept-Ranges"] == "bytes"
    assert full.wfile.getvalue() == f.read_bytes()
    part = _media(_H({"Range": "bytes=10-19"}), f, True)
    assert part.status == 206 and part.wfile.getvalue() == f.read_bytes()[10:20]
    assert part.sent["Content-Range"] == f"bytes 10-19/{f.stat().st_size}"
    tail = _media(_H({"Range": "bytes=-5"}), f, False)
    assert tail.status == 206 and tail.wfile.getvalue() == f.read_bytes()[-5:] and tail.sent["Cache-Control"] == "no-cache"
    assert _media(_H({"Range": f"bytes={f.stat().st_size + 5}-"}), f, True).status == 416
    assert _media(_H({"If-None-Match": full.sent["ETag"]}), f, True).status == 304


def test_template_audio_url_carries_its_hash(tmp_path):
    d = _copy("wuwu", tmp_path)
    (d / "assets" / "audio").mkdir(parents=True)
    (d / "assets" / "audio" / "sea.mp3").write_bytes(b"ID3" + b"\x01" * 64)
    hit = audio.resolve("assets/audio/sea.mp3", "ambient", "wuwu", d)
    assert hit["url"] == f"/api/v1/local/templates/wuwu/audio?path=assets/audio/sea.mp3&h={audio.file_hash(d / 'assets/audio/sea.mp3')}"
    assert audio.resolve("assets/../x.mp3", "ambient", "wuwu", d) is None
    assert audio.resolve("silence", "music") == {"quiet": True} and audio.resolve("default", "music") is None
    assert audio.resolve("harbor-waves", "music") is None, "a bed is not music"
