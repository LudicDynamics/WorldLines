---
title: "캐릭터 & Multi-Agent"
description: "월드는 두 가지 방식 중 하나로 실행됩니다: sub-agent(town / dungeon / npc)를 거느린 orchestrator World-Agent, 또는 각 캐릭터가 자신만의 soul·기억·목소리·sub-agent를 가진 일급(first-class) 정체성, 즉 자기 자신인 Character-Agent가 되는 멀티에이전트 마을. 둘 다 오늘 제공됩니다."
---

<!-- section: today -->
## 오늘 — World-Agent + sub-agent

v0.1에서 월드의 모든 엔티티는 하나의 최상위 **World-Agent**(orchestrator / narrator)를 통해 접근됩니다. World-Agent는 `task()`를 통해 자신의 **sub-agent**에 위임합니다.

| World-Agent 하위의 Sub-agent | 책임                                                         |
|------------------------------|--------------------------------------------------------------|
| **Town sub-agent**           | 마을 내부의 장소, 일반 상인, 이벤트                          |
| **Dungeon sub-agent**        | 던전 내부의 지형, 함정, 조우 페이싱                          |
| **NPC sub-agent**            | 개별 NPC의 대사와 반응(현재는 공유 풀)                       |

이 방식은 동작합니다 — 하지만 모든 NPC가 하나의 서사적 렌즈(World-Agent의 시스템 프롬프트)를 공유하게 되며, 그들의 "인격"은 매 턴 정적인 캐릭터 JSON으로부터 재구성됩니다.

<!-- section: character-agent -->
## Character-Agent — 병렬 분기 ✅

> **v0.2.3에서 제공(로컬)** — 이것이 멀티에이전트 마을입니다. [Multi-Agent Mode](/docs/core-concepts/engine-modes#multi-agent) 참조.

World-Agent와 각 캐릭터(**soul-agent**)는 공유 **메시지 버스**를 통해 대화하는 독립된 agent입니다 — 내레이터는 결코 캐릭터를 조종하지 않습니다.

```
   world-agent  ◄─────►┌────────────────┐◄─────►  soul-agents
   (호스트 /            │  message bus   │         ┌─ Elena  (soul.md · 기억 · 목소리 · subs)
    내레이터)          └────────────────┘         ├─ Rowan  (자신만의 마음)
                                                   └─ …

   world-agent가 장면을 버스에 게시하면, 이번 턴에 등장하는 소울들이
   각자 그것을 읽고 자신의 발화 / 행동 / 내면의 목소리를 결정해 다시
   게시하며, world-agent가 그 응답들을 하나의 내레이션으로 엮습니다.
```

각 소울은 다음을 소유합니다.

- **`soul.md`** — 정체성 문서. 핵심 가치, 이력, 관계, 상처. 한 번 작성하고, 큰 스토리 순간에만 갱신합니다.
- **장기 메모리** — 세션을 가로지르는 살아온 경험. 압축되고, 검색 가능하며, snapshot/load에도 살아남습니다.
- **단기 메모리** — 현재 장면의 컨텍스트. 장면이 바뀌면 감쇠(decay)되거나 압축됩니다.
- **성격(Personality)** — 구조화된 특성(big-five, 커스텀 축 등, 저작자가 원하는 무엇이든).
- **서사 스타일** — 그녀의 목소리를 프롬프트 조각으로 표현한 것. 턴을 넘나들며 일관되게 유지됩니다. 심지어 World-Agent가 그녀 주변을 나레이션할 때에도, 그녀의 직접 대사는 캐릭터답게(in-character) 유지됩니다.
- **커스텀 sub-agent** — 저작자는 캐릭터에게 그녀만의 위임자를 부여할 수 있습니다 (Elena는 메뉴 가격 책정을 위한 `innkeeper` 스킬 sub-agent를, 속마음을 주고받는 순간을 위한 `confidante` sub-agent를 가질 수 있습니다). 공유 NPC 풀에 강제로 밀어 넣는 것이 아니라, 캐릭터별로 조합 가능합니다.

<!-- section: why-parallel -->
## 왜 nested가 아니라 parallel인가

Character-Agent를 World-Agent **아래가 아니라 옆에** 두는 것이 중요한 이유.

- 캐릭터의 정체성은 월드 로직의 한 분기여서는 안 됩니다. 장면이 새로운 마을로 옮겨가도 Elena는 Elena로 남아 있어야 합니다.
- 메모리 범위가 다릅니다. World-Agent는 월드의 사건을 기억하고, Character-Agent는 *그녀 자신의* 사건을 기억합니다.
- 목소리는 장면 전환에도 살아남습니다 — 그녀가 선술집(town sub-agent)에 있든 던전(dungeon sub-agent)을 가로질러 도망치든, 동일한 캐릭터 Agent가 말합니다.
- 캐릭터별 커스텀 sub-agent는 공유 NPC 풀에 몰아넣는 것보다 훨씬 잘 확장됩니다.

이것이 바로 **Multi-Agent 모드 — 마을**(✅ v0.2.3 제공, [Router Mode](/docs/core-concepts/engine-modes#multi-agent) 참조)이 감당하는 지점입니다: 각 캐릭터가 매 턴 내레이터에게 처음부터 다시 목소리를 부여받는 대신, 여러 턴에 걸쳐 펜을 쥐고 자신의 기억을 유지하는 자기 자신의 agent가 됩니다.

<!-- section: bridge -->
## Orchestrator 또는 마을 — 둘 다 오늘 제공

**Orchestrator 월드**(`stoneford` 같은)는 NPC를 `game/npc/`의 데이터로 다루고, World-Agent의 공유 sub-agent 풀을 통해 목소리를 부여합니다. 단순하고, 저렴하며, 규칙 중심 플레이에 좋습니다.

**마을 월드**(`kagura-island`나 `stoneford-elena` 같은)는 각 캐릭터에게 자신만의 Character-Agent를 부여합니다: NPC를 `souls/` 아래의 소울 폴더 + `playthrough.json`으로 승격하면, 여러 턴에 걸쳐 스스로 생각합니다. [Multi-Agent Mode](/docs/core-concepts/engine-modes#multi-agent) 참조.

기저의 agent 구성은 [Agents & Orchestration](/docs/core-concepts/agents-orchestration)을, 저작 플로우는 [Building Character Agents](/docs/guides/building-character-agents)를 참조하세요.
