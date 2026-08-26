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
