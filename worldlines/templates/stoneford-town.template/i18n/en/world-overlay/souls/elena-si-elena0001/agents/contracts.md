# Soul Agent Contract — elena

1 soul = 1 agent (M30). The write surface = the `write_globs` in manifest.json
(a soul only edits its own context; out-of-bounds writes are rejected by the apply pipeline).
Prompt contract: the engine defaults to the system.md template, which can be
overridden by this soul's `agents/soul-agent/system.md`.
