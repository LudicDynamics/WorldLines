# NeonRP

**A world-simulation engine for AI role-play: let the model tell the story, let the world keep its rules.**

Pure prompting drifts and agrees with everything; letting a model freely edit files corrupts state; a rule engine can't
understand what a player actually says. NeonRP sits in between: the model proposes, the engine validates and writes,
and the world, the player and every character keep their own agency.

NeonRP is the engine of [WorldLines](https://github.com/LudicDynamics/WorldLines) and is released under **Apache-2.0**.

## What it does

- **One line, one turn.** The player says what they want to do; the engine rolls the dice that apply, lets the characters
  present act in turn, has the narrator write the turn (calling tools where an outcome decides what comes next), and
  validates and commits one state transition. A turn is an orchestration graph that packs and templates can patch.
- **Three parties, isolated.** World, player and characters each have their own agency. What the player says is an
  *attempt*, not a fact; characters decide for themselves.
- **State is files.** A world is a folder of JSON / Markdown you can read, diff and version. Closed schema (registered
  variables) and open schema (classes whose instances can grow during play), each change checked before it lands.
- **Worldlines.** Every turn is a commit; roll back, branch and compare timelines.
- **Packs and templates.** Rules live in packs (`rpg`, `pct`, `werewolf`, `monopoly`, mixins such as `economy` and `factions`); a template binds
  a world + souls + a pack + prompts, plots and asset slots, and is linted before it can be published.
- **An SDK.** Register and subscribe to state from Python; a generated contract (TypeScript / GDScript) lets other front ends
  such as Godot talk to the engine.

## Install

```bash
uv tool install neonrp          # the engine + CLI + terminal UI
uv tool install worldlines      # the WorldLines product (web UI + launcher), brings neonrp with it
```

<details>
<summary><b>One-line installer / desktop app / mirrors</b></summary>

```bash
curl -LsSf https://worldlines.gg/install.sh | sh        # macOS / Linux (installs uv if missing, then worldlines)
irm https://worldlines.gg/install.ps1 | iex             # Windows PowerShell
```

Desktop builds are attached to the [WorldLines releases](https://github.com/LudicDynamics/WorldLines/releases).
Behind a slow PyPI connection, point uv at a mirror first, e.g.
`export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple` — `neonrp self-update` honors it too.

</details>

## Play

```bash
neonrp tui                      # pick a built-in world and play; the first line is 「开始游戏」 / "start the game"
```

Inside a world folder:

```bash
neonrp validate                 # is this world playable? (JSON, souls, opening, lint)
neonrp tui --play               # play it
neonrp commit --help            # the commit graph: log, branch, roll back
```

Templates:

```bash
neonrp template list
neonrp template lint  <dir>.template        # every problem; blocks stop publishing
neonrp template build <dir>.template <run>  # build a playable run
cd <run> && neonrp tui --play
```

Run `neonrp --help` for every command.

## Documentation

- Specs — [world](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.en.md) ·
  [soul](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.en.md) ·
  [template](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.en.md) ·
  [contract](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.en.md) ·
  [pack](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.en.md)
- Concepts, creator and developer guides — [docs.worldlines.gg](https://docs.worldlines.gg)
  (source: [`documents/site`](https://github.com/LudicDynamics/WorldLines/tree/main/documents/site))

## Develop

```bash
uv sync --all-extras --dev
uv run ruff check src tests
uv run pytest -q
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright © 2026 worldlines-nikoloside, redoctober (Ludic Dynamics).
"NeonRP" and "WorldLines" are names of Ludic Dynamics; the license does not grant rights to use them.
