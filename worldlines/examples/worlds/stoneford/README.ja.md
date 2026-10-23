# ⛩ Stoneford — WorldLines 旗艦ワールド

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

![Stoneford](./assets/s1bg.png)

> 灰霧の北方河港。古典ファンタジー TRPG · d20 ダイス · **10-agent マルチエージェントの村**。

Stoneford は [WorldLines](https://github.com/LudicDynamics/WorldLines) に同梱される旗艦サンプル —— NPC、クエスト、ダンジョン、攻城戦を備えた完全にプレイ可能な町を、マルチエージェント社会が編成して動かします。

**[▶ オンラインで遊ぶ（インストール不要）→](https://hub.worldlines.gg/play/worlds/stoneford)**

## 遊び方

```bash
# ローカル TUI
neonrp tui --from examples/orch/stoneford

# Claude Code / MCP —— このディレクトリで Claude Code を開く
@world-agent 開始游戏
```

## 村 —— マルチエージェント社会

Stoneford は**生きた村**です。中心の `world-agent` がドメイン agent の社会を編成し、それぞれが世界の一部を司ります。トリガーを持つのは world-agent だけで、他の agent はすべて `task()` で呼び出され、各々が独立したコンテキストを持ちます。

```
world-agent（オーケストレータ）   — 状態読込 · ルーティング · patch 統合 · 叙述 · アーカイブ
├── rpg-world-builder             — ワールドマップ、地域、勢力
├── rpg-story-narrative           — メインストーリー + 噂
├── rpg-town-agent                — 町のナビ、NPC、商店、ギルド、宿
├── rpg-dungeon-agent             — ダンジョン探索
├── rpg-combat-referee            — d20 戦闘判定
├── rpg-rules-referee             — ルール参照・判定
├── rpg-clock-keeper              — 時間、スケジュール、世界時計
├── rpg-world-evolution           — 世界の長期的変化
└── rpg-character-agent           — NPC の心:意図・記憶・対話
```

これが**村の構造**の実践です。世界は覚えており、NPC は自身の心を持ち、毎ターンが単一のプロンプトではなく編成された agent 社会になります。

## 世界の内容

- **T001 Stoneford** —— 開始の町:ギルド、雑貨、宿、波止場
- **T004** —— 第二の集落:礼拝堂、鑑定士、薬草店、酒場
- **D001 苔の墓地下** —— 4 部屋のダンジョン
- **クエスト** —— 霧の中の失踪者 · 苔墓の前の遠吠え · 隊商護衛
- **戦闘** —— d20 + 能力修正 + 状態効果

<p align="center">
  <img src="./assets/gameplay.jpg" alt="Stoneford —— 霧の中で到着" width="640" />
</p>

## 主要ファイル

| ファイル | 役割 |
|------|------|
| `game/agents/manifest.json` | 10-agent マニフェスト（id、役割、読み書き範囲） |
| `game/meta/run_state.json` | 世界状態（位置、時間、最後の行動） |
| `game/meta/game-start.json` | 開始ガイド（開幕叙述 + 初期読込リスト） |
| `game/towns/*/` | 町データ:NPC、クエスト、施設、マップ |
| `game/dungeons/D001/` | ダンジョン構成、部屋、遭遇・戦利品テーブル |
| `game/rules/combat_rules.md` | d20 戦闘ルール |
| `agents/*/` · `.claude/agents/*` | agent 定義（TUI + Claude Code ミラー） |

## ライセンス

Stoneford は **AGPL-3.0**。フォーク、改変、自分の世界を出荷できます。実行する WorldLines エンジン（`neonrp`）はプロプライエタリプレビューです。

> *Stoneford は **nikoloside**、**redoctober**、Claude が共作したオリジナルシナリオで、東洋的世界観と西洋中世魔法を融合しています。*
