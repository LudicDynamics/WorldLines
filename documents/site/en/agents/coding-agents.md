---
title: "Create with Codex / Claude Code"
description: "Install the world-creation skill and hand a world spec to a coding agent: it edits the files by the specs, you watch progress in the local web workbench, and 0 lint blocks means playable and publishable."
---

<!-- section: what -->
## What this page covers

Build a world in the terminal with a coding agent such as Claude Code or Codex. You write a world spec. The agent turns it into a template folder. You watch the result and add images in the local web workbench.

First, four things: how WorldLines models a world, how a run moves, what the agent edits, and how to make sure the engine can run it. Then the steps.

<!-- section: ideas -->
## Four basic ideas

| Idea | Meaning | For the agent |
|---|---|---|
| **Three parties** | The world, the characters and the player each have their own agency and are kept apart. A player's line is an attempt; the world decides the outcome. A character settles its own thoughts | Do not write a character's ending into the files. Do not pre-fill a character's diary or state |
| **The file system is the interface** | Worlds, characters and templates are folders. The folder is the only truth; the web UI and the TUI render it | Editing files is enough. What the web page shows is what is on disk |
| **Effects belong to the engine; customization controls them** | Effects such as a robber getting surrounded or a player getting sick from bad food come from engine mechanics and work with zero configuration. A creator's tables and rules only **change** the result | Do not write long prompts that "teach" the engine how to act. Write data: prices, distances, who is where, what a character agrees to |
| **Template = world + characters + play pack + contract** | A template binds one world, a cast, a rule pack (`rpg` / `pct` / `werewolf` / `monopoly`) and a play contract, and picks an orchestration. It is the unit that is played, exported and published | The agent's output is one `<id>.template/` folder |

Characters live in the character library; a template only holds links. Place names, status names and faction names go in the template's data, never in engine code.

<!-- section: orchestration -->
## Orchestration: how a run moves

An orchestration is a state-machine graph. Nodes are "what this beat does"; edges are "when to move to the next node". A template names an orchestration template in `template.json` `uses`. It carries no rule pack and no contract, so many worlds can share one.

| Orchestration | One turn |
|---|---|
| `one_beat` | Resolve beat only: the world writes the narration, the characters present act, the engine writes, checks and lands the state |
| `two_beat` | A planning beat, then the resolve beat. In planning, the host passes the word to the characters present and lists costs, checks and time; the world does not change. Once it is settled, the resolve beat runs |

The `worldlines` / `neonrp` packages on PyPI include the two-beat orchestration. An engine installed from the open-source repo has one beat. When the engine lacks the orchestration a template names, it falls back to one beat and the world still plays.

See the graph a template uses:

```bash
neonrp engine graph --template <template folder>
```

Edit the graph (add an edge, change a condition) on the local orchestration board. It is saved in the template as a patch on the default graph. The agent does not need to write graphs by hand.

<!-- section: ops -->
## Tool calls: the agent edits files, the engine runs ops

Two separate things:

- **While creating**, the agent edits files: `template.json`, the map and data under `world/`, character folders, plot packs.
- **While playing**, the world can only *propose* changes each beat, as ops (move, change a variable, create an instance …). The engine checks them before they land. Rule packs register the ops.

Tools inside the narration use brackets. The shape says whether to wait:

| Form | Meaning |
|---|---|
| `[op args]` | Synchronous tool: stop here, continue after the engine answers. E.g. `[dice 1d20+2 vs 12]` · `[ask Elena]` · `[player.gold -12]` |
| `[~op args]` | Tool that does not wait: the engine does it, the narration continues. E.g. `[~map]` |
| `<…>` | A message from the engine to the model; the model never writes it |

So the agent does not write ops into files and does not fake run state. It writes the data the ops read: variable ranges, connections between places, price lists, plot trigger conditions. Details: [Propose → verify → apply](/docs/concepts/ops) and [How a turn runs](/docs/concepts/turn-flow).

<!-- section: install -->
## Install the skill

The skill is at the root of the open-source repo [WorldLines](https://github.com/LudicDynamics/WorldLines):

| Agent | Where | Instructions file |
|---|---|---|
| Claude Code | `.claude/skills/world-creation/` (this repo only) or `~/.claude/skills/world-creation/` (any folder) | `CLAUDE.md` |
| Codex | `.agents/skills/world-creation/` | `AGENTS.md` |

The simplest way: clone the repo and open Claude Code or Codex at its root. The root `CLAUDE.md` / `AGENTS.md` already list the skill.

To use it in your own template store, copy `.claude/skills/world-creation/` to `~/.claude/skills/`.

The engine:

```bash
uv tool install worldlines      # installs both worldlines and neonrp
```

<!-- section: flow -->
## Steps

**1. Write the spec.** Fill in `references/world-spec-template.md` from the skill: id, language, rule pack, contract, places, people, opening, plot and endings, world data. Write the content in the target language; keep ids ASCII. Example: `examples/tidepool/world-spec.md`.

**2. Hand it to the agent.** "Build a template from this spec." The agent runs:

```bash
neonrp template new tidepool --title "Tidepool" --lang en --pack rpg --contract open-adventure@1 --store ~/.worldlines/templates
```

When the spec is close to a built-in template, it uses `neonrp template fork pct-house <id>` or `fork stoneford-town <id>` instead. It copies the spec into the template folder as the source for the work.

**3. Open the local web workbench.**

```bash
worldlines --no-browser         # http://127.0.0.1:8787; add --port when the port is taken
```

| Address | Shows |
|---|---|
| `/local?screen=tpl&edit=<id>` | Template: card, contract, Lint, asset slots (upload or generate images here) |
| `/local?screen=duo&edit=<id>` | World · Characters: map, plot, schema, data |

The page reads the files on disk. Reload after each pass to see it.

![Template page: contract, Lint, asset slots](../../images/coding-agents/template.jpg)

![World · Characters page: the map drawn from the folders](../../images/coding-agents/world.jpg)

**4. The agent writes in passes.** Card and mode → map → lore and data → people → opening → plot and endings → art prompts. After each pass it runs lint and tells you what changed. You upload or generate the images on the Template page.

**5. Play-test.** This uses the model you configured. Web: "Run on the test bench →" on the Template page. Terminal: run `neonrp` and pick the template in the launcher.

<!-- section: lint -->
## Lint keeps it runnable

Lint first builds the template into a run, then checks references, assets, prompts, plots, the contract and languages. Each finding is a **block** (stops publishing) or a **warn** (a reminder).

```bash
neonrp template lint <template folder>      # last line: publishable / NOT publishable
(cd <template folder>/world && neonrp validate)
neonrp template build <template folder> /tmp/try-<id>
```

The agent's rule: **keep fixing until 0 block.** Report each block's text and the fix to the author. Read every warn; fix what can be fixed.

Publishing has one more check. When you click "Publish" on the Template page, the engine checks five things first. If one fails, nothing is sent:

| Check | Fails when |
|---|---|
| Linked characters are in the local library | a `{"lib": …}` target is missing |
| No secrets | a file holds something that looks like an API key |
| No lint block | there is still a blocking problem |
| Card in four languages | zh / en / ja / ko is missing a title or pitch |
| A cover | `card.cover` does not point to an image in the template |

The platform runs its own automatic checks after it receives the upload. See [Lint](/docs/creators/lint) and [Publish to the Hub](/docs/creators/publish). The author clicks Publish.

<!-- section: skill -->
## Where the skill is

| File | Contents |
|---|---|
| `.claude/skills/world-creation/SKILL.md` | The steps: setup → read the spec → create the template → open the workbench → write in passes → checks without a model → play-test → hand off |
| `.claude/skills/world-creation/references/world-spec-template.md` | The spec form, and the four contracts at a glance |
| `.claude/skills/world-creation/references/spec-to-files.md` | Which files each spec section becomes, with tested examples |
| `.claude/skills/world-creation/examples/tidepool/world-spec.md` | A complete small spec |

The Codex copy is in `.agents/skills/world-creation/`. Every template folder also has `AGENTS.md` and `spec/`, which the agent reads before editing; see [For agents](/docs/agents/overview).

The engine package carries the same copy: `neonrp spec skill` prints its folder on your machine, `neonrp spec skill world-creation` prints `SKILL.md`. The engine does not install it into any agent; to use it, put it in the agent's skills folder as in "Install the skill" above.
