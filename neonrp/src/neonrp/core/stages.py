"""Plot stages as events (10-14, the standard front end §5.7): a plot's stage variable — ``<plot id>.stage`` that
``stages`` declares, or the variable the plot names in ``stage_var`` — moved in this apply. The record carries the
stage's name and, when the plot declares one (``stage_cg``), the cut-scene slot ``stage.cg:<plot>.<n>`` to play.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neonrp.core.objective import stage_name  # a stage may be {name, goal} (10-15)


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def stage_vars(root: Path) -> dict[str, dict[str, Any]]:
    """variable → {plot, stages, cg: {n: cg}} for every installed plot that has stages."""
    from neonrp.core import scene_cg
    from neonrp.core.paths import get_data_dir_name

    out: dict[str, dict[str, Any]] = {}
    meta = root / get_data_dir_name(root) / "meta"
    for pid, info in (_j(meta / "plots.json", {}) or {}).items():
        var = (info or {}).get("stage_var")
        if not var:
            continue
        pj = _j(root / str((info or {}).get("dir") or "") / "plot.json", {}) or {}
        out[str(var)] = {"plot": str(pid), "stages": [stage_name(x) for x in pj.get("stages") or []], "cg": dict(scene_cg.stage(pj))}
    return out


def changes(root: Path, before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for var, sv in stage_vars(root).items():
        b, a = before.get(var), after.get(var)
        if a == b or a is None:
            continue
        n = a if isinstance(a, int) and not isinstance(a, bool) else None
        names = sv["stages"]
        rec: dict[str, Any] = {"plot": sv["plot"], "var": var, "from": b, "to": a,
                               "name": names[n] if n is not None and 0 <= n < len(names) else None}
        cg = sv["cg"].get(n) if n is not None else None
        if cg is not None:  # this run's companion's picture where the stage has one (10-15)
            from neonrp.core.scene_cg import for_companion
            from neonrp.template import run_companion

            rec["cg"] = for_companion({k: v for k, v in cg.items() if k != "prompt"}, f"stage.cg:{sv['plot']}.{n}", run_companion(root))
        out.append(rec)
    return out
