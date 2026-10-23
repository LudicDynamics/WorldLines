---
title: "最初の世界を作る"
description: "世界を作る 3 つの方法 — ランチャー、WebHub スタジオ、または AI コーディング agent。"
---

<!-- section: launcher -->
## WorldLines ランチャーで

WorldLines を開き → **New world**、作りたいものに近いテンプレート（Stoneford · Kagura Island · …）から始め、それを遊びながら **Build** モードで手を入れます。実際に遊べる世界へ最短でたどり着く方法です。

<!-- section: webhub -->
## ブラウザで — WebHub Create スタジオ

[hub.worldlines.gg](https://hub.worldlines.gg) では、**Create** スタジオが AI 支援であなたを世界づくりへ導きます — 前提・キャラクター・トーンを設定し、納得したら公開レジストリに登録。インストール不要。

<!-- section: ai-skill -->
## Claude Code または Codex で — オーサリングスキル

WorldLines は **Claude Code** と **Codex** のオーサリングスキルを同梱しています。リポジトリを clone し、AI コーディング agent で開いて、欲しいものを伝えるだけ:

```bash
git clone https://github.com/LudicDynamics/WorldLines.git
cd WorldLines        # その後 Claude Code または Codex で開く
```

> *「国風の乙女世界を作って: 宮殿、四人の皇子、そしてヒロインを選ぶ灯」*

該当するスキルが自動で読み込まれ、`game/` のエンティティ・agent、そして（村なら）ソウルを雛形作成してくれます。ステップごとの解説: [オーサリングチュートリアル](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials) — キャラクターカード · ワールドカード · 完全な世界 · ソウル。

<!-- section: advanced-cli -->
## 上級者向け — CLI から手書きする

完全な制御が欲しいですか? エンジンメタデータを雛形作成し、`game/` を手書きします:

```bash
worldlines init        # .neonrp/ エンジンメタデータを作成
# game/meta/world.json、game/player/、ロケーション、agent を作成…
neonrp validate        # スキーマをチェック
neonrp index build     # リトリーバルインデックスを再構築
```

最小の世界には `game/meta/world.json`、プレイヤーの初期ステート、少なくとも 1 つのロケーション、そして 1 つの agent（orchestrator）が必要です。
