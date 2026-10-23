# WorldLines에 기여하기

**언어:** [English](./CONTRIBUTING.md) · [简体中文](./CONTRIBUTING.zh.md) · [日本語](./CONTRIBUTING.ja.md) · [한국어](./CONTRIBUTING.ko.md)

기여를 고민해 주셔서 감사합니다. 버그 리포트, 수정, 월드, 아이디어 모두 환영합니다.

## 이 저장소의 운영 방식

이 저장소는 WorldLines의 공개 릴리스 저장소입니다. 개발은 업스트림(비공개 개발 저장소)에서 이루어지며, 릴리스마다
**릴리스 커밋 하나**(squash한 스냅숏)로 이곳에 반영됩니다. 따라서 세세한 커밋 이력은 여기에 남지 않습니다.
무엇이 바뀌었는지는 릴리스 노트를 확인해 주세요.

## 이슈

- **버그:** neonrp / worldlines 버전, OS, 재현 절차, 기대한 결과와 실제 결과를 적어 주세요. 로그나 스크린숏이 있으면
  더 좋습니다.
- **아이디어:** 기능 제안, 새 팩, 월드나 템플릿 기획도 환영합니다. 이슈를 열어 편하게 이야기해 주세요.

## 풀 리퀘스트

풀 리퀘스트는 이 저장소로 보내 주세요.

1. 채택된 PR은 **먼저 이 저장소에 병합**됩니다. 작성자 정보는 이 공개 이력에 그대로 남습니다.
2. 이후 업스트림으로 옮겨져 다음 릴리스에 포함됩니다.
3. 어느 릴리스에 들어갔는지는 메인테이너가 PR에 남겨 드립니다.

PR 하나에는 주제 하나만 담고, *무엇을* 왜 바꿨는지 적어 주세요. 큰 변경은 코드를 쓰기 전에 이슈에서 범위를 먼저
맞춰 주세요.

### 기여자 라이선스 계약(CLA)

첫 풀 리퀘스트를 병합하기 전에 [기여자 라이선스 계약](./CLA.md)(CLA, 영어 원문이 구속력을 가집니다)에 서명해야 합니다. PR에 봇이 댓글을 남기면, 안내된 문장을 그대로 답글로 달면 서명이 끝납니다. 서명은 한 번만 하면 되고 이후의 모든 기여에 적용됩니다. 저작권은 계속 기여자에게 있습니다. CLA는 저희가 기여 내용을 이 저장소의 라이선스로 공개하고, 이를 바탕으로 한 WorldLines 제품(온라인 서비스와 앱 스토어 앱)에도 쓸 수 있게 해 줍니다.

## 구성과 라이선스

| 폴더 | 내용 | 라이선스 |
|---|---|---|
| `neonrp/` | 엔진(Python) | Apache-2.0 |
| `worldlines/` | 제품: 웹 UI(`worldlines/ui`), 데스크톱 셸, 런처 패키지, 템플릿, 예제 월드 | AGPL-3.0 |
| `documents/` | 사양과 문서 사이트 원문 | CC BY 4.0 |
| `benchmarks/` | 엔진의 설계 결정을 뒷받침하는 테스트 스위트 | 코드 Apache-2.0 · 데이터 CC BY 4.0 |

기여는 변경한 폴더의 라이선스와 [CLA](./CLA.md)에서 부여하는 권리로 받습니다.

## 개발 환경

엔진:

```bash
cd neonrp
uv sync --all-extras --dev
uv run ruff check src tests
uv run pytest -q
```

웹 UI:

```bash
cd worldlines/ui
npm ci
npm run lint
npm run build:local
```

PR을 열기 전에 관련 검사가 모두 통과하는지 확인해 주세요.

## 월드·캐릭터·템플릿 만들기

저장소를 Claude Code나 Codex로 열고, 워크벤치(저장소 루트의 `CLAUDE.md` / `AGENTS.md`)와
[`documents/spec/`](./documents/spec)의 사양을 활용하세요. 제출하기 전에 `neonrp template lint`(템플릿)와
`neonrp validate`(월드)로 검증해 주세요.

## 비밀 정보

비밀 정보는 절대 커밋하지 마세요. API 키는 자신의 컴퓨터에 있는 `~/.neonrp/config.json`에만 두고, 월드, 템플릿,
테스트, 스크린숏에 넣지 마세요.

## 행동 강령과 보안

예의를 지키고, 선의를 전제하며, 사람이 아니라 아이디어를 비판해 주세요. 전체 규정은
[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)를 참고하세요. 취약점은 공개 이슈가 아니라 [SECURITY.md](./SECURITY.md)의
안내에 따라 비공개로 제보해 주세요.

## 연락처

- Issues: https://github.com/LudicDynamics/WorldLines/issues
- Discord: https://discord.gg/HJYWbdqWrE
- Email: `info@worldlines.gg`
