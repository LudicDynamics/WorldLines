# WorldLines のインストール

**Language:** [English](./INSTALL.md) · [简体中文](./INSTALL.zh.md) · [日本語](./INSTALL.ja.md) · [한국어](./INSTALL.ko.md)

> ステータス: Beta — v0.1.0 のインストール経路は安定

WorldLines は `neonrp` コマンドラインツールとして配布され、macOS と Linux で動作します。v0.1.0 では Windows は公式サポート外です（WSL2 は動きます）。

## 要件

| コンポーネント | 最低                      | 備考                                                   |
|----------------|---------------------------|--------------------------------------------------------|
| Python         | 3.11                      | 3.12 推奨                                              |
| `uv`           | 0.4+                      | [install](https://docs.astral.sh/uv/)                 |
| OS             | macOS 13 / Ubuntu 22.04   | Apple Silicon・x86_64 どちらも可                      |
| Terminal       | 256 色、UTF-8             | iTerm2 / Alacritty / Ghostty / tmux ラップ            |
| LLM            | GLM / OpenAI / LM Studio / Ollama のいずれか | 下記参照                          |

## インストール方法

### オプション A — `uv tool install`（推奨）

editable インストールなら `git pull` したときにエンジン更新を拾えます。

```bash
git clone <worldlines-repo-url> worldlines
cd worldlines
uv tool install -e .

# 確認
neonrp --help
```

### オプション B — ビルド済み wheel

```bash
uv tool install ./dist/neonrp-0.1.0-py3-none-any.whl
neonrp --help
```

### オプション C — インストールせずに実行

```bash
uv run --project /path/to/worldlines neonrp --help
```

### オプション D — ワンショットインストールスクリプト

リポジトリを clone 済みなら、便利スクリプトが同梱されています:

```bash
./install.sh
```

## macOS 固有の注意

- デフォルトの `python3` がシステムのものなら、`uv` 自身に Python を管理させてください: `uv python install 3.12`。
- TUI には truecolor 対応のターミナルが必要。Apple Terminal は機能が弱いので、iTerm2 / Ghostty / Alacritty を推奨。

## Linux 固有の注意

- Ubuntu 22.04+ では `uv` を公式シェルインストーラで導入。
- ヘッドレスサーバ: TUI は実 TTY を要求します。SSH 経由なら `tmux` か `screen` を併用してください。

## LLM プロバイダ設定

WorldLines は `~/.neonrp/config.json`（グローバル）と `./.neonrp/config.json`（プロジェクト上書き）から provider 設定を読み込みます。プロジェクトディレクトリで `neonrp init` を実行するとテンプレートが生成されます。

### 例 — GLM (ZhipuAI)

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

### 例 — OpenAI

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

### 例 — LM Studio（ローカル、OpenAI 互換）

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

### 例 — Ollama（ローカル）

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

### オプション — Embedding 検索

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

embedding を有効化すると、`neonrp index build` がベクトルを事前計算し、コンテキスト検索パイプラインはハイブリッド（fuzzy + vector）になります。

## 環境変数

| 変数                | 用途                                     |
|---------------------|------------------------------------------|
| `OPENAI_API_KEY`    | OpenAI                                   |
| `GLM_API_KEY`       | Zhipu GLM                                |
| `ANTHROPIC_API_KEY` | Anthropic                                |
| `NEONRP_E2E_LLM`    | 実エンドポイント統合テストを有効化       |

プロジェクトルートの `.env` は自動で読み込まれます。

## アンインストール

```bash
uv tool uninstall neonrp
```

プロジェクトデータ（`.neonrp/` ディレクトリ）は保持されます。

## 次へ

- [QUICKSTART.ja.md](QUICKSTART.ja.md) — 初回プレイ
- [templates/stoneford/](templates/stoneford/README.ja.md) — サンプル世界
