// 网页 Hub 默认区创作台(web-create 10-18 · PLATFORM-PLAY-RULES-1015 §2):Hub 详情页 → 创作台(表单来自 catalog 的 creation.form)
// → 填(卡面 · 新角色 + 立绘 · 结局 · 线索 · 规则)→ 检查(浏览器里的引擎,play/engine.html)→ 刷新草稿还在 → 存(作品 stoneford-town-mine
// + 传图 + 发布前检查)→ 试玩(浏览器版 play/?tpl=<作品>&base=<模板>,假模型说一句)→ 回来提交到默认区(协议写在提交页上;六步全部拦在本机,
// 不发真平台)→ 「我的作品」默认区:审核中 · 撤回。
//   WL_PLAY_PORT=8796 WL_PLAY_AI_PORT=8797 · 构建时 --ai / --auth / --billing / --platform 指到 http://127.0.0.1:8797 · WL_PLAY_SHOTS=<截图目录>
//   平台(identity / storage)是 serve.py 里的假平台:浏览器里的引擎在 Service Worker 控制的 iframe 里,WebKit 下 Playwright 拦不到它的请求,
//   所以不靠 route,构建时 --platform 把页面和引擎都指到本机(10-21 create-art)。任何请求打到 *.worldlines.gg 测试就失败。
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const AI = `http://127.0.0.1:${process.env.WL_PLAY_AI_PORT || '8611'}`
const plat = async () => (await (await fetch(`${AI}/_plat/state`)).json()) as { steps: string[], bodies: Record<string, any>, puts: Record<string, string> }
const SHOTS = process.env.WL_PLAY_SHOTS || '../test-results/create-shots'
mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true })
const mock = (mode: string, reset = false) => fetch(`${AI}/_mock/mode`, { method: 'POST', body: JSON.stringify({ mode, reset }) })
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64')

test('网页创作台:开表单 → 填 → 检查 → 存 → 试玩 → 提交到默认区 → 我的作品', async ({ page, context }) => {
  test.setTimeout(900_000)
  await context.addInitScript(() => {
    try {
      if (!localStorage.getItem('wl.hub.auth')) localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok-e2e', exp: Date.now() + 3600e3, refresh: 'r-e2e', user: { id: 'u-e2e', display_name: 'e2e' } }))
      localStorage.setItem('wl.play.ackCharge', '1')
    } catch { /* blocked */ }
  })
  await mock('ok', true)
  // 一个请求都不许出本机:打到线上平台(*.worldlines.gg)的一律拦下、记下,最后断言为空
  const leaks: string[] = []
  context.on('request', r => { if (/(^|\.)worldlines\.gg$/.test(new URL(r.url()).hostname)) leaks.push(`${r.method()} ${r.url()}`) })
  await context.route(/^https?:\/\/([a-z0-9-]+\.)*worldlines\.gg\//, r => r.abort())
  // 每条测试一个空平台:上一条(另一个浏览器)留下的作品在,引擎会把这次当成「已在默认区的作品再提交」,publish 不带 zone(core/template_publish keep)
  await fetch(`${AI}/_plat/reset`, { method: 'POST', body: JSON.stringify({ all: true }) })

  // 1. 详情页:模板开放了创作层、世界能在浏览器里跑 → 「在这个模板上创作」直接开网页创作台(不再引导去本地版)
  await page.goto('/#/t/stoneford-town')
  const go = page.locator('a[href="#/t/stoneford-town/create"]')
  await expect(go).toBeVisible()
  await shot(page, '01-detail')
  await go.click()
  await expect(page.locator('h1')).toContainText('有限创作台')
  await expect(page.locator('.cfeng.ready')).toBeVisible({ timeout: 360_000 })   // 浏览器里的引擎(看不见的 iframe)起来了
  await shot(page, '02-form-empty')

  // 2. 填:卡面(中文必填)· 新角色 + 立绘 · 结局 · 线索 · 规则(说到「脚印」→ 走向结局 #1)
  await page.fill('[data-cf-card="zh.title"]', '雾夜猎人')
  await page.fill('[data-cf-card="zh.pitch"]', '雾里有人在追一串脚印。')
  await page.fill('[data-cf-card="en.title"]', 'The Fog Hunter')
  await page.fill('[data-sec="soul"][data-name="name"]', '阿青')
  await page.fill('[data-sec="soul"][data-name="persona"]', '沉默的猎人,只跟着脚印走')
  await page.setInputFiles('[data-cf-img][data-sec="soul"]', { name: 'aqing.png', mimeType: 'image/png', buffer: PNG })
  await page.fill('[data-sec="ending"][data-name="title"]', '雾散')
  await page.selectOption('[data-sec="ending"][data-name="kind"]', 'true')
  await page.fill('[data-sec="clue"][data-name="name"]', '脚印')
  await page.fill('[data-sec="clue"][data-name="summary"]', '泥里一串往北去的脚印')
  await page.selectOption('[data-sec="rule"][data-name="trigger_ui.when"]', 'text')
  await page.fill('[data-sec="rule"][data-name="trigger_ui.kw"]', '脚印')
  await page.selectOption('[data-sec="rule"][data-name="trigger_ui.then"]', 'end')
  await page.selectOption('[data-sec="rule"][data-name="trigger_ui.tv"]', '#1')

  // 3. 检查(引擎 creation/check)
  await page.click('[data-cf-check]')
  await expect(page.locator('[data-cf-msg]')).toContainText('检查通过', { timeout: 120_000 })
  await shot(page, '03-filled-checked')

  // 草稿存在这个浏览器里:刷新以后表单和还没传的图都还在
  await page.reload()
  await expect(page.locator('[data-sec="soul"][data-name="name"]')).toHaveValue('阿青')
  await expect(page.locator('[data-cf-card="zh.title"]')).toHaveValue('雾夜猎人')
  await expect(page.locator('.cfpic .cfthumb img').nth(1)).toBeVisible()   // 封面(模板的)之后那一张 = 阿青的立绘(草稿里的)
  await expect(page.locator('.cfeng.ready')).toBeVisible({ timeout: 360_000 })

  // 4. 存:作品 + 传图 + 发布前检查
  const t0 = Date.now()
  await page.click('[data-cf-save]')
  await expect(page.locator('[data-cf-msg]')).toContainText('存好了', { timeout: 180_000 })
  console.log(`[create] 存(检查 + creation/work + 传图)${Date.now() - t0} ms`)   // lead 10-18:目标 5 秒以内
  const perf = await page.evaluate(async () => { const f = document.querySelector('iframe[title=engine]') as HTMLIFrameElement; const d = await (f.contentWindow as any).WLPLAY.debug(); return d.perf.filter((r: any) => r.method !== 'GET' || /creation|publish/.test(r.path)) })
  console.log('[create] 引擎里每条请求(ms):', JSON.stringify(perf))
  await expect(page.locator('.cfpre')).toContainText('发布前检查都过了', { timeout: 120_000 })
  await expect(page.locator('.cfpic small').nth(1)).toContainText('已传')
  await shot(page, '04-saved-prechecked')

  // 5. 试玩:浏览器版接着就开这份作品(世界包用模板的;作品在 IndexedDB 里)
  await page.click('[data-cf-try]')
  await expect(page).toHaveURL(/\/play\/\?.*tpl=stoneford-town-mine.*/)
  expect(new URL(page.url()).searchParams.get('base')).toBe('stoneford-town')
  await page.goto(page.url().replace('/play/?', '/play/bench.html?'))   // 和 play.spec 一样对着测试台走(同一个引擎层)
  await page.waitForFunction(() => (window as any).WLPLAY && (window as any).WLPLAY.ready, null, { timeout: 360_000 })
  const run = await page.evaluate(() => ({ tpl: (window as any).WLPLAY.tpl, base: (window as any).WLPLAY.base }))
  expect(run.tpl).toBe('stoneford-town-mine')
  expect(run.base).toBe('stoneford-town')
  await page.waitForSelector('#min', { timeout: 180_000 })
  await page.waitForFunction(() => { try { const E = (0, eval)('E'); return !E.busy && E.s && E.s.feed.length > 0 } catch { return false } }, null, { timeout: 240_000 })
  const said = await page.evaluate(async () => { const d = await (window as any).WLPLAY.engine.sayAndWait('我顺着泥里的脚印往北走'); return { ok: d && d.success, err: d && d.error } })
  expect(said.ok, String(said.err)).toBe(true)
  const tm = await page.evaluate(() => fetch('/api/v1/local/templates').then(r => r.json()))
  const mine = (tm.templates || tm).find((x: any) => x.id === 'stoneford-town-mine')
  expect(mine, 'the work is installed in the browser engine').toBeTruthy()
  await shot(page, '05-trial-play')

  // 6. 回到创作台(草稿 + 作品都还在)→ 提交到默认区:页上写明协议;要登录;六步拦在本机
  await page.goto('/#/t/stoneford-town/create')
  await expect(page.locator('[data-cf-submit]')).toBeEnabled({ timeout: 60_000 })
  await expect(page.locator('.cfeng.ready')).toBeVisible({ timeout: 360_000 })
  await page.click('[data-cf-submit]')
  const sheet = page.locator('.sheet')
  await expect(sheet).toContainText('创作者协议')
  await expect(sheet).toContainText('内容政策')
  await expect(sheet).toContainText('30 分钟')
  await expect(page.locator('[data-cf-submit-go]')).toBeEnabled({ timeout: 120_000 })
  await shot(page, '06-submit-sheet')
  await fetch(`${AI}/_plat/reset`, { method: 'POST' })
  await page.click('[data-cf-submit-go]')
  await expect(sheet).toContainText('已提交到默认区审核', { timeout: 180_000 })
  await shot(page, '07-submitted')
  const P = await plat(), bodies = P.bodies, puts = Object.fromEntries(Object.entries(P.puts).map(([k, v]) => [k, Buffer.from(v, 'base64')]))
  expect(P.steps.filter(s => s.startsWith('POST')).map(s => s.replace(/hub\/template\/[^/]+/, 'W'))).toEqual([
    'POST /v1/resources', 'POST /v1/resources/W/lease', 'POST /v1/objects/W/upload-url', 'POST /v1/objects/W/complete', 'POST /v1/resources/W/publish'])
  expect(bodies.publish).toEqual({ zone: 'curated' })
  const wid = (bodies.register as any).id as string
  expect(wid).toMatch(/^stoneford-town-mine-[0-9a-f]{6}$/)   // 非官方作品的 id 带 -<6hex>
  expect((bodies.register as any).meta.title.zh).toBe('雾夜猎人')
  expect((bodies.register as any).meta.title.en).toBe('The Fog Hunter')
  expect(Object.keys(puts).sort()).toEqual(['cover.png', 'package.zip'])
  const pkg = puts['package.zip'].toString('latin1')
  expect(pkg).toContain('stoneford-town-mine.template/plots/mine/plot.json')
  expect(pkg).toMatch(/stoneford-town-mine\.template\/plots\/mine\/[^\s]*\.png/)   // 阿青的立绘跟着包走

  // 7. 我的作品 · 默认区:审核中,能撤回
  await sheet.locator('a[href="#/me"]').click()   // 「去『我的作品』看状态」:关掉提交页、进「我的」
  const row = page.locator('.meitem.wk').filter({ hasText: '雾夜猎人' })
  await expect(row).toContainText('审核中', { timeout: 60_000 })
  await expect(row).toContainText('预计')   // review.autopass_at → 预计 xx 上线
  await expect(row.locator(`[data-wk-withdraw="${wid}"]`)).toBeVisible()
  await expect(row.locator('a[href="#/t/stoneford-town/create"]')).toBeVisible()   // 改版再提交 → 回创作台
  await shot(page, '08-my-works-pending')
  await row.locator(`[data-wk-withdraw="${wid}"]`).click()
  await expect.poll(async () => (await plat()).steps.some(s => s === `POST /v1/resources/hub/template/${wid}/withdraw`)).toBe(true)
  await expect(page.locator('.meitem.wk').filter({ hasText: '雾夜猎人' })).not.toContainText('审核中')
  await expect(page.locator('.meitem.wk').filter({ hasText: '雾夜猎人' })).toContainText('未提交')
  await shot(page, '09-my-works-withdrawn')
  // 一个请求都没出本机:平台全走 serve.py(生产平台一次都没碰)
  expect(leaks, 'requests to the live platform').toEqual([])
})
