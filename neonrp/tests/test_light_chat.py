"""对话拍(T1)— docs/HARNESS-TEAM-DESIGN.md 的 lane=算力契约回归。

契约:同场景门 / 一次纯 LLM 调用(无工具)/ 小 context(线程尾部截断)/
线程落盘 + pending 结算桥(deliver-once 给世界拍 preflight)。
"""

import json
import shutil
from pathlib import Path

from neonrp.core import light_chat

_TPL = Path("src/neonrp/templates/stoneford-elena")
_ELENA = "si-elena0001"
_ROWAN = "si-rowan0001"


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeRes:
    def __init__(self, content: str) -> None:
        self.message = _FakeMsg(content)


class _FakeAdapter:
    def __init__(self, reply: str = "……哼,你倒是自来熟。") -> None:
        self.reply = reply
        self.calls: list[list] = []

    def chat(self, messages, tools=None):  # noqa: ANN001
        assert tools is None  # 契约:直聊无工具
        self.calls.append(messages)
        return _FakeRes(self.reply)


def test_co_location_gate(tmp_path: Path) -> None:
    # elena 与玩家同在 north-gate → 可聊(非远程);rowan 在 T004 且世界
    # 无远程通讯 → 不可达;未知 iid → None。
    root = _install(tmp_path)
    resolved = light_chat.resolve_reachable_soul(root, _ELENA)
    assert resolved is not None and resolved[2] is False
    assert light_chat.resolve_reachable_soul(root, _ROWAN) is None
    assert light_chat.resolve_reachable_soul(root, "si-nobody") is None


def test_reply_lands_thread_and_pending(tmp_path: Path, monkeypatch) -> None:
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = light_chat.light_chat_reply(root, _ELENA, "早。昨晚睡得好吗?")

    assert out["ok"] is True and out["reply"] == fake.reply
    assert len(fake.calls) == 1  # 契约:一次调用,封顶
    # 线程落盘:player + soul 两行
    thread = light_chat.read_thread(root, _ELENA)
    assert [r["role"] for r in thread] == ["player", "soul"]
    # 结算桥:pending 有两行,drain 一次取尽(deliver-once)
    digest = light_chat.drain_chat_digest(root)
    assert len(digest) == 2 and "艾琳娜" in digest[0]
    assert light_chat.drain_chat_digest(root) == []


def test_offsite_soul_refused(tmp_path: Path, monkeypatch) -> None:
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    out = light_chat.light_chat_reply(root, _ROWAN, "喂,你在吗?")
    assert out["ok"] is False and out["error"] == "not-co-located"
    assert fake.calls == []  # 门在 LLM 之前:一次调用都不发生


def test_context_is_small_and_tail_capped(tmp_path: Path, monkeypatch) -> None:
    # 小 context 契约:长线程只带尾部 THREAD_TAIL 条进 prompt。
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    for i in range(20):
        light_chat._append_thread(root, _ELENA, "player", f"第{i}句")
    light_chat.light_chat_reply(root, _ELENA, "最新一句")
    msgs = fake.calls[0]
    # system + tail(≤THREAD_TAIL) + 新输入
    assert len(msgs) <= 1 + light_chat.THREAD_TAIL + 1
    assert msgs[0].role == "system" and "艾琳娜" in msgs[0].content
    assert msgs[-1].content == "最新一句"


def test_empty_input_noop(tmp_path: Path) -> None:
    root = _install(tmp_path)
    assert light_chat.light_chat_reply(root, _ELENA, "  ")["ok"] is False


class _RoomAdapter:
    """按 soul 依次回:第一个接话,第二个沉默(自选不接话协议)。"""

    def __init__(self) -> None:
        self.n = 0
        self.seen_prompts: list[str] = []

    def chat(self, messages, tools=None):  # noqa: ANN001
        assert tools is None
        self.n += 1
        self.seen_prompts.append(messages[-1].content)
        return _FakeRes("……嗯,我在。" if self.n == 1 else "[沉默]")


def test_room_chat_self_selection_and_interplay(tmp_path: Path, monkeypatch) -> None:
    # stoneford-elena:与玩家同在 north-gate 的只有 elena;把 rowan 也搬来
    # 凑成两人房间,验证:顺序调用 / 第二个看得到第一个的回应 / 沉默=在听。
    root = _install(tmp_path)
    rowan_state = root / "souls" / "rowan-si-rowan0001" / "run_state.json"
    st = json.loads(rowan_state.read_text(encoding="utf-8"))
    st["location"] = "north-gate"
    rowan_state.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")

    fake = _RoomAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = light_chat.room_chat_reply(root, "大家早,昨晚都睡得好吗?")

    assert out["ok"] is True and fake.n == 2  # 每个在场 soul 恰一次调用
    r_by_name = {r["name"]: r["reply"] for r in out["replies"]}
    assert r_by_name["艾琳娜"] == "……嗯,我在。"
    assert list(r_by_name.values()).count(None) == 1  # rowan 沉默=在听
    # 互相接话:第二个 soul 的 prompt 里能看到第一个的回应
    assert "……嗯,我在。" in fake.seen_prompts[1]
    # 房间线程落盘:玩家 + 接话者(沉默者不落)
    thread = light_chat.read_room_thread(root)
    assert [r["who"] for r in thread] == ["玩家", "艾琳娜"]
    # 结算桥:玩家一行 + 接话一行
    digest = light_chat.drain_chat_digest(root)
    assert len(digest) == 2


def test_room_chat_no_souls_here(tmp_path: Path, monkeypatch) -> None:
    # 把 elena 也挪走 → 房间没人 → 拒(rowan 本就在 T004)。
    root = _install(tmp_path)
    es = root / "souls" / "elena-si-elena0001" / "run_state.json"
    st = json.loads(es.read_text(encoding="utf-8"))
    st["location"] = "T004/guild"
    es.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    out = light_chat.room_chat_reply(root, "有人吗?")
    assert out["ok"] is False and out["error"] == "no-souls-here"


def _write_recent_event(root: Path, soul: str, event: str) -> None:
    p = root / "souls" / soul / "short-term-memo" / "recent_events.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["events"].append({"turn": 1, "event": event, "my_reaction": "记下了"})
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _events(root: Path, soul: str) -> list:
    p = root / "souls" / soul / "short-term-memo" / "recent_events.json"
    return json.loads(p.read_text(encoding="utf-8"))["events"]


def test_soul_memory_enters_chat_context(tmp_path: Path, monkeypatch) -> None:
    # T1R(M24 §4):答话以 soul 本体记忆为底——memo 里的经历必须进 system。
    root = _install(tmp_path)
    _write_recent_event(root, "elena-si-elena0001", "在北门救治了摔断腿的老泰德")
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    light_chat.light_chat_reply(root, _ELENA, "今天累不累?")
    system = fake.calls[0][0].content
    assert "老泰德" in system  # 记忆装配进 context
    assert "当下心境" in system  # current_context notes 也在


def test_chat_commits_soul_memory(tmp_path: Path, monkeypatch) -> None:
    # 「不 commit 是不行的」:每次交换落 recent_events(本体记忆)。
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    light_chat.light_chat_reply(root, _ELENA, "早。")
    evs = _events(root, "elena-si-elena0001")
    assert len(evs) == 1 and str(evs[0]["turn"]).startswith("幕间@")
    assert "早。" in evs[0]["event"] and fake.reply[:20] in evs[0]["my_reaction"]


def test_room_silent_soul_remembers_hearing(tmp_path: Path, monkeypatch) -> None:
    # 在听也是经历:沉默的 soul 也 commit「听到了,没接话」。
    root = _install(tmp_path)
    rowan_state = root / "souls" / "rowan-si-rowan0001" / "run_state.json"
    st = json.loads(rowan_state.read_text(encoding="utf-8"))
    st["location"] = "north-gate"
    rowan_state.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    fake = _RoomAdapter()  # 第一个接话,第二个沉默
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    light_chat.room_chat_reply(root, "大家听我说——")
    elena_evs = _events(root, "elena-si-elena0001")
    rowan_evs = _events(root, "rowan-si-rowan0001")
    assert any("我接话" in e["my_reaction"] for e in elena_evs)
    assert any("没接话" in e["my_reaction"] for e in rowan_evs)


class _RoomV2Adapter:
    """依次吐预设回复;耗尽后一律 [沉默]。记录完整 messages 供 stance 断言。"""

    def __init__(self, replies) -> None:  # noqa: ANN001
        self.replies = list(replies)
        self.calls: list[list] = []

    def chat(self, messages, tools=None):  # noqa: ANN001
        assert tools is None
        self.calls.append(messages)
        return _FakeRes(self.replies.pop(0) if self.replies else "[沉默]")


def _both_in_room(root: Path) -> None:
    rowan_state = root / "souls" / "rowan-si-rowan0001" / "run_state.json"
    st = json.loads(rowan_state.read_text(encoding="utf-8"))
    st["location"] = "north-gate"
    rowan_state.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def test_room_v2_primary_by_mention_only_primary_called(tmp_path: Path, monkeypatch) -> None:
    # M24 §6 v2:点名艾琳娜 → 她是主对话人(必回 stance);罗文未被提及
    # → 零调用,但听到了(广播 memo)。
    root = _install(tmp_path)
    _both_in_room(root)
    fake = _RoomV2Adapter(["我看行。"])
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = light_chat.room_chat_reply(root, "艾琳娜,你怎么看?")

    assert out["primary"] == "si-elena0001"
    assert len(fake.calls) == 1  # 只有主对话人起了调用
    assert "主要是对你说的" in fake.calls[0][0].content  # primary stance
    rowan_evs = _events(root, "rowan-si-rowan0001")
    assert any("在场听到" in e["my_reaction"] for e in rowan_evs)  # 听是零 LLM 的


def test_room_v2_jump_in_when_reply_mentions(tmp_path: Path, monkeypatch) -> None:
    # 主对话人的回应点到罗文 → 触发 jump-in(其 stance=被提及可插话)。
    root = _install(tmp_path)
    _both_in_room(root)
    fake = _RoomV2Adapter(["这得问罗文——罗文,你说呢?", "[沉默]"])
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = light_chat.room_chat_reply(root, "艾琳娜,咱们下一步去哪?")

    assert len(fake.calls) == 2  # primary + jump-in
    assert "提到了你" in fake.calls[1][0].content  # jumpin stance
    r_by_iid = {r["iid"]: r["reply"] for r in out["replies"]}
    assert r_by_iid["si-rowan0001"] is None  # 插话机会给了,他选择沉默


def test_room_v2_last_speaker_becomes_primary(tmp_path: Path, monkeypatch) -> None:
    # 无点名时,上一个说话的 soul 是主对话人 → 只调它,不再全员轮询。
    root = _install(tmp_path)
    _both_in_room(root)
    light_chat._append_room(root, "艾琳娜", "嗯,先歇会儿。")
    fake = _RoomV2Adapter(["……你还真是闲不住。"])
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = light_chat.room_chat_reply(root, "然后呢?")

    assert out["primary"] == "si-elena0001" and len(fake.calls) == 1


def test_detect_world_intent_move_to_known_place(tmp_path: Path) -> None:
    # 升级签:聊天里「情不自禁」说移动 → 探测到已知地名+移动动词 → move 签。
    root = _install(tmp_path)
    out = light_chat.detect_world_intent(root, "走吧,我们去河灯旅店问问米拉")
    assert out is not None and out["kind"] == "move" and out["target"] == "inn"
    assert "河灯旅店" in out["label"]


def test_detect_world_intent_pure_chat_is_none(tmp_path: Path) -> None:
    root = _install(tmp_path)
    assert light_chat.detect_world_intent(root, "昨晚睡得好吗?") is None
    # 提到地名但没有移动语气 → 不出签(感慨不是行动)。
    assert light_chat.detect_world_intent(root, "河灯旅店的粥真不错") is None


def test_chat_reply_carries_world_intent(tmp_path: Path, monkeypatch) -> None:
    root = _install(tmp_path)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    out = light_chat.light_chat_reply(root, _ELENA, "收拾一下,我们去主街吧")
    assert out["ok"] is True
    assert out["world_intent"] and out["world_intent"]["target"] == "main_street"


def _enable_phone(root: Path) -> None:
    p = root / "game" / "meta" / "comms.json"
    p.write_text(json.dumps({"remote": True, "medium": "手机"}, ensure_ascii=False), encoding="utf-8")


def test_remote_comms_reaches_offsite_soul(tmp_path: Path, monkeypatch) -> None:
    # M24 §6.6(实测反馈:现代世界在家给学校的 soul 发消息收不到):
    # 世界声明远程通讯 ⇒ 异地 soul 经媒介可达;她的 canon 是她自己的场景。
    root = _install(tmp_path)
    _enable_phone(root)
    fake = _FakeAdapter("(瞄了一眼手机)……嗯,下课再说。")
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)

    out = light_chat.light_chat_reply(root, _ROWAN, "在忙吗?晚上一起吃饭?")  # rowan 在 T004(异地)

    assert out["ok"] is True and out["remote"] is True and out["medium"] == "手机"
    system = fake.calls[0][0].content
    assert "手机" in system and "不在你身边" in system  # 以收讯息方式回应
    assert "石津镇·北门" not in system  # 她的 canon 不是玩家的场景
    # 记忆与结算桥都带媒介
    evs = _events(root, "rowan-si-rowan0001")
    assert any("经手机" in e["event"] for e in evs)
    digest = light_chat.drain_chat_digest(root)
    assert any("(经手机)" in ln for ln in digest)


def test_fantasy_world_gate_stays_strict(tmp_path: Path) -> None:
    # 无 comms.json(奇幻默认)⇒ 异地仍不可达——远程通讯不是白送的能力。
    root = _install(tmp_path)
    assert light_chat.resolve_reachable_soul(root, _ROWAN) is None
    out = light_chat.light_chat_reply(root, _ROWAN, "喂?")
    assert out["ok"] is False and out["error"] == "not-co-located"


def test_co_located_chat_unchanged_with_phone(tmp_path: Path, monkeypatch) -> None:
    # 有手机的世界里,同场直聊仍是面对面(remote=False,不套讯息框)。
    root = _install(tmp_path)
    _enable_phone(root)
    fake = _FakeAdapter()
    monkeypatch.setattr(light_chat, "_adapter", lambda _root: fake)
    out = light_chat.light_chat_reply(root, _ELENA, "早。")
    assert out["ok"] is True and out["remote"] is False
    assert "面对面" in fake.calls[0][0].content
