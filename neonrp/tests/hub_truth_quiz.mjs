// tests/test_hub_truth_quiz.py 用:创作台「真相三问」一条走完 —— 编辑 → 点生成 → 改 → 检查 → 存(truth-quiz 代理 10-18)。
//   node tests/hub_truth_quiz.mjs <引擎地址> <page.html> <playwright 所在的 package.json> <截图目录>
// 页面(index.html + truthquiz.js + hub.js)由这里供给,其余请求全走 pytest 起的真引擎(模型在引擎里被换成假的)。
import { createRequire } from 'module'
import { readFileSync, mkdirSync } from 'fs'
import { join } from 'path'

const [base, html, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
mkdirSync(shots, { recursive: true })
const page0 = readFileSync(html, 'utf-8')
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 1280, height: 1000 } })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh') } catch { /* no storage */ } })
const p = await ctx.newPage()
const errs = [], out = {}
p.on('pageerror', e => errs.push(e.message))
p.on('dialog', d => d.accept())
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.origin !== base) return r.abort()
  if (u.pathname === '/__hub.html') return r.fulfill({ status: 200, contentType: 'text/html', body: page0 })
  return r.continue()
})
const shot = async (name, sel) => { const el = sel ? p.locator(sel).first() : p; await el.screenshot({ path: join(shots, name), ...(sel ? {} : { fullPage: true }) }) }
try {
  await p.goto(`${base}/__hub.html#/t/guixiang/create`)
  await p.waitForSelector('[data-tq-root]', { timeout: 120000 })
  out.blank = await p.locator('[data-tq="q"]').count()
  await shot('01-blank.png', '[data-tq-root]')
  // 1 编辑:先手写第一题,再点生成(覆盖要确认 → 接受)
  await p.fill('[data-tq="q"][data-i="0"]', '手写的题')
  await p.fill('[data-cf-reveal]', '族长把祠堂的钥匙藏进了井里,怕人看见族谱最后一页。')
  await p.click('[data-tq-gen]')
  await p.waitForFunction(() => /生成好了/.test((document.querySelector('[data-tq-msg]') || {}).textContent || ''), null, { timeout: 60000 })
  out.generated = await p.inputValue('[data-tq="q"][data-i="0"]')
  await shot('02-generated.png', '[data-tq-root]')
  // 2 改:第一题改字,第二题换正确答案,看英文那一份
  await p.fill('[data-tq="q"][data-i="0"]', '是谁把祠堂钥匙藏进井里的?')
  await p.check('[data-tq="ans"][data-i="1"][data-j="1"]')
  await p.click('[data-tq-lang="en"]')
  out.en = await p.inputValue('[data-tq="q"][data-i="0"]')
  await p.click('[data-tq-lang="zh"]')
  await p.click('[data-tq-pv]')
  out.preview = await p.locator('[data-tq-preview] li').allTextContents()
  out.pvHint = (await p.textContent('[data-tq-preview] .note')).trim()
  await shot('03-preview.png', '[data-tq-root]')
  // 3 检查:别的必填(卡面 · 结局 · 规则)也写上
  const fillIf = async (sel, v) => { if (await p.locator(sel).count()) await p.fill(sel, v) }
  await fillIf('[data-cf-card="zh.title"]', '井里的钥匙')
  await fillIf('[data-cf-card="zh.pitch"]', '冬至夜,祠堂的钥匙不见了。')
  await fillIf('[data-cf][data-sec="ending"][data-name="title"]', '开祠堂')
  if (await p.locator('[data-cf][data-sec="ending"][data-name="kind"]').count()) await p.selectOption('[data-cf][data-sec="ending"][data-name="kind"]', 'true')
  await p.click('[data-cf-check]')
  await p.waitForFunction(() => !/检查中/.test((document.querySelector('[data-cf-msg]') || {}).textContent || '') && ((document.querySelector('[data-cf-msg]') || {}).textContent || '').trim(), null, { timeout: 60000 })
  out.check = (await p.locator('[data-cf-msg]').textContent()).trim()
  // 4 存
  const t0 = Date.now()
  await p.click('[data-cf-save]')
  // 存 = creation/work(写 plot)→ 传图;等「正在存」结束(机器忙时冷拷贝模板要一两分钟)
  await p.waitForFunction(() => { const m = (document.querySelector('[data-cf-msg]') || {}).textContent || ''; return m.trim() && !/正在存|检查中/.test(m) }, null, { timeout: 300000 })
  out.saveMs = Date.now() - t0
  out.save = (await p.locator('[data-cf-msg]').textContent()).trim()
  await shot('04-saved.png')
} catch (e) {
  errs.push(String(e && e.message || e))
  await shot('99-failed.png').catch(() => {})
}
await b.close()
console.log(JSON.stringify({ errs, ...out }))
