# Ralph Loop Plan — WorldLines P0/P1 Execution

Working dir: `/Users/yuhanghuang/Workspaces/10.coc-proj/Ludic-Dynamics/Publishment/WorldLines/`

Each item: apply to all 4 language files (`.md`, `.zh.md`, `.ja.md`, `.ko.md`) with matching translations. Use Edit tool per file. No commits. Do not touch NeonRP/.

## Items

### P0-1 — AGPL version fix
- File: `templates/stoneford-worldlines/LICENSE` — replace `AGPL-2.0-only` with `AGPL-3.0-only`; replace link `agpl-2.0.html` with `agpl-3.0.html`.
- Files: `templates/stoneford-worldlines/README.md|zh|ja|ko` — replace any `AGPL-2.0` with `AGPL-3.0` in License section.

### P0-2 — Stoneford parody disclaimer
Add near top (after Language line, before/after Status line) in all 4 stoneford READMEs.

English:
> **Disclaimer:** Stoneford-on-the-Shale is a fan-inspired tribute and parody work. Any resemblance to *A Song of Ice and Fire* by George R.R. Martin or other referenced works is for creative and educational purposes only. All third-party trademarks and characters remain property of their respective owners.

Translate to zh/ja/ko with same meaning, technical terms in English.

### P0-3 — Strategy paragraph in main README
Add to Positioning/About area in all 4 main READMEs.

English:
> **Why proprietary engine + open data?** The WorldLines engine is released as a proprietary preview to preserve orchestration fidelity during rapid iteration. Game data formats, starter worlds (like Stoneford), and integration protocols are open to seed an interoperable AIRP ecosystem.

### P0-4 — License asymmetry in CONTRIBUTING
Add new section "License Asymmetry" in all 4 CONTRIBUTING files:
- WorldLines engine: All rights reserved, proprietary preview
- `templates/stoneford-worldlines/`: AGPL-3.0-only
- Contributions to stoneford-worldlines are licensed under AGPL-3.0
- Contributions do NOT grant any rights to the engine core
- Contributors should ensure they can license their work under AGPL-3.0

### P1-5 — RELEASE_NOTES known limitations
Append two bullets to Known Limitations in all 4 RELEASE_NOTES:
- **Harness strictness**: NeonRP orchestration depends on complete context. Missing entity data may require manual harness tuning.
- **Beta API stability**: Engine core is in rapid iteration. Expect breaking changes in v0.2 and v0.3 as we balance determinism vs flexibility.

### P1-6 — Acknowledgements in CONTRIBUTING
Add "Acknowledgements" section:
- Contributors will be credited in CHANGELOG for each release.
- v0.2 will introduce a Contributor Hall / Community Memory page.
- Full credit system design in progress; early contributors will be grandfathered.

### P1-7 — Create _PUBLISHING_CHECKLIST.md
New file `Publishment/WorldLines/_PUBLISHING_CHECKLIST.md` listing items requiring user confirmation before D-Day:
- Confirm `amber` consents to being publicly acknowledged by that name (or switch to handle).
- Confirm `worldlines-nikoloside` is the handle to use in copyright.
- Confirm `redoctober` is the handle to use in copyright.
- Confirm all 4 language translations were reviewed by someone fluent (esp. ja/ko).
- Verify `neonrp init --template stoneford` actually works on clean install.
- Verify SPDX identifier AGPL-3.0-only is recognized by GitHub license detector.
Keep it short, checklist format with `- [ ]`.

### P1-8 — CC comparison honesty
Add one line to the CC-vs-WorldLines comparison in all 4 main READMEs.

English:
> Note: WorldLines's harness is currently stricter than Claude Code's — it depends on complete context to orchestrate reliably. This is a deliberate tradeoff for higher determinism and easier debugging, not a deficiency.

## Execution rules
- One item per loop iteration.
- Use Edit tool with `replace_all=false`, edit each of 4 language files separately.
- Preserve: Language nav line, Status line, Markdown structure, relative links.
- No emoji. No AI footer. No commits.
- After each item: one-line report "✓ Pn-N done: <summary>".
- After P1-8: stop the loop.
