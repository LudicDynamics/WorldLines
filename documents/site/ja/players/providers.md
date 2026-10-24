---
title: "モデルをつなぐ"
description: "ローカル版には LLM が必要です。Worldlines アカウントを使うか、自分のキーを入れます。オンラインで遊ぶなら、このページは読まなくてかまいません。"
---

<!-- section: three -->
## つなぎ方は二つ

**Worldlines アカウント**:ターミナルのゲーム内で `/login` と入力し、ブラウザで一度ログインします(ブラウザのないマシンでは `/login code`)。ログインすると二つのものが使えます。

- **モデル中継**:自分のキーは不要で、新しい一局は既定で Worldlines のモデルを使います;
- **判定役 Jev**:相談の拍で話がまとまったかを 1 秒以内に判定します([1 ターンの流れ](/docs/players/how-to-play) を参照)。

`/login status` でログイン状態を確認し、`/login out` でログアウトします。アカウントは任意で、エンジン自体は無料です。

**自分のキー**:最初の起動時か `/settings` でプロバイダーを選び、キーを貼り付けます。

| プロバイダー | キーの入手先 |
|---|---|
| OpenCode Zen | [opencode.ai/zen](https://opencode.ai/zen) |
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| OpenRouter | [openrouter.ai](https://openrouter.ai/keys) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| Kimi(Moonshot) | [platform.kimi.ai](https://platform.kimi.ai) |
| GLM(智譜、無料枠あり) | [zhipuai.cn](https://zhipuai.cn) |

**OpenAI 互換のカスタムエンドポイント**:Ollama、LM Studio、vLLM のようなローカルまたは自前のサーバーは、設定で「カスタム」を選び、`base_url` とモデル名を入れます。

0.4.x にあった Claude Code プリセットは 1.0.3 で削除されました。

<!-- section: judge -->
## アカウントなしでは誰が判定するか

二拍のプレイでは、話がまとまったかを誰かが判定しなければなりません。アカウントがないときは、その一局自身のモデルが判定します。相談の拍ごとに数秒長くかかります。判定を待たずに進めたいときは、いつでも「決まり」か `@dm` と言えます。

<!-- section: where -->
## 保存場所

キーとモデル設定は `~/.neonrp/config.json` に保存され、Web UI とターミナルで共有されます。変更は Web UI の右上「⚙」(設定)から、またはターミナルの `/settings` で行います。

設定にキーを入れず、環境変数を使うこともできます。設定に保存したキーが最優先です。なければエンジンは次の順に探します。

1. `NEONRP_LLM_API_KEY`(プロバイダーを問わず、設定されていればこれを使う);
2. 各プロバイダー固有の変数。`DEEPSEEK_API_KEY`、`OPENROUTER_API_KEY`、`ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`OPENCODE_ZEN_API_KEY`、`MOONSHOT_API_KEY`、`GLM_API_KEY` など。

<!-- section: stall -->
## モデルが止まったとき:ストリームの監視

プロバイダーによっては、リクエストを受け付けたまま何も返さないことがあります(キープアライブだけを送り、トークンを送らない)。エンジンはストリーミング呼び出しを監視します。最初のトークンが遅すぎるか、トークンとトークンの間隔が長すぎるときは、待ち続けずにその呼び出しを打ち切って送り直します。推論トークンは進行として数え、キープアライブは数えません。

| 環境変数 | 既定 | 働き |
|---|---|---|
| `NEONRP_LLM_FIRST_TOKEN_S` | `20` | 最初のトークンを待つ秒数 |
| `NEONRP_LLM_STALL_GAP_S` | `0`(オフ) | トークン間に許す最長の間隔(秒)。0 = 途中は制限なし(本当に切れたストリームは読み取りタイムアウトで終わる) |
| `NEONRP_LLM_STALL_RETRIES` | `2` | 止まった呼び出しを送り直す回数 |
| `NEONRP_LLM_CHAT_VIA_STREAM` | オン | ツールなしの一回きりの呼び出しも監視つきのストリームを通す。`0` でオフ |

最初のトークンまで本当に時間がかかる遅いモデルやローカルモデルでは、`NEONRP_LLM_FIRST_TOKEN_S` を大きくします。途中で止まった返答は文の途中から続けず、呼び出し全体をやり直します。
