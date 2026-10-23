// tests/test_hub_run_points.py 用:Hub「我的」· 对局积分(runpoints.js,10-21)—— 本地模式,引擎代问 billing 的
// /api/v1/local/account/run-points 在这里给:核对中(进度)· 核对过可领 · 核对过只记录 · 到上限 · 没核对上;点「领取」走 …/rewards/<id>/claim。
//   node tests/hub_run_points.mjs <page.html> <playwright 所在的 package.json> <截图目录>
import { createRequire } from 'module'
import { readFileSync, mkdirSync } from 'fs'
import { join } from 'path'

const [html, pkg, shots] = process.argv.slice(2)
mkdirSync(shots, { recursive: true })
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const RW = '11111111-2222-4333-8444-555555555555'
const DATA = { signed_in: true, runs: [
  { ref: 'hub:settlement:pct-house:r1', world: 'pct-house', status: 'pending_verification', points_asked: 60, points: 0, progress: { calls: 3, need_calls: 8, minutes: 12, need_minutes: 5 } },
  { ref: 'hub:settlement:pct-house:r2', world: 'pct-house', status: 'verified', points_asked: 80, points: 80, reward_id: RW },
  { ref: 'hub:settlement:guixiang:r3', world: 'guixiang', status: 'verified', points_asked: 50, points: 50 },
  { ref: 'hub:settlement:guixiang:r4', world: 'guixiang', status: 'capped', points_asked: 50, points: 0 },
  { ref: 'hub:settlement:guixiang:r5', world: 'guixiang', status: 'expired', points_asked: 50, points: 0 },
], rewards: [{ id: RW, kind: 'run_points', ref: 'hub:settlement:pct-house:r2', amount_mc: 160000, state: 'claimable' }] }
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 900, height: 1400 } })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh') } catch { /* */ } })
const p = await ctx.newPage()
const errs = [], claims = []
let gets = 0
p.on('pageerror', e => errs.push(e.message))
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname === '/api/v1/local/account/run-points') { gets += 1; return json(r, claims.length ? { ...DATA, rewards: [{ ...DATA.rewards[0], state: 'claimed' }] } : DATA) }
  if (u.pathname === `/api/v1/local/account/rewards/${RW}/claim`) { claims.push(r.request().method()); return json(r, { reward: { id: RW, state: 'claimed' } }) }
  if (u.pathname === '/api/v1/local/account') return json(r, { signed_in: true })
  if (u.pathname === '/api/v1/local/templates') return json(r, { templates: [] })
  if (u.pathname.startsWith('/api/')) return json(r, {})
  if (u.pathname === '/catalog.json') return json(r, { templates: [] })
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
await p.goto('http://hub.test/#/me')
// 「我的」每到一个请求的回包就整页重画(hub.js render() 换掉 #app):等到没有请求在路上(networkidle)、积分块的五行都在,
// 页面才算停下来,之后再读字、截图、点按钮 —— 不然截图那一下元素可能刚被换掉(layers-a 10-21:4 遍挂 1 遍)
await p.waitForSelector('[data-rpts] .meitem', { timeout: 60000 })
await p.waitForLoadState('networkidle')
await p.waitForFunction(() => document.querySelectorAll('[data-rpts] .meitem').length === 5 && !!document.querySelector('[data-rpts-claim]'), null, { timeout: 30000 })
const out = { rows: await p.$$eval('[data-rpts] .meitem', a => a.map(x => x.textContent.replace(/\s+/g, ' ').trim())) }
await p.locator('[data-rpts]').screenshot({ path: join(shots, 'run-points.png') })
await p.click('[data-rpts-claim]')
await p.waitForSelector('.toast')
out.toast = await p.textContent('.toast')
await p.waitForFunction(() => !document.querySelector('[data-rpts-claim]') && /✓/.test((document.querySelectorAll('[data-rpts] .meitem')[1] || {}).textContent || ''), null, { timeout: 30000 })
await p.waitForLoadState('networkidle')
out.after = await p.$$eval('[data-rpts] .meitem', a => a.map(x => x.textContent.replace(/\s+/g, ' ').trim()))
out.claims = claims
out.gets = gets
out.errs = errs
console.log(JSON.stringify(out))
await b.close()
