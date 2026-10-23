# ソウルエージェント契約 — makoto

1 ソウル = 1 エージェント(M30)。書き込み範囲 = manifest.json の `write_globs`
(ソウルは自分の context しか書き換えられず、範囲外への書き込みは apply パイプラインが拒否する)。
prompt 契約:エンジン既定の system.md テンプレートは、
本ソウルの `agents/soul-agent/system.md` で上書きできる。
