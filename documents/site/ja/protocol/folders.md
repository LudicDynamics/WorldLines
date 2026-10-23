---
title: "フォルダ構成とバージョン管理"
description: "world(game/)・soul(soul/)のディスク上の形と、3 つのバージョン軸 —— クリエイター・インスタンス・commit —— の関係。1 つのフォルダレイアウト、2 つの消費者:エンジンが書き、Web レンダラーが歩く。"
---

<!-- section: shared-contract -->
## 共有契約

これは **world**(`game/`)・**soul**(`soul/`)のディスク上の形、そして 3 つのバージョン軸がどう関係するかの正準リファレンスです。

設計ロック済みの SoulHub(M16)と commit バージョニング(M17)を統合したもの;world の `game/` 側は今日ディスクに既に存在するものを記述しています。1 つのフォルダレイアウト、2 つの消費者:エンジンがこれらのフォルダを書き、Web レンダラーがそれらを歩く。

<!-- section: world-folder -->
## world フォルダ —— game/

world バンドルは `game/` ディレクトリです。クリエイターが作成し、world 作者がバージョン管理し、WorldHub 経由で配布。現在の実レイアウト:

```
game/
├── agents/                 # world の agent ロスター(クリエイターバージョン管理テンプレート)
│   ├── manifest.json       # この world が同梱する sub-agent(world-agent + domain agent)
│   └── contracts/          # agent ごとの IO 契約
├── meta/
│   ├── run_state.json      # ライブ位置 / 時間 / turn_count(playthrough ごと)
│   ├── active-agent.json   # 現在書き込みロックを持つ sub-agent
│   ├── game-start.json     # オープニング / handoff
│   ├── flag_aliases.json   # story flag の可読名
│   └── schedule.json       # タイマー / スケジュール世界イベント
├── lore/
│   ├── story.md            # メインストーリー(append-only ナラティブ)
│   └── notes.md            # 噂 / 世界観察
├── world/
│   ├── world_map.json      # ノードグラフ
│   ├── regions.json
│   └── factions.json
├── towns/<Txxx>/           # 街の位置ノード
├── dungeons/<Dxxx>/        # ダンジョンの位置ノード
├── rules/                  # ルール schema(ダイス・判定・戦闘)
└── player/                 # 旧プレイヤー状態 —— soul に移行
```

- `game/agents/manifest.json` は world の sub-agent チームの**クリエイターバージョン管理テンプレート**。playthrough 作成時に `playthrough.json` へ *seed* される;実行中のエンジンは `playthrough.json` を読み、バンドル manifest を直接読むことはない。
- `game/player/` は**旧**の単一プレイヤー状態モデル。M16 では soul フォルダに置き換わる;既存ゲームは自動移行。

<!-- section: soul-folder -->
## soul フォルダ —— soul/

soul バンドルは自己完結したキャラクター。プレイヤーアバターにも NPC にもなれる。SoulHub 経由で配布。設計ロック形状(M16、オプション B —— NeonRP ネイティブ、レガシー非互換):

```
souls/<sid>-<instance_id>/
├── soul.json               # マシン用アイデンティティエンベロープ(NeonRP 固有)
├── soul.md                 # ランタイム向け soul チャーター(声 / 価値観 / タブー)
├── run_state.json          # ライブ位置/状態(soul-orchestrator/action が書く)
├── agents/
│   ├── manifest.json       # soul の 6-agent ロスター + agent ごとの write glob
│   └── contracts.md        # agent ごとの入出力 schema
├── persona/                # 不変の心理カーネル
│   └── core_traits.json  motivations.json  values.json  relationships.json
├── background/             # 不変 lore: origin.md  history.md  secrets.md
├── character/              # RPG メカニクス(soul-action のみ)
│   └── stats.json  inventory.json  equipment.json  wallet.json  status.json  profile.json
├── rules/                  # 意思決定/行動ガードレール(読み取り専用)
├── short-term-memo/        # セッション作業記憶
├── long-term-memo/         # 永続記憶(soul-memory が書く)
├── trajectory/             # append-only 自律行動ログ
└── .commits/               # この soul インスタンス自身の commit チェーン(M17)
```

**`soul.json` —— アイデンティティエンベロープ:**

```json
{
  "schema_version": 1,
  "sid": "elena",
  "name": "Elena Voss",
  "name_local": "艾莲娜",
  "version": "1.0",
  "source": {"kind": "soulhub|builtin|local-create", "hash": "...", "version": "1.0"},
  "agent_template": "heroine-classic|minimal",
  "tags": ["companion", "mage"]
}
```

**`soul.md` —— ランタイム向け soul チャーター。** `soul.json` と並ぶ一等のルートファイル。*この soul がロールプレイでどう感じ、どう振る舞うべきか*を 1 ファイルで自然言語にしたもの:一人称のアイデンティティと自己像、声と感情のトーン、価値観 / タブー / 譲れない一線、この soul が何に気づき、何を隠し、何を追い、何を避ける傾向があるか。構造化ファイルを補完するもので、置き換えない:`soul.json` = マシン identity / バージョンアンカー · `soul.md` = ランタイム向け自然言語チャーター · `persona/*.json` = 構造化された心理カーネル · `background/*.md` = 事実 lore。より広い「soul document」パターンの NeonRP によるロールプレイ向け適応 —— 明示的にロールプレイ向けであり、汎用アシスタント憲法ではない。

**Soul agent ロスター。** `soul/agents/manifest.json` は 6 つの専門家を列挙:`soul-orchestrator`(ディスパッチャ)+ `soul-mind`(認知)+ `soul-memory`(保持)+ `soul-action`(実行)+ `soul-dialogue`(発話)+ `soul-narrative`(物語インターフェース)。各々が `write_globs` ホワイトリストを持つ;apply パイプラインはその外への書き込みを拒否する。

**書き込み権限契約:**

| パス | 書き手 |
|---|---|
| `persona/` `background/` `rules/` | なし(作成後は不変) |
| `soul.md` | なし(作成後は不変) |
| `soul.json` | `soul-orchestrator` —— rename 時のみ |
| `character/` | `soul-action` |
| `short-term-memo/` | `soul-memory`、`soul-dialogue` |
| `long-term-memo/` | `soul-memory` |
| `trajectory/` | `soul-action`、`soul-orchestrator`(append-only) |
| `run_state.json` | `soul-orchestrator`、`soul-action` |
| `agents/manifest.json` | 決して書かない(soul bundle とともにバージョン管理) |

**移行。** 既存の `~/.worldlines/players/` プロファイルは M16 後の初回起動で `~/.worldlines/souls/` へ自動インポート:最小 `soul.json` + persona スタブが合成され、`game/player/*` の内容が `soul/character/*` へマップされる。

<!-- section: version-axes -->
## バージョン管理 —— 3 つのアイデンティティ軸

world と soul は 1 つのモデルを共有。3 つの直交する軸(M17):

- **クリエイター軸 —— `slug + version_hash`。** 公開・作成済みバージョン。不変。`wid`/`sid` + `version_hash`。WorldHub/SoulHub レジストリの slug+version ごとに 1 つ。*(M17 以前に存在した唯一のバージョニング。)*
- **インスタンス軸 —— `instance_id`。** 1 つの playthrough への fork。soul が world に入ると fork される → 独自の `instance_id`(fork 時の UUID)と独自の独立したターンごと commit チェーンを持つ新しい soul **インスタンス**。プレイ中の world も同様にインスタンス。2 つのチェーンは互いのハッシュを埋め込まない。`(wid|sid, instance_id)` はグローバルに一意 —— **アイデンティティにタイムスタンプはない**。
- **commit 軸 —— `commit_hash`。** 1 インスタンスのターンごと状態スナップショット。コンテンツハッシュ → ハッシュがアイデンティティであり、メタデータではない。world インスタンスと soul インスタンスは各々独自の commit DAG を持つ(分岐可能、v1 ではマージなし)。commit はフォルダ blob + 各 agent の会話スナップショット + `determinism` ブロック(rng seed、rolls、llm-calls ハッシュ)を束ねる —— 完全・ポータブル・決定的な実行コンテキスト。

**完全アドレス + バインディング:**

| アセット | アドレス |
|---|---|
| World | `(wid, instance_id, version_hash, commit_hash)` |
| Soul  | `(sid, instance_id, version_hash, commit_hash)` |

world↔soul の関係とライブ agent チームは、セッション層の playthrough manifest **のみ**で正準:`~/.worldlines/games/<wid>-<world_instance_id>/.neonrp/playthrough.json`。world インスタンス ref + `world_agent_team`(`game/agents/manifest.json@<version_hash>` から seed)+ soul インスタンスのリストを持つ。world commit は追加で*読み取り専用*の `soul_scene_index` を持つ;soul は world を逆参照しない。

**タイムスタンプ規則。** タイムスタンプは決してアイデンティティの一部ではない。`instance_id` が一意;`commit_hash` が状態を固定。`archived_at` は commit がアップロード/エクスポート用にパッケージされる時のみ現れる —— ソート用の人間向けラベルであり、決して key ではない。**ハッシュが位置を定め、タイムスタンプはラベルのみ。**

<!-- section: on-disk-map -->
## ディスク上のマップ

```
~/.worldlines/
├── games/<wid>-<world_instance_id>/
│   ├── .neonrp/
│   │   ├── playthrough.json     # バインディング
│   │   ├── HEAD                 # 現在の world commit_id
│   │   └── sessions/<branch>.jsonl
│   ├── game/                    # world 作業ツリー
│   └── souls/<sid>-<soul_instance_id>/   # soul 作業ツリー
├── souls/<sid>-<ts>/            # ダウンロード/作成した soul ライブラリ(fork 前)
│   └── .commits/<soul_commit_id>.json + blobs/
└── commits/
    ├── worlds/<world_commit_id>.json
    ├── refs/<wid>/{HEAD,branches/*,tags/*}
    └── blobs/<hash>.{tar,jsonl}.zst
```

<!-- section: sandbox-replay -->
## sandbox / replay との関係

このモデルは M4 sandbox/replay 設計の**スーパーセット**:`sandbox` = commit をブランチに fork;`save` = 退化した単一 agent commit;`replay verify` = マシン間の commit ハッシュ比較。エンジンの安定 tree-hash がフォルダハッシュにそのまま再利用される。M4 の予約済み seed/rolls インターフェースは commit `determinism` ブロックで埋められる。

関連:[World プロトコル](/docs/protocol/world) · [Soul プロトコル](/docs/protocol/soul) · [Agent プロトコル](/docs/protocol/agent)。
