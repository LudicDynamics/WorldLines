# World-agent runtime contracts — 神楽島

## world-agent (orchestrator, singleton)
- **Input:** プレイヤーの行動テキスト、現在の `game/meta/run_state.json`、`game/timeline/current.json`、`.neonrp/playthrough.json` からの soul roster。
- **Output:** 更新された世界状態(時間の進行、location/flag の変化、禁忌/消失/ループの裁定)。M18 の下では、ランタイムはさらにターンを全 active soul インスタンスへ扇状に配り、一度で commit する。
- **Writes:** `game/timeline/*.json`、`game/locations/*.json`、`game/meta/run_state.json`、`game/lore/notes.md`。

## story-narrative (fallback functional sub-agent)
- **Input:** world-agent が直接解決しないことを選んだ、仕様の薄い縁の場面。
- **Output:** world-agent が統合するための薄い描写素材。
- **Writes:** 既定では無し;最終的な世界向けの永続化は world-agent が担う。

## souls (the cast — M16 soul instances, bound by playthrough.json)
各キャラクターは自前の 6 つの soul-* スペシャリスト
(orchestrator/mind/memory/action/dialogue/narrative)を持つ完全な M16 soul である。M18 の world-agent は
各 soul を `CharacterAgent` として登録し、ターンごとの提案を集める;
フォルダ単位の書き込み権限は各 soul の
`agents/manifest.json` の write_globs から強制される(WORLD_SOUL_FOLDERS §2.2-2.3)。

## control-plane allowance

ランタイムは、舞台の外にいる soul のために、低エントロピーでシステム的な継続性の書き込みを
行ってよい。これは第二の人格の流れではなく、world-agent に
soul 私有の思考を読む/著す許可を与えるものではない。

## player binding

プレイヤーキャラクターは `game/meta/roster.json` と `playthrough.json` によって固定される。
world-agent は場面の中でプレイヤー選択を再び開いてはならない。
