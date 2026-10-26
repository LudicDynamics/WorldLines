# Changelog

`neonrp` (engine and terminal launcher) and `worldlines` (local web UI) share version numbers from 1.0.3.
Full notes for each version are on [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases).

## 1.0.6 (2026-10-26)

- Create with a coding agent on your computer. `neonrp mcp serve-create` serves the creation tools over MCP; the workbench can use Claude Code or Codex as its creation backend. The agent reads and writes only the template folder, and writes that look like keys are refused.
- The world-creation skill ships with the engine. `neonrp spec skill` prints where it is. New tutorial in four languages: create with Codex or Claude Code.
- Creation desk: AI writes or rewrites each text field, or fills the empty ones. Your own text is changed only after you confirm.
- When a turn is cut off by a timeout or a dropped stream, the text written so far is kept. Continue, redo, or rewrite the line.
- Contested rolls say who won first, then both rolls and the rule that decided it. The web dice show both dice.
- Workbench, Template page: turn character creation on or off for any world, and edit its fields. Bundled worlds are read-only; copy one to change it.
- Judge settings page in the terminal UI and the local web UI.
- The blank world has no sample characters or places.
- A new world made from a copied template opens again.
- The terminal launcher lists your own templates.
- CG captions stay readable on colourful art.
- Online play in the browser: Default Zone worlds use Worldlines credits; your own key works on Free Zone works.
- Usage data: a setting to turn it off (`NEONRP_USAGE=off` also turns it off).

## 1.0.5 (2026-10-25)

- The workbench interface is in Chinese, English, Japanese and Korean. Switching in Settings changes the interface at once; the narration language applies from the next run. The workbench and the local Hub share one language setting.
- The workbench carries on with your newest save when it opens, instead of starting a new run on every visit. "Cannot reach the engine" no longer appears when a world's saves are full.
- The local edition has no save limit, signed in or not.
- Desktop app on Windows: no console windows when the engine starts. Windows installer.

## 1.0.4 (2026-10-24)

- The local Hub shows the Free Zone only. Bundled worlds and your own templates are listed under "On this computer". The Default Zone opens on the online Hub.
- Delete templates you made from the local Hub.
- "Copy to my workbench" and "Create on this template" appear on Free Zone works and on worlds on this computer only.
- Report a problem from the Hub footer.
- Desktop app: the engine port comes from a pool (8792–8799), and only the app's own engine is used. Reload (⌘R) and Restart engine (⇧⌘R) in the menu; the engine restarts once by itself if it exits.

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
