# Play contract spec (`worldlines.play-contract/1`)

> Status: fields, lint and settlement are **implemented** (`src/neonrp/template/contract.py` · `src/neonrp/core/settlement.py`);
> §6 the soul protocol is **in design**. The four contracts in force: `neonrp spec contracts`.

## 1. What it is

A play contract states **what a kind of game must give the player**: how it starts, how it ends, how many endings, what
it rewards, how deaths settle, what it outputs at the end, and what it takes to publish. A template promises one with the
top-level `"play_contract": "<id>@<version>"`.

- A contract governs **experience, never orchestration**: how beats run is the orchestration graph's job (template spec 3.1 `orchestration`); one contract can sit on different graphs.
- Lint checks a template against its contract (§4); when a run reaches its exit the engine writes the settlement (§5).
- Files: `<id>.play-contract.json`, looked up on `NEONRP_PLAY_CONTRACT_PATH` (`:`-separated) → the source tree's `worldlines/contracts/` → the copy an installed release carries.

The four official ones:

| id | name | exit | endings | to publish |
|---|---|---|---|---|
| `mystery-trpg` | sandbox TRPG | an ending; the truth must be revealed | ≥ 3, a true ending among them | no lint block + reach one ending |
| `open-adventure` | open adventure | a segment settles (a day) | not required | no lint block + settle one segment |
| `murder-mystery` | murder mystery | an ending after the accusation; the truth must be revealed | ≥ 2, a true ending among them | no lint block + reach one ending |
| `romance-companion` | romance companion | a segment settles (a date) | not required | no lint block + settle one segment |

## 2. Minimal example

```json
{
  "schema": "worldlines.play-contract/1",
  "id": "my-mystery",
  "version": 1,
  "title": {"zh": "我的解谜", "en": "My Mystery"},
  "pitch": {"en": "One line on what this kind of game gives the player."},
  "entry": {"opening": "required", "cast": "fixed"},
  "exit": {"on": "ending", "reveal": "required"},
  "endings": {"min": 2, "require": ["true"]},
  "rewards": {"player": ["ending_cg"], "soul": ["memory_carry"], "world": []},
  "deaths": {"player": {"exit": "ending", "ending_kind": "fail"}},
  "outputs": ["ending_id", "truth_reveal", "cg_unlocked"],
  "publish": {"lint": "no_block", "test_run": "reach_one_ending"}
}
```

## 3. Fields

| key | type | meaning | status |
|---|---|---|---|
| `schema` | str | always `"worldlines.play-contract/1"` | implemented |
| `id` · `version` | str · int | a template refers to `"<id>@<version>"`; an id alone takes the current version | implemented |
| `title` · `pitch` | localized object | name and one line for the card; any of `{zh, en, ja, ko}` | implemented |
| `entry.opening` | `"required"` | an opening must exist (the world's `game-start.json` `startup.opening_scene`) | implemented (lint) |
| `entry.cast` | `"fixed"` \| `"open"` | fixed: the template casts everyone (cast list, world-native souls or a rule pack's seat class); open: players may bring characters in | implemented (lint · fixed) |
| `entry.roles` | `"assigned"` | every character is handed a role at the start (murder mystery / werewolf) | convention |
| `exit.on` | `"ending"` \| `"segment"` | the run ends at an ending; or it settles per segment and goes on | implemented |
| `exit.segment` | `"day"` \| `"date"` … | what a segment is; `day` settles when `time.day` moves on | `day` implemented |
| `exit.via` | str | how the ending is reached (e.g. `accusation`) | convention |
| `exit.reveal` | `"required"` | the truth is revealed at the ending: every plot with endings needs a `reveal` | implemented (lint) |
| `endings.min` | int | at least this many endings | implemented (lint) |
| `endings.require` | list[str] | ending kinds that must exist (an ending's `kind`, e.g. `true` · `fail`) | implemented (lint) |
| `rewards.player` · `.soul` · `.world` | list[str] | what a run gives: `ending_cg` · `clue_codex` · `trust` · `affection` · `memory_carry` · `map_unlock` … | recorded: implemented; carried over: mostly convention |
| `deaths` | object | how deaths settle, see 3.1 | implemented |
| `outputs` | list[str] | what the settlement must carry: `ending_id` · `truth_reveal` · `accusation` · `cg_unlocked` · `segment_id` … | `truth_reveal` · `accusation` implemented |
| `settlement.truth_quiz` | `"required"` | the settlement's three truth questions **must be there**, written by the plot: `plot.json` `truth_quiz.questions` (3 questions, q and options in four languages, `answer` the right index; `reward_soul`, if given, a sid of the cast that may leave). `mystery-trpg` has it. The engine writing them from the solution is a fallback (open zone / older templates), not the way (see 5.1) | implemented (lint · 10-16) |
| `settlement.truth_quiz_points` | `{settle, per_right, fallback}` | the three truths' Worldlines credits (whole numbers ≥ 0): every run `settle + per_right × right answers`; `fallback` on top when nobody comes home with the player (not all right · no questions · all right but that character is already in the collection with full memory). `mystery-trpg` defaults to 200 / 100 / 0 (finishing a run 200, +100 per right answer, at most 500; niko 10-21); a template's `template.json` `settlement.truth_quiz_points` overrides any of them. The amounts are data, never in the engine; unsaid = 0 (lint `truth_quiz.points` warns). Written as pending rewards | implemented (10-20) |
| `publish.lint` | `"no_block"` | no lint block before publishing | implemented |
| `publish.test_run` | `"reach_one_ending"` \| `"settle_one_segment"` | how far the test bench must get before publishing | convention |
| `engine` | object | how a turn runs (optional): merged into the engine config after the rule pack, before the world's own `game/meta/engine.json` (which can still override it). Public contracts carry none; the released values live in the private layer's `contracts/<id>.engine.json`, laid on at run time, never saved | implemented |

### 3.1 `deaths`

```json
"deaths": {
  "player":    {"exit": "ending", "ending_kind": "fail"},
  "companion": {"settle": "record", "plot": "optional"},
  "other":     {"settle": "record"},
  "insanity":  {"exit": "ending", "ending_kind": "fail"}
}
```

- `player` · `companion` (a brought-in soul) · `other` (anyone else in the world) · `insanity` (a mind stat at 0, worlds that have one; key kept as insanity).
- `{"exit": "ending", "ending_kind": "fail"}`: the run exits on the template's first ending of that `kind` (with its CG / epilogue); none → a plain death exit (lint `contract.deaths` warn).
- `{"settle": "record"}`: only added to the settlement's `deaths`; the run goes on. `"plot": "optional"` = a plot may react to it.
- Missing entries: the player exits, everyone else is recorded.

## 4. Lint (against the contract)

| code | level | when |
|---|---|---|
| `contract.unknown` | block | the `play_contract` cannot be found |
| `contract.entry` | block | an opening is required but missing; a fixed cast is required but nobody is cast |
| `contract.exit` | block | the run exits at an ending but no trigger reaches one |
| `contract.endings` | block | fewer endings than `min`; a `require`d kind is missing |
| `contract.reveal` | block | the truth must be revealed but a plot with endings has no `reveal` |
| `contract.rewards` | block | `ending_cg` is a reward but an ending has no image slot |
| `contract.deaths` | warn | a death exits on an ending kind the template does not have |
| `contract.truth_quiz` | reviewed zone block · open zone warn | the contract requires the truth questions (`settlement.truth_quiz: required`) and no plot writes `truth_quiz.questions` |
| `truth_quiz.schema` | reviewed block · open warn | `truth_quiz` is malformed: not 3 questions, a q / options missing, `answer` not an option's index (a language layer that breaks it too; `where` carries `[lang]`) |
| `truth_quiz.lang` | reviewed block · open warn | one of the four languages (zh · en · ja · ko) lacks a question or option: write `{zh, en, ja, ko}` texts or translate `truth_quiz` in `i18n/<lang>/plots/<P>/plot.json`; a layer that changes a right answer too |
| `truth_quiz.reward_soul` | reviewed block · open warn | `reward_soul` is not a sid of the cast, or that character is `takeable: false` (three right would give nothing) |
| `truth_quiz.points` | warn | neither the contract nor the template says `settlement.truth_quiz_points` (the run's three truths give 0 credits), or it is not `{settle, per_right, fallback}` in whole numbers ≥ 0 |

Reviewed / open = the template's `zone` (`reviewed` / `open`); unsaid counts as open. A plot's own lint (`neonrp plot lint`) knows no zone: shape problems are warnings there, graded by zone in the template lint.

## 5. Settlement (what the engine writes at the exit)

`game/meta/settlement.json` (`worldlines.settlement/1`), plus a `run.settled` event:

```json
{"schema": "worldlines.settlement/1",
 "exit": {"kind": "ending" | "death" | "insanity", "id": "E01", "turn": 12},
 "cg_unlocked": ["E01"], "epilogue": "…", "deaths": [{"who": "…", "name": "…", "kind": "player", "turn": 9, "cause": "…"}],
 "rewards": {"player": {"ending_cg": ["E01"]}, "soul": {"trust": {"Winnie": 3}}},
 "contract": "mystery-trpg@1",
 "truth_reveal": {"text": "…"}, "accusation": []}
```

A segment contract (`exit.on: segment`) writes `game/meta/segments/day-<n>.json` per segment; the run goes on.

### 5.1 After the settlement: three truths · milestones · achievements · pending rewards (10-15)

| Call | What it does |
|---|---|
| `GET /api/v1/play/engine/settlement/quiz` | a sandbox mystery's (`mystery-trpg`) three truth questions: `{state: locked\|open\|answered\|unavailable, questions: [{id, q, options}], reward_soul, points: {settle, per_right, fallback}, result?}`. `locked` before the settlement (no question shows); the questions are the plot's `truth_quiz.questions` — **required** by the `mystery-trpg` contract (§3 `settlement.truth_quiz`, lint §4); `by` = `author`. The fallback (open zone / an older template without them — not the way): the engine writes them once from the solution (`by: model`, `meta/truth_quiz.json`); a model that does not answer in shape = `unavailable` (`by: none`; the player takes the credits: `POST {answers: []}`) |
| `POST /api/v1/play/engine/settlement/quiz {answers: [i,i,i]}` | graded once (again → the first result): three right → `reward_soul` comes home with full memory (`memory: full`; one already in the collection starting fresh is upgraded = delivered); nobody delivered (not all right · no questions · already home whole) → the `fallback` credits; every run also `settle + per_right × right answers` (§3 `settlement.truth_quiz_points`), all pending. The result carries `delivered` · `fallback` · `no_questions`. The floor is no longer taking one character home (niko 10-20); an old client's `take` is ignored |
| `GET /api/v1/play/engine/settlement/milestones` | this open adventure's milestones `{enabled, milestones: [{id, type: place\|job\|day\|stretch, label, points, art, generate}], settled}` |
| `POST /api/v1/play/engine/settlement/leave` | the player leaves: the milestones since the last leave settle, points (provisional, niko to set: place 30 · commission 75 · day 45 · stretch 30) and pictures pending; a place counts only when it has a picture (the author's or its scene image), at most 10 a run; leaving again settles only what is new |
| `GET /api/v1/play/engine/achievements` | every achievement this run can unlock (built-in + the template's), with `unlocked` / `at` |

An open adventure may go on forever: when 12 beats pass with no milestone, the stretch of road is one (`stretch`). A milestone need not have its own picture; `art` is, in order: the author's (the plot picture of that place / commission) `{kind: cg, slot}` → the parts for the front end to compose `{kind: composite, scene: <the scene slot where the player stands>, souls: [{iid, sid, name, slot: <sprite, else portrait>}], caption}` → `generate: {scene, caption}` for the front end's live-picture button (Voyager may press it; others see it greyed and go to the upgrade page; the engine never generates on its own).

Events (`/engine/beats`): `milestone {id, type, label, points, art, generate}` · `achievement.unlocked {id, title, desc, scope, points}`.
Built-in achievements: `first_ending` · `first_character` · `characters_5` · `first_milestone` (once per player) · `true_ending` · `all_endings` · `quiz_perfect` · `places_5` · `places_10` · `run_complete` (once per world); four-language names in `prompts/achievements.<lang>.json`.
The player data (`~/.worldlines/player-data/<player>.json`) gains `rewards: [{id, kind: points, amount, cg?, world, source, status: pending}]` — paying points out needs the platform; the engine only records them pending.

### 5.2 Reward cards · the contract's achievements · 「a run finished」 (10-18)

A template declares its reward cards as data — `template.json` `rewards` (the engine names no world's things):

```json
"rewards": [{"id": "half_burnt_diary", "kind": "card", "rarity": "common",
             "title": {"zh": "…", "en": "…", "ja": "…", "ko": "…"}, "desc": {…},
             "when": "stage:P01:1",                       // or a list: every one holds
             "slot": "item.icon:I801"}]                   // or "image": "assets/reward-<id>.webp"
```

- `when` — the same conditions as achievements: `ending:<id>` · `ending_kind:<kind>` · `flag:<key>` · `stage:<plot>:<n>` · `var:<key>:<n>` (≥ n) · `places:<n>` · `character:<sid>` · `milestone:<n>` · `quiz_perfect` · `run_end`
- `kind` — `card` (the Hub's collection cards); any other kind is kept as written and shown as a card (lint warns). `rarity` — common · rare · epic
- picture — `slot` = a picture the template already has, else the reward's own slot `reward:<id>` (filled in the asset workbench like any other)
- the contract lets them out: `rewards.player` has `cards` (all four official contracts do); no contract = allowed; a Free-Zone template (`zone: open`) hands none out. Lint: an unreadable row blocks, everything else warns
- once each per world; kept in the player's record (`cards`, the picture copied beside it) — never taken back, not even when the author drops it. Each card keeps the template version it was earned under; when the author ships another, the Hub offers to pull its new face (a gained character's persona the same way; its memory stays)
- the settlement lists the run's cards: `rewards.player.cards: [id, …]`

A contract may carry its own `achievements` (same rows as a template's), for every world played under it — only conditions that name nothing of a world: `ending_kind:<kind>` · `places:<n>` · `milestone:<n>` · `quiz_perfect` · `run_end`.

「A run finished」 = the run reached its exit (`run.settled`). The player's record gets one `runs` row `{world, run, exit, ending?, version}` and the built-in `run_complete` (once per world) unlocks.

Event: `reward.granted {id, kind, world, title, desc, rarity, image?}`. Endpoints: `GET /api/v1/local/player-data?lang=` → `cards: [{id, world, kind, title, desc, rarity, image, version, upd, gone}]`, `characters[].upd` · `POST /api/v1/local/player-data/refresh {kind: cards|characters, world, id}` · `GET /api/v1/local/player-data/card?world=&id=` (the kept picture).

## 6. Soul protocol `souls` (in design)

What a character must bring in, what it is handed in the run, and what goes back to the library at the end (soul spec 4.4).

```jsonc
"souls": {
  "in":     {"sheet": "pct", "player": "required", "companion": {"min": 0, "max": 3}, "assets": ["portrait"]},
  "assign": ["role", "secret"],
  "out":    ["memory_carry", "trust"]
}
```

| part | meaning |
|---|---|
| `in.sheet` | the sheet it needs: `pct` (characteristics + d100 skills + a mind stat) · `rpg` · `none`; a linked soul without one → the converter makes `character/sheets/<contract id>.json` at the start of the run |
| `in.player` · `in.companion` · `in.assets` | whether a player is needed, how many companions, required assets |
| `assign` | what the world hands a character (role, secret, seat, side) — lives in that run only, never written back to the library |
| `out` | what a run writes back to the library; replaces today's `rewards.soul` |

## 7. Reference implementation

| What | Where |
|---|---|
| loading · lookup · lint against the contract · death rules | `src/neonrp/template/contract.py` |
| settlement · segments · fixed outputs | `src/neonrp/core/settlement.py` |
| the official contracts | `worldlines/contracts/*.play-contract.json` |
| the `set_play_contract` op · `neonrp template set-contract` / `contracts` | `src/neonrp/template/author.py` · `src/neonrp/commands/template_cmd.py` |
