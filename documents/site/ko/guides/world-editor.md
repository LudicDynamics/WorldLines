---
title: "CLI Reference"
description: "필수 `neonrp` 명령들. 정식 플래그 목록은 `worldlines <cmd> --help`에서 확인하세요."
---

<!-- section: overview -->
## 명령 한눈에 보기

| 명령        | 용도                                           |
|-------------|------------------------------------------------|
| `init`      | 현재 디렉터리에 `.neonrp/` 생성               |
| `game`      | 스타터 월드 스캐폴딩 (템플릿)                   |
| `run`       | 쿼리를 agent에 dispatch                         |
| `save`      | 현재 상태를 snapshot으로 저장                   |
| `load`      | snapshot에서 복원                               |
| `branch`    | branch 생성 또는 전환                           |
| `undo`      | head를 한 event 뒤로 이동                       |
| `redo`      | undo한 event를 다시 적용                        |
| `validate`  | `game/`를 스키마에 대해 검증                   |
| `index`     | 엔티티 인덱스 빌드/갱신                         |
| `find`      | 엔티티 검색                                     |
| `context`   | 쿼리에 대한 순위화된 관련성                     |
| `agent`     | Agent 라이프사이클 (new / list / show / run / apply / logs / context / path) |
| `import`    | SillyTavern / 외부 card import                  |
| `sandbox`   | Sandbox 관리                                    |
| `replay`    | Replay 및 결정성 검증                           |
| `tui`       | Terminal UI 실행                                |

<!-- section: project -->
## 프로젝트 라이프사이클

```bash
worldlines init                           # .neonrp/ 생성
neonrp game new --template stoneford-orch  # 템플릿: default / kagura-island / soul-talk / stoneford-elena / stoneford-orch
neonrp validate                       # game/ 스키마 검사
neonrp index build                    # retrieval 인덱스 재구축
```

<!-- section: play-loop -->
## Play 루프

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp load checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

<!-- section: agents -->
## Agent

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent path town-agent                            # agent 디렉터리 출력
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent apply town-agent --proposal proposal.json --dry-run
neonrp agent context town-agent --query "harbor" --limit 8
neonrp agent logs --tail 10
```

### `agent run` 옵션

| 옵션           | 용도                                              |
|----------------|---------------------------------------------------|
| `--query`, `-q` | 지시문 (필수)                                     |
| `--provider`   | config provider 오버라이드 (glm / openai / lmstudio / ollama / stub) |
| `--fixture`    | stub-provider proposal JSON 파일                  |
| `--apply`      | 미리보기 후 적용                                  |
| `--json`       | 기계 판독 가능 출력                               |

<!-- section: retrieval -->
## Retrieval

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

`find`는 엔티티 검색을 수행하고, `context`는 쿼리에 대한 순위화된 관련 엔티티를 반환합니다 (embedding이 설정되어 있으면 하이브리드 fuzzy + vector).

<!-- section: import -->
## Import

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

SillyTavern character card (JSON 또는 PNG-with-tEXt)를 import합니다. [SillyTavern Import 가이드](/docs/guides/sillytavern-import) 참고.

<!-- section: sandbox-replay -->
## Sandbox & Replay

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force

neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

<!-- section: tui -->
## TUI — 실행 플래그

```bash
neonrp tui                               # 기본
neonrp tui --branch experiment           # 특정 branch
neonrp tui --provider lmstudio           # provider 오버라이드
neonrp tui --continue                    # 마지막 세션 재개
neonrp tui --new                         # 새 세션 강제 시작
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose                     # 원시 LLM 트래픽 스트리밍
```

<!-- section: slash-commands -->
## TUI — 슬래시 명령

TUI 안에서 `/<cmd>`는 액션을 트리거합니다. 전체 목록:

### 세션 및 이력

| 명령          | 용도                                                    |
|---------------|---------------------------------------------------------|
| `/new`        | 새로운 대화 세션을 시작                                 |
| `/continue`   | 현재 branch의 이전 대화를 재개                          |
| `/sessions`   | Branch별로 저장된 세션을 나열                           |
| `/clear`      | 대화 이력 지우기                                        |
| `/copy`       | 대화를 클립보드에 복사                                  |
| `/compact`    | 대화 이력을 압축                                        |
| `/stats`      | 대화 통계 표시                                          |
| `/files`      | 최근에 수정된 파일 나열                                 |

### 월드 및 상태

| 명령                                   | 용도                                            |
|----------------------------------------|-------------------------------------------------|
| `/init`                                | 현재 디렉터리에 프로젝트 초기화                 |
| `/game new`                            | 템플릿으로 새 월드 스캐폴딩                     |
| `/worlds`                              | `~/.worldlines/games/`의 월드 탐색             |
| `/worldlines`                          | 가이드형 월드 선택기 (model + 월드 + 실행)      |
| `/save [name]`                         | 상태 snapshot                                   |
| `/load [name]`                         | Snapshot에서 복원                               |
| `/branch [name\|list]`                 | Branch 생성 / 전환 / 나열                       |
| `/undo` · `/redo`                       | Head를 뒤로 / 앞으로 이동                       |
| `/sandbox [new\|list\|switch\|drop]`     | Sandbox 관리                                    |
| `/validate`                            | `game/`를 스키마에 대해 검증                    |
| `/index [build\|update]`                | Retrieval 인덱스 재구축/갱신                    |
| `/find <keyword>`                      | 엔티티 검색                                     |
| `/context <query>`                     | 쿼리에 대한 순위화된 관련성                     |
| `/export-world [output.zip]`           | `game/` + `.neonrp/`를 .zip으로 압축           |
| `/load-world <zip>`                    | Export된 zip을 `~/.worldlines/games/`로 복원   |
| `/import sillytavern-card <file>`      | SillyTavern character card import               |
| `/replay [verify\|checkout]`            | Replay 검증                                     |

### 모드 및 라우팅

| 명령                                             | 용도                                              |
|--------------------------------------------------|---------------------------------------------------|
| `/mode [build\|sandbox\|play]`                   | Play 모드 전환                                    |
| `/router-mode [fast\|orchestrator\|multi-agent]` | Router 실행 모드 전환                             |
| `/autoapply [on\|off\|status]`                    | Sandbox 자동 적용 토글                            |
| `/verbose [on\|off\|status]`                      | Verbose 디버그 모드 토글                          |
| `/debug`                                        | MCP 디버그 모드 토글                              |

### Agent 및 실행

| 명령                                                                           | 용도                                                 |
|--------------------------------------------------------------------------------|------------------------------------------------------|
| `/run <query>`                                                                 | Agent 쿼리를 명시적으로 실행                         |
| `/agent [list\|show <name>\|run <name>\|new <name>]`                            | Agent 라이프사이클                                   |
| `/apply`                                                                       | Sandbox 모드에서 대기 중인 proposal 적용             |
| `/skills`                                                                      | 사용 가능한 skill 나열                               |

### Provider 및 설정

| 명령                                                                 | 용도                                               |
|----------------------------------------------------------------------|----------------------------------------------------|
| `/models [name\|list\|set <name>\|show <name>]`                      | 빠른 모델 전환                                     |
| `/auth [list\|add\|set\|rm\|show]`                                   | 이름이 붙은 모델 설정 관리                         |
| `/wl-model [preset]`                                                | WorldLines 모델 preset 전환 (glm / opus)           |
| `/config [show\|set <key> <value>]`                                 | 설정 표시 / 변경                                   |
| `/settings`                                                          | 통합 모델 / api key / discord 설정 열기            |
| `/locale [auto\|en\|zh\|ja\|ko]`                                    | UI 언어 전환                                       |
| `/mcp [status\|restart <server>]`                                   | MCP 서버 관리                                      |
| `/bridge [status\|start <name>\|stop <name>]`                        | 런타임에 Discord / Telegram 브리지 관리            |
| `/update [check\|apply\|status\|channel <name>]`                     | worldlines 업데이트 확인 / 적용                        |

### 기타

| 명령          | 용도                                      |
|---------------|-------------------------------------------|
| `/help`        | 도움말 표시                               |
| `/quit` · `/q`  | TUI 종료                                  |

<!-- section: exit-codes -->
## 종료 코드

| 코드 | 의미                                              |
|------|---------------------------------------------------|
| 0    | 성공                                              |
| 1    | 일반 오류 (검증 실패, 찾을 수 없음 등)             |
| 2    | 시스템 오류 (초기화되지 않음, 어댑터 실패)          |

<!-- section: env -->
## 환경 변수

| 변수                 | 용도                          |
|---------------------|-------------------------------|
| `OPENAI_API_KEY`    | OpenAI                        |
| `GLM_API_KEY`       | Zhipu GLM                     |
| `ANTHROPIC_API_KEY` | Anthropic                     |
| `NEONRP_E2E_LLM`    | 실제 엔드포인트 테스트 활성화 |

프로젝트 루트의 `.env`는 자동으로 로드됩니다.
