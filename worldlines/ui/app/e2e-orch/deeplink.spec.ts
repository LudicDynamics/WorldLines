// 创作台「到编排台编辑」(orch-preview 10-19):本地 Hub 创作台 → 点按钮 → /local?screen=orch&edit=<模板> → 编排台打开的是这个模板,
// 正在玩的那一局不换、也不新开一局(页面没有 POST /api/v1/play/session,引擎绑着的还是原来那个模板)。
import { test, expect } from '@playwright/test'
import { mkdirSync } from 'fs'
import { join } from 'path'

const BASE = process.env.WL_OD_BASE || 'http://127.0.0.1:8805'
const SHOTS = process.env.WL_OD_SHOTS || 'shots'
const TID = 'stoneford-town', PLAYING = 'pct-house'

test('到编排台编辑:落到这个模板的编排台,不开局', async ({ page, request }) => {
  mkdirSync(SHOTS, { recursive: true })
  // 先有一局在玩(niko 手上的那一局):绑灰橡宅
  const bound = await request.post(`${BASE}/api/v1/play/session`, { data: { slug: `tpl--${PLAYING}`, output_lang: 'zh' }, timeout: 600_000 })
  expect(bound.ok()).toBeTruthy()
  const before = await (await request.get(`${BASE}/api/v1/play/engine/template`)).json()
  const errs: string[] = [], posts: string[] = []
  page.on('pageerror', e => errs.push(e.message))
  page.on('request', r => { if (r.method() === 'POST') posts.push(new URL(r.url()).pathname) })
  await page.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh') } catch { /* no storage */ } })

  await page.goto(`${BASE}/hub.html#/t/${TID}/create`)
  const edit = page.locator('#cf-orch [data-orch-edit]')
  await expect(edit).toBeVisible({ timeout: 300_000 })
  await expect(edit).toHaveAttribute('href', `/local?screen=orch&edit=${TID}`)
  await page.locator('#cf-orch').screenshot({ path: join(SHOTS, '01-desk-edit-button.png') })

  await edit.click()
  await page.waitForURL(u => u.pathname === '/local' && u.searchParams.get('screen') === 'orch' && u.searchParams.get('edit') === TID, { timeout: 60_000 })
  // 编排台:选中的图是这个模板的(G().tpl);读完图再看
  // G 是 app.js 顶层的 const(不在 window 上),按名字取
  await page.waitForFunction(`(() => { try { const g = G(); return !!g && !g.pending && g.tpl === ${JSON.stringify(TID)} } catch { return false } })()`, null, { timeout: 300_000 })
  await expect(page.locator('#gsel')).toBeVisible()
  const graphTpl = await page.evaluate('G().tpl')
  await page.screenshot({ path: join(SHOTS, '02-bench-this-template.png') })

  const after = await (await request.get(`${BASE}/api/v1/play/engine/template`)).json()
  expect(graphTpl).toBe(TID)
  expect(posts.filter(p => p === '/api/v1/play/session')).toEqual([])
  expect(JSON.stringify(after)).toBe(JSON.stringify(before))
  expect(JSON.stringify(after)).toContain(PLAYING)
  expect(errs).toEqual([])
})
