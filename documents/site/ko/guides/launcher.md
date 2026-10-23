---
title: "WorldLines 런처"
description: "더블클릭 런처 가이드 — 세션을 시작하는 가장 친절한 방법."
---

<!-- section: intro -->
## 런처가 하는 일

런처는 더블클릭하여 WorldLines를 시작하는 자체 완결형 파일입니다. 첫 실행에 터미널이 필요하지 않습니다.

세 가지 종류가 있습니다.

- `WorldLines.command` (macOS)
- `WorldLines.bat` (Windows)
- `WorldLines.sh` (Linux — 먼저 `chmod +x` 실행)

[worldlines.gg](https://worldlines.gg) → **Quick Install**에서 다운로드하세요.

<!-- section: screenshots -->
## 사용 흐름

📸 **스크린샷 추후 추가 예정** — 이 페이지는 자리 표시자입니다. 사용 흐름에서는 다음을 보여줄 예정입니다.

1. Finder / Explorer / Files에서 파일 실행
2. 첫 실행 부트스트랩 (Python 감지 + 필요 시 설치)
3. Provider 선택 (GLM / OpenAI / LM Studio / Ollama)
4. 첫 월드 선택 (기본값은 Stoneford)
5. TUI가 자동으로 열림

스크린샷은 macOS / Windows / Linux에서 캡처되고 있으며 곧 이곳에 추가될 예정입니다.

<!-- section: troubleshooting -->
## 자주 발생하는 문제

- **macOS "확인되지 않은 개발자"** — 더블클릭 대신 처음에는 우클릭 → 열기로 실행하세요.
- **Windows SmartScreen** — "추가 정보" → "실행"을 클릭하세요. v0.1 스크립트는 서명되어 있지 않습니다.
- **Linux 권한 거부** — 한 번 `chmod +x WorldLines.sh`를 실행한 뒤 `./WorldLines.sh`로 실행합니다.
- **Python을 찾을 수 없음** — 런처가 `uv`로 3.12를 자동 설치합니다. `uv` 설치가 실패하면 수동으로 설치하세요: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
