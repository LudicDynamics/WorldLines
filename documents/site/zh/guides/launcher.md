---
title: "WorldLines 启动器"
description: "双击启动器指南 —— 最友好的开始 session 的方式。"
---

<!-- section: intro -->
## 启动器做什么

启动器是一个自包含文件,双击即可启动 WorldLines。首次运行无需终端。

三种版本:

- `WorldLines.command`(macOS)
- `WorldLines.bat`(Windows)
- `WorldLines.sh`(Linux —— 先执行 `chmod +x`)

从 [worldlines.gg](https://worldlines.gg) → **Quick Install** 下载。

<!-- section: screenshots -->
## 流程演示

📸 **截图稍后补上** —— 本页是占位。演示会展示:

1. 从 Finder / 资源管理器 / 文件管理器启动该文件
2. 首次运行的引导(检测 Python,必要时安装)
3. Provider 选择器(GLM / OpenAI / LM Studio / Ollama)
4. 首个世界的选择器(默认 Stoneford)
5. TUI 自动打开

截图正在 macOS / Windows / Linux 上拍摄,随后就会补上。

<!-- section: troubleshooting -->
## 常见问题

- **macOS "来自身份不明的开发者"** —— 首次请右键点击 → 打开,而不是直接双击。
- **Windows SmartScreen** —— 点击"更多信息" → "仍要运行"。脚本在 v0.1 阶段未签名。
- **Linux 权限被拒** —— 先执行一次 `chmod +x WorldLines.sh`,再 `./WorldLines.sh`。
- **找不到 Python** —— 启动器通过 `uv` 自动安装 3.12。如果 `uv` 安装失败,请手动安装:`curl -LsSf https://astral.sh/uv/install.sh | sh`。
