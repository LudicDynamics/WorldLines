# CLI 레퍼런스

**Language:** [English](./CLI_REFERENCE.md) · [简体中文](./CLI_REFERENCE.zh.md) · [日本語](./CLI_REFERENCE.ja.md) · [한국어](./CLI_REFERENCE.ko.md)

> 상태: Beta — v0.1.0 명령은 안정, 플래그는 옵션이 추가될 수 있음

`neonrp` 커맨드라인 도구의 전체 레퍼런스. 최신이자 공식 플래그 목록은 `neonrp <cmd> --help` 로 확인하세요.

## 명령 맵

| 명령         | 용도                                            |
|--------------|-------------------------------------------------|
| `init`       | 현재 디렉터리에 `.neonrp/` 생성                 |
| `game`       | 스타터 월드 (templates) 스캐폴딩                |
| `run`        | agent 에게 쿼리 디스패치                        |
| `save`       | 현재 상태 snapshot                              |
| `load`       | snapshot 에서 복원                              |
| `branch`     | branch 생성 / 전환                              |
| `undo`       | head 를 event 1 단계 뒤로                       |
| `redo`       | undo 한 event 재적용                            |
| `validate`   | `game/` 을 schema 로 검증                       |
| `index`      | 엔티티 인덱스 구축 / 업데이트                   |
| `find`       | 엔티티 검색                                     |
| `context`    | 쿼리에 대한 관련도 랭킹                         |
| `agent`      | agent 라이프사이클                              |
| `import`     | SillyTavern / 외부 카드 가져오기                |
| `sandbox`    | sandbox 관리                                    |
| `replay`     | Replay 및 결정성 검증                           |
| `tui`        | 터미널 UI 실행                                  |

## 프로젝트 라이프사이클

```bash
neonrp init
neonrp game new --template stoneford    # 또는: default / isekai / kagura-island
neonrp validate
neonrp index build
```

## 플레이 루프

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

## Agents

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent logs --tail 10
```

### Agent run 옵션

| 옵션            | 용도                                                             |
|-----------------|------------------------------------------------------------------|
| `--query, -q`   | 지시 (필수)                                                      |
| `--provider`    | config provider 오버라이드 (glm/openai/lmstudio/ollama/stub)     |
| `--fixture`     | stub provider 용 proposal JSON 파일                              |
| `--apply`       | 미리보기 후 적용                                                 |
| `--agentic`     | 다중 턴 agentic 루프                                             |
| `--json`        | 기계 판독 가능 출력                                              |

## 검색

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

## Import

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

## Sandbox

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force
```

## Replay

```bash
neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

## TUI

```bash
neonrp tui
neonrp tui --branch experiment
neonrp tui --provider lmstudio
neonrp tui --continue
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose
```

## 종료 코드

| 코드 | 의미                                                           |
|------|----------------------------------------------------------------|
| 0    | 성공                                                           |
| 1    | 일반 에러 (검증 실패, not found 등)                            |
| 2    | 시스템 에러 (미초기화, 어댑터 실패)                            |

## 환경 변수

| 변수                | 용도                           |
|---------------------|--------------------------------|
| `OPENAI_API_KEY`    | OpenAI                         |
| `GLM_API_KEY`       | Zhipu GLM                      |
| `ANTHROPIC_API_KEY` | Anthropic                      |
| `NEONRP_E2E_LLM`    | 실제 엔드포인트 테스트 활성화  |

프로젝트 루트의 `.env` 는 자동으로 로드됩니다.

## 참고

- [TUI_GUIDE.ko.md](TUI_GUIDE.ko.md)
- [CONCEPTS.ko.md](CONCEPTS.ko.md)
