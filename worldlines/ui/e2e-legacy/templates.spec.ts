// 模板库 + 3.0 游玩(Mock 3.0 原样 + 真引擎适配,/v3.html)(docs/TEMPLATE-PROTOCOL.md):列表 / Lint 读真引擎(NeonRP webui/template_routes.py),
// 开局 = POST /session {slug: "tpl--<id>"};「让世界自己走」= 引擎 tick(玩法包规则 + 触发器,0 token)。
import { test, expect, type Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

async function prep(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh')
  })
}

test('模板库:卡片、结局模式、玩法包扩展、Lint 面板', async ({ page }) => {
  await prep(page)
  await page.goto('/local/templates')
  await expect(page.getByTestId('templates-page')).toBeVisible()
  const elena = page.getByTestId('tpl-stoneford-elena')
  await expect(elena).toContainText('多结局')
  await expect(elena).toContainText('可发布')
  const market = page.getByTestId('tpl-stoneford-market')
  await expect(market).toContainText('+economy')
  await expect(market).toContainText('+factions')
  await page.getByTestId('tpl-lint-stoneford-elena').click()
  // v3 四类检查:可发布(无阻断),只剩两条提醒 —— 可选素材没填、还没量过每回合 token
  const lint = page.getByTestId('lint-panel')
  await expect(lint).toContainText('可选槽位没填')
  await expect(lint).toContainText('还没有回合')
  await expect(elena).toContainText('可发布')
})

// 1×1 PNG
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')

test('Lint 面板的素材槽:缺图的剧情物品可以直接上传,缩略图出现', async ({ page }) => {
  await prep(page)
  await page.goto('/local/templates')
  await page.getByTestId('tpl-lint-stoneford-elena').click()
  const slot = page.getByTestId('slot-item.icon:I910')
  await expect(slot).toContainText('褪色的护身符')
  await expect(slot.locator('img')).toHaveCount(0)
  const chooser = page.waitForEvent('filechooser')
  await slot.getByRole('button', { name: '上传' }).click()
  await (await chooser).setFiles({ name: 'amulet.png', mimeType: 'image/png', buffer: PNG })
  await expect(slot.locator('img')).toHaveCount(1, { timeout: 10_000 })
  await expect(slot).toContainText('已有')
})


// ── 3.0(/v3.html):Mock 3.0 的页面原样,状态与动作全部来自真引擎 ──
async function openV3(page: Page, tpl: string) {
  await prep(page)
  await page.goto('/local/templates')
  await page.getByTestId(`tpl-start-${tpl}`).click()
  await expect(page).toHaveURL(/\/v3\.html\?save=tpl-/, { timeout: 20_000 })
  await expect(page.locator('#v3boot')).toHaveCount(0, { timeout: 30_000 })
}

test('3.0 开局:Mock 的游玩页原样 · 地图 / 集市 / 主角团都是这一局的真实状态', async ({ page }) => {
  await openV3(page, 'stoneford-market')
  await expect(page.locator('#v3title')).toHaveText('石津镇 · 驿路与商队')
  await expect(page.locator('.tabsTop')).toContainText('模拟工作台')
  await expect(page.locator('#pmain .crumbs')).toContainText('石津镇')        // 真实的层级图
  await expect(page.locator('#rbody')).toContainText('集市 · 石津镇')          // economy mixin 的市场
  await expect(page.locator('#rbody')).toContainText('艾琳娜')
  const st = await page.evaluate("({ loc: E.where('player').at, price: E.get('price.T001.grain') })") as { loc: string; price: unknown }
  expect(st.loc).toBe('T001/gate_north')
  expect(typeof st.price).toBe('number')
})

test('3.0 推进一格 = 引擎 tick:世界规则自己动(0 token),模拟工作台的变化事件流里有 tick 规则的改动', async ({ page }) => {
  await openV3(page, 'stoneford-market')
  // 商量层开着时开局只有开场拍(世界不动、回合号停在 0);tick 照样改变量 → 看 tick 规则的变化数,不看回合号
  const ticks = () => page.evaluate<number>("E.s.events.filter(e => e.by === 'tick').reduce((n, e) => n + e.changes.length, 0)")
  const n0 = await ticks()
  await expect(async () => {
    await page.locator('#stepBtn').click()
    expect(await ticks()).toBeGreaterThan(n0)
  }).toPass({ timeout: 45_000, intervals: [1_000, 2_000, 3_000] })
  await page.locator('[data-view=studio]').click()
  await expect(page.locator('#smain')).toContainText('世界规则(tick)', { timeout: 10_000 })
})

test('3.0 世界线:模拟工作台「⑂ 分支」= 从当前提交回滚分岔(POST /rollback)', async ({ page }) => {
  // e2e 没有模型,开局不产生提交;世界线用一份固定的提交图,检查按钮真的向引擎要了分岔
  await page.route(/\/api\/v1\/play\/engine\/commits$/, r => r.fulfill({ json: { branch: 'main', head: 'c2', branches: { main: { tip: 'c2' } },
    nodes: [{ id: 'c1', parent: null, branch: 'main', turn_seq: 1, label: '回合 1' }, { id: 'c2', parent: 'c1', branch: 'main', turn_seq: 2, label: '回合 2' }] } }))
  let asked = ''
  await page.route(/\/rollback$/, r => { asked = (r.request().postDataJSON() as { commit: string }).commit; return r.fulfill({ json: { ok: true, branch: 'main-2' } }) })
  await openV3(page, 'stoneford-market')
  await page.locator('[data-view=studio]').click()
  await page.locator('#sBr').click()
  await expect.poll(() => asked, { timeout: 15_000 }).toBe('c2')
})

test('3.0 Schema 页签:改类的增长策略 = 创作者操作落到引擎', async ({ page, request }) => {
  await openV3(page, 'stoneford-market')
  await page.locator('[data-view=studio]').click()
  await page.locator('[data-lt=schema]').click()
  await page.locator('select[data-pol=rumor]').selectOption('approve')
  await expect.poll(async () => (await (await request.get('/api/v1/play/engine/approvals')).json()).policies.rumor, { timeout: 10_000 }).toBe('approve')
})

test('多结局模板:引擎给出剧情阶段与结局槽位,谜底在结局前不返回', async ({ page, request }) => {
  await openV3(page, 'stoneford-elena')
  const v = await (await request.get('/api/v1/play/engine/template')).json()
  expect(v.template.mode.ending).toBe('multi')
  expect(v.plots[0].stages).toEqual(['相遇', '线索', '抉择'])
  expect(Object.keys(v.plots[0].endings).sort()).toEqual(['E10', 'E11', 'E19'])
  expect(v.reveal).toBeUndefined()
})

// ── 3.0 组装 · Lint = 模板创作:Mock 的页面原样,数据与写操作都是这一局所用的 template(neonrp template/author.py)──
async function openStudioLink(page: Page) {
  await page.locator('[data-view=studio]').click()
  await page.locator('[data-ct=link]').click()
  await expect(page.locator('.lkhead b')).toBeVisible({ timeout: 30_000 })
}

test('三镇驿路(Mock 3.0 的世界):三个集市 + 组装 · Lint 读引擎的真实检查 / 槽位 / 契约', async ({ page }) => {
  await prep(page)
  await page.goto('/v3.html?tpl=stoneford-three-towns')
  await expect(page.locator('#v3boot')).toHaveCount(0, { timeout: 30_000 })
  await expect(page.locator('#v3title')).toHaveText('灰雾北境 · 三镇驿路')
  expect(await page.evaluate('Object.keys(MARKETS)')).toEqual(['T001', 'T004', 'T002'])
  await openStudioLink(page)
  await expect(page.locator('.lkhead b')).toHaveText('可以发布')
  await expect(page.locator('[data-lk=slots]')).toContainText(/素材槽位 \d+\/\d+/)
  await page.locator('[data-lk=contract]').click()
  await page.locator('[data-ck=ts]').click()
  await expect(page.locator('pre.code')).toContainText('stoneford-three-towns')
})

test('创作 op 写回模板:改配方后端 / 加槽位 → 模板 ui 变了;非法的被引擎拒绝', async ({ page, request }) => {
  await prep(page)
  await page.goto('/v3.html?tpl=stoneford-three-towns')
  await expect(page.locator('#v3boot')).toHaveCount(0, { timeout: 30_000 })
  await openStudioLink(page)
  const ui = async () => (await (await request.get('/api/v1/local/templates/stoneford-three-towns/ui')).json()).ui
  await page.locator('[data-lk=recipe]').click()
  await page.locator('#rBack').selectOption('openai')
  await expect.poll(async () => (await ui()).recipe.backend, { timeout: 15_000 }).toBe('openai')
  await page.locator('[data-lk=slots]').click()
  await page.locator('#asC').selectOption('place')
  await page.locator('#asS').fill('night')
  await page.locator('#asGo').click()
  await expect.poll(async () => (await ui()).slots.some((s: { cls: string; slot: string }) => s.cls === 'place' && s.slot === 'night'), { timeout: 15_000 }).toBe(true)
  const bad = await request.post('/api/v1/local/templates/stoneford-three-towns/ops', { data: { ops: [{ op: 'add_slot', cls: 'place', slot: 'night' }] } })
  expect(bad.status()).toBe(422)
  expect((await bad.json()).refused[0].why).toContain('已经声明过')
})

test('世界页「＋ 新建世界」= 另存当前模板 → 用新模板开一局,素材车间建好 space', async ({ page, request }) => {
  await prep(page)
  await page.goto('/v3.html?tpl=stoneford-three-towns')
  await expect(page.locator('#v3boot')).toHaveCount(0, { timeout: 30_000 })
  await page.locator('[data-view=worlds]').click()
  page.once('dialog', d => d.accept('雾港 · 我的三镇'))
  await page.locator('[data-v3fork]').click()
  await expect(page.locator('#v3title')).toHaveText('雾港 · 我的三镇', { timeout: 30_000 })
  const tid = await page.evaluate<string>('V3.template.id')
  expect(tid).toMatch(/^stoneford-three-towns-f[a-z0-9]{4}$/)
  const rows = (await (await request.get('/api/v1/local/templates')).json()).templates as { id: string }[]
  expect(rows.some(r => r.id === tid)).toBe(true)
  const v = await (await request.get(`/api/v1/local/templates/${tid}/ui`)).json()
  expect(v.writable).toBe(true)
  expect(v.forked_from.id).toBe('stoneford-three-towns')
})
