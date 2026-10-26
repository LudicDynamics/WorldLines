// tests/test_hub_zone_key.py 用:浏览器游玩启动层(hub/play/boot.js)按区选模型(niko 10-26)——
//   默认区(官方世界 ?tpl= · 默认区的社区作品 ?ref=&zone=curated)只用 Worldlines 额度,门上没有「用我自己的 key」,存过的 key 不删也不用;
//   自由区作品(?ref= 不带 zone)额度默认,也能填自己的 key。不起引擎:门在下载 Pyodide 之前;manifest / auth 都是假的,worker.js / sw.js 404(页面在 localhost:8885:Service Worker 要安全上下文,请求全被拦下,不真开端口)。
//   node tests/hub_play_zone.mjs <hub/play 目录> <playwright 所在的 package.json> [截图目录]
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { join } from 'path'

const [dir, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page = '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="boot.css"><script src="boot.js" defer></script></head><body></body></html>'
const manifest = { cfg: { auth: 'https://auth.test', billing: 'https://billing.test', ai: 'https://ai.test/v1', storage: 'https://storage.test' },
  edition: 'full', engine: { bytes: 1 }, pyodide: { version: '0', url: '', packages: [], bytes: 1, fallbacks: [] },
  worlds: { official: { ok: true, bytes: 1 } }, titles: { official: { zh: '官方世界' } } }
const KEY = { base: 'https://llm.test/v1', key: 'sk-zone-test', model: 'm' }
const AUTH = { access: 'tok', exp: Date.now() + 3600e3, refresh: 'r', user: { id: 'u' } }
const b = await chromium.launch()
const out = {}

async function open(name, qs, { auth = false, key = false } = {}) {
  const ctx = await b.newContext({ viewport: { width: 1100, height: 760 }, locale: 'zh-CN' })
  await ctx.addInitScript(([a, k, key]) => {
    try {
      if (a) localStorage.setItem('wl.hub.auth', JSON.stringify(a))
      if (k) { localStorage.setItem('wl.play.key', JSON.stringify(key)); localStorage.setItem('wl.play.mode', 'key') }
    } catch { /* no storage */ }
  }, [auth ? AUTH : null, key, KEY])
  const errs = [], seen = []
  const p = await ctx.newPage()
  p.on('pageerror', e => errs.push(e.message))
  await ctx.route('**/*', r => {
    const u = new URL(r.request().url())
    seen.push(`${u.host}${u.pathname}`)
    if (u.host === 'auth.test') return r.fulfill({ status: 503, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: '{}' })   // 游客令牌拿不到 → 门
    if (u.host !== 'localhost:8885') return r.abort()
    if (u.pathname === '/play/' || u.pathname === '/play/index.html') return r.fulfill({ contentType: 'text/html', body: page })
    if (u.pathname === '/play/manifest.json') return r.fulfill({ contentType: 'application/json', body: JSON.stringify(manifest) })
    if (u.pathname === '/play/boot.js' || u.pathname === '/play/boot.css') return r.fulfill({ contentType: u.pathname.endsWith('.js') ? 'text/javascript' : 'text/css', body: readFileSync(join(dir, u.pathname.slice(6)), 'utf-8') })
    return r.fulfill({ status: 404, body: '' })
  })
  await p.goto(`http://localhost:8885/play/?${new URLSearchParams({ lang: 'zh', ...qs })}`)
  await p.waitForFunction(() => (window.WLPLAY && window.WLPLAY.mode) || document.querySelector('.wlp-screen'), null, { timeout: 20000 })
  await p.waitForTimeout(300)
  const r = await p.evaluate(() => ({
    mode: window.WLPLAY.mode,
    screen: (document.querySelector('.wlp-screen') || {}).innerText || '',
    keyForm: document.querySelectorAll('form[data-key]').length,
    signin: [...document.querySelectorAll('.wlp-screen a.wlp-btn')].map(a => [a.textContent.trim(), a.getAttribute('href')]),
    stored: { key: !!localStorage.getItem('wl.play.key'), mode: localStorage.getItem('wl.play.mode') },
    modelSheet: !!(window.WLPLAY.engine && window.WLPLAY.engine.modelSheet),
  }))
  if (shots) await p.screenshot({ path: join(shots, `${name}.png`) })
  await ctx.close()
  return { ...r, errs }
}

out.defaultGuest = await open('play-default-gate', { tpl: 'official' })
out.defaultOwnLink = await open('play-default-own-link', { tpl: 'official', own: '1' }, { key: true })
out.defaultSignedKey = await open('play-default-signed-in', { tpl: 'official' }, { auth: true, key: true })
out.curatedGuest = await open('play-curated-guest', { ref: 'hub/template/comm-abc123', zone: 'curated' })
out.freeGuest = await open('play-free-gate', { ref: 'hub/template/w-free-abc123', title: '别人的作品' })
out.freeOwnNoKey = await open('play-free-own', { ref: 'hub/template/w-free-abc123', own: '1' })
out.freeSignedKey = await open('play-free-signed-in-key', { ref: 'hub/template/w-free-abc123' }, { auth: true, key: true })
await b.close()
console.log(JSON.stringify(out))
