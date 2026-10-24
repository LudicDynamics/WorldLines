// 创作台「用一句话说」(10-18 · PLATFORM-PLAY-RULES-1015 §10):作者说一句 → 助手(假模型,fake_llm.py)只用模板开放的那一层
// 把它落成表单的行 → 预览 → 「写进表单」→ 表单里真的有这些行 → 检查 · 存 → 作品的 plot.json 里是那几条规则。
// 三种句子(地点门槛 · 收集条件 · 角色条件)+ 一种做不到的(模板不开放数值 → 说人话 + 点替代再问一次)。截图进 WL_CA_SHOTS。
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_CA_BASE || 'http://127.0.0.1:8797'
const AI = process.env.WL_CA_AI || 'http://127.0.0.1:8798'
const HOME = process.env.WL_CA_HOME || ''
const SHOTS = process.env.WL_CA_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.locator('#cf-assist').screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())
const full = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true }) : Promise.resolve())

async function say(page: Page, text: string) {
  await page.locator('[data-cfa-say]').fill(text)
  await page.locator('[data-cfa-go]').click()
  await expect(page.locator('[data-cfa-go]')).not.toHaveAttribute('aria-busy', 'true', { timeout: 90_000 })   // 机器忙时一句要几十秒
}

test('say it in one sentence → preview → into the form → check → save', async ({ page }) => {
  const errors: string[] = []   // 页面不许有 pageerror(几段脚本拼成一个 <script> 时,拼接处断句错会整页停在「…」)
  page.on('pageerror', e => { errors.push(String(e.stack || e)); console.log('pageerror', e.stack) })
  page.on('requestfailed', r => console.log('requestfailed', r.method(), r.url(), r.failure()?.errorText))
  await page.goto(`${BASE}/hub.html#/t/stoneford-town/create`)
  await expect(page.locator('#cf-assist [data-cfa-say]')).toBeVisible({ timeout: 150_000 })   // 冷的 HOME:第一次要建世界取素材槽

  expect(errors).toEqual([])
  // ① 地点门槛
  await say(page, '拿到钥匙后才能进地下室')
  const prev = page.locator('[data-cfa-preview] li')
  await expect(prev).toHaveCount(3)
  await expect(prev.nth(0)).toContainText('铁钥匙')
  await expect(prev.nth(2)).toContainText('晨光小教堂')
  await expect(prev.nth(2)).toContainText('还没有标记「has.key」')
  await expect(page.locator('[data-cfa-reply]')).toContainText('杂货铺')
  await shot(page, '01-gate-preview')
  await page.locator('[data-cfa-apply]').click()
  await expect(page.locator('[data-cfa-done]')).toBeVisible()
  await expect(page.locator('[data-sec="clue"][data-name="name"]').first()).toHaveValue('铁钥匙')
  await expect(page.locator('[data-sec="rule"][data-name="trigger_ui.kw"]').first()).toHaveValue('钥匙')   // 一行选择能表示的:照常是选择框
  await expect(page.locator('[data-cf-trtext]').first()).toContainText('晨光小教堂')                      // 多条件的:只读一句话

  // ② 收集条件
  await say(page, '玩到坏结局可以带走老板')
  await expect(page.locator('[data-cfa-preview] li')).toHaveCount(2)
  await expect(page.locator('[data-cfa-preview] li').nth(1)).toContainText('走到结局 #1 能带走')
  await page.locator('[data-cfa-apply]').click()
  await expect(page.locator('[data-sec="soul"][data-name="name"]').first()).toHaveValue('老板')
  await expect(page.locator('[data-sec="soul"][data-name="collect"]').first()).toHaveValue('ending')
  await expect(page.locator('[data-sec="ending"][data-name="kind"]').first()).toHaveValue('fail')

  // ③ 做不到的:这个模板不开放数值 → 说人话 + 最接近的替代;点替代 = 用它再问一次(角色条件:被骗三次她就走)
  await say(page, '她被骗三次就会离开')
  const cant = page.locator('[data-cfa-unsupported] li')
  await expect(cant.first()).toContainText('这个模板不开放「数值」')
  await expect(cant).toContainText(['用三个标记接力', '这个模板不开放「数值」这种效果'])
  await expect(page.locator('[data-cfa-apply]')).toHaveCount(0)
  await shot(page, '02-unsupported')
  await page.locator('[data-cfa-near="0"]').click()
  await expect(page.locator('[data-cfa-preview] li')).toHaveCount(3)
  await expect(page.locator('[data-cfa-preview] li').nth(2)).toContainText('艾琳娜不再看你')
  await shot(page, '03-nearest-preview')
  await page.locator('[data-cfa-apply]').click()
  await expect(page.locator('[data-cf-trtext]')).toHaveCount(4)   // 地下室那条 + 接力的三条(都带 if 两个条件)

  // 检查 · 存:走创作台原来的那条路(creation/work),作品的 plot.json 就是助手写的那几条
  await page.locator('[data-cf-card="zh.title"]').fill('雾夜钥匙')
  await page.locator('[data-cf-card="zh.pitch"]').fill('地下室的门只为拿到钥匙的人打开。')
  await page.locator('[data-cf-check]').click()
  await expect(page.locator('[data-cf-msg]')).toContainText('检查通过', { timeout: 60_000 })
  await page.waitForLoadState('networkidle', { timeout: 300_000 }).catch(() => {})   // 页面自己的素材槽请求(冷构建)先跑完,存不跟它抢同一个模板
  await page.locator('[data-cf-save]').click()
  await expect(page.locator('[data-cf-msg]')).toContainText('stoneford-town-mine', { timeout: 600_000 })   // 第一次存 = 先拷一份模板 + lint(冷构建,机器忙时几分钟)
  await full(page, '04-form-saved')
  const work = readdirSync(join(HOME, 'templates')).find(d => d.startsWith('stoneford-town-mine')) || ''   // 作品文件夹(<id>.template)
  const plot = JSON.parse(readFileSync(join(HOME, 'templates', work, 'plots', 'mine', 'plot.json'), 'utf-8'))
  const trig = Object.values(plot.triggers) as any[]
  expect(trig).toHaveLength(5)
  expect(trig.some(t => t.when.entry === 'T004/chapel' && t.if[0].flag === 'has.key' && t.if[0].is === false)).toBe(true)
  expect(plot.collect).toEqual({ mine_N01: { on: { ending: 'mine_E1' }, rarity: 'rare' } })
  expect(plot.endings.mine_E1.kind).toBe('fail')

  expect(errors).toEqual([])
  const calls = (await (await fetch(`${AI}/_mock/state`)).json()).calls
  expect(calls.map((c: any) => c.say)).toContain('用三个标记接力:每被骗一次设一个,第三个设上时她离开')
  expect(calls).toHaveLength(12)   // 四句话 × read_form · propose · done
})
