---
title: "给 agent"
description: "Claude Code、Codex 或 WorldLines 自己的创作 agent:打开文件夹,先读 AGENTS.md 和 spec/,改完跑 lint。"
---

<!-- section: who -->
## 这一部分写给谁

> **状态:随 1.0 发布**

写给替创作者干活的 agent:Claude Code、Codex 这类在文件夹里工作的编程 agent,以及 WorldLines 自己的创作 agent。人也可以读 —— 它就是「用文件创作」的说明书。

<!-- section: folders -->
## 三种文件夹,每个都自带说明

| 文件夹 | 里面有 | 先读 |
|---|---|---|
| 一个模板 `<id>.template/` | 世界、演员表、剧情、素材、合约、编排 | `AGENTS.md`(Claude 读 `CLAUDE.md`,内容相同)→ `spec/` 里对应的一份 |
| 模板库(你的模板都在这) | 很多 `<id>.template/` | `AGENTS.md` → 进你要改的那个模板 |
| 角色库 `~/.worldlines/souls/` | 每个文件夹一个角色 | `AGENTS.md` → `spec/soul.md` |

模板文件夹的 `spec/` 里:`template` · `world` · `soul` · `contract`(中英各一份)、这个模板玩法包的 `ops`(模型每回合能写什么)、`authoring`(引擎提供的作者操作)。它们跟着引擎版本生成,**不在外面查,就在文件夹里读**。人想先通读的话,同一套规格(另加规则包 RPG Pack)也在 [规格](/docs/developers/specs) 页,装好引擎后 `neonrp spec` 也能读。

<!-- section: rules -->
## 规则

1. **先读 spec 再写**:改 `template.json` 读 `spec/template.md`,改 `world/` 读 `spec/world.md`,改角色读 `spec/soul.md`。
2. **角色是 link**:演员表写 `{"lib": "<角色库里的名字>"}`,不要把角色库的角色复制进模板;这个世界里的差异写 `prompts/souls/<sid>/` 或 `world-overlay/`。
3. **内置模板只读**:先 `neonrp template fork <id> <新 id>`,在副本上改。
4. **世界词只进数据**:地名、状态名、阵营名写在模板的数据里,不写进引擎代码。
5. **不要手改生成的文件**:`AGENTS.md` / `CLAUDE.md` / `spec/` 带「generated」标记,会被覆盖;你自己写的 `AGENTS.md` 不会被覆盖。

<!-- section: check -->
## 改完怎么检查

```bash
neonrp template lint .            # 在模板文件夹里跑:0 block = 能玩、能发布
neonrp template build . /tmp/try  # 真建一局看看
(cd world && neonrp validate)       # 只查世界
```

lint 的每个代码是什么意思:`spec/template.md` §7;按合约的检查:`spec/contract.md` §4。

具体任务的步骤见[常见任务](/docs/agents/recipes)。
