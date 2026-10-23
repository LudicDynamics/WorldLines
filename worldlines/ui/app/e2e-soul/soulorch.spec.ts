// 角色编排台(10-16):编排页「世界 / 角色」切换 → 三类角色列表 → 画这个角色的图 → 改 chat 节点参数 → 写回
// (独立角色写角色库;世界里的角色写模板覆盖,只改这个世界)→ 右栏真的和它聊,按写回的图回话。截图进 WL_SOUL_SHOTS。
import { test, expect, type Page } from '@playwright/test'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_SOUL_BASE || 'http://127.0.0.1:8796'
const HOME = process.env.WL_SOUL_HOME || ''
const SHOTS = process.env.WL_SOUL_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())

async function openBench(page: Page) {
  await page.goto(`${BASE}/`)
  await expect(page.locator('#ctx')).toContainText('真引擎', { timeout: 90_000 })   // 认出是本机引擎(不是 Hub)之后再进编排台
  await page.locator('.nav [data-go=orch]').click()
  await page.locator('[data-somode=soul]').click()
  await expect(page.locator('[data-sopick]')).toBeVisible()
}
async function pick(page: Page, tab: string, name: RegExp) {
  await page.locator('[data-sopick]').click()
  await page.locator(`[data-sotab=${tab}]`).click()
  await page.locator('.sopick .row1', { hasText: name }).first().click()
  await expect(page.locator('[data-sopick]')).toContainText(name)   // 这个角色的图读回来了
}
// 节点内部的一个参数(按名字找,不靠顺序)
const knob = (page: Page, k: string) => page.locator('#board .well dl.kv dt', { hasText: new RegExp(`^${k}$`) }).locator('xpath=following-sibling::dd[1]').locator('input,textarea')
async function setBubbles(page: Page, n: string) {
  await page.locator('#board .nd').filter({ hasText: '直聊' }).first().click()
  await page.locator('.crumb [data-layer=node]').click()
  await expect(page.locator('#board .well dl.kv input')).toHaveCount(3)   // history · doc_cap · max_bubbles(来自 hooks 的 chat 参数)
  await knob(page, 'max_bubbles').fill(n)
  await page.locator('.crumb [data-layer=graph]').click()
}

test('角色面:三类角色 · 独立角色写回角色库 · 对话测试按写回的图回话', async ({ page }) => {
  await openBench(page)
  await page.locator('[data-sopick]').click()
  for (const [tab, min] of [['independent', 1], ['standalone', 3], ['takeable', 3]] as const) {
    const n = Number(((await page.locator(`[data-sotab=${tab}]`).textContent()) || '').split('·').pop())
    expect(n, tab).toBeGreaterThanOrEqual(min)
  }
  await shot(page, '01-pick')
  await page.locator('[data-sotab=independent]').click()
  await page.locator('.sopick .row1', { hasText: /阿雾|Awu/ }).click()
  await expect(page.locator('#board .nd').filter({ hasText: '直聊' })).toBeVisible()
  await expect(page.locator('[data-sosave]')).toBeDisabled()
  await expect(page.locator('#board .tb [data-add=tick]')).toBeVisible()
  await expect(page.locator('#board .tb [data-add=mode]')).toHaveCount(0)
  await shot(page, '02-graph')
  await setBubbles(page, '1')
  await expect(page.locator('[data-sosave]')).toBeEnabled()
  await page.locator('[data-sosave]').click()
  await expect(page.locator('.orchsave')).toContainText('写回角色库')
  if (HOME) {
    const f = join(HOME, '.worldlines/souls/awu/agents/orchestration.json')
    expect(existsSync(f)).toBe(true)
    expect(JSON.parse(readFileSync(f, 'utf-8')).nodes.chat.max_bubbles).toBe(1)
  }
  await page.locator('#soin').fill('船还好吗')
  await page.locator('#sosend').click()
  await expect(page.locator('#sochat .m.soul')).toHaveCount(1)   // max_bubbles = 1:只回一条
  await shot(page, '03-saved-chat')
})

test('世界里的角色:只改这个世界(模板覆盖)· 工具注册表换成角色的 · 世界面不出角色节点', async ({ page }) => {
  await openBench(page)
  await pick(page, 'standalone', /薇拉|Vera/)
  await setBubbles(page, '2')
  await page.locator('[data-sosave]').click()
  await expect(page.locator('.orchsave')).toContainText('写回世界 wuwu')
  if (HOME) {
    const f = join(HOME, 'templates/wuwu.template/prompts/souls/vera/orchestration.json')
    expect(JSON.parse(readFileSync(f, 'utf-8')).nodes.chat.max_bubbles).toBe(2)
    expect(existsSync(join(HOME, 'templates/wuwu.template/world/souls/vera-si-vera0001/agents/orchestration.json'))).toBe(false)
  }
  await page.locator('.crumb [data-layer=tools]').click()
  await expect(page.locator('#board table.t')).toContainText('image.generate')
  await expect(page.locator('#board table.t')).not.toContainText('end_combat')
  await shot(page, '04-tools')
  await page.locator('[data-somode=world]').click()
  await expect(page.locator('[data-sopick]')).toHaveCount(0)
  await expect(page.locator('#board .tb [data-add=chat]')).toHaveCount(0)
})

test('简单世界观:世界里的角色复刻原来的世界 → 改一句 → 只改这个世界;角色库的角色从空白写 → 存进角色库', async ({ page }) => {
  await openBench(page)
  await pick(page, 'standalone', /薇拉|Vera/)
  await page.locator('[data-solayer=ambient]').click()
  await expect(page.locator('#board h2')).toContainText('简单世界观')
  await expect(page.locator('#board .tag').first()).toContainText('复刻自原来的世界')
  await expect(page.locator('[data-sop="0:name"]')).toHaveValue('港务所')
  await page.locator('[data-sor="morning:doing"]').fill('去工坊修灯')
  await page.locator('[data-soamb=save]').click()
  await expect(page.locator('#board .note')).toContainText('只改这个世界')
  if (HOME) expect(JSON.parse(readFileSync(join(HOME, 'templates/wuwu.template/prompts/souls/vera/ambient/world.json'), 'utf-8')).routine.find((r: { at: string }) => r.at === 'morning').doing).toBe('去工坊修灯')
  await shot(page, '05-ambient')
  await pick(page, 'independent', /阿雾|Awu/)
  await expect(page.locator('[data-soamb=blank]')).toBeVisible()
  await expect(page.locator('[data-soamb=replicate]')).toHaveCount(0)   // 角色库的角色没有原来的世界
  await page.locator('[data-soamb=blank]').click()
  await page.locator('[data-sow=setting]').fill('海边小镇,雾多')
  await page.locator('[data-soamb=save]').click()
  await expect(page.locator('#board .note')).toContainText('角色库')
  if (HOME) expect(JSON.parse(readFileSync(join(HOME, '.worldlines/souls/awu/ambient/world.json'), 'utf-8')).setting).toBe('海边小镇,雾多')
})

test('专属表情:上传一张 PNG → 写含义(四语)和什么时候发 → 存进角色库的 stickers.json', async ({ page }) => {
  await openBench(page)
  await pick(page, 'independent', /阿雾|Awu/)
  await page.locator('[data-solayer=stickers]').click()
  await expect(page.locator('#board h2')).toContainText('专属表情')
  await page.locator('#sostkid').fill('fish')
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
  await page.locator('#sostkfile').setInputFiles({ name: 'fish.png', mimeType: 'image/png', buffer: png })
  await expect(page.locator('#board .note')).toContainText('上传好了')
  await page.locator('[data-sol="fish:zh"]').fill('举起一条鱼')
  await page.locator('[data-sol="fish:zh"]').press('Tab')
  await page.locator('[data-sowhen="fish"]').fill('炫耀今天的货')
  await page.locator('[data-sowhen="fish"]').press('Tab')
  await expect(page.locator('#board .note')).toContainText('存好了')
  await shot(page, '08-stickers')
  if (HOME) {
    const m = JSON.parse(readFileSync(join(HOME, '.worldlines/souls/awu/stickers/stickers.json'), 'utf-8'))
    expect(m.fish.label.zh).toBe('举起一条鱼'); expect(m.fish.when).toBe('炫耀今天的货')
  }
})

// ── 工作台去 mock 第 3 批(10-17)──

test('自由行动的参数从节点读:加 tick 节点 → interval_min 改 1 → 写回角色库的 orchestration.json', async ({ page }) => {
  await openBench(page)
  await pick(page, 'independent', /阿雾|Awu/)
  await page.locator('#board .tb [data-add=tick]').click()
  await page.locator('.crumb [data-layer=node]').click()
  await expect(page.locator('#board h2')).toContainText('自由行动')
  for (const k of ['interval_min', 'daily_max', 'proactive_daily', 'prompt']) await expect(knob(page, k)).toHaveCount(1)
  await expect(knob(page, 'interval_min')).toHaveValue('10')   // 缺省 = 引擎的默认值
  await knob(page, 'interval_min').fill('1')
  await shot(page, '09-tick-knobs')
  await page.locator('.crumb [data-layer=graph]').click()
  await page.locator('[data-sosave]').click()
  await expect(page.locator('.orchsave')).toContainText('写回角色库')
  if (HOME) {
    const g = JSON.parse(readFileSync(join(HOME, '.worldlines/souls/awu/agents/orchestration.json'), 'utf-8'))
    const tick = Object.values(g.nodes as Record<string, { kind: string; interval_min: number; daily_max: number }>).find(n => n && n.kind === 'tick')
    expect(tick && tick.interval_min).toBe(1)
    expect(tick && tick.daily_max).toBe(24)
  }
})

test('节点种类 / 步骤来自接口:hooks 里加一步就画出来,拿掉一种就不能加', async ({ page }) => {
  await page.route('**/api/v1/souls/orchestration?*', async route => {
    const r = await route.fetch(); const j = await r.json()
    j.hooks.node_kinds.chat.steps.push({ by: 'engine', id: 'probe', doc: 'PROBE-STEP' })
    delete j.hooks.node_kinds.reflect
    await route.fulfill({ response: r, json: j })
  })
  await openBench(page)
  await pick(page, 'independent', /阿雾|Awu/)
  await expect(page.locator('#board .tb [data-add=tick]')).toBeVisible()
  await expect(page.locator('#board .tb [data-add=reflect]')).toHaveCount(0)
  await expect(page.locator('#board .tb [data-add=in_world]')).toHaveCount(0)   // addable: false
  await page.locator('#board .nd').filter({ hasText: '直聊' }).first().click()
  await page.locator('.crumb [data-layer=node]').click()
  await expect(page.locator('#board .lane')).toContainText('读文档')
  await expect(page.locator('#board .lane')).toContainText('PROBE-STEP')
  await shot(page, '10-steps-from-hooks')
})

test('世界里那一拍:艾琳娜的真实设置 → 改成 S-direct → 写进模板的 pack.engine(只改这个世界)', async ({ page }) => {
  await openBench(page)
  await pick(page, 'standalone', /艾琳娜|Elena/)
  await page.locator('#board .nd').filter({ hasText: '世界里那一拍' }).first().click()
  await page.locator('.crumb [data-layer=node]').click()
  await expect(page.locator('[data-soiwnow]')).toContainText('S-judge')   // 石津镇 · rpg 包默认
  await expect(page.locator('#board .well table.t')).toContainText('不在玩家眼前')
  await expect(page.locator('#board .well')).toContainText('soul_step')
  await page.locator('[data-soiw]').selectOption('S-direct')
  await page.locator('[data-soiwsave]').click()
  await expect(page.locator('[data-soiwnow]')).toContainText('S-direct')
  await expect(page.locator('[data-soiwmsg]')).toContainText('stoneford-elena')
  await shot(page, '11-in-world')
  if (HOME) {
    const t = JSON.parse(readFileSync(join(HOME, 'templates/stoneford-elena.template/template.json'), 'utf-8'))
    expect(t.pack.engine.turn.parallel.souls.per_soul.elena).toBe('S-direct')
    expect(t.pack.engine.turn.mode).toBe('v3')
  }
  await page.locator('.crumb [data-layer=graph]').click()
  await expect(page.locator('[data-sosave]')).toBeDisabled()   // 世界那一拍不是图的一部分:图没变
})

test('世界里那一拍跟着「当前世界」:角色库的角色在当前世界里有绑定就看它,没有看第一个绑定的;写回进它显示的那个世界', async ({ page }) => {
  test.skip(!HOME, '要隔离 HOME:把阿雾 link 进两个世界')
  const tj = (t: string) => join(HOME, `templates/${t}.template/template.json`)
  const keep: Record<string, string> = {}
  for (const t of ['spice-witch', 'wuwu']) {   // 阿雾进两个世界(用完还原:前面几条用例要她是独立角色)
    keep[t] = readFileSync(tj(t), 'utf-8')
    const d = JSON.parse(keep[t]); d.souls = [...(d.souls || []), { lib: 'awu', role: 'npc' }]
    writeFileSync(tj(t), JSON.stringify(d, null, 2))
  }
  try {
    await openBench(page)
    await page.locator('#wlWorld').selectOption('wuwu')
    await pick(page, 'library', /阿雾|Awu/)
    await page.locator('#board .nd').filter({ hasText: '世界里那一拍' }).first().click()
    await page.locator('.crumb [data-layer=node]').click()
    const tag = page.locator('#board .well .tag').first()
    await expect(tag).toContainText('wuwu')
    await page.locator('#wlWorld').selectOption('spice-witch')
    await expect(tag).toContainText('spice-witch')   // 换世界 = 重读这一拍
    await page.locator('#wlWorld').selectOption('stoneford-town')
    await expect(tag).toContainText('spice-witch')   // 石津镇没 link 她:第一个绑定的世界
    await page.locator('#wlWorld').selectOption('wuwu')
    await expect(tag).toContainText('wuwu')
    await page.locator('[data-soiw]').selectOption('S-free')
    await page.locator('[data-soiwsave]').click()
    await expect(page.locator('[data-soiwnow]')).toContainText('S-free')
    await shot(page, '12-in-world-current')
    expect(JSON.parse(readFileSync(tj('wuwu'), 'utf-8')).pack.engine.turn.parallel.souls.per_soul.awu).toBe('S-free')
    expect(JSON.stringify(JSON.parse(readFileSync(tj('spice-witch'), 'utf-8')).pack)).not.toContain('per_soul')
  } finally {
    for (const t of Object.keys(keep)) writeFileSync(tj(t), keep[t])
  }
})
