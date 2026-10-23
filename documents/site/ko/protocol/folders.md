---
title: "폴더와 버전 관리"
description: "world(game/)·soul(soul/)의 디스크상 형태와, 세 가지 버전 축 —— 크리에이터·인스턴스·commit —— 의 관계. 하나의 폴더 레이아웃, 두 소비자: 엔진이 쓰고, 웹 렌더러가 걷는다."
---

<!-- section: shared-contract -->
## 공유 계약

이것은 **world**(`game/`)·**soul**(`soul/`)의 디스크상 형태와, 세 버전 축이 어떻게 연결되는지에 대한 정준 레퍼런스입니다.

설계 잠금된 SoulHub(M16)와 commit 버전화(M17)를 종합한 것;world 의 `game/` 쪽은 오늘 디스크에 이미 존재하는 것을 기술합니다. 하나의 폴더 레이아웃, 두 소비자: 엔진이 이 폴더들을 쓰고, 웹 렌더러가 그것들을 걷습니다.

<!-- section: world-folder -->
## world 폴더 —— game/

world 번들은 `game/` 디렉터리입니다. 크리에이터가 작성하고, world 작가가 버전 관리하며, WorldHub 를 통해 배포. 현재 실제 레이아웃:

```
game/
├── agents/                 # world 의 agent 로스터(크리에이터 버전 관리 템플릿)
│   ├── manifest.json       # 이 world 가 동봉하는 sub-agent(world-agent + domain agent)
│   └── contracts/          # agent 별 IO 계약
├── meta/
│   ├── run_state.json      # 라이브 위치 / 시간 / turn_count(playthrough 별)
│   ├── active-agent.json   # 현재 쓰기 락을 가진 sub-agent
│   ├── game-start.json     # 오프닝 / handoff
│   ├── flag_aliases.json   # story flag 의 읽기 좋은 이름
│   └── schedule.json       # 타이머 / 예약 세계 이벤트
├── lore/
│   ├── story.md            # 메인 스토리(append-only 내러티브)
│   └── notes.md            # 소문 / 세계 관찰
├── world/
│   ├── world_map.json      # 노드 그래프
│   ├── regions.json
│   └── factions.json
├── towns/<Txxx>/           # 마을 위치 노드
├── dungeons/<Dxxx>/        # 던전 위치 노드
├── rules/                  # 규칙 schema(주사위·판정·전투)
└── player/                 # 구 플레이어 상태 —— soul 로 마이그레이션
```

- `game/agents/manifest.json` 은 world 의 sub-agent 팀을 위한 **크리에이터 버전 관리 템플릿**. playthrough 생성 시 `playthrough.json` 으로 *seed* 됨;실행 중 엔진은 `playthrough.json` 을 읽고, 번들 manifest 를 직접 읽지 않음.
- `game/player/` 는 **구** 단일 플레이어 상태 모델. M16 에서 soul 폴더로 대체됨;기존 게임은 자동 마이그레이션.

<!-- section: soul-folder -->
## soul 폴더 —— soul/

soul 번들은 자기 완결형 캐릭터. 플레이어 아바타도 NPC 도 될 수 있음. SoulHub 를 통해 배포. 설계 잠금 형태(M16, 옵션 B —— NeonRP 네이티브, 레거시 비호환):

```
souls/<sid>-<instance_id>/
├── soul.json               # 머신용 아이덴티티 엔벨로프(NeonRP 고유)
├── soul.md                 # 런타임 대상 soul 차터(목소리 / 가치관 / 금기)
├── run_state.json          # 라이브 위치/상태(soul-orchestrator/action 가 씀)
├── agents/
│   ├── manifest.json       # soul 의 6-agent 로스터 + agent 별 write glob
│   └── contracts.md        # agent 별 입출력 schema
├── persona/                # 불변 심리 커널
│   └── core_traits.json  motivations.json  values.json  relationships.json
├── background/             # 불변 lore: origin.md  history.md  secrets.md
├── character/              # RPG 메커닉(soul-action 만)
│   └── stats.json  inventory.json  equipment.json  wallet.json  status.json  profile.json
├── rules/                  # 의사결정/행동 가드레일(읽기 전용)
├── short-term-memo/        # 세션 작업 기억
├── long-term-memo/         # 영속 기억(soul-memory 가 씀)
├── trajectory/             # append-only 자율 행동 로그
└── .commits/               # 이 soul 인스턴스 자신의 commit 체인(M17)
```

**`soul.json` —— 아이덴티티 엔벨로프:**

```json
{
  "schema_version": 1,
  "sid": "elena",
  "name": "Elena Voss",
  "name_local": "艾莲娜",
  "version": "1.0",
  "source": {"kind": "soulhub|builtin|local-create", "hash": "...", "version": "1.0"},
  "agent_template": "heroine-classic|minimal",
  "tags": ["companion", "mage"]
}
```

**`soul.md` —— 런타임 대상 soul 차터.** `soul.json` 과 나란한 일급 루트 파일. *이 soul 이 롤플레이에서 어떻게 느끼고 행동해야 하는지*를 한 파일의 자연어로 정리한 것: 1 인칭 정체성과 자기상, 목소리와 감정 톤, 가치관 / 금기 / 타협 불가 선, 이 soul 이 무엇을 알아채고, 숨기고, 추구하고, 회피하는 경향이 있는지. 구조화 파일을 보완하되 대체하지 않는다: `soul.json` = 머신 아이덴티티 / 버전 앵커 · `soul.md` = 런타임 대상 자연어 차터 · `persona/*.json` = 구조화 심리 커널 · `background/*.md` = 사실 lore. 더 넓은 「soul document」 패턴을 NeonRP 가 롤플레이용으로 적응한 것 —— 명시적으로 롤플레이 대상이며, 범용 어시스턴트 헌법이 아니다.

**Soul agent 로스터.** `soul/agents/manifest.json` 은 6 명의 전문가를 나열: `soul-orchestrator`(디스패처)+ `soul-mind`(인지)+ `soul-memory`(보존)+ `soul-action`(실행)+ `soul-dialogue`(발화)+ `soul-narrative`(스토리 인터페이스). 각자 `write_globs` 화이트리스트를 가짐;apply 파이프라인은 그 밖의 쓰기를 거부함.

**쓰기 권한 계약:**

| 경로 | 작성자 |
|---|---|
| `persona/` `background/` `rules/` | 없음(생성 후 불변) |
| `soul.md` | 없음(생성 후 불변) |
| `soul.json` | `soul-orchestrator` —— rename 시에만 |
| `character/` | `soul-action` |
| `short-term-memo/` | `soul-memory`、`soul-dialogue` |
| `long-term-memo/` | `soul-memory` |
| `trajectory/` | `soul-action`、`soul-orchestrator`(append-only) |
| `run_state.json` | `soul-orchestrator`、`soul-action` |
| `agents/manifest.json` | 절대 안 함(soul bundle 과 함께 버전 관리) |

**마이그레이션.** 기존 `~/.worldlines/players/` 프로파일은 M16 이후 첫 실행에서 `~/.worldlines/souls/` 로 자동 임포트: 최소 `soul.json` + persona 스텁이 합성되고, `game/player/*` 내용이 `soul/character/*` 로 매핑됨.

<!-- section: version-axes -->
## 버전 관리 —— 세 가지 아이덴티티 축

world 와 soul 은 하나의 모델을 공유. 세 직교 축(M17):

- **크리에이터 축 —— `slug + version_hash`.** 공개·작성된 버전. 불변. `wid`/`sid` + `version_hash`. WorldHub/SoulHub 레지스트리의 slug+version 마다 하나. *(M17 이전에 존재한 유일한 버전화.)*
- **인스턴스 축 —— `instance_id`.** 하나의 playthrough 로의 fork. soul 이 world 에 들어가면 fork 됨 → 자체 `instance_id`(fork 시 UUID)와 자체 독립적인 턴별 commit 체인을 가진 새 soul **인스턴스**. 플레이 중인 world 도 마찬가지로 인스턴스. 두 체인은 서로의 해시를 임베드하지 않음. `(wid|sid, instance_id)` 는 전역 고유 —— **아이덴티티에 타임스탬프 없음**.
- **commit 축 —— `commit_hash`.** 한 인스턴스의 턴별 상태 스냅샷. 콘텐츠 해시 → 해시가 아이덴티티이지 메타데이터가 아님. world 인스턴스와 soul 인스턴스는 각자 독자 commit DAG 를 가짐(분기 가능, v1 에서 머지 없음). commit 은 폴더 blob + 각 agent 의 대화 스냅샷 + `determinism` 블록(rng seed, rolls, llm-calls 해시)을 묶음 —— 완전·이식 가능·결정적 실행 컨텍스트.

**완전 주소 + 바인딩:**

| 자산 | 주소 |
|---|---|
| World | `(wid, instance_id, version_hash, commit_hash)` |
| Soul  | `(sid, instance_id, version_hash, commit_hash)` |

world↔soul 관계와 라이브 agent 팀은 세션 계층 playthrough manifest **에서만** 정준: `~/.worldlines/games/<wid>-<world_instance_id>/.neonrp/playthrough.json`. world 인스턴스 ref + `world_agent_team`(`game/agents/manifest.json@<version_hash>` 에서 seed)+ soul 인스턴스 목록을 가짐. world commit 은 추가로 *읽기 전용* `soul_scene_index` 를 가짐;soul 은 world 를 역참조하지 않음.

**타임스탬프 규칙.** 타임스탬프는 결코 아이덴티티의 일부가 아님. `instance_id` 가 고유;`commit_hash` 가 상태를 고정. `archived_at` 은 commit 이 업로드/익스포트용으로 패키징될 때만 나타남 —— 정렬용 사람 대상 라벨이지, 절대 key 가 아님. **해시가 위치를 정하고, 타임스탬프는 라벨만.**

<!-- section: on-disk-map -->
## 디스크상 맵

```
~/.worldlines/
├── games/<wid>-<world_instance_id>/
│   ├── .neonrp/
│   │   ├── playthrough.json     # 바인딩
│   │   ├── HEAD                 # 현재 world commit_id
│   │   └── sessions/<branch>.jsonl
│   ├── game/                    # world 작업 트리
│   └── souls/<sid>-<soul_instance_id>/   # soul 작업 트리
├── souls/<sid>-<ts>/            # 다운로드/생성한 soul 라이브러리(fork 전)
│   └── .commits/<soul_commit_id>.json + blobs/
└── commits/
    ├── worlds/<world_commit_id>.json
    ├── refs/<wid>/{HEAD,branches/*,tags/*}
    └── blobs/<hash>.{tar,jsonl}.zst
```

<!-- section: sandbox-replay -->
## sandbox / replay 와의 관계

이 모델은 M4 sandbox/replay 설계의 **슈퍼셋**: `sandbox` = commit 을 브랜치로 fork;`save` = 퇴화된 단일 agent commit;`replay verify` = 머신 간 commit 해시 비교. 엔진의 안정 tree-hash 가 폴더 해싱에 그대로 재사용됨. M4 의 예약된 seed/rolls 인터페이스는 commit `determinism` 블록으로 채워짐.

함께 보기: [World 프로토콜](/docs/protocol/world) · [Soul 프로토콜](/docs/protocol/soul) · [Agent 프로토콜](/docs/protocol/agent).
