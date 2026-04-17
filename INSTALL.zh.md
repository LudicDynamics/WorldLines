# 安装 WorldLines

**Language:** [English](./INSTALL.md) · [简体中文](./INSTALL.zh.md) · [日本語](./INSTALL.ja.md) · [한국어](./INSTALL.ko.md)

> 状态：Beta — v0.1.0 的安装路径已稳定

WorldLines 以 `neonrp` 命令行工具的形式发布，运行于 macOS 和 Linux。v0.1.0 不正式支持 Windows（WSL2 可用）。

## 环境要求

| 组件      | 最低版本                | 说明                                              |
|-----------|-------------------------|---------------------------------------------------|
| Python    | 3.11                    | 推荐 3.12                                         |
| `uv`      | 0.4+                    | [安装指南](https://docs.astral.sh/uv/)            |
| OS        | macOS 13 / Ubuntu 22.04 | Apple Silicon 与 x86_64 均可                      |
| 终端      | 256 色、UTF-8           | iTerm2 / Alacritty / Ghostty / tmux 包装          |
| LLM       | GLM、OpenAI、LM Studio、Ollama 任一 | 见下文                                |

## 安装方式

### 方案 A —— `uv tool install`（推荐）

editable 安装会在你 `git pull` 时自动跟进引擎更新。

```bash
git clone <worldlines-repo-url> worldlines
cd worldlines
uv tool install -e .

# 校验
neonrp --help
```

### 方案 B —— 预构建 wheel

```bash
uv tool install ./dist/neonrp-0.1.0-py3-none-any.whl
neonrp --help
```

### 方案 C —— 不安装直接运行

```bash
uv run --project /path/to/worldlines neonrp --help
```

### 方案 D —— 一键安装脚本

克隆仓库后，里面附带了一个便捷脚本：

```bash
./install.sh
```

## macOS 专属说明

- 如果默认的 `python3` 是系统自带版本，建议让 `uv` 管理自己的 Python：`uv python install 3.12`。
- 终端模拟器必须支持 truecolor 才能正常渲染 TUI。Apple Terminal 能力有限；建议使用 iTerm2、Ghostty 或 Alacritty。

## Linux 专属说明

- 在 Ubuntu 22.04+ 上通过官方 shell 安装器安装 `uv`。
- 无头服务器：TUI 需要真实的 TTY。通过 SSH 连接时请使用 `tmux` 或 `screen`。

## LLM Provider 配置

WorldLines 从 `~/.neonrp/config.json`（全局）和 `./.neonrp/config.json`（项目级覆盖）读取 provider 设置。在项目目录执行 `neonrp init` 会生成模板文件。

### 示例 —— GLM（智谱 AI）

```json
{
  "provider": "glm",
  "models": {
    "glm": {
      "provider": "openai",
      "base_url": "https://open.bigmodel.cn/api/paas/v4",
      "model": "glm-4-plus",
      "api_key_env": "GLM_API_KEY"
    }
  }
}
```

### 示例 —— OpenAI

```json
{
  "provider": "openai",
  "models": {
    "openai": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "api_key_env": "OPENAI_API_KEY"
    }
  }
}
```

### 示例 —— LM Studio（本地，OpenAI 兼容）

```json
{
  "provider": "lmstudio",
  "models": {
    "lmstudio": {
      "provider": "openai",
      "base_url": "http://127.0.0.1:1234/v1",
      "model": "qwen2.5-14b-instruct",
      "api_key": "lm-studio"
    }
  }
}
```

### 示例 —— Ollama（本地）

```json
{
  "provider": "ollama",
  "models": {
    "ollama": {
      "provider": "openai",
      "base_url": "http://127.0.0.1:11434/v1",
      "model": "qwen2.5:14b",
      "api_key": "ollama"
    }
  }
}
```

### 可选 —— Embedding 检索

```json
{
  "embedding": {
    "enabled": true,
    "model_ref": "openai-local-qwen3-embedding-0.6b"
  },
  "models": {
    "openai-local-qwen3-embedding-0.6b": {
      "provider": "openai",
      "base_url": "http://127.0.0.1:1234/v1",
      "model": "text-embedding-qwen3-embedding-0.6b",
      "api_key": "1234"
    }
  }
}
```

启用 embedding 后，`neonrp index build` 会预计算向量，上下文检索 pipeline 即变为混合检索（fuzzy + vector）。

## 环境变量

| 变量                 | 用途                                 |
|----------------------|--------------------------------------|
| `OPENAI_API_KEY`     | OpenAI                               |
| `GLM_API_KEY`        | 智谱 GLM                             |
| `ANTHROPIC_API_KEY`  | Anthropic                            |
| `NEONRP_E2E_LLM`     | 启用真实 endpoint 集成测试           |

项目根目录下的 `.env` 文件会被自动加载。

## 卸载

```bash
uv tool uninstall neonrp
```

项目数据（`.neonrp/` 目录）会被保留。

## 下一步

- [QUICKSTART.zh.md](QUICKSTART.zh.md) — 你的第一次游玩
- [templates/stoneford/](templates/stoneford/README.zh.md) — 示例世界
