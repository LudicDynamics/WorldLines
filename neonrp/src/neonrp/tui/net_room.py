"""The TUI at a networked table: the host's room (``/status room``), join requests
as they come, and — when this TUI holds a character's seat — the table turning to you ("what do you do this turn?"):
the next line you type answers it instead of starting a turn.
"""
from __future__ import annotations

import threading
from typing import Any

from rich.text import Text

ACCENT, MUTED, WARN = "#c4b5fd", "#9ca3af", "#fbbf24"
ASK_WAIT = 35.0  # s — a little longer than the host's deadline for a person (soul_remote.HUMAN_TIMEOUT)


def _remote(app: Any) -> Any:
    s = getattr(app, "session", None)
    return s if getattr(s, "remote", False) else None


def _row(app: Any, text: Any, cls: str = "pc-out") -> None:
    from neonrp.tui.app import ConversationView

    try:
        app.query_one("#conversation-view", ConversationView).add_beat_row(text if isinstance(text, Text) else Text(str(text), style=MUTED), cls)
    except Exception:  # noqa: BLE001
        pass


# ── /status room ─────────────────────────────────────────────────────────────────────────────────────────────────────

def cmd_room(app: Any, args: list[str]) -> None:
    """/status room [invite <kind> <target> [label] | approve <request|all> | deny <request> | revoke <seat> | auto on|off]"""
    c = _remote(app)
    if c is None:
        _row(app, "这一局不在联网:先 `neonrp serve --project <世界>` 起主进程,再 `neonrp tui --connect <地址> --token <令牌>`。")
        return
    sub, rest = (args[0].lower() if args else ""), args[1:]

    def work() -> None:
        try:
            if sub == "invite" and len(rest) >= 2:
                inv = c.call("room.invite", {"kind": rest[0], "target": rest[1], "label": " ".join(rest[2:])})
                t = Text("邀请 ", style=f"bold {ACCENT}")
                t.append(f"{inv['seat']}\n", style="bold #f8fafc")
                t.append("链接  ", style=MUTED)
                t.append(f"{inv['link']}\n", style="#e5e7eb")
                t.append("短码  ", style=MUTED)
                t.append(inv["code"], style=f"bold {WARN}")
                t.append("    对方:neonrp tui --join <链接>(短码另加 --url http://<本机地址:端口>)", style=MUTED)
                app.call_from_thread(_row, app, t)
                return
            if sub == "approve" and rest:
                ids = [p["request"] for p in c.call("room.pending")] if rest[0] == "all" else [rest[0]]
                for r in ids:
                    c.call("room.approve", {"request": r})
                app.call_from_thread(_row, app, f"已批准 {len(ids)} 个入座请求。")
                return
            if sub == "deny" and rest:
                c.call("room.deny", {"request": rest[0]})
                app.call_from_thread(_row, app, "已拒绝。")
                return
            if sub == "revoke" and rest:
                n = c.call("room.revoke", {"seat": rest[0]})["revoked"]
                app.call_from_thread(_row, app, f"{rest[0]}:收回 {n} 个凭证。")
                return
            if sub == "auto" and rest:
                on = c.call("room.auto_approve", {"on": rest[0] in ("on", "1", "true", "开")})["auto_approve"]
                app.call_from_thread(_row, app, "入座:自动批准" if on else "入座:要房主批准")
                return
            info, pend = c.call("room.seats"), c.call("room.pending")
            t = Text(f"房间 {info['room']}", style=f"bold {ACCENT}")
            t.append(f"   入座{'自动批准' if info['auto_approve'] else '要房主批准'}\n", style=MUTED)
            for s in info["seats"] or []:
                t.append(f"  {'●' if s['connected'] else '○'} ", style="#4ade80" if s["connected"] else MUTED)
                t.append(f"{s['seat']}", style="bold #f8fafc")
                t.append(f"  {s.get('label') or ''}\n", style=MUTED)
            for p in pend:
                t.append(f"  ? {p['seat']} 请求入座({p.get('who') or '—'})  /status room approve {p['request']}\n", style=WARN)
            if not info["seats"] and not pend:
                t.append("  还没有席位。/status room invite character <角色 iid> [名字] · /status room invite player <pid>\n", style=MUTED)
            app.call_from_thread(_row, app, t)
        except Exception as e:  # noqa: BLE001
            app.call_from_thread(_row, app, Text(f"房间操作失败:{e}", style="#f87171"))

    threading.Thread(target=work, daemon=True).start()


# ── the table turning to you, and join requests ───────────────────────────────────────────────────────────────────────

def attach(app: Any) -> None:
    """Hook a remote session's host requests and notices into this TUI (once per session)."""
    c = _remote(app)
    if c is None or getattr(app, "_net_room_attached", None) is c:
        return
    app._net_room_attached = c
    app._net_pending_ask = None

    def _soul_ask(p: dict[str, Any]) -> Any:
        ev, box = threading.Event(), []
        app._net_pending_ask = (ev, box)
        t = Text("轮到你 ", style=f"bold {WARN}")
        t.append(str(p.get("question") or ""), style="#f8fafc")
        t.append("\n(直接输入你的角色这回合做什么 / 说什么)", style=MUTED)
        app.call_from_thread(_row, app, t, "pc-status")
        ev.wait(ASK_WAIT)
        app._net_pending_ask = None
        return box[0] if box else None

    c.on("soul.ask", _soul_ask)

    def _note(msg: Any) -> None:
        p = dict(msg.payload or {})
        if msg.topic == "net/room.join_request":
            app.call_from_thread(_row, app, Text(f"有人请求入座 {p.get('seat')}({p.get('who') or '—'}):/status room approve {p.get('request')}", style=WARN))

    c.bus().subscribe("net/#", _note)


def take_answer(app: Any, text: str) -> bool:
    """If the table is waiting on you, this line is your answer (not a new turn). True = consumed."""
    pend = getattr(app, "_net_pending_ask", None)
    if not pend:
        return False
    ev, box = pend
    box.append(text)
    ev.set()
    app._net_pending_ask = None
    _row(app, Text(f"你:{text}", style="#e5e7eb"))
    return True
