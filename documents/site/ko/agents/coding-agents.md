---
title: "Codex / Claude Code로 창작하기"
description: "world-creation 스킬을 설치하고 세계 설정서를 coding agent에게 넘긴다. agent가 규격대로 파일을 쓰고, 당신은 로컬 웹 워크벤치에서 진행 상황을 본다. lint block이 0이면 플레이할 수 있고 공개할 수 있다."
---

<!-- section: what -->
## 이 페이지에서 다루는 것

Claude Code나 Codex 같은 coding agent로 터미널에서 세계를 만든다. 당신이 설정서를 쓰면 agent가 그것을 템플릿 폴더로 만든다. 결과 확인과 이미지 추가는 로컬 웹 워크벤치에서 한다.

먼저 네 가지를 설명한다. WorldLines가 세계를 어떻게 보는지, 한 판이 어떻게 진행되는지, agent가 무엇을 고치는지, 엔진이 돌아가는 것을 어떻게 확인하는지. 그다음에 단계별 실습.

<!-- section: ideas -->
## 네 가지 기본 생각

| 생각 | 뜻 | agent에게는 |
|---|---|---|
| **세 주체** | 세계, 캐릭터, 플레이어는 각자 주체이고 서로 분리된다. 플레이어의 말은 "시도"이고 결과는 세계가 정한다. 캐릭터의 생각은 캐릭터가 스스로 정한다 | 캐릭터의 결말을 파일에 써 두지 않는다. 캐릭터의 일기와 상태를 미리 채우지 않는다 |
| **파일 시스템이 곧 인터페이스** | 세계, 캐릭터, 템플릿은 모두 폴더다. 폴더가 유일한 진실이고, 웹 화면과 TUI는 그것을 그릴 뿐이다 | 파일을 고치면 충분하다. 웹에 보이는 것이 곧 디스크의 파일이다 |
| **효과는 엔진, 커스터마이즈는 제어만** | 강도가 포위되거나 아무거나 먹고 탈이 나는 효과는 엔진의 메커니즘이 만들고, 설정 없이도 성립한다. 창작자의 표와 규칙은 결과를 **바꾸는** 데만 쓴다 | 엔진에게 연기 방법을 "가르치는" 긴 프롬프트를 쓰지 않는다. 데이터를 쓴다: 가격, 거리, 누가 어디 있는지, 무엇에 동의하는지 |
| **템플릿 = 세계 + 캐릭터 + 룰 팩 + 계약** | 템플릿은 하나의 세계, 캐스트, 룰 팩(`rpg` / `pct` / `werewolf` / `monopoly`), 플레이 계약을 묶고 오케스트레이션을 하나 고른다. 플레이되고, 내보내지고, 공개되는 단위다 | agent의 산출물은 `<id>.template/` 폴더 하나 |

캐릭터는 캐릭터 라이브러리에 살고, 템플릿에는 링크만 둔다. 지명, 상태 이름, 세력 이름은 템플릿의 데이터에만 쓰고 엔진 코드에는 쓰지 않는다.

<!-- section: orchestration -->
## 오케스트레이션: 한 판이 진행되는 방식

오케스트레이션은 상태 기계 그래프다. 노드는 "이 비트에서 무엇을 하는가", 엣지는 "언제 다음 노드로 넘어가는가"다. 템플릿은 `template.json`의 `uses`에서 오케스트레이션 템플릿을 지정한다. 룰 팩도 계약도 담지 않으므로 여러 세계가 함께 쓸 수 있다.

| 오케스트레이션 | 한 턴 |
|---|---|
| `one_beat` | 정산 비트만: 세계가 서술을 쓰고, 그 자리의 캐릭터가 각자 행동하고, 엔진이 상태를 쓰고 검증하고 확정한다 |
| `two_beat` | 상의 비트 다음에 정산 비트. 상의 비트에서 호스트가 그 자리의 캐릭터에게 말을 넘기고 비용, 판정, 시간을 늘어놓는다. 세계는 움직이지 않는다. 합의되면 정산 비트로 |

PyPI의 `worldlines` / `neonrp`에는 두 비트가 들어 있다. 오픈소스 저장소에서 소스로 설치한 엔진은 한 비트뿐이다. 템플릿이 지정한 오케스트레이션이 엔진에 없으면 한 비트로 돌아가고, 세계는 그대로 플레이할 수 있다.

템플릿이 쓰는 그래프 보기:

```bash
neonrp engine graph --template <템플릿 폴더>
```

그래프 편집(엣지 추가, 조건 변경)은 로컬 오케스트레이션 화면에서 하고, 기본 그래프에 대한 패치로 템플릿에 저장된다. agent가 그래프를 손으로 쓸 필요는 없다.

<!-- section: ops -->
## 도구 호출: agent는 파일을 고치고, 엔진은 op를 실행한다

두 가지는 별개다:

- **창작할 때** agent가 고치는 것은 파일이다: `template.json`, `world/` 아래의 지도와 데이터, 캐릭터 폴더, 플롯 팩.
- **플레이할 때** 세계는 매 비트 변화를 "제안"할 수 있을 뿐이고, 그 형태가 op(이동, 변수 변경, 인스턴스 생성……)다. 엔진이 검증한 뒤에 확정한다. op는 룰 팩이 등록한다.

서술 안의 도구는 괄호로 쓴다. 모양이 기다릴지 말지를 나타낸다:

| 표기 | 뜻 |
|---|---|
| `[op 인자]` | 동기 도구: 여기서 멈추고, 엔진의 답을 받은 뒤 이어서 쓴다. 예: `[dice 1d20+2 vs 12]` · `[ask 엘레나]` · `[player.gold -12]` |
| `[~op 인자]` | 기다리지 않는 도구: 엔진이 실행하고 서술은 그대로 이어진다. 예: `[~map]` |
| `<…>` | 엔진이 모델에게 보내는 메시지. 모델은 쓰지 않는다 |

그래서 agent는 파일에 op를 쓰지 않고, 실행 상태를 꾸며 넣지도 않는다. 쓰는 것은 op가 읽는 데이터다: 변수의 범위, 장소 사이의 연결, 가격표, 플롯 트리거의 조건. 자세한 내용은 [Propose → verify → apply](/docs/concepts/ops)와 [How a turn runs](/docs/concepts/turn-flow).

<!-- section: install -->
## 스킬 설치

스킬은 오픈소스 저장소 [WorldLines](https://github.com/LudicDynamics/WorldLines)의 루트에 있다:

| agent | 위치 | 안내 파일 |
|---|---|---|
| Claude Code | `.claude/skills/world-creation/`(이 저장소 안에서만) 또는 `~/.claude/skills/world-creation/`(어느 폴더에서나) | `CLAUDE.md` |
| Codex | `.agents/skills/world-creation/` | `AGENTS.md` |

가장 간단한 방법: 저장소를 clone하고 루트에서 Claude Code나 Codex를 연다. 루트의 `CLAUDE.md` / `AGENTS.md`에 이 스킬이 이미 적혀 있다.

자신의 템플릿 라이브러리에서 바로 쓰려면 `.claude/skills/world-creation/`을 `~/.claude/skills/`에 복사한다.

엔진:

```bash
uv tool install worldlines      # worldlines와 neonrp가 함께 설치된다
```

<!-- section: flow -->
## 실습

**1. 설정서를 쓴다.** 스킬의 `references/world-spec-template.md`에 맞춰 채운다: id, 언어, 룰 팩, 계약, 장소, 인물, 오프닝, 플롯과 엔딩, 세계 데이터. 내용은 목표 언어로 바로 쓰고, id는 ASCII. 예시: `examples/tidepool/world-spec.md`.

**2. agent에게 넘긴다.** "이 설정서로 템플릿을 만들어 줘." agent는 이렇게 실행한다:

```bash
neonrp template new tidepool --title "조수 웅덩이 마을" --lang ko --pack rpg --contract open-adventure@1 --store ~/.worldlines/templates
```

내장 템플릿과 비슷하면 `neonrp template fork pct-house <id>`나 `fork stoneford-town <id>`를 쓴다. 설정서는 템플릿 폴더에 복사해 작업의 원본으로 둔다.

**3. 로컬 웹 워크벤치를 연다.**

```bash
worldlines --no-browser         # http://127.0.0.1:8787. 포트가 사용 중이면 --port를 붙인다
```

| 주소 | 보는 것 |
|---|---|
| `/local?screen=tpl&edit=<id>` | Template: 카드, 계약, Lint, 소재 슬롯(여기서 이미지를 업로드하거나 생성) |
| `/local?screen=duo&edit=<id>` | 세계 · 캐릭터: 지도, 플롯, 스키마, 데이터 |

화면은 디스크의 파일을 읽는다. agent가 한 단계를 쓸 때마다 새로고침하면 보인다.

![Template 화면: 계약, Lint, 소재 슬롯](../../images/coding-agents/template.jpg)

![세계 · 캐릭터 화면: 폴더로 그린 지도](../../images/coding-agents/world.jpg)

**4. agent는 단계별로 쓴다.** 카드와 모드 → 지도 → 전승과 데이터 → 인물 → 오프닝 → 플롯과 엔딩 → 이미지 프롬프트. 단계마다 lint를 돌리고 무엇을 바꿨는지 알려 준다. 이미지는 Template 화면에서 당신이 업로드하거나 생성한다.

**5. 시험 플레이.** 설정한 모델을 쓴다. 웹: Template 화면의 "테스트 벤치에서 실행 →". 터미널: `neonrp`를 실행하고 런처에서 이 템플릿을 고른다.

<!-- section: lint -->
## lint로 엔진이 돌아가게 한다

lint는 먼저 템플릿을 한 판으로 조립한 뒤 참조, 소재, 프롬프트, 플롯, 계약, 언어를 검사한다. 각 항목은 **block**(공개를 막음) 또는 **warn**(알림만).

```bash
neonrp template lint <템플릿 폴더>      # 마지막 줄: publishable / NOT publishable
(cd <템플릿 폴더>/world && neonrp validate)
neonrp template build <템플릿 폴더> /tmp/try-<id>
```

agent의 규칙: **block이 0이 될 때까지 고친다.** block의 원문과 고친 방법은 작가에게 알린다. warn도 하나씩 읽고 고칠 수 있는 것은 고친다.

공개할 때 확인이 한 번 더 있다. Template 화면에서 공개를 누르면 엔진이 먼저 다섯 가지를 확인하고, 하나라도 통과하지 못하면 아무것도 보내지 않는다:

| 확인 | 통과하지 못할 때 |
|---|---|
| 링크한 캐릭터가 로컬 라이브러리에 있다 | `{"lib": …}`가 가리키는 캐릭터가 없다 |
| 비밀 정보가 없다 | 파일에 API 키처럼 보이는 문자열이 있다 |
| Lint에 block이 없다 | 꼭 고쳐야 할 문제가 남아 있다 |
| 4개 언어 카드 | 중 / 영 / 일 / 한 중 하나에 제목이나 소개가 없다 |
| 커버 | `card.cover`가 템플릿 안의 이미지를 가리키지 않는다 |

플랫폼은 받은 뒤 자체 자동 검사를 한 번 더 한다. 자세한 내용은 [Lint](/docs/creators/lint)와 [Publish to the Hub](/docs/creators/publish). 공개 버튼은 작가가 누른다.

<!-- section: skill -->
## 스킬 위치

| 파일 | 내용 |
|---|---|
| `.claude/skills/world-creation/SKILL.md` | 단계: 준비 → 설정서 읽기 → 템플릿 만들기 → 웹 열기 → 단계별로 쓰기 → 모델 없이 하는 검사 → 시험 플레이 → 넘겨주기 |
| `.claude/skills/world-creation/references/world-spec-template.md` | 설정서 양식과 네 가지 계약 요약 |
| `.claude/skills/world-creation/references/spec-to-files.md` | 설정서의 각 부분이 어떤 파일이 되는지(실측 예시 포함) |
| `.claude/skills/world-creation/examples/tidepool/world-spec.md` | 작은 설정서의 완전한 예 |

Codex용 같은 파일은 `.agents/skills/world-creation/`에 있다. 각 템플릿 폴더에도 `AGENTS.md`와 `spec/`이 있고, agent는 고치기 전에 그것을 읽는다. [For agents](/docs/agents/overview) 참고.

엔진 패키지에도 같은 사본이 들어 있다: `neonrp spec skill`은 내 컴퓨터의 폴더를, `neonrp spec skill world-creation`은 `SKILL.md`를 출력한다. 엔진은 어떤 agent에도 설치하지 않는다. 쓰려면 위 "스킬 설치"처럼 agent의 skills 폴더에 둔다.
