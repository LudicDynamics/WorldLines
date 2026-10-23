---
title: "첫 번째 세계 만들기"
description: "월드를 만드는 세 가지 방법 — 런처, WebHub 스튜디오, 또는 AI 코딩 agent."
---

<!-- section: launcher -->
## WorldLines 런처에서

WorldLines를 열고 → **New world**, 원하는 것에 가까운 템플릿(Stoneford · Kagura Island · …)에서 시작한 뒤, 플레이하면서 **Build** 모드로 손보세요. 실제로 플레이 가능한 월드에 가장 빠르게 도달하는 방법입니다.

<!-- section: webhub -->
## 브라우저에서 — WebHub Create 스튜디오

[hub.worldlines.gg](https://hub.worldlines.gg)에서 **Create** 스튜디오가 AI 지원으로 월드를 안내합니다 — 전제, 캐릭터, 톤을 설정한 뒤 만족스러우면 공개 레지스트리에 게시하세요. 설치 불필요.

<!-- section: ai-skill -->
## Claude Code 또는 Codex로 — 저작 스킬

WorldLines는 **Claude Code**와 **Codex** 저작 스킬을 제공합니다. 저장소를 clone하고, AI 코딩 agent에서 열어, 원하는 것을 그냥 설명하세요.

```bash
git clone https://github.com/LudicDynamics/WorldLines.git
cd WorldLines        # 그다음 Claude Code 또는 Codex에서 열기
```

> *"국풍(国风) 오토메 월드를 만들어줘: 궁궐, 네 명의 왕자, 그리고 히로인을 고르는 등불."*

해당 스킬이 자동으로 로드되어 `game/` 엔티티, agent, 그리고 (마을의 경우) 소울을 대신 스캐폴딩합니다. 단계별 안내: [저작 튜토리얼](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials) — character card · world card · 전체 월드 · soul.

<!-- section: advanced-cli -->
## 고급 — CLI에서 직접 저작

완전한 제어를 원하나요? 엔진 메타데이터를 스캐폴딩하고 `game/`를 직접 손으로 작성하세요.

```bash
worldlines init        # .neonrp/ 엔진 메타데이터 생성
# game/meta/world.json, game/player/, location, agent 저작…
neonrp validate        # 스키마 확인
neonrp index build     # retrieval 인덱스 재구축
```

최소한의 월드에는 `game/meta/world.json`, 시작 플레이어 상태, 최소 하나의 location, 그리고 하나의 agent(orchestrator)가 필요합니다.
