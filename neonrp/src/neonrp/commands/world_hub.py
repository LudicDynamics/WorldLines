"""`neonrp world upload / download / list` — WorldHub CLI.

Same command group is reused for souls via `--kind soul` (alias for
the `souls` S3 prefix). A dedicated `soul` group will mirror this
when SoulHub onboarding ships (M-5).
"""

from __future__ import annotations

from pathlib import Path

import click

from neonrp.core.worldhub import (
    HUB_KINDS,
    WorldHubError,
    download,
    list_stories,
    registry_url,
    replace_cover_via_api,
    set_unlisted,
    upload_via_api,
)

_KIND_ALIASES = {"world": "worlds", "soul": "souls"}


def _resolve_kind(kind: str) -> str:
    """Accept singular ('world','soul') or plural ('worlds','souls')."""
    k = kind.lower().strip()
    return _KIND_ALIASES.get(k, k)


@click.group("world")
def world_group() -> None:
    """WorldHub — publish and fetch worldlines worlds by slug+version (or hash)."""


def _publish_gate(path: Path, kind: str, *, unlisted: bool, force: bool) -> None:
    """Nothing with a key inside ships, and nothing goes
    PUBLIC without every picture and all four languages. Drafts
    (--unlisted) only need the secrets scan; --force skips the public gate
    (never the secrets scan)."""
    from neonrp.core.worldhub import validate_for_upload

    check = validate_for_upload(Path(path), kind=kind)
    if check.secrets:
        files = sorted({str(h.get("path")) for h in check.secrets})
        raise click.ClickException(
            "Refusing to upload: key-shaped strings / credential files would ship —\n  "
            + "\n  ".join(files)
        )
    if unlisted or force:
        return
    blockers = [e for e in check.errors if e != "check.secret_found"] + list(check.publish_blockers)
    if not blockers:
        return
    lines = []
    for key in blockers:
        if key == "check.i18n_missing":
            lines.append(f"title/description missing in: {', '.join(check.missing_langs)}")
        elif key == "check.souls_no_portrait":
            lines.append(f"characters without a portrait: {', '.join(check.souls_without_portrait)}")
        else:
            lines.append(key.removeprefix("check."))
    raise click.ClickException(
        "Not ready for a PUBLIC listing:\n  " + "\n  ".join(lines)
        + "\nUpload it as a draft with --unlisted (then submit for review from the Hub), or pass --force."
    )


@world_group.command("upload")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--name", default=None, help="Display name (default: directory name)")
@click.option(
    "--slug",
    default=None,
    help="Logical story id, used as the version handle. Default: slug derived from --name. "
         "Re-uploading under the same slug+version creates a sibling version entry.",
)
@click.option("--version", default="1.0", show_default=True, help="Version string for this build")
@click.option("--changelog", default="", help="One-line note explaining what changed in this version")
@click.option(
    "--kind",
    type=click.Choice(list(HUB_KINDS) + list(_KIND_ALIASES.keys()), case_sensitive=False),
    default="worlds",
    show_default=True,
    help="Which hub: 'worlds' (default) or 'souls'.",
)
@click.option(
    "--unlisted",
    is_flag=True,
    default=False,
    help="Hide this entry from `world list` and the launcher's WorldHub "
         "picker. Still reachable via `download <hash>` or `download <slug>@<version>`.",
)
@click.option(
    "--token",
    default=None,
    envvar="HUB_API_TOKEN",
    help="WorldHub session token from worldlines.gg/account (env: HUB_API_TOKEN).",
)
@click.option("--force", is_flag=True, default=False, help="Skip the public-listing gate (pictures, zh/en/ja/ko title+description). Secrets are never skipped.")
@click.option(
    "--api-url",
    default=None,
    envvar="HUB_API_URL",
    help="WorldHub API base URL (env: HUB_API_URL, default: https://api.worldlines.gg).",
)
def world_upload(
    path: Path,
    name: str | None,
    slug: str | None,
    version: str,
    changelog: str,
    kind: str,
    unlisted: bool,
    token: str | None,
    force: bool,
    api_url: str | None,
) -> None:
    """Zip, upload, and register a world. Returns the WorldHub hash.

    Posts the bundle to the WorldHub API — no AWS credentials needed.
    Get your session token at https://worldlines.gg/account and set it
    as HUB_API_TOKEN, or pass --token.

    Examples:

    \b
      neonrp world upload worldlines/examples/worlds/dark-train --slug dark-train --version 2.0
      neonrp world upload ./mod --slug dark-train --version 2.1 --changelog "fix carriage 4 puzzle"
      neonrp world upload worldlines/examples/worlds/dark-train --slug dark-train --version 2.0 --unlisted
    """
    kind_resolved = _resolve_kind(kind)
    _publish_gate(path, kind_resolved, unlisted=unlisted, force=force)
    try:
        entry = upload_via_api(
            path,
            kind=kind_resolved,
            name=name,
            slug=slug,
            version=version,
            changelog=changelog,
            unlisted=unlisted,
            api_token=token,
            api_url=api_url,
        )
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"✓ Uploaded — {entry['name']}  ·  {entry['slug']}@{entry['version']}")
    click.echo(f"  hash:       {entry['hash']}")
    click.echo(f"  size:       {entry['size_bytes']:,} bytes")
    click.echo(f"  url:        {entry['url']}")
    if entry.get("unlisted"):
        click.echo("  unlisted:   yes  (hidden from `world list` / launcher picker)")
    if entry.get("changelog"):
        click.echo(f"  changelog:  {entry['changelog']}")
    click.echo()
    click.echo("Share any of these:")
    click.echo(f"  worldlines world download {entry['slug']}                # latest")
    click.echo(f"  worldlines world download {entry['slug']}@{entry['version']}            # this exact version")
    click.echo(f"  worldlines world download {entry['hash']}            # by hash")


@world_group.command("cover")
@click.argument("slug")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--kind",
    type=click.Choice(list(HUB_KINDS) + list(_KIND_ALIASES.keys()), case_sensitive=False),
    default="worlds",
    show_default=True,
    help="Which hub: 'worlds' (default) or 'souls'.",
)
@click.option(
    "--token",
    default=None,
    envvar="HUB_API_TOKEN",
    help="WorldHub session token from worldlines.gg/account (env: HUB_API_TOKEN).",
)
@click.option(
    "--api-url",
    default=None,
    envvar="HUB_API_URL",
    help="WorldHub API base URL (env: HUB_API_URL, default: https://api.worldlines.gg).",
)
def world_cover(
    slug: str,
    image: Path,
    kind: str,
    token: str | None,
    api_url: str | None,
) -> None:
    """Replace the cover image of a world you published.

    Goes through the WorldHub API (no AWS creds) — you must own the slug.

    \b
      worldlines world cover dark-train ./new-cover.png
    """
    kind_resolved = _resolve_kind(kind)
    try:
        result = replace_cover_via_api(
            kind_resolved, slug, image, api_token=token, api_url=api_url
        )
    except WorldHubError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"✓ Cover updated — {slug}")
    click.echo(f"  cover_url:  {result['cover_url']}")


@world_group.command("download")
@click.argument("query")
@click.option(
    "--kind",
    type=click.Choice(list(HUB_KINDS) + list(_KIND_ALIASES.keys()), case_sensitive=False),
    default="worlds",
    show_default=True,
    help="Which hub to query.",
)
def world_download(query: str, kind: str) -> None:
    """Fetch a world from WorldHub.

    QUERY may be:

    \b
      dark-train          → latest version of slug "dark-train"
      dark-train@1.0      → that exact version
      e38aff4819a0        → direct hash (full or unambiguous prefix)
    """
    kind_resolved = _resolve_kind(kind)
    try:
        target = download(query, kind=kind_resolved)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"✓ Downloaded into: {target}")
    click.echo("  Open the launcher (`worldlines`) and pick it from continue.")


@world_group.command("list")
@click.option(
    "--kind",
    type=click.Choice(list(HUB_KINDS) + list(_KIND_ALIASES.keys()), case_sensitive=False),
    default="worlds",
    show_default=True,
)
@click.option("--all", "show_all", is_flag=True, help="Show every version, not just the latest per slug.")
def world_list(kind: str, show_all: bool) -> None:
    """Show worlds published to WorldHub, grouped by slug."""
    kind_resolved = _resolve_kind(kind)
    try:
        stories = list_stories(kind=kind_resolved)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    if not stories:
        click.echo(f"(no entries at {registry_url(kind_resolved)})")
        return

    click.echo(f"{len(stories)} stor{'y' if len(stories) == 1 else 'ies'} on WorldHub  ·  {kind_resolved}")
    click.echo()
    for story in stories:
        latest = story["versions"][0]
        size_mb = latest.get("size_bytes", 0) / (1024 * 1024)
        click.echo(
            f"  {story['slug']:<28}  "
            f"{story['display_name']:<36}  "
            f"latest v{story['latest_version']:<6}  "
            f"{size_mb:>5.2f} MB   {story['latest_hash']}"
        )
        if show_all and len(story["versions"]) > 1:
            for v in story["versions"][1:]:
                sm = v.get("size_bytes", 0) / (1024 * 1024)
                click.echo(
                    f"    · v{v.get('version', '?'):<6}  {sm:>5.2f} MB   {v.get('hash', '')}"
                    + (f"   {v['changelog']}" if v.get("changelog") else "")
                )


def _render_entry_line(e: dict) -> str:
    slug = e.get("slug", "?")
    version = e.get("version", "?")
    hash_short = e.get("hash", "")
    return f"  · {slug}@{version}  hash={hash_short}"


@world_group.command("unlist")
@click.argument("query")
@click.option(
    "--kind",
    type=click.Choice(list(HUB_KINDS) + list(_KIND_ALIASES.keys()), case_sensitive=False),
    default="worlds",
    show_default=True,
)
def world_unlist(query: str, kind: str) -> None:
    """Hide matching entries from the public listing.

    QUERY accepts the same forms as `download`:

    \b
      dark-train          → every version of that slug
      dark-train@2.0      → just that version
      b54b307b50ef        → a single hash (prefix ok)

    Hidden entries still download via slug or hash; they just don't
    appear in `world list` or the launcher's WorldHub picker.

    Requires a WorldHub session token (--token or HUB_API_TOKEN).
    """
    kind_resolved = _resolve_kind(kind)
    try:
        changed = set_unlisted(query, kind=kind_resolved, unlisted=True)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    if not changed:
        click.echo("(nothing changed — matched entries are already unlisted)")
        return

    click.echo(f"✓ Unlisted {len(changed)} entr{'y' if len(changed) == 1 else 'ies'}:")
    for e in changed:
        click.echo(_render_entry_line(e))


@world_group.command("relist")
@click.argument("query")
@click.option(
    "--kind",
    type=click.Choice(list(HUB_KINDS) + list(_KIND_ALIASES.keys()), case_sensitive=False),
    default="worlds",
    show_default=True,
)
def world_relist(query: str, kind: str) -> None:
    """Restore matching entries to the public listing.

    Inverse of `unlist`; same QUERY forms.
    """
    kind_resolved = _resolve_kind(kind)
    try:
        changed = set_unlisted(query, kind=kind_resolved, unlisted=False)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    if not changed:
        click.echo("(nothing changed — matched entries are already listed)")
        return

    click.echo(f"✓ Relisted {len(changed)} entr{'y' if len(changed) == 1 else 'ies'}:")
    for e in changed:
        click.echo(_render_entry_line(e))
