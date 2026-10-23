"""`neonrp vault` — project this world into an Obsidian vault (M31).

The engine is file-first, but its files are records: mostly JSON, which
Obsidian shows as dead text. This command writes the *readable* face of the
same data — one linked note per soul, place and entity, portraits, and a
canvas of who-is-where — into `vault/`, so the world can be watched from
above in any markdown client.

Turns re-project automatically; this command is for the first build, for a
world you have been editing outside a session, and for repair. `--open`
is the one-click: register the folder with Obsidian and open it (restarting
the app if it is running, because it reads its vault list only at launch).
"""

from __future__ import annotations

import click

from neonrp.core.paths import get_project_root
from neonrp.core.vault import VAULT_DIRNAME, project_vault, write_config_template


@click.command()
@click.option("--quiet", is_flag=True, help="Only report the summary line.")
@click.option(
    "--init-config",
    is_flag=True,
    help="写一份 frontmatter 规则模板到 .neonrp/vault.json(不覆盖已有的)。",
)
@click.option(
    "--open",
    "open_app",
    is_flag=True,
    help="投影完直接在 Obsidian 里打开(自动登记 vault;Obsidian 在跑时会重启它)。",
)
def vault(quiet: bool, init_config: bool, open_app: bool) -> None:
    """Project the world into an Obsidian-readable vault under `vault/`."""
    root = get_project_root()

    if init_config:
        path = write_config_template(root)
        click.echo(f"frontmatter 规则:{path}")
        click.echo("改完再跑一次 `neonrp vault` 生效(回合中会自动重投影)。")

    report = project_vault(root)

    if not quiet:
        for rel in report.written:
            click.echo(f"  + {rel}")
        for rel in report.removed:
            click.echo(f"  - {rel}")

    click.echo(f"{report.headline()}(未变 {report.unchanged})")
    click.echo(f"→ {root / VAULT_DIRNAME}")

    if open_app:
        from neonrp.core.obsidian import open_vault

        for line in open_vault(root / VAULT_DIRNAME).lines():
            click.echo(line)
    else:
        click.echo("加 --open 直接在 Obsidian 里打开(或在 TUI 里敲 /vault)。")
