// 工作台「捏角色」开关(10-25):内置世界只读 → 复制一份 → 打开开关(通用捏人设置)→ 改一个字段的标题 → 去测试台开局 = 先出捏人页;
// 关掉以后再开局 = 直接开场。截图进 WL_PB_SHOTS。
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_PB_BASE || 'http://127.0.0.1:8801'
const HOME = process.env.WL_PB_HOME || ''
const SHOTS = process.env.WL_PB_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())
const WORLD = 'pct-house', MINE = 'pct-house-mine'

async function boot(page: Page) {
  await page.goto(`${BASE}/`)
  await expect(page.locator('#ctx .chip').first()).not.toHaveText(/连接引擎|正在开一局/, { timeout: 90_000 })
}
async function openTpl(page: Page, id: string) {
  await page.locator('.nav [data-go=tpl]').click()
  await page.evaluate(i => (window as any).LIVE_openTpl(i), id)
  await expect(page.locator('#s-tpl .tplhd .tag').first()).toContainText(`${id}.template`)
  await settle(page)
}
// 模板页的几份数据各自回来各自重画:都到齐了再点 / 截图
async function settle(page: Page) {
  await expect.poll(() => page.evaluate(() => { const t = (window as any).TPL; return !!(t && t.detail && t.ui && t.lint && t.slots && t.pb) }), { timeout: 90_000 }).toBe(true)
  await expect(page.locator('#s-tpl .pbbox')).toBeVisible()
}
const toBox = (page: Page) => page.evaluate(() => document.querySelector('#s-tpl .pbbox')?.scrollIntoView({ block: 'center' }))

test('捏角色开关:打开 → 开局先出捏人页;关掉 → 直接开局', async ({ page }) => {
  await boot(page)
  await openTpl(page, WORLD)
  const sw = page.locator('#s-tpl [data-tpb]')
  await expect(sw).toBeDisabled()   // 内置的只读,先复制
  await toBox(page)
  await shot(page, '01-builtin-readonly')
  await page.locator('#s-tpl .pbbox [data-tfork]').click()
  await expect(page.locator('#s-tpl .tplhd .tag').first()).toContainText(`${MINE}.template`, { timeout: 60_000 })
  await settle(page)
  await expect(sw).toBeEnabled()
  await expect(sw).not.toHaveClass(/\bon\b/)
  await sw.click()
  await expect(sw).toHaveClass(/\bon\b/)
  const label = page.locator('#s-tpl [data-pbl="name"]')
  await expect(label).toHaveValue('名字')
  await expect(page.locator('#s-tpl [data-pbr="name"]')).not.toHaveValue('')
  await label.fill('代号')
  await page.locator('#s-tpl [data-pbsave]').click()
  await expect(page.locator('#s-tpl [data-pbsave]')).toBeDisabled()
  await expect(label).toHaveValue('代号')
  await toBox(page)
  await shot(page, '02-switch-on-editor')
  if (HOME) {
    const d = JSON.parse(readFileSync(join(HOME, 'store', `${MINE}.template`, 'template.json'), 'utf-8'))
    expect(d.player.builder.fields[0].label.zh).toBe('代号')
    expect(JSON.parse(readFileSync(join(HOME, 'templates', `${WORLD}.template`, 'template.json'), 'utf-8')).player?.builder, '内置的那份没被写').toBeUndefined()
  }

  // 开局:先出捏人页
  await page.locator('#s-tpl [data-tplay]').click()
  const pb = page.locator('.pb')
  await expect(pb).toBeVisible({ timeout: 60_000 })
  await expect(pb.locator('.pb-lab').first()).toContainText('代号')
  await pb.locator('[data-pbt="name"]').fill('阿澄')
  await pb.locator('[data-pbo="gender"][data-v="female"]').click()
  await pb.locator('[data-pbt="look"]').fill('灰色风衣,左手缠着绷带')
  await shot(page, '03-builder-screen')
  await pb.locator('[data-pbx="next"]').click()
  await pb.locator('[data-pbx="go"]').click()
  await expect(pb).toHaveCount(0, { timeout: 150_000 })
  await expect.poll(() => page.evaluate(() => (window as any).LIVE.bound), { timeout: 150_000 }).toBe(MINE)
  const card = await page.evaluate(() => fetch('/api/v1/play/engine/player-card').then(r => r.json()))
  expect(card.values.name).toBe('阿澄')
  await page.locator('[data-rside=card]').click()   // 测试台右栏的「面板」= 这一局捏的角色
  await expect(page.locator('.pcard')).toContainText('阿澄')
  await shot(page, '04-run-with-character')

  // 关掉:直接开局,不出捏人页
  await openTpl(page, MINE)
  await page.locator('#s-tpl [data-tpb]').click()
  await expect(page.locator('#s-tpl [data-tpb]')).not.toHaveClass(/\bon\b/)
  await expect(page.locator('#s-tpl .pbbox')).toContainText('之前的设置还留着')
  await toBox(page)
  await shot(page, '05-switch-off')
  await page.locator('#s-tpl [data-tplay]').click()
  await expect.poll(async () => page.evaluate(() => fetch('/api/v1/play/engine/player-card').then(r => r.json())), { timeout: 150_000 }).toEqual({})
  await expect(page.locator('.pb')).toHaveCount(0)
  await expect(page.locator('[data-rside=card]')).toHaveCount(0)   // 没捏人的局没有面板页签
  await shot(page, '06-run-without-builder')
})
