// 小手机在浏览器引擎上(play/chat.html,10-17):boot.js 是 defer 的,比聊天页的内联脚本晚 —— 以前第一次取对话打到静态站(线上 403),
// 页面一直停在「连不上 / 还不能聊」。这里:登录 → 等引擎就绪 → 对话打开(不是那条)→ 第一次打开有开场白 + 三句建议 → 点一句 → 假模型回话。
// 全程不能出现 disabled 的输入框。只跑这一个:WL_PLAY_SITE=… npx playwright test -c playwright.config.ts chat.spec.ts --project chromium
import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const SHOTS = process.env.WL_PLAY_SHOTS || '../test-results/play-shots'
mkdirSync(SHOTS, { recursive: true })

test('小手机 · 浏览器引擎:等引擎再取对话 · 开场白 + 建议 · 点建议有回复', async ({ page, context }) => {
  await context.addInitScript(() => {
    const W = window as any
    try { if (!localStorage.getItem('wl.hub.auth')) localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok-e2e', exp: Date.now() + 3600e3, refresh: 'r-e2e', user: { id: 'u-e2e' } })) } catch { /* storage blocked */ }
    W.__taDisabled = 0
    new MutationObserver(() => { if (document.querySelector('textarea[disabled]')) W.__taDisabled++ }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ['disabled'] })
  })
  const early: string[] = []
  page.on('response', r => { if (r.request().resourceType() === 'fetch' && /\/api\/v1\/chat\//.test(r.url())) early.push(`${r.status()} ${r.url()}`) })   // 打到静态站的会在这里(引擎的走 worker,不经网络)
  await page.goto('/play/chat.html?tpl=wuwu&sid=vera&lang=zh')
  await page.waitForFunction(() => (window as any).WLPLAY && (window as any).WLPLAY.ready, null, { timeout: 300_000 })
  await expect(page.locator('.who b')).toHaveText('薇拉', { timeout: 60_000 })
  await expect(page.locator('.m.soul .bub.t').first()).toBeVisible({ timeout: 120_000 })   // 开场白(引擎在浏览器里写的)
  await expect(page.locator('.sug')).toHaveCount(3)
  await expect(page.locator('.lockbar')).toHaveCount(0)
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-chat-first-open.png` })
  const n = await page.locator('.m.soul .bub.t').count()
  await page.locator('.sug').first().click()
  await expect(page.locator('.m.me').last()).toContainText('你好呀')
  await expect(page.locator('.m.soul .bub.t')).not.toHaveCount(n, { timeout: 120_000 })
  await expect(page.locator('.m.me .fail')).toHaveCount(0)
  await expect(page.locator('.sugs')).toHaveCount(0)
  await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-chat-replied.png` })
  expect(early, 'no chat request reached the static site').toEqual([])
  expect(await page.evaluate(() => (window as any).__taDisabled)).toBe(0)
})
