# 🌿 Stoneford · Elena — Multi-Agent World

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> Engine mode: **multi-agent**. The Stoneford world, now inhabited by living souls — **Elena** and **Rowan** — who think, remember, and act on their own.

> **Play it (recommended):** open the **WorldLines Launcher** → **New game** → pick **Stoneford · Elena** → choose your characters → **Browser · Web** — and watch every soul live in your browser. From the CLI: `neonrp web --project examples/multi-agent/stoneford-elena`. **Multi-agent plays best in the browser (`neonrp web`), not the TUI.** Elena also has a hosted soul-talk demo: **[Talk to Elena →](https://hub.worldlines.gg/play/souls/elena)**

<p align="center">
  <img src="./assets/web-play.png" alt="Stoneford · Elena — multi-agent web play" width="860" />
</p>
<p align="center"><em>Browser play (<code>neonrp web</code>) — the world-agent narrates, Elena and Rowan each perceive, move, and act on their own, and the agent map shows who's where.</em></p>

## What makes this multi-agent

`fast` and `orch` modes run a **world-agent + domain agents** (town, dungeon, combat). NPCs are data the orchestrator voices.

**multi-agent** adds a `souls/` folder. Each soul is an **independent character-agent** with its own persona, memory, secrets, and goals — they think for themselves. The runtime engages the soul wrapper:

```
world-agent  →  active souls (Elena, Rowan)  →  world-agent
  (sovereign     each soul decides its own       (closes the turn,
   orchestrator)  speech / action / inner voice)   narrates to you)
```

Souls are isolated actors — they don't share folders or own world state. Elena remembers what you said three sessions ago; Rowan pursues his own agenda whether you're there or not. This is the **village / society** model in practice.

```bash
neonrp web --project examples/multi-agent/stoneford-elena
```

## The souls

| Soul | Who |
|---|---|
| **Elena** (`elena-si-elena0001`) | the healer who remembers — warm, perceptive, carries her own past |
| **Rowan** (`rowan-si-rowan0001`) | his own motives, his own timeline |

Each soul folder follows the bundle shape: `soul.json` / `soul.md` (identity), `persona/` (traits, values, relationships), `background/` (history, origin, secrets), `character/` (profile, stats, inventory), `long-term-memo/` + `short-term-memo/` (memory), `rules/` (per-soul guardrails), `agents/` (the soul's 6-agent mind), `trajectory/` (what it has lived).

## World

Built on the Stoneford orch world (`agents/` = world-agent + town / dungeon / combat / story / world-builder / rules / clock / evolution / character agents), `game/` holds the world truth. The souls live on top of it.

## License

**AGPL-3.0** — fork, mod, ship your own. Engine (`neonrp`) is a proprietary preview.
