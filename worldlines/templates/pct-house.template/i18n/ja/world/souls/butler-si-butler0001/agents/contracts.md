# Soul Agent Contract — butler

1 soul = 1 agent(M30)。書き込み範囲 = manifest.json の `write_globs`
(soul が変えられるのは自分の context だけ。範囲外への書き込みは apply パイプラインに拒否される)。
prompt 契約:エンジン既定の system.md テンプレート。この soul の
`agents/soul-agent/system.md` で上書きできる。
