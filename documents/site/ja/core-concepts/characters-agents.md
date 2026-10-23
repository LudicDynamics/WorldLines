---
title: "キャラクターとマルチ Agent"
description: "世界は 2 通りのどちらかで動きます: サブ agent（town / dungeon / npc）を従えたオーケストレーター型の World-Agent か、あるいは各キャラクターが固有の soul・記憶・声・サブ agent を持つ第一級のアイデンティティ —— Character-Agent —— になるマルチエージェントの村です。どちらも今日提供されています。"
---

<!-- section: today -->
## 現状 — World-Agent とサブ Agent

v0.1 では、ワールド上のすべてのエンティティは単一のトップレベル **World-Agent**（オーケストレーター / ナレーター）を通じて到達されます。World-Agent は `task()` を介して自身の**サブ Agent** に委任します:

| World-Agent 配下のサブ Agent | 責務                                                               |
|------------------------------|--------------------------------------------------------------------|
| **Town サブ Agent**          | 場所、街全体の商人、街中で起きるイベント                           |
| **Dungeon サブ Agent**       | 地形、トラップ、ダンジョン内の遭遇ペース                           |
| **NPC サブ Agent**           | 個々の NPC のダイアログと反応（現状は共有プール）                  |

これは機能します — しかし、どの NPC も同じ語りのレンズ（World-Agent のシステムプロンプト）を共有しており、彼らの「人格」は毎ターン静的なキャラクター JSON から再構築されます。

<!-- section: character-agent -->
## Character-Agent — 並列ブランチ ✅

> **v0.2.3 で提供（ローカル）** — これがマルチエージェントの村です。[Multi-Agent モード](/docs/core-concepts/engine-modes#multi-agent) を参照。

World-Agent と各キャラクター（**soul-agent**）は、共有の **メッセージバス** 越しに会話する独立した agent です —— ナレーターがキャラクターを操る傀儡にすることはありません:

```
   world-agent  ◄─────►┌────────────────┐◄─────►  soul-agents
   (host /             │  message bus   │         ┌─ Elena  (soul.md · memory · voice · subs)
    narrator)          └────────────────┘         ├─ Rowan  (its own mind)
                                                   └─ …

   The world-agent posts the scene to the bus; the souls present this turn
   each read it, decide their own speech / action / inner voice, and post
   back; the world-agent weaves the replies into a single narration.
```

各ソウルは以下を所有します:

- **`soul.md`** — アイデンティティを記述したドキュメント。中核となる価値観、経歴、関係性、傷。一度書かれ、大きな物語の節目で更新されます。
- **長期メモリ** — セッションをまたいで蓄積される経験。圧縮され、検索可能で、スナップショット / ロードを生き延びます。
- **短期メモリ** — 現在のシーンのコンテキスト。シーンの切り替わりに応じて減衰・圧縮されます。
- **パーソナリティ** — 構造化された特性（ビッグファイブ、カスタム軸など、作者が望むもの）。
- **ナラティブスタイル** — プロンプトフラグメントとしての彼女の声。ターンを跨いで一貫しており、World-Agent が彼女の周囲を語るときでも、彼女自身の直接の発話はキャラクターに忠実であり続けます。
- **カスタムサブ Agent** — 作者はキャラクターに独自の委任先を持たせられます（Elena にはメニュー価格用の `innkeeper` スキルサブ Agent、心を打ち明ける場面用の `confidante` サブ Agent を持たせられます）。共有 NPC プールを無理に通さず、キャラクターごとにコンポーザブルです。

<!-- section: why-parallel -->
## なぜネストではなく並列なのか

Character-Agent を World-Agent の**配下ではなく隣に**置くことが重要な理由:

- キャラクターのアイデンティティはワールドロジックのブランチであるべきではありません。シーンが新しい街に移っても、Elena は Elena のままでいるべきです。
- メモリのスコープが異なります: World-Agent はワールドのイベントを覚え、Character-Agent は*彼女の*イベントを覚えます。
- 声はシーンの切り替わりを生き延びます — 同じキャラクター Agent が、酒場にいるとき（town サブ Agent）でも、ダンジョンを逃げ回っているとき（dungeon サブ Agent）でも話します。
- キャラクターごとのカスタムサブ Agent は、共有 NPC プールに積み上げるよりスケールします。

これこそが **Multi-Agent モード — 村**（✅ v0.2.3 で提供、[Router モード](/docs/core-concepts/engine-modes#multi-agent) を参照）が担うものです — 各キャラクターが自分自身の agent であり、ターンを跨いでペンを握り続け、固有の記憶を保ちます。毎ターン、ナレーターがゼロから声を当て直すことはありません。

<!-- section: bridge -->
## オーケストレーターか村か — どちらも今日提供

**オーケストレーターの世界**（`stoneford` など）は、NPC を `game/npc/` のデータとして保ち、World-Agent の共有サブ Agent プールを通じて声を与えます。シンプルで安価、ルール重視のプレイに最適です。

**村の世界**（`kagura-island` や `stoneford-elena` など）は、各キャラクターに固有の Character-Agent を与えます: NPC を `souls/` 配下のソウルフォルダ + `playthrough.json` に昇格させると、そのキャラクターはターンを跨いで自ら考えるようになります。[Multi-Agent モード](/docs/core-concepts/engine-modes#multi-agent) を参照。

基礎となる Agent の構造については [Agents & Orchestration](/docs/core-concepts/agents-orchestration)、オーサリングの流れについては [Building Character Agents](/docs/guides/building-character-agents) を参照してください。
