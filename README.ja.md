# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 生きた世界への扉" width="640" />
</p>

<p align="center"><em>YouTube トレーラー — 近日公開。</em></p>

> ステータス: Preview（v0.1.0 — 2026-04-17 パブリックプレビュー）

> *AI チャットから Agentic AIRP へ。*
> ファイル裏付け・イベントソーシングの、生きた世界のためのエンジン。

WorldLines は [Ludic Dynamics](https://ludic-dynamics.com) が開発する
Agentic AIRP engine（AI RolePlay engine）です。エンジンバイナリの
コードネームは `neonrp`、リリースブランドは **WorldLines**。

ゲーム世界を、バージョン管理されたファイルベースのステートマシンとして
扱います。プレイ・編集・Agent のすべてが、揮発的なチャットログではなく
再現可能なアーティファクトになります。

---

## なぜ WorldLines か

従来の「AI とチャットする」UI は、context window が埋まった瞬間に
すべてを失います。WorldLines は本物のエンジンとしての保証を提供します:

- **Event-sourced state。** 各ターンは append-only な Events、
  Snapshots が高速な巻き戻しを可能にします。
- **Branch / Undo / Redo。** git branch のように物語の分岐を探索。
- **Sandbox & Replay。** 隔離環境で実験し、決定性を検証。
- **Multi-Agent オーケストレーション。** Orchestrator がドメイン
  Agents（town / dungeon / combat-referee / world-builder /
  rules-referee）にルーティングし、単一の状態を共有します。
- **Plan → Diff → Apply。** LLM が構造化ファイル操作を出力、
  反映前にレビュー可能。
- **File-backed world。** `game/` は単なる JSON と Markdown。
  git で管理、好きなエディタで編集。
- **Rich TUI。** プレイと構築の両方に使える Claude-Code 風の
  会話型ターミナル。
- **Local-first モデル。** GLM / OpenAI / LM Studio / Ollama。

### 位置付け — Claude Code との比較

|              | Claude Code                     | WorldLines                              |
|--------------|---------------------------------|-----------------------------------------|
| 領域         | コード編集 / ソフトウェア agent | ゲーム世界 / AIRP agent                 |
| 状態の単位   | ファイル + git                  | Events + Snapshots + branches           |
| 主ループ     | Plan → Edit → Test              | Plan → Diff → Apply → Save              |
| 同梱         | リポジトリは自前                | `stoneford` スターターテンプレ同梱      |
| Sandbox      | Shell / コンテナ                | エンジン内蔵 Sandbox + Replay           |

Claude Code がコードの IDE なら、WorldLines は生きた世界の IDE です。

> 備考：現時点で WorldLines の harness は Claude Code よりも厳格です — 信頼性のある orchestration のために完全なコンテキストを要求します。これはより高い決定性とデバッグのしやすさを得るための意図的なトレードオフであり、欠陥ではありません。

> **なぜプロプライエタリなエンジン + オープンなデータか？** WorldLines エンジンは、急速なイテレーションのさなかで orchestration の忠実性を保つため、プロプライエタリなプレビューとしてリリースされています。一方でゲームデータフォーマット、スターターワールド（Stoneford など）、統合プロトコルは、相互運用可能な AIRP エコシステムを育むためにオープンにされています。

---

## クイックスタート

```bash
# 1. インストール（他の方法は INSTALL.ja.md 参照）
uv tool install -e /path/to/worldlines

# 2. stoneford スターターを生成して起動
mkdir my-world && cd my-world
neonrp init
neonrp game new --template stoneford

# 3. TUI でプレイ
neonrp tui
```

`look around` と入力して Enter。これがあなたの最初の agentic ターンです。

30 分のウォークスルーは [QUICKSTART.ja.md](QUICKSTART.ja.md) を参照。

---

## モジュールマップ

- [INSTALL.ja.md](INSTALL.ja.md) — wheel / ソース / `uv tool` でインストール
- [QUICKSTART.ja.md](QUICKSTART.ja.md) — 30 分の初回プレイガイド
- [CONCEPTS.ja.md](CONCEPTS.ja.md) — Events、Snapshots、branches、Agents、Sandboxes
- [CLI_REFERENCE.ja.md](CLI_REFERENCE.ja.md) — すべての `neonrp` コマンド
- [TUI_GUIDE.ja.md](TUI_GUIDE.ja.md) — ターミナル UI リファレンス
- [RELEASE_NOTES.ja.md](RELEASE_NOTES.ja.md) — v0.1.0 スコープとロードマップ
- [templates/stoneford-worldlines/](templates/stoneford-worldlines/README.ja.md) — サンプル世界と Agents
- [CONTRIBUTING.ja.md](CONTRIBUTING.ja.md) — コントリビュート方法
- [LICENSE](LICENSE) — プロプライエタリのプレビュー条件

## コミュニティと連絡先

- Issue と議論: GitHub（リンクは 2026-04-17 D-Day に公開予定）
- Founder / メンテナ: Ludic Dynamics（東京）
- 連絡先: `hello@ludic-dynamics.com`（仮）

---

## 著作権と謝辞

Copyright © 2026 worldlines-nikoloside, redoctober. All rights reserved.

WorldLines はプロプライエタリなエンジンであり、評価目的のプレビュー
としてのみリリースされます。再利用、再配布、派生物に対するライセンスは
付与されません。詳細は [LICENSE](LICENSE) を参照してください。

Ludic Dynamics コミュニティの皆さん、そして amber をはじめ本リリースを
支えてくれた友人たちに感謝します。

*WorldLines と Ludic Dynamics は Ludic Dynamics の商標です。*
