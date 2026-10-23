"""`neonrp soul upload / download / list` — SoulHub CLI.

Ergonomic alias group mirroring `commands/world_hub.py`. Souls share the
exact distribution infra as worlds (`neonrp.core.worldhub` already accepts
`kind="souls"` for every operation — see `docs/M16_SOULHUB_DESIGN.md` §4.1);
this group only adds a dedicated command surface with the kind hard-wired
so authors don't have to type `world ... --kind souls`. No new core code.

Helper reuse: `_render_entry_line` is imported verbatim from `world_hub`
since the registry entry shape is identical (M16 §4.1 — "no schema
bifurcation"). `_resolve_kind` is intentionally NOT reused: this group
has no `--kind` flag, so the literal `"souls"` is passed directly.
"""

from __future__ import annotations

from pathlib import Path

import click

from neonrp.commands.world_hub import _render_entry_line
from neonrp.core.worldhub import (
    WorldHubError,
    download,
    list_stories,
    registry_url,
    replace_cover_via_api,
    set_unlisted,
    upload_via_api,
)

# Hard-wired everywhere below. A constant (not a literal) so the intent
# is self-documenting and a future hub_base refactor has one anchor.
_SOUL_KIND = "souls"


@click.group("soul")
def soul_group() -> None:
    """SoulHub — publish and fetch character souls by slug+version (or hash)."""


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


@soul_group.command("upload")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--name", default=None, help="Display name (default: directory name)")
@click.option(
    "--slug",
    default=None,
    help="Logical soul id, used as the version handle. Default: slug derived from --name. "
         "Re-uploading under the same slug+version creates a sibling version entry.",
)
@click.option("--version", default="1.0", show_default=True, help="Version string for this build")
@click.option("--changelog", default="", help="One-line note explaining what changed in this version")
@click.option(
    "--unlisted",
    is_flag=True,
    default=False,
    help="Hide this entry from `soul list` and the launcher's character "
         "picker. Still reachable via `download <hash>` or `download <slug>@<version>`.",
)
@click.option(
    "--token",
    default=None,
    envvar="HUB_API_TOKEN",
    help="WorldHub session token from worldlines.gg/account (env: HUB_API_TOKEN).",
)
@click.option("--force", is_flag=True, default=False, help="Skip the public-listing gate (portrait, zh/en/ja/ko name+intro). Secrets are never skipped.")
@click.option(
    "--api-url",
    default=None,
    envvar="HUB_API_URL",
    help="WorldHub API base URL (env: HUB_API_URL, default: https://api.worldlines.gg).",
)
def soul_upload(
    path: Path,
    name: str | None,
    slug: str | None,
    version: str,
    changelog: str,
    unlisted: bool,
    token: str | None,
    force: bool,
    api_url: str | None,
) -> None:
    """Zip, upload, and register a soul. Returns the SoulHub hash.

    Posts the bundle to the WorldHub API — no AWS credentials needed.
    Get your session token at https://worldlines.gg/account and set it
    as HUB_API_TOKEN, or pass --token.

    Examples:

    \b
      neonrp soul upload souls/elena --slug elena --version 2.0
      neonrp soul upload ./elena --slug elena --version 2.1 --changelog "richer persona"
      neonrp soul upload souls/elena --slug elena --version 2.0 --unlisted
    """
    _publish_gate(path, _SOUL_KIND, unlisted=unlisted, force=force)
    try:
        entry = upload_via_api(
            path,
            kind=_SOUL_KIND,
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
        click.echo("  unlisted:   yes  (hidden from `soul list` / launcher picker)")
    if entry.get("changelog"):
        click.echo(f"  changelog:  {entry['changelog']}")
    click.echo()
    click.echo("Share any of these:")
    click.echo(f"  worldlines soul download {entry['slug']}                # latest")
    click.echo(f"  worldlines soul download {entry['slug']}@{entry['version']}            # this exact version")
    click.echo(f"  worldlines soul download {entry['hash']}            # by hash")


@soul_group.command("cover")
@click.argument("slug")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
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
def soul_cover(
    slug: str,
    image: Path,
    token: str | None,
    api_url: str | None,
) -> None:
    """Replace the cover image of a soul you published.

    Goes through the WorldHub API (no AWS creds) — you must own the slug.

    \b
      worldlines soul cover elena ./new-cover.png
    """
    try:
        result = replace_cover_via_api(
            _SOUL_KIND, slug, image, api_token=token, api_url=api_url
        )
    except WorldHubError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"✓ Cover updated — {slug}")
    click.echo(f"  cover_url:  {result['cover_url']}")


@soul_group.command("download")
@click.argument("query")
def soul_download(query: str) -> None:
    """Fetch a soul from SoulHub.

    QUERY may be:

    \b
      elena               → latest version of slug "elena"
      elena@1.0           → that exact version
      b54b307b50ef        → direct hash (full or unambiguous prefix)
    """
    try:
        target = download(query, kind=_SOUL_KIND)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"✓ Downloaded into: {target}")
    click.echo("  Open the launcher (`worldlines`) and pick it from the character picker.")


@soul_group.command("list")
@click.option("--all", "show_all", is_flag=True, help="Show every version, not just the latest per slug.")
def soul_list(show_all: bool) -> None:
    """Show souls published to SoulHub, grouped by slug."""
    try:
        stories = list_stories(kind=_SOUL_KIND)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    if not stories:
        click.echo(f"(no entries at {registry_url(_SOUL_KIND)})")
        return

    click.echo(f"{len(stories)} soul{'' if len(stories) == 1 else 's'} on SoulHub  ·  {_SOUL_KIND}")
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


@soul_group.command("unlist")
@click.argument("query")
def soul_unlist(query: str) -> None:
    """Hide matching entries from the public listing.

    QUERY accepts the same forms as `download`:

    \b
      elena               → every version of that slug
      elena@2.0           → just that version
      b54b307b50ef        → a single hash (prefix ok)

    Hidden entries still download via slug or hash; they just don't
    appear in `soul list` or the launcher's character picker.

    Requires a WorldHub session token (--token or HUB_API_TOKEN).
    """
    try:
        changed = set_unlisted(query, kind=_SOUL_KIND, unlisted=True)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    if not changed:
        click.echo("(nothing changed — matched entries are already unlisted)")
        return

    click.echo(f"✓ Unlisted {len(changed)} entr{'y' if len(changed) == 1 else 'ies'}:")
    for e in changed:
        click.echo(_render_entry_line(e))


@soul_group.command("relist")
@click.argument("query")
def soul_relist(query: str) -> None:
    """Restore matching entries to the public listing.

    Inverse of `unlist`; same QUERY forms.
    """
    try:
        changed = set_unlisted(query, kind=_SOUL_KIND, unlisted=False)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))

    if not changed:
        click.echo("(nothing changed — matched entries are already listed)")
        return

    click.echo(f"✓ Relisted {len(changed)} entr{'y' if len(changed) == 1 else 'ies'}:")
    for e in changed:
        click.echo(_render_entry_line(e))
