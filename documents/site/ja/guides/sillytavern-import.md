---
title: "SillyTavern インポート"
description: "SillyTavern のワールドカードとキャラクターカードを WorldLines に取り込む。"
---

<!-- section: character-cards -->
## キャラクターカード

SillyTavern のキャラクターカードは JSON ファイル、あるいは tEXt メタデータが埋め込まれた PNG 画像として配布されます。両方に対応しています。

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json --id mira-ashford
```

このコマンドはカードを解析し、WorldLines の `npc/` スキーマにマッピングして `game/npc/<id>.json` としてエンティティを書き出します。

📸 **スクリーンショットは近日追加** — PNG プレビュー付きのインポートダイアログを掲載予定。

<!-- section: world-cards -->
## ワールドカード

SillyTavern のワールドカード（lorebook）はより豊富で、地域・派閥・世界ロアを定義します。インポート:

```bash
neonrp import sillytavern-world world-card.json
```

エンティティは内容に応じて `game/lore/`、`game/towns/`、`game/world/` に振り分けられます。

📸 **スクリーンショットは近日追加** — インポートした lorebook のビフォー / アフター diff ビューを掲載予定。

<!-- section: caveats -->
## 注意事項

- SillyTavern のフィールドで 1:1 にマッピングできないものは、生成されるエンティティの `_meta.silly_tavern` blob に格納されます。情報は失われませんが、スキーマのファーストクラスにはまだ昇格していません。
- インポートは v0.1 では**一方向**です。SillyTavern フォーマットへの往復エクスポートは v0.2 で予定しています。
- カードが外部ホスト上の画像を参照している場合、インポートは警告をログに出しますが、画像自体はダウンロードしません。
