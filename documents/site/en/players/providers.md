---
title: "Connect a model"
description: "The local edition needs an LLM: use a Worldlines account, or your own key. Playing online? You can skip this page."
---

<!-- section: three -->
## Two ways to connect

**A Worldlines account**: type `/login` in the terminal game and sign in once in your browser (on a machine without a browser, use `/login code`). Signing in gives you two things:

- **the model relay**: no key of your own; new runs use Worldlines models by default;
- **the Jev judge**: decides when the talk in a planning beat is settled, in under a second (see [How a turn works](/docs/players/how-to-play)).

`/login status` shows whether you are signed in; `/login out` signs you out. The account is optional; the engine itself is free.

**Your own key**: pick a provider on the first run or in `/settings`, and paste the key:

| Provider | Get a key |
|---|---|
| OpenCode Zen | [opencode.ai/zen](https://opencode.ai/zen) |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| OpenRouter | [openrouter.ai](https://openrouter.ai/keys) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| Kimi (Moonshot) | [platform.kimi.ai](https://platform.kimi.ai) |
| GLM (Zhipu, has a free tier) | [zhipuai.cn](https://zhipuai.cn) |

**A custom OpenAI-compatible endpoint**: for local or self-hosted servers such as Ollama, LM Studio or vLLM, choose "Custom" in settings and fill in `base_url` and the model name.

The Claude Code preset of 0.4.x was removed in 1.0.3.

<!-- section: judge -->
## Who judges without an account

In two-beat play, someone has to decide when the talk is settled. Without an account, your run's own model decides: each planning beat takes a few seconds longer. You can always say 「定」 or `@dm` to move on without waiting for the judge.

<!-- section: where -->
## Where it is stored

Keys and model settings are stored in `~/.neonrp/config.json`, shared by the web UI and the terminal. Change them under "⚙" (settings) at the top right of the web UI, or with `/settings` in the terminal.

You can also leave the key out of settings and use environment variables. A key saved in settings is used first; without one, the engine looks for:

1. `NEONRP_LLM_API_KEY` (any provider; if set, it is used);
2. the provider's own variable, such as `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENCODE_ZEN_API_KEY`, `MOONSHOT_API_KEY`, `GLM_API_KEY`.

<!-- section: stall -->
## When the model stalls: the stream watchdog

Some providers occasionally accept a request and then sit on it (sending keep-alives but no tokens). The engine watches streamed calls: if the first token takes too long, or the gap between two tokens is too long, it drops the call and sends it again instead of waiting. Reasoning tokens count as progress; keep-alives do not.

| Environment variable | Default | What it does |
|---|---|---|
| `NEONRP_LLM_FIRST_TOKEN_S` | `20` | seconds to wait for the first token |
| `NEONRP_LLM_STALL_GAP_S` | `0` (off) | longest pause allowed between two tokens, in seconds; 0 = no mid-stream limit (a dead stream ends at the read timeout) |
| `NEONRP_LLM_STALL_RETRIES` | `2` | how many times a stalled call is sent again |
| `NEONRP_LLM_CHAT_VIA_STREAM` | on | one-shot calls without tools also go through the guarded stream; set `0` to turn this off |

With a slow or local model whose first token legitimately takes a while, raise `NEONRP_LLM_FIRST_TOKEN_S`. A reply that stalls halfway is not continued mid-sentence; the whole call starts over.
