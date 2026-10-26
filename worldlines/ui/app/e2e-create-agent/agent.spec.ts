// 工作台「创作后端」(10-26 · C2):世界·角色 → 创作 agent → 选「本机 Claude Code」→ 说一句 → 假 CLI 经 neonrp-create MCP 改文件 →
// 页面上有流式文字、每次工具调用(✓ / ✗:读 .neonrp 被拒)、改了的文件、lint;换「本机 Codex」→ 慢的一句 → 中止;
// 没装 CLI 时选项灰掉 + 说明(拦 GET create-agents 模拟);日文界面;创作台(hub)模型下拉 = 本机配好 key 的 provider。截图进 WL_AG_SHOTS。
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, readFileSync, existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.WL_AG_BASE || 'http://127.0.0.1:8875'
const HOME = process.env.WL_AG_HOME || ''
const LOG = process.env.WL_AG_LOG || ''
const SHOTS = process.env.WL_AG_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
// 世界·角色这页会自己重画(地图任务、角色卡回来):截到一半元素被换掉就再截一次
async function shot(page: Page, name: string) {
  if (!SHOTS) return
  for (let i = 0; ; i++) {
    try { await page.locator('.rside').screenshot({ path: join(SHOTS, `${name}.png`), timeout: 5_000 }); return } catch (e) { if (i >= 5) throw e; await page.waitForTimeout(300) }
  }
}
const full = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())

async function openDuo(page: Page, path = '/') {
  await page.goto(`${BASE}${path}`)
  await expect(page.locator('#ctx .chip').first()).not.toHaveText(/连接引擎|正在开一局|接続|connect/i, { timeout: 120_000 })
  await page.locator('.nav [data-go=duo]').click()
  await expect.poll(() => page.evaluate(() => !!((window as any).MAPHOOK && (window as any).MAPHOOK.edit)), { timeout: 150_000 }).toBe(true)
  await expect(page.locator('#agSel')).toBeVisible({ timeout: 30_000 })
}
// 这页会自己重画(地图任务、角色卡回来),打字和点发送之间输入框可能被换掉:没发出去就再发一次(发出去 = 对话里多了一条「我」)
async function say(page: Page, text: string) {
  const mine = page.locator('#achat .m.me'), n = await mine.count()
  await expect(async () => {
    if (await mine.count() > n) return
    await page.locator('#ain').fill(text)
    await page.locator('#asend').click()
    expect(await mine.count()).toBeGreaterThan(n)
  }).toPass({ timeout: 30_000 })
}

test('本机 Claude Code / Codex 当创作后端:进度 · 改了的文件 · lint · 中止', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(String(e.stack || e)))
  await openDuo(page)
  const sel = page.locator('#agSel')
  await expect(sel.locator('option[value="claude-code"]')).toContainText('9.9.9')
  await expect(sel.locator('option[value="codex"]')).toBeEnabled()
  await shot(page, '01-backend-picker')

  // ① Claude Code
  await sel.selectOption('claude-code')
  await expect(page.locator('.agnote')).toContainText('Claude Code')
  await say(page, '加一条笔记:雾港的灯塔夜里不亮')
  const last = page.locator('#achat .m.agent').last()
  await expect(last.locator('.agfin, .agl')).toHaveCount(1, { timeout: 120_000 })   // lint 行 = 这一轮结束
  await expect(last).toContainText('写好了 notes/agent-1.md')
  await expect(last.locator('.agc.ok')).not.toHaveCount(0)
  await expect(last.locator('.agc.bad')).toContainText('.neonrp/config.json')        // 读引擎内部被 MCP 拒
  await expect(last.locator('.agf')).toContainText('notes/agent-1.md')
  await expect(last.locator('.agl')).toContainText('lint')
  await expect(page.locator('[data-agstop]')).toHaveCount(0)
  await shot(page, '02-claude-code-progress')
  await full(page, '02b-workbench-full')

  // ② Codex + 中止
  await sel.selectOption('codex')
  await expect(page.locator('.agnote')).toContainText('Codex')   // 换完会重画:等它画完再打字,不然输入框被换掉
  await say(page, 'SLOW 慢慢来')
  await expect(page.locator('[data-agstop]')).toBeVisible()
  await expect(page.locator('#achat .m.agent').last().locator('.agc.ok')).toHaveCount(1, { timeout: 60_000 })   // list_files 回来了,正睡着
  await shot(page, '03-codex-running')
  await page.locator('[data-agstop]').click()
  await expect(page.locator('#achat .m.agent').last().locator('.agfin')).toContainText('已中止', { timeout: 30_000 })
  await expect(page.locator('[data-agstop]')).toHaveCount(0)
  await shot(page, '04-codex-stopped')

  // 起的是什么:在世界文件夹里、没有 key 的环境、收紧的参数
  const recs = readFileSync(LOG, 'utf-8').trim().split('\n').map(l => JSON.parse(l))
  const cc = recs.find(r => r.name === 'claude'), cx = recs.find(r => r.name === 'codex')
  expect(cc.argv).toEqual(expect.arrayContaining(['--strict-mcp-config', 'mcp__neonrp-create__*']))
  expect(cc.argv[cc.argv.indexOf('--tools') + 1]).toBe('')   // 没有任何内置工具
  expect(cc.argv).not.toContain('--bare')
  expect(cx.argv).toEqual(expect.arrayContaining(['--ignore-user-config', 'default_permissions="neonrp_create"']))
  expect(cx.argv).not.toContain('--sandbox')   // 内置 read-only 沙箱读全盘;用只读这个文件夹的权限档
  for (const r of recs) expect(r.env).not.toContain('ANTHROPIC_API_KEY')
  expect(existsSync(join(cc.cwd, 'notes', 'agent-1.md'))).toBe(true)
  expect(existsSync(join(cc.cwd, 'notes', 'agent-2.md'))).toBe(false)   // 中止的那一轮没写
  expect(errors).toEqual([])
  await sel.selectOption('engine')
})

test('没装 CLI:选项灰掉 + 说明;日文界面', async ({ page }) => {
  await page.route('**/api/v1/local/create-agents', r => r.fulfill({ json: { selected: 'engine', agents: [
    { id: 'engine', available: true },
    { id: 'claude-code', label: 'Claude Code', bin: 'claude', available: false, version: null, why: 'not_installed' },
    { id: 'codex', label: 'Codex', bin: 'codex', available: false, version: null, why: 'not_installed' }] } }))
  await openDuo(page)
  await expect(page.locator('#agSel option[value="claude-code"]')).toBeDisabled()
  await expect(page.locator('#agSel option[value="codex"]')).toContainText('没装')
  await expect(page.locator('.agnote')).toContainText('claude / codex')
  await shot(page, '05-no-cli')
  await page.evaluate(() => localStorage.setItem('wl-local-lang', 'ja'))
  await page.unroute('**/api/v1/local/create-agents')
  await openDuo(page)
  await expect(page.locator('#agSel option[value="claude-code"]')).toContainText('この端末の Claude Code')
  await page.locator('#agSel').selectOption('claude-code')
  await expect(page.locator('.agnote')).toContainText('neonrp-create')
  await shot(page, '06-ja')
  await page.locator('#agSel').selectOption('engine')
  await page.evaluate(() => localStorage.removeItem('wl-local-lang'))
})

test('创作台:模型下拉 = 本机配好 key 的 provider,改了写回创作用', async ({ page }) => {
  await page.goto(`${BASE}/hub.html#/t/stoneford-town/create`)
  const pick = page.locator('#cfModelSel')
  await expect(pick).toBeVisible({ timeout: 150_000 })
  await expect(pick.locator('option')).toContainText(['自动', 'mock', 'claude-test'])
  await page.locator('#cfmodel').scrollIntoViewIfNeeded()
  if (SHOTS) await page.locator('.cfaiall').screenshot({ path: join(SHOTS, '07-hub-model-pick.png') })
  // 创作台这页会整页重画(编排图、一句话面板回来):选的时候选择框刚好被换掉就再选一次
  const cfg = () => { try { return JSON.parse(readFileSync(join(HOME, '.neonrp', 'config.json'), 'utf-8')).create_provider ?? null } catch { return 'unreadable' } }
  await expect(async () => { await pick.selectOption('claude-test'); expect(cfg()).toBe('claude-test') }).toPass({ timeout: 30_000 })
  await expect(async () => { await pick.selectOption(''); expect(cfg()).toBe(null) }).toPass({ timeout: 30_000 })
  expect(readdirSync(HOME).length).toBeGreaterThan(0)
})
