"""Template authoring (template/author.py): fork into the write store, creator ops all-or-nothing, overlay files,
the asset workshop mirror, and the HTTP face (/api/v1/local/templates/<id>/ui|fork|ops)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.template import author

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def store(tmp_path, monkeypatch):
    w = tmp_path / "store"
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(w))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(w))
    monkeypatch.setenv("WORLDLINES_ASSETS_DIR", str(tmp_path / "assets"))
    return w


def test_fork_market_into_store(store, tmp_path):
    src = TP.discover()["stoneford-market"]
    t = author.fork(src, "mist-market", title="雾市")
    assert t.dir == store / "mist-market.template"
    assert t.id == "mist-market" and t.card["title"] == "雾市" and t.version == "0.1"
    assert t.data["forked_from"]["id"] == "stoneford-market"
    assert (t.dir / "world-overlay" / "game" / "world" / "economy.json").is_file()
    assert (tmp_path / "assets" / "worlds" / "mist-market" / "prompts.md").is_file()  # the workshop space
    assert "mist-market" in TP.discover() and author.writable(t)
    assert not author.writable(TP.load(src))  # built-ins stay read-only


def test_fork_refuses_bad_or_taken_ids(store):
    src = TP.discover()["stoneford-market"]
    with pytest.raises(TP.TemplateError):
        author.fork(src, "Bad Id")
    with pytest.raises(TP.TemplateError):
        author.fork(src, "stoneford-elena")


def test_builtin_is_read_only(store):
    with pytest.raises(TP.TemplateError, match="只读"):
        author.apply_ops(TP.discover()["stoneford-market"], [{"op": "edit_card", "title": "x"}])


def test_ops_apply_and_relint(store):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    res = author.apply_ops(t, [
        {"op": "edit_card", "title": "雾市", "pitch": "雾里的集市", "tags": ["经济"]},
        {"op": "set_mode", "ending": "open", "freedom": "semi"},
        {"op": "edit_prompt", "id": "portrait", "text": "{soul.name},半身立绘,{style}"},
        {"op": "edit_recipe", "key": "style", "value": "暗色水彩"},
        {"op": "add_slot", "cls": "soul", "slot": "voice", "kind": "audio", "required": "optional"},
        {"op": "set_view", "view": {"id": "alert", "title": "警戒", "bind": ["town.alert"], "widget": "gauge"}},
        {"op": "set_budget", "value": 18000},
    ])
    assert res["ok"], res
    t2 = TP.load(t.dir)
    assert t2.card["pitch"] == "雾里的集市" and t2.mode["freedom"] == "semi"
    assert t2.data["recipe"]["style"] == "暗色水彩"
    u = res["ui"]
    assert u["prompts"]["portrait"].startswith("{soul.name}") and u["budget"] == 18000
    assert any(s["cls"] == "soul" and s["slot"] == "voice" for s in u["slots"])
    assert any(v["id"] == "alert" for v in u["views"])
    assert "problems" in res["lint"]


def test_one_refused_op_writes_nothing(store):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    before = (t.dir / "template.json").read_text(encoding="utf-8")
    res = author.apply_ops(t, [{"op": "edit_card", "title": "新名字"}, {"op": "add_slot", "cls": "nope", "slot": "x"}])
    assert not res["ok"] and res["refused"][0]["why"].startswith("没有类")
    assert (t.dir / "template.json").read_text(encoding="utf-8") == before


def test_duplicate_slot_and_bad_recipe_key_refused(store):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    assert author.apply_ops(t, [{"op": "add_slot", "cls": "soul", "slot": "portrait"}])["refused"][0]["why"].endswith("已经声明过")
    assert author.apply_ops(t, [{"op": "edit_recipe", "key": "seed", "value": "1"}])["refused"]


def test_class_and_policy_go_to_the_overlay_and_reach_a_run(store, tmp_path):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    res = author.apply_ops(t, [{"op": "register_class", "name": "omen", "policy": "approve"}, {"op": "set_policy", "cls": "omen", "policy": "creator"}])
    assert res["ok"], res
    cj = json.loads((t.dir / "world-overlay" / "game" / "meta" / "classes.json").read_text(encoding="utf-8"))
    assert cj["omen"]["policy"] == "creator"
    dest = tmp_path / "run"
    TP.build(TP.load(t.dir), dest)
    from neonrp.core.registry import load_registry

    assert load_registry(dest).classes["omen"].policy == "creator"
    assert author.apply_ops(t, [{"op": "register_class", "name": "omen"}])["refused"][0]["why"].endswith("已存在")


def test_mixins_and_world_data(store, tmp_path):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    assert author.apply_ops(t, [{"op": "set_mixins", "mixins": ["economy", "nope"]}])["refused"]
    eco = json.loads((t.dir / "world-overlay" / "game" / "world" / "economy.json").read_text(encoding="utf-8"))
    eco["goods"] = {k: v for k, v in list(eco["goods"].items())[:2]}
    res = author.apply_ops(t, [{"op": "set_mixins", "mixins": ["economy"]}, {"op": "set_world_data", "name": "economy", "data": eco}])
    assert res["ok"], res
    t2 = TP.load(t.dir)
    assert t2.pack_name == "rpg+economy"
    got = json.loads((t2.dir / "world-overlay" / "game" / "world" / "economy.json").read_text(encoding="utf-8"))
    assert len(got["goods"]) == 2


def test_cover_upload_is_mirrored_to_the_workshop(store, tmp_path):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    TP.put_asset(t, "card:cover", PNG)
    out = author.mirror(TP.load(t.dir), "card:cover", TP.slot_file(TP.load(t.dir), "card:cover"))
    assert out is not None and out.is_file() and out.is_relative_to(tmp_path / "assets" / "worlds" / "mist-market")
    assert "card:cover" in (tmp_path / "assets" / "worlds" / "mist-market" / "prompts.md").read_text(encoding="utf-8")


def test_no_workshop_without_env(store, monkeypatch):
    monkeypatch.delenv("WORLDLINES_ASSETS_DIR")
    assert author.workshop("mist-market", create=True) is None


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _client(store):
    from neonrp.webui.template_routes import TemplateRoutes

    class H(TemplateRoutes):
        def __init__(self, path: str, body: dict | None = None):
            self.path, self.body, self.out, self.status = path, body, None, 200

        def _read_json_body(self):
            return self.body

        def _send_json(self, d, status=200):
            self.out, self.status = d, status

        def send_error(self, code, msg=""):
            self.out, self.status = {"error": msg}, code

    return H


def test_http_fork_ops_ui(store):
    H = _client(store)
    h = H("/api/v1/local/templates/stoneford-market/fork", {"id": "mist-market", "title": "雾市"})
    assert h._template_route_post(None) and h.status == 200 and h.out["template"]["id"] == "mist-market"
    h = H("/api/v1/local/templates/mist-market/ui")
    assert h._template_route_get(None)
    assert h.out["writable"] and "economy" in h.out["mixins_available"] and h.out["world_data"]["economy"]["markets"]
    h = H("/api/v1/local/templates/mist-market/ops", {"ops": [{"op": "edit_recipe", "key": "backend", "value": "comfy"}]})
    assert h._template_route_post(None) and h.out["ok"] and h.out["ui"]["recipe"]["backend"] == "comfy"
    h = H("/api/v1/local/templates/mist-market/ops", {"ops": [{"op": "set_budget", "value": 5}]})
    h._template_route_post(None)
    assert h.status == 422 and not h.out["ok"]
    h = H("/api/v1/local/templates/stoneford-market/ops", {"ops": [{"op": "set_budget", "value": 9000}]})
    h._template_route_post(None)
    assert h.status == 400 and "只读" in h.out["error"]



def test_delete_only_the_players_own(store):
    author.fork(TP.discover()["stoneford-market"], "mist-market")
    H = _client(store)
    h = H("/api/v1/local/templates")
    assert h._template_route_get(None)
    rows = {r["id"]: r for r in h.out["templates"]}
    assert rows["mist-market"].get("removable") and not rows["stoneford-market"].get("removable"), "the Hub offers delete on the player's own only"
    assert not author.delete("stoneford-market") and TP.discover().get("stoneford-market"), "a built-in is refused"
    assert not author.delete("no-such-one")
    assert author.delete("mist-market") and not (store / "mist-market.template").exists() and "mist-market" not in TP.discover()


def test_http_ops_sync_the_bound_run(store, tmp_path):
    t = author.fork(TP.discover()["stoneford-market"], "mist-market")
    run = tmp_path / "run"
    TP.build(TP.load(t.dir), run)

    class RT:
        root = run

    H = _client(store)
    h = H("/api/v1/local/templates/mist-market/ops", {"ops": [{"op": "set_view", "view": {"id": "omen", "title": "征兆", "bind": ["town.alert"], "widget": "number"}}]})
    h._template_route_post(RT())
    rec = json.loads((run / "game" / "meta" / "template.json").read_text(encoding="utf-8"))
    assert any(v.get("id") == "omen" for v in rec["ui"]["views"])
