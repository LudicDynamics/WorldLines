---
title: "Model providers"
description: "WorldLines needs an LLM. The first run walks you through it; keys are saved to ~/.neonrp/config.json."
---

<!-- section: three -->
## Three ways to connect

> **Status: ships with 1.0**

**A Worldlines account** — `/login` inside the game: the model relay and the Jev judge, no key of your own. (The Claude Code preset of 0.4.x is gone since 1.0.3.)

**A third-party provider + API key**:

| Provider | Get a key |
|---|---|
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| GLM | [zhipuai.cn](https://zhipuai.cn) |
| OpenRouter | [openrouter.ai](https://openrouter.ai/keys) |

**A custom OpenAI-compatible endpoint** — Ollama, LM Studio, vLLM, etc.; just fill in `base_url`.

<!-- section: where -->
## Where it is stored

`~/.neonrp/config.json`, plus environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …), which take precedence. To change it later, switch the default provider or test the connection in settings.

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
