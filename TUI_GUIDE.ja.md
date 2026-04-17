# TUI ガイド

**Language:** [English](./TUI_GUIDE.md) · [简体中文](./TUI_GUIDE.zh.md) · [日本語](./TUI_GUIDE.ja.md) · [한국어](./TUI_GUIDE.ko.md)

> ステータス: Beta — レイアウトは安定。キーバインドは v0.2 で設定可能に

WorldLines の TUI はプレイと世界構築の両方に使える Claude-Code 風の会話型ターミナルです。

## 起動

```bash
neonrp tui                               # デフォルト
neonrp tui --branch experiment           # 特定 branch
neonrp tui --provider lmstudio           # provider 上書き
neonrp tui --continue                    # 前回セッション再開
neonrp tui --new                         # 強制新セッション（デフォルト）
neonrp tui --import-card card.png        # 最初のターン前にインポート
neonrp tui --verbose                     # 生 LLM トラフィックをストリーム
```

`init` のみのディレクトリでもすぐに build モードに入れます。`game new` は任意で、デフォルト世界と play-agent 足場を追加するだけです。

## レイアウト

上部に単一ペインの会話 transcript、下部に入力行、右上にステータスバー。

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Transcript                                                     │
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
├─────────────────────────────────────────────────────────────────┤
│ q Quit │ Ctrl+K Commands │ Esc Interrupt │ F6 Copy              │
└─────────────────────────────────────────────────────────────────┘
```

## モード

`/mode <name>` で切替:

| モード    | 挙動                                                          |
|-----------|---------------------------------------------------------------|
| `build`   | 直接ファイル編集 + 自然なナレーション。制作向け。             |
| `sandbox` | Proposal パイプライン。すべての変更に承認が必要。             |
| `play`    | GM モード。auto-apply ON、完全没入。                          |

## スラッシュコマンド

| コマンド                        | 用途                                        |
|---------------------------------|---------------------------------------------|
| `/init`                         | 現在ディレクトリでプロジェクト初期化        |
| `/game new [--template T]`      | スターター世界を展開                        |
| `/mode <build\|sandbox\|play>`  | インタラクションモードを切替                |
| `/save [name]`                  | snapshot                                    |
| `/load <name>`                  | snapshot から復元                           |
| `/branch <name>`                | branch 作成 / 切替                          |
| `/undo` / `/redo`               | head を前後移動                             |
| `/run <query>`                  | dispatcher 明示実行                         |
| `/files`                        | ファイルナビゲータ表示                      |
| `/skills`                       | ビルトイン + ローカル skill 一覧            |
| `/agents`                       | agent とその trigger 一覧                   |
| `/import sillytavern-card`      | キャラクターカードインポート                |
| `/sessions`                     | セッション選択                              |
| `/continue` / `/new`            | セッション選択                              |
| `/verbose on\|off\|status`      | 詳細診断の切替                              |
| `/clear`                        | transcript クリア（状態はそのまま）         |
| `/help`                         | アプリ内ヘルプ                              |

Tab でコマンド補完、Enter で送信。

## キーバインド

| キー         | 動作                                             |
|--------------|--------------------------------------------------|
| `q`          | 終了                                             |
| `Ctrl+Q`     | セーフ終了（即ターミナルに戻る）                 |
| `Esc`        | 進行中の LLM ターンを中断                        |
| `Ctrl+K`     | コマンドパレット                                 |
| `Ctrl+P`     | コマンドパレット（代替）                         |
| `Enter`      | 送信                                             |
| `F6`         | transcript 全体をコピー                          |

## ストリーミング出力

3 本のストリームが交互に表示されます:

- **user** — 入力
- **tool** — tool 呼び出し（`read_context`、`find`、ファイル読み込みなど）
- **thinking** — デフォルト折りたたみ。展開で推論を確認
- **agent** — 最終ナレーション

右上ステータスバーにリアルタイム token カウンタ。

## セッション永続化

セッションは branch ごとに保持されます。`--continue` で現在 branch の前回セッションを復元、`/sessions` で branch をまたいで選択。

## トラブルシュート

| 症状                            | 対処                                             |
|---------------------------------|--------------------------------------------------|
| 文字化け                        | iTerm2 / Ghostty / Alacritty を使用、UTF-8       |
| 色が変                          | `TERM` が 256 色対応か確認                       |
| TUI フリーズ                    | `Esc` で現在のターンを中断                       |
| agent 出力が空                  | `--verbose` で起動してトラフィックを確認         |
| "not initialized"               | `/init` または `neonrp init` を実行              |

## 関連

- [CLI_REFERENCE.ja.md](CLI_REFERENCE.ja.md)
- [CONCEPTS.ja.md](CONCEPTS.ja.md)
- [QUICKSTART.ja.md](QUICKSTART.ja.md)
