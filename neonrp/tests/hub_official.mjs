// tests/test_hub_official.py 用:本地 Hub(引擎模式)的官方世界(niko 10-17)—— 引擎接口用 page.route 假装。
//   没登录:只有本机的世界 + 「登录后可获取更多官方世界」;登录了:默认区远端世界进发现页(标「官方」),详情页「获取」,
//   已装的官方世界不出复制按钮、有新版出「更新」;内置的(灰橡宅)照旧能复制。
//   node tests/hub_official.mjs <page.html> <api.json> <playwright 所在的 package.json> <lang> [shots dir]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, apiFile, pkg, lang, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const api = JSON.parse(readFileSync(apiFile, 'utf-8'))
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } })
await ctx.addInitScript(l => { try { localStorage.setItem('wl.hub.lang', l) } catch { /* no storage */ } }, lang)
const p = await ctx.newPage()
const errs = [], posts = []
let signed = false
p.on('pageerror', e => errs.push(e.message))
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname.startsWith('/api/')) {
    if (r.request().method() === 'POST') { posts.push([u.pathname, JSON.parse(r.request().postData() || '{}')]); const a = api['POST ' + u.pathname]; return r.fulfill({ status: a ? a[0] : 404, contentType: 'application/json', body: JSON.stringify(a ? a[1] : {}) }) }
    const key = u.pathname === '/api/v1/local/hub/official' ? (signed ? 'official:in' : 'official:out') : u.pathname
    return r.fulfill({ contentType: 'application/json', body: JSON.stringify(api[key] || {}) })
  }
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
const cards = () => p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, ''))))
const out = { errs, posts }
await p.goto('http://hub.test/#/')
await p.waitForSelector('.cards .wcard')
out.out = { cards: await cards(), more: await p.textContent('.ofmore').catch(() => null), moreBtn: !!(await p.$('.ofmore [data-wl-login]')) }
if (shots) await p.screenshot({ path: `${shots}/signed-out-${lang}.png` })
signed = true
await p.goto('http://hub.test/#/?r=1'); await p.reload()
await p.waitForSelector('.cards .wcard')
out.in = { cards: await cards(), more: !!(await p.$('.ofmore')),
  heads: await p.$$eval('.cards .wcard', a => Object.fromEntries(a.map(x => [decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, '')), [...x.querySelectorAll('.head .ver')].map(v => v.textContent.trim())]))) }
if (shots) await p.screenshot({ path: `${shots}/signed-in-${lang}.png` })
const ctas = async id => { await p.goto(`http://hub.test/#/t/${id}`); await p.waitForSelector('.ctas'); return p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim())) }
out.remote = await ctas('guixiang')
if (shots) await p.screenshot({ path: `${shots}/get-${lang}.png` })
await p.click('[data-ofget]'); await p.waitForTimeout(400)
out.afterGet = p.url()
out.cached = await ctas('wuwu')
out.cachedNote = (await p.textContent('.hero .note')).trim()
out.builtin = await ctas('pct-house')
await b.close()
console.log(JSON.stringify(out))
