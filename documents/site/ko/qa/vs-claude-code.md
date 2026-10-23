---
title: "vs Claude Code"
description: "Claude Code는 agentic 코딩 환경. WorldLines는 agentic worlding 환경. 비슷한 기본 요소, 다른 도메인."
---

<!-- section: shared-primitives -->
## 공유하는 것

두 엔진 모두 같은 agentic 토대 위에 있습니다.

- 구조화된 proposal / diff / apply 루프
- 실제 디렉터리에 사는 파일 기반 상태
- 대화형 터미널 인터페이스
- 전체 코퍼스가 아닌, 작업 세트에 대한 retrieval
- branch하고 replay할 수 있는 세션 히스토리

Claude Code가 **코드**를 위한 IDE라면, WorldLines는 **살아있는 세계**를 위한 IDE입니다. 직관은 그대로 이전됩니다.

<!-- section: where-they-diverge -->
## 갈라지는 지점

|                  | Claude Code                       | WorldLines                              |
|------------------|-----------------------------------|-----------------------------------------|
| 도메인           | 코드 편집 / 소프트웨어 agent      | 게임 세계 / AIRP agent                  |
| 상태 단위        | 파일 + git                        | Event + Snapshot + branch               |
| 주요 루프        | Plan → Edit → Test                | Plan → Diff → Apply → Save              |
| 기본 제공 내용   | 직접 repo를 준비                  | `stoneford` 스타터 템플릿 포함         |
| 샌드박싱         | Shell / 컨테이너                  | 엔진 내장 Sandbox + Replay              |
| 멀티 agent       | 태스크별 서브 agent               | World-agent + 소울들의 사회(마을) + 도메인 agent |

같은 에이전트형 근력을, 다른 도메인을 향해 겨눈 것: 코드베이스가 아니라 *세계*를 여러 턴에 걸쳐 정합성 있게 유지합니다.

<!-- section: fit-together -->
## 어떻게 맞물리는가

둘은 경쟁자가 아닙니다 — WorldLines는 Claude Code가 대중화한 것과 같은 에이전트형 패러다임 *위에서* 돌아가며, Claude Code는 WorldLines 월드를 **저작**하는 가장 좋은 방법 중 하나입니다.

- **스킬로 저작.** WorldLines는 Claude Code(와 Codex) 저작 스킬을 제공합니다 — 저장소를 clone하고, Claude Code에서 열어, 원하는 월드를 설명하면, `game/` + agent + 소울을 대신 스캐폴딩합니다. [튜토리얼](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials) 참조.
- **에이전트형으로 플레이.** 이미 많은 사람들이 Claude Code 안에서 직접 롤플레이합니다. WorldLines는 거기에 빠진 조각들을 더합니다: 지속적인 세계, 독립된 소울들의 사회(멀티에이전트 마을), 저장 / branch / replay — 그리고 모든 것이 날것의 터미널이 아니도록 하는 프론트엔드.

Claude Code가 코드를 위한 IDE라면, WorldLines는 그 같은 에이전트형 근력을 살아있고 플레이 가능한 세계로 바꿉니다.

<!-- section: what-we-push -->
## 우리가 더 밀어붙이는 것

이미 많은 사람들이 Claude Code와 Codex 안에서 롤플레이하고 있고 — 우리는 그것을 지지합니다. 그 방향 위에서, 우리는 세 가지를 풀고자 했습니다.

1. **속도.** Claude Code / Codex는 한 턴에 **3분 이상** 걸릴 수 있습니다 — 코딩에는 괜찮지만 플레이에는 고통스럽습니다. 우리는 한 턴이 빌드가 아니라 대화처럼 느껴지도록, **롤플레이에 맞춰 튜닝된 더 빠른 agent**를 원합니다.

2. **락인 없음 — 어떤 모델이든, 로컬 & 무료까지.** 롤플레이가 하나의 벤더에 묶여서는 안 됩니다. **DeepSeek, OpenRouter, 오픈소스, 로컬, 무료** 모델에서 실행하고, **커스터마이즈 가능**하게 유지하세요 — 두뇌는 당신이 고릅니다.

3. **멀티에이전트, 규모 있게.** 우리는 **멀티에이전트 마을**을 더 밀어붙입니다 — 더 많은 독립 소울, 더 큰 장면, 더 큰 세계 — 그리고 그들 모두를 정합성 있게 유지하는 **오케스트레이션**을 혁신합니다.

Claude Code와 같은 에이전트형 정신; 다만 코드베이스가 아니라 살아있는 세계에 맞춰 튜닝되었습니다.
