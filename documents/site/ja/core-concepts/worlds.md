---
title: "Event、Snapshot、Branch"
description: "WorldLines はすべての変更を追記専用の Event として保存します。Snapshot と Branch により巻き戻しが安価になります。"
---

<!-- section: events -->
## Event

世界のあらゆる変更は、`.neonrp/events.jsonl` に書き込まれる**追記専用 Event** です:

```json
{
  "id": 42,
  "ts": "2026-04-17T10:03:11Z",
  "branch": "main",
  "agent_id": "town-agent",
  "kind": "proposal_applied",
  "ops": [
    {"op": "upsert_text", "path": "player/journal.json", "content": "..."}
  ]
}
```

Event が**唯一の真実の源（source of truth）**です。`game/` は Event ストリームのマテリアライズ結果にすぎません。event 0 から再生すれば、いつでも `game/` を再構築できます。

<!-- section: snapshots -->
## Snapshot

**Snapshot**（別名 save）は、ある Event 時点での `game/` の完全なコピーとメタデータです。Snapshot は `.neonrp/saves/<name>/` 配下に保存されます。Snapshot の目的は巻き戻しを高速にすることです — 10,000 個の Event をリプレイするのは遅いですが、Snapshot のロードは単なるファイルコピーです。

```bash
neonrp save opening-scene
neonrp load opening-scene
```

<!-- section: branches -->
## Branch

**Branch** は Event ログ上の名前付き head ポインタです。git と同様に、ブランチ作成は安価です。現在のステートをフォークし、分岐した Event を書き込むだけです。

```bash
neonrp branch try-stealing
```

Branch は変更されていないエンティティを copy-on-write で共有し、`.neonrp/branches/` 配下に保存されます。

<!-- section: sandboxes -->
## Sandbox

**Sandbox** とは *Snapshot から作成され*、一時的と印を付けられた Branch です。名前付きブランチを汚さずに「もし〜だったら」の実験を走らせられます。

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... プレイ ...
neonrp sandbox drop experiment --force
```

<!-- section: replay -->
## Replay と決定性

同じ Event とシード済み LLM（またはキャッシュされた fixture）があれば、リプレイは同じ `game/` ステートを生成するはずです。`replay verify` がこれを検証します:

```bash
neonrp replay verify --from opening-scene
```

これが WorldLines が AI 駆動ステートの再現性を維持する仕組みです — チャット UI では得られない性質です。
