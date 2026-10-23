"""SoulContextScreen — one character's context, team-mode style (TODO #3).

Opened by clicking a name in the 在场灵魂 lane or with ``/who <name>``.
Shows where the character is, what it remembers, what it did in the last
turns and the private thread; ``t`` starts a private chat (``@name``) and
the input at the bottom makes the character act *now* on your behalf
(``engage_soul_run`` — a full soul turn with your note as the situation).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from neonrp.tui.i18n import get_message


class SoulContextScreen(ModalScreen[tuple[str, str] | None]):
    """Dismisses with ``("talk", iid)`` (open a private chat) or ``None``."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("t", "talk", "Talk", show=True),
        Binding("a", "act", "Act as", show=True),
    ]

    DEFAULT_CSS = """
    SoulContextScreen { align: center middle; background: #09090B; }
    SoulContextScreen > #soul-ctx {
        width: 88%; max-width: 110; height: 92%;
        border-top: double #5BE0B0; border-bottom: double #5BE0B0;
        border-left: solid #5BE0B0; border-right: solid #5BE0B0;
        background: #09090B; padding: 1 2;
    }
    SoulContextScreen Static.title { color: #E4E4E7; text-style: bold; margin-bottom: 1; }
    SoulContextScreen Static.section { color: #5BE0B0; text-style: bold; margin-top: 1; }
    SoulContextScreen Static.body { color: #D4D4D8; }
    SoulContextScreen Static.dim { color: #71717A; }
    SoulContextScreen #soul-act { margin-top: 1; }
    SoulContextScreen #soul-act-result { height: auto; color: #A1A1AA; margin-top: 1; }
    """

    def __init__(
        self,
        ctx: dict[str, Any],
        *,
        root: Path | None = None,
        locale: str = "zh",
        on_engaged: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__()
        self._ctx = ctx
        self._root = root
        self._locale = locale
        self._on_engaged = on_engaged
        self._busy = False

    def _t(self, key: str) -> str:
        try:
            return get_message(self._locale, key)
        except Exception:
            return key

    @property
    def iid(self) -> str:
        return str(self._ctx.get("iid") or "")

    def compose(self) -> ComposeResult:
        c = self._ctx
        loc = c.get("location") or {}
        status = c.get("status") or {}
        with VerticalScroll(id="soul-ctx"):
            stage = self._t("soul.ctx.on_stage") if c.get("on_stage") else self._t("soul.ctx.off_stage")
            yield Static(
                f"[bold #5BE0B0]◆[/] [bold]{c.get('name', '?')}[/]  [dim]{c.get('sid', '')} · {c.get('role', '')} · {stage}[/]",
                classes="title",
                id="soul-ctx-title",
            )
            where = loc.get("name") or loc.get("node") or self._t("soul.ctx.unknown")
            bits = [f"{self._t('soul.ctx.location')}: {where}"]
            if status.get("mood"):
                bits.append(f"{self._t('soul.ctx.mood')}: {status['mood']}")
            if status.get("hp") is not None:
                bits.append(f"HP {status.get('hp')}/{status.get('max_hp', '?')}")
            if c.get("turn_count") is not None:
                bits.append(f"T{c.get('turn_count')}")
            if c.get("remote"):
                bits.append(self._t("chat.call_via").format(medium=c.get("medium") or ""))
            elif c.get("reachable") is False:
                bits.append(self._t("chat.unreachable"))
            yield Static("  ·  ".join(bits), classes="body", markup=False)

            yield Static(self._t("soul.ctx.progress"), classes="section")
            progress = c.get("progress") or []
            if not progress:
                yield Static(self._t("soul.ctx.no_progress"), classes="dim", markup=False)
            for row in progress:
                head = f"T{row.get('turn_seq')}"
                if row.get("location"):
                    head += f" · {row['location']}"
                line = head
                if row.get("reason"):
                    line += f"\n    ↳ {row['reason']}"
                if row.get("speech"):
                    line += f"\n    「{row['speech']}」"
                yield Static(line, classes="body", markup=False)

            yield Static(self._t("soul.ctx.memory"), classes="section")
            yield Static(str(c.get("memory") or self._t("soul.ctx.none")), classes="body", markup=False)

            yield Static(self._t("soul.ctx.persona"), classes="section")
            yield Static(str(c.get("persona") or self._t("soul.ctx.none")), classes="dim", markup=False)

            yield Static(self._t("soul.ctx.thread"), classes="section")
            thread = c.get("thread") or []
            if not thread:
                yield Static(self._t("soul.ctx.no_thread"), classes="dim", markup=False)
            for r in thread:
                who = self._t("soul.ctx.you") if r.get("role") == "player" else c.get("name", "TA")
                yield Static(f"{r.get('ts', '')} {who}: {r.get('text', '')}", classes="dim", markup=False)

            yield Static(self._t("soul.ctx.hint"), classes="dim", markup=False)
            yield Input(placeholder=self._t("soul.ctx.act_placeholder"), id="soul-act")
            yield Static("", id="soul-act-result", markup=False)

    # ── actions ──────────────────────────────────────────────────────
    def action_close(self) -> None:
        self.dismiss(None)

    def action_talk(self) -> None:
        self.dismiss(("talk", self.iid))

    def action_act(self) -> None:
        try:
            self.query_one("#soul-act", Input).focus()
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if getattr(event.input, "id", None) != "soul-act":
            return
        note = event.value.strip()
        if not note:
            return
        event.stop()
        self.engage(note)

    def _set_result(self, text: str) -> None:
        try:
            self.query_one("#soul-act-result", Static).update(text)
        except Exception:
            pass

    def engage(self, note: str) -> None:
        """Make the character take a turn now with ``note`` as the situation."""
        if self._busy or self._root is None:
            return
        self._busy = True
        self._set_result(self._t("soul.ctx.acting"))
        try:
            self.query_one("#soul-act", Input).value = ""
        except Exception:
            pass
        root, iid = self._root, self.iid

        def worker() -> None:
            try:
                from neonrp.core.engage import engage_soul_run

                out = engage_soul_run(root, iid, note=note)
            except Exception as exc:  # noqa: BLE001 — never crash the screen
                out = {"ok": False, "error": str(exc)[:200]}

            def apply() -> None:
                self._busy = False
                if out.get("ok"):
                    text = out.get("digest") or ""
                    if out.get("intended_action"):
                        text += f"\n→ {out['intended_action']}"
                    if out.get("inner_voice"):
                        text += f"\n({out['inner_voice']})"
                    self._set_result(text.strip() or self._t("soul.ctx.acted"))
                else:
                    self._set_result(f"{self._t('soul.ctx.act_failed')}: {out.get('error', '?')}")
                if self._on_engaged is not None:
                    try:
                        self._on_engaged({**out, "note": note})
                    except Exception:
                        pass

            try:
                self.app.call_from_thread(apply)
            except Exception:
                apply()

        threading.Thread(target=worker, daemon=True, name="neonrp-engage").start()
