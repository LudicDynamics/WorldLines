# Quickstart — 30 分で最初のターンまで

**Language:** [English](./QUICKSTART.md) · [简体中文](./QUICKSTART.zh.md) · [日本語](./QUICKSTART.ja.md) · [한국어](./QUICKSTART.ko.md)

> ステータス: Beta — デフォルトの stoneford スターター経路をカバー

このガイドは [INSTALL.ja.md](INSTALL.ja.md) を完了し、`neonrp --help` でコマンド一覧が表示できることを前提にします。

## 1. プロジェクト作成（2 分）

```bash
mkdir my-world && cd my-world
neonrp init
```

`.neonrp/` が作られ、`manifest.json` と `config.json` テンプレートが配置されます。まだ世界はなく、空プロジェクトです。

## 2. stoneford スターターを展開（3 分）

```bash
neonrp game new --template stoneford
```

これで構成は次のようになります:

```
my-world/
├── .neonrp/
│   ├── manifest.json
│   └── config.json
├── agents/
│   ├── orchestrator/
│   ├── town-agent/
│   ├── dungeon-agent/
│   ├── combat-referee/
│   ├── world-builder/
│   └── rules-referee/
└── game/
    ├── meta/
    ├── player/
    ├── towns/
    ├── dungeons/
    ├── rules/
    ├── lore/
    └── world/
```

サンプル世界の中身は [templates/stoneford/](templates/stoneford/README.ja.md) を参照。

## 3. プロバイダ設定（5 分）

`./.neonrp/config.json` を開き、[INSTALL.ja.md](INSTALL.ja.md#llm-プロバイダ設定) のブロックから 1 つ選びます。API キーを export:

```bash
export GLM_API_KEY=sk-...
# または
export OPENAI_API_KEY=sk-...
```

世界を検証:

```bash
neonrp validate
neonrp index build
```

## 4. TUI を起動（1 分）

```bash
neonrp tui
```

右上ステータスバーに、プロジェクト名・branch（`main`）・head event（`0`）・provider が表示されます。

## 5. 最初のターン（5 分）

入力欄で以下を入力:

```
look around
```

Orchestrator が `town-agent` にルーティングし、Stoneford の街データを読んでナレーションします。次が表示されます:

1. **thinking** ストリーム（デフォルト折りたたみ）。
2. **tool use** インジケータ（agent がファイルを読みます）。
3. **narrative** レスポンス。
4. 新しい **event** がログに追記（head が `0 → 1` に進む）。

## 6. チェックポイントを保存

TUI で:

```
/save opening-scene
```

別シェルから:

```bash
neonrp save opening-scene
```

## 7. 実験用に分岐（5 分）

思い切った選択を試しましょう。例えば Old Reed から盗む:

```
/branch try-stealing
steal the coin pouch while Old Reed is turned away
```

WorldLines は新 branch に書き込み、main branch はそのままです。

## 8. Undo / 巻き戻し

```
/undo
```

head event が 1 歩戻ります。`/redo` で再適用。

## 9. セーブをロード

```bash
neonrp load opening-scene
```

または TUI を `--continue` で再起動して前回セッションを再開。

## 10. 次は？

- [CONCEPTS.ja.md](CONCEPTS.ja.md) を軽く読み events / snapshots / sandboxes を把握。
- `/mode build` を試し、agent に新しい NPC を Stoneford に追加させ、**plan → diff → apply** パイプラインを観察。
- `templates/stoneford/README.ja.md` を読み、街の JSON を直接編集。
- [CLI_REFERENCE.ja.md](CLI_REFERENCE.ja.md) で全サブコマンドを確認。

## トラブルシュート

| 症状                                 | 対処                                                 |
|--------------------------------------|------------------------------------------------------|
| `neonrp: command not found`          | `uv tool install -e .` を再実行                      |
| TUI が文字化け                       | iTerm2 / Ghostty / Alacritty に切替、UTF-8 に設定    |
| `provider not configured`            | `.neonrp/config.json` と環境変数を確認               |
| `validate` が schema エラーを出す    | `neonrp validate --json` で詳細を取得                |
| Agent がハング / 出力が空            | `neonrp tui --verbose` で生 LLM トラフィックを確認   |
