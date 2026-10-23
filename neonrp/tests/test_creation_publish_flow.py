"""创作台「发布作品」全流程(niko 10-24「创作台能不能测试发布作品」):网页创作台和 iOS 创作台是同一套前端,
本地 / iOS 都打这几条引擎路由(网页版是浏览器里的同一个引擎),平台是本机假的 identity + storage(test_template_publish.Platform)。

    存作品 POST …/<模板>/creation/work → 发布前检查 GET …/<作品>/publish → 提交 POST …/<作品>/publish {zone: curated}
    → 平台:draft + 审核中(快审)→ 「我的作品」GET /api/v1/local/hub/mine:默认区 · 审核中

另外几种:没登录 · 必填没填(图 / 四语卡面)· 平台出错后重试 · 同一个模板两份作品各自提交。
前端那一半(提交页、按钮、提示)在 tests/hub_create_publish.mjs(test_hub_create_publish.py)。"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from unittest.mock import patch

from test_creation_web_desk import CARD, PNG, TOWN, desk  # noqa: F401 — two official templates + the creator's store
from test_template_publish import platform  # noqa: F401 — the fake identity + storage


@contextmanager
def engine(tmp_path, monkeypatch):
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
                body = e.read() or b"{}"
                return e.code, (json.loads(body) if body[:1] == b"{" else {})
        try:
            yield call
        finally:
            server.shutdown()


def _save(call, tid="stoneford-town", wid=None, card=CARD, addition=TOWN):
    st, b = call("POST", f"/api/v1/local/templates/{tid}/creation/work", {"addition": addition, "card": card, **({"id": wid} if wid else {})})
    assert st == 200, b
    return b


def _publishes(platform):  # noqa: F811
    return [p for m, p, b in platform.calls if m == "POST" and p.endswith("/publish")]


def test_save_check_submit_then_my_works_shows_in_review(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    with engine(tmp_path, monkeypatch) as call:
        w = _save(call)
        assert w["id"] == "stoneford-town-mine"
        st, pre = call("GET", "/api/v1/local/templates/stoneford-town-mine/publish?lang=en")
        assert st == 200 and pre["checks"]["ok"] and pre["signed_in"], pre["checks"]
        st, out = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "en", "zone": "curated"})
        assert st == 200 and out["zone"] == "reviewed" and out["review"]["state"] == "pending", out
        assert "30" in out["message"], "the quick review: passes on its own in 30 minutes"
        r = platform.res[out["id"]]
        assert r["status"] == "draft" and r["review"]["state"] == "pending", "nothing public before it passes"
        st, mine = call("GET", "/api/v1/local/hub/mine?lang=en")
        row = next(x for x in mine["works"] if x["id"] == out["id"])
        assert st == 200 and row["zone"] == "reviewed" and row["review"]["state"] == "pending" and row["source"] == "stoneford-town-mine"


def test_not_signed_in_cannot_submit(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("WORLDLINES_API_KEY")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))   # no Worldlines session on this machine either
    with engine(tmp_path, monkeypatch) as call:
        _save(call)
        st, pre = call("GET", "/api/v1/local/templates/stoneford-town-mine/publish?lang=zh")
        assert st == 200 and pre["signed_in"] is False
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 401 and b.get("error") == "not_signed_in", b
        assert _publishes(platform) == [] and platform.res == {}, "nothing reaches the platform"


def test_missing_languages_or_a_required_picture_blocks_the_submit(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    with engine(tmp_path, monkeypatch) as call:
        # 四语卡面:作者只写原文(中文)也能交 —— 没写的语言沿用模板自己的卡面(表单上写明了),检查不拦;
        # 原文的标题 / 一句话简介没写,创作台在「存」之前就拦了(前端 cfNeedTitle,见 hub_create_publish.mjs)
        _save(call, card={"zh": CARD["zh"]})
        st, pre = call("GET", "/api/v1/local/templates/stoneford-town-mine/publish?lang=zh")
        assert st == 200 and pre["checks"]["ok"], pre
        from neonrp import template as TP
        from neonrp.template import i18n
        w = TP.load(TP.discover()["stoneford-town-mine"])
        assert i18n.card(w, "en").get("title") == i18n.card(TP.load(TP.discover()["stoneford-town"]), "en").get("title"), "English falls back to the template's card"
        # 结局图必填(归乡:rewards 的 ending_cg)没传:同样拦下;传了以后就能提交
        g = _save(call, tid="guixiang", card=CARD, addition={"ending": [{"title": "上谱", "kind": "true"}], "reveal": "y",
                                                            "rule": [{"trigger": {"when": {"text": "player"}, "then": [{"to": "end", "ending": "#1"}], "once": True}}]})
        end = next(s for s in g["slots"] if s["row"] == {"sec": "ending", "i": 0})
        st, b = call("POST", "/api/v1/local/templates/guixiang-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 422 and b.get("problems"), b
        st, up = call("POST", f"/api/v1/local/templates/guixiang-mine/assets/upload?slot={urllib.parse.quote(end['slot'])}&ext=.png", raw=PNG, ct="image/png")
        assert st == 200 and up["slot"]["have"]
        st, b = call("POST", "/api/v1/local/templates/guixiang-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200 and b["review"]["state"] == "pending", b


def test_a_failed_submit_can_be_retried_without_a_duplicate(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    with engine(tmp_path, monkeypatch) as call:
        _save(call)
        platform.fail["/publish"] = (503, {"error": "busy"})
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st >= 400 and b.get("message"), b
        assert not any(r["review"].get("state") == "pending" for r in platform.res.values() if r.get("review"))
        platform.fail.clear()
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200 and b["review"]["state"] == "pending", b
        assert list(platform.res) == [b["id"]], "the retry reuses the resource the first try made — no second copy"


def test_two_works_on_one_template_are_submitted_separately(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    with engine(tmp_path, monkeypatch) as call:
        _save(call)
        second = {**CARD, "zh": {"title": "雾里的第二封信", "pitch": "同一个镇子,另一个故事。"}}
        _save(call, wid="stoneford-town-mine-0a1b2c", card=second, addition={**TOWN, "clue": [{"name": "断箭", "summary": "林边的断箭"}]})
        st, a = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200, a
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine-0a1b2c/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200, b
        assert a["id"] != b["id"] and a["id"].startswith("stoneford-town-mine-") and b["id"].startswith("stoneford-town-mine-0a1b2c-")
        assert all(platform.res[i]["review"]["state"] == "pending" for i in (a["id"], b["id"]))
        st, mine = call("GET", "/api/v1/local/hub/mine?lang=zh")
        src = {x["id"]: x["source"] for x in mine["works"]}
        assert src[a["id"]] == "stoneford-town-mine" and src[b["id"]] == "stoneford-town-mine-0a1b2c"


# ── 编辑(lead 10-24:发布之外加编辑)──────────────────────────────────────────
# 现有设计(核对过,写清楚):作品在本机永远能改 ——「存」= 改写同一份作品里那一段剧情和卡面(不追加);平台上的那件只在「提交」时才变:
#   - 草稿(没提交过):改了再存就是新内容,提交时交的是最新的
#   - 已提交、还在审核中:照样能改能存;平台上排队的仍是上次交的那版,再「提交」= 同一件作品出新版本(revision +1)顶掉排队的那版,还是审核中
#   - 已上架:改了再提交 = 新版本进审核队列,通过之前线上照旧是旧版(published_revision 不动)
#   - 同一个模板的两份作品各是各的文件夹:改一份不碰另一份

def _plot(tid):
    from neonrp import template as TP

    t = TP.load(TP.discover()[tid])
    return json.loads((t.dir / "plots" / "mine" / "plot.json").read_text(encoding="utf-8")), t


def test_a_draft_edited_and_saved_again_is_rewritten_not_appended(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    from neonrp.template import i18n

    with engine(tmp_path, monkeypatch) as call:
        w = _save(call)
        cover = next(s for s in w["slots"] if s["slot"] == "card:cover")
        st, up = call("POST", f"/api/v1/local/templates/stoneford-town-mine/assets/upload?slot={urllib.parse.quote(cover['slot'])}&ext=.png", raw=PNG, ct="image/png")
        assert st == 200, up
        # 改:四语标题 · 角色换人 · 编排节奏 · 换封面
        card2 = {lg: {"title": f"{c['title']} · 改", "pitch": c["pitch"]} for lg, c in CARD.items()}
        add2 = {**TOWN, "soul": [{"name": "阿白", "persona": "爱说话的向导"}]}
        st, opts = call("GET", "/api/v1/local/templates/stoneford-town/creation")
        orch = (opts.get("orchestration") or {}).get("default") or ""
        w2 = _save(call, card=card2, addition={**add2, **({"orchestration": orch} if orch else {})})
        assert w2["id"] == "stoneford-town-mine", "the same work"
        png2 = PNG + b"\x01"
        st, up = call("POST", f"/api/v1/local/templates/stoneford-town-mine/assets/upload?slot={urllib.parse.quote(cover['slot'])}&ext=.png", raw=png2, ct="image/png")
        assert st == 200 and up["slot"]["have"]
        plot, t = _plot("stoneford-town-mine")
        names = [e.get("name") for e in plot["entries"].values() if e.get("class") == "npc"]
        assert names == ["阿白"], f"the plot is rewritten, not appended: {names}"
        assert {lg: i18n.card(t, lg).get("title") for lg in CARD} == {lg: c["title"] for lg, c in card2.items()}
        from neonrp import template as TP
        assert TP.slot_file(t, "card:cover").read_bytes() == png2, "the new cover replaced the old one"
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200
        r = platform.res[b["id"]]
        title = r["meta"].get("title")
        assert str(title["zh"] if isinstance(title, dict) else title).endswith("· 改"), f"what is submitted is the latest save: {title}"


def test_edit_while_in_review_then_submit_again_replaces_the_queued_version(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    with engine(tmp_path, monkeypatch) as call:
        _save(call)
        st, a = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200 and a["review"]["state"] == "pending"
        rev1 = platform.res[a["id"]]["revision"]
        # 审核中照样能改能存;平台上排队的还是上次那版
        _save(call, addition={**TOWN, "clue": [{"name": "断箭", "summary": "林边的断箭"}]})
        assert platform.res[a["id"]]["revision"] == rev1, "saving does not touch the platform"
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        assert st == 200 and b["id"] == a["id"] and b["revision"] == rev1 + 1 and b["review"]["state"] == "pending", b
        assert len(platform.res) == 1, "the same work, a new version — not a second work"
        assert platform.res[a["id"]]["status"] == "draft", "still nothing public"


def test_edit_a_published_work_the_old_version_stays_online(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    with engine(tmp_path, monkeypatch) as call:
        _save(call)
        st, a = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "zh", "zone": "curated"})
        platform.res[a["id"]].update(status="published", published_revision=1, review={"state": "approved"})   # the quick review passed
        _save(call, addition={**TOWN, "clue": [{"name": "断箭", "summary": "林边的断箭"}]})
        st, b = call("POST", "/api/v1/local/templates/stoneford-town-mine/publish", {"lang": "en", "zone": "curated"})
        assert st == 200 and b["id"] == a["id"] and b["revision"] == 2 and b["review"]["state"] == "pending" and "old one stays" in b["message"], b
        assert (platform.res[a["id"]]["status"], platform.res[a["id"]]["published_revision"]) == ("published", 1)
        st, mine = call("GET", "/api/v1/local/hub/mine?lang=en")
        row = next(x for x in mine["works"] if x["id"] == a["id"])
        assert row["status"] == "published" and row["review"]["state"] == "pending", "「旧版在线 · 审核中」"


def test_two_works_on_one_template_never_overwrite_each_other(desk, platform, tmp_path, monkeypatch):  # noqa: F811
    from neonrp.template import i18n

    with engine(tmp_path, monkeypatch) as call:
        _save(call)
        second = {**CARD, "zh": {"title": "雾里的第二封信", "pitch": "同一个镇子,另一个故事。"}}
        _save(call, wid="stoneford-town-mine-0a1b2c", card=second, addition={**TOWN, "soul": [{"name": "阿白", "persona": "向导"}]})
        _save(call, wid="stoneford-town-mine-0a1b2c", card={**second, "zh": {"title": "第二封信 · 改", "pitch": "改过"}},
              addition={**TOWN, "soul": [{"name": "阿黑", "persona": "船夫"}]})
        a, ta = _plot("stoneford-town-mine")
        b, tb = _plot("stoneford-town-mine-0a1b2c")
        npc = lambda p: [e.get("name") for e in p["entries"].values() if e.get("class") == "npc"]  # noqa: E731
        assert npc(a) == ["阿青"] and npc(b) == ["阿黑"]
        assert i18n.card(ta, "zh")["title"] == CARD["zh"]["title"] and i18n.card(tb, "zh")["title"] == "第二封信 · 改"
