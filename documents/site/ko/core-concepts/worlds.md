---
title: "Event, Snapshot & Branch"
description: "WorldLines는 모든 변화를 append-only event로 저장합니다. Snapshot과 branch로 되감기 비용을 낮춥니다."
---

<!-- section: events -->
## Event

세계의 모든 변화는 `.neonrp/events.jsonl`에 기록되는 **append-only event**입니다.

```json
{
  "id": 42,
  "ts": "2026-04-17T10:03:11Z",
  "branch": "main",
  "agent_id": "town-agent",
  "kind": "proposal_applied",
  "ops": [
    {"op": "upsert_text", "path": "player/journal.json", "content": "..."}
  ]
}
```

Event는 **신뢰의 원천(source of truth)**입니다. `game/`는 event 스트림을 실체화(materialization)한 것입니다. event 0부터 다시 재생하면 언제든지 `game/`를 재구성할 수 있습니다.

<!-- section: snapshots -->
## Snapshot

**Snapshot**(세이브)은 특정 event 시점의 `game/` 전체 복사본과 메타데이터입니다. Snapshot은 `.neonrp/saves/<name>/`에 보관됩니다. 10,000개의 event를 재생하는 것은 느리지만 snapshot 로드는 파일 복사이므로, 되감기를 빠르게 하기 위해 존재합니다.

```bash
neonrp save opening-scene
neonrp load opening-scene
```

<!-- section: branches -->
## Branch

**Branch**는 event 로그 위의 이름 붙은 head 포인터입니다. git처럼 분기 비용이 저렴합니다. 현재 상태에서 fork하고 분기된 event를 씁니다.

```bash
neonrp branch try-stealing
```

Branch는 `.neonrp/branches/` 아래에서 copy-on-write 방식으로 변경되지 않은 엔티티를 공유합니다.

<!-- section: sandboxes -->
## Sandbox

**Sandbox**는 *snapshot에서 생성된* branch이며 ephemeral로 표시됩니다. 명명된 branch를 오염시키지 않고 "what-if" 실험을 돌릴 수 있습니다.

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... 플레이 ...
neonrp sandbox drop experiment --force
```

<!-- section: replay -->
## Replay & 결정성

동일한 event와 시드가 고정된 LLM(또는 캐시된 fixture)이 주어지면, replay는 같은 `game/` 상태를 만들어야 합니다. `replay verify`가 이를 확인합니다.

```bash
neonrp replay verify --from opening-scene
```

이것이 WorldLines가 AI 구동 상태를 재현 가능하게 유지하는 방식입니다 — 채팅 UI에서는 얻을 수 없는 속성입니다.
