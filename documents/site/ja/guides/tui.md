---
title: "TUI ターミナルガイド"
description: "ターミナルでのプレイと管理:worldlines ランチャー、スラッシュコマンド、設定とデータの場所。"
---

<!-- section: entries -->
## 2つの入口

導入後(`pip install worldlines`、または `uv tool install worldlines`、またはワンライナー `curl -LsSf https://worldlines.gg/install.sh | sh`)、コマンドは2つ。どちらも起動時に新しいリリースを確認して自動更新します:

- **`worldlines`** — ローカル Web UI、http://127.0.0.1:8787/local:ワールド、セーブ、創作デスク、設定。
- **`neonrp`** — ターミナル。「Welcome to WorldLines」ランチャーでワールドかセーブを選ぶとゲームへ。中はスラッシュコマンド(`/status` · `/plan` · `/update` …)。初回は UI 言語を選択。

> ブラウザ派は `neonrp web` で http://127.0.0.1:8787/local。TUI と同じデータをいつでも行き来できます。

<!-- section: first-run -->
## 最初のプレイ

`worldlines` のメインメニューは 2×2:**プレイ**(続き/新規)、**ワールド庫**(新規/インポート/Hub/管理)、**キャラクター庫**(Soul Talk/新規/インポート/Hub/管理)、下段(設定/終了)。ホットキー `c` 続き、`n` 新規、`s` 設定。

新規の流れ:**ワールド選択 → 分身+同行キャラ(Casting)→ モデル preset(初回はキー設定をガイド)→ 画面選択(🌟ブラウザ / ターミナル)**。ターミナルを選ぶと世界は自動で開演します。

<!-- section: slash -->
## プレイ中のスラッシュコマンド

`/` で補完と候補が出ます。よく使うもの:

- `/save [名前]` · `/load` · `/undo` · `/redo` — セーブとチェックポイント単位のやり直し
- `/cast <soul> [npc|player]` — 庫のキャラクターをこのプレイへ投入
- `/mode [build|play]` — 創作/プレイ切替(build では agent がワールドファイルを自由に編集)
- `/models` · `/auth` · `/config` · `/locale` — モデル・キー・言語
- `/export-world` · `/load-world <zip>` — ワールドの梱包/復元
- `/settings` — 設定全体;`/help` — 全コマンド

グローバルキー:`Ctrl+K` コマンドパレット、`Ctrl+L` 情報レイヤー、`F6` ログコピー。

素の REPL:`neonrp play`(入力=行動。`/trace` で前ターンのルーティング、`/debug` で agent 呼び出し)。

<!-- section: settings-data -->
## 設定とデータの場所

設定(ランチャー「設定」または `/settings`):モデル項目(テスト/キー変更/削除)、creation LLM(創作専用モデル)、画像生成(ComfyUI URL/ckpt/カスタム workflow ノード、または OpenAI)、言語、Discord ブリッジ。

データの場所:

- `~/.worldlines/worlds/` ワールド源 · `plays/` 各プレイ · `souls/` キャラクター庫
- `~/.neonrp/config.json` キー/画像バックエンド/言語(TUI と Web で共有)

バックアップ = `~/.worldlines` を丸ごと保存。
