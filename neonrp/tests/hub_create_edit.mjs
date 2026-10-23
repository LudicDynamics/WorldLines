// tests/test_hub_create_publish.py 用:创作台「编辑」的前端一半(网页 / iOS 同一份 hub.js;网页宽度 / iOS 手机宽度各跑一遍)。
// 草稿:填四语标题 · 角色 · 编排节奏 · 封面 → 存 → 整页重开,都还在 → 改了再存(编排节奏 / 角色 / 新封面都交给引擎)
// 审核中:「我的作品」→「改版再提交」回到这一份 → 改 → 存 → 再提交(同一件作品)· 已上架:同样改版再提交,提示「旧版照常在线」
// 同一模板第二份:改它不碰第一份的草稿。
//   node tests/hub_create_edit.mjs <page.html> <playwright 的 package.json> <web|ios> [截图目录]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, pkg, mode, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64')
const L = (zh, en) => ({ zh, en, ja: en, ko: en })
const PACE = { id: 'pace', default: 'normal', title: L('商量节奏', 'Talk pace'), choices: [{ id: 'normal', title: L('照常', 'As usual'), summary: L('照常谈', 'as usual') }, { id: 'quick', title: L('快商量', 'Quick talk'), summary: L('谈得短', 'short') }] }
const view = (id, rounds) => ({ schema: 'worldlines.orchestration-view/1', preset: id, readonly: true, title: L('先商量后行动', 'Talk first'), summary: L('', ''),
  nodes: [{ id: 'plan', kind: 'core', title: L('商量', 'Talk'), summary: L('', ''), steps: [], settings: [{ id: 'rounds', title: L('每句最多', 'per line'), short: L(`${rounds} 轮`, `${rounds} rounds`), shows: L('', ''), changed: rounds === 2 }] },
    { id: 'resolve', kind: 'core', title: L('结算', 'Resolve'), summary: L('', ''), steps: [] }], edges: [{ from: 'plan', to: 'resolve', labels: [L('谈定了', 'settled')] }], start: 'plan' })
const ORCH = { schema: 'worldlines.orchestration-view/1', template: 'stoneford-town', default: 'two_beat',
  options: [{ id: 'two_beat', title: L('先商量后行动', 'Talk first, then act'), summary: L('', ''), params: [PACE] }, { id: 'one_beat', title: L('一句一拍', 'One line, one beat'), summary: L('', '') }],
  views: { two_beat: view('two_beat', 4), 'two_beat?pace=quick': view('two_beat?pace=quick', 2), one_beat: { ...view('one_beat', 4), nodes: [{ id: 'resolve', kind: 'core', title: L('结算', 'Resolve'), summary: L('', ''), steps: [] }], edges: [], start: 'resolve' } } }
const FORM = { schema: 'worldlines.creation-form/1', template: 'stoneford-town', open: true, card: ['title', 'pitch'],
  sections: [{ key: 'soul', fields: [{ name: 'name', type: 'text', required: true }, { name: 'persona', type: 'longtext', required: true }] }],
  images: [{ for: 'card', name: 'cover', required: true }], orchestration: { default: 'two_beat', options: ORCH.options } }
const S = { works: {}, posts: [], uploads: [], saved: {} }   // saved: 作品 id → 最近一次存的 {addition, card}
const b = await chromium.launch()
const ctx = await b.newContext(mode === 'ios' ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1360, height: 900 } })
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
  let mm
  if ((mm = /^\/api\/v1\/local\/templates\/([^/]+)\/assets\/upload$/.exec(path))) { S.uploads.push([decodeURIComponent(mm[1]), u.searchParams.get('slot')]); return json(r, 200, { ok: true, slot: { slot: u.searchParams.get('slot'), have: true } }) }
  const body = m === 'POST' ? JSON.parse(r.request().postData() || '{}') : {}
  if (m === 'POST') S.posts.push([path, body])
  if (path === '/api/v1/local/templates') return json(r, 200, { templates: [{ id: 'stoneford-town', card: { title: '石津镇', pitch: '雾里的小镇', lang: 'zh' }, mode: { ending: 'multi' }, zone: 'reviewed', official: true, creation: { open: true } }] })
  if (path === '/api/v1/local/templates/stoneford-town/creation') return json(r, 200, FORM)
  if (path === '/api/v1/local/templates/stoneford-town/creation/orchestration') return json(r, 200, ORCH)
  if (/\/creation\/orchestration$/.test(path)) return json(r, 200, { default: 'two_beat' })
  if (path === '/api/v1/local/account') return json(r, 200, { signed_in: true })
  if (path === '/api/v1/local/templates/stoneford-town/creation/check') return json(r, 200, { ok: true, problems: [] })
  if (path === '/api/v1/local/templates/stoneford-town/creation/work') {
    const id = body.id || 'stoneford-town-mine'
    S.saved[id] = { addition: body.addition, card: body.card }
    // 封面这个槽:这份作品传过图就 have(和引擎一样)
    return json(r, 200, { ok: true, id, plot: 'plots/mine', slots: [{ slot: 'card:cover', name: 'cover', need: true, have: S.uploads.some(([w, sl]) => w === id && sl === 'card:cover'), row: { sec: 'card', i: 0 } }] })
  }
  if ((mm = /^\/api\/v1\/local\/templates\/([^/]+)\/publish$/.exec(path))) {
    const wid = decodeURIComponent(mm[1])
    if (m === 'GET') return json(r, 200, { checks: { ok: true, problems: [] }, signed_in: true })
    const prev = Object.values(S.works).find(w => w.source === wid)
    if (prev) {   // 同一件作品出新版本:已上架的旧版照常在线
      prev.revision++
      const live = prev.status === 'published'
      prev.review = { state: 'pending', autopass_at: '2026-10-24T12:30:00Z' }
      return json(r, 200, { id: prev.id, revision: prev.revision, zone: 'reviewed', review: prev.review, message: live ? '改版已提交:新版本进审核队列,旧版照常在线' : '新版本已提交,顶掉了排队的那一版' })
    }
    const pid = `${wid}-${(0xabc000 + Object.keys(S.works).length).toString(16)}`
    S.works[pid] = { id: pid, ref: `hub/template/${pid}`, source: wid, zone: 'reviewed', status: 'draft', revision: 1, meta: { title: { zh: (S.saved[wid].card.zh || {}).title || wid } }, review: { state: 'pending', autopass_at: '2026-10-24T12:30:00Z' } }
    return json(r, 200, { id: pid, revision: 1, zone: 'reviewed', review: { state: 'pending' }, message: '已提交到默认区审核' })
  }
  if (path === '/api/v1/local/hub/mine') return json(r, 200, { works: Object.values(S.works) })
  if (path === '/api/v1/local/hub/withdraw') return json(r, 200, { ok: true })
  if (path.startsWith('/api/v1/local/ai/')) return json(r, 404, {})
  return json(r, 200, {})
})
const shot = async n => { if (shots) await p.screenshot({ path: `${shots}/${mode}-${n}.png`, fullPage: true }) }
const out = { errs, mode }
const val = sel => p.$eval(sel, el => el.value)
const pace = () => p.$eval('[data-orch-choice][aria-checked="true"]', el => el.dataset.orchChoice).catch(() => '')
const saveNow = async () => {
  await p.click('[data-cf-save]')
  await p.waitForFunction(() => { const b = document.querySelector('[data-cf-submit]'); return b && !b.disabled })
  await p.waitForTimeout(300)
}
const submit = async () => {
  await p.click('[data-cf-submit]')
  await p.waitForSelector('.sheet [data-cf-submit-go]:not([disabled])', { timeout: 15000 }).catch(async e => { throw new Error('submit stays off: ' + (await p.textContent('.sheet')).replace(/\s+/g, ' ').slice(0, 600)) })
  await p.click('.sheet [data-cf-submit-go]')
  await p.waitForFunction(() => /已提交|改版已提交|新版本已提交/.test((document.querySelector('.sheet') || {}).textContent || ''))
  const t = await p.textContent('.sheet')
  await p.click('.sheet a[href="#/me"]')
  return t
}
const toDesk = async () => { await p.waitForSelector('[data-cf-card="zh.title"]'); await p.waitForTimeout(300) }

// 1. 草稿:填 → 存 → 整页重开,都还在
await p.goto('http://hub.test/#/t/stoneford-town/create')
await toDesk()
for (const [lg, t] of [['zh', '雾夜猎人'], ['en', 'The Fog Hunter'], ['ja', '霧夜の猟師'], ['ko', '안개 밤의 사냥꾼']]) await p.fill(`[data-cf-card="${lg}.title"]`, t)
await p.fill('[data-cf-card="zh.pitch"]', '雾里有人在追脚印。')
await p.fill('[data-sec="soul"][data-name="name"]', '阿青')
await p.fill('[data-sec="soul"][data-name="persona"]', '沉默的猎人')
await p.waitForSelector('[data-orch-choice="quick"]')
await p.click('[data-orch-choice="quick"]')
await p.setInputFiles('[data-cf-img][data-sec="card"]', { name: 'cover.png', mimeType: 'image/png', buffer: PNG })
await saveNow()
out.firstSave = S.saved['stoneford-town-mine']
out.coverUploads1 = S.uploads.filter(([, s]) => s === 'card:cover').length
await p.reload()
await toDesk()
out.reopened = { zh: await val('[data-cf-card="zh.title"]'), ko: await val('[data-cf-card="ko.title"]'), soul: await val('[data-sec="soul"][data-name="name"]'), pace: await pace() }
await shot('01-draft-reopened')
// 2. 继续编辑:改标题 · 换角色 · 节奏改回「照常」· 换封面 → 再存
await p.fill('[data-cf-card="zh.title"]', '雾夜猎人 · 改')
await p.fill('[data-sec="soul"][data-name="name"]', '阿白')
await p.click('[data-orch-choice="normal"]')
await p.setInputFiles('[data-cf-img][data-sec="card"]', { name: 'cover2.png', mimeType: 'image/png', buffer: Buffer.concat([PNG, Buffer.from([1])]) })
await saveNow()
out.secondSave = S.saved['stoneford-town-mine']
out.coverUploads2 = S.uploads.filter(([, s]) => s === 'card:cover').length
// 3. 提交 → 审核中 →「改版再提交」回到这一份,改了再提交:同一件作品的新版本
out.submit1 = await submit()
await p.waitForSelector('.meworks .meitem.wk')
out.revise = await p.$eval('.meworks .meitem.wk a[href*="/create"]', a => a.getAttribute('href'))
await p.click('.meworks .meitem.wk a[href*="/create"]')
await toDesk()
out.revisedOpen = await val('[data-cf-card="zh.title"]')
await p.fill('[data-sec="soul"][data-name="persona"]', '沉默的猎人,改了一句')
await saveNow()
out.submit2 = await submit()
// 4. 上架以后(快审通过)再改版:提示旧版照常在线;「我的作品」里写「旧版在线 · 审核中」
const w = Object.values(S.works)[0]
Object.assign(w, { status: 'published', review: { state: 'approved' } })
await p.evaluate(() => { location.hash = '#/' })
await p.goto('http://hub.test/#/me')
await p.waitForSelector('.meworks .meitem.wk a[href*="/create"]')
await p.click('.meworks .meitem.wk a[href*="/create"]')
await toDesk()
await p.fill('[data-cf-card="zh.pitch"]', '雾里有人在追脚印,第二版。')
await saveNow()
out.submit3 = await submit()
await p.waitForFunction(() => /旧版在线/.test((document.querySelector('.meworks') || {}).textContent || ''))
out.mineAfter = await p.$eval('.meworks', el => el.textContent.replace(/\s+/g, ' '))
await shot('02-my-works-new-version')
out.works = Object.values(S.works).map(x => [x.id, x.revision])
// 5. 同一模板另起一份:改它,第一份的草稿不变
await p.click('.meworks .menew summary')
const href = await p.$eval('.meworks .menew [data-wk-new="stoneford-town"]', a => a.getAttribute('href'))
out.second = new URLSearchParams(href.split('?')[1]).get('w')
await p.click('.meworks .menew [data-wk-new="stoneford-town"]')
await toDesk()
await p.fill('[data-cf-card="zh.title"]', '雾里的第二封信')
await p.fill('[data-cf-card="zh.pitch"]', '另一个故事。')
await p.fill('[data-sec="soul"][data-name="name"]', '阿黑')
await p.fill('[data-sec="soul"][data-name="persona"]', '船夫')
await saveNow()
await p.goto('http://hub.test/#/t/stoneford-town/create')
await toDesk()
out.firstStill = { zh: await val('[data-cf-card="zh.title"]'), soul: await val('[data-sec="soul"][data-name="name"]') }
out.secondSaved = S.saved[out.second]
await b.close()
console.log(JSON.stringify(out))
