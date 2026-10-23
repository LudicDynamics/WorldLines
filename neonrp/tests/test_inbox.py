"""文件收件箱(v0.4.0 T2 通信地基)— HARNESS-TEAM-DESIGN §5 契约回归。

契约:定向投递 / peek 不消耗 / drain=deliver-once(标已读但留档作 trace)/
kind 过滤 / request_id 关联(T3 重拍的地基)/ 容量上限滚动。
"""

from pathlib import Path

from neonrp.core import inbox
from neonrp.core.inbox import InboxMessage


def test_send_peek_drain_roundtrip(tmp_path: Path) -> None:
    root = tmp_path
    mid = inbox.send(root, InboxMessage.new("chat", "player", "si-elena0001", {"text": "早"}))
    assert mid

    # peek 不消耗
    assert len(inbox.peek(root, "si-elena0001")) == 1
    assert len(inbox.peek(root, "si-elena0001")) == 1

    # drain = deliver-once
    got = inbox.drain(root, "si-elena0001")
    assert len(got) == 1 and got[0].payload["text"] == "早" and got[0].sender == "player"
    assert inbox.drain(root, "si-elena0001") == []

    # 已读消息仍留在文件里(trace 不丢)
    kept = inbox.peek(root, "si-elena0001", unread_only=False)
    assert len(kept) == 1


def test_kind_filter(tmp_path: Path) -> None:
    root = tmp_path
    inbox.send(root, InboxMessage.new("perception", "world-agent", "si-a", {"scene": "北门"}))
    inbox.send(root, InboxMessage.new("chat", "player", "si-a", {"text": "喂"}))

    percept = inbox.drain(root, "si-a", kind="perception")
    assert [m.kind for m in percept] == ["perception"]
    # chat 还没被消耗
    rest = inbox.drain(root, "si-a")
    assert [m.kind for m in rest] == ["chat"]


def test_send_many_room_fanout(tmp_path: Path) -> None:
    # 群聊:同一句话投给房间内每个 soul,各自收件箱各一条。
    root = tmp_path
    line = {"text": "大家早", "room": "riverlamp-inn"}
    inbox.send_many(
        root,
        [InboxMessage.new("chat_room", "player", iid, line) for iid in ("si-a", "si-b")],
    )
    assert inbox.peek(root, "si-a")[0].payload["room"] == "riverlamp-inn"
    assert inbox.peek(root, "si-b")[0].payload["text"] == "大家早"


def test_request_id_correlation(tmp_path: Path) -> None:
    # T3 重拍地基:world 发 retake_request,soul 回 soul_response 回显 request_id。
    root = tmp_path
    req = InboxMessage.new(
        "retake_request", "world-agent", "si-a", {"request_id": "rq-1", "prompt": "接住玩家的请求"}
    )
    inbox.send(root, req)
    got = inbox.drain(root, "si-a", kind="retake_request")
    rid = got[0].payload["request_id"]

    inbox.send(
        root,
        InboxMessage.new("soul_response", "si-a", "world-agent", {"request_id": rid, "speech": "…好吧。"}),
    )
    resp = inbox.reply_of(root, "world-agent", "rq-1")
    assert resp is not None and resp.payload["speech"] == "…好吧。"
    # 未知 request_id → None
    assert inbox.reply_of(root, "world-agent", "rq-404") is None


def test_cap_rolls_old_messages(tmp_path: Path) -> None:
    root = tmp_path
    for i in range(inbox.INBOX_CAP + 20):
        inbox.send(root, InboxMessage.new("chat", "p", "si-a", {"i": i}))
    all_rows = inbox.peek(root, "si-a", unread_only=False)
    assert len(all_rows) == inbox.INBOX_CAP
    # 留的是最新的
    assert all_rows[-1].payload["i"] == inbox.INBOX_CAP + 19
