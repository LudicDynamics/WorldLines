// 世界编排台止损(10-17 审计 P0):顶栏选世界 → 读那个模板的图;引擎不读的字段画成灰的只读;改过的边真写回(守卫 → when,
// return 不丢);侧栏对话测试标「演示」、不冒充引擎回复;石津镇的交互节点不再报「跑不了」。截图进 WL_SOUL_SHOTS。
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_SOUL_BASE || 'http://127.0.0.1:8796'
const SHOTS = process.env.WL_SOUL_SHOTS || ''
const PRIVATE = !!process.env.WL_SOUL_PRIVATE
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())

async function boot(page: Page) {
  await page.goto(`${BASE}/`)
  await expect(page.locator('#ctx .chip').first()).not.toHaveText(/连接引擎|正在开一局/, { timeout: 90_000 })
  const err = await page.locator('#ctx [data-err]').getAttribute('data-err').catch(() => null)
  expect(err, '本地界面开机失败的原因').toBeNull()
  await expect(page.locator('#ctx')).toContainText('真引擎')
}
// 已知问题的诊断(S1):对话中途被清空时 orch.js 记一笔,这里打出来(不判失败)
test.afterEach(async ({ page }) => {
  const drops = await page.evaluate(() => (window as any).ORCHLINT && (window as any).ORCHLINT.chatDrops).catch(() => null)
  if (drops && drops.length) console.log('ORCHDBG chatDrops', JSON.stringify(drops))
})
async function openOrch(page: Page, tpl: string) {
  await boot(page)
  await page.locator('.nav [data-go=orch]').click()
  await expect(page.locator('#wlWorld')).toBeVisible()
  await page.locator('#wlWorld').selectOption(tpl)
  await expect(page.locator('#gsel')).toHaveValue(`tpl:${tpl}`, { timeout: 60_000 })
  await expect(page.locator('#board .nd').first()).toBeVisible()
}
const linted = (page: Page, key: string) => page.waitForFunction(k => !!(window as any).ORCHLINT.sig[k], key, { timeout: 30_000 })

test('顶栏选世界 → 编排台换成那个模板的图;石津镇交互节点不报跑不了', async ({ page }) => {
  await openOrch(page, 'stoneford-town')
  await expect(page.locator('#wlWorld')).toHaveValue('stoneford-town')
  if (PRIVATE) {
    await expect(page.locator('#board [data-n="interaction.talk"]')).toBeVisible()
    await linted(page, 'tpl:stoneford-town')
    expect(await page.evaluate(() => (window as any).ORCHLINT.lint['tpl:stoneford-town'])).toEqual([])
    await expect(page.locator('#board .orchlint')).toHaveCount(0)
  }
  await shot(page, 'orch-01-world-picked')
  await page.locator('#wlWorld').selectOption('stoneford-elena')
  await expect(page.locator('#gsel')).toHaveValue('tpl:stoneford-elena', { timeout: 60_000 })
  await expect(page.locator('#board [data-n="interaction.talk"]')).toHaveCount(0)
  await page.locator('#gsel').selectOption('tpl:wuwu')   // 反过来:编排图下拉换了,顶栏跟着换
  await expect(page.locator('#wlWorld')).toHaveValue('wuwu')
})

test('引擎不读的字段是灰的只读;侧栏对话测试跑真引擎(假模型),带着没写回的草稿', async ({ page }) => {
  await openOrch(page, 'stoneford-elena')
  await page.locator('#board .nd[data-n=resolve]').click()
  await page.locator('.crumb [data-layer=node]').click()
  await expect(page.locator('#board h2')).toContainText('resolve')
  // 步骤 = 引擎的步骤目录(S1):真实顺序、谁来跑、可换的实现;设置带现在的值和出处
  await expect(page.locator('#board .lane [data-step=s1_plan]')).toBeVisible({ timeout: 60_000 })
  await expect(page.locator('#board .lane [data-step]')).toHaveCount(18)
  await expect(page.locator('#board .lane')).not.toHaveClass(/unread/)
  await expect(page.locator('#board .lane [data-step=s2_souls]')).toContainText('soul_turn')
  await expect(page.locator('#board [data-stepparams]')).toContainText('default_variant')
  await expect(page.locator('#board [data-stepparams]')).toContainText('玩法包')
  await expect(page.locator('#board .unread-tag').first()).toBeVisible()
  await expect(page.locator('#drop')).toHaveClass(/unread/)
  const knobs = page.locator('#board .well dl.kv input')
  for (let i = 0; i < await knobs.count(); i++) await expect(knobs.nth(i)).toBeDisabled()
  await expect(page.locator('#board .orchstate [data-ostate]').first()).toBeEnabled()   // 出状态是引擎真读的参数:照样能改
  await shot(page, 'orch-02-node-readonly')
  await page.locator('.crumb [data-layer=tools]').click()
  await expect(page.locator('#ntAdd')).toHaveCount(0)
  await expect(page.locator('#board table.t')).toContainText('引擎尚未读取')
  // 侧栏对话测试 = 真引擎(graph-test 子进程 · 假模型):商量 → 「定」推进到清算;不出私有层的桩回复
  await page.locator('.crumb [data-layer=graph]').click()
  await expect(page.locator('#s-orch .side .side-h')).toContainText('会花额度')   // 默认真模型(④),标明花额度
  await page.locator('[data-omodel=stub]').click()
  await expect(page.locator('#s-orch .side .side-h')).toContainText('不花额度')
  await page.locator('#oin').fill('我去杂货铺买药')
  await page.locator('#osend').click()
  await expect(page.locator('#ochat .m.sys').last()).toContainText('planning', { timeout: 120_000 })
  await page.locator('#oin').fill('定')
  await page.locator('#osend').click()
  await expect(page.locator('#ochat .m.sys').last()).toContainText('推进:player', { timeout: 120_000 })
  await expect(page.locator('#ochat .m.sys').last()).toContainText('resolve')
  await expect(page.locator('#ochat')).toContainText('graph-test')
  await expect(page.locator('#ochat')).not.toContainText('d20=15')
  expect(await page.evaluate(() => { const p = (window as any).PRIVATE_UI; return !!(p && (p.stubs || p.graphs)) }), '私有层演示数据只在 ?demo=1').toBe(false)
  await expect(page.locator('#board .nd.cur[data-n=resolve]')).toHaveCount(1)   // 画布上标出停在哪
  // 没写回的草稿也算数:删掉商量拍 → 第一句就进清算
  await page.locator('#board .nd[data-n=plan]').click()
  await page.locator('[data-onodedel=plan]').click()
  await page.locator('#oin').fill('我四处看看')
  await page.locator('#osend').click()
  await expect(page.locator('#ochat .m.sys').last()).toContainText('resolve', { timeout: 120_000 })
  await expect(page.locator('#ochat .m.sys').last()).not.toContainText('planning')
  await shot(page, 'orch-03-real-chat')
})

test('改过的边真写回:守卫 → when,进层的 return 不丢', async ({ page }) => {
  await openOrch(page, 'stoneford-elena')
  const eid = 'resolve>combat:op'
  await page.locator(`#board .elabel[data-e="${eid}"]`).click({ force: true })
  await page.locator('#pgd').fill('turn >= 0')
  await expect(page.locator('#pgdw')).toHaveText('')
  await page.locator('[data-pclose]').first().click()
  await expect(page.locator('[data-orchsave]')).toBeEnabled()
  // 引擎忙的时候草稿 lint 回来会重画存盘条,点击可能落在旧按钮上:没开始写回就再点一次
  await expect(async () => {
    if (!/写回中|写回模板 stoneford-elena:/.test((await page.locator('.orchsave').textContent()) || '')) await page.locator('[data-orchsave]').click()
    await expect(page.locator('.orchsave')).toContainText('下一局开始按这张图走', { timeout: 10_000 })
  }).toPass({ timeout: 60_000 })
  const r = await page.request.get(`${BASE}/api/v1/play/engine/graph?template=stoneford-elena`)
  const e = ((await r.json()).graph.edges as any[]).find(x => x.id === eid)
  expect(e.when).toEqual([{ var: 'turn', '>=': 0 }])
  expect(e.return).toBe(true)
  expect(e.on).toEqual({ op: 'combat' })
  expect(await page.locator('.orchsave').textContent()).not.toMatch(/edges \+\d+ -[1-9]/)   // 没删掉别的边
  const ids = ((await r.json()).graph.edges as any[]).map(x => x.id)
  for (const k of ['*>combat:gate', '*>dungeon:here', 'combat>@return:end_combat', 'plan>resolve:words']) expect(ids, k).toContain(k)   // 图上画不出来的「从任何节点」边也还在
  await shot(page, 'orch-04-edge-saved')
  // 看不懂的守卫不写回
  await page.locator(`#board .elabel[data-e="${eid}"]`).click({ force: true })
  await page.locator('#pgd').fill('就是想打')
  await expect(page.locator('#pgdw')).toContainText('看不懂')
  await page.locator('[data-pclose]').first().click()
  await page.locator('[data-orchsave]').click()
  await expect(page.locator('.orchsave')).toContainText('守卫看不懂')
})

test('测试台顶上选世界 → 问一声 → 开那个模板的一局', async ({ page }) => {
  await boot(page)
  await page.locator('.nav [data-go=test]').click()
  await expect(page.locator('#wlWorld')).toBeVisible()
  page.once('dialog', d => d.accept())
  await page.locator('#wlWorld').selectOption('wuwu')
  await expect(page.locator('#wlWorld')).toHaveValue('wuwu', { timeout: 150_000 })
  await shot(page, 'orch-05-test-world')
})

test('侧栏对话测试 · 真模型(④):用设置里的模型在临时局里一句一回合;回复显示出来;接着说只跑新的一句', async ({ page }) => {
  await openOrch(page, 'stoneford-elena')
  await expect(page.locator('#s-orch .side .side-h')).toContainText('会花额度')
  const sent: any[] = []
  page.on('request', r => { if (r.url().includes('/graph-test')) sent.push(r.postDataJSON()) })
  await page.locator('#oin').fill('我去杂货铺买药')
  await page.locator('#osend').click()
  await expect(page.locator('#ochat .m.sys').last()).toContainText('graph-test · 真模型', { timeout: 240_000 })
  await expect(page.locator('#ochat .m.sys').last()).not.toContainText('没跑成')
  await expect(page.locator('#ochat .m.human').last()).not.toBeEmpty()   // 模型写的这一回合
  await page.locator('#oin').fill('定')
  await page.locator('#osend').click()
  await expect(page.locator('#ochat .m.sys').last()).toContainText('graph-test · 真模型', { timeout: 240_000 })
  expect(sent.map(b => b.model)).toEqual(['real', 'real'])
  expect(sent[1].session).toBe(sent[0].session)   // 同一段对话:引擎接着上一句的局跑
  await expect(page.locator('#ochat .m.sys').last()).not.toContainText('重放了')
  await shot(page, 'orch-06-real-model-chat')
})

test('这一拍的设置在图上改(S2):改角色出手方式 → 写回 → 引擎读到的值来自「编排图」,侧栏草稿马上按它跑', async ({ page }) => {
  await openOrch(page, 'stoneford-elena')
  await page.locator('#board .nd[data-n=resolve]').click()
  await page.locator('.crumb [data-layer=node]').click()
  const sel = page.locator('[data-sp="resolve|s2_souls|default_variant"]')
  await expect(sel).toBeVisible({ timeout: 60_000 })
  await expect(sel).toHaveValue('S-judge')                        // 玩法包定的
  await sel.selectOption('S-direct')
  await expect(page.locator('[data-orchsave]')).toBeEnabled()
  const bad = page.locator('[data-sp="resolve|verify|max_loops"]')
  await bad.fill('9'); await bad.press('Tab')                    // 超出范围:标红,不进草稿
  await expect(bad).toHaveAttribute('title', /整数/)
  await expect(async () => {
    if (!/写回中|写回模板 stoneford-elena:/.test((await page.locator('.orchsave').textContent()) || '')) await page.locator('[data-orchsave]').click()
    await expect(page.locator('.orchsave')).toContainText('下一局开始按这张图走', { timeout: 10_000 })
  }).toPass({ timeout: 60_000 })
  const h = await (await page.request.get(`${BASE}/api/v1/play/engine/hooks?template=stoneford-elena`)).json()
  const p = h.steps.nodes.resolve.find((x: any) => x.id === 's2_souls').params.find((x: any) => x.name === 'default_variant')
  expect([p.value, p.source]).toEqual(['S-direct', 'graph'])
  const v = h.steps.nodes.resolve.find((x: any) => x.id === 'verify').params.find((x: any) => x.name === 'max_loops')
  expect(v.source).not.toBe('graph')
  await page.locator('.crumb [data-layer=node]').click()
  await expect(page.locator('#board [data-stepparams]')).toContainText('编排图', { timeout: 30_000 })
  await shot(page, 'orch-08-step-params')
})

