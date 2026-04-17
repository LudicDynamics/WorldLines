# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 살아있는 세계로 향하는 문" width="640" />
</p>

<p align="center"><em>YouTube 트레일러 — 곧 공개.</em></p>

> 상태: Preview (v0.1.0 — 2026-04-17 공개 프리뷰)

> *AI 채팅에서 Agentic AIRP 로.*
> 파일로 뒷받침되는 이벤트 소싱 기반의 살아있는 세계 엔진.

WorldLines 는 [Ludic Dynamics](https://ludic-dynamics.com) 가 만드는
Agentic AIRP engine(AI RolePlay engine)입니다. 엔진 바이너리의 코드네임은
`neonrp`, 릴리스 브랜드는 **WorldLines** 입니다.

게임 세계를 버전 관리되는 파일 기반 상태 기계로 다루기에, 플레이·편집·
Agent 가 모두 휘발성 채팅 로그가 아닌 재현 가능한 아티팩트가 됩니다.

---

## 왜 WorldLines 인가

전통적인 "AI 와 채팅" 인터페이스는 context window 가 가득 차는 순간
모든 것을 잃습니다. WorldLines 는 진짜 엔진 수준의 보장을 제공합니다:

- **Event-sourced state.** 모든 턴은 append-only Events, Snapshots
  덕분에 되감기가 빠릅니다.
- **Branch / Undo / Redo.** git branch 처럼 서사 분기를 탐색하세요.
- **Sandbox & Replay.** 격리 환경에서 실험하고 결정성을 검증합니다.
- **Multi-Agent 오케스트레이션.** Orchestrator 가 도메인 Agents
  (town / dungeon / combat-referee / world-builder / rules-referee)
  로 라우팅하며, 단일 상태를 공유합니다.
- **Plan → Diff → Apply.** LLM 이 구조화된 파일 연산을 출력,
  반영 전 검토할 수 있습니다.
- **File-backed world.** `game/` 은 JSON 과 Markdown 일 뿐입니다.
  git 으로 관리하고 어떤 에디터로도 편집하세요.
- **Rich TUI.** 플레이와 제작 모두를 위한 Claude-Code 스타일 대화형
  터미널.
- **Local-first 모델.** GLM / OpenAI / LM Studio / Ollama.

### 포지셔닝 — Claude Code 와 비교

|              | Claude Code                     | WorldLines                              |
|--------------|---------------------------------|-----------------------------------------|
| 영역         | 코드 편집 / 소프트웨어 agent    | 게임 월드 / AIRP agent                  |
| 상태 단위    | 파일 + git                      | Events + Snapshots + branches           |
| 주 루프      | Plan → Edit → Test              | Plan → Diff → Apply → Save              |
| 동봉         | 저장소는 직접 준비              | `stoneford` 스타터 템플릿 동봉          |
| Sandbox      | Shell / 컨테이너                | 엔진 내장 Sandbox + Replay              |

Claude Code 가 코드용 IDE 라면, WorldLines 는 살아있는 세계를 위한 IDE.

> 참고: 현재 WorldLines 의 harness 는 Claude Code 보다 엄격합니다 — 신뢰할 수 있는 orchestration 을 위해 완전한 컨텍스트에 의존합니다. 이는 더 높은 결정성과 더 쉬운 디버깅을 위한 의도적인 트레이드오프이며, 결함이 아닙니다.

> **왜 독점 엔진 + 개방 데이터인가?** WorldLines 엔진은 빠른 이터레이션 중에 orchestration 충실도를 유지하기 위해 독점 프리뷰로 공개됩니다. 반면 게임 데이터 포맷, 스타터 월드(Stoneford 등), 통합 프로토콜은 상호 운용 가능한 AIRP 에코시스템을 키우기 위해 개방되어 있습니다.

---

## 빠른 시작

```bash
# 1. 설치 (다른 방법은 INSTALL.ko.md 참고)
uv tool install -e /path/to/worldlines

# 2. stoneford 스타터 스캐폴딩 및 실행
mkdir my-world && cd my-world
neonrp init
neonrp game new --template stoneford

# 3. TUI 에서 플레이
neonrp tui
```

`look around` 를 입력하고 Enter. 이것이 당신의 첫 agentic 턴입니다.

30 분 튜토리얼은 [QUICKSTART.ko.md](QUICKSTART.ko.md) 를 참고.

---

## 모듈 맵

- [INSTALL.ko.md](INSTALL.ko.md) — wheel / 소스 / `uv tool` 설치
- [QUICKSTART.ko.md](QUICKSTART.ko.md) — 30 분 첫 플레이 가이드
- [CONCEPTS.ko.md](CONCEPTS.ko.md) — Events, Snapshots, branches, Agents, Sandboxes
- [CLI_REFERENCE.ko.md](CLI_REFERENCE.ko.md) — 모든 `neonrp` 명령
- [TUI_GUIDE.ko.md](TUI_GUIDE.ko.md) — 터미널 UI 레퍼런스
- [RELEASE_NOTES.ko.md](RELEASE_NOTES.ko.md) — v0.1.0 범위와 로드맵
- [templates/stoneford-worldlines/](templates/stoneford-worldlines/README.ko.md) — 샘플 월드와 Agents
- [CONTRIBUTING.ko.md](CONTRIBUTING.ko.md) — 기여 방법
- [LICENSE](LICENSE) — 독점 프리뷰 조건

## 커뮤니티 및 연락처

- 이슈 및 토론: GitHub (링크는 2026-04-17 D-Day 공개 예정)
- 창립자 / 메인테이너: Ludic Dynamics (일본 도쿄)
- 연락처: `hello@ludic-dynamics.com` (임시)

---

## 저작권 및 감사

Copyright © 2026 worldlines-nikoloside, redoctober. All rights reserved.

WorldLines 는 독점 엔진이며, 평가 목적의 프리뷰로만 배포됩니다. 재사용,
재배포, 파생 저작물에 대한 라이선스는 부여되지 않습니다. 전체 조건은
[LICENSE](LICENSE) 를 참조하세요.

Ludic Dynamics 커뮤니티 여러분, 그리고 이번 릴리스를 가능하게 해준
amber 및 그 밖의 친구들에게 감사드립니다.

*WorldLines 와 Ludic Dynamics 는 Ludic Dynamics 의 상표입니다.*
