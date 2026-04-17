# 핵심 개념

**Language:** [English](./CONCEPTS.md) · [简体中文](./CONCEPTS.zh.md) · [日本語](./CONCEPTS.ja.md) · [한국어](./CONCEPTS.ko.md)

> 상태: Beta — 개념 모델은 안정, 내부 구현은 바뀔 수 있음

WorldLines 는 소수의 원시 요소를 중심으로 설계되어 있습니다. 이것들을 이해하면 나머지 엔진이 뒤따라옵니다.

## Events

세계의 모든 변경은 **append-only event** 로 `.neonrp/events.jsonl` 에 기록됩니다. 예:

```json
{
  "id": 42,
  "ts": "2026-04-17T10:03:11Z",
  "branch": "main",
  "agent_id": "town-agent",
  "kind": "proposal_applied",
  "ops": [
    {"op": "upsert_text", "path": "player/journal.json", "content": "..."}
  ]
}
```

Events 가 진실의 원천이며, `game/` 은 event 스트림의 *머티리얼라이제이션* 입니다. event 0 부터 재생하면 언제든 `game/` 을 재구성할 수 있습니다.

## Snapshots

**snapshot** (= save) 은 특정 event 시점의 `game/` 전체 복사본과 메타데이터입니다. `.neonrp/saves/<name>/` 에 저장됩니다. 빠른 되감기를 위한 것으로, 10,000 개 event 재생은 느리지만 snapshot 로드는 파일 복사일 뿐입니다.

```bash
neonrp save opening-scene
neonrp load opening-scene
```

## Branches

**branch** 는 event log 상의 이름 있는 head 포인터입니다. git 처럼 분기는 저렴하며, 현재 상태에서 fork 하여 분기된 event 를 씁니다.

```bash
neonrp branch try-stealing
```

Branches 는 `.neonrp/branches/` 아래 copy-on-write 로 변경되지 않은 엔티티를 공유합니다.

## Undo / Redo

`undo` / `redo` 는 head 포인터를 앞뒤로 이동시켜 가까운 snapshot 에서 복원한 뒤 전방으로 재생합니다. event log 는 절대 삭제되지 않습니다.

## Sandboxes

**sandbox** 는 snapshot 에서 만들어지고 ephemeral 로 표시된 branch 입니다. 이름 있는 branch 를 오염시키지 않고 "만약" 실험을 할 수 있으며, 깔끔하게 버릴 수 있습니다.

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... 플레이 ...
neonrp sandbox drop experiment --force
```

## Replay 와 결정성

동일한 events 와 시드된 LLM (또는 캐시된 fixture) 가 주어지면 재생은 동일한 `game/` 상태를 내야 합니다. `replay verify` 가 이를 검사합니다:

```bash
neonrp replay verify --from opening-scene
```

이것이 WorldLines 가 AI 기반 상태를 재현 가능하게 유지하는 방식입니다 — 채팅 UI 에서는 얻을 수 없는 속성입니다.

## Agents

**agent** 는 `agents/<agent-id>/` 디렉터리이며 다음을 포함합니다:

- `agent.json` — triggers, tags, priority, 라우팅 메타데이터
- `system.md` — system prompt 템플릿
- (선택) `skills/`, `tools.json`, `policies.md`

**dispatcher** 는 다음 순서로 각 쿼리의 agent 를 고릅니다:

1. 명시적 `--agent` 플래그
2. 정규식 trigger 패턴
3. Tag 겹침
4. Priority 타이브레이크

stoneford 스타터에는 6 개의 agent 가 포함됩니다 ([templates/stoneford](templates/stoneford/README.ko.md) 참고).

## Skills

**Skills** 는 agent 가 `use` 할 수 있는 재사용 가능한 prompt 조각 / 능력 모듈입니다. 빌트인 skill (엔진 동봉) 은 자동으로 등장하며, `skills/` 에 프로젝트 로컬 skill 을 정의할 수도 있습니다.

## Plan → Diff → Apply

agent 가 세계에 기록할 때 파일을 직접 편집하지 않고 **proposal** 을 발행합니다:

```json
{
  "run_id": "20260417-100311",
  "agent_id": "town-agent",
  "rationale": "Player examined the harbor; adding observed detail.",
  "ops": [
    {"op": "upsert_text", "path": "towns/stoneford.json", "content": "..."}
  ]
}
```

엔진은 diff 를 보여주고 schema 로 검증한 뒤 새 event 로 적용합니다. 당신 (또는 auto-apply 규칙) 이 전이를 승인합니다.

## Harness — 오케스트레이션 루프

WorldLines 의 agent harness 는 Plan–Diff–Apply 루프를 구현하며 다음을 제공합니다:

- Bounded retrieval (minimal-context, fuzzy+vector 하이브리드)
- 결정적 tool 호출 순서
- 턴별 예산 (tokens / tool calls)
- Thinking 채널과 서술의 분리

**orchestrator** agent 가 최상위 harness 코디네이터입니다 — `task()` 툴로 도메인 agent 에게 라우팅하고, 게임 상태를 일관되게 유지하며, 플레이어 대상 서술을 담당합니다.

## Build / Sandbox / Play 모드

TUI 는 세 가지 모드를 노출합니다:

- **build** — 직접 파일 편집 + 자연스러운 서술. 제작할 때 사용.
- **sandbox** — proposal 파이프라인 + 수동 승인. 가장 안전.
- **play** — GM 모드. auto-apply ON, 완전 몰입.

TUI 안에서 `/mode <name>` 으로 전환.

## 더 읽을거리

- [CLI_REFERENCE.ko.md](CLI_REFERENCE.ko.md) — 표면 명령
- [TUI_GUIDE.ko.md](TUI_GUIDE.ko.md) — 인터랙티브 워크플로우
- [templates/stoneford/](templates/stoneford/README.ko.md) — 샘플 월드
