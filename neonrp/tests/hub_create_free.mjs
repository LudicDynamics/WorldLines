// tests/test_hub_create_publish.py 用:桌面本地版(worldlines web 起的 /hub.html,没有 window.HUB)的创作台「发布到自由区」
// (10-24「local 可以自由上传到自由区」)。引擎接口用 page.route 装成假引擎:没登录 → 只给「登录」· 登录后发布 = zone open、
// 直接公开 · 「我的作品」里是「公开中」,带「撤下」和「申请进默认区」。
//   node tests/hub_create_free.mjs <page.html> <playwright 所在的 package.json> [截图目录]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const FORM = { schema: 'worldlines.creation-form/1', template: 'stoneford-town', open: true, card: ['title', 'pitch'],
  sections: [{ key: 'soul', fields: [{ name: 'name', type: 'text', required: true }, { name: 'persona', type: 'longtext', required: true }] }],
  images: [{ for: 'card', name: 'cover', required: true }] }
const S = { signed: false, works: {}, posts: [] }
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } })
await ctx.addInitScript(() => { try { if (!sessionStorage.getItem('wl.t.init')) { localStorage.setItem('wl.hub.lang', 'zh'); localStorage.setItem('wl.hub.intro', '1'); sessionStorage.setItem('wl.t.init', '1') } } catch { /* no storage */ } })
const p = await ctx.newPage()
const errs = []
p.on('pageerror', e => errs.push(e.message))
p.on('dialog', d => d.accept())
const json = (r, status, body) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
await p.route('**/*', r => {
  const u = new URL(r.request().url()), m = r.request().method(), path = u.pathname
  if (u.host !== 'hub.test') return r.abort()
  if (!path.startsWith('/api/')) return r.fulfill({ contentType: 'text/html', body: page0 })
  const body = m === 'POST' ? JSON.parse(r.request().postData() || '{}') : {}
  if (m === 'POST') S.posts.push([path, body])
  if (path === '/api/v1/local/templates') return json(r, 200, { templates: [{ id: 'stoneford-town', card: { title: '石津镇', pitch: '雾里的小镇', lang: 'zh' }, mode: { ending: 'multi' }, zone: 'reviewed', official: true, creation: { open: true } }] })
  if (path === '/api/v1/local/templates/stoneford-town/creation') return json(r, 200, FORM)
  if (path === '/api/v1/local/account') return json(r, 200, { signed_in: S.signed })
  if (path === '/api/v1/local/templates/stoneford-town/creation/check') return json(r, 200, { ok: true, problems: [] })
  if (path === '/api/v1/local/templates/stoneford-town/creation/work') return json(r, 200, { ok: true, id: 'stoneford-town-mine', plot: 'plots/mine', slots: [{ slot: 'card:cover', name: 'cover', need: true, have: true, row: { sec: 'card', i: 0 } }] })
  let mm
  if ((mm = /^\/api\/v1\/local\/templates\/([^/]+)\/publish$/.exec(path))) {
    const wid = decodeURIComponent(mm[1])
    if (m === 'GET') return json(r, 200, { checks: { ok: true, problems: [] }, signed_in: S.signed })
    if (!S.signed) return json(r, 401, { error: 'not_signed_in', message: '先登录 Worldlines 账号' })
    const pid = `${wid}-a1b2c3`, zone = body.zone === 'curated' ? 'reviewed' : 'open'
    S.works[pid] = { id: pid, ref: `hub/template/${pid}`, source: wid, zone, status: zone === 'open' ? 'published' : 'draft', revision: 1, meta: { title: { zh: '雾夜猎人' } }, published_at: '2026-10-24T12:00:00Z' }
    return json(r, 200, { id: pid, zone, status: S.works[pid].status, message: zone === 'open' ? '已发布:公开在自由区' : '已提交到默认区审核' })
  }
  if (path === '/api/v1/local/hub/mine') return S.signed ? json(r, 200, { works: Object.values(S.works) }) : json(r, 401, { error: 'not_signed_in' })
  if (path.startsWith('/api/v1/local/ai/')) return json(r, 404, {})
  return json(r, 200, {})
})
const shot = async n => { if (shots) await p.screenshot({ path: `${shots}/${n}.png`, fullPage: true }) }
const out = { errs }
const sheet = () => p.textContent('.sheet')
const openSheet = async signed => {
  await p.click('[data-cf-submit]')
  await p.waitForFunction(() => { const s = document.querySelector('.sheet'); return s && !/正在做发布前检查/.test(s.textContent) })
  await p.waitForSelector(signed ? '.sheet [data-cf-submit-go]' : '.sheet [data-cf-sign]')
}

await p.goto('http://hub.test/#/t/stoneford-town/create')
await p.waitForSelector('[data-cf-card="zh.title"]')
// 世界列表 / 账号 / 进度是后补进来的,补完会重画一次创作台:等它安静下来再填,不然先填的那格会被换掉的输入框吞掉(10-24 约一半概率)
await p.waitForLoadState('networkidle'); await p.waitForTimeout(300)
await p.fill('[data-cf-card="zh.title"]', '雾夜猎人')
await p.fill('[data-cf-card="zh.pitch"]', '雾里有人在追脚印。')
await p.fill('[data-sec="soul"][data-name="name"]', '阿青')
await p.fill('[data-sec="soul"][data-name="persona"]', '沉默的猎人')
await p.click('[data-cf-save]')
await p.waitForSelector('[data-cf-submit]:not([disabled])')
out.button = await p.textContent('[data-cf-submit]')
out.savedMsg = await p.textContent('[data-cf-msg]')
// 1. 没登录:只给「登录」
await openSheet(false)
out.unsigned = { sign: !!(await p.$('.sheet [data-cf-sign]')), go: !!(await p.$('.sheet [data-cf-submit-go]')), text: await sheet() }
await shot('free-01-not-signed-in')
await p.click('.sheet [data-close-btn]')
// 2. 登录了:发布 → zone open,直接公开
S.signed = true
await openSheet(true)
out.sheet = await sheet()
await p.click('.sheet [data-cf-submit-go]')
await p.waitForFunction(() => /公开在自由区/.test((document.querySelector('.sheet') || {}).textContent || ''))
out.done = { text: await sheet(), mine: !!(await p.$('.sheet a[href="#/me"]')) }
await shot('free-02-published')
await p.click('.sheet a[href="#/me"]')
await p.waitForFunction(() => document.querySelectorAll('.meworks .meitem.wk').length >= 1)
out.mine = await p.$$eval('.meworks .meitem.wk', a => a.map(x => x.textContent.replace(/\s+/g, ' ').trim()))
await shot('free-03-my-works')
out.publishBodies = S.posts.filter(([q]) => q.endsWith('/publish')).map(([q, bd]) => [q, bd.zone])
await b.close()
console.log(JSON.stringify(out))
