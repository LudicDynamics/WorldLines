---
title: "遊びはじめる"
description: "入り口は三つ:オンライン、ローカル Web UI、ターミナル。どれか一つを選べば、数分で最初の世界に入れます。"
---

<!-- section: paths -->
## 三つの入り口

| 遊び方 | 入れるもの | 場所 |
|---|---|---|
| **オンライン** | なし | [worldlines.gg](https://worldlines.gg)、または iOS アプリ |
| **ローカル Web UI** | `worldlines` | ブラウザで http://127.0.0.1:8787/local |
| **ターミナル** | `worldlines` または `neonrp` | ターミナルで `neonrp` と入力 |

ローカル Web UI とターミナルは同じ世界、セーブ、設定を読み書きします。いつでも切り替えられます。

<!-- section: online -->
## オンラインで遊ぶ

[worldlines.gg](https://worldlines.gg) を開き、Hub で世界を選んで、そのままブラウザで遊びます。スマートフォンでは iOS アプリを使います。インストールは不要で、自分のモデルも要りません。

<!-- section: install -->
## ローカルにインストール

Python 3.10 以上が必要です。

```bash
pip install worldlines        # または:uv tool install worldlines / pipx install worldlines
```

`worldlines` を入れるとエンジン `neonrp` も一緒に入るので、二つのコマンドが両方使えます。ターミナルだけでよければ `pip install neonrp`。

ソースとリリースノートは GitHub リポジトリ [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines) にあります。ワンライナーのインストーラーも引き続き使えます(uv がなければ一緒に入れます)。

```bash
curl -LsSf https://worldlines.gg/install.sh | sh      # macOS / Linux
irm https://worldlines.gg/install.ps1 | iex           # Windows PowerShell
```

<!-- section: open -->
## 開く

```bash
worldlines        # ローカル Web UI:ブラウザで http://127.0.0.1:8787/local が開きます
neonrp            # ターミナル:「Welcome to WorldLines」ランチャー
```

- **Web**:プレイ一覧で世界をクリックし、新しい一局を始めます。その世界のセーブ済みの一局も同じパネルに並び、そこから続けられます。
- **ターミナル**:ランチャーで「新しく始める」(`n`)を選んで世界を選びます。「⚡ 前回の続き」(`r`)は最新の一局にそのまま入ります。いちばん最初の起動では表示言語を聞かれます。

最初の一局ではモデルも選びます。[モデルをつなぐ](/docs/players/providers) を参照してください。新しい一局は自分で場面を開くので、先に何か入力する必要はありません。

<!-- section: update -->
## 自動更新

pip、uv tool、pipx で入れた場合、`worldlines` と `neonrp` は起動時に新しいバージョンを確認します。新しいものがあれば自分で更新し、新しい版で再起動します。この動作を変えるには、ターミナルのゲーム内で次を入力します。

| コマンド | 効果 |
|---|---|
| `/update mode prompt` | 先に確認する |
| `/update mode notify` | 知らせるだけで、更新しない |
| `/update mode auto` | 自分で更新する(既定) |
| `/update status` | 現在のバージョンと更新設定を表示 |

ソースからのインストール(`pip install -e`)は知らせるだけで、自分では更新しません。

<!-- section: data -->
## データの場所

| 場所 | 中身 |
|---|---|
| `~/.worldlines/plays/` | 遊んだすべての一局 |
| `~/.worldlines/templates/` | 自分のテンプレート(編集用にコピーしたもの、新しく作ったもの) |
| `~/.worldlines/souls/` | キャラクターライブラリ |
| `~/.worldlines/official/` | ログイン後にダウンロードした公式の世界 |
| `~/.neonrp/config.json` | モデル、キー、言語、更新モード |

バックアップするには、`~/.worldlines` と `~/.neonrp/config.json` を一緒にコピーします。

<!-- section: next -->
## 次に読む

[モデルをつなぐ](/docs/players/providers) → [最初の一局](/docs/players/first-world) → [1 ターンの流れ](/docs/players/how-to-play)
