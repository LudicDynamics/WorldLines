# Soul Agent Contract — kagami

1 soul = 1 agent(M30)。写面 = manifest.json 的 `write_globs`
(soul 只改自己的 context;越界写入被 apply 管线拒绝)。
prompt 契约:引擎默认 system.md 模板,可被本 soul 的
`agents/soul-agent/system.md` 覆盖。
