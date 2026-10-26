"""Template v3 (Mock 3.0 「组装 · Lint」): pack ui, class slots, staleness, the four checks, views, contract."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from neonrp import packs
from neonrp import template as TP
from neonrp.template import v3
from _paths import PRODUCT_TEMPLATES

_ELENA = PRODUCT_TEMPLATES / "stoneford-elena.template"
_MARKET = PRODUCT_TEMPLATES / "stoneford-market.template"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _copy(tmp_path: Path, src: Path = _MARKET) -> Path:
    d = tmp_path / "t.template"
    shutil.copytree(src, d)
    return d


def _patch(d: Path, **kv) -> None:
    t = json.loads((d / "template.json").read_text(encoding="utf-8"))
    t.update(kv)
    (d / "template.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")


def _codes(r: dict) -> dict[str, str]:
    return {p["code"] + "@" + p["where"]: p["level"] for p in r["problems"]}


def test_ui_layers_pack_mixins_template():
    u = v3.ui(TP.load(_MARKET))
    views = {v["id"] for v in u["views"]}
    assert {"alert", "purse", "market", "factions", "rumors", "quests"} <= views           # rpg + economy + factions
    assert {(s["cls"], s["slot"]) for s in u["slots"]} >= {("level", "map"), ("soul", "portrait"), ("faction", "emblem"), ("caravan", "icon")}
    assert {p["id"] for p in u["panels"]} == {"formation", "map", "sheet"} and u["budget"] == 20000
    merged = packs.merge_ui(u, {"panels": [{"id": "formation", "format": "json"}], "views": [{"id": "purse", "remove": True}],
                                "prompts": {"emblem": None}, "budget": 9000})
    assert next(p for p in merged["panels"] if p["id"] == "formation")["format"] == "json"
    assert "purse" not in {v["id"] for v in merged["views"]} and "emblem" not in merged["prompts"] and merged["budget"] == 9000


def test_custom_slot_goes_stale_when_its_inputs_change(tmp_path, monkeypatch):
    # e3384bde (10-15): the slot table's template signature is reused for SIG_TTL seconds, so an edit made outside the
    # engine (here template.json written directly) shows up only after that — this test edits and reads at once
    monkeypatch.setattr(v3, "SIG_TTL", 0.0)
    d = _copy(tmp_path)
    slot = "faction.emblem:guild"
    rows = {r["slot"]: r for r in TP.asset_slots(TP.load(d))}
    assert slot in rows and not rows[slot]["have"] and "石津公会" in rows[slot]["prompt"]
    row = TP.put_asset(d, slot, _PNG)
    assert row["have"] and not row["stale"] and (d / "world-overlay/assets/faction/emblem/guild.png").is_file()
    # the class recipe's wording changes → the emblem was drawn from other inputs → stale, and lint says so
    _patch(d, ui={"prompts": {"emblem": "「{inst.name}」的旗帜,{style}。"}})
    rows = {r["slot"]: r for r in TP.asset_slots(TP.load(d))}
    assert rows[slot]["stale"]
    assert _codes(TP.lint(d))["asset.stale@slots.faction.emblem:guild"] == "warn"  # optional slot → warn even at publish


def test_four_checks_block_what_mock_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(v3, "measured_tokens", lambda t, **kw: (0, 0))  # independent of real local runs in PLAYS_HOME
    d = _copy(tmp_path)
    _patch(d, ui={
        "prompts": {"emblem": "{inst.name} 的旗 {nope.var},{style}", "extra": "现在 {town.alert} 级警戒"},
        "views": [{"id": "ghost", "bind": ["ghost.*"], "widget": "table"},
                  {"id": "bad_act", "bind": ["town.alert"], "widget": "gauge", "actions": ["teleport"]},
                  {"id": "cls", "bind": ["class:dragon"], "widget": "list"}],
        "slots": [{"cls": "faction", "slot": "banner", "kind": "image", "recipe": "no_such_recipe"}],
    })
    c = _codes(TP.lint(d))
    assert c["prompt.placeholder@prompts.emblem"] == "block" and "prompt.placeholder@prompts.extra" not in c  # registered var is fine
    assert c["schema.view@views.ghost"] == "block" and c["schema.view@views.bad_act"] == "block" and c["schema.view@views.cls"] == "block"
    assert c["schema.slot@slots.faction.banner"] == "block"
    assert c["token.unmeasured@budget"] == "warn"


def test_token_budget_blocks_at_publish(tmp_path, monkeypatch):
    d = _copy(tmp_path)
    monkeypatch.setattr(v3, "measured_tokens", lambda t, **kw: (31000, 6))
    assert _codes(TP.lint(d))["token.over@budget"] == "block"
    _patch(d, lint={"level": "draft"})
    assert _codes(TP.lint(d))["token.over@budget"] == "warn"
    monkeypatch.setattr(v3, "measured_tokens", lambda t, **kw: (17000, 6))
    assert _codes(TP.lint(d))["token.near@budget"] == "warn"


def test_views_are_bound_to_the_players_town(tmp_path):
    run = tmp_path / "run"
    TP.build(_MARKET, run)
    rec = json.loads((run / "game/meta/template.json").read_text(encoding="utf-8"))
    views = {v["id"]: v for v in v3.views_data(run, rec["ui"])}
    market = views["market"]
    assert market["actions"] == ["trade"] and "price.T001.fish" in market["vars"] and "price.T004.fish" not in market["vars"]
    assert market["vars"]["stock.T001.fish"]["value"] == 64
    assert views["alert"]["vars"]["town.alert"]["max"] is not None or "town.alert" in views["alert"]["vars"]
    assert len(views["rumors"]["rows"]) == 2 and views["rumors"]["rows"][0]["text"]
    assert [v["id"] for v in v3.views_data(run, rec["ui"])][0] == "alert"  # ordered by layout


def test_contract_and_bindings():
    t = TP.load(_MARKET)
    with v3._scratch(t, None) as root:
        c = v3.contract(t, root)
    assert c["$schema"] == "worldlines.contract/0.1" and c["template"] == {"base": "rpg", "mixins": ["economy", "factions"]}
    names = {x["name"] for x in c["vars"]}
    assert {"player.gold", "price.T001.grain", "faction.bandits.power"} <= names
    ops = {o["op"]: o for o in c["ops"]}
    assert "trade" in ops and ops["trade"]["owner"] == "economy" and "move_to" in ops
    assert any(s["id"] == "faction.emblem" for s in c["slots"]) and any(v["id"] == "market" for v in c["views"])
    assert next(k for k in c["classes"] if k["name"] == "rumor")["policy"] == "auto"
    assert {p["id"] for p in c["panels"]} == {"formation", "map", "sheet"} and set(c["interaction"]) >= {"requests", "switches", "panels"}
    ts, gd = v3.gen_ts(c), v3.gen_gd(c)
    assert f"CONTRACT_HASH = '{c['hash']}'" in ts and "'price.T001.grain': number;" in ts and "trade: {" in ts
    assert "class_name StonefordMarketWorld" in gd and "var price_T001_grain: int" in gd
    with v3._scratch(t, None) as root:
        assert v3.contract(t, root)["hash"] == c["hash"]  # deterministic


def test_prompt_entries_take_current_values(tmp_path):
    from neonrp.core.adv import entries_for
    from neonrp.core.registry import load_registry

    run = tmp_path / "run"
    TP.build(_ELENA, run)
    reg = load_registry(run)
    spec = {"entries": [{"id": "status", "text": "现在第 {time.day} 天,警戒 {town.alert};{not.a.var} 原样", "when": "post"}]}
    post = entries_for(spec, "zh", reg=reg)["post"][0]
    assert f"第 {reg.variables['time.day'].value} 天" in post and "{not.a.var} 原样" in post
    assert entries_for(spec, "zh")["post"][0].startswith("现在第 {time.day}")  # no registry → untouched


def test_views_and_contract_http(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(_MARKET, store / "stoneford-market.template")
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

        def call(path, body=None, raw=False):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return b.decode() if raw else json.loads(b)
        try:
            c = call("/api/v1/local/templates/stoneford-market/contract")
            assert c["$schema"] == "worldlines.contract/0.1"
            assert "class_name StonefordMarketWorld" in call("/api/v1/local/templates/stoneford-market/contract?fmt=gd", raw=True)
            call("/api/v1/play/session", {"slug": "tpl--stoneford-market"})
            v = call("/api/v1/play/engine/views")
            assert any(x["id"] == "market" for x in v["views"]) and {p["id"] for p in v["panels"]} == {"formation", "map", "sheet"}
            # 1.0 UI reads (10-06): the graph in effect + its default · the run's contract ({} when none) · settlement ({} before an exit)
            g = call("/api/v1/play/engine/graph")
            assert g["graph"]["nodes"] and g["default"]["nodes"] and isinstance(g["graph"]["edges"], list)
            assert isinstance(call("/api/v1/play/engine/contract"), dict)
            assert call("/api/v1/play/engine/settlement") == {}
        finally:
            server.shutdown()


def test_plots_read_and_write_http(tmp_path, monkeypatch):
    """The 1.0 UI's plot graph (10-06): read every plot of a template with the files beside it; write one back only on a
    template the creator owns (built-ins are read-only), re-linted on the way out."""
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store, mine = tmp_path / "store", tmp_path / "mine"
    shutil.copytree(_ELENA, store / "stoneford-elena.template")
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{store}")   # the write store is searched first, like the app
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/templates"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        try:
            v = call("/stoneford-elena/plots")
            assert v["writable"] is False
            p10 = next(p for p in v["plots"] if p["path"] == "plots/P10/plot.json")
            assert p10["data"]["stages"] and "E10" in p10["data"]["endings"] and "plot.json" in p10["files"]
            data = p10["data"]
            data["endings"]["E10"]["title"] = "她想起来了"
            with pytest.raises(urllib.error.HTTPError) as exc:
                call("/stoneford-elena/plots", {"path": "plots/P10/plot.json", "data": data})
            assert exc.value.code == 403                                   # built-in: fork first
            fork = call("/stoneford-elena/fork", {"id": "elena-mine", "title": "我的"})
            fid = fork.get("id") or "elena-mine"
            out = call(f"/{fid}/plots", {"path": "plots/P10/plot.json", "data": data})
            assert out["ok"] and "problems" in out["lint"]
            assert next(p for p in call(f"/{fid}/plots")["plots"] if p["path"] == "plots/P10/plot.json")["data"]["endings"]["E10"]["title"] == "她想起来了"
            for bad in ({"path": "plots/../template.json", "data": data}, {"path": "plots/P10/plot.json", "data": [1]}):
                with pytest.raises(urllib.error.HTTPError) as exc:
                    call(f"/{fid}/plots", bad)
                assert exc.value.code == 400
        finally:
            server.shutdown()


def test_edit_session_from_any_template(tmp_path, monkeypatch):
    """世界 · 角色 edits the selected template's world (10-06): the edit session is built like a run of the template — a
    template with its own world folder opens (it used to fail: the old scaffold only knew the built-in worlds) and an overlay
    template keeps its overlay."""
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    for tid in ("pct-house", "stoneford-three-towns"):
        shutil.copytree(PRODUCT_TEMPLATES / f"{tid}.template", store / f"{tid}.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        try:
            for tid, must in (("pct-house", "game/"), ("stoneford-three-towns", "game/world/economy.json")):
                out = post("/api/v1/create/session", {"template": tid, "name": tid})
                paths = [f["path"] for f in out["files"]]
                assert any(p.startswith(must) for p in paths), (tid, must)
                assert ".neonrp/manifest.json" in paths
        finally:
            server.shutdown()


def _shipped_ids():
    return sorted(p.name[: -len(".template")] for p in PRODUCT_TEMPLATES.glob("*.template") if (p / "template.json").is_file())


@pytest.mark.parametrize("tid", _shipped_ids())
def test_copied_template_opens_before_and_after_new_world(tmp_path, monkeypatch, tid):
    """10-25: every built-in template, copied (「复制一份来改」), opens as an edit session — and still does after「＋ 新建世界」
    swaps its world for a blank one (灰橡宅's copy then answered 400: its plots name the old world's rooms and player.san, the
    plot lint failed the build). The session opens without the plots and says why; a failure is JSON with a readable reason."""
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    monkeypatch.setattr(TP, "can_fork", lambda t: True)   # the copy path itself, for the templates the local edition does not offer
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            mine = f"{tid}-mine"[:40]
            code, out = post(f"/api/v1/local/templates/{tid}/fork", {"id": mine, "title": "(我的)"})
            assert code == 200, out
            code, out = post("/api/v1/create/session", {"template": mine, "name": "我的"})
            assert code == 200 and not out.get("warnings"), out
            code, out = post(f"/api/v1/local/templates/{mine}/world/new", {"title": "新世界"})
            assert code == 200, out
            code, out = post("/api/v1/create/session", {"template": mine, "name": "新世界"})
            assert code == 200, out
            assert ".neonrp/manifest.json" in [f["path"] for f in out["files"]]
            if tid == "pct-house":   # its plot names the old house's rooms: opened without it, with the reason
                assert out.get("warnings") and "T001/cellar" in out["warnings"][0]
            code, out = post("/api/v1/create/session", {"template": "no-such-template", "name": "x"})
            assert code == 400 and out["error"] == "scaffold_failed" and out["message"]
        finally:
            server.shutdown()


def test_cli_contract_and_slots():
    from click.testing import CliRunner

    from neonrp.commands.template_cmd import template_group

    r = CliRunner().invoke(template_group, ["contract", str(_ELENA), "--ts"])
    assert r.exit_code == 0 and "export interface StonefordElenaVars" in r.output
    r = CliRunner().invoke(template_group, ["slots", str(_ELENA)])
    assert r.exit_code == 0 and "level.map:T001" in r.output and "item.icon:I910" in r.output


@pytest.mark.parametrize("bad", ["../../etc/x", "faction.emblem:../../x"])
def test_slot_ids_cannot_escape(tmp_path, bad):
    d = _copy(tmp_path)
    with pytest.raises(TP.TemplateError):
        TP.put_asset(d, bad, _PNG)
