# 灰橡宅 · Godot client (Godot 4.5 · a small game on a WorldLines host)

The same game as the TS example, in Godot: title screen, the scene behind you changing as you move (cross-faded), the
people in the room (the one speaking lights up), the dialogue with the prose as it is written, d100 checks rolled on
screen, clues as they turn up, a map of the house, the ending with its CG. It reads the same art pack as the TS
example (`../art/<world>/art.json`; `WL_ART_DIR` to point elsewhere) and draws stand-ins for pictures not drawn yet.

```
addons/worldlines/client.gd   the protocol in one node — copy addons/worldlines/ into your project
game/art.gd · game/dice.gd    the art pack · the checks lifted out of the prose
main.gd                       the screens
```

It knows no particular beat: names, colours, hints and dividers come from the host's `beat-kinds`.

## Run it

```bash
neonrp serve --project <a run of pct-house> --port 8788      # prints a token
godot --path .                                                # host + token → 进入
```

Checks:

```bash
godot --headless --path . -s tests/scene_check.gd                                          # the game builds
WL_HOST=… WL_TOKEN=… godot --headless --path . -s tests/smoke.gd                           # one line through the client node
WL_HOST=… WL_TOKEN=… WL_SHOTS=/tmp godot --path . -s tests/scene_play.gd                   # plays one line, saves screenshots
```

## The node

```gdscript
var wl := preload("res://addons/worldlines/client.gd").new()
add_child(wl)
wl.chunk.connect(func(text, who, beat): …)     # prose as it is written (who = a character, "" = the host)
wl.beat.connect(func(event, data): …)          # node.enter · <node>.beat · dice · state.changed · run.settled …
wl.beat_kinds_loaded.connect(func(k): …)       # how this run's beats are shown
wl.ask_user.connect(func(id, q, options): wl.answer(id, options[0]))
wl.failed.connect(func(message): …)            # a readable sentence: wrong token, no host, a turn still running
await wl.connect_to_host("http://127.0.0.1:8788", token)
var result: Dictionary = await wl.send_line("Look around.")
```

| signal / call | |
|---|---|
| `connect_to_host(url, token)` | `session.hello` → `beat_kinds_loaded` → starts the event stream |
| `send_line(text)` | `turn.send`; returns when the turn is over (prose arrives meanwhile) |
| `cancel()` · `answer(id, value)` | `turn.cancel` · `reply` to an `ask_user` |
| `chunk` · `beat` · `turn_started` · `turn_finished` | from `/rpc/events` (`engine/stream` · `engine/beat` · `engine/event`) |

The event stream is read over a raw TCP (+ TLS) connection, not `HTTPClient`: the host answers it as HTTP/1.0 with no
length, which `HTTPClient` treats as an empty body. After a drop it reconnects and asks for what it missed (`since`).
