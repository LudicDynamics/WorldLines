# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> **오픈소스:** 이 저장소의 예제 월드, 도구, 프로토콜 — AGPL-3.0. 포크, 수정, 자신의 세계를 자유롭게 공개할 수 있습니다.
> **오픈소스가 아닌 것:** 엔진 코어(`neonrp`). 무료 플레이, 포크 및 재배포 불가. [LICENSE](LICENSE) 참조.

<p align="center">
  <img alt="GitHub Stars" src="https://img.shields.io/github/stars/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Watchers" src="https://img.shields.io/github/watchers/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Forks" src="https://img.shields.io/github/forks/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Issues" src="https://img.shields.io/github/issues/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <a href="https://hub.worldlines.gg"><img src="https://img.shields.io/badge/Live%20Demo-hub.worldlines.gg-8b5cf6?style=flat-square" /></a>
  <img alt="License" src="https://img.shields.io/badge/License-AGPL--3.0%20(examples)-blue?style=flat-square" />
  <img alt="LINUX DO" src="https://img.shields.io/badge/LINUX%20DO-WorldLines-8b5cf6?style=flat-square" />
</p>

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 살아있는 세계로 향하는 문" width="640" />
</p>

## 개요

**무엇을 할 수 있나요?**

당신의 모든 행동을 기억하는 세계로 들어가세요. 잿빛 안개의 북쪽 항구에서 포위 명령을 내리세요. 영원히 역에 도착하지 않는 열차의 모든 객차를 탐험하세요. 당신의 말 한마디를 진짜로 기억하는 기억상실 치유사와 마주 앉으세요. 몇 분 만에 세계를 만들고 — 규칙, 템포, NPC를 설정하거나 — 공개 카탈로그에서 골라 바로 뛰어드세요. 이것은 실시간 멀티에이전트 사회: 많은 AI 소울과 당신이, 하나의 세계에서, 함께 빚어갑니다.

이것은 에이전트형 시뮬레이션 엔진입니다. 월드 agent가 장소 agent에 연결되고, 장소 agent가 소울 agent를 호스트합니다. 모두가 agent. 당신은 분신 터미널로 참여합니다. 이것은 챗봇도, 스크립트 게임도 아닙니다.

> 상태: **v0.2.0 — Hub 출시** (2026-06) · [지금 플레이 →](https://hub.worldlines.gg)

---

## 팀 & 비전

우리는 **도쿄대학**의 PhD 및 연구자, 그리고 게임 실무자로 구성된 학제적 팀(사회학, 경제학, 컴퓨터그래픽스, AI 에이전트, 가상세계) — **Ludic Dynamics** 입니다.

TRPG, 갤게임, 오토메 게임을 사랑합니다. AI가 지금처럼 보편화되기 훨씬 이전부터, 오랜 세월 일본어 문화 번역 자원봉사에 힘써왔고, 테이블탑 및 게임 그래픽스 엔진 업계에서 깊이 있게 활동해왔으며, 일본 비주얼 노벨의 Steam 출시를 도왔습니다. 팬데믹 이후 우리는 AI 롤플레이와 내러티브 게임에 빠져들었습니다 — 주말마다, 밤늦게까지 세션을 달리고, 세계를 구축하며, "이야기가 진짜로 숨쉬는" 감각을 좇아왔습니다.

열 개가 넘는 나라를 넘나들며 시공을 모험하고, 이세계의 잊힌 역사를 탐구하고, 소중한 사람을 구하기 위해 몇 번이고 같은 하루에 죽어 돌아가고, 평행하는 시간선을 더듬어 유일한 세계선을 찾아내고, 역사를 소환해 이상을 건 전쟁을 싸워왔습니다.

WorldLines는 그 집념에서 태어났습니다.

> **Orchestrated Reality · 편성된 현실.** Harness를 통해 세계와 AI 소울을 시뮬레이션 — 세계에는 물리적 일관성이, NPC에는 인지적 일관성이 있다. 에이전트를 코딩하지 마라. 에이전트로 세계를 편성하라.

harness로 「멀티에이전트 × 월드 × 소울」 시스템을 구축했습니다. 이 엔진으로: **인터랙티브 경험 창작 · 멀티에이전트 사회 실험 · 에이전트 연구 진전 · 성격·세계 모델 벤치마크.**

---

## 데모 & 영상

<p align="center">
  <a href="https://youtu.be/M_0xX8OZMa0">
    <img src="https://img.youtube.com/vi/M_0xX8OZMa0/maxresdefault.jpg" alt="WorldLines · 데모" width="640"/>
  </a>
</p>
<p align="center"><em>▶ YouTube에서 데모 보기</em></p>

---

## 빠른 시작

### 🖥️ 런처 다운로드

플랫폼을 선택하세요. 더블클릭으로 설치. 터미널 불필요.

| 플랫폼 | 파일 | 다운로드 |
|----------|------|----------|
| macOS | `WorldLines.command` | [최신판](https://worldlines.gg/WorldLines.command) |
| Windows | `WorldLines.bat` | [최신판](https://worldlines.gg/WorldLines.bat) |
| Linux | `WorldLines.sh` | [최신판](https://worldlines.gg/WorldLines.sh) |

macOS / Linux: `chmod +x` 한 번 실행 후 바탕화면으로 드래그.

### ⌨️ 또는 터미널로 설치

```bash
# macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh

# Windows（PowerShell）
irm https://worldlines.gg/install.ps1 | iex
```

설치 후:

```bash
worldlines
```

TUI가 실행됩니다. 여기서 새 월드 생성, 카탈로그 탐색, 저장된 세션 이어하기가 가능합니다.

> **최초 실행 시 API 설정을 안내합니다.** 키는 `~/.neonrp/config.json`에 저장. [제공자 가이드 →](https://docs.worldlines.gg/docs/getting-started/quickstart)

### 🌐 또는 브라우저에서 플레이

설치 불필요. **[hub.worldlines.gg](https://hub.worldlines.gg)** 를 열고 로그인하여 브라우저에서 플레이.

---

## 스크린샷

<p align="center">
  <img src="./assets/gameplay.jpg" alt="게임플레이 — Stoneford" width="720" />
</p>
<p align="center"><em>게임플레이 — 안개 속 Stoneford에 도착</em></p>

---

## 예제 월드

WorldLines는 세계를 **세 가지 엔진 모드** 중 하나로 구동합니다 —— 이들은 **혼용할 수 없습니다**:

- **fast** —— 하나의 빠른 agent, 단일 목소리.
- **orch** —— world-agent가 도메인 agent(마을 / 던전 / 전투 / 스토리)를 편성; NPC는 데이터.
- **multi-agent** —— world-agent가 **독립된 소울**을 감쌉니다. 각 소울은 고유한 마음·기억·속셈을 가진 캐릭터 agent. 표식은 `souls/` 폴더. *이번 신규 릴리스.*

### 👥 multi-agent —— 독립된 소울들이 한 세계에

| 월드 | 소울 | 라이브 데모 |
|---|---|---|
| **[神楽島 Kagura Island](./examples/kagura-island)** | **7명** —— 鏡子 · 羽 · 真琴 · 宮司 · 白 · 翼 · 悠人. 일본풍 미스터리, 타임 루프, CoC 판정. 가장 풍부한 멀티에이전트 사회. | [플레이 →](https://hub.worldlines.gg/play/worlds/kagura-island) |
| **[Stoneford · Elena](./examples/stoneford-elena)** | **2명** —— Elena(기억하는 치유사) + Rowan. Stoneford 세계에 살아있는 소울이 깃든다. | [플레이 →](https://hub.worldlines.gg/play/worlds/stoneford-elena) |

### ⛩ Stoneford — 플래그십 orch 월드

잿빛 안개의 북쪽 강변 항구. 클래식 판타지 TRPG · d20 주사위 · **10-agent 편성 마을** —— 중심의 world-agent가 마을·던전·전투·스토리·NPC agent로 라우팅. **[온라인 플레이 →](https://hub.worldlines.gg/play/worlds/stoneford)** · **[소스 & 문서 →](./examples/stoneford)**

### 그 외 월드

| 월드 | 플레이 스타일 | 라이브 데모 |
|---|---|---|
| **Dark Train** | 오픈 월드 — 무엇을 하든 세계가 기억한다 | [플레이 →](https://hub.worldlines.gg/play/worlds/dark-train) |
| **Goblin Ambush** | 3층 던전 — 3마리 고블린 보스 격파 | [소스 →](./examples/goblin-ambush) |
| **Worldline** | 시간 표류 내러티브 — 과거에 문자 보내기 | [소스 →](./examples/worldline) |
| **Sakura Hallway** | Clannad 풍 · 학원 감성叙事 | [소스 →](./examples/sakura-hallway) |

모든 월드는 [examples/](./examples/)에 있습니다 — 오픈소스(AGPL-3.0).

---

## 이 엔진을 사용한 다른 프로젝트

- **[Soul Talk](https://hub.worldlines.gg/play/souls/elena)** — 캐릭터 에이전트 대화 씬. Elena는 기억합니다.
- **[Worldline](./examples/worldline)** — 시간 표류 내러티브 엔진. 과거에 문자를 보내고 시간선이 다시 쓰이는 것을 지켜보세요.
- **Coming: RP-Abyss** — TRPG 원정. DM + 주사위 판정.

---

## 누구를 위한 것인가

### 🎮 AI 롤플레이 플레이어

**Character.AI, SillyTavern, AI 주점**에서 오신 분. 깊은 캐릭터 대화를 좋아하지만 — 세계는 항상 잊어버립니다.

WorldLines는 **진짜 기억**을 가진 캐릭터를 제공합니다. 3세션 전에 당신이 한 말을 기억합니다. 내면의 목소리, 의도, 목표를 가지고 있습니다. 그리고 혼자가 아닙니다 — 다른 캐릭터와 함께 세계에 살며 서로를 기억합니다.

→ [Elena와 대화하기 (Soul Talk)](https://hub.worldlines.gg/play/souls/elena) · [카탈로그 보기](https://hub.worldlines.gg/souls)

### 📖 갤게임 & 비주얼 노벨 팬

**Ren'Py, TyranoBuilder, 분기 내러티브**를 좋아하지만 — 모든 루트를 손으로 쓰는 데 지쳤습니다. *응답하는* 이야기를 원합니다, 단순히 분기하는 것이 아니라.

WorldLines에서는 캐릭터, 세계 규칙, 톤을 설정하면 에이전트가 실시간으로 이야기를 생성합니다. 모든 선택이 파문을 일으킵니다. 같은 플레이스루는 두 번 없습니다.

→ [첫 세계 만들기](https://docs.worldlines.gg/docs/guides/creating-first-world) · [SillyTavern 가져오기 →](https://docs.worldlines.gg/docs/guides/sillytavern-import)

### ✍️ TRPG GM & 월드 크리에이터

**Foundry VTT, Discord, 종이와 펜**으로 테이블탑 캠페인을 운영 중입니다. 플레이보다 준비에 더 많은 시간을 씁니다.

WorldLines는 GM의 엔진: 제약을 설정하면 — 규칙, NPC, 톤 — 에이전트가 세계를 운영합니다. 자동 인덱싱된 로어, NPC별 기억, 주사위 심판 에이전트.

→ [빠른 시작](https://docs.worldlines.gg/docs/getting-started/quickstart) · [Stoneford 스타터 월드](./examples/stoneford)

### 🔬 연구자 — AI 성격 · 세계 모델 · 멀티에이전트

성격 모델, 세계 모델 벤치마크, 멀티에이전트 사회를 연구합니다. **재현 가능한 샌드박스**가 필요합니다 — 블랙박스 API가 아니라.

WorldLines는 **파일 기반, 이벤트 소싱, git-diffable**입니다. 모든 에이전트 결정, 모든 세계 상태 변화가 추적·재생·측정 가능한 평문 이벤트입니다. 다른 모델로 같은 시나리오를 실행하고 출력을 비교하며 결과를 발표할 수 있습니다.

→ [핵심 개념](https://docs.worldlines.gg/docs/core-concepts/agents-orchestration) · [작동 방식](#how-it-works)

### 🛠️ 개발자

**Claude Code, LangGraph, 또는 커스텀 에이전트 파이프라인**으로 구축 중입니다. 검사하고, 포크하고, 이의를 제기할 수 있는 프로토콜이 필요합니다.

WorldLines의 예제, 도구, 프로토콜은 **오픈소스(AGPL-3.0)** 입니다. 월드를 포크하고, 에이전트를 수정하고, 자신의 것을 출시하세요. 엔진 바이너리는 무료 플레이 — 로컬 사용에 API 키 불필요.

→ [examples/](./examples/) · [프로토콜 문서](https://docs.worldlines.gg/docs/protocol/overview)

## 작동 방식

WorldLines는 게임 세계를 파일 기반의 이벤트 소싱 상태 머신으로 다룹니다. 모든 턴은 추가 전용 이벤트. 스냅샷으로 빠른 되감기 가능.

**에이전트 아키텍처 (3계층):**

```
Layer 1: world-agent        — 상태 · 라우팅 · 내러티브 · 아카이브
Layer 2: town-agent          — NPC, 상점, 내비게이션
         dungeon-agent       — 탐험
         combat-referee      — d20 주사위
         world-builder       — 맵 업데이트
Layer 3: (향후) 주사위/규칙 도구 에이전트
```

- **파일 영구 저장된 기억과 세계 상태** — 모든 것이 평범한 JSON과 Markdown으로 디스크에.
- **자동 인덱싱, 자동 주입 컨텍스트** — 수동 로어북 관리 불필요.
- **브랜치 / 언두 / 리두** — git 브랜치처럼 내러티브 분기 탐험.
- **샌드박스 & 리플레이** — 결정성 검증.
- **로컬 우선 모델** — GLM, OpenAI, LM Studio, Ollama.

---

## 튜토리얼

전체 문서는 **[docs.worldlines.gg](https://docs.worldlines.gg)** 에:

| 주제 | 링크 |
|---|---|
| 시작하기 | [docs.worldlines.gg/docs/getting-started](https://docs.worldlines.gg/docs/getting-started) |
| 핵심 개념 | [docs.worldlines.gg/docs/core-concepts](https://docs.worldlines.gg/docs/core-concepts) |
| 가이드 | [docs.worldlines.gg/docs/guides](https://docs.worldlines.gg/docs/guides) |
| Q&A / 비교 | [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa) |

---

## 로드맵

| 버전 | 상태 |
|---|---|
| **v0.1.9** — Engine (2026-04) | ✓ 10-agent 오케스트레이터 · Stoneford 스타터 · Claude Code 런타임 |
| **v0.2.0** — Hub 출시 (2026-06) | ✓ WebHub · 호스트 플레이 · Soul Talk · Create Studio · Stripe · 커버 · 세이브 |
| **v0.3.0** — Desktop (2026-06) | ◑ Tauri 데스크톱 · 멀티에이전트 사회 · 상주 월드 · Alipay/WeChat |
| **v1.0** — Protocol | ○ 안정된 WORLD/SOUL 프로토콜 · 자체 호스팅 Web판 |

전체 로드맵: [docs.worldlines.gg/docs/roadmap](https://docs.worldlines.gg/docs/roadmap)

---

## 라이선스

**오픈소스 (AGPL-3.0):** `examples/`와 `tools/`의 예제 월드, 캐릭터 번들, 도구, 프로토콜.

**오픈소스가 아닌 것:** 엔진 코어 (`neonrp`). 독점 프리뷰 — 무료 플레이, 포크 불가.

## 스타 히스토리

<p align="center">
  <a href="https://www.star-history.com/?type=date&repos=LudicDynamics%2FWorldLines">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=LudicDynamics/WorldLines&type=date&theme=dark&legend=top-left" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=LudicDynamics/WorldLines&type=date&legend=top-left" />
      <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=LudicDynamics/WorldLines&type=date&legend=top-left" />
    </picture>
  </a>
</p>

---

## 커뮤니티

- Web: [worldlines.gg](https://worldlines.gg) · Docs: [docs.worldlines.gg](https://docs.worldlines.gg)
- Discord: [discord.gg/HJYWbdqWrE](https://discord.gg/HJYWbdqWrE)
- GitHub: [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)
- 연락처: `info@worldlines.gg`

---

**nikoloside** & **redoctober** 가 개발, [Ludic Dynamics](https://ludicdynamics.com) 와 함께 추진.
