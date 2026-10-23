"""Runtime Discord bridge — mirrors narration to a channel, reads replies.

Design notes:
- Lazy-imports `discord.py`. If the user didn't install the optional
  [discord] extra, `start()` reports a friendly error and the bridge
  just no-ops.
- Runs discord.py's asyncio loop in a dedicated daemon thread so the
  Textual TUI keeps its own event loop clean.
- Outbound events from the hub are scheduled via
  `asyncio.run_coroutine_threadsafe` — safe from any thread.
- Only the bound channel is listened to; the bot's own messages and DMs
  are ignored. Single-player mode: every Discord user's message is
  treated as "the player".
- Narration messages are chunked to Discord's 2000-char limit; long
  turns split across multiple messages preserving paragraph breaks.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from neonrp.bridges.hub import BridgeHub, InboundMessage, OutboundEvent

# Defence-in-depth against callers that emit text with long blank-line runs
# (e.g. raw subprocess stdout, or narrator buffers that kept whitespace-only
# lines). `\n{3,}` alone doesn't catch `\n \n \n` — a blank line with a lone
# space reads as non-empty to the regex. `_normalize_blanks` rstrips each
# line first, then collapses runs of empty lines to a single empty line.


def _normalize_blanks(text: str) -> str:
    """Right-trim each line and collapse blank-line runs to one blank line.

    Discord renders Markdown where one blank line separates paragraphs —
    more blank lines add no value and look like dead air. Also strips
    leading/trailing blank lines entirely.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if prev_blank:
                continue
            prev_blank = True
            cleaned.append("")
        else:
            prev_blank = False
            cleaned.append(line)
    # Strip leading / trailing blanks.
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)

logger = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000
SAFE_CHUNK_LIMIT = 1900  # leave room for `> ...` prefix and code-fence wrapping


def discord_py_status() -> tuple[bool, str | None, str | None]:
    """Return (installed, version, error_hint) for the optional discord.py dep.

    Used by the wizard to tell the user up-front whether the runtime bridge
    is usable. Installation hint is the same command surfaced in the bridge's
    own `start()` fallback.
    """
    try:
        import discord  # noqa: F401
    except ImportError as exc:
        return (
            False,
            None,
            f"discord.py not installed — run `uv tool install --force worldlines` ({exc})",
        )
    version = getattr(discord, "__version__", None)
    return True, str(version) if version else None, None


class DiscordBridge:
    """Mirrors narrator output to a Discord channel and relays player input."""

    name = "discord"

    def __init__(
        self,
        *,
        bot_token: str,
        channel_id: str,
        speaker_prefix: bool = True,
    ) -> None:
        self._token = bot_token
        self._channel_id = int(str(channel_id).strip() or "0")
        self._speaker_prefix = speaker_prefix
        self._hub: BridgeHub | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None  # discord.Client (lazy-typed)
        self._channel: Any = None  # discord.TextChannel
        self._ready_event = threading.Event()
        self._import_error: str | None = None
        # In-flight "💭 Thinking…" message — set on `turn_status=thinking`,
        # edited into the real narration on `narrator_text`, cleaned up on
        # `turn_status=complete`. Keeps Discord visually active while the
        # LLM is still streaming locally.
        self._pending_status_msg: Any = None  # discord.Message | None
        # Most-recent inbound Discord message — we react on it with 🤔 when
        # the turn starts and swap to ✅ when it ends, so the Discord-side
        # player sees the status directly on their own message.
        self._last_inbound_msg: Any = None  # discord.Message | None
        self._thinking_emoji = "🤔"
        self._done_emoji = "✅"

    # ------------------------------------------------------------------
    # Bridge protocol
    # ------------------------------------------------------------------

    def start(self, hub: BridgeHub) -> None:
        if not self._token or not self._channel_id:
            logger.warning("discord bridge: missing bot_token or channel_id, not starting")
            return
        self._hub = hub

        # Import here so missing optional dep doesn't break TUI startup.
        try:
            import discord  # noqa: F401
        except ImportError as exc:
            self._import_error = (
                f"discord.py not installed — run `uv tool install --force worldlines` ({exc})"
            )
            logger.warning(self._import_error)
            return

        self._thread = threading.Thread(
            target=self._run_loop,
            name="neonrp-discord-bridge",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None and self._client is not None:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                fut.result(timeout=5.0)
            except Exception:
                logger.debug("discord bridge: stop timed out / raised", exc_info=True)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._loop = None
        self._client = None
        self._channel = None
        self._ready_event.clear()

    def on_outbound(self, event: OutboundEvent) -> None:
        if self._loop is None or self._client is None:
            return

        if event.kind == "turn_status":
            state = str((event.data or {}).get("state", "")).strip().lower()
            try:
                if state == "thinking":
                    asyncio.run_coroutine_threadsafe(
                        self._post_thinking_status(), self._loop
                    )
                elif state == "complete":
                    asyncio.run_coroutine_threadsafe(
                        self._finalize_thinking_status(), self._loop
                    )
            except Exception:
                logger.exception("discord bridge: failed to schedule turn_status")
            return

        if event.kind == "ask_user":
            text = self._format_ask_user(event)
            if text:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._send_or_replace_pending(text), self._loop
                    )
                except Exception:
                    logger.exception("discord bridge: failed to schedule ask_user")
            return

        if event.kind not in ("narrator_text", "system_notice"):
            return
        text = self._format_outbound(event)
        if not text:
            return
        try:
            # Prefer editing the pending "thinking" message in place, so the
            # Discord viewer sees 💭 → narration without a new message below.
            asyncio.run_coroutine_threadsafe(
                self._send_or_replace_pending(text), self._loop
            )
        except Exception:
            logger.exception("discord bridge: failed to schedule send")

    def last_error(self) -> str | None:
        return self._import_error

    # ------------------------------------------------------------------
    # asyncio loop thread
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        import discord

        intents = discord.Intents.default()
        intents.message_content = True  # needs Message Content Intent enabled in portal

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:  # noqa: ANN202 — discord.py callback
            try:
                self._channel = client.get_channel(self._channel_id) or await client.fetch_channel(
                    self._channel_id
                )
            except Exception as exc:
                logger.warning("discord bridge: couldn't fetch channel %s: %s", self._channel_id, exc)
                self._channel = None
                return
            self._ready_event.set()
            logger.info(
                "discord bridge ready: bot=%s channel=%s",
                getattr(client.user, "name", "?"),
                getattr(self._channel, "name", "?"),
            )

        @client.event
        async def on_message(message: Any) -> None:  # noqa: ANN202
            if client.user is not None and message.author.id == client.user.id:
                return
            # Only react to the bound channel (ignore DMs, other channels).
            if getattr(message.channel, "id", None) != self._channel_id:
                return
            if not self._hub:
                return
            # Strip Discord mentions of the bot itself so the player text is clean.
            raw = message.content or ""
            if client.user is not None:
                raw = raw.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
            if not raw:
                return
            inbound = InboundMessage(
                source="discord",
                kind="message",
                text=raw,
                user_id=str(message.author.id),
                channel_id=str(message.channel.id),
                extra={
                    "author": str(message.author),
                    "mention": f"<@{message.author.id}>",
                },
            )
            # Remember the source Discord message so `turn_status` can
            # decorate it with 🤔 / ✅ reactions. Overwriting is fine —
            # whoever typed last is whose turn we're processing.
            self._last_inbound_msg = message
            # Submit back to the game. The hub's inbound_handler (TUI's
            # _send_message wrapper) hops to the UI thread via call_from_thread.
            try:
                self._hub.submit_inbound(inbound)
            except Exception:
                logger.exception("discord bridge: inbound submit failed")

        # Each thread needs its own event loop.
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(client.start(self._token))
        except Exception:
            logger.exception("discord bridge: gateway task failed")
        finally:
            try:
                loop.run_until_complete(asyncio.sleep(0))
            except Exception:
                pass
            loop.close()

    # ------------------------------------------------------------------
    # Outbound helpers
    # ------------------------------------------------------------------

    def _format_outbound(self, event: OutboundEvent) -> str:
        speaker = (event.speaker or "").strip()
        text = _normalize_blanks(event.text or "")
        if not text:
            return ""
        if self._speaker_prefix and speaker and event.kind == "narrator_text":
            return f"**[{speaker}]**\n{text}"
        if event.kind == "system_notice":
            return f"_{text}_"
        return text

    def _format_ask_user(self, event: OutboundEvent) -> str:
        """Render an ask_user prompt as a Discord message with numbered options.

        We edit this INTO the 💭 placeholder slot so the Discord viewer sees
        the turn move from "thinking" → "awaiting choice" cleanly, without
        the silent-completion fallback that used to fire when the turn was
        paused on ask_user.
        """
        data = event.data or {}
        question = _normalize_blanks(str(data.get("question", "") or ""))
        raw_options = data.get("options") or []
        options = [str(o).strip() for o in raw_options if str(o).strip()]
        if not question and not options:
            return ""
        lines = ["❓  **Input needed**"]
        if question:
            lines.append("")
            lines.append(question)
        if options:
            lines.append("")
            for i, opt in enumerate(options, start=1):
                lines.append(f"  **{i}.** {opt}")
        lines.append("")
        lines.append("_(reply in-game — this channel is read-only for prompts)_")
        return "\n".join(lines)

    async def _send_chunks(self, text: str) -> None:
        if self._channel is None:
            # Channel not resolved yet — wait up to 5s, then drop.
            for _ in range(50):
                if self._channel is not None:
                    break
                await asyncio.sleep(0.1)
            if self._channel is None:
                return
        for chunk in _split_for_discord(text, SAFE_CHUNK_LIMIT):
            try:
                await self._channel.send(chunk)
            except Exception:
                logger.exception("discord bridge: send failed")

    # ------------------------------------------------------------------
    # Turn-status lifecycle: visible "thinking" placeholder that morphs
    # into the final narration in-place.
    # ------------------------------------------------------------------

    async def _await_channel_ready(self) -> bool:
        if self._channel is not None:
            return True
        for _ in range(50):
            if self._channel is not None:
                return True
            await asyncio.sleep(0.1)
        return self._channel is not None

    async def _post_thinking_status(self) -> None:
        """Post the 💭 placeholder and add a 🤔 reaction on the source msg."""
        if not await self._await_channel_ready():
            return
        if self._pending_status_msg is not None:
            # Previous turn never completed — let it linger; start a fresh one.
            self._pending_status_msg = None
        # React on the Discord player's own message so they see the status
        # right next to what they sent. Best-effort — if the message was
        # deleted or we lack permission, just skip.
        src = self._last_inbound_msg
        if src is not None:
            try:
                await src.add_reaction(self._thinking_emoji)
            except Exception:
                logger.debug("discord bridge: add thinking reaction failed", exc_info=True)
        try:
            self._pending_status_msg = await self._channel.send("💭  _Thinking…_")
        except Exception:
            logger.exception("discord bridge: failed to post thinking status")
            self._pending_status_msg = None

    async def _send_or_replace_pending(self, text: str) -> None:
        """If a 💭 placeholder exists, edit it into the first chunk of the
        narration (so the same slot morphs from thinking→narration) and
        send any remaining chunks as follow-ups. Otherwise just send."""
        if not await self._await_channel_ready():
            return
        chunks = _split_for_discord(text, SAFE_CHUNK_LIMIT)
        if not chunks:
            return
        pending = self._pending_status_msg
        self._pending_status_msg = None
        first = chunks[0]
        if pending is not None:
            try:
                await pending.edit(content=first)
            except Exception:
                # Edit races against delete / channel change — fall back to a
                # fresh send so the narration still lands.
                logger.debug("discord bridge: edit pending failed, sending new", exc_info=True)
                try:
                    await self._channel.send(first)
                except Exception:
                    logger.exception("discord bridge: send fallback failed")
        else:
            try:
                await self._channel.send(first)
            except Exception:
                logger.exception("discord bridge: send failed")
        for extra in chunks[1:]:
            try:
                await self._channel.send(extra)
            except Exception:
                logger.exception("discord bridge: send follow-up failed")

    async def _finalize_thinking_status(self) -> None:
        """Called on turn_status=complete. Swap 🤔 → ✅ on the player's
        source message, and if the bot-side placeholder is still around
        (turn produced no visible narration), mark it as done so the user
        knows the turn finished silently rather than crashed."""
        src = self._last_inbound_msg
        self._last_inbound_msg = None
        pending = self._pending_status_msg
        self._pending_status_msg = None

        # Swap 🤔 → ✅ on the player's message. Best-effort — fire both
        # regardless of each other's result so partial failures don't leave
        # the player's message stuck showing 🤔 forever.
        if src is not None:
            client_user = getattr(self._client, "user", None) if self._client else None
            try:
                if client_user is not None:
                    await src.remove_reaction(self._thinking_emoji, client_user)
            except Exception:
                logger.debug("discord bridge: remove thinking reaction failed", exc_info=True)
            try:
                await src.add_reaction(self._done_emoji)
            except Exception:
                logger.debug("discord bridge: add done reaction failed", exc_info=True)

        if pending is None:
            return
        if not await self._await_channel_ready():
            return
        try:
            await pending.edit(content="✓  _(turn completed silently — no narration)_")
        except Exception:
            logger.debug("discord bridge: finalize pending failed", exc_info=True)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _split_for_discord(text: str, limit: int) -> list[str]:
    """Split on paragraph / line boundaries to stay under Discord's 2000-char cap."""
    text = text.strip()
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        # Prefer paragraph break, then newline, then space.
        window = remaining[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


def build_discord_bridge_from_config(user_config_path: Path | None = None) -> DiscordBridge | None:
    """Build a DiscordBridge from `~/.neonrp/config.json → discord`.

    Returns None when required fields are missing so the caller can show a
    user-friendly "not configured" message instead of crashing.
    """
    from neonrp.core.discord_config import get_discord_settings

    settings = get_discord_settings()
    token = str(settings.get("bot_token", "") or "").strip()
    channel_id = str(settings.get("channel_id", "") or "").strip()
    if not token or not channel_id:
        return None
    return DiscordBridge(bot_token=token, channel_id=channel_id)
