"""`neonrp commit log / checkout / branch / gc / verify / backfill`.

The M17 commit-versioning CLI (local-only v1, M17 §10 acceptance). This
module is a thin click surface mirroring `commands/world_hub.py`: it
parses args and renders output; every operation delegates to a leaf
(`core/commit_store`) or the integration glue (`core/commit_subsystem`),
which in turn wires the pure composer (`core/turn_commit`) and the
manifest leaf (`core/playthrough`). No commit/hash logic lives here.

`commits_root` defaults to the real `~/.worldlines/commits` store but is
overridable via `--commits-root` so this whole surface is testable on a
tmp fixture with no network and no home-dir writes.
"""

from __future__ import annotations

from pathlib import Path

import click

from neonrp.core import commit_store
from neonrp.core.commit_subsystem import (
    CommitSubsystemError,
    backfill_game,
    branch_from_head,
    checkout_commit,
    land_commit,
    verify_commit,
    walk_log,
)

# The real store root (M17 §4). Matches commit_store.COMMITS_HOME; kept as
# the CLI default so tests inject a tmp path instead of touching $HOME.
_DEFAULT_COMMITS_ROOT = commit_store.COMMITS_HOME

_commits_root_option = click.option(
    "--commits-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Commit store root (default: ~/.worldlines/commits). "
    "Override for tests or a relocatable install.",
)

_game_root_option = click.option(
    "--game-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd,
    help="Game working tree (default: cwd).",
)


def _resolve_commits_root(commits_root: Path | None) -> Path:
    return Path(commits_root) if commits_root is not None else _DEFAULT_COMMITS_ROOT


@click.group("commit")
def commit_group() -> None:
    """Commit-versioning — per-playthrough commit DAG (log/checkout/branch/gc/verify)."""


@commit_group.command("commit")
@_game_root_option
@_commits_root_option
@click.option("--turn", "turn_seq", type=int, required=True, help="Turn sequence number for this commit.")
@click.option("--branch", default="main", show_default=True, help="Branch to land this commit on.")
@click.option("--parent", default=None, help="Parent world_commit_id (omit for the initial commit).")
def commit_create(
    game_root: Path,
    commits_root: Path | None,
    turn_seq: int,
    branch: str,
    parent: str | None,
) -> None:
    """Pack the working tree into a content-hashed commit and advance HEAD.

    Wires the leaves: tree-hash (`core/hashing`) → blob
    (`commit_store.pack_dir`/`write_blob`, keyed by the tree-hash) →
    `turn_commit.compose_commit` (pure id derivation) →
    `commit_store.write_world_commit`/`write_ref` → manifest HEAD bump.
    """
    root = _resolve_commits_root(commits_root)
    try:
        landed = land_commit(
            Path(game_root), root, turn_seq=turn_seq, branch=branch, parent=parent
        )
    except CommitSubsystemError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"✓ Committed {landed.world_commit_id}  ·  turn {landed.turn_seq}  ·  {landed.branch}")
    if landed.parent:
        click.echo(f"  parent:  {landed.parent}")


@commit_group.command("log")
@_game_root_option
@_commits_root_option
@click.option("--from", "from_commit", default=None, help="Start commit (default: working-tree HEAD).")
def commit_log(game_root: Path, commits_root: Path | None, from_commit: str | None) -> None:
    """Walk the commit DAG and print the turn timeline (M17 §10)."""
    root = _resolve_commits_root(commits_root)
    head = from_commit
    if head is None:
        head_file = Path(game_root) / ".neonrp" / "HEAD"
        if head_file.exists():
            head = head_file.read_text(encoding="utf-8").strip() or None
    if not head:
        raise click.ClickException(
            "no HEAD for this game dir — commit a turn or pass --from <commit_id>"
        )

    entries = walk_log(root, head)
    if not entries:
        click.echo("(no commits reachable from HEAD)")
        return

    click.echo(f"{len(entries)} commit(s)  ·  HEAD {head}")
    click.echo()
    for e in entries:
        tag = f"  [{', '.join(e.labels)}]" if e.labels else ""
        click.echo(f"  {e.commit_id}  turn {e.turn_seq:<5}  {e.branch}{tag}")
        if e.parent:
            click.echo(f"    └─ parent {e.parent}")


@commit_group.command("checkout")
@click.argument("commit_id")
@_commits_root_option
@click.option(
    "--into",
    "dest_root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.cwd,
    help="Destination working tree (default: cwd).",
)
def commit_checkout(commit_id: str, commits_root: Path | None, dest_root: Path) -> None:
    """Restore a working tree (game + soul instances) from COMMIT_ID.

    Delegates to `commit_subsystem.checkout_commit`, which reads the
    commit object via `commit_store`, unpacks the game-folder blob, and
    follows the read-only `soul_scene_index` to restore each soul.
    """
    root = _resolve_commits_root(commits_root)
    try:
        obj = checkout_commit(root, commit_id, Path(dest_root))
    except CommitSubsystemError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"✓ Checked out {commit_id} into {dest_root}")
    click.echo(f"  turn:    {obj.get('turn_seq')}")
    click.echo(f"  branch:  {obj.get('branch', 'main')}")
    n_souls = len(obj.get("soul_scene_index") or [])
    click.echo(f"  souls:   {n_souls} restored from scene index")


@commit_group.command("branch")
@click.argument("name")
@_game_root_option
@_commits_root_option
def commit_branch(name: str, game_root: Path, commits_root: Path | None) -> None:
    """Fork HEAD onto a new branch NAME (M17 §3.2).

    Creates a divergent ref at HEAD, copies `playthrough.json`, mints
    fresh `instance_id`s, resets HEAD to the fork point. No merge (§3.3).
    """
    root = _resolve_commits_root(commits_root)
    try:
        at = branch_from_head(Path(game_root), root, name)
    except CommitSubsystemError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"✓ Branched {name!r} at {at}")
    click.echo("  Future commits with --branch " + name + " land on this divergent line.")


@commit_group.command("gc")
@_commits_root_option
@click.option(
    "--keep-tagged/--no-keep-tagged",
    default=True,
    show_default=True,
    help="Always retain tagged commits (M17 §4.2).",
)
@click.option("--keep-last", type=int, default=100, show_default=True, help="Retain the most-recent N reachable commits.")
def commit_gc(commits_root: Path | None, keep_tagged: bool, keep_last: int) -> None:
    """Reclaim unreachable commit objects and orphan blobs (M17 §4.2).

    Pure delegation to `commit_store.gc` — the reachability walk, the
    keep-last cap, and the tagged-preserve rule all live in the leaf.
    """
    root = _resolve_commits_root(commits_root)
    report = commit_store.gc(root, keep_tagged=keep_tagged, keep_last=keep_last)
    click.echo("✓ GC complete")
    click.echo(f"  commits:  kept {len(report.kept_commits)}  ·  deleted {len(report.deleted_commits)}")
    click.echo(f"  blobs:    kept {len(report.kept_blobs)}  ·  deleted {len(report.deleted_blobs)}")


@commit_group.command("verify")
@click.argument("commit_id")
@_commits_root_option
@click.option(
    "--scratch",
    "scratch_root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Scratch dir to rehydrate into (default: a tmp dir).",
)
def commit_verify(commit_id: str, commits_root: Path | None, scratch_root: Path | None) -> None:
    """Rehydrate COMMIT_ID and recompute its hash; report match/mismatch.

    M17 §5 replay-verify (single-machine first). Exit code is non-zero on
    mismatch so this is usable in CI / scripted regression checks.
    """
    import tempfile

    root = _resolve_commits_root(commits_root)
    if scratch_root is not None:
        result = _do_verify(root, commit_id, Path(scratch_root))
    else:
        with tempfile.TemporaryDirectory(prefix="neonrp-verify-") as td:
            result = _do_verify(root, commit_id, Path(td))

    if result.match:
        click.echo(f"✓ MATCH  {commit_id}")
        click.echo(f"  hash: {result.recorded_hash}")
        click.echo(
            f"  determinism: {result.determinism_status.upper()} — "
            f"{result.determinism_message}"
        )
        return
    click.echo(f"✗ MISMATCH  {commit_id}")
    click.echo(f"  recorded:   {result.recorded_hash}")
    click.echo(f"  recomputed: {result.recomputed_hash}")
    click.echo(
        f"  determinism: {result.determinism_status.upper()} — "
        f"{result.determinism_message}"
    )
    raise SystemExit(1)


def _do_verify(root: Path, commit_id: str, scratch: Path):
    try:
        return verify_commit(root, commit_id, scratch)
    except CommitSubsystemError as exc:
        raise click.ClickException(str(exc))


@commit_group.command("backfill")
@_game_root_option
@_commits_root_option
def commit_backfill(game_root: Path, commits_root: Path | None) -> None:
    """Synthesise a single commit for a legacy game dir (M17 §7).

    Treats the latest session state as ONE commit at
    `run_state.json.turn_count`, parent=null, branch=main. Games without
    a usable run_state are skipped with a warning (§7 step 3).
    """
    root = _resolve_commits_root(commits_root)
    try:
        result = backfill_game(Path(game_root), root)
    except CommitSubsystemError as exc:
        # §7 step 3: skip-with-warning rather than a hard failure.
        raise click.ClickException(str(exc))

    click.echo(f"✓ Backfilled {result.game_root.name}")
    click.echo(f"  commit:  {result.world_commit_id}")
    click.echo(f"  turn:    {result.turn_seq}  (single commit, parent=null, branch=main)")
