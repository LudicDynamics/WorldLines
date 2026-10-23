"""ask_user narration must accumulate in the scrollable transcript.

In orchestrator / multi-agent mode the sub-agent's scene narration is the
ask_user *question*, so it only lived in the ephemeral choice dialog and
the playthrough log never built up. `_echo_ask_user_to_transcript` mirrors
it into the transcript as a Narrator bubble — local only (the bridge gets
it via the explicit ask_user event), and de-duped against narration that
fast mode already streamed this turn.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

from neonrp.tui.app import NeonRPApp


def _fake_app(plain_chunks: list[str]):
    view = MagicMock()
    view._plain_chunks = list(plain_chunks)
    view._last_header_speaker_in_turn = None
    app = types.SimpleNamespace()
    app._collapse_ws = NeonRPApp._collapse_ws
    app.query_one = lambda *a, **k: view
    return app, view


def test_echoes_novel_narration_local_only() -> None:
    app, view = _fake_app(["### You\n\nhello\n"])
    NeonRPApp._echo_ask_user_to_transcript(app, "你走近柜台，老王放下茶壶。你想先聊什么？")
    view.add_named_assistant_message.assert_called_once()
    _, kwargs = view.add_named_assistant_message.call_args
    # Local transcript only — the bridge already gets the ask_user text.
    assert kwargs.get("mirror_to_bridge") is False


def test_skips_when_narration_already_streamed_this_turn() -> None:
    q = "你走近柜台，老王放下茶壶。你想先聊什么？"
    # Fast mode already streamed it into the transcript.
    app, view = _fake_app([f"### Narrator\n\n{q}\n"])
    NeonRPApp._echo_ask_user_to_transcript(app, q)
    view.add_named_assistant_message.assert_not_called()


def test_skips_empty_question() -> None:
    app, view = _fake_app([])
    NeonRPApp._echo_ask_user_to_transcript(app, "   ")
    view.add_named_assistant_message.assert_not_called()
