"""Import a SillyTavern character card into the soul library as a rich soul.

The card is parsed deterministically (no re-asking the user for the file the
launcher already picked), its fields are folded into a single concept, and the
``soul-card-authoring`` skill is run through the caller-supplied LLM to author a
COMPLETE NeonRP soul bundle — a handful of card fields are transformed and
FILLED IN into the full persona/background/character/rules/memory file set that
:func:`neonrp.core.soul_authoring.scaffold_soul` expects. Anything the model
omits is still backfilled with a structural seed, so the soul is always
schema-complete, playable, and visible in :func:`neonrp.core.souls.list_souls`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.core.importers.sillytavern import (
    load_card_file,
    name_to_id,
    parse_card,
    resolve_id_conflict,
)
from neonrp.core.soul_authoring import _LLMLike, scaffold_soul
from neonrp.core.souls import SoulSource, create_soul_dir, list_souls

# The soul-card-authoring skill body (the prompt contract the LLM follows).
_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "builtin_skills"
    / "soul-card-authoring"
    / "SKILL.md"
)


def _skill_body() -> str:
    try:
        return _SKILL_MD.read_text(encoding="utf-8")
    except OSError:
        return ""


def _summary_from(parsed: dict[str, Any]) -> str:
    personality = (parsed.get("personality") or "").strip()
    if personality:
        return personality
    desc = (parsed.get("description") or "").strip()
    if len(desc) <= 300:
        return desc
    cut = desc[:300]
    dot = cut.rfind(".")
    return cut[: dot + 1] if dot > 100 else cut + "..."


def _clean_tags(tags: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        if isinstance(t, str) and t.strip():
            v = t.strip().lower()
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def _concept(parsed: dict[str, Any], tags: list[str]) -> str:
    """Fold every card field into one concept string for the authoring LLM."""
    lines = ["SillyTavern character card — author a faithful NeonRP soul from it.", ""]
    lines.append(f"Name: {parsed['name']}")
    for key, label in (
        ("personality", "Personality"),
        ("description", "Description"),
        ("scenario", "Scenario"),
        ("first_mes", "First message (their own voice)"),
    ):
        val = (parsed.get(key) or "").strip()
        if val:
            lines.append(f"{label}: {val}")
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    return "\n".join(lines)


def import_card_to_library(card_path: Path | str, *, llm: _LLMLike) -> Path:
    """Parse a SillyTavern PNG/JSON card and author a rich soul folder in the
    library (``~/.worldlines/souls/``) via the ``soul-card-authoring`` skill.

    ``llm`` is any object with ``generate(system_prompt, user_prompt, tools)``
    (an :class:`neonrp.core.llm.LLMAdapter`). Returns the new soul dir path.

    Raises ``ValueError`` if the file can't be read or isn't a valid card
    (no ``name``). LLM failures propagate from ``scaffold_soul`` (the caller —
    the launcher's spinner worker — turns them into an error notice)."""
    raw = load_card_file(card_path)      # ValueError on unreadable / bad PNG
    parsed = parse_card(raw)             # ValueError if the card has no name

    name = parsed["name"]
    tags = _clean_tags(parsed.get("tags"))
    summary = _summary_from(parsed)

    existing = {s.get("sid") for s in list_souls()}
    existing.discard(None)
    sid = resolve_id_conflict(name_to_id(name), existing)  # type: ignore[arg-type]

    soul_dir = create_soul_dir(
        sid,
        name=name,
        tags=["sillytavern", *tags],
        source=SoulSource(kind="local-create"),
    )

    scaffold_soul(
        soul_dir,
        description=_concept(parsed, tags) or summary or name,
        sid=sid,
        agent_template="heroine-classic",
        llm=llm,
        skill_body=_skill_body(),
    )
    return soul_dir
