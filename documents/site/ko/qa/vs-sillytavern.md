---
title: "vs SillyTavern"
description: "SillyTavern의 포맷과 호환 — 그러나 다른 패러다임: 프롬프트 단위 채팅이 아니라 에이전트형 시뮬레이션."
---

<!-- section: two-paradigms -->
## 두 가지 패러다임: 프롬프팅 vs 에이전트

**SillyTavern**은 선택한 LLM에 정교하게 다듬은 **프롬프트**를 보내는 파워 유저용 *프론트엔드*입니다. 캐릭터, lorebook, 프롬프트 매크로 — 프롬프트 기반 롤플레이를 위한 동급 최강의 채팅 지향 도구입니다.

**WorldLines는 에이전트형입니다.** 하나의 LLM이 프롬프트에 답하는 대신, 오케스트레이션 시스템 — **Claude Code**와 **Codex**를 구동하는 것과 같은 종류 — 이 세계를 실행합니다: 계획하고, 툴을 호출하고, 상태를 읽고 쓰며, 스스로 행동하는 agent들. 우리는 캐릭터에게 프롬프트를 던지지 않습니다; 우리는 캐릭터를, 그리고 그를 둘러싼 세계를 **시뮬레이션**합니다.

<!-- section: compatible -->
## 호환성을 유지하고 싶다

SillyTavern의 character card와 world book은 훌륭한 콘텐츠 포맷이며, 우리는 사람들이 있는 그곳에서 만나고 싶습니다. SillyTavern card는 이미 import할 수 있습니다.

```bash
neonrp import sillytavern-card card.png --id mira-ashford
```

방향성: SillyTavern 포맷을 계속 import 가능하게 유지하면서, 그 위에 **새로운 플레이 방식**을 제공하는 것 — 프롬프트 단위 채팅이 아니라 에이전트형 시뮬레이션.

<!-- section: agent-roleplay -->
## 새로운 종류의 롤플레이

이미 많은 사람들이 **Claude Code**나 **Codex** 안에서 *직접* 롤플레이하며, 에이전트형 시스템이 캐릭터와 장면을 구동하게 합니다. 이는 프롬프트 기반 프론트엔드가 만들어진 목적을 이미 넘어선 것입니다 — 우리가 **Agent Role Play**라 부르는 새로운 패러다임입니다.

WorldLines는 정확히 이를 위해 만들어졌습니다: agent 오케스트레이션을 통해 페르소나와 세계를 시뮬레이션하는 것. 그리고 우리는 에이전트형 롤플레이가 강력한 만큼 좋은 느낌이 들도록 **프론트엔드 완성도**에 투자하고 있습니다 — 돌아가는 시뮬레이션의 깊이를, 날것의 터미널에 살지 않고도.

지속되고, branch하며, 진정으로 *시뮬레이션되는* 세계를 원할 때 WorldLines를 선택하세요. 최대한의 프롬프트 유연성과 정착된 확장 생태계를 원할 때는 SillyTavern을 찾으세요 — 그리고 어느 쪽이든 당신의 card를 import하세요.
