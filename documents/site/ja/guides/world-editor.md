---
title: "CLI リファレンス"
description: "必須の `neonrp` コマンド集。正式なフラグ一覧は `worldlines <cmd> --help` を参照してください。"
---

<!-- section: overview -->
## コマンド概要

| コマンド    | 用途                                             |
|-------------|--------------------------------------------------|
| `init`      | カレントディレクトリに `.neonrp/` を作成         |
| `game`      | スターター世界の雛形作成（テンプレート）         |
| `run`       | クエリを Agent にディスパッチ                    |
| `save`      | 現在のステートを Snapshot                        |
| `load`      | Snapshot から復元                                |
| `branch`    | Branch の作成・切り替え                          |
| `undo`      | head を 1 イベント戻す                           |
| `redo`      | Undo したイベントを再適用                        |
| `validate`  | `game/` をスキーマに照らして検証                |
| `index`     | エンティティインデックスの作成 / 更新             |
| `find`      | エンティティ検索                                 |
| `context`   | クエリに対するランク付きの関連度                 |
| `agent`     | Agent のライフサイクル（new / list / show / run / apply / logs / context / path） |
| `import`    | SillyTavern / 外部カードのインポート             |
| `sandbox`   | Sandbox 管理                                     |
| `replay`    | Replay と決定性検証                              |
| `tui`       | ターミナル UI の起動                             |

<!-- section: project -->
## プロジェクトのライフサイクル

```bash
worldlines init                           # .neonrp/ を作成
neonrp game new --template stoneford-orch  # templates: default / kagura-island / soul-talk / stoneford-elena / stoneford-orch
neonrp validate                       # game/ のスキーマチェック
neonrp index build                    # リトリーバルインデックスを再構築
```

<!-- section: play-loop -->
## プレイループ

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp load checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

<!-- section: agents -->
## Agent

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent path town-agent                            # Agent ディレクトリを出力
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent apply town-agent --proposal proposal.json --dry-run
neonrp agent context town-agent --query "harbor" --limit 8
neonrp agent logs --tail 10
```

### `agent run` のオプション

| オプション       | 用途                                                |
|------------------|-----------------------------------------------------|
| `--query`, `-q` | 指示内容（必須）                                    |
| `--provider`   | 設定のプロバイダーを上書き（glm / openai / lmstudio / ollama / stub） |
| `--fixture`    | stub プロバイダー用の proposal JSON ファイル        |
| `--apply`      | プレビュー後に適用                                  |
| `--json`       | 機械可読な出力                                      |

<!-- section: retrieval -->
## リトリーバル

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

`find` はエンティティ検索を行い、`context` はクエリに対してランク付けされた関連エンティティを返します（embedding が設定されている場合はハイブリッド fuzzy + ベクター検索）。

<!-- section: import -->
## インポート

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

SillyTavern キャラクターカード（JSON または tEXt 付き PNG）を取り込みます。[SillyTavern インポートガイド](/docs/guides/sillytavern-import) を参照してください。

<!-- section: sandbox-replay -->
## Sandbox と Replay

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force

neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

<!-- section: tui -->
## TUI — 起動フラグ

```bash
neonrp tui                               # デフォルト
neonrp tui --branch experiment           # 特定ブランチ
neonrp tui --provider lmstudio           # プロバイダー上書き
neonrp tui --continue                    # 直近のセッションを再開
neonrp tui --new                         # 新規セッションを強制
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose                     # 生の LLM トラフィックをストリーム
```

<!-- section: slash-commands -->
## TUI — スラッシュコマンド

TUI 内では `/<cmd>` がアクションを発動します。全一覧:

### セッションと履歴

| コマンド     | 用途                                                    |
|--------------|---------------------------------------------------------|
| `/new`       | 新規会話セッションを開始                                |
| `/continue`  | 現在のブランチの前回会話を再開                          |
| `/sessions`  | 保存されたブランチごとのセッションを一覧                |
| `/clear`     | 会話履歴をクリア                                        |
| `/copy`      | 会話をクリップボードにコピー                            |
| `/compact`   | 会話履歴をコンパクト化                                  |
| `/stats`     | 会話の統計情報を表示                                    |
| `/files`     | 最近変更されたファイルを一覧                            |

### 世界とステート

| コマンド                                | 用途                                              |
|----------------------------------------|---------------------------------------------------|
| `/init`                                | カレントディレクトリにプロジェクトを初期化        |
| `/game new`                            | テンプレートから新しい世界の雛形を作成            |
| `/worlds`                              | `~/.worldlines/games/` 配下の世界を一覧          |
| `/worldlines`                          | ガイド付き世界ピッカー（モデル + 世界 + 起動）   |
| `/save [name]`                         | ステートを Snapshot                               |
| `/load [name]`                         | Snapshot から復元                                 |
| `/branch [name\|list]`                 | ブランチの作成 / 切り替え / 一覧                  |
| `/undo` · `/redo`                       | head を 1 イベント戻す / 進める                   |
| `/sandbox [new\|list\|switch\|drop]`     | Sandbox を管理                                    |
| `/validate`                            | `game/` をスキーマに対して検証                   |
| `/index [build\|update]`                | リトリーバルインデックスを再構築 / 更新           |
| `/find <keyword>`                      | エンティティを検索                                |
| `/context <query>`                     | クエリに対するランク付きの関連度                  |
| `/export-world [output.zip]`           | `game/` + `.neonrp/` を .zip にまとめる         |
| `/load-world <zip>`                    | エクスポート済み zip を `~/.worldlines/games/` に復元 |
| `/import sillytavern-card <file>`      | SillyTavern のキャラクターカードをインポート      |
| `/replay [verify\|checkout]`            | Replay 検証                                       |

### モードとルーティング

| コマンド                                         | 用途                                              |
|-------------------------------------------------|---------------------------------------------------|
| `/mode [build\|sandbox\|play]`                   | プレイモードの切り替え                            |
| `/router-mode [fast\|orchestrator\|multi-agent]` | Router 実行モードの切り替え                       |
| `/autoapply [on\|off\|status]`                    | Sandbox の自動適用を切り替え                      |
| `/verbose [on\|off\|status]`                      | 詳細デバッグモードを切り替え                      |
| `/debug`                                        | MCP デバッグモードを切り替え                      |

### Agent と実行

| コマンド                                                                       | 用途                                                  |
|-------------------------------------------------------------------------------|-------------------------------------------------------|
| `/run <query>`                                                                | Agent クエリを明示的に実行                            |
| `/agent [list\|show <name>\|run <name>\|new <name>]`                            | Agent のライフサイクル                                |
| `/apply`                                                                      | Sandbox モードで保留中の Proposal を適用              |
| `/skills`                                                                     | 利用可能な Skill を一覧                               |

### プロバイダーと設定

| コマンド                                                             | 用途                                                |
|---------------------------------------------------------------------|-----------------------------------------------------|
| `/models [name\|list\|set <name>\|show <name>]`                      | モデルのクイック切り替え                            |
| `/auth [list\|add\|set\|rm\|show]`                                   | 名前付きモデル設定の管理                            |
| `/wl-model [preset]`                                               | WorldLines モデルプリセットを切り替え（glm / opus）|
| `/config [show\|set <key> <value>]`                                 | 設定の表示 / 設定                                   |
| `/settings`                                                         | 統一された model / api key / discord 設定を開く    |
| `/locale [auto\|en\|zh\|ja\|ko]`                                    | UI 言語の切り替え                                   |
| `/mcp [status\|restart <server>]`                                   | MCP サーバーの管理                                  |
| `/bridge [status\|start <name>\|stop <name>]`                        | 実行時に Discord / Telegram ブリッジを管理          |
| `/update [check\|apply\|status\|channel <name>]`                     | worldlines の更新を確認 / 適用                          |

### メタ

| コマンド        | 用途                                      |
|-----------------|-------------------------------------------|
| `/help`        | ヘルプを表示                              |
| `/quit` · `/q`  | TUI を終了                                |

<!-- section: exit-codes -->
## 終了コード

| コード | 意味                                                |
|--------|-----------------------------------------------------|
| 0      | 成功                                                |
| 1      | 一般的なエラー（検証失敗、未検出 など）             |
| 2      | システムエラー（未初期化、アダプター障害）          |

<!-- section: env -->
## 環境変数

| 変数                | 用途                          |
|---------------------|-------------------------------|
| `OPENAI_API_KEY`    | OpenAI                        |
| `GLM_API_KEY`       | Zhipu GLM                     |
| `ANTHROPIC_API_KEY` | Anthropic                     |
| `NEONRP_E2E_LLM`    | 実エンドポイントテストを有効化 |

プロジェクトルートの `.env` は自動読み込みされます。
