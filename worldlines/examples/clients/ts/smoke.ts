// Plays one line against a running host from Node — the same client the page uses.
//   WL_HOST=http://127.0.0.1:8788 WL_TOKEN=<token> npm run smoke -- "我先看看四周"
import { WorldLinesClient, explain, speaker } from './src/client.ts'

const host = process.env.WL_HOST || 'http://127.0.0.1:8788'
const token = process.env.WL_TOKEN || ''
const line = process.argv[2] || 'Look around.'
let prose = '', beats: string[] = [], who = ''
const c = new WorldLinesClient(host, token, {
  onChunk: (raw, beat) => { const s = speaker(raw); if (s.who !== who) { who = s.who; prose += `\n[${who || 'host'}${beat ? ' · ' + beat : ''}] ` } prose += s.text },
  onBeat: ev => { beats.push(ev.kind) },
  onAsk: (_q, options) => options[0] ?? null,
})
try {
  const hello = await c.connect()
  const kinds = await c.beatKinds()
  console.log(`connected · world ${hello.world} · beats: ${Object.keys(kinds.kinds).join(', ') || '(one plain turn)'}`)
  const t0 = Date.now()
  const r = await c.send(line)
  await new Promise(res => setTimeout(res, 300))
  console.log(`turn ${((Date.now() - t0) / 1000).toFixed(1)} s · success ${r.success}${r.error ? ' · ' + r.error : ''}`)
  console.log(`beat events: ${beats.join(' → ') || '(none)'}`)
  console.log(`streamed ${prose.trim().length} chars:${prose.slice(0, 400)}`)
  process.exitCode = r.success && prose.trim() ? 0 : 1
} catch (e) {
  console.error(explain(e)); process.exitCode = 2
} finally { c.close() }
