# ストーンフォード・エレナ

> `llm-rpg-starter`/`stoneford-orch` の実際の contract をもとにした混成テンプレート:旧来の world contract はそのまま残し、新しい soul runtime をつないである。

`stoneford-elena` は `stoneford-orch` を丸ごと壊して書き直したものではない。実際に動作が確かめられた
world-agent / town-agent / rules-referee の contract の上に、`playthrough.json + souls/`
と `soul.md` を重ねたものだ。

## このデモは何か

- テストできる二つ目の世界
- `game/player/` の互換層を残した、soul-native への移行テンプレート
- はっきりした heroine を持つストーンフォードの変種

## ランタイムの形

ランタイムでは、この世界は次のように振る舞う:

`world-agent -> active souls -> world-agent`

その一方で、`agents/` の下にストーンフォードの domain-agent contract 群をそのまま保っている。

## 正となる情報源

- `game/` は引き続き world-agent が所有する世界の状態。
- `souls/elena-si-elena0001/` がエレナの soul の正本。
- `game/player/*` は、現行の orchestrator 時代のストーンフォード contract のための互換投影だ。
  役には立つが、もはや唯一の正となる情報源ではない。

soul の身元と `game/player/*` がずれた場合は、soul フォルダを長期的なキャラクターの情報源とし、
`game/player/*` はすり合わせるべき世界向けのローカル投影として扱う。

## 収録されている souls

- `elena-si-elena0001` — heroine / プレイヤーの soul
- `rowan-si-rowan0001` — ジェイドストーンの若い冒険者の soul。「世界の果て」の深い洞穴の伝説を追っている

## なぜこれがあるのか

カグラは純粋な soul-native の道を証明した。ストーンフォード・エレナは移行の道を証明する:
実績のある world contract を保ったまま、主人公のロジックを少しずつ
`game/player/` から明示的な soul バンドルへ移していける。
