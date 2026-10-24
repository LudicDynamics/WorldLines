---
title: "터미널 명령"
description: "터미널 게임의 모든 슬래시 명령과 옛 명령이 옮겨 간 곳."
---

<!-- section: how -->
## 사용 방법

`neonrp`로 들어가는 터미널 게임에서 입력 상자에 `/`를 입력하면 명령이 자동 완성과 함께 나열됩니다. 인자 없는 명령은 대부분 선택 목록을 열기 때문에 id를 외울 필요가 없습니다.

아래 명령 외에 세계가 자기 명령을 가져올 수 있습니다. 예를 들어 그레이오크 저택의 기술 `/듣기`와 `/발견`은 `/`를 입력할 때 엔진 명령 옆에 나타납니다.

<!-- section: play -->
## 플레이

| 명령 | 동작 |
|---|---|
| `/open [세계 또는 저장]` | 인자 없음: 플레이할 수 있는 세계와 저장을 나열. 저장을 주면 이어서 하기. 세계를 주면 새 판 시작 |
| `/init [세계]` | 세계로 새 판 시작. 인자 없으면 선택 목록이 열리고, 거기서 빈 세계를 처음부터 만들 수도 있음 |
| `/load [저장 또는 스냅샷]` | 저장을 이어서 하거나 이 판의 스냅샷을 불러오기. 인자 없으면 선택 목록 |
| `/save [이름]` | 이 판에 스냅샷 저장 |
| `/undo` | 한 수 물리기 |
| `/undo list` | 이 줄기의 턴 나열 |
| `/undo <턴>` | 그 턴으로 돌아가 새 줄기 시작. 이전 줄기는 남음 |
| `/redo` | 방금 물린 수를 다시 하기 |
| `/status [페이지]` | 상태 패널. 페이지: `player` 나 · `agents` 캐릭터 · `plan` 계획판 · `dice` 주사위 · `settlement` 엔딩과 정산 · `contract` 플레이 계약 · `account` 계정과 판정자 · `usage` 사용량 · `room` 네트워크 테이블 |
| `/lang [언어]` | 이 판의 서술 언어: `zh` `en` `ja` `ko` |
| `/find <키워드>` | 이 세계의 장소, 인물, 아이템 검색 |
| `/clear` | 화면의 대화 지우기 |

<!-- section: characters -->
## 캐릭터

| 명령 | 동작 |
|---|---|
| `/who [캐릭터]` | 캐릭터의 시점으로 들어가기: 어디 있는지, 무엇을 기억하는지, 최근 몇 턴 동안 무엇을 했는지. 거기서 직접 이야기하거나 대신 행동할 수 있음 |
| `/cast [캐릭터] [역할]` | 라이브러리의 캐릭터를 이 세계에 `npc` 또는 `player`로 데려오기. 인자 없으면 데려올 수 있는 캐릭터 나열 |
| `/create <이름>` | build 모드에서 새 캐릭터 만들기. 에이전트가 씀 |
| `/remove <캐릭터>` | 캐릭터를 이 세계에서 내보내기(라이브러리의 사본은 그대로) |
| `/reset <캐릭터>` | 캐릭터가 여기서의 기억과 경험을 잊게 하기. 설정은 그대로 |
| `/import <파일>` | 세계 패키지(`.zip`) 또는 SillyTavern 카드(`.png` / `.json`) 가져오기. 내용으로 구분 |

<!-- section: build -->
## 세계 만들기

| 명령 | 동작 |
|---|---|
| `/mode [build 또는 play]` | 같은 세계 안에서 전환: build = 에이전트가 이 세계를 고치게 함, play = 플레이 |
| `/vault [build]` | 이 세계를 Obsidian 볼트로 투영해서 열기. `build`는 만들기만 하고 열지 않음 |
| `/dev [항목]` | 크리에이터와 문제 해결용: `graph` 편성 그래프 · `dry-run` 한 박자 시험 실행 · `beats` 서술에 박자 뼈대 표시 · `template` 템플릿 · `validate` 세계 검사 · `mcp` · `bridge` · `debug` |

<!-- section: app -->
## 계정, 설정, 업데이트

| 명령 | 동작 |
|---|---|
| `/login` | Worldlines 계정(선택): 판정자 Jev, 모델 중계, 세계 업로드. `/login code`는 브라우저 없이 로그인 · `/login status`는 상태 보기 · `/login out`은 로그아웃 |
| `/settings` | 모델, 키, Discord 브리지 등 설정 |
| `/update` | 업데이트 확인. `/update apply` 설치 · `/update status` 버전과 설정 보기 · `/update mode auto`, `prompt`, `notify`는 실행 시 동작 설정 · `/update channel` 업데이트 채널 변경 |
| `/help` | 명령 나열 |
| `/quit` · `/q` | 종료 |

<!-- section: input -->
## 입력 상자의 표시

| 쓰기 | 동작 |
|---|---|
| `@이름` | 캐릭터에게 말하기. `@`를 입력하면 그 자리에 있는 사람을 자동 완성 |
| `@dm` | 진행자에게 계속 진행하게 하기. 상의에서 바로 해결로 |
| 「결정」 | 같은 뜻. 이야기가 정리됨 |
| `#` | 문장 안에서 장소와 아이템 자동 완성 |

<!-- section: removed -->
## 옛 명령이 간 곳

1.0부터 명령은 위의 것들로 줄었습니다. 옛 명령을 입력해도 「알 수 없는 명령」으로 실패하지 않고, 지금 무엇을 쓰면 되는지 알려 줍니다.

| 옛 명령 | 지금 쓰는 것 |
|---|---|
| `/branch` | `/undo list` · `/undo <턴>` |
| `/worlds` `/worldlines` `/continue` | `/open` |
| `/game` | `/open` · `/create` |
| `/sessions` | `/load` |
| `/models` `/auth` `/wl-model` `/locale` | `/settings` |
| `/load-world` | `/import` |
| `/export-world` | 명령줄 `neonrp export-world` |
| `/context` | `/find` |
| `/replay` | `/dev dry-run` |
| `/compact` | `/clear` |
| `/copy` | `F6` |
| `/run` `/agent` | 그냥 말하기 |
| `/index` | 엔진이 알아서 최신으로 유지 |
| `/skills` | 에이전트가 스스로 사용 |
| `/files` | 명령줄 git |

몇 개는 더 이상 나열되지 않지만 입력하면 여전히 동작합니다. `/validate`(`/dev validate`에도 있음), `/mcp`(`/dev mcp`에도 있음), `/bridge`(`/dev bridge`에도 있음), `/debug`와 `/verbose`(`/dev debug`로 합쳐짐), `/stats`(지금은 `/status usage`), `/config`(평소에는 `/settings`).

`--mcp` 실행 모드와 Claude Code 프리셋은 1.0.3에서 제거되었습니다.
