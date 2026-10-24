# 05 · 用终端游玩与管理

**目标:** 不碰浏览器,在终端里完成 WorldLines 的完整闭环:安装、选世界、开一局、
游玩中的常用命令、管理存档与角色。
**适合:** 喜欢终端的玩家、想在 SSH / 服务器上跑的玩家、给 AI 助手当「手册」的场景。

> 想用浏览器:装好后跑 `worldlines`,打开 `http://127.0.0.1:8787/local`。
> 两边读写同一份数据(`~/.worldlines/` 与 `~/.neonrp/config.json`),随时互换。

## 0. 安装

需要 Python 3.10 或更新。

```bash
pip install worldlines        # 或:uv tool install worldlines / pipx install worldlines
# 只要终端版:pip install neonrp
# 一行安装器:curl -LsSf https://worldlines.gg/install.sh | sh
```

装好后有两个命令:

| 命令 | 是什么 |
|---|---|
| `worldlines` | 本地网页,`http://127.0.0.1:8787/local` |
| `neonrp` | 终端:「Welcome to WorldLines」启动器,选世界或存档后进游戏 |

两个命令启动时都会检查新版本,有就自己更新并重启。想先问一声:游戏里 `/update mode prompt`;只提示不更新:`/update mode notify`。

## 1. 第一局:`neonrp` 启动器

第一次跑 `neonrp` 会先让你选界面语言,然后进首页。首页分四块:

- **继续**:「⚡ 接着上次」一键进最近的一局;也可以从存档里挑;
- **新游戏**:挑一个世界开新的一局;
- **世界库**:新建世界、上传到 Hub、浏览并游玩;
- **角色库**:和角色聊天(灵魂对话)、新建角色、上传到 Hub、浏览。

底部是设置和退出。按键:方向键或 `Tab` 移动,`Enter` 确认,`r` 接着上次,`c` 继续,`n` 新游戏,`s` 设置,`Esc` 退出。

本地自带两个世界:**灰橡宅 · 关上的门**(一夜的百分骰推理,第一次玩推荐)和 **石津镇 · 雾退之夜**(开放小镇)。
其他官方世界在 Hub 里,登录 Worldlines 账号后可以下载到本机。

第一次开局会让你选模型:用 Worldlines 账号(游戏里 `/login`),或者填自己的 key(OpenCode Zen、DeepSeek、OpenRouter、
Anthropic、OpenAI、Kimi、GLM,或任何 OpenAI 兼容服务)。新的一局会自己开场。

## 2. 一回合怎么走

每一回合分两拍:

1. **商量**:你说想做什么,在场的角色接话,一起谈怎么做、要不要检定。世界还没变。
2. **清算**:谈妥之后,主持写出发生了什么,掷该掷的骰子,把结果写进世界。

什么时候算谈妥,由判官判断:登录了是 Jev,没登录是这一局自己的模型(每拍多几秒)。说「定」或 `@dm` 可以马上推进。
状态先写下,后台再复核一遍;复核改了什么,会在那一拍下面告诉你。

## 3. 游玩中的常用命令

输入框里 `/` 开头,有补全和下拉建议。

| 命令 | 作用 |
|---|---|
| `/status` | 状态面板:你、在场的每个角色、用量;`/status plan` 计划板,`/status dice` 骰子 |
| `/who <角色>` | 看一个角色在哪、记得什么、最近在做什么 |
| `/save [名字]` · `/load` | 存一个快照 · 读存档或快照 |
| `/undo` · `/redo` | 退回上一步 · 做回来 |
| `/undo list` · `/undo <回合>` | 列出回合 · 回到那一回合另起一条线(原来那条保留) |
| `/open` | 列出能玩的世界和存档,换一局 |
| `/cast <角色>` | 把角色库里的角色请进这一局 |
| `/import <文件>` | 导入世界包(`.zip`)或酒馆角色卡(`.png` / `.json`) |
| `/mode build` · `/mode play` | 在同一个世界里切换:让 agent 改这个世界 / 玩 |
| `/settings` | 模型、key、Discord 桥接等设置 |
| `/login` | Worldlines 账号(可选) |
| `/help` | 全部命令 |

完整命令表(包括旧命令搬到了哪里)见 [docs.worldlines.gg 的「终端命令」](https://docs.worldlines.gg/docs/players/commands)。

按键:`Ctrl+K` 命令面板、`Ctrl+L` 切换显示层、`F6` 复制对话记录、`Ctrl+Q` 退出。

## 4. 没有界面的纯 REPL:`neonrp play`

要最轻量的循环(适合脚本、低配终端),在一局的文件夹里:

```bash
neonrp play                 # 进 REPL,输入即行动
neonrp play "环顾四周"       # 只跑一回合,打印叙事
neonrp play --json --trace "环顾四周"   # 输出 JSON,附上这一回合的编排记录
```

REPL 里 `/trace` 看上一回合的编排,`/debug` 看最近的 agent 调用。

## 5. 设置(启动器「设置」,或游戏里 `/settings`)

- **模型**:每个 provider 一条,可以测试连接、换 key、换模型、删除;也能加一个自定义的 OpenAI 兼容端点
- **创作用的模型**:建世界、建角色、导入角色卡时用哪个模型,和游玩模型分开
- **图像生成**:给立绘和封面用
- **语言**、**Discord 桥接**
- 都存在 `~/.neonrp/config.json`,和网页共用

## 6. 常用命令行(不进游戏也能干活)

```bash
neonrp template list                              # 有哪些模板
neonrp tui --from my/<id>.template                # 用一个模板开一局新的,直接进游玩
neonrp template fetch <世界 id>                    # 登录后下载一个官方世界
neonrp export-world -o out.zip                    # 把当前文件夹的世界打包成 zip
neonrp commit log                                 # 在一局的文件夹里:看提交图
neonrp --help                                     # 全部子命令
```

## 7. 数据都在哪

```
~/.worldlines/plays/       # 每一局(存档就是一局的文件夹)
~/.worldlines/templates/   # 你自己的模板
~/.worldlines/souls/       # 角色库(可复用,可带进任何世界)
~/.worldlines/official/    # 登录后下载的官方世界
~/.neonrp/config.json      # 模型 key / 图像后端 / 语言 / 更新方式(终端与网页共用)
```

删档 = 删 `plays/` 里对应的文件夹;备份 = 打包 `~/.worldlines` 和 `~/.neonrp/config.json`。

---

下一步:想创作内容,回到 [教程总览](./README.md) 的 AI 助手创作流;
想在浏览器里做同样的事,跑 `worldlines`。
