// tests/test_hub_free_zone.py 用:线上(静态)Hub 的两个地址 —— / = 默认区,/free/ = 自由区(同一份页面 + <base href="../">,build_static 出)。
// 平台(identity 公开列表 · storage 公开下载地址)和 catalog.json 都是假的。
//   node tests/hub_free_web.mjs <hub/index.html> <hub/hub.js> <api.json> <playwright 所在的 package.json> [ios]
// 按区选模型(niko 10-26):默认区的「在浏览器里玩」弹窗没有自己的 key;自由区详情主按钮 = 下载到本地玩,次按钮 = 在浏览器里玩(弹窗里额度默认 + 自己的 key)。
//   HUB_SHOTS=<目录>:顺手截这几屏
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { join } from 'path'

const [htmlF, jsF, apiFile, pkg, ios] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const api = JSON.parse(readFileSync(apiFile, 'utf-8'))
const cfg = { mode: 'static', catalog: 'catalog.json', auth: 'https://auth.test', storage: 'https://storage.test', play: 'play/', ...(ios ? { openZone: false } : {}) }
const page = readFileSync(htmlF, 'utf-8').replace('<!--SCRIPT-->', () => `<script>window.HUB=${JSON.stringify(cfg)}</script><script>${readFileSync(jsF, 'utf-8')}</script>`)
const free = page.replace('<head>', '<head>\n<base href="../">')
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh') } catch { /* no storage */ } })
const p = await ctx.newPage()
const errs = [], seen = []
p.on('pageerror', e => errs.push(e.message))
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  const json = o => r.fulfill({ contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(o) })
  if (u.host === 'auth.test' || u.host === 'storage.test') { seen.push(u.pathname + u.search); return json(api[u.pathname] || {}) }
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname === '/catalog.json') return json(api['/catalog.json'])
  if (u.pathname === '/free/' || u.pathname === '/free/index.html') return r.fulfill({ contentType: 'text/html', body: free })
  if (u.pathname === '/') return r.fulfill({ contentType: 'text/html', body: page })
  return r.fulfill({ status: 404, body: '' })
})
const ids = () => p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, ''))))
const out = { errs, seen }
const shot = async name => { if (process.env.HUB_SHOTS) await p.screenshot({ path: join(process.env.HUB_SHOTS, `${name}.png`) }) }
const sheet = () => p.$eval('#modal .sheet', el => ({ text: el.innerText, links: [...el.querySelectorAll('a.btn, button.btn:not(.prov)')].map(a => [a.textContent.trim(), a.getAttribute('href') || '', a.className]) }))
await p.goto('http://hub.test/#/')
await p.waitForSelector('.cards .wcard')
await p.waitForTimeout(300)
out.root = { cards: await ids(), toggle: await p.$$eval('#ztog a', a => a.map(x => [x.textContent, x.getAttribute('href'), x.className])) }
await p.goto('http://hub.test/#/t/official')
await p.waitForSelector('.ctas')
out.officialCtas = await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim()))
if (await p.$('[data-web="official"]')) {
  await p.click('[data-web="official"]')
  await p.waitForSelector('#modal .sheet')
  out.officialSheet = await sheet()
  await shot('hub-default-web-sheet')
  await p.click('#modal [data-close-btn]')
}
if (!ios) {
  await p.goto('http://hub.test/#/')
  await p.waitForSelector('#ztog a')
  await Promise.all([p.waitForURL(/\/free\//), p.click('#ztog a:not(.on)')])
  await p.waitForSelector('.cards .wcard')
  await p.waitForTimeout(300)
  out.free = { url: p.url(), cards: await ids(), hrefs: await p.$$eval('.cards .wcard', a => a.map(x => x.getAttribute('href'))), toggleOn: await p.$eval('#ztog a.on', x => x.textContent) }
  await p.goto('http://hub.test/free/#/t/w-free-abc123')   // 直达:分享的自由区详情链接
  await p.waitForSelector('.ctas')
  out.freeDetail = { url: p.url(), ctas: await p.$$eval('.ctas > *', a => a.map(x => [x.textContent.trim(), x.getAttribute('href'), x.className])), cover: await p.getAttribute('.hero img.bimg', 'src') }
  await shot('hub-free-detail')
  await p.click('[data-fzlocal]')
  await p.waitForSelector('#modal .sheet')
  out.freeLocalSheet = await sheet()
  await shot('hub-free-local-sheet')
  await p.click('#modal [data-close-btn]')
  await p.click('.ctas [data-web]')
  await p.waitForSelector('#modal .sheet')
  out.freeWebSheet = await sheet()
  await shot('hub-free-web-sheet')
  await p.click('#modal [data-close-btn]')
  await Promise.all([p.waitForURL(u => !/\/free\//.test(u.href)), p.click('#ztog a:not(.on)')])
  await p.waitForSelector('.cards .wcard')
  out.back = { url: p.url(), cards: await ids() }
}
await b.close()
console.log(JSON.stringify(out))
