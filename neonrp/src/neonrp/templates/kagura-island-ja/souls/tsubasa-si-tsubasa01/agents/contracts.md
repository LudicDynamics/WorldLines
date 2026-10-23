# Soul Agent Contract — tsubasa

1 soul = 1 agent(M30)。書き込み範囲 = manifest.json の `write_globs`
(soul は自分の context のみ変更する;越境した書き込みは apply パイプラインに拒否される)。
prompt 契約:エンジン既定の system.md テンプレート、本 soul の
`agents/soul-agent/system.md` で上書き可能。
