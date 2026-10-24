---
title: "接模型"
description: "本地版需要一个大模型:用 Worldlines 账号,或者填你自己的 key。在线玩不用管这一页。"
---

<!-- section: three -->
## 两种接法

**Worldlines 账号**:在终端游戏里敲 `/login`,浏览器里登录一次就好(没有浏览器的机器用 `/login code`)。登录后有两样东西:

- **模型中转**:不用自己的 key,新开的局默认走 Worldlines 的模型;
- **Jev 判官**:判断商量拍谈没谈妥,一秒内出结果(见[一回合怎么走](/docs/players/how-to-play))。

`/login status` 看登录状态,`/login out` 退出。账号是可选的,引擎本身免费。

**你自己的 key**:首次运行或 `/settings` 里选一个,填 key:

| Provider | 去哪拿 key |
|---|---|
| OpenCode Zen | [opencode.ai/zen](https://opencode.ai/zen) |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| OpenRouter | [openrouter.ai](https://openrouter.ai/keys) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| Kimi(Moonshot) | [platform.kimi.ai](https://platform.kimi.ai) |
| GLM(智谱,有免费档) | [zhipuai.cn](https://zhipuai.cn) |

**OpenAI 兼容的自定义端点**:Ollama、LM Studio、vLLM 这类本地或自建服务,在设置里选「Custom」,填 `base_url` 和模型名。

0.4.x 里的 Claude Code 预设在 1.0.3 去掉了。

<!-- section: judge -->
## 没有账号时谁来判断

两拍玩法里,「商量谈妥了没有」要有人判断。没登录时,由你这局自己的模型来判断:每个商量拍会多花几秒。你随时可以说「定」或 `@dm`,不等判断直接推进。

<!-- section: where -->
## 存在哪

key 和模型设置存在 `~/.neonrp/config.json`,网页和终端共用。网页上在右上角「⚙ 设置」里改,终端里用 `/settings`。

也可以不在设置里填,改用环境变量。设置里填过 key 的,用填的那个;没填时按这个顺序找:

1. `NEONRP_LLM_API_KEY`(不分 provider,设了就用它);
2. 各家自己的变量,比如 `DEEPSEEK_API_KEY`、`OPENROUTER_API_KEY`、`ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`OPENCODE_ZEN_API_KEY`、`MOONSHOT_API_KEY`、`GLM_API_KEY`。

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
