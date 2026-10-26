---
title: "1 つのテンプレート、複数のフロントエンド"
description: "Web、Godot、TypeScript のフロントエンドが同じテンプレートと同じプレイをどう読むか。自分のフロントエンドに必要なインターフェースとイベント。"
---

<!-- section: picture -->
## 全体の形

```text
テンプレート(template.json · world/ · souls · plots/ · 画像)
   │  プレイ開始:テンプレートからプレイを組み立てる
   ▼
エンジンのプロセス — このプレイの唯一の真実
   │  POST /rpc · GET /rpc/events · HTTP の読み取り
   ├── 標準 Web フロントエンド(Hub と iOS でプレイヤーが見る画面。オープンソースではない)
   ├── Godot の例   worldlines/examples/clients/godot
   ├── TS の例      worldlines/examples/clients/ts
   └── あなたのフロントエンド
```

フロントエンドはワールドを変えません。一言や行動を送ると、エンジンが判定して確定させ、物語、拍イベント、状態を送り返します。画面に出るものはすべて、エンジンのデータとテンプレートの画像から来ます。

だからテンプレートはフロントエンドごとに書き直しません。フロントエンドが知っているのはインターフェースで、特定のワールドではありません。

<!-- section: host -->
## どのエンジンにつなぐか

| エンジン | 起動 | トークン |
|---|---|---|
| ローカルのワークベンチ | `worldlines`(既定 `http://127.0.0.1:8787`) | ワークベンチの「フロントエンド」ページで「トークンをコピー」。または `curl -s http://127.0.0.1:8787/api/v1/local/frontends/_/connect`(ローカルからの要求にだけ答えます) |
| ワールドのフォルダ 1 つ | `neonrp serve --project <フォルダ> --port 8788` | 起動時に `{"url", "token", "protocol"}` を表示 |

フロントエンドを作るときは、ローカルのワークベンチにつなぐのが楽です。テストベンチとフロントエンドが同じプレイを共有するので、片方でデバッグし、片方で画面を見られます。ワークベンチなしでワールドを 1 つ動かすときは `neonrp serve` を使います(英語版:[Protocol](/docs/developers/protocol))。

<!-- section: five -->
## フロントエンドが読む 6 つのもの

| もの | 取り方 |
|---|---|
| 接続 | `POST /rpc` で `session.hello {protocol: "worldlines.net/1"}`。どの要求にも `Authorization: Bearer <トークン>` |
| 拍の見た目 | `GET /api/v1/play/engine/beat-kinds`:各拍の名前、トーン、入力のヒント、候補、区切り |
| 物語と拍イベント | `GET /rpc/events`(SSE):`engine/stream` は書かれていく物語、`engine/beat` は拍イベント、`engine/event` はターンの開始 / 終了 |
| 状態 | `GET /state`(誰がどこに)· `GET /api/v1/play/schema`(変数)· `GET /api/v1/play/engine/entities?cls=<クラス>` · `GET /api/v1/play/engine/views` · `GET /api/v1/play/engine/settlement` |
| 画像 | このプレイの画像はアドレスで(`/api/v1/play/place-image?addr=` など)。CG、エンディングなどはスロット id で指す(下の「画像」) |
| 型 | `neonrp template contract <id> --ts` / `--gd`:変数、クラス、ops、イベント、スロットの型(英語版:[Interface contract](/docs/developers/contract)) |

一言は `turn.send {text}` で送ります。ターンが終わると返り、その間の物語は `/rpc/events` に届きます。止めるときは `turn.cancel`。ホストから質問(`ask_user`)が来たら `reply {id, result}` で答えます。

フロントエンドは特定の拍を知りません。オープンソースのエンジンは 1 ターンに清算の拍が 1 つ、PyPI 版は相談の拍と清算の拍です。名前と見た目は `beat-kinds` から来るので、同じコードで両方に対応できます。

<!-- section: events -->
## 拍イベントと画面

| イベント | フロントエンドでできること |
|---|---|
| `node.enter` / `node.leave` | 拍の見た目を切り替える(名前とトーンは `beat-kinds`) |
| `plan.beat` / `resolve.beat` | 物語を一段落確定させる。`options` をボタンにする |
| `dice` | 画面でダイスを振る:`total` · `vs` · `level` |
| `state.changed` | 数値を更新する。`applied` の各項目は `{var, from, to}`、`refused` は通らなかった変化 |
| `place.discovered` | マップに新しい場所を出す:`addr` · `name` |
| `party.join` / `party.leave` | 仲間が加わる / 抜ける |
| `stage.changed` | プロットの段階が進んだ。`cg` があれば一枚絵を出す |
| `show` | テンプレートの画像を今出す:`slot` はスロット id |
| `audio.cue` | 音楽 / 環境音を変える |
| `run.settled` | 出口に着いた:`GET /api/v1/play/engine/settlement` でエンディングを読む |

全フィールド:英語版 [Live event stream](/docs/developers/events)。切れたあとは `GET /rpc/events?since=<seq>` で取りこぼしを取り直せます。

<!-- section: slots -->
## 画像:このプレイの画像をアドレスで

このプレイの画像はアドレスで取ります。

```text
GET /api/v1/play/place-image?addr=T001/hall      場所の背景。アドレスは /state の player_location
GET /api/v1/play/portrait?id=chara               キャラクターの立ち絵。id=player はプレイヤー
GET /api/v1/play/sprite?id=chara                 透過の立ち姿
GET /api/v1/play/map/image?level=T001            レベルのマップ。場所と道は GET /api/v1/play/map
```

画像がなければ 404 を返すので、プレースホルダーを描きます。これらの画像はプレイ開始時にテンプレートからコピーされます。テンプレートの画像を差し替えたら、新しく始めたプレイから反映されます。

テンプレートの画像にはすべてスロット id があります。CG、エンディング、カバー、アイテムのアイコンには、アドレスで取るルートがありません。エンジンはスロット id で指します。

| スロット id | 中身 |
|---|---|
| `card:cover` | テンプレートのカバー |
| `level.map:<レベル>` | レベルのマップ。例 `level.map:T001` |
| `place.scene:<アドレス>` | 場所の背景。例 `place.scene:T001/hall` |
| `soul.portrait:<キャラクター>` · `soul.sprite:<キャラクター>` | 立ち絵 · 透過の立ち姿 |
| `item.icon:<id>` | アイテムのアイコン |
| `player.portrait:player` | プレイヤーの画像 |
| `opening.cg:<n>` · `stage.cg:<プロット>.<n>` | オープニング CG · プロット段階の CG |
| `plot:<プロットのフォルダ>:ending:<エンディング>` | エンディングの画像 |

拍イベント `show` の `slot` と `stage.changed` の `cg.slot` はスロット id です。エンディングは `GET /api/v1/play/engine/settlement` の `exit` にあります。2 つの例はこれらの画像を自前のアートパック(`art.json`、エンディング id と場所のアドレスで対応)に持ち、イベントが来たらそこから取ります。スロットの種類(比率、必須かどうか)は `neonrp template contract <id>` の `slots` にあります。どのスロットが埋まっているかは:`neonrp template slots <id>`。

<!-- section: switch -->
## プレイが替わったとき

ローカルのワークベンチで、テストベンチが別のプレイを開いたり、プレイ一覧で新しく始めたりすると、エンジンは新しいプレイに移ります。

- `/rpc/events` はつながったままで、そのあとのイベントは新しいプレイのものです;
- `GET /events` が `rebound` を 1 回送ります;
- それを受けたら、テンプレート id、`beat-kinds`、画像を読み直して描き直します。

テストベンチの標準 Web フロントエンドは、プレイが替わるとページごと読み込み直し、画像も新しいテンプレートのものになります。2 つの例は接続時に一度だけ読むので、プレイが替わったらつなぎ直します(TS はページを再読み込み、Godot はゲームを再起動)。

<!-- section: three -->
## 各フロントエンドが読むもの

| | 標準 Web フロントエンド | Godot の例 | TS の例 |
|---|---|---|---|
| 場所 | Hub、iOS | オープンソースのリポジトリ `worldlines/examples/clients/godot` | オープンソースのリポジトリ `worldlines/examples/clients/ts` |
| プロトコル | 同じインターフェース | `addons/worldlines/client.gd`(ノード 1 つ) | `src/client.ts`(ファイル 1 つ) |
| 拍の見た目 | `beat-kinds` | `beat-kinds` | `beat-kinds` |
| 画像 | テンプレートのスロット | 自前のアートパック `art.json`。描いていない画像はプレースホルダー | Godot と同じアートパック |

標準 Web フロントエンドはオープンソースではありません。このページのインターフェースは、それが使っているものと同じです。PyPI 版のテストベンチには右の列に「標準フロントエンド」タブがあり、同じプレイを並べて見られます。

2 つの例の動かし方と変え方:[Godot と TS のフロントエンド](/docs/tutorials/frontend-examples)。

<!-- section: own -->
## フロントエンドをテンプレートに入れる

ワールドは自分のフロントエンドを持てます:`<テンプレート>/frontends/<名前>/frontend.json`。

```json
{"schema": "worldlines.frontend/1", "kind": "web-ts", "title": "My front end", "entry": "index.html",
 "events": ["node.enter", "resolve.beat", "dice", "state.changed", "run.settled"], "targets": ["local"]}
```

| フィールド | 意味 |
|---|---|
| `kind` | `web-ts` · `godot` · `chat` |
| `entry` | 入口のファイル。例 `index.html` / `project.godot` |
| `events` | 使うイベント。エンジンが既知のイベントと照らし合わせます |
| `targets` | 今は `local` だけ |

ワークベンチの「フロントエンド」ページで「+ 新規」、または内蔵フロントエンドの「このワールドにコピー」。内蔵テンプレートは先に自分のものに複製します。`frontends/` は手元に残り、エクスポートされません。
