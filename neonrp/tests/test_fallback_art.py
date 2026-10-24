"""没图时的占位图(10-17:没有角色素材的人显示问号不好看)—— core/fallback_art。

人:按 soul.json / profile.json / NPC 行里已有的 gender / age / 外貌 / 简介(四语)选「男 / 女 × 儿童 / 青年 / 中年 / 老年」,
推断不出男女 = 中性;物:按名字 / 类别字段选图标,对不上 = 通用图标。词表在 schema/fallback_art.json,接口里给 id,前端只认 id。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import fallback_art as F
from neonrp.core import people, worldmap
from neonrp.core.registry import load_registry


# ── people, four languages ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("src, want", [
    ({"summary": "21岁，刚抵达石津镇的失忆女治愈师。她只记得自己的名字。"}, "f-young"),
    ({"description": "年约四十的壮硕女性，左脸有一道旧刀疤。"}, "f-adult"),
    ({"description": "白发苍苍的老人，拄着拐杖，他总在门口晒太阳。"}, "m-elder"),
    ({"intro": "七八岁的小男孩，跟在姐姐身后。"}, "m-child"),
    ({"intro_i18n": {"ja": "十六歳の少女。彼女は神社の巫女をしている。"}}, "f-young"),
    ({"description": "四十がらみの、がっしりした体格の男性。彼は鉱夫頭だ。"}, "m-adult"),
    ({"intro": "腰の曲がったお婆さん。"}, "f-elder"),
    ({"intro_i18n": {"ko": "열 살 소녀. 그녀는 마을 아이들과 논다."}}, "f-child"),
    ({"description": "마흔 줄의 다부진 여성."}, "f-adult"),
    ({"summary": "젊은 남자. 그는 항구에서 일한다."}, "m-young"),
    ({"intro": "A 60-year-old lighthouse keeper; he lost his daughter years ago."}, "m-elder"),
    ({"appearance": "a little girl in a red coat", "summary": "She is eight."}, "f-child"),
    ({"summary": "A middle-aged woman who runs the inn."}, "f-adult"),
    ({"summary": "A young man with a quick grin. He wants a legend."}, "m-young"),
])
def test_person_inferred_in_four_languages(src, want):
    assert F.portrait(src) == want


def test_explicit_fields_win_over_words():
    assert F.portrait({"gender": "female", "age": 70, "summary": "他是她的爷爷"}) == "f-elder"
    assert F.portrait({"sex": "M", "age": "12"}) == "m-child"
    assert F.portrait({"gender": "男", "summary": "一位少女的护卫"}) == "m-young"  # gender known, no age → a young adult
    assert F.portrait({"portrait_fallback": "f-adult", "summary": "he"}) == "f-adult"  # the world picked one itself
    assert F.portrait({"portrait_fallback": "dragon", "summary": "她"}) == "f-young"  # an unknown id is ignored


@pytest.mark.parametrize("src", [
    {}, {"name": "角色A"}, {"summary": "义手泛着紫光的技师,你的搭档,嘴上从不饶人。"},
    {"summary": "他和她一起长大"},  # the same weight each way: can't tell
    {"tags": ["spice-witch", "inquisitor"]},  # a world id is not the word witch
    {"summary": "其他人都走了,只剩下吉他声。"},  # 其他 / 吉他 are not 他
])
def test_nothing_to_go_on_is_neutral(src):
    assert F.portrait(src) == "n-adult"


def test_kinship_words_count_less_than_the_person_themself():
    # a retired detective hunting whoever erased his daughter: 娘 / daughter is somebody else
    assert F.gender({"summary": "元刑事の男性、58歳。娘を抹消した者を探している。"}) == "m"
    assert F.gender({"summary": "她的父亲在码头做工。"}) == "f"


def test_describing_fields_before_the_story():
    # the description says who this is; the story is mostly about the witch he hunts
    prof = {"appearance": "一个男人的声音"}
    sj = {"intro_i18n": {"zh": "她年长、知道得比她多,她唯一的同伴"}}
    assert F.portrait(sj, prof) == "m-young"


def test_soul_dir_reads_soul_json_and_profile(tmp_path):
    d = tmp_path / "souls" / "x-si-x0001"
    (d / "character").mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"sid": "x", "name_local": "某人", "intro_i18n": {"en": "She keeps the shop."}}), encoding="utf-8")
    (d / "character" / "profile.json").write_text(json.dumps({"age": 47}), encoding="utf-8")
    assert F.soul_dir(d) == "f-adult"
    assert F.soul_dir(None) == "n-adult" and F.soul_dir(tmp_path / "missing") == "n-adult"


def test_the_words_live_in_the_data_file_not_the_code():
    src = (Path(F.__file__)).read_text(encoding="utf-8")
    for w in ("她", "彼女", "그녀", "钥匙", "열쇠", "물약", "elixir"):
        assert w in F.DATA.read_text(encoding="utf-8") and f'"{w}"' not in src
    t = F.table()
    assert set(t["portrait"]["ids"]) == {"f-child", "f-young", "f-adult", "f-elder", "m-child", "m-young", "m-adult", "m-elder", "n-adult"}


# ── items ──────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, want", [
    ("地窖钥匙", "item-key"), ("合鍵", "item-key"), ("녹슨 열쇠", "item-key"), ("the cellar key", "item-key"),
    ("委托信", "item-letter"), ("古い手紙", "item-letter"), ("낡은 편지", "item-letter"), ("a torn letter", "item-letter"),
    ("烧了一半的日记", "item-book"), ("革表紙の手帳", "item-book"), ("일기장", "item-book"), ("old diary", "item-book"),
    ("短剑", "item-weapon"), ("錆びた短剣", "item-weapon"), ("단검", "item-weapon"), ("rusty dagger", "item-weapon"),
    ("一瓶药水", "item-potion"), ("ポーション", "item-potion"), ("물약", "item-potion"), ("healing potion", "item-potion"),
    ("艾琳娜的银坠", "item-jewelry"), ("銀の指輪", "item-jewelry"), ("은반지", "item-jewelry"), ("silver locket", "item-jewelry"),
    ("扳手", "item-tool"), ("虫眼鏡", "item-tool"), ("망치", "item-tool"), ("brass compass", "item-tool"),
    ("面包", "item-food"), ("おにぎり", "item-food"), ("주먹밥", "item-food"), ("an apple", "item-food"),
    ("三枚金币", "item-coin"), ("金貨", "item-coin"), ("금화", "item-coin"), ("gold coins", "item-coin"),
    ("灰呢大衣", "item-clothing"), ("黒いマント", "item-clothing"), ("검은 망토", "item-clothing"), ("wool cloak", "item-clothing"),
    ("木箱", "item-container"), ("古い鞄", "item-container"), ("가죽 가방", "item-container"), ("iron chest", "item-container"),
    ("墙上的新灰", "item-generic"), ("広場の大画面", "item-generic"), ("이상한 것", "item-generic"), ("strange thing", "item-generic"),
])
def test_item_icon_by_name_four_languages(name, want):
    assert F.icon(name=name) == want


def test_lights_are_not_tools():
    # 手电 / 灯 / 蜡烛:照明自成一类,没有 item-light 的图之前按数据文件里的 alias 显示成「其他」(不是锤子扳手)
    for n in ("懐中電灯", "手电筒", "提灯", "罩灯", "蜡烛", "손전등", "양초", "oil lantern", "a candle"):
        assert F.icon(name=n) == "item-other", n
    assert F.table()["item"]["alias"]["item-light"] == "item-other"


def test_item_head_noun_and_category():
    assert F.icon(name="金色项链") == "item-jewelry"  # 金 (coin) and 项链: the head noun wins the tie
    assert F.icon(name="装钥匙的盒子") == "item-container"
    assert F.icon({"category": "weapon"}, name="祖传之物") == "item-weapon"  # the category field counts
    assert F.icon({"tags": ["food"]}, name="一个钥匙形的饼干") == "item-food"


# ── what the engine hands the screen ───────────────────────────────────────────────────────────────────────

def _run(tmp_path: Path, name: str = "pct-house") -> Path:
    dest = tmp_path / f"run-{name}"
    TP.build(TP.load(PRODUCT_TEMPLATES / f"{name}.template"), dest, lang="zh")
    return dest


def test_map_entities_and_people_carry_portrait_fallback(tmp_path):
    root = _run(tmp_path)
    tree = worldmap.build_map_tree(root)
    souls = {e["id"]: e for e in tree["entities"] if e["kind"] == "soul"}
    assert souls["butler"]["portrait_fallback"] == "m-elder"  # 奥斯温, the old butler
    assert souls["chara"]["portrait_fallback"] == "f-young"  # 温妮
    me = next(e for e in tree["entities"] if e["kind"] == "player")
    assert me["portrait_fallback"] in F.table()["portrait"]["ids"]
    for e in tree["entities"]:
        assert e["portrait_fallback"] in F.table()["portrait"]["ids"]
    for p in people.people(root)["people"]:
        assert p["portrait_fallback"] in F.table()["portrait"]["ids"]


def test_npc_rows_carry_portrait_fallback(tmp_path):
    root = _run(tmp_path, "stoneford-three-towns")
    tree = worldmap.build_map_tree(root)
    npc = {e["name"]: e for e in tree["entities"] if e["kind"] == "npc"}
    hit = next(v for k, v in npc.items() if k.startswith("卡萨"))  # 「年约四十的壮硕女性」
    assert hit["portrait_fallback"] == "f-adult"


def test_slots_and_entities_carry_the_stand_ins(tmp_path):
    t = TP.load(PRODUCT_TEMPLATES / "pct-house.template")
    rows = TP.asset_slots(t)
    soul = next(r for r in rows if r["slot"] == "soul.portrait:butler")
    assert soul["portrait_fallback"] == "m-elder"
    icons = {r["label"]: r["icon_fallback"] for r in rows if r.get("icon_fallback")}
    assert icons.get("地窖钥匙") == "item-key" and icons.get("委托信") == "item-letter" and icons.get("烧了一半的日记") == "item-book"

    from neonrp.webui.schema_routes import schema_view

    root = _run(tmp_path)
    reg = load_registry(root)
    ents = schema_view(root)["entries"]
    for cls, rows in ents.items():
        for r in rows:
            if reg.is_person(cls):
                assert "icon_fallback" not in r
            elif cls == "item-generic":
                assert r["icon_fallback"] in F.table()["item"]["ids"]
