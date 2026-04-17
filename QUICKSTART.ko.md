# Quickstart — 30 분 안에 첫 턴까지

**Language:** [English](./QUICKSTART.md) · [简体中文](./QUICKSTART.zh.md) · [日本語](./QUICKSTART.ja.md) · [한국어](./QUICKSTART.ko.md)

> 상태: Beta — 기본 stoneford 스타터 경로를 다룸

이 가이드는 [INSTALL.ko.md](INSTALL.ko.md) 를 마쳤고 `neonrp --help` 가 명령 목록을 출력하는 상태를 전제로 합니다.

## 1. 프로젝트 생성 (2 분)

```bash
mkdir my-world && cd my-world
neonrp init
```

`.neonrp/` 가 생성되며 `manifest.json` 과 `config.json` 템플릿이 들어갑니다. 아직 월드는 없고, 빈 프로젝트입니다.

## 2. stoneford 스타터 스캐폴딩 (3 분)

```bash
neonrp game new --template stoneford
```

이제 구조는 다음과 같습니다:

```
my-world/
├── .neonrp/
│   ├── manifest.json
│   └── config.json
├── agents/
│   ├── orchestrator/
│   ├── town-agent/
│   ├── dungeon-agent/
│   ├── combat-referee/
│   ├── world-builder/
│   └── rules-referee/
└── game/
    ├── meta/
    ├── player/
    ├── towns/
    ├── dungeons/
    ├── rules/
    ├── lore/
    └── world/
```

샘플 월드의 내용은 [templates/stoneford/](templates/stoneford/README.ko.md) 참고.

## 3. Provider 설정 (5 분)

`./.neonrp/config.json` 을 편집하고 [INSTALL.ko.md](INSTALL.ko.md#llm-provider-설정) 의 블록 중 하나를 선택합니다. API 키를 export:

```bash
export GLM_API_KEY=sk-...
# 또는
export OPENAI_API_KEY=sk-...
```

월드 검증:

```bash
neonrp validate
neonrp index build
```

## 4. TUI 실행 (1 분)

```bash
neonrp tui
```

우측 상단 상태 바에 프로젝트명, branch (`main`), head event (`0`), provider 가 표시됩니다.

## 5. 첫 턴 (5 분)

입력 줄에:

```
look around
```

Orchestrator 가 `town-agent` 로 라우팅하고, 해당 agent 가 Stoneford 마을 데이터를 읽어 서술합니다. 다음이 보입니다:

1. **thinking** 스트림 (기본 접힘).
2. **tool use** 표시 — agent 가 파일을 읽음.
3. **narrative** 응답.
4. 새로운 **event** 가 로그에 추가 (head 가 `0 → 1` 로 전진).

## 6. 체크포인트 저장

TUI 에서:

```
/save opening-scene
```

또는 별도 셸에서:

```bash
neonrp save opening-scene
```

## 7. 실험용 브랜치 (5 분)

위험한 선택을 시도 — 예를 들어 Old Reed 에게서 훔치기:

```
/branch try-stealing
steal the coin pouch while Old Reed is turned away
```

WorldLines 는 이를 새 branch 에 기록합니다. main 은 그대로입니다.

## 8. Undo / 되감기

```
/undo
```

head event 가 한 단계 뒤로. `/redo` 로 다시 적용.

## 9. 세이브 로드

```bash
neonrp load opening-scene
```

또는 TUI 를 `--continue` 로 재시작해 이전 세션을 이어갑니다.

## 10. 다음은?

- [CONCEPTS.ko.md](CONCEPTS.ko.md) 를 훑어 events / snapshots / sandboxes 를 이해하세요.
- `/mode build` 를 시도해 agent 에게 Stoneford 에 새 NPC 를 추가하게 하고 **plan → diff → apply** 파이프라인을 관찰하세요.
- `templates/stoneford/README.ko.md` 를 읽고 마을 JSON 을 직접 편집해 보세요.
- 모든 서브커맨드는 [CLI_REFERENCE.ko.md](CLI_REFERENCE.ko.md) 참고.

## 트러블슈팅

| 증상                                 | 해결                                                 |
|--------------------------------------|------------------------------------------------------|
| `neonrp: command not found`          | `uv tool install -e .` 재실행                        |
| TUI 문자가 깨짐                      | iTerm2 / Ghostty / Alacritty 로 전환, UTF-8 설정     |
| `provider not configured`            | `.neonrp/config.json` 과 환경 변수 확인              |
| `validate` 가 schema 오류를 보고     | `neonrp validate --json` 으로 세부 확인              |
| Agent 멈춤 / 빈 출력                 | `neonrp tui --verbose` 로 원시 LLM 트래픽 확인       |
