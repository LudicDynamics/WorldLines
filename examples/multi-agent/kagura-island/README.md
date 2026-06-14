# ⛩ Kagura Island 神楽島 — Multi-Agent World

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> Engine mode: **multi-agent**. Japanese-folk mystery · time loop · Yith mythos. **Seven living souls** on one island — WorldLines' richest multi-agent society. CoC-style checks (not d20 combat).

> **Runs locally** (TUI / CLI) — multi-agent is not on hosted play. `neonrp tui --from examples/multi-agent/kagura-island`

## What makes this multi-agent

`fast` and `orch` modes run a **world-agent + domain agents**; NPCs are data. **multi-agent** adds a `souls/` folder where each soul is an **independent character-agent** with its own mind. Kagura is the showcase: **seven souls** who think, scheme, and remember in parallel, wrapped by the world-agent:

```
world-agent  →  active souls (this turn's actors)  →  world-agent
  (sovereign      each soul: speech / action /          (single world-close
   orchestrator)   inner voice, on its own agenda)        boundary, narrates)
```

`playthrough.json` declares which souls are active each turn. Souls are isolated actors — not a peer mesh, but an **owner-directed actor set** with one world-close boundary. The island remembers; the loop turns; each soul carries its own secrets through it.

```bash
neonrp tui --from examples/multi-agent/kagura-island
```

## The seven souls

| Soul | id |
|---|---|
| **Kagami** 镜子 | `kagami-si-kagami001` |
| **Hane** 羽 | `hane-si-hane0001` |
| **Makoto** 真琴 | `makoto-si-makoto001` |
| **Miyaji** 宫司 | `miyaji-si-miyaji001` |
| **Shiro** 白 | `shiro-si-shiro0001` |
| **Tsubasa** 翼 | `tsubasa-si-tsubasa01` |
| **Yuto** 悠人 | `yuto-si-yuto0001` |

Each soul folder follows the bundle shape: `soul.json` / `soul.md` (identity), `persona/` (traits, values, relationships), `background/` (history, origin, secrets), `character/` (profile, stats, inventory), memory (`long-term-memo/` + `short-term-memo/`), `rules/` (per-soul guardrails), `agents/` (the soul's mind), `trajectory/` (lived history).

## World

`agents/` = world-agent + town / combat / story / world-builder / npc-builder / rules-referee. `game/` holds the island truth (lore, locations, items, timeline; GM truth in `game/lore/gm-truth.md` — world-agent only). `runtime_contract.json` keeps the router shell; the live soul wrapper engages because `playthrough.json + souls/` are present.

> Time loop · sanity · taboo: irreversible consequences, CoC-style. The player is a **human**, never a named soul.

## License

**AGPL-3.0** — fork, mod, ship your own. Engine (`neonrp`) is a proprietary preview.
