# Soul Agent Contract — miyaji

1 soul = 1 agent（M30）。書き込み面 = manifest.json の `write_globs`
（soul は自らの context のみを改める；越境した書き込みは apply パイプラインが拒む）。
prompt 契約：エンジン既定の system.md テンプレートは、この soul の
`agents/soul-agent/system.md` によって上書きできる。
