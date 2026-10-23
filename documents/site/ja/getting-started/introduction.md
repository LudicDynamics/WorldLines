---
title: "はじめに"
description: "WorldLines はエージェント型シミュレーションエンジン —— 生きた AI agent の村と、あなたが共に遊ぶ場所。"
---

<!-- section: what-is-worldlines -->
## WorldLines とは

WorldLines は **エージェント型シミュレーションエンジン** です。world-agent が place-agent につながり、各 place-agent が soul-agent をホストします。ここでは全員が agent。あなたは分身端末を通じて参加します。

これは「ひとりの AI キャラと会話する」ものではありません。**マルチエージェント社会** がリアルタイムで動き、各 agent が固有の目標・記憶・制約を持ちます。

私たちは world-agent・place-agent・soul-agent をひとつの生きたシミュレーションに接続する harness を構築しました。このエンジンで動かしたいもの：**インタラクティブ体験の創造 · マルチエージェント社会実験 · エージェント研究の推進 · 人格モデル・世界モデルのベンチマーク。**

現在のステータス: **v0.3.0**（2026-07-13）。[今すぐ遊ぶ →](https://hub.worldlines.gg)

**nikoloside** と **redoctober** が共同開発、[Ludic Dynamics](https://ludicdynamics.com) と共に推進。

<!-- section: ways-to-play -->
## 3 つの遊び方

> **👉 はじめての方は Stoneford · Elena —— マルチエージェントの村 から。** Elena と Rowan の二人は、それぞれが*自分で考え、記憶し、行動する* —— ナレーターが書いた台詞をなぞるのではありません。WorldLines が何を違えているのか、最もはっきり味わえます。下のランチャーでインポートすれば村の全体を、あるいは [WebHub で Elena に会う](https://hub.worldlines.gg/play/souls/elena) ならワンクリックで。

**1. WorldLines ランチャー — デスクトップ、ワンダウンロード。** [worldlines.gg](https://worldlines.gg) からランチャーを入手し、ダブルクリックして **世界をインポート** —— 公式の世界はすぐ遊べる状態で、ターミナルは要りません。Python と LLM プロバイダの設定もやってくれます。

**2. WebHub — ブラウザ、インストール不要。** [hub.worldlines.gg](https://hub.worldlines.gg) を開き、サインインして遊ぶ。世界とソウルのカタログを閲覧し、AI 支援スタジオで自作し、公開レジストリに登録。クラウドエージェントが動かしてくれます。

**3. CLI & TUI — ローカル、オープンツール（上級者向け）。** `worldlines` バイナリをインストールし、Claude Code 風の TUI でターミナル内で遊ぶ。サンプル・ツール・プロトコルはオープンソース（AGPL-3.0）。Ollama / LM Studio / GLM で自分のモデルを動かせます。

<!-- section: why-worldlines -->
## なぜ WorldLines なのか

従来の「AI とチャットする」インターフェースは、コンテキストウィンドウが埋まった瞬間にすべてを失います。WorldLines は本物のエンジンとしての保証を提供します:

- **⭐ ファイル永続化された記憶とワールド状態** — 記憶・セーブ・NPC・Agent がすべてプレーンな JSON と Markdown としてディスク上に存在します。クラウドなし、データベースなし、隠し状態なし。フォルダを開けるならその世界はあなたのものです。
- **自動インデックス化されたコンテキストを自動注入** — WorldLines はファイルインデックスとローカルのベクタ DB を自動構築し、毎ターン関連するゲームデータだけを各 Agent のコンテキストに自動注入します。lorebook を手作業で管理する必要はありません。
- **イベントソース型のステート** — 各ターンは追記専用のイベント。Snapshot により巻き戻しが高速。
- **Branch / Undo / Redo** — git のブランチのように物語の分岐を探索できます。
- **Sandbox と Replay** — 実験を隔離環境で実行し、決定性を検証できます。
- **Orchestrator 駆動のマルチ Agent** — Orchestrator が共有ステート上でドメイン Agent（town / dungeon / combat-referee / world-builder / rules-referee）にルーティングします。
- **Plan → Diff → Apply** — LLM が構造化されたファイル操作を出力し、適用前にレビューできます。
- **リッチな TUI** — Claude Code 風の対話型ターミナルで、プレイもビルドも行えます。
- **ローカルファーストなモデル** — GLM、OpenAI、LM Studio、Ollama に対応。

<!-- section: positioning -->
## WorldLines と他ツールの比較

|                       | Character.AI     | SillyTavern               | Claude Code             | **WorldLines**                     |
|-----------------------|-------------------|----------------------------|-------------------------|-------------------------------------|
| 主な領域              | キャラクター チャット | Prompt フロントエンド      | コード編集               | 生きているゲーム世界                 |
| ワールドの保存先       | 運営サービス       | Prompt 設定 + チャットログ  | ディスク上のコードベース  | **プレーンファイル + git**          |
| 記憶と検索            | クラウド / 不透明   | 手動 lorebook              | コードベース検索          | **自動ファイル索引 + ベクタ DB**     |
| Multi-agent           | —                 | —                          | タスクごとにサブ agent    | Orchestrator + ドメイン agents       |
| ローカル優先 LLM      | ✗                | 自分で持ち込み              | API のみ                | GLM / LM Studio / Ollama             |
| 決定性 / Replay       | —                 | —                          | —                       | **Sandbox + Replay**                 |

Claude Code がコードのための IDE なら、WorldLines は生きた世界のための IDE です——記憶・検索・orchestration が組み込まれた状態で。

各競合との完全な比較は [Q&A](/docs/qa/what-is-airp) を参照 — vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph。

> 注: WorldLines の harness は現時点で Claude Code より厳格です。信頼性の高いオーケストレーションのために完全なコンテキストを必要とします。これは欠陥ではなく、より高い決定性とデバッグ容易性のための意図的なトレードオフです。

<!-- section: next-steps -->
## 次のステップ

- [クイックスタート](/docs/getting-started/quickstart) に従って、10 分以内に最初のターンを実行
- [コアコンセプト](/docs/core-concepts/worlds) を学ぶ — Event、Snapshot、Branch、Agent
- [ロードマップ](/docs/roadmap) を確認 — 次の予定
- [Q&A](/docs/qa/what-is-airp) — 既存ツールとの比較
