// tests/test_hub_create_autofill.py 用:创作台「用 AI 填其他语言」一条走完 —— 只写中文 → 点按钮补其他语言(手写格不动)→ 再改中文 →
//   「存」之前自动补过时的格 → 模型不可用时照原样存(niko 10-25)。
//   node tests/hub_create_autofill.mjs <引擎地址> <page.html> <playwright 所在的 package.json> <截图目录>
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
const dialogs = []
p.on('dialog', d => { dialogs.push(d.message()); d.accept() })
const serve = r => {
  const u = new URL(r.request().url())
  if (u.origin !== base) return r.abort()
  if (u.pathname === '/__hub.html') return r.fulfill({ status: 200, contentType: 'text/html', body: page0 })
  if (u.pathname === '/__ios.html') return r.fulfill({ status: 200, contentType: 'text/html', body: page0.replace('window.HUB={"mode":"auto"}', 'window.HUB={"mode":"auto","noPayLinks":true}') })
  return r.continue()
}
await p.route('**/*', serve)
const shot = async (name, sel) => { const el = sel ? p.locator(sel).first() : p; await el.screenshot({ path: join(shots, name), ...(sel ? {} : { fullPage: true }) }) }
const val = sel => p.inputValue(sel)
const card = async () => Object.fromEntries(await Promise.all(['zh', 'en', 'ja', 'ko'].flatMap(lg => ['title', 'pitch'].map(async k => [`${lg}.${k}`, await val(`[data-cf-card="${lg}.${k}"]`)]))))
const idle = () => p.waitForFunction(() => { const m = (document.querySelector('[data-cf-msg]') || {}).textContent || ''; return m.trim() && !/正在存|检查中|正在填/.test(m) }, null, { timeout: 300000 })
try {
  await p.goto(`${base}/__hub.html#/t/guixiang/create`)
  await p.waitForSelector('[data-cf-fill]', { timeout: 120000 })
  out.fillLabel = (await p.textContent('[data-cf-fill]')).trim()
  out.fillNote = (await p.textContent('.cffill .note')).trim()
  out.prefill = await card()
  // 1 只写中文(卡面 + 第一道题),日文标题自己改 = 手写
  await p.fill('[data-cf-card="zh.title"]', '井里的钥匙')
  await p.fill('[data-cf-card="zh.pitch"]', '冬至夜,祠堂的钥匙不见了。')
  await p.fill('[data-cf-card="ja.title"]', '井戸の鍵')
  // 真相三问:按谜底生成(四种语言),再把第一题的韩文清掉 = 空着的语言
  await p.fill('[data-cf-reveal]', '族长把祠堂的钥匙藏进了井里,怕人看见族谱最后一页。')
  await p.click('[data-tq-gen]')
  await p.waitForFunction(() => /生成好了/.test((document.querySelector('[data-tq-msg]') || {}).textContent || ''), null, { timeout: 60000 })
  await p.click('[data-tq-lang="ko"]')
  await p.fill('[data-tq="q"][data-i="0"]', '')
  await p.click('[data-tq-lang="zh"]')
  await shot('01-written.png', '.cfrow')
  // 2 点「用 AI 填其他语言」
  await p.click('[data-cf-fill]')
  await p.waitForSelector('[data-cf-fillmsg]', { timeout: 60000 })
  out.fillMsg = (await p.textContent('[data-cf-fillmsg]')).trim()
  out.filled = await card()
  out.marks = await p.locator('[data-cf-mark]').evaluateAll(els => els.map(e => [e.closest('label').querySelector('input').dataset.cfCard, e.dataset.cfMark]))
  await p.click('[data-tq-lang="ko"]')
  out.tqKo = await val('[data-tq="q"][data-i="0"]')
  await p.click('[data-tq-lang="zh"]')
  await shot('02-filled.png', '.cfrow')
  // 3 再改中文标题 → 存:存之前自动重写过时的(不是手写的)格
  await p.fill('[data-cf-card="zh.title"]', '井里的第二把钥匙')
  await p.fill('[data-cf][data-sec="ending"][data-name="title"]', '开祠堂')
  if (await p.locator('[data-cf][data-sec="ending"][data-name="kind"]').count()) await p.selectOption('[data-cf][data-sec="ending"][data-name="kind"]', 'true')
  await p.click('[data-cf-save]')
  await idle()
  out.save = (await p.locator('[data-cf-msg]').textContent()).trim()
  out.saved = await card()
  out.saveFillMsg = (await p.locator('[data-cf-fillmsg]').count()) ? (await p.textContent('[data-cf-fillmsg]')).trim() : ''
  await shot('03-saved.png')
  // 4 模型不可用:清掉英文简介再存 —— 不挡存,说一句
  await p.fill('[data-cf-card="zh.pitch"]', 'NOMODEL 冬至夜。')
  await p.click('[data-cf-save]')
  await idle()
  out.save2 = (await p.locator('[data-cf-msg]').textContent()).trim()
  out.save2FillMsg = (await p.textContent('[data-cf-fillmsg]')).trim()
  out.after2 = await card()
  await shot('04-no-model.png')
  // 5 「AI 填空着的栏」:只写空栏(结局正文 · 线索 · 规则说明),写过的不动
  await p.click('[data-cf-aiall]')
  await p.waitForSelector('[data-cf-aimsg]', { timeout: 60000 })
  out.aiMsg = (await p.textContent('[data-cf-aimsg]')).trim()
  out.endText = await val('[data-cf][data-sec="ending"][data-name="text"]')
  out.endTitle = await val('[data-cf][data-sec="ending"][data-name="title"]')
  out.clue = await val('[data-cf][data-sec="clue"][data-name="summary"]')
  out.aiMarks = await p.locator('.cfrow [data-cf-mark="ai"]').count()
  await shot('05-ai-all.png')
  // 6 单栏 ✦ 改写作者写的结局名:先问一句
  await p.click('[data-cf-ai="ending.0.title"]')
  await p.waitForFunction(() => /^AI·/.test((document.querySelector('[data-cf][data-sec="ending"][data-name="title"]') || {}).value || ''), null, { timeout: 60000 })
  out.endTitle2 = await val('[data-cf][data-sec="ending"][data-name="title"]')
  out.dialogs = [...dialogs]
  await p.click('[data-cf-save]')
  await idle()
  out.save3 = (await p.locator('[data-cf-msg]').textContent()).trim()
  // 7 额度不够:说一句 + 去充值(网页 / 本地 = billing 的链接)
  await p.fill('[data-cf-reveal]', 'NOCREDIT 族长藏了钥匙。')
  await p.click('[data-cf-ai="reveal"]')
  await p.waitForFunction(() => /额度不够/.test((document.querySelector('[data-cf-aimsg]') || {}).textContent || ''), null, { timeout: 60000 })
  out.broke = (await p.textContent('[data-cf-aimsg]')).trim()
  out.brokeHref = await p.getAttribute('[data-cf-aimsg] a', 'href')
  out.revealAfter = await p.inputValue('[data-cf-reveal]')
  await shot('06-credits.png', '.cfaiall')
  // 8 iOS:App 内方案页(wlNative.plans),绝不出外部付款链接
  const q = globalThis.Q = await ctx.newPage()
  q.on('pageerror', e => errs.push('ios: ' + e.message))
  q.on('dialog', d => d.accept())
  await q.route('**/*', serve)
  await q.addInitScript(() => { window.wlNative = { plans() { window.__plans = (window.__plans || 0) + 1 } } })
  await q.goto(`${base}/__ios.html#/t/guixiang/create`)
  await q.waitForSelector('[data-cf-reveal]', { timeout: 120000 })
  await q.fill('[data-cf-reveal]', 'NOCREDIT 真相')
  await q.click('[data-cf-ai="reveal"]')
  await q.waitForSelector('[data-cf-upgrade]', { timeout: 60000 })
  out.iosLinks = await q.locator('[data-cf-aimsg] a').count()
  await q.click('[data-cf-upgrade]')
  out.iosPlans = await q.evaluate(() => window.__plans || 0)
} catch (e) {
  errs.push(String(e && e.message || e))
  await shot('99-failed.png').catch(() => {})
  if (globalThis.Q) await globalThis.Q.screenshot({ path: join(shots, '99-ios.png'), fullPage: true }).catch(() => {})
}
await b.close()
console.log(JSON.stringify({ errs, ...out }))
