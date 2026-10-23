---
title: "vs LangGraph, Graflow & other multi-agent frameworks"
description: "WorldLines is a multi-agent framework built specifically for role-play."
---

<!-- section: vs-orchestration -->
## vs orchestration frameworks (LangGraph · Graflow)

**LangGraph** and **Graflow** are *general* toolkits for building stateful, multi-agent workflows — nodes, edges, state channels, checkpointing — that you assemble into whatever your domain needs.

**WorldLines is purpose-built for one thing: role-play.** Its primitives — world-agent, soul-agents, events, snapshots, branches, Plan → Diff → Apply — are a vocabulary for *living, playable worlds*, not a generic graph you design yourself.

<!-- section: vs-simulators -->
## vs multi-agent simulators (Oasis · 灵台 · Mirror Fish)

A wave of multi-agent *simulation* frameworks model different kinds of worlds:

- **Oasis** — simulates **social networks**: large populations of agents posting, following, and influencing one another.
- **灵台 (Lingtai)** · **Mirror Fish** — other multi-agent simulation environments.

WorldLines targets a different domain on purpose: **tabletop-style role-play (跑团)** driven by **multiple Soul Agents**. We're **not** adapting for SNS / social-network simulation. We adapt for settings closer to **real life** or to **fantasy worlds** — a place you step into and play, where each character is its own soul with memory and agency.

<!-- section: when-to-pick-which -->
## When to pick which

- **LangGraph / Graflow** — building a custom agentic workflow (research assistant, support bot, code pipeline); you want maximum flexibility.
- **Oasis / social simulators** — studying network-scale social dynamics.
- **WorldLines** — building or playing a **role-play world**: TRPG, narrative, companions — a living world of soul-agents you can save, branch, and replay.
