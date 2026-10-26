---
name: world-creation
description: Turn a written world spec (premise, places, people, opening, endings — a markdown file the author pastes or points to) into a playable WorldLines template, file by file, from the terminal, while the author watches progress in the local web workbench. Use when the user hands over a world or setting document and says "build this world", "make a template from this spec", "here is my world spec", or wants an existing template rewritten to match a new spec. Not for one character only (soul-authoring), one entity only (entity-authoring), or SillyTavern cards (character-card-authoring, world-card-authoring).
---

# World creation

You write the files. The author watches the result in the web workbench and fills in images and plot details there.
The output is one `<id>.template/` folder in the author's template store that lints with 0 block and builds into a run.

Formats: `spec/template.md`, `spec/world.md`, `spec/soul.md`, `spec/contract.md` inside every template folder
(the same files as `documents/spec/` in this repo; `neonrp spec <name>` prints them). This skill says the order of
work; the specs say what each field means. Read the spec section before you write a file. Never invent a field.

## 0. Setup

```bash
neonrp --help >/dev/null || uv tool install worldlines     # installs both `worldlines` and `neonrp`
STORE=~/.worldlines/templates                              # the store the web workbench reads
```

Always pass `--store "$STORE"` to `template new / fork / import / set-contract`, and pass folder paths (not ids) to
`template lint / slots / build / export`.

## 1. Read the spec

The author's spec is free text or follows `references/world-spec-template.md`. Extract:
id, language, pack, contract, ending / freedom mode, pitch, places, people, opening, plot and endings, world data, art.

- Ask once, in one message, only for what blocks the work: the language, and the contract when the endings are
  unclear. Pick defaults for the rest and list them in your first progress note.
- Content goes in the spec's language, written natively. Ids, keys and file names are ASCII.
- `examples/tidepool/world-spec.md` is a complete small spec.

## 2. Create the template

| The spec is closest to | Start with |
|---|---|
| a percentile investigation with clues and several endings | `neonrp template fork pct-house <id> --store "$STORE"` |
| an open town with an economy | `neonrp template fork stoneford-town <id> --store "$STORE"` |
| anything else | `neonrp template new <id> --title "<title>" --lang <lang> --pack <pack> --contract <contract> --store "$STORE"` |

Then:

```bash
T="$STORE/<id>.template"
cp <the author's spec> "$T/world-spec.md"     # keep the source next to the work; re-read it before each pass
neonrp template lint "$T"
```

## 3. Open the workbench for the author

```bash
worldlines --no-browser          # http://127.0.0.1:8787 ; add --port <n> when 8787 is taken
```

Give the author two links. They show the files as they are on disk; a reload shows your latest pass.

| Link | Shows |
|---|---|
| `http://127.0.0.1:<port>/local?screen=tpl&edit=<id>` | Template: card, contract, lint, asset slots (upload or generate images here) |
| `http://127.0.0.1:<port>/local?screen=duo&edit=<id>` | World · Characters: map, plot, schema, data |

Do not open `/local?tpl=<id>`: that starts a run and replaces the one the author may be playing.
If the author edits in the workbench, re-read the changed files before your next pass.

## 4. Write in passes

One pass = one part of the spec. End every pass with the check line and a two-line note to the author
(what changed, lint counts, what to look at in the workbench).

```bash
neonrp template lint "$T"                                   # after every pass
(cd "$T/world" && neonrp validate) && neonrp map status --world "$T/world"   # after passes B–E
```

**With the `neonrp-create` MCP server** (tools `mcp__neonrp-create__*`; `neonrp mcp serve-create --root "$T"`), do the
passes through it instead of Bash and your own file tools: `read_file` / `write_file` (text only, JSON must parse, only
inside the template, never `.neonrp/` or `.git/`, key-shaped text is refused), `lint` as the check line after every pass,
`slots`, `build_preview` for §5 (a scratch build, no model call), `spec_read("world" | "template" | "soul")` before a new
field. The world's own `neonrp validate` and `map status` and the play-test (§6) still run in a terminal. Setup samples:
the workbench `CLAUDE.md`.

| Pass | Files | Spec |
|---|---|---|
| A · card and mode | `template.json`: `card` (title, pitch, lang, tags), `mode`, `play_contract` (`neonrp template set-contract "$T" <contract> --store "$STORE"`) | template §3.2–3.3, contract |
| B · map | `world/game/world/world_map.json`, `world/game/locations/<T###>/<place>/location.json`, `world/game/towns/<T###>/town.json`, start position in `world/game/meta/run_state.json` | world §3.1–3.3, §4 |
| C · lore and data | `world/game/lore/story.md`, `rumors.md`, `gm-truth.md`; `world/game/rules/*.md`; root `world/manifest.json` `{"lang": "<lang>"}` | world §3.7 |
| D · people | characters who think: `souls/<sid>/` in the template + `{"sid", "path": "souls/<sid>"}` in `template.json` `souls`; background people: `world/game/towns/<T###>/npcs.json` | soul §6, template §3.6, world §3.3 |
| E · opening | `world/game/meta/game-start.json` `startup.opening_scene` / `opening_choices` / `read_first`, `world_info` | world §3.12 |
| F · plot and endings | `plots/<id>/plot.json` (stages, entries, triggers, endings, reveal; `truth_quiz` when the contract asks), `"plots": ["plots/<id>"]` | template §5, contract §4 |
| G · art | `recipe.style`, named prompts; `neonrp template slots "$T"` lists what is missing. The author uploads or generates the images on the Template page. Do not add images you did not get from the author | template §6 |

`references/spec-to-files.md` maps each spec section to files with short examples.

### A blank world from `template new`

The blank world is clean: one starting place (`T001/start`), a player, no characters, no plots, empty lore. Write over it; there is nothing to remove first.

Leave `world/agents/` as it is unless the spec asks for a world-specific agent (world §3.13).

## 5. Build and check without a model

```bash
neonrp template build "$T" /tmp/try-<id>
(cd /tmp/try-<id> && neonrp validate && neonrp engine graph)
```

Optional smoke test of the turn flow with a stub model (no network, nothing written outside a temp copy):

```bash
echo '{"template": "'"$T"'", "lines": ["开始游戏", "<a line from the spec>"]}' > /tmp/gt.json
neonrp engine graph-test /tmp/gt.json
```

## 6. Play-test (uses the author's model — ask first)

- Web: the Template page's "Run on the test bench", or the Test bench screen.
- Terminal: run `neonrp` (the launcher) and pick the template.

Report the first two turns: did the opening appear as written, did the characters present act as written,
did the state land (place, money, time).

## 7. Hand off

Report in a short table: files written per pass, lint (block / warn), slots still missing, defaults you chose,
open questions. Then:

```bash
neonrp template export "$T" -o <id>.template.zip    # a package the author can share or import elsewhere
```

Publishing is the author's action, on the Template page.

## Rules

- Never edit engine code. World words (places, statuses, factions) go in this template's data only.
- Built-in templates are read-only. Fork first.
- Characters from the author's character library are links (`{"lib": "<name>"}`); per-world differences go in
  `prompts/souls/<sid>/` or `world-overlay/`.
- `AGENTS.md`, `CLAUDE.md` and `spec/` in the template are generated. Do not edit them.
- Characters need positions they can take: what they agree to, refuse, and bargain over. The world needs data the host
  can read: prices, distances, schedules, who is where.
- No secrets, personal paths or internal addresses in any file.
