---
title: "设置模型提供商"
description: "WorldLines 需要一个 LLM。首次运行会引导你设置,密钥保存在 ~/.neonrp/config.json。"
---

<!-- section: three -->
## 三种接法

> **状态:随 1.0 发布**

**Claude Code(MCP)** —— 已经装了 Claude Code 的话,选它即可,不需要另外的 API key。

**第三方 provider + API key**:

| Provider | 获取 key |
|---|---|
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| GLM | [zhipuai.cn](https://zhipuai.cn) |
| OpenRouter | [openrouter.ai](https://openrouter.ai/keys) |

**OpenAI 兼容的自定义端点** —— Ollama、LM Studio、vLLM 等,填 `base_url` 即可。

<!-- section: where -->
## 存在哪

`~/.neonrp/config.json`,以及环境变量(`ANTHROPIC_API_KEY`、`OPENAI_API_KEY` 等)。环境变量优先。之后想改,在设置里切换默认提供商或测试连接。

<!-- section: stall -->
## 模型卡住时:流式看门狗

有些 provider 偶尔会接了请求却迟迟不出字(只发保活、不发 token)。引擎对流式调用设了看门狗:第一个 token 迟迟不来、或两个 token 之间停太久,就断开这次调用重发,不干等。思考(reasoning)token 也算在出字;保活不算。

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `NEONRP_LLM_FIRST_TOKEN_S` | `20` | 第一个 token 之前最多等多少秒 |
| `NEONRP_LLM_STALL_GAP_S` | `0`(关) | 两个 token 之间最多停多少秒;0 = 中途不限(真断掉的流由读超时结束) |
| `NEONRP_LLM_STALL_RETRIES` | `2` | 卡住后重发几次 |
| `NEONRP_LLM_CHAT_VIA_STREAM` | 开 | 不带工具的一次性调用也改走受看门狗保护的流;设 `0` 关闭 |

用慢模型或本地模型、第一个字本来就要等很久时,把 `NEONRP_LLM_FIRST_TOKEN_S` 调大。已经出了一半字才卡住的,不会续写半句,而是整次重来。
