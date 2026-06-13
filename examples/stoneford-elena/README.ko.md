# 🌿 Stoneford · Elena — 멀티에이전트 월드

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> 엔진 모드: **multi-agent**. Stoneford 세계에 살아있는 소울 —— **Elena** 와 **Rowan** —— 이 깃든다. 그들은 스스로 생각하고, 기억하고, 행동한다.

**[▶ 온라인 플레이 →](https://hub.worldlines.gg/play/worlds/stoneford-elena)** · **[Elena와 대화 →](https://hub.worldlines.gg/play/souls/elena)**

## 왜 multi-agent인가

`fast` 와 `orch` 모드는 **world-agent + 도메인 agent**(마을·던전·전투)를 구동합니다. NPC는 오케스트레이터가 대변하는 데이터입니다.

**multi-agent** 는 `souls/` 폴더를 추가합니다. 각 소울은 **독립된 캐릭터 agent** 로, 고유한 페르소나·기억·비밀·목표를 가지고 스스로 생각합니다. 런타임은 소울 래퍼로 진입합니다:

```
world-agent  →  active souls (Elena, Rowan)  →  world-agent
  (주권적        각 소울이 스스로                  (턴을 닫고,
   편성자)        발화 / 행동 / 내면의 목소리 결정)    당신에게 서술)
```

소울은 격리된 액터 —— 폴더를 공유하지 않고 세계 상태를 소유하지 않습니다. Elena는 3세션 전 당신의 말을 기억하고, Rowan은 당신이 있든 없든 자신의 목적을 추구합니다. 이것이 **마을 / 사회** 모델의 실천입니다.

```bash
neonrp tui --from examples/stoneford-elena
```

## 소울

| Soul | 누구 |
|---|---|
| **Elena**（`elena-si-elena0001`） | 기억하는 치유사 —— 따뜻하고 예리하며, 자신의 과거를 안고 있다 |
| **Rowan**（`rowan-si-rowan0001`） | 자신의 동기, 자신의 시간선을 가진다 |

각 소울 폴더는 번들 구조를 따릅니다: `soul.json` / `soul.md`(정체성), `persona/`(특성·가치·관계), `background/`(역사·출신·비밀), `character/`(프로필·스탯·인벤토리), `long-term-memo/` + `short-term-memo/`(기억), `rules/`(소울별 가드레일), `agents/`(소울의 6-agent 마음), `trajectory/`(살아온 궤적).

## 세계

Stoneford orch 월드 위에 구축（`agents/` = world-agent + 마을 / 던전 / 전투 / 스토리 / world-builder / rules / clock / evolution / character agent）, `game/` 이 세계 진실을 보관. 소울은 그 위에 삽니다.

## 라이선스

**AGPL-3.0** —— 포크, 수정, 자신의 세계 출시 가능. 엔진(`neonrp`)은 독점 프리뷰.
