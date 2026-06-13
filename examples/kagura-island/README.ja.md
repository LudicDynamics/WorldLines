# ⛩ 神楽島 Kagura Island — マルチエージェント・ワールド

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> エンジンモード:**multi-agent**。和風ミステリー · タイムループ · イスの神話。一つの島に**七つの生きたソウル** —— WorldLines 最も豊かなマルチエージェント社会。CoC 式判定（d20 戦闘ではない）。

**[▶ オンラインで遊ぶ →](https://hub.worldlines.gg/play/worlds/kagura-island)**

## なぜ multi-agent なのか

`fast` と `orch` モードは **world-agent + ドメイン agent** を動かし、NPC はデータです。**multi-agent** は `souls/` フォルダを追加し、各ソウルは**独立した心を持つキャラクター agent** です。神楽島はその showcase:**七つのソウル**が並行して考え、企み、覚え、world-agent がそれを包みます:

```
world-agent  →  active souls (このターンのアクター)  →  world-agent
  (主権的         各ソウル:発話 / 行動 /                (単一の世界クローズ境界、
   編成者)         内なる声、それぞれの思惑で)             あなたへ叙述)
```

`playthrough.json` が毎ターンどのソウルがアクティブかを宣言します。ソウルは隔離されたアクター —— ピアメッシュではなく、world-agent が**主導するアクター集合**で、世界クローズ境界は一つだけ。島は覚えており、ループは回り、各ソウルが自分の秘密を抱えてそれを通り抜けます。

```bash
neonrp tui --from examples/kagura-island
```

## 七つのソウル

| Soul | id |
|---|---|
| **鏡子** Kagami | `kagami-si-kagami001` |
| **羽** Hane | `hane-si-hane0001` |
| **真琴** Makoto | `makoto-si-makoto001` |
| **宮司** Miyaji | `miyaji-si-miyaji001` |
| **白** Shiro | `shiro-si-shiro0001` |
| **翼** Tsubasa | `tsubasa-si-tsubasa01` |
| **悠人** Yuto | `yuto-si-yuto0001` |

各ソウルフォルダはバンドル構造に従います:`soul.json` / `soul.md`（identity）、`persona/`（特性・価値・関係）、`background/`（歴史・出自・秘密）、`character/`（プロフィール・ステータス・所持品）、記憶（`long-term-memo/` + `short-term-memo/`）、`rules/`（ソウルごとのガードレール）、`agents/`（ソウルの心）、`trajectory/`（軌跡）。

## 世界

`agents/` = world-agent + 町 / 戦闘 / 物語 / world-builder / npc-builder / rules-referee。`game/` が島の真実を保持（lore・場所・アイテム・タイムライン;GM 真相は `game/lore/gm-truth.md` —— world-agent のみ）。`runtime_contract.json` はルーターシェルを保ち、`playthrough.json + souls/` があるためソウルラッパーが起動します。

> タイムループ · 正気度 · 禁忌:不可逆の結果、CoC 式。プレイヤーは**人間**であり、名前を持つソウルにはなりません。

## ライセンス

**AGPL-3.0** —— フォーク、改変、自分の世界を出荷可能。エンジン（`neonrp`）はプロプライエタリプレビュー。
