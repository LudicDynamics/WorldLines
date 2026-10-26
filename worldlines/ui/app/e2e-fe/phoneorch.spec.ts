// 小手机编排的编辑页(10-21 阶段 B · 私有层 ui/phoneorch.js):本地前端台 → 小手机台 → 编辑 →「编排」页签:图只读 · 参数改了是草稿 →
// 存 = 本机覆盖层只留和默认不同的 → 重开读回;越界 = 检查里说是哪个参数、存不进去;恢复默认 = 覆盖层删掉。要私有层(没有就跳过)。
import { test, expect, type Page } from '@playwright/test'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_FE_BASE || 'http://127.0.0.1:8909'
const HOME = process.env.WL_FE_HOME || ''
const SHOTS = process.env.WL_FE_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())
const field = (page: Page, k: string) => page.locator(`#phoneorch [data-po="${k}"]`)

async function openTab(page: Page) {
  await page.goto(`${BASE}/`)
  await expect(page.locator('#ctx .chip').first()).not.toHaveText(/连接引擎|正在开一局/, { timeout: 90_000 })
  await page.locator('.nav [data-go=fe]').click()
  await page.locator('[data-fxdesk="builtin.chat"]').click()
  if (!(await page.locator('[data-fxv=phone-orch]').count())) await page.locator('[data-fxmode=edit]').click()
}

test('小手机编排:改参数 → 存进本机覆盖层 → 重开读回 · 越界拒 · 恢复默认', async ({ page }) => {
  await openTab(page)
  test.skip((await page.locator('[data-fxv=phone-orch]').count()) === 0, 'no private layer: no phone orchestration tab')
  await page.locator('[data-fxv=phone-orch]').click()
  await expect(page.locator('#phoneorch')).toContainText('私有包默认')
  await expect(page.locator('#phoneorch')).toContainText('世界执行')
  await expect(field(page, 'world_exec_daily')).toHaveValue('6')
  await expect(page.locator('#phoneorch [data-poact=save]')).toBeDisabled()
  await field(page, 'world_exec_daily').fill('4')
  await expect(page.locator('#phoneorch .fxstate')).toContainText('草稿')
  await shot(page, 'phoneorch-01-draft')
  await page.locator('#phoneorch [data-poact=save]').click()
  await expect(page.locator('#phoneorch .po-msg')).toContainText('存好了')
  if (HOME) {
    const f = join(HOME, '.worldlines/phone/orch.json')
    expect(JSON.parse(readFileSync(f, 'utf-8')).params).toEqual({ world_exec_daily: 4 })   // only what differs from the default
  }
  await openTab(page)
  await page.locator('[data-fxv=phone-orch]').click()
  await expect(field(page, 'world_exec_daily')).toHaveValue('4')
  await expect(page.locator('#phoneorch')).toContainText('本机覆盖层')
  await field(page, 'carry').fill('9')
  await expect(page.locator('#phoneorch .po-lint')).toContainText('carry', { timeout: 10_000 })
  await page.locator('#phoneorch [data-poact=save]').click()
  await expect(page.locator('#phoneorch .po-msg')).toContainText('没存')
  await shot(page, 'phoneorch-02-out-of-range')
  if (HOME) expect(JSON.parse(readFileSync(join(HOME, '.worldlines/phone/orch.json'), 'utf-8')).params).toEqual({ world_exec_daily: 4 })
  await page.locator('#phoneorch [data-poact=reset]').click()
  await expect(page.locator('#phoneorch .po-msg')).toContainText('已恢复')
  await expect(field(page, 'world_exec_daily')).toHaveValue('6')
  if (HOME) expect(existsSync(join(HOME, '.worldlines/phone/orch.json'))).toBe(false)
  await shot(page, 'phoneorch-03-reset')
})
