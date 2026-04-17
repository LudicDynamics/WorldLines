# コア概念

**Language:** [English](./CONCEPTS.md) · [简体中文](./CONCEPTS.zh.md) · [日本語](./CONCEPTS.ja.md) · [한국어](./CONCEPTS.ko.md)

> ステータス: Beta — 概念モデルは安定。内部実装は変わる可能性あり

WorldLines は少数のプリミティブを中心に設計されています。これらを理解すれば残りは自ずと見えてきます。

## Events

世界のすべての変更は **append-only event** として `.neonrp/events.jsonl` に書かれます。例:

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

Events が真実の源で、`game/` は event ストリームの *マテリアライゼーション* に過ぎません。event 0 から再生すれば `game/` をいつでも再構築できます。

## Snapshots

**snapshot**（= save）は、特定の event 時点における `game/` の完全コピー + メタデータです。`.neonrp/saves/<name>/` に保存されます。巻き戻しを高速化するための存在で、1 万 event の再生は遅いですが snapshot のロードはファイルコピーで済みます。

```bash
neonrp save opening-scene
neonrp load opening-scene
```

## Branches

**branch** は event log 上の名前付き head ポインタです。git と同様に分岐は軽量で、現在状態から fork して分岐 event を書き進めます。

```bash
neonrp branch try-stealing
```

Branches は `.neonrp/branches/` 配下の copy-on-write で未変更エンティティを共有します。

## Undo / Redo

`undo` / `redo` は head ポインタを前後に動かし、最寄りの snapshot から復元して前方再生します。event log は決して破壊されません。

## Sandboxes

**sandbox** は snapshot から作られ、一時的なフラグを持った branch です。名前付き branch を汚さずに「もしも」実験ができ、きれいに破棄できます。

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... プレイ ...
neonrp sandbox drop experiment --force
```

## Replay と決定性

同じ events と seed された LLM（もしくはキャッシュされた fixture）があれば、再生は同じ `game/` 状態を生みます。`replay verify` がそれを検証します:

```bash
neonrp replay verify --from opening-scene
```

これが、WorldLines が AI 駆動状態を再現可能に保つ方法です。チャット UI では得られない性質です。

## Agents

**agent** は `agents/<agent-id>/` ディレクトリで、以下を含みます:

- `agent.json` — triggers、tags、priority、ルーティングメタデータ
- `system.md` — system prompt テンプレート
- （任意）`skills/`、`tools.json`、`policies.md`

**dispatcher** は次の優先順で各クエリの agent を決定します:

1. 明示的な `--agent` フラグ
2. 正規表現 trigger パターン
3. Tag の重複度
4. Priority によるタイブレーク

stoneford スターターは 6 つの agent を同梱します（[templates/stoneford](templates/stoneford/README.ja.md) 参照）。

## Skills

**Skills** は agent が `use` できる再利用可能な prompt 断片 / 能力モジュールです。ビルトイン skill（エンジン同梱）は自動で登録され、プロジェクトローカル skill は `skills/` に定義できます。

## Plan → Diff → Apply

agent が世界に書き込むとき、ファイルを直接編集せず **proposal** を発行します:

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

エンジンは diff を表示し、schema 検証してから新 event として適用します。あなた（あるいは auto-apply ルール）がこの遷移を承認します。

## Harness — オーケストレーションループ

WorldLines の agent harness は Plan–Diff–Apply ループを実装し、次を備えます:

- Bounded retrieval（minimal-context、fuzzy+vector のハイブリッド）
- 決定的なツール呼び出し順序
- ターンごとの予算（tokens / tool calls）
- Thinking チャネルとナレーションの分離

**orchestrator** agent は最上位の harness コーディネータで、`task()` ツールでドメイン agent にルーティングし、ゲーム状態の整合性を保ち、プレイヤー向けナレーションを担当します。

## Build / Sandbox / Play モード

TUI は 3 モードを公開:

- **build** — 直接ファイル編集 + 自然なナレーション。制作時に使用。
- **sandbox** — proposal パイプライン + 手動承認。最も安全。
- **play** — GM モード。auto-apply ON、完全没入。

TUI 内で `/mode <name>` で切替。

## さらに読む

- [CLI_REFERENCE.ja.md](CLI_REFERENCE.ja.md) — 表層コマンド
- [TUI_GUIDE.ja.md](TUI_GUIDE.ja.md) — インタラクティブワークフロー
- [templates/stoneford/](templates/stoneford/README.ja.md) — サンプル世界
