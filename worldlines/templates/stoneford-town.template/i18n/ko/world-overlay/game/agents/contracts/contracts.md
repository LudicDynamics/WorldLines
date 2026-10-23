# 하위 에이전트 계약 (읽기/쓰기 경계)

stoneford-elena는 원래의 스톤포드 계약에 명시적인 souls를 더한 것이다.
`game/player/*`는 여주인공을 위한 호환용 투영으로 남아 있을 뿐,
캐릭터에 관한 유일한 진실 원천이 아니다.

각 하위 에이전트는 반드시:
- 허용된 파일 glob만 읽는다
- 허용된 파일 glob만 쓴다
- 변경 사항은 어떤 파일을 왜 생성/갱신하는지 적은 "patch plan"으로 출력한다

## Orchestrator (main)
READ: game/** (전부). 단, 쓰기는 patch plan 또는 world-agent의 직접 갱신으로만
WRITE: game/run_state.json, lore/notes.md (선택), lore/story.md (선택)

soul 런타임 메모:
- 활성 souls는 `playthrough.json`에 선언된다
- world-agent는 soul의 출력을 받지만, `souls/**`를 직접 읽지는 않는다
- `game/player/*`는 예전 스톤포드 흐름을 위한, 엘레나 상태의 로컬 투영이다

## World Builder
READ: world/world_map.json, lore/story.md, lore/notes.md
WRITE: world/world_map.json, world/regions.json (선택), world/factions.json (선택)

## Story / Narrative
READ: lore/story.md, lore/notes.md, world/world_map.json, player/flags.json
WRITE: lore/story.md, lore/rumors.md (선택)

## Town Agent (마을별)
READ: towns/<town>/**, player/**, lore/notes.md
WRITE: towns/<town>/town.json, towns/<town>/town_map.json, towns/<town>/npcs.json, towns/<town>/quests.json

## Facility Agents (길드/상점/여관)
READ: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/**
WRITE: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/inventory.json, player/wallet.json, player/flags.json, player/stats.json (여관 휴식)

## Dungeon Agent (던전별)
READ: dungeons/<dungeon>/**, player/**, rules/combat_rules.md
WRITE: dungeons/<dungeon>/** (상태), world/world_map.json (발견/소탕 플래그), player/flags.json

## Combat Referee
READ: rules/combat_rules.md, player/stats.json, player/equipment.json, player/inventory.json
WRITE: player/stats.json, player/inventory.json, player/wallet.json (전리품), lore/notes.md
