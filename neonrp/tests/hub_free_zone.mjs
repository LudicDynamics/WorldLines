// tests/test_hub_free_zone.py 用:引擎模式的 Hub(hub/index.html + hub.js),引擎接口用 page.route 假装 ——
// 自由区列表(/api/v1/local/hub/open)进发现页 · 远端作品详情页「下载到本地玩」+「举报」· 我的作品 · iOS(openZone:false)不拉。
//   node tests/hub_free_zone.mjs <page.html> <api.json> <playwright 所在的 package.json> [openZone=0]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, apiFile, pkg, openZone] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8').replace('<script>window.HUB={}</script>', openZone === '0' ? '<script>window.HUB={openZone:false}</script>' : '<script>window.HUB={}</script>')
const api = JSON.parse(readFileSync(apiFile, 'utf-8'))
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh') } catch { /* no storage */ } })
const p = await ctx.newPage()
const errs = [], posts = [], gets = []
p.on('pageerror', e => errs.push(e.message))
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname.startsWith('/api/')) {
    if (r.request().method() === 'POST') { posts.push([u.pathname, JSON.parse(r.request().postData() || '{}')]); const a = api['POST ' + u.pathname]; return r.fulfill({ status: a ? a[0] : 404, contentType: 'application/json', body: JSON.stringify(a ? a[1] : {}) }) }
    gets.push(u.pathname)
    return r.fulfill({ contentType: 'application/json', body: JSON.stringify(api[u.pathname] || {}) })
  }
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
const out = { errs, posts }
await p.goto('http://hub.test/')   // 没带 # 打开:本地版先进自由区
await p.waitForTimeout(300)
out.landing = new URL(p.url()).hash
await p.goto('http://hub.test/#/free/')   // 本地的自由区地址:直达
await p.waitForTimeout(600)
out.openHrefs = await p.$$eval('.cards .wcard', a => a.map(x => x.getAttribute('href')))
out.toggle = await p.$$eval('#ztog a', a => a.map(x => [x.getAttribute('href'), x.className]))
out.openCards = await p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, ''))))
out.zoneBtn = !!(await p.$('[data-zone]'))
await p.goto('http://hub.test/#/')
await p.waitForTimeout(300)
out.defaultCards = await p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, ''))))
if (out.zoneBtn) {
  await p.goto('http://hub.test/#/t/remote-abc123')
  await p.waitForSelector('[data-fzget]')
  out.remote = { ctas: await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim())), tag: await p.textContent('.hero .info .tag'), cover: await p.getAttribute('.hero img.bimg', 'src') }
  await p.click('[data-report]'); await p.fill('#fzWhy', '侵权'); await p.click('[data-report-go]'); await p.waitForTimeout(300)
  out.reportMsg = await p.textContent('#fzMsg').catch(() => null)
  await p.click('[data-close-btn]').catch(() => {})
  await p.click('[data-fzget]'); await p.waitForTimeout(500)
  out.afterFetch = p.url()
  await p.goto('http://hub.test/#/t/mine-local')
  await p.waitForSelector('.hero .note')
  out.localOpen = { note: (await p.textContent('.hero .note')).trim(), report: !!(await p.$('[data-report]')) }
}
await p.goto('http://hub.test/#/me')
await p.waitForSelector('.mebox .wk', { timeout: 5000 }).catch(() => {})
out.works = await p.$$eval('.wk', a => a.map(x => ({ text: x.textContent.replace(/\s+/g, ' ').trim(), chips: [...x.querySelectorAll('.chip')].map(c => c.textContent), unpub: !!x.querySelector('[data-wk-unpub]'), apply: !!x.querySelector('[data-wk-apply]') })))
if (out.works.some(w => w.apply)) { await p.click('[data-wk-apply]'); await p.waitForTimeout(300) }
out.gets = [...new Set(gets)]
await b.close()
console.log(JSON.stringify(out))
