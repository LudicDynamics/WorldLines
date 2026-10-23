"""回合结算链(自 conversation.py 纯搬家抽离)。

哲学(M25):LLM 裁定 → procedural 校验 → 写回 → trace。
本模块持有「位置/回合数」这类**物理事实**的落地与队列:
- soul/玩家移动落地(place_nav 裁判校验后写 run_state)
- [位置裁定] 队列(本回合裁定 → 下回合 preflight,deliver-once)
- ⟦CORRECTIONS⟧ 结算块的解析与剥离(世界拍的回合结算义务)
- turn_count 推进(纯代码,不依赖 world-agent 记得写)

命名保留下划线前缀:S1 期与 conversation.py 门面 re-export 保持
同名 seam(tests 从 conversation 导入);S1.4 收面时统一转正。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

logger = logging.getLogger("neonrp")

CORRECTIONS_RE = re.compile(r"⟦CORRECTIONS⟧(.*?)⟦/CORRECTIONS⟧", re.S)

MISSING_BLOCK_REMINDER = (
    "[system] 上回合你没有输出移动裁定块(⟦CORRECTIONS⟧)。若上回合"
    "叙事中有任何角色(含玩家)改变了位置,其位置尚未结算——本回合"
    "必须在叙事后输出裁定块,按当前叙事把所有人的真实位置补齐。"
)


def _apply_soul_move(
    soul_dir: Path, node: str, root: Path | None = None, *, allow_cross_town: bool = False
) -> bool:
    """Write a soul's reported ``moved_to`` into its own run_state.json.

    This is what keeps the deterministic locality router alive: souls move,
    and the state the router reads moves with them. Missing run_state.json is
    created minimally; a no-op move (same node) returns False.

    When ``root`` is given the move is normalized to a scoped address
    (``T###/node``) via the soul's current town — a bare id stays in the
    soul's own town (default stay-in-town) so it can't be misread into another
    town on later reads, which is what made souls appear to jump (place_nav).
    """
    node = str(node or "").strip()
    if not node:
        return False
    path = soul_dir / "run_state.json"
    try:
        state: dict[str, Any] = {}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        if root is not None:
            from neonrp.core.place_nav import resolve_move_target

            resolved = resolve_move_target(
                root, node, current_location=state.get("location"), cross_town=allow_cross_town
            )
            if resolved is None:
                # Target isn't reachable from the soul's current town (e.g. a
                # hallucinated or cross-town bare node) — refuse to teleport; the
                # soul stays put. Cross-town travel needs an explicit T###/node.
                return False
            node = resolved
        if state.get("location") == node:
            return False
        state["location"] = node
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except (OSError, ValueError):
        logger.warning("soul move skipped: cannot update %s", path, exc_info=True)
        return False


def _soul_current_location(soul_dir: Path) -> str | None:
    """Read a soul's current run_state location (None when unknown)."""
    try:
        state = json.loads((soul_dir / "run_state.json").read_text(encoding="utf-8"))
        loc = state.get("location") if isinstance(state, dict) else None
        return str(loc) if loc else None
    except (OSError, ValueError):
        return None


def _location_judgments_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "location_judgments.json"


def _queue_location_judgment(root: Path, line: str) -> None:
    """Queue a location-judge verdict line for the world-agent's NEXT turn.

    V3(M30):统一便签通道(mailbox deliver-once);裁定在本回合结算后
    产生,下回合 preflight drain——投递模式与幕间直聊/秘密便签同族。"""
    from neonrp.core.notes import post_note

    post_note(root, "judgment", line)


def _drain_location_judgments(root: Path) -> list[str]:
    """Read-and-clear the queued judge lines (each delivers exactly once)."""
    from neonrp.core.notes import drain_notes

    return drain_notes(root, "judgment", legacy_path=_location_judgments_path(root))


def _judge_world_agent_move(
    root: Path, soul_dir: Path, *, instance_id: str, display_name: str, move: str
) -> str:
    """Run the location judge over a world-agent move before it lands.

    Returns the address to persist ("" = refused, soul stays put). Clamps and
    refusals queue a [位置裁定] line for the world-agent's next preflight. A
    judge failure lands the move as-is (the judge must never break a turn)."""
    from neonrp.core.place_nav import judge_move

    try:
        verdict = judge_move(
            root, current_location=_soul_current_location(soul_dir), target=move
        )
    except Exception:
        logger.warning("location judge failed; landing move as-is", exc_info=True)
        return move
    if verdict.allowed:
        return verdict.resolved or move
    landing = verdict.clamped_to or ""
    logger.info(
        "location judge %s soul %s: %r -> %r (%s)",
        "clamped" if landing else "refused",
        instance_id,
        move,
        landing or "(stay)",
        verdict.reason,
    )
    if verdict.reason:
        _queue_location_judgment(
            root, f"[soul:{instance_id}] {display_name}:{verdict.reason}"
        )
    return landing


def _apply_player_move(root: Path, move: str) -> bool:
    """Land the world-agent's adjudicated PLAYER position — the procedural
    twin of the soul path (judge_move validates, then game/meta/run_state.json
    is written). The player previously had NO landing path at all: narration
    moved them, state never followed (the 0-hop desync of 2026-07-24, see
    docs/POSITION-GROUND-TRUTH.md P0). Same map-judged policy as souls; a
    refused/unknown target stays put and queues a [位置裁定] line."""
    move = str(move or "").strip()
    if not move:
        return False
    from neonrp.core.place_nav import judge_move, qualify_location, split_location

    path = root / get_data_dir_name(root) / "meta" / "run_state.json"
    try:
        state: dict[str, Any] = {}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        loc = state.get("location") if isinstance(state.get("location"), dict) else {}
        loc = loc or {}
        cur = qualify_location(
            root,
            str(loc.get("node") or "") or None,
            current_town=str(loc.get("node_id") or "") or None,
        )
        try:
            verdict = judge_move(root, current_location=cur, target=move)
        except Exception:  # noqa: BLE001 — the judge must never break a turn
            logger.warning("player location judge failed; landing as-is", exc_info=True)
            verdict = None
        if verdict is None:
            landing = move
        elif verdict.allowed:
            landing = verdict.resolved or move
        else:
            landing = verdict.clamped_to or ""
            if verdict.reason:
                _queue_location_judgment(root, f"[player] 玩家:{verdict.reason}")
        if not landing:
            return False
        town, node = split_location(landing)
        new_loc = dict(loc)
        new_loc["node"] = node or landing
        if town:
            new_loc["node_id"] = town
        if "subnode_id" in loc:
            new_loc["subnode_id"] = node or landing
        # display 与 node 同步刷新(canonical 地名),否则 UI/场景标签仍显示
        # 旧地点 —— 又一层「状态与叙事脱节」。best-effort:解析不到就保守清空
        # 前缀格式(镇名·地名)里的地名部分由 town_node_view 提供。
        try:
            from neonrp.core.place_nav import town_node_view

            _view = town_node_view(
                root, node or landing, prefer_town=town or str(loc.get("node_id") or "") or None
            )
            if _view and _view.get("name") and isinstance(loc.get("display"), str):
                _old = str(loc["display"])
                _prefix = _old.rsplit("·", 1)[0] if "·" in _old else ""
                new_loc["display"] = (
                    f"{_prefix}·{_view['name']}" if _prefix else str(_view["name"])
                )
        except Exception:  # noqa: BLE001 — display polish must never block landing
            pass
        if new_loc == loc:
            return False
        state["location"] = new_loc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except (OSError, ValueError):
        logger.warning("player move skipped: cannot update %s", path, exc_info=True)
        return False


def _bump_turn_count(root: Path, turn_count_at_start: int) -> None:
    """Advance game/meta/run_state.json turn_count after a turn — pure code.

    The router's turn_seq must not depend on the world-agent remembering to
    write it (evidence: sessions where turn_count stayed 0 across every turn).
    Idempotent against a world-agent that already bumped it this turn.
    """
    path = root / get_data_dir_name(root) / "meta" / "run_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return
        try:
            current = int(state.get("turn_count"))
        except (TypeError, ValueError):
            current = 0
        state["turn_count"] = max(current, int(turn_count_at_start) + 1)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, ValueError):
        logger.debug("turn_count bump skipped", exc_info=True)


def extract_corrections(
    narration_text: str, valid_iids: set[str] | frozenset[str]
) -> tuple[dict[str, dict[str, str]], str]:
    """⟦CORRECTIONS⟧ 结算块:解析 + 剥离(自 conversation.py 内联搬家)。

    Returns ``(corrections, cleaned_text)``. Tolerant — a malformed block is
    discarded but still stripped (nothing leaks to the player). ``"player"``
    是玩家位移的固定 key(P0);容忍模型常见的 key 笔误。
    """
    corrections: dict[str, dict[str, str]] = {}
    if "⟦CORRECTIONS⟧" not in narration_text:
        return corrections, narration_text
    m = CORRECTIONS_RE.search(narration_text)
    if m:
        try:
            raw = json.loads(m.group(1).strip())
        except (ValueError, TypeError):
            raw = None
            logger.warning("world-agent CORRECTIONS block unparseable; ignored")
        if isinstance(raw, dict):
            for iid, ov in raw.items():
                if (iid in valid_iids or iid == "player") and isinstance(ov, dict):
                    # `moved_to` is the authoritative final position (even
                    # empty string = stay put). The world-agent is the SOLE
                    # mover, so tolerate the common key typos a model emits
                    # rather than silently losing the whole move.
                    key = next(
                        (
                            k
                            for k in ("moved_to", "movedto", "moved to", "movedTo")
                            if k in ov
                        ),
                        None,
                    )
                    if key is not None:
                        corrections[iid] = {"moved_to": str(ov.get(key) or "")}
            if corrections:
                logger.info(
                    "world-agent corrections: %s",
                    {k: v.get("moved_to") for k, v in corrections.items()},
                )
    # Strip every marker/region (even a malformed/unterminated one).
    cleaned = CORRECTIONS_RE.sub("", narration_text)
    cleaned = (
        cleaned.replace("⟦CORRECTIONS⟧", "").replace("⟦/CORRECTIONS⟧", "").rstrip()
    )
    return corrections, cleaned
