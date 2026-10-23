---
title: "世界 — 新規作成 · インポート · エクスポート"
description: "ゲーム世界の作成、インポート、エクスポート。"
---

<!-- section: new -->
## 新しい世界を作る

**ランチャーで（推奨）。** WorldLines を開き **New world** を選ぶ — 組み込みテンプレート（Stoneford · Stoneford · Elena · Kagura Island · …）を選ぶと、雛形が作られて開き、遊んで編集できる状態になります。覚えることは何もありません。

**AI agent でオーサリングする。** WorldLines は **Claude Code** と **Codex** のオーサリングスキルを同梱しています。AI コーディング agent でリポジトリを開き、欲しいものを伝えるだけ — *「四人の皇子が登場する国風の乙女世界」* — すると、スキルが `game/` のエンティティと agent を雛形作成してくれます。[オーサリングチュートリアル](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials)（キャラクターカード · ワールドカード · 完全な世界 · ソウル）を参照。

**上級者向け — CLI。** ターミナルでテンプレートから雛形を作ります:

```bash
neonrp game new --template stoneford-orch    # 旗艦攻城 TRPG（10-agent）
neonrp game new --template stoneford-elena   # Stoneford + Elena — マルチエージェントの村
neonrp game new --template kagura-island     # ミステリー · 7 ソウル
neonrp game new --template default           # 最小スターター
```

あるいは空プロジェクトから始めて `game/` を直接手書きすることもできます（[最初の世界を作る](/docs/guides/creating-first-world) を参照）。

<!-- section: home-dir -->
## 世界の保管場所 — `~/.worldlines/games/`

ランチャーから世界をインポートまたは雛形作成すると、結果の世界は `~/.worldlines/games/<name>/` 配下に配置されます。このディレクトリはあなたのマシン上のすべての世界のホームで、各世界は独自の `game/` ツリーと `.neonrp/` ステートを持ちます。

現在プレイしているプロジェクトは、これらのフォルダのうちの 1 つのインスタンスです（`cd` + `worldlines init` によるアドホックなパスでも動作しますが、`~/.worldlines/games/` が慣例となる置き場所です）。

<!-- section: export -->
## 世界のエクスポート

組み込みの TUI コマンド（あるいはシェルエイリアス）を使用します:

```
/export-world                    # TUI 内 → ~/Downloads/worldlines-<name>-<ts>.zip に書き出し
/export-world my-world.zip       # 出力パスを指定
```

シェル版:

```bash
neonrp export-world                        # デフォルト保存先は ~/Downloads/
neonrp export-world --output ~/my-world.zip
```

アーカイブには `game/` フォルダに加えて `.neonrp/` ステート（Event、Snapshot、manifest）が含まれるため、受け取った相手はあなたが中断した地点から正確に再開できます。

📸 **スクリーンショットは近日追加** — ランチャー UI からのワンクリックエクスポートは v0.1.6 で予定しています。

<!-- section: import -->
## 世界のインポート

TUI 内またはシェルから:

```
/load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

```bash
neonrp load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

アーカイブが `~/.worldlines/games/<name>/` 配下に展開され、他の世界と並んで表示されます。その後、`/worlds`（TUI）で切り替えるか、ランチャー起動前に `cd ~/.worldlines/games/<name>` してください。

📸 **スクリーンショットは近日追加** — ランチャーのドラッグ&ドロップインポートフロー。

<!-- section: browse -->
## ローカルの世界を一覧する

TUI 内で:

```
/worlds                         # ~/.worldlines/games/ 配下の世界を一覧し、テンプレートから雛形作成
/worldlines                     # ガイド付き世界ピッカー（モデルプリセット + 世界 + 起動）
```

あるいは手動で:

```bash
ls ~/.worldlines/games/
```
