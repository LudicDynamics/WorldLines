// WorldLines 1.0 界面(app/,UI/UX 固定为 prototypes/v3)对着真引擎:一览读模板库 · 测试台读这一局 · 地图读引擎的层。
// e2e 引擎没有模型:开场真跑。两拍(商量 / 清算)的展示属于私有层,它的测试随私有层维护,不在本仓(跑的时候同步到 e2e/private/)。
import { test, expect } from '@playwright/test'
import { ready, SHOTS } from './helpers'

test.use({ viewport: { width: 1440, height: 900 } })
// 事件流:测试台读调试流 /events?debug=1(aaffb1af 10-15 起;玩家视角的是 /events)。不能写成 /events(\?|$) ——
// 会把 /api/v1/play/schema/events?limit=3000 也接走(返回一段 SSE 给 JSON 读,引擎状态就成了「连不上引擎」)
const EVENTS = /\/events(\?debug=1)?$/

test('根路径进的就是新界面:游玩一览 = 模板库,按合约筛选', async ({ page }) => {
  await page.goto('/')
  await ready(page)
  await expect(page.locator('.nav [data-go=cat]')).toHaveClass(/on/)
  const cards = page.locator('#catPlane .wc[data-w]')
  expect(await cards.count()).toBeGreaterThanOrEqual(3)
  await expect(page.locator('#catPlane')).toContainText('石津镇')
  await page.locator('.catbar [data-cf=none]').click()
  expect(await page.locator('#catPlane .wc[data-w]').count()).toBeGreaterThanOrEqual(1)
  await page.locator('#catPlane .wc[data-w]').first().click()
  await expect(page.locator('#shelf')).toHaveClass(/on/)
  await expect(page.locator('#shelf')).toContainText('合约体检')
})

test('世界面 · 地图:引擎的层(石津镇)· 树 · JSON;没接上的台子标演示数据', async ({ page }) => {
  test.setTimeout(120_000)  // 第一次打开世界要复制文件;整套跑时引擎忙,45 秒不够
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('#mwSel')).toBeVisible({ timeout: 60_000 })   // 编辑的是选中的世界(引擎里的工作副本),不是原型演示世界
  await expect(page.locator('.mp .crumbs')).toContainText('石津镇')
  await expect(page.locator('.mnode', { hasText: '北门' })).toHaveCount(1)
  await page.locator('[data-mv=map]').click()
  await expect(page.locator('.mpbg')).toBeVisible()
  await page.locator('[data-mv=tree]').click()
  await expect(page.locator('.tlw')).toContainText('石津镇')
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#ctx')).toContainText('编排图读自引擎')   // 编排台已接引擎(只读);图上的改动是草稿
})

test('地图编辑:世界 · 角色直接编辑选中的世界 → 拖钉子写回 · 加地点写回', async ({ page }) => {
  test.setTimeout(120_000)  // 第一次编辑一个世界要复制它的文件,十几秒
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('#mwSel')).toBeVisible({ timeout: 60_000 })
  await expect(page.locator('[data-msave]')).toHaveCount(0)   // 没有「只读 / 另存」这一步
  await page.locator('[data-mv=map]').click()
  await expect(page.locator('.mnode', { hasText: '北门' })).toHaveCount(1)
  await page.waitForTimeout(800)
  // 拖北门的钉子 → PUT map/node → 重新读回来位置变了
  const pin = page.locator('.mnode', { hasText: '北门' }).locator('.pin')
  await expect(pin).toBeVisible()
  let before: { x: number; y: number; width: number; height: number } | null = null
  await expect.poll(async () => (before = await pin.boundingBox()) !== null).toBe(true)
  const put = page.waitForRequest(r => r.method() === 'PUT' && r.url().includes('/edit-local/map/node'))
  await page.mouse.move(before!.x + before!.width / 2, before!.y + before!.height / 2)
  await page.mouse.down()
  await page.mouse.move(before!.x + 60, before!.y + 48, { steps: 6 })
  await page.mouse.up()
  const body = (await put).postDataJSON()
  expect(body.addr).toBe('T001/gate_north')
  await expect.poll(async () => ((await page.locator('.mnode', { hasText: '北门' }).locator('.pin').boundingBox()) || { x: 0 }).x).toBeGreaterThan(before!.x + 30)
  // 加地点:选北门 → + 节点 → 输名字 → POST map/node,新地点出现在图上
  await page.locator('.mnode', { hasText: '北门' }).locator('.lb').click()
  await page.locator('[data-madd]').click()
  await page.locator('#maddName').fill('雾灯塔')
  await page.locator('[data-maddok]').click()
  await expect(page.locator('.mnode', { hasText: '雾灯塔' })).toHaveCount(1, { timeout: 30_000 })
  // 生成按钮在(图片生成需要模型,e2e 不点)
  await expect(page.locator('[data-mgen]').first()).toBeVisible()
})

test('第 1 步:设置抽屉(模型 · 语言)· 书架里的存档:新开一局 → 测试台 → 回一览 → 继续', async ({ page }) => {
  await page.goto('/local')
  await ready(page)
  await page.locator('[data-setopen]').first().click()
  await expect(page.locator('#setdrawer')).toHaveClass(/on/)
  expect(await page.locator('#setdrawer .setrow').count()).toBeGreaterThanOrEqual(3)
  await page.locator('[data-setlang=ja]').click()
  expect(await page.evaluate(() => localStorage.getItem('wl-local-lang'))).toBe('ja')
  await page.locator('[data-setlang=zh]').click()
  await page.locator('[data-setclose]').click()
  // 新开一局
  await page.locator('#catPlane .wc[data-w="stoneford-elena"]').click()
  await expect(page.locator('#shelf .savesbox')).toBeVisible()
  await page.locator('[data-savenew="stoneford-elena"]').click()
  await expect(page.locator('.nav [data-go=test]')).toHaveClass(/on/)
  await expect(page.locator('#mfeed .bt.open').first()).toBeVisible({ timeout: 30_000 })
  // 右栏的地图节点图(没有地图图片也有):这一层的地点 · 你在的那个亮着 · 点一个 = 「我去……」进输入框
  await expect(page.locator('.mapg .mg').first()).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('.mapg .mg.me')).toHaveCount(1)
  await page.locator('.mapg .mg:not(.me) circle').first().dispatchEvent('pointerdown', { bubbles: true })
  await expect(page.locator('#min')).toHaveValue(/^我去.+。$/)
  // 回一览:这一局出现在存档里,标「正在玩」,能继续
  await page.locator('.nav [data-go=cat]').click()
  await page.locator('#catPlane .wc[data-w="stoneford-elena"]').click()
  await expect(page.locator('#shelf .savesbox')).toContainText('正在玩')
  await page.locator('#shelf [data-saveplay]').first().click()
  await expect(page.locator('.nav [data-go=test]')).toHaveClass(/on/)
  await expect(page.locator('#mfeed .bt.open').first()).toBeVisible({ timeout: 30_000 })
})

test('Template:Pack 读真实模板 + 素材槽 · Lint 读引擎 lint · 合约页', async ({ page }) => {
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=tpl]').click()
  await expect(page.locator('.tplw h1')).toContainText('石津镇')
  await expect(page.locator('.slotgrid .slotc').first()).toBeVisible({ timeout: 15_000 })
  expect(await page.locator('.slotgrid .slotc').count()).toBeGreaterThan(5)
  await page.locator('[data-tt=lint]').click()
  await expect(page.locator('.term')).toContainText('没有 block', { timeout: 30_000 })
  await page.locator('[data-tt=ctr]').click()
  await expect(page.locator('.letter')).toBeVisible()
  // 换一个声明了合约的模板:合约页逐条盖章
  await page.locator('#tplSel').selectOption('stoneford-three-towns')
  await page.locator('[data-tt=ctr]').click()
  await expect(page.locator('.letter')).toContainText('开放冒险', { timeout: 15_000 })
  expect(await page.locator('.letter .clause').count()).toBe(6)
})

test('Template:导出一个包 → 再导入回来(10-08:改好的东西能 extract / import)', async ({ page }) => {
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=tpl]').click()
  await expect(page.locator('.tplw h1')).toContainText('石津镇')
  const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('.tplhd a.btn', { hasText: '导出' }).click()])
  expect(dl.suggestedFilename()).toBe('stoneford-elena.template.zip')
  const file = await dl.path()
  await page.locator('#tplImport').setInputFiles(file)
  await expect(page.locator('.tplw .setmsg')).toContainText('导入了模板 stoneford-elena-2', { timeout: 30_000 })
  await expect(page.locator('#tplSel')).toHaveValue('stoneford-elena-2')
  await expect(page.locator('.tplw .tag').first()).toContainText('可写', { timeout: 30_000 })
})

test('编排台读引擎生效图 · 工具注册表 = 这一局的 actions · 前端文件 = 真实契约导出', async ({ page }) => {
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#gsel')).toContainText('引擎生效图', { timeout: 15_000 })
  await expect(page.locator('.nd[data-n=resolve]')).toBeVisible()
  // 商量拍是私有层的节点(10-11 a7805c13):开源版的图里没有它
  await expect(page.locator('.nd[data-n=plan]')).toHaveCount(process.env.WL_PRIVATE_UI === 'off' ? 0 : 1)
  await page.locator('[data-layer=tools]').click()
  await expect(page.locator('#board table.t')).toContainText('move_to')
  await page.locator('.nav [data-go=fe]').click()
  await page.locator('[data-fxmode=edit]').click()   // 10-19:契约 / 事件流在「编辑」模式里
  await page.locator('[data-fxv=contract]').click()   // 10-17 前端台做实:契约一页(这个世界的 TS / GDScript / JSON)
  await page.locator('[data-fxcf=ts]').click()
  await expect(page.locator('#s-fe pre.code')).toContainText('CONTRACT_HASH', { timeout: 15_000 })
  await expect(page.locator('#s-fe pre.code')).toContainText('export interface')
})

test('世界 · 角色:角色卡 = 编辑中的世界的角色 · Schema = 类与变量', async ({ page }) => {
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await page.locator('[data-dt=schema]').click()
  await expect(page.locator('.schw')).toContainText('player.gold', { timeout: 15_000 })
  await page.locator('[data-face=soul]').click()
  await expect(page.locator('.sc[data-soul]').first()).toBeVisible()
  await expect(page.locator('.souls')).toContainText('艾琳娜')
})

test('测试台出口检查:声明了合约的模板列出固定输出;没声明的说明', async ({ page }) => {
  await page.goto('/local?tpl=stoneford-three-towns')
  await ready(page)
  await page.locator('.nav [data-go=test]').click()
  const box = page.locator('#s-test .mk-left .glass', { hasText: '出口检查' })
  await expect(box).toContainText('open-adventure', { timeout: 20_000 })
  await expect(box).toContainText('还没到出口')
})

test('剧情图读模板的 plots:阶段 · 触发器(条件)· 结局(类型 / CG)', async ({ page }) => {
  test.setTimeout(120_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode').first()).toBeVisible({ timeout: 60_000 })
  await page.locator('[data-dt=plot]').click()
  await expect(page.locator('.gn', { hasText: '相遇' })).toHaveCount(1, { timeout: 15_000 })   // plots/P10/plot.json 的 stages
  await expect(page.locator('.gn', { hasText: 'E10 记忆归来' })).toHaveCount(1)
  await expect(page.locator('.elabel', { hasText: '护身符' })).toHaveCount(1)                   // 触发器 P10.clue 的条件
  await page.locator('.elabel', { hasText: '护身符' }).click({ force: true })
  await expect(page.locator('.insp')).toContainText('P10.clue')
})

test('世界 · 角色读写真实文件:文件树 · 角色卡 · 关系图 · 数据页保存写回', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode').first()).toBeVisible({ timeout: 60_000 })
  await page.locator('[data-face=soul]').click()
  await expect(page.locator('.ftree [data-tdir="souls"]')).toBeVisible({ timeout: 15_000 })     // 真实的文件树
  await expect(page.locator('.ftree')).not.toContainText('.claude')
  await expect(page.locator('.sc', { hasText: '艾琳娜' })).toHaveCount(1)                       // souls/elena-*/soul.json
  await page.locator('[data-dt=rel]').click()
  await expect(page.locator('.elabel', { hasText: 'not_met' })).toHaveCount(1)                   // persona/relationships.json
  // 数据页:改 soul.json 的 name_local → 保存 → 卡片跟着变(重读了文件)
  await page.locator('[data-dt=data]').click()
  const name = page.locator('[data-dk="name_local"]')
  await expect(name).toBeVisible({ timeout: 15_000 })
  await name.fill('艾琳娜·改')
  const put = page.waitForRequest(r => r.method() === 'PUT' && r.url().includes('/edit-local/file'))
  await page.locator('[data-dsave]').click()
  expect(JSON.parse((await put).postDataJSON().content).name_local).toBe('艾琳娜·改')
  await page.locator('[data-dt=cards]').click()
  await expect(page.locator('.sc', { hasText: '艾琳娜·改' })).toHaveCount(1, { timeout: 15_000 })
})

test('Schema 页读编辑中的世界 · 注册变量写进这个世界 → 表里出现 → 注销', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode').first()).toBeVisible({ timeout: 60_000 })
  await page.locator('[data-dt=schema]').click()
  await expect(page.locator('.schw')).toContainText('player.gold', { timeout: 15_000 })
  await page.locator('#dvId').fill('fog.level')
  await page.locator('#dvType').selectOption('int')
  const reg = page.waitForResponse(r => r.url().includes('/edit-local/schema/register'))
  await page.locator('[data-vreg]').click()
  expect((await reg).ok()).toBe(true)
  await expect(page.locator('.schw tr', { hasText: 'fog.level' })).toHaveCount(1, { timeout: 15_000 })
  await page.locator('[data-vun="fog.level"]').click()
  await expect(page.locator('.schw tr', { hasText: 'fog.level' })).toHaveCount(0, { timeout: 15_000 })
})

test('数据页按 schema 标注:被注册成变量的字段 · 类和实例 · 声明的类型', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode').first()).toBeVisible({ timeout: 60_000 })
  await page.locator('[data-dt=data]').click()
  await page.locator('[data-dg="game/player"]').click()
  await page.locator('[data-dfile="game/player/wallet.json"]').click()
  await expect(page.locator('.kv dt', { hasText: 'gold' })).toContainText('变量 player.gold', { timeout: 15_000 })
  await page.locator('[data-face=soul]').click()
  await page.locator('[data-dt=data]').click()
  await page.locator('[data-dfile$="character/stats.json"]').first().click()
  await expect(page.locator('.schw')).toContainText('类 soul', { timeout: 15_000 })
  await expect(page.locator('.kv dt', { hasText: 'max_hp' })).toContainText('int ≥ 0')
})

test('人格控制台读写角色的人格文件:特质强度滑块 · 保存写回 core_traits.json', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode').first()).toBeVisible({ timeout: 60_000 })
  await page.locator('[data-face=soul]').click()
  await page.locator('[data-dt=persona]').click()
  const slider = page.locator('[data-pt="0:intensity"]')
  await expect(slider).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('[data-pt="0:trait"]')).toHaveValue('Gentle')                       // 艾琳娜 persona/core_traits.json
  await slider.fill('31')
  await expect(page.locator('.ptr').first().locator('.pv')).toHaveText('31')
  const put = page.waitForRequest(r => r.method() === 'PUT' && r.url().includes('/edit-local/file') && r.postDataJSON().path.endsWith('persona/core_traits.json'))
  await page.locator('[data-psave]').click()
  const saved = JSON.parse((await put).postDataJSON().content)
  expect(saved.core_traits[0]).toMatchObject({ trait: 'Gentle', intensity: 31 })
  await expect(page.locator('[data-psave]')).toBeDisabled()
})

test('编排台按模板切换编排图 · 草稿里引擎跑不了的节点标红', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#gsel option', { hasText: '狼人杀' })).toHaveCount(1, { timeout: 60_000 })   // 每个模板自己的图
  await page.locator('#gsel').selectOption('tpl:werewolf-night-village')
  await expect(page.locator('.nd', { hasText: 'night' })).toHaveCount(1)                                // 昼夜那张,不是 rpg 的
  await expect(page.locator('.orchlint')).toHaveCount(0)                                               // 引擎自己的图没有警告
  await page.locator('[data-add=loop]').click()
  await expect(page.locator('.orchlint')).toContainText('没有玩法层', { timeout: 45_000 })   // 引擎刚起时后台在给各模板预热 lint,草稿检查偶尔要二三十秒
  await expect(page.locator('.nd.orchwarn')).toHaveCount(1)
})

test('前端台事件流:补这一局的历史 · 实时流来的拍事件马上出现 · 点开看接法', async ({ page }) => {
  await page.route(/\/api\/v1\/play\/engine\/beats/, r => r.fulfill({ json: { events: [{ seq: 0, kind: 'node.enter', node: 'turn', turn: 0 }, { seq: 1, kind: 'plan.beat', turn: 0, opening: true, script: ['主持:雾从巷口漫上来。'], mic: [], board: {}, checks: [] }], next: 2, names: [] } }))
  let streams = 0   // 真的流是长连接;模拟的一发完就断,浏览器会自己重连 —— 只在第一次连上时发事件
  await page.route(EVENTS, r => r.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' },
    body: streams++ ? ': keepalive\n\n' : 'data: {"kind":"dice","turn":3,"request":"dice 1d100 侦查","answer":"42 / 60 成功","async":false}\n\n' }))
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=fe]').click()
  await page.locator('[data-fxmode=edit]').click()   // 10-19:契约 / 事件流在「编辑」模式里
  await page.locator('[data-fxv=events]').click()
  await expect(page.locator('.fevr', { hasText: '进入 回合' })).toHaveCount(1, { timeout: 15_000 })    // 补的历史
  await expect(page.locator('.fevr', { hasText: '开场' })).toHaveCount(1)
  await expect(page.locator('.fevr.new', { hasText: '1d100' })).toHaveCount(1, { timeout: 15_000 })   // 实时流来的
  await page.locator('.fevr', { hasText: '1d100' }).click()
  await page.locator('[data-fxdesk="builtin.godot"]').click()
  await expect(page.locator('.fevd pre').first()).toContainText('"dice":')                             // Godot:signal beat
  await page.locator('[data-fxdesk=ts]').click()                                                        // 网页 TS 的台
  await expect(page.locator('.fevd pre').first()).toContainText("event === 'dice'")                      // 网页 TS:BeatEvent
  await page.locator('[data-evk=dice]').click()                                                         // 筛掉掷骰
  await expect(page.locator('.fevr', { hasText: '1d100' })).toHaveCount(0)
})

// 编排台的用例都写同一个模板(e2e 引擎里 pct-house 的副本):开头先恢复默认、结尾再恢复默认 —— 谁先跑、单跑整组跑都一样
// (10-17:「加节点写回」留下的节点让后面「删节点 · 恢复默认」数错,整组连跑才挂)
async function orchDefault(page: import('@playwright/test').Page) {
  await page.locator('[data-orestore]').click()
  await expect(page.locator('.orchsave')).toContainText('写回模板 pct-house', { timeout: 30_000 })
  // 重新打开编排台:写回栏的那句「写回模板 …」会一直留着、盖住后面的「还没写回」;用例要的是一张干净的、从引擎读来的默认图
  await page.reload()
  await ready(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#gsel option', { hasText: '灰橡宅' })).toHaveCount(1, { timeout: 60_000 })
  await page.locator('#gsel').selectOption('tpl:pct-house')
  await expect(page.locator('.nd[data-n=resolve]')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.orchsave')).toContainText('和模板里的一致')
}

test('编排图写回模板:加节点 → 写回 → 引擎重新给出的图里就有它', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#gsel option', { hasText: '灰橡宅' })).toHaveCount(1, { timeout: 60_000 })
  await page.locator('#gsel').selectOption('tpl:pct-house')
  await expect(page.locator('.nd[data-n=resolve]')).toBeVisible({ timeout: 30_000 })
  await orchDefault(page)
  const before = await page.locator('.nd').count()
  await page.locator('[data-add=loop]').click()
  await expect(page.locator('.orchsave')).toContainText('还没写回')
  const ops = page.waitForResponse(r => r.url().includes('/templates/pct-house/ops'))
  await page.locator('[data-orchsave]').click()
  expect((await ops).ok()).toBe(true)
  await expect(page.locator('.orchsave')).toContainText('写回模板 pct-house', { timeout: 30_000 })
  await expect(page.locator('.nd')).toHaveCount(before + 1)                                // 读回来的引擎图里有新节点
  await expect(page.locator('[data-orchsave]')).toBeDisabled()
  await orchDefault(page)                                                                  // 不给后面的用例留下这个节点
  await expect(page.locator('.nd')).toHaveCount(before)
})

test('编排台:清算拍的出状态二选一 · 删节点(删掉起点就从清算开始)· 写回 · 恢复默认', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#gsel option', { hasText: '灰橡宅' })).toHaveCount(1, { timeout: 60_000 })
  await page.locator('#gsel').selectOption('tpl:pct-house')
  await expect(page.locator('.nd[data-n=resolve]')).toBeVisible({ timeout: 30_000 })
  await orchDefault(page)   // 从玩法包默认的图开始(不管前面的用例写回过什么)
  // 出状态:双击清算节点 → 节点内部有二选一 → 选「文字直出 → Jev」→ 回图上,写回栏里显示它、可以写回
  await page.locator('.nd[data-n=resolve]').click()
  await page.locator('.tb [data-layer=node]').click()
  await expect(page.locator('.orchstate')).toContainText('出状态')
  await page.locator('[data-ostate=jev]').click()
  await expect(page.locator('[data-ostate=jev]')).toHaveClass(/solid/)
  await page.locator('.crumb [data-layer=graph]').click()
  await expect(page.locator('.orchsave')).toContainText('文字直出 → Jev')
  await expect(page.locator('.orchsave')).toContainText('还没写回')
  // 删节点:有商量拍(私有层)就删它,起点挪到清算;开源版没有它,删一个层节点
  const victim = (await page.locator('.nd[data-n=plan]').count()) ? 'plan' : await page.locator('.nd:not([data-n=resolve])').first().getAttribute('data-n')
  const before = await page.locator('.nd').count()
  await page.locator(`.nd[data-n="${victim}"]`).click()
  await page.locator(`[data-onodedel="${victim}"]`).click()
  await expect(page.locator('.nd')).toHaveCount(before - 1)
  if (victim === 'plan') await expect(page.locator('.nd[data-n=resolve] .start')).toBeVisible()
  const ops = page.waitForResponse(r => r.url().includes('/templates/pct-house/ops'))
  await page.locator('[data-orchsave]').click()
  expect((await ops).ok()).toBe(true)
  // 写回做完(读回了引擎的图)才有这句;「写回模板 pct-house」按钮上一直有,等它等于没等(10-21)
  await expect(page.locator('.orchsave')).toContainText('下一局开始按这张图走', { timeout: 30_000 })
  await expect(page.locator('.nd')).toHaveCount(before - 1)                                 // 引擎读回来的图里没有它
  await expect(page.locator('.orchsave')).toContainText('文字直出 → Jev')                  // 出状态也写进去了
  // 恢复默认:覆盖去掉,节点回来
  await page.locator('[data-orestore]').click()
  await expect(page.locator('.nd')).toHaveCount(before, { timeout: 30_000 })
  await expect(page.locator('.orchsave')).not.toContainText('文字直出 → Jev')
})

test('触发器创作:剧情图上从阶段拖到结局 = 新触发器 · 检查器里填词 · 写回 plot.json', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode').first()).toBeVisible({ timeout: 60_000 })
  await page.locator('[data-dt=plot]').click()
  const from = page.locator('.gn', { hasText: '线索' }), to = page.locator('.gn', { hasText: 'E11' })
  await expect(from).toHaveCount(1, { timeout: 15_000 })
  const port = await from.locator('[data-gp]').boundingBox(), dst = await to.boundingBox()
  let posts = 0
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/templates/stoneford-elena/plots')) posts++ })
  await page.mouse.move(port!.x + port!.width / 2, port!.y + port!.height / 2)
  await page.mouse.down()
  await page.mouse.move(dst!.x + dst!.width / 2, dst!.y + dst!.height / 2, { steps: 10 })
  await page.mouse.up()
  await expect(page.locator('.insp')).toContainText('条件还没填', { timeout: 15_000 })          // 新触发器先是草稿
  await expect(page.locator('.elabel', { hasText: '草稿' })).toHaveCount(1)
  expect(posts, '没填完的触发器不写进文件(引擎会认为剧情文件有错,建局失败)').toBe(0)
  const filled = page.waitForRequest(r => r.method() === 'POST' && r.url().includes('/templates/stoneford-elena/plots'))
  await page.locator('[data-tf2$=":words"]').fill('雾中, 新名字')
  await page.locator('[data-tf2$=":words"]').press('Tab')
  const trs = (await filled).postDataJSON().data.triggers
  const tr: any = Object.values(trs).find((v: any) => v.then?.[0]?.ending === 'E11' && v.if?.some((c: any) => Array.isArray(c.text) && c.text.includes('雾中')))
  expect(tr, '填完词才写进 plot.json').toBeTruthy()
  expect(tr.if.find((c: any) => c.text).text).toEqual(['雾中', '新名字'])
  expect(tr.if.find((c: any) => c.var === 'P10.stage')['>=']).toBe(1)
  await expect(page.locator('.elabel', { hasText: '雾中' })).toHaveCount(1, { timeout: 15_000 })
})

test('地图建路 / 删路:「+ 路」点起点再点终点 → 写回 · 点路删掉', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=duo]').click()
  await expect(page.locator('.mnode', { hasText: '码头' })).toHaveCount(1, { timeout: 60_000 })
  await page.locator('[data-mv=graph]').click()
  const lines = page.locator('.mpw line.hitln')
  // 这一层原来有几条路:读地图数据,不数画面上的线(数线会碰上重画)
  const before = await page.evaluate(() => (window as any).MAPW.edit.levels[(window as any).MAPM.level].edges.length)
  await expect(lines).toHaveCount(before, { timeout: 15_000 })
  await page.locator('[data-mlink]').click()
  await page.locator('.mnode', { hasText: '码头' }).locator('.lb').click()
  await expect(page.locator('[data-mlink]')).toContainText('码头')
  const add = page.waitForRequest(r => r.method() === 'POST' && r.url().includes('/edit-local/map/edge'))
  await page.locator('.mnode', { hasText: '河灯旅店' }).locator('.lb').click()
  expect((await add).postDataJSON()).toMatchObject({ level: 'T001', a: 'T001/dock', b: 'T001/inn' })
  await expect(lines).toHaveCount(before + 1, { timeout: 20_000 })
  await expect(page.locator('.mpside')).toContainText('码头 ↔ 河灯旅店')
  const del = page.waitForRequest(r => r.method() === 'POST' && r.url().includes('/edit-local/map/edge'))
  await page.locator('[data-mroaddel]').click()
  expect((await del).postDataJSON()).toMatchObject({ remove: true })
  await expect(lines).toHaveCount(before, { timeout: 20_000 })
})


test('游玩层 · 灰橡宅:身上的状态(中毒 · 剩几次结算)· 结局卡(CG · 真相 · 拿到的东西)', async ({ page }) => {
  test.setTimeout(150_000)
  await page.route(/\/api\/v1\/play\/engine\/entities\?cls=status/, r => r.fulfill({ json: { cls: 'status', entities: [{ id: 'ST001', name: '中毒', props: { turns: 3, rule: '每次结算 hp -1' } }] } }))
  await page.route(/\/api\/v1\/play\/engine\/settlement$/, r => r.fulfill({ json: { exit: { kind: 'ending', id: 'E01', turn: 5 }, cg_unlocked: ['E01'], epilogue: '墙后的人',
    truth_reveal: { text: '宅主人凿开地窖西墙,看见了不该看见的东西,把自己砌进了墙后。' }, deaths: [], rewards: { player: { ending_cg: ['E01'], clue_codex: ['烧了一半的日记'] } } } }))
  await page.goto('/local?tpl=pct-house')
  await ready(page)
  await page.locator('.nav [data-go=test]').click()
  await expect(page.locator('.mk-right .cond', { hasText: '中毒' })).toContainText('剩 3 次结算', { timeout: 60_000 })
  const card = page.locator('#mfeed .ending-card')
  await expect(card).toHaveClass(/\btrue\b/, { timeout: 30_000 })
  await expect(card.locator('h2')).toHaveText('墙后的人')
  await expect(card).toContainText('把自己砌进了墙后')
  await expect(card).toContainText('结局 CG · 1')
  // 模板里真实的结局图载出来了(不是占位 / 坏图):宽度不写死 —— 10-16 换过一版素材(8d930f1c,1920 → 1536)
  await expect.poll(() => card.locator('img.ecg').evaluate(i => (i as HTMLImageElement).naturalWidth), { timeout: 15_000 }).toBeGreaterThan(1000)
  if (SHOTS) { await card.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${SHOTS}/play-ending.png` }) }
})

test('拍怎么显示由引擎给(玩法包的 ui.beats):开源界面单凭 beat-kinds + chunk.beat 就能画出两拍', async ({ page }) => {
  // 中性的假声明 —— 不是我们任何一个包的真文案;界面不认识这两种拍,全靠引擎给的数据
  const SPEC = { start: 'talk', kinds: {
    talk: { label: '说话拍', tone: 'plan', live: '主持 · 说话拍', you: '试探', placeholder: '先说说看', chips: ['@主持'] },
    land: { label: '落账拍', tone: 'res', live: '落账拍', narr: '落账拍', divider_from: { talk: '说完 → 落账' } },
  } }
  await page.route(/\/api\/v1\/play\/engine\/beat-kinds/, r => r.fulfill({ json: SPEC }))
  let release: () => void = () => {}
  const gate = new Promise<void>(r => { release = r })
  let streams = 0
  await page.route(EVENTS, async r => {
    if (streams++) return r.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body: ': keepalive\n\n' })
    await gate
    const ev = (o: unknown) => `data: ${JSON.stringify(o)}\n\n`
    r.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body:
      ev({ kind: 'chunk', beat: 'talk', text: '门房说:先登记名字。' }) +
      ev({ kind: 'chunk', beat: 'land', text: '你推开门,雾气涌进来。' }) })
  })
  await page.route(/\/cmd$/, () => new Promise(() => {}))
  await page.goto('/local?tpl=stoneford-elena')
  await ready(page)
  await page.locator('.nav [data-go=test]').click()
  await expect(page.locator('#min')).toHaveAttribute('placeholder', '先说说看', { timeout: 15_000 })
  await expect(page.locator('.sugg')).toContainText('@主持')
  await page.locator('#min').fill('我推门进去')
  await page.locator('#msend').click()
  release()
  await expect(page.locator('#mfeed .bt.res.live')).toContainText('你推开门', { timeout: 15_000 })
  await expect(page.locator('#mfeed .bt.res.live .who')).toContainText('落账拍')
  await expect(page.locator('#mfeed .bt.host.plan.live')).toContainText('先登记名字')
  await expect(page.locator('#mfeed .bt.host.plan.live .who')).toContainText('主持 · 说话拍')
  await expect(page.locator('#mfeed .beatdiv').last()).toContainText('说完 → 落账')
})
