"""对话拍(light dialogue lane)— docs/HARNESS-TEAM-DESIGN.md T1.

lane = 算力契约:玩家与**同场景**单个 soul 的直聊,结构上封顶为
**一次纯 LLM 调用**——无工具、无 sub-agent、小 context(persona 摘要 +
canon 一行 + 线程尾部)。时钟不走、回合不加、不结算任何世界状态。

- 线程落盘:.neonrp/chats/<iid>.jsonl(UI 的 IM 历史;也是该 soul 直聊时
  自己的上下文——常驻记忆的文件形态)。
- 结算桥:每次交换同时 append 进 .neonrp/chats/pending.json;下一个世界拍
  preflight drain(deliver-once),world-agent 由此知道幕间聊了什么,
  叙事保持连续。消息不背状态:位置/事实仍只走结算链。
- 同场景门:soul 与玩家不同地点 ⇒ 拒绝(UI 本就不该给入口;引擎兜底)。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

logger = logging.getLogger("neonrp.light_chat")

# 线程尾部带多少条历史进 prompt(小 context 是契约的一部分)。
THREAD_TAIL = 12


def _L(root: Path | None) -> dict[str, Any]:
    """This module's prompt strings (src/neonrp/prompts/light_chat.<lang>.json) in the run's language."""
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    return prompts.strings("light_chat", prompt_lang(root) if root is not None else "zh")


def _f(s: str, /, **kw: Any) -> str:
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s
# persona / soul.md 摘要上限(字符)。
PERSONA_CAP = 1800


def _chats_dir(root: Path) -> Path:
    return root / ".neonrp" / "chats"


def thread_path(root: Path, iid: str) -> Path:
    safe = "".join(c for c in iid if c.isalnum() or c in "-_") or "soul"
    return _chats_dir(root) / f"{safe}.jsonl"


def _pending_path(root: Path) -> Path:
    return _chats_dir(root) / "pending.json"


def read_thread(root: Path, iid: str, limit: int = 60) -> list[dict[str, Any]]:
    """Read the chat thread (oldest→newest), best-effort."""
    path = thread_path(root, iid)
    rows: list[dict[str, Any]] = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        pass
    return rows[-limit:]


def _append_thread(root: Path, iid: str, role: str, text: str) -> None:
    path = thread_path(root, iid)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"role": role, "text": text, "ts": time.strftime("%H:%M")}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_pending(root: Path, line: str) -> None:
    from neonrp.core.notes import post_note

    post_note(root, "chat_digest", line)


def drain_chat_digest(root: Path) -> list[str]:
    """Read-and-clear the未固化的幕间对话行(deliver-once,给世界拍 preflight)."""
    from neonrp.core.notes import drain_notes

    return drain_notes(root, "chat_digest", legacy_path=_pending_path(root))


# ── 同场景门 ────────────────────────────────────────────────────────────────


def _player_node(root: Path) -> str | None:
    from neonrp.core.place_nav import qualify_location

    try:
        payload = json.loads(
            (root / get_data_dir_name(root) / "meta" / "run_state.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        return None
    loc = payload.get("location") if isinstance(payload, dict) else None
    if not isinstance(loc, dict):
        return None
    # `node` is the spot inside the town; saves written before it existed
    # carry only subnode_id (TODO #5: the seeded soul must land on the same
    # address, or the roster calls it "away" while standing next to you).
    raw = loc.get("node") or loc.get("subnode_id") or loc.get("node_id")
    town = loc.get("node_id")
    return (
        qualify_location(root, str(raw), current_town=str(town) if town else None)
        if raw
        else None
    )


def _soul_node(root: Path, soul_dir: Path) -> str | None:
    from neonrp.core.place_nav import qualify_location

    try:
        state = json.loads((soul_dir / "run_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    loc = state.get("location") if isinstance(state, dict) else None
    node = str(loc) if isinstance(loc, str) and loc else None
    return qualify_location(root, node) if node else None


def _medium_default(root: Path) -> str:
    """The world's remote medium when comms.json names none, in the run's language (10-06)."""
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    return str(prompts.strings("light_chat", prompt_lang(root)).get("medium_default") or "message")


def remote_comms(root: Path) -> dict[str, Any] | None:
    """世界的远程通讯能力(M24 §6.6)。现代世界声明 game/meta/comms.json
    {"remote": true, "medium": "手机"} ⇒ 异地 soul 经该媒介可达;
    奇幻世界无此文件 ⇒ 同场门保持严格(远程通讯不是默认能力)。"""
    cfg = _read_json_file(root / get_data_dir_name(root) / "meta" / "comms.json")
    if cfg.get("remote"):
        return {"medium": str(cfg.get("medium") or _medium_default(root))}
    return None


def resolve_reachable_soul(root: Path, iid: str) -> tuple[Path, str, bool] | None:
    """Return (soul_dir, display_name, remote) iff the soul is REACHABLE:
    与玩家同节点(remote=False),或世界有远程通讯且 soul 异地(remote=True)。
    None ⇒ 不可达(她不在身边,且这个世界没有联系她的办法)。
    无位置视作同场,镜像 scene_understanding。"""
    from neonrp.core.playthrough import read_playthrough

    pt = read_playthrough(root)
    if pt is None:
        return None
    ref = next((s for s in pt.souls if s.instance_id == iid), None)
    if ref is None:
        return None
    soul_dir = root / "souls" / f"{ref.sid}-{ref.instance_id}"
    if not soul_dir.is_dir():
        return None
    s_node = _soul_node(root, soul_dir)
    p_node = _player_node(root)
    co_located = not (s_node is not None and p_node is not None and s_node != p_node)
    if not co_located and remote_comms(root) is None:
        return None  # 异地且世界无远程通讯 ⇒ 不可达
    name = _display_name(soul_dir, ref.sid)
    return soul_dir, name, not co_located


def _display_name(soul_dir: Path, fallback: str) -> str:
    try:
        data = json.loads((soul_dir / "soul.json").read_text(encoding="utf-8"))
        # name_local 优先(游戏场景不钉英文名):艾琳娜,不是 Elena Vale。
        for key in ("name_local", "name"):
            n = data.get(key)
            if isinstance(n, str) and n.strip():
                return n.strip()
    except (OSError, ValueError):
        pass
    try:
        prof = json.loads(
            (soul_dir / "character" / "profile.json").read_text(encoding="utf-8")
        )
        n = prof.get("name")
        if isinstance(n, str) and n.strip():
            return n.strip()
    except (OSError, ValueError):
        pass
    return fallback


# ── prompt 装配 + 一次调用 ──────────────────────────────────────────────────


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def _soul_memory_digest(soul_dir: Path) -> str:
    """soul 本体记忆摘要(T1R,M24 §4 hybrid 轻拍):与全思考同源的
    short/long-term memo,截断紧——答话出自它的记忆与心境,不是外挂 chat。"""
    L = _L(soul_dir.parent.parent)
    parts: list[str] = []
    cc = _read_json_file(soul_dir / "short-term-memo" / "current_context.json")
    notes = cc.get("notes")
    if isinstance(notes, list) and notes:
        parts.append(_f(L["mem_mood"], items=L["mem_sep"].join(str(n) for n in notes[-6:])))
    ev = _read_json_file(soul_dir / "short-term-memo" / "recent_events.json")
    events = ev.get("events")
    if isinstance(events, list) and events:
        lines = []
        for e in events[-8:]:
            if isinstance(e, dict):
                lines.append(
                    f"- {e.get('event', '')}"
                    + (_f(L["mem_me"], reaction=e.get("my_reaction")) if e.get("my_reaction") else "")
                )
        if lines:
            parts.append(_f(L["mem_recent"], lines="\n".join(lines)))
    lf = _read_json_file(soul_dir / "long-term-memo" / "learned_facts.json")
    facts = lf.get("facts")
    if isinstance(facts, list) and facts:
        parts.append(_f(L["mem_facts"], items=L["mem_sep"].join(str(x) for x in facts[-5:])))
    try:
        imp = (soul_dir / "long-term-memo" / "important_events.md").read_text(
            encoding="utf-8"
        ).strip()
        if imp:
            parts.append(_f(L["mem_important"], text=imp[:400]))
    except OSError:
        pass
    return "\n".join(parts)[:1400] or L["mem_none"]


def _current_turn(root: Path) -> int:
    payload = _read_json_file(root / get_data_dir_name(root) / "meta" / "run_state.json")
    try:
        return int(payload.get("turn_count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def commit_chat_memory(root: Path, soul_dir: Path, event: str, my_reaction: str, label: str | None = None) -> bool:
    """幕间对话的 soul 记忆 commit(「不 commit 是不行的」):
    追加进 short-term-memo/recent_events.json ——与全思考同一份记忆,
    下个世界拍它靠**本体记忆**记得这场闲聊,不靠 preflight 桥。"""
    path = soul_dir / "short-term-memo" / "recent_events.json"
    try:
        payload = _read_json_file(path)
        events = payload.get("events")
        if not isinstance(events, list):
            events = []
        events.append(
            {
                "turn": label or f"幕间@{_current_turn(root)}",
                "event": event[:200],
                "my_reaction": my_reaction[:200],
            }
        )
        payload["events"] = events[-40:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except OSError:
        logger.warning("chat memory commit failed: %s", path, exc_info=True)
        return False


def _beat_system(root: Path, iid: str, name: str, soul_dir: Path) -> str:
    """Her own beat: who she is, from her soul folder, once — persona, rules, goals, the people she knows, memory."""
    me = None
    try:
        from neonrp.core.registry import load_registry

        me = load_registry(root).entries.get(iid)
    except Exception:  # noqa: BLE001
        me = None
    props = me.props if me is not None else {}
    L = _L(root)
    parts = [_f(L["beat_intro"], name=name),
             L["beat_who"] + (str(props.get("persona") or "") or _persona_digest(soul_dir))[:PERSONA_CAP]]
    if props.get("rules"):
        parts.append(L["beat_rules"] + str(props["rules"])[:600])
    if props.get("goals"):
        parts.append(L["beat_goals"] + "\n".join(f"- {g}" for g in props["goals"]))
    rel = props.get("relationships")
    if isinstance(rel, dict) and rel:
        parts.append(L["beat_people"] + "\n".join(_f(L["beat_person"], who=k, what=(v or {}).get('disposition') or (v or {}).get('truth') or '') for k, v in rel.items()))
    parts.append(L["beat_memory"] + _soul_memory_digest(soul_dir))
    return "\n\n".join(parts)


def _persona_digest(soul_dir: Path) -> str:
    """persona 摘要:soul.md 开头 + core_traits(小 context 契约)."""
    parts: list[str] = []
    try:
        md = (soul_dir / "soul.md").read_text(encoding="utf-8").strip()
        if md:
            parts.append(md[:PERSONA_CAP])
    except OSError:
        pass
    try:
        traits = json.loads(
            (soul_dir / "persona" / "core_traits.json").read_text(encoding="utf-8")
        )
        t = traits.get("traits")
        if t:
            parts.append(f"core_traits: {json.dumps(t, ensure_ascii=False)[:400]}")
    except (OSError, ValueError):
        pass
    return "\n\n".join(parts) or _L(soul_dir.parent.parent)["persona_missing"]


def _canon_line(root: Path) -> str:
    try:
        payload = json.loads(
            (root / get_data_dir_name(root) / "meta" / "run_state.json").read_text(
                encoding="utf-8"
            )
        )
        loc = payload.get("location") or {}
        t = payload.get("time") or {}
        L = _L(root)
        return (
            f"{loc.get('display') or loc.get('node') or L['here']}"
            + _f(L["canon_time"], day=t.get('day', '?'), clock=t.get('clock', '?'))
        )
    except (OSError, ValueError):
        return _L(root)["here"]


def _soul_place_label(root: Path, soul_dir: Path) -> str:
    """soul 自己所在地的人话标签(远程直聊时她的 canon 是她的场景)。"""
    from neonrp.core.place_nav import split_location, town_node_view

    node = _soul_node(root, soul_dir)
    if not node:
        return _L(root)["your_place"]
    town, bare = split_location(node)
    view = town_node_view(root, bare or node, prefer_town=town)
    return (view or {}).get("name") or bare or node


def build_chat_messages(
    root: Path,
    iid: str,
    soul_dir: Path,
    name: str,
    text: str,
    *,
    remote: bool = False,
    medium: str = "",
) -> list[Any]:
    """装配一次直聊调用的 messages(公开以便测试断言 context 契约)."""
    from neonrp.core.llm import Message

    L = _L(root)
    medium = medium or _medium_default(root)
    if remote:
        scene_line = _f(L["remote_scene"], place=_soul_place_label(root, soul_dir), medium=medium)
    else:
        scene_line = _f(L["face_scene"], canon=_canon_line(root))
    system = _f(L["chat_system"], name=name, how=L["how_remote"] if remote else L["how_face"], scene=scene_line,
                persona=_persona_digest(soul_dir), memory=_soul_memory_digest(soul_dir))
    msgs: list[Any] = [Message(role="system", content=system)]
    for row in read_thread(root, iid, limit=THREAD_TAIL):
        role = "assistant" if row.get("role") == "soul" else "user"
        msgs.append(Message(role=role, content=str(row.get("text") or "")))
    msgs.append(Message(role="user", content=text))
    return msgs


def _adapter(root: Path) -> Any:
    """Run 配置的 provider → 单发 adapter(独立函数以便测试注入)."""
    from neonrp.core.config import load_config, resolve_provider
    from neonrp.core.llm import get_adapter_from_config

    config = load_config(root)  # default policy: user config in play, never under pytest (10-02: stub e2e was calling the real provider)
    provider_config = resolve_provider(config, None, None)
    return get_adapter_from_config(provider_config)


# ── 群聊(房间频道)────────────────────────────────────────────────────────
# HARNESS-TEAM-DESIGN §6:同场景 = 一个房间。不全员必回——每个在场 soul
# 一次轻调用内**自选**接话或 [沉默](= "在场、在听");顺序调用,后面的
# soul 看得到前面的回应 ⇒ 互相接话,群聊自己长戏。procedural 上限 ROOM_CAP。

ROOM_CAP = 3
SILENT_MARK = "[沉默]"  # the zh mark; each language has its own (prompts/light_chat.<lang>.json "silent"), any of them counts
SILENT_MARKS = ("[沉默]", "[silent]", "[沈黙]", "[침묵]")


def room_thread_path(root: Path) -> Path:
    return _chats_dir(root) / "room.jsonl"


def read_room_thread(root: Path, limit: int = 80) -> list[dict[str, Any]]:
    path = room_thread_path(root)
    rows: list[dict[str, Any]] = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        pass
    return rows[-limit:]


def _append_room(root: Path, who: str, text: str) -> None:
    path = room_thread_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps({"who": who, "text": text, "ts": time.strftime("%H:%M")}, ensure_ascii=False)
            + "\n"
        )


def resolve_room_souls(root: Path) -> list[tuple[str, Path, str]]:
    """同场景(与玩家同节点)的 souls:(iid, soul_dir, name),cap ROOM_CAP。"""
    from neonrp.core.playthrough import read_playthrough

    pt = read_playthrough(root)
    if pt is None:
        return []
    p_node = _player_node(root)
    out: list[tuple[str, Path, str]] = []
    for ref in pt.souls:
        soul_dir = root / "souls" / f"{ref.sid}-{ref.instance_id}"
        if not soul_dir.is_dir():
            continue
        s_node = _soul_node(root, soul_dir)
        if s_node is not None and p_node is not None and s_node != p_node:
            continue
        out.append((ref.instance_id, soul_dir, _display_name(soul_dir, ref.sid)))
        if len(out) >= ROOM_CAP:
            break
    return out


def _room_messages(
    root: Path,
    soul_dir: Path,
    name: str,
    others: list[str],
    text: str,
    earlier: list[tuple[str, str]],
    stance: str = "open",
) -> list[Any]:
    """stance(M24 §6 v2):primary=主对话人必回;jumpin=被提及可插话;
    open=无主对象(开场问候式),全员自选。"""
    from neonrp.core.llm import Message

    L = _L(root)
    silent = L["silent"]
    roster = L["room_sep"].join(n for n in others if n != name) or L["room_only_you"]
    earlier_txt = (
        "\n".join(_f(L["room_said"], who=n, text=r) for n, r in earlier) if earlier else L["room_nobody_yet"]
    )
    st = stance if stance in ("primary", "jumpin") else "open"
    stance_rule = _f(L[f"stance_{st}"], silent=silent)
    ask = _f(L[f"ask_{st}"], silent=silent)
    system = _f(L["room_system"], name=name, canon=_canon_line(root), roster=roster, persona=_persona_digest(soul_dir),
                memory=_soul_memory_digest(soul_dir), stance=stance_rule)
    recent = read_room_thread(root, limit=8)
    hist = "\n".join(_f(L["room_said"], who=r.get('who'), text=r.get('text')) for r in recent) or L["room_none"]
    user = _f(L["room_user"], hist=hist, text=text, earlier=earlier_txt, ask=ask)
    return [Message(role="system", content=system), Message(role="user", content=user)]


def _mentioned_iids(
    aliases: dict[str, set[str]], text: str, *, exclude: set[str] | None = None
) -> list[str]:
    """文本里被点名的 souls(别名 casefold 子串命中,len≥2;保持发现顺序)。"""
    low = str(text or "").casefold()
    out: list[str] = []
    for iid, names in aliases.items():
        if exclude and iid in exclude:
            continue
        if any(len(n) >= 2 and n in low for n in names):
            out.append(iid)
    return out


def _last_room_speaker(root: Path, name_to_iid: dict[str, str]) -> str | None:
    for row in reversed(read_room_thread(root, limit=20)):
        who = str(row.get("who") or "")
        if who and who != "玩家" and who in name_to_iid:
            return name_to_iid[who]
    return None


def room_chat_reply(
    root: Path, text: str, primary_iid: str | None = None
) -> dict[str, Any]:
    """一轮群聊(M24 §6 v2:广播 + 主对话人 + jump-in)。

    1. 广播:同场全员都「听到」(收件箱扇出 + memo),听=零 LLM。
    2. 主对话人必回:显式指定 > 文中点名 > 上一个说话的 soul;
       无主对象(开场问候)→ 退化为全员自选。
    3. jump-in:其余 soul 仅当被玩家的话或主对话人的回应提及才起轻调用,
       仍可 [沉默]。
    Returns {ok, replies, participants, primary}。
    """
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "empty"}
    souls = resolve_room_souls(root)
    if not souls:
        return {"ok": False, "error": "no-souls-here"}

    from neonrp.core.address import soul_aliases
    from neonrp.core.inbox import InboxMessage, send_many

    dir_of = {iid: d for iid, d, _n in souls}
    name_of = {iid: n for iid, _d, n in souls}
    name_to_iid = {n: iid for iid, _d, n in souls}
    aliases = {iid: names for iid, names in soul_aliases(root) if iid in dir_of}

    # 1) 广播:全员听到(通信落收件箱;memo 在收尾统一 commit)。
    send_many(
        root,
        [
            InboxMessage.new("chat_room", "player", iid, {"text": text[:300]})
            for iid in dir_of
        ],
    )
    _append_room(root, "玩家", text)
    _append_pending(root, f"玩家 → 在场众人:「{text[:120]}」")

    # 2) 主对话人判定。
    primary = primary_iid if primary_iid in dir_of else None
    if primary is None:
        hit = _mentioned_iids(aliases, text)
        primary = hit[0] if hit else None
    if primary is None:
        primary = _last_room_speaker(root, name_to_iid)

    # 说话队列:(iid, stance)。开场无主 → 全员自选(open)。
    if primary is None:
        queue: list[tuple[str, str]] = [(iid, "open") for iid in dir_of]
    else:
        queue = [(primary, "primary")]
        for iid in _mentioned_iids(aliases, text, exclude={primary}):
            queue.append((iid, "jumpin"))

    adapter = _adapter(root)
    names = list(name_of.values())
    earlier: list[tuple[str, str]] = []
    replies: list[dict[str, Any]] = []
    called: set[str] = set()
    qi = 0
    while qi < len(queue):
        iid, stance = queue[qi]
        qi += 1
        if iid in called:
            continue
        called.add(iid)
        soul_dir, name = dir_of[iid], name_of[iid]
        try:
            res = adapter.chat(
                _room_messages(root, soul_dir, name, names, text, earlier, stance=stance)
            )
            msg = getattr(res, "message", None)
            reply = (
                getattr(msg, "content", None) or (msg if isinstance(msg, str) else "") or ""
            ).strip()
        except Exception:  # noqa: BLE001 — 单个 soul 失败不拖垮整轮
            logger.warning("room chat call failed for %s", iid, exc_info=True)
            reply = ""
        silent = (not reply) or any(m in reply[:12] for m in SILENT_MARKS)
        if silent:
            replies.append({"iid": iid, "name": name, "reply": None})
            commit_chat_memory(
                root,
                soul_dir,
                event=f"玩家在场说:「{text[:120]}」",
                my_reaction="我在场听到了,没接话",
            )
            continue
        replies.append({"iid": iid, "name": name, "reply": reply})
        earlier.append((name, reply))
        _append_room(root, name, reply)
        _append_pending(root, f"{name} 回应:「{reply[:160]}」")
        commit_chat_memory(
            root,
            soul_dir,
            event=f"玩家在场说:「{text[:120]}」",
            my_reaction=f"我接话:「{reply[:120]}」",
        )
        # 3) jump-in:回应中点到了尚未说话的在场 soul → 触发其插话机会。
        for jid in _mentioned_iids(aliases, reply, exclude=called):
            queue.append((jid, "jumpin"))

    # 收尾:没被叫到的人也「听到了」(在听是经历,M24 §4 记忆义务)。
    for iid, soul_dir, _name in souls:
        if iid not in called:
            replies.append({"iid": iid, "name": name_of[iid], "reply": None})
            commit_chat_memory(
                root,
                soul_dir,
                event=f"玩家在场说:「{text[:120]}」",
                my_reaction="我在场听到了",
            )
    return {
        "ok": True,
        "replies": replies,
        "participants": names,
        "primary": primary,
        "world_intent": detect_world_intent(root, text),
    }


# ── 世界意图探测(升级签)────────────────────────────────────────────────────
# 聊天里会「情不自禁」说移动——拍是引擎概念,玩家不需要知道它
# 存在;边界由 UI 优雅接驳。procedural 探测玩家话里的移动/行动意图,回包带
# world_intent,UI 渲染一枚「▸ 动身」升级签;点了才进世界拍,不点只是聊过
# (意向仍经结算桥告知 world-agent)。不自动升级:误判感慨句代价太高。

_MOVE_VERBS = ("去", "走吧", "出发", "动身", "前往", "移动", "带我", "我们走", "过去")


def _known_places(root: Path) -> list[tuple[str, str]]:
    """[(友好名, node_id)];来自各镇 town_map 节点。best-effort。"""
    out: list[tuple[str, str]] = []
    try:
        from neonrp.core.place_nav import _town_maps

        for _town, tmap in _town_maps(root).items():
            nodes = tmap.get("nodes")
            if isinstance(nodes, list):
                for n in nodes:
                    if isinstance(n, dict) and n.get("id"):
                        nm = str(n.get("name") or "").strip()
                        if nm:
                            out.append((nm, str(n["id"])))
    except Exception:  # noqa: BLE001 — 探测器绝不冒泡
        pass
    return out


def detect_world_intent(root: Path, text: str) -> dict[str, Any] | None:
    """玩家聊天句里的世界意图(MVP:移动)。None=纯聊天。"""
    t = str(text or "").strip()
    if not t:
        return None
    has_verb = any(v in t for v in _MOVE_VERBS)
    for nm, node in _known_places(root):
        if len(nm) >= 2 and nm in t:
            if has_verb or f"去{nm}" in t:
                return {"kind": "move", "target": node, "label": f"▸ 动身:去{nm}"}
    if has_verb and ("吧" in t or "走" in t):
        # 强移动语气但没点到具体地名 → 泛行动签(由世界拍解析去处)。
        return {"kind": "action", "target": None, "label": "▸ 付诸行动"}
    return None


def ask_soul_deliver(
    root: Path, target: str, question: str, *, asker: str = "world-agent", beat: dict[str, str] | None = None,
    on_text: Any = None,
) -> dict[str, Any]:
    """M24 §5 主权双向通道的投递面。

    判断力(该不该问/问什么/可达性)完全归 world-agent —— 它像用 ask_user
    一样调用 ask_soul;引擎只做两件事:把问题带着 soul 的本体视角(她的
    场景/persona/记忆)投给她,把她的原话带回。无同场门:中世纪联系不上
    是 world-agent 的叙事判断,不是引擎硬门。

    协议留痕:收件箱 ask_request → soul_response(request_id 关联);
    soul 记忆 commit(被问也是经历)。target 可为 iid 或名字/别名。
    """
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "error": "empty question"}
    from neonrp.core.address import soul_aliases
    from neonrp.core.playthrough import read_playthrough

    pt = read_playthrough(root)
    if pt is None:
        return {"ok": False, "error": "no playthrough"}
    tgt = str(target or "").strip()
    low = tgt.casefold()
    iid: str | None = None
    for _iid, names in soul_aliases(root):
        if _iid == tgt or low in names:
            iid = _iid
            break
    if iid is None:
        return {"ok": False, "error": f"unknown soul: {tgt}"}
    ref = next((s for s in pt.souls if s.instance_id == iid), None)
    if ref is None:
        return {"ok": False, "error": f"unknown soul: {tgt}"}
    soul_dir = root / "souls" / f"{ref.sid}-{ref.instance_id}"
    if not soul_dir.is_dir():
        return {"ok": False, "error": f"soul folder missing: {iid}"}
    name = _display_name(soul_dir, ref.sid)
    s_node = _soul_node(root, soul_dir)
    p_node = _player_node(root)
    co_located = not (s_node and p_node and s_node != p_node)

    from neonrp.core.inbox import InboxMessage, send as _send

    rid = uuid.uuid4().hex[:8]
    _send(
        root,
        InboxMessage.new(
            "ask_request", asker, iid, {"request_id": rid, "question": q[:400]}
        ),
    )
    from neonrp.core import soul_remote

    proxy = False
    remote = soul_remote.route(iid)
    if remote is not None:  # 10-10: her seat is taken by someone elsewhere — she answers herself, over the network
        human = soul_remote.is_human(iid)
        try:
            got = remote(question=q, beat=beat, timeout=soul_remote.HUMAN_TIMEOUT if human else soul_remote.ASK_TIMEOUT)
        except Exception:  # noqa: BLE001 — a broken connection is a late answer
            got = None
        if got and str(got).strip():
            answer = str(got).strip()
            if on_text is not None:
                on_text(answer)
            _send(root, InboxMessage.new("soul_response", iid, asker, {"request_id": rid, "answer": answer[:400], "remote": True}))
            return {"ok": True, "iid": iid, "name": name, "answer": answer, "co_located": co_located,
                    "location": s_node or "", "streamed": on_text is not None, "remote": True}
        if human:  # a person: never stood in for — she hesitates this turn
            _send(root, InboxMessage.new("soul_response", iid, asker, {"request_id": rid, "answer": "", "hesitated": True}))
            return {"ok": True, "iid": iid, "name": name, "answer": _f(_L(root).get("hesitated") or "({name} hesitates and says nothing)", name=name),
                    "co_located": co_located, "location": s_node or "", "streamed": False, "remote": True, "hesitated": True}
        proxy = True  # no answer in time: the host stands in for her, from what it holds (her public card), marked 「代」

    from neonrp.core.llm import Message

    if beat is not None:  # her own beat — she plays like the player, on the world's prose (core/soul_view)
        system = _beat_system(root, iid, name, soul_dir)
    else:  # the world calls on her ([ask 名字]): the host asks, she answers
        system = _f(_L(root)["ask_system"], name=name, place=_soul_place_label(root, soul_dir),
                    persona=_persona_digest(soul_dir), memory=_soul_memory_digest(soul_dir))
    streamed = False
    try:
        if on_text is not None:  # her words reach the screen as she writes them
            from neonrp.core.stream_lines import stream_chat

            answer, streamed = stream_chat(_adapter(root), [Message(role="system", content=system), Message(role="user", content=q)], on_text)
        else:
            res = _adapter(root).chat(
                [Message(role="system", content=system), Message(role="user", content=q)]
            )
            msg = getattr(res, "message", None)
            answer = (
                getattr(msg, "content", None) or (msg if isinstance(msg, str) else "") or ""
            ).strip()
    except Exception as exc:  # noqa: BLE001 — 通道失败不冒泡进世界拍
        logger.warning("ask_soul LLM failed", exc_info=True)
        return {"ok": False, "error": f"llm: {exc}"[:200]}
    if not answer:
        return {"ok": False, "error": "empty answer"}
    if beat is not None:  # what happened, not the prompt (10-02: memory held 「主持人问我:「# 你眼前…」」)
        commit_chat_memory(root, soul_dir, event=str(beat.get("event") or "")[:200], my_reaction=f"我:{answer[:160]}", label=f"回合{_current_turn(root)}")
    else:
        commit_chat_memory(
            root,
            soul_dir,
            event=f"主持人问我:「{q[:120]}」",
            my_reaction=f"我答:「{answer[:120]}」",
        )
    _send(
        root,
        InboxMessage.new(
            "soul_response", iid, asker, {"request_id": rid, "answer": answer[:400], **({"proxy": True} if proxy else {})}
        ),
    )
    return {
        "ok": True,
        "iid": iid,
        "name": name,
        "answer": answer,
        "co_located": co_located,
        "location": s_node or "",
        "streamed": streamed,
        **({"proxy": True} if proxy else {}),
    }


def light_chat_reply(root: Path, iid: str, text: str) -> dict[str, Any]:
    """一次直聊交换:同场景门 → 一次纯 LLM 调用 → 落线程 + 落结算桥。

    Returns {ok, name?, reply?, error?}。阻塞;调用方放线程池/请求线程。
    """
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "empty"}
    resolved = resolve_reachable_soul(root, iid)
    if resolved is None:
        return {"ok": False, "error": "not-co-located"}
    soul_dir, name, remote = resolved
    medium = (remote_comms(root) or {}).get("medium", _medium_default(root)) if remote else ""
    msgs = build_chat_messages(
        root, iid, soul_dir, name, text, remote=remote, medium=medium or _medium_default(root)
    )
    try:
        res = _adapter(root).chat(msgs)
        msg = getattr(res, "message", None)
        reply = (
            getattr(msg, "content", None) or (msg if isinstance(msg, str) else "") or ""
        ).strip()
    except Exception as exc:  # noqa: BLE001 — 轻拍失败绝不崩世界
        logger.warning("light chat LLM failed", exc_info=True)
        return {"ok": False, "error": f"llm: {exc}"[:200]}
    if not reply:
        return {"ok": False, "error": "empty reply"}
    _append_thread(root, iid, "player", text)
    _append_thread(root, iid, "soul", reply)
    L = _L(root)  # 10-06: these lines reach the model again (pending notes, the soul's memory) — the run's language
    _via = L["chat_via"].format(medium=medium) if remote else ""
    _append_pending(root, L["chat_pending_player"].format(name=name, via=_via, text=text[:120]))
    _append_pending(root, L["chat_pending_soul"].format(name=name, via=_via, text=reply[:160]))
    # M24 §4:soul 记忆 commit(本体记得这场闲聊/这条讯息)。
    commit_chat_memory(
        root,
        soul_dir,
        event=L["chat_mem_event"].format(via_word=L["chat_mem_via_word"].format(medium=medium) if remote else "", text=text[:120]),
        my_reaction=L["chat_mem_reaction"].format(text=reply[:120]),
    )
    try:  # talking with a standalone character is noted in the player's record — not gained (core/player_data, 10-15)
        from neonrp.core import player_data as _pd

        _pd.talked(root, iid)
    except Exception:  # noqa: BLE001 — the player's record never fails a chat
        pass
    return {
        "ok": True,
        "name": name,
        "reply": reply,
        "remote": remote,
        "medium": medium or None,
        "world_intent": detect_world_intent(root, text),
    }
