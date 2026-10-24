---
title: "모델 연결"
description: "로컬판에는 LLM이 필요합니다. Worldlines 계정을 쓰거나 내 키를 넣습니다. 온라인으로 플레이한다면 이 페이지는 건너뛰어도 됩니다."
---

<!-- section: three -->
## 두 가지 연결 방법

**Worldlines 계정**: 터미널 게임에서 `/login`을 입력하고 브라우저에서 한 번 로그인합니다(브라우저가 없는 기기에서는 `/login code`). 로그인하면 두 가지를 얻습니다.

- **모델 중계**: 내 키가 필요 없고, 새 판은 기본으로 Worldlines 모델을 씁니다.
- **판정자 Jev**: 상의 박자의 이야기가 정리됐는지를 1초 안에 판정합니다([한 턴의 진행](/docs/players/how-to-play) 참고).

`/login status`는 로그인 상태를 보여 주고, `/login out`은 로그아웃합니다. 계정은 선택 사항이며, 엔진 자체는 무료입니다.

**내 키**: 처음 실행할 때나 `/settings`에서 제공자를 하나 고르고 키를 붙여 넣습니다.

| 제공자 | 키 받는 곳 |
|---|---|
| OpenCode Zen | [opencode.ai/zen](https://opencode.ai/zen) |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| OpenRouter | [openrouter.ai](https://openrouter.ai/keys) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| Kimi(Moonshot) | [platform.kimi.ai](https://platform.kimi.ai) |
| GLM(Zhipu, 무료 등급 있음) | [zhipuai.cn](https://zhipuai.cn) |

**OpenAI 호환 사용자 정의 엔드포인트**: Ollama, LM Studio, vLLM 같은 로컬 또는 자체 호스팅 서버는 설정에서 「사용자 정의」를 고르고 `base_url`과 모델 이름을 넣습니다.

0.4.x에 있던 Claude Code 프리셋은 1.0.3에서 제거되었습니다.

<!-- section: judge -->
## 계정이 없을 때 누가 판정하나

두 박자 플레이에서는 이야기가 정리됐는지를 누군가 판정해야 합니다. 계정이 없으면 그 판의 모델이 판정하며, 상의 박자마다 몇 초가 더 걸립니다. 판정자를 기다리지 않고 넘어가려면 언제든 「결정」이라고 말하거나 `@dm`을 입력하면 됩니다.

<!-- section: where -->
## 저장되는 곳

키와 모델 설정은 `~/.neonrp/config.json`에 저장되며, 웹과 터미널이 함께 씁니다. 웹에서는 오른쪽 위 「⚙」(설정)에서, 터미널에서는 `/settings`로 바꿉니다.

설정에 키를 넣지 않고 환경 변수를 쓸 수도 있습니다. 설정에 저장한 키가 먼저 쓰이고, 없으면 엔진은 다음 순서로 찾습니다.

1. `NEONRP_LLM_API_KEY`(제공자와 관계없이, 설정되어 있으면 이것을 씀);
2. 제공자별 변수. 예: `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_ZEN_API_KEY`, `MOONSHOT_API_KEY`, `GLM_API_KEY`.

<!-- section: stall -->
## 모델이 멈출 때: 스트림 워치독

일부 제공자는 요청을 받아 놓고 한참 아무 토큰도 보내지 않을 때가 있습니다(keep-alive만 보내고 토큰은 없음). 엔진은 스트리밍 호출을 지켜봅니다. 첫 토큰이 너무 늦거나 두 토큰 사이의 간격이 너무 길면 기다리지 않고 그 호출을 끊고 다시 보냅니다. 추론(reasoning) 토큰은 진행으로 치고, keep-alive는 치지 않습니다.

| 환경 변수 | 기본값 | 역할 |
|---|---|---|
| `NEONRP_LLM_FIRST_TOKEN_S` | `20` | 첫 토큰을 기다리는 최대 초 |
| `NEONRP_LLM_STALL_GAP_S` | `0`(끔) | 두 토큰 사이에 허용하는 최대 멈춤(초). 0 = 중간 제한 없음(정말 끊긴 스트림은 읽기 시간 초과로 끝남) |
| `NEONRP_LLM_STALL_RETRIES` | `2` | 멈춘 호출을 다시 보내는 횟수 |
| `NEONRP_LLM_CHAT_VIA_STREAM` | 켬 | 도구 없는 일회성 호출도 워치독이 지키는 스트림으로 보냄. `0`으로 끔 |

느린 모델이나 로컬 모델처럼 첫 토큰이 원래 오래 걸리는 경우에는 `NEONRP_LLM_FIRST_TOKEN_S`를 올리세요. 중간에 멈춘 응답은 문장 중간부터 이어 쓰지 않고 호출 전체를 처음부터 다시 합니다.
