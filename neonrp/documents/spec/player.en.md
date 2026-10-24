# Player-side data spec (avatars · player data · chat threads)

What belongs to the player: the avatars they make for themselves, their record across runs (characters gained, characters talked with, endings, achievements, rewards waiting to be paid out) and their private chats with characters. All of it lives under `~/.worldlines/`, owned by the launcher, and is **not stored in a template or a run folder** (the engine / launcher line). The one exception is when you choose to start a run as your avatar: the avatar's fields are copied into that run's protagonist profile (see 2.3); the avatar itself stays in `~/.worldlines/players/`. Local and browser builds use the same HTTP.

> Status: **implemented** (in the code, with tests) · **convention** (an agreed practice) · **in design**.

## 1. Where it lives

| What | Path | Status |
|---|---|---|
| Avatars | `~/.worldlines/players/<file>.json` (one file per avatar, named after it) | implemented |
| Current avatar | `~/.worldlines/players/.current` (holds the file name; when never set and there is exactly one avatar, that one) | implemented |
| Avatar portrait | `~/.worldlines/players/<file>.portrait.<png\|jpg\|webp>` | implemented |
| Player data | `~/.worldlines/player-data/<player>.json` | implemented |
| Memory snapshot of a gained character | `~/.worldlines/player-data/<player>/souls/<tpl>/<sid>/` (the run's character folder at the moment it was gained; `assets/` not copied) | implemented |
| Chat thread with a character | `~/.worldlines/player-data/<player>/chats/<tpl>__<sid>.jsonl` (one message per line) | implemented |

`<player>` is `local` by default; the environment variable `WORLDLINES_PLAYER_ID` names another (a signed-in account uses its own file). Code: `src/neonrp/core/player_data.py:player_id`.

## 2. Avatars

An avatar is the protagonist the player makes for themselves. It stays on this machine, is never published, and is separate from the character library (`~/.worldlines/souls/`): a character cannot be an avatar and an avatar never becomes a character. Code: `src/neonrp/players.py`.

### 2.1 Fields

| Field | Meaning | Status |
|---|---|---|
| `name` | name (required when creating) | implemented |
| `summary` | short description | implemented |
| `gender` · `personality` · `appearance` · `backstory` | gender · personality · looks · background | implemented |

Only these six fields are kept; anything else is ignored.

### 2.2 Endpoints

| Endpoint | Meaning | Status |
|---|---|---|
| `GET /api/v1/local/avatar[?tpl=<template id>]` | `{current, avatar, avatars: [{file, name, summary, data, current, portrait_url}]}`; with `tpl`, also `prefill: {fields: {<field id>: value}}` (see 2.4) | implemented |
| `POST` / `PUT /api/v1/local/avatar` `{name?, summary?, …, file?}` | with `file` = edit that one (fields not sent are kept); without = create (needs `name`, else 400). The written avatar becomes the current one. Returns `{ok, file}` | implemented |
| `POST /api/v1/local/avatar/current {file}` | switch the current avatar; 404 when there is no such avatar | implemented |
| `POST /api/v1/local/avatar/portrait?file=` | the request body is the image bytes (png / jpg / webp); returns `{ok, portrait_url}`; 400 when not an image or no such avatar | implemented |
| `GET /api/v1/local/avatar/portrait?file=` | the portrait image (with an ETag) | implemented |
| `avatars` in `GET /api/v1/local/souls` | the same list, each row with `current` and `portrait_url` | implemented |

### 2.3 Opening a run with the avatar as the player

`POST /api/v1/play/session {slug, avatar: "current" | <file>}` applies only to **a run opened by this call** and only when the **builder was not used** (no `player`). The avatar's fields are written over the run's `game/player/profile.json` (for each field it sets, the world's per-language copies `name_i18n` / `intro_i18n` / `<field>_i18n` are dropped); a portrait, if any, becomes the run's player portrait (`game/player/assets/portrait.*`). Older worlds without `profile.json` take the same merge as the TUI's new game. The engine **never applies an avatar on its own**: without `avatar` the run keeps the world's own protagonist. Code: `src/neonrp/players.py:apply_avatar_to_run`, `src/neonrp/webui/engine_routes.py`. implemented

Which kind of protagonist a world has is in the template meta's `pc: {fixed, builder}` (every row of `GET /api/v1/local/templates` and `/api/v1/local/templates/<id>`): `fixed` = the world writes its own protagonist (`players[0].name` in its `playthrough.json` is a name, not the scaffold's "Player"); `builder` = it has a builder screen. Offer "start as my avatar" only when `builder` is true or `fixed` is false. A template may say it outright: `template.json` `player.fixed: true | false`. Code: `src/neonrp/template/__init__.py:pc_meta`. implemented

### 2.4 Builder prefill

When a template has a builder (`template.json` `player.builder`), `prefill.fields` from `GET /api/v1/local/avatar?tpl=<id>` holds what the current avatar can fill: every builder field with `kind: text` whose `to` writes `player/profile.json:<name|summary|gender|personality|appearance|backstory>`, valued from the avatar's field of the same name (cut to the field's `max`). The front end merges it into the draft; opening the run still goes through the builder's checks. Code: `src/neonrp/players.py:builder_prefill`. implemented

## 3. Player data

One file per player, `GET /api/v1/local/player-data[?player=<id>&lang=]`:

```
{player,
 characters: [{sid, name, world, how, memory: full|fresh, at}],
 talked:     [{sid, name, world, at}],
 endings:    [{id, title, world, at}],
 achievements: [{id, world, source, at, title?, desc?, points?, scope?}],
 rewards:    [{id, kind, amount?, cg?, world, source, status: pending, at}],
 cards:      [{id, world, kind, title, desc, rarity, image?, version, run, source, at}],
 runs:       [{world, run, exit, ending?, version, at}]}
```

`world` is always a template id (the `id` in the run's `game/meta/template.json`; for a run not built from a template, the run folder's name).

| Record | Written when | Status |
|---|---|---|
| `characters` (gained) | a character's `take_when` holds (`companion_at_ending` = it is a companion and present when an ending lands; `ending:<id>` = that ending lands), or it is taken at a settlement (`how` = settlement · truth_quiz). Only `takeable` characters can be gained. With `memory: full` a memory snapshot is taken too (see 1) | implemented |
| `talked` | the first time the player exchanges words with a `standalone` character: a direct chat, or it answered the player in words during a run. **Not a gain** — it does not enter `characters` | implemented |
| `endings` | when a run's ending lands (one row per ending per world) | implemented |
| `achievements` | on unlock (`core/achievements.py`). On read, each row carries `title` / `desc` / `points` / `scope` in `lang`: built-ins from the four-language table, a template's own from that template's `template.json` `achievements`; unknown ids come back as they are | implemented |
| `rewards` | earned by a settlement / milestone / achievement and not yet paid out by the platform: written `pending`, the platform marks them `granted` | implemented |
| `cards` | cards a template's `rewards` handed out (`core/rewards.py`). Each is a copy of the card as it was when earned (its picture copied into the player's folder) and is never taken back, even if the author drops it; `version` is the template's version then, and the player may pull the new face when the author ships one | implemented |
| `runs` | one row per run that reached its exit (settlement): `exit` is the kind of exit, plus `ending` when an ending landed | implemented |

`memory` on `characters`: `full` = with this run's memory (a snapshot is taken); `fresh` = the character as its author wrote it, without this run's memory (collection rules, the settlement's floor). A later `full` take upgrades the record.

A run made from a Free Zone work (`zone: open`) hands out no cards, and no character comes home from it.

The two switches on a character (`standalone`, `takeable` / `take_when`) live in its `soul.json`; see [soul.en.md](soul.en.md) 3.1.

## 4. Continuing a world

| Endpoint | Meaning | Status |
|---|---|---|
| `GET /api/v1/local/plays?lang=[&all=1]` | `{plays: [{session_id, template, world, turns, last_modified, cover_url, in_memory}]}`, newest first; by default only runs with at least one turn, `all=1` lists all. `world` = the template's title localized to `lang`; `cover_url` = the template's card cover (null when it has none), `/api/v1/local/worlds/<slug>/cover` for older worlds | implemented |
| `GET /api/v1/play/saves` | the save list (each row with `template` and `turns`) | implemented |
| Continue | `POST /api/v1/play/session {slug: <session_id>}` | implemented |

## 5. Chat threads

Private chats with characters (the phone chat screen). The endpoints, who can be talked to, what the character knows and stickers are in [soul.en.md](soul.en.md) 4.5. The player side keeps two things:

| What | Rule | Status |
|---|---|---|
| Thread file | `chats/<tpl>__<sid>.jsonl`, one `{id, from: me\|soul, kind: text\|sticker, text?, sticker?, at}` per line; a failed send writes nothing | implemented |
| Memory source | a gained character reads its `souls/<tpl>/<sid>/` snapshot (`memory: full`); one not gained reads the template's character folder (`memory: trial`) | implemented |

## 6. Reference implementation

| What | Code |
|---|---|
| Avatars | `src/neonrp/players.py` |
| Avatar endpoints | `src/neonrp/webui/launcher_routes.py:_avatar_route` |
| Player data | `src/neonrp/core/player_data.py` |
| Achievements | `src/neonrp/core/achievements.py` |
| Continuing a world | `src/neonrp/commands/web.py:_local_plays` · `_library_saves` |
| Direct chat | `src/neonrp/core/soul_chat.py` |
| Tests | `tests/test_hub_my_page_local.py` · `tests/test_standalone_player_data.py` · `tests/test_soul_chat.py` |
