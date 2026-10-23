---
title: "キャラクター Agent を作る"
description: "キャラクター固有の AI Agent を構築するためのファーストクラスなフローはロードマップ上にあります。このページでは想定する形をプレビューします。"
---

<!-- section: shipping -->
## ✓ v0.2.0 で提供中

マルチエージェントのキャラクター NPC とソウル agent は v0.2.0 で **稼働中** です。キャラクターはソウルバンドル（persona, character, agents, memo）として作成され、WebHub の [Soul Talk](https://hub.worldlines.gg/play/souls/elena) でプレイするか、CLI でローカルに読み込めます。

ワールド NPC については、エンジンが `agents/` 以下の NPC ごとの agent ディレクトリをサポートします（[CLI `agent new`](/docs/guides/world-editor#agents) 参照）。Orchestrator がコンテキストに応じてこれらの agent にディスパッチします。

<!-- section: agent-structure -->
## Agent ディレクトリ構造

`agents/my-agent/` を次のように作成します:

```
agents/my-agent/
├── agent.json        # triggers, tags, priority
├── system.md         # system prompt template
├── skills/           # optional: skill fragments
└── tools.json        # optional: extra tool definitions
```

CLI で雛形を作れます:

```bash
neonrp agent new my-agent
```

<!-- section: agent-json -->
## agent.json

```json
{
  "id": "harbormaster",
  "triggers": ["harbor", "dock", "ship"],
  "tags": ["location:harbor", "npc:official"],
  "priority": 50,
  "routing": {
    "invoke": "on_match",
    "fallback_to": "town-agent"
  }
}
```

Dispatcher はクエリが triggers または tags にマッチしたとき、優先度に従ってこの Agent を選択します。

<!-- section: test-agent -->
## Agent をテストする

```bash
neonrp agent run harbormaster --query "who is in charge of the harbor?"
neonrp agent run harbormaster --query "register a ship" --apply
```

機械可読な出力には `--json` を付与します。テスト中に LLM レスポンスをスタブするには `--fixture file.json` を付与します。
