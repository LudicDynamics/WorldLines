// tests/test_hub_login.py 用:Hub 登录 / 退出的进行中状态 + 超时 / 重试(10-17:点了没反应像卡住,偶尔 timeout)。
// 线上(静态)Hub:auth.test 是假的 identity,可以拖慢 / 断开 / 永远不回;本地(引擎模式):/api/v1/local/account* 是假的引擎。
//   node tests/hub_login.mjs <hub/index.html> <hub/hub.js> <playwright 所在的 package.json> <截图目录>
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [htmlF, jsF, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const html = readFileSync(htmlF, 'utf-8'), js = readFileSync(jsF, 'utf-8')
const build = cfg => html.replace('<!--SCRIPT-->', () => `<script>window.HUB=${JSON.stringify(cfg)}</script><script>${js}</script>`)
const web = build({ mode: 'static', catalog: 'catalog.json', auth: 'https://auth.test', billing: 'https://billing.test', ai: 'https://ai.test/v1', loginSlowMs: 700, loginGiveupMs: 2200, authTimeoutMs: 1200 })
const local = build({})
const catalog = { templates: [{ id: 'official', title: { zh: '官方世界' }, pitch: { zh: 'p' }, lang: 'zh', tags: {}, endings: [], cast: [], zone: 'reviewed' }] }
const tokens = { access_token: 'a1', refresh_token: 'r1', expires_in: 900, user: { display_name: 'Niko', email: 'n@x.test' } }
const sleep = ms => new Promise(r => setTimeout(r, ms))

const b = await chromium.launch()
const out = { errs: [] }
async function open(page, { reduced = false, auth = {}, engine = null } = {}) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: reduced ? 'reduce' : 'no-preference' })
  await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh'); localStorage.setItem('wl.hub.intro', '1') } catch { /* no storage */ } })
  const p = await ctx.newPage()
  p.on('pageerror', e => out.errs.push(e.message))
  const calls = {}
  await p.route('**/*', async r => {
    const u = new URL(r.request().url()), m = r.request().method(), key = `${m} ${u.host}${u.pathname}`
    calls[key] = (calls[key] || 0) + 1
    const json = (o, status = 200) => r.fulfill({ status, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(o) })
    if (m === 'OPTIONS') return r.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } })
    const h = auth[key] || (engine && engine[key])
    if (h) return h(r, json, calls[key])
    if (u.host === 'auth.test' || u.host === 'billing.test' || u.host === 'ai.test') return json({}, 404)
    if (u.host !== 'hub.test') return r.abort()
    if (u.pathname === '/catalog.json') return json(catalog)
    if (u.pathname.startsWith('/api/')) return json({}, page === 'web' ? 404 : 200)
    return r.fulfill({ contentType: 'text/html', body: page === 'web' ? web : local })
  })
  return { ctx, p, calls }
}
const bar = p => p.$eval('#lgbar', el => ({ cls: el.className, text: el.querySelector('.lgmsg').textContent, btns: [...el.querySelectorAll('button,a')].map(x => x.textContent.trim()), spin: !!el.querySelector('.spin') })).catch(() => null)
const toasts = p => p.$$eval('.toast', a => a.map(x => x.textContent))

// ── 1. 线上:点「登录」→ 按钮马上转圈、别的登录按钮锁住;登录页一直不回 → 「网络可能有点慢」+ 重试 / 取消 → 再等算超时 ──
{
  // 登录页不回:204 = 浏览器留在这一页不跳(和一直在转的导航一样,页面还在;一直挂着的导航会卡住 playwright 的 evaluate)
  const { ctx, p, calls } = await open('web', { auth: { 'GET auth.test/v1/login/start': r => r.fulfill({ status: 204, body: '' }) } })
  await p.goto('https://hub.test/#/me')   // https:PKCE 要 crypto.subtle
  await p.waitForSelector('#who [data-signin]')
  await p.click('#who [data-signin]')
  await p.$eval('[data-login="google"]', x => x.click())   // 点下去页面会跳走:不等导航
  await sleep(150)
  out.opening = {
    btn: await p.$eval('[data-login="google"]', x => ({ text: x.textContent, busy: x.getAttribute('aria-busy'), spin: !!x.querySelector('.spin'), disabled: x.disabled })),
    others: await p.$$eval('[data-login]:not([data-login="google"])', a => a.map(x => x.disabled)),
    bar: await bar(p),
  }
  await p.screenshot({ path: `${shots}/hub-login-opening.png` })
  await p.$eval('[data-login="google"]', x => x.click())   // 再点一次(按钮已锁):不会再开一次
  await sleep(800)
  out.slow = await bar(p)
  await p.screenshot({ path: `${shots}/hub-login-slow.png` })
  await sleep(1700)
  out.giveup = await bar(p)
  out.giveupBtns = await p.$$eval('[data-login]', a => a.map(x => x.disabled))
  await p.screenshot({ path: `${shots}/hub-login-timeout.png` })
  out.startCalls = calls['GET auth.test/v1/login/start'] || 0
  await ctx.close()
}

// ── 2. 回来换 token:慢 → 「正在完成登录…」;连不上两次再成功 = 自动重试;换完列表早就出来了 ──
async function callback(handler) {
  const r = await open('web', { auth: { 'POST auth.test/v1/token': handler } })
  await r.p.goto('https://hub.test/#/')
  await r.p.evaluate(() => sessionStorage.setItem('wl.hub.pkce', JSON.stringify({ verifier: 'v', state: 'S1', back: '#/me', provider: 'google', fallback: false })))
  await r.p.goto('https://hub.test/?code=c1&state=S1')
  return r
}
{
  const { ctx, p, calls } = await callback(async (r, json) => { await sleep(900); return json(tokens) })
  await sleep(300)
  out.finishing = { bar: await bar(p), cards: await p.$$eval('.cards .wcard, .me', a => a.length) }
  await p.screenshot({ path: `${shots}/hub-login-finishing.png` })
  await p.waitForSelector('#who .avatar', { timeout: 5000 })
  out.finished = { bar: await bar(p), toasts: await toasts(p), url: p.url(), calls: calls['POST auth.test/v1/token'] }
  await ctx.close()
}
{
  const { ctx, p, calls } = await callback((r, json, n) => (n < 3 ? r.abort('connectionrefused') : json(tokens)))
  await p.waitForSelector('#who .avatar', { timeout: 8000 }).catch(() => {})
  out.netRetry = { signed: !!(await p.$('#who .avatar')), calls: calls['POST auth.test/v1/token'], bar: await bar(p) }
  await ctx.close()
}
{
  const { ctx, p, calls } = await callback(() => {})   // 永远不回 = 超时;授权码只能用一次,超时不再发
  await sleep(2600)
  out.tokenTimeout = { bar: await bar(p), calls: calls['POST auth.test/v1/token'], signed: !!(await p.$('#who .avatar')) }
  await p.screenshot({ path: `${shots}/hub-login-token-timeout.png` })
  await ctx.close()
}

// ── 3. 退出:按钮「正在退出…」转圈,撤销慢也等着;撤不掉 = 本机照退 + 明说 ──
async function signedIn(handler, reduced = false) {
  const r = await open('web', { reduced, auth: { 'POST auth.test/v1/logout': handler } })
  await r.ctx.addInitScript(t => { try { localStorage.setItem('wl.hub.auth', JSON.stringify(t)) } catch { /* no storage */ } }, { access: 'a1', refresh: 'r1', exp: Date.now() + 3600e3, user: { display_name: 'Niko' } })
  await r.p.goto('https://hub.test/#/me')
  await r.p.waitForSelector('[data-signout]')
  return r
}
{
  const { ctx, p, calls } = await signedIn(async (r, json) => { await sleep(900); return json({ ok: true }) })
  await p.click('[data-signout]')
  await sleep(200)
  out.out = { btn: await p.$eval('[data-signout]', x => ({ text: x.textContent, busy: x.getAttribute('aria-busy'), disabled: x.disabled })), bar: await bar(p) }
  await p.screenshot({ path: `${shots}/hub-logout.png` })
  await p.waitForSelector('#who [data-signin]', { timeout: 5000 })
  out.outDone = { toasts: await toasts(p), auth: await p.evaluate(() => localStorage.getItem('wl.hub.auth')), calls: calls['POST auth.test/v1/logout'] }
  await ctx.close()
}
{
  const { ctx, p, calls } = await signedIn(r => r.abort('connectionrefused'))
  await p.click('[data-signout]')
  await p.waitForSelector('#who [data-signin]', { timeout: 6000 })
  out.outFail = { toasts: await toasts(p), calls: calls['POST auth.test/v1/logout'], auth: await p.evaluate(() => localStorage.getItem('wl.hub.auth')) }
  await ctx.close()
}
{   // 少动模式:照样有转圈的圈,但不转
  const { ctx, p } = await signedIn(async (r, json) => { await sleep(900); return json({ ok: true }) }, true)
  await p.click('[data-signout]')
  await sleep(150)
  out.reduced = await p.$eval('[data-signout] .spin', x => { const c = getComputedStyle(x); return { anim: c.animationName, style: c.borderTopStyle } })
  await ctx.close()
}

// ── 4. 本地版:引擎后台起浏览器登录 → 「请在浏览器里批准」+ 取消 + 登录页链接 → 登好了;引擎报超时 → 重试;取消 ──
function engine(seq, extra = {}) {
  let signed = false
  return {
    'GET hub.test/api/v1/local/templates': (r, json) => json({ templates: [{ id: 'official', card: { title: '官方世界', pitch: 'p', lang: 'zh' }, mode: { ending: 'open' }, zone: 'reviewed' }] }),
    'GET hub.test/api/v1/local/hub/mine': (r, json) => (signed ? json({ works: [] }) : json({ error: 'not_signed_in' }, 401)),
    'POST hub.test/api/v1/local/account/login': async (r, json) => { await sleep(300); return json({ login: 'running', login_timeout_s: 300 }) },
    'GET hub.test/api/v1/local/account': (r, json, n) => { const a = seq[Math.min(n - 1, seq.length - 1)]; signed = !!a.signed_in; return json(a) },
    ...extra,
  }
}
{
  const { ctx, p, calls } = await open('local', { engine: engine([{ signed_in: false, login: 'running' }, { signed_in: false, login: 'running', login_url: 'https://auth.test/v1/login/start?x=1' }, { signed_in: false, login: 'running', login_url: 'https://auth.test/v1/login/start?x=1' }, { signed_in: true, login: 'idle' }]) })
  await p.goto('http://hub.test/#/me')
  await p.waitForSelector('[data-wl-login]')
  await p.click('[data-wl-login]')
  await sleep(100)
  out.localOpening = { btn: await p.$eval('[data-wl-login]', x => ({ text: x.textContent, busy: x.getAttribute('aria-busy'), disabled: x.disabled })), bar: await bar(p) }
  await sleep(2900)
  out.localWait = { bar: await bar(p), link: await p.$eval('#lgbar a', x => x.href).catch(() => null) }
  await p.screenshot({ path: `${shots}/local-login-wait.png` })
  await p.waitForSelector('[data-wl-logout]', { timeout: 6000 })
  out.localDone = { bar: await bar(p), toasts: await toasts(p), polls: calls['GET hub.test/api/v1/local/account'] }
  await ctx.close()
}
{
  const { ctx, p } = await open('local', { engine: engine([{ signed_in: false, login: 'error', login_code: 'login_timeout', login_error: 'login_timeout' }]) })
  await p.goto('http://hub.test/#/me')
  await p.waitForSelector('[data-wl-login]')
  await p.click('[data-wl-login]')
  await sleep(1900)
  out.localTimeout = await bar(p)
  await p.screenshot({ path: `${shots}/local-login-timeout.png` })
  await ctx.close()
}
{
  const { ctx, p, calls } = await open('local', { engine: engine([{ signed_in: false, login: 'running' }], { 'POST hub.test/api/v1/local/account/login/cancel': (r, json) => json({ login: 'cancelled' }) }) })
  await p.goto('http://hub.test/#/me')
  await p.waitForSelector('[data-wl-login]')
  await p.click('[data-wl-login]')
  await sleep(700)
  await p.click('[data-lg-cancel]')
  await sleep(400)
  out.localCancel = { bar: await bar(p), toasts: await toasts(p), cancel: calls['POST hub.test/api/v1/local/account/login/cancel'] || 0, btn: await p.$eval('[data-wl-login]', x => x.disabled) }
  await ctx.close()
}
{
  const { ctx, p, calls } = await open('local', { engine: { ...engine([{ signed_in: true, login: 'idle' }]), 'GET hub.test/api/v1/local/hub/mine': (r, json) => (out.localOutSent ? json({ error: 'not_signed_in' }, 401) : json({ works: [] })), 'POST hub.test/api/v1/local/account/logout': async (r, json) => { out.localOutSent = true; await sleep(600); return json({ signed_in: false, login: 'idle' }) } } })
  await p.goto('http://hub.test/#/me')
  await p.waitForSelector('[data-wl-logout]')
  await p.click('[data-wl-logout]')
  await sleep(150)
  out.localOut = { btn: await p.$eval('[data-wl-logout]', x => ({ text: x.textContent, busy: x.getAttribute('aria-busy') })), bar: await bar(p) }
  await sleep(900)
  out.localOutDone = { toasts: await toasts(p), btn: !!(await p.$('[data-wl-logout]')), login: !!(await p.$('[data-wl-login]')), calls: calls['POST hub.test/api/v1/local/account/logout'] }
  await ctx.close()
}
await b.close()
console.log(JSON.stringify(out))
