---
title: "Mode — Build · TUI · Web UI"
description: "월드를 실행하는 세 가지 방법: 저작(Build), 터미널에서 플레이(TUI), 또는 브라우저에서 플레이(Web UI)."
---

<!-- section: modes -->
## 세 가지 모드: Build · TUI · Web UI

월드는 세 가지 모드 중 하나로 실행됩니다.

| 모드 | 무엇인가 | 어디서 |
|---|---|---|
| **Build** | 월드 저작 — `game/` 파일을 직접 편집하거나, AI agent가 대신 편집(plan → diff → apply) | 런처 · CLI · 임의의 편집기 |
| **TUI** | Claude Code 스타일로 터미널에서 플레이 — thinking, tool-use, 내레이션을 관찰 | `neonrp tui` |
| **Web UI** | 브라우저에서 플레이, 모든 agent를 실시간으로 관찰 | [WebHub](https://hub.worldlines.gg), 또는 로컬에서 `neonrp web` |

**플러그형 미디어 생성.** 월드는 텍스트에 국한되지 않습니다. 장면이 전개될 때 엔진이 호출하는 생성 API를 연결할 수 있습니다.

- **이미지 생성 API** — 장면 아트, 캐릭터 초상, 핵심 순간
- **BGM 생성 API** — 분위기를 따라가는 적응형 배경 음악

그래서 같은 에이전트형 월드가 단순한 트랜스크립트가 아니라 완전한 시청각 경험으로 렌더링될 수 있습니다.

> **Build**와 플레이 내부에서, 엔진은 agent proposal이 *어떻게* 적용되는지도 추적합니다 — **직접**, **게이트(sandbox)**, 또는 **자동** — 그리고 이는 [router 모드](/docs/core-concepts/engine-modes)(fast / orchestrator / multi-agent)와 조합됩니다. 아래 섹션을 참조하세요.

<!-- section: build-mode -->
## Build Mode

저작 모드. `game/`의 파일을 (어떤 편집기로든) 직접 편집하며 — agent 턴이 라우팅되지 않습니다. 유용한 경우.

- 새 마을 / NPC / 퀘스트 스캐폴딩
- 플레이 세션에서 드러난 데이터 수정
- 주어진 상태를 agent가 어떻게 narration하는지 빠른 테스트

*사용자*가 신뢰의 원천이므로 승인 게이트도 없고 router 모드도 의미가 없습니다.

<!-- section: sandbox-mode -->
## Sandbox Mode

Agent 실행이 **proposal**을 생성하면 사용자가 검토하고 **턴마다 승인**합니다. `.neonrp/events.jsonl`에 기록되기 전에 diff가 먼저 표시됩니다.

TUI 내에서 `/autoapply on|off`로 게이트를 즉시 토글할 수 있습니다 — `autoapply on`은 해당 세션 동안 sandbox를 사실상 play처럼 동작하게 만들고, `autoapply off`는 게이트를 복원합니다.

**적합한 상황**:
- Proposal을 완전히 신뢰하지 않는 새 agent를 실험
- 거부권을 유지하면서 AI 보조로 저작
- Dispatcher / harness 동작 디버깅 — 모든 proposal이 드러납니다

<!-- section: play-mode -->
## Play Mode

GM 모드. Agent가 proposal을 생성하고 엔진이 이를 **자동 적용**합니다. 트랜스크립트는 서사처럼 읽힙니다 — 스키마 검증에 실패하지 않는 한 diff는 보이지 않습니다.

플레이어가 대부분의 시간을 보내는 모드입니다. 이야기가 전개되면서 세계가 바뀝니다. 나중에 되감고 싶다면 위험한 행동 전에 branch 또는 snapshot을 만들어 두세요.

여기에서 router 모드가 적용됩니다. 최소한의 라우팅에는 `/router-mode fast`, cross-domain 일관성에는 `/router-mode orchestrator`, sub-agent 위임을 유지하려면 `/router-mode multi-agent`를 사용하세요.

<!-- section: tui-layout -->
## TUI 레이아웃

상단에 단일 창의 대화형 트랜스크립트, 하단에 입력줄, 오른쪽 상단에 상태 표시줄. 상태 표시줄의 `[AUTO]`/`[manual]` 태그는 현재 play 모드를 반영합니다.

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
└─────────────────────────────────────────────────────────────────┘
```
