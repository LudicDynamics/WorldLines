// tests/test_replay_pack.py 用:Hub 的只读回放页 #/replay/<id>(replay 代理 10-18)。
//   node tests/hub_replay.mjs <page.html> <doc.json> <playwright 所在的 package.json> <local|online>
// local = 引擎模式,GET /api/v1/local/replays/<id> 给文档;点「分享到平台」→ 假装没登录(401)
// online = 线上静态模式,storage 公开下载地址 → timeline.json
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, docFile, pkg, mode] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const doc = JSON.parse(readFileSync(docFile, 'utf-8'))
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'en') } catch { /* no storage */ } })
const p = await ctx.newPage()
const errs = [], shares = []
p.on('pageerror', e => errs.push(e.message))
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host === 'storage.test') {
    if (u.pathname === '/v1/public/objects/hub/replay/r-pub/download-url') return json(r, { files: [{ path: 'timeline.json', url: 'http://storage.test/obj/timeline.json' }] })
    if (u.pathname === '/obj/timeline.json') return json(r, doc)
    return r.fulfill({ status: 404, body: '' })
  }
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname === '/catalog.json') return json(r, { templates: [] })
  if (mode === 'local') {
    if (u.pathname === '/api/v1/local/templates') return json(r, { templates: [] })
    if (u.pathname === '/api/v1/local/replays/r1') return json(r, { ...doc, id: 'r1', local: { id: 'r1', shared: null, cover_url: null } })
    if (u.pathname === '/api/v1/local/replays/r1/share') { shares.push(r.request().postData()); return json(r, { error: 'not_signed_in', message: 'sign in' }, 401) }
    if (u.pathname === '/api/v1/local/replays') return json(r, { replays: [] })
    if (u.pathname.startsWith('/api/')) return json(r, {})
  } else if (u.pathname.startsWith('/api/')) return r.fulfill({ status: 404, body: '' })
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
await p.goto(`http://hub.test/#/replay/${mode === 'local' ? 'r1' : 'r-pub'}`)
await p.waitForSelector('.rplog .rpt', { timeout: 60000 })
const out = {
  sections: await p.$$eval('.rplog .rpt', a => a.length),
  tags: await p.$$eval('.rplog .rpt > .tag', a => a.map(x => x.textContent)),
  you: await p.$$eval('.rpl.you p', a => a.map(x => x.textContent)),
  dice: await p.$$eval('.rpd', a => a.map(x => x.textContent.trim())),
  text: await p.textContent('#app'),
  share: !!(await p.$('[data-rp-share]')),
  copy: await p.$$eval('[data-copy]', a => a.map(x => x.dataset.copy)),
  play: await p.$$eval('.ctas a.btn.p', a => a.map(x => x.getAttribute('href'))),
}
if (mode === 'local') {
  await p.click('[data-rp-share]')
  await p.waitForSelector('.toast')
  out.toast = await p.textContent('.toast')
  out.shares = shares
}
out.errs = errs
console.log(JSON.stringify(out))
await b.close()
