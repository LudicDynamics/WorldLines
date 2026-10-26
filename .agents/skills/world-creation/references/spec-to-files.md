# Spec section → files

Paths are relative to the template folder `T`. Examples come from `examples/tidepool/world-spec.md`, built and linted
(0 block) with the steps in `SKILL.md`. Field meanings: the spec file named in each heading.

## Header lines → `template.json` (spec/template.md §3)

```json
{
  "id": "tidepool",
  "card": {"title": "潮池镇 · 灯塔熄灭的那晚", "pitch": "海边小镇的灯塔三天没亮。……", "lang": "zh", "tags": ["海边", "小镇", "寻人"]},
  "mode": {"ending": "multi", "freedom": "semi"},
  "play_contract": "open-adventure@1",
  "world": {"path": "world"},
  "pack": {"name": "rpg", "mixins": [], "engine": {"turn": {"mode": "v3"}}},
  "souls": [{"sid": "axi", "path": "souls/axi", "role": "npc"}],
  "plots": ["plots/P01"],
  "recipe": {"style": "水彩,冷灰海色,唯一暖色是风灯的橙光;无文字"}
}
```

Keep the keys `template new` / `fork` wrote (`schema`, `version`, `uses`, `lint`). Change `uses` only when the author asks
for a different orchestration (spec/template.md §2a).

## Places → map folders (spec/world.md §3.1–3.3)

One town = `game/locations/T001/location.json` + `game/towns/T001/town.json`. One place = one folder under the town.
Town ids match `^[A-Z]{1,3}\d{2,4}$`. Every town has at least one `gate`; every place is reachable from a gate.

```text
world/game/world/world_map.json            {"world_id": "W001", "name": "潮池镇", "time": {"day": 1, "clock": "17:30"}}
world/game/locations/T001/location.json    {"name": "潮池镇", "type": "town", "pos": [0, 0], "entry": "pier", "isolated": true, "summary": "…"}
world/game/locations/T001/pier/location.json
    {"name": "渡船码头", "type": "gate", "pos": {"x": 40, "y": 200}, "connections": ["square", "inn"], "summary": "…"}
world/game/towns/T001/town.json            {"name": "潮池镇", "overview": "…", "entry_points": ["pier"]}
world/game/meta/run_state.json             {"location": {"node_id": "T001", "subnode_id": "pier"}, "time": {"day": 1, "clock": "17:30"}, "turn_count": 0}
```

A single town with no roads out: `"isolated": true`. Several towns: add `routes` in `world_map.json` and `ports.up`
on the gates (world §3.2).

## Premise, World data → lore and rules (spec/world.md §3.7)

| Spec | File | Who reads it |
|---|---|---|
| Premise (what everyone may know) | `world/game/lore/story.md` | narration context; also decides the world language |
| Rumors | `world/game/lore/rumors.md` | narration context |
| The truth behind the plot | `world/game/lore/gm-truth.md` | host only; characters cannot read it |
| Prices, distances, tides, laws | `world/game/rules/<topic>.md` | referee and host |
| Language | `world/manifest.json` `{"lang": "zh"}` | small worlds without much lore |

## People → souls and background NPCs

A character who thinks (spec/soul.md §6, recommended minimum):

```text
souls/axi/soul.json                  {"sid": "axi", "name": "Axi", "name_local": "阿汐"}
souls/axi/soul.md                    ## Core Presence — looks, voice, will / won't
souls/axi/persona/motivations.json   {"motivations": ["渡船不停", "知道老顾那晚为什么点了三次灯又灭掉"]}
souls/axi/run_state.json             {"sid": "axi", "location": "T001/pier", "status": {"mood": "wary"}}
```

List it in `template.json` `souls`. A character with no `location` is nowhere and does not act.

A background person the narrator plays (spec/world.md §3.3):

```json
// world/game/towns/T001/npcs.json
{"town_id": "T001", "npcs": [{"id": "innkeeper", "name": "钟婶(旅店老板娘)", "role": "innkeeper", "location": "inn"}]}
```

## Opening → `world/game/meta/game-start.json` (spec/world.md §3.12)

```json
"startup": {
  "opening_scene": {"zh": "渡船靠岸时天快黑了。……"},
  "opening_choices": {"zh": ["跟阿汐打听灯塔的事", "先去潮声旅店落脚", "走到广场看看", "直接朝北礁走"]},
  "read_first": ["game/meta/game-start.json", "game/meta/run_state.json", "game/lore/story.md", "game/rules/town.md"]
}
```

With at least one soul in the world, the opening is shown as written (no model call). Up to 4 choices are shown.

## Plot and endings → `plots/P01/plot.json` (spec/template.md §5)

```json
{
  "id": "P01", "title": "灯塔熄灭的那晚",
  "stages": [{"name": "打听", "goal": "弄清灯塔那晚发生了什么"}, {"name": "上礁", "goal": "趁退潮去北礁"}, {"name": "塔里", "goal": "在灯塔里找到老顾留下的东西"}],
  "entries": {"P01-log": {"class": "item", "name": "守塔日志", "parent": "T001/lighthouse", "clue": true}},
  "triggers": {
    "P01.reach": {"when": {"entry": "T001/lighthouse_path", "event": "enter"}, "if": [{"var": "P01.stage", "<": 1}], "once": true,
                  "then": [{"to": "var", "var": "P01.stage", "set": 1}]},
    "P01.true":  {"when": {"text": "player"}, "if": [{"var": "P01.stage", ">=": 2}, {"text": ["日志"]}, {"who": "阿汐", "at": "player"}], "once": true,
                  "then": [{"to": "end", "ending": "E1"}]}
  },
  "endings": {"E1": {"title": "第四次灯", "kind": "true"}, "E2": {"title": "涨潮", "kind": "fail"}},
  "prompt": {"guide": "…"},
  "reveal": {"zh": "…"}
}
```

Each ending needs at least one trigger branch that emits it, and one branch emits at most one ending (lint
`loop.distinct` is a block). A `fail` ending also gives a player death its exit (lint `contract.deaths`).
`mystery-trpg@1` also requires `truth_quiz.questions` (contract §4).

## Art → slots (spec/template.md §6)

`neonrp template slots "$T"` lists every slot. `MISSING` = required to publish (cover, level maps, soul portraits).
Write `recipe.style` from the spec's style line and leave the images to the author (Template page: Upload / Generate).
