---
title: "하나의 템플릿, 여러 프런트엔드"
description: "웹, Godot, TypeScript 프런트엔드가 같은 템플릿과 같은 판을 어떻게 읽는지, 내 프런트엔드에 필요한 인터페이스와 이벤트."
---

<!-- section: picture -->
## 전체 모습

```text
템플릿(template.json · world/ · souls · plots/ · 그림)
   │  판 시작: 템플릿으로 판을 조립
   ▼
엔진 프로세스 — 이 판의 유일한 진실
   │  POST /rpc · GET /rpc/events · HTTP 읽기
   ├── 표준 웹 프런트엔드(Hub와 iOS에서 플레이어가 보는 화면, 오픈 소스 아님)
   ├── Godot 예제   worldlines/examples/clients/godot
   ├── TS 예제      worldlines/examples/clients/ts
   └── 내 프런트엔드
```

프런트엔드는 월드를 바꾸지 않습니다. 한마디나 행동을 보내면 엔진이 판정하고 확정한 뒤, 서술, 박자 이벤트, 상태를 돌려보냅니다. 화면에 나오는 것은 모두 엔진 데이터와 템플릿 그림에서 옵니다.

그래서 템플릿은 프런트엔드마다 따로 쓰지 않습니다. 프런트엔드가 아는 것은 인터페이스이지 특정 월드가 아닙니다.

<!-- section: host -->
## 어느 엔진에 연결할까

| 엔진 | 시작 방법 | 토큰 |
|---|---|---|
| 로컬 워크벤치 | `worldlines`(기본 `http://127.0.0.1:8787`) | 워크벤치 "프런트엔드" 페이지의 "토큰 복사". 또는 `curl -s http://127.0.0.1:8787/api/v1/local/frontends/_/connect`(로컬 요청에만 응답) |
| 월드 폴더 하나 | `neonrp serve --project <폴더> --port 8788` | 시작할 때 `{"url", "token", "protocol"}` 출력 |

프런트엔드를 만들 때는 로컬 워크벤치에 연결하는 편이 쉽습니다. 테스트 벤치와 프런트엔드가 같은 판을 공유하므로, 한쪽에서 디버그하고 한쪽에서 화면을 볼 수 있습니다. 워크벤치 없이 월드 하나만 돌릴 때는 `neonrp serve`를 씁니다(영어판: [Protocol](/docs/developers/protocol)).

<!-- section: five -->
## 프런트엔드가 읽는 여섯 가지

| 무엇 | 어디서 |
|---|---|
| 연결 | `POST /rpc`로 `session.hello {protocol: "worldlines.net/1"}`. 모든 요청에 `Authorization: Bearer <토큰>` |
| 박자 모양 | `GET /api/v1/play/engine/beat-kinds`: 박자마다 이름, 톤, 입력 힌트, 추천, 구분선 |
| 서술과 박자 이벤트 | `GET /rpc/events`(SSE): `engine/stream`은 쓰이는 중인 서술, `engine/beat`는 박자 이벤트, `engine/event`는 턴 시작 / 끝 |
| 상태 | `GET /state`(누가 어디에) · `GET /api/v1/play/schema`(변수) · `GET /api/v1/play/engine/entities?cls=<클래스>` · `GET /api/v1/play/engine/views` · `GET /api/v1/play/engine/settlement` |
| 그림 | 이 판의 그림은 주소로(`/api/v1/play/place-image?addr=` 등), CG·엔딩 등은 슬롯 id로 가리킴(아래 "그림") |
| 타입 | `neonrp template contract <id> --ts` / `--gd`: 변수, 클래스, ops, 이벤트, 슬롯의 타입(영어판: [Interface contract](/docs/developers/contract)) |

한마디는 `turn.send {text}`로 보냅니다. 턴이 끝나면 돌아오고, 그동안 서술은 `/rpc/events`로 옵니다. 멈출 때는 `turn.cancel`. 호스트가 물으면(`ask_user`) `reply {id, result}`로 답합니다.

프런트엔드는 특정 박자를 모릅니다. 오픈 소스 엔진은 턴마다 정산 박자 하나, PyPI 버전은 상의 박자와 정산 박자입니다. 이름과 모양이 `beat-kinds`에서 오므로 같은 코드로 둘 다 처리합니다.

<!-- section: events -->
## 박자 이벤트와 화면

| 이벤트 | 프런트엔드가 할 수 있는 일 |
|---|---|
| `node.enter` / `node.leave` | 박자 모양 바꾸기(이름과 톤은 `beat-kinds`) |
| `plan.beat` / `resolve.beat` | 서술 한 단락 확정, `options`를 버튼으로 |
| `dice` | 화면에서 주사위 굴리기: `total` · `vs` · `level` |
| `state.changed` | 수치 갱신. `applied`의 각 항목은 `{var, from, to}`, `refused`는 반영되지 않은 변화 |
| `place.discovered` | 지도에 새 장소 표시: `addr` · `name` |
| `party.join` / `party.leave` | 동료 합류 / 이탈 |
| `stage.changed` | 플롯 단계 진행. `cg`가 있으면 한 장 그림 연출 |
| `show` | 템플릿 그림을 지금 보이기: `slot`은 슬롯 id |
| `audio.cue` | 음악 / 환경음 바꾸기 |
| `run.settled` | 출구 도달: `GET /api/v1/play/engine/settlement`로 엔딩 읽기 |

모든 필드: 영어판 [Live event stream](/docs/developers/events). 연결이 끊긴 뒤에는 `GET /rpc/events?since=<seq>`로 놓친 것을 다시 받습니다.

<!-- section: slots -->
## 그림: 이 판의 그림을 주소로

이 판의 그림은 주소로 받습니다.

```text
GET /api/v1/play/place-image?addr=T001/hall      장소 배경. 주소는 /state의 player_location
GET /api/v1/play/portrait?id=chara               캐릭터 초상. id=player는 플레이어
GET /api/v1/play/sprite?id=chara                 투명 배경 스탠딩
GET /api/v1/play/map/image?level=T001            레벨 지도. 장소와 길은 GET /api/v1/play/map
```

그림이 없으면 404를 돌려주니 자리 표시를 그립니다. 이 그림들은 판을 시작할 때 템플릿에서 복사됩니다. 템플릿 그림을 바꾸면 새로 시작한 판부터 반영됩니다.

템플릿의 모든 그림에는 슬롯 id가 있습니다. CG, 엔딩, 커버, 아이템 아이콘은 주소로 받는 경로가 없습니다. 엔진은 슬롯 id로 가리킵니다.

| 슬롯 id | 내용 |
|---|---|
| `card:cover` | 템플릿 커버 |
| `level.map:<레벨>` | 레벨 지도. 예 `level.map:T001` |
| `place.scene:<주소>` | 장소 배경. 예 `place.scene:T001/hall` |
| `soul.portrait:<캐릭터>` · `soul.sprite:<캐릭터>` | 초상 · 투명 배경 스탠딩 |
| `item.icon:<id>` | 아이템 아이콘 |
| `player.portrait:player` | 플레이어 그림 |
| `opening.cg:<n>` · `stage.cg:<플롯>.<n>` | 오프닝 CG · 플롯 단계 CG |
| `plot:<플롯 폴더>:ending:<엔딩>` | 엔딩 그림 |

박자 이벤트 `show`의 `slot`과 `stage.changed`의 `cg.slot`이 슬롯 id입니다. 엔딩은 `GET /api/v1/play/engine/settlement`의 `exit`에 있습니다. 두 예제는 이 그림들을 자체 아트 팩(`art.json`, 엔딩 id와 장소 주소로 대응)에 두고, 이벤트가 오면 거기서 꺼냅니다. 슬롯 종류(비율, 필수 여부)는 `neonrp template contract <id>`의 `slots`에 있습니다. 어느 슬롯이 채워졌는지는: `neonrp template slots <id>`.

<!-- section: switch -->
## 판이 바뀔 때

로컬 워크벤치에서 테스트 벤치가 다른 판을 열거나 플레이 목록에서 새로 시작하면, 엔진은 새 판으로 옮겨 갑니다.

- `/rpc/events`는 연결된 채로 있고, 그 뒤의 이벤트는 새 판의 것입니다;
- `GET /events`가 `rebound`를 한 번 보냅니다;
- 이를 받으면 템플릿 id, `beat-kinds`, 그림을 다시 읽고 다시 그립니다.

테스트 벤치의 표준 웹 프런트엔드는 판이 바뀌면 페이지 전체를 다시 불러와 그림도 새 템플릿 것으로 바뀝니다. 두 예제는 연결할 때 한 번만 읽으므로, 판이 바뀌면 다시 연결합니다(TS는 페이지 새로 고침, Godot는 게임 재시작).

<!-- section: three -->
## 프런트엔드별로 읽는 것

| | 표준 웹 프런트엔드 | Godot 예제 | TS 예제 |
|---|---|---|---|
| 위치 | Hub, iOS | 오픈 소스 저장소 `worldlines/examples/clients/godot` | 오픈 소스 저장소 `worldlines/examples/clients/ts` |
| 프로토콜 | 같은 인터페이스 | `addons/worldlines/client.gd`(노드 하나) | `src/client.ts`(파일 하나) |
| 박자 모양 | `beat-kinds` | `beat-kinds` | `beat-kinds` |
| 그림 | 템플릿 슬롯 | 자체 아트 팩 `art.json`, 그리지 않은 그림은 자리 표시 | Godot와 같은 아트 팩 |

표준 웹 프런트엔드는 오픈 소스가 아닙니다. 이 페이지의 인터페이스는 그것이 쓰는 것과 같습니다. PyPI 버전의 테스트 벤치에는 오른쪽 열에 "표준 프런트엔드" 탭이 있어, 같은 판을 나란히 볼 수 있습니다.

두 예제를 돌리고 고치는 법: [Godot와 TS 프런트엔드](/docs/tutorials/frontend-examples).

<!-- section: own -->
## 프런트엔드를 템플릿에 넣기

월드는 자기 프런트엔드를 가질 수 있습니다: `<템플릿>/frontends/<이름>/frontend.json`.

```json
{"schema": "worldlines.frontend/1", "kind": "web-ts", "title": "My front end", "entry": "index.html",
 "events": ["node.enter", "resolve.beat", "dice", "state.changed", "run.settled"], "targets": ["local"]}
```

| 필드 | 뜻 |
|---|---|
| `kind` | `web-ts` · `godot` · `chat` |
| `entry` | 시작 파일. 예 `index.html` / `project.godot` |
| `events` | 쓰는 이벤트. 엔진이 알려진 이벤트와 대조합니다 |
| `targets` | 지금은 `local`만 |

워크벤치 "프런트엔드" 페이지에서 "+ 새로 만들기", 또는 내장 프런트엔드의 "이 월드로 복사". 내장 템플릿은 먼저 내 것으로 복사합니다. `frontends/`는 내 컴퓨터에만 남고 내보내지 않습니다.
