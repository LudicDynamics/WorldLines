# Changelog

`neonrp` (engine and terminal launcher) and `worldlines` (local web UI) share version numbers from 1.0.3.
Full notes for each version are on [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases).

## 1.0.3 (2026-10-24)

- Install from this repository or PyPI; worldlines.gg is online play. Installs update themselves at launch.
- The local Hub lists the online Hub's worlds without signing in.
- Workbench: new template, new world, new character.
- Upload a world to the Free Zone from the local edition.
- Without a judging model, the run's own model decides when the planning talk is settled.
- Report AI content from the play page and the phone.
- Character names follow the interface language.
- Removed: the TUI's `--mcp` mode and the Claude Code preset.
- Fixes: plot graph names, the top bar on narrow screens, TUI quick bar labels, zero values in orchestration settings.

## 1.0.2 (2026-10-23)

- First 1.0 release on PyPI.
- State changes are written fast, then checked and corrected in the background.
- Relative changes in `<vars>` (`-6`, `+= 2`) are applied as increments.
- Characters away from the player travel between towns by road.
- Money agreed while planning is settled by the engine.

## Earlier

Versions up to 0.4.2: see [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases).
