# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 살아있는 세계로 향하는 문" width="640" />
</p>

<p align="center">
  <img src="./assets/helloworld.jpg" alt="WorldLines TUI 시작 화면" width="720" />
</p>

<p align="center"><em>YouTube 트레일러 — 곧 공개됩니다.</em></p>

<table align="center">
  <tr>
    <td width="50%" align="center"><img src="./assets/cards/D0%20Hero%20%28deck%20%C2%B7%20KO%29.png" alt="WorldLines — Hero" /></td>
    <td width="50%" align="center"><img src="./assets/cards/D1%20%E7%B1%B3%E1%84%85%E1%85%A1%E1%84%8B%E1%85%AC%E1%84%89%E1%85%A1%E1%86%BC%20%28deck%20%C2%B7%20KO%29.png" alt="미라 외상 · 스토리 카드" /></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/cards/D2%20%E1%84%85%E1%85%A1%E1%84%8B%E1%85%A9%E1%84%8B%E1%85%B0%E1%84%8B%E1%85%B5%20%E1%84%8B%E1%85%A3%E1%86%A8%E1%84%89%E1%85%A9%E1%86%A8%20%28deck%20%C2%B7%20KO%29.png" alt="라오웨이 약속 · 스토리 카드" /></td>
    <td align="center"><img src="./assets/cards/D3%20Gameplay%20%28deck%20%C2%B7%20KO%29.png" alt="게임플레이" /></td>
    <td align="center"><img src="./assets/cards/D4%204%20Worlds%20%28deck%20%C2%B7%20KO%29.png" alt="4 개의 세계" /></td>
  </tr>
</table>

> 상태: **v0.1.7 stable** (2026-04-27) · 다음: **v0.2.0** (예정)

> *Agents for Role Play. Agents for Game. Agents as a Game.*
> 파일 기반, 이벤트 소싱 방식으로 살아있는 세계를 구동하는 엔진입니다.

> **아직 매우 초기 단계입니다 — 공개적으로 만들고 있습니다.** WorldLines는
> 활발히 개발 중입니다. 새로운 게임플레이, 새로운 orchestration 모드,
> 새로운 모듈이 꾸준히 나올 예정입니다. 조용히 완성도를 다듬는 것보다
> 일찍 내놓고 여러분과 함께 반복하고 싶습니다.

WorldLines는 **nikoloside** 와 **redoctober** 가 공동 개발하고,
[Ludic Dynamics](https://ludicdynamics.com) 와 함께 지속적으로
추진하고 있는 Agentic AIRP 엔진(AI RolePlay engine)입니다. 엔진
바이너리의 코드네임은 `neonrp`이며, 릴리스 브랜드는 **WorldLines**입니다.

게임 세계를 버전 관리되는 파일 기반 상태 기계로 다루기 때문에, 여러분의
플레이, 편집, Agent가 모두 휘발성 채팅 로그가 아닌 재현 가능한 아티팩트로
남게 됩니다.

---

## 왜 WorldLines인가

전통적인 "AI와 채팅" 인터페이스는 context window가 가득 차는 순간 모든
것을 잃어버립니다. WorldLines는 진정한 엔진 수준의 보장을 제공합니다.

- **⭐ 파일로 영구 저장되는 기억과 월드 상태.** 기억, 저장, NPC, Agent
  가 모두 평범한 JSON과 Markdown으로 디스크에 저장됩니다. 클라우드
  없음, 데이터베이스 없음, 숨겨진 상태 없음. 폴더를 열 수 있다면
  그 세계는 당신의 것입니다.
- **인덱스 + 컨텍스트 자동 주입.** WorldLines는 파일 인덱스와 로컬
  벡터 DB를 자동으로 구축하고, 각 턴마다 관련 게임 데이터만을
  Agent의 컨텍스트에 자동 주입합니다. lorebook을 수동으로 관리할
  필요가 없습니다.
- **Event-sourced state.** 모든 턴은 append-only Event이며, Snapshots
  덕분에 되감기가 빠릅니다.
- **Branch / Undo / Redo.** git branch처럼 서사 분기를 탐색할 수 있습니다.
- **Sandbox & Replay.** 격리된 환경에서 실험하고 결정성을 검증합니다.
- **Orchestrator 기반 multi-agent.** Orchestrator가 단일 상태 위에서
  도메인 Agent(town / dungeon / combat-referee / world-builder /
  rules-referee)로 라우팅합니다.
- **Plan → Diff → Apply.** LLM이 구조화된 파일 연산을 출력하고, 반영
  전에 검토할 수 있습니다.
- **Rich TUI.** 플레이와 제작 모두를 위한 Claude-Code 스타일 대화형
  터미널을 제공합니다.
- **Local-first 모델.** GLM, OpenAI, LM Studio, Ollama를 지원합니다.

### WorldLines와 다른 도구 비교

|                      | Character.AI       | SillyTavern                 | Claude Code              | **WorldLines**                      |
|----------------------|--------------------|------------------------------|---------------------------|--------------------------------------|
| 주요 영역            | 캐릭터 채팅        | Prompt 프론트엔드            | 코드 편집                 | 살아있는 게임 월드                    |
| 월드의 저장 위치     | 그들의 서비스      | Prompt 설정 + 채팅 로그       | 디스크 상의 코드베이스     | **평범한 파일 + git**                |
| 기억과 검색          | 클라우드 / 불투명  | 수동 lorebook                | 코드베이스 검색            | **자동 파일 인덱스 + 벡터 DB**       |
| Multi-agent          | —                  | —                            | 태스크별 서브 agent         | Orchestrator + 도메인 agents          |
| 로컬 우선 LLM        | ✗                 | 직접 연결                     | API 전용                  | GLM / LM Studio / Ollama             |
| 결정성 / Replay      | —                  | —                            | —                         | **Sandbox + Replay**                 |

Claude Code가 코드를 위한 IDE라면, WorldLines는 살아있는 세계를 위한
IDE입니다 — 기억, 검색, orchestration이 모두 내장된 상태로.

> 각 경쟁 도구에 대한 완전한 비교는
> [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa)
> (vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph · vs OpenClaw)을 참고하세요.

> 참고: 현재 WorldLines의 harness는 Claude Code보다 더 엄격합니다 — 신뢰할 수 있는 오케스트레이션을 위해 완전한 컨텍스트에 의존합니다. 이는 더 높은 결정성과 더 쉬운 디버깅을 위한 의도적인 트레이드오프이며, 결함이 아닙니다.


---

## 설치

### 원라이너

```bash
# macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh

# Windows (PowerShell)
irm https://worldlines.gg/install.ps1 | iex
```

`uv`가 없으면 설치한 뒤 `uv tool install worldlines`를 실행합니다.
`neonrp --help` 또는 `worldlines`로 설치를 확인하세요.

### 더블클릭 런처

터미널을 다루고 싶지 않으신가요? 플랫폼별 런처를 내려받아 더블클릭하기만
하면 됩니다. 각 런처는 터미널 창을 열어 최초 설치를 진행하거나(두 번째
실행부터는 자체 업데이트) 이후 TUI로 이어집니다.

| 플랫폼   | 파일                 | 다운로드 |
|----------|----------------------|----------|
| macOS    | `WorldLines.command` | [최신](https://worldlines.gg/WorldLines.command) |
| Windows  | `WorldLines.bat`     | [최신](https://worldlines.gg/WorldLines.bat)     |
| Linux    | `WorldLines.sh`      | [최신](https://worldlines.gg/WorldLines.sh)      |

내려받은 뒤(macOS / Linux) 한 번만 `chmod +x`를 실행합니다.

```bash
chmod +x ~/Downloads/WorldLines.command   # 또는 WorldLines.sh
```

그런 다음 바탕화면 / Dock으로 끌어다 놓고, 다른 바로가기처럼 사용하세요.

### 중국 사용자 안내

일부 중국 본토 네트워크에서는 GitHub Releases와 Cloudflare 기반 도메인이
지연될 수 있습니다. `curl https://worldlines.gg/install.sh`가 타임아웃
된다면 다음을 시도해 보세요.

```bash
# GitHub 직접 다운로드(Cloudflare 리다이렉트보다 빠를 수 있습니다):
curl -LsSf \
  https://github.com/LudicDynamics/WorldLines/releases/latest/download/install.sh \
  | sh

# 또는 uv가 Tsinghua PyPI 미러를 사용하도록 강제:
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv tool install worldlines

# 또는 둘을 동시에:
CHINA_MIRROR=1 curl -LsSf https://worldlines.gg/install.sh | sh
```

자동 업데이트(`neonrp self-update`)는 `UV_DEFAULT_INDEX`를 존중하므로,
셸 프로필에 export 해 두면 이후 업그레이드도 계속 미러를 이용하게 됩니다.

### 개발자용 — editable 설치

```bash
uv tool install -e /path/to/worldlines
neonrp --help
```

모든 옵션(wheel, 소스, 대체 미러)은
[docs.worldlines.gg/docs/guides/launcher](https://docs.worldlines.gg/docs/guides/launcher)
를 참조하세요.

---

## 빠른 시작

```bash
# 새 디렉터리 — /init만으로 build 모드로 시작할 수 있습니다
mkdir my-world && cd my-world
neonrp init

# 또는 대표 샘플로 stoneford 스타터를 스캐폴딩
neonrp game new --template stoneford

# TUI 실행
neonrp tui
```

새 프로젝트는 패키지된 내장 스킬을 자동으로 노출합니다. `/game new`는
스타터 월드 + 플레이 agent 스캐폴드를 즉시 원할 때만 선택적으로
사용합니다.

> **첫 실행 시 런처가 API 설정을 안내합니다.** 이미 **Claude Code (MCP)**
> 가 있다면 그것을 선택하세요. 또는 **Anthropic / OpenAI / DeepSeek /
> OpenRouter / [GLM 무료 티어](https://zhipuai.cn)** 의 키를 붙여넣거나,
> **Ollama / LM Studio** 로컬 서버를 지정할 수도 있습니다. 키는
> `~/.neonrp/config.json`에 자동 저장되며, 나중에 `[3] settings / api`에서
> 변경할 수 있습니다.
> [전체 프로바이더 가이드 →](https://docs.worldlines.gg/docs/getting-started/quickstart)

`look around`를 입력하고 Enter를 눌러 보세요. 이것이 여러분의 첫
agentic 턴입니다.

<p align="center">
  <img src="./assets/gameplay.jpg" alt="WorldLines 플레이 — 안개 속에서 Stoneford에 도착" width="720" />
</p>

10분짜리 튜토리얼은
[docs.worldlines.gg/docs/getting-started/quickstart](https://docs.worldlines.gg/docs/getting-started/quickstart)
에 있습니다.

---

## 문서

전체 문서는 공식 사이트에 있습니다 — 이 저장소는 진입점만 유지합니다.

| 주제               | URL                                                                              |
|--------------------|----------------------------------------------------------------------------------|
| 시작하기           | [docs.worldlines.gg/docs/getting-started](https://docs.worldlines.gg/docs/getting-started) |
| 핵심 개념          | [docs.worldlines.gg/docs/core-concepts](https://docs.worldlines.gg/docs/core-concepts)（Worlds · 캐릭터 & Multi-Agent · Agents & 오케스트레이션 · 엔진 모드 · Sessions · 메모리 시스템） |
| 가이드             | [docs.worldlines.gg/docs/guides](https://docs.worldlines.gg/docs/guides)（Launcher · 월드 라이프사이클 · SillyTavern 임포트 · Discord 튜토리얼） |
| Q&A / 비교         | [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa)（vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph · vs OpenClaw） |
| Changelog・로드맵  | [docs.worldlines.gg/docs/changelog](https://docs.worldlines.gg/docs/changelog) |

**이 저장소 안:**

- [templates/stoneford-worldlines/](templates/stoneford-worldlines) — 샘플 월드 및 Agents（submodule）
- [CONTRIBUTING.ko.md](CONTRIBUTING.ko.md) — 기여 방법
- [SECURITY.md](SECURITY.md) — 보안 취약점 신고 방법
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — 커뮤니티 기대 사항
- [LICENSE](LICENSE) — 독점 프리뷰 조건

## 왜 AGPL 인가 —— 기여자에게 의미하는 것

WorldLines 의 오픈소스 영역(예: `templates/stoneford-worldlines/`)은 **AGPL-3.0** 입니다. AGPL 을 의도적으로 선택했습니다:

> AGPL 은 "소프트웨어를 배포한다"에서 "서비스로 운영한다"로 시대가 넘어간 뒤에도 의미를 잃지 않는, 사실상 유일한 보편 OSS 라이선스입니다. 수정된 WorldLines 를 호스팅 서비스로 운영하는 누구에게나 우리와 동일한 의무 —— 소스 공개 의무를 부과합니다.

PR 을 보내는 사람에게 의미:

- 🪪 **기여자는 자신의 기여에 대한 저작권을 유지합니다.** copyright assignment 를 요구하지 않습니다.
- 🟢 **기여는 기본적으로 AGPL-3.0 으로 OSS 프로젝트에 편입됩니다.** 별도 합의가 없는 한 다른 오픈소스 영역과 동일한 조건입니다.
- 🛡 **추가 라이선스 허가 없이 기여자 코드를 클로즈드소스 버전에 병합하지 않습니다.** 필요한 경우 기여자에게 별도로 확인합니다.

엔진 코어(`neonrp`)는 현재 proprietary preview 입니다 —— [CONTRIBUTING.md → License Asymmetry](CONTRIBUTING.md#license-asymmetry) 참고. 위 정책은 AGPL-3.0 영역에 적용됩니다.

## 커뮤니티 및 연락처

- 웹: [worldlines.gg](https://worldlines.gg) · 문서: [docs.worldlines.gg](https://docs.worldlines.gg)
- Discord: [discord.gg/HJYWbdqWrE](https://discord.gg/HJYWbdqWrE) · Patreon: [patreon.com/cw/WorldLines](https://www.patreon.com/cw/WorldLines)
- GitHub: [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)
- 연락처: `info@worldlines.gg`

---

## 저작권 및 감사

Copyright © 2026 **nikoloside**, **redoctober**. All rights reserved.

WorldLines는 독점 엔진이며, 평가 목적의 프리뷰로만 배포됩니다. 재사용,
재배포, 파생 저작물에 대한 라이선스는 부여되지 않습니다. 전체 조건은
[LICENSE](LICENSE)를 참조하세요.

**nikoloside**와 **redoctober**가 개발 및 유지보수를 담당하며, Ludic
Dynamics 커뮤니티가 지속적으로 운영, 실험, 발전시키고 있습니다.
`llm-rpg-starter` 전신의 초기 참여자(Ludic Dynamics 커뮤니티) 여러분의
관대하고 뜨거운 토론·교류·협업·지지에 특별히 감사드립니다 —
**Amber**, **琛琛**, **Claire**.

*WorldLines와 Ludic Dynamics는 Ludic Dynamics의 상표입니다.*
