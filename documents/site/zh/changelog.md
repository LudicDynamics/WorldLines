---
title: "更新日志"
description: "发布历史。完整记录见 [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases)。"
---

<!-- section: v103 -->
## 1.0.3(2026-10-24)

- 从[这个仓库](https://github.com/LudicDynamics/WorldLines)或 PyPI 安装;[worldlines.gg](https://worldlines.gg) 是在线版。启动时自动更新
- 本地 Hub 不登录也列出线上 Hub 的世界
- 工作台:新建模板、新建世界、新建角色
- 本地版可以把世界上传到自由区
- 没有判断模型时,由这局自己的模型判断商量是否谈妥
- 可以举报 AI 内容;角色名跟随界面语言;新图标
- 修复剧情图名称、窄屏顶栏和 TUI 快捷栏的显示

完整说明:[GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases)

<!-- section: dev10 -->
## 1.0.0–1.0.2(2026-10)

- 商量拍和清算拍分开显示,带骰子卡、状态变化和结局页
- 进行中的回合可以停止;新开一局后页面会重新连接
- 工作台把编排图、地图道路和剧情触发直接存进模板
- 玩法合约;角色库,世界里只放链接;模板和角色可以导出、导入
- 状态先快速写下,再在后台复核修正;角色跨镇沿道路移动
- 规则包 `rpg`、`pct`、`monopoly`;见[规格](/docs/developers/specs)

<!-- section: v040 -->
## v0.4.0 — 一引擎两产品 (2026-08)

- **引擎 / 壳分离** —— Web UI 与桌面壳迁入开源 [WorldLines 仓](https://github.com/LudicDynamics/WorldLines)(AGPL-3.0);引擎向极轻模拟内核收敛(`pip install worldlines` 用法完全不变)
- **谁发言,由 agent 决定** —— world-agent 主持场面:只唤醒该反应的角色,需要答案时直接去问某个角色,角色也会在世界该知情时主动举手
- **与角色的直连线** —— 回合之外 `@名字` 一对一、`#` 对全场,从角色自己的记忆作答,不走世界时钟
- **观察成为独立界面** —— 观察页以三栏频道玻璃打开世界:频道栏(◉世界 / #此地 / @角色)、实时流、在场栏
- **在场心跳** —— 在场但未被点名的角色每回合仍给一个轻反应,群像不再冻结
- **骰子与物理校验的移动** —— `roll_check`(BRP d100 / SRD d20)进入链路;所有移动过地图校验
- **模式收敛为二** —— `orchestrator` 与 `multi-agent`;旧 `fast` 模式退役,旧档静默迁移
- **修复** —— 挂死的 LLM 流会超时进入重试梯;会话刷新自愈;长生成不再截断

<!-- section: v036 -->
## v0.3.1–v0.3.6 — 桌面加固与位置一致性 (2026-07)

- **Windows 批** —— 全面 UTF-8(中文世界不再崩)、桌面壳看门狗不再误杀引擎、自更新死循环终结
- **玩家位置跟随剧情** —— 叙事和引擎状态不再对"你在哪"各执一词
- **`worldlines` 重新默认进 TUI** —— 终端界面回归命令行默认入口
- **下载的多智能体世界跑真多智能体** —— 包布局在开局时自动迁移,不再静默降级成单叙事者

<!-- section: v0300 -->
## v0.2.10–v0.3.0 — LocalShell:引擎长成完整的本地产品 (2026-07)

- **LocalShell** — `neonrp web` 从游玩页长成完整本地产品:游戏门面 / 书房(继续游玩·世界库) / 创作门 / PrePlay 进场确认 / 游玩工具条;与桌面壳共用同一份构建
- **备团工作台** — 工坊 + 三画布(世界/角色/剧本):AI 起草,你把结果落地成真实世界文件
- **引擎防线三件套** — LLM 写坏的 JSON 在写入边界修复或拒绝;`neonrp validate` 变成可玩性体检;位置裁判:镇内自由、跨镇必须过城门,瞬移物理上不可能
- **回合回滚** — 任意历史回合一键分叉(git 式),当前线原样保留
- **导入即完整 soul** — 酒馆角色卡导入由 LLM 补齐成完整 soul;创建访谈的 AI 思考实时流式显示
- **稳定性** — 中文世界名(封面/删除/继续)全修;Playwright e2e 地基 + 发布门禁(测试不绿不发版)

<!-- section: v029 -->
## v0.2.4–v0.2.9 — 创作、世界与有生命的移动 (2026-06)

- **新建世界即真正的多智能体世界** —— 完整初始化、每角色独立 soul-agent、世界库(`worlds/` 与 `plays/` 拆分,可浏览+删除)
- **更丰富的网页游玩** —— 世界图 + 镇内地图(缩放·双指·最小化)、编排进度、灵魂心象面板、继续与回放
- **创作** —— 实体可放进嵌套子文件夹(`game/<kind>/.../<id>.json`)
- **有生命的移动(trial-beta)** —— 角色去向统一由 world-agent 裁定,状态与叙事不再矛盾;角色不再跨镇瞬移
- **稳定性** —— 修复中日文/IME 输入、按安装方式自动更新、更快的新版检测、Windows 装完即可在当前 shell 运行

<!-- section: v023 -->
## v0.2.3 — 多智能体村庄 (2026-06)

- **Multi-agent 模式** —— 村庄模型:一个 world-agent 包装一群独立灵魂(`world-agent → active souls → world-agent`)
- 可复刻 —— 任何带 `souls/` + `playthrough.json` 的世界都会启用
- 新示例世界:**神楽島 Kagura Island**(7 灵魂)· **石津镇 · 艾莲娜**(2 灵魂)
- stoneford-worldlines 整合进 `examples/orch/stoneford`;四个官方世界 + multi-agent 世界同处一仓
- 本地运行(TUI / CLI);hosted play 维持 Fast + Orchestrator

<!-- section: v020 -->
## v0.2.0 — Hub 上线 (2026-06)

- **WebHub** / 在线游玩 / WorldHub+SoulHub / 创作工坊 / 封面系统 / 继续存档 / 多语言

<!-- section: v019 -->
## v0.1.9 — 引擎 (2026-04)

- 10-agent 四层编排器 / Stoneford 起始世界 / Claude Code 运行时 / 文件支撑的世界状态
