---
title: "エンジンモード —— マルチエージェント・シミュレーション（+ 軽量な Fast / Orchestrator）"
description: "WorldLines はそれ自体がマルチエージェント・シミュレーション:world-agent が独立した魂の社会を包む。Fast と Orchestrator は、より単純な単線シーン向けの軽量モード。"
---

<!-- section: comparison -->
## 一目でわかる比較

| モード           | 毎ターン何が動くか                                                    | ステータス                        |
|------------------|-----------------------------------------------------------------------|-----------------------------------|
| **Multi-Agent**  | world-agent が**アクティブなソウル**を包む — 各々が固有の心を持つ独立キャラクター agent | ✅ 提供済み（v0.2.3、ローカル）   |
| **Orchestrator** | world-agent が `task()` でドメイン agent にルーティング              | ✅ 出荷済み / Shipped              |
| **Fast**         | 単一 Agent、最小限のルーティング                                      | ✅ 提供済み                        |

**マルチエージェント（Multi-Agent）こそがエンジンの本体** —— world-agent が独立した魂からなる社会を包み、それぞれが自分の心を持つ。これが村モデルであり、すべてのワールドが向かう先。**Orchestrator**（world-agent がデータ駆動の NPC を束ねるドメイン agent にルーティング）と **Fast**（単一 agent）は、より単純な単線シーン向けの軽量モード。三つとも同じイベントログ形式で書き込み、永続化される状態は同一 —— 違いは**各ターンに何が思考するか**だけ。

**マルチエージェントはローカルで動作**（TUI / CLI）;hosted play は今のところ軽量な Fast + Orchestrator を提供。再現可能で、`souls/` フォルダ + `playthrough.json` を持つワールドなら自動的に有効化される。[worldlines/templates/stoneford-town.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/stoneford-town.template)（ストーンフォード）と [worldlines/templates/pct-house.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/pct-house.template)（グレイオーク館、2つの魂）を参照。

<!-- section: fast -->
## Fast モード

**単一の Agent** がターンをエンドツーエンドで処理します。Orchestrator なし、委任なし、`task()` 呼び出しなしです。

**向いている用途**:
- ターンあたりの LLM コストが最も安い
- オーサリング中の素早い反復
- ルーティングが不要な、語り中心のシーン

**制限事項**:
- サブ Agent による専門化がない — 戦闘に関する質問も語りと同じ Agent に届きます
- ドメインを跨ぐ複雑なシーンではステートドリフトのリスクが高くなります

<!-- section: orchestrator -->
## Orchestrator モード

Stoneford のデフォルトです。**orchestrator** / ナレーター Agent がドメイン Agent（town / dungeon / combat-referee / world-builder / rules-referee）の上に位置し、`task()` ツールを通じて**毎ターン再ルーティング**します。

**向いている用途**:
- 複数ドメインにまたがるシーン（街中での戦闘、ダンジョンでの儀式など）
- ルールの一貫性が重要なあらゆる瞬間
- 正規のプレイループ

**コスト**:
- 毎ターン orchestrator と最低 1 つのドメイン Agent の両方のコストを支払う
- レイテンシは境界内だが Fast より高い

<!-- section: multi-agent -->
## Multi-Agent モード — 村モデル ✅

**v0.2.3 で提供（ローカル）。** これが**村**です。ひとりのナレーターがすべてのキャラクターを演じるのではなく、**各キャラクターが自分自身の AI agent** —— 固有の人格・記憶・秘密・目標を持つ「ソウル」—— になります。彼らは自ら考えます。

**world-agent** がゲームマスターのようにシーンをホストします: 毎ターン、その場にいるキャラクターを起こし、各々に何を言い何をするか決めさせ、彼らの動きをひとつの語りへと織り上げます。

```
              world-agent  (the host / narrator)
                    │  wakes whoever is in the scene
          ┌─────────┼─────────┐
       Kagami     Hane      Shiro      ← each an independent soul:
      (own mind) (own mind) (own mind)    its own memory, agenda, voice
          └─────────┼─────────┘
                    ▼
              world-agent  → narrates the turn; the world remembers
```

**なぜ重要か**

- **各キャラクターが本物。** Elena はナレーターが彼女のために書く台詞ではありません —— 自分で決める agent であり、あなたを驚かせることもあります。
- **彼らは覚えている。** ソウルはターンを跨いで記憶・関係・個人の弧を保ち、村は進化し、キャラクターはあなたが前にしたことを話題に出します。
- **ソウルは持ち運べる。** 各々が自己完結しているため、同じ Elena が Stoneford から Kagura Island へ渡っても、なお自分自身でいられます。

**試す**（今日はローカルで動きます）:

```bash
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # グレイオーク館
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # ストーンフォード
```

`souls/` フォルダ + `playthrough.json` を同梱する世界は、自動的に村になります。`soul-authoring` ワークフローで自分のキャラクターを作れます。

ホストプレイ（WebHub）は現在 Fast + Orchestrator をカバーしています; 村をオンライン化するのは別トラックです。

<!-- section: switching -->
## Router モードの切り替え

Router モードはプロジェクト単位ではなくターン単位です。TUI で切り替えます:

```
/router-mode fast
/router-mode orchestrator
/router-mode multi-agent
```

あるいは `neonrp run` に `--router-mode <mode>` を渡します。セッションログは各 Event に Router モードを記録するため、リプレイは常に忠実です。
