// 网页 Hub 发现页的社区作品(web-create 10-18 · 平台 4cb013e):identity 公开列表(默认区 · 通过审核的那一版 · 不要 mature)
// → 官方世界和社区作品分两块,社区作品标作者;列表读不到官方世界照常;游客点进去只有封面 + 介绍 +「登录后在浏览器里玩」,
// 直接开浏览器版 = 先登录;登录后浏览器版带令牌拿默认区的包,装成这个作品,假模型打一回合。平台全部拦在本机。
//   WL_PLAY_PORT=8908 WL_PLAY_AI_PORT=8909 · 构建时 --ai / --auth / --billing 指到 http://127.0.0.1:8909 · WL_PLAY_SHOTS=<截图目录>
import { test, expect, type Page, type Route, type BrowserContext } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

const AI = `http://127.0.0.1:${process.env.WL_PLAY_AI_PORT || '8611'}`
const SHOTS = process.env.WL_PLAY_SHOTS || '../test-results/community-shots'
mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true })
const mock = (mode: string, reset = false) => fetch(`${AI}/_mock/mode`, { method: 'POST', body: JSON.stringify({ mode, reset }) })
const WID = 'stoneford-town-mine-c0ffee'
const FID = 'stoneford-town-mine-f4ee00'   // 自由区作品(同一份包,?ref= 不带 zone)
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64')

// 一份真的作品包:创作台存出来的作品(石津镇 + 一段 plots/mine)用引擎自己的打包(export_template + 内置世界)
function makePackage(): Buffer {
  const out = join(mkdtempSync(join(tmpdir(), 'wl-comm-')), 'package.zip')
  const py = `
import os, sys, tempfile
from pathlib import Path
d = Path(tempfile.mkdtemp()); os.environ["NEONRP_TEMPLATE_WRITE_DIR"] = str(d); os.environ["NEONRP_TEMPLATE_PATH"] = str(d)
from neonrp import template as TP
from neonrp.template import creation
from neonrp.template.package import export_template
from neonrp.core.template_publish import _with_builtin
t = TP.load(TP.discover()["stoneford-town"])
w = creation.save(t, {"soul": [{"name": "阿青", "persona": "沉默的猎人"}]}, work_id="stoneford-town-mine", card={"zh": {"title": "雾夜猎人", "pitch": "雾里有人在追脚印。"}})
Path(sys.argv[1]).write_bytes(_with_builtin(export_template(w, any_zone=True), w))
`
  execFileSync('uv', ['run', 'python', '-c', py, out], { cwd: resolve(HERE, '../../..'), stdio: ['ignore', 'ignore', 'inherit'], timeout: 600_000 })
  return readFileSync(out)
}

const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'authorization, content-type', 'access-control-allow-methods': 'GET, HEAD, OPTIONS' }
const row = (id: string, title: string, extra: Record<string, unknown> = {}) => ({ id, title, zone: 'curated', status: 'published', revision: 1, published_revision: 1, published_at: '2026-10-18T09:00:00Z', mature: false, official: false,
  meta: { title: { zh: title, en: `${title} EN` }, pitch: { zh: '雾里有人在追一串脚印。' }, lang: 'zh', langs: ['zh'], author: '阿青的作者', cover: 'cover.png', source: 'stoneford-town-mine', play_contract: 'open-adventure@1', ending: 'single', cast: ['阿青'] }, ...extra })

async function platform(ctx: BrowserContext, opts: { pkg?: Buffer, failList?: boolean }, seen: { list: string[], dl: string[] }) {
  const json = (r: Route, body: unknown, status = 200) => r.fulfill({ status, headers: { ...cors, 'content-type': 'application/json' }, body: JSON.stringify(body) })
  await ctx.route(new RegExp(`^${AI.replace(/[.]/g, '\\.')}/v1/public/resources`), r => {
    seen.list.push(r.request().url())
    if (opts.failList) return r.fulfill({ status: 500, headers: cors, body: 'down' })
    if (new URL(r.request().url()).searchParams.get('zones') !== 'curated') return json(r, { resources: [] })   // 自由区那一份(loadOpen)
    if (new URL(r.request().url()).searchParams.get('cursor') === 'p2') return json(r, { resources: [row('stoneford-town-mine-beef01', '第二页的作品')], next_cursor: null })   // 翻页
    return json(r, { resources: [row(WID, '雾夜猎人'), row('stoneford-town', '石津镇', { official: true }), row('night-x-aaaaaa', '夜里的事', { mature: true })], next_cursor: 'p2' })
  })
  await ctx.route(/^https:\/\/(auth|storage|sns)\.worldlines\.gg\//, r => {
    const req = r.request(), u = new URL(req.url())
    if (req.method() === 'OPTIONS') return r.fulfill({ status: 204, headers: cors })
    if (u.pathname === `/v1/public/objects/hub/template/${WID}/cover`) return r.fulfill({ status: 200, headers: { ...cors, 'content-type': 'image/png' }, body: PNG })
    if (u.pathname === `/v1/objects/hub/template/${WID}/download-url`) {
      const auth = req.headers()['authorization'] || ''
      seen.dl.push(`${u.search} ${auth ? 'auth' : 'anon'}`)
      if (!auth) return json(r, { limited: 'zone', files: [{ path: 'cover.png', url: 'https://storage.worldlines.gg/_cover' }] })
      return json(r, { revision: 1, published_revision: 1, files: [{ path: 'package.zip', url: 'https://storage.worldlines.gg/_pkg' }, { path: 'cover.png', url: 'https://storage.worldlines.gg/_cover' }] })
    }
    if (u.pathname === `/v1/public/objects/hub/template/${FID}/download-url`) {   // 自由区作品:公开下载地址,不要令牌
      seen.dl.push(`free ${req.headers()['authorization'] ? 'auth' : 'anon'}`)
      return json(r, { files: [{ path: 'package.zip', url: 'https://storage.worldlines.gg/_pkg' }, { path: 'cover.png', url: 'https://storage.worldlines.gg/_cover' }] })
    }
    if (u.pathname === '/_pkg' && opts.pkg) return r.fulfill({ status: 200, headers: { ...cors, 'content-type': 'application/zip' }, body: opts.pkg })
    return json(r, {}, 404)
  })
}

test('发现页的社区作品:分区 · 作者 · 列表挂了官方照常 · 游客先登录 · 登录后浏览器里玩', async ({ browser }) => {
  test.setTimeout(900_000)
  await mock('ok', true)
  const pkg = makePackage()

  // 1. 游客:官方世界和社区作品分两块;社区作品标作者;官方 / mature 的不进社区那块
  const seen = { list: [] as string[], dl: [] as string[] }
  const guest = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1360, height: 860 } })
  await platform(guest, { pkg }, seen)
  const g = await guest.newPage()
  await g.goto('/')
  const comm = g.locator('.sec.comm')
  await expect(comm).toContainText('社区作品', { timeout: 60_000 })
  await expect(comm.locator(`a[href$="#/t/${WID}"]`)).toContainText('阿青的作者')
  await expect(comm).not.toContainText('夜里的事')   // mature
  await expect(comm.locator('a[href$="#/t/stoneford-town"]')).toHaveCount(0)   // 官方的走 catalog,不在社区那块
  await expect(g.locator('.cards').first().locator('a[href$="#/t/stoneford-town"]')).toBeVisible()
  const q = new URL(seen.list.find(x => new URL(x).searchParams.get('zones') === 'curated') || '').searchParams
  expect([q.get('zones'), q.get('client'), q.get('kind'), q.get('mature')]).toEqual(['curated', 'web', 'template', null])
  await shot(g, '01-find-community')
  // 翻页:第一页带 next_cursor,滚到社区那块底下就取下一页(cursor=p2),取完「加载更多」消失
  await expect(comm).not.toContainText('第二页的作品')
  await g.locator('.commmore').scrollIntoViewIfNeeded()
  await expect(comm).toContainText('第二页的作品', { timeout: 30_000 })
  expect(seen.list.some(x => new URL(x).searchParams.get('cursor') === 'p2')).toBe(true)
  await expect(g.locator('.commmore')).toHaveCount(0)
  await g.evaluate(() => window.scrollTo(0, 0))

  // 2. 游客点进去:封面 + 介绍 + 作者,按钮是「登录后在浏览器里玩」;直接开浏览器版 = 先登录(包一个字节都没下)
  await comm.locator(`a[href$="#/t/${WID}"]`).click()
  await expect(g.locator('.hero h1')).toHaveText('雾夜猎人')
  await expect(g.locator('.hero')).toContainText('阿青的作者')
  await expect(g.locator(`[data-comm-login="${WID}"]`)).toBeVisible()
  await shot(g, '02-detail-guest')
  await g.goto(`/play/bench.html?${new URLSearchParams({ ref: `hub/template/${WID}`, zone: 'curated', lang: 'zh' })}`)
  await expect(g.getByText('登录后才能玩这个作品')).toBeVisible({ timeout: 120_000 })
  await shot(g, '03-play-guest-needs-login')
  expect(seen.dl).toEqual([])
  await guest.close()

  // 3. 列表读不到:官方世界照常,社区那块不出现
  const down = await browser.newContext({ locale: 'zh-CN' })
  await platform(down, { failList: true }, { list: [], dl: [] })
  const d = await down.newPage()
  await d.goto('/')
  await expect(d.locator('a[href$="#/t/stoneford-town"]').first()).toBeVisible({ timeout: 60_000 })
  await expect(d.locator('.sec.comm')).toHaveCount(0)
  await down.close()

  // 4. 登录后:详情页给「在浏览器里玩」→ 浏览器版带令牌拿默认区的包,装成这个作品,打一回合
  const user = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1360, height: 860 } })
  await user.addInitScript(() => {
    try {
      localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok-e2e', exp: Date.now() + 3600e3, refresh: 'r-e2e', user: { id: 'u-e2e' } }))
      localStorage.setItem('wl.play.ackCharge', '1')
    } catch { /* blocked */ }
  })
  const seen2 = { list: [] as string[], dl: [] as string[] }
  await platform(user, { pkg }, seen2)
  const u = await user.newPage()
  await u.goto(`/#/t/${WID}`)
  const play = u.locator('.ctas a.btn.p')
  await expect(play).toBeVisible({ timeout: 60_000 })
  const href = new URL(await play.getAttribute('href') || '', u.url())
  expect([href.searchParams.get('ref'), href.searchParams.get('zone')]).toEqual([`hub/template/${WID}`, 'curated'])
  await shot(u, '04-detail-signed-in')
  await u.goto(`${href.pathname.replace(/\/play\/$/, '/play/bench.html')}${href.search}`)
  await u.waitForFunction(() => (window as any).WLPLAY && (window as any).WLPLAY.ready, null, { timeout: 360_000 })
  expect(await u.evaluate(() => (window as any).WLPLAY.tpl)).toBe(WID)
  expect(seen2.dl).toEqual(['?revision=published auth'])
  await u.waitForSelector('#min', { timeout: 180_000 })
  await u.waitForFunction(() => { try { const E = (0, eval)('E'); return !E.busy && E.s && E.s.feed.length > 0 } catch { return false } }, null, { timeout: 240_000 })
  const said = await u.evaluate(async () => { const r = await (window as any).WLPLAY.engine.sayAndWait('我往雾里走'); return { ok: r && r.success, err: r && r.error } })
  expect(said.ok, String(said.err)).toBe(true)
  await shot(u, '05-play-community-work')
  await user.close()
})

// 自己的 key 只给自由区作品(niko 10-26):没登录、拿不到游客令牌 → 门上额度在前、自己的 key 在后(写明只发给填的地址);
// 填了 key → 包走公开下载地址(不带令牌),模型调用全带这把 key,不带 Worldlines 产品头;同一个浏览器回到默认区作品 = 还是额度、key 不删
test('自由区作品:额度默认,也能用自己的 key;默认区不用这把 key', async ({ browser }) => {
  test.setTimeout(900_000)
  await mock('ok', true)
  const pkg = makePackage()
  const seen = { list: [] as string[], dl: [] as string[] }
  const ctx = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1360, height: 860 } })
  await platform(ctx, { pkg }, seen)
  const p = await ctx.newPage()
  await p.goto(`/play/bench.html?${new URLSearchParams({ ref: `hub/template/${FID}`, lang: 'zh', title: '雾夜猎人' })}`)
  await expect(p.getByText('用什么模型来跑?')).toBeVisible({ timeout: 120_000 })
  await expect(p.getByText('只发给你填的地址')).toBeVisible()
  await shot(p, '06-free-gate')
  await p.fill('form[data-key] input[name=base]', `${AI}/v1`)
  await p.fill('form[data-key] input[name=key]', 'sk-own-e2e')
  await p.fill('form[data-key] input[name=model]', 'own-model')
  await p.locator('form[data-key] button[type=submit]').click()
  await p.waitForFunction(() => (window as any).WLPLAY && (window as any).WLPLAY.ready, null, { timeout: 360_000 })
  expect(await p.evaluate(() => [(window as any).WLPLAY.tpl, (window as any).WLPLAY.mode, !!(window as any).WLPLAY.engine.modelSheet])).toEqual([FID, 'key', true])
  expect(seen.dl).toEqual(['free anon'])
  await p.waitForSelector('#min', { timeout: 180_000 })
  await p.waitForFunction(() => { try { const E = (0, eval)('E'); return !E.busy && E.s && E.s.feed.length > 0 } catch { return false } }, null, { timeout: 240_000 })
  const said = await p.evaluate(async () => { const r = await (window as any).WLPLAY.engine.sayAndWait('我往雾里走'); return { ok: r && r.success, err: r && r.error } })
  expect(said.ok, String(said.err)).toBe(true)
  const calls = (await (await fetch(`${AI}/_mock/state`)).json()).calls.filter((c: any) => !c.jev)
  expect(calls.length).toBeGreaterThan(0)
  expect(calls.every((c: any) => c.auth === 'Bearer sk-own-e2e' && c.product === '' && c.model === 'own-model')).toBe(true)
  await shot(p, '07-free-own-key')
  // 同一个浏览器(存着 key 模式)打开官方世界:默认区只用额度,门上没有 key,存的 key 还在
  await p.goto('/play/bench.html?tpl=stoneford-town&lang=zh')
  await expect(p.getByText('登录后用 Worldlines 额度玩')).toBeVisible({ timeout: 120_000 })
  await expect(p.locator('form[data-key]')).toHaveCount(0)
  expect(await p.evaluate(() => [localStorage.getItem('wl.play.mode'), !!localStorage.getItem('wl.play.key')])).toEqual(['key', true])
  await shot(p, '08-default-after-key')
  await ctx.close()
})
