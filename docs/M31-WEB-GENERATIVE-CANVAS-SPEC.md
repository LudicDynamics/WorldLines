# M31 · Web 生成画布 spec — agent 在画布上造世界/角色/CG（参考 Nodesign）

> **范围**：WorldLines web 的 **build/生成** 侧富前端。是 M31「build 模式 coding-agent 建 agent」的**可视化前端**（TUI 侧 build=命令行；web 侧 build=这块画布）。
> **参考实现**：`~/Workspaces/worldlines/worldlines-design/Nodesign`（`@xiaobuyu/nodesign`）—— agent-native、建在 real files 上的无限画布，holds 整个 **生成→审阅→圈选→修订** 闭环。
> 纪律：独立大轨、分支开发、不发布、不破坏 observe/play。niko 2026-08-27 定「无限画布=agent 通过画布生成图/角色/逻辑，很仔细的功能」。

---

## 1. 一句话
不是「把 AI 输出摆到画布上」，是**画布 holds 整个闭环**：你跟 build-agent 说要什么 → 它在画布上生成 artifacts（soul / 世界 / 地点 / CG，**真文件**）→ 你在画布上**圈选/评论「this」**→ agent 改背后真文件 → 回画布。跟 WorldLines file-first 天然同构（souls/worlds 本就是 real files）。

## 2. Nodesign 可迁移的核心机制（照搬）

### 2.1 闭环三链路（Canvas.md §5）
- **用户改/圈 → agent 看见**：用户在画布直接编辑或圈选评论 → 落 `pending-changes.json` buffer（`{kind:'edit'|'comment', anchor, aiContext, diff?/text?}`）。下条 chat 时 turn 组装器看 buffer 非空 → prepend `<system>用户做了 N 处变更/评论</system>` → agent 主动 `get_pending_changes` → 区分 edit(既成事实别 revert) vs comment(修改请求→用 Edit 改) → `clear_pending_changes` → 收尾总结。**这就是「context 随消息走 / agent 知道 this 指谁」的机制。**
- **用户调参 → agent 固化**：agent `expose_tweaks` → 前端渲染控件 → 用户拖 → [Apply] → agent Edit 源文件固化。
- **agent 反向操作画布**：`navigate_to`/`highlight` → 前端滚动/脉冲高亮 → 用户视觉锚定。

### 2.2 agent↔画布 = in-process MCP 工具（Canvas.md §4，13 个）
| 组 | 工具 |
|---|---|
| 感知 | `screenshot_canvas` · `list_pages` · `read_page` · `query_elements` · `get_computed_styles` |
| 控制 | `navigate_to_page` · `highlight` · `expose_tweaks` · `record_decision` |
| 反馈 | `get_pending_changes` · `clear_pending_changes` |
| 其他 | `web_search` · `export_handoff` · `ping` |
> in-process（同进程函数调用，无 IPC）；WorldLines 已有 NeonRP agent + `mcp_client.py`/`mcp_pool.py`，同模式可复用。

### 2.3 数据模型（Canvas.md §6，file-first）
- per-session 落盘：`canvas.html`(主产物) + `spec.json`(意图+decisions+history+tweaks) + `pending-changes.json`(用户 buffer) + `.git/`(per-session 版本,commit=user-edit/agent-edit)。
- **元素 anchor**：`{dataId(data-node-id,agent 写时埋,最可靠), path(tag:nth 链), textHint(前50字fuzzy), bbox}` → `findElementByAnchor` 三层 fallback。跨 patch 稳定查找某元素。

## 3. 映射到 WorldLines（差异 = 多文件多类型 artifact）
Nodesign 一个 `canvas.html`；WorldLines 是**多个 real-file artifacts**：
| Nodesign | WorldLines 生成画布 |
|---|---|
| canvas.html(一个 HTML) | **多张卡**:soul 卡(`souls/<sid>/`) · 地点卡(`game/locations/*.json`) · CG 图卡 · 世界卡 |
| 双击改字 | 圈选一张 soul 卡/CG → 评论「更阴郁」 |
| agent Edit canvas.html | agent 调 `soul-authoring`/`world-authoring`/`entity-authoring` skill 改对应真文件 + 出图 |
| spec.json(单页布局) | 画布布局 spec(哪张卡在哪) + 复用 souls/worlds 真文件为 artifact 源 |
| 元素 anchor(dom) | artifact anchor:`{kind:'soul'|'location'|'cg', id, field?}` |

**WorldLines 版 MCP 工具**（镜像 Nodesign 13，改造）：
- 感知：`list_artifacts`(souls/locations/CG) · `read_artifact` · `query_artifact` · `screenshot_canvas`
- 控制：`navigate_to`(某卡) · `highlight` · `write_soul`/`write_location`(经 skill) · `generate_cg`(出图,接 `/api/v1/local/settings/image`) · `record_decision`
- 反馈：`get/clear_pending_changes`(用户在卡上的圈选/评论)

**闭环例子**：「给我一个香料女巫，永远十六七岁」→ build-agent 用 `soul-authoring` scaffold soul + `generate_cg` 出立绘 → 画布出一张 soul 卡 → 用户圈立绘评论「眼神更冷」→ pending-changes → agent 重出图 → 卡更新。

## 4. 与其它面的关系
- **observe/play**（`ObservatoryShell`）= **看/玩** 活世界（souls 移动、附身下场）。
- **生成画布** = **build/造** 世界与角色（agent 生成、你圈选修订）。
- **M31 TUI build** = 同一个 build,命令行前端;**生成画布 = build 的 web 前端**。三者共享同一批 file-first 真文件(souls/worlds/CG)。

## 5. 分阶段（G 系列，独立于 observe/play）
- **G0 · 深挖 Nodesign**：读 `server/`(engine/edit/runtime/skills 的 agent-loop + 文件编辑) + Canvas.md 全文 + `web/src/components/canvas/`;定「复用 Nodesign 引擎/前端」还是「学它自研」。
- **G1 · 画布壳 + artifact 卡**：web 加 `/local/build` 路由;读 souls/worlds/CG 渲成卡(卡库选型:xyflow 节点 vs Nodesign react-rnd 卡片,见开放问题)。纯读先行。
- **G2 · build-agent MCP 工具面**：NeonRP 侧起 in-process MCP(镜像 §3 工具);agent 能 list/read/write artifact + generate_cg。
- **G3 · 圈选→pending-changes→agent 修订闭环**：前端圈选/评论落 buffer;turn 组装注入 system;agent 拿 context 改真文件;anchor 稳定定位。
- **G4 · tweaks/参数固化 + 反向 highlight**：agent expose 可调项;navigate/highlight 反向操作画布。
- 每步:lint/build 绿、不破坏 observe/play、分支不发布。

## 6. 开放问题
1. **画布库**：复用 Nodesign（react-rnd 卡片 + 它整套 server）最快但引入大依赖 vs WorldLines 自研（可与 observe 的 xyflow 统一）。→ G0 拍板。
2. **artifact 卡形态**：soul/地点/CG 卡的视觉与 Nodesign 的 HTML iframe 不同,要自定义。
3. **build-agent 落哪**：复用 NeonRP build 模式 agent + 加 MCP 工具面,还是新起一个 web-build service。
4. **出图管线**:接现有 `/api/v1/local/settings/image` + soul 立绘出图,复用不重造。
5. **与 Obsidian**:生成画布是 web 富前端;Obsidian 仍是 file-first 长时段视图,两不冲突。

## 7. 参考锚（深挖清单）
- `Nodesign/Canvas.md`(30KB,全)：§2 架构 · §4 MCP 工具 · §5 交互链路 · §6 数据模型 · §8 怎么扩展 · §9 设计决策
- `Nodesign/server/`：engine / edit / runtime / skills / api（agent-loop + 文件编辑 + in-proc MCP）
- `Nodesign/web/src/components/canvas/`：前端画布组件
- `Nodesign/Claude_design.md`(73KB)：完整设计
- WorldLines 侧复用：`NeonRP core/mcp_client.py`/`mcp_pool.py`(MCP) · `soul-authoring`/`world-authoring`/`entity-authoring` skill · `/api/v1/local/settings/image`(出图)
