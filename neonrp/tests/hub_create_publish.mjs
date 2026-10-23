// tests/test_hub_create_publish.py 用:创作台「提交到默认区」的前端一半(网页 / iOS 同一份 hub.js;这里按 iOS / 本地那样打开,
// 引擎接口用 page.route 装成有状态的假引擎)。没登录 → 只给「登录」· 原文标题没写 → 存之前拦 · 发布前检查有问题 → 按钮灰、列出问题 ·
// 平台出错 → 「没提交成功 · 原因」、按钮还能再点、再点成功 · 同一模板第二份作品各自提交 · 「我的作品」里两份都是审核中。
//   node tests/hub_create_publish.mjs <page.html> <playwright 所在的 package.json> [截图目录]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const FORM = { schema: 'worldlines.creation-form/1', template: 'stoneford-town', open: true, card: ['title', 'pitch'],
  sections: [{ key: 'soul', fields: [{ name: 'name', type: 'text', required: true }, { name: 'persona', type: 'longtext', required: true }] }],
  images: [{ for: 'card', name: 'cover', required: true }] }
// 假引擎的状态:登录 · 发布前检查的问题 · 下一次提交要不要失败 · 平台上的作品
const S = { signed: false, problems: [], failNext: 0, works: {}, posts: [] }
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
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
  if (path === '/api/v1/local/templates/stoneford-town/creation/work') {
    const id = body.id || 'stoneford-town-mine'
    return json(r, 200, { ok: true, id, plot: 'plots/mine', slots: [{ slot: 'card:cover', name: 'cover', need: true, have: true, row: { sec: 'card', i: 0 } }] })
  }
  let mm
  if ((mm = /^\/api\/v1\/local\/templates\/([^/]+)\/publish$/.exec(path))) {
    const wid = decodeURIComponent(mm[1])
    if (m === 'GET') return json(r, 200, { checks: { ok: !S.problems.length, problems: S.problems.map(message => ({ message })) }, signed_in: S.signed })
    if (!S.signed) return json(r, 401, { error: 'not_signed_in', message: '先登录 Worldlines 账号' })
    if (S.problems.length) return json(r, 422, { error: 'checks', problems: S.problems.map(message => ({ message })) })
    if (S.failNext > 0) { S.failNext--; return json(r, 502, { error: 'platform_error', message: '平台暂时连不上,稍后再试' }) }
    const pid = `${wid}-${Object.keys(S.works).length.toString(16).padStart(6, 'a')}`
    S.works[pid] = { id: pid, ref: `hub/template/${pid}`, source: wid, zone: 'reviewed', status: 'draft', revision: 1, meta: { title: { zh: wid } }, review: { state: 'pending', autopass_at: '2026-10-24T12:30:00Z' } }
    return json(r, 200, { id: pid, zone: 'reviewed', status: 'draft', review: { state: 'pending' }, message: '已提交到默认区审核:快审 30 分钟内没人提出问题就自动通过' })
  }
  if (path === '/api/v1/local/hub/mine') return S.signed ? json(r, 200, { works: Object.values(S.works) }) : json(r, 401, { error: 'not_signed_in' })
  if (path.startsWith('/api/v1/local/ai/')) return json(r, 404, {})
  return json(r, 200, {})
})
const shot = async n => { if (shots) await p.screenshot({ path: `${shots}/${n}.png`, fullPage: true }) }
const out = { errs }
const sheet = () => p.textContent('.sheet')
const fill = async (title = '雾夜猎人') => {
  await p.fill('[data-cf-card="zh.title"]', title)
  await p.fill('[data-cf-card="zh.pitch"]', '雾里有人在追脚印。')
  await p.fill('[data-sec="soul"][data-name="name"]', '阿青')
  await p.fill('[data-sec="soul"][data-name="persona"]', '沉默的猎人')
}
// signed:提交页打开后会再问一次引擎的登录状态(hub.js),等它回来:登录了要看到提交按钮,没登录要看到「登录」
const openSheet = async (signed = true) => {
  await p.click('[data-cf-submit]')
  await p.waitForFunction(() => { const s = document.querySelector('.sheet'); return s && !/正在做发布前检查/.test(s.textContent) })
  await p.waitForSelector(signed ? '.sheet [data-cf-submit-go]' : '.sheet [data-cf-sign]')
}
const closeSheet = () => p.click('.sheet [data-close-btn]')
// 改一个字再存:发布前检查跟着「存」重做(hub.js cfSave → cfPre)
const resave = async pitch => {
  await p.fill('[data-cf-card="zh.pitch"]', pitch)
  await p.click('[data-cf-save]')
  await p.waitForFunction(() => { const b = document.querySelector('[data-cf-submit]'); return b && !b.disabled })
  await p.waitForTimeout(300)
}

await p.goto('http://hub.test/#/t/stoneford-town/create')
await p.waitForSelector('[data-cf-card="zh.title"]')
// 1. 原文(中文)标题清空:存之前就拦,引擎一个字都没收到
await p.fill('[data-cf-card="zh.title"]', '')
await p.click('[data-cf-save]')
await p.waitForFunction(() => /作品名/.test((document.querySelector('[data-cf-msg]') || {}).textContent || ''))
out.needTitle = await p.textContent('[data-cf-msg]')
out.workPostsBefore = S.posts.filter(([q]) => q.endsWith('/creation/work')).length
// 2. 存好 → 没登录:提交页只给「登录」,没有提交按钮
await fill()
await p.click('[data-cf-save]')
await p.waitForSelector('[data-cf-submit]:not([disabled])')
await openSheet(false)
out.unsigned = { sign: !!(await p.$('.sheet [data-cf-sign]')), go: !!(await p.$('.sheet [data-cf-submit-go]')), text: await sheet() }
await shot('01-not-signed-in')
await closeSheet()
// 3. 登录了,但发布前检查有问题(缺封面 · 缺图):按钮灰、问题列出来、写着「先改好」
S.signed = true
S.problems = ['封面:还没有图', '结局图:雾散 · 还没有图']
await resave('雾里有人在追脚印。(改了一句)')
await openSheet()
out.blocked = { disabled: await p.$eval('.sheet [data-cf-submit-go]', el => el.disabled), text: await sheet() }
await shot('02-checks-block')
await closeSheet()
// 4. 问题改好 → 提交;平台第一次出错:「没提交成功 · 原因」,按钮还能点;再点成功
S.problems = []
S.failNext = 1
await resave('雾里有人在追脚印。')
await openSheet()
await p.click('.sheet [data-cf-submit-go]')
await p.waitForFunction(() => /没提交成功/.test((document.querySelector('.sheet') || {}).textContent || ''))
out.failed = { text: await sheet(), again: await p.$eval('.sheet [data-cf-submit-go]', el => !el.disabled), mine: !!(await p.$('.sheet a[href="#/me"]')) }
await shot('03-failed')
await p.click('.sheet [data-cf-submit-go]')
await p.waitForFunction(() => /已提交到默认区审核/.test((document.querySelector('.sheet') || {}).textContent || ''))
out.retried = { text: await sheet(), mine: !!(await p.$('.sheet a[href="#/me"]')) }
await shot('04-submitted')
await p.click('.sheet a[href="#/me"]')
// 5. 同一个模板另起一份(「我的」→ 新的创作):各自的 id,各自提交
await p.waitForSelector('.meworks .menew summary')
await p.click('.meworks .menew summary')
out.newHref = await p.$eval('.meworks .menew [data-wk-new="stoneford-town"]', a => a.getAttribute('href'))
await p.click('.meworks .menew [data-wk-new="stoneford-town"]')
await p.waitForSelector('[data-cf-card="zh.title"]')
await fill('雾里的第二封信')
await p.click('[data-cf-save]')
await p.waitForSelector('[data-cf-submit]:not([disabled])')
await openSheet()
await p.click('.sheet [data-cf-submit-go]')
await p.waitForFunction(() => /已提交到默认区审核/.test((document.querySelector('.sheet') || {}).textContent || ''))
await p.click('.sheet a[href="#/me"]')
// 6. 「我的作品」:两份都在默认区、都是审核中,带预计上线时间和「撤回」
await p.waitForFunction(() => document.querySelectorAll('.meworks .meitem.wk').length >= 2)
out.mine = await p.$$eval('.meworks .meitem.wk', a => a.map(x => x.textContent.replace(/\s+/g, ' ').trim()))
await shot('05-my-works')
out.publishPosts = S.posts.filter(([q]) => q.endsWith('/publish')).map(([q]) => q)
out.workIds = S.posts.filter(([q]) => q.endsWith('/creation/work')).map(([, bd]) => bd.id || '')
await b.close()
console.log(JSON.stringify(out))
