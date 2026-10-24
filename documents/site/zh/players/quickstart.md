---
title: "开始玩"
description: "三条路:在线玩、本地网页、终端。选一条,几分钟进第一个世界。"
---

<!-- section: paths -->
## 三条路

| 怎么玩 | 要装什么 | 入口 |
|---|---|---|
| **在线** | 不用装 | [worldlines.gg](https://worldlines.gg),或 iOS App |
| **本地网页** | `worldlines` | 浏览器里的 http://127.0.0.1:8787/local |
| **终端** | `worldlines` 或 `neonrp` | 在终端里敲 `neonrp` |

本地的网页和终端读写同一份世界、存档和设置,随时可以换着用。

<!-- section: online -->
## 在线玩

打开 [worldlines.gg](https://worldlines.gg),在 Hub 里挑一个世界,直接在浏览器里玩;手机上用 iOS App。不用装任何东西,也不用自己准备模型。

<!-- section: install -->
## 本地安装

需要 Python 3.10 或更新的版本。

```bash
pip install worldlines        # 或:uv tool install worldlines / pipx install worldlines
```

装 `worldlines` 会把引擎 `neonrp` 一起装上,所以两个命令都能用。只想要终端版:`pip install neonrp`。

源码和发布说明在 GitHub 仓库 [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)。一行安装器也还能用(会顺带装好 uv):

```bash
curl -LsSf https://worldlines.gg/install.sh | sh      # macOS / Linux
irm https://worldlines.gg/install.ps1 | iex           # Windows PowerShell
```

<!-- section: open -->
## 打开

```bash
worldlines        # 本地网页:自动在浏览器里打开 http://127.0.0.1:8787/local
neonrp            # 终端:进「Welcome to WorldLines」启动器
```

- **网页**:在「游玩一览」里点一个世界,点「新开一局」。以后在同一个地方点「继续」接着玩。
- **终端**:启动器里选「开始新的游戏」(`n`)挑世界;「⚡ 接着上次」(`r`)直接进最近的一局。第一次运行会先让你选界面语言。

第一次运行还会让你选一个模型,见[接模型](/docs/players/providers)。新的一局会自己开场,不用先打字。

<!-- section: update -->
## 自动更新

用 pip、uv tool 或 pipx 装的,`worldlines` 和 `neonrp` 启动时都会检查新版本;有新版就自己更新,然后重启进新版。想换个做法,在终端游戏里敲:

| 命令 | 效果 |
|---|---|
| `/update mode prompt` | 有新版时先问你 |
| `/update mode notify` | 只提示,不更新 |
| `/update mode auto` | 自己更新(默认) |
| `/update status` | 看当前版本和更新设置 |

从源码装的(`pip install -e`)只提示,不会自己更新。

<!-- section: data -->
## 数据在哪

| 位置 | 放什么 |
|---|---|
| `~/.worldlines/plays/` | 你玩过的每一局 |
| `~/.worldlines/templates/` | 你自己的模板(复制来改的、新建的) |
| `~/.worldlines/souls/` | 角色库 |
| `~/.worldlines/official/` | 登录后下载到本机的官方世界 |
| `~/.neonrp/config.json` | 模型、key、语言、更新方式 |

想备份,把 `~/.worldlines` 和 `~/.neonrp/config.json` 一起拷走。

<!-- section: next -->
## 下一步

[接模型](/docs/players/providers) → [第一局](/docs/players/first-world) → [一回合怎么走](/docs/players/how-to-play)
