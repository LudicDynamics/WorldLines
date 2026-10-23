---
title: "Quickstart"
description: "다운로드부터 첫 번째 살아있는 월드까지 — 런처, 브라우저, 또는 CLI."
---

<!-- section: launcher -->
## 1. 로컬 실행 — Web UI (권장)

가장 빠른 진입. WorldLines를 다운로드해 실행하면 **기본적으로 브라우저에 로컬 Web UI가 열립니다** — 터미널 설정이 필요 없습니다.

[worldlines.gg](https://worldlines.gg) → **Download**에서 OS에 맞는 설치 파일을 받으세요:

- **macOS**: `WorldLines.command`
- **Windows**: `WorldLines.bat`
- **Linux**: `WorldLines.sh` (`chmod +x` 후 실행)

자체 완결형입니다 — 필요하면 Python을 부트스트랩하고 로컬 Web UI를 엽니다. 세 개의 공식 월드가 바로 **import해서 플레이**할 수 있게 준비되어 있습니다:

- **Spice & Witch** — 향신료 대상 × 늙지 않는 마녀 × 마녀사냥
- **Kagura Island** (7 소울) — 일본풍 미스터리 · 타임 루프
- **Stoneford · Elena** — 기억을 잃은 히로인 + 동료 (Elena & Rowan)

셋 다 **멀티에이전트 마을** — world-agent가 독립된 소울 사회를 감싸는 형태입니다. 저장된 세션을 이어가거나, 직접 만들 수도 있습니다. 첫 실행 때 LLM 프로바이더 선택(5단계)을 안내하므로 `config.json`을 손으로 편집할 일은 없습니다.

<!-- section: tui -->
## 2. WorldLines TUI (터미널)

터미널을 선호하나요? 같은 엔진이 **WorldLines TUI**를 함께 제공합니다 — Claude Code 스타일의 대화형 터미널로, 플레이와 제작을 모두 할 수 있습니다.

```bash
pip install worldlines        # 또는: uv tool install worldlines
neonrp           # 터미널 런처: 월드를 고르고 플레이
```

이것도 로컬에서 실행되며, 완전한 멀티에이전트 마을을 플레이할 수 있습니다. 스크립트 가능한 고급 사용법은 6단계를 참고하세요.

<!-- section: webhub -->
## 3. Hub — 브라우저, 설치 불필요

아무것도 설치하고 싶지 않나요? [hub.worldlines.gg](https://hub.worldlines.gg)를 열고 로그인하여 플레이하세요. 클라우드 에이전트가 대신 실행하므로 별도 설정이 필요 없습니다.

- **월드**와 **소울** 카탈로그 탐색
- [Elena](https://hub.worldlines.gg/play/souls/elena) 같은 소울과 대화하거나, 더 가벼운 오케스트레이터 월드를 체험
- AI 지원 스튜디오로 직접 창작하고 공개 레지스트리에 게시

Hub는 현재 **fast**와 **orchestrator** 월드를 실행합니다. 완전한 **멀티에이전트 마을**(위 세 개의 공식 월드)은 로컬에서 실행됩니다 — Web UI 또는 TUI로.

<!-- section: worlds -->
## 4. 공식 월드

세 개의 공식 월드는 모두 **멀티에이전트 마을** — world-agent가 독립된 소울 사회를 감싸는 형태입니다. 각각 **Web UI**에서 import, **TUI**에서 플레이, 또는 **CLI**로 실행(6단계)할 수 있습니다.

| 월드 | 무엇인가 | 모드 |
|---|---|---|
| **Spice & Witch** | 향신료 대상 × 늙지 않는 마녀 × 마녀사냥 | multi-agent |
| **Kagura Island** | 일본풍 미스터리 · 타임 루프 · **독립된 7 소울** | multi-agent |
| **Stoneford · Elena** | 기억을 잃은 히로인 + 동료 · **Elena & Rowan** | multi-agent |

멀티에이전트 마을은 **로컬**(Web UI 또는 TUI)에서 실행됩니다. 브라우저에서 설치 없이 체험하려면 [Hub](https://hub.worldlines.gg)에서 더 가벼운 오케스트레이터 월드를 플레이하거나 소울과 대화하세요.

<!-- section: configure-provider -->
## 5. LLM 프로바이더 선택

WorldLines는 LLM 위에서 동작하며, 연결 방법은 **세 가지**가 있습니다. 어떤 방식을 선택하든 런처가 과정을 안내하므로 `config.json`을 직접 편집할 필요는 없습니다.

### 옵션 1: Claude Code (MCP) — API 키 불필요

[Claude Code](https://claude.com/claude-code)가 이미 설치되어 있다면, WorldLines는 MCP를 통해 Claude Code를 구동할 수 있습니다. 별도의 API 키도, 별도의 결제도 필요 없습니다. 런처가 프로바이더를 물을 때 **"Claude Code"**를 선택하면 끝입니다.

### 옵션 2: API 키를 사용하는 서드파티 프로바이더

최초 실행 시 런처가 프로바이더를 고르고 키를 붙여넣도록 안내합니다. 입력한 키는 `~/.neonrp/config.json`에 자동으로 저장되어 이후 실행마다 재사용됩니다.

| 프로바이더        | 키 발급 경로                                                                            | 비고                              |
|------------------|----------------------------------------------------------------------------------------|----------------------------------|
| **GLM-4-Flash**  | [zhipuai.cn](https://zhipuai.cn)                                                        | **무료 티어 제공**                 |
| Anthropic        | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)     | 종량제                            |
| OpenAI           | [platform.openai.com/api-keys](https://platform.openai.com/api-keys)                   | 종량제                            |
| DeepSeek         | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)               | 종량제                            |
| OpenRouter       | [openrouter.ai/keys](https://openrouter.ai/keys)                                        | 애그리게이터 — 키 하나로 여러 모델  |

### 옵션 3: OpenAI 호환 커스텀 엔드포인트

로컬 모델 서버(**Ollama**, **LM Studio**, **vLLM** 등)를 운영 중이거나 OpenAI 호환 백엔드를 직접 가지고 있다면, WorldLines가 해당 URL을 바라보도록 설정하면 됩니다. 클라우드 API 키는 필요하지 않습니다. 설정 플로우에서 **"Custom"**을 선택하고 `base_url`과 필요한 경우 인증 정보를 입력하세요.

---

**키가 저장되는 위치:** `~/.neonrp/config.json`, 그리고 설정해 두었다면 환경 변수(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GLM_API_KEY` 등)에도 저장됩니다. 런처는 환경 변수를 먼저 읽고, 그다음 설정 파일을 읽습니다.

**나중에 바꾸고 싶다면:** 런처 메뉴에서 `[3] settings / api`를 선택해 모델을 추가하거나 기본값을 바꾸고, 연결을 테스트할 수 있습니다.

<!-- section: advanced-cli -->
## 6. 고급 — CLI (개발자 / 연구자)

터미널을 선호하거나 실험을 위한 스크립트 가능한 harness가 필요한가요? 같은 엔진이 `worldlines` CLI로도 제공됩니다.

```bash
pip install worldlines        # 또는: uv tool install worldlines
# 또는 원라인 인스톨러 (macOS / Linux / WSL):
curl -fsSL https://worldlines.gg/install.sh | sh
```

TUI를 열거나, 저장소에서 바로 예제 월드를 실행하세요:

```bash
neonrp           # 터미널 런처: 월드를 고르고 플레이

git clone https://github.com/LudicDynamics/WorldLines.git && cd WorldLines

# 내장된 두 세계 (다른 공식 세계는 로컬 Hub에서 로그인해 받기):
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # 그레이오크 저택
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # 스톤포드

# 오케스트레이터 월드도 (Hub에서도 플레이 가능):
neonrp tui --from examples/orch/stoneford
```

**턴 진행:** `look around`를 입력하세요. world-agent가 내레이션하고 적절한 sub-agent로 라우팅합니다 — 또는 멀티에이전트 월드라면 장면에 있는 소울들을 깨웁니다. thinking 스트림, 파일을 읽는 tool-use, 내레이션, 그리고 로그에 추가된 새 **event**가 보입니다.

**저장 · branch · 되감기:** `/save opening-scene`으로 체크포인트, `/branch try-stealing`으로 위험한 경로를 새 branch에서 탐험, `/undo`로 되감기, `neonrp load opening-scene`으로 복원합니다. main branch는 그대로 유지됩니다.

Python 3.11+ (3.12 권장)와 256-컬러 UTF-8 터미널이 필요합니다.

<!-- section: what-next -->
## 다음에 할 일

- [Core Concepts](/docs/core-concepts/worlds) — 세계가 어떻게 기억하는가: event, snapshot, branch
- Web UI에서 공식 월드를 **import해서 플레이**한 뒤 Create 스튜디오에서 손봐 보세요
- **[WebHub에서 플레이](https://hub.worldlines.gg)** — [Elena](https://hub.worldlines.gg/play/souls/elena) 같은 멀티에이전트 소울 포함
- 고급 (CLI): [CLI Reference](/docs/guides/world-editor) — `/mode build`, JSON 직접 편집, 모든 서브커맨드
