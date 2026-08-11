# Soul-agent contract (M30 · 1 soul = 1 agent)

一个 soul = 一个 agent。它只改**自己的 context**（记忆/心境/状态），对世界**只读**；
写世界状态一律由 world-agent 经 ontology 工具落地。soul 有 `escalate()` 主权上报「这事世界该知道」。

| | 范围 |
|---|---|
| **Writes**（仅本 soul 目录内） | `run_state.json` · `trajectory/**` · `short-term-memo/**` · `long-term-memo/**` · `character/**` |
| **Immutable**（创建后无 writer） | `soul.md` · `persona/` · `background/` · `rules/` |
| **Reads** | 本 soul 全部 + 世界只读（经感知投递 / `game/meta/run_state.json` · `game/timeline/**` · `game/locations/**`） |
| **绝不** | 直接写世界状态、跨 soul、替玩家决定/发言 |

> prompt 不在此包内：由引擎注入（可 override 的 runtime 契约 + 本 soul 的 `soul.md` + `persona`）。
> 旧的 6 路分解（orchestrator/mind/memory/action/dialogue/narrative）与 `.claude/agents/soul-*.md` 已按 M30 废弃。
