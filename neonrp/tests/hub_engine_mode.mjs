// tests/test_hub_catalog.py 用:在「引擎模式」下打开 Hub(hub/index.html + hub.js),引擎接口用 page.route 假装,
// 读每张世界卡和详情页上的区域标,打印成 JSON。
//   node tests/hub_engine_mode.mjs <page.html> <templates.json> <playwright 所在的 package.json>
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, payload, pkg, progressFile, uiLang] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const listObj = JSON.parse(readFileSync(payload, 'utf-8'))
const assets = listObj._assets || {}
const apiBodies = listObj._api || {}   // 其他引擎接口的假返回:路径 → JSON
delete listObj._assets
delete listObj._api
const list = JSON.stringify(listObj)
const progress = progressFile ? readFileSync(progressFile, 'utf-8') : null
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } })
await ctx.addInitScript(lg => { try { localStorage.setItem('wl.hub.lang', lg) } catch { /* no storage */ } }, uiLang || 'zh')
const p = await ctx.newPage()
const errs = []
p.on('pageerror', e => errs.push(e.message))
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname === '/api/v1/local/templates') return r.fulfill({ contentType: 'application/json', body: list })
  if (u.pathname === '/api/v1/local/player-data') return progress ? r.fulfill({ contentType: 'application/json', body: progress }) : r.fulfill({ status: 404, body: '' })
  const m = u.pathname.match(/^\/api\/v1\/local\/templates\/([^/]+)\/assets$/)   // 角色立绘槽:测试给了就用(和引擎 asset_slots 同形)
  if (m && assets[decodeURIComponent(m[1])]) return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ slots: assets[decodeURIComponent(m[1])] }) })
  if (apiBodies[u.pathname]) return r.fulfill({ contentType: 'application/json', body: JSON.stringify(apiBodies[u.pathname]) })
  if (u.pathname.startsWith('/api/')) return r.fulfill({ contentType: 'application/json', body: '{}' })
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
await p.goto('http://hub.test/#/')
await p.waitForSelector('.cards .wcard')
const cards = await p.$$eval('.cards .wcard', a => a.map(x => {
  const v = x.querySelector('.head .ver')
  return { id: decodeURIComponent(x.getAttribute('href').slice(4)), cls: v ? v.className : '', text: v ? v.textContent.trim() : '', title: x.querySelector('h3').textContent }
}))
// 开源区入口:切过去看 zone=open 的作品(没有就是空状态说明),再切回来
const zoneBtn = !!(await p.$('[data-zone]'))
let open = null
if (zoneBtn) {
  await p.click('.tyrow [data-zone]')
  await p.waitForTimeout(200)
  open = { cards: await p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, '')))), empty: !!(await p.$('.openempty')), url: p.url() }
}
const detail = {}, avsw = []
for (const c of cards) {
  await p.goto(`http://hub.test/#/t/${encodeURIComponent(c.id)}`)
  await p.waitForSelector('.hero .note')
  detail[c.id] = (await p.$eval('.hero .note', e => e.textContent)).trim()
  if (await p.$('[data-avstart]')) avsw.push(c.id)
}
// 角色页:默认只列已获得的;切到「可获得」后没获得的是灰的
const soulsView = async q => { await p.goto(`http://hub.test/#/souls${q}`); await p.waitForTimeout(200)
  return { cards: await p.$$eval('.cards.souls > a', a => a.length), locked: await p.$$eval('.cards.souls > a.locked', a => a.length), empty: !!(await p.$('.openempty')),
    names: await p.$$eval('.cards.souls > a', a => a.map(x => x.querySelector('h3').textContent)), go: await p.$$eval('.cards.souls [data-chatgo]', a => a.map(x => x.dataset.chatgo)) } }
const souls = { owned: await soulsView(''), all: await soulsView('?all=1') }
// 详情页角色栏上标「可以直接聊」的角色名
// 以及每个角色「和 ta 聊聊」的地址(chat.html?tpl=&sid=)
const chat = {}, chatgo = {}
for (const c of cards) { await p.goto(`http://hub.test/#/t/${encodeURIComponent(c.id)}`); await p.waitForSelector('.hero .note')
  chat[c.id] = await p.$$eval('.soul', a => a.filter(x => x.querySelector('.chatok')).map(x => x.querySelector('b').textContent))
  chatgo[c.id] = await p.$$eval('.soul a.chatgo', a => a.map(x => x.getAttribute('href'))) }
// 角色列表卡上的「和 ta 聊聊」:点它进聊天页(不是进角色详情)
await p.goto('http://hub.test/#/souls?all=1'); await p.waitForTimeout(200)
const cardgo = await p.$$eval('.cards.souls [data-chatgo]', a => a.map(x => x.dataset.chatgo))
let clicked = null
if (cardgo.length) { await Promise.all([p.waitForURL(/chat\.html/), p.click('.cards.souls [data-chatgo]')]); clicked = p.url() }
// 没获得的角色详情:「怎么获得」那一段(乐师 = 香料魔女的同伴)
await p.goto(`http://hub.test/#/s/${encodeURIComponent('乐师')}`); await p.waitForTimeout(200)
const how = await p.$eval('.how', e => e.textContent).catch(() => null)
const soulgo = await p.$$eval('.ctas a.chatgo', a => a.map(x => x.getAttribute('href')))
const note = await p.$eval('.hero .info .note', e => e.textContent).catch(() => null)
// 我的:分身名 · 继续世界 / 继续聊天的条数
await p.goto('http://hub.test/#/me'); await p.waitForTimeout(300)
const me = { avatar: await p.$eval('.mebox h3', e => e.textContent).catch(() => null), sums: await p.$$eval('.medet summary', a => a.map(x => x.textContent)),
  chats: await p.$$eval('.medet .meitem', a => a.map(x => x.getAttribute('href'))) }
await b.close()
console.log(JSON.stringify({ cards, detail, avsw, zoneBtn, open, souls, chat, chatgo: { cast: chatgo, cards: cardgo, clicked, soul: soulgo, note }, how, me, errs }))
