# Stoneford-on-the-Shale — Claude Code RPG

これは Claude Code で動かすファイル駆動の RPG だ。

## 遊びかた

Claude Code に直接こう入力する：`@world-agent ゲーム開始`

## アーキテクチャ

すべてのゲームデータは `game/` ディレクトリにある。すべての agent は `.claude/agents/` にある。

```
@world-agent  — 主制御：状態管理 + ルーティング + 語り
  ├─ @town-agent       — 町の交流
  ├─ @dungeon-agent    — ダンジョン探索
  ├─ @combat-referee   — d20 戦闘
  ├─ @rules-referee    — ダイス判定 + 常識チェック
  └─ @world-builder    — 世界地図の更新
```

## 規則

- すべての不確実な行動は d20 で判定する
- HP がゼロ = 死。自動復活はない。
- NPC の好感は永続する。怒らせたら、怒らせたままだ。
- どの依頼の裏にも派閥の動機がある。「純粋な善行」は存在しない。

## してはいけないこと

- 語りの中でシステム情報を露出しない（HP の数値、ダイスの結果は例外）
- 感嘆符を使わない
- プレイヤーに「自分は選ばれし者だ」と思わせない

> 上下文语言(词条包 · 输出格式 · <> [] 标签 · 条目):见 `CONTEXT.md`(引擎生成)。
