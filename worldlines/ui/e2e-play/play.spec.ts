// 「在浏览器里玩」:Hub 详情页 → 浏览器里的引擎开局 → 假模型两回合 → 刷新接着玩 → 导出存档 → 额度用完(不重试)
// · 没登录用自己的 key · iPhone 显示「请用 app 或电脑浏览器」· 公开版没有的世界标「暂不支持」。
import { test, expect, type Page, type BrowserContext } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const AI = 'http://127.0.0.1:8611'
const SHOTS = process.env.WL_PLAY_SHOTS || '../test-results/play-shots'
mkdirSync(SHOTS, { recursive: true })
type Call = { auth: string; product: string; origin: string; stream?: boolean; model?: string; jev?: boolean; mode: string }

const mock = (mode: string, reset = false) => fetch(`${AI}/_mock/mode`, { method: 'POST', body: JSON.stringify({ mode, reset }) })
const calls = async (): Promise<Call[]> => (await (await fetch(`${AI}/_mock/state`)).json()).calls
const shot = (page: Page, name: string) => page.screenshot({ path: `${SHOTS}/${test.info().project.name}-${name}.png` })
const edition = async (): Promise<string> => (await (await fetch('http://127.0.0.1:8610/play/manifest.json')).json()).edition
const signIn = (ctx: BrowserContext) => ctx.addInitScript(() => {
  try {
    if (!localStorage.getItem('wl.hub.auth')) localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok-e2e', exp: Date.now() + 3600e3, refresh: 'r-e2e', user: { id: 'u-e2e' } }))
  } catch { /* storage blocked: the test will fail on the gate */ }
})

async function ready(page: Page) {
  await page.waitForFunction(() => (window as any).WLPLAY && (window as any).WLPLAY.ready, null, { timeout: 300_000 })
  await page.waitForSelector('#min', { timeout: 120_000 })
  // 开场那一拍(新开一局时引擎自己跑的)落定以后再说话,不然界面会说「上一句还在跑」
  await page.waitForFunction(() => { try { const E = (0, eval)('E'); return !E.busy && E.s && E.s.feed.length > 0 } catch { return false } }, null, { timeout: 120_000 })
  await page.waitForTimeout(500)
}
async function say(page: Page, text: string) {
  await page.fill('#min', text)
  await page.press('#min', 'Enter')
  await page.waitForFunction(() => typeof (window as any).E === 'undefined' ? false : true, null, { timeout: 5_000 }).catch(() => {})
  await page.waitForFunction(() => { try { return (0, eval)('E').busy } catch { return false } }, null, { timeout: 20_000 }).catch(() => { /* a fast turn may be over already */ })
  await page.waitForFunction(() => { try { return !(0, eval)('E').busy } catch { return true } }, null, { timeout: 240_000 })
}
const feed = (page: Page) => page.evaluate(() => document.body.innerText)

test('Hub → 浏览器里开局 · 两回合 · 刷新继续 · 导出 · 额度用完不重试', async ({ page, context }) => {
  await signIn(context)
  await mock('ok', true)

  // Hub 详情页:公开版能玩的世界有按钮,不能玩的标出来
  await page.goto('/#/t/stoneford-town')
  if ((await edition()) === 'public') await expect(page.getByText('暂不支持浏览器游玩')).toBeVisible()
  else await expect(page.locator('[data-web="stoneford-town"]')).toBeVisible()   // 完整版带石津镇
  await page.goto('/#/t/pct-house')
  const btn = page.locator('[data-web="pct-house"]')
  await expect(btn).toBeVisible()
  await shot(page, '01-hub-detail')
  await btn.click()
  await expect(page.getByText('用你的 Worldlines 额度跑')).toBeVisible()
  await shot(page, '02-hub-sheet')
  await page.locator('.sheet a.btn.p').click()
  await expect(page).toHaveURL(/\/play\/\?tpl=pct-house/)
  // Hub 打开的是 play/(标准重前端);这几条用例对着测试台(play/bench.html,同一个引擎层)走
  await page.goto(page.url().replace('/play/?', '/play/bench.html?'))

  await ready(page)
  await shot(page, '03-play-ready')
  const timing = await page.evaluate(() => (window as any).WLPLAY.timing)
  test.info().annotations.push({ type: 'first-open', description: JSON.stringify({ ...timing, bytes: await page.evaluate(() => (window as any).WLPLAY.ready.bytes) }) })

  // 第一句:先提示「走 Worldlines 额度」
  await page.fill('#min', '我走近灯影')
  await page.press('#min', 'Enter')
  await expect(page.getByText('这一局走 Worldlines 额度')).toBeVisible()
  await shot(page, '04-charge-notice')
  await page.getByRole('button', { name: '知道了,开始' }).click()
  await page.waitForFunction(() => { try { return !(0, eval)('E').busy && (0, eval)('E').s.feed.length > 2 } catch { return false } }, null, { timeout: 240_000 })
  await say(page, '问他是谁')
  expect(await feed(page)).toContain('问他是谁')
  expect(await feed(page)).toContain('灯影里有人在等你开口')
  const c1 = await calls()
  expect(c1.filter(c => !c.jev).length).toBeGreaterThan(0)
  for (const c of c1) {   // 浏览器直接带 Worldlines 令牌 + 产品 id 调 ai,跨域(origin = 静态站)
    expect(c.auth).toBe('Bearer tok-e2e')
    expect(c.product).toBe('hub')
    expect(c.origin).toBe('http://127.0.0.1:8610')
  }
  await shot(page, '05-two-turns')
  expect(page.url()).toMatch(/save=tpl-pct-house-/)

  // 刷新:接着这一局(存档在 IndexedDB)
  await page.reload()
  await ready(page)
  await page.waitForFunction(() => document.body.innerText.includes('问他是谁'), null, { timeout: 60_000 })
  await shot(page, '06-after-reload')

  // 导出存档
  await page.locator('#wlp-badge [data-menu]').click()
  const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('[data-export]').click()])
  expect(dl.suggestedFilename()).toMatch(/^tpl-pct-house-.*\.zip$/)
  await shot(page, '07-menu-saves')
  await page.locator('.wlp-modal [data-x]').click()

  // 额度用完:429 quota_exceeded → 弹出领取 / 订阅,这一句只发出去一次模型请求
  await mock('quota')
  const before = (await calls()).filter(c => !c.jev).length
  await page.fill('#min', '数钟声')
  await page.press('#min', 'Enter')
  const bill = page.locator('.wlp-modal.bill')
  await expect(bill).toBeVisible()
  await expect(bill).toContainText('今天的 Worldlines 额度用完了')
  await expect(bill.locator('[data-claim]')).toHaveAttribute('href', /#\/me$/)
  await expect(bill.locator('[data-subscribe]')).toHaveAttribute('href', /billing\.worldlines\.gg\/subscribe/)
  await page.waitForFunction(() => { try { return !(0, eval)('E').busy } catch { return true } }, null, { timeout: 240_000 })
  await page.waitForTimeout(1500)
  const quota = (await calls()).filter(c => !c.jev).slice(before)
  expect(quota.length).toBe(1)
  expect(quota[0].mode).toBe('quota')
  await shot(page, '08-quota-exceeded')

  // 402 claim_required:同样停下,告诉玩家先领
  await bill.locator('[data-x]').click()
  await mock('claim')
  await page.fill('#min', '再试一次')
  await page.press('#min', 'Enter')
  await expect(page.locator('.wlp-modal.bill')).toContainText('今天的免费额度还没领')
  await page.waitForFunction(() => { try { return !(0, eval)('E').busy } catch { return true } }, null, { timeout: 240_000 })
  await shot(page, '09-claim-required')
  await mock('ok')

  // 回 Hub:详情页能「继续上一局」
  await page.goto('/#/t/pct-house')
  await page.locator('[data-web="pct-house"]').click()
  await expect(page.getByText(/继续上一局/)).toBeVisible()
  await shot(page, '10-hub-continue')
})

test('没登录:填自己的 key 玩(不走 Worldlines,不调 Jev)', async ({ page }) => {
  await mock('ok', true)
  await page.goto('/play/bench.html?tpl=pct-house&lang=zh')
  await expect(page.getByText('用什么模型来跑?')).toBeVisible()
  await shot(page, '11-gate')
  await page.fill('form[data-key] input[name=base]', `${AI}/v1`)
  await page.fill('form[data-key] input[name=key]', 'sk-own-e2e')
  await page.fill('form[data-key] input[name=model]', 'own-model')
  await page.locator('form[data-key] button[type=submit]').click()
  await ready(page)
  await expect(page.locator('#wlp-badge')).toContainText('自己的 key')
  await say(page, '我四处看看')
  const c = await calls()
  expect(c.length, JSON.stringify(await page.evaluate(async () => { const d = await (window as any).WLPLAY.debug(); return { n: d.n, perf: d.perf.map((r: any) => r.method[0] + ' ' + r.path + ' ' + r.status + (r.turn ? ' t' + r.turn : '')).join(' | ') } }))).toBeGreaterThan(0)
  expect(c.every(x => x.auth === 'Bearer sk-own-e2e' && x.product === '' && !x.jev && x.model === 'own-model')).toBe(true)
  // 导出的存档里不带 key
  await page.locator('#wlp-badge [data-menu]').click()
  const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('[data-export]').click()])
  const { readFileSync } = await import('node:fs')
  expect(readFileSync(await dl.path()).includes(Buffer.from('sk-own-e2e'))).toBe(false)
  await shot(page, '12-own-key')
})

test('iPhone 的 UA 不拦:照常进门(选模型)', async ({ browser }) => {
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1', viewport: { width: 390, height: 844 }, locale: 'zh-CN' })
  const page = await ctx.newPage()
  await page.goto('/play/bench.html?tpl=pct-house&lang=zh')
  await expect(page.getByText('用什么模型来跑?')).toBeVisible()
  await shot(page, '13-iphone')
  await ctx.close()
})

test('公开版没有的世界:暂不支持浏览器游玩', async ({ page }) => {
  test.skip((await edition()) !== 'public', '完整版带石津镇')
  await page.goto('/play/bench.html?tpl=stoneford-town&lang=zh')
  await expect(page.getByText('这个世界暂不支持浏览器游玩')).toBeVisible()
})

test('引擎接口 WLPLAY.engine:就绪 · 说一句等 turn_done · 事件 · 存档', async ({ page, context }) => {
  await signIn(context)
  await context.addInitScript(() => { try { localStorage.setItem('wl.play.ackCharge', '1') } catch { /* blocked */ } })
  await mock('ok', true)
  await page.goto('/play/bench.html?tpl=pct-house&lang=zh&new=1')
  await ready(page)
  const r = await page.evaluate(async () => {
    const e = (window as any).WLPLAY.engine
    const info = await e.ready
    const kinds: string[] = []
    const off = e.onEvent((x: any) => kinds.push(x.kind))
    const done = await e.sayAndWait('我四处看看')
    off()
    return { pyodide: info.pyodide, done, kinds, saves: await e.saves(), hello: !!(await e.hello()) }
  })
  expect(r.done.success).toBe(true)
  expect(r.kinds).toContain('turn_start')
  expect(r.kinds).toContain('turn_done')
  expect(r.saves.some((s: any) => s.template === 'pct-house')).toBe(true)
  expect(r.hello).toBe(true)
})
