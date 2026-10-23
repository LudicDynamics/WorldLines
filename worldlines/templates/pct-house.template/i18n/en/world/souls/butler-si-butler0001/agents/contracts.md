# Soul Agent Contract — butler

1 soul = 1 agent (M30). Write surface = the `write_globs` in manifest.json
(a soul changes only its own context; out-of-bounds writes are rejected by the apply pipeline).
Prompt contract: the engine's default system.md template, which this soul's
`agents/soul-agent/system.md` may override.
