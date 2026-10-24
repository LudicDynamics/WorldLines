---
title: "플레이 시작하기"
description: "들어가는 길은 세 가지입니다. 온라인, 로컬 웹, 터미널. 하나를 골라 몇 분 안에 첫 세계로 들어갑니다."
---

<!-- section: paths -->
## 세 가지 길

| 방법 | 설치할 것 | 입구 |
|---|---|---|
| **온라인** | 없음 | [worldlines.gg](https://worldlines.gg) 또는 iOS 앱 |
| **로컬 웹** | `worldlines` | 브라우저에서 http://127.0.0.1:8787/local |
| **터미널** | `worldlines` 또는 `neonrp` | 터미널에서 `neonrp` 입력 |

로컬 웹과 터미널은 같은 세계, 저장, 설정을 읽고 씁니다. 언제든 바꿔 가며 쓸 수 있습니다.

<!-- section: online -->
## 온라인으로 플레이

[worldlines.gg](https://worldlines.gg)를 열고 Hub에서 세계를 하나 골라 브라우저에서 바로 플레이합니다. 휴대폰에서는 iOS 앱을 씁니다. 설치할 것도 없고, 내 모델을 준비할 필요도 없습니다.

<!-- section: install -->
## 로컬 설치

Python 3.10 이상이 필요합니다.

```bash
pip install worldlines        # 또는: uv tool install worldlines / pipx install worldlines
```

`worldlines`를 설치하면 엔진 `neonrp`도 함께 설치되므로 두 명령을 모두 쓸 수 있습니다. 터미널만 쓰려면 `pip install neonrp`.

소스와 릴리스 노트는 GitHub 저장소 [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)에 있습니다. 한 줄 설치 스크립트도 그대로 쓸 수 있습니다(uv가 없으면 함께 설치합니다).

```bash
curl -LsSf https://worldlines.gg/install.sh | sh      # macOS / Linux
irm https://worldlines.gg/install.ps1 | iex           # Windows PowerShell
```

<!-- section: open -->
## 열기

```bash
worldlines        # 로컬 웹: 브라우저에서 http://127.0.0.1:8787/local 을 엽니다
neonrp            # 터미널: 「Welcome to WorldLines」 런처로 들어갑니다
```

- **웹**: 플레이 목록에서 세계를 하나 클릭하고 새 판을 시작합니다. 그 세계에서 저장한 판은 같은 패널에 나열되어 바로 이어서 할 수 있습니다.
- **터미널**: 런처에서 「새 게임 시작」(`n`)을 고르고 세계를 선택합니다. 「⚡ 이어하기」(`r`)는 가장 최근 판으로 바로 들어갑니다. 맨 처음 실행할 때는 인터페이스 언어를 묻습니다.

처음 실행할 때는 모델도 하나 고르게 됩니다. [모델 연결](/docs/players/providers)을 참고하세요. 새 판은 스스로 장면을 열기 때문에 먼저 무언가를 입력할 필요가 없습니다.

<!-- section: update -->
## 자동 업데이트

pip, uv tool, pipx로 설치했다면 `worldlines`와 `neonrp` 모두 실행할 때 새 버전을 확인합니다. 새 버전이 있으면 스스로 업데이트한 뒤 새 버전으로 다시 시작합니다. 이 동작을 바꾸려면 터미널 게임 안에서 입력합니다.

| 명령 | 효과 |
|---|---|
| `/update mode prompt` | 먼저 묻기 |
| `/update mode notify` | 알리기만 하고 업데이트하지 않기 |
| `/update mode auto` | 스스로 업데이트(기본) |
| `/update status` | 현재 버전과 업데이트 설정 보기 |

소스로 설치한 경우(`pip install -e`)에는 알리기만 하고 스스로 업데이트하지 않습니다.

<!-- section: data -->
## 데이터가 있는 곳

| 위치 | 내용 |
|---|---|
| `~/.worldlines/plays/` | 플레이한 모든 판 |
| `~/.worldlines/templates/` | 내 템플릿(복사해서 고친 것, 새로 만든 것) |
| `~/.worldlines/souls/` | 캐릭터 라이브러리 |
| `~/.worldlines/official/` | 로그인 후 내려받은 공식 세계 |
| `~/.neonrp/config.json` | 모델, 키, 언어, 업데이트 방식 |

백업하려면 `~/.worldlines`와 `~/.neonrp/config.json`을 함께 복사하세요.

<!-- section: next -->
## 다음

[모델 연결](/docs/players/providers) → [첫 판](/docs/players/first-world) → [한 턴의 진행](/docs/players/how-to-play)
