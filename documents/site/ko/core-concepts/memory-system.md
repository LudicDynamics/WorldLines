---
title: "Plan → Diff → Apply"
description: "Agent는 파일을 직접 편집하지 않습니다. Proposal을 발행합니다. 사용자가 검토하고 적용합니다."
---

<!-- section: proposal -->
## Proposal

Agent가 세계에 쓸 때 파일을 직접 편집하지 않습니다. **Proposal**을 발행합니다.

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

엔진이 diff를 보여주고, 스키마로 검증한 뒤, 새 event로 적용합니다. 사용자(또는 자동 적용 규칙)가 전이를 승인합니다.

<!-- section: ops-schema -->
## Operation 종류

Operation은 작고 닫힌 어휘입니다.

- `upsert_text` — 텍스트 내용으로 파일을 생성하거나 교체
- `upsert_json` — JSON 엔티티를 생성하거나 교체
- `patch_json` — 타겟팅된 필드 업데이트 (JSONPath 기준)
- `delete` — 파일 제거
- `move` — 이름 변경 / 이동

모든 op는 적용 전에 스키마로 검증됩니다.

<!-- section: retrieval -->
## Retrieval — minimal context

Harness는 각 agent 턴에 관련 있는 엔티티만 공급하기 위해 **bounded retrieval**을 사용합니다.

- 하이브리드 fuzzy + vector 검색
- 쿼리당 엔티티 예산
- 엔티티 종류 필터 (`--kind location`, `--kind npc`)

CLI에서:

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

이것이 세계가 10,000개 이상의 엔티티로 커져도 턴 지연을 제한 안에 유지하는 방법입니다.

<!-- section: determinism -->
## 왜 중요한가

Plan → Diff → Apply는 WorldLines를 **검토 가능**하고 **재현 가능**하게 만드는 것입니다.

- 모든 상태 변경을 구조화된 diff로 감사할 수 있습니다
- Agent가 조용히 세계 상태를 손상시킬 수 없습니다
- `replay verify`가 event로부터 같은 상태를 다시 유도할 수 있습니다
- 채팅 UI는 이런 보장을 제공하지 않습니다
