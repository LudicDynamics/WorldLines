---
title: "Agent & Orchestration"
description: "WorldLines의 agent 설계 — 파일 기반 agent 포맷 + harness 커스터마이즈가 어떻게 높은 자유도의 게임 저작을 가능하게 하는가."
---

<!-- section: philosophy -->
## 왜 파일 기반 agent인가

WorldLines의 agent 시스템은 **철저하게 파일 기반**입니다. 캐릭터, 도메인, 심판 등 모든 agent는 평범한 파일들이 담긴 디렉터리입니다.

- `agent.json` — trigger, tag, priority, 라우팅 메타데이터
- `system.md` — 시스템 프롬프트 템플릿(Markdown, 사람이 읽을 수 있음)
- `skills/` — 재사용 가능한 프롬프트 조각 / capability 모듈(선택)
- `tools.json` — 추가 툴 정의(선택)
- `policies.md` — 하드 룰(선택, v0.2+)

데이터베이스도, API에 묶인 상태도 없습니다. agent를 `git diff` 하고, fork 하고, 복사·붙여넣기 할 수 있습니다. 이는 Claude Code가 코드에 적용한 것과 동일한 통찰입니다 — **파일 시스템이 곧 UI**라는 것입니다.

<!-- section: harness-editing -->
## 높은 자유도의 harness 편집

Harness — 계획하고, 컨텍스트를 가져오고, 툴을 호출하고, diff를 적용하는 루프 — 는 엔진 코드가 아니라 **agent 파일로 정의**됩니다.

즉, 게임 저작자는 다음을 할 수 있습니다.

- `system.md`를 다시 쓰는 것으로 **나레이션 목소리** 변경
- agent의 `tools.json`을 편집하는 것으로 **retrieval 범위** 변경
- `policies.md`를 추가하는 것으로 **의사결정 스타일** 변경
- trigger / tag / priority를 조정하는 것으로 **dispatcher 동작** 변경

미스터리 / 슬립스트림 / 오토메 / TRPG 같은 하나의 서브장르 전체를, Python 한 줄도 건드리지 않고 stoneford 베이스 위의 agent 디렉터리 변경 집합으로 표현할 수 있습니다. 이것이 WorldLines가 최적화하고자 하는 설계 공간입니다.

<!-- section: anatomy -->
## Agent의 구성

완성된 agent 디렉터리는 다음과 같이 생겼습니다.

```
agents/elena/
├── agent.json        # trigger, tag, priority, 라우팅
├── system.md         # 시스템 프롬프트 템플릿
├── skills/
│   └── innkeeper.md  # 재사용 가능한 프롬프트 조각
├── tools.json        # 추가 툴 정의 (선택)
└── policies.md       # 하드 룰 (v0.2+)
```

stoneford 스타터는 **6개의 agent**와 함께 제공됩니다: `orchestrator`, `town-agent`, `dungeon-agent`, `combat-referee`, `world-builder`, `rules-referee`.

<!-- section: dispatch -->
## Dispatcher

Dispatcher는 다음 기준으로 각 쿼리의 agent를 선택합니다.

1. 명시적 `--agent` 플래그
2. `agent.json`의 정규식 trigger 패턴
3. 현재 컨텍스트와의 태그 겹침
4. Priority 타이브레이크

CLI로 agent를 직접 호출할 수 있습니다.

```bash
neonrp agent run town-agent --query "describe the harbor"
neonrp agent list --json
neonrp agent show town-agent
```

<!-- section: harness-loop -->
## Harness — Orchestration 루프

WorldLines의 agent harness는 다음을 갖춘 **Plan → Diff → Apply 루프**를 구현합니다.

- 경계가 있는 retrieval (minimal-context, 하이브리드 fuzzy + vector)
- 결정적 툴 호출 순서
- 턴당 예산 (토큰 / 툴 호출)
- 나레이션과 분리된 thinking 채널

**Orchestrator** agent가 최상위 harness 코디네이터입니다 — `task()` 툴로 도메인 / 캐릭터 agent에 라우팅하고, 게임 상태의 정합성을 유지하며, 플레이어가 보는 나레이션을 소유합니다.

Router 모드(`fast` / `orchestrator` / `multi-agent`)는 턴마다 orchestration이 *어떻게* 일어나는지를 바꿉니다 — [Router Mode](/docs/core-concepts/engine-modes)를 참조하세요.

<!-- section: skills -->
## Skill

**Skill**은 agent가 `use`할 수 있는 재사용 가능한 프롬프트 조각 / capability 모듈입니다. 엔진에 포함된 빌트인 skill이 함께 제공되며, 프로젝트 로컬 skill을 `skills/`에 정의할 수도 있습니다.

사용 가능한 목록 보기:

```bash
/skills              # TUI 내부에서
```
