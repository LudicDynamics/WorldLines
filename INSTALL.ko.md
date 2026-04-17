# WorldLines 설치

**Language:** [English](./INSTALL.md) · [简体中文](./INSTALL.zh.md) · [日本語](./INSTALL.ja.md) · [한국어](./INSTALL.ko.md)

> 상태: Beta — v0.1.0 설치 경로 안정

WorldLines 는 `neonrp` 커맨드라인 도구로 배포되며 macOS 와 Linux 에서 동작합니다. v0.1.0 에서 Windows 는 공식 지원 대상이 아닙니다 (WSL2 는 동작).

## 요구사항

| 구성요소    | 최소                      | 비고                                                |
|-------------|---------------------------|-----------------------------------------------------|
| Python      | 3.11                      | 3.12 권장                                           |
| `uv`        | 0.4+                      | [install](https://docs.astral.sh/uv/)              |
| OS          | macOS 13 / Ubuntu 22.04   | Apple Silicon / x86_64 모두 가능                    |
| 터미널      | 256 색, UTF-8             | iTerm2 / Alacritty / Ghostty / tmux 래핑            |
| LLM         | GLM / OpenAI / LM Studio / Ollama 중 하나 | 아래 참고                             |

## 설치 방법

### 옵션 A — `uv tool install` (권장)

editable 설치는 `git pull` 시 엔진 업데이트를 반영합니다.

```bash
git clone <worldlines-repo-url> worldlines
cd worldlines
uv tool install -e .

# 확인
neonrp --help
```

### 옵션 B — 사전 빌드 wheel

```bash
uv tool install ./dist/neonrp-0.1.0-py3-none-any.whl
neonrp --help
```

### 옵션 C — 설치 없이 실행

```bash
uv run --project /path/to/worldlines neonrp --help
```

### 옵션 D — 원샷 설치 스크립트

저장소를 clone 했다면 편의 스크립트가 포함되어 있습니다:

```bash
./install.sh
```

## macOS 관련 참고

- 기본 `python3` 이 시스템 것이라면, `uv` 가 자체 Python 을 관리하도록 하세요: `uv python install 3.12`.
- TUI 에는 truecolor 를 지원하는 터미널이 필요합니다. Apple Terminal 은 제한적이므로 iTerm2 / Ghostty / Alacritty 를 권장합니다.

## Linux 관련 참고

- Ubuntu 22.04+ 에서는 공식 shell installer 로 `uv` 를 설치하세요.
- 헤드리스 서버: TUI 는 실제 TTY 가 필요합니다. SSH 로 접속할 때는 `tmux` 또는 `screen` 을 사용하세요.

## LLM Provider 설정

WorldLines 는 `~/.neonrp/config.json` (전역) 과 `./.neonrp/config.json` (프로젝트 오버라이드) 에서 provider 설정을 읽습니다. 프로젝트 디렉터리에서 `neonrp init` 을 실행하면 템플릿이 생성됩니다.

### 예시 — GLM (ZhipuAI)

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

### 예시 — OpenAI

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

### 예시 — LM Studio (로컬, OpenAI 호환)

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

### 예시 — Ollama (로컬)

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

### 선택 — Embedding 검색

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

embedding 이 활성화되면 `neonrp index build` 가 벡터를 미리 계산하고, 컨텍스트 검색 파이프라인은 하이브리드 (fuzzy + vector) 가 됩니다.

## 환경 변수

| 변수                | 용도                                     |
|---------------------|------------------------------------------|
| `OPENAI_API_KEY`    | OpenAI                                   |
| `GLM_API_KEY`       | Zhipu GLM                                |
| `ANTHROPIC_API_KEY` | Anthropic                                |
| `NEONRP_E2E_LLM`    | 실제 엔드포인트 통합 테스트 활성화       |

프로젝트 루트의 `.env` 는 자동으로 로드됩니다.

## 제거

```bash
uv tool uninstall neonrp
```

프로젝트 데이터 (`.neonrp/` 디렉터리) 는 보존됩니다.

## 다음

- [QUICKSTART.ko.md](QUICKSTART.ko.md) — 첫 플레이 세션
- [templates/stoneford/](templates/stoneford/README.ko.md) — 샘플 월드
