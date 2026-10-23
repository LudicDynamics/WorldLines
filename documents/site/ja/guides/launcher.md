---
title: "WorldLines ランチャー"
description: "ダブルクリックランチャーガイド — セッションを始める最もフレンドリーな方法。"
---

<!-- section: intro -->
## ランチャーの役割

ランチャーは、ダブルクリックするだけで WorldLines を起動できる自己完結型のファイルです。初回起動にターミナルは不要です。

3 種類あります:

- `WorldLines.command`（macOS）
- `WorldLines.bat`（Windows）
- `WorldLines.sh`（Linux — 事前に `chmod +x` が必要）

[worldlines.gg](https://worldlines.gg) → **Quick Install** からダウンロードしてください。

<!-- section: screenshots -->
## ウォークスルー

📸 **スクリーンショットは近日追加** — このページは仮置きです。ウォークスルーでは以下を示します:

1. Finder / エクスプローラー / ファイルマネージャーからファイルを起動
2. 初回起動時のブートストラップ（Python の検出と必要に応じたインストール）
3. プロバイダー選択（GLM / OpenAI / LM Studio / Ollama）
4. 初回の世界セレクター（デフォルトは Stoneford）
5. TUI が自動で開く

macOS / Windows / Linux でスクリーンショットを撮影中で、まもなくここに掲載します。

<!-- section: troubleshooting -->
## よくある問題

- **macOS「開発元が未確認」** — 初回は右クリック → 開く を使ってください（ダブルクリックではなく）。
- **Windows SmartScreen** —「詳細情報」→「実行」をクリックしてください。v0.1 ではスクリプトは未署名です。
- **Linux permission denied** — `chmod +x WorldLines.sh` を一度実行してから `./WorldLines.sh` で起動してください。
- **Python が見つからない** — ランチャーは `uv` 経由で Python 3.12 を自動インストールします。`uv` のインストールが失敗する場合は手動で入れてください: `curl -LsSf https://astral.sh/uv/install.sh | sh`。
