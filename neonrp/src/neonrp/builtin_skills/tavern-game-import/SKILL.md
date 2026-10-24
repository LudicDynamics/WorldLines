---
name: tavern-game-import
description: Convert a SillyTavern/酒馆 character card, world card, lorebook-heavy PNG/JSON, or imported raw card payload into a playable NeonRP project slice. Use when the user wants more than a single character import: full setting conversion, starter game scaffolding, entity decomposition, quest/location/NPC extraction, or build-mode transformation of tavern content into `game/` entities.
---

# Tavern Game Import

Convert tavern content into a playable NeonRP slice with the current engine.

# Core Rule

- Treat this as project authoring, not engine work.
- Prefer the nearest layer:
  - Imported raw content / source card
  - Project entities under `game/`
  - Existing agents / startup files
- Do not modify core engine unless the source content proves a cross-project engine defect.

# What "Playable" Means In NeonRP

Create the minimum coherent game state that NeonRP can actually run:

- A valid startup entry at `game/meta/game-start.json`
- A valid routing state at `game/meta/active-agent.json`
- A player entity at `game/player/player.json`
- At least one starting domain entity:
  - usually `town/<id>.json` or `location/<id>.json`
- Supporting content connected to that start:
  - 2-5 NPCs
  - 1-3 locations
  - 1 starter quest or explicit goal
  - optional items / dungeon / faction entities when source material supports them

Do not try to exhaustively convert every lore fragment in one pass unless the user asks for a full conversion.

# Required Workflow

1. Read the project contract first.
2. Read startup and routing files.
3. Read schema/rules before writing entities.
4. Read the imported tavern source.
5. Extract world structure.
6. Ask the user about ambiguous design choices.
7. Write a minimal playable slice first.
8. Ensure the play scaffold exists.
9. Validate the slice for path/id/kind consistency.

# 1) Read Project Contract First

- Read `.neonrp/runtime_contract.json` if present.
- Read `.neonrp/config.json`.
- Respect the active data dir from the runtime contract; default to `game/`.
- Read the current startup file path and routing state path from the contract when present.

# 2) Read Startup And Routing Files

- Read `game/meta/game-start.json` if it exists.
- Read `game/meta/active-agent.json` if it exists.
- Preserve router-owned behavior:
  - `active-agent.json` must remain a valid entity and a valid routing-state file.
- Valid active-agent state uses a top-level `active_agent` field.
- Do not invent a new startup flow if the project already has one; extend the existing flow.

# 3) Read Schema And Rules Before Writing

- Load `entity-authoring` first when available.
- Read `rules/game_entity.schema.json` if present.
- If project rules/config specify a domain rules profile, read that too.
- Keep every entity aligned:
  - folder kind
  - filename id
  - JSON `kind`
  - JSON `id`

# 4) Read The Tavern Source

Read the actual source artifact before planning:

- If the user provides a PNG/JSON card path, read the imported NeonRP entity created from it if available.
- Prefer the imported raw payload under `meta.raw` as the canonical source.
- If there is no imported entity yet, call `import_sillytavern_card(path, entity_id?, target_path?, name?)` first.
- Do not use `read_file` directly on Tavern PNG cards; they are binary files and must go through the import tool.
- After importing, treat the generated `game/character/*.json` entity and its `meta.raw` payload as the canonical source.
- If you already know the desired destination, pass `target_path` so the card lands in the right directory first.
- If you need to preserve or adjust the visible Chinese display name, pass `name`.

Extract these source buckets:

- Premise / genre / setting frame
- Player role
- Main scenario / opening scene
- Important NPCs
- Important locations
- Factions / sects / organizations
- Progression structure
- Explicit mechanics or constraints
- Lorebook / character_book entries

# 5) Classify The Source Before Converting

Decide which of these cases you are handling:

- Single-character card:
  - keep it as `character/` only unless the user asks for world expansion
- Character card with embedded world premise:
  - convert the setting into a starter slice around that character
- Full world card / lorebook-heavy package:
  - build a world-first slice, then place the imported character(s) inside it
- "Complete game" request:
  - create a starter playable loop, not a giant encyclopedia dump

# 6) Map Tavern Content To NeonRP Entities

Use this default mapping:

- Protagonist / player surrogate -> `game/player/profile.json`
- Main imported persona(s) -> a soul folder under `souls/` (see the soul spec);
  minor people -> the town's `game/towns/<T>/npcs.json` or `game/npc/*.json`
- Hubs / cities / sect bases -> a place folder `game/locations/<T>/location.json`
  (its spots as sub-folders `game/locations/<T>/<spot>/location.json`) plus
  `game/towns/<T>/town.json`
- Dangerous explorable areas -> `game/dungeons/<D>/` or a place folder
- Lore-only directives / opening instructions / quest briefs -> `game/meta/*.json`
  (the opening goes in `game/meta/game-start.json`)
- Gear / pills / artifacts / manuals -> `game/item/**/<id>.json`

Prefer existing kinds already used by the project before inventing new kinds.

Secrets partition: tavern cards routinely mix the mystery's answer into the
same description as the public face (a character's true identity, a hidden
room, "what really happened"). Do NOT copy that into the entity file. Write
the public description in the entity, and move every spoiler into a
`game/secrets/<kind>--<id>.json` overlay:

```jsonc
{
  "id": "secret-npc--sensei",
  "kind": "secret",
  "about": "npc/sensei",
  "audience": ["gm", "npc:sensei"],       // the character knows their own secret
  "content": { "summary_hidden": "他其实是十二年前失踪的家主。" },
  "revealed_when": [ { "judgment": "玩家出示旧照片当面对质" } ]
}
```

`*_hidden` fields merge back into the host entity when the engine reveals the
secret (ledger: `game/meta/secret_ledger.json`). Hidden passages go in
`connections_hidden` so unrevealed routes do not exist on the map. Card
"world info / lorebook" entries that are answers rather than ambience belong
here too.

# 7) Localize Player-Facing Text, Normalize IDs

- Translate every player-facing field into the project's narrative language —
  see "Target Language" below. Do not copy the card's original language verbatim.
- Do not rely on raw non-ASCII entity IDs unless the project schema explicitly allows them.
- Use stable ASCII ids for filenames and references.
- If the source title is non-ASCII and no explicit id is provided, derive an ASCII id by one of:
  - established project naming
  - pinyin / romaji / hangul→latin transliteration if available and reliable
  - short semantic English slug
  - deterministic fallback with a short suffix

The ASCII id is independent of the display name — set the visible `name` in
the project's narrative language regardless of what the id looks like.

# Target Language

- The import handoff names the **target language** (the player's UI locale:
  zh / ja / ko / en). When it does, that overrides any "keep the source
  language" habit below.
- The source card may be written in any language (often English or Chinese).
  TRANSLATE every player-facing field you write into the slice into the target
  language: `name`, `summary`, `description`, persona / personality, `scenario`,
  first message / opening scene, example dialogue, lore, quest text, location
  and NPC prose, and `ask_user` options.
- Keep `id` and other reference keys ASCII.
- Proper nouns (character names, place names, sect/faction names) may stay in
  their original form when that reads naturally in the target language; render
  them in the target language otherwise.
- Preserve the untouched original card payload in `meta.raw` so nothing is lost
  — translation applies only to the authored, player-facing slice.
- If the handoff does not specify a target language, fall back to the project's
  existing narrative language (the language already used in `game/` entities).

# 8) Build A Minimal Playable Slice First

When the user says "import as a full game", do this first-pass target:

- `game/meta/game-start.json`
  - explain how play begins
  - point to required initial reads if the project uses them
- `game/meta/active-agent.json`
  - valid entity shape plus routing state
- `game/player/player.json`
  - define the player role in this setting
- one starting hub
- one adjacent explorable area or pressure source
- 2-5 important NPCs
- one explicit starter objective

Only after this first slice is coherent should you expand with extra factions, regions, or long lore chains.

# 9) Ensure The Play Scaffold Exists

Before claiming the project is playable:

- Call `ensure_playable_scaffold(template_name?, active_agent?, force?)`.
- Let that tool copy the packaged play agents and runtime scaffold when missing.
- Let that tool rewrite `game/meta/active-agent.json` with the canonical state protocol.
- Do not hand-write `agents/narrator/agent.json`, `agents/town-agent/agent.json`, `agents/dungeon-agent/agent.json`, or a custom routing blob unless the user explicitly asks for custom agents.

A world is only playable when its controller agent is wired correctly. The
runtime expects a conventional router agent on disk. To make the slice play
without an "Agent 'world-agent' not found" error, author the controller as:

- `agents/world-agent/agent.json` with `"id": "world-agent"` and
  `"system_prompt": "system.md"`, plus the system prompt at
  `agents/world-agent/system.md`.
- `.neonrp/runtime_contract.json` whose `router.agent_id` is `world-agent` and
  `router.execution_mode` is `"orchestrator"`.
- `game/meta/game-start.json` with a TOP-LEVEL
  `"agent_routing": { "entry_agent": "world-agent", "router_type": "sticky" }`.

If `ensure_playable_scaffold` already produced a conventional router
(`narrator` / `orchestrator` / `world-agent`) and a runtime contract pointing
at it, honour that instead of adding a second router.

# 10) Ask User On These Ambiguities

You must ask instead of guessing when the source does not make these clear:

- Is the tavern card meant to become:
  - a single NPC
  - the player role
  - the whole campaign world
- Should the imported persona be:
  - `player`
  - `character`
  - `npc`
- What is the intended starting location?
- Is the tone sandbox / narrative / combat-heavy / social?
- Should the conversion target:
  - minimal playable slice
  - broad first-region scaffold
  - near-complete world codex

# 11) Avoid Common Conversion Mistakes

- Do not dump the entire tavern description into one giant `summary`.
- Do not create dozens of disconnected entities with no startup path.
- Do not leave implicit relationships unresolved.
- Do not store core world facts only inside one character file if they should drive gameplay.
- Do not overwrite valid project bootstrap files blindly; merge or extend them.
- Do not touch core engine files for source-specific lore mapping.
- Do not invent `routing.current_agent` or other ad-hoc state shapes inside `active-agent.json`.

# 12) Quality Bar For Converted Output

Before finishing, ensure:

- Startup path is readable and actionable.
- Player spawn and current situation are explicit.
- At least one meaningful next action exists.
- Referenced IDs actually exist.
- Required play agents and runtime contract exist.
- `active-agent.json` remains schema-valid.
- Player-facing text is in the target language (the player's UI locale), even
  though ids stay ASCII.
- The imported raw tavern payload remains preserved somewhere authoritative.

# 13) Recommended Build-Mode Execution Pattern

1. Read runtime contract, startup, routing state, schema, and relevant existing entities.
2. Read the imported tavern source entity/raw payload.
3. Write a short conversion plan in plain language for the user when scope is large.
4. Ask the user about unresolved role/start/scope ambiguities.
5. Create or update the minimal playable slice under `game/`.
6. Call `ensure_playable_scaffold(...)`.
7. Re-read touched files if needed and tighten cross-references.
8. End with a concise summary of:
   - what became playable now
   - what remains as optional follow-up expansion

# 14) 计划-分批协议(Planned Batched Conversion)

大卡一回合转不完;一次性转换被打断后也没有任何进度记录。本协议把转换
拆成**持久化计划 + 顺序批次**,可中断、可恢复。它是**显式路径**:用户在
工坊选「制定转换计划」、明说要分批、或开场指令要求本协议时才启用 ——
不要因为卡大就擅自切换(卡大只是向用户**推荐**本协议的理由)。

前置:源卡必须已持久化在 `game/import/source.<ext>`(引擎在进工坊时已
**原样**拷入,不改格式;如果只拿到外部路径,先把内容原样写到该位置再开始)。
世界卡不一定是 ZIP —— 三种形态都会出现,读法各异,**不要假设 zip**:
- `png-card`:tavern 式 PNG,JSON 内嵌在图片元数据 —— 用现有导入路径提取
  (`import_sillytavern_card(path)` / 引擎的 PNG 读卡),不要当图片读;
- `json-card`:裸 JSON 卡 / lorebook —— 直接 `read_file`;
- `zip`:世界包 —— 逐文件读包内内容再分类;
- `lore-text`(.txt/.md):纯文本设定 —— 按 lore 拆解。

## 计划文件 `game/import/plan.json`(schema v1,机器可校验)

```json
{
  "version": 1,
  "source": "game/import/source.json",
  "source_format": "json-card",
  "source_name": "原卡显示名",
  "target_language": "zh",
  "batches": [
    { "id": "b1", "kind": "scaffold",  "title": "最小可玩切片",
      "items": ["game-start", "world", "首个地点", "首个NPC"],
      "status": "pending", "files_written": [] },
    { "id": "b2", "kind": "locations", "title": "其余地点",
      "items": ["…"], "status": "pending", "files_written": [] }
  ],
  "notes": "自由备注(可选)"
}
```

分批纪律:
- 批次顺序固定:骨架(最小可玩切片)→ 地点 → 角色/NPC → lore → 任务/钩子。
  **首批必须让世界可开局**(含 `ensure_playable_scaffold`),后续批次只做加厚。
- 每批 ≤8 个条目,以"一个回合内舒服完成"为准;条目名写进 `items`。
- 秘密分区规则(§6)对每一批同样生效:该进 `game/secrets/` 的内容随批落位。

## 执行纪律(每回合一批)

1. 执行当前第一个 `pending` 批次,把写过的文件路径记入该批 `files_written`。
2. 批次完成后**先更新 plan.json**(`status: "done"`),再向用户汇报:
   `批次 k/M 完成:<一句话>。回复「继续」执行下一批(<下一批 title>)。`
3. 然后**停下**等用户;不要在同一回合连吃多批(除非用户明说"一口气做完")。
4. 批次必须幂等:重跑只覆盖自己 `files_written` 里的文件,绝不重复造实体。

## 恢复规则

- 开场发现 `game/import/plan.json` 存在且有 `pending` 批次:**不要重新规划**,
  报一行进度(`k/M 批已完成`),直接从第一个 pending 批次继续。
- 用户此时要求"从头一次性转换"(工坊路径②):警告存在进行中的计划,
  须用户明确确认放弃(删除 plan.json)后才可改走一次性路径。
- 全部批次 done:汇报完成,收尾同 §13 第 8 步。

# Suggested Prompt Patterns

These user requests should trigger this skill:

- "把这个酒馆卡直接转成完整游戏"
- "不要只导入角色，帮我转成 NeonRP 可玩的世界"
- "根据这个 tavern PNG 生成开局、地图、NPC 和任务"
- "把 lorebook-heavy 酒馆设定拆成我们系统的实体"
- "在 build 模式下把这张卡转换成 starter game"
- "制定转换计划,分批导入这张卡"(→ §14 计划-分批协议)
- "继续执行导入计划" / "继续导入"(→ §14 恢复规则)
