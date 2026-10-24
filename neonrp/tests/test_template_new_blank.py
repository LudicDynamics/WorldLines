"""A template from nothing (author.blank · POST /api/v1/local/templates · `neonrp template new`), a blank character in the
library (POST /api/v1/local/souls/blank) and linking it into a world (op link_soul · POST …/<id>/souls/link)."""

from __future__ import annotations

import json

import pytest

from neonrp import template as TP
from neonrp.template import author


@pytest.fixture
def store(tmp_path, monkeypatch):
    w = tmp_path / "store"
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(w))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(w))
    monkeypatch.delenv("WORLDLINES_ASSETS_DIR", raising=False)
    return w


def _lib_soul(name="Ava"):
    from neonrp.core.souls import create_soul_dir

    return create_soul_dir(name.lower(), name=name)


def test_blank_is_writable_lints_clean_and_builds(store, tmp_path):
    t = author.blank("fog-port", title="雾港")
    assert t.dir == store / "fog-port.template" and author.writable(t) and "fog-port" in TP.discover()
    assert t.card["title"] == "雾港" and t.mode["ending"] == "open" and t.version == "0.1"
    assert not (t.dir / "world" / "souls").exists()   # the blank world's placeholders stay behind
    wm = json.loads((t.dir / "world" / "game" / "world" / "world_map.json").read_text(encoding="utf-8"))
    assert wm["name"] == "雾港"
    lint = TP.lint(t)
    assert not [p for p in lint["problems"] if p["level"] == "block"], lint["problems"]
    run = tmp_path / "run"
    rec = TP.build(t, run)
    pt = json.loads((run / "playthrough.json").read_text(encoding="utf-8"))
    assert pt["souls"] == [] and rec["id"] == "fog-port"


def test_blank_refuses_taken_ids_and_free_id_steps_past_them(store):
    author.blank("fog-port")
    with pytest.raises(TP.TemplateError):
        author.blank("fog-port")
    with pytest.raises(TP.TemplateError):
        author.blank("Bad Id")
    assert author.free_id("Fog Port") == "fog-port-2"
    assert author.free_id("雾港") == "my-world"   # no latin letters: a plain default


def test_link_soul_adds_to_the_cast(store, tmp_path):
    t = author.blank("fog-port")
    d = _lib_soul()
    res = author.apply_ops(t, [{"op": "link_soul", "lib": d.name}])
    assert res["ok"], res
    assert TP.load(t.dir).souls == [{"lib": d.name, "sid": "ava"}]
    again = author.apply_ops(t, [{"op": "link_soul", "lib": d.name, "role": "companion"}])   # the same one: no second row
    assert again["ok"] and TP.load(t.dir).souls == [{"lib": d.name, "sid": "ava", "role": "companion"}]
    assert not author.apply_ops(t, [{"op": "link_soul", "lib": "nobody"}])["ok"]
    run = tmp_path / "run"
    TP.build(TP.load(t.dir), run)
    assert [r["sid"] for r in json.loads((run / "playthrough.json").read_text(encoding="utf-8"))["souls"]] == ["ava"]


def test_link_soul_keeps_the_world_native_cast(store):
    t = author.fork(TP.discover()["stoneford-market"], "mine")
    assert author.apply_ops(t, [{"op": "set_cast", "souls": []}])["ok"]   # no cast list = every world-native soul plays
    t = TP.load(t.dir)
    native = set(TP._world_souls(TP.world_dir(t)))
    assert not t.souls and native
    d = _lib_soul()
    assert author.apply_ops(t, [{"op": "link_soul", "lib": d.name}])["ok"]
    cast = TP.load(t.dir).souls
    assert {r.get("sid") for r in cast} == native | {"ava"}


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _handler(base):
    class H(base):
        def __init__(self, path, body=None, server=None):
            self.path, self.body, self.out, self.status, self.server = path, body, None, 200, server

        def _read_json_body(self):
            return self.body

        def _send_json(self, d, status=200):
            self.out, self.status = d, status

        def send_error(self, code, msg=""):
            self.out, self.status = {"error": msg}, code

        def _cors_headers(self):
            pass

    return H


def test_http_new_template_and_link_into_the_edit_copy(store, tmp_path, monkeypatch):
    from neonrp.commands import web as _web
    from neonrp.webui.template_routes import TemplateRoutes

    H = _handler(TemplateRoutes)
    h = H("/api/v1/local/templates", {"title": "Fog Port"})
    assert h._template_route_post(None) and h.status == 200 and h.out["id"] == "fog-port"
    assert h.out["template"]["card"]["title"] == "Fog Port"
    h = H("/api/v1/local/templates", {"id": "fog-port"})
    h._template_route_post(None)
    assert h.status == 400 and not h.out["ok"]

    edit = tmp_path / "edit"   # the editor's working copy, built from the template (as POST /create/session does)
    TP.build(TP.load(store / "fog-port.template"), edit)

    class ERT:
        world_dir = edit

    class Srv:
        edit_runtime = ERT()

    monkeypatch.setattr(_web, "_try_rebind_edit_runtime", lambda server: server.edit_runtime)
    d = _lib_soul()
    h = H("/api/v1/local/templates/fog-port/souls/link", {"lib": d.name}, server=Srv())
    assert h._template_route_post(None) and h.status == 200 and h.out["ok"] and h.out["edit"] is True
    pt = json.loads((edit / "playthrough.json").read_text(encoding="utf-8"))
    assert [r["sid"] for r in pt["souls"]] == ["ava"] and (edit / "souls" / f"ava-{pt['souls'][0]['instance_id']}" / "soul.json").is_file()
    h = H("/api/v1/local/templates/fog-port/souls/link", {"lib": d.name}, server=Srv())
    h._template_route_post(None)
    assert h.out["ok"] and h.out["edit"] is False   # already there
    h = H("/api/v1/local/templates/stoneford-market/souls/link", {"lib": d.name}, server=Srv())
    h._template_route_post(None)
    assert h.status == 400 and "只读" in h.out["error"]   # a built-in world: copy it first


def test_http_blank_soul(monkeypatch):
    from neonrp.core.souls import SOUL_HOME, list_souls, read_soul_json
    from neonrp.webui.launcher_routes import LauncherRoutes

    H = _handler(LauncherRoutes)
    h = H("/api/v1/local/souls/blank", {"name": "阿雾", "intro": "码头卖鱼的姑娘"})
    assert h._launcher_route_post(None) and h.status == 200 and h.out["ok"]
    meta = read_soul_json(SOUL_HOME / h.out["soul_dir"])
    assert meta.name_local == "阿雾" and meta.summary_i18n == {"zh": "码头卖鱼的姑娘"}
    assert any(s.get("sid") == h.out["sid"] for s in list_souls())
    h2 = H("/api/v1/local/souls/blank", {"name": "阿雾"})
    h2._launcher_route_post(None)
    assert h2.out["sid"] != h.out["sid"]   # same name: a second character, not the first one again
    h3 = H("/api/v1/local/souls/blank", {"name": " "})
    h3._launcher_route_post(None)
    assert h3.status == 400


def test_cli_template_new(store):
    from click.testing import CliRunner

    from neonrp.commands.template_cmd import template_group

    r = CliRunner().invoke(template_group, ["new", "fog-port", "--title", "雾港"])
    assert r.exit_code == 0, r.output
    assert "fog-port" in TP.discover()


def test_blank_takes_pack_contract_orchestration(store):
    opts = author.new_options()
    assert "rpg" in opts["packs"]["options"] and opts["orchestration"]["options"]
    assert any(c["id"].startswith("open-adventure@") for c in opts["contracts"]["options"])
    orch = opts["orchestration"]["options"][-1]["id"]
    t = author.blank("fog-port", pack="pct", contract="open-adventure@1", orchestration=orch)
    assert t.pack_name.startswith("pct") and t.play_contract == "open-adventure@1" and t.data["uses"]["template"] == orch
    for bad in ({"pack": "nope"}, {"contract": "nope@1"}, {"orchestration": "nope"}):
        with pytest.raises(TP.TemplateError):
            author.blank("other", **bad)
    assert "other" not in TP.discover()


def test_new_world_swaps_the_world_and_keeps_the_rest(store, tmp_path):
    t = author.fork(TP.discover()["stoneford-market"], "mine")   # builtin-bound + world-overlay
    d = _lib_soul()
    assert author.apply_ops(t, [{"op": "link_soul", "lib": d.name}])["ok"]
    before = TP.load(t.dir)
    out = author.new_world(before, title="新港")
    t2 = out["template"]
    assert t2.world == {"path": "world"} and not (t2.dir / "world-overlay").exists()
    assert t2.souls == [{"lib": d.name, "sid": "ava"}] and set(out["dropped"]) >= {"elena"}   # natives left with the old world
    assert t2.card == before.card and t2.play_contract == before.play_contract and t2.plots == before.plots
    assert (store / ".world-backups").is_dir() and out["moved"] and "mine" in TP.discover()
    wm = json.loads((t2.dir / "world" / "game" / "world" / "world_map.json").read_text(encoding="utf-8"))
    assert wm["name"] == "新港"
    TP.build(t2, tmp_path / "run")
    with pytest.raises(TP.TemplateError, match="只读"):
        author.new_world(TP.discover()["stoneford-market"])


def test_http_options_and_new_world(store):
    from neonrp.webui.template_routes import TemplateRoutes

    H = _handler(TemplateRoutes)
    h = H("/api/v1/local/templates/_new")
    assert h._template_route_get(None) and "packs" in h.out
    h = H("/api/v1/local/templates", {"title": "Fog", "pack": "rpg", "contract": "open-adventure@1"})
    h._template_route_post(None)
    assert h.out["ok"] and h.out["template"]["play_contract"] == "open-adventure@1"
    h = H("/api/v1/local/templates/fog/world/new", {"title": "雾港二"})
    assert h._template_route_post(None) and h.status == 200 and h.out["ok"] and h.out["moved"] == ["world"]
