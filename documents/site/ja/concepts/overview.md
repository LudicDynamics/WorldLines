---
title: "三つの層:エンジン · テンプレートパック · プロダクト"
description: "WorldLines — Make you play with your AI character in an infinite world. 誰もがまずこのページを読みます。"
---

<!-- section: what -->
## WorldLines とは

**WorldLines — Make you play with your AI character in an infinite world.**

あなたは主人公を演じ、自分で動き続ける世界の中で AI キャラクターとともに暮らします。キャラクター(soul)はそれぞれ自分の agent を持ち、自分で判断し、自分で話します。世界 NPC は世界が声を当て、そのルールで動きます。地図には新しい場所が生まれ、経済と勢力は自分で回ります。あなたの言葉もキャラクターの決定も、すべてはまず**提案**にすぎません。世界(world agent)が検証してはじめて、世界が変わります。

<!-- section: layers -->
## 独立した三つの層

| 層 | 何か | 誰が使うか |
|---|---|---|
| **NeonRP エンジン**(`neonrp` パッケージ) | 開スキーマ / 閉スキーマの状態ロジック、提案 → 検証 → 適用、イベントと購読、コミットと分岐だけ。**プレイの中身はいっさい含みません。** | SDK 開発者 |
| **テンプレートパック** | 一種類のプレイをエンジンに登録します:クラス、変数、ops、トリガー、メカニクスの継ぎ目、プロンプト。内蔵は `rpg`(d20 + 能力修正、独自ルール。判定と戦闘不能のルールは SRD 5.2、CC BY 4.0 も使える)、`pct`(百面ダイス、BRP —— Chaosium の *Basic Roleplaying*、ORC License:d100 スキル、正気度、瀕死判定。rpg の上に作られ、この種のプレイを「サンドボックスTRPG」と呼びます)、`werewolf` と `monopoly` | クリエイター / 開発者 |
| **WorldLines プロダクト**(`worldlines` パッケージ) | プレイ UI、創作のワークベンチ、組み立て、Lint、書き出し / 取り込み、Hub への公開。`neonrp` エンジンに依存し、公開インターフェースだけを呼びます | プレイヤー / クリエイター |

つまり、**プレイヤーは `worldlines` を入れます**(エンジンも一緒に入ります)。**開発者は `neonrp` だけを入れて**、自分のプログラムや Godot にエンジンを組み込めます。

**入れ方が二つ、ターンも二種類。** PyPI の `worldlines` / `neonrp` パッケージには完全な二拍の編成(まず相談、次に解決)が入っています。オープンソースのリポジトリからビルドすると得られるのはオープンエンジンで、ターンは一拍(解決だけ)です。同じテンプレートがどちらでも遊べます。テンプレートが二拍を求めてもエンジンにそれがないときは、一拍に戻ります。[1 ターンの流れ](/docs/concepts/turn-flow) を参照してください。

<!-- section: readers -->
## 自分に合わせて読む

| あなたは | ここから |
|---|---|
| プレイヤー | [プレイヤー クイックスタート](/docs/players/quickstart) |
| クリエイター | [クリエイター クイックスタート](/docs/creators/quickstart) |
| SDK / 独自フロントエンドの開発者 | [開発者 クイックスタート](/docs/developers/quickstart) · [リアルタイムのイベントストリーム](/docs/developers/events) |
| 誰かのために働く agent(Claude Code、Codex、WorldLines の創作 agent) | [agent 向け](/docs/agents/overview) |

ほかに短い概念ページが四つあります。[開スキーマと閉スキーマ](/docs/concepts/schema) · [提案 → 検証 → 適用](/docs/concepts/ops) · [キャラクターと NPC](/docs/concepts/souls) · [世界線](/docs/concepts/worldlines)。

<!-- section: map -->
## 1.0 にあるもの

| もの | 何か | 読む |
|---|---|---|
| 世界 | 一つのフォルダ:場所の木、NPC、持ち物、オープニング | テンプレートフォルダ内の `spec/world.md` |
| キャラクター | ライブラリに住み、テンプレートはリンクだけを持ち、一局の開始時に実体化する | [キャラクターとキャスト](/docs/creators/characters) · [あなたのキャラクター](/docs/players/your-character) |
| テンプレート | 世界 + キャラクターへのリンク + ルールパック + 契約 + 編成:遊び、書き出し、公開する単位 | [テンプレートファイル](/docs/creators/template-card) · [ワークベンチ](/docs/creators/workbench) |
| プレイ契約 | 一種類のゲームが約束する体験。lint はこれに沿って調べ、一局はこれに沿って精算する | [プレイ契約](/docs/creators/contracts) |
| 編成 | 1 ターンの流れ方:テンプレートが `uses` で指定する(二拍 `two_beat` / 一拍 `one_beat`)。ローカルの編成ベンチではグラフを編集できる | [ワークベンチ](/docs/creators/workbench) · [相談と解決](/docs/concepts/planning-resolve) |
| 1 ターン | 二拍:相談(世界は変わらない)→ 解決(まず本文、次に状態)。オープンソース版には解決の拍だけがある | [1 ターンの流れ](/docs/concepts/turn-flow) · [リアルタイムのイベントストリーム](/docs/developers/events) |

<!-- section: stoneford -->
## 共通の例:ストーンフォード

例はすべて内蔵テンプレート **ストーンフォード · 霧の退く夜**(`stoneford-town`)を使います。一年に一夜だけ霧が北の道から退きます。探索隊は帰ってこず、山賊**隻眼の虎**が街道を押さえていて、あなたには夜二つと昼一つのあいだに北門から出るのに必要なものをそろえなければなりません。治癒師の**エレナ**と**ローワン**は自分の agent を持つキャラクターです。門のキャス、ギルドのヘロン、宿屋のミラは世界 NPC です。もう一つの内蔵テンプレートは **グレイオーク館 · 閉ざされた扉**(`pct-house`)で、百面ダイスのサンドボックスTRPGです。

<!-- section: license -->
## ライセンス

1.0 から NeonRP エンジンは **Apache-2.0** のオープンソースです。WorldLines プロダクト(`worldlines`、UI、内蔵のサンプルテンプレート)は **AGPL-3.0** で公開しています。PyPI パッケージに入っている二拍の編成はオープンソースのリポジトリには含まれず、オープンソースではありません。

テンプレートとサンプルの世界の**コンテンツ**には別のライセンスがあります(エンジンパッケージ内の `CONTENT-LICENSE.md` を参照)。設定テキスト(世界とキャラクターの設定、場所、ルール表)は **CC BY 4.0** です。改変も商用利用もでき、クレジットを入れるだけです。画像と音声(立ち絵、カバー、背景、効果音)は **CC BY-NC 4.0** です。クレジットを入れれば改変できますが、商用利用はできません。使っているオープンなルールはそれぞれのライセンスのままです。SRD 5.2 は CC BY 4.0、BRP は ORC License です。
