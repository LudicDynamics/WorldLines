"""Skill loading for M9 conversation knowledge injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path


@dataclass
class LoadedSkill:
    """A parsed skill document."""

    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    body: str = ""
    path: Path | None = None


def _parse_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    """Parse simple YAML frontmatter.

    This parser intentionally supports a constrained subset:
    - `key: value`
    - `tags: [a, b]` or `tags: a, b`
    """
    if not raw.startswith("---\n"):
        return {}, raw

    end_marker = "\n---\n"
    end_index = raw.find(end_marker, 4)
    if end_index < 0:
        return {}, raw

    frontmatter = raw[4:end_index]
    body = raw[end_index + len(end_marker) :]
    parsed: dict[str, object] = {}

    for line in frontmatter.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "tags":
            parsed[key] = _parse_tags(value)
        else:
            parsed[key] = _strip_quotes(value)

    return parsed, body


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_tags(raw_tags: str) -> list[str]:
    value = raw_tags.strip()
    if not value:
        return []

    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    if not value:
        return []

    parts = [part.strip() for part in value.split(",")]
    return [_strip_quotes(part) for part in parts if part]


class SkillLoader:
    """Loads project-local skills plus package builtin skills."""

    def __init__(
        self,
        root: Path,
        skills_dir: Path | None = None,
        builtin_skills_dir: Path | None = None,
    ):
        self.root = root
        self.skills_dir = skills_dir or (root / "skills")
        self.builtin_skills_dir = builtin_skills_dir
        self._skills: dict[str, LoadedSkill] = {}
        self._mtimes: dict[Path, float] = {}
        self.reload()

    def reload(self) -> None:
        """Rescan builtin and project skills; project-local skills override builtin ones."""
        skills: dict[str, LoadedSkill] = {}

        for path, raw in self._iter_builtin_skill_files():
            loaded = self._parse_loaded_skill(path=path, raw=raw, fallback_name=self._skill_parent_name(path))
            if loaded is not None:
                skills[loaded.name] = loaded

        mtimes: dict[Path, float] = {}
        if self.skills_dir.exists():
            for path in sorted(self.skills_dir.glob("*/SKILL.md")):
                try:
                    raw = path.read_text(encoding="utf-8")
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                loaded = self._parse_loaded_skill(path=path, raw=raw, fallback_name=path.parent.name)
                if loaded is not None:
                    skills[loaded.name] = loaded
                    mtimes[path] = mtime

        self._skills = skills
        self._mtimes = mtimes

    def list_skills(self) -> list[str]:
        """List available skill names."""
        self.reload()
        return sorted(self._skills.keys())

    def get_descriptions(self) -> list[str]:
        """Get compact `name: description` lines for prompt injection."""
        self.reload()
        return [f"{skill.name}: {skill.description}" for skill in self._ordered_skills()]

    def get_description(self, name: str) -> str | None:
        """Get the description for a single skill by name."""
        self.reload()
        skill = self._skills.get(name)
        return skill.description if skill else None

    def get_content(self, name: str) -> str | None:
        """Get full skill body wrapped for tool_result injection."""
        self.reload()
        skill = self._skills.get(name)
        if not skill:
            return None
        return f'<skill-loaded name="{skill.name}">\n{skill.body}\n</skill-loaded>'

    def _ordered_skills(self) -> list[LoadedSkill]:
        return [self._skills[name] for name in sorted(self._skills.keys())]

    @staticmethod
    def _derive_description(body: str) -> str:
        for line in body.splitlines():
            line = line.strip()
            if line:
                return line[:120]
        return "No description"

    def _iter_builtin_skill_files(self) -> list[tuple[Path | str, str]]:
        """Return builtin skill files bundled with the package."""
        if self.builtin_skills_dir is not None:
            if not self.builtin_skills_dir.exists():
                return []
            result: list[tuple[Path | str, str]] = []
            for path in sorted(self.builtin_skills_dir.glob("*/SKILL.md")):
                try:
                    result.append((path, path.read_text(encoding="utf-8")))
                except OSError:
                    continue
            return result

        try:
            builtin_root = resources.files("neonrp").joinpath("builtin_skills")
        except Exception:
            return []

        try:
            if not builtin_root.is_dir():
                return []
        except Exception:
            return []

        result: list[tuple[Path | str, str]] = []
        try:
            children = sorted(builtin_root.iterdir(), key=lambda child: child.name)
        except Exception:
            return []
        for child in children:
            try:
                if not child.is_dir():
                    continue
                skill_file = child.joinpath("SKILL.md")
                if not skill_file.is_file():
                    continue
                result.append((str(skill_file), skill_file.read_text(encoding="utf-8")))
            except Exception:
                continue
        return result

    @staticmethod
    def _skill_parent_name(path: Path | str) -> str:
        if isinstance(path, Path):
            return path.parent.name
        normalized = str(path).replace("\\", "/").rstrip("/")
        parts = normalized.split("/")
        return parts[-2] if len(parts) >= 2 else normalized

    def _parse_loaded_skill(self, path: Path | str, raw: str, fallback_name: str) -> LoadedSkill | None:
        meta, body = _parse_frontmatter(raw)
        name = str(meta.get("name") or fallback_name).strip()
        if not name:
            return None

        description = str(meta.get("description") or "").strip()
        if not description:
            description = self._derive_description(body)

        tags = meta.get("tags")
        tags_list = tags if isinstance(tags, list) else []
        return LoadedSkill(
            name=name,
            description=description,
            tags=[str(tag) for tag in tags_list],
            body=body.strip(),
            path=path if isinstance(path, Path) else None,
        )
