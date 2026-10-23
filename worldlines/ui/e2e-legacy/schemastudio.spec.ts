// 工作台 · Schema:五张表读真引擎;注册变量 / 类 / 实例走引擎校验(错误原样显示);
// 订阅面板读事件账本(SSE)。引擎侧见 NeonRP webui/schema_routes.py。
import { test, expect, type Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

async function openSchema(page: Page, name: string) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh')
  })
  const r = await page.request.post('/api/v1/create/session', { data: { template: 'stoneford-elena', name } })
  expect(r.ok()).toBe(true)
  await page.goto('/local/create/studio')
  await page.getByRole('button', { name: 'Schema', exact: true }).click()
  await expect(page.getByTestId('schema-studio')).toBeVisible({ timeout: 10_000 })
}

test('五张表来自真引擎:变量带当前值,类显示实例数', async ({ page }) => {
  await openSchema(page, 'e2e-schema-read')
  await expect(page.locator('.wsc-row[data-row="player.gold"]')).toBeVisible()
  await page.locator('.wsc-row[data-row="player.gold"]').click()
  await expect(page.getByTestId('schema-detail')).toContainText('game/player/wallet.json')
  await page.locator('[data-table=classes]').click()
  await expect(page.locator('.wsc-row[data-row=place]')).toContainText('个实例')
})

test('注册:闭 schema 变量成功;坏 spec 被引擎拒绝并显示原因;开 schema 先类后实例', async ({ page }) => {
  await openSchema(page, 'e2e-schema-register')
  // 变量(表单默认填好 price.T001.grain)
  await page.getByTestId('schema-new').click()
  await page.getByTestId('schema-submit').click()
  await expect(page.getByTestId('schema-detail')).toContainText('price.T001.grain')
  await expect(page.locator('.wsc-row[data-row="price.T001.grain"]')).toBeVisible()
  // 坏类型 → 引擎拒绝
  await page.getByTestId('schema-new').click()
  await page.getByTestId('schema-id').fill('bad.money')
  await page.getByTestId('schema-spec').fill('{"type":"money","path":"a","key":"b"}')
  await page.getByTestId('schema-submit').click()
  await expect(page.getByTestId('schema-error')).toContainText('int|float|str|bool')
  // 实例先于类 → 拒绝
  await page.locator('[data-table=entries]').click()
  await page.getByTestId('schema-new').click()
  await page.getByTestId('schema-submit').click()
  await expect(page.getByTestId('schema-error')).toContainText('register it in classes first')
  // 先注册类 faction,再注册实例
  await page.locator('[data-table=classes]').click()
  await page.getByTestId('schema-new').click()
  await page.getByTestId('schema-submit').click()
  await expect(page.locator('.wsc-row[data-row=faction]')).toBeVisible()
  await page.locator('[data-table=entries]').click()
  await page.getByTestId('schema-new').click()
  await page.getByTestId('schema-submit').click()
  await expect(page.locator('.wsc-row[data-row=F_bandits]')).toContainText('独眼虎山贼')
  // 取消注册变量
  await page.locator('[data-table=variables]').click()
  await page.locator('.wsc-row[data-row="price.T001.grain"]').click()
  await page.getByTestId('schema-unregister').click()
  await expect(page.locator('.wsc-row[data-row="price.T001.grain"]')).toHaveCount(0)
})

test('订阅面板:pattern 可切换,预设含所选变量', async ({ page }) => {
  await openSchema(page, 'e2e-schema-sub')
  await expect(page.getByTestId('schema-subscribe')).toContainText('接收中')
  await page.locator('.wsc-row[data-row="player.gold"]').click()
  await page.locator('.wsc-presets button', { hasText: 'var.changed:player.gold' }).click()
  await expect(page.getByTestId('schema-pattern')).toHaveValue('var.changed:player.gold')
  const r = await page.request.get('/api/v1/create/session/edit-local/schema/stream?pattern=*&timeout=0.3')
  expect(r.ok()).toBe(true)
  expect(await r.text()).toContain('event: hello')
})

test('一键切换回合引擎:v2b ⇄ v3,写进世界的 engine.json', async ({ page }) => {
  await openSchema(page, 'e2e-schema-mode')
  await page.locator('.wsc-mode [data-mode=v3]').click()
  await expect(page.locator('.wsc-mode [data-mode=v3]')).toHaveClass(/is-on/)
  const r = await page.request.get('/api/v1/create/session/edit-local/engine/mode')
  expect((await r.json()).mode).toBe('v3')
  await page.locator('.wsc-mode [data-mode=v2b]').click()
  await expect(page.locator('.wsc-mode [data-mode=v2b]')).toHaveClass(/is-on/)
  await expect(page.locator('.wsc-note')).toContainText('v2b')
})
