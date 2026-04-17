# 릴리스 노트

**Language:** [English](./RELEASE_NOTES.md) · [简体中文](./RELEASE_NOTES.zh.md) · [日本語](./RELEASE_NOTES.ja.md) · [한국어](./RELEASE_NOTES.ko.md)

> 상태: Beta — v0.1.0 공개 프리뷰

## v0.1.0 — 2026-04-17 (D-Day)

**WorldLines** (엔진 코드네임 `neonrp`) 의 첫 공개 프리뷰.

### 포함 내용

**엔진 코어**
- Event-sourced 상태: append-only 로그 + snapshots
- Branch / undo / redo
- Sandbox 생성, 전환, 폐기
- 결정성 검증용 replay verification
- Schema 검증 (`game_entity.schema.json`)
- 엔티티 인덱스 (fuzzy + 선택적 embedding 하이브리드 검색)

**Agents 와 harness**
- Plan → Diff → Apply 파이프라인
- trigger / tag / priority 라우팅 dispatcher
- 다중 턴 agentic 루프 (`--agentic`)
- 엔진 동봉 빌트인 skills
- `task()` 를 통한 orchestrator 주도 멀티 agent 협업

**LLM provider**
- OpenAI 호환 (OpenAI, GLM, LM Studio, Ollama)
- 테스트용 fixture 포함 stub provider

**TUI (M9+)**
- Claude-Code 스타일 대화형 레이아웃
- `build` / `sandbox` / `play` 모드
- Tab 자동완성이 있는 슬래시 명령
- 세션 관리 (`/continue`, `/new`, `/sessions`)
- 실시간 token 카운터, 스트리밍 transcript, thinking 채널

**Import**
- SillyTavern 캐릭터 카드 (JSON + PNG tEXt)

**템플릿**
- `default` — 최소 스타터
- `isekai` — 일본식 이세계 스케치
- `kagura-island` — 미스터리 드라마
- `tokyo-science-university` — 현대 일상
- `dark-train` — 슬립스트림 단편
- **`stoneford`** — 대표 샘플: 5 도시, 28+3 퀘스트, 6 agents, d20 전투 규칙 ([templates/stoneford/](templates/stoneford/README.ko.md) 참고)

### 알려진 제한

- Python 3.11+ 전용. Windows 는 공식 지원 아님 (WSL2 사용).
- Embedding 검색에는 로컬 OpenAI 호환 embedding 서버가 필요.
- 대규모 월드 (>2k 엔티티) 는 아직 성능 최적화 미완료.
- 웹 UI 없음 — v0.1 은 터미널 전용.
- `replay verify` 는 엄격함: 캐시된 fixture 없이 LLM 비결정성이 있으면 불일치로 표시됨. temperature=0 또는 fixture 를 사용.
- 멀티플레이어 / 공유 branch 미지원. 단일 저자 워크플로우만.
- Stoneford 스타터는 영어 / CJK 혼재, 현지화 파이프라인은 프리뷰 수준.
- 엔진 라이선스 조항은 **프리뷰 / 미정**. [LICENSE](LICENSE) 참고.
- **Harness strictness (harness 엄격성)**: NeonRP orchestration 은 완전한 컨텍스트에 의존합니다. 엔티티 데이터가 누락되면 수동 harness 튜닝이 필요할 수 있습니다.
- **Beta API 안정성**: 엔진 코어는 빠르게 반복되고 있습니다. 결정성과 유연성의 균형을 맞추는 과정에서 v0.2 및 v0.3 에서 호환성 파괴 변경이 예상됩니다.

### 로드맵 — 다음 마일스톤

**v0.2 (2026 Q2 후반)**
- 공개 데이터 포맷 사양 ("WorldLines Data" 표준)
- agent 별 policy 언어 (ops 에 대한 강제 제약)
- 그래프 기반 NPC 기억
- 웹 컴패니언 뷰어 (읽기 전용)

**v0.3**
- 다중 branch 차이 / 병합 도구
- 공유 월드 협업 sandbox
- 퍼스트 클래스 Anthropic provider
- 더 풍부한 combat referee DSL

**v1.0**
- 안정적인 엔진 API
- 공개 데이터 포맷 1.0
- 커뮤니티 템플릿 마켓플레이스

전략적 서사는 [task-thinking/gotomarket-releases-open-source-rethink-0326.md](../../task-thinking/gotomarket-releases-open-source-rethink-0326.md) 참고.

### 감사의 말

도쿄에서 Ludic Dynamics 창립자가 단독 개발. 전신 `llm-rpg-starter` 의 초기 테스터들께 감사.

---

*버그 리포트와 기능 요청은 공개 저장소 issue 에 (링크는 D-Day 공개 예정).*
