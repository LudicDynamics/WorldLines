// tests/test_hub_loading.py 用:Hub 刚打开、世界列表还没到时显示骨架卡片 +「正在载入世界…」,到了才出卡片;
// 真的为空(或拿不到)才说「没有符合的世界」(10-21 审核准备:以前先画一次空列表,闪一下「没有符合的世界」)。
//   node tests/hub_loading.mjs <hub/index.html> <hub/hub.js> <playwright 所在的 package.json> [截图目录]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [htmlF, jsF, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const html = readFileSync(htmlF, 'utf-8'), js = readFileSync(jsF, 'utf-8')
const build = cfg => html.replace('<!--SCRIPT-->', () => `<script>window.HUB=${JSON.stringify(cfg)}</script><script>${js}</script>`)
const sleep = ms => new Promise(r => setTimeout(r, ms))
const local = [{ id: 'official', card: { title: '官方世界', pitch: 'p', lang: 'zh' }, mode: { ending: 'open' }, zone: 'reviewed' }, { id: 'second', card: { title: '第二个', pitch: 'p', lang: 'zh' }, mode: { ending: 'open' }, zone: 'reviewed' }]
const catalog = { templates: [{ id: 'official', title: { zh: '官方世界' }, pitch: { zh: 'p' }, lang: 'zh', tags: {}, endings: [], cast: [], zone: 'reviewed' }] }

const b = await chromium.launch()
const out = { errs: [] }
async function run(name, { web = false, delay = 1500, templates = local, down = false, hash = '#/', lang = 'zh', width = 390, settle = 1500 } = {}) {
  const ctx = await b.newContext({ viewport: { width, height: 844 } })
  await ctx.addInitScript(l => { try { localStorage.setItem('wl.hub.lang', l); localStorage.setItem('wl.hub.intro', '1') } catch { /* no storage */ } }, lang)
  const p = await ctx.newPage()
  p.on('pageerror', e => out.errs.push(`${name}: ${e.message}`))
  const page = build(web ? { mode: 'static', catalog: 'catalog.json', auth: 'https://auth.test' } : {})
  await p.route('**/*', async r => {
    const u = new URL(r.request().url())
    const json = (o, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(o) })
    if (u.host !== 'hub.test') return r.abort()
    if (u.pathname === '/api/v1/local/templates') { if (down) return json({}, 500); await sleep(delay); return json({ templates }) }
    if (u.pathname === '/catalog.json') { if (down) return json({}, 404); await sleep(delay); return json(web ? catalog : {}, web ? 200 : 404) }
    if (u.pathname.startsWith('/api/')) return json(web ? {} : {}, web ? 404 : 200)
    return r.fulfill({ contentType: 'text/html', body: page })
  })
  const look = () => p.evaluate(() => ({
    skel: document.querySelectorAll('.cards.skel .skc').length, busy: !!document.querySelector('[aria-busy="true"]'),
    msg: (document.querySelector('.skmsg') || {}).textContent || '', cards: document.querySelectorAll('.cards .wcard, .cards.souls > a').length,
    empty: (document.querySelector('.glass.empty') || {}).textContent || '',
  }))
  await p.goto(`http://hub.test/${hash}`)
  await sleep(250)
  const early = await look()
  if (shots && name === 'local') await p.screenshot({ path: `${shots}/hub-loading-early.png` })
  await sleep(delay + settle)
  const late = await look()
  if (shots && name === 'local') await p.screenshot({ path: `${shots}/hub-loading-done.png` })
  out[name] = { early, late }
  await ctx.close()
}
await run('local')
await run('web', { web: true })
await run('empty', { templates: [], delay: 600 })
await run('down', { down: true, delay: 0, settle: 5000 })   // 引擎连不上:再问两次(0.8s · 1.6s)以后,不能一直停在载入中
await run('souls', { hash: '#/souls' })
await run('en', { lang: 'en' })
await run('desktop', { width: 1280 })
await b.close()
console.log(JSON.stringify(out))
