// tests/test_hub_soul_update.py 用:Hub「我的 · 收集区」里角色有新版 → 打开 diff(core/soul_update 的 worldlines.soul-update/1)逐项选、
// 三个一键、按这样更新(POST choices + token)、作者又改了(409)重新拉。引擎接口用 page.route 假装。
//   node tests/hub_soul_update.mjs <page.html> <diff.json> <playwright 所在的 package.json> <截图目录>
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, diffFile, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8'), diffs = JSON.parse(readFileSync(diffFile, 'utf-8')), diff = diffs.zh   // {zh, en}: the engine's diff in each language
const b = await chromium.launch()
const out = { errs: [], posts: [] }
let stale = 0
async function open(lang, width) {
  const ctx = await b.newContext({ viewport: { width, height: 900 } })
  await ctx.addInitScript(l => { try { localStorage.setItem('wl.hub.lang', l) } catch { /* no storage */ } }, lang)
  const p = await ctx.newPage()
  p.on('pageerror', e => out.errs.push(e.message))
  await p.route('**/*', r => {
    const u = new URL(r.request().url()), m = r.request().method()
    if (u.host !== 'hub.test') return r.abort()
    const json = (o, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(o) })
    if (u.pathname === '/api/v1/local/templates') return json({ templates: [{ id: 'pct-house', card: { title: '灰橡宅', pitch: 'p', lang: 'zh' }, mode: { ending: 'multi' }, zone: 'reviewed' }] })
    if (u.pathname === '/api/v1/local/player-data') return json({ characters: [{ sid: 'chara', world: 'pct-house', name: '温妮', how: 'companion_at_ending', memory: 'full', version: '0.2', upd: true }], cards: [], achievements: [], endings: [], talked: [] })
    if (u.pathname.endsWith('/souls/pct-house/chara/update') && m === 'GET') return json(diffs[u.searchParams.get('lang')] || diff)
    if (u.pathname.endsWith('/souls/pct-house/chara/update') && m === 'POST') {
      const body = JSON.parse(r.request().postData() || '{}')
      out.posts.push(body)
      if (stale-- > 0) return json({ error: 'stale' }, 409)
      return json({ ok: true, took: Object.values(body.choices).filter(v => v === 'theirs').length, kept: Object.values(body.choices).filter(v => v === 'mine').length, version: '0.3' })
    }
    if (u.pathname.startsWith('/api/')) return json({})
    if (u.pathname.endsWith('.png')) return r.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkqPhfDwAEJwHG2Ar9pAAAAABJRU5ErkJggg==', 'base64') })
    return r.fulfill({ contentType: 'text/html', body: page0 })
  })
  return { ctx, p }
}
const picks = p => p.$$eval('[data-su-item]', a => a.map(x => [x.dataset.suItem, (x.querySelector('input:checked') || {}).value]))
{
  const { ctx, p } = await open('zh', 1280)
  await p.goto('http://hub.test/#/me')
  await p.waitForSelector('[data-coll-pull]', { timeout: 20000 })
  await p.click('[data-coll-pull]')
  await p.waitForSelector('[data-su-item]')
  out.defaults = await picks(p)
  out.labels = await p.$$eval('[data-su-item] .suhd b', a => a.map(x => x.textContent))
  out.groups = await p.$$eval('.suh h4', a => a.map(x => x.textContent))
  out.both = await p.$$eval('.suitem.both', a => a.length)
  out.chips = await p.$$eval('.suchip.only', a => a.map(x => [x.classList.contains('theirs') ? 'theirs' : 'mine', x.firstChild.textContent, x.querySelector('small').textContent]))
  out.brackets = await p.$$eval('.suside', a => a.some(x => /\[\s*"/.test(x.textContent)))
  await (await p.$('.suh')).screenshot({ path: `${shots}/09-soul-update-diff-zh.png` })
  await p.click('[data-su-all="theirs"]')
  out.allTheirs = await picks(p)
  await p.click('[data-su-all="mine"]')
  out.allMine = await picks(p)
  await p.click('[data-su-all="defaults"]')
  const first = diff.items[0].id
  await p.click(`[data-su-item="${first}"] .suside:first-child`)   // 第一项改成「留我的」
  out.edited = await picks(p)
  stale = 1
  await p.click('[data-su-go]')
  await p.waitForTimeout(500)
  out.afterStale = { open: !!(await p.$('[data-su-item]')), toast: await p.$$eval('.toast', a => a.map(x => x.textContent)) }
  await p.click('[data-su-go]')
  await p.waitForTimeout(500)
  out.afterGo = { open: !!(await p.$('[data-su-item]')), toast: await p.$$eval('.toast', a => a.map(x => x.textContent)) }
  await ctx.close()
}
for (const [lang, width, name] of [['en', 1280, '10-soul-update-diff-en'], ['zh', 390, '11-soul-update-diff-zh-phone'], ['en', 390, '12-soul-update-diff-en-phone']]) {
  const { ctx, p } = await open(lang, width)
  await p.goto('http://hub.test/#/me')
  await p.waitForSelector('[data-coll-pull]', { timeout: 20000 })
  await p.click('[data-coll-pull]')
  await p.waitForSelector('[data-su-item]')
  out[name] = { hscroll: await p.evaluate(() => document.documentElement.scrollWidth - innerWidth), h2: await p.$eval('.suh h2', x => x.textContent),
    labels: await p.$$eval('[data-su-item] .suhd b', a => a.map(x => x.textContent)) }
  await (await p.$('.suh')).screenshot({ path: `${shots}/${name}.png` })
  await ctx.close()
}
await b.close()
console.log(JSON.stringify(out))
