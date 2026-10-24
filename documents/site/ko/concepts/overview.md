---
title: "세 층: 엔진 · 템플릿 팩 · 제품"
description: "WorldLines — Make you play with your AI character in an infinite world. 누구나 이 페이지를 먼저 읽습니다."
---

<!-- section: what -->
## WorldLines란

**WorldLines — Make you play with your AI character in an infinite world.**

당신은 주인공을 연기하며, 스스로 계속 움직이는 세계에서 AI 캐릭터와 함께 삽니다. 캐릭터(soul)는 자기 에이전트를 가지고 스스로 판단하고 말합니다. 세계 NPC는 세계가 대신 말하고 규칙대로 움직입니다. 지도에는 새 장소가 생기고, 경제와 세력은 스스로 돌아갑니다. 당신이 하는 모든 말과 캐릭터가 내리는 모든 결정은 **제안**일 뿐입니다. 세계(world agent)가 검증한 뒤에야 세계가 바뀝니다.

<!-- section: layers -->
## 서로 독립된 세 층

| 층 | 무엇인가 | 누가 쓰나 |
|---|---|---|
| **NeonRP 엔진**(`neonrp` 패키지) | 열린 스키마 / 닫힌 스키마 상태 로직, 제안 → 검증 → 적용, 이벤트와 구독, 커밋과 분기만 있습니다. **게임플레이는 전혀 없습니다.** | SDK 개발자 |
| **템플릿 팩** | 한 종류의 플레이를 엔진에 등록합니다. 클래스, 변수, ops, 트리거, 메커닉 이음새, 프롬프트. 내장: `rpg`(d20 + 능력치 보정, 자체 규칙. 판정과 쓰러짐 규칙은 SRD 5.2, CC BY 4.0 사용 가능), `pct`(백분위 주사위, BRP — Chaosium의 *Basic Roleplaying*, ORC License: d100 기술, 이성, 빈사 판정. rpg 위에 만들어졌으며 이 종류의 플레이를 「샌드박스 테이블탑」이라 부릅니다), `werewolf`와 `monopoly` | 크리에이터 / 개발자 |
| **WorldLines 제품**(`worldlines` 패키지) | 플레이 UI, 창작 워크벤치, 조립, Lint, 내보내기 / 가져오기, Hub 공개. `neonrp` 엔진에 의존하며 공개 인터페이스만 호출합니다 | 플레이어 / 크리에이터 |

따라서 **플레이어는 `worldlines`를 설치합니다**(엔진이 함께 옵니다). **개발자는 `neonrp`만 설치해** 자기 프로그램이나 Godot에 엔진을 넣을 수 있습니다.

**설치 방법 두 가지, 턴 종류 두 가지.** PyPI의 `worldlines` / `neonrp` 패키지에는 두 박자 편성(먼저 상의, 다음에 해결)이 모두 들어 있습니다. 오픈소스 저장소에서 빌드하면 오픈 엔진을 얻으며, 한 박자 턴(해결만)으로 돌아갑니다. 같은 템플릿이 둘 다에서 플레이됩니다. 템플릿이 두 박자를 요구하는데 엔진에 없으면 한 박자로 돌아갑니다. [한 턴의 흐름](/docs/concepts/turn-flow)을 참고하세요.

<!-- section: readers -->
## 누구인지에 따라 읽기

| 당신은 | 여기서 시작 |
|---|---|
| 플레이어 | [플레이어 빠른 시작](/docs/players/quickstart) |
| 크리에이터 | [크리에이터 빠른 시작](/docs/creators/quickstart) |
| SDK / 무거운 프런트엔드 개발자 | [개발자 빠른 시작](/docs/developers/quickstart) · [실시간 이벤트 스트림](/docs/developers/events) |
| 누군가를 대신해 일하는 에이전트(Claude Code, Codex, WorldLines 창작 에이전트) | [에이전트를 위해](/docs/agents/overview) |

읽어 둘 만한 짧은 개념 페이지가 네 개 더 있습니다. [열린 / 닫힌 스키마](/docs/concepts/schema) · [제안 → 검증 → 적용](/docs/concepts/ops) · [캐릭터와 NPC](/docs/concepts/souls) · [세계선](/docs/concepts/worldlines).

<!-- section: map -->
## 1.0에 있는 것

| 항목 | 무엇인가 | 읽기 |
|---|---|---|
| 세계 | 폴더 하나: 장소 트리, NPC, 아이템, 오프닝 | 템플릿 폴더의 `spec/world.md` |
| 캐릭터 | 라이브러리에 살고, 템플릿에는 링크만 두며, 판을 시작할 때 실체화 | [캐릭터와 캐스팅](/docs/creators/characters) · [나의 캐릭터](/docs/players/your-character) |
| 템플릿 | 세계 + 캐릭터 링크 + 규칙 팩 + 계약 + 편성: 플레이, 내보내기, 공개의 단위 | [템플릿 파일](/docs/creators/template-card) · [워크벤치](/docs/creators/workbench) |
| 플레이 계약 | 한 종류의 게임이 약속하는 경험. lint가 이에 맞춰 검사하고, 판은 이에 따라 정산 | [플레이 계약](/docs/creators/contracts) |
| 편성 | 턴이 진행되는 방식. 템플릿이 `uses`에서 지정(두 박자 `two_beat` / 한 박자 `one_beat`). 로컬 편성 벤치에서 그래프 편집 가능 | [워크벤치](/docs/creators/workbench) · [상의와 해결](/docs/concepts/planning-resolve) |
| 한 턴 | 두 박자: 상의(세계는 그대로) → 해결(먼저 서술, 다음에 상태). 오픈소스판은 해결 박자만 | [한 턴의 흐름](/docs/concepts/turn-flow) · [실시간 이벤트 스트림](/docs/developers/events) |

<!-- section: stoneford -->
## 문서 전체의 예시: 스톤포드

모든 예시는 내장 템플릿 **스톤포드 · 안개가 물러나는 밤**(`stoneford-town`)을 씁니다. 일 년에 하룻밤, 안개가 북쪽 길에서 물러납니다. 정찰대는 돌아오지 않았고, 산적 **외눈 호랑이**가 역로를 쥐고 있으며, 당신에게는 북문으로 떠나는 데 필요한 것을 모을 두 밤과 하루가 있습니다. 치유사 **엘레나**와 **로완**은 자기 에이전트를 가진 캐릭터입니다. 문지기 캐스, 길드의 헤론, 여관의 미라는 세계 NPC입니다. 다른 내장 템플릿은 **그레이오크 저택 · 닫힌 문**(`pct-house`)으로, 백분위 주사위를 쓰는 샌드박스 테이블탑입니다.

<!-- section: license -->
## 라이선스

1.0부터 NeonRP 엔진은 **Apache-2.0**으로 오픈소스입니다. WorldLines 제품(`worldlines`, UI와 내장 샘플 템플릿)은 **AGPL-3.0**으로 배포됩니다. PyPI 패키지의 두 박자 편성은 오픈소스 저장소에 없으며 오픈소스가 아닙니다.

템플릿과 예시 세계의 **콘텐츠**에는 별도의 라이선스가 있습니다(엔진 패키지의 `CONTENT-LICENSE.md` 참고). 설정 텍스트(세계와 캐릭터 설정, 장소, 규칙 표)는 **CC BY 4.0**입니다. 리믹스와 상업적 이용이 가능하며 출처만 밝히면 됩니다. 이미지와 오디오(스탠딩 일러스트, 표지, 배경, 소리)는 **CC BY-NC 4.0**입니다. 출처를 밝히면 리믹스할 수 있지만 상업적 이용은 할 수 없습니다. 사용한 오픈 규칙은 각자의 라이선스를 유지합니다. SRD 5.2는 CC BY 4.0, BRP는 ORC License입니다.
