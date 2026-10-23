# Soul Agent Contract — rowan

1 soul = 1 agent（M30）。書き込み面 = manifest.json の `write_globs`
（soul は自分の context しか変更しない。越境した書き込みは apply パイプラインに拒否される）。
prompt 契約：エンジン既定の system.md テンプレートは、この soul の
`agents/soul-agent/system.md` で上書きできる。
