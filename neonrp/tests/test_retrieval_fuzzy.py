"""Tests for fuzzy matching in retrieval module."""

import json
from pathlib import Path

import pytest

from neonrp.core.manifest import EntityRecord
from neonrp.core.retrieval import (
    _compute_score,
    _fuzzy_field_score,
    _fuzzy_token_score,
    _levenshtein,
    _tokenize,
    retrieve_context,
)


# ---------------------------------------------------------------------------
# _levenshtein
# ---------------------------------------------------------------------------

class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("hello", "hello") == 0

    def test_empty_strings(self):
        assert _levenshtein("", "") == 0

    def test_one_empty(self):
        assert _levenshtein("abc", "") == 3
        assert _levenshtein("", "abc") == 3

    def test_single_substitution(self):
        assert _levenshtein("cat", "bat") == 1

    def test_single_insertion(self):
        assert _levenshtein("cat", "cats") == 1

    def test_single_deletion(self):
        assert _levenshtein("cats", "cat") == 1

    def test_two_edits(self):
        # "rouge" -> "rogue" = 1 transposition, but Levenshtein = 2 (del + ins)
        assert _levenshtein("rouge", "rogue") == 2

    def test_completely_different(self):
        assert _levenshtein("abc", "xyz") == 3

    def test_symmetric(self):
        assert _levenshtein("abc", "adc") == _levenshtein("adc", "abc")


# ---------------------------------------------------------------------------
# _fuzzy_token_score
# ---------------------------------------------------------------------------

class TestFuzzyTokenScore:
    def test_exact_match(self):
        assert _fuzzy_token_score("dragon", {"dragon", "knight", "wizard"}) == 1.0

    def test_no_match(self):
        assert _fuzzy_token_score("dragon", {"knight", "wizard"}) == 0.0

    def test_empty_targets(self):
        assert _fuzzy_token_score("dragon", set()) == 0.0

    def test_substring_query_in_target(self):
        # "dragon" is a substring of "dragonborn"
        score = _fuzzy_token_score("dragon", {"dragonborn", "wizard"})
        assert score == pytest.approx(0.7)

    def test_substring_target_in_query(self):
        # "born" is a substring of query "dragonborn"
        score = _fuzzy_token_score("dragonborn", {"born", "wizard"})
        assert score == pytest.approx(0.7)

    def test_near_miss_levenshtein(self):
        # "rouge" vs "rogue" — distance 2, max_len 5
        score = _fuzzy_token_score("rouge", {"rogue"})
        assert score == pytest.approx(1.0 - 2 / 5)

    def test_short_tokens_skip_fuzzy(self):
        # "at" vs "ax" — both len=2, below MIN_TOKEN_LEN_FOR_FUZZY=3
        # no substring, no exact match, and fuzzy is skipped for short tokens
        assert _fuzzy_token_score("at", {"ax"}) == 0.0

    def test_prefers_exact_over_substring(self):
        # "fire" exact match should beat "fireball" substring
        score = _fuzzy_token_score("fire", {"fire", "fireball"})
        assert score == 1.0


# ---------------------------------------------------------------------------
# _fuzzy_field_score
# ---------------------------------------------------------------------------

class TestFuzzyFieldScore:
    def test_all_exact(self):
        assert _fuzzy_field_score({"dragon", "king"}, {"dragon", "king", "realm"}) == 1.0

    def test_partial_match(self):
        # "dragon" exact, "prince" no match → avg = 0.5
        score = _fuzzy_field_score({"dragon", "prince"}, {"dragon", "king"})
        assert score == pytest.approx(0.5)

    def test_empty_query(self):
        assert _fuzzy_field_score(set(), {"dragon"}) == 0.0

    def test_empty_field(self):
        assert _fuzzy_field_score({"dragon"}, set()) == 0.0


# ---------------------------------------------------------------------------
# _compute_score with fuzzy matching
# ---------------------------------------------------------------------------

class TestComputeScore:
    @pytest.fixture
    def tmp_entity_dir(self, tmp_path):
        """Create a temporary entity directory with a JSON file."""
        entity_dir = tmp_path / "game" / "character"
        entity_dir.mkdir(parents=True)
        entity_file = entity_dir / "dragon_king.json"
        entity_file.write_text(json.dumps({
            "id": "dragon_king",
            "kind": "character",
            "name": "The Dragon King",
            "tags": ["dragon", "royalty", "fire"],
            "summary": "A powerful dragon who rules the volcanic realm.",
        }), encoding="utf-8")
        return tmp_path, entity_file

    def _make_record(self, name="The Dragon King", tags=None, summary=None,
                     path="game/character/dragon_king.json"):
        return EntityRecord(
            id="dragon_king",
            kind="character",
            name=name,
            tags=tags or ["dragon", "royalty", "fire"],
            summary=summary or "A powerful dragon who rules the volcanic realm.",
            path=path,
            mtime=0.0,
            hash="abc123",
        )

    def test_exact_tag_match(self, tmp_entity_dir):
        root, _ = tmp_entity_dir
        record = self._make_record()
        score = _compute_score(record, _tokenize("dragon"), root)
        assert score > 0.3  # should score well on tags + name + summary + content

    def test_fuzzy_matches_typo(self, tmp_entity_dir):
        root, _ = tmp_entity_dir
        record = self._make_record()
        # "dargon" is 2 edits from "dragon" → should get fuzzy score > 0
        score = _compute_score(record, _tokenize("dargon"), root)
        assert score > 0.0

    def test_substring_match(self, tmp_entity_dir):
        root, _ = tmp_entity_dir
        record = self._make_record(tags=["dragonborn", "warrior"])
        # "dragon" is substring of "dragonborn" tag
        score = _compute_score(record, _tokenize("dragon"), root)
        assert score > 0.0

    def test_no_match(self, tmp_entity_dir):
        root, _ = tmp_entity_dir
        record = self._make_record()
        score = _compute_score(record, _tokenize("unicorn"), root)
        # "unicorn" has no fuzzy match to dragon/royalty/fire
        assert score == 0.0

    def test_exact_scores_higher_than_fuzzy(self, tmp_entity_dir):
        root, _ = tmp_entity_dir
        record = self._make_record()
        exact_score = _compute_score(record, _tokenize("dragon"), root)
        fuzzy_score = _compute_score(record, _tokenize("dargon"), root)
        assert exact_score > fuzzy_score


# ---------------------------------------------------------------------------
# retrieve_context integration
# ---------------------------------------------------------------------------

class TestRetrieveContextFuzzy:
    """Integration tests that verify fuzzy matching works end-to-end."""

    @pytest.fixture
    def project_with_entities(self, tmp_path):
        """Set up a minimal NeonRP project with entities."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()

        # Minimal manifest
        manifest = {
            "version": "0.3",
            "created": "2025-01-01T00:00:00+00:00",
            "current_branch": "main",
            "branches": {"main": {"head_event": -1, "created": "2025-01-01T00:00:00+00:00", "kind": "main"}},
            "entities": {},
        }

        # Create world entities
        game_dir = tmp_path / "game"
        entities = [
            {
                "id": "dragon_king",
                "kind": "character",
                "name": "The Dragonborn King",
                "tags": ["dragon", "royalty"],
                "summary": "A half-dragon ruler of the northern wastes.",
            },
            {
                "id": "rogue_thief",
                "kind": "character",
                "name": "Rogue",
                "tags": ["thief", "stealth"],
                "summary": "A cunning rogue who lurks in shadows.",
            },
            {
                "id": "fire_temple",
                "kind": "location",
                "name": "Temple of Fire",
                "tags": ["fire", "sacred"],
                "summary": "An ancient temple dedicated to the fire god.",
            },
        ]

        for entity in entities:
            kind_dir = game_dir / entity["kind"]
            kind_dir.mkdir(parents=True, exist_ok=True)
            entity_path = kind_dir / f"{entity['id']}.json"
            entity_path.write_text(json.dumps(entity), encoding="utf-8")

        # Write manifest
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        return tmp_path

    def test_exact_query(self, project_with_entities):
        results = retrieve_context(project_with_entities, "dragon")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "The Dragonborn King" in names

    def test_typo_query_finds_entity(self, project_with_entities):
        results = retrieve_context(project_with_entities, "rouge")
        # "rouge" is 2 edits from "rogue" → should find the rogue
        rogue_found = any(r["id"] == "rogue_thief" for r in results)
        assert rogue_found, f"Expected rogue_thief in results, got: {[r['id'] for r in results]}"

    def test_substring_query(self, project_with_entities):
        results = retrieve_context(project_with_entities, "dragon")
        # "dragon" is substring of "dragonborn" in the name
        dragon_found = any(r["id"] == "dragon_king" for r in results)
        assert dragon_found

