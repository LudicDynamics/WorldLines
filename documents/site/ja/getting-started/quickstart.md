---
title: "クイックスタート"
description: "ダウンロードから最初の生きた世界まで —— ランチャー、ブラウザ、または CLI。"
---

<!-- section: launcher -->
## 1. ローカルで動かす —— Web UI（推奨）

いちばん速い入り口。WorldLines をダウンロードして実行すると、**既定でブラウザにローカル Web UI が開きます** —— ターミナルの設定は不要。

[worldlines.gg](https://worldlines.gg) → **Download** から、お使いの OS 向けのインストーラを入手:

- **macOS**: `WorldLines.command`
- **Windows**: `WorldLines.bat`
- **Linux**: `WorldLines.sh`（`chmod +x` してから実行）

自己完結型で、必要に応じて Python をブートストラップし、ローカル Web UI を開きます。3 つの公式世界はすぐそこにあり、**インポートしてプレイ** できます:

- **Spice & Witch** — スパイス隊商 × 不老の魔女 × 魔女狩り
- **Kagura Island**（7 ソウル）— 和風ミステリー · タイムループ
- **Stoneford · Elena** — 記憶を失ったヒロイン + 相棒（Elena & Rowan）

3 つとも **マルチエージェントの村** —— 独立したソウルの社会を包む world-agent です。セーブしたセッションの続行や、自作も可能です。初回起動では LLM プロバイダ選び（ステップ 5）を案内するので、`config.json` を手で編集することはありません。

<!-- section: tui -->
## 2. WorldLines TUI（ターミナル）

ターミナルが好み? 同じエンジンが **WorldLines TUI** を同梱しています —— Claude Code スタイルの対話型ターミナルで、プレイも構築もできます。

```bash
pip install worldlines        # または: uv tool install worldlines
neonrp           # ターミナルのランチャー:ワールドを選んでプレイ
```

これもローカルで動き、完全なマルチエージェントの村を遊べます。スクリプタブルな上級用途はステップ 6 を参照。

<!-- section: webhub -->
## 3. Hub — ブラウザ、インストール不要

何もインストールしたくない? [hub.worldlines.gg](https://hub.worldlines.gg) を開き、サインインして遊ぶ。クラウドエージェントが動かしてくれるので、設定は要りません。

- **世界** と **ソウル** のカタログを閲覧
- [Elena](https://hub.worldlines.gg/play/souls/elena) のようなソウルと話す、あるいは軽量なオーケストレーション世界を試す
- AI 支援スタジオで自作し、公開レジストリに登録

Hub は現在 **fast** と **orchestrator** の世界を動かします。完全な **マルチエージェントの村**（上記 3 つの公式世界）はローカルで動きます —— Web UI または TUI で。

<!-- section: worlds -->
## 4. 公式の世界

3 つの公式世界はすべて **マルチエージェントの村** —— 独立したソウルの社会を包む world-agent です。それぞれ **Web UI** でインポート、**TUI** でプレイ、または **CLI** から実行（ステップ 6）できます。

| 世界 | 内容 | モード |
|---|---|---|
| **Spice & Witch** | スパイス隊商 × 不老の魔女 × 魔女狩り | multi-agent |
| **Kagura Island** | 和風ミステリー · タイムループ · **7 つの独立したソウル** | multi-agent |
| **Stoneford · Elena** | 記憶を失ったヒロイン + 相棒 · **Elena & Rowan** | multi-agent |

マルチエージェントの村は **ローカル**（Web UI または TUI）で動きます。ブラウザでインストール不要で試すなら、[Hub](https://hub.worldlines.gg) で軽量なオーケストレーション世界を遊ぶか、ソウルと話してください。

<!-- section: configure-provider -->
## 5. LLM プロバイダを選ぶ

WorldLines は LLM の上で動作し、接続方法は **3 つ** あります。どれを選んでもランチャーが案内してくれる——`config.json` を手で編集する必要はありません。

### Option 1: Claude Code (MCP) —— API キー不要

すでに [Claude Code](https://claude.com/claude-code) をインストール済みなら、WorldLines は MCP 経由でそれを駆動できます。別の API キーも別の課金も不要。ランチャーでプロバイダを訊かれたら **「Claude Code」** を選ぶだけ——完了です。

### Option 2: API キー付きのサードパーティプロバイダ

初回起動時に、ランチャーがプロバイダを選んでキーを貼り付けるよう促します。キーは自動で `~/.neonrp/config.json` に保存され、次回以降は再利用されます。

| プロバイダ         | キー取得先                                                                              | 備考                         |
|-------------------|----------------------------------------------------------------------------------------|------------------------------|
| **GLM-4-Flash**   | [zhipuai.cn](https://zhipuai.cn)                                                        | **無料枠あり**               |
| Anthropic         | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)     | 従量課金                     |
| OpenAI            | [platform.openai.com/api-keys](https://platform.openai.com/api-keys)                   | 従量課金                     |
| DeepSeek          | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)               | 従量課金                     |
| OpenRouter        | [openrouter.ai/keys](https://openrouter.ai/keys)                                        | アグリゲーター——キー 1 つで多数のモデル |

### Option 3: OpenAI 互換のカスタムエンドポイント

ローカルのモデルサーバ（**Ollama**、**LM Studio**、**vLLM** など）や自前の OpenAI 互換バックエンドを動かしているなら、WorldLines をその URL に向けます。クラウドの API キーは不要。設定フローで **「Custom」** を選び、`base_url` と任意の認証情報を入力してください。

---

**キーの保存先:** `~/.neonrp/config.json`、および設定している場合は環境変数（`ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`GLM_API_KEY` など）。ランチャーはまず環境変数を読み、次に設定ファイルを読みます。

**後から変更したいとき:** ランチャーのメニューで `[3] settings / api` を選ぶと、モデルの追加、デフォルトの切り替え、接続テストができます。

<!-- section: advanced-cli -->
## 6. 上級者向け — CLI（開発者 / 研究者）

ターミナルが好み、あるいは実験用のスクリプタブルな harness が欲しいですか? 同じエンジンが `worldlines` CLI を同梱しています。

```bash
pip install worldlines        # または: uv tool install worldlines
# あるいはワンラインインストーラー（macOS / Linux / WSL）:
curl -fsSL https://worldlines.gg/install.sh | sh
```

TUI を開く、あるいはリポジトリから直接サンプル世界を実行します:

```bash
neonrp           # ターミナルのランチャー:ワールドを選んでプレイ

git clone https://github.com/LudicDynamics/WorldLines.git && cd WorldLines

# 内蔵の 2 つの世界（ほかの公式の世界はローカルの Hub でログインして入手）:
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # グレイオーク館
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # ストーンフォード

# オーケストレーション型の世界も（これらは Hub でも遊べます）:
neonrp tui --from examples/orch/stoneford
```

**ターンを進める:** `look around` と入力。world-agent が語り、適切なサブ agent にルーティングします —— マルチエージェントの世界なら、シーンにいるソウルたちを起こします。thinking ストリーム、ファイル読み込み時の tool-use、物語、そしてログに追加される新しい **event** が見えます。

**Save · branch · rewind:** `/save opening-scene` でチェックポイント; `/branch try-stealing` で危険な道を新しいブランチで試す; `/undo` で巻き戻し; `neonrp load opening-scene` で復元。main ブランチは無傷のままです。

Python 3.11+（3.12 推奨）と 256 色 UTF-8 ターミナルが必要です。

<!-- section: what-next -->
## 次は何を

- [コアコンセプト](/docs/core-concepts/worlds) — 世界はどう覚えるか: Event、Snapshot、Branch
- 公式の世界を Web UI で **インポートしてプレイ**、Create スタジオで手を入れる
- **[WebHub でプレイ](https://hub.worldlines.gg)** —— [Elena](https://hub.worldlines.gg/play/souls/elena) のようなマルチエージェントのソウルも含む
- 上級者向け（CLI）: [CLI リファレンス](/docs/guides/world-editor) — `/mode build`、JSON を直接編集、全サブコマンド
