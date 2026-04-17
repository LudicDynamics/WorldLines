# リリースノート

**Language:** [English](./RELEASE_NOTES.md) · [简体中文](./RELEASE_NOTES.zh.md) · [日本語](./RELEASE_NOTES.ja.md) · [한국어](./RELEASE_NOTES.ko.md)

> ステータス: Beta — v0.1.0 パブリックプレビュー

## v0.1.0 — 2026-04-17（D-Day）

**WorldLines**（エンジンコードネーム `neonrp`）初のパブリックプレビュー。

### 同梱内容

**エンジンコア**
- Event-sourced 状態: append-only ログ + snapshots
- Branch / undo / redo
- Sandbox 生成、切替、破棄
- 決定性検証のための replay verification
- Schema 検証（`game_entity.schema.json`）
- エンティティインデックス（fuzzy + 任意の embedding によるハイブリッド検索）

**Agents と harness**
- Plan → Diff → Apply パイプライン
- trigger / tag / priority ルーティング付き dispatcher
- 多ターン agentic ループ（`--agentic`）
- エンジン同梱のビルトイン skills
- `task()` 経由の orchestrator 主導マルチ agent 協調

**LLM プロバイダ**
- OpenAI 互換（OpenAI、GLM、LM Studio、Ollama）
- テスト用 fixture 付き stub provider

**TUI（M9+）**
- Claude-Code 風会話型レイアウト
- `build` / `sandbox` / `play` モード
- Tab 補完付きスラッシュコマンド
- セッション管理（`/continue`、`/new`、`/sessions`）
- リアルタイム token カウンタ、ストリーム transcript、thinking チャネル

**インポート**
- SillyTavern キャラクターカード（JSON + PNG tEXt）

**テンプレート**
- `default` — 最小スターター
- `isekai` — 異世界スケッチ
- `kagura-island` — ミステリードラマ
- `tokyo-science-university` — 現代・日常
- `dark-train` — スリップストリーム短編
- **`stoneford`** — 看板サンプル: 5 都市、28+3 クエスト、6 agents、d20 戦闘ルール（[templates/stoneford/](templates/stoneford/README.ja.md) 参照）

### 既知の制約

- Python 3.11+ のみ。Windows は公式サポート外（WSL2 を使用）。
- Embedding 検索にはローカルの OpenAI 互換 embedding サーバが必要。
- 大規模世界（>2k エンティティ）はまだ性能最適化未完了。
- Web UI なし。v0.1 はターミナルのみ。
- `replay verify` は厳格: キャッシュ fixture なしの LLM 非決定性は逸脱としてフラグされます。temperature=0 か fixture を使用してください。
- マルチプレイヤー / 共有 branch 未対応。単一著者ワークフローのみ。
- Stoneford スターターは英語 / CJK 混在。ローカライズパイプラインはプレビュー品質。
- エンジンのライセンス条項は **プレビュー / 未確定**。[LICENSE](LICENSE) を参照。
- **Harness strictness（Harness の厳格性）**: NeonRP orchestration は完全なコンテキストに依存します。エンティティデータの欠落時は、手動での harness チューニングが必要になる場合があります。
- **Beta API 安定性**: エンジンコアは急速なイテレーション中です。決定性と柔軟性のバランスを取る中で、v0.2 および v0.3 で破壊的変更が入る見込みです。

### ロードマップ — 次のマイルストーン

**v0.2（2026 Q2 後半）**
- オープンデータフォーマット仕様（"WorldLines Data" 標準）
- agent ごとのポリシー言語（ops への強制制約）
- グラフベースの NPC 記憶
- Web コンパニオンビューア（読み取り専用）

**v0.3**
- 複数 branch 差分とマージツール
- 共有世界の協調 sandbox
- ファーストクラス Anthropic provider
- より豊かな combat referee DSL

**v1.0**
- 安定エンジン API
- 公開データフォーマット 1.0
- コミュニティテンプレートのマーケットプレイス

戦略的ナラティブは [task-thinking/gotomarket-releases-open-source-rethink-0326.md](../../task-thinking/gotomarket-releases-open-source-rethink-0326.md) を参照。

### 謝辞

東京にて Ludic Dynamics の創業者による単独開発。前身 `llm-rpg-starter` の初期テスターに感謝。

---

*バグ報告や機能要望は公開リポジトリの issue へ（リンクは D-Day に公開予定）。*
