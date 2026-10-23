# 05 · 用 TUI 游玩与管理(终端指南)

**目标:** 不碰浏览器,在终端里完成 WorldLines 的完整闭环——装引擎、选世界、开一局、
游玩中的常用命令、管理存档与角色。
**适合:** 喜欢终端的玩家、想在 SSH/服务器上跑的玩家、给 AI 助手当"手册"的场景。

> 只想点鼠标?浏览器版更省事:装好后跑 `worldlines web`(或直接 `worldlines`),打开 `http://127.0.0.1:8787/local`。
> 这篇讲的是纯终端(TUI)路线,两边读写同一份数据(`~/.worldlines/` 与 `~/.neonrp/config.json`),随时互换。

## 0. 安装

```bash
curl -LsSf https://worldlines.gg/install.sh | sh
# 或者:pip install neonrp
```

装好后有两个入口:

| 命令 | 是什么 |
|---|---|
| `worldlines` | **引导式启动器**——菜单选世界/存档/新建/设置,选完自动进游戏 |
| `neonrp` | **对话式 TUI**(仿 Claude Code)——直接进当前目录的世界,斜杠命令驱动 |

第一次跑 `worldlines` 会先让你选界面语言,然后进主菜单。

## 1. 第一局:`worldlines` 启动器

主菜单是 2×2 象限:**游玩**(继续 / 新建游戏)、**世界库**(新建 / 导入 / Hub 下载 / 上传 / 管理)、
**角色库**(Soul Talk / 新建角色 / 导入 / Hub / 管理)、底部条(设置 / 退出)。快捷键:`c` 继续、`n` 新建、`s` 设置。

新建一局的流程链:

```
选世界 → 选分身 + 带入角色(Casting,可编辑每个 NPC 的动机/关系/起始位置)
      → 选模型 preset(第一次会引导你填 API key)
      → 选渲染面:🌟 浏览器 Web / 终端 TUI
```

选「终端 TUI」就进对话式界面,世界会自动开演——直接开始扮演即可。

## 2. 游玩中的斜杠命令(常用速查)

输入框里 `/` 开头,有 ghost-text 补全和下拉建议。

| 命令 | 作用 |
|---|---|
| `/save [名字]` · `/load [名字]` | 命名存档 / 读档 |
| `/undo` · `/redo` | 撤回 / 重做上一次变化(检查点级,不丢当前线) |
| `/cast <soul> [npc\|player]` | 把库里的角色投放进本局 |
| `/mode [build\|play]` | 切创作 / 游玩模式(build = agent 可以自由改世界文件) |
| `/models` · `/auth` · `/config` | 模型与 key 管理 |
| `/locale [auto\|en\|zh\|ja\|ko]` | 界面语言 |
| `/export-world [out.zip]` · `/load-world <zip>` | 世界打包 / 恢复 |
| `/stats` · `/compact` · `/sessions` | 会话统计 / 压缩上下文 / 会话列表 |
| `/settings` | 完整设置(provider、创作 LLM、Discord、图像生成) |
| `/help` | 全部命令 |

全局键位:`Ctrl+K` 命令面板、`Ctrl+L` 切换信息层(L1/L2/L3)、`F6` 复制对话记录、`q` 退出。

## 3. 无界面纯 REPL:`neonrp play`

要最轻量的循环(适合脚本/低配终端):

```bash
neonrp play                 # 进 REPL,输入即行动
neonrp play "环顾四周"       # 单回合一次性执行
```

REPL 里 `/trace` 看上一回合的路由(哪些角色被激活、为什么),`/debug` 看最近的 agent 调用。

## 4. 设置(`worldlines` → 设置,或游玩中 `/settings`)

- **模型条目**:每个 provider 一条,可测试连接 / 换 key / 换 model / 删除;「测试全部」一键体检
- **creation LLM**:创作(建世界/建角色/导入)单独用哪个模型,与游玩模型独立
- **图像生成**:ComfyUI(URL / ckpt / 自定义 workflow + 节点 id)或 OpenAI,给立绘和封面用
- **语言**、**Discord 桥接**、**配置文件位置**(`~/.neonrp/config.json`,和 Web 版同一份)

## 5. 常用 CLI 子命令(不进 TUI 也能干活)

```bash
worldlines web                  # 起浏览器版(LocalShell)
neonrp save / load / undo / redo
neonrp cast <soul> --into <世界目录>
neonrp export-world --world <id> -o out.zip
neonrp world upload <目录> --slug my-world     # 发布到 WorldHub
neonrp soul upload <目录>                      # 发布角色到 SoulHub
neonrp validate                                # 校验世界数据
```

## 6. 数据都在哪

```
~/.worldlines/worlds/   # 你的世界(库源,纯内容)
~/.worldlines/plays/    # 每一局(存档=一局的目录)
~/.worldlines/souls/    # 角色库(可复用,可带进任何世界)
~/.neonrp/config.json   # 模型 key / 图像后端 / 语言(TUI 与 Web 共用)
```

删档 = 删 `plays/` 里对应目录;备份 = 打包 `~/.worldlines`。

---

下一步:想创作内容,回到 [教程 README](./README.md) 的 AI 助手创作流;
想在浏览器里做同样的事,跑 `worldlines web` 打开 LocalShell。
