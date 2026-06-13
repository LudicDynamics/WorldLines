# ⛩ Stoneford — WorldLines 플래그십 월드

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

![Stoneford](./assets/s1bg.png)

> 잿빛 안개의 북방 강변 항구. 클래식 판타지 TRPG · d20 주사위 · **10-agent 멀티에이전트 마을**.

Stoneford는 [WorldLines](https://github.com/LudicDynamics/WorldLines)에 기본 포함된 플래그십 예제 —— NPC, 퀘스트, 던전, 공성 메커니즘을 갖춘 완전히 플레이 가능한 마을을 멀티에이전트 사회가 편성하여 구동합니다.

**[▶ 온라인 플레이(설치 불필요)→](https://hub.worldlines.gg/play/worlds/stoneford)**

## 플레이 방법

```bash
# 로컬 TUI
neonrp tui --from examples/stoneford

# Claude Code / MCP —— 이 디렉터리에서 Claude Code 열기
@world-agent 开始游戏
```

## 마을 —— 멀티에이전트 사회

Stoneford는 **살아있는 마을**입니다. 중심의 `world-agent`가 도메인 agent 사회를 편성하며, 각자 세계의 일부를 담당합니다. 트리거를 가진 것은 world-agent뿐이며, 다른 agent는 모두 `task()`로 호출되어 각자 독립된 컨텍스트를 가집니다.

```
world-agent（오케스트레이터）     — 상태 읽기 · 라우팅 · patch 병합 · 서술 · 아카이브
├── rpg-world-builder             — 월드맵, 지역, 세력
├── rpg-story-narrative           — 메인 스토리 + 소문
├── rpg-town-agent                — 마을 내비, NPC, 상점, 길드, 여관
├── rpg-dungeon-agent             — 던전 탐험
├── rpg-combat-referee            — d20 전투 판정
├── rpg-rules-referee             — 규칙 조회·판정
├── rpg-clock-keeper              — 시간, 일정, 세계 시계
├── rpg-world-evolution           — 세계의 장기 변화
└── rpg-character-agent           — NPC의 마음:의도·기억·대화
```

이것이 **마을 구조**의 실천입니다. 세계는 기억하고, NPC는 각자의 마음을 가지며, 매 턴이 단일 프롬프트가 아닌 편성된 agent 사회가 됩니다.

## 세계 내용

- **T001 Stoneford** —— 시작 마을:길드, 잡화, 여관, 부두
- **T004** —— 두 번째 정착지:예배당, 감정사, 약초 상점, 주점
- **D001 이끼 무덤** —— 4개 방 던전
- **퀘스트** —— 안개 속 실종자 · 이끼 무덤 앞의 울부짖음 · 대상 호위
- **전투** —— d20 + 능력 수정치 + 상태 효과

<p align="center">
  <img src="./assets/gameplay.jpg" alt="Stoneford —— 안개 속 도착" width="640" />
</p>

## 주요 파일

| 파일 | 역할 |
|------|------|
| `game/agents/manifest.json` | 10-agent 매니페스트（id, 역할, 읽기/쓰기 범위） |
| `game/meta/run_state.json` | 세계 상태（위치, 시간, 마지막 행동） |
| `game/meta/game-start.json` | 시작 가이드（오프닝 서술 + 초기 읽기 목록） |
| `game/towns/*/` | 마을 데이터:NPC, 퀘스트, 시설, 맵 |
| `game/dungeons/D001/` | 던전 레이아웃, 방, 조우·전리품 테이블 |
| `game/rules/combat_rules.md` | d20 전투 규칙 |
| `agents/*/` · `.claude/agents/*` | agent 정의（TUI + Claude Code 미러） |

## 라이선스

Stoneford는 **AGPL-3.0**. 포크, 수정, 자신의 세계를 출시하세요. 구동하는 WorldLines 엔진（`neonrp`）은 독점 프리뷰입니다.

> *Stoneford는 **nikoloside**, **redoctober**, Claude가 공동 창작한 오리지널 시나리오로, 동양적 세계관과 서양 중세 마법을 융합했습니다.*
