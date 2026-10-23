"""Tests for SillyTavern import (M3-T6)."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.importers.sillytavern import (
    name_to_id,
    resolve_id_conflict,
    parse_card,
    build_entity,
    _build_summary,
    _filter_tags,
)


# ---------------------------------------------------------------------------
# Fixtures: minimal card payloads
# ---------------------------------------------------------------------------


def _v2_card(name: str = "August", **overrides) -> dict:
    """Build a minimal v2 SillyTavern card."""
    data = {
        "name": name,
        "description": "A test character.",
        "personality": "",
        "first_mes": "Hello.",
        "scenario": "",
        "tags": ["Noble", "Male"],
        "creator": "tester",
        **overrides,
    }
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


def _v1_card(name: str = "Hero", **overrides) -> dict:
    """Build a minimal v1 SillyTavern card (flat)."""
    return {
        "name": name,
        "description": "A simple hero.",
        "personality": "brave",
        "first_mes": "Greetings!",
        "scenario": "",
        "tags": [],
        "creator": "",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Unit tests: name_to_id
# ---------------------------------------------------------------------------


class TestNameToId:
    def test_simple_name(self):
        assert name_to_id("August") == "august"

    def test_multi_word(self):
        assert name_to_id("August Babenberg") == "august-babenberg"

    def test_special_characters(self):
        assert name_to_id("Dr. Müller (Jr.)") == "dr-m-ller-jr"

    def test_leading_trailing_hyphens_stripped(self):
        assert name_to_id("--test--") == "test"

    def test_empty_name_returns_unnamed(self):
        assert name_to_id("") == "unnamed"

    def test_numbers_preserved(self):
        assert name_to_id("Agent 007") == "agent-007"

    def test_already_kebab(self):
        assert name_to_id("already-kebab") == "already-kebab"

    def test_non_ascii_name_falls_back_to_stable_ascii_hash(self):
        result = name_to_id("天罗修仙界")
        assert result.startswith("entity-")
        assert result == name_to_id("天罗修仙界")


# ---------------------------------------------------------------------------
# Unit tests: resolve_id_conflict
# ---------------------------------------------------------------------------


class TestResolveIdConflict:
    def test_no_conflict(self):
        assert resolve_id_conflict("hero", set()) == "hero"

    def test_single_conflict(self):
        assert resolve_id_conflict("hero", {"hero"}) == "hero-2"

    def test_multiple_conflicts(self):
        assert resolve_id_conflict("hero", {"hero", "hero-2", "hero-3"}) == "hero-4"


# ---------------------------------------------------------------------------
# Unit tests: parse_card
# ---------------------------------------------------------------------------


class TestParseCard:
    def test_v2_card(self):
        card = _v2_card()
        parsed = parse_card(card)
        assert parsed["name"] == "August"
        assert parsed["tags"] == ["Noble", "Male"]
        assert parsed["raw"] is card

    def test_v1_card(self):
        card = _v1_card()
        parsed = parse_card(card)
        assert parsed["name"] == "Hero"
        assert parsed["personality"] == "brave"
        assert parsed["raw"] is card

    def test_missing_name_raises(self):
        try:
            parse_card({"data": {"description": "no name"}})
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "name" in str(e).lower()

    def test_empty_name_raises(self):
        try:
            parse_card({"name": "  "})
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "name" in str(e).lower()

    def test_character_book_preserved(self):
        book = {"entries": [{"name": "Lore"}]}
        card = _v2_card(character_book=book)
        parsed = parse_card(card)
        assert parsed["character_book"] == book

    def test_deterministic(self):
        """Same input produces same output."""
        card = _v2_card()
        p1 = parse_card(card)
        p2 = parse_card(card)
        assert p1["name"] == p2["name"]
        assert p1["tags"] == p2["tags"]


# ---------------------------------------------------------------------------
# Unit tests: build_entity
# ---------------------------------------------------------------------------


class TestBuildEntity:
    def test_basic_entity(self):
        parsed = parse_card(_v2_card())
        entity = build_entity(parsed)
        assert entity["id"] == "august"
        assert entity["kind"] == "character"
        assert entity["name"] == "August"
        assert entity["meta"]["source"] == "sillytavern"
        assert entity["meta"]["raw"]["spec"] == "chara_card_v2"

    def test_explicit_id(self):
        parsed = parse_card(_v2_card())
        entity = build_entity(parsed, entity_id="custom-id")
        assert entity["id"] == "custom-id"

    def test_invalid_explicit_id_raises(self):
        parsed = parse_card(_v2_card())
        try:
            build_entity(parsed, entity_id="INVALID ID!")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "invalid" in str(e).lower()

    def test_id_conflict_resolution(self):
        parsed = parse_card(_v2_card())
        entity = build_entity(parsed, existing_ids={"august"})
        assert entity["id"] == "august-2"

    def test_tags_normalised(self):
        parsed = parse_card(_v2_card(tags=["Noble", "noble", "Male"]))
        entity = build_entity(parsed)
        assert "noble" in entity["tags"]
        assert "male" in entity["tags"]
        # No duplicates
        assert entity["tags"].count("noble") == 1

    def test_meta_raw_contains_full_payload(self):
        card = _v2_card()
        parsed = parse_card(card)
        entity = build_entity(parsed)
        assert entity["meta"]["raw"] == card

    def test_creator_in_meta(self):
        parsed = parse_card(_v2_card(creator="TestCreator"))
        entity = build_entity(parsed)
        assert entity["meta"]["creator"] == "TestCreator"

    def test_no_creator_when_empty(self):
        parsed = parse_card(_v2_card(creator=""))
        entity = build_entity(parsed)
        assert "creator" not in entity["meta"]

    def test_deterministic(self):
        """Same input produces same output."""
        card = _v2_card()
        e1 = build_entity(parse_card(card))
        e2 = build_entity(parse_card(card))
        assert json.dumps(e1, sort_keys=True) == json.dumps(e2, sort_keys=True)


# ---------------------------------------------------------------------------
# Unit tests: _build_summary / _filter_tags
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_personality_preferred(self):
        parsed = parse_card(_v1_card(personality="brave and bold"))
        assert _build_summary(parsed) == "brave and bold"

    def test_description_fallback_short(self):
        parsed = parse_card(_v2_card(description="Short desc."))
        assert _build_summary(parsed) == "Short desc."

    def test_description_fallback_long_truncated(self):
        long_desc = "A" * 200 + ". " + "B" * 200
        parsed = parse_card(_v2_card(description=long_desc))
        summary = _build_summary(parsed)
        assert len(summary) <= 303  # 300 + "..."
        assert summary.endswith(".")  # truncated at sentence

    def test_empty_description(self):
        parsed = parse_card(_v2_card(description="", personality=""))
        assert _build_summary(parsed) == ""


class TestFilterTags:
    def test_normalise_lowercase(self):
        assert _filter_tags(["Noble", "MALE"]) == ["noble", "male"]

    def test_deduplicate(self):
        assert _filter_tags(["noble", "Noble", "NOBLE"]) == ["noble"]

    def test_skip_empty(self):
        assert _filter_tags(["", "  ", "valid"]) == ["valid"]

    def test_preserve_order(self):
        assert _filter_tags(["Beta", "Alpha"]) == ["beta", "alpha"]

    def test_non_string_ignored(self):
        assert _filter_tags([123, None, "ok"]) == ["ok"]


# ---------------------------------------------------------------------------
# Integration tests: CLI import command
# ---------------------------------------------------------------------------


class TestImportSillyTavernCardCLI:
    def test_import_v2_card(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            # Write test card
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path)])

            assert result.exit_code == 0, result.output
            assert "august" in result.output.lower()
            assert Path("game/character/august.json").exists()

            # Verify entity content
            entity = json.loads(Path("game/character/august.json").read_text(encoding="utf-8"))
            assert entity["id"] == "august"
            assert entity["kind"] == "character"
            assert entity["meta"]["source"] == "sillytavern"

    def test_import_v1_card(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v1_card()), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path)])

            assert result.exit_code == 0, result.output
            assert Path("game/character/hero.json").exists()

    def test_import_chinese_name_uses_stable_ascii_fallback_id(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card(name="天罗修仙界")), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path), "--json"])

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["id"].startswith("entity-")
            assert Path(f"game/character/{data['id']}.json").exists()

    def test_import_with_explicit_id(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path), "--id", "my-august"])

            assert result.exit_code == 0, result.output
            assert Path("game/character/my-august.json").exists()

    def test_import_json_output(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path), "--json"])

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["success"] is True
            assert data["id"] == "august"
            assert data["kind"] == "character"
            assert data["path"] == "character/august.json"

    def test_import_id_conflict_resolved(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            # Import twice
            runner.invoke(cli, ["import", "sillytavern-card", str(card_path)])
            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path), "--json"])

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["id"] == "august-2"
            assert Path("game/character/august.json").exists()
            assert Path("game/character/august-2.json").exists()

    def test_import_invalid_json_exits_1(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            bad = Path("bad.json")
            bad.write_text("not valid json", encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(bad)])

            assert result.exit_code == 1

    def test_import_invalid_card_exits_1(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps({"data": {"no_name": True}}), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path)])

            assert result.exit_code == 1

    def test_import_invalid_card_json_output(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps({"data": {"no_name": True}}), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path), "--json"])

            assert result.exit_code == 1
            data = json.loads(result.output)
            assert data["success"] is False
            assert "error" in data

    def test_imported_entity_passes_validation(self, tmp_path: Path):
        """Imported entity should pass neonrp validate."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            runner.invoke(cli, ["import", "sillytavern-card", str(card_path)])
            result = runner.invoke(cli, ["validate"])

            assert result.exit_code == 0, result.output

    def test_imported_entity_indexable(self, tmp_path: Path):
        """Imported entity should be indexable by neonrp index build."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            runner.invoke(cli, ["import", "sillytavern-card", str(card_path)])
            result = runner.invoke(cli, ["index", "build"])

            assert result.exit_code == 0, result.output
            # Verify indexed
            find_result = runner.invoke(cli, ["find", "--kind", "character"])
            assert "august" in find_result.output.lower()

    def test_import_invalid_explicit_id_exits_1(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            card_path = Path("card.json")
            card_path.write_text(json.dumps(_v2_card()), encoding="utf-8")

            result = runner.invoke(cli, ["import", "sillytavern-card", str(card_path), "--id", "INVALID!"])

            assert result.exit_code == 1

