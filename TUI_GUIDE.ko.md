# TUI 가이드

**Language:** [English](./TUI_GUIDE.md) · [简体中文](./TUI_GUIDE.zh.md) · [日本語](./TUI_GUIDE.ja.md) · [한국어](./TUI_GUIDE.ko.md)

> 상태: Beta — 레이아웃 안정. 키바인딩은 v0.2 에서 설정 가능

WorldLines TUI 는 플레이와 월드 제작 모두를 위한 Claude-Code 스타일의 대화형 터미널입니다.

## 실행

```bash
neonrp tui                               # 기본
neonrp tui --branch experiment           # 특정 branch
neonrp tui --provider lmstudio           # provider 오버라이드
neonrp tui --continue                    # 이전 세션 재개
neonrp tui --new                         # 강제 새 세션 (기본)
neonrp tui --import-card card.png        # 첫 턴 전 임포트
neonrp tui --verbose                     # 원시 LLM 트래픽 스트리밍
```

`init` 만 한 디렉터리도 바로 build 모드에 진입할 수 있습니다. `game new` 는 선택사항이며, 기본 월드 + play-agent 스캐폴드를 추가할 뿐입니다.

## 레이아웃

상단에 단일 페인의 대화형 transcript, 하단에 입력 줄, 우측 상단에 상태 바.

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Transcript                                                     │
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
├─────────────────────────────────────────────────────────────────┤
│ q Quit │ Ctrl+K Commands │ Esc Interrupt │ F6 Copy              │
└─────────────────────────────────────────────────────────────────┘
```

## 모드

`/mode <name>` 로 전환:

| 모드      | 동작                                                         |
|-----------|--------------------------------------------------------------|
| `build`   | 직접 파일 편집 + 자연스러운 서술. 제작용.                    |
| `sandbox` | Proposal 파이프라인. 모든 변경에 승인 필요.                  |
| `play`    | GM 모드. auto-apply ON, 완전 몰입.                           |

## 슬래시 명령

| 명령                            | 용도                                        |
|---------------------------------|---------------------------------------------|
| `/init`                         | 현재 디렉터리에서 프로젝트 초기화           |
| `/game new [--template T]`      | 스타터 월드 스캐폴딩                        |
| `/mode <build\|sandbox\|play>`  | 인터랙션 모드 전환                          |
| `/save [name]`                  | snapshot                                    |
| `/load <name>`                  | snapshot 에서 복원                          |
| `/branch <name>`                | branch 생성 / 전환                          |
| `/undo` / `/redo`               | head 앞뒤 이동                              |
| `/run <query>`                  | dispatcher 명시 실행                        |
| `/files`                        | 파일 내비게이터 표시                        |
| `/skills`                       | 빌트인 + 로컬 skill 목록                    |
| `/agents`                       | agent 와 trigger 목록                       |
| `/import sillytavern-card`      | 캐릭터 카드 임포트                          |
| `/sessions`                     | 세션 선택기                                 |
| `/continue` / `/new`            | 세션 선택                                   |
| `/verbose on\|off\|status`      | 상세 진단 토글                              |
| `/clear`                        | transcript 지움 (상태는 그대로)             |
| `/help`                         | 앱 내 도움말                                |

Tab 으로 명령 자동완성, Enter 로 제출.

## 키바인딩

| 키           | 동작                                             |
|--------------|--------------------------------------------------|
| `q`          | 종료                                             |
| `Ctrl+Q`     | 안전 종료 (즉시 터미널 복귀)                     |
| `Esc`        | 진행 중인 LLM 턴 중단                            |
| `Ctrl+K`     | 명령 팔레트                                      |
| `Ctrl+P`     | 명령 팔레트 (대체)                               |
| `Enter`      | 제출                                             |
| `F6`         | 전체 transcript 복사                             |

## 스트리밍 출력

세 스트림이 교차되어 표시됩니다:

- **user** — 입력
- **tool** — tool 호출 (`read_context`, `find`, 파일 읽기 등)
- **thinking** — 기본 접힘. 펼쳐서 추론 확인
- **agent** — 최종 서술

우측 상단 상태 바에 실시간 token 카운터.

## 세션 지속성

세션은 branch 별로 보존됩니다. `--continue` 는 현재 branch 의 이전 세션 복원, `/sessions` 는 branch 간 이동용 선택기를 엽니다.

## 트러블슈팅

| 증상                            | 해결                                             |
|---------------------------------|--------------------------------------------------|
| 문자가 깨짐                     | iTerm2 / Ghostty / Alacritty 사용, UTF-8         |
| 색상이 이상                     | `TERM` 이 256 색 지원하는지 확인                 |
| TUI 프리즈                      | `Esc` 로 현재 턴 중단                            |
| agent 출력이 빔                 | `--verbose` 로 실행해 트래픽 확인                |
| "not initialized"               | `/init` 또는 `neonrp init` 실행                  |

## 참고

- [CLI_REFERENCE.ko.md](CLI_REFERENCE.ko.md)
- [CONCEPTS.ko.md](CONCEPTS.ko.md)
- [QUICKSTART.ko.md](QUICKSTART.ko.md)
