# WorldLines

**言語:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> **WorldLines —— あなたとあなたのキャラクター agent のための、マルチエージェント世界シミュレーションエンジン。**
> オープンソース:**NeonRP** エンジン(Apache-2.0)、**WorldLines** プロダクト(AGPL-3.0)、ドキュメントとベンチマーク(CC BY 4.0)。

<p align="center">
  <img alt="GitHub Stars" src="https://img.shields.io/github/stars/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Forks" src="https://img.shields.io/github/forks/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Issues" src="https://img.shields.io/github/issues/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <a href="https://worldlines.gg"><img alt="Live" src="https://img.shields.io/badge/Live-worldlines.gg-8b5cf6?style=flat-square" /></a>
  <img alt="LINUX DO" src="https://img.shields.io/badge/LINUX%20DO-WorldLines-8b5cf6?style=flat-square" />
  <a href="https://doi.org/10.1145/3800965.3834285"><img alt="Paper" src="https://img.shields.io/badge/Paper-CHI%20PLAY%20Companion%20%2726-b31b1b?style=flat-square" /></a>
  <a href="https://arxiv.org/abs/2606.16014"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2606.16014-8b5cf6?style=flat-square" /></a>
  <img alt="Engine license" src="https://img.shields.io/badge/neonrp-Apache--2.0-blue?style=flat-square" />
  <img alt="Product license" src="https://img.shields.io/badge/worldlines-AGPL--3.0-blue?style=flat-square" />
</p>

<p align="center">
  <img src="./worldlines/assets/hero.png" alt="WorldLines — 生きた世界への扉" width="640" />
</p>

## WorldLines とは

たいていの AI ロールプレイが用意してくれるのは、おしゃべりの相手になるキャラクターです。WorldLines が用意するのは、
**そのキャラクターが暮らしている世界**。場所があり、物価があり、勢力があり、それぞれの考えで動くほかのキャラクターがいて、
崩れないルールがあります。ただ話すだけではありません。どこかへ出かけ、取引をまとめ、喧嘩を売る。世界はそれに、
あとまで残る結果で応えます。

私たちはこう考えています。ゲームの時代、私たちはシミュレーターをコードで書いた。agent の時代には、agent でシミュレーターを編成する。そして TRPG こそが最良の世界シミュレーターです。あなたは AI キャラクターと一緒に、この TRPG 世界シミュレーターの中で思うままに遊べます。

**TRPG × AIRP:TRPG はそれ自体がひとつの世界シミュレーションです。それが私たちの核です。**

その下で動いているのが **NeonRP**。ひとつの考え方で作られた世界シミュレーションエンジンです ——
*物語はモデルが語り、ルールは世界が守る。*

- **先に相談、次に解決。** やりたいことを伝えるだけ。相談の拍ではその場のキャラクターが応じ、どうするかを話し合います。
  判定役が「まとまった」と判断すると(あるいはあなたが「決まり」/ `@dm` と言うと)、解決の拍で振るべきダイスを振り、
  物語を書き、検証済みの変更をひとつだけ世界に反映します。
- **三者それぞれ。** 世界、あなた、そして各キャラクターが、それぞれ自分の意思を持ちます。あなたの言葉は*試み*であって
  事実ではなく、キャラクターは自分で決めます。
- **世界はファイルでできている。** 読めて、diff が取れて、バージョン管理できるプレーンな JSON / Markdown。ターンのたびに
  コミットが積まれ、そこから巻き戻すことも、分岐させることもできます。

## チームとビジョン

私たちは**東京大学**の PhD および研究者、そしてゲーム実務者からなる学際的チーム（社会学、経済学、コンピュータグラフィックス、AIエージェント、仮想世界）— **Ludic Dynamics** です。

TRPG、ギャルゲー、乙女ゲームに育ちました。AI が今のように普及する以前から、長年にわたり日本語文化翻訳のボランティア活動を続け、テーブルトークやゲームグラフィックスエンジンの世界に深く携わり、日本のビジュアルノベルの Steam 展開を支援してきました。パンデミック以降、私たちは AI ロールプレイとナラティブゲームの世界に没頭しました——週末のたびに、深夜までセッションを走らせ、世界を構築し、「物語が本当に息づく」感覚を追い続けてきました。

十を超える国々をまたいで時空を冒険し、異世界の失われた歴史を探り、大切な人を救うために何度も同じ一日に死に戻り、並行する時間線を辿って唯一の世界線を見つけ出し、歴史を召喚して理想をかけた戦いを戦い抜いてきました。

WorldLines はその執念から生まれました。

> **Orchestrated Reality · 編成された現実。** Harness を通じて世界と AI ソウルをシミュレート —— 世界には物理的一貫性が、NPC には認知的一貫性がある。エージェントをコードするな。エージェントで世界を編成せよ。

harness によって「マルチエージェント × ワールド × ソウル」のシステムを構築しました。このエンジンで実現したいこと：**インタラクティブ体験創造 · マルチエージェント社会実験 · エージェント研究推進 · 人格・世界モデルのベンチマーク。**

言語モデルと agent は、物語を生成するだけのものではないと私たちは考えています。法則とエンジンと境界条件を与えれば、世界そのものをシミュレートできます。世界シミュレーションはそれ自体がゲームになりますし、すべてのキャラクター agent と世界をひとつの土台にして、その上にゲームを作ることもできます。このシミュレートされた世界の中で、すべてのキャラクターがプレイヤーとともに本当に生きている。世界に生きるキャラクターだけが、本当のキャラクターです。

- **シミュレーションから物語を。** NeonRP は、シミュレートされた世界と、それぞれの目的を持つキャラクター agent のせめぎ合いから物語を生み出します。
- **誰でも書けるオーケストレーション。** ターンの進め方は TRPG からマーダーミステリーまで、言葉だけで設計でき、コンテンツとして共有できます。
- **キャラクター・世界・遊び方を切り離す。** キャラクターの素材と設定、世界の素材と設定、遊びのルールはそれぞれ独立した部品で、自由に組み合わせられます。
- **速いエンジンに、どんなフロントエンドでも。** AI エンジンは速さ・堅牢さ・自由度に徹し、フロントエンドを載せればそのままゲームクライアントになります。
- **エンジンはオープン、プラットフォームはみんなに。** エンジンはオープンソースで、自分の API キーで動きます。[worldlines.gg](https://worldlines.gg) は一般のプレイヤー向けのプラットフォームです。コミュニティはその両方の上でつくります。

それぞれについて一本ずつ:[ビジョン](https://docs.worldlines.gg/docs/vision/overview)。

> **Agent Role Play。** 人々はすでに Claude Code や Codex の中で直接ロールプレイしています —— エージェント型システムにキャラクターとシーンを動かさせて。それはプロンプトベースのチャットを超えた新しいパラダイムであり、私たちが目指しているのはまさにそこです。WorldLines はその同じエージェントの筋力を、**より速く、モデル非依存（DeepSeek / OpenRouter / ローカル / 無料モデルで動かせる）、そしてスケールするマルチエージェント**にします —— ソウルたちが本当に息づく、生きてプレイできる世界へと変えるのです。

## デモ & 動画

<p align="center">
  <a href="https://youtu.be/M_0xX8OZMa0">
    <img src="https://img.youtube.com/vi/M_0xX8OZMa0/maxresdefault.jpg" alt="WorldLines · Demo" width="640"/>
  </a>
</p>
<p align="center"><em>▶ YouTube でデモを観る</em></p>

## このリポジトリの中身

| フォルダ | 内容 | ライセンス |
|---|---|---|
| [`neonrp/`](./neonrp) | エンジン:ターンループ、スキーマ、パック(`rpg`、`pct`、`werewolf`、`monopoly`)と mixins(`economy`、`factions`)、テンプレート、CLI、ターミナル UI、SDK | Apache-2.0 |
| [`worldlines/`](./worldlines) | プロダクト:Web UI(3.0)、ランチャーパッケージ、テンプレート、サンプルワールド、チュートリアル。NeonRP デスクトップアプリ(macOS) | AGPL-3.0 |
| [`documents/`](./documents) | 仕様(world · soul · template · contract · pack)と [docs.worldlines.gg](https://docs.worldlines.gg) のソース | CC BY 4.0 |
| [`benchmarks/`](./benchmarks) | エンジンの設計判断を裏づけるテストスイート | コード Apache-2.0 · データ CC BY 4.0 |
| `CLAUDE.md` · `AGENTS.md` · `.claude/` · `.agents/` | Claude Code / Codex 向けのキャラクター・ワールド制作ワークベンチ(後述) | AGPL-3.0 |

## このリポジトリと PyPI パッケージ

PyPI パッケージは同じコードから作られ、オープンソースではない部分を含みます([`neonrp/LICENSE-PROPRIETARY.md`](./neonrp/LICENSE-PROPRIETARY.md)):

| | このリポジトリ | PyPI `neonrp` / `worldlines` |
|---|---|---|
| ターン | 解決ビート | 相談ビート + 解決ビート、同梱のオーケストレーション |
| Web UI | ワークベンチ、テストベンチ、プレイ画面 | さらに Hub、標準フロントエンド、スマホのチャット画面 |
| 同梱の世界 | 灰橡宅、石津鎮 | 同じ。ほかの公式の世界は worldlines.gg にサインインして取得 |

このリポジトリだけで、自分の API キーを使って動かせます。

## クイックスタート

```bash
pip install worldlines          # または: uv tool install worldlines — プロダクト本体。neonrp エンジンも一緒に入ります
worldlines                      # ローカル Web UI → http://127.0.0.1:8787/local
neonrp                          # ターミナル:「Welcome to WorldLines」ランチャー
```

**デスクトップアプリ(macOS、Apple シリコン):**[NeonRP をダウンロード](https://worldlines.gg/downloads/NeonRP_aarch64.dmg)。公証されていないため、初回は「システム設定 › プライバシーとセキュリティ」で「このまま開く」を押してください。初回起動時にアプリがエンジンをインストールします。

**デスクトップアプリ(Windows、x64):**[NeonRP をダウンロード](https://worldlines.gg/downloads/NeonRP_x64-setup.exe)。署名なし:SmartScreen に止められたら「詳細情報」›「実行」を押してください。

ローカル版はここから入れます(PyPI パッケージ。このリポジトリがそのソースです)。[worldlines.gg](https://worldlines.gg) はインストール不要のオンラインプレイです。
どちらのコマンドも起動時に新しいリリースを確認して自動更新します(先に確認したい場合はゲーム内で `/update mode prompt`)。
リリースノート:[`neonrp/CHANGELOG.md`](./neonrp/CHANGELOG.md) · [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases)。ワンライナーのインストーラーも引き続き使えます:
`curl -LsSf https://worldlines.gg/install.sh | sh`(macOS / Linux)· `irm https://worldlines.gg/install.ps1 | iex`(Windows)。
Python 3.10 以上が必要です。初回起動時に、使うモデルの選択を案内します。Worldlines アカウントでログインする(`/login`:モデル中継と
Jev 判定役。自分のキーは不要)か、自分のキーを使います(OpenCode Zen、DeepSeek、OpenRouter、Anthropic、OpenAI、GLM、または任意の
OpenAI 互換サーバー)。API キーはあなたのマシンの中にだけ保存されます。

## 遊ぶ

ワールドを選ぶと、そのワールド固有のオープニングシーンから始まります。あとは、やりたいことをそのまま伝えるだけです:

```text
你:   艾琳娜，陪我去杂货铺买一瓶小治疗药水，价你来砍。
主持: 杂货铺在主街，你们走了十来分钟。艾琳娜在柜台前和老苇讲价，说好谈下来的差价一半归她……
      金 18 → 8 · 两人到杂货铺 · +小治疗药水
```

1 ターンは二拍です。**相談**の拍では進行役(「主持」= GM として表示)が場面を描き、その場のキャラクターが応じて、何をするかを話し合います。
話がまとまったら(判定するのは、Worldlines アカウントがあれば Jev、なければそのプレイ自身のモデル。「決まり」や `@dm` ですぐ進めることも
できます)、**解決**の拍で起きたことを語り、変化を世界に書き込みます。状態はまずすぐに書き込まれ、裏でもう一度確認されます。
確認で誤りが見つかれば修正され、何が変わったかを知らせます。

| テンプレート | 内容 |
|---|---|
| グレイオーク館 · 閉ざされた扉 | 霧の小路の突き当たりの古い館。三日前、館の主は扉をくぐったきり出てこない。一夜、口の堅い執事、百面ダイスの推理 |
| ストーンフォード · 霧の退く夜 | 霧が退くのは一年に一夜だけ。夜二つと昼一つで、北門を抜ける備えを町で揃える |

ローカル版に入っているのはこの二つの世界です。ほかの公式の世界は Hub にあり、ログインしなくても見られて、
[worldlines.gg](https://worldlines.gg)(またはローカル Web UI の「Hub ↗」)からそのままオンラインで遊べます。Worldlines アカウントで
ログインすると、ダウンロードしてローカルで遊べます。

## スクリーンショット


<p align="center">
  <img src="./worldlines/assets/readme-turn-ja.png" alt="WorldLines" width="860" />
</p>
<p align="center"><em>1 ターンの二拍 —— 相談の拍で進行役とキャラクターがこれから起きることを決め、解決の拍でダイスを振り、語りを書き、結果が世界に入る。プレイヤーは「目の前の全員を斬る」と言った。世界は忖度しなかった。</em></p>

<p align="center">
  <img src="./worldlines/assets/readme-tui-ja.png" alt="WorldLines" width="860" />
</p>
<p align="center"><em>ターミナルの灰樫邸・裏庭 —— 植木鉢の下から鍵が出てくるが、鍵穴にはさっき折ったヘアピンの半分が詰まっていて入らない。物は残る。右の所持品がひとつ増えている。</em></p>

<p align="center">
  <img src="./worldlines/assets/readme-orchestration-ja.png" alt="WorldLines" width="860" />
</p>
<p align="center"><em>編成 —— 一局の進め方はひとつの状態機械:相談 → 解決、戦闘になれば戦闘裁定役に渡し、終われば戻る。この図がテンプレートの中の編成そのもので、これを変えれば遊び方が変わる。</em></p>

## 誰のためのものか

### 🎮 AI ロールプレイプレイヤー

**Character.AI、SillyTavern、AI 酒場**から来たあなた。深いキャラクター会話が好きなのに、世界はいつも忘れてしまう。

WorldLines は**本当の記憶**を持つキャラクターを渡します。3 セッション前のあなたの言葉を覚え、自分の意図と目標を持ち、他のキャラクターと同じ世界に生きて互いを覚えています。ターンは速く、一拍は数秒です。

その先へ。一緒に編成を作ってみませんか。一局の進め方は自分で設計でき、編成のツールを組み合わせて試し、欲しい遊び方を組み立てられます。

→ [オンラインでプレイ](https://worldlines.gg) · [AI キャラクターカードを世界に持ち込む](https://docs.worldlines.gg/docs/players/your-character) · [言葉にすれば規則になる編成](https://docs.worldlines.gg/docs/vision/orchestration-for-everyone)

### 📖 ギャルゲー · 乙女ゲーム · ビジュアルノベルファン

**Ren'Py、TyranoBuilder、分岐ナラティブ**が好き。でもすべてのルートを手書きするのには疲れた。分岐するだけでなく、*応えてくれる*物語が欲しい。

WorldLines ではキャラクター、世界のルール、トーンを決めれば、エージェントがリアルタイムで物語を生成し、すべての選択が波紋を広げます。エンジンは土台だけを受け持ち、見せ方はフロントエンドに任せます。Godot や TypeScript の重いフロントエンドのワークベンチを試して、立ち絵・演出・分岐画面を好きな形に作り、できたものをエンジンに書き戻してテンプレートの一部にすることができます。

→ [Godot との連携](https://docs.worldlines.gg/docs/developers/godot) · [Godot サンプル](./worldlines/examples/clients/godot) · [TS サンプルフロントエンド](./worldlines/examples/clients/ts) · [開発者向けクイックスタート](https://docs.worldlines.gg/docs/developers/quickstart)

### ✍️ TRPG GM & ワールドクリエイター

**Foundry VTT、Discord、紙とペン**で卓を回している。遊ぶ時間より準備の時間のほうが長い。

WorldLines は GM のエンジンです。ルール・NPC・トーンという制約を決めれば、エージェントが世界を動かします。自動で索引されるロア、NPC ごとの記憶、ダイスの裁定役。

私たちが一番やりたいのは、編成のツールをあなたと一緒に研究することです。いまの「相談 → 解決」とプレイ契約という枠組みで卓の需要を満たせるのか、何が足りないか、どこが窮屈か。Discord で話しましょう。

→ [クイックスタート](https://docs.worldlines.gg/docs/players/quickstart) · [ストーンフォード スターターワールド](./worldlines/templates/stoneford-town.template) · [プレイ契約](https://docs.worldlines.gg/docs/creators/contracts) · [ワークベンチ](https://docs.worldlines.gg/docs/creators/workbench)

### 🔬 研究者 — AI パーソナリティ · 世界モデル · マルチエージェント

人格モデル、世界モデルのベンチマーク、マルチエージェント社会を研究している。必要なのは**再現可能なサンドボックス**で、ブラックボックスの API ではない。

WorldLines は**ファイルベース、イベントソース、git-diffable** です。エージェントの意思決定と世界状態の変化はすべてプレーンテキストのイベントとして追跡・再生・計測できます。[`benchmarks/`](./benchmarks) にはエンジンの設計判断ひとつひとつの裏にあるテストスイートがあります。

いまの重点は世界シミュレーションを安定させること。エンジンのカスタム編集はまだテスト中です。次の一歩は `rpg` パックの隣に `science` パックを作ること。社会シミュレーションと経済シミュレーションのルールです。**研究ニーズがありますか?[Issue を立てる](https://github.com/LudicDynamics/WorldLines/issues) か `info@worldlines.gg` へ。あなたの実験に協力します。**

→ [三つの層:エンジン · テンプレートパック · プロダクト](https://docs.worldlines.gg/docs/concepts/overview) · [一局のはじめから終わりまで](https://docs.worldlines.gg/docs/concepts/journey) · [仕様](./documents/spec/)

### 🛠️ 開発者

**Claude Code、LangGraph、またはカスタムエージェントパイプライン**で構築している。世界・キャラクター・プレイヤーの三者が agent としてどう噛み合うのか、そして速くて堅い AI エンジンの中身がどうなっているのかに興味がある。

エンジン NeonRP とその仕様はオープンソースです(Apache-2.0)。世界・キャラクター・テンプレート・プレイ契約・ルールパックの仕様は [`documents/spec/`](./documents/spec/) に、ターンの流れは [`neonrp/`](./neonrp) のソースにそのままあります。インターフェースは HTTP・イベントストリーム・ファイル。入り口は二つあります。

- **自分の重いフロントエンドを作る。** エンジンは状態・ターン・agent・台帳だけを受け持ち、見せ方はすべてフロントエンドのものです。[Godot](./worldlines/examples/clients/godot) と [TypeScript](./worldlines/examples/clients/ts) のサンプルクライアントから始められ、作った演出や画面はテンプレートに書き戻して世界の一部にできます。
- **ルールパックと編成のツールを書く。** `rpg` パックの隣で `science` パック(社会シミュレーションと経済シミュレーションのルール)を作っていて、編成のツールを使いやすくする仲間も探しています。エンジンのカスタム編集はまだテスト中、アーキテクチャも反復中で、唯一の完璧な答えがあるとは考えていません —— ワールドをフォークし、エージェントを改造し、どう配線されているか調べて、**[Discord](https://discord.gg/HJYWbdqWrE)** で一緒に決めていきましょう。

リポジトリ自体が創作のワークベンチです。clone して Claude Code / Codex で開くと `.claude/skills/` の創作スキルが自動で読み込まれます —— キャラクターカード / 世界 / キャラクターの作り方は **[tutorials/](./worldlines/tutorials/)** へ。

→ [開発者向けクイックスタート](https://docs.worldlines.gg/docs/developers/quickstart) · [ルールパック](https://docs.worldlines.gg/docs/developers/packs) · [Godot との連携](https://docs.worldlines.gg/docs/developers/godot) · [benchmarks/](./benchmarks)
## 作る

このリポジトリを clone して **Claude Code** か **Codex** で開いてください。ワークベンチ(`CLAUDE.md` / `AGENTS.md` と
`.claude/skills/` · `.agents/skills/` のスキル)が、キャラクターひとり、ワールドひとつ、あるいはテンプレート一式の制作を
手伝い、エンジンでチェックまでしてくれます。

```bash
neonrp template lint  my/<id>.template          # 問題をすべて表示。block があると公開できません
neonrp template build my/<id>.template /tmp/try
cd /tmp/try && neonrp tui --play
```

仕様:[world](./documents/spec/world.en.md) · [soul](./documents/spec/soul.en.md) · [template](./documents/spec/template.en.md) · [contract](./documents/spec/contract.en.md) · [pack](./documents/spec/pack.en.md)
· チュートリアル(中国語):[`worldlines/tutorials/`](./worldlines/tutorials)。

## 研究と引用

WorldLines の主張は三本の論文にまとめています —— 世界を定義すること、それを多数のエージェントへ拡張すること、
そして世界が破綻せずに保たれるかどうかはアーキテクチャの性質だと示すこと。概要:[worldlines.gg/research](https://worldlines.gg/research/)。

> **[From Character Role-Play to Orchestrated Reality: LLM-Driven Game World Simulation as a Parameterized-Action POMDP](https://doi.org/10.1145/3800965.3834285)**
> Yuhang Huang, Chenmiao Li, Chaowei Fang. *CHI PLAY Companion '26*, ACM. DOI: 10.1145/3800965.3834285 · [arXiv:2606.16014](https://arxiv.org/abs/2606.16014)

> **Multi-Agent LLM Simulation for Living Game Worlds: Coordinating World, Soul, and Player Agents over a Pub/Sub Message Bus**
> *情報処理学会 エンタテインメントコンピューティング 2026*(京都、2026 年 9 月)。

三本目はワーキングペーパーとして準備中です。

```bibtex
@inproceedings{huang2026orchestrated,
  title     = {From Character Role-Play to Orchestrated Reality: LLM-Driven
               Game World Simulation as a Parameterized-Action POMDP},
  author    = {Huang, Yuhang and Li, Chenmiao and Fang, Chaowei},
  booktitle = {Companion Proceedings of the Annual Symposium on
               Computer-Human Interaction in Play (CHI PLAY Companion '26)},
  publisher = {Association for Computing Machinery},
  year      = {2026},
  doi       = {10.1145/3800965.3834285},
  url       = {https://doi.org/10.1145/3800965.3834285}
}
```

## コントリビュート

このリポジトリは WorldLines の公開リリース用です。開発は上流で行われ、リリースごとにひとつのコミットとしてここに反映されます。
Issue もプルリクエストも歓迎します。採用された PR はまずこのリポジトリにマージされ(あなたの作者情報はこの履歴に残ります)、
次のリリースに取り込まれます。詳しくは [CONTRIBUTING.ja.md](./CONTRIBUTING.ja.md) をご覧ください。

## ライセンス

- `neonrp/` — Apache License 2.0([`neonrp/LICENSE`](./neonrp/LICENSE)、[`neonrp/NOTICE`](./neonrp/NOTICE))
- `worldlines/` とワークベンチ — GNU AGPL v3.0([`worldlines/LICENSE`](./worldlines/LICENSE))
- `documents/`、ベンチマークデータ — CC BY 4.0([`documents/LICENSE`](./documents/LICENSE))
- `worldlines/templates/` と `worldlines/examples/` の設定コンテンツ — テキストは CC BY 4.0、画像と音声は CC BY-NC 4.0
  ([`worldlines/CONTENT-LICENSE.md`](./worldlines/CONTENT-LICENSE.md))

「NeonRP」「WorldLines」は Ludic Dynamics の名称です。各ライセンスはこれらの名称を使用する権利を付与するものではありません。

## スター履歴

<p align="center">
  <a href="https://github.com/LudicDynamics/WorldLines/stargazers">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=LudicDynamics/WorldLines&type=Date&theme=dark" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=LudicDynamics/WorldLines&type=Date" width="720" />
    </picture>
  </a>
</p>

## コミュニティ

- [worldlines.gg](https://worldlines.gg) · [docs.worldlines.gg](https://docs.worldlines.gg) · [Discord](https://discord.gg/HJYWbdqWrE) · `info@worldlines.gg`

開発:**nikoloside** & **redoctober**。推進:[Ludic Dynamics](https://ludicdynamics.com)。
