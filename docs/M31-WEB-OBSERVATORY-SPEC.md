# M31 · Tauri/Web 修改逻辑 — 常驻观察 · 大地图（WorldLines 可视化轨）

> **范围横幅**：本 spec **只做 Tauri/Web 可视化（WorldLines 仓 `ui/` + `desktop/`）**。TUI（build↔play、coding-agent 建 agent）是**另一条轨、隔壁 tui/neonrp 已在做**，不在本 spec。
> 基准：`Ludic-Dynamics/docs/design-refs/desktop-tasks-whiteboard-2026-08-25.png`（让世界「长在桌面上」）+ M31 §4 常驻观察。
> 纪律：**扩展现有 Observatory，纯加法、分支开发、不发布、不破坏现有 SPA（v0.4.0 已发）、build/lint 全绿**。

---

## 1. 现状（已经有的，别重造）
- **技术栈**：React + Vite + TS + react-router；**已装 `@xyflow/react`（React Flow 图可视化）** + lucide 图标。双构建 `build:local` / `build:hub`。
- **`src/local/ObservatoryShell.tsx` 已 live**（路由 `/observe`，`main-local.tsx`）——就是「看活世界的窗」。niko v0.4.0 定稿层阶：
  - 第一层·选内容：存档大卡
  - 第二层·频道玻璃(M24 §7)：左=频道(◉世界/#此地/@souls)+镜头 · 中=舞台 · 右=在场
  - ◉世界=下场(内嵌 `PlayStage`，时钟走)；@/#/镜头=幕间(时钟停)
  - 模块注册表 `MODULES`：**pulse / feed / map / chars / places / debug**（`has(data)` 有数据才点亮）
- **xyflow 已有先例**：`StudioCanvas.tsx` / `SoulArcCanvas.tsx`（图画布）。
- **数据面** `localClient.ts`：`/api/v1/local/{worlds,souls,saves,...}`；trace 走 `play/stage/stageClient`（`getTraces`/`getTrace`）。

## 2. 目标态（差距 = 扩展 Observatory，非重建）
> **niko 2026-08-26 补（核心愿景）**：Observatory 的心脏是一块**无限画布**——角色在游玩/自动推进时**在画布上行动、移动**，看得见谁从哪走到哪。**比 Obsidian 的静态 vault 活得多**。Obsidian 仍是 file-first 长时段/著述视图(M26 §6)，但「**一边跑一边看**」的现场体验 = 这块画布。

1. **无限画布世界图（centerpiece）**：xyflow 无限画布(pan/zoom)——地点为节点、souls 落位其上、点节点看详情。✅ **P1 已落**（`WorldMapCanvas`，build 绿）。
2. **角色在画布上活动**：世界推进时 souls 位置**实时更新/移动**（谁从哪走到哪，画布上看得见）。
3. **可设 tick + 挂机**：设定后台**每 N 分钟走一步**，**挂机**让它自己跑；回来看结果。
4. **回看 replay**：挂机跑完后可**回放**这段时间发生了什么（souls 移动 + 事件流）。
5. **（后置）CG / 出图**：画布节点挂 CG、点击出图（接已有 `/api/v1/local/settings/image`）。
6. **（后置）白板 A 桌面层**：Tauri `desktop/` 常驻桌面窗（壁纸/Übersicht/Plash 那套）。
7. **可视化归这条轨**：TUI 不做可视化（配合 Obsidian 著述/长时段）；**现场活画布全在此**。

## 3. 分层落地（先富 /observe，再桌面）
- **P1 · 无限画布世界图** ✅ **已落**：`map` 镜头 → `WorldMapCanvas`(xyflow)，地点节点 + souls 落位 + 点节点详情。读现有 trace 数据，纯加法，`build:local` 绿。
- **P2a · 挂机/tick 控制 + 自动刷新** ✅ **已落**：左栏「挂机·Watch」——开关自动刷新、间隔(5s~5min)、回合数、手动刷新；开启后画布/镜头随世界推进实时更新。
- **P2b · 角色在画布上平滑移动** ✅ **已落**：souls 升级成各自节点，落在所在地点周围、稳定配色 + 真名；换地点时 CSS transition 平滑滑行（画布上"活着"地移动）。
- **P3 · 回看 replay** ✅ **已落**：左栏「时间轴·Replay」——拖时间轴/▶回放，重看这段每回合 souls 的移动；回放自动暂停挂机，「⏭现在」回到 live。
- **P4（后置） · CG / 出图**：画布节点挂 CG，点击出图（接 `/api/v1/local/settings/image`）。
- **P5（后置） · Tauri 桌面常驻窗**：`desktop/tauri` 常驻桌面观察窗（白板 A）。
- **⏳ 待引擎** · 真·后台自动推进（auto-tick）：隔壁 NeonRP 域；就绪后接进挂机的「每 N 分钟一步」，届时挂机=真自动演进 + replay 回看。

## 4. 第一刀（P1）工作分解
- **T1 · 读世界地图数据**：`localClient` 加/复用取某世界 `locations`（节点）+ 关系（edges）；souls 当前落位（`ObservatoryShell` 已有 `soulLoc`/`nearPlayer`）。纯读。
- **T2 · WorldMap 组件**：`src/local/WorldMapCanvas.tsx`（仿 `StudioCanvas` 用 xyflow）：地点节点 + souls 头像落位 + 点节点开详情。
- **T3 · 接进 map 模块**：`ObservatoryShell` 的 `map` 镜头渲染 `WorldMapCanvas`；`has()` 谓词=世界有 locations 才点亮。
- **T4 · 保活**：`npm run build:local` + `lint` + Playwright e2e 全绿；`/observe` 现有频道/PlayStage 零回归。

## 5. 约束 / 验收
- 纯加法：新增组件 + 复用现有数据面；**不改引擎、不碰 play/PlayStage 流、不动 hub 构建**。
- 分支开发（`feature/web-observatory-map`），**不发布**。
- `build:local` + `lint` + e2e 全绿。
- 大地图能显示某世界的地点 + souls 落位 + 点节点看详情。

---

## 6. Play ↔ Observe 合并计划（niko 2026-08-27）

**现状**：play 存在**两处** → 重复。
- ① `/observe` 的 **◉世界频道已内嵌 PlayStage**（`ObservatoryShell.tsx:490`，下场游玩、时钟走）；@/#/镜头 = 幕间观察（时钟停）。
- ② 独立老路 `/local/play` → `/preplay/:slug` → `/stage`（LocalPlayGate/LocalPrePlay/PlayStage standalone）。
- nav 里「👁 观察」「游玩」是**两个入口**（`LocalApp.tsx:134-135`）。

**目标**：`/observe` = **唯一的 play+watch 同一块玻璃**。◉世界=下场游玩；幕间=观察。退役独立 play 路由。

**阶段（U 系列）**：
- **U1 · 入口统一**（最大一块）：observe 首层「选内容」从「只选存档」扩成「**选世界(开新局)** + 选存档(续/看)」。选世界 → 起新 session → 进 observe、◉世界激活=游玩。（observe 现只 handle 存档 trace，要补「起新局」链路，可复用 preplay 逻辑。）
- **U2 · ◉世界 = 完整 play**：确认内嵌 PlayStage 的输入/生图/状态栏完整；开局设置（preplay）内化进 observe 首层。
- **U3 · 退役 standalone**：`/local/play`、`/local/stage`、`/local/preplay` → 重定向进 observe（保留深链兼容一版）；nav「游玩」+「观察」合成一个入口。
- **U4 · 保活**：PlayStage 现有游玩零回归；lint/build/e2e 绿；分支不发布。

**三态收口（大图）**：**build 生成**（造世界/角色/CG，Nodesign 式画布，见 §7）· **play 游玩**（并入 observe）· **observe 观察**（宿主面）。→ observe = play+watch 统一；build = 生成画布，另一条大轨。

## 7. Build/生成画布 — 参考 Nodesign（agent 驱动的生成式画布）

> niko：无限画布不止「看 souls 移动」——是 **agent 通过画布生成图片/角色/逻辑**（很仔细的功能）。参考 `~/Workspaces/worldlines/worldlines-design/Nodesign`。

**Nodesign 是什么**：Agent-native、建在 real files 上的无限画布，holds 整个 **生成 → 审阅 → 圈选 → 修订** 闭环。你跟 agent 说要什么 → 它在画布上生成 artifacts(HTML/图/文档，真文件) → 你圈选/评论「this」→ agent 改背后真文件 → 回画布。

**可迁移的关键机制**（WorldLines 造世界/角色/CG 直接照搬）：
- **agent ↔ 画布 = in-process MCP 工具**：感知(`screenshot_canvas`/`list_pages`/`query_elements`) · 控制(`navigate`/`highlight`/`expose_tweaks`/写盘) · 反馈(`get/clear_pending_changes` 拿用户圈选评论)。WorldLines 已有 NeonRP agent + `mcp_client`/`mcp_pool`，同模式可复用。
- **数据模型 file-first**：`spec.json`(画布布局) + `pending-changes.json`(用户直改 buffer) + **元素 anchor schema**(跨 patch 稳定查找，像我们 manifest 的 anchor)。WorldLines 的 souls/worlds 本就是 real files，天然契合。
- **选区上下文随消息走**：用户当前视图 + 选中 + 圈选区 → agent 知道「this」指谁 → 改对应真文件。
- **图片生成内建**（Canvas.md §6.6 3-角色模型 + 7 页型）——正对我们「生成 CG / 立绘」。
- **画布库不同**：Nodesign 自研(react-rnd 拖拽卡片 + zustand，artifacts=HTML iframe)；我们 observe 用 xyflow(节点图)。两种画布**用途不同**：xyflow=世界地图/souls(空间关系)；Nodesign 式=生成审阅 artifacts。生成画布复用 xyflow 还是学 Nodesign 卡片式，待设计。

**定位**：= M31「build 模式 coding-agent 建 agent」的**可视化前端**——TUI 侧 build 是命令行，web 侧 build 是这块生成画布。**独立大轨**（不阻塞 observe/play 合并）。要专门立 spec，深挖 Nodesign 的 `server/`(agent loop) + `Canvas.md` §5 交互链路 + §6 数据模型。
