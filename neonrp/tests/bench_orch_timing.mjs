// 测试台「本轮编排」的时间预算字段(10-19,lead:只放调试页):worldlines/ui/app/real/bench.js 的 benchOrch 在 node vm 里跑,
// 给一拍带 beat.truncated / advance_deferred / calls[].first_ms + trace.timing.llm_calls 的数据,打印 HTML 和 TUI 两种出口
//   node tests/bench_orch_timing.mjs <bench.js>   → stdout: {"html": …, "tui": …, "plain": …}
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const src = readFileSync(process.argv[2], 'utf-8')
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const round = (extra) => ({ i: 3, seq: 2, kind: 'plan', input: '@莲妹', loc: 'T001/hall', ts: '', spans: [], ms: 20100, rounds: 1, advanced_by: null,
  calls: [{ who: 'host', ms: 19800, first_ms: 12300, truncated: true }, { who: 'si-xiulian0001', ms: 6296, first_ms: 2100 }],
  rolled: [], mic: [], checks: [], applied: [], refused: [], created: [], commit: null,
  truncated: true, deferred: 'world:settled',
  timing: { llm_calls: [{ beat: 'plan', first_ms: 12300, ms: 19800, chars: 84, truncated: true, model: 'deepseek-v4' }, { beat: 'resolve', first_ms: 900, ms: 4100, chars: 210 }] }, ...extra })
let R = [round({})]
const ctx = { U: { ptab: 'orch', bout: 'html', bround: null, bcls: null, bq: '' }, st: () => ({ rounds: R, turn: 2 }), esc, nm: x => x, $: () => null,
  BEATS: { label: k => k, kinds: {} }, renderPlay: () => {}, V3: { j: async () => null }, window: {} }
vm.createContext(ctx)
vm.runInContext(src + '\n;globalThis.__orch = benchOrch;', ctx)
const html = ctx.__orch()
ctx.U.bout = 'tui'
const tui = ctx.__orch()
// 一拍没有这些字段(老引擎 / 开源版):不出这几块
R = [round({ truncated: false, deferred: null, calls: [{ who: 'host', ms: 3000 }], timing: null })]
ctx.U.bout = 'html'
const plain = ctx.__orch()
process.stdout.write(JSON.stringify({ html, tui, plain }))
