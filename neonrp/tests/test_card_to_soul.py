"""Tests for SillyTavern card → soul-library import (LLM-authored).

SOUL_HOME is monkeypatched onto a tmp dir so nothing touches ~/.worldlines.
The authoring LLM is a stub that returns a fixed ``{relpath: content}`` map —
we never hit the network / real provider here.
"""

import json

import pytest

from neonrp.core import souls
from neonrp.core.importers.card_to_soul import _SKILL_MD, import_card_to_library


class _StubLLM:
    """Satisfies the ``_LLMLike`` contract scaffold_soul expects: ``generate``
    returns a JSON string whose keys are ``"<subfolder>/<file>"``."""

    def __init__(self, files: dict) -> None:
        self._payload = json.dumps(files, ensure_ascii=False)

    def generate(self, system_prompt: str, user_prompt: str, tools=None) -> str:
        return self._payload


def _v2_card(name: str = "August", **data_overrides) -> dict:
    data = {
        "name": name,
        "description": "A test character with a rain-soaked past.",
        "personality": "curious, warm, stubborn",
        "scenario": "You meet in a rain-soaked market at dusk.",
        "first_mes": "Oh — hello there.",
        "tags": ["Adventure"],
    }
    data.update(data_overrides)
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


_AUTHORED = {
    "soul.md": "# Soul Charter — August\n\n## Core Presence\n\nWarm, curious, quietly stubborn.\n",
    "persona/core_traits.json": {
        "sid": "august",
        "personality_type": "curious and warm",
        "core_traits": [{"trait": "Curious", "intensity": 80, "description": "asks before assuming"}],
        "quirks": [],
        "fears": [],
        "pet_peeves": [],
    },
    "persona/values.json": {"sid": "august", "values": ["kindness first"]},
    "character/profile.json": {
        "sid": "august",
        "display_name": "August",
        "name_local": "",
        "role": "npc",
        "tags": ["adventure"],
        "summary": "A curious traveler.",
    },
    "background/origin.md": "Born on the road, raised by rain.\n",
}


def test_import_card_authors_rich_soul_via_injected_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(souls, "SOUL_HOME", tmp_path / "souls")
    card = tmp_path / "august.json"
    card.write_text(json.dumps(_v2_card()), encoding="utf-8")

    soul_dir = import_card_to_library(card, llm=_StubLLM(_AUTHORED))

    # Identity envelope + library provenance tag.
    meta = json.loads((soul_dir / "soul.json").read_text(encoding="utf-8"))
    assert meta["name"] == "August"
    assert "sillytavern" in meta["tags"]

    # The LLM-authored persona/character landed (non-empty, from the stub).
    core = json.loads((soul_dir / "persona" / "core_traits.json").read_text(encoding="utf-8"))
    assert core["personality_type"] == "curious and warm"
    assert core["core_traits"][0]["trait"] == "Curious"
    profile = json.loads((soul_dir / "character" / "profile.json").read_text(encoding="utf-8"))
    assert profile["display_name"] == "August"
    assert "Warm, curious" in (soul_dir / "soul.md").read_text(encoding="utf-8")

    # A file the model omitted is still seeded → structurally complete.
    assert (soul_dir / "character" / "stats.json").is_file()
    assert (soul_dir / "agents" / "manifest.json").is_file()

    # Shows up in the library listing.
    assert any(s.get("name") == "August" for s in souls.list_souls())


def test_import_card_missing_name_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(souls, "SOUL_HOME", tmp_path / "souls")
    bad = tmp_path / "bad.json"
    bad.write_text('{"data": {"description": "no name here"}}', encoding="utf-8")
    with pytest.raises(ValueError):
        import_card_to_library(bad, llm=_StubLLM({}))


def test_soul_card_authoring_skill_exists_and_nonempty():
    assert _SKILL_MD.is_file(), f"missing {_SKILL_MD}"
    body = _SKILL_MD.read_text(encoding="utf-8")
    assert len(body) > 400
    assert "soul-card-authoring" in body


def test_preset_resolves_to_usable_llm_config():
    """The card-import flow authors with the CHOSEN preset's LLM (a launcher has
    no in-game effective provider, and the default user config resolves to an
    unusable placeholder). Guard that a real preset → a usable provider config."""
    from neonrp.core.config import _parse_config, resolve_provider
    from neonrp.presets import build_config_dict

    pc = resolve_provider(_parse_config(build_config_dict("deepseek")))
    assert pc.provider != "stub"
    assert pc.model and pc.model != "asdf"
