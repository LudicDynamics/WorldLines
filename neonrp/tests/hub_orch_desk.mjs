// tests/test_hub_orch_view.py 用:真的 Hub 创作台(index.html + orchview.js + truthquiz.js + create_assist.js + hub.js)里挂上的编排系统 ——
// 选一套 → addition.orchestration 跟着变(角色那一行没有选择框) → 检查过 → 存进作品(pack.engine 由 pytest 核对);草稿刷新后还记得选的哪套。
//   node tests/hub_orch_desk.mjs <引擎地址> <page.html> <世界 id> <编排模板的写法:模板 id[?参数=选项]> <playwright 所在的 package.json> <截图目录>
import { createRequire } from 'module'
import { readFileSync, mkdirSync } from 'fs'
import { join } from 'path'

const [base, html, tid, pick, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
mkdirSync(shots, { recursive: true })
const page0 = readFileSync(html, 'utf-8')
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh') } catch { /* no storage */ } })
const p = await ctx.newPage()
const out = { errs: [] }
p.on('pageerror', e => out.errs.push(e.message))
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.origin !== base) return r.abort()
  if (u.pathname === '/__hub.html') return r.fulfill({ status: 200, contentType: 'text/html', body: page0 })
  return r.continue()
})
try {
  await p.goto(`${base}/__hub.html#/t/${tid}/create`)
  await p.waitForSelector('#cf-orch [data-orch-svg]', { timeout: 300000 })
  out.before = await p.evaluate(() => window.WLCreate.addition().orchestration ?? null)
  const [pickId, pickQ] = pick.split('?')
  await p.click(`#cf-orch [data-orch-opt="${pickId}"]`)
  for (const [k, v] of new URLSearchParams(pickQ || '')) await p.click(`#cf-orch [data-orch-param="${k}"][data-orch-choice="${v}"]`)
  out.after = await p.evaluate(() => window.WLCreate.addition().orchestration ?? null)
  out.graph = await p.$eval('#cf-orch [data-orch]', x => x.dataset.orch)
  out.overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  await p.locator('#cf-orch').screenshot({ path: join(shots, '07-desk-390-picked.png') })
  out.rowPickers = await p.locator('[data-cf-sorch]').count()   // 角色那一行没有编排选择(10-19:编排是模板的一整套)
  out.check = await p.evaluate(async t => { const W = window.WLCreate; return W.post(W.path(t, 'creation/check'), { addition: { ...W.addition(), ending: [{ title: '雾散', kind: 'true' }] } }) }, tid)
  out.save = await p.evaluate(async t => { const W = window.WLCreate; return W.post(W.path(t, 'creation/work'), { addition: { ...W.addition(), ending: [{ title: '雾散', kind: 'true' }] }, card: { zh: { title: '雾夜', pitch: '雾里的一夜。' } }, lang: 'zh' }) }, tid)
  await p.reload()
  await p.waitForSelector('#cf-orch [data-orch-svg]', { timeout: 300000 })
  out.reloaded = await p.$eval('#cf-orch [data-orch-opt][aria-checked=true]', x => x.dataset.orchOpt)
  out.reloadedParam = await p.$eval('#cf-orch [data-orch-param][aria-checked=true]', x => x.dataset.orchParam + '=' + x.dataset.orchChoice).catch(() => null)
  // 草稿里没记编排(旧草稿 / 别处存的),但记得作品:向引擎问作品现在按哪套跑
  // (存是直接 POST 的,桌面没记 CF.work:把作品记进草稿,和点「存」之后的草稿一样)
  out.draft = await p.evaluate(([t, wid]) => { const k = `wl.hub.cf.${t}`, d = JSON.parse(localStorage.getItem(k)); const was = d.orch; delete d.orch; d.work = { id: wid, slots: [], map: {}, lint: 0 }; localStorage.setItem(k, JSON.stringify(d)); return was }, [tid, out.save.body.id])
  // 先等引擎回了作品那一问,再等页面画上它答的那套:模板默认就是 two_beat(pace=normal)时,只看「不是 one_beat」会在引擎回话之前就读(10-21 collection 报的时序不稳)
  const asked = p.waitForResponse(r => r.url().includes(`/templates/${encodeURIComponent(out.save.body.id)}/creation/orchestration`), { timeout: 120000 }).catch(() => null)
  await p.reload()
  out.askedWork = !!(await asked)
  const want = [pickId, ...[...new URLSearchParams(pickQ || '')].map(([k, v]) => `${k}=${v}`)]
  await p.waitForFunction(w => {
    const x = document.querySelector('#cf-orch [data-orch-opt][aria-checked=true]')
    const ps = [...document.querySelectorAll('#cf-orch [data-orch-param][aria-checked=true]')].map(y => y.dataset.orchParam + '=' + y.dataset.orchChoice)
    return !!x && x.dataset.orchOpt === w[0] && w.slice(1).every(q => ps.includes(q))
  }, want, { timeout: 120000 }).catch(() => {})
  out.fromWork = await p.$eval('#cf-orch [data-orch-opt][aria-checked=true]', x => x.dataset.orchOpt)
  out.fromWorkParam = await p.$eval('#cf-orch [data-orch-param][aria-checked=true]', x => x.dataset.orchParam + '=' + x.dataset.orchChoice).catch(() => null)
} catch (e) {
  out.errs.push(String(e && e.stack || e))
}
await b.close()
console.log(JSON.stringify(out))
