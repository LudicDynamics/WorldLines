"""「查看」人 / 物 / 地方(niko 10-16:点了只把名字再显示一遍、没有详细介绍)—— core/inspect。

GET /api/v1/play/engine/inspect?target= → 玩家知道的:人 = 一句简介 · 外貌 · 关系(不给 background / persona / truth);
物 = 世界写的描述 · 来历;POST 同一个:没描述的东西 / 人(只写外在印象)/ 地方现写一段(一次模型调用,本局语言),存进这一局的 entries 覆盖层
(模板不动),之后的读、entities、[inspect …] 动作都用它;写不出来只有名字、不缓存。stub,不调真模型。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import inspect as I
from neonrp.core import player_action
from neonrp.core.llm import LLMResponse
from neonrp.core.output_lang import write_output_lang
from neonrp.core.registry import load_registry


class FakeAdapter:
    def __init__(self, raw: str = "", error: str | None = None):
        self.raw, self.error, self.calls, self.max_tokens = raw, error, [], 4096

    def generate(self, system, user, tools=None):
        self.calls.append((system, user))
        # the adapter flags plain text (no proposal JSON) as an error — the text still counts
        return LLMResponse(proposal_text=None, raw_output=self.raw, usage={"total_tokens": 7}, error=self.error or ("no json" if self.raw else None))


def _run(tmp_path: Path, lang: str = "zh", name: str = "pct-house") -> Path:
    dest = tmp_path / f"run-{name}-{lang}"
    TP.build(TP.load(PRODUCT_TEMPLATES / f"{name}.template"), dest, lang=lang)
    write_output_lang(dest, lang)
    return dest


def _strip_desc(root: Path, eid: str) -> None:
    """A thing the world wrote no description for (the run's copy only)."""
    p = root / "game" / "meta" / "entries.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d[eid]["props"] = {k: v for k, v in d[eid]["props"].items() if k != "summary"}
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_a_person_as_the_player_knows_them(tmp_path):
    root = _run(tmp_path)
    d = I.detail(root, "si-butler0001")
    assert d["found"] and d["kind"] == "person" and d["name"] == "奥斯温" and d["sid"] == "butler"
    assert "老管家" in d["intro"] and "燕尾服" in d["appearance"] and d["relation"] and d["here"]
    assert I.detail(root, "butler")["id"] == "si-butler0001", "the screen keys people by sid"
    secrets = (root / "souls" / "butler-si-butler0001" / "background" / "secrets.md")
    flat = json.dumps(d, ensure_ascii=False)
    if secrets.is_file():
        for line in [x.strip("-# ") for x in secrets.read_text(encoding="utf-8").splitlines() if len(x.strip()) > 12][:5]:
            assert line not in flat, "no secrets"
    rel = json.loads((root / "souls" / "butler-si-butler0001" / "persona" / "relationships.json").read_text(encoding="utf-8"))
    truth = ((rel.get("relationships") or {}).get("player") or {}).get("truth")
    assert not truth or truth not in flat, "no relationship truth"
    assert not {"persona", "rules", "goals", "truth", "secrets"} & set(d)


def test_someone_not_met_and_not_here_is_not_known(tmp_path):
    root = _run(tmp_path, name="kagura-island")
    reg = load_registry(root)
    away = [e for e in reg.of_class("soul") if e.parent != reg.player_location]
    assert away
    assert I.detail(root, away[0].id) == {"lang": "zh", "found": False, "target": away[0].id}


def test_a_thing_with_the_worlds_description_and_where_it_came_from(tmp_path):
    root = _run(tmp_path)
    letter = I.detail(root, "I804")
    assert letter["kind"] == "item" and letter["held"] and "火漆" in letter["desc"] and letter["desc_by"] == "world"
    assert letter["source"] == "开局时就带在身上" and not letter["needs_desc"]
    portrait = I.detail(root, "宅主人的肖像")
    assert portrait["source"] == "在门厅" and not portrait["held"]
    fake = FakeAdapter("不该被调用")
    assert I.describe(root, "I806", adapter=fake)["desc"] == portrait["desc"] and fake.calls == []
    assert I.detail(root, "I805") == {"lang": "zh", "found": False, "target": "I805"}, "a thing not come across yet"
    assert I.detail(root, "T001/hall")["kind"] == "place" and I.detail(root, "T001/hall")["desc"]


def test_a_thing_with_no_description_gets_one_written_once(tmp_path):
    root = _run(tmp_path)
    _strip_desc(root, "I806")
    tpl_before = (PRODUCT_TEMPLATES / "pct-house.template" / "world" / "game" / "meta" / "entries.json").read_bytes() \
        if (PRODUCT_TEMPLATES / "pct-house.template" / "world" / "game" / "meta" / "entries.json").is_file() else b""
    d = I.detail(root, "I806")
    assert d["needs_desc"] and d["desc"] == ""
    assert player_action.perform(root, "inspect", "I806", turn=1)["text"].startswith("宅主人的肖像"), "before: the name"
    fake = FakeAdapter("「画布边缘起了细裂,油彩的气味还没散尽。」")
    out = I.describe(root, "I806", adapter=fake)
    assert out["generated"] and out["desc"] == "画布边缘起了细裂,油彩的气味还没散尽。" and out["desc_by"] == "inspect"
    system, user = fake.calls[0]
    assert system.startswith("你在为一个跑团世界里的一样东西写") and "宅主人的肖像" in user and "灰橡宅" in user
    assert "gm-truth" not in user and fake.max_tokens <= 400
    # kept in the run: the read, the entities read, the [inspect] action — and asked only once
    again = FakeAdapter("另一段")
    assert I.describe(root, "I806", adapter=again)["desc"] == out["desc"] and again.calls == []
    reg = load_registry(root)
    assert reg.entries["I806"].props["summary"] == out["desc"] and reg.entries["I806"].props.get("fixed") is True
    assert player_action.perform(root, "inspect", "I806", turn=2)["text"].startswith(out["desc"])
    side = [json.loads(x) for x in (root / ".neonrp" / "orchestration" / "main.side.jsonl").read_text(encoding="utf-8").splitlines()]
    assert side[-1]["kind"] == "inspect" and side[-1]["desc"] == out["desc"]
    if tpl_before:
        assert (PRODUCT_TEMPLATES / "pct-house.template" / "world" / "game" / "meta" / "entries.json").read_bytes() == tpl_before


def test_a_model_error_answers_with_the_name_and_tries_again(tmp_path):
    root = _run(tmp_path)
    _strip_desc(root, "I806")
    bad = I.describe(root, "I806", adapter=FakeAdapter(error="quota"))
    assert bad["needs_desc"] and bad["desc"] == "" and bad["error"] == "quota"
    assert I.describe(root, "I806", adapter=FakeAdapter(""))["needs_desc"], "an empty answer is not kept either"
    ok = I.describe(root, "I806", adapter=FakeAdapter("落了灰的画框。"))
    assert ok["desc"] == "落了灰的画框。"


def test_four_languages(tmp_path):
    want = {"en": ("You write a short description", "butler of Greyoak", "On you since the start"),
            "ja": ("あなたは TRPG の世界", "老執事", "最初から持っていた"),
            "ko": ("당신은 TRPG 세계", "집사", "처음부터 지니고 있던 것"),
            "zh": ("你在为一个跑团世界", "老管家", "开局时就带在身上")}
    for lang, (sys_head, intro, start) in want.items():
        root = _run(tmp_path, lang)
        p = I.detail(root, "si-butler0001")
        assert p["lang"] == lang and intro in p["intro"] and p["appearance"], lang
        assert I.detail(root, "I804")["source"] == start, lang
        _strip_desc(root, "I806")
        fake = FakeAdapter(f"{lang} desc")
        assert I.describe(root, "I806", adapter=fake)["desc"] == f"{lang} desc"
        assert fake.calls[0][0].startswith(sys_head), lang
        assert I.detail(root, "I806")["name"] in fake.calls[0][1]


def _strip_person(root: Path, folder: str) -> None:
    """Someone the world wrote nothing about that the player may see (the run's copy only)."""
    d = root / "souls" / folder
    sj = json.loads((d / "soul.json").read_text(encoding="utf-8"))
    (d / "soul.json").write_text(json.dumps({k: v for k, v in sj.items() if not k.startswith(("intro", "appearance"))}, ensure_ascii=False), encoding="utf-8")
    pf = d / "character" / "profile.json"
    pj = json.loads(pf.read_text(encoding="utf-8"))
    pf.write_text(json.dumps({k: v for k, v in pj.items() if not k.startswith(("summary", "appearance"))}, ensure_ascii=False), encoding="utf-8")


def _strip_place(root: Path, rel: str) -> None:
    p = root / "game" / "locations" / rel / "location.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps({k: v for k, v in d.items() if k.split("_")[0] not in I.DESC_KEYS}, ensure_ascii=False), encoding="utf-8")


def test_a_person_with_nothing_written_gets_an_outward_impression_once(tmp_path):
    root = _run(tmp_path)
    _strip_person(root, "butler-si-butler0001")
    d = I.detail(root, "si-butler0001")
    assert d["needs_desc"] and not d["intro"] and not d["appearance"]
    fake = FakeAdapter("个子很高,白手套一尘不染,说话前先欠一欠身。")
    out = I.describe(root, "si-butler0001", adapter=fake)
    assert out["generated"] and out["appearance"] == out["desc"] == "个子很高,白手套一尘不染,说话前先欠一欠身。"
    system, user = fake.calls[0]
    assert system.startswith("你在为一个跑团世界里的一个人写") and "奥斯温" in user and "门厅" in user and "灰橡宅" in user
    reg = load_registry(root)
    persona = str(reg.entries["si-butler0001"].props.get("persona") or "")
    for line in [x for x in persona.splitlines() if len(x) > 10][:6]:
        assert line not in user, "no persona in the prompt"
    rel = json.loads((root / "souls" / "butler-si-butler0001" / "persona" / "relationships.json").read_text(encoding="utf-8"))
    for r in (rel.get("relationships") or {}).values():
        assert not (isinstance(r, dict) and r.get("truth")) or r["truth"] not in user, "no truths"
    assert reg.entries["si-butler0001"].props["impression"] == out["desc"]
    again = FakeAdapter("另一段")
    assert I.describe(root, "si-butler0001", adapter=again)["appearance"] == out["desc"] and again.calls == []
    assert not I.detail(root, "si-butler0001")["needs_desc"]
    assert out["desc"] in player_action.perform(root, "inspect", "si-butler0001", turn=1)["text"]


def test_a_place_with_nothing_written_gets_a_description_once(tmp_path):
    root = _run(tmp_path)
    _strip_place(root, "T001/hall")
    d = I.detail(root, "T001/hall")
    assert d["kind"] == "place" and d["needs_desc"] and d["desc"] == ""
    fake = FakeAdapter("窄长的门厅,一盏油灯照不到墙角。")
    out = I.describe(root, "T001/hall", adapter=fake)
    assert out["generated"] and out["desc"] == "窄长的门厅,一盏油灯照不到墙角。"
    assert fake.calls[0][0].startswith("你在为一个跑团世界里的一个地方写") and "门厅" in fake.calls[0][1]
    assert load_registry(root).entries["T001/hall"].props["summary"] == out["desc"]
    again = FakeAdapter("x")
    assert I.describe(root, "T001/hall", adapter=again)["desc"] == out["desc"] and again.calls == []
    # a model error: the name only, tried again next time
    _strip_place(root, "T001/study")
    with patch.object(I, "_adapter", lambda root: FakeAdapter(error="down")):
        assert player_action.perform(root, "inspect", "T001/study", turn=1)["text"] in ("书房", "这里没有「T001/study」。", "书房不在这里。")
    assert I.detail(root, "T001/study").get("needs_desc", True)


def test_the_inspect_action_writes_what_is_missing(tmp_path):
    root = _run(tmp_path)
    _strip_desc(root, "I806")
    with patch.object(I, "_adapter", lambda root: FakeAdapter("画框积了一层灰。")):
        assert player_action.perform(root, "inspect", "I806", turn=1)["text"].startswith("画框积了一层灰。")
    assert load_registry(root).entries["I806"].props["summary"] == "画框积了一层灰。"


def test_people_and_places_in_four_languages(tmp_path):
    heads = {"en": ("You write the player's first impression", "You write a short description of one place"),
             "ja": ("あなたは TRPG の世界にいるひとりの人物", "あなたは TRPG の世界にあるひとつの場所"),
             "ko": ("당신은 TRPG 세계에 있는 한 인물", "당신은 TRPG 세계에 있는 한 장소"),
             "zh": ("你在为一个跑团世界里的一个人写", "你在为一个跑团世界里的一个地方写")}
    for lang, (ph, lh) in heads.items():
        root = _run(tmp_path, lang)
        _strip_person(root, "butler-si-butler0001")
        _strip_place(root, "T001/hall")
        fp, fl = FakeAdapter(f"{lang} look"), FakeAdapter(f"{lang} room")
        assert I.describe(root, "si-butler0001", adapter=fp)["appearance"] == f"{lang} look"
        assert I.describe(root, "T001/hall", adapter=fl)["desc"] == f"{lang} room"
        assert fp.calls[0][0].startswith(ph) and fl.calls[0][0].startswith(lh), lang
        assert I.detail(root, "si-butler0001")["name"] in fp.calls[0][1]


def test_inspecting_a_person_says_who_they_are(tmp_path):
    root = _run(tmp_path)
    text = player_action.perform(root, "inspect", "si-butler0001", turn=1)["text"]
    assert "老管家" in text and "燕尾服" in text and text != "奥斯温"


def test_where_a_held_thing_came_from(tmp_path):
    root = _run(tmp_path)
    trace = root / ".neonrp" / "orchestration" / "main.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"turn_seq": 1, "apply": {"gained": [{"id": "I804", "who": "player", "from": "si-chara0001", "how": "given"}]}}]
    trace.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert I.detail(root, "I804")["source"] == "温妮交给你的"
    rows.append({"turn_seq": 2, "apply": {"gained": [{"id": "I804", "who": "player", "from": "T001/hall", "how": "picked"}]}})
    trace.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert I.detail(root, "I804")["source"] == "在门厅拿到的", "the latest way it came"


def test_http_route(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    fake = FakeAdapter("落了灰的画框。")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
        patch.object(I, "_adapter", lambda root: fake),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        try:
            call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            root = server.runtime.root
            p = call("/api/v1/play/engine/inspect?target=si-butler0001")
            assert p["kind"] == "person" and "老管家" in p["intro"]
            _strip_desc(root, "I806")
            assert call("/api/v1/play/engine/inspect?target=I806")["needs_desc"]
            assert server.runtime._busy.acquire(blocking=False)
            try:  # a turn is running: the read, nothing written
                busy = call("/api/v1/play/engine/inspect", {"target": "I806"})
                assert busy["busy"] and busy["needs_desc"] and fake.calls == []
            finally:
                server.runtime._busy.release()
            out = call("/api/v1/play/engine/inspect", {"target": "I806"})
            assert out["desc"] == "落了灰的画框。" and out["generated"] and len(fake.calls) == 1
            ents = call("/api/v1/play/engine/entities?cls=item")["entities"]
            assert next(e for e in ents if e["id"] == "I806")["props"]["summary"] == "落了灰的画框。"
            assert not call("/api/v1/play/engine/inspect?target=nothing-here")["found"]
        finally:
            server.shutdown()
