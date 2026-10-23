---
title: "Agent とオーケストレーション"
description: "WorldLines の Agent 設計 — ファイルベースの Agent フォーマットと harness のカスタマイズが、高自由度なゲームオーサリングを可能にします。"
---

<!-- section: philosophy -->
## なぜファイルベースの Agent なのか

WorldLines の Agent システムは**徹底してファイルベース**です。キャラクター、ドメイン、レフェリー — すべての Agent はプレーンなファイルを並べたディレクトリです:

- `agent.json` — トリガー、タグ、優先度、ルーティングメタデータ
- `system.md` — システムプロンプトテンプレート（Markdown、人間が読める）
- `skills/` — 任意の再利用可能なプロンプトフラグメント / ケイパビリティモジュール
- `tools.json` — 任意の追加ツール定義
- `policies.md` — 任意のハードルール（v0.2 以降）

データベースはありません。API に縛られたステートもありません。Agent を `git diff` でき、フォークでき、別の Agent からコピーアンドペーストできます。これは Claude Code がコードに対して適用したのと同じ着想です — **ファイルシステムが UI である**。

<!-- section: harness-editing -->
## 高自由度な harness 編集

harness — プランニング、コンテキスト取得、ツール呼び出し、差分適用を行うループ — は**エンジンのコードではなく、Agent ファイルによって定義されます**。

これにより、ゲームの作者は次のことができます:

- `system.md` を書き換えて**語りの声**を変える
- Agent の `tools.json` を編集して**リトリーバルのスコープ**を変える
- `policies.md` を追加して**意思決定のスタイル**を変える
- トリガー / タグ / 優先度を調整して**Dispatcher の挙動**を変える

まったく新しいサブジャンル（ミステリー / スリップストリーム / 乙女 / TRPG）が、stoneford のベースに対する Agent ディレクトリの変更の集合として表現できます — Python を一行も書くことなく。これが WorldLines が最適化している設計空間です。

<!-- section: anatomy -->
## Agent の構造

完全な Agent ディレクトリは次のようになります:

```
agents/elena/
├── agent.json        # triggers, tags, priority, routing
├── system.md         # system prompt template
├── skills/
│   └── innkeeper.md  # reusable prompt fragments
├── tools.json        # extra tool definitions (optional)
└── policies.md       # hard rules (v0.2+)
```

stoneford スターターには **6 つの Agent** が同梱されています: `orchestrator`、`town-agent`、`dungeon-agent`、`combat-referee`、`world-builder`、`rules-referee`。

<!-- section: dispatch -->
## Dispatcher

Dispatcher は各クエリに対して次の基準で Agent を選択します:

1. 明示的な `--agent` フラグ
2. `agent.json` の正規表現トリガーパターン
3. 現在のコンテキストとのタグの重なり
4. 優先度によるタイブレーク

Agent は CLI から直接呼び出せます:

```bash
neonrp agent run town-agent --query "describe the harbor"
neonrp agent list --json
neonrp agent show town-agent
```

<!-- section: harness-loop -->
## Harness — オーケストレーションループ

WorldLines の Agent harness は **Plan → Diff → Apply ループ**を実装しており、以下を備えます:

- 境界付きリトリーバル（最小コンテキスト、ハイブリッド fuzzy + ベクター検索）
- 決定的なツール順序
- ターンごとの予算（トークン / ツールコール）
- thinking チャンネルを narration から分離

**orchestrator** Agent はトップレベルの harness コーディネーターです — `task()` ツールを通じてドメイン / キャラクター Agent にルーティングし、ゲームステートの一貫性を保ち、プレイヤー向けの narration を担当します。

Router モード（`fast` / `orchestrator` / `multi-agent`）はターンごとに*どのようにオーケストレーションが行われるか*を変えます — [Router モード](/docs/core-concepts/engine-modes) を参照してください。

<!-- section: skills -->
## Skill

**Skill** は Agent が `use` できる再利用可能なプロンプトフラグメント / ケイパビリティモジュールです。組み込み Skill はエンジンに同梱されており、`skills/` 配下にプロジェクトローカルな Skill を定義することもできます。

利用可能なものを一覧するには:

```bash
/skills              # TUI 内で
```
