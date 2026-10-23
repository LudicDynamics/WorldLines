---
title: "World — New · Import · Export"
description: "게임 월드를 생성, import, export합니다."
---

<!-- section: new -->
## 새 월드 만들기

**런처에서 (권장).** WorldLines를 열고 **New world**를 선택하세요 — 내장 템플릿(Stoneford · Stoneford · Elena · Kagura Island · …) 중 하나를 고르면, 스캐폴딩되어 플레이하고 편집할 준비가 된 상태로 열립니다. 외울 것이 없습니다.

**AI agent로 저작.** WorldLines는 **Claude Code**와 **Codex** 저작 스킬을 제공합니다. AI 코딩 agent에서 저장소를 열고 원하는 것을 그냥 설명하세요 — *"네 명의 왕자가 있는 국풍(国风) 오토메 월드"* — 그러면 스킬이 `game/` 엔티티 + agent를 대신 스캐폴딩합니다. [저작 튜토리얼](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials)(character card · world card · 전체 월드 · soul) 참조.

**고급 — CLI.** 터미널에서 템플릿으로 스캐폴딩합니다.

```bash
neonrp game new --template stoneford-orch    # 플래그십 공성 TRPG (10-agent)
neonrp game new --template stoneford-elena   # Stoneford + Elena — 멀티에이전트 마을
neonrp game new --template kagura-island     # 미스터리 · 7 소울
neonrp game new --template default           # 최소 스타터
```

또는 빈 프로젝트에서 시작해 `game/`를 직접 손으로 저작할 수도 있습니다([첫 번째 세계 만들기](/docs/guides/creating-first-world) 참고).

<!-- section: home-dir -->
## 월드가 저장되는 위치 — `~/.worldlines/games/`

런처에서 import하거나 스캐폴딩하면 결과 월드는 `~/.worldlines/games/<name>/` 아래에 생성됩니다. 해당 디렉터리가 이 머신의 모든 월드를 담는 홈이며, 각 월드는 자체 `game/` 트리와 `.neonrp/` 상태를 가집니다.

현재 플레이 중인 프로젝트는 이 폴더들 중 하나의 인스턴스입니다 (임시 경로에서 `cd` + `worldlines init`으로도 여전히 작업할 수 있지만, `~/.worldlines/games/`가 관례입니다).

<!-- section: export -->
## 월드 export

내장 TUI 명령(또는 셸 별칭)을 사용합니다.

```
/export-world                    # TUI 안에서 → ~/Downloads/worldlines-<name>-<ts>.zip 생성
/export-world my-world.zip       # 출력 경로 지정
```

셸에서는 다음과 같이 실행합니다.

```bash
neonrp export-world                        # 기본 대상은 ~/Downloads/
neonrp export-world --output ~/my-world.zip
```

아카이브에는 `game/` 폴더와 `.neonrp/` 상태(events, snapshots, manifest)가 포함되어 있어, 수령자가 중단된 지점부터 정확히 이어서 플레이할 수 있습니다.

📸 **스크린샷 추후 추가 예정** — 런처 UI에서의 원클릭 export는 v0.1.6에 계획되어 있습니다.

<!-- section: import -->
## 월드 import

TUI 내부 또는 셸에서 실행합니다.

```
/load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

```bash
neonrp load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

이 명령은 아카이브를 `~/.worldlines/games/<name>/` 아래에 풀어서 다른 월드들과 나란히 나타나게 합니다. 이후 `/worlds` (TUI)로 전환하거나, 런처를 실행하기 전에 `cd ~/.worldlines/games/<name>`을 수행합니다.

📸 **스크린샷 추후 추가 예정** — 런처의 드래그 앤 드롭 import 흐름.

<!-- section: browse -->
## 로컬 월드 탐색

TUI 내부에서:

```
/worlds                         # ~/.worldlines/games/의 월드를 탐색하고 템플릿에서 스캐폴딩
/worldlines                     # 가이드형 월드 선택기 (model preset + 월드 + 실행)
```

또는 수동으로:

```bash
ls ~/.worldlines/games/
```
