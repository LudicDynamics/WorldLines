"""Build mode is the authoring mode: a restrictive agent.json `tools`
allowlist (written for play-time routing, e.g. the `default` router
narrator) must NOT strip the write/import tools in build mode, or
world/card-import skills can't run. Play mode keeps the allowlist strict.
"""

from __future__ import annotations

from neonrp.core.conversation import (
    _BUILD_WRITE_TOOLS,
    _filter_tool_schemas_by_agent_config,
)


def _schemas(*names: str) -> list[dict[str, str]]:
    return [{"name": n} for n in names]


# A `default`-narrator-style allowlist: routing/read tools, no writers.
_RESTRICTIVE = {"tools": ["read_file", "find", "list_entities", "task", "Skill"]}


def test_build_mode_keeps_authoring_tools_despite_restrictive_allowlist() -> None:
    schemas = _schemas(
        "read_file", "find", "task", "Skill",
        "write_file", "import_sillytavern_card", "ensure_playable_scaffold",
    )
    out = {s["name"] for s in _filter_tool_schemas_by_agent_config(schemas, _RESTRICTIVE, mode="build")}
    # The bug: these used to be filtered out, so the import skill's
    # import_sillytavern_card call was rejected as "not enabled".
    assert _BUILD_WRITE_TOOLS <= out | _BUILD_WRITE_TOOLS  # constant sanity
    assert {"import_sillytavern_card", "write_file", "ensure_playable_scaffold"} <= out
    assert "read_file" in out  # explicitly-listed tools still present


def test_play_mode_still_strips_unlisted_write_tools() -> None:
    schemas = _schemas("read_file", "write_file", "import_sillytavern_card")
    out = {s["name"] for s in _filter_tool_schemas_by_agent_config(schemas, _RESTRICTIVE, mode="play")}
    # Play mode is unchanged: a restrictive agent does NOT get write/import.
    assert out == {"read_file"}


def test_no_allowlist_exposes_everything_in_any_mode() -> None:
    schemas = _schemas("read_file", "write_file", "import_sillytavern_card")
    for mode in ("build", "play"):
        out = {s["name"] for s in _filter_tool_schemas_by_agent_config(schemas, {}, mode=mode)}
        assert out == {"read_file", "write_file", "import_sillytavern_card"}
