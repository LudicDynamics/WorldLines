---
title: "Character Agent 구축"
description: "캐릭터 특화 AI agent를 만들기 위한 일급 플로우가 로드맵에 있습니다. 이 페이지는 의도한 모양을 미리 보여줍니다."
---

<!-- section: shipping -->
## ✓ v0.2.0 제공 중

멀티에이전트 캐릭터 NPC와 소울 agent는 v0.2.0에서 **운영 중**입니다. 캐릭터는 소울 번들(persona, character, agents, memo)로 제작되며, WebHub의 [Soul Talk](https://hub.worldlines.gg/play/souls/elena)에서 플레이하거나 CLI로 로컬에서 불러올 수 있습니다.

월드 NPC의 경우, 엔진이 `agents/` 아래에 NPC별 agent 디렉터리를 지원합니다([CLI `agent new`](/docs/guides/world-editor#agents) 참조). Orchestrator가 컨텍스트에 따라 해당 agent로 디스패치합니다.

<!-- section: agent-structure -->
## Agent 디렉터리 구조

`agents/my-agent/`를 다음과 같이 생성합니다.

```
agents/my-agent/
├── agent.json        # trigger, tag, priority
├── system.md         # 시스템 프롬프트 템플릿
├── skills/           # 선택: skill 조각
└── tools.json        # 선택: 추가 툴 정의
```

CLI로 스캐폴딩:

```bash
neonrp agent new my-agent
```

<!-- section: agent-json -->
## agent.json

```json
{
  "id": "harbormaster",
  "triggers": ["harbor", "dock", "ship"],
  "tags": ["location:harbor", "npc:official"],
  "priority": 50,
  "routing": {
    "invoke": "on_match",
    "fallback_to": "town-agent"
  }
}
```

Dispatcher는 쿼리가 trigger 또는 태그에 일치할 때 priority에 따라 이 agent를 선택합니다.

<!-- section: test-agent -->
## Agent 테스트

```bash
neonrp agent run harbormaster --query "who is in charge of the harbor?"
neonrp agent run harbormaster --query "register a ship" --apply
```

기계가 읽을 수 있는 출력은 `--json`을 추가하세요. 테스트 중 LLM 응답을 스텁하려면 `--fixture file.json`을 추가하세요.
