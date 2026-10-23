---
title: "TUI 终端指南"
description: "在终端里游玩与管理:worldlines 启动器、斜杠命令、设置与数据位置。"
---

<!-- section: entries -->
## 两个入口

装好以后(`pip install worldlines`,或 `uv tool install worldlines`,或一行安装器 `curl -LsSf https://worldlines.gg/install.sh | sh`)有两个命令;启动时都会检查新版并自动更新:

- **`worldlines`** — 本地网页,http://127.0.0.1:8787/local:世界、存档、创作台、设置。
- **`neonrp`** — 终端:「Welcome to WorldLines」启动器选世界或存档后进游戏;里面用斜杠命令(`/status` · `/plan` · `/update` …)。首次运行会先选界面语言。

> 浏览器党:`neonrp web` 打开 http://127.0.0.1:8787/local 就是 Web 版 LocalShell —— 和 TUI 读写同一份数据,随时互换。

<!-- section: first-run -->
## 第一局

`worldlines` 主菜单是 2×2 象限:**游玩**(继续/新建)、**世界库**(新建/导入/Hub 下载/上传/管理)、**角色库**(Soul Talk/新建/导入/Hub/管理)、底部条(设置/退出)。快捷键 `c` 继续、`n` 新建、`s` 设置。

新建一局的流程链:**选世界 → 选分身+带入角色(Casting)→ 选模型 preset(首次引导填 key)→ 选渲染面(🌟浏览器 / 终端)**。选终端即进对话式界面,世界自动开演。

<!-- section: slash -->
## 游玩中的斜杠命令

输入 `/` 有补全与建议。常用:

- `/save [名]` · `/load` · `/undo` · `/redo` — 存档与检查点级撤回/重做
- `/cast <soul> [npc|player]` — 把库里的角色投放进本局
- `/mode [build|play]` — 创作/游玩模式切换(build 下 agent 可自由改世界文件)
- `/models` · `/auth` · `/config` · `/locale` — 模型、key、语言
- `/export-world` · `/load-world <zip>` — 世界打包/恢复
- `/settings` — 完整设置;`/help` — 全部命令

全局键位:`Ctrl+K` 命令面板、`Ctrl+L` 信息层切换、`F6` 复制对话记录。

纯 REPL:`neonrp play`(输入即行动,`/trace` 看上回合路由,`/debug` 看 agent 调用)。

<!-- section: settings-data -->
## 设置与数据位置

设置(启动器「设置」或 `/settings`):模型条目(测试/换 key/删除)、creation LLM(创作专用模型)、图像生成(ComfyUI URL/ckpt/自定义 workflow 节点,或 OpenAI)、语言、Discord 桥接。

数据都在:

- `~/.worldlines/worlds/` 世界库源 · `plays/` 每一局 · `souls/` 角色库
- `~/.neonrp/config.json` 模型 key/图像后端/语言(TUI 与 Web 共用)

备份 = 打包 `~/.worldlines`;删档 = 删 `plays/` 里对应目录。
