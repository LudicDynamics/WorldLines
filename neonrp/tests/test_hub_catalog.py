"""线上 Hub 目录(worldlines/ui/app/hub/build_static.py + catalog.overlay.json):官方世界全在审核区。

10-15 iOS 上七夜标成了「非审核区」—— 官方世界的审核状态只有一个来源(模板 template.json 的 zone,和引擎同一处),这里锁住。
"""
from __future__ import annotations

import functools
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "worldlines" / "ui" / "app" / "hub"
OFFICIAL = ("guixiang", "wuwu", "last-train", "pct-house", "stoneford-town", "kagura-island", "spice-witch", "neon-rebirth")


@pytest.fixture(scope="module")
def bs():
    pytest.importorskip("PIL")
    spec = importlib.util.spec_from_file_location("hub_build_static", HUB / "build_static.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_official_worlds_are_listed(bs):
    listed = list(bs.load_overlay()["templates"])
    assert set(OFFICIAL) <= set(listed), f"missing from catalog.overlay.json: {set(OFFICIAL) - set(listed)}"


@pytest.mark.parametrize("tid", OFFICIAL)
def test_official_world_is_reviewed(bs, tid):
    # 区域只有一个来源:模板 template.json 的 zone(引擎 /api/v1/local/templates 读的同一处)
    from neonrp import template as TP

    assert bs.zone_of(TP.load(TP.discover()[tid]), tid) == "reviewed"


def test_overlay_has_no_zone(bs):
    doc = bs.load_overlay()
    assert "zone" not in doc and not any("zone" in v for v in doc["templates"].values())


def test_unlabelled_or_bad_zone_stops_the_build(bs):
    from types import SimpleNamespace

    assert bs.zone_of(SimpleNamespace(zone="open"), "x") == "open"
    for z in (None, "nope"):
        with pytest.raises(SystemExit):
            bs.zone_of(SimpleNamespace(zone=z), "x")


def test_page_reads_zone_not_mock():
    # 「审核区」只看 catalog / 引擎给的 zone;按 id 算的示意值(mockOf)不许回来
    js = (HUB / "hub.js").read_text(encoding="utf-8")
    assert "mockOf" not in js
    assert js.count("verified: zoneOf(x.zone) === 'reviewed'") == 2   # 引擎模式 + 静态目录


# ── 引擎模式(本地引擎 / iOS 读 /api/v1/local/templates):区域只看引擎给的 zone,没写的显示中性「未标注」──

UI = ROOT / "worldlines" / "ui"


@functools.cache
def _slots(tid):
    """引擎 /api/v1/local/templates/<id>/assets 的 slots(同一份 asset_slots);一次测试会话只算一遍"""
    from neonrp import template as TP

    found = TP.discover()
    if tid not in found:
        return None
    return [{k: v for k, v in sl.items() if k in ("slot", "cls", "name", "label", "have")} for sl in TP.asset_slots(TP.load(found[tid]))]


def _engine_mode(tmp_path, rows, hub='{"mode":"auto"}', progress=None, ui_lang=None, api=None):
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", f'<script>window.HUB={hub}</script><script>' + (HUB / "hub.js").read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    assets = {m["id"]: _slots(m["id"]) for m in rows if _slots(m["id"]) is not None}
    (tmp_path / "templates.json").write_text(json.dumps({"templates": rows, "_assets": assets, "_api": api or {}}, ensure_ascii=False), encoding="utf-8")
    extra = []
    if progress is not None or ui_lang:
        (tmp_path / "progress.json").write_text(json.dumps(progress or {}, ensure_ascii=False), encoding="utf-8")
        extra = [str(tmp_path / "progress.json")]
    if ui_lang:
        extra.append(ui_lang)
    out = subprocess.run([node, str(ROOT / "tests" / "hub_engine_mode.mjs"), str(tmp_path / "page.html"), str(tmp_path / "templates.json"),
                          str(UI / "package.json"), *extra], capture_output=True, text=True, timeout=180, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_engine_mode_zone_tags(tmp_path):
    from neonrp import template as TP

    found = TP.discover()
    rows = [TP.load(found[tid]).meta() for tid in OFFICIAL]       # 和 template_routes 列表里 checking 那一行同一份 meta()
    unlabelled = [m for m in (TP.load(d).meta() for tid, d in found.items() if tid not in OFFICIAL) if m.get("zone") is None][:2]
    assert unlabelled, "need a template without zone"
    rows += unlabelled
    got = _engine_mode(tmp_path, rows)
    assert got["errs"] == []
    tags = {c["id"]: c for c in got["cards"]}
    for tid in OFFICIAL:   # 本地版(10-24):卡片上标「本机」;详情页照样写它属于默认区
        assert tags[tid]["cls"] == "ver none" and tags[tid]["text"] == "本机", (tid, tags[tid])
        assert got["detail"][tid].endswith("默认区"), (tid, got["detail"][tid])
    for m in unlabelled:   # 没写 zone:中性,既不标默认区也不标自由区
        assert tags[m["id"]]["cls"] == "ver none" and tags[m["id"]]["text"] == "本机", (m["id"], tags[m["id"]])
        for z in ("默认区", "自由区"):
            assert z not in tags[m["id"]]["text"] and z not in got["detail"][m["id"]], (m["id"], got["detail"][m["id"]])


def _meta_rows():
    from neonrp import template as TP

    found = TP.discover()
    return [TP.load(found[tid]).meta() for tid in OFFICIAL]


def test_open_zone_entry(tmp_path):
    # 「开源区」入口(10-15):默认视图只有审核区;开源区的作品切过去才看得到;没有作品时是空状态说明
    rows = _meta_rows()
    opened = {**rows[0], "id": "someones-open-work", "zone": "open"}
    # 本地版(10-24):首页就是自由区(#/free/),没有切换按钮;本机的世界在「本机」一栏,默认区去线上 Hub
    got = _engine_mode(tmp_path, [*rows, opened])
    assert got["errs"] == [] and not got["zoneBtn"]
    assert got["open"]["cards"] == ["someones-open-work"], "#/ is the free zone page (details under #/free/t/…, test_hub_free_zone)"
    assert sorted(got["open"]["mine"]) == sorted(r["id"] for r in rows)
    got = _engine_mode(tmp_path, rows)
    assert got["open"]["cards"] == [] and got["open"]["empty"], "no free work yet: the empty note under the 本机 section"


def test_open_zone_hidden_when_disabled(tmp_path):
    # iOS 那边设 window.HUB.openZone = false:开源区入口和作品都不出现
    rows = _meta_rows()
    got = _engine_mode(tmp_path, [*rows, {**rows[0], "id": "someones-open-work", "zone": "open"}], hub='{"mode":"auto","openZone":false}')
    assert not got["zoneBtn"] and "someones-open-work" not in {c["id"] for c in got["cards"]}


def test_zone_names_in_four_languages():
    js = (HUB / "hub.js").read_text(encoding="utf-8")
    # 10-15 定名:默认区 / 自由区(代码值 reviewed / open 不变)
    for name in ("zoneOn: '默认区'", "zoneOn: 'Default Zone'", "zoneOn: 'デフォルトエリア'", "zoneOn: '기본 구역'",
                 "zoneOff: '自由区'", "zoneOff: 'Free Zone'", "zoneOff: 'フリーエリア'", "zoneOff: '자유 구역'"):
        assert name in js
    for old in ("非审核区'", "'Unreviewed'", "'未審査'", "'미심사'", "'开源区'", "'Open Zone'", "'オープンエリア'", "'오픈 구역'", "'审核区'"):
        assert old not in js


def test_legal_docs_use_open_zone_name():
    # docs/legal(线上 Hub 的 legal/ 页由它生成):旧名(非审核区 / 审核区 / 开源区)不许留下
    for f in (ROOT / "docs" / "legal").rglob("*.md"):
        text = f.read_text(encoding="utf-8")
        for old in ("非审核区", "非審査エリア", "Unreviewed Area", '"Unreviewed"', "「未审核」", "「未審査」",
                    "审核区", "开源区", "審査エリア", "オープンエリア", "Reviewed Area", "Open Zone"):
            assert old not in text, f"{f.relative_to(ROOT)}: {old}"


# ── 10-15 第三批:玩法四类 + 其他 · 主角进角色栏 · 角色页按「已获得」──

def test_play_types_are_four_contracts_plus_other():
    js = (HUB / "hub.js").read_text(encoding="utf-8")
    for k in ("'mystery-trpg': {", "'open-adventure': {", "'murder-mystery': {", "'romance-companion': {", "none: { key: 'none'"):
        assert k in js
    assert "table: { key: 'table'" not in js


@pytest.mark.parametrize("tid", ["spice-witch", "guixiang", "neon-rebirth"])
def test_player_lead_has_portrait(bs, tid, tmp_path):
    from neonrp import template as TP

    row = bs._player(TP.load(TP.discover()[tid]), tmp_path / "img", lambda p: p.relative_to(tmp_path).as_posix())
    assert row and row["role"] == "player" and row["img"], row
    assert (tmp_path / row["img"]).is_file()


def test_souls_page_owned_and_chattable_by_default(tmp_path):
    # 角色页默认 = 已获得的 + 能直接聊的(standalone,10-16:不用获得就能在小手机聊);其余在「可获得」里是灰的
    from urllib.parse import parse_qs, urlparse

    from neonrp import template as TP

    if not hasattr(TP.Template, "standalone"):
        pytest.skip("engine without Template.standalone")
    rows = _meta_rows()
    got = _engine_mode(tmp_path, rows)
    assert got["errs"] == []
    own, every = got["souls"]["owned"], got["souls"]["all"]
    free = set(own["names"])
    assert "乐师" in free and own["locked"] == 0 and not own["empty"], own   # 没获得任何角色:standalone 的照样在,不灰、有「和 ta 聊聊」
    assert len(own["go"]) == own["cards"], own
    assert every["locked"] == every["cards"] - len(free), every
    # 获得一个不是 standalone 的(塞维林 · 香料魔女,可带走):默认视图多了他,不灰;卡片 / 世界阵容 / 详情都能直接进聊天页,进的是获得的那个世界
    got = _engine_mode(tmp_path, rows, progress={"player": "local", "characters": [{"sid": "severin", "name": "塞维林", "world": "spice-witch", "how": "companion_at_ending"}], "endings": [], "achievements": []})
    assert got["errs"] == []
    own = got["souls"]["owned"]
    assert own["cards"] == len(free) + 1 and own["locked"] == 0, own
    def q(h):
        u = urlparse(h)
        return u.path, parse_qs(u.query)["tpl"][0], parse_qs(u.query)["sid"][0]
    assert ("/chat.html", "spice-witch", "severin") in [q(h) for h in own["go"]], own["go"]
    assert ("/chat.html", "spice-witch", "severin") in [q(h) for h in got["chatgo"]["cast"]["spice-witch"]], got["chatgo"]["cast"]
    assert got["chat"]["spice-witch"] == ["乐师"], got["chat"]   # 「可以直接聊」徽标只给 standalone;获得的有按钮、没徽标
    assert got["souls"]["all"]["locked"] == got["souls"]["all"]["cards"] - len(free) - 1


def test_chat_flag_from_template_standalone(tmp_path):
    # 「可以直接聊」= 作者同意单独出场(soul.json standalone: true → 引擎 meta 的 standalone);香料魔女是乐师(主角在引擎模式下不进角色栏),塞维林不是
    from neonrp import template as TP

    if not hasattr(TP.Template, "standalone"):
        pytest.skip("engine without Template.standalone")
    got = _engine_mode(tmp_path, _meta_rows())
    assert got["errs"] == [] and got["chat"]["spice-witch"] == ["乐师"], got["chat"]
    # 没获得时的「怎么获得」读模板的 take(乐师 = companion_at_ending)+ standalone 的「不用获得也能聊」
    assert got["how"] and "同伴" in got["how"] and "不用获得" in got["how"], got["how"]


def test_chat_button_opens_chat_page(tmp_path):
    # 10-16:能直接聊的角色点开就聊 —— 世界详情的阵容 · 角色列表卡 · 角色详情都有「和 ta 聊聊」,直接进 chat.html?tpl=&sid=(本地 = 引擎同源 /chat.html)
    from urllib.parse import parse_qs, urlparse

    from neonrp import template as TP

    if not hasattr(TP.Template, "standalone"):
        pytest.skip("engine without Template.standalone")
    api = {"/api/v1/chat/souls": {"souls": [{"tpl": "spice-witch", "sid": "maestro", "name": "乐师", "talked": True, "last": {"from": "soul", "kind": "text", "text": "嗯?"}}]}}
    got = _engine_mode(tmp_path, _meta_rows(), api=api)
    assert got["errs"] == []
    go = got["chatgo"]

    def target(href):
        u = urlparse(href)
        q = parse_qs(u.query)
        return u.path, q["tpl"][0], q["sid"][0], "back" in q

    # 阵容:只有能直接聊的有按钮(和「可以直接聊」徽标同一批)
    for tid, names in got["chat"].items():
        assert len(go["cast"][tid]) == len(names), (tid, go["cast"][tid], names)
    assert [target(h) for h in go["cast"]["spice-witch"]] == [("/chat.html", "spice-witch", "maestro", True)]
    cast = {target(h)[1:3] for hs in go["cast"].values() for h in hs}
    cards = [target(h)[1:3] for h in go["cards"]]
    assert ("spice-witch", "maestro") in cards and set(cards) <= cast, (cards, cast)
    assert urlparse(go["clicked"]).path == "/chat.html" and target(go["clicked"])[1:3] in cast
    assert [target(h)[:3] for h in go["soul"]] == [("/chat.html", "spice-witch", "maestro")]
    # 「我的 · 继续聊天」也直接进聊天页
    assert any(h.startswith("/chat.html?") and "sid=maestro" in h for h in got["me"]["chats"]), got["me"]["chats"]
    # 过时说法「聊天要先开一局」删掉了(四语)
    assert not got["chatgo"]["note"] or "开一局" not in got["chatgo"]["note"]
    js = (HUB / "hub.js").read_text(encoding="utf-8")
    for old in ("聊天要先开一局", "Talking starts a run first", "会話は一局を始めてから", "대화는 먼저 한 판을"):
        assert old not in js, old


def test_chat_button_online_uses_browser_engine(tmp_path):
    # 线上(静态 Hub):进浏览器引擎那份 play/chat.html;那个世界跑不了浏览器版就不给入口(徽标照旧)
    def row(i, ok):
        return {"id": i, "title": {"zh": i}, "pitch": {"zh": ""}, "tags": {"zh": []}, "lang": "zh", "endings": [], "zone": "reviewed", "browser": {"ok": ok},
                "cast": [{"sid": "a", "name": {"zh": f"甲{i}"}, "role": "npc", "chat": True}, {"sid": "b", "name": {"zh": f"乙{i}"}, "role": "npc"}]}
    cat = {"templates": [row("w1", True), row("w2", False)]}
    got = _engine_mode(tmp_path, [], hub='{"mode":"static","catalog":"catalog.json","play":"play/"}', api={"/catalog.json": cat})
    assert got["errs"] == [] and got["chat"] == {"w1": ["甲w1"], "w2": ["甲w2"]}
    go = got["chatgo"]
    assert [h.split("&lang=")[0] for h in go["cast"]["w1"]] == ["play/chat.html?tpl=w1&sid=a"] and go["cast"]["w2"] == []
    assert [h.split("&lang=")[0] for h in go["cards"]] == ["play/chat.html?tpl=w1&sid=a"]
    assert go["clicked"].startswith("http://hub.test/play/chat.html?tpl=w1&sid=a&")


def test_image_names_carry_content_hash(bs, tmp_path):
    # 图的文件名带内容哈希 → 部署时图可以上一年 immutable 缓存;目录里的路径跟着换
    (tmp_path / "img" / "w").mkdir(parents=True)
    (tmp_path / "img" / "w" / "cover.webp").write_bytes(b"a")
    (tmp_path / "img" / "w" / "cover-sm.webp").write_bytes(b"b")
    cat = {"templates": [{"cover": {"src": "img/w/cover.webp", "sm": "img/w/cover-sm.webp"}, "x": ["img/w/cover.webp", "other"]}]}
    assert bs.hash_names(tmp_path, cat) == 2
    src, sm = cat["templates"][0]["cover"]["src"], cat["templates"][0]["cover"]["sm"]
    assert src != "img/w/cover.webp" and src.startswith("img/w/cover.") and (tmp_path / src).is_file()
    assert sm.startswith("img/w/cover-sm.") and cat["templates"][0]["x"] == [src, "other"]
    assert ("img/*", "public, max-age=31536000, immutable") in bs.CACHE and ("catalog.json", "no-cache") in bs.CACHE


def test_engine_mode_card_titles_follow_ui_language(tmp_path):
    # ios2 10-15:英文界面下(iOS = 引擎模式)首页卡片标题还是中文 —— 卡片要读引擎 meta 的 cards(模板外语层的 card)
    from neonrp import template as TP

    rows = _meta_rows()
    got = _engine_mode(tmp_path, rows, ui_lang="en")
    titles = {c["id"]: c["title"] for c in got["cards"]}
    for tid in OFFICIAL:
        want = TP.load(TP.discover()[tid]).meta()["cards"]["en"]["title"]
        assert titles[tid] == want, (tid, titles[tid], want)


def test_images_fade_in_listener_on_document():
    # 图先透明、下完再淡入:监听要挂在 document 上(元素的 load 事件按规范不经过 window,挂 window 图会一直透明)
    js = (HUB / "hub.js").read_text(encoding="utf-8")
    assert "document.addEventListener('load'" in js and "\n  addEventListener('load'" not in js


def test_me_page_reads_engine_avatar_saves_and_chats(tmp_path):
    # 「我的」(engine-events 94577db4):当前分身 /api/v1/local/avatar · 局 /api/v1/play/saves · 直聊 /api/v1/chat/souls
    api = {"/api/v1/local/avatar": {"current": "lin", "avatar": {"file": "lin", "name": "林间", "summary": "一个旅人", "data": {"name": "林间", "summary": "一个旅人"}, "current": True, "portrait_url": None}},
           "/api/v1/play/saves": {"saves": [{"session_id": "s1", "name": "归乡", "template": "guixiang", "turns": 5, "last_modified": "2026-10-15T09:00:00"}]},
           "/api/v1/chat/souls": {"souls": [{"tpl": "spice-witch", "sid": "maestro", "name": "乐师", "talked": True, "last": {"from": "soul", "kind": "text", "text": "嗯?"}}]}}
    got = _engine_mode(tmp_path, _meta_rows(), api=api)
    assert got["errs"] == [] and got["me"]["avatar"] == "林间"
    assert [x.split("·")[-1].strip() for x in got["me"]["sums"]] == ["1", "1"], got["me"]


def test_avatar_start_toggle_only_where_the_lead_is_open(tmp_path):
    # 「用我的分身开局」:本地引擎有分身、世界没有固定主角(或能捏)才出现
    # 有捏人台的世界(七夜)不放开关(分身走捏人台预填);pc 用引擎 meta 自己给的(e280008e),老引擎没有就按这里的假值
    rows = _meta_rows()
    for m in rows:
        m.setdefault("pc", {"fixed": m["id"] in ("guixiang", "kagura-island", "spice-witch"), "builder": m["id"] == "neon-rebirth"})
    api = {"/api/v1/local/avatar": {"current": "lin", "avatar": {"file": "lin", "name": "林间", "data": {"name": "林间"}, "current": True, "portrait_url": None}}}
    got = _engine_mode(tmp_path, rows, api=api)
    assert got["errs"] == []
    assert sorted(got["avsw"]) == ["last-train", "pct-house", "stoneford-town", "wuwu"], got["avsw"]   # 末班车 656c3e41:player.fixed: false


@pytest.mark.parametrize("tid,want", [("spice-witch", {"fixed": True, "builder": False}), ("neon-rebirth", {"fixed": False, "builder": True}),
                                      ("wuwu", {"fixed": False, "builder": False}), ("last-train", {"fixed": False, "builder": False})])
def test_static_pc_rule_matches_engine(bs, tid, want, tmp_path):
    from neonrp import template as TP

    t = TP.load(TP.discover()[tid])
    pc = bs._pc(t, bs._player(t, tmp_path / "img", lambda p: p.relative_to(tmp_path).as_posix()))
    assert pc == want
    if "pc" in t.meta():
        assert t.meta()["pc"] == pc, "build_static 和引擎 meta 的 pc 要同一条规则"


def test_hero_without_portrait_falls_back(bs, capsys):
    # 10-16:门面角色的图在重出(槽位还在、文件拿掉了)时不退出构建 —— 打警告,按 overlay 的顺序顺延到下一个有图的
    faces = {"NPC104": object(), "NPC102": object(), "NPC101": object()}
    got = bs.pick_hero("w", ["xiulian", {"sid": "NPC104", "crop": [0, 0, 1, 1]}, "NPC102", "NPC101"], faces)
    assert got == [("NPC104", [0, 0, 1, 1]), ("NPC102", None), ("NPC101", None)]
    assert "hero 'xiulian' has no portrait" in capsys.readouterr().err
    assert bs.pick_hero("w", ["NPC101", "NPC102", "NPC104", "x"], faces) == [("NPC101", None), ("NPC102", None), ("NPC104", None)]


def test_guixiang_builds_without_xiulian_portrait(bs, tmp_path):
    # 归乡:年轻秀莲的图拿掉重出 → 门面从细妹起;角色栏里秀莲照常在(没图 = 页面上的占位);overlay 顺序不动,图回来她自动回第一位
    from neonrp import template as TP

    over = bs.load_overlay()["templates"]["guixiang"]
    assert over["hero"][0] == "xiulian"
    row = bs.entry(TP, "guixiang", TP.discover()["guixiang"], over, tmp_path, False)
    keys = [h["key"] for h in row["hero"]]
    assert keys and all((tmp_path / h["src"]).is_file() for h in row["hero"]), row["hero"]
    xl = next((r for r in row["cast"] if r["sid"] == "xiulian"), None)
    if xl is not None and xl["img"] is None:
        assert "xiulian" not in keys and keys[0] == next(h if isinstance(h, str) else h["sid"] for h in over["hero"][1:]), keys
    else:
        assert keys[0] == "xiulian", keys


def test_favicon_at_site_root(bs, tmp_path):
    # 10-16 线上控制台 /favicon.ico 403:构建在站点根放一份(品牌图标转 ico),Hub / 404 / play 页都指它
    from PIL import Image

    bs.build_index(tmp_path, {"mode": "static"})
    ico = tmp_path / "favicon.ico"
    with Image.open(ico) as im:
        assert im.format == "ICO" and (32, 32) in im.info["sizes"]
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" href="favicon.ico"' in page and '<link rel="apple-touch-icon" href="apple-touch-icon.png">' in page
    assert '<link rel="manifest" href="site.webmanifest">' in page and f'<meta property="og:image" content="{bs.SITE}/og.png">' in page
    assert 'href="/favicon.ico"' in (tmp_path / "404.html").read_text(encoding="utf-8")
    assert ("favicon.ico", "public, max-age=86400") in bs.CACHE and ("site.webmanifest", "public, max-age=86400") in bs.CACHE


def test_brand_icon_set(bs, tmp_path):
    # 10-24 新图标(三体轨道 · 深紫夜空 + 三颗星球):一张 1024 原图出的网页一套,尺寸 / 格式都对,manifest 指的文件都在
    from PIL import Image

    bs.build_index(tmp_path, {"mode": "static"})
    with Image.open(ROOT / "assets" / "brand" / "neonrp-icon-1024.png") as im:
        assert im.size == (1024, 1024)
    want = {"icon-32.png": (32, 32), "apple-touch-icon.png": (180, 180), "icon-192.png": (192, 192), "icon-512.png": (512, 512),
            "icon-maskable-512.png": (512, 512), "og.png": (1200, 630)}
    for name, size in want.items():
        with Image.open(tmp_path / name) as im:
            assert im.format == "PNG" and im.size == size, name
            if name == "apple-touch-icon.png":
                assert im.mode == "RGB", "iOS: opaque, no rounded corners of our own"
    with Image.open(tmp_path / "favicon.ico") as im:
        assert {(16, 16), (32, 32), (48, 48)} <= set(im.info["sizes"])
    # UI 象征性一点(10-24):顶栏品牌前一枚小徽记;载入中徽记轻轻呼吸,少动模式不动
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<a class="logo" href="#/"><span class="wlmark" aria-hidden="true"></span>WorldLines <i>HUB</i></a>' in page
    assert 'url("icon-192.png")' in page and "@media (prefers-reduced-motion:reduce){.wlmark.breathe{animation:none}}" in page
    js = (ROOT / "worldlines" / "ui" / "app" / "hub" / "hub.js").read_text(encoding="utf-8")
    assert "<p class=\"skmsg\">${WAIT}" in js and js.count("WAIT + esc(t('loadingW'))") == 2
    man = json.loads((tmp_path / "site.webmanifest").read_text(encoding="utf-8"))
    assert all((tmp_path / i["src"]).is_file() for i in man["icons"]) and any(i.get("purpose") == "maskable" for i in man["icons"])


def test_player_pages_meta_and_icon(tmp_path):
    # mobile-web-app-capable(apple- 前缀的已废弃,留着给 iOS);play/ 里的两页(浏览器引擎)指到站点根的 favicon
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node needed")
    player = ROOT / "worldlines" / "ui" / "player"
    subprocess.run([node, str(player / "build.mjs"), "--out", str(tmp_path / "out"), "--play", str(tmp_path / "play")], check=True, capture_output=True, timeout=120)
    for d in ("out", "play"):
        for name in ("player.html", "chat.html"):
            page = (tmp_path / d / name).read_text(encoding="utf-8")
            assert '<meta name="mobile-web-app-capable" content="yes">' in page and '<meta name="apple-mobile-web-app-capable" content="yes">' in page, (d, name)
            # play/ = 站点根往上一层;本地(out = dist-local 那样)= 引擎根上的图标(10-24 新图标)
            pre = "../" if d == "play" else "/"
            assert f'<link rel="icon" href="{pre}favicon.ico"' in page and f'<link rel="apple-touch-icon" href="{pre}apple-touch-icon.png">' in page, (d, name)


def test_player_drawer_uses_inert_not_aria_hidden():
    # 抽屉 / 地图页关着 = inert;不再用 aria-hidden(焦点留在里面会报 Blocked aria-hidden),关之前把焦点还回去
    js = (ROOT / "worldlines" / "ui" / "player" / "src" / "stage.js").read_text(encoding="utf-8")
    assert '<aside class="drawer" inert>' in js and '<section class="page" inert>' in js
    assert "setAttribute('aria-hidden'" not in js and "el.inert = off" in js


def test_local_ui_carries_the_icons(tmp_path):
    # 本地界面(测试台 / launcher · 本地 hub.html,app/build.mjs → dist-local):10-24 以前一个图标都没有;现在拷一套到引擎根、<head> 指过去
    import os
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node needed")
    ui = tmp_path / "worldlines" / "ui"
    shutil.copytree(ROOT / "worldlines" / "ui" / "app", ui / "app", ignore=shutil.ignore_patterns("node_modules", "e2e*"))
    shutil.copy(ROOT / "worldlines" / "ui" / "brand.mjs", ui / "brand.mjs")
    shutil.copytree(ROOT / "assets" / "brand" / "web", tmp_path / "assets" / "brand" / "web")
    subprocess.run([node, str(ui / "app" / "build.mjs")], cwd=str(ui), env={**os.environ, "WL_PRIVATE_UI": "off", "WL_PLAYER": "off"},
                   check=True, capture_output=True, timeout=180)
    out = ui / "dist-local"
    assert all((out / f).is_file() for f in ("favicon.ico", "apple-touch-icon.png", "icon-192.png", "site.webmanifest"))
    for page in ("index.html", "hub.html"):
        h = (out / page).read_text(encoding="utf-8")
        assert '<link rel="icon" href="/favicon.ico"' in h and '<link rel="manifest" href="/site.webmanifest">' in h, page
    assert '<div class="brand"><span class="wlmark" aria-hidden="true"></span>World<span>lines</span></div>' in (out / "index.html").read_text(encoding="utf-8")
