"""Tests for skills module."""

import base64
import json
import struct
from pathlib import Path

from neonrp.core.skills import (
    SkillRegistry,
    get_skill_schemas,
    SKILL_SCHEMAS,
)


def _build_png_with_chara(card_json: dict) -> bytes:
    """Build a minimal valid PNG with a SillyTavern chara chunk."""
    import zlib

    json_bytes = json.dumps(card_json).encode("utf-8")
    base64_bytes = base64.b64encode(json_bytes)
    text_data = b"chara\x00" + base64_bytes

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat_data = b"\x08\xd7\x63\x00\x00\x00\x01\x00\x01"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr_data)
        + _chunk(b"tEXt", text_data)
        + _chunk(b"IDAT", idat_data)
        + _chunk(b"IEND", b"")
    )


class TestSkillSchemas:
    """Tests for skill JSON schemas."""

    def test_all_skills_have_schemas(self):
        """All built-in skills should have JSON schemas."""
        expected_skills = ["read_context", "find", "read_file", "list_entities", "import_sillytavern_card", "ensure_playable_scaffold"]
        for skill in expected_skills:
            assert skill in SKILL_SCHEMAS

    def test_get_skill_schemas(self):
        """Should return list of all skill schemas."""
        schemas = get_skill_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) >= 4
        for schema in schemas:
            assert "name" in schema
            assert "parameters" in schema

    def test_get_skill_schemas_without_resolve_action(self):
        """Should hide resolve_action schema when disabled."""
        schemas = get_skill_schemas(include_resolve_action=False)
        names = {schema["name"] for schema in schemas}
        assert "resolve_action" not in names

    def test_get_skill_schemas_with_root_injects_dynamic_kind_enum(self, tmp_path: Path):
        """find/list_entities kind filter should be constrained to indexed kinds for this project."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (tmp_path / "game" / "npc").mkdir(parents=True)
        (tmp_path / "game" / "town").mkdir(parents=True)
        (tmp_path / "game" / "npc" / "merchant.json").write_text(
            json.dumps({"id": "merchant", "kind": "npc", "name": "Merchant"}),
            encoding="utf-8",
        )
        (tmp_path / "game" / "town" / "start-town.json").write_text(
            json.dumps({"id": "start-town", "kind": "town", "name": "Start Town"}),
            encoding="utf-8",
        )
        manifest = {
            "version": "0.3",
            "current_branch": "main",
            "branches": {"main": {"head_event": -1}},
            "entities": {
                "npc:merchant": {
                    "id": "merchant",
                    "kind": "npc",
                    "name": "Merchant",
                    "path": "game/npc/merchant.json",
                    "mtime": 1.0,
                    "hash": "sha256:a",
                },
                "town:start-town": {
                    "id": "start-town",
                    "kind": "town",
                    "name": "Start Town",
                    "path": "game/town/start-town.json",
                    "mtime": 1.0,
                    "hash": "sha256:b",
                },
            },
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        schemas = get_skill_schemas(root=tmp_path)
        by_name = {schema["name"]: schema for schema in schemas}
        find_kind = by_name["find"]["parameters"]["properties"]["kind"]
        list_kind = by_name["list_entities"]["parameters"]["properties"]["kind"]

        assert find_kind["enum"] == ["npc", "town"]
        assert list_kind["enum"] == ["npc", "town"]

    def test_get_skill_schemas_without_root_does_not_pin_kind_enum(self):
        """Without project context, kind remains open-ended for generic projects."""
        schemas = get_skill_schemas(root=None)
        by_name = {schema["name"]: schema for schema in schemas}
        assert "enum" not in by_name["find"]["parameters"]["properties"]["kind"]
        assert "enum" not in by_name["list_entities"]["parameters"]["properties"]["kind"]


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    def setup_method(self, method):
        """Set up test fixtures."""
        self.read_globs = ["game/**", ".neonrp/manifest.json"]
        self.deny_globs = [".neonrp/secrets/**", "agents/**"]

    def test_invoke_unknown_skill(self, tmp_path: Path):
        """Should return error for unknown skill."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=self.read_globs,
            deny_globs=self.deny_globs,
        )

        result = registry.invoke("nonexistent_skill", {})
        assert not result.success
        assert "unknown" in result.error.lower()

    def test_read_file_allowed(self, tmp_path: Path):
        """Should read file when allowed by permissions."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        test_file = game_dir / "test.json"
        test_file.write_text('{"id": "test"}', encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=self.read_globs,
            deny_globs=self.deny_globs,
        )

        result = registry.invoke("read_file", {"path": "game/test.json"})
        assert result.success
        assert result.data["content"] == '{"id": "test"}'

    def test_read_file_allowed_with_relative_project_root(self, tmp_path: Path, monkeypatch):
        """Relative root paths should still map permission checks to project-relative files."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        monkeypatch.chdir(tmp_path.parent)
        relative_root = Path(tmp_path.name)

        registry = SkillRegistry(
            root=relative_root,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=self.read_globs,
            deny_globs=self.deny_globs,
        )

        result = registry.invoke("read_file", {"path": "game/test.json"})
        assert result.success
        assert result.data["content"] == '{"id": "test"}'

    def test_read_file_denied(self, tmp_path: Path):
        """Should deny file read when path matches deny glob."""
        (tmp_path / "agents").mkdir()
        (tmp_path / "agents" / "secret.json").write_text("secret", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],  # Allow all
            deny_globs=["agents/**"],  # But deny agents
        )

        result = registry.invoke("read_file", {"path": "agents/secret.json"})
        assert not result.success
        assert "permission denied" in result.error.lower()
        assert "agents/secret.json" in result.denied_paths

    def test_read_file_not_found(self, tmp_path: Path):
        """Should return error for non-existent file."""
        registry = SkillRegistry(
            root=tmp_path, run_id="test_run", agent_id="test-agent", read_globs=["**"], deny_globs=[]
        )

        result = registry.invoke("read_file", {"path": "nonexistent.json"})
        assert not result.success
        assert "not found" in result.error.lower()

    def test_write_file_json_normalizes_unicode_escape_sequences(self, tmp_path: Path):
        """write_file should keep JSON UTF-8 text readable instead of \\uXXXX escapes."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["game/**"],
        )
        (tmp_path / "game" / "meta").mkdir(parents=True, exist_ok=True)
        payload = '{"name":"\\u5f00\\u59cb\\u6e38\\u620f"}'
        result = registry.invoke("write_file", {"path": "game/meta/sample.json", "content": payload})
        assert result.success
        written = (tmp_path / "game" / "meta" / "sample.json").read_text(encoding="utf-8")
        assert "\\u5f00\\u59cb\\u6e38\\u620f" not in written
        assert "开始游戏" in written

    def test_resolve_action_disabled_returns_error(self, tmp_path: Path):
        """Should return a clear error when resolve_action is disabled."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            enable_resolve_action=False,
        )
        result = registry.invoke("resolve_action", {"action": "heal", "actor": "player", "amount": 10})
        assert not result.success
        assert "disabled" in result.error.lower()

    def test_import_sillytavern_card_from_json(self, tmp_path: Path):
        """Should import a SillyTavern JSON card through the tool surface."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["game/**"],
        )
        card_path = tmp_path / "card.json"
        card_path.write_text(
            json.dumps(
                {
                    "spec": "chara_card_v2",
                    "data": {
                        "name": "August",
                        "description": "A test character.",
                        "personality": "",
                        "first_mes": "Hello.",
                        "scenario": "",
                        "tags": ["Noble"],
                        "creator": "tester",
                    },
                }
            ),
            encoding="utf-8",
        )

        result = registry.invoke("import_sillytavern_card", {"path": "card.json"})

        assert result.success
        assert result.data["id"] == "august"
        assert (tmp_path / "game" / "character" / "august.json").exists()

    def test_import_sillytavern_card_from_png(self, tmp_path: Path):
        """Should import a Tavern PNG card instead of trying to read it as text."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["game/**"],
        )
        png_path = tmp_path / "card.png"
        png_path.write_bytes(
            _build_png_with_chara(
                {
                    "spec": "chara_card_v2",
                    "data": {
                        "name": "Hero",
                        "description": "A PNG card",
                        "personality": "brave",
                        "first_mes": "Greetings!",
                        "scenario": "",
                        "tags": [],
                        "creator": "",
                    },
                }
            )
        )

        result = registry.invoke("import_sillytavern_card", {"path": "card.png", "entity_id": "hero-card"})

        assert result.success
        assert result.data["id"] == "hero-card"
        written = json.loads((tmp_path / "game" / "character" / "hero-card.json").read_text(encoding="utf-8"))
        assert written["meta"]["raw"]["data"]["name"] == "Hero"

    def test_import_sillytavern_card_supports_target_path_and_name_override(self, tmp_path: Path):
        """Tool should allow the model to choose destination folder/id and visible name."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["game/**"],
        )
        card_path = tmp_path / "card.json"
        card_path.write_text(
            json.dumps({"name": "天罗修仙界", "description": "x", "personality": "", "first_mes": ""}),
            encoding="utf-8",
        )

        result = registry.invoke(
            "import_sillytavern_card",
            {
                "path": "card.json",
                "target_path": "game/npc/yan_chiyang.json",
                "name": "燕赤阳",
            },
        )

        assert result.success
        written = json.loads((tmp_path / "game" / "npc" / "yan_chiyang.json").read_text(encoding="utf-8"))
        assert written["id"] == "yan_chiyang"
        assert written["kind"] == "npc"
        assert written["name"] == "燕赤阳"

    def test_import_sillytavern_card_requires_write_permission(self, tmp_path: Path):
        """Import tool should respect direct game-write permissions."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )
        card_path = tmp_path / "card.json"
        card_path.write_text(json.dumps({"name": "Hero", "description": "x", "personality": "", "first_mes": ""}), encoding="utf-8")

        result = registry.invoke("import_sillytavern_card", {"path": "card.json"})

        assert not result.success
        assert "direct_write_globs" in (result.error or "")

    def test_ensure_playable_scaffold_copies_agents_runtime_and_normalizes_active_agent(self, tmp_path: Path):
        """Tool should make a generated project actually playable by copying scaffold assets."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["game/**", "agents/**", ".neonrp/**"],
            allow_protected_paths=True,
        )
        (tmp_path / "game" / "meta").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".neonrp").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "meta" / "active-agent.json").write_text(
            json.dumps(
                {
                    "id": "active-agent",
                    "kind": "meta",
                    "name": "Broken Routing State",
                    "routing": {"current_agent": "narrator"},
                }
            ),
            encoding="utf-8",
        )

        result = registry.invoke("ensure_playable_scaffold", {})

        assert result.success
        assert (tmp_path / "agents" / "narrator" / "agent.json").exists()
        assert (tmp_path / "agents" / "town-agent" / "agent.json").exists()
        assert (tmp_path / "agents" / "dungeon-agent" / "agent.json").exists()
        assert (tmp_path / ".neonrp" / "runtime_contract.json").exists()
        state = json.loads((tmp_path / "game" / "meta" / "active-agent.json").read_text(encoding="utf-8"))
        assert state["active_agent"] == "narrator"
        assert "routing" not in state
        assert "agents/narrator/agent.json" in result.data["relative_files"]

    def test_ensure_playable_scaffold_requires_permissions_for_agents_and_runtime(self, tmp_path: Path):
        """Scaffold tool should respect non-game direct-write boundaries."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["game/**"],
        )
        (tmp_path / "game" / "meta").mkdir(parents=True, exist_ok=True)

        result = registry.invoke("ensure_playable_scaffold", {})

        assert not result.success
        assert "agents/narrator/agent.json" in (result.error or "")

    def test_list_entities_basic(self, tmp_path: Path):
        """Should list entities from manifest."""
        # Set up minimal project
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        game_dir = tmp_path / "game" / "character"
        game_dir.mkdir(parents=True)

        # Create entity
        entity = {"id": "hero", "kind": "character", "name": "Hero", "tags": ["player"]}
        (game_dir / "hero.json").write_text(json.dumps(entity), encoding="utf-8")

        # Create manifest with entity index
        manifest = {
            "version": "0.2",
            "current_branch": "main",
            "branches": {"main": {"head_event": 0, "created_at": "2026-01-01T00:00:00Z"}},
            "entities": {
                "character:hero": {
                    "id": "hero",
                    "kind": "character",
                    "name": "Hero",
                    "path": "game/character/hero.json",
                    "tags": ["player"],
                    "summary": None,
                    "mtime": 1.0,
                    "hash": "abc",
                }
            },
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path, run_id="test_run", agent_id="test-agent", read_globs=["game/**"], deny_globs=[]
        )

        result = registry.invoke("list_entities", {})
        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["id"] == "hero"

    def test_list_entities_filters(self, tmp_path: Path):
        """Should filter entities by kind and tag."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (tmp_path / "game" / "character").mkdir(parents=True)
        (tmp_path / "game" / "npc").mkdir(parents=True)
        (tmp_path / "game" / "character" / "hero.json").write_text(
            json.dumps({"id": "hero", "kind": "character", "name": "Hero", "tags": ["player"]}),
            encoding="utf-8",
        )
        (tmp_path / "game" / "npc" / "merchant.json").write_text(
            json.dumps({"id": "merchant", "kind": "npc", "name": "Merchant", "tags": ["shop"]}),
            encoding="utf-8",
        )

        manifest = {
            "version": "0.2",
            "current_branch": "main",
            "branches": {"main": {"head_event": 0, "created_at": "2026-01-01T00:00:00Z"}},
            "entities": {
                "character:hero": {
                    "id": "hero",
                    "kind": "character",
                    "name": "Hero",
                    "path": "game/character/hero.json",
                    "tags": ["player"],
                    "summary": None,
                    "mtime": 1.0,
                    "hash": "abc",
                },
                "npc:merchant": {
                    "id": "merchant",
                    "kind": "npc",
                    "name": "Merchant",
                    "path": "game/npc/merchant.json",
                    "tags": ["shop"],
                    "summary": None,
                    "mtime": 1.0,
                    "hash": "def",
                },
            },
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path, run_id="test_run", agent_id="test-agent", read_globs=["game/**"], deny_globs=[]
        )

        # Filter by kind
        result = registry.invoke("list_entities", {"kind": "npc"})
        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["id"] == "merchant"

    def test_list_entities_auto_refreshes_index_from_game(self, tmp_path: Path):
        """list_entities should auto-refresh manifest.entities from game/ when stale."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (tmp_path / "game" / "town").mkdir(parents=True)
        (tmp_path / "game" / "town" / "tokyo.json").write_text(
            json.dumps({"id": "tokyo", "kind": "town", "name": "Tokyo"}),
            encoding="utf-8",
        )

        # Stale/empty entities map: auto-refresh should repopulate from world files.
        manifest = {
            "version": "0.2",
            "current_branch": "main",
            "branches": {"main": {"head_event": 0, "created_at": "2026-01-01T00:00:00Z"}},
            "entities": {},
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path, run_id="test_run", agent_id="test-agent", read_globs=["game/**"], deny_globs=[]
        )

        result = registry.invoke("list_entities", {})
        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["id"] == "tokyo"


class TestSkillAuditLog:
    """Tests for skill audit logging."""

    def test_audit_log_created(self, tmp_path: Path):
        """Should create JSONL audit log."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()

        registry = SkillRegistry(
            root=tmp_path, run_id="audit_test_run", agent_id="test-agent", read_globs=["**"], deny_globs=[]
        )

        # Make some calls
        registry.invoke("read_file", {"path": "nonexistent.json"})

        # Save audit log
        log_path = registry.save_audit_log()

        assert log_path.exists()
        assert log_path.suffix == ".jsonl"

        # Parse log
        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["skill_name"] == "read_file"
        assert record["agent_id"] == "test-agent"
        assert record["run_id"] == "audit_test_run"
        assert "duration_ms" in record


class TestSkillPermissionFiltering:
    """Tests for permission-based result filtering."""

    def test_denied_paths_filtered_silently(self, tmp_path: Path):
        """Denied paths should be filtered but logged."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (tmp_path / "game" / "character").mkdir(parents=True)
        (tmp_path / "game" / "private").mkdir(parents=True)
        (tmp_path / "game" / "character" / "public.json").write_text(
            json.dumps({"id": "public", "kind": "character", "name": "Public"}),
            encoding="utf-8",
        )
        (tmp_path / "game" / "private" / "secret.json").write_text(
            json.dumps({"id": "secret", "kind": "private", "name": "Secret"}),
            encoding="utf-8",
        )

        # Create manifest with entities in allowed and denied paths
        manifest = {
            "version": "0.2",
            "current_branch": "main",
            "branches": {"main": {"head_event": 0, "created_at": "2026-01-01T00:00:00Z"}},
            "entities": {
                "character:public": {
                    "id": "public",
                    "kind": "character",
                    "name": "Public",
                    "path": "game/character/public.json",
                    "tags": [],
                    "summary": None,
                    "mtime": 1.0,
                    "hash": "abc",
                },
                "character:secret": {
                    "id": "secret",
                    "kind": "private",
                    "name": "Secret",
                    "path": "game/private/secret.json",
                    "tags": [],
                    "summary": None,
                    "mtime": 1.0,
                    "hash": "def",
                },
            },
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test_run",
            agent_id="test-agent",
            read_globs=["game/**"],
            deny_globs=["game/private/**"],
        )

        result = registry.invoke("list_entities", {})

        assert result.success
        assert len(result.data) == 1  # Only public
        assert result.data[0]["id"] == "public"
        assert "game/private/secret.json" in result.denied_paths

