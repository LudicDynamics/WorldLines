---
title: "Agent 协议"
description: "agent 是什么、能读写哪些文件,以及一组 agent 在 world 或 soul 里如何协作。"
---

<!-- section: what-is-an-agent -->
## agent 是什么

*agent* 是单个 LLM 驱动的决策单元,带显式权限、明确角色、和一份说「被调用时该做什么」的契约。Agent 不会独立存在 —— 它要么活在 world bundle(world 下的 `agents/`)、要么活在 soul bundle(soul 下的 `agents/`),由 manifest 声明集合 + 之间的路由规则。

这套协议是**契约层**。它不规定*你应该带哪些* agent —— 那是 world 作者或 soul 作者的选择。NeonRP 有两个权威集合:

- **World 侧**(`game/agents/manifest.json`)—— 运行时称为 *world-agent team* 的 10-agent、4 层阵容:`orchestrator`(L1 路由)· `town-agent` `dungeon-agent` `combat-referee` `rules-referee` `world-builder`(L2 domain)· `npc-mind` `story-narrative`(L3 perspective)· `clock-keeper` `world-evolution`(L4 world-time)。
- **Soul 侧**(`soul/agents/manifest.json`)—— 6 个专家:`soul-orchestrator`(分派)· `soul-mind`(认知)· `soul-memory`(留存)· `soul-action`(执行)· `soul-dialogue`(言语)· `soul-narrative`(故事接口)。

自定义 world 与 soul 可以自由替换。协议只确保每个 agent 都声明它会触碰什么。

<!-- section: the-contract -->
## 契约

每个 agent 声明一份 `agent-contract@0.1.0` 形状的 JSON 文件(或 Claude-Code 风格的 `.md` 带 frontmatter)。最少:

```json
{
  "schema_version": "0.1.0",
  "agent_id": "soul-mind",
  "name": "Soul Mind Agent",
  "role": "character-agent",
  "system_prompt": "...",
  "permissions": {
    "read_globs":  ["persona/**", "*-memo/**", "run_state.json"],
    "write_globs": [],
    "deny_globs":  ["**/secrets.md"]
  },
  "routing": { "scope": "any", "trigger_condition": "decision_required" },
  "max_turns": 20
}
```

关键不变量:

- **deny-first 权限。** 没声明 glob = 没访问。每一项读写都必须显式。
- **`deny_globs` 优先于 `write_globs`。** 用它在已许可区域内挖洞。
- **role 标签是开放的。** 适用时用规范字符串(orchestrator、world-agent、character-agent、rule-agent、town-agent、dungeon-agent、combat-referee、facility-agent、notary、narrative),否则用 `custom`。

<!-- section: the-manifest -->
## Manifest:一组 agent 怎么协作

`agents/manifest.json` 列出集合并声明路由规则:

```json
{
  "schema_version": "0.1.0",
  "agents": [
    { "id": "soul-orchestrator", "role": "orchestrator", "agent_path": "contracts/orchestrator.json" },
    { "id": "soul-mind", "role": "character-agent", "agent_path": "contracts/mind.json" }
  ],
  "routing_rules": {
    "after_player_turn": {
      "agents": ["soul-orchestrator", "soul-mind", "soul-action", "soul-memory", "soul-narrative"]
    },
    "conversation": {
      "agents": ["soul-dialogue", "soul-mind", "soul-memory"]
    }
  }
}
```

路由规则支持三种形态:

- **`agents`** —— 该规则触发时按顺序串联的 pipeline
- **`facilities`** —— 按设施类型分发的子 agent 映射(town 把 `shop_*`、`inn`、`guild` 派发出去)
- **`transitions`** —— 状态变更 → 下一规则指针(world scope → enter_town → town scope)

<!-- section: three-layers -->
## owner-directed 运行时(M18)

拓扑是 **owner-directed**,不是 peer mesh。一个单例 **world-agent** 拥有 `game/`、回合循环、commit 事务。回合开始时它扇出到 N 个 **character-agent** —— 每个活跃 soul 一个,各跑自己的 LLM 实例,只在自己的 `souls/<sid>/` 树里、按每 soul 权限 glob 写。任何 world 级闭环都回到 world-agent。

```
            world-agent  (单例:拥有 game/、回合循环、commit)
                 │  回合开始扇出
     ┌───────────┼───────────┐
     ▼           ▼           ▼
 character-   character-   character-
  agent       agent        agent
 (Elena)     (Conductor)  (Passenger)
  自有 LLM     自有 LLM      自有 LLM
     └───── proposals ─────┘
                 ▼
        apply 管线(按 soul glob)→ 一个 M17 commit
```

契约层让它安全 —— soul 的 `soul-action` 只有当 `write_globs` 允许才能写自己树外。commit 边界见 [文件夹与版本管理](/docs/protocol/folders)。

<!-- section: see-also -->
## 另见

- [World 协议](/docs/protocol/world) —— world 侧 agent 集合在跑什么
- [Soul 协议](/docs/protocol/soul) —— soul 侧 agent 集合在跑什么
- GitHub 上的规范文档:[AGENT-PROTOCOL.md](https://github.com/LudicDynamics)
