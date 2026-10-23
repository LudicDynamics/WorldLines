---
title: "엔진 모드 — 멀티에이전트 시뮬레이션 (+ 가벼운 Fast / Orchestrator)"
description: "WorldLines는 그 자체가 멀티에이전트 시뮬레이션입니다: world-agent가 독립적인 영혼들의 사회를 감쌉니다. Fast와 Orchestrator는 더 단순한 단일 흐름 장면용 가벼운 모드입니다."
---

<!-- section: comparison -->
## 한눈에 보기

| 모드             | 매 턴 무엇이 도는가                                          | 상태                           |
|------------------|-------------------------------------------------------------|--------------------------------|
| **Multi-Agent**  | world-agent가 **활성 소울**을 감쌈 — 각자 고유한 마음을 가진 독립 캐릭터 agent | ✅ Shipped (v0.2.3, 로컬)     |
| **Orchestrator** | world-agent가 `task()`로 도메인 agent에 재라우팅            | ✅ 출시됨 / Shipped            |
| **Fast**         | 단일 agent, 최소한의 라우팅                                  | ✅ Shipped                     |

**멀티에이전트(Multi-Agent)가 곧 엔진의 본체** — world-agent가 독립적인 영혼들로 이루어진 사회를 감싸며, 각자 자기만의 마음을 가진다. 이것이 마을 모델이며, 모든 월드가 향하는 곳. **Orchestrator**(world-agent가 데이터 기반 NPC를 다루는 도메인 에이전트로 라우팅)와 **Fast**(단일 에이전트)는 더 단순한 단일 흐름 장면용 가벼운 모드. 셋 다 동일한 이벤트 로그 형식으로 기록하며 영속화되는 상태는 동일하다 — 차이는 **매 턴에 무엇이 사고하는가**뿐이다.

**멀티에이전트는 로컬에서 실행**(TUI / CLI); hosted play는 현재 가벼운 Fast + Orchestrator를 제공한다. 재현 가능하며, `souls/` 폴더 + `playthrough.json`이 있는 월드라면 자동으로 활성화된다. [worldlines/templates/stoneford-town.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/stoneford-town.template)(스톤포드)와 [worldlines/templates/pct-house.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/pct-house.template)(그레이오크 저택, 영혼 2) 참조.

<!-- section: fast -->
## Fast Mode

**단일 agent**가 턴을 끝까지 처리합니다. Orchestrator도, 위임도, `task()` 호출도 없습니다.

**적합한 상황**:
- 턴당 LLM 비용이 가장 저렴
- 저작 중 빠른 반복
- 라우팅이 필요 없는 narration 중심 장면

**한계**:
- Sub-agent 전문화가 없음 — 전투 관련 질문도 narration과 같은 agent에 도달
- 도메인을 오가는 복잡한 장면에서 상태 drift 위험이 더 큼

<!-- section: orchestrator -->
## Orchestrator Mode

Stoneford의 기본값입니다. **Orchestrator** / narrator agent가 도메인 agent(town / dungeon / combat-referee / world-builder / rules-referee) 위에 올라타, `task()` 툴을 통해 **매 턴 재라우팅**합니다.

**적합한 상황**:
- 여러 도메인을 오가는 장면 (마을 안의 전투, 던전의 의식 등)
- 규칙 일관성이 중요한 모든 순간
- 정규 플레이 루프

**비용**:
- 매 턴 orchestrator + 최소 하나의 도메인 agent 비용을 지불
- 지연 시간은 상한이 있지만 Fast보다 높음

<!-- section: multi-agent -->
## Multi-Agent Mode — 마을 모델 ✅

**v0.2.3에서 제공(로컬).** 이것이 **마을**입니다. 하나의 내레이터가 모든 캐릭터를 연기하는 대신, **각 캐릭터가 자기 자신의 AI agent** — 고유한 성격·기억·비밀·목표를 가진 "소울" — 입니다. 그들은 스스로 생각합니다.

**world-agent**가 게임 마스터처럼 장면을 호스트합니다: 매 턴, 그 자리에 있는 캐릭터들을 깨우고, 각자가 무엇을 말하고 행동할지 결정하게 한 뒤, 그들의 움직임을 하나의 내레이션으로 엮습니다.

```
              world-agent  (호스트 / 내레이터)
                    │  장면에 있는 누구든 깨운다
          ┌─────────┼─────────┐
       Kagami     Hane      Shiro      ← 각자 독립된 소울:
      (own mind) (own mind) (own mind)    자신만의 기억, 목적, 목소리
          └─────────┼─────────┘
                    ▼
              world-agent  → 턴을 내레이션; 세계가 기억한다
```

**왜 중요한가**

- **각 캐릭터가 실재합니다.** Elena는 내레이터가 대신 써 주는 대사가 아닙니다 — 스스로 결정하는 agent이며, 당신을 놀라게 할 수 있습니다.
- **그들은 기억합니다.** 소울은 턴을 넘어 기억·관계·개인 서사호를 유지하므로, 마을은 진화하고 캐릭터들은 당신이 앞서 한 일을 꺼내 옵니다.
- **소울은 이식 가능합니다.** 각각이 자기 완결형이기에, 같은 Elena가 Stoneford에서 Kagura Island로 건너가도 여전히 자기 자신입니다.

**해 보기** (오늘 로컬에서 실행):

```bash
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # 그레이오크 저택
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # 스톤포드
```

`souls/` 폴더 + `playthrough.json`을 동봉한 세계는 자동으로 마을이 됩니다. `soul-authoring` 워크플로로 자신만의 캐릭터를 제작하세요.

호스티드 플레이(WebHub)는 현재 Fast + Orchestrator를 커버합니다; 마을을 온라인으로 가져오는 것은 별도 트랙입니다.

<!-- section: switching -->
## Router 모드 전환

Router 모드는 프로젝트 단위가 아니라 턴 단위입니다. TUI에서 전환합니다.

```
/router-mode fast
/router-mode orchestrator
/router-mode multi-agent
```

또는 `neonrp run`에 `--router-mode <mode>`를 전달합니다. 세션 로그는 모든 event에 router 모드를 기록하여 replay가 항상 충실하도록 합니다.
