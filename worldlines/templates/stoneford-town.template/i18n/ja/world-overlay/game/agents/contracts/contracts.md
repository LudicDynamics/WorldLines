# サブエージェント契約(読み書きの境界)

ストーンフォード・エレナは、実際のストーンフォード contract を明示的な souls で拡張したものだ。
`game/player/*` は引き続き heroine の互換投影であって、唯一の
キャラクターの正となる情報源ではない。

各サブエージェントは必ず:
- 許可されたファイル glob だけを読む
- 許可されたファイル glob だけに書く
- どのファイルをなぜ作成/更新するかを記した「patch plan」として変更を出力する

## Orchestrator(main)
READ: game/**(すべて)。ただし書き込みは patch plan か world-agent の直接更新を通してのみ
WRITE: game/run_state.json, lore/notes.md(任意), lore/story.md(任意)

soul runtime についての注記:
- 有効な souls は `playthrough.json` で宣言される
- world-agent は soul の出力を受け取るが、`souls/**` を直接は読まない
- `game/player/*` は、旧来のストーンフォードの流れのためのエレナの状態のローカル投影である

## World Builder
READ: world/world_map.json, lore/story.md, lore/notes.md
WRITE: world/world_map.json, world/regions.json(任意), world/factions.json(任意)

## Story / Narrative
READ: lore/story.md, lore/notes.md, world/world_map.json, player/flags.json
WRITE: lore/story.md, lore/rumors.md(任意)

## Town Agent(町ごと)
READ: towns/<town>/**, player/**, lore/notes.md
WRITE: towns/<town>/town.json, towns/<town>/town_map.json, towns/<town>/npcs.json, towns/<town>/quests.json

## Facility Agents(ギルド/店/宿)
READ: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/**
WRITE: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/inventory.json, player/wallet.json, player/flags.json, player/stats.json(宿での休息)

## Dungeon Agent(ダンジョンごと)
READ: dungeons/<dungeon>/**, player/**, rules/combat_rules.md
WRITE: dungeons/<dungeon>/**(state), world/world_map.json(発見/踏破の flag), player/flags.json

## Combat Referee
READ: rules/combat_rules.md, player/stats.json, player/equipment.json, player/inventory.json
WRITE: player/stats.json, player/inventory.json, player/wallet.json(戦利品), lore/notes.md
