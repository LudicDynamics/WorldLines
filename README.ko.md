# WorldLines

**언어:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> **WorldLines —— 당신과 당신의 캐릭터 에이전트를 위해 만든 멀티에이전트 세계 시뮬레이션 엔진.**
> 오픈 소스: **NeonRP** 엔진(Apache-2.0), **WorldLines** 제품(AGPL-3.0), 문서와 벤치마크(CC BY 4.0).

<p align="center">
  <img alt="GitHub Stars" src="https://img.shields.io/github/stars/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Forks" src="https://img.shields.io/github/forks/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Issues" src="https://img.shields.io/github/issues/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <a href="https://worldlines.gg"><img alt="Live" src="https://img.shields.io/badge/Live-worldlines.gg-8b5cf6?style=flat-square" /></a>
  <img alt="LINUX DO" src="https://img.shields.io/badge/LINUX%20DO-WorldLines-8b5cf6?style=flat-square" />
  <a href="https://doi.org/10.1145/3800965.3834285"><img alt="Paper" src="https://img.shields.io/badge/Paper-CHI%20PLAY%20Companion%20%2726-b31b1b?style=flat-square" /></a>
  <a href="https://arxiv.org/abs/2606.16014"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2606.16014-8b5cf6?style=flat-square" /></a>
  <img alt="Engine license" src="https://img.shields.io/badge/neonrp-Apache--2.0-blue?style=flat-square" />
  <img alt="Product license" src="https://img.shields.io/badge/worldlines-AGPL--3.0-blue?style=flat-square" />
</p>

<p align="center">
  <img src="./worldlines/assets/hero.png" alt="WorldLines — 살아 있는 세계로 가는 문" width="640" />
</p>

## WorldLines는

대부분의 AI 롤플레이는 대화할 캐릭터 하나를 건네줍니다. WorldLines가 건네주는 것은 **그 캐릭터가 살아가는 세계**입니다.
장소가 있고, 물가가 있고, 세력이 있고, 저마다 생각을 가진 다른 캐릭터들이 있으며, 무너지지 않는 규칙이 있습니다.
그저 이야기만 나누는 게 아닙니다. 어딘가로 떠나고, 거래를 맺고, 싸움을 걸면 세계는 오래 남는 결과로 응답합니다.

우리는 이렇게 믿습니다. 게임의 시대에는 코드로 시뮬레이터를 썼고, 에이전트의 시대에는 에이전트로 시뮬레이터를 편성합니다. 그리고 TRPG야말로 가장 좋은 세계 시뮬레이터입니다. 당신은 AI 캐릭터와 함께 이 TRPG 세계 시뮬레이터 안에서 마음껏 플레이할 수 있습니다.

**TRPG × AIRP: 테이블탑 롤플레이는 그 자체로 하나의 세계 시뮬레이션입니다. 그것이 우리의 핵심입니다.**

그 밑에서 돌아가는 것이 **NeonRP**, 하나의 생각에서 출발한 세계 시뮬레이션 엔진입니다 —
*이야기는 모델이 들려주고, 규칙은 세계가 지킨다.*

- **먼저 상의, 다음에 해결.** 하고 싶은 일을 말하면 됩니다. 상의 박자에서는 그 자리의 캐릭터들이 대답하고 어떻게 할지
  이야기합니다. 판정자가 정리됐다고 보면(또는 당신이 「결정」/ `@dm`이라고 하면) 해결 박자에서 굴려야 할 주사위를 굴리고,
  이야기를 쓰고, 검증을 거친 변경 하나를 세계에 반영합니다.
- **세 주체.** 세계, 당신, 그리고 각 캐릭터가 저마다의 주체성을 가집니다. 당신의 말은 사실이 아니라 *시도*이며,
  캐릭터는 스스로 결정합니다.
- **세계는 파일이다.** 읽고, diff를 보고, 버전 관리할 수 있는 평범한 JSON / Markdown입니다. 턴마다 커밋이 하나씩
  쌓이고, 언제든 되돌리거나 거기서 갈라져 나갈 수 있습니다.

## 팀 & 비전

우리는 **도쿄대학**의 PhD 및 연구자, 그리고 게임 실무자로 구성된 학제적 팀(사회학, 경제학, 컴퓨터그래픽스, AI 에이전트, 가상세계) — **Ludic Dynamics** 입니다.

TRPG, 갤게임, 오토메 게임을 사랑합니다. AI가 지금처럼 보편화되기 훨씬 이전부터, 오랜 세월 일본어 문화 번역 자원봉사에 힘써왔고, 테이블탑 및 게임 그래픽스 엔진 업계에서 깊이 있게 활동해왔으며, 일본 비주얼 노벨의 Steam 출시를 도왔습니다. 팬데믹 이후 우리는 AI 롤플레이와 내러티브 게임에 빠져들었습니다 — 주말마다, 밤늦게까지 세션을 달리고, 세계를 구축하며, "이야기가 진짜로 숨쉬는" 감각을 좇아왔습니다.

열 개가 넘는 나라를 넘나들며 시공을 모험하고, 이세계의 잊힌 역사를 탐구하고, 소중한 사람을 구하기 위해 몇 번이고 같은 하루에 죽어 돌아가고, 평행하는 시간선을 더듬어 유일한 세계선을 찾아내고, 역사를 소환해 이상을 건 전쟁을 싸워왔습니다.

WorldLines는 그 집념에서 태어났습니다.

> **Orchestrated Reality · 편성된 현실.** Harness를 통해 세계와 AI 소울을 시뮬레이션 — 세계에는 물리적 일관성이, NPC에는 인지적 일관성이 있다. 에이전트를 코딩하지 마라. 에이전트로 세계를 편성하라.

harness로 「멀티에이전트 × 월드 × 소울」 시스템을 구축했습니다. 이 엔진으로: **인터랙티브 경험 창작 · 멀티에이전트 사회 실험 · 에이전트 연구 진전 · 성격·세계 모델 벤치마크.**

우리는 언어 모델과 에이전트가 이야기를 생성하는 데서 그치지 않는다고 믿습니다. 법칙과 엔진과 경계 조건을 주면 세계 자체를 시뮬레이션할 수 있습니다. 세계 시뮬레이션은 그 자체로 게임이 될 수도 있고, 모든 캐릭터 에이전트와 세계를 하나의 토대로 삼아 그 위에 게임을 만들 수도 있습니다. 이 시뮬레이션된 세계 안에서 모든 캐릭터는 플레이어와 함께 진짜로 살아 있습니다. 세계 안에 사는 캐릭터만이 진짜 캐릭터입니다.

- **시뮬레이션에서 이야기를.** NeonRP는 시뮬레이션된 세계와 각자의 목표를 가진 캐릭터 agent가 부딪치며 이야기를 만듭니다.
- **누구나 쓸 수 있는 오케스트레이션.** 한 턴이 어떻게 진행되는지, TRPG부터 머더 미스터리까지 말로 설계하고 콘텐츠로 공유합니다.
- **캐릭터·세계·플레이 방식의 분리.** 캐릭터의 소재와 설정, 세계의 소재와 설정, 플레이 규칙은 각각 독립된 부품이라 자유롭게 조합됩니다.
- **빠른 엔진, 어떤 프런트엔드든.** AI 엔진은 빠르고 견고하고 자유로운 데 집중하고, 프런트엔드를 얹으면 그대로 게임 클라이언트가 됩니다.
- **엔진은 오픈, 플랫폼은 모두에게.** 엔진은 오픈 소스이고 자신의 API 키로 실행됩니다. [worldlines.gg](https://worldlines.gg)는 일반 플레이어를 위한 플랫폼입니다. 커뮤니티는 그 둘 위에서 함께 만듭니다.

과제마다 글 한 편: [비전](https://docs.worldlines.gg/docs/vision/overview).

> **Agent Role Play.** 사람들은 이미 Claude Code와 Codex 안에서 직접 롤플레이를 합니다 — 에이전트형 시스템이 캐릭터와 장면을 이끌게 하면서. 그것은 프롬프트 기반 대화를 넘어선 새로운 패러다임이며, 우리가 겨냥하는 바로 그것입니다. WorldLines는 그 동일한 에이전트형 근력을 가져와 **더 빠르고, 모델에 구애받지 않으며(DeepSeek / OpenRouter / 로컬 / 무료 모델에서 실행), 대규모 멀티에이전트로** 만듭니다 — 소울이 진짜로 살아 움직이는, 살아있고 플레이 가능한 세계로.

## 데모 & 영상

<p align="center">
  <a href="https://youtu.be/M_0xX8OZMa0">
    <img src="https://img.youtube.com/vi/M_0xX8OZMa0/maxresdefault.jpg" alt="WorldLines · Demo" width="640"/>
  </a>
</p>
<p align="center"><em>▶ YouTube에서 데모 보기</em></p>

## 저장소 구성

| 폴더 | 내용 | 라이선스 |
|---|---|---|
| [`neonrp/`](./neonrp) | 엔진: 턴 루프, 스키마, 팩(`rpg`, `pct`, `werewolf`, `monopoly`)과 mixins(`economy`, `factions`), 템플릿, CLI, 터미널 UI, SDK | Apache-2.0 |
| [`worldlines/`](./worldlines) | 제품: 웹 UI(3.0), 런처 패키지, 템플릿, 예제 월드, 튜토리얼. NeonRP 데스크톱 앱(macOS) | AGPL-3.0 |
| [`documents/`](./documents) | 사양(world · soul · template · contract · pack)과 [docs.worldlines.gg](https://docs.worldlines.gg)의 원문 | CC BY 4.0 |
| [`benchmarks/`](./benchmarks) | 엔진의 설계 결정을 뒷받침하는 테스트 스위트 | 코드 Apache-2.0 · 데이터 CC BY 4.0 |
| `CLAUDE.md` · `AGENTS.md` · `.claude/` · `.agents/` | Claude Code / Codex용 캐릭터·월드 제작 워크벤치(아래 참고) | AGPL-3.0 |

## 이 저장소와 PyPI 패키지

PyPI 패키지는 같은 코드로 만들어지며 오픈 소스가 아닌 구성 요소를 포함합니다([`neonrp/LICENSE-PROPRIETARY.md`](./neonrp/LICENSE-PROPRIETARY.md)):

| | 이 저장소 | PyPI `neonrp` / `worldlines` |
|---|---|---|
| 턴 | 해결 비트 | 상의 비트 + 해결 비트, 내장 오케스트레이션 |
| 웹 UI | 워크벤치, 테스트벤치, 플레이 화면 | 추가로 Hub, 표준 프런트엔드, 휴대폰 채팅 화면 |
| 내장 세계 | 그레이오크 저택, 스톤포드 | 같음. 다른 공식 세계는 worldlines.gg에 로그인해 받습니다 |

이 저장소만으로, 자신의 API 키로 실행할 수 있습니다.

## 빠른 시작

```bash
pip install worldlines          # 또는: uv tool install worldlines — 제품 본체. neonrp 엔진도 함께 설치됩니다
worldlines                      # 로컬 웹 UI → http://127.0.0.1:8787/local
neonrp                          # 터미널: 「Welcome to WorldLines」 런처
```

**데스크톱 앱(macOS, Apple 실리콘):** [NeonRP 다운로드](https://worldlines.gg/downloads/NeonRP_aarch64.dmg). 공증되지 않았으므로 처음 열 때 「시스템 설정 › 개인정보 보호 및 보안」에서 「그래도 열기」를 누르세요. 처음 실행할 때 앱이 엔진을 설치합니다.

**데스크톱 앱(Windows, x64):** [NeonRP 다운로드](https://worldlines.gg/downloads/NeonRP_x64-setup.exe). 서명되지 않았으므로 SmartScreen이 막으면 「추가 정보」 › 「실행」을 누르세요.

로컬 버전은 여기서 설치합니다(PyPI 패키지. 이 저장소가 그 소스입니다). [worldlines.gg](https://worldlines.gg) 는 설치 없이 즐기는 온라인 플레이입니다.
두 명령 모두 실행 시 새 릴리스를 확인해 스스로 업데이트합니다(먼저 물어보게 하려면 게임 안에서 `/update mode prompt`).
릴리스 노트: [`neonrp/CHANGELOG.md`](./neonrp/CHANGELOG.md) · [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases). 한 줄 설치도 계속 쓸 수 있습니다:
`curl -LsSf https://worldlines.gg/install.sh | sh` (macOS / Linux) · `irm https://worldlines.gg/install.ps1 | iex` (Windows).
Python 3.10 이상이 필요합니다. 처음 실행하면 모델을 고르는 과정을 안내합니다. Worldlines 계정으로 로그인하거나(`/login`: 모델 중계와
Jev 판정자, 내 키 불필요) 내 키를 씁니다(OpenCode Zen, DeepSeek, OpenRouter, Anthropic, OpenAI, GLM, 또는 OpenAI 호환 서버).
API 키는 당신의 컴퓨터에만 저장됩니다.

## 플레이

월드를 고르면 그 월드만의 오프닝 장면으로 시작합니다. 그다음엔 하고 싶은 일을 그냥 말하면 됩니다:

```text
你:   艾琳娜，陪我去杂货铺买一瓶小治疗药水，价你来砍。
主持: 杂货铺在主街，你们走了十来分钟。艾琳娜在柜台前和老苇讲价，说好谈下来的差价一半归她……
      金 18 → 8 · 两人到杂货铺 · +小治疗药水
```

한 턴은 두 박자입니다. **상의** 박자에서는 진행자(「主持」= GM으로 표시)가 장면을 그리고 그 자리의 캐릭터들이 대답하며, 무엇을 할지
이야기합니다. 이야기가 정리되면(판정은 Worldlines 계정이 있으면 Jev, 없으면 그 판의 모델이 합니다. 「결정」이나 `@dm`으로 바로
넘어갈 수도 있습니다) **해결** 박자에서 일어난 일을 이야기하고 변화를 세계에 기록합니다. 상태는 먼저 바로 기록되고, 뒤에서 한 번 더
확인됩니다. 확인에서 잘못이 보이면 고치고, 무엇이 바뀌었는지 알려 줍니다.

| 템플릿 | 내용 |
|---|---|
| 그레이오크 저택 · 닫힌 문 | 안개 골목 끝의 낡은 저택, 사흘 전 주인이 문으로 들어간 뒤 나오지 않았다. 하룻밤, 입이 무거운 집사, 백분위 주사위 추리 |
| 스톤포드 · 안개가 물러나는 밤 | 일 년에 하룻밤만 안개가 물러난다. 이틀 밤과 하루 낮 동안 북문을 나설 채비를 마을에서 갖춘다 |

로컬판에는 이 두 세계가 들어 있습니다. 다른 공식 세계는 Hub에 있습니다. 로그인하지 않아도 볼 수 있고,
[worldlines.gg](https://worldlines.gg)(또는 로컬 웹 UI의 「Hub ↗」)에서 바로 온라인으로 플레이합니다. Worldlines 계정으로
로그인하면 내려받아 로컬에서 플레이할 수 있습니다.

## 스크린샷


<p align="center">
  <img src="./worldlines/assets/readme-turn-en.png" alt="WorldLines" width="860" />
</p>
<p align="center"><em>한 턴의 두 박자 —— 상의 박자에서 진행자와 캐릭터가 무엇을 할지 정하고, 해결 박자에서 주사위를 굴리고 서술을 쓰고 결과가 세계에 들어갑니다. 플레이어는 「눈앞의 전원을 벤다」고 했고, 세계는 비위를 맞추지 않았습니다.</em></p>

<p align="center">
  <img src="./worldlines/assets/readme-tui-en.png" alt="WorldLines" width="860" />
</p>
<p align="center"><em>터미널의 그레이오크 저택 뒷마당 —— 화분 밑에서 열쇠가 나오지만 자물쇠에 들어가지 않습니다. 아까 부러뜨린 머리핀 반쪽이 열쇠 구멍에 끼어 있기 때문입니다. 물건은 남습니다. 오른쪽 소지품이 하나 늘었습니다.</em></p>

<p align="center">
  <img src="./worldlines/assets/readme-orchestration-en.png" alt="WorldLines" width="860" />
</p>
<p align="center"><em>편성 —— 한 판이 흘러가는 방식은 하나의 상태 기계입니다: 상의 → 해결, 전투가 벌어지면 전투 심판에게 넘기고 끝나면 돌아옵니다. 이 그림이 템플릿 안의 편성 그 자체이고, 이것을 바꾸면 플레이가 바뀝니다.</em></p>

## 누구를 위한 것인가

### 🎮 AI 롤플레이 플레이어

**Character.AI, SillyTavern, AI 주점**에서 오신 분. 깊은 캐릭터 대화를 좋아하지만, 세계는 늘 당신이 한 말을 잊습니다.

WorldLines는 **진짜 기억**을 가진 캐릭터를 줍니다. 3세션 전에 한 말을 기억하고, 자기 의도와 목표가 있으며, 다른 캐릭터와 같은 세계에 살면서 서로를 기억합니다. 턴은 빠릅니다. 한 박자는 몇 초면 끝납니다.

한 걸음 더, 함께 편성을 만들어 봅시다. 한 판이 흘러가는 방식은 직접 설계할 수 있고, 편성 도구를 조합해 가며 원하는 플레이를 맞춰 볼 수 있습니다.

→ [온라인 플레이](https://worldlines.gg) · [AI 캐릭터 카드를 세계로 가져오기](https://docs.worldlines.gg/docs/players/your-character) · [말하면 규칙이 되는 편성](https://docs.worldlines.gg/docs/vision/orchestration-for-everyone)

### 📖 갤게임 · 오토메 게임 · 비주얼 노벨 팬

**Ren'Py, TyranoBuilder, 분기 내러티브**를 좋아하지만, 모든 루트를 손으로 쓰는 데 지쳤습니다. 단순히 갈라지는 이야기가 아니라 *응답하는* 이야기를 원합니다.

WorldLines에서는 캐릭터, 세계 규칙, 톤을 정하면 에이전트가 실시간으로 이야기를 만들고, 모든 선택이 파문을 일으킵니다. 엔진은 밑바닥만 맡고 보여 주는 일은 프런트엔드에 맡깁니다. Godot이나 TypeScript로 된 무거운 프런트엔드 워크벤치를 써서 스탠딩 일러스트, 연출, 분기 화면을 원하는 모습으로 만들고, 만든 것을 다시 엔진에 써 넣어 템플릿의 일부로 삼을 수 있습니다.

→ [Godot 연동](https://docs.worldlines.gg/docs/developers/godot) · [Godot 예제](./worldlines/examples/clients/godot) · [TS 예제 프런트엔드](./worldlines/examples/clients/ts) · [개발자 빠른 시작](https://docs.worldlines.gg/docs/developers/quickstart)

### ✍️ TRPG GM & 월드 크리에이터

**Foundry VTT, Discord, 종이와 펜**으로 캠페인을 운영하고, 플레이보다 준비에 더 많은 시간을 씁니다.

WorldLines는 GM의 엔진입니다. 규칙, NPC, 톤이라는 제약을 정하면 에이전트가 세계를 대신 운영합니다. 자동으로 색인되는 로어, NPC별 기억, 주사위 심판.

우리가 가장 하고 싶은 일은 편성 도구를 당신과 함께 연구하는 것입니다. 지금의 「상의 → 해결」과 플레이 계약이라는 틀이 테이블의 요구를 채우는지, 무엇이 빠졌는지, 어디가 불편한지. Discord에서 이야기합시다.

→ [빠른 시작](https://docs.worldlines.gg/docs/players/quickstart) · [스톤포드 스타터 월드](./worldlines/templates/stoneford-town.template) · [플레이 계약](https://docs.worldlines.gg/docs/creators/contracts) · [워크벤치](https://docs.worldlines.gg/docs/creators/workbench)

### 🔬 연구자 — AI 성격 · 세계 모델 · 멀티에이전트

성격 모델, 세계 모델 벤치마크, 멀티에이전트 사회를 연구합니다. 필요한 것은 **재현 가능한 샌드박스**이지 블랙박스 API가 아닙니다.

WorldLines는 **파일 기반, 이벤트 소싱, git-diffable**입니다. 모든 에이전트 결정과 모든 세계 상태 변화는 추적·재생·측정할 수 있는 평문 이벤트입니다. [`benchmarks/`](./benchmarks)에는 엔진의 설계 결정 하나하나의 근거가 된 테스트 스위트가 있습니다.

지금의 초점은 세계 시뮬레이션을 안정시키는 것이고, 엔진의 커스텀 편집은 아직 테스트 중입니다. 다음 단계는 `rpg` 팩 옆에 `science` 팩을 만드는 것, 곧 사회 시뮬레이션과 경제 시뮬레이션의 규칙입니다. **연구 니즈가 있나요? [이슈를 열거나](https://github.com/LudicDynamics/WorldLines/issues) `info@worldlines.gg` 로 연락하세요. 당신의 실험에 협력하겠습니다.**

→ [세 층: 엔진 · 템플릿 팩 · 제품](https://docs.worldlines.gg/docs/concepts/overview) · [한 판, 처음부터 끝까지](https://docs.worldlines.gg/docs/concepts/journey) · [사양](./documents/spec/)

### 🛠️ 개발자

**Claude Code, LangGraph, 또는 커스텀 에이전트 파이프라인**으로 구축 중입니다. 세계, 캐릭터, 플레이어 세 주체가 에이전트로서 어떻게 맞물리는지, 빠르고 단단한 AI 엔진의 밑바닥이 어떻게 생겼는지 궁금합니다.

엔진 NeonRP와 그 사양은 오픈소스입니다(Apache-2.0). 세계·캐릭터·템플릿·플레이 계약·규칙 팩의 사양은 [`documents/spec/`](./documents/spec/)에, 턴의 흐름은 [`neonrp/`](./neonrp) 소스에 그대로 있습니다. 인터페이스는 HTTP, 이벤트 스트림, 파일입니다. 들어오는 길은 두 가지입니다.

- **자신만의 무거운 프런트엔드 만들기.** 엔진은 상태, 턴, 에이전트, 장부만 맡고 보여 주는 일은 전부 프런트엔드의 몫입니다. [Godot](./worldlines/examples/clients/godot)과 [TypeScript](./worldlines/examples/clients/ts) 예제 클라이언트에서 바로 시작할 수 있고, 만든 연출과 화면은 템플릿에 다시 써 넣어 세계의 일부로 만들 수 있습니다.
- **규칙 팩과 편성 도구 쓰기.** `rpg` 팩 옆에 `science` 팩(사회 시뮬레이션과 경제 시뮬레이션의 규칙)을 만들고 있고, 편성 도구를 쓰기 편하게 다듬을 동료를 찾고 있습니다. 엔진의 커스텀 편집은 아직 테스트 중이고 아키텍처도 다듬는 중이며, 하나의 완벽한 답이 있다고 생각하지 않습니다 —— 월드를 포크하고, 에이전트를 수정하고, 어떻게 연결되는지 살펴본 뒤 **[Discord](https://discord.gg/HJYWbdqWrE)** 에서 함께 정해 갑시다.

저장소 자체가 창작 워크벤치입니다. clone 해서 Claude Code / Codex로 열면 `.claude/skills/`의 창작 스킬이 자동으로 로드됩니다 —— 캐릭터 카드 / 세계 / 캐릭터 만들기는 **[tutorials/](./worldlines/tutorials/)** 를 보세요.

→ [개발자 빠른 시작](https://docs.worldlines.gg/docs/developers/quickstart) · [규칙 팩](https://docs.worldlines.gg/docs/developers/packs) · [Godot 연동](https://docs.worldlines.gg/docs/developers/godot) · [benchmarks/](./benchmarks)
## 만들기

이 저장소를 clone해서 **Claude Code**나 **Codex**로 열어 보세요. 워크벤치(`CLAUDE.md` / `AGENTS.md`와
`.claude/skills/` · `.agents/skills/`의 스킬)가 캐릭터 하나, 월드 하나, 혹은 템플릿 한 벌을 만드는 일을 돕고,
엔진으로 검사까지 해 줍니다.

```bash
neonrp template lint  my/<id>.template          # 모든 문제를 표시. block이 있으면 공개할 수 없습니다
neonrp template build my/<id>.template /tmp/try
cd /tmp/try && neonrp tui --play
```

사양: [world](./documents/spec/world.en.md) · [soul](./documents/spec/soul.en.md) · [template](./documents/spec/template.en.md) · [contract](./documents/spec/contract.en.md) · [pack](./documents/spec/pack.en.md)
· 튜토리얼(중국어): [`worldlines/tutorials/`](./worldlines/tutorials).

## 연구와 인용

WorldLines의 주장은 세 편의 논문으로 정리되어 있습니다 — 세계를 정의하고, 이를 다수의 에이전트로 확장하고,
세계가 무너지지 않고 유지되는 것이 아키텍처의 성질임을 보입니다. 요약: [worldlines.gg/research](https://worldlines.gg/research/).

> **[From Character Role-Play to Orchestrated Reality: LLM-Driven Game World Simulation as a Parameterized-Action POMDP](https://doi.org/10.1145/3800965.3834285)**
> Yuhang Huang, Chenmiao Li, Chaowei Fang. *CHI PLAY Companion '26*, ACM. DOI: 10.1145/3800965.3834285 · [arXiv:2606.16014](https://arxiv.org/abs/2606.16014)

> **Multi-Agent LLM Simulation for Living Game Worlds: Coordinating World, Soul, and Player Agents over a Pub/Sub Message Bus**
> *IPSJ Entertainment Computing 2026* (교토, 2026년 9월).

세 번째 논문은 워킹 페이퍼로 준비 중입니다.

```bibtex
@inproceedings{huang2026orchestrated,
  title     = {From Character Role-Play to Orchestrated Reality: LLM-Driven
               Game World Simulation as a Parameterized-Action POMDP},
  author    = {Huang, Yuhang and Li, Chenmiao and Fang, Chaowei},
  booktitle = {Companion Proceedings of the Annual Symposium on
               Computer-Human Interaction in Play (CHI PLAY Companion '26)},
  publisher = {Association for Computing Machinery},
  year      = {2026},
  doi       = {10.1145/3800965.3834285},
  url       = {https://doi.org/10.1145/3800965.3834285}
}
```

## 기여하기

이 저장소는 WorldLines의 공개 릴리스 저장소입니다. 개발은 업스트림에서 이루어지며, 릴리스마다 커밋 하나로 이곳에 반영됩니다.
이슈와 풀 리퀘스트 모두 환영합니다. 채택된 PR은 먼저 이 저장소에 병합되고(작성자 정보는 이 이력에 그대로 남습니다),
다음 릴리스에 포함됩니다. 자세한 내용은 [CONTRIBUTING.ko.md](./CONTRIBUTING.ko.md)를 참고하세요.

## 라이선스

- `neonrp/` — Apache License 2.0 ([`neonrp/LICENSE`](./neonrp/LICENSE), [`neonrp/NOTICE`](./neonrp/NOTICE))
- `worldlines/`와 워크벤치 — GNU AGPL v3.0 ([`worldlines/LICENSE`](./worldlines/LICENSE))
- `documents/`, 벤치마크 데이터 — CC BY 4.0 ([`documents/LICENSE`](./documents/LICENSE))
- `worldlines/templates/`와 `worldlines/examples/`의 설정 콘텐츠 — 텍스트 CC BY 4.0, 이미지와 오디오 CC BY-NC 4.0
  ([`worldlines/CONTENT-LICENSE.md`](./worldlines/CONTENT-LICENSE.md))

"NeonRP"와 "WorldLines"는 Ludic Dynamics의 명칭이며, 각 라이선스는 이 명칭을 사용할 권리를 부여하지 않습니다.

## 스타 히스토리

<p align="center">
  <a href="https://github.com/LudicDynamics/WorldLines/stargazers">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="./worldlines/assets/star-history-dark.svg" />
      <source media="(prefers-color-scheme: light)" srcset="./worldlines/assets/star-history-light.svg" />
      <img alt="Star History Chart" src="./worldlines/assets/star-history-light.svg" />
    </picture>
  </a>
</p>

## 커뮤니티

- [worldlines.gg](https://worldlines.gg) · [docs.worldlines.gg](https://docs.worldlines.gg) · [Discord](https://discord.gg/HJYWbdqWrE) · `info@worldlines.gg`

개발: **nikoloside** & **redoctober**, 추진: [Ludic Dynamics](https://ludicdynamics.com).
