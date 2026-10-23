# 스톤포드 · 엘레나

> `llm-rpg-starter`/`stoneford-orch`의 실제 contract를 바탕으로 한 혼합 템플릿: 옛 world contract는 그대로 두고, 새로운 soul runtime을 붙였다.

`stoneford-elena`는 `stoneford-orch`를 통째로 갈아엎어 다시 쓴 것이 아니다. 실제로 돌아가 본
world-agent / town-agent / rules-referee contract 위에 `playthrough.json + souls/`와
`soul.md`를 덧붙인 것이다.

## 이 데모는 무엇인가

- 테스트할 수 있는 두 번째 세계
- `game/player/` 호환층을 남겨 둔, soul-native로 넘어가는 과도기 템플릿
- 확실한 히로인을 가진 스톤포드 변형판

## 런타임 형태

런타임에서 이 세계는 이렇게 움직인다:

`world-agent -> active souls -> world-agent`

동시에 `agents/` 아래의 스톤포드 domain-agent contract 계열도 그대로 유지한다.

## 진실의 출처

- `game/`은 여전히 world-agent가 소유하는 세계 상태다.
- `souls/elena-si-elena0001/`은 엘레나의 soul 진실이다.
- `game/player/*`는 지금의 orchestrator 시대 스톤포드 contract를 위한 호환용 투영이다.
  쓸모는 있지만, 더 이상 유일한 진실의 출처는 아니다.

soul의 정체성과 `game/player/*`가 어긋나면, soul 폴더를 장기적인 캐릭터의 기준으로,
`game/player/*`를 맞춰 나가야 할 이 세계 쪽 투영으로 본다.

## 포함된 Souls

- `elena-si-elena0001` — 히로인 / 플레이어 soul
- `rowan-si-rowan0001` — 제이드스톤의 젊은 모험가 soul. '세상의 끝' 깊은 굴의 전설을 쫓는다

## 왜 있는가

카구라는 순수한 soul-native 경로를 증명한다. 스톤포드 · 엘레나는 이행 경로를 증명한다.
검증된 world contract를 그대로 지키면서, 주인공 로직을 `game/player/`에서 명시적인
soul 번들로 조금씩 옮겨 갈 수 있다는 것.
