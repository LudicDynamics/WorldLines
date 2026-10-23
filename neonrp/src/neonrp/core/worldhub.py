"""WorldHub — distribute worldlines worlds and souls via hash-addressable
registries, with slug-based versioning so the same story can ship
multiple versions side by side.

Layout (single S3 bucket, two prefixes):

    s3://worldlines-hub/worlds/index.json          (world registry)
    s3://worldlines-hub/worlds/<hash>.zip          (world bundles)
    s3://worldlines-hub/souls/index.json           (soul registry — same shape)
    s3://worldlines-hub/souls/<hash>.zip           (soul bundles)

Registry entry shape (schema_version: 1):

    {
      "hash":       "12-char sha256 prefix of the zip",
      "slug":       "dark-train",                  # logical story id
      "name":       "Dark Train",                  # display name
      "version":    "2.0",                          # caller-supplied
      "changelog":  "switched from d20 to BRP", # optional
      "url":        "https://...zip",
      "size_bytes": 103988,
      "uploaded_at":"2026-05-13T12:34:56+00:00"
    }

Upload (via WorldHub API — no AWS creds needed on client):

    zip dir → compute hash → derive slug
    → POST multipart to api.worldlines.gg/api/v1/me/upload
    → server validates, mints slug, pushes to S3 (Hub-9)

Upload (legacy boto3 direct — server-side only, requires AWS creds):

    zip dir → compute hash → PUT zip to s3 → append entry to index.json

Download (no auth, S3 public read):

    parse query → fetch index.json → resolve to (slug, version, hash)
    → GET zip → verify hash → extract via load_world_zip

Query forms:

    "dark-train"        → slug, latest version (by uploaded_at desc)
    "dark-train@1.0"    → slug, exact version
    "538d19b9e55e"      → direct hash (legacy / specific build)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neonrp.core.world_export import export_world, load_world_zip

logger = logging.getLogger(__name__)

HUB_BUCKET = "worldlines-hub"
HUB_REGION = "ap-northeast-1"
HUB_KINDS = ("worlds", "souls")
WORLDHUB_META_FILENAME = ".worldhub.json"
# A restored hosted-play save carries this marker (written by the play
# gateway) instead of .worldhub.json — its presence means "run", not "source".
SESSION_META_FILENAME = ".session-meta.json"
HASH_LEN = 12  # sha256[:12] — < 2^-48 collision probability
SCHEMA_VERSION = 1


class WorldHubError(Exception):
    """WorldHub operation failed."""


# ---------------------------------------------------------------------------
# URL helpers — keep the bucket/region/prefix knobs in one place.
# ---------------------------------------------------------------------------

def _kind_prefix(kind: str) -> str:
    if kind not in HUB_KINDS:
        raise WorldHubError(f"unknown kind: {kind!r} (must be one of {HUB_KINDS})")
    return kind


def _hub_base() -> str:
    """Registry 基址。默认公网 S3;`WORLDHUB_REGISTRY_BASE` 覆盖 —— hosted
    沙盒/本地 hub 栈把引擎指向自己的 registry(HUB-GOLIVE §P1/P2 隔离)。"""
    override = os.environ.get("WORLDHUB_REGISTRY_BASE", "").strip().rstrip("/")
    return override or f"https://{HUB_BUCKET}.s3.{HUB_REGION}.amazonaws.com"


def registry_url(kind: str = "worlds") -> str:
    return f"{_hub_base()}/{_kind_prefix(kind)}/index.json"


def _registry_api_base() -> str | None:
    """审查线 API 基址(HUB-GOLIVE §P5)。显式 `WORLDHUB_REGISTRY_API`
    优先;否则从 `WORLDHUB_REGISTRY_BASE` 的 /hubindex 形态推导(hub 栈
    的 nginx 同时代理两者)。公网 S3 形态下无 API → None。"""
    explicit = os.environ.get("WORLDHUB_REGISTRY_API", "").strip().rstrip("/")
    if explicit:
        return explicit
    base = os.environ.get("WORLDHUB_REGISTRY_BASE", "").strip().rstrip("/")
    if base.endswith("/hubindex"):
        return base[: -len("/hubindex")] + "/api/v1/registry"
    return None


def submit_for_review(
    source_path: Path,
    *,
    kind: str = "worlds",
    name: str | None = None,
    slug: str | None = None,
    summary: str = "",
    version: str = "1.0",
) -> dict[str, Any]:
    """把本地世界/soul 打包提交进 Hub 审查队列(pending 三态,后台
    审)。zip 原样 POST 给 registry 的 submit 面;uploader 取沙盒引擎
    烙入的账户 uid(SANDBOX_TRUSTED_UID_HEADER),本地直跑则为 local。"""
    api = _registry_api_base()
    if not api:
        raise WorldHubError(
            "no review API configured (WORLDHUB_REGISTRY_API / hub-stack "
            "WORLDHUB_REGISTRY_BASE required)"
        )
    _kind_prefix(kind)
    zip_path = _zip_world_for_upload(source_path)
    try:
        import urllib.parse
        import urllib.request

        uploader = os.environ.get("SANDBOX_TRUSTED_UID_HEADER", "").strip() or "local"
        q = urllib.parse.urlencode(
            {
                "kind": kind,
                "name": name or source_path.name,
                "slug": slug or "",
                "summary": summary,
                "version": version,
                "uploader": uploader,
            }
        )
        req = urllib.request.Request(
            f"{api}/submit?{q}",
            data=zip_path.read_bytes(),
            headers={"Content-Type": "application/zip"},
            method="POST",
        )
        token = os.environ.get("HUB_REGISTRY_TOKEN", "").strip()
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except OSError as exc:
        raise WorldHubError(f"submit failed: {exc}") from exc
    finally:
        import shutil

        shutil.rmtree(zip_path.parent, ignore_errors=True)


def _zip_url(hash_short: str, kind: str) -> str:
    return f"{_hub_base()}/{_kind_prefix(kind)}/{hash_short}.zip"


def _zip_s3_key(hash_short: str, kind: str) -> str:
    return f"{_kind_prefix(kind)}/{hash_short}.zip"


def _index_s3_key(kind: str) -> str:
    return f"{_kind_prefix(kind)}/index.json"


# ---------------------------------------------------------------------------
# Hashing + slug helpers.
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_hash(zip_path: Path) -> str:
    """12-char SHA256 prefix for the zip file."""
    return _sha256_file(zip_path)[:HASH_LEN]


_SLUG_NON_ALPHANUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a display name to a stable slug.

    "Dark Train (BRP)" → "dark-train-brp"
    "暗夜列车" → "" (non-ascii lost) — caller must supply --slug then.
    """
    lowered = name.strip().lower()
    slug = _SLUG_NON_ALPHANUM.sub("-", lowered).strip("-")
    return slug


# ---------------------------------------------------------------------------
# Bootstrap + zip helpers (template dir → playable game dir → zip).
# ---------------------------------------------------------------------------

def _bootstrap_neonrp(world_dir: Path) -> None:
    """Add a minimal `.neonrp/` to a template-style world dir so the
    resulting archive passes `load_world_zip`'s manifest check.
    """
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path
    from neonrp.core.storage import atomic_write_json, ensure_dirs

    ensure_dirs(world_dir)
    manifest_path = get_manifest_path(world_dir)
    if not manifest_path.exists():
        atomic_write_json(manifest_path, Manifest().model_dump())

    src_contract = world_dir / "runtime_contract.json"
    nested_contract = world_dir / ".neonrp" / "runtime_contract.json"
    if src_contract.exists() and not nested_contract.exists():
        nested_contract.write_text(src_contract.read_text(encoding="utf-8"), encoding="utf-8")


def _zip_world_for_upload(source: Path) -> Path:
    """Return a tmp .zip ready for S3. Template-style sources (no
    `.neonrp/`) are copied to a tmp dir and bootstrapped first.
    """
    source = source.resolve()
    if not source.is_dir():
        raise WorldHubError(f"Not a directory: {source}")

    if (source / ".neonrp").is_dir():
        out = Path(tempfile.mkdtemp(prefix="worldhub-")) / f"{source.name}.zip"
        return export_world(source, output_path=out, include_logs=False)

    tmp_root = Path(tempfile.mkdtemp(prefix="worldhub-"))
    work = tmp_root / source.name
    shutil.copytree(source, work)
    _bootstrap_neonrp(work)
    out = tmp_root / f"{source.name}.zip"
    return export_world(work, output_path=out, include_logs=False)


# ---------------------------------------------------------------------------
# Registry IO.
# ---------------------------------------------------------------------------

def read_registry(kind: str = "worlds") -> dict[str, Any]:
    """Fetch the public registry. Missing → empty skeleton."""
    url = registry_url(kind)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _empty_registry(kind)
        raise WorldHubError(f"Failed to fetch registry: {exc}") from exc
    except Exception as exc:
        raise WorldHubError(f"Failed to fetch registry: {exc}") from exc

    return _normalize_registry(data, kind)


def _empty_registry(kind: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "kind": kind, kind: []}


def _normalize_registry(raw: dict[str, Any], kind: str) -> dict[str, Any]:
    """Accept either the old (no schema_version, flat list under 'worlds')
    or the new shape, return a normalised v1 dict with `kind` and entry
    list keyed by `kind`.

    Also backfills `slug` (derived from `name`) on entries missing it,
    so older uploads remain queryable by slug.
    """
    if not isinstance(raw, dict):
        return _empty_registry(kind)

    entries_key = kind
    entries = raw.get(entries_key)
    if not isinstance(entries, list):
        # Legacy: some old registries used the key "worlds" regardless of kind.
        entries = raw.get("worlds") if isinstance(raw.get("worlds"), list) else []

    normalised: list[dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if "slug" not in e or not e["slug"]:
            e["slug"] = slugify(str(e.get("name", e.get("hash", "unknown"))))
        if "changelog" not in e:
            e["changelog"] = ""
        normalised.append(e)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        entries_key: normalised,
    }


# ---------------------------------------------------------------------------
# Upload.
# ---------------------------------------------------------------------------

def upload(
    source_path: Path,
    *,
    kind: str = "worlds",
    name: str | None = None,
    slug: str | None = None,
    version: str = "1.0",
    changelog: str = "",
    unlisted: bool = False,
) -> dict[str, Any]:
    """Zip → upload → register. Returns the new registry entry.

    - If `slug` is None, derive from `name` (or directory name).
    - `kind` is "worlds" or "souls"; controls the S3 prefix + registry.
    - Idempotent by hash: re-uploading identical content under the same
      slug+version replaces that entry. Different hash → new entry.
    - `unlisted=True` marks the entry hidden — ``list_stories`` skips
      it, but ``resolve()`` still finds it by hash or by slug@version.
      Use for share-by-hash distribution.
    """
    _kind_prefix(kind)  # validate

    try:
        import boto3
    except ImportError as exc:
        raise WorldHubError(
            "boto3 required for upload. Install with `uv pip install -e \".[hub-publish]\"`."
        ) from exc

    display_name = name or source_path.name
    final_slug = (slug or slugify(display_name)).strip()
    if not final_slug:
        raise WorldHubError(
            f"Could not derive a slug from name {display_name!r}. Pass --slug explicitly."
        )

    # Discover a cover image before zipping — the source may be a
    # template dir; images sit in assets/ / art/ / media/ etc.
    cover_path: Path | None = None
    cover_ext: str = ""
    try:
        from neonrp.core.image_render import discover_world_images

        _imgs = discover_world_images(source_path)
        if _imgs:
            cover_path = _imgs[0]
            cover_ext = cover_path.suffix.lower().lstrip(".")
    except Exception:  # noqa: BLE001 — image discovery is best-effort
        logger.debug("cover discovery skipped", exc_info=True)

    zip_path = _zip_world_for_upload(source_path)
    try:
        hash_short = compute_hash(zip_path)
        size_bytes = zip_path.stat().st_size

        s3 = boto3.client("s3", region_name=HUB_REGION)
        s3.upload_file(
            str(zip_path),
            HUB_BUCKET,
            _zip_s3_key(hash_short, kind),
            ExtraArgs={"ContentType": "application/zip"},
        )

        cover_url: str | None = None
        if cover_path is not None and cover_path.is_file():
            cover_key = f"{_kind_prefix(kind)}/{hash_short}-cover.{cover_ext}"
            _ct = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
            }.get(cover_ext, "image/png")
            try:
                s3.upload_file(
                    str(cover_path),
                    HUB_BUCKET,
                    cover_key,
                    ExtraArgs={"ContentType": _ct},
                )
                cover_url = (
                    f"https://{HUB_BUCKET}.s3.{HUB_REGION}.amazonaws.com/{cover_key}"
                )
            except Exception:  # noqa: BLE001 — cover is best-effort
                logger.debug("cover upload skipped", exc_info=True)

        registry = read_registry(kind)
        entries: list[dict[str, Any]] = registry[kind]

        entry = {
            "hash": hash_short,
            "slug": final_slug,
            "name": display_name,
            "version": version,
            "changelog": changelog,
            "url": _zip_url(hash_short, kind),
            "size_bytes": size_bytes,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        if cover_url:
            entry["cover_url"] = cover_url
        if unlisted:
            entry["unlisted"] = True
        # Idempotent: replace any prior entry sharing this hash.
        registry[kind] = [w for w in entries if w.get("hash") != hash_short] + [entry]

        s3.put_object(
            Bucket=HUB_BUCKET,
            Key=_index_s3_key(kind),
            Body=json.dumps(registry, indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
            CacheControl="public, max-age=60",
        )

        return entry
    finally:
        shutil.rmtree(zip_path.parent, ignore_errors=True)


# Back-compat alias (unchanged semantics for worlds kind).
def upload_world(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return upload(*args, kind="worlds", **kwargs)


# ---------------------------------------------------------------------------
# API-based upload (no AWS creds on the client — Hub-9).
# ---------------------------------------------------------------------------

def _encode_multipart_fields(
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    boundary: str,
    file_content_type: str = "application/zip",
) -> bytes:
    """Build a multipart/form-data body (stdlib only, no extra deps)."""
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        parts.append(f"{value}\r\n".encode())

    filename = file_path.name
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {file_content_type}\r\n\r\n".encode())
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts)


def upload_via_api(
    source_path: Path,
    *,
    kind: str = "worlds",
    name: str | None = None,
    slug: str | None = None,
    version: str = "1.0",
    changelog: str = "",
    unlisted: bool = False,
    api_url: str | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Zip → POST to WorldHub API → server-side S3 upload.

    No AWS credentials needed on the client. Requires a WorldHub session
    token from ``hub.worldlines.gg/account`` (set ``HUB_API_TOKEN`` env var
    or pass ``api_token``).

    The API validates the zip, mints a globally-unique slug, pushes to S3,
    and returns the registry entry — same shape as ``upload()``.
    """
    _kind_prefix(kind)

    token = api_token or os.environ.get("HUB_API_TOKEN", "").strip()
    if not token:
        raise WorldHubError(
            "HUB_API_TOKEN is required. Get your session token at "
            "https://hub.worldlines.gg/account and set it as HUB_API_TOKEN "
            "environment variable, or pass --token to the CLI."
        )

    base_url = (
        api_url or os.environ.get("HUB_API_URL", "https://api.worldlines.gg")
    ).rstrip("/")

    # Map "worlds"/"souls" to "world"/"soul" for the API's kind parameter.
    api_kind = "world" if kind == "worlds" else "soul"

    display_name = name or source_path.name
    final_slug = (slug or slugify(display_name)).strip()
    if not final_slug:
        raise WorldHubError(
            f"Could not derive a slug from name {display_name!r}. Pass --slug explicitly."
        )

    zip_path = _zip_world_for_upload(source_path)
    try:
        fields: dict[str, str] = {
            "kind": api_kind,
            "name": display_name,
            "version": version,
            "changelog": changelog or "",
            "unlisted": "true" if unlisted else "false",
        }
        if final_slug:
            fields["slug"] = final_slug
        return _post_bundle(zip_path, fields, token=token, base_url=base_url)
    finally:
        try:
            zip_path.unlink()
        except OSError:
            pass


def _post_bundle(zip_path: Path, fields: dict[str, str], *, token: str, base_url: str) -> dict[str, Any]:
    """Multipart POST of one bundle to ``/api/v1/me/upload``; returns the
    registry entry (plus ``status`` / ``precheck`` when the gateway sends them)."""
    boundary = "----WorldHubBoundary"
    body = _encode_multipart_fields(
        fields, file_field="file", file_path=zip_path, boundary=boundary
    )
    url = f"{base_url}/api/v1/me/upload"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        if exc.code == 401:
            raise WorldHubError(
                "Authentication failed — your session token may have expired. "
                "Get a new one at https://hub.worldlines.gg/account"
            ) from exc
        if exc.code == 413:
            raise WorldHubError(
                "File too large — the bundle exceeds the WorldHub size limit."
            ) from exc
        if exc.code == 422 and "secret_found" in detail:
            raise WorldHubError(
                "The hub refused the bundle: it contains key-shaped strings or "
                f"credential files. {detail}"
            ) from exc
        raise WorldHubError(
            f"WorldHub API error {exc.code}: {detail or 'no details'}"
        ) from exc

    if not isinstance(result, dict):
        raise WorldHubError(f"Unexpected API response: {result}")

    entry = result.get("entry")
    if entry and isinstance(entry, dict):
        for k in ("status", "precheck", "warnings"):
            if k in result and k not in entry:
                entry[k] = result[k]
        return entry

    if result.get("dry_run"):
        raise WorldHubError(
            "WorldHub publishing is not enabled on the server. "
            "Ask the hub maintainer to set HUB_PUBLISH_ENABLED=1."
        )
    raise WorldHubError(f"Unexpected API response: {result}")


def upload_replay_via_api(
    run_dir: Path,
    *,
    name: str | None = None,
    lang: str = "zh",
    uploader: str = "",
    cover: Path | None = None,
    api_url: str | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Pack a saved run as a Replay Bundle and upload it (kind=replay).

    Lands as a draft like everything else; the Hub's review makes it
    public in the 回放馆. Nothing but story / feed / backstage / cover
    leaves the machine (see :mod:`neonrp.core.replay_export`).
    """
    import tempfile

    from neonrp.core.replay_export import ReplayExportError, build_replay_bundle

    token = api_token or os.environ.get("HUB_API_TOKEN", "").strip()
    if not token:
        raise WorldHubError(
            "HUB_API_TOKEN is required. Get your session token at "
            "https://hub.worldlines.gg/account and set it as HUB_API_TOKEN "
            "environment variable, or pass --token to the CLI."
        )
    base_url = (api_url or os.environ.get("HUB_API_URL", "https://api.worldlines.gg")).rstrip("/")
    run_dir = Path(run_dir).expanduser().resolve()
    tmp = Path(tempfile.mkdtemp(prefix="replay-")) / "replay.zip"
    try:
        try:
            meta = build_replay_bundle(run_dir, tmp, uploader=uploader, lang=lang, cover=cover)
        except ReplayExportError as exc:
            raise WorldHubError(str(exc)) from exc
        world = meta.get("world") or {}
        display_name = (name or "").strip() or f"{world.get('name') or world.get('slug')} · replay"
        fields = {
            "kind": "replay",
            "name": display_name,
            "version": "1.0",
            "changelog": f"{meta.get('turns', 0)} turns",
            "unlisted": "true",
            "slug": f"{world.get('slug') or 'world'}-replay-{datetime.now(timezone.utc):%Y%m%d%H%M}",
            **({"world_ref": meta["world_ref"]} if meta.get("world_ref") else {}),
        }
        entry = _post_bundle(tmp, fields, token=token, base_url=base_url)
        entry.setdefault("world", world)
        entry.setdefault("turns", meta.get("turns"))
        if meta.get("world_ref"):
            entry.setdefault("world_ref", meta["world_ref"])
        return entry
    finally:
        try:
            tmp.unlink()
            tmp.parent.rmdir()
        except OSError:
            pass


_COVER_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def replace_cover_via_api(
    kind: str,
    slug: str,
    image_path: Path,
    *,
    api_url: str | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """Replace the cover of a published asset you own, via the WorldHub
    API. The server uploads to S3 and patches index.json — no AWS creds
    on the client. Requires a session token (HUB_API_TOKEN or api_token).

    Returns the API response ``{"kind", "slug", "cover_url"}``.
    """
    _kind_prefix(kind)
    image_path = Path(image_path)
    if not image_path.is_file():
        raise WorldHubError(f"cover image not found: {image_path}")
    ext = image_path.suffix.lower().lstrip(".")
    content_type = _COVER_CONTENT_TYPES.get(ext)
    if not content_type:
        raise WorldHubError(
            f"unsupported image type {ext!r} — use png, jpg, or webp"
        )

    token = api_token or os.environ.get("HUB_API_TOKEN", "").strip()
    if not token:
        raise WorldHubError(
            "HUB_API_TOKEN is required. Get your session token at "
            "https://hub.worldlines.gg/account and set it as HUB_API_TOKEN "
            "environment variable, or pass --token to the CLI."
        )
    base_url = (
        api_url or os.environ.get("HUB_API_URL", "https://api.worldlines.gg")
    ).rstrip("/")
    api_kind = "world" if kind in ("worlds", "world") else "soul"

    boundary = "----WorldHubCoverBoundary"
    body = _encode_multipart_fields(
        {},
        file_field="file",
        file_path=image_path,
        boundary=boundary,
        file_content_type=content_type,
    )
    url = f"{base_url}/api/v1/me/published/{api_kind}/{slug}/cover"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        if exc.code == 401:
            raise WorldHubError(
                "Authentication failed — your session token may have expired. "
                "Get a new one at https://hub.worldlines.gg/account"
            ) from exc
        if exc.code == 404:
            raise WorldHubError(
                f"You don't own a published {api_kind} with slug {slug!r} "
                "(publish it first, then set its cover)."
            ) from exc
        raise WorldHubError(
            f"WorldHub API error {exc.code}: {detail or 'no details'}"
        ) from exc

    if not isinstance(result, dict) or not result.get("cover_url"):
        raise WorldHubError(f"Unexpected API response: {result}")
    return result


def set_unlisted(
    query: str,
    *,
    kind: str = "worlds",
    unlisted: bool,
) -> list[dict[str, Any]]:
    """Flip the ``unlisted`` flag on registry entries matching ``query``.

    Query forms (same as ``download``):
      - ``"dark-train"``     → every entry of that slug;
      - ``"dark-train@2.0"`` → just that version;
      - ``"<hash-prefix>"``  → entries whose ``hash`` starts with this.

    Returns the list of entries that actually changed (already-correct
    entries are skipped). Writes the registry back to S3 if at least
    one entry changed.

    Requires AWS credentials with write access to the hub bucket —
    same as ``upload``.
    """
    _kind_prefix(kind)
    try:
        import boto3
    except ImportError as exc:
        raise WorldHubError(
            "boto3 required for unlist/relist. Install with "
            "`uv pip install -e \".[hub-publish]\"`."
        ) from exc

    token, version = parse_query(query)
    if not token:
        raise WorldHubError("empty query")

    reg = read_registry(kind)
    entries: list[dict[str, Any]] = reg[kind]

    is_hash = version is None and _looks_like_hash(token)
    matched: list[dict[str, Any]] = []
    for e in entries:
        if is_hash:
            if e.get("hash", "").lower().startswith(token):
                matched.append(e)
            continue
        if (e.get("slug") or "").lower() != token:
            continue
        if version is not None and str(e.get("version")) != version:
            continue
        matched.append(e)

    if not matched:
        raise WorldHubError(f"no entries match query {query!r}")

    changed: list[dict[str, Any]] = []
    for e in matched:
        currently = bool(e.get("unlisted"))
        if unlisted and not currently:
            e["unlisted"] = True
            changed.append(e)
        elif not unlisted and currently:
            e.pop("unlisted", None)
            changed.append(e)

    if changed:
        boto3.client("s3", region_name=HUB_REGION).put_object(
            Bucket=HUB_BUCKET,
            Key=_index_s3_key(kind),
            Body=json.dumps(reg, indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
            CacheControl="public, max-age=60",
        )

    return changed


# ---------------------------------------------------------------------------
# Resolve query → entry.
# ---------------------------------------------------------------------------

def parse_query(query: str) -> tuple[str, str | None]:
    """Split a user-supplied query into (slug_or_hash, version_or_None).

    Forms:
      "dark-train"       → ("dark-train", None)
      "dark-train@2.0"   → ("dark-train", "2.0")
      "538d19b9e55e"     → ("538d19b9e55e", None)   (handled as hash later)
    """
    q = query.strip().lower()
    if "@" in q:
        slug, version = q.split("@", 1)
        return slug.strip(), version.strip() or None
    return q, None


def _looks_like_hash(token: str) -> bool:
    # SHA256[:HASH_LEN] is hex; treat anything matching as hash.
    return len(token) >= 6 and all(c in "0123456789abcdef" for c in token)


def resolve(query: str, *, kind: str = "worlds") -> dict[str, Any]:
    """Resolve a query against the public registry. Returns the entry."""
    token, version = parse_query(query)
    if not token:
        raise WorldHubError("empty query")

    registry = read_registry(kind)
    entries: list[dict[str, Any]] = registry[kind]

    if not entries:
        raise WorldHubError(f"registry {kind!r} is empty")

    # Direct hash match (with optional prefix). Only consider if no version
    # was specified — `dark-train@2.0` is never a hash.
    if version is None and _looks_like_hash(token):
        hash_matches = [e for e in entries if e.get("hash", "").startswith(token)]
        if len(hash_matches) == 1:
            return hash_matches[0]
        if len(hash_matches) > 1:
            tail = ", ".join(e["hash"] for e in hash_matches[:5])
            raise WorldHubError(f"hash {token!r} is ambiguous; matches: {tail}")
        # No hash match — fall through to slug lookup (could be a slug-shaped hex string).

    slug_matches = [e for e in entries if e.get("slug") == token]
    if not slug_matches:
        # Friendly hint
        available = sorted({e.get("slug", "") for e in entries if e.get("slug")})
        sample = ", ".join(available[:5]) if available else "(none)"
        raise WorldHubError(
            f"no entry matching {query!r}. Known slugs: {sample}"
        )

    if version is not None:
        version_matches = [e for e in slug_matches if str(e.get("version")) == version]
        if not version_matches:
            versions = sorted({e["version"] for e in slug_matches if "version" in e})
            raise WorldHubError(
                f"version {version!r} not found for slug {token!r}. Versions: {versions}"
            )
        return version_matches[0]

    # No version: pick the latest by uploaded_at.
    slug_matches.sort(key=lambda e: e.get("uploaded_at", ""), reverse=True)
    return slug_matches[0]


def list_stories(kind: str = "worlds") -> list[dict[str, Any]]:
    """Return one record per slug, with `versions` listed newest-first.

    Shape:
      [
        {
          "slug": "dark-train",
          "display_name": "Dark Train (BRP)",   # name of the latest version
          "latest_version": "2.0",
          "latest_hash": "e38a...",
          "versions": [
            {"version":"2.0","hash":"e38a...","uploaded_at":"...","size_bytes":...,"name":"...","changelog":"..."},
            {"version":"1.0","hash":"538d...","uploaded_at":"...","size_bytes":...,"name":"...","changelog":"..."}
          ]
        },
        ...
      ]
    """
    registry = read_registry(kind)
    entries: list[dict[str, Any]] = registry[kind]

    by_slug: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        # Skip share-by-hash entries — they intentionally don't appear
        # in the public listing.
        if e.get("unlisted"):
            continue
        slug = e.get("slug") or "unknown"
        by_slug.setdefault(slug, []).append(e)

    out: list[dict[str, Any]] = []
    for slug, vs in by_slug.items():
        vs.sort(key=lambda e: e.get("uploaded_at", ""), reverse=True)
        latest = vs[0]
        out.append({
            "slug": slug,
            "display_name": latest.get("name", slug),
            "latest_version": latest.get("version", "?"),
            "latest_hash": latest.get("hash", ""),
            "versions": vs,
        })
    out.sort(key=lambda r: r["versions"][0].get("uploaded_at", ""), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Download.
# ---------------------------------------------------------------------------

def _extract_soul_zip(zip_path: Path, slug: str) -> Path:
    """Extract a SOUL-PROTOCOL bundle into ``SOUL_HOME/<slug>``.

    Soul bundles are validated by ``<root>/soul.json`` — NOT the world
    export's ``.neonrp/manifest.json`` (which souls never carry), so they
    must not go through ``load_world_zip``. Extracting to a slug-named dir
    (rather than the zip's name-prefixed top folder) is also what the play
    gateway's ``_resolve_soul_bundle`` looks for (``souls/<slug>``)."""
    from neonrp.core.souls import SOUL_HOME

    zip_path = Path(zip_path).expanduser().resolve()
    SOUL_HOME.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        if not members:
            raise ValueError("Soul zip is empty")
        top_levels = {m.split("/", 1)[0] for m in members if m.strip("/")}
        if len(top_levels) != 1:
            raise ValueError(
                f"Expected exactly one top-level folder in the soul archive, got {len(top_levels)}"
            )
        arc_root = next(iter(top_levels))
        if not any(m == f"{arc_root}/soul.json" for m in members):
            raise ValueError(
                "Archive does not look like a soul bundle (missing soul.json)."
            )
        safe_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(slug or "")).strip("-") or arc_root
        target = SOUL_HOME / safe_slug
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        staging = SOUL_HOME / f".extract-tmp-{safe_slug}"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        try:
            staging.mkdir(parents=True, exist_ok=False)
            zf.extractall(staging)
            shutil.move(str(staging / arc_root), str(target))
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    return target


def _zip_is_hosted_save(zip_path: Path) -> bool:
    """True if the archive is a restored hosted-play SAVE (a run), not a world.

    Hosted-play saves carry ``.session-meta.json`` at the top-level folder
    (written by the play gateway); a plain world export does not. A save is a
    RUN and belongs in PLAYS_HOME; a world is a reusable SOURCE in WORLDS_HOME.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            return any(
                m.rsplit("/", 1)[-1] == SESSION_META_FILENAME for m in members
            )
    except Exception:
        return False


def download(query: str, *, kind: str = "worlds") -> Path:
    """Fetch a story (or specific version) into the world library.

    A downloaded WORLD lands in ``WORLDS_HOME`` (a reusable library source);
    a downloaded hosted-play SAVE (carries ``.session-meta.json``) lands in
    ``PLAYS_HOME`` instead — it is a run, not a source. Souls go to SOUL_HOME.
    """
    from neonrp.worlds import PLAYS_HOME, WORLDS_HOME

    entry = resolve(query, kind=kind)
    expected_hash = entry["hash"]
    # index 条目的 url 是发布时写死的绝对地址(生产=S3)。基址被
    # WORLDHUB_REGISTRY_BASE 覆盖时(本地/dev 隔离栈),按覆盖基址重导出
    # zip 地址 —— 隔离环境绝不回连生产 S3。
    if os.environ.get("WORLDHUB_REGISTRY_BASE", "").strip():
        url = _zip_url(expected_hash, kind)
    else:
        url = entry["url"]

    tmp_dir = Path(tempfile.mkdtemp(prefix="worldhub-dl-"))
    zip_path = tmp_dir / f"{expected_hash}.zip"
    try:
        urllib.request.urlretrieve(url, zip_path)
        actual = compute_hash(zip_path)
        if actual != expected_hash:
            raise WorldHubError(
                f"hash mismatch: registry says {expected_hash}, downloaded {actual}"
            )

        # Souls are SOUL-PROTOCOL bundles (validated by soul.json), not
        # world exports — extract them with the soul-aware path straight
        # into the slug-named soul library dir. Worlds keep the export
        # loader (.neonrp/manifest.json).
        if kind == "souls":
            target = _extract_soul_zip(zip_path, entry.get("slug") or expected_hash)
        elif _zip_is_hosted_save(zip_path):
            # A restored hosted-play save is a RUN → it lands in PLAYS_HOME,
            # never the library (which holds reusable world SOURCES).
            target = load_world_zip(zip_path, games_dir=PLAYS_HOME)
        else:
            # A downloaded world is a library SOURCE → WORLDS_HOME.
            target = load_world_zip(zip_path, games_dir=WORLDS_HOME)

        # Restored hosted-play saves identify themselves via `.session-meta.json`
        # — don't also drop a `.worldhub.json` (it would compete for provenance
        # in resolve_wid/list_saved_games and mislabel the run as a hub world).
        if not (target / SESSION_META_FILENAME).is_file():
            (target / WORLDHUB_META_FILENAME).write_text(
                json.dumps(
                    {
                        "hash": expected_hash,
                        "slug": entry.get("slug", ""),
                        "name": entry.get("name", target.name),
                        "version": entry.get("version", "1.0"),
                        "changelog": entry.get("changelog", ""),
                        "source_url": url,
                        "kind": kind,
                        "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return target
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def download_world(query: str) -> Path:
    """Back-compat alias."""
    return download(query, kind="worlds")


# ---------------------------------------------------------------------------
# Metadata read for the launcher's saved-game list.
# ---------------------------------------------------------------------------

def read_worldhub_meta(game_dir: Path) -> dict[str, Any] | None:
    meta_path = game_dir / WORLDHUB_META_FILENAME
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Legacy constant for callers that imported the singular URL.
# Prefer registry_url(kind) instead.
# ---------------------------------------------------------------------------

REGISTRY_URL = registry_url("worlds")
HUB_PREFIX = "worlds"  # retained for callers; new code should pass `kind=`.


# ---------------------------------------------------------------------------
# Pre-upload validation + owner-side API wrappers (「上传的
# 时候记得做检验 —— hub 的文件、图片、其他」;the two worlds on the hub
# today had no picture and one of them was a run directory).
# ---------------------------------------------------------------------------

_RUN_DIR_RE = re.compile(r"^(?P<world>.+)-\d{8}-\d{6}$")
UPLOAD_SIZE_LIMIT = 50 * 1024 * 1024


@dataclass
class UploadCheck:
    """What the upload form shows before anything leaves the machine."""

    kind: str
    source: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    title: str = ""
    description: str = ""
    cover: Path | None = None
    # Souls inside a world that ship without a picture (warning detail).
    souls_without_portrait: list[str] = field(default_factory=list)
    # Publish gate (2026-09-13): what still blocks a PUBLIC listing. A draft
    # (unlisted) upload only needs `errors` empty; going public needs these
    # empty too — every picture present, title/description in all four
    # languages. Secrets always go to `errors`.
    publish_blockers: list[str] = field(default_factory=list)
    secrets: list[dict[str, Any]] = field(default_factory=list)
    title_i18n: dict[str, str] = field(default_factory=dict)
    description_i18n: dict[str, str] = field(default_factory=dict)
    missing_langs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def public_ready(self) -> bool:
        return not self.errors and not self.publish_blockers


def _dir_size(root: Path) -> int:
    total = 0
    for p in root.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def _first_text(*candidates: Any) -> str:
    for c in candidates:
        if isinstance(c, dict):
            for key in ("zh", "en", "ja", "ko"):
                v = c.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            for v in c.values():
                if isinstance(v, str) and v.strip():
                    return v.strip()
        elif isinstance(c, str) and c.strip():
            return c.strip()
    return ""


def validate_for_upload(source: Path, kind: str = "worlds") -> UploadCheck:
    """Check a world source / soul folder before upload and pre-fill the
    form. Errors block the upload; warnings only inform.

    Worlds need a start card, a map and a cover picture; souls need
    ``soul.json`` and a portrait. A run directory (``<world>-YYYYMMDD-HHMMSS``)
    is flagged: the source under ``~/.worldlines/worlds/`` is what belongs
    on the hub, not a played-through copy.
    """
    from neonrp.core.image_render import discover_world_images

    source = Path(source)
    check = UploadCheck(kind=kind, source=source)
    if not source.is_dir():
        check.errors.append("check.missing_dir")
        return check

    try:
        pics = discover_world_images(source)
    except Exception:
        pics = []
    check.cover = pics[0] if pics else None

    if kind == "souls":
        soul_json = source / "soul.json"
        if not soul_json.is_file():
            check.errors.append("check.no_soul_json")
            data: dict[str, Any] = {}
        else:
            try:
                data = json.loads(soul_json.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except (OSError, ValueError):
                data = {}
                check.errors.append("check.bad_soul_json")
        check.title = _first_text(data.get("name_local"), data.get("name")) or source.name
        check.description = _first_text(data.get("intro_i18n"), data.get("intro"), data.get("description"))
        if check.cover is None:
            check.errors.append("check.no_portrait")
    else:
        try:
            from neonrp.core.paths import get_game_dir

            game = get_game_dir(source)
        except Exception:
            game = source / "game"
        start = game / "meta" / "game-start.json"
        world_map = game / "world" / "world_map.json"
        if not start.is_file():
            check.errors.append("check.no_start_card")
            start_data: dict[str, Any] = {}
        else:
            try:
                start_data = json.loads(start.read_text(encoding="utf-8"))
                if not isinstance(start_data, dict):
                    start_data = {}
            except (OSError, ValueError):
                start_data = {}
                check.errors.append("check.bad_start_card")
        if not world_map.is_file():
            check.warnings.append("check.no_map")
        if check.cover is None:
            check.errors.append("check.no_cover")

        info = start_data.get("world_info") if isinstance(start_data.get("world_info"), dict) else {}
        name = _first_text(info.get("world_name"), start_data.get("name"))
        if not name:
            try:
                from neonrp.worlds import read_local_world_name

                name = read_local_world_name(source) or ""
            except Exception:
                name = ""
        # The world's own characters: each soul folder should carry a portrait.
        souls_dir = source / "souls"
        if souls_dir.is_dir():
            for sd in sorted(p for p in souls_dir.iterdir() if p.is_dir()):
                try:
                    has_pic = bool(discover_world_images(sd))
                except Exception:
                    has_pic = False
                if not has_pic:
                    label = sd.name
                    try:
                        sj = json.loads((sd / "soul.json").read_text(encoding="utf-8"))
                        label = _first_text(sj.get("name_local"), sj.get("name")) or label
                    except Exception:
                        pass
                    check.souls_without_portrait.append(label)
            if check.souls_without_portrait:
                check.warnings.append("check.souls_no_portrait")
        m = _RUN_DIR_RE.match(source.name)
        if m:
            check.warnings.append("check.is_run_dir")
            if not name:
                name = m.group("world")
        check.title = name or source.name
        check.description = _first_text(info.get("premise"), start_data.get("premise"), start_data.get("description"), info.get("description"))
        if not check.description:
            # Older start cards carry no premise; genre · tone is a usable seed.
            bits = [_first_text(info.get("genre")), _first_text(info.get("tone"))]
            check.description = " · ".join(b for b in bits if b)

    if _dir_size(source) > UPLOAD_SIZE_LIMIT:
        check.errors.append("check.too_big")

    # ── publish gate ───────────────────────────────────────────────
    from neonrp.core.hub_publish import scan_for_secrets, seed_hub_meta

    try:
        hits = scan_for_secrets(source)
    except Exception:
        hits = []
    if hits:
        check.secrets = [h.to_dict() for h in hits]
        check.errors.append("check.secret_found")
    if check.souls_without_portrait:
        check.publish_blockers.append("check.souls_no_portrait")
    meta = seed_hub_meta(source, kind, title=check.title, description=check.description)
    check.title_i18n = dict(meta.title)
    check.description_i18n = dict(meta.description)
    check.missing_langs = meta.missing
    if check.missing_langs:
        check.publish_blockers.append("check.i18n_missing")
    return check


def _owner_api_call(
    path: str,
    *,
    api_token: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
    api_url: str | None = None,
) -> dict[str, Any]:
    """JSON call against the owner-gated ``/api/v1/me/published/...`` routes."""
    if not api_token:
        raise WorldHubError("hub token required")
    base_url = (api_url or os.environ.get("HUB_API_URL", "https://api.worldlines.gg")).rstrip("/")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {api_token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise WorldHubError(f"{method} {path} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise WorldHubError(f"{method} {path} failed: {exc.reason}") from exc
    try:
        result = json.loads(raw) if raw else {}
    except ValueError:
        result = {}
    return result if isinstance(result, dict) else {"result": result}


def _api_kind(kind: str) -> str:
    if kind in ("replay", "replays"):
        return "replay"
    return "world" if kind in ("world", "worlds") else "soul"


def update_meta_via_api(
    kind: str,
    slug: str,
    *,
    api_token: str,
    name: str | None = None,
    description: str | None = None,
    api_url: str | None = None,
    name_i18n: dict[str, str] | None = None,
    description_i18n: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Edit the display name / catalog description of one of the caller's
    published assets. ``name_i18n`` / ``description_i18n`` carry the four
    hub languages (zh/en/ja/ko) for the publish gate."""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if name_i18n:
        payload["name_i18n"] = {k: v for k, v in name_i18n.items() if isinstance(v, str) and v.strip()}
    if description_i18n:
        payload["description_i18n"] = {k: v for k, v in description_i18n.items() if isinstance(v, str) and v.strip()}
    return _owner_api_call(
        f"/api/v1/me/published/{_api_kind(kind)}/{slug}/meta", api_token=api_token, payload=payload, api_url=api_url
    )


def set_visibility_via_api(
    kind: str, slug: str, *, unlisted: bool, api_token: str, api_url: str | None = None
) -> dict[str, Any]:
    return _owner_api_call(
        f"/api/v1/me/published/{_api_kind(kind)}/{slug}/visibility",
        api_token=api_token,
        payload={"unlisted": bool(unlisted)},
        api_url=api_url,
    )


def delete_published_via_api(kind: str, slug: str, *, api_token: str, api_url: str | None = None) -> dict[str, Any]:
    """Remove one of the caller's published assets from the hub."""
    return _owner_api_call(
        f"/api/v1/me/published/{_api_kind(kind)}/{slug}", api_token=api_token, method="DELETE", api_url=api_url
    )
