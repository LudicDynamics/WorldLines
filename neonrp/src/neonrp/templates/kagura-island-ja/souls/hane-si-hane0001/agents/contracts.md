# Soul Agent Contract — hane

1 soul = 1 agent(M30)。書き込み面 = manifest.json の `write_globs`
(soul は自分の context しか書き換えられない;越境した書き込みは apply パイプラインが拒否する)。
prompt 契約:エンジン既定の system.md テンプレートを、本 soul の
`agents/soul-agent/system.md` で上書きできる。
