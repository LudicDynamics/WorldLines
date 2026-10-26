"""`neonrp spec` — the specs an agent reads before it writes a world, a soul, a template or a contract (neonrp/spec.py).

    neonrp spec                          list them
    neonrp spec <name> [--lang zh|en]    print one (world · soul · template · contract · ops · authoring · contracts · http)
    neonrp spec ops --pack pct           one play pack's op space
    neonrp spec --llms                   the llms.txt index
    neonrp spec skill [NAME]             the skills shipped for coding agents: where each folder is, or print one's SKILL.md
    neonrp spec sync [DIR ...]           put AGENTS.md / CLAUDE.md / spec/ into every template, the store and the library
                                         (or just the template folders given) — that is where Claude / Codex read them
"""

from __future__ import annotations

import click


@click.command("spec")
@click.argument("name", required=False)
@click.argument("extra", nargs=-1)
@click.option("--lang", default="zh", type=click.Choice(["zh", "en"]), help="Language of a written spec.")
@click.option("--pack", default=None, help="ops: only this play pack (rpg · pct · werewolf · monopoly).")
@click.option("--llms", is_flag=True, help="Print the llms.txt index instead.")
def spec_cmd(name: str | None, extra: tuple[str, ...], lang: str, pack: str | None, llms: bool) -> None:
    """Print a spec (for you or an agent): what a world / soul / template / contract folder must hold, and the op space."""
    from neonrp import spec

    if llms:
        click.echo(spec.llms_txt())
        return
    if name == "sync":
        from pathlib import Path

        from neonrp.template import agentdocs

        dirs = [Path(d).expanduser() for d in extra] if extra else None
        for where, files in agentdocs.sync(templates=dirs).items():
            click.echo(f"{where}: {len(files)} updated" if files else f"{where}: up to date")
        return
    if name == "skill":
        if not extra:
            for s in spec.SKILLS:
                d = spec.skill_dir(s)
                click.echo(f"{s:16s} {d if d else '(not installed with this engine)'}")
            return
        d = spec.skill_dir(extra[0])
        if d is None:
            raise click.ClickException(f"no skill {extra[0]!r} (have: {', '.join(spec.SKILLS)})")
        click.echo((d / "SKILL.md").read_text(encoding="utf-8"))
        return
    if not name:
        for n in spec.names():
            click.echo(f"{n['name']:10s} {n['kind']:9s} {'/'.join(n['langs']):6s} {n['title']}")
        return
    try:
        click.echo(spec.read(name, lang=lang, pack=pack))
    except KeyError as e:
        raise click.ClickException(str(e).strip("'\"")) from e
