# 发布说明

**Language:** [English](./RELEASE_NOTES.md) · [简体中文](./RELEASE_NOTES.zh.md) · [日本語](./RELEASE_NOTES.ja.md) · [한국어](./RELEASE_NOTES.ko.md)

> 状态：Beta — v0.1.0 公开预览版

## v0.1.0 — 2026-04-17（D-Day）

**WorldLines**（引擎代号 `neonrp`）的首次公开预览。

### 本次发布

**引擎核心**
- Event-sourced 状态：append-only 日志 + snapshots
- Branch / undo / redo
- Sandbox 创建、切换、销毁
- 用于确定性校验的 replay verification
- Schema 校验（`game_entity.schema.json`）
- 实体索引，支持 fuzzy + 可选 embedding（混合）检索

**Agents 与 harness**
- Plan → Diff → Apply 流水线
- 支持 trigger / tag / priority 路由的 dispatcher
- 多轮 agentic 循环（`--agentic`）
- 随引擎打包的 builtin skills
- 通过 `task()` 实现的 orchestrator 驱动多 agent 协作

**LLM provider**
- OpenAI 兼容（OpenAI、GLM、LM Studio、Ollama）
- 用于测试的 stub provider + fixture 文件

**TUI（M9+）**
- Claude-Code 风格对话式布局
- `build` / `sandbox` / `play` 模式
- 斜杠命令 + Tab 自动补全
- 会话管理（`/continue`、`/new`、`/sessions`）
- 实时 token 计数、流式 transcript、thinking 通道

**导入**
- SillyTavern 角色卡（JSON + PNG tEXt）

**模板**
- `default` —— 最小起步
- `isekai` —— 日式异世界草稿
- `kagura-island` —— 悬疑剧
- `tokyo-science-university` —— 现代日常
- `dark-train` —— 意识流短篇
- **`stoneford`** —— 头牌样本：5 座城、28+3 条任务、6 个 agent、d20 战斗规则（见 [templates/stoneford/](templates/stoneford/README.zh.md)）

### 已知限制

- 仅支持 Python 3.11+；不正式支持 Windows（请用 WSL2）。
- Embedding 检索需要一个本地 OpenAI 兼容的 embedding server。
- 大型世界（>2k 实体）尚未做性能调优。
- 无 Web UI —— v0.1 仅限终端。
- `replay verify` 很严格：LLM 非确定性若无缓存 fixture 会被判为偏离。请使用 temperature=0 或 fixture。
- 不支持多人 / 共享 branch。仅面向单作者工作流。
- Stoneford 起步模板是英文 / CJK 混合；本地化管线仍是预览级。
- 引擎的授权条款为 **预览 / 待定**。详见 [LICENSE](LICENSE)。
- **Harness strictness（harness 严格性）**：NeonRP orchestration 依赖完整的上下文。若实体数据缺失，可能需要手动调整 harness。
- **Beta API 稳定性**：引擎核心正在快速迭代。在我们平衡确定性与灵活性的过程中，v0.2 与 v0.3 预计会有破坏性变更。

### 路线图 —— 未来里程碑

**v0.2（2026 Q2 末）**
- 公开数据格式规范（"WorldLines Data" 标准）
- 每 agent 的策略语言（对 ops 的硬约束）
- 基于图的 NPC 记忆
- Web 伴读查看器（只读）

**v0.3**
- 多 branch 差异与合并工具
- 共享世界的协作 sandbox
- First-class Anthropic provider
- 更丰富的 combat referee DSL

**v1.0**
- 稳定的引擎 API
- 1.0 版公开数据格式
- 社区模板市场

关于战略叙事见 [task-thinking/gotomarket-releases-open-source-rethink-0326.md](../../task-thinking/gotomarket-releases-open-source-rethink-0326.md)。

### 鸣谢

东京独立开发、由 Ludic Dynamics 的创始人一人完成。特别感谢前身项目 `llm-rpg-starter` 的早期测试者。

---

*Bug 报告与功能请求请在公开仓库上开 issue（链接待 D-Day 公布）。*
