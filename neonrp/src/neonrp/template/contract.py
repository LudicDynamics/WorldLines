"""Play contracts (`worldlines.play-contract/1`) — what a kind of game must deliver: entry, exit, endings, rewards, fixed
outputs, deaths, and what it takes to publish.

A template opts in with ``"play_contract": "<id>@<version>"``. Contracts are data files ``<id>.play-contract.json``,
looked up in the source tree's ``worldlines/contracts/`` and every directory on ``NEONRP_PLAY_CONTRACT_PATH``
(``:``-separated). The contract governs experience only, never orchestration.

``deaths`` (「死亡结算算在 Template 的合约里」)::

    "deaths": {"player":    {"exit": "ending", "ending_kind": "fail"},   # the run ends on the template's fail ending
               "companion": {"settle": "record"},                        # recorded, the run goes on (a plot may react)
               "other":     {"settle": "record"},
               "insanity":  {"exit": "ending", "ending_kind": "fail"}}   # SAN at 0 (worlds that have SAN)

``{"exit": "ending"}`` ends the run (core/settlement.py); ``{"settle": "record"}`` only adds to the settlement's
``deaths``. Missing entries default to: player → exit, everyone else → record.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.play-contract/1"
DEFAULT_DEATHS: dict[str, dict[str, Any]] = {"player": {"exit": "ending", "ending_kind": "fail"},
                                             "companion": {"settle": "record"}, "other": {"settle": "record"}}


class ContractError(ValueError):
    pass


def search_dirs() -> list[Path]:
    out: list[Path] = []
    for p in os.environ.get("NEONRP_PLAY_CONTRACT_PATH", "").split(os.pathsep):
        if p.strip():
            out.append(Path(p).expanduser())
    repo = Path(__file__).resolve().parents[3]
    # running from source — dev repo: <repo>/worldlines/contracts · public repo: <repo>/neonrp/src/neonrp → the sibling
    for src in (repo / "worldlines" / "contracts", repo.parent / "worldlines" / "contracts"):
        if src.is_dir() and src not in out:
            out.append(src)
    from neonrp.core.paths import shell_dir

    shipped = shell_dir("contracts")  # an installed release: the worldlines wheel carries them (10-08)
    if shipped is not None and shipped not in out:
        out.append(shipped)
    return out


def parse_ref(ref: str) -> tuple[str, int | None]:
    """``mystery-trpg@1`` → (``mystery-trpg``, 1); ``mystery-trpg`` → (…, None = any version)."""
    s = str(ref or "").strip()
    cid, _, ver = s.partition("@")
    try:
        return cid.strip(), int(ver) if ver.strip() else None
    except ValueError as e:
        raise ContractError(f"bad contract version in {ref!r}") from e


def available() -> dict[str, Path]:
    """{id: file} — the first directory wins (the env path before the source tree)."""
    out: dict[str, Path] = {}
    for d in search_dirs():
        for f in sorted(d.glob("*.play-contract.json")):
            out.setdefault(f.name.removesuffix(".play-contract.json"), f)
    return out


def load(ref: str) -> dict[str, Any]:
    """The contract ``ref`` names (``<id>@<version>``); ContractError when unknown, wrong schema or wrong version."""
    cid, ver = parse_ref(ref)
    f = available().get(cid)
    if f is None:
        raise ContractError(f"unknown play contract {cid!r} (have: {', '.join(sorted(available())) or 'none'})")
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ContractError(f"{f}: not JSON ({e})") from e
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise ContractError(f"{f}: not a {SCHEMA} file")
    if ver is not None and int(d.get("version") or 0) != ver:
        raise ContractError(f"{cid}: version {d.get('version')} here, {ver} asked")
    return d


def deaths(c: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The contract's death rules, defaults filled in (no contract = the defaults)."""
    out = {k: dict(v) for k, v in DEFAULT_DEATHS.items()}
    for k, v in ((c or {}).get("deaths") or {}).items():
        if isinstance(v, dict):
            out[str(k)] = dict(v)
    return out


def ends_run(rule: dict[str, Any] | None) -> bool:
    return bool(rule) and str((rule or {}).get("exit") or "") in ("ending", "exit", "settle")


def run_contract(root: Path) -> dict[str, Any] | None:
    """The contract a run was built under (copied into ``game/meta/play_contract.json`` at build), or None."""
    from neonrp.core.paths import get_data_dir_name

    try:
        d = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "play_contract.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


# ── lint by contract (R1) ────────────────────────────────────────────────────

def _endings(plots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for plot in plots:
        for eid, spec in (plot.get("endings") or {}).items():
            out[str(eid)] = {**(spec if isinstance(spec, dict) else {}), "_plot": plot.get("id")}
    return out


def _has_opening(t: Any, wdir: Path | None) -> bool:
    from neonrp.template import overlay_dir

    for base in (overlay_dir(t), wdir):
        if base is None:
            continue
        try:
            gs = json.loads((Path(base) / "game" / "meta" / "game-start.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(gs, dict) and (gs.get("startup") or {}).get("opening_scene"):
            return True
    return False


def _pack_cast(t: Any, wdir: Path) -> int:
    """How many instances of the pack's cast class the world ships (a rule pack's seats, 10-08 E2)."""
    try:
        from neonrp import packs

        pk = packs.load(t.pack_name, wdir)
    except Exception:  # noqa: BLE001
        return 0
    cc = str(getattr(pk, "cast_class", "") or "")
    spec = pk.classes.get(cc) if cc else None
    folder = str(getattr(spec, "folder", "") or "") if spec is not None else ""
    d = wdir / folder.split("#", 1)[0] if folder else None
    return sum(1 for _ in d.glob("*.json")) if d is not None and d.is_dir() else 0


def lint(t: Any, plots: list[dict[str, Any]], wdir: Path | None) -> list[tuple[str, str, str, str]]:
    """(level, code, where, msg) for every way the template falls short of its contract. No contract → nothing."""
    if not getattr(t, "play_contract", ""):
        return []
    out: list[tuple[str, str, str, str]] = []
    try:
        c = load(t.play_contract)
    except ContractError as e:
        return [("block", "contract.unknown", "play_contract", str(e))]
    from neonrp.template import _ending_emitters, _pack_plot, _world_souls

    entry, ex, ends = c.get("entry") or {}, c.get("exit") or {}, c.get("endings") or {}
    if entry.get("opening") == "required" and not _has_opening(t, wdir):
        out.append(("block", "contract.entry", "entry.opening", "the contract needs an opening (game-start.json startup.opening_scene)"))
    if entry.get("cast") == "fixed" and not (t.souls or (wdir is not None and (_world_souls(wdir) or _pack_cast(t, wdir)))):
        out.append(("block", "contract.entry", "entry.cast", "the contract needs a fixed cast; the template casts no one"))
    endings = _endings(plots)
    reachable = set(_ending_emitters([*plots, _pack_plot(t)]))  # a rule pack's own end triggers reach endings too (E1)
    if ex.get("on") == "ending" and not (reachable & set(endings)):
        out.append(("block", "contract.exit", "exit.on", "the contract exits at an ending; no trigger reaches one"))
    if len(endings) < int(ends.get("min") or 0):
        out.append(("block", "contract.endings", "endings.min", f"needs ≥ {ends.get('min')} endings, has {len(endings)}"))
    kinds = {str(e.get("kind") or "") for e in endings.values()}
    for k in ends.get("require") or []:
        if str(k) not in kinds:
            out.append(("block", "contract.endings", f"endings.require.{k}", f"needs an ending of kind {k!r}"))
    if ex.get("reveal") == "required":
        for plot in plots:
            if plot.get("endings") and not plot.get("reveal"):
                out.append(("block", "contract.reveal", f"{plot.get('id')}.reveal",
                            "the contract reveals the truth at the ending; the plot has no reveal"))
    if "ending_cg" in ((c.get("rewards") or {}).get("player") or []):
        for eid, e in endings.items():
            if not (e.get("assets") or {}).get("image"):
                out.append(("block", "contract.rewards", f"endings.{eid}.assets.image",
                            "rewards.player has ending_cg: every ending needs an image slot"))
    for who, rule in deaths(c).items():
        kind = str((rule or {}).get("ending_kind") or "")
        if ends_run(rule) and kind and kind not in kinds:
            out.append(("warn", "contract.deaths", f"deaths.{who}",
                        f"a {who} death exits on a {kind!r} ending; the template has none — the engine gives a plain death exit"))
    return out
