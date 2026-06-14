# ⛩ 神楽島 Kagura Island — 멀티에이전트 월드

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> 엔진 모드: **multi-agent**. 일본풍 미스터리 · 타임 루프 · 이스 신화. 한 섬에 **일곱 살아있는 소울** —— WorldLines에서 가장 풍부한 멀티에이전트 사회. CoC 식 판정(d20 전투 아님).

> **로컬 실행**(TUI / CLI)—— multi-agent는 호스티드 플레이 미지원. `neonrp web --project examples/multi-agent/kagura-island`

## 왜 multi-agent인가

`fast` 와 `orch` 모드는 **world-agent + 도메인 agent** 를 구동하고 NPC는 데이터입니다. **multi-agent** 는 `souls/` 폴더를 추가하며, 각 소울은 **독립된 마음을 가진 캐릭터 agent** 입니다. 神楽島는 그 showcase: **일곱 소울**이 병렬로 생각하고, 꾸미고, 기억하며, world-agent가 이를 감쌉니다:

```
world-agent  →  active souls (이번 턴의 액터)  →  world-agent
  (주권적         각 소울: 발화 / 행동 /             (단일 세계 클로즈 경계,
   편성자)         내면의 목소리, 각자의 속셈으로)        당신에게 서술)
```

`playthrough.json` 이 매 턴 어떤 소울이 활성인지 선언합니다. 소울은 격리된 액터 —— 피어 메시가 아니라 world-agent가 **주도하는 액터 집합**으로, 세계 클로즈 경계는 하나뿐입니다. 섬은 기억하고, 루프는 돌고, 각 소울은 자신의 비밀을 안고 그것을 통과합니다.

```bash
neonrp web --project examples/multi-agent/kagura-island
```

## 일곱 소울

| Soul | id |
|---|---|
| **镜子** Kagami | `kagami-si-kagami001` |
| **羽** Hane | `hane-si-hane0001` |
| **真琴** Makoto | `makoto-si-makoto001` |
| **宫司** Miyaji | `miyaji-si-miyaji001` |
| **白** Shiro | `shiro-si-shiro0001` |
| **翼** Tsubasa | `tsubasa-si-tsubasa01` |
| **悠人** Yuto | `yuto-si-yuto0001` |

각 소울 폴더는 번들 구조를 따릅니다: `soul.json` / `soul.md`(정체성), `persona/`(특성·가치·관계), `background/`(역사·출신·비밀), `character/`(프로필·스탯·인벤토리), 기억(`long-term-memo/` + `short-term-memo/`), `rules/`(소울별 가드레일), `agents/`(소울의 마음), `trajectory/`(궤적).

## 세계

`agents/` = world-agent + 마을 / 전투 / 스토리 / world-builder / npc-builder / rules-referee. `game/` 이 섬의 진실을 보관(lore·장소·아이템·타임라인; GM 진실은 `game/lore/gm-truth.md` —— world-agent 전용). `runtime_contract.json` 은 라우터 셸을 유지하고, `playthrough.json + souls/` 가 있어 소울 래퍼가 작동합니다.

> 타임 루프 · 정신력 · 금기: 되돌릴 수 없는 결과, CoC 식. 플레이어는 **인간**이며, 이름을 가진 소울이 되지 않습니다.

## 라이선스

**AGPL-3.0** —— 포크, 수정, 자신의 세계 출시 가능. 엔진(`neonrp`)은 독점 프리뷰.
