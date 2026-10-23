---
title: "Plan → Diff → Apply"
description: "Agent はファイルを直接編集しません。Proposal を発行し、あなたがレビューしてから適用します。"
---

<!-- section: proposal -->
## Proposal

Agent が世界に書き込むとき、ファイルを直接編集することはありません。**Proposal** を発行します:

```json
{
  "run_id": "20260417-100311",
  "agent_id": "town-agent",
  "rationale": "Player examined the harbor; adding observed detail.",
  "ops": [
    {"op": "upsert_text", "path": "towns/stoneford.json", "content": "..."}
  ]
}
```

エンジンは diff を表示し、スキーマ検証を行い、新しい Event として適用します。遷移はあなた（または自動適用ルール）が承認します。

<!-- section: ops-schema -->
## 操作の種類

操作は小さな閉じた語彙です:

- `upsert_text` — テキスト内容のファイルを作成または置換
- `upsert_json` — JSON エンティティを作成または置換
- `patch_json` — JSONPath 指定でピンポイントにフィールド更新
- `delete` — ファイル削除
- `move` — リネーム / 移動

すべての op は適用前にスキーマ検証されます。

<!-- section: retrieval -->
## リトリーバル — 最小コンテキスト

harness は**境界付きリトリーバル**を用いて、各 Agent ターンに関連するエンティティだけを投入します:

- ハイブリッド fuzzy + ベクター検索
- クエリごとのエンティティ予算
- エンティティ種別フィルタ（`--kind location`、`--kind npc`）

CLI から:

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

これにより、世界が 10,000 以上のエンティティに成長してもターンレイテンシが境界内に保たれます。

<!-- section: determinism -->
## なぜこれが重要なのか

Plan → Diff → Apply が WorldLines を **レビュー可能**かつ **再現可能**にする理由です:

- すべてのステート変更を構造化された diff として監査できる
- Agent が世界ステートを静かに破壊することは不可能
- `replay verify` で Event から同じステートを再導出できる
- チャット UI はこれらの保証を一切提供しません
