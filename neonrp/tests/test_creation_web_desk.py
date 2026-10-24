"""网页 Hub 默认区创作台(10-18 · PLATFORM-PLAY-RULES-1015 §1 §2):每个官方模板一个表单式创作台,作品进默认区、走快审。

- 表单按模板的协议和合约生成:要填的(mode.reveal / 合约的谜底 → 谜底;rewards ending_cg → 每个结局的图必填)、卡面、哪些图
- 「存」= 作者的作品(模板的一份拷贝,第一次存时建)里的一段 plot + 作者写的四语卡面;再存覆盖同一段;不能复制的官方世界也能在它开放的层里创作
- 作品的图:封面(必填)+ 每个新角色 / 结局 / 线索一张,带它属于表单哪一行
- 提交到默认区 = publish {zone: curated} → 202 待审;改版再提交:新版本进队列,通过的旧版照常在线;撤回待审
- 引擎路由:POST …/<模板>/creation/work · POST …/<作品>/publish {zone: curated} · POST /api/v1/local/hub/withdraw"""
from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest
from _paths import PRODUCT_TEMPLATES

from neonrp import template as TP
from neonrp.core import template_publish as tp
from neonrp.template import author, creation

from test_template_publish import platform  # noqa: F401 — the fake identity + storage

TPLS = PRODUCT_TEMPLATES
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """Two official templates (read-only store) + the creator's write store: stoneford-town (forkable) · guixiang (not)."""
    ro, mine = tmp_path / "official", tmp_path / "mine"
    for n in ("stoneford-town", "guixiang"):
        if n == "guixiang" and not (TPLS / f"{n}.template").is_dir():
            continue  # not a shipped template: the open repo has only stoneford-town (the cases that need it skip)
        shutil.copytree(TPLS / f"{n}.template", ro / f"{n}.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    return mine


def _t(tid):
    return TP.load(TP.discover()[tid])


TOWN = {"soul": [{"name": "阿青", "persona": "沉默的猎人", "collect": "clear"}],
        "ending": [{"title": "雾散", "kind": "true", "text": "雾散了"}],
        "clue": [{"name": "脚印", "summary": "泥里的脚印"}],
        "rule": [{"trigger": {"when": {"text": "player"}, "if": [{"text": "脚印"}], "then": [{"to": "end", "ending": "#1"}], "once": True}}]}
CARD = {"zh": {"title": "雾夜猎人", "pitch": "雾里有人在追脚印。"}, "en": {"title": "The Fog Hunter", "pitch": "Someone follows footprints in the fog."},
        "ja": {"title": "霧夜の猟師", "pitch": "霧の中で足跡を追う者がいる。"}, "ko": {"title": "안개 밤의 사냥꾼", "pitch": "안개 속에서 발자국을 쫓는 사람이 있다."}}


def test_the_form_asks_what_the_mode_and_contract_need(desk):
    town, gx = creation.form(_t("stoneford-town")), creation.form(_t("guixiang"))
    assert town["card"] == ["title", "pitch"] and "reveal" not in town
    assert town["images"] == [{"for": "card", "name": "cover", "required": True}, {"for": "soul", "name": "portrait"},
                              {"for": "ending", "name": "art"}, {"for": "clue", "name": "image"}]
    assert gx["reveal"]["required"] is True and gx["reveal"]["template"]["zh"], "归乡 plays with mode.reveal: every plot carries the truth"
    assert {"for": "ending", "name": "art", "required": True} in gx["images"], "its contract rewards ending CGs"
    add = {"ending": [{"title": "上谱", "kind": "true"}]}
    assert "reveal: required" in creation.check(_t("guixiang"), add)
    assert creation.check(_t("guixiang"), {**add, "reveal": "其实是他自己"}) == []
    assert "the template does not ask for a reveal" in creation.check(_t("stoneford-town"), {"reveal": "x"})


def test_save_makes_one_work_and_saving_again_rewrites_it(desk):
    w = creation.save(_t("stoneford-town"), TOWN, work_id="stoneford-town-mine", card=CARD)
    assert w.id == "stoneford-town-mine" and w.dir.parent == desk and w.data["forked_from"]["creation"] is True
    plot = json.loads((w.dir / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    assert plot["classes"]["clue"]["clue"] is True, "clues are a class the plot declares itself"
    assert plot["collect"] == {"mine_N01": {"on": "clear", "rarity": "common"}}
    assert not [p for p in TP.lint(w.dir)["problems"] if p["level"] == "block"], "a filled-in form lints clean"
    assert not [p for p in TP.lint(w.dir)["problems"] if p["code"] == "plot" and "unknown top-level key" in p["msg"]]
    cs = tp.cards(w)
    assert {lg: cs[lg]["_own"]["title"] for lg in cs} == {lg: c["title"] for lg, c in CARD.items()}, "the card in four languages"
    assert tp.preflight(w, lang="zh") == [], "secrets · lint · four-language card · cover: the local desk's own checks pass"
    w2 = creation.save(_t("stoneford-town"), {**TOWN, "soul": []}, work_id="stoneford-town-mine")
    assert w2.data["plots"].count("plots/mine") == 1
    assert "mine_N01" not in json.loads((w2.dir / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))["entries"]
    assert tp.cards(w2)["en"]["_own"]["title"] == "The Fog Hunter", "no card sent = the card stays"
    with pytest.raises(TP.TemplateError):
        creation.save(_t("guixiang"), {"ending": [{"title": "x", "kind": "true"}], "reveal": "y"}, work_id="stoneford-town-mine")
    with pytest.raises(TP.TemplateError, match="required"):
        creation.save(_t("stoneford-town"), {"soul": [{"name": "无名"}]}, work_id="stoneford-town-mine")


def test_an_official_world_that_cannot_be_copied_still_takes_creations(desk):
    gx = _t("guixiang")
    assert not TP.can_fork(gx)
    with pytest.raises(TP.TemplateError):
        author.fork(gx, "gx-copy")
    w = creation.save(gx, {"ending": [{"title": "上谱", "kind": "true"}], "clue": [{"name": "族谱", "summary": "被划掉的名字"}],
                           "rule": [{"trigger": {"when": {"text": "player"}, "if": [{"text": "族谱"}], "then": [{"to": "end", "ending": "#1"}], "once": True}}],
                           "reveal": "其实是他自己"}, work_id="guixiang-mine", card=CARD)
    sl = {s["slot"]: s for s in creation.slots(w)}
    end = sl["plot:plots/mine:ending:mine_E1"]
    assert (end["row"], end["name"], end["need"], end["have"]) == ({"sec": "ending", "i": 0}, "art", True, False)
    assert sl["card:cover"]["need"] and sl["card:cover"]["have"] and sl["card:cover"]["row"] == {"sec": "card", "i": 0}
    assert sl["plot:plots/mine:entry:mine_C01"]["row"] == {"sec": "clue", "i": 0} and not sl["plot:plots/mine:entry:mine_C01"]["need"]
    assert [p["code"] for p in tp.preflight(w, lang="zh")] == ["lint"], "the ending's picture is still missing"
    TP.put_asset(w, end["slot"], PNG)
    w = _t("guixiang-mine")
    assert next(s for s in creation.slots(w) if s["slot"] == end["slot"])["have"]
    assert tp.preflight(w, lang="zh") == []


def test_submit_to_the_default_zone_then_a_new_version_then_withdraw(desk, platform):  # noqa: F811
    w = creation.save(_t("stoneford-town"), TOWN, work_id="stoneford-town-mine", card=CARD)
    out = tp.publish(w, lang="zh", zone="curated")
    wid, ref = out["id"], out["ref"]
    assert wid.startswith("stoneford-town-mine-") and len(wid.rsplit("-", 1)[1]) == 6, "a non-official work id carries -<6 hex>"
    assert (out["zone"], out["review"]["state"]) == ("reviewed", "pending") and "30" in out["message"]
    assert [b for m, p, b in platform.calls if p.endswith("/publish")][-1] == {"zone": "curated"}
    assert platform.res[wid]["status"] == "draft", "nothing is public before it passes"
    # approved (the quick review) → the author changes it and submits again: the new version waits, the approved one stays
    platform.res[wid].update(status="published", published_revision=1, review={"state": "approved"})
    w = creation.save(_t("stoneford-town"), {**TOWN, "clue": [{"name": "断箭", "summary": "林边的断箭"}]}, work_id="stoneford-town-mine")
    again = tp.publish(w, lang="en", zone="curated")
    assert again["id"] == wid and again["revision"] == 2 and again["review"]["state"] == "pending" and "old one stays" in again["message"]
    assert [b for m, p, b in platform.calls if p.endswith("/publish")][-1] == {}, "a published work keeps its zone"
    assert (platform.res[wid]["status"], platform.res[wid]["published_revision"]) == ("published", 1)
    row = next(x for x in tp.mine() if x["id"] == wid)
    assert row["zone"] == "reviewed" and row["review"]["state"] == "pending" and row["source"] == "stoneford-town-mine"
    back = tp.withdraw(wid, lang="ja")
    assert back["ok"] and back["work"]["review"]["state"] == "approved" and "取り下げ" in back["message"]
    with pytest.raises(tp.PublishError) as e:
        tp.withdraw(wid)
    assert e.value.code == "platform_error", "nothing pending any more"


def test_a_free_zone_work_asks_to_move_up(desk, platform):  # noqa: F811
    w = creation.save(_t("stoneford-town"), TOWN, work_id="stoneford-town-mine", card=CARD)
    wid = tp.publish(w)["id"]
    assert platform.res[wid]["zone"] == "open"
    out = tp.publish(w, lang="zh", zone="curated")
    assert out["zone"] == "open" and out["review"]["state"] == "pending" and "申请" in out["message"]
    assert platform.steps()[-1] == f"/auth/v1/resources/hub/template/{wid}/submit"


def test_desk_routes(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(method, path, b=None, raw=None, ct="application/json"):
            data = raw if raw is not None else (json.dumps(b).encode() if b is not None else None)
            req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": ct})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                raw = e.read() or b"{}"
                return e.code, (json.loads(raw) if raw[:1] == b"{" else {})
        try:
            st, b = call("POST", "/api/v1/local/templates/stoneford-town/creation/work", {"addition": {"soul": [{"name": "x"}]}})
            assert st == 400 and any("persona: required" in p for p in b["problems"])
            st, b = call("POST", "/api/v1/local/templates/guixiang/creation/work",
                         {"addition": {"ending": [{"title": "上谱", "kind": "true"}], "reveal": "y",
                                       "rule": [{"trigger": {"when": {"text": "player"}, "then": [{"to": "end", "ending": "#1"}], "once": True}}]},
                          "card": CARD})
            assert st == 200 and b["id"] == "guixiang-mine" and b["plot"] == "plots/mine", b
            end = next(s for s in b["slots"] if s["row"] == {"sec": "ending", "i": 0})
            assert end["need"] and not end["have"]
            st, up = call("POST", f"/api/v1/local/templates/guixiang-mine/assets/upload?slot={urllib.parse.quote(end['slot'])}&ext=.png", raw=PNG, ct="image/png")
            assert st == 200 and up["slot"]["have"], up
            st, b = call("GET", "/api/v1/local/templates/guixiang-mine/publish?lang=zh")
            assert st == 200 and b["checks"]["ok"] and b["signed_in"], b["checks"]
            st, b = call("POST", "/api/v1/local/templates/guixiang-mine/publish", {"lang": "zh", "zone": "curated"})
            assert st == 200 and b["zone"] == "reviewed" and b["review"]["state"] == "pending", b
            st, w = call("POST", "/api/v1/local/hub/withdraw", {"id": b["id"], "lang": "en"})
            assert st == 200 and w["ok"] and "withdrawn" in w["message"]
            st, b = call("POST", "/api/v1/local/templates/stoneford-town/creation/work", {"addition": TOWN, "id": "guixiang-mine"})
            assert st == 409, "a work made from another template"
        finally:
            server.shutdown()


def test_the_online_catalog_carries_the_whole_form(tmp_path):
    """The web Hub draws the desk from catalog.json (build_static.entry): the whole form, card / reveal / pictures included."""
    import importlib.util
    import sys

    pytest.importorskip("PIL")
    hub = Path(__file__).resolve().parents[1] / "worldlines" / "ui" / "app" / "hub"
    spec = importlib.util.spec_from_file_location("hub_build_static_desk", hub / "build_static.py")
    bs = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bs
    spec.loader.exec_module(bs)
    over = bs.load_overlay()["templates"]
    found = TP.discover()
    row = bs.entry(TP, "guixiang", found["guixiang"], over.get("guixiang") or {}, tmp_path, False)
    f = row["creation"]["form"]
    assert row["creation"]["open"] and f == creation.form(_t("guixiang"))
    assert f["reveal"]["required"] is True and {"for": "card", "name": "cover", "required": True} in f["images"]
    assert {s for s, _ in bs.LEGAL} >= {"creator-agreement", "content-policy"}, "the submit page links both"


def test_my_works_carry_the_quick_review_eta(desk, platform):  # noqa: F811
    """The quick review's author fields (platform 86cb3f4): autopass_at → 「预计 xx 上线」· held → 「有问题待处理」."""
    w = creation.save(_t("stoneford-town"), TOWN, work_id="stoneford-town-mine", card=CARD)
    wid = tp.publish(w, zone="curated")["id"]
    platform.res[wid]["review"] = {"state": "pending", "autopass_at": "2026-10-18T10:30:00Z", "held": False}
    rv = next(x for x in tp.mine() if x["id"] == wid)["review"]
    assert rv == {"state": "pending", "note": None, "autopass_at": "2026-10-18T10:30:00Z", "held": False}
    platform.res[wid]["review"] = {"state": "pending"}
    assert next(x for x in tp.mine() if x["id"] == wid)["review"] == {"state": "pending", "note": None}, "an older platform: no new fields"


def test_a_big_upload_gets_time_for_its_size(monkeypatch):
    """The browser engine's upload is one synchronous XHR: its timeout grows with the bytes (≥ 64 KB/s on top of a minute),
    and a signed PUT that times out is sent once more (lead 10-18: a 10 MB package under load timed out at 60 s)."""
    import urllib.error

    from neonrp.core import replay_share as rs

    seen = []

    def urlopen(req, timeout):
        seen.append(timeout)
        if len(seen) == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))

        class R:
            status = 200
            def read(self): return b""
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R()

    monkeypatch.setattr(rs.urllib.request, "urlopen", urlopen)
    st, _ = rs._call("PUT", "https://s3.example/x", None, raw=b"x" * (10 << 20), platform=False, step="put")
    assert st == 200 and len(seen) == 2 and seen[0] == pytest.approx(60 + (10 << 20) / rs.UPLOAD_FLOOR_BPS)
    seen.clear()
    with pytest.raises(rs.ShareError):
        rs._call("POST", "https://auth.example/v1/x", "t", {"a": 1}, step="register")   # a platform call is not retried
    assert len(seen) == 1 and seen[0] == pytest.approx(60, abs=0.01)


def test_block_an_author_by_a_work(desk, platform, monkeypatch):  # noqa: F811
    """App Store 1.2: a player blocks the author of a work (identity feat/block-owner): their works leave the listings the
    engine reads with the player's token; unblock brings them back; your own work cannot be blocked."""
    w = creation.save(_t("stoneford-town"), TOWN, work_id="stoneford-town-mine", card=CARD)
    wid = tp.publish(w)["id"]   # the free zone: public at once (the author's)
    assert [x["id"] for x in tp.open_works()] == [wid]
    with pytest.raises(tp.PublishError) as e:
        tp.block(wid)
    assert e.value.code == "platform_error", "your own work (400 cannot_block_self)"
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
    out = tp.block(wid, lang="zh")
    assert out["ok"] and out["created"] and "屏蔽" in out["message"]
    assert tp.open_works() == [], "the listing the reader asks for leaves the blocked author out"
    assert [b["ref"]["id"] for b in tp.blocks()] == [wid]
    assert tp.unblock(wid, lang="en")["unblocked"] is True
    assert [x["id"] for x in tp.open_works()] == [wid]


def test_an_approved_community_work_comes_down_to_play_not_labelled_official(desk, platform, monkeypatch, tmp_path):  # noqa: F811
    """10-21: iOS plays approved community works — fetched into the official cache like an official world, but it is
    the creator's, so it must not say official."""
    w = creation.save(_t("stoneford-town"), TOWN, work_id="stoneford-town-mine", card=CARD)
    wid = tp.publish(w, zone="curated")["id"]
    platform.res[wid].update(status="published", published_revision=1, review={"state": "approved"})   # the quick review passed
    monkeypatch.setenv("NEONRP_OFFICIAL_DIR", str(tmp_path / "official"))
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
    row = next(x for x in tp.official_works()["works"] if x["id"] == wid)
    assert row["official"] is False
    out = tp.fetch_official(wid, lang="zh")
    t = TP.load(TP.discover()[out["id"]])
    assert t.dir.parent == tmp_path / "official" and t.zone == "reviewed" and not t.official and t.data["hub_ref"] == f"hub/template/{wid}"
    m = t.meta()   # the template list tells the UI it came from the Hub (report / block the author), still not official
    assert m["hub_ref"] == f"hub/template/{wid}" and "official" not in m


def test_the_form_carries_the_templates_own_truth():
    """lead 10-23: the desk starts from the template's words — its truth comes with the form, per language."""
    f = creation.form(_t("guixiang"))
    rv = f["reveal"]["template"]
    assert set(rv) >= {"zh", "en", "ja", "ko"} and all(v.strip() for v in rv.values())
    assert "template" not in (creation.form(_t("stoneford-town")).get("reveal") or {})


def test_two_works_on_one_template_each_name_it(desk):  # noqa: F811
    """lead 10-23: one template, several works — the first keeps <template>-mine, the next are <template>-mine-<6 hex>;
    the template list says which template each came from (work_of), the template itself says nothing."""
    t = _t("stoneford-town")
    a = creation.save(t, TOWN, work_id="stoneford-town-mine", card=CARD)
    b = creation.save(t, TOWN, work_id="stoneford-town-mine-0a1b2c", card=CARD)
    assert a.dir != b.dir and a.meta()["work_of"] == b.meta()["work_of"] == "stoneford-town"
    assert "work_of" not in t.meta()


def test_soul_names_per_language():
    """ios4 10-23: the local Hub (iOS) showed every character's Chinese name in every language."""
    from neonrp.template import i18n
    t = _t("stoneford-town")
    labels = {s["slot"].split(":", 1)[1]: s.get("label") for s in TP.asset_slots(t) if s.get("cls") == "soul" and s.get("name") == "portrait"}
    n = i18n.soul_names(t, labels)
    assert n["elena"]["en"] == "Elena Vale" and n["elena"]["zh"] == "艾琳娜" and n["elena"]["ja"] and n["elena"]["ko"]
