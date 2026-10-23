"""`neonrp template` — the layer above a world (docs/TEMPLATE-PROTOCOL.md).

    neonrp template list                     templates on NEONRP_TEMPLATE_PATH (+ worldlines/templates from source)
    neonrp template lint <dir|id> [--json] [--i18n-deep]   every check (+ localization coverage); exit 1 when not publishable
    neonrp template build <dir|id> <dest> [--lang L]   materialize a playable run (in language L: its i18n/L/ layer)
    neonrp template show [--world DIR]       a built run's card / mode / plot stages / ending
    neonrp template contract <dir|id> [--ts|--gd]   worldlines.contract/0.1, or generated TS / GDScript bindings
    neonrp template slots <dir|id>           every asset slot instance (have / stale / required)
    neonrp template contracts                the official play contracts, and which templates promise each
    neonrp template fork <dir|id> <new-id>   copy a template into your store to edit it (built-ins are read-only)
    neonrp template set-contract <id> <contract[@v]>|--clear   declare the experience it promises; re-linted
    neonrp template export <dir|id> [-o FILE]      a template package (.zip) — linked library souls come along
    neonrp template export --soul <name> [-o FILE]  one character-library soul as a package
    neonrp template import <FILE> [--id NEW] [--store DIR]   bring a package back (template → your store, souls → library)
    neonrp template publish <dir|id> --official   the official account: up to the default zone as hub/template/<id> (10-17)
    neonrp template fetch <id>               get / update an official (default-zone) world with your account (10-17)
"""

from __future__ import annotations

import json
from pathlib import Path

import click


def _resolve(ref: str) -> Path:
    from neonrp import template as TP

    p = Path(ref).expanduser()
    if (p / "template.json").is_file() or p.name == "template.json":
        return p
    hit = TP.discover().get(ref)
    if hit is None:
        raise click.ClickException(f"no template {ref!r} (not a folder with template.json, not on NEONRP_TEMPLATE_PATH)")
    return hit


@click.group("template")
def template_group() -> None:
    """Templates: world × souls × pack × prompts × plots, linted and built into a run."""


@template_group.command("list")
def list_cmd() -> None:
    from neonrp import template as TP

    for tid, d in TP.discover().items():
        t = TP.load(d)
        click.echo(f"{tid:<28} {t.pack_name:<9} {t.ending_mode:<7} {(t.play_contract or '-'):<20} {t.card.get('title') or ''}  ({d})")


@template_group.command("lint")
@click.argument("ref")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--i18n-deep", is_flag=True, help="Also build + lint each localized version (i18n/<lang>/).")
def lint_cmd(ref: str, as_json: bool, i18n_deep: bool) -> None:
    from neonrp import template as TP

    r = TP.lint(_resolve(ref), i18n_deep=i18n_deep)
    if as_json:
        click.echo(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        for p in r["problems"]:
            click.echo(f"[{p['level']:<5}] {p['code']:<16} {p['where']}: {p['msg']}")
        for lg, v in ((r.get("i18n") or {}).get("langs") or {}).items():
            click.echo(f"i18n {lg}: {v['covered']}/{v['units']} ({v['coverage']:.0%}) · residue {len(v['residue'])}")
        c = r.get("counts") or {}
        click.echo(("publishable" if r["publishable"] else "NOT publishable") + f" — {c.get('block', 0)} block, {c.get('warn', 0)} warn")
    if not r["publishable"]:
        raise SystemExit(1)


@template_group.command("build")
@click.argument("ref")
@click.argument("dest")
@click.option("--force", is_flag=True, help="Build even when lint blocks.")
@click.option("--lang", default=None, help="The run's language: lay the template's i18n/<lang>/ layer over it.")
def build_cmd(ref: str, dest: str, force: bool, lang: str | None) -> None:
    from neonrp import template as TP

    d = _resolve(ref)
    r = TP.lint(d)
    if not r["publishable"] and not force:
        for p in r["problems"]:
            if p["level"] == "block":
                click.echo(f"[block] {p['code']} {p['where']}: {p['msg']}", err=True)
        raise click.ClickException("lint blocks the build (use --force to build anyway)")
    try:
        rec = TP.build(d, Path(dest).expanduser(), lang=lang)
    except TP.TemplateError as e:
        raise click.ClickException(str(e)) from e
    _ensure_project(Path(dest).expanduser())  # a built run is playable as it stands: neonrp serve --project / tui --play
    b = rec["built"]
    click.echo(f"built {rec['id']} → {dest}  pack={rec['pack']} souls={','.join(b['souls'])} plots={','.join(b['plots']) or '-'}"
               f" prompt-overlays={len(b['prompt_overlays'])}")


def _ensure_project(run: Path) -> None:
    """The project manifest the engine checks (``.neonrp/manifest.json``) — new_run writes it, a CLI build did not
    (10-11: ``neonrp serve --project <built run>`` said "Not initialized")."""
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path
    from neonrp.core.storage import atomic_write_json, ensure_dirs

    if not get_manifest_path(run).exists():
        ensure_dirs(run)
        atomic_write_json(get_manifest_path(run), Manifest().model_dump())


@template_group.command("show")
@click.option("--world", "into", default=None, help="Run folder (default: cwd).")
def show_cmd(into: str | None) -> None:
    from neonrp import template as TP

    v = TP.run_view(Path(into).expanduser() if into else Path.cwd())
    if v is None:
        raise click.ClickException("this folder was not built from a template (no game/meta/template.json)")
    click.echo(json.dumps(v, ensure_ascii=False, indent=2))


@template_group.command("contract")
@click.argument("ref")
@click.option("--ts", "fmt", flag_value="ts", help="Generated TypeScript client.")
@click.option("--gd", "fmt", flag_value="gd", help="Generated GDScript (Godot) binding.")
def contract_cmd(ref: str, fmt: str | None) -> None:
    from neonrp import template as TP
    from neonrp.template import v3

    t = TP.load(_resolve(ref))
    with v3._scratch(t, None) as root:
        c = v3.contract(t, root)
    click.echo(v3.gen_ts(c) if fmt == "ts" else v3.gen_gd(c) if fmt == "gd" else json.dumps(c, ensure_ascii=False, indent=2))


@template_group.command("slots")
@click.argument("ref")
def slots_cmd(ref: str) -> None:
    from neonrp import template as TP

    for r in TP.asset_slots(TP.load(_resolve(ref))):
        state = "stale" if r.get("stale") else "ok" if r.get("have") else ("MISSING" if r.get("need") else "-")
        click.echo(f"{state:<8} {r['slot']:<40} {r.get('label') or ''}")


def _store(store: str | None) -> None:
    """--store wins over NEONRP_TEMPLATE_WRITE_DIR (the folder your own templates live in)."""
    import os

    if store:
        os.environ["NEONRP_TEMPLATE_WRITE_DIR"] = str(Path(store).expanduser())
        tp = os.environ.get("NEONRP_TEMPLATE_PATH", "")
        if str(Path(store).expanduser()) not in tp.split(os.pathsep):
            os.environ["NEONRP_TEMPLATE_PATH"] = os.pathsep.join(x for x in (str(Path(store).expanduser()), tp) if x)


def _title(v: object, lang: str = "zh") -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("zh") or v.get("en") or next(iter(v.values()), ""))
    return str(v or "")


@template_group.command("contracts")
def contracts_cmd() -> None:
    """The official play contracts (worldlines/contracts) and the templates that declare each."""
    from neonrp import template as TP
    from neonrp.template import contract as C

    users: dict[str, list[str]] = {}
    for tid, d in TP.discover().items():
        try:
            ref = TP.load(d).play_contract
        except Exception:  # noqa: BLE001 — a broken template doesn't hide the list
            continue
        if ref:
            users.setdefault(C.parse_ref(ref)[0], []).append(tid)
    for cid, f in C.available().items():
        c = C.load(cid)
        exit_ = c.get("exit") or {}
        ends = c.get("endings") or {}
        click.echo(f"{cid}@{c.get('version')}  {_title(c.get('title'))}")
        click.echo(f"    exit: {exit_.get('on')}{'/' + str(exit_.get('segment')) if exit_.get('segment') else ''}"
                   f" · endings ≥ {ends.get('min', 0)}{' incl. ' + ','.join(ends.get('require') or []) if ends.get('require') else ''}"
                   f" · cast {(c.get('entry') or {}).get('cast', '-')}")
        click.echo(f"    templates: {', '.join(users.get(cid, [])) or '(none yet)'}")


@template_group.command("fork")
@click.argument("ref")
@click.argument("new_id")
@click.option("--title", default=None, help="Card title of the copy.")
@click.option("--store", default=None, help="Your template folder (default: NEONRP_TEMPLATE_WRITE_DIR).")
def fork_cmd(ref: str, new_id: str, title: str | None, store: str | None) -> None:
    """Copy a template (plots / prompts / overlay / assets come along) into your store, to edit it."""
    from neonrp.template import TemplateError, author

    _store(store)
    try:
        t = author.fork(_resolve(ref), new_id, title=title)
    except TemplateError as e:
        raise click.ClickException(f"{e} — pass --store DIR or set NEONRP_TEMPLATE_WRITE_DIR" if "WRITE_DIR" in str(e) else str(e)) from e
    click.echo(f"forked {ref} → {t.id}  ({t.dir})")


@template_group.command("set-contract")
@click.argument("ref")
@click.argument("contract", required=False, default="")
@click.option("--clear", is_flag=True, help="Drop the declared contract.")
@click.option("--store", default=None, help="Your template folder (default: NEONRP_TEMPLATE_WRITE_DIR).")
def set_contract_cmd(ref: str, contract: str, clear: bool, store: str | None) -> None:
    """Declare which play contract the template promises (mystery-trpg / open-adventure / murder-mystery /
    romance-companion …, see `neonrp template contracts`), then re-lint: the contract's checks become lint checks."""
    from neonrp.template import TemplateError, author

    _store(store)
    if not clear and not contract:
        raise click.ClickException("which contract? (see `neonrp template contracts`) — or --clear")
    try:
        r = author.apply_ops(_resolve(ref), [{"op": "set_play_contract", "contract": "" if clear else contract}])
    except TemplateError as e:
        raise click.ClickException(str(e)) from e
    if not r["ok"]:
        raise click.ClickException("; ".join(x["why"] for x in r["refused"]))
    a = r["applied"][0]
    click.echo(f"play_contract: {a['from'] or '-'} → {a['to'] or '-'}")
    lint = r["lint"]
    for p in lint["problems"]:
        if p["code"].startswith("contract"):
            click.echo(f"[{p['level']:<5}] {p['code']:<16} {p['where']}: {p['msg']}")
    c = lint.get("counts") or {}
    click.echo(("publishable" if lint["publishable"] else "NOT publishable") + f" — {c.get('block', 0)} block, {c.get('warn', 0)} warn")


@template_group.command("export")
@click.argument("ref", required=False)
@click.option("--soul", "soul", default=None, help="Export a character-library soul instead of a template.")
@click.option("-o", "--out", "out", default=None, help="Where to write the .zip (default: ./<id>.<kind>.zip).")
def export_cmd(ref: str | None, soul: str | None, out: str | None) -> None:
    """Take what you authored out of the engine: a template (with the library souls it links) or one soul."""
    from neonrp.template import TemplateError
    from neonrp.template import load as _load
    from neonrp.template import package as P

    if bool(ref) == bool(soul):
        raise click.UsageError("give a template (REF) or --soul NAME")
    try:
        if soul:
            data, name, kind = P.export_soul(soul), soul, "soul"
        else:
            t = _load(_resolve(str(ref)))
            data, name, kind = P.export_template(t), t.id, "template"
    except P.ExportRefused as e:   # 10-16: default-zone works (the official worlds) are not exported
        from neonrp.core.template_publish import _msg
        from neonrp.tui.i18n import resolve_locale

        raise click.ClickException(_msg("export_default_zone", resolve_locale())) from e
    except TemplateError as e:
        raise click.ClickException(str(e)) from e
    dest = Path(out).expanduser() if out else Path.cwd() / f"{name}.{kind}.zip"
    dest.write_bytes(data)
    click.echo(f"exported {kind} {name} → {dest}  ({len(data):,} B)")


@template_group.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--id", "new_id", default=None, help="Import under this id / name (default: the package's, -2 … when taken).")
@click.option("--store", default=None, help="Your template folder (default: NEONRP_TEMPLATE_WRITE_DIR).")
def import_cmd(file: str, new_id: str | None, store: str | None) -> None:
    """Bring a package back: a template goes into your store, the souls it carries into the character library."""
    from neonrp.template import TemplateError
    from neonrp.template import package as P

    _store(store)
    try:
        r = P.import_package(Path(file).read_bytes(), new_id=new_id)
    except TemplateError as e:
        raise click.ClickException(f"{e} — pass --store DIR or set NEONRP_TEMPLATE_WRITE_DIR" if "WRITE_DIR" in str(e) else str(e)) from e
    extra = f" (id {r['renamed_from']} was taken)" if r.get("renamed_from") else ""
    click.echo(f"imported {r['kind']} {r['id']}{extra}")
    for s in r.get("souls") or []:
        click.echo(f"  soul {s['name']}: {s['how']}")


@template_group.command("publish")
@click.argument("ref")
@click.option("--official", is_flag=True, required=True, help="Publish as an official world (the official account only).")
def publish_cmd(ref: str, official: bool) -> None:
    """「发布为官方」(niko 10-17): the default zone under the template's own id, a new revision each time (raise the version
    first). The free zone is published from the creation desk."""
    from neonrp import template as TP
    from neonrp.core import template_publish as _tp
    from neonrp.tui.i18n import resolve_locale

    lang = resolve_locale()
    try:
        r = _tp.publish_official(TP.load(_resolve(ref)), lang=lang)
    except _tp.PublishError as e:
        probs = "".join(f"\n  - {p.get('message')}" for p in (e.extra or {}).get("problems") or [])
        raise click.ClickException(f"{e}{probs}") from e
    click.echo(f"{r['ref']}  v{r['version']} · revision {r['revision']} · {r['status']}\n{r['message']}")


@template_group.command("fetch")
@click.argument("wid")
def fetch_cmd(wid: str) -> None:
    """Get (or update) a default-zone world into ~/.worldlines/official with your Worldlines account."""
    from neonrp.core import template_publish as _tp
    from neonrp.core.paths import ensure_template_store
    from neonrp.tui.i18n import resolve_locale

    ensure_template_store()
    try:
        r = _tp.fetch_official(wid, lang=resolve_locale())
    except _tp.PublishError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"{r['ref']} · revision {r['revision']}\n{r['message']}")
