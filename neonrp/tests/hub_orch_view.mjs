// tests/test_hub_orch_view.py 用:创作台「编排系统」只读执行图(orch-preview 10-18)—— 选编排 → 图跟着换 → 节点拖不动、没有能改的控件;
// 手机宽 390 不横向溢出;本地版有「到编排台编辑」,网页版没有。
//   node tests/hub_orch_view.mjs <引擎地址> <page.html> <orch 目录(网页版的静态图)> <playwright 所在的 package.json> <截图目录>
// 页面 = Hub 的 index.html + orchview.js + 一个最小的挂载;网页版的 orch/<id>.json 由这里供给(= build_static 的产物),本地版走真引擎的路由。
import { createRequire } from 'module'
import { readFileSync, mkdirSync, existsSync } from 'fs'
import { join } from 'path'

const [base, html, orchDir, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
mkdirSync(shots, { recursive: true })
const page0 = readFileSync(html, 'utf-8')
const b = await chromium.launch()
const out = { errs: [] }
async function open(viewport, qs) {
  const ctx = await b.newContext({ viewport, deviceScaleFactor: 2, hasTouch: viewport.width < 500 })
  const p = await ctx.newPage()
  p.on('pageerror', e => out.errs.push(e.message))
  await p.route('**/*', r => {
    const u = new URL(r.request().url())
    if (u.origin !== base) return r.abort()
    if (u.pathname === '/__orch.html') return r.fulfill({ status: 200, contentType: 'text/html', body: page0 })
    if (u.pathname.startsWith('/orch/')) { const f = join(orchDir, u.pathname.slice(6)); return existsSync(f) ? r.fulfill({ status: 200, contentType: 'application/json', body: readFileSync(f, 'utf-8') }) : r.fulfill({ status: 404, body: '' }) }
    return r.continue()
  })
  await p.goto(`${base}/__orch.html?${new URLSearchParams(qs)}`)
  await p.waitForSelector('[data-orch-svg]', { timeout: 60000 })
  return p
}
const nodes = p => p.$$eval('[data-orch-node]', xs => xs.map(x => x.dataset.orchNode))
const shot = (p, name) => p.locator('#cf-orch').screenshot({ path: join(shots, name) })
try {
  // 1 网页 · 手机宽 390:默认选中模板默认的那套
  let p = await open({ width: 390, height: 844 }, { mode: 'web', tid: 'pct-house', lang: 'zh' })
  out.opts = await p.$$eval('[data-orch-opt]', xs => xs.map(x => x.dataset.orchOpt))
  out.checked = await p.$eval('[data-orch-opt][aria-checked=true]', x => x.dataset.orchOpt)
  out.chips = await p.$$eval('[data-orch-param]', xs => xs.map(x => x.dataset.orchParam + '=' + x.dataset.orchChoice + (x.getAttribute('aria-checked') === 'true' ? '*' : '')))
  out.nodesDefault = await nodes(p)
  out.overflow390 = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  out.editWeb = await p.locator('[data-orch-edit]').count()
  await shot(p, '01-web-390-default.png')
  // 节点上的设定:两个节奏各一张图,商量节点上写着它们改到的设定(10-23:以前两个选项的图一模一样)
  const sets = () => p.$$eval('#cf-orch [data-orch-node] [data-orch-setting]', xs => xs.map(x => [x.dataset.orchSetting, x.textContent, x.classList.contains('ch')]))
  out.refNormal = await p.$eval('[data-orch]', x => x.dataset.orchRef)
  out.setsNormal = await sets()
  // 2 换一套:图跟着换,host 拿到选中的 id
  await p.click('[data-orch-param="pace"][data-orch-choice="quick"]')   // 两拍的参数:快商量(10-19 起不是单独一套)
  out.chosenQuick = await p.evaluate(() => window.__chosen)
  out.quickChecked = await p.$eval('[data-orch-param][aria-checked=true]', x => x.dataset.orchChoice)
  out.refQuick = await p.$eval('[data-orch]', x => x.dataset.orchRef)
  out.setsQuick = await sets()
  await p.locator('[data-orch-node="plan"]').click()
  out.detailSets = await p.$$eval('[data-orch-detail] [data-orch-setting]', xs => xs.map(x => [x.dataset.orchSetting, x.textContent, x.classList.contains('ch')]))
  await shot(p, '01b-web-390-quick.png')
  await p.locator('[data-orch-node="plan"]').click()
  await p.click('[data-orch-opt="one_beat"]')
  out.after = await p.$eval('[data-orch]', x => x.dataset.orch)
  out.nodesOneBeat = await nodes(p)
  out.chosen = await p.evaluate(() => window.__chosen)
  out.chipsOneBeat = await p.locator('[data-orch-param]').count()
  await shot(p, '02-web-390-one-beat.png')
  // 3 只读:拖节点不动;容器里没有输入控件、没有可拖的东西
  const n = p.locator('[data-orch-node="combat"]')
  const t0 = await n.getAttribute('transform'), bb = await n.boundingBox()
  await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await p.mouse.down(); await p.mouse.move(bb.x + 120, bb.y + 90, { steps: 6 }); await p.mouse.up()
  out.dragMoved = (await n.getAttribute('transform')) !== t0
  out.controls = await p.$$eval('#cf-orch input, #cf-orch select, #cf-orch textarea, #cf-orch [contenteditable], #cf-orch [draggable=true]', xs => xs.length)
  // 4 点节点看说明
  await p.click('[data-orch-opt="two_beat"]')
  await p.click('[data-orch-zoom="fit"]')
  await p.locator('[data-orch-node="plan"]').click()
  out.detail = await p.$eval('[data-orch-detail]', x => x.dataset.orchDetail)
  out.steps = await p.$$eval('[data-orch-detail] ol li b', xs => xs.map(x => x.textContent))
  await shot(p, '03-web-390-plan-detail.png')
  // 5 缩放
  await p.click('[data-orch-zoom="in"]'); await p.click('[data-orch-zoom="in"]')
  out.zoomed = await p.$eval('[data-orch-pz]', g => g.getAttribute('transform'))
  out.overflowZoom = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  await shot(p, '04-web-390-zoomed.png')
  await p.context().close()
  // 6 本地 · 桌面宽:图来自本机引擎,旁边有「到编排台编辑」
  p = await open({ width: 1180, height: 900 }, { mode: 'local', tid: 'pct-house', lang: 'en' })
  out.editLocal = await p.getAttribute('[data-orch-edit]', 'href')
  out.titleEn = await p.$eval('[aria-checked=true] b', x => x.textContent)
  await p.locator('[data-orch-node="resolve"]').click()
  await shot(p, '05-local-desktop-en.png')
  await p.context().close()
  // 7 日语 / 韩语也有字
  p = await open({ width: 390, height: 844 }, { mode: 'web', tid: 'pct-house', lang: 'ja' })
  out.titleJa = await p.$eval('[aria-checked=true] b', x => x.textContent)
  await shot(p, '06-web-390-ja.png')
  await p.context().close()
} catch (e) {
  out.errs.push(String(e && e.stack || e))
}
await b.close()
console.log(JSON.stringify(out))
