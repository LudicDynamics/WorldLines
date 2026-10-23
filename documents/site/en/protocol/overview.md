---
title: "Protocol Overview"
description: "Three open protocols — World, Soul, Agent — define what gets published to WorldHub and SoulHub. The contract layer for any rp-core engine."
---

<!-- section: three-protocols -->
## Three protocols, one ecosystem

Everything you publish to WorldLines lives behind one of three open protocols:

- **[World Protocol](/docs/protocol/world)** — the *setting*: regions, NPCs, factions, lore, spatial maps, rules. Distributed via WorldHub.
- **[Soul Protocol](/docs/protocol/soul)** — the *inhabitant*: persona, memory, goals, emotions. Distributed via SoulHub. (Naming: `soul` is preferred; `character` remains as a legacy alias.)
- **[Agent Protocol](/docs/protocol/agent)** — the *decider*: a single LLM unit with explicit read/write globs, a role, and a routing condition. Lives inside a world or soul bundle.

A *runnable session* = one world bundle + one soul bundle (often the player's, plus 0..N NPCs') + the agent sets each ships.

<!-- section: why-protocols -->
## Why a protocol layer at all

Without a contract layer, every editor / engine / hub would invent its own data shape, and Elena-the-soul wouldn't be droppable into Stoneford-the-world. The protocols are the **smallest** set of constraints that lets:

- **Any engine** load any world or soul published anywhere
- **Any editor** validate against the same schema before saving
- **Any hub** index, search, and serve bundles uniformly
- **Any author** ship something today that still loads when v0.2 arrives — `additionalProperties: true` everywhere means future fields don't break old files

The full schemas live at [github.com/LudicDynamics/rp-shared-protocol](https://github.com/LudicDynamics) under Apache 2.0. Forks and alternative engines are encouraged.

<!-- section: design-principles -->
## Design principles

1. **Schema version in every file** — `"schema_version": "0.1.0"` enables migration detection
2. **Minimal required fields** — only `id`, `kind`, `name`, `schema_version` are required for entities
3. **`additionalProperties: true`** — unknown fields are preserved, not stripped (forward-compatible)
4. **Validate at load time** — reject incompatible versions with clear errors
5. **Deny-first permissions** — agent contracts default to DENY ALL; every read/write must be explicit
6. **Folder = bundle = schema** — distribution layout *is* the contract; the zip uploaded to S3 must validate against the matching `*-bundle@0.1.0` schema

<!-- section: versioning -->
## Versioning

Current schema version: **`0.1.0`** — initial draft, expect breaking changes. Each schema has its own `$id`: `ludic://schemas/<domain>/<name>@<version>`. Breaking changes require a new version + migration script. Target: `1.0.0` for production stability.

Bundle / content versions (the `--version` flag at upload time) are **independent** of schema version — they identify a content build, not a schema build. A world can ship many content versions while pinned to the same schema version.
