---
title: "vs Character AI"
description: "WorldLines가 Character AI와 겹치는 지점과 결정적으로 다른 지점."
---

<!-- section: what-caai-does-well -->
## Character AI가 잘하는 것

- 마찰 없는 온보딩 — 원클릭으로 캐릭터와 채팅
- 거대한 커뮤니티 character card 라이브러리
- 모바일 네이티브

<!-- section: where-worldlines-differs -->
## WorldLines가 다른 점

두 가지 차이가 가장 중요합니다.

1. **캐릭터 중심이 아니라 세계 중심.** Character AI는 대화할 캐릭터를 줍니다. WorldLines는 모든 AI 페르소나를 **살아있는 세계 안에** 빚어냅니다 — 캐릭터는 진공 속 채팅이 아니라, 한 장소에 존재하며 사건·다른 agent·결과에 둘러싸여 있습니다.

2. **대화가 아니라 지속적 페르소나 + 시뮬레이션.** 캐릭터의 성격·기억·관계가 **영속화**됩니다 — 세션을 넘어, 심지어 세계를 넘어 이어집니다(같은 Elena가 Stoneford에서 Kagura Island로 건너갈 수 있습니다). 그리고 엔진은 대화가 아니라 **시뮬레이션**을 돌립니다: agent들이 스스로 행동하고, 당신이 있든 없든 세계가 움직이며, 일어난 일은 저장·branch·replay할 수 있는 상태로 기록됩니다.

구체적으로: 지속적인 세계 + 캐릭터 상태, 멀티에이전트 오케스트레이션, 파일 기반 / git 버전 관리 월드, 로컬 우선 모델(GLM / LM Studio / Ollama), 그리고 검토 가능한 Plan → Diff → Apply 변경.

<!-- section: who-should-use-which -->
## 누가 무엇을 써야 하나

- 좋아하는 캐릭터와 가벼운 채팅 → Character AI
- 간직하고, fork하고, 진화시킬 세계를 만들거나 플레이 → WorldLines
