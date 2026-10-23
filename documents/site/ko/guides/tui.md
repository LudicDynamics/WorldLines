---
title: "TUI 터미널 가이드"
description: "터미널에서 플레이와 관리: worldlines 런처, 슬래시 명령, 설정과 데이터 위치."
---

<!-- section: entries -->
## 두 개의 입구

설치 후(`pip install worldlines`, 또는 `uv tool install worldlines`, 또는 원라인 `curl -LsSf https://worldlines.gg/install.sh | sh`) 명령은 두 가지. 둘 다 실행 시 새 릴리스를 확인해 스스로 업데이트합니다:

- **`worldlines`** — 로컬 웹 UI, http://127.0.0.1:8787/local: 월드, 세이브, 창작 데스크, 설정.
- **`neonrp`** — 터미널. 「Welcome to WorldLines」 런처에서 월드나 세이브를 고르면 게임으로. 안에서는 슬래시 명령(`/status` · `/plan` · `/update` …). 첫 실행 시 UI 언어 선택.

> 브라우저가 편하면 `neonrp web` 으로 http://127.0.0.1:8787/local — TUI 와 같은 데이터를 언제든 오갈 수 있습니다.

<!-- section: first-run -->
## 첫 플레이

`worldlines` 메인 메뉴는 2×2: **플레이**(계속/새로), **월드 라이브러리**(새로/가져오기/Hub/관리), **캐릭터 라이브러리**(Soul Talk/새로/가져오기/Hub/관리), 하단(설정/종료). 단축키 `c` 계속, `n` 새로, `s` 설정.

새 플레이 흐름: **월드 선택 → 아바타+동행 캐릭터(캐스팅) → 모델 preset(첫 사용 시 키 설정 가이드) → 화면 선택(🌟브라우저 / 터미널)**. 터미널을 고르면 세계가 자동으로 시작됩니다.

<!-- section: slash -->
## 플레이 중 슬래시 명령

`/` 입력 시 자동완성과 추천이 나옵니다. 자주 쓰는 것:

- `/save [이름]` · `/load` · `/undo` · `/redo` — 저장과 체크포인트 단위 되돌리기
- `/cast <soul> [npc|player]` — 라이브러리 캐릭터를 이번 플레이에 투입
- `/mode [build|play]` — 창작/플레이 전환(build 에서 agent 가 월드 파일을 자유 편집)
- `/models` · `/auth` · `/config` · `/locale` — 모델·키·언어
- `/export-world` · `/load-world <zip>` — 월드 패키징/복원
- `/settings` — 전체 설정; `/help` — 모든 명령

글로벌 키: `Ctrl+K` 커맨드 팔레트, `Ctrl+L` 정보 레이어, `F6` 기록 복사.

순수 REPL: `neonrp play`(입력=행동. `/trace` 로 지난 턴 라우팅, `/debug` 로 agent 호출).

<!-- section: settings-data -->
## 설정과 데이터 위치

설정(런처 「설정」 또는 `/settings`): 모델 항목(테스트/키 교체/삭제), creation LLM(창작 전용 모델), 이미지 생성(ComfyUI URL/ckpt/커스텀 workflow 노드, 또는 OpenAI), 언어, Discord 브리지.

데이터 위치:

- `~/.worldlines/worlds/` 월드 소스 · `plays/` 플레이별 디렉터리 · `souls/` 캐릭터 라이브러리
- `~/.neonrp/config.json` 키/이미지 백엔드/언어(TUI 와 Web 공유)

백업 = `~/.worldlines` 통째로 보관.
