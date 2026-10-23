---
title: "vs LangGraph, Graflow & 기타 멀티에이전트 프레임워크"
description: "WorldLines는 롤플레이를 위해 특별히 만들어진 멀티에이전트 프레임워크입니다."
---

<!-- section: vs-orchestration -->
## vs 오케스트레이션 프레임워크 (LangGraph · Graflow)

**LangGraph**와 **Graflow**는 stateful한 멀티에이전트 워크플로를 구축하기 위한 *범용* 툴킷입니다 — node, edge, state channel, checkpointing — 을 도메인에 필요한 무엇으로든 조립합니다.

**WorldLines는 단 하나, 롤플레이를 위해 특별히 만들어졌습니다.** 그 기본 요소들 — world-agent, soul-agent, event, snapshot, branch, Plan → Diff → Apply — 은 직접 설계하는 범용 그래프가 아니라, *살아있고 플레이 가능한 세계*를 위한 어휘입니다.

<!-- section: vs-simulators -->
## vs 멀티에이전트 시뮬레이터 (Oasis · 灵台 · Mirror Fish)

여러 종류의 세계를 모델링하는 멀티에이전트 *시뮬레이션* 프레임워크의 물결이 있습니다.

- **Oasis** — **소셜 네트워크**를 시뮬레이션합니다: 게시하고, 팔로우하고, 서로 영향을 주는 대규모 agent 집단.
- **灵台 (Lingtai)** · **Mirror Fish** — 다른 멀티에이전트 시뮬레이션 환경.

WorldLines는 의도적으로 다른 도메인을 겨냥합니다: **여러 Soul Agent**가 구동하는 **테이블탑 스타일 롤플레이(跑团)**. 우리는 SNS / 소셜 네트워크 시뮬레이션에 맞추지 **않습니다**. 우리는 **실생활**에 가깝거나 **판타지 세계**에 가까운 설정에 맞춥니다 — 발을 들여 플레이하는 장소, 각 캐릭터가 기억과 주체성을 가진 자기 자신의 소울인 곳.

<!-- section: when-to-pick-which -->
## 언제 어느 것을 선택할까

- **LangGraph / Graflow** — 커스텀 에이전트형 워크플로(리서치 어시스턴트, 지원 봇, 코드 파이프라인)를 구축 중; 최대 유연성을 원함.
- **Oasis / 소셜 시뮬레이터** — 네트워크 규모의 사회적 역학을 연구 중.
- **WorldLines** — **롤플레이 세계**를 구축하거나 플레이 중: TRPG, 내러티브, 동료 — 저장·branch·replay할 수 있는 soul-agent들의 살아있는 세계.
