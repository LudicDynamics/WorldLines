// 第 1 批(10-17 审计):一个全局的「当前世界」—— 顶栏选一次,编排 · Template · 世界·角色 · 前端都跟着;测试台不一样时先问再开;
// 刷新后记得;小手机 / Hub 的入口;Hub「我的」里角色库的角色能点进小手机聊。截图进 WL_SOUL_SHOTS。
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_SOUL_BASE || 'http://127.0.0.1:8906'
const SHOTS = process.env.WL_SOUL_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())

async function boot(page: Page, path = '/') {
  await page.goto(`${BASE}${path}`)
  await expect(page.locator('#ctx .chip').first()).not.toHaveText(/连接引擎|正在开一局/, { timeout: 90_000 })
  expect(await page.locator('#ctx [data-err]').getAttribute('data-err').catch(() => null), '本地界面开机失败的原因').toBeNull()
}

test('当前世界:顶栏选一次 → 编排 · Template · 世界·角色 · 前端都跟着;测试台先问再开;刷新后还在', async ({ page }) => {
  test.setTimeout(300_000)
  await boot(page)
  await page.locator('.nav [data-go=orch]').click()
  await page.locator('#wlWorld').selectOption('wuwu')
  // 编排图 = wuwu 的:模板图 tpl:wuwu,或者 wuwu 正是这一局时用引擎生效图(live)
  await expect.poll(() => page.evaluate('(() => { const g = GRAPHS[S.graph]; return g && !g.pending ? g.tpl : null })()'), { timeout: 60_000 }).toBe('wuwu')
  expect(await page.evaluate(() => (window as any).WL_WORLD())).toBe('wuwu')
  await page.locator('.nav [data-go=tpl]').click()
  await expect(page.locator('#s-tpl .tplhd .tag').first()).toContainText('wuwu.template', { timeout: 30_000 })
  await expect(page.locator('#wlWorld')).toHaveValue('wuwu')
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('#mwSel')).toHaveValue('wuwu', { timeout: 90_000 })   // 打开的是 wuwu 的编辑副本
  await shot(page, 'world-01-duo-follows')
  await page.locator('.nav [data-go=test]').click()
  const bar = page.locator('#wlTestBar')
  if (await page.evaluate(() => (window as any).LIVE.bound) !== 'wuwu') {
    await expect(bar).toBeVisible({ timeout: 30_000 })   // 这一局不是当前世界:横幅,不自动开
    await shot(page, 'world-02-test-banner')
    page.once('dialog', d => d.accept())
    await bar.locator('[data-wlopen]').click()
    await expect.poll(() => page.evaluate(() => (window as any).LIVE.bound), { timeout: 150_000 }).toBe('wuwu')
  }
  await expect(bar).toHaveCount(0)
  // 测试台上选别的世界、在确认框里取消 → 当前世界不变
  page.once('dialog', d => d.dismiss())
  await page.locator('#wlWorld').selectOption('stoneford-elena')
  await expect(page.locator('#wlWorld')).toHaveValue('wuwu')
  expect(await page.evaluate(() => (window as any).WL_WORLD())).toBe('wuwu')
  // 刷新:记得上次选的
  await boot(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#wlWorld')).toHaveValue('wuwu')
  await expect(page.locator('#gsel')).toHaveValue(/wuwu|live/)
})

test('入口:导航里有小手机和 Hub;Hub「我的」里角色库的角色点进小手机能聊(假模型回话)', async ({ page }) => {
  const phone = (await page.request.get(`${BASE}/chat.html`)).ok()   // run.sh 不带 WL_SOUL_PLAYER=1 时不构建小手机
  await boot(page)
  await expect(page.locator('.nav [data-navx=chat]')).toHaveCount(phone ? 1 : 0)
  if (phone) await expect(page.locator('.nav [data-navx=chat]')).toHaveAttribute('href', '/chat.html')
  await expect(page.locator('.nav [data-navx=hub]')).toHaveAttribute('href', '/hub.html')
  await shot(page, 'world-03-nav-links')
  await page.goto(`${BASE}/hub.html#/me`)
  const tile = page.locator('a.metile', { hasText: /阿雾|Awu/ })
  await expect(tile).toHaveAttribute('href', /\/chat\.html\?tpl=lib%3Aawu&sid=awu/, { timeout: 90_000 })
  await shot(page, 'world-04-hub-me')
  test.skip(!phone, '这次构建没有小手机(WL_SOUL_PLAYER=1 才带)')
  await tile.click()
  // 小手机就绪 = 对话取回来了、开场白写完(或超时说了「想得有点久」)—— 引擎在后台建世界时会很慢,等这个状态,不卡固定 30 秒
  await page.waitForFunction(() => { const st = (window as any).WLCHAT && (window as any).WLCHAT.state(); return !!st && st.ready && !st.greeting }, null, { timeout: 180_000 })
  await expect(page.locator('.who b')).toContainText(/阿雾|Awu/)
  await page.locator('textarea').fill('船还好吗')
  await page.locator('.snd').click()
  // 回的是这一句(排在它后面的角色气泡),不把晚到的开场白算成回话
  await expect(page.locator('.m.me:has-text("船还好吗") ~ .m.soul:not(.typing)').first()).toBeVisible({ timeout: 120_000 })
  await shot(page, 'world-05-phone-chat')
})
