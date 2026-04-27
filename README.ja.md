# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 生きた世界への扉" width="640" />
</p>

<p align="center"><em>YouTube トレーラー — 近日公開。</em></p>

<table align="center">
  <tr>
    <td width="50%" align="center"><img src="./assets/helloworld.jpg" alt="WorldLines TUI 起動画面" /></td>
    <td width="50%" align="center"><img src="./assets/cards/D0%20Hero%20%28deck%20%C2%B7%20JA%29.png" alt="WorldLines — Hero" /></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/cards/D1%20%E3%83%9F%E3%83%A9%E3%81%AE%E3%83%84%E3%82%B1%20%28deck%20%C2%B7%20JA%29.png" alt="ミラのツケ · ストーリーカード" /></td>
    <td align="center"><img src="./assets/cards/D2%20%E8%80%81%E3%82%A6%E3%82%A7%E3%82%A4%E3%81%AE%E8%AA%98%E3%81%84%20%28deck%20%C2%B7%20JA%29.png" alt="老ウェイの誘い · ストーリーカード" /></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/cards/D3%20%E3%82%B1%E3%82%99%E3%83%BC%E3%83%A0%E3%83%95%E3%82%9A%E3%83%AC%E3%82%A4%20%28deck%20%C2%B7%20JA%29.png" alt="ゲームプレイ" /></td>
    <td align="center"><img src="./assets/cards/D4%204%20%E3%81%A4%E3%81%AE%E4%B8%96%E7%95%8C%20%28deck%20%C2%B7%20JA%29.png" alt="4 つの世界" /></td>
  </tr>
</table>

> ステータス: **v0.1.8 stable**（2026-04-27）· 次期: **v0.2.0**（計画中）

> *Agents for Role Play. Agents for Game. Agents as a Game.*
> ファイル裏付け・イベントソーシングで、生きた世界を駆動するエンジンです。

> **まだ非常に早期です — オープンに開発しています。** WorldLines は
> 活発に開発中です。新しい遊び方、新しい orchestration モード、新しい
> モジュールが継続的にリリースされます。ひっそり完成形を磨くより、
> 早めに出してあなたと一緒に反復していきたいと考えています。

WorldLines は **nikoloside** と **redoctober** が共同開発し、
[Ludic Dynamics](https://ludicdynamics.com) と共に継続的に推進している
Agentic AIRP engine（AI RolePlay engine）です。エンジンバイナリの
コードネームは `neonrp`、リリースブランドは **WorldLines** です。

ゲーム世界をバージョン管理されたファイルベースのステートマシンとして
扱うため、プレイ、編集、Agent のすべてが揮発的なチャットログではなく
再現可能なアーティファクトになります。

---

## なぜ WorldLines か

従来の「AI とチャットする」UI は、context window が埋まった瞬間に
すべてを失います。WorldLines は本物のエンジンとしての保証を提供します。

- **⭐ ファイル永続化された記憶とワールド状態。** 記憶・セーブ・NPC・
  Agent がすべてプレーンな JSON と Markdown としてディスク上に存在
  します。クラウドなし、データベースなし、隠し状態なし。フォルダを
  開けるならその世界はあなたのものです。
- **インデックスとコンテキストを自動注入。** WorldLines はファイル
  インデックスとローカル ベクタ DB を自動構築し、毎ターン関連する
  ゲームデータだけを各 Agent のコンテキストに自動注入します。
  lorebook を手作業で管理する必要はありません。
- **Event-sourced state。** 各ターンは append-only な Event として記録され、
  Snapshots が高速な巻き戻しを可能にします。
- **Branch / Undo / Redo。** git branch のように物語の分岐を探索できます。
- **Sandbox & Replay。** 隔離環境で実験し、決定性を検証できます。
- **Orchestrator 駆動の multi-agent。** Orchestrator がドメイン
  Agents（town / dungeon / combat-referee / world-builder /
  rules-referee）にルーティングし、一つの共有状態の上で動作します。
- **Plan → Diff → Apply。** LLM は構造化されたファイル操作を出力し、
  反映前にレビューできます。
- **Rich TUI。** プレイと構築の双方に使える Claude-Code 風の
  会話型ターミナルです。
- **Local-first モデル。** GLM、OpenAI、LM Studio、Ollama に対応。

### WorldLines と他ツールの比較

|                       | Character.AI     | SillyTavern               | Claude Code             | **WorldLines**                     |
|-----------------------|-------------------|----------------------------|-------------------------|-------------------------------------|
| 主な領域              | キャラクター チャット | Prompt フロントエンド      | コード編集               | 生きているゲーム世界                 |
| ワールドの保存先       | 運営サービス       | Prompt 設定 + チャットログ  | ディスク上のコードベース  | **プレーンファイル + git**          |
| 記憶と検索            | クラウド / 不透明   | 手動 lorebook              | コードベース検索          | **自動ファイル索引 + ベクタ DB**     |
| Multi-agent           | —                 | —                          | タスクごとにサブ agent    | Orchestrator + ドメイン agents       |
| ローカル優先 LLM      | ✗                | 自分で持ち込み              | API のみ                | GLM / LM Studio / Ollama             |
| 決定性 / Replay       | —                 | —                          | —                       | **Sandbox + Replay**                 |

Claude Code がコードの IDE なら、WorldLines は生きた世界の IDE です
——記憶・検索・orchestration が組み込まれた状態で。

> 各競合との完全な比較は
> [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa)
> （vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph · vs OpenClaw）を参照。

> 備考：現時点で WorldLines の harness は Claude Code よりも厳格です — 信頼性のある orchestration のために完全なコンテキストを要求します。これはより高い決定性とデバッグのしやすさを得るための意図的なトレードオフであり、欠陥ではありません。


---

## インストール

### ワンライナー

```bash
# macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh

# Windows (PowerShell)
irm https://worldlines.gg/install.ps1 | iex
```

`uv` が未導入の場合はインストールし、続いて `uv tool install worldlines`
を実行します。`neonrp --help` あるいは `worldlines` のみで確認できます。

### ダブルクリック起動

ターミナルに触れたくない方向けに、プラットフォーム別ランチャーを
ダブルクリックするだけで使えます。初回は自動でインストールを実行し、
2 回目以降は自己アップデートし、その後 TUI に引き渡します。

| プラットフォーム | ファイル             | ダウンロード |
|------------------|----------------------|--------------|
| macOS            | `WorldLines.command` | [latest](https://worldlines.gg/WorldLines.command) |
| Windows          | `WorldLines.bat`     | [latest](https://worldlines.gg/WorldLines.bat)     |
| Linux            | `WorldLines.sh`      | [latest](https://worldlines.gg/WorldLines.sh)      |

ダウンロード後（macOS / Linux）、初回に一度だけ `chmod +x` を実行してください。

```bash
chmod +x ~/Downloads/WorldLines.command   # または WorldLines.sh
```

あとはデスクトップや Dock にドラッグし、他のショートカットと同様に扱えます。

### 中国のユーザー向け

一部の中国本土のネットワークでは GitHub Releases や Cloudflare 経由の
ドメインが制限されることがあります。もし
`curl https://worldlines.gg/install.sh` がタイムアウトする場合は、
以下をお試しください。

```bash
# GitHub から直接取得（Cloudflare リダイレクトより速いことがあります）:
curl -LsSf \
  https://github.com/LudicDynamics/WorldLines/releases/latest/download/install.sh \
  | sh

# あるいは uv に清華大学の PyPI ミラーを使わせる:
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv tool install worldlines

# 両方を同時に使う:
CHINA_MIRROR=1 curl -LsSf https://worldlines.gg/install.sh | sh
```

自動アップデート（`neonrp self-update`）も `UV_DEFAULT_INDEX` を尊重するため、
シェルプロファイルで export しておけば今後のアップグレードもミラー経由に
なります。

### 開発者向け — editable install

```bash
uv tool install -e /path/to/worldlines
neonrp --help
```

wheel・ソース・別ミラーなど全オプションは
[docs.worldlines.gg/docs/guides/launcher](https://docs.worldlines.gg/docs/guides/launcher)
を参照してください。

---

## クイックスタート

```bash
# 新規ディレクトリ — /init だけでビルドモードを開始できます
mkdir my-world && cd my-world
neonrp init

# あるいは看板サンプルとして stoneford スターターを展開
neonrp game new --template stoneford

# TUI を起動
neonrp tui
```

新規プロジェクトでは同梱の builtin skill が自動で有効になります。
`/game new` は任意で、スターターワールドと play-agent のひな形を
すぐに欲しい場合にのみ使用します。

> **初回起動時にランチャーが API セットアップを案内します。** すでに
> **Claude Code (MCP)** をお持ちならそれを選択。または **Anthropic /
> OpenAI / DeepSeek / OpenRouter / [GLM 無料枠](https://zhipuai.cn)** 用の
> キーを貼り付け。あるいは **Ollama / LM Studio** のローカルサーバを指定。
> キーは `~/.neonrp/config.json` に自動保存され、あとで
> `[3] settings / api` から変更できます。
> [プロバイダ完全ガイド →](https://docs.worldlines.gg/docs/getting-started/quickstart)

`look around` と入力して Enter。これがあなたの最初の agentic ターンです。

<p align="center">
  <img src="./assets/gameplay.jpg" alt="WorldLines ゲームプレイ — 霧のなかで Stoneford に辿り着く" width="720" />
</p>

10 分のウォークスルーは
[docs.worldlines.gg/docs/getting-started/quickstart](https://docs.worldlines.gg/docs/getting-started/quickstart)
を参照してください。

---

## ドキュメント

完全なドキュメントは公式サイトにあります — このリポジトリには入り口のみ。

| トピック              | URL                                                                              |
|-----------------------|----------------------------------------------------------------------------------|
| はじめに              | [docs.worldlines.gg/docs/getting-started](https://docs.worldlines.gg/docs/getting-started) |
| コア概念              | [docs.worldlines.gg/docs/core-concepts](https://docs.worldlines.gg/docs/core-concepts)（Worlds · キャラクター & Multi-Agent · Agents & オーケストレーション · エンジンモード · Sessions · 記憶システム） |
| ガイド                | [docs.worldlines.gg/docs/guides](https://docs.worldlines.gg/docs/guides)（Launcher · ワールドライフサイクル · SillyTavern インポート · Discord チュートリアル） |
| Q&A / 比較            | [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa)（vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph · vs OpenClaw） |
| Changelog・ロードマップ | [docs.worldlines.gg/docs/changelog](https://docs.worldlines.gg/docs/changelog) |

**このリポジトリ内:**

- [templates/stoneford-worldlines/](templates/stoneford-worldlines) — サンプルワールドと Agents（submodule）
- [CONTRIBUTING.ja.md](CONTRIBUTING.ja.md) — コントリビュート方法
- [SECURITY.md](SECURITY.md) — 脆弱性報告の方法
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — コミュニティの期待値
- [LICENSE](LICENSE) — プロプライエタリプレビュー条件

## なぜ AGPL · コントリビューターポリシー

OSS 部分（`templates/stoneford-worldlines/` など）は **AGPL-3.0** です。あなたが stoneford の上に書く新しい世界・テンプレート・モジュールは、同じオープンコモンズに入り、誰かにこっそり fork されてクローズドソース製品にされることはありません。コントリビューターへ：

- 🪪 **著作権は保持されます** —— copyright assignment は要求しません。
- 🟢 **既定の in-bound ライセンスは AGPL-3.0** —— 他の OSS 部分と同条件。
- 🛡 **無断でクローズドソース化はしません** —— 追加許諾なしにクローズドソース版へ取り込みません。

エンジンコア（`neonrp`）は proprietary preview です —— 詳細は [CONTRIBUTING.md → License Asymmetry](CONTRIBUTING.md#license-asymmetry)。

## コミュニティと連絡先

- Web: [worldlines.gg](https://worldlines.gg) · Docs: [docs.worldlines.gg](https://docs.worldlines.gg)
- Discord: [discord.gg/HJYWbdqWrE](https://discord.gg/HJYWbdqWrE) · Patreon: [patreon.com/cw/WorldLines](https://www.patreon.com/cw/WorldLines)
- GitHub: [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)
- Contact: `info@worldlines.gg`

---

## 著作権と謝辞

Copyright © 2026 **nikoloside**, **redoctober**. All rights reserved.

WorldLines はプロプライエタリなエンジンであり、評価目的のプレビュー
としてのみリリースされます。再利用、再配布、派生物に対するライセンスは
付与されません。詳細は [LICENSE](LICENSE) を参照してください。

**nikoloside** と **redoctober** が開発・メンテナンスを行い、Ludic Dynamics
コミュニティによって継続的に運営・実験・進化が続けられています。
先行プロジェクト `llm-rpg-starter` の初期参加者（Ludic Dynamics
コミュニティ）による寛大で熱い議論・交流・協力・支援に特別な感謝を：
**Amber**、**琛琛**、**Claire**。

*WorldLines と Ludic Dynamics は Ludic Dynamics の商標です。*
