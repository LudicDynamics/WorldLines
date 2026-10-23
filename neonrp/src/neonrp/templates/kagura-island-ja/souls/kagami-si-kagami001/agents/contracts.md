# Soul Agent Contract — kagami

1 soul = 1 agent（M30）。書き込み範囲 = manifest.json の `write_globs`
（soul は自分の context しか書き換えられない；範囲外への書き込みは apply パイプラインが拒否する）。
prompt 契約：エンジン既定の system.md テンプレート。本 soul の
`agents/soul-agent/system.md` で上書きできる。
