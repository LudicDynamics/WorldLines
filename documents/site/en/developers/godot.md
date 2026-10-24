---
title: "Godot"
description: "A Godot game talks to a local engine process: one client node speaks worldlines.net/1, art comes from an art pack."
---

<!-- section: arch -->
## Architecture

```text
Godot game  ── JSON-RPC (POST /rpc) + SSE (/rpc/events) ──>  neonrp serve (the engine process)
```

Godot connects to a local engine process (the way an editor talks to a language server) instead of embedding the engine in the game. The engine is the one truth of the run: the game sends a line or an action, the engine rules on it and lands it, then streams the prose and beat events back. The engine itself is open source (Apache-2.0); the PyPI release adds the two-beat orchestration, which is not open source, and the game-side code works with both.

A complete example lives in `worldlines/examples/clients/godot` (Godot 4.5, Greyoak House): a title screen, the scene changing as you move, the people in the room, dialogue appearing as it is written, d100 checks rolled on screen, clues, a map of the house, an ending with its CG.

<!-- section: run -->
## Run it

```bash
neonrp template build pct-house ./house
neonrp serve --project ./house --port 8788      # prints the url and a token
godot --path worldlines/examples/clients/godot  # host + token → enter
```

A run made with `template build` has no model chosen yet; it falls back to your global settings, and without one it answers with placeholder text and no model call. The easy way: start a Greyoak House game in `worldlines` (the model is chosen when the game starts), then point `neonrp serve --project` at that run's folder under `~/.worldlines/plays/`.

<!-- section: node -->
## The client node

The protocol is in one file: copy `addons/worldlines/` into your project.

```gdscript
var wl := preload("res://addons/worldlines/client.gd").new()
add_child(wl)
wl.chunk.connect(func(text, who, beat): …)     # prose as it is written (who = a character, "" = the host)
wl.beat.connect(func(event, data): …)          # node.enter · plan.beat / resolve.beat · dice · state.changed · run.settled …
wl.beat_kinds_loaded.connect(func(k): …)       # how this run's beats are shown
wl.ask_user.connect(func(id, q, options): wl.answer(id, options[0]))
wl.failed.connect(func(message): …)            # a readable sentence: wrong token, no host, a turn still running
await wl.connect_to_host("http://127.0.0.1:8788", token)
var result: Dictionary = await wl.send_line("Look around.")
```

| signal / call | |
|---|---|
| `connect_to_host(url, token)` | `session.hello` → `beat_kinds_loaded` → starts the event stream |
| `send_line(text)` | `turn.send`; returns when the turn is over (the prose arrives meanwhile) |
| `cancel()` · `answer(id, value)` | `turn.cancel` · answer the host's `ask_user` |
| `chunk` · `beat` · `turn_started` · `turn_finished` | from `/rpc/events` (`engine/stream` · `engine/beat` · `engine/event`) |
| `get_json(path)` | read an HTTP route directly, e.g. `/state`, `/api/v1/play/schema` |

The game knows no particular beat: names, colours, the input hint and dividers come from the host's `beat-kinds`. So the open engine (resolve beat only) and the release (planning + resolve) run with the same code.

The event stream is read over a raw TCP (+ TLS) connection, not `HTTPClient`: the host answers it as HTTP/1.0 with no length, which `HTTPClient` treats as an empty body. After a drop it reconnects and asks for what it missed (`since`).

<!-- section: types -->
## Types

For typed properties per variable, generate a GDScript mirror as well: `neonrp template contract pct-house --gd` (see [Code generation](/docs/developers/codegen)). It does no networking; pass the variable changes you receive to `apply_change`.

<!-- section: assets -->
## Art

The example reads an art pack: `worldlines/examples/clients/art/<world>/art.json` (which picture goes with which place, person, ending, clue); `WL_ART_DIR` points elsewhere. Pictures not drawn yet get placeholders. `art/pull.sh` copies pictures from the template's `assets/` and resizes them.

<!-- section: checks -->
## Checks

```bash
godot --headless --path . -s tests/scene_check.gd                          # the game builds
WL_HOST=… WL_TOKEN=… godot --headless --path . -s tests/smoke.gd           # one line through the client node
```
