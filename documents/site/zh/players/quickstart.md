---
title: "玩家快速开始"
description: "装好 WorldLines,在浏览器里进入第一个世界。"
---

<!-- section: install -->
## 1. 安装

> **状态:随 1.0 发布**

**桌面应用(推荐)** —— 首次启动会自动装好引擎,然后打开本地 Web 产品。

| 平台 | 文件 |
|---|---|
| macOS(Apple Silicon) | [WorldLines-Installer.dmg](https://github.com/LudicDynamics/WorldLines/releases/latest/download/WorldLines-Installer.dmg) |
| Windows | [WorldLines-Desktop-windows-x64-setup.exe](https://github.com/LudicDynamics/WorldLines/releases/latest/download/WorldLines-Desktop-windows-x64-setup.exe) |

macOS:右键安装器 → 打开 → 打开。Windows:SmartScreen → 更多信息 → 仍要运行。

**或者用终端**(Linux 用这个):

```bash
pip install worldlines        # 或:uv tool install worldlines(任何系统)
# 一行安装器 —— macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh
# Windows(PowerShell)
irm https://worldlines.gg/install.ps1 | iex
```

<!-- section: open -->
## 2. 打开

```bash
worldlines        # 浏览器打开 http://127.0.0.1:8787/local
```

首次运行会引导你设置模型提供商,见 [设置模型提供商](/docs/players/providers)。你的世界和存档都在 `~/.worldlines`。

<!-- section: hub -->
## 不想装?

打开 [hub.worldlines.gg](https://hub.worldlines.gg),登录就能在浏览器里玩。

<!-- section: next -->
## 下一步

[第一次进世界:石津](/docs/players/first-world) → [怎么玩](/docs/players/how-to-play)
