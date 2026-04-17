# Installing WorldLines

**Language:** [English](./INSTALL.md) · [简体中文](./INSTALL.zh.md) · [日本語](./INSTALL.ja.md) · [한국어](./INSTALL.ko.md)

> Status: Beta — install paths stable for v0.1.0

WorldLines ships as the `neonrp` command-line tool. It runs on macOS and
Linux. Windows is not officially supported for v0.1.0 (WSL2 works).

## Requirements

| Component | Minimum | Notes                                          |
|-----------|---------|------------------------------------------------|
| Python    | 3.11    | 3.12 recommended                               |
| `uv`      | 0.4+    | [install](https://docs.astral.sh/uv/)          |
| OS        | macOS 13 / Ubuntu 22.04 | Apple Silicon & x86_64 both OK   |
| Terminal  | 256-color, UTF-8 | iTerm2 / Alacritty / Ghostty / tmux-wrapped |
| LLM       | One of: GLM, OpenAI, LM Studio, Ollama | See below          |

## Installation Options

### Option A — `uv tool install` (recommended)

Editable install picks up engine updates when you `git pull`.

```bash
git clone <worldlines-repo-url> worldlines
cd worldlines
uv tool install -e .

# Verify
neonrp --help
```

### Option B — Prebuilt wheel

```bash
uv tool install ./dist/neonrp-0.1.0-py3-none-any.whl
neonrp --help
```

### Option C — Run without installing

```bash
uv run --project /path/to/worldlines neonrp --help
```

### Option D — One-shot installer script

If you cloned the repo, a convenience script is included:

```bash
./install.sh
```

## macOS-specific notes

- If your default `python3` is the system one, let `uv` manage its own
  Python: `uv python install 3.12`.
- Terminal emulator must support truecolor for the TUI. Apple Terminal is
  limited; prefer iTerm2, Ghostty, or Alacritty.

## Linux-specific notes

- On Ubuntu 22.04+ install `uv` via the official shell installer.
- Headless servers: the TUI requires a real TTY. Use `tmux` or `screen` if
  connecting over SSH.

## LLM Provider Configuration

WorldLines reads provider settings from `~/.neonrp/config.json` (global) and
`./.neonrp/config.json` (per-project override). Run `neonrp init` in a
project directory to generate a template.

### Example — GLM (ZhipuAI)

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

### Example — OpenAI

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

### Example — LM Studio (local, OpenAI-compatible)

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

### Example — Ollama (local)

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

### Optional — Embedding retrieval

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

When embedding is enabled, `neonrp index build` will precompute vectors and
the context retrieval pipeline becomes hybrid (fuzzy + vector).

## Environment Variables

| Variable            | Purpose                               |
|---------------------|---------------------------------------|
| `OPENAI_API_KEY`    | OpenAI                                |
| `GLM_API_KEY`       | Zhipu GLM                             |
| `ANTHROPIC_API_KEY` | Anthropic                             |
| `NEONRP_E2E_LLM`    | Enable real-endpoint integration tests|

A `.env` file in the project root is auto-loaded.

## Uninstall

```bash
uv tool uninstall neonrp
```

Project data (`.neonrp/` directories) is preserved.

## Next

- [QUICKSTART.md](QUICKSTART.md) — your first play session
- [templates/stoneford/](templates/stoneford/README.md) — sample world
