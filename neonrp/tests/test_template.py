"""Template protocol (docs/TEMPLATE-PROTOCOL.md): load → lint → build → the built run plays its plot to an ending."""
from __future__ import annotations

import json
import time
import urllib.error
import shutil
from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.core import sdk
from neonrp.core.adv import entries_for, prompt_spec
from neonrp.core.registry import load_registry
from neonrp.packs import template_of
from _paths import PRODUCT_TEMPLATES

_EX = PRODUCT_TEMPLATES / "stoneford-elena.template"


def _j(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _copy(tmp_path: Path) -> Path:
    d = tmp_path / "t.template"
    shutil.copytree(_EX, d)
    return d


def _codes(r: dict) -> dict[str, str]:
    return {p["code"] + "@" + p["where"]: p["level"] for p in r["problems"]}


_SOFT = ("asset.optional", "token.unmeasured")  # v3: optional slots unfilled / no measured turns yet — warnings by design


def _hard(r: dict) -> list:
    return [p for p in r["problems"] if p["code"] not in _SOFT]


def test_example_template_lints_clean():
    r = TP.lint(_EX)
    assert _hard(r) == [] and r["publishable"]
    assert r["meta"]["pack"] == "rpg" and r["meta"]["mode"]["ending"] == "multi" and r["meta"]["souls"] == ["elena", "rowan"]


def test_build_binds_every_layer(tmp_path):
    run = tmp_path / "run"
    rec = TP.build(_EX, run)
    assert rec["built"]["plots"] == ["P10"] and rec["built"]["souls"] == ["elena", "rowan"]
    assert template_of(run) == "rpg"                                                   # pack bound
    assert _j(run / "game" / "meta" / "engine.json")["turn"]["mode"] == "v3"          # pack's loop setting
    assert _j(run / "game" / "meta" / "template.json")["card"]["title"].startswith("石津镇")  # meta for the UI
    assert _j(run / "game" / "meta" / "game-start.json")["name"] == "石津镇 · 艾琳娜与罗文"
    assert (run / "game" / "plots" / "P10" / "reveal.json").is_file()                # 谜底 kept for the epilogue
    ids = [e["id"] for e in prompt_spec(run)["entries"]]
    assert {"town_attitude", "voice", "P10.guide", "P10.choice"} <= set(ids)           # world < template prompts < plot prompts
    spec = prompt_spec(run)
    reg = load_registry(run)
    assert not any("此后让艾琳娜" in x for x in entries_for(spec, "zh", reg=reg)["keyword"])  # stage 0: the choice hint is off
    assert "voice" in [e["id"] for e in spec["entries"] if e.get("when") == "post"]


def test_built_run_reaches_both_endings(tmp_path):
    def play(ending_line: str) -> dict:
        run = tmp_path / ending_line[:2]
        TP.build(_EX, run)
        ar = sdk.apply(run, [], load_registry(run), turn=1, narration="码头木桩缝里有一枚护身符在反光。")
        assert ar.variables["P10.stage"] == 1 and ar.ended is None
        ar = sdk.apply(run, [{"op": "move_to", "who": "player", "to": "T004/chapel"}], load_registry(run), turn=2)
        assert ar.variables["P10.stage"] == 2 and ar.ended is None
        ar = sdk.apply(run, [], load_registry(run), turn=3, player_says=ending_line)
        assert ar.ended, ar
        return ar.ended

    assert play("我把真相告诉她")["id"] == "E10"
    assert play("把护身符扔掉吧")["id"] == "E11"


def test_template_can_swap_souls_and_overlay_prompts_only(tmp_path):
    d = _copy(tmp_path)
    t = _j(d / "template.json")
    src = Path("src/neonrp/templates/stoneford-elena/souls/elena-si-elena0001")
    shutil.copytree(src, d / "souls" / "mira")                   # a soul brought in from elsewhere (data)
    sj = _j(d / "souls" / "mira" / "soul.json")
    sj["sid"] = "mira"
    (d / "souls" / "mira" / "soul.json").write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")
    t["souls"] = [{"sid": "elena"}, {"sid": "mira", "path": "souls/mira", "role": "npc"}]
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    ov = d / "prompts" / "souls" / "elena"
    (ov / "rules").mkdir(parents=True)
    (ov / "soul.md").write_text("# 换一种说法的艾琳娜\n", encoding="utf-8")
    assert TP.lint(d)["publishable"]
    run = tmp_path / "run"
    rec = TP.build(d, run)
    pt = _j(run / ".neonrp" / "playthrough.json")
    assert [s["sid"] for s in pt["souls"]] == ["elena", "mira"] and len(pt["active_souls"]) == 2
    assert (run / "souls" / f"mira-{pt['souls'][1]['instance_id']}" / "soul.json").is_file()
    assert (run / "souls" / "elena-si-elena0001" / "soul.md").read_text(encoding="utf-8").startswith("# 换一种说法")
    assert (run / "souls" / "elena-si-elena0001" / "character" / "stats.json").is_file()  # data untouched
    assert rec["built"]["prompt_overlays"] == ["elena:soul.md"]
    # the prompt layer may not write soul data
    (ov / "character").mkdir()
    (ov / "character" / "stats.json").write_text("{}", encoding="utf-8")
    assert "prompt.soul.data@prompts/souls/elena/character/stats.json" in _codes(TP.lint(d))


@pytest.mark.parametrize("mutate, code", [
    (lambda t, p: t["mode"].update(ending="single"), "loop.single@mode.ending"),                      # 3 reachable ≠ 1
    (lambda t, p: p["triggers"].pop("P10.letgo"), "loop.reach@endings.E11"),                            # multi: an ending with no road
    (lambda t, p: p["triggers"]["P10.letgo"]["then"].append({"to": "end", "ending": "E10"}), "loop.distinct@triggers.P10.letgo.then"),
    (lambda t, p: p["triggers"].pop("P10.fall"), "loop.reach@endings.E19"),
    (lambda t, p: t.update(world={"builtin": "nope"}), "ref.world@world"),
    (lambda t, p: t.update(pack={"name": "no-such-pack"}), "ref.pack@pack.name"),
    (lambda t, p: t["souls"].append({"sid": "ghost"}), "ref.soul@souls[2].ghost"),
    (lambda t, p: t["card"].pop("title"), "meta.card@card.title"),
    (lambda t, p: t["mode"].update(reveal=True) or p.pop("reveal"), "loop.reveal@P10.reveal"),
    (lambda t, p: p["triggers"]["P10.chapel"].update(when={"entry": "T004/nowhere", "event": "enter"}), None),
])
def test_lint_blocks(tmp_path, mutate, code):
    d = _copy(tmp_path)
    t, p = _j(d / "template.json"), _j(d / "plots" / "P10" / "plot.json")
    mutate(t, p)
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    (d / "plots" / "P10" / "plot.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    r = TP.lint(d)
    assert not r["publishable"]
    if code:
        assert _codes(r).get(code) == "block", r["problems"]
    else:
        assert any(x["code"] == "plot" and x["level"] == "block" for x in r["problems"]), r["problems"]


def test_asset_rules_warn_or_block_by_level(tmp_path):
    """v3 slots: a publish-required slot left empty blocks at publish level, warns at draft; the card cover too."""
    d = _copy(tmp_path)
    t = _j(d / "template.json")
    t["ui"] = {"slots": [{"cls": "item", "slot": "icon", "kind": "icon", "required": "publish", "recipe": "item_icon"}]}
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    (d / "assets" / "cover.png").unlink()
    c = _codes(TP.lint(d))
    assert c["asset.missing@slots.item.icon:I910"] == "block" and c["asset.card@card.cover"] == "block"
    t["lint"]["level"] = "draft"
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    c = _codes(TP.lint(d))
    assert c["asset.missing@slots.item.icon:I910"] == "warn" and c["asset.card@card.cover"] == "warn"


def test_run_view_hides_the_reveal_until_the_ending(tmp_path):
    run = tmp_path / "run"
    TP.build(_EX, run)
    v = TP.run_view(run)
    assert v["template"]["id"] == "stoneford-elena" and v["plots"][0]["stage"] == 0 and v["ending"] is None and "reveal" not in v
    assert set(v["plots"][0]["endings"]) == {"E10", "E11", "E19"}
    sdk.apply(run, [], load_registry(run), turn=1, narration="护身符")
    sdk.apply(run, [{"op": "move_to", "who": "player", "to": "T004/chapel"}], load_registry(run), turn=2)
    sdk.apply(run, [], load_registry(run), turn=3, player_says="说出真相吧")
    v = TP.run_view(run)
    assert v["ending"]["id"] == "E10" and "礼拜堂" in v["reveal"]["P10"]["zh"]


def test_template_http_routes(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(_EX, store / "stoneford-elena.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        get = lambda p: json.loads(urllib.request.urlopen(base + p, timeout=20).read())  # noqa: E731
        try:
            assert get("/api/v1/meta")["capabilities"]["template"] == 1
            # 10-08:列表不等 lint —— 引擎刚起时立刻返回(checking),lint 在后台补进缓存,之后的列表带结果
            from neonrp.webui import template_routes as _tr

            _tr._LINT_CACHE.clear()
            t0 = time.time()
            rows = get("/api/v1/local/templates")["templates"]
            el = lambda rs: next(r for r in rs if r["id"] == "stoneford-elena")  # noqa: E731 — 10-17: the shipped two lead the list
            assert time.time() - t0 < 3 and [r["id"] for r in rows[:2]] == ["pct-house", "stoneford-town"]
            assert el(rows).get("checking") and el(rows)["mode"]["ending"] == "multi"
            while any(r.get("checking") for r in rows) and time.time() - t0 < 120:
                time.sleep(0.3)
                rows = get("/api/v1/local/templates")["templates"]
            assert el(rows)["publishable"] and not el(rows).get("checking")
            r = get("/api/v1/local/templates/stoneford-elena/lint")
            assert r["publishable"] and _hard(r) == []
            with pytest.raises(urllib.error.HTTPError):
                get("/api/v1/local/templates/..%2F..%2Fetc/lint")
            assert get("/api/v1/play/engine/template") == {"template": None}
        finally:
            server.shutdown()


def test_world_prompts_replaced_by_the_template_layer(tmp_path):
    run = tmp_path / "run"
    rec = TP.build(_EX, run)
    assert rec["built"]["prompts_from_world"] is False  # stoneford's prompts now live in the template's prompts/world.json
    ids = [e["id"] for e in prompt_spec(run)["entries"]]
    assert ids.count("town_attitude") == 1 and "voice" in ids
    t = _j(_EX / "template.json")
    t["world"] = {"builtin": "stoneford-elena"}
    d = tmp_path / "t.template"
    shutil.copytree(_EX, d)
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    assert TP.build(d, tmp_path / "run2")["built"]["prompts_from_world"] is True  # merge mode: world's own stays underneath


def test_start_a_run_from_a_template_and_tick_it(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "stoneford-market.template", store / "stoneford-market.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    plays = tmp_path / "lib" / "plays"
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", plays),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        try:
            with pytest.raises(urllib.error.HTTPError):
                call("/api/v1/play/engine/tick", {"turns": 1})  # no session yet
            started = call("/api/v1/play/session", {"slug": "tpl--stoneford-market"})
            assert started["root"].startswith("tpl-stoneford-market-")
            run = plays / started["root"]
            assert (run / "game" / "meta" / "template.json").is_file() and (run / ".neonrp" / "manifest.json").is_file()
            v = call("/api/v1/play/engine/template")
            assert v["template"]["id"] == "stoneford-market" and v["template"]["pack"] == "rpg+economy+factions"
            r = call("/api/v1/play/engine/tick", {"turns": 8})
            assert r["ok"] and len(r["turns"]) == 8
            assert any(a["op"] == "new_caravan" for t in r["turns"] for a in t["applied"])
            with pytest.raises(urllib.error.HTTPError):
                call("/api/v1/play/session", {"slug": "tpl--nope"})
        finally:
            server.shutdown()


def test_soul_pool_draws_a_seeded_cast(tmp_path):
    d = _copy(tmp_path)
    t = _j(d / "template.json")
    t["souls"] = [{"pool": ["elena", "rowan"], "pick": 1, "role": "npc"}]
    t["plots"], t["mode"] = [], {"ending": "open"}  # P10 talks to 艾琳娜 by name: with rowan drawn, its lint (rightly) blocks
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    assert TP.lint(d)["publishable"] and TP.load(d).meta()["souls"] == ["1/2"]
    casts = {tuple(TP.build(d, tmp_path / f"r{i}")["built"]["cast"]) for i in range(8)}
    assert casts <= {("elena",), ("rowan",)} and len(casts) == 2, "different runs draw differently"
    t["seed"] = "fixed"
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    assert len({tuple(TP.build(d, tmp_path / f"s{i}")["built"]["cast"]) for i in range(4)}) == 1, "a seed pins the cast"
    # with the plot back: lint checks refs with every candidate cast, and warns the plot may talk to no one
    t2 = {**{k: v for k, v in t.items() if k != "seed"}, "plots": ["plots/P10"], "mode": {"ending": "multi"}}
    (d / "template.json").write_text(json.dumps(t2, ensure_ascii=False), encoding="utf-8")
    r = TP.lint(d)
    assert r["publishable"] and any(p["code"] == "loop.pool" and "elena" in p["msg"] for p in r["problems"])
    built = [TP.build(d, tmp_path / f"p{i}")["built"] for i in range(6)]  # every draw builds; rowan-only runs drop the line to elena
    assert all(b["plots"] == ["P10"] for b in built)
    assert any(b["cast"] == ["rowan"] and b.get("dropped_soul_emits") == ["P10.P10.clue.then→艾琳娜"] for b in built)
    t["souls"] = [{"pool": ["elena"], "pick": 3}]
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    assert _codes(TP.lint(d))["ref.soul.pool@souls[0].pick"] == "block"


def test_werewolf_template_deals_roles_and_ends_by_pack_rules(tmp_path):
    ex = PRODUCT_TEMPLATES / "werewolf-night-village.template"
    r = TP.lint(ex)
    assert r["publishable"], r["problems"]  # multi: 好人胜 / 狼人胜 come from the werewolf pack's own triggers
    roles = set()
    for i in range(6):
        run = tmp_path / f"r{i}"
        rec = TP.build(ex, run)
        assert rec["built"]["shuffled"] == 6
        seats = {p.stem: _j(p)["props"]["role"] for p in sorted((run / "game" / "seats").glob("*.json"))}
        assert sorted(seats.values()) == sorted(["villager", "wolf", "seer", "wolf", "villager", "villager"])
        roles.add(seats["S01"])
    assert len(roles) > 1, "the deal changes run to run"
    run = tmp_path / "r0"
    reg = load_registry(run)
    assert reg.template == "werewolf" and reg.variables["table.wolves"].value == 2
    from neonrp.core import engine_config
    assert engine_config.v3_enabled(run)  # the werewolf pack's loop
    wolves = [e.id for e in reg.of_class("seat") if e.props["role"] == "wolf"]
    ar = None
    for w in wolves:
        ar = sdk.apply(run, [{"op": "kill", "target": w}], load_registry(run), turn=1)
    assert ar is not None and ar.ended and ar.ended["id"] == "E_VILLAGE"


_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_asset_slots_upload_and_generate(tmp_path, monkeypatch):
    d = _copy(tmp_path)
    slots = {s["slot"]: s for s in TP.asset_slots(TP.load(d))}
    # template-level + class slots (Template v3): the builtin world already has its maps and portraits
    assert slots["card:cover"]["have"] and "plot:plots/P10:ending:E10" in slots
    assert slots["level.map:T001"]["have"] and slots["level.map:T001"]["need"] and slots["soul.portrait:elena"]["have"]
    item = slots["item.icon:I910"]
    assert not item["have"] and "amulet" in item["prompt"]  # the entry's own image_prompt beats the class recipe
    # upload → the plot's own assets + plot.json records it (the plot / ending UI reads it from there)
    row = TP.put_asset(d, "item.icon:I910", _PNG, ext=".png")
    assert row["have"] and (d / "plots/P10/assets/entry-I910.png").is_file()
    assert _j(d / "plots/P10/plot.json")["entries"]["I910"]["assets"]["image"] == "assets/entry-I910.png"
    assert TP.slot_file(TP.load(d), "item.icon:I910") == d / "plots/P10/assets/entry-I910.png"
    # a map uploaded into the template lands in world-overlay with the CURRENT layout frozen next to it (hotspots follow data)
    row = TP.put_asset(d, "level.map:T004", _PNG, ext=".png")
    meta = _j(d / "world-overlay/assets/maps/T004.json")
    assert row["have"] and not row["stale"] and meta["layout_hash"] and meta["fit"]["sx"] > 0
    # not an image / unknown slot / a slot that would leave the template
    for bad_slot, data in (("item.icon:I910", b"<svg/>"), ("plot:../x:entry:I910", _PNG), ("card:nope", _PNG), ("item.icon:nope", _PNG)):
        with pytest.raises(TP.TemplateError):
            TP.put_asset(d, bad_slot, data)
    # generation goes through the configured backend
    seen = {}

    def fake_gen(prompt, out_dir, **kw):
        seen.update(prompt=prompt, **kw)
        p = Path(out_dir) / "g.png"
        p.write_bytes(_PNG)
        return p
    monkeypatch.setattr("neonrp.core.imagegen.generate_image", fake_gen)
    row = TP.generate_asset(d, "plot:plots/P10:ending:E10")
    assert row["have"] and seen["width"] == 1344 and "记忆归来" in seen["prompt"]
    assert _j(d / "plots/P10/plot.json")["endings"]["E10"]["assets"]["image"] == "assets/ending-E10.png"


def test_asset_http(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(_EX, store / "stoneford-elena.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/templates/stoneford-elena"
        try:
            slots = json.loads(urllib.request.urlopen(base + "/assets", timeout=20).read())["slots"]
            assert any(s["slot"] == "item.icon:I910" and not s["have"] for s in slots)
            req = urllib.request.Request(base + "/assets/upload?slot=item.icon:I910&ext=.png", data=_PNG, method="POST",
                                         headers={"Content-Type": "image/png"})
            r = json.loads(urllib.request.urlopen(req, timeout=20).read())
            assert r["ok"] and r["slot"]["have"]
            img = urllib.request.urlopen(base + "/assets/file?slot=item.icon:I910", timeout=20).read()
            assert img == _PNG
            bad = urllib.request.Request(base + "/assets/upload?slot=item.icon:I910", data=b"hello", method="POST")
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(bad, timeout=20)
            assert ei.value.code == 400
        finally:
            server.shutdown()
