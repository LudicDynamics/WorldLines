// tests/test_hub_collection.py 用:线上(静态)Hub 登录后的收集区读账号上的 data hub/collection(10-18,COLLECTION-SYNC-1018);
// 自由区作品不进角色收集。data.test 是假的 data 服务(两页 + 一条重复),auth.test 只回 /v1/me。
//   node tests/hub_collection.mjs <hub/index.html> <hub/hub.js> <playwright 所在的 package.json> <截图目录>
import { createRequire } from 'module'
import { existsSync, readFileSync } from 'fs'
import { dirname, resolve } from 'path'

const [htmlF, jsF, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const html = readFileSync(htmlF, 'utf-8'), js = readFileSync(jsF, 'utf-8')
const ART = resolve(dirname(htmlF), '../../../templates/pct-house.template/plots/P01/assets/ending-E01.webp')   // 卡图 = 模板里那张结局图(仓库里没有就 1px)
const PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkqPhfDwAEJwHG2Ar9pAAAAABJRU5ErkJggg=='
const web = html.replace('<!--SCRIPT-->', () => `<script>window.HUB=${JSON.stringify({ mode: 'static', catalog: 'catalog.json', auth: 'https://auth.test', billing: 'https://billing.test', ai: 'https://ai.test/v1', data: 'https://data.test' })}</script><script>${js}</script>`)
const catalog = { templates: [
  { id: 'pct-house', title: { zh: '灰橡宅 · 关上的门', en: 'Greyoak House' }, pitch: { zh: 'p' }, lang: 'zh', tags: {}, endings: [], zone: 'reviewed',
    cast: [{ sid: 'butler', name: { zh: '奥斯温', en: 'Oswin' }, img: null, role: 'npc' }],
    rewards: [{ id: 'behind_the_wall', img: 'img/pct-house/cards/behind_the_wall.webp' }, { id: 'half_burnt_diary', img: null }] },
  { id: 'free-work-1a2b3c', title: { zh: '自由区的作品' }, pitch: { zh: 'p' }, lang: 'zh', tags: {}, endings: [], zone: 'open',
    cast: [{ sid: 'stranger', name: { zh: '自由区的陌生人' }, img: null, role: 'npc' }] },
] }
const T = '2026-10-18T01:00:00Z'
const rec = (id, body) => ({ id, rev: 1, body: { v: 1, at: T, updated: T, ...body } })
const L = (zh, en) => ({ zh, en, ja: zh, ko: zh })
const page1 = [
  rec('r1', { type: 'card', world: 'pct-house', key: 'behind_the_wall', version: '0.2', card: { kind: 'card', rarity: 'epic', title: L('墙后的人', 'The One Behind the Wall'), desc: L('你把真相说出了口。', 'You said the truth out loud.'), image_slot: 'plot:plots/P01:ending:E01' } }),
  rec('r2', { type: 'card', world: 'pct-house', key: 'half_burnt_diary', version: '0.2', card: { kind: 'card', rarity: 'common', title: L('烧了一半的日记', 'The Half-Burnt Diary') } }),
  rec('r3', { type: 'character', world: 'pct-house', key: 'butler', version: '0.2', character: { sid: 'butler', name: '奥斯温', how: 'companion_at_ending', memory: 'full' } }),
]
const page2 = [
  rec('r4', { type: 'achievement', world: 'pct-house', key: 'walked_out', achievement: { id: 'walked_out', scope: 'world', points: 10, title: L('另一扇门', 'Another Door'), desc: L('没有揭开全部真相,但活着走了出来。', 'Left without the whole truth, but alive.') } }),
  rec('r5', { type: 'run', world: 'pct-house', key: 'run-1', run: { run: 'run-1', exit: 'ending', ending: 'E02' } }),
  // the same card again, older (two devices at once): the newer one above is shown
  rec('r6', { type: 'card', world: 'pct-house', key: 'behind_the_wall', updated: '2026-10-01T00:00:00Z', card: { kind: 'card', rarity: 'epic', title: L('旧卡面', 'Old face') } }),
]
const b = await chromium.launch()
const out = { errs: [] }
async function open(lang, { data = 'ok', signed = true, width = 1280 } = {}) {
  const ctx = await b.newContext({ viewport: { width, height: 900 } })
  await ctx.addInitScript(([l, s]) => {
    localStorage.setItem('wl.hub.lang', l); localStorage.setItem('wl.hub.intro', '1')
    if (s) localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok', refresh: 'r1', exp: Date.now() + 3600e3, user: { display_name: 'Niko', email: 'n@x.test' } }))
  }, [lang, signed])
  const p = await ctx.newPage()
  p.on('pageerror', e => out.errs.push(e.message))
  const seen = []
  await p.route('**/*', async r => {
    const u = new URL(r.request().url()), m = r.request().method()
    const json = (o, status = 200) => r.fulfill({ status, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(o) })
    if (m === 'OPTIONS') return r.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } })
    if (u.host === 'data.test') {
      seen.push(`${u.pathname}?${u.searchParams.get('scope')}|${u.searchParams.get('cursor') || ''}|${r.request().headers().authorization || ''}`)
      if (data === 'relogin') return json({ error: 'insufficient_scope' }, 403)
      return json(u.searchParams.get('cursor') === 'p2' ? { records: page2, next_cursor: null } : { records: page1, next_cursor: 'p2' })
    }
    if (u.host === 'auth.test' && u.pathname === '/v1/me') return json({ user: { display_name: 'Niko', email: 'n@x.test' } })
    if (u.host.endsWith('.test') && u.host !== 'hub.test') return json({}, 404)
    if (u.host !== 'hub.test') return r.abort()
    if (u.pathname === '/catalog.json') return json(catalog)
    if (u.pathname.endsWith('.webp')) return existsSync(ART) ? r.fulfill({ contentType: 'image/webp', body: readFileSync(ART) }) : r.fulfill({ contentType: 'image/png', body: Buffer.from(PX, 'base64') })
    return r.fulfill({ contentType: 'text/html', body: web })
  })
  return { ctx, p, seen }
}

{
  const { ctx, p, seen } = await open('en')
  await p.goto('https://hub.test/#/me')
  await p.waitForSelector('[data-coll-cards]', { timeout: 15000 })
  out.web = {
    calls: seen,
    cards: await p.$$eval('[data-coll-card]', a => a.map(x => ({ key: x.dataset.collCard, title: x.querySelector('b').textContent, img: (x.querySelector('.ccimg img:not(.sil)') || {}).src || null, pull: !!x.querySelector('[data-coll-pull]') }))),
    roster: await p.$$eval('[data-coll-roster] .metile b', a => a.map(x => x.textContent)),
    party: await p.$$eval('[data-coll-party] .metile b', a => a.map(x => x.textContent)),
    ach: await p.$$eval('.meitem b', a => a.map(x => x.textContent)),
    sync: await p.$eval('[data-coll-sync-state]', x => x.dataset.collSyncState).catch(() => null),
  }
  await (await p.$('.mebox.coll')).screenshot({ path: `${shots}/web-collection-en.png` })
  await p.goto('https://hub.test/#/souls?all=1')
  await p.waitForTimeout(600)
  out.souls = await p.$eval('#app', x => x.textContent)
  await ctx.close()
}
{
  const { ctx, p } = await open('zh', { data: 'relogin', width: 390 })
  await p.goto('https://hub.test/#/me')
  await p.waitForSelector('[data-coll-sync-state]', { timeout: 15000 })
  out.relogin = { state: await p.$eval('[data-coll-sync-state]', x => x.dataset.collSyncState), text: await p.$eval('[data-coll-sync-state]', x => x.textContent),
    hscroll: await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) }
  await (await p.$('.mebox.coll')).screenshot({ path: `${shots}/web-collection-relogin-zh-phone.png` })
  await ctx.close()
}
{
  const { ctx, p, seen } = await open('zh', { signed: false })
  await p.goto('https://hub.test/#/me')
  await p.waitForTimeout(1200)
  out.signedOut = { calls: seen.length }
  await ctx.close()
}
await b.close()
console.log(JSON.stringify(out))
