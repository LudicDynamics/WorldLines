"""Tests for skill loader (M9-T3)."""

from pathlib import Path

from neonrp.core.skill_loader import SkillLoader


def _write_project_skill(root: Path, folder: str, content: str) -> None:
    path = root / "skills" / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(content, encoding="utf-8")


def _write_builtin_skill(root: Path, folder: str, content: str) -> None:
    path = root / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(content, encoding="utf-8")


class TestSkillLoader:
    def test_loads_builtin_and_project_skills_and_lists_names(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        _write_builtin_skill(
            builtin_dir,
            "combat",
            """---
name: combat
description: Combat rules and tactical guidance
tags: [rpg, combat]
---
# Combat
Roll initiative and apply damage.
""",
        )
        _write_project_skill(
            tmp_path,
            "narrative",
            """---
name: narrative
description: Narrative style
tags: storytelling, prose
---
Use vivid sensory language.
""",
        )

        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        assert loader.list_skills() == ["combat", "narrative"]

    def test_default_loader_exposes_packaged_builtin_skills_in_empty_project(self, tmp_path: Path):
        loader = SkillLoader(tmp_path)
        names = loader.list_skills()

        assert "entity-authoring" in names
        assert "tavern-game-import" in names

    def test_project_skill_overrides_builtin_skill_of_same_name(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        _write_builtin_skill(
            builtin_dir,
            "combat",
            """---
name: combat
description: Builtin combat rules
---
Use builtin combat.
""",
        )
        _write_project_skill(
            tmp_path,
            "combat",
            """---
name: combat
description: Project combat rules
---
Use project combat.
""",
        )

        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)

        assert loader.get_description("combat") == "Project combat rules"
        content = loader.get_content("combat")
        assert content is not None
        assert "Use project combat." in content
        assert "Use builtin combat." not in content

    def test_get_descriptions_returns_name_and_description(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        _write_builtin_skill(
            builtin_dir,
            "world-building",
            """---
name: world-building
description: Entity conventions and map structure
---
Keep IDs stable.
""",
        )

        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        descriptions = loader.get_descriptions()
        assert descriptions == ["world-building: Entity conventions and map structure"]

    def test_get_content_wraps_skill_body(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        _write_builtin_skill(
            builtin_dir,
            "combat",
            """---
name: combat
description: Combat skill
---
Line one
Line two
""",
        )

        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        content = loader.get_content("combat")

        assert content is not None
        assert '<skill-loaded name="combat">' in content
        assert "Line one" in content
        assert content.strip().endswith("</skill-loaded>")

    def test_get_content_returns_none_for_unknown_skill(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        assert loader.get_content("missing") is None

    def test_empty_project_returns_no_skills_when_builtin_source_is_explicitly_missing(self, tmp_path: Path):
        loader = SkillLoader(tmp_path, builtin_skills_dir=tmp_path / "missing-builtin")
        assert loader.list_skills() == []
        assert loader.get_descriptions() == []

    def test_get_description_returns_single_skill_description(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        _write_builtin_skill(
            builtin_dir,
            "combat",
            """---
name: combat
description: Combat rules and tactical guidance
tags: [rpg]
---
# Combat
Roll initiative.
""",
        )
        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        assert loader.get_description("combat") == "Combat rules and tactical guidance"
        assert loader.get_description("nonexistent") is None

    def test_accessors_hot_reload_new_project_skill_without_manual_reload(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)

        assert loader.list_skills() == []

        _write_project_skill(
            tmp_path,
            "alchemy",
            """---
name: alchemy
description: Potion brewing
---
Brew potions.
""",
        )

        assert loader.list_skills() == ["alchemy"]
        assert loader.get_description("alchemy") == "Potion brewing"

    def test_reload_invalidates_removed_project_skill_and_cache(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        _write_project_skill(
            tmp_path,
            "alchemy",
            """---
name: alchemy
description: Potion brewing
---
Brew potions.
""",
        )
        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        assert "alchemy" in loader.list_skills()

        import shutil

        shutil.rmtree(tmp_path / "skills" / "alchemy")

        assert "alchemy" not in loader.list_skills()
        assert loader.get_description("alchemy") is None
        assert all("alchemy" not in str(path) for path in loader._mtimes)

    def test_malformed_frontmatter_is_tolerated(self, tmp_path: Path):
        builtin_dir = tmp_path / "builtin"
        _write_builtin_skill(
            builtin_dir,
            "broken",
            """---
name: broken
description: missing end marker
Body starts here
""",
        )

        loader = SkillLoader(tmp_path, builtin_skills_dir=builtin_dir)
        assert loader.list_skills() == ["broken"]
        assert loader.get_content("broken") is not None
