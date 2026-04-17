# CLI リファレンス

**Language:** [English](./CLI_REFERENCE.md) · [简体中文](./CLI_REFERENCE.zh.md) · [日本語](./CLI_REFERENCE.ja.md) · [한국어](./CLI_REFERENCE.ko.md)

> ステータス: Beta — v0.1.0 のコマンドは安定。フラグはオプションが追加される可能性あり

`neonrp` コマンドラインツールの完全リファレンス。最新かつ正式なフラグ一覧は `neonrp <cmd> --help` で取得できます。

## コマンドマップ

| コマンド    | 用途                                             |
|-------------|--------------------------------------------------|
| `init`      | カレントディレクトリに `.neonrp/` を作成         |
| `game`      | スターター世界（templates）を展開                |
| `run`       | クエリを agent にディスパッチ                    |
| `save`      | 現在の状態を snapshot                            |
| `load`      | snapshot から復元                                |
| `branch`    | branch を作成 / 切替                             |
| `undo`      | head を 1 event 戻す                             |
| `redo`      | undo した event を再適用                         |
| `validate`  | `game/` を schema で検証                         |
| `index`     | エンティティインデックスを構築 / 更新            |
| `find`      | エンティティ検索                                 |
| `context`   | クエリに対する関連度ランキング                   |
| `agent`     | agent ライフサイクル                             |
| `import`    | SillyTavern / 外部カードのインポート             |
| `sandbox`   | sandbox 管理                                     |
| `replay`    | Replay と決定性検証                              |
| `tui`       | ターミナル UI を起動                             |

## プロジェクトライフサイクル

```bash
neonrp init
neonrp game new --template stoneford    # または: default / isekai / kagura-island
neonrp validate
neonrp index build
```

## プレイループ

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

## Agents

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent logs --tail 10
```

### Agent run オプション

| オプション      | 用途                                                            |
|-----------------|-----------------------------------------------------------------|
| `--query, -q`   | 指示内容（必須）                                                |
| `--provider`    | config の provider を上書き（glm/openai/lmstudio/ollama/stub）  |
| `--fixture`     | stub provider 用の proposal JSON ファイル                       |
| `--apply`       | プレビュー後に適用                                              |
| `--agentic`     | 多ターン agentic ループ                                         |
| `--json`        | 機械可読出力                                                    |

## 検索

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

## Import

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

## Sandbox

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force
```

## Replay

```bash
neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

## TUI

```bash
neonrp tui
neonrp tui --branch experiment
neonrp tui --provider lmstudio
neonrp tui --continue
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose
```

## 終了コード

| コード | 意味                                                         |
|--------|--------------------------------------------------------------|
| 0      | 成功                                                         |
| 1      | 一般エラー（検証失敗、not found など）                       |
| 2      | システムエラー（未初期化、アダプタ失敗）                     |

## 環境変数

| 変数                | 用途                          |
|---------------------|-------------------------------|
| `OPENAI_API_KEY`    | OpenAI                        |
| `GLM_API_KEY`       | Zhipu GLM                     |
| `ANTHROPIC_API_KEY` | Anthropic                     |
| `NEONRP_E2E_LLM`    | 実エンドポイントテスト有効化  |

プロジェクトルートの `.env` は自動で読み込まれます。

## 関連

- [TUI_GUIDE.ja.md](TUI_GUIDE.ja.md)
- [CONCEPTS.ja.md](CONCEPTS.ja.md)
