# Soul Agent Contract — rowan

1 soul = 1 agent(M30)。書き込み面 = manifest.json の `write_globs`
(soul は自分の context だけを変更する。範囲外への書き込みは apply パイプラインで拒否される)。
prompt の契約:エンジン既定の system.md テンプレート。この soul の
`agents/soul-agent/system.md` で上書きできる。
