---
title: "SillyTavern Import"
description: "SillyTavern의 world card와 character card를 WorldLines로 import합니다."
---

<!-- section: character-cards -->
## Character card

SillyTavern character card는 JSON 파일 또는 tEXt 메타데이터가 내장된 PNG 이미지로 배포됩니다. 둘 다 지원합니다.

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json --id mira-ashford
```

이 명령은 card를 파싱하여 WorldLines의 `npc/` 스키마에 매핑하고, 엔티티를 `game/npc/<id>.json`에 씁니다.

📸 **스크린샷 추후 추가 예정** — PNG 미리보기가 포함된 import 다이얼로그.

<!-- section: world-cards -->
## World card

SillyTavern world card (lorebook)는 더 풍부합니다 — 지역, 팩션, 월드 설정을 정의합니다. Import:

```bash
neonrp import sillytavern-world world-card.json
```

엔티티는 필요에 따라 `game/lore/`, `game/towns/`, `game/world/`로 분할됩니다.

📸 **스크린샷 추후 추가 예정** — import된 lorebook의 before/after diff 뷰.

<!-- section: caveats -->
## 주의 사항

- 1:1로 매핑되지 않는 SillyTavern 필드는 결과 엔티티의 `_meta.silly_tavern` blob에 담깁니다. 잃는 것은 없지만, 아직 스키마에서 일급 시민은 아닙니다.
- v0.1에서 import는 **단방향**입니다. SillyTavern 포맷으로의 round-trip export는 v0.2에 계획되어 있습니다.
- card가 외부에 호스팅된 이미지를 참조하면 import는 경고를 로그로 남기지만 다운로드하지는 않습니다.
