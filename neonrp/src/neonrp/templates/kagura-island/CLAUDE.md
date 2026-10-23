# 神楽島 Kagura Island — Multi-Agent RPG

一座和风悬疑孤岛：时间循环 × 失忆 × 三势力。文件驱动的 multi-agent RPG。

## 怎么玩

> ⚠️ **本世界需要 NeonRP 引擎运行**（`worldlines` 启动器 / `neonrp web`）。
> 7 个 soul 的并发编排、出场判定（scene-understanding）、失败隔离都由引擎运行时承担
> ——纯 Claude Code 没有这个运行时，跑不起 7-soul 编排。
> 想在 Claude Code 里直接玩 multi-agent，请用 **stoneford-elena**（2 souls，
> 里面有可 @ 派发的 character-agent）。

引擎内启动后直接游玩；`@world-agent 开始游戏` 仅适用于引擎托管的会话。

## 架构

所有游戏数据在 `game/`。所有 agent 在 `.claude/agents/`。具名角色（カカル/羽/悠人/翼/白/镜子/真琴/宫司）是 `souls/` 下各自自治的 soul-agent。

```
@world-agent  — 世界主权体：状态 + 回合收口 + 最终叙事
  ├─ @town-agent       — 城镇/场所导航与互动
  ├─ @combat-agent     — 危机/冲突/失血时限裁定（非地下城战斗）
  ├─ @rules-referee    — BRP 式技能/理智/禁忌判定
  ├─ @world-builder    — 岛屿地图地理状态
  ├─ @npc-builder      — 临时无名路人 NPC
  └─ @story-narrative  — 漂移到未创作内容时的兜底薄描
```

## 规则

- 不确定的行为走 BRP 式判定（侦查/聆听/洞察/说服/潜行/知识/理智），不是 d20 战斗。
- 玩家是**人类**，不是任何角色。身份/身体/道具在 `game/player/`。绝不让玩家扮演具名角色。
- 禁忌一旦违反**不可逆**——信任下降、次日态度变化，没有反悔骰。
- 翼 Day1 数小时内失血而死，除非被发现并急救；悠人醒来会反射性攻击最近的人。
- GM 真相在 `game/lore/gm-truth.md`——只有 world-agent 可读。

## 不要做

- 不在叙事里暴露系统信息（agent 调用、JSON、flag 名、机制本身）。
- 不剧透循环/失血/Yith/和渊——氛围里可以"不对劲"，但不点破。
- 不替玩家叙事、不替玩家做决定；玩家未行动时收束在"等待玩家选择"。
- 不堆砌形容词，不滥用感叹号。和风悬疑的留白靠克制。
