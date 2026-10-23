from __future__ import annotations

from neonrp.core.soul_result import parse_soul_turn_report


def test_parse_valid_soul_turn_report() -> None:
    report = parse_soul_turn_report(
        """
        {
          "state": "completed",
          "confidence": 0.82,
          "urgency": 0.4,
          "intended_action": "step between Elena and the door",
          "speech": "Stay behind me.",
          "inner_voice": "The hallway smells wrong.",
          "memory_delta": "The door made her afraid.",
          "needs_world_decision": true
        }
        """
    )

    assert report.state == "completed"
    assert report.confidence == 0.82
    assert report.urgency == 0.4
    assert report.needs_world_decision is True
    assert "Stay behind me" in report.digest_line("Elena")


def test_player_soul_digest_marks_avatar_suggestions_non_authoritative() -> None:
    report = parse_soul_turn_report(
        """
        {
          "state": "completed",
          "confidence": 0.7,
          "urgency": 0.2,
          "intended_action": "go to the inn",
          "speech": "Any rooms?",
          "inner_voice": "The fog makes my skin crawl.",
          "memory_delta": "Stone Ford feels damp and unfamiliar.",
          "needs_world_decision": false
        }
        """
    )

    digest = report.digest_line("Elena", role="player")

    assert "role=player" in digest
    assert "human_player_sovereignty=true" in digest
    assert "avatar_action_suggestion=go to the inn" in digest
    assert "avatar_speech_suggestion=Any rooms?" in digest
    assert "action=go to the inn" not in digest
    assert "speech=Any rooms?" not in digest


def test_player_soul_preview_does_not_prefer_intended_action() -> None:
    report = parse_soul_turn_report(
        '{"state":"completed","confidence":1,"urgency":0,'
        '"intended_action":"go to the inn",'
        '"inner_voice":"The fog makes my skin crawl."}'
    )

    assert report.preview(role="player") == "The fog makes my skin crawl."
    assert report.preview(role="npc") == "The fog makes my skin crawl."


def test_parse_fenced_json_report() -> None:
    report = parse_soul_turn_report(
        'voice before\n```json\n{"state":"completed","confidence":1,"urgency":0,"speech":"Yes."}\n```'
    )

    assert report.is_structured is True
    assert report.speech == "Yes."


def test_malformed_report_degrades_and_preserves_raw_text() -> None:
    report = parse_soul_turn_report("I am only prose.")

    assert report.state == "degraded"
    assert report.is_structured is False
    assert "malformed" in report.parse_error
    assert report.raw_text == "I am only prose."


def test_repair_string_concatenation_recovers_report() -> None:
    # A chatty soul broke its `speech` value with JS-style concatenation +
    # bare prose between quoted segments (the real deepseek failure that sent
    # rowan to the degraded path). The repair pass must recover it.
    text = (
        '```json\n{"state":"completed","confidence":0.8,"urgency":0.3,'
        '"speech":"好问题。" + 目光扫过她的背包，"我看你这包不简单。",'
        '"moved_to":"main_street"}\n```'
    )
    report = parse_soul_turn_report(text)

    assert report.parse_error == ""
    assert report.is_structured is True
    assert report.moved_to == "main_street"
    assert "好问题" in report.speech and "我看你这包不简单" in report.speech


def test_repair_unescaped_newline_in_string_recovers_report() -> None:
    text = '{"state":"completed","confidence":1,"urgency":0,"speech":"line one\nline two"}'
    report = parse_soul_turn_report(text)

    assert report.parse_error == ""
    assert report.speech == "line one\nline two"


def test_invalid_confidence_degrades() -> None:
    report = parse_soul_turn_report(
        '{"state":"completed","confidence":2,"urgency":0.2,"speech":"Too sure."}'
    )

    assert report.state == "degraded"
    assert "confidence" in report.parse_error


def test_failed_soul_turn_degrades_even_with_valid_text() -> None:
    report = parse_soul_turn_report(
        '{"state":"completed","confidence":1,"urgency":0}',
        success=False,
    )

    assert report.state == "degraded"
    assert report.parse_error == "soul turn failed"


def test_moved_to_parses_and_appears_in_digest() -> None:
    report = parse_soul_turn_report(
        '{"state":"completed","confidence":0.7,"urgency":0.2,'
        '"intended_action":"去旅店","moved_to":"inn"}'
    )

    assert report.moved_to == "inn"
    assert "moved_to=inn" in report.digest_line("Elena")


def test_moved_to_defaults_empty_when_absent() -> None:
    report = parse_soul_turn_report(
        '{"state":"completed","confidence":0.5,"urgency":0.1}'
    )

    assert report.moved_to == ""
    assert "moved_to" not in report.digest_line("Elena")


def test_candidates_parse_and_normalize() -> None:
    report = parse_soul_turn_report(
        '{"state":"completed","confidence":0.7,"urgency":0.2,'
        '"intended_action":"算了不等了，现在就去探磨坊","moved_to":"mill",'
        '"candidates":['
        '  {"action":"继续追问工钱","fit":0.4},'
        '  {"action":"在公会门口等开门","fit":0.5},'
        '  {"action":"回旅店喝汤","fit":0.3},'
        '  {"action":"算了不等了，现在就去探磨坊","fit":0.8}'
        ']}'
    )
    assert len(report.candidates) == 4
    # a well-formed soul commits to the highest-fit candidate (self-selected);
    # the parser reads both fields as-is, it does not enforce the equality.
    best = max(report.candidates, key=lambda c: c["fit"])
    assert best["action"] == "算了不等了，现在就去探磨坊"
    assert report.intended_action == best["action"]
    assert report.candidates[0] == {"action": "继续追问工钱", "fit": 0.4}


def test_candidates_absent_defaults_empty_and_malformed_dropped() -> None:
    r1 = parse_soul_turn_report(
        '{"state":"completed","confidence":0.5,"urgency":0.1}'
    )
    assert r1.candidates == ()
    # malformed entries (non-dict / no action) are dropped, never raise
    r2 = parse_soul_turn_report(
        '{"state":"completed","confidence":0.5,"urgency":0.1,'
        '"candidates":["bad", {"fit":0.9}, {"action":"ok"}]}'
    )
    assert r2.candidates == ({"action": "ok", "fit": 0.0},)


def test_preview_never_leaks_raw_json() -> None:
    """WOR-26: malformed soul JSON must not dump the blob into the UI."""
    # Malformed (trailing junk) but carries a usable voice → salvage it.
    r = parse_soul_turn_report(
        '{"state":"completed","confidence":0.7,"speech":"我记得你。"} oops'
    )
    assert not r.is_structured
    p = r.preview()
    assert p == "我记得你。"
    assert "{" not in p and "state" not in p

    # Malformed with no human voice → short error, never the JSON.
    r2 = parse_soul_turn_report('{"state":"x","n":1,')
    p2 = r2.preview()
    assert "{" not in p2 and '"n"' not in p2

    # Plain prose (not JSON) is legitimate RP and passes through.
    r3 = parse_soul_turn_report("她沉默地点了点头。")
    assert r3.preview() == "她沉默地点了点头。"
