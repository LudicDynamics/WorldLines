"""JSON-repair test suite — the deepseek quote-escaping problem.

deepseek (and LLMs generally) write world/soul JSON with malformed escaping, so
files used to land invalid on disk. `neonrp.core.json_repair` is the shared
write-boundary pipeline: heal the known malformations deterministically,
canonicalize on write, REJECT (with a precise parse error) what cannot be
repaired. This suite pins the 7 real failure-mode samples we measured — 6 are
repaired; the genuinely ambiguous one stays ``xfail`` and is instead covered by
the rejection path (garbage never lands silently).
"""

import json

import pytest

from neonrp.core.json_repair import JsonRepairError, loads_repaired, repair_json
from neonrp.core.skills import SkillRegistry


# (id, broken_json, key, expected_value) — a stable key that must survive repair.
_HANDLED = [
    # THE reported customer bug: unescaped inner quotes inside a value.
    ("unescaped_inner_quotes", '{"speech": "她说 "你好" 然后笑了", "id": "elena"}', "id", "elena"),
    # JS-style `"A" + prose + "B"` concatenation the model emits mid-value.
    ("js_concat_prose", '{"speech": "台词A" + （她转身） + "台词B", "id": "x"}', "id", "x"),
    # Raw newline (unescaped control char) inside a string value.
    ("raw_newline_in_string", '{"desc": "第一行\n第二行", "id": "loc1"}', "id", "loc1"),
    # Valid-but-escaped input must pass through untouched.
    ("valid_unicode_escape", '{"name": "caf\\u00e9", "ok": true}', "name", "café"),
    # Trailing comma before a closing brace/bracket.
    ("trailing_comma", '{"a": 1, "b": 2,}', "b", 2),
    # Curly/smart quotes used as JSON delimiters (structural positions).
    ("smart_quote_delimiters", "{“name”: “值”}", "name", "值"),
]

# Known gap — a value that ENDS on a quoted phrase (`…"别过来""`) is genuinely
# ambiguous: no algorithm can know where the string ends. The write boundary
# REJECTS these instead (see TestWriteBoundary) so they never land on disk.
_KNOWN_GAPS = [
    ("deeply_nested_quotes", '{"note": "他喊 "住手！" 又说 "别过来"", "k": 1}', "k", 1),
]


@pytest.mark.parametrize(
    "name,raw,key,expected", _HANDLED, ids=[c[0] for c in _HANDLED]
)
def test_repair_handles(name, raw, key, expected):
    obj = loads_repaired(raw)
    assert isinstance(obj, dict)
    assert obj[key] == expected


@pytest.mark.parametrize(
    "name,raw,key,expected", _KNOWN_GAPS, ids=[c[0] for c in _KNOWN_GAPS]
)
@pytest.mark.xfail(reason="genuinely ambiguous; write boundary rejects instead", strict=False)
def test_repair_known_gap(name, raw, key, expected):
    obj = loads_repaired(raw)
    assert isinstance(obj, dict)
    assert obj[key] == expected


def test_smart_quotes_inside_string_content_preserved():
    """Smart quotes / 「」 in VALUES are content, not delimiters — repair of an
    unrelated breakage (trailing comma) must keep them byte-for-byte."""
    raw = '{"speech": "她说“你好”，又喊「走吧」", "a": 1,}'
    obj = loads_repaired(raw)
    assert obj["speech"] == "她说“你好”，又喊「走吧」"
    assert obj["a"] == 1


def test_valid_input_is_not_rewritten_by_heuristics():
    """A parseable document never goes through the repair passes."""
    raw = '{"note": "quote \\" plus, comma}", "arr": [1, 2]}'
    assert loads_repaired(raw) == {"note": 'quote " plus, comma}', "arr": [1, 2]}


def test_repair_json_returns_canonical_serialization():
    out = repair_json('{"b":2,"a":"café",}')
    assert out == json.dumps({"b": 2, "a": "café"}, ensure_ascii=False, indent=2)
    # ensure_ascii=False: UTF-8 stays readable, no \uXXXX escapes.
    assert "café" in out


def test_unrepairable_raises_with_line_col_snippet():
    raw = '{"note": "他喊 "住手！" 又说 "别过来"", "k": 1}'
    with pytest.raises(JsonRepairError) as exc_info:
        loads_repaired(raw)
    msg = str(exc_info.value)
    assert "line 1" in msg
    assert "column" in msg
    assert "near:" in msg


class TestWriteBoundary:
    """write_file / edit_file: repairable .json lands repaired+canonical;
    unrepairable .json is rejected with a precise error and the file untouched."""

    def _registry(self, tmp_path):
        return SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

    def test_repairable_json_lands_canonical(self, tmp_path):
        registry = self._registry(tmp_path)
        result = registry.invoke(
            "write_file", {"path": "notes/data.json", "content": '{"a": 1, "b": 2,}'}
        )
        assert result.success is True
        on_disk = (tmp_path / "notes" / "data.json").read_text(encoding="utf-8")
        assert on_disk == json.dumps({"a": 1, "b": 2}, ensure_ascii=False, indent=2)

    def test_unescaped_quotes_repaired_on_write(self, tmp_path):
        """The customer bug end-to-end: deepseek's broken quoting is healed."""
        registry = self._registry(tmp_path)
        result = registry.invoke(
            "write_file",
            {"path": "notes/soul.json", "content": '{"speech": "她说 "你好" 然后笑了", "id": "elena"}'},
        )
        assert result.success is True
        data = json.loads((tmp_path / "notes" / "soul.json").read_text(encoding="utf-8"))
        assert data["id"] == "elena"

    def test_unrepairable_json_rejected_file_not_created(self, tmp_path):
        registry = self._registry(tmp_path)
        result = registry.invoke(
            "write_file",
            {"path": "notes/bad.json", "content": '{"note": "他喊 "住手！" 又说 "别过来"", "k": 1}'},
        )
        assert result.success is False
        assert "Rejected write" in result.error
        assert "line 1" in result.error  # precise parse position for the model
        assert not (tmp_path / "notes" / "bad.json").exists()

    def test_unrepairable_overwrite_leaves_existing_file_untouched(self, tmp_path):
        registry = self._registry(tmp_path)
        good = registry.invoke(
            "write_file", {"path": "notes/keep.json", "content": '{"v": 1}'}
        )
        assert good.success is True
        before = (tmp_path / "notes" / "keep.json").read_text(encoding="utf-8")

        bad = registry.invoke(
            "write_file", {"path": "notes/keep.json", "content": '{"v": "he said "no"" broken'}
        )
        assert bad.success is False
        assert (tmp_path / "notes" / "keep.json").read_text(encoding="utf-8") == before

    def test_edit_file_rejects_edit_that_breaks_json(self, tmp_path):
        registry = self._registry(tmp_path)
        registry.invoke(
            "write_file", {"path": "notes/cfg.json", "content": '{"name": "ok"}'}
        )
        result = registry.invoke(
            "edit_file",
            {
                "path": "notes/cfg.json",
                "old_text": '"ok"',
                "new_text": '"he said "no"" and {{{',
            },
        )
        assert result.success is False
        assert "Rejected write" in result.error
        # File untouched.
        data = json.loads((tmp_path / "notes" / "cfg.json").read_text(encoding="utf-8"))
        assert data == {"name": "ok"}

    def test_edit_file_repairs_and_canonicalizes(self, tmp_path):
        registry = self._registry(tmp_path)
        registry.invoke(
            "write_file", {"path": "notes/cfg.json", "content": '{"name": "ok", "n": 1}'}
        )
        # The canonical file body is indented; introduce a trailing comma via
        # the edit and verify the boundary repairs + re-canonicalizes it.
        result = registry.invoke(
            "edit_file",
            {"path": "notes/cfg.json", "old_text": '"n": 1', "new_text": '"n": 2,'},
        )
        assert result.success is True
        on_disk = (tmp_path / "notes" / "cfg.json").read_text(encoding="utf-8")
        assert on_disk == json.dumps({"name": "ok", "n": 2}, ensure_ascii=False, indent=2)

    def test_non_json_files_never_go_through_repair(self, tmp_path):
        registry = self._registry(tmp_path)
        prose = 'He said "wait" — {not json, at all,}'
        result = registry.invoke(
            "write_file", {"path": "notes/prose.md", "content": prose}
        )
        assert result.success is True
        assert (tmp_path / "notes" / "prose.md").read_text(encoding="utf-8") == prose


class _SeqLLM:
    """Stub adapter: returns queued replies in order, records every call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, system_prompt, user_prompt, tools=None):
        self.calls.append((system_prompt, user_prompt))
        return self.replies.pop(0)


class TestLlmLastResort:
    """`repair_json_with_llm` — ONE focused request for what the deterministic
    passes can't heal; any failure re-raises the original JsonRepairError."""

    # The genuinely ambiguous sample (value ENDS on a quoted phrase).
    BROKEN = '{"note": "他喊 "住手！" 又说 "别过来"", "k": 1}'
    FIXED = '{"note": "他喊 「住手！」 又说 「别过来」", "k": 1}'

    def test_heals_the_deterministic_gap(self):
        from neonrp.core.json_repair import repair_json_with_llm

        llm = _SeqLLM([self.FIXED])
        obj = repair_json_with_llm(self.BROKEN, llm)
        assert obj["k"] == 1
        assert "住手" in obj["note"] and "别过来" in obj["note"]  # content preserved
        assert len(llm.calls) == 1
        # The request carries the parse error + the broken document.
        _system, user = llm.calls[0]
        assert "invalid JSON" in user
        assert self.BROKEN in user

    def test_garbage_reply_raises_original_error_after_one_call(self):
        from neonrp.core.json_repair import JsonRepairError, repair_json_with_llm

        llm = _SeqLLM(["sorry, I cannot fix this {{{"])
        with pytest.raises(JsonRepairError) as exc_info:
            repair_json_with_llm(self.BROKEN, llm)
        assert "line 1" in str(exc_info.value)  # the ORIGINAL deterministic error
        assert len(llm.calls) == 1  # exactly one request — no retries

    def test_code_fenced_reply_is_unwrapped(self):
        from neonrp.core.json_repair import repair_json_with_llm

        llm = _SeqLLM([f"```json\n{self.FIXED}\n```"])
        obj = repair_json_with_llm(self.BROKEN, llm)
        assert obj["k"] == 1

    def test_scaffold_soul_escalates_to_llm_repair(self, tmp_path):
        """Authoring reply is broken beyond deterministic repair → scaffold_soul
        issues ONE repair request on the same adapter and the soul lands
        populated with the LLM's content, not hollow seeds."""
        from neonrp.core.soul_authoring import scaffold_soul

        broken_payload = (
            '{"soul.md": "他喊 "住手！" 又说 "别过来"", '
            '"persona/core_traits.json": {"sid": "t9", "personality_type": "brave"}}'
        )
        fixed_payload = json.dumps(
            {
                "soul.md": "# Soul Charter — t9\n他喊「住手！」又说「别过来」",
                "persona/core_traits.json": {"sid": "t9", "personality_type": "brave"},
            },
            ensure_ascii=False,
        )
        llm = _SeqLLM([broken_payload, fixed_payload])
        soul_dir = tmp_path / "t9-sit90001"
        scaffold_soul(
            soul_dir,
            description="a brave test soul",
            sid="t9",
            agent_template="minimal",
            llm=llm,
        )
        assert len(llm.calls) == 2  # authoring + exactly one repair
        traits = json.loads(
            (soul_dir / "persona" / "core_traits.json").read_text(encoding="utf-8")
        )
        assert traits["personality_type"] == "brave"  # LLM content, not a seed
        assert "住手" in (soul_dir / "soul.md").read_text(encoding="utf-8")
