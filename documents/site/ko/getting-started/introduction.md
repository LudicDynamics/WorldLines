---
title: "소개"
description: "WorldLines는 에이전트형 시뮬레이션 엔진 — 살아있는 AI 에이전트 마을, 그리고 당신이 함께 노는 곳."
---

<!-- section: what-is-worldlines -->
## WorldLines란?

WorldLines는 **에이전트형 시뮬레이션 엔진**입니다. world-agent가 place-agent에 연결되고, 각 place-agent가 soul-agent를 호스트합니다. 여기서는 모두가 agent입니다. 당신은 아바타 터미널을 통해 참여합니다.

이것은 "AI 캐릭터 하나와 대화하는" 것이 아닙니다. **멀티에이전트 사회**가 실시간으로 움직이며, 각 agent가 고유한 목표·기억·제약을 가집니다.

우리는 world-agent, place-agent, soul-agent를 하나의 살아있는 시뮬레이션으로 잇는 harness를 만들었습니다. 이 엔진으로 다음을 구동하고자 합니다: **인터랙티브 경험 창작 · 멀티에이전트 사회 실험 · 에이전트 연구 진전 · 성격 모델과 세계 모델 벤치마크.**

현재 상태: **v0.3.0** (2026-07-13). [지금 플레이 →](https://hub.worldlines.gg)

**nikoloside**와 **redoctober**가 공동 개발하고, [Ludic Dynamics](https://ludicdynamics.com)와 함께 추진합니다.

<!-- section: ways-to-play -->
## 세 가지 플레이 방법

> **👉 처음이신가요? Stoneford · Elena — 멀티에이전트 마을에서 시작하세요.** Elena와 Rowan 두 캐릭터는 각자 *스스로 생각하고, 기억하고, 행동합니다* — 내레이터가 대신 써 주는 대사가 아닙니다. WorldLines가 무엇이 다른지 가장 명확하게 맛볼 수 있는 곳입니다. 아래 런처에서 import하면 전체 마을을, 또는 [WebHub에서 Elena를 만나기](https://hub.worldlines.gg/play/souls/elena)로 클릭 한 번에.

**1. WorldLines 런처 — 데스크톱, 다운로드 한 번.** [worldlines.gg](https://worldlines.gg)에서 런처를 받아 더블클릭하고 **월드를 import**하세요 — 공식 월드는 바로 플레이할 수 있고, 터미널이 필요 없습니다. Python과 LLM 프로바이더 설정을 대신 해 줍니다.

**2. WebHub — 브라우저, 설치 불필요.** [hub.worldlines.gg](https://hub.worldlines.gg)를 열고 로그인하여 플레이하세요. 월드와 소울 카탈로그를 탐색하고, AI 지원 스튜디오로 직접 창작하며, 공개 레지스트리에 게시할 수 있습니다. 클라우드 에이전트가 대신 실행합니다.

**3. CLI & TUI — 로컬, 오픈 도구 (고급).** `worldlines` 바이너리를 설치하고 Claude Code 스타일의 TUI로 터미널에서 플레이하세요. 예제, 도구, 프로토콜은 오픈소스(AGPL-3.0)이며, Ollama / LM Studio / GLM으로 자신의 모델을 실행할 수 있습니다.

<!-- section: why-worldlines -->
## 왜 WorldLines인가

기존의 "AI와 채팅하기" 인터페이스는 컨텍스트 윈도우가 가득 차는 순간 모든 것을 잃어버립니다. WorldLines는 진정한 엔진이 제공해야 할 보장을 제공합니다.

- **⭐ 파일로 영구 저장되는 기억과 월드 상태** — 기억, 저장, NPC, Agent가 모두 평범한 JSON과 Markdown으로 디스크에 저장됩니다. 클라우드 없음, 데이터베이스 없음, 숨겨진 상태 없음. 폴더를 열 수 있다면 그 세계는 당신의 것입니다.
- **인덱스 + 컨텍스트 자동 주입** — WorldLines는 파일 인덱스와 로컬 벡터 DB를 자동으로 구축하고, 각 턴마다 관련 게임 데이터만을 Agent의 컨텍스트에 자동 주입합니다. lorebook을 수동으로 관리할 필요가 없습니다.
- **이벤트 소싱 기반 상태** — 모든 턴이 append-only Event이며, Snapshot으로 빠른 되감기가 가능합니다.
- **Branch / Undo / Redo** — git branch처럼 서사의 분기를 탐험합니다.
- **Sandbox & Replay** — 격리된 환경에서 실험을 돌리고 결정성을 검증합니다.
- **Orchestrator 기반 멀티 Agent** — Orchestrator가 하나의 공유 상태 위에서 도메인 Agent(town / dungeon / combat-referee / world-builder / rules-referee)로 라우팅합니다.
- **Plan → Diff → Apply** — LLM이 구조화된 파일 연산을 제안하면 적용 전에 검토할 수 있습니다.
- **풍부한 TUI** — 플레이와 빌드 모두를 위한 Claude Code 스타일의 대화형 터미널입니다.
- **로컬 우선 모델** — GLM, OpenAI, LM Studio, Ollama를 지원합니다.

<!-- section: positioning -->
## WorldLines와 다른 도구 비교

|                      | Character.AI       | SillyTavern                 | Claude Code              | **WorldLines**                      |
|----------------------|--------------------|------------------------------|---------------------------|--------------------------------------|
| 주요 영역            | 캐릭터 채팅        | Prompt 프론트엔드            | 코드 편집                 | 살아있는 게임 월드                    |
| 월드의 저장 위치     | 그들의 서비스      | Prompt 설정 + 채팅 로그       | 디스크 상의 코드베이스     | **평범한 파일 + git**                |
| 기억과 검색          | 클라우드 / 불투명  | 수동 lorebook                | 코드베이스 검색            | **자동 파일 인덱스 + 벡터 DB**       |
| Multi-agent          | —                  | —                            | 태스크별 서브 agent         | Orchestrator + 도메인 agents          |
| 로컬 우선 LLM        | 불가              | 직접 연결                     | API 전용                  | GLM / LM Studio / Ollama             |
| 결정성 / Replay      | —                  | —                            | —                         | **Sandbox + Replay**                 |

Claude Code가 코드를 위한 IDE라면, WorldLines는 살아있는 세계를 위한 IDE입니다 — 기억, 검색, orchestration이 모두 내장된 상태로.

각 도구에 대한 상세 비교는 [Q&A](/docs/qa/what-is-airp)에 있습니다 — vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph.

> 참고: WorldLines의 harness는 현재 Claude Code보다 엄격합니다 — 안정적인 오케스트레이션을 위해 완전한 컨텍스트에 의존합니다. 이는 결핍이 아니라 더 높은 결정성과 쉬운 디버깅을 위한 의도적인 트레이드오프입니다.

<!-- section: next-steps -->
## 다음 단계

- [Quickstart](/docs/getting-started/quickstart)를 따라가 보세요 — 10분 안에 첫 턴까지
- [Core Concepts](/docs/core-concepts/worlds)를 살펴보세요 — event, snapshot, branch, agent
- [로드맵](/docs/roadmap)을 확인하세요 — 다음에 무엇이 올지
- [Q&A](/docs/qa/what-is-airp) — WorldLines가 기존 도구와 어떻게 다른지
