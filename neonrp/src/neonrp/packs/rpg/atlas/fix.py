"""After-turn placement (「move 是异步的 [~move],可以后期再补」): a place grown this turn without a readable
relation was hung beside the player so the turn never waited. After the reply, a small model (the judge's) reads the
prose that grew it and the tree around it, and says where it sits — near / between / in / over which places. The engine
checks that answer like any other (``atlas.graph.town_rehang``: the places exist, one layer, no cycle, the map still
draws) and re-hangs the node; a wrong answer leaves the default and is logged. The player stays on the node.

The prompt is the template's: prompt spec key ``place_fix`` — ``enabled`` · ``system`` · ``extra`` (merged per field)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SYS = ("You are tidying the layers of a town map. The map is a tree: places on one layer have roads between them; a place may be "
        "inside another (one layer down, entered only from it); a place may also wrap several places of one layer (one layer up, "
        "e.g. a district). A place grown just now hangs beside the player for the moment. Read the narration, decide where it "
        "really is, and output one JSON only:\n"
        '{"rel": "near|between|in|over|keep", "to": ["names of existing places", …], "why": "one line"}\n'
        "near = on the same layer as these places, beside them; between = on the road between two places (exactly two); in = inside "
        "one place; over = wraps these places of one layer; keep = where it hangs now is right. to uses only names that appear in "
        "the map.")


def _spec(root: Path) -> dict[str, Any]:
    from neonrp.core.adv import prompt_spec

    try:
        g = prompt_spec(root).get("place_fix")
    except Exception:  # noqa: BLE001
        g = None
    return g if isinstance(g, dict) else {}


def pending(created: list[dict[str, Any]] | None) -> list[str]:
    return [str(c["id"]) for c in created or [] if c.get("class") == "place" and c.get("default")]


def available(root: Path) -> bool:
    from neonrp.core import system_one as s1

    if _spec(root).get("enabled") is False:
        return False
    return s1.LLM_ADAPTER_FACTORY is not None or bool(s1.fallback_judge_preset())


def _tree_text(data: dict[str, Any], node: str) -> str:
    """The map the model sees: every node with its layer and roads (names only)."""
    by_id = {str(n.get("id")): n for n in data.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
    nm = lambda i: str((by_id.get(i) or {}).get("name") or i)  # noqa: E731
    rows = []
    for nid, n in by_id.items():
        up = f", inside '{nm(n['parent'])}'" if n.get("parent") else ""
        roads = ", ".join(nm(x) for x in n.get("links") or [] if x in by_id) or "none"
        rows.append(f"- {nm(nid)}{up}; roads to: {roads}" + ("   ← grown just now" if nid == node else ""))
    return "\n".join(rows)


def fix(root: Path, narration: str, ids: list[str]) -> list[dict[str, Any]]:
    """Place each pending node; returns one record per node (also appended to game/meta/place_fixes.json)."""
    if not ids or not available(root):
        return []
    from neonrp.core import system_one as s1
    from neonrp.core.llm import Message
    from neonrp.packs.rpg.atlas.graph import _town_map, town_rehang
    from neonrp.core.paths import get_data_dir_name
    from neonrp.core.place_nav import split_location
    from neonrp.core.registry import load_registry

    sp = _spec(root)
    system = str(sp.get("system") or _SYS) + (("\n" + str(sp["extra"])) if sp.get("extra") else "")
    out: list[dict[str, Any]] = []
    for pid in ids:
        t0 = time.monotonic()
        town, node = split_location(pid)
        if not town or not node:
            continue
        _p, data = _town_map(root, town)
        rec: dict[str, Any] = {"id": pid, "rel": None, "to": [], "ok": False}
        try:
            user = f"# Map\n{_tree_text(data, node)}\n\n# This turn's narration\n{(narration or '')[-2500:]}\n\nWhere is '{node}'?"
            res = s1._llm_adapter().chat([Message(role="system", content=system), Message(role="user", content=user)])
            text = (getattr(getattr(res, "message", None), "content", None) or "").strip()
            i, j = text.find("{"), text.rfind("}")
            d = json.loads(text[i : j + 1]) if 0 <= i < j else {}
        except Exception as exc:  # noqa: BLE001 — placement is best-effort, the default stays
            rec["why"] = f"model: {exc}"[:200]
            out.append(rec)
            continue
        rel, names = str(d.get("rel") or "keep"), [str(x) for x in d.get("to") or []]
        rec.update({"rel": rel, "to": names, "said": str(d.get("why") or "")[:200]})
        if rel == "keep":
            rec["ok"] = True
        else:
            reg = load_registry(root)
            targets = [reg.resolve(x, cls="place") for x in names]
            if not targets or None in targets:
                rec["why"] = f"unknown places {[n for n, t in zip(names, targets) if t is None] or names}"
            else:
                ok, why = town_rehang(root, town, node, rel, [split_location(x)[1] or x for x in targets if x])
                rec.update({"ok": ok, **({"why": why} if why else {})})
        rec["ms"] = round((time.monotonic() - t0) * 1000, 1)
        out.append(rec)
    try:
        log = root / get_data_dir_name(root) / "meta" / "place_fixes.json"
        prev = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps([*prev, *out][-200:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        logger.debug("place_fixes log failed", exc_info=True)
    return out


def after_turn(root: Path, *, created: list[dict[str, Any]] | None = None, narration: str = "", **_: Any) -> Any:
    """The ``after_turn`` mechanics seam: work to run after the reply, as a zero-arg callable — or None when nothing
    waits (no place grown by default this turn, or no judge model)."""
    ids = pending(created)
    if not ids or not available(root):
        return None
    return lambda: fix(root, narration, ids)

