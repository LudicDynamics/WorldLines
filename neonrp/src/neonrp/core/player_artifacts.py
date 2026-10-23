"""V0 player-facing run artifacts — the visionRP/Obsidian file contract.

Per ``rp-visionrp/DESIGN-VISIONRP.md`` (V0): every landed turn must leave the
run folder fully readable by any file client — Obsidian today, the visionRP
shell later, Claude Code always. Artifacts live at the run root:

  story.md     — append-only narrative log, one section per landed turn
  feed.jsonl   — append-only feed source, one JSON entry per landed turn
  feed.md      — "今日动态" digest, regenerated from feed.jsonl each turn
  tree.json    — branch/worldline snapshot from .neonrp/manifest.json
  inbox/       — player/director → world directives; ``pending/`` is drained
                 into the next turn at the raw-input boundary, then files
                 move to ``consumed/``

Same discipline as :mod:`neonrp.core.orchestration_trace`: **never raise
into a turn** — every public function is best-effort and swallows its own
errors. The shell/Obsidian side must treat all of these as engine-owned
(read-only); the only write surface for other clients is ``inbox/pending/``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_game_dir, get_manifest_path

logger = logging.getLogger(__name__)

ARTIFACTS_SCHEMA_VERSION = 1
FEED_DIGEST_TURNS = 10
FEED_SUMMARY_CHARS = 200

INBOX_README = """# inbox/ — 玩家/导演 → 世界 的干预通道

把一条指示写成一个 `.md` 或 `.txt` 文件放进 `pending/`，
引擎会在**下一回合开始时**读取它（与你打字输入同一入口），
然后把文件移到 `consumed/` 留档。

- 一个文件 = 一条指示，文件名任意（按文件名排序依次注入）
- 适合：离线留言、导演调度（"让 elena 今晚来找玩家"）、其他客户端
  （Obsidian / Dashboard / Claude Code）发起的干预
- 不要改 `consumed/` 里的文件；那是已生效记录

对应设计：rp-visionrp/DESIGN-VISIONRP.md §2（feed 是世界→玩家，inbox 方向相反）。
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_run_state(root: Path) -> dict[str, Any]:
    try:
        path = get_game_dir(root) / "meta" / "run_state.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — artifacts must never raise into a turn
        return {}


def _world_clock(run_state: dict[str, Any]) -> str:
    t = run_state.get("time") or {}
    parts: list[str] = []
    if t.get("day") is not None:
        parts.append(f"Day{t['day']}")
    if t.get("clock"):
        parts.append(str(t["clock"]))
    return " ".join(parts)


def _location_display(run_state: dict[str, Any], fallback: str | None) -> str:
    loc = run_state.get("location") or {}
    return str(loc.get("display") or loc.get("node") or fallback or "")


def _waiting_souls(run_state: dict[str, Any]) -> list[str]:
    """Souls currently available for interaction — the feed's "谁在等你"."""
    souls = (run_state.get("party") or {}).get("souls") or {}
    waiting: list[str] = []
    for sid, info in souls.items():
        if isinstance(info, dict) and info.get("available_for_interaction"):
            waiting.append(str(sid))
    return sorted(waiting)


def _one_line(text: str, limit: int) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed[:limit] + ("…" if len(collapsed) > limit else "")


# ---------------------------------------------------------------------------
# story.md


def _append_story(
    root: Path,
    branch: str,
    *,
    turn_seq: int,
    player_input: str,
    narration: str,
    speaker: str,
    location: str,
    clock: str,
) -> None:
    path = root / "story.md"
    if not path.exists():
        path.write_text(
            "# 世界线实录\n\n"
            "> 引擎每回合追加；这是游玩叙事的正本，人和 agent 共读。\n"
            "> 干预世界请写 inbox/pending/，不要直接改本文件。\n",
            encoding="utf-8",
        )
    head_bits = [f"T{turn_seq}"]
    if location:
        head_bits.append(location)
    if clock:
        head_bits.append(clock)
    if branch and branch != "main":
        head_bits.append(f"⎇{branch}")
    lines = ["", f"## {' · '.join(head_bits)}", ""]
    if player_input:
        lines.append(f"> {_one_line(player_input, 200)}")
        lines.append("")
    body = (narration or "").strip()
    if speaker and body:
        lines.append(f"**{speaker}**：{body}")
    elif body:
        lines.append(body)
    lines.append("")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def append_build_artifacts(
    root: Path,
    branch: str,
    *,
    author_input: str,
    narration: str,
    ledger: Any,
) -> bool:
    """Mirror one authoring turn into ``build.md`` (M31 B3).

    `story.md` is the played world's record; this is the *workshop* record —
    what the author asked for, what the agent said, and which files actually
    moved. Without it, editing a world leaves no trace anywhere a file client
    can see: the files just silently differ.

    Kept out of `feed.*` on purpose — the feed is the world's in-fiction
    activity, and authoring is not something that happened *in* the world.

    Returns True when an entry was written (i.e. the turn touched files).
    Best-effort like every artifact writer here: never raises into a turn.
    """
    try:
        if ledger is None or getattr(ledger, "is_empty", True):
            return False

        path = root / "build.md"
        if not path.exists():
            path.write_text(
                "# 世界工坊日志\n\n"
                "> build 模式每次改动世界后由引擎追加。\n"
                "> 记录「谁要求的 / agent 做了什么 / 哪些文件动了」——\n"
                "> 文件本身是正本，本文件是可追溯的过程。\n",
                encoding="utf-8",
            )

        headline = ledger.headline()
        # Human heading — the machine-precise stamp belongs in feed.jsonl,
        # not in something an author reads down a page of.
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = ["", f"## {stamp} · {headline}", ""]
        if branch and branch != "main":
            lines.append(f"⎇ {branch}")
            lines.append("")
        if author_input:
            lines.append(f"> {_one_line(author_input, 200)}")
            lines.append("")
        for entry in ledger.to_dict().get("files", []):
            lines.append(f"- `{entry['path']}` — {entry['headline']}")
        lines.append("")
        body = (narration or "").strip()
        if body:
            lines.append(_one_line(body, 400))
            lines.append("")
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return True
    except Exception:  # noqa: BLE001 — artifacts must never raise into a turn
        logger.debug("build artifacts append skipped", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# feed.jsonl + feed.md


def _append_feed_entry(root: Path, entry: dict[str, Any]) -> None:
    with (root / "feed.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_feed_tail(root: Path, last: int) -> list[dict[str, Any]]:
    try:
        lines = (root / "feed.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for ln in lines[-last:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            entries.append(json.loads(ln))
        except ValueError:
            continue
    return entries


def _render_feed_md(root: Path, waiting: list[str]) -> None:
    entries = _read_feed_tail(root, FEED_DIGEST_TURNS)
    lines = [
        "# 今日动态",
        "",
        f"> 世界在你离开时继续向前。最近 {len(entries)} 回合，新的在前：",
        "",
    ]
    for e in reversed(entries):
        head_bits = [f"T{e.get('turn_seq', '?')}"]
        if e.get("world_time"):
            head_bits.append(str(e["world_time"]))
        if e.get("location"):
            head_bits.append(str(e["location"]))
        branch = e.get("branch") or "main"
        branch_tag = f"（⎇{branch}）" if branch != "main" else ""
        summary = str(e.get("summary") or "")
        lines.append(f"- **{' · '.join(head_bits)}**{branch_tag} {summary}")
    if waiting:
        lines += ["", f"**正在等你回应：** {'、'.join(waiting)}"]
    lines += [
        "",
        f"*更新于 {_now_iso()} · 引擎每回合重写本文件；留言请写 inbox/pending/*",
        "",
    ]
    (root / "feed.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# tree.json


def _write_tree(root: Path, *, current_turn_seq: int, branch: str) -> None:
    try:
        manifest = json.loads(get_manifest_path(root).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    branches = []
    for name, meta in (manifest.get("branches") or {}).items():
        if not isinstance(meta, dict):
            continue
        branches.append(
            {
                "name": name,
                "kind": meta.get("kind", "main"),
                "parent": meta.get("parent"),
                "fork_event": meta.get("fork_event"),
                "head_event": meta.get("head_event"),
                "max_event": meta.get("max_event"),
                "created": meta.get("created"),
            }
        )
    tree = {
        "schema_version": ARTIFACTS_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "current_branch": manifest.get("current_branch", branch),
        "head": {"branch": branch, "turn_seq": current_turn_seq},
        "branches": branches,
    }
    (root / "tree.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# inbox/


def ensure_inbox(root: Path) -> None:
    """Create the inbox contract surface (idempotent, best-effort)."""
    try:
        pending = root / "inbox" / "pending"
        consumed = root / "inbox" / "consumed"
        pending.mkdir(parents=True, exist_ok=True)
        consumed.mkdir(parents=True, exist_ok=True)
        readme = root / "inbox" / "README.md"
        if not readme.exists():
            readme.write_text(INBOX_README, encoding="utf-8")
    except Exception:  # noqa: BLE001
        logger.debug("inbox ensure skipped", exc_info=True)


def drain_inbox(root: Path) -> list[str]:
    """Read + consume pending directives (oldest filename first).

    Each file's text is returned for injection at the raw-input boundary;
    the file is moved to ``consumed/`` (timestamp-prefixed to avoid name
    collisions). Best-effort per file: an unreadable file is left in place.
    """
    notes: list[str] = []
    try:
        pending = root / "inbox" / "pending"
        if not pending.is_dir():
            return notes
        consumed = root / "inbox" / "consumed"
        consumed.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        for path in sorted(pending.iterdir()):
            if path.suffix.lower() not in (".md", ".txt") or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
                path.rename(consumed / f"{stamp}-{path.name}")
            except OSError:
                logger.debug("inbox file skipped: %s", path, exc_info=True)
                continue
            if text:
                notes.append(text)
    except Exception:  # noqa: BLE001 — inbox must never break a turn
        logger.debug("inbox drain skipped", exc_info=True)
    return notes


# ---------------------------------------------------------------------------
# per-turn entry point


def append_turn_artifacts(
    root: Path,
    branch: str,
    *,
    turn_seq: int,
    player_input: str,
    narration: str,
    speaker: str,
) -> None:
    """Mirror one landed turn into the player-facing artifacts.

    Called next to ``append_turn_trace`` at the end of a multi-agent turn.
    Best-effort: any failure is logged at debug level and swallowed.
    """
    try:
        run_state = _read_run_state(root)
        clock = _world_clock(run_state)
        location = _location_display(run_state, None)
        waiting = _waiting_souls(run_state)

        _append_story(
            root,
            branch,
            turn_seq=turn_seq,
            player_input=player_input,
            narration=narration,
            speaker=speaker,
            location=location,
            clock=clock,
        )
        _append_feed_entry(
            root,
            {
                "schema_version": ARTIFACTS_SCHEMA_VERSION,
                "ts": _now_iso(),
                "turn_seq": turn_seq,
                "branch": branch or "main",
                "location": location,
                "world_time": clock,
                "speaker": speaker,
                "summary": _one_line(narration, FEED_SUMMARY_CHARS),
                "waiting": waiting,
            },
        )
        _render_feed_md(root, waiting)
        _write_tree(root, current_turn_seq=turn_seq, branch=branch or "main")
        ensure_inbox(root)
    except Exception:  # noqa: BLE001 — artifacts must never raise into a turn
        logger.debug("player artifacts append skipped", exc_info=True)
