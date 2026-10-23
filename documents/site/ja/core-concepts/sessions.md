---
title: "モード — Build · TUI · Web UI"
description: "世界を動かす 3 つの方法: オーサリングする（Build）、ターミナルで遊ぶ（TUI）、ブラウザで遊ぶ（Web UI）。"
---

<!-- section: modes -->
## 3 つのモード: Build · TUI · Web UI

世界は次の 3 つのモードのいずれかで動きます:

| モード | 内容 | 場所 |
|---|---|---|
| **Build** | 世界をオーサリング — `game/` ファイルを直接編集するか、AI agent にやらせる（plan → diff → apply） | ランチャー · CLI · 任意のエディタ |
| **TUI** | ターミナルで遊ぶ、Claude Code スタイル — thinking、tool-use、語りを眺める | `neonrp tui` |
| **Web UI** | ブラウザで遊び、すべての agent をライブで見守る | [WebHub](https://hub.worldlines.gg)、またはローカルで `neonrp web` |

**プラガブルなメディア生成。** 世界はテキストに限りません。シーンが展開するにつれてエンジンが呼び出す生成 API を組み込めます:

- **画像生成 API** — シーンアート、キャラクターの肖像、決定的な瞬間
- **BGM 生成 API** — ムードに追従する適応的な背景音楽

つまり同じエージェント型の世界が、単なるトランスクリプトではなく、完全な視聴覚体験としてレンダリングできます。

> **Build** とプレイの内部では、エンジンは agent の Proposal が*どのように*適用されるか —— **直接（direct）**、**ゲート経由（sandbox）**、または **自動（auto）** —— も追跡し、[Router モード](/docs/core-concepts/engine-modes)（fast / orchestrator / multi-agent）と組み合わさります。以下のセクションを参照。

<!-- section: build-mode -->
## Build モード

オーサリングモードです。`game/` 配下のファイルを任意のエディタで直接編集します — Agent ターンはルーティングされません。以下に便利です:

- 新しい街 / NPC / クエストの雛形作成
- プレイセッションで発覚したデータの修正
- 特定のステートを Agent がどう語るかのクイックテスト

*あなた*が真実の源であるため、承認ゲートも Router モードもありません。

<!-- section: sandbox-mode -->
## Sandbox モード

Agent の実行は **Proposal** を生成し、あなたが**ターンごとに**レビューして**承認**します。`.neonrp/events.jsonl` に何かが書き込まれる前に diff が表示されます。

TUI 内で `/autoapply on|off` を使うと、ゲートを動的に切り替えられます — `autoapply on` はそのセッションにおいて sandbox を実質 play に変え、`autoapply off` でゲートを復活させます。

**向いている用途**:
- Proposal を完全には信頼していない新しい Agent の試行
- 拒否権を保持しながらの AI 支援オーサリング
- Dispatcher / harness の挙動のデバッグ — すべての Proposal が可視化される

<!-- section: play-mode -->
## Play モード

GM モードです。Agent が Proposal を生成し、エンジンがそれを**自動適用**します。スキーマ検証に失敗しない限り diff は表示されず、トランスクリプトは物語のように読めます。

プレイヤーが最も時間を費やすモードです。物語が進むにつれて世界が変わります。あとで巻き戻したい場合は、リスクのある行動の前に Branch や Snapshot を取っておきましょう。

Router モードはここでも適用されます: 最小限のルーティングには `/router-mode fast`、クロスドメインの一貫性には `/router-mode orchestrator`、スティッキーなサブ Agent 委任には `/router-mode multi-agent` を使います。

<!-- section: tui-layout -->
## TUI レイアウト

上部は単一ペインの対話トランスクリプト、下部は入力行、右上にステータスバーがあります。ステータスバーの `[AUTO]`/`[manual]` タグが現在のプレイモードを示します。

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
└─────────────────────────────────────────────────────────────────┘
```
