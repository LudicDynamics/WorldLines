// 浏览器版结局分享回放(replay 代理 10-18):浏览器里的引擎打一回合 → POST /api/v1/local/replay/share(引擎同一个接口,
// 内部 replay_export.pack_replay → replay_share.share_files)→ 平台六步全部拦在本机(auth / storage / sns 都是假的,不发真平台),
// 看上传的文件里有图、而且是原样的字节(wlweb._body 把图转 base64 过桥,worker.js 解回 Uint8Array)。
//   WL_PLAY_PORT=8908 WL_PLAY_AI_PORT=8909 · 构建时 --ai / --auth / --billing 指到 http://127.0.0.1:8909
import { test, expect, type Route } from '@playwright/test'

const AI = `http://127.0.0.1:${process.env.WL_PLAY_AI_PORT || '8611'}`
const mock = (mode: string, reset = false) => fetch(`${AI}/_mock/mode`, { method: 'POST', body: JSON.stringify({ mode, reset }) })

test('浏览器版:分享回放带图(封面 / 立绘 / 结局插画按原字节上传)', async ({ page, context, browserName }) => {
  // Playwright 的 WebKit 拦不到 Web Worker 里的同步 XHR(context.route 只拦页面的),平台六步会真的发出去(被真平台的 CORS 挡在登记那一步):只在 Chromium 跑
  test.skip(browserName === 'webkit', 'WebKit: worker sync XHR is not routable in Playwright')
  await context.addInitScript(() => {
    try {
      localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok-e2e', exp: Date.now() + 3600e3, refresh: 'r-e2e', user: { id: 'u-e2e' } }))
      localStorage.setItem('wl.play.ackCharge', '1')
    } catch { /* blocked */ }
  })
  await mock('ok', true)
  // 平台:全部拦下(浏览器里引擎的同步 XHR 从 worker 发出,也走 context.route)
  const steps: string[] = [], puts: Record<string, Buffer> = {}
  let declared: { path: string; size: number }[] = []
  const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'authorization, content-type, idempotency-key, x-worldlines-product, x-amz-checksum-sha256',
    'access-control-allow-methods': 'GET, POST, PUT, DELETE, OPTIONS' }
  const json = (r: Route, body: unknown, status = 200) => r.fulfill({ status, headers: { ...cors, 'content-type': 'application/json' }, body: JSON.stringify(body) })
  await context.route(/^https:\/\/(auth|storage|sns)\.worldlines\.gg\//, async (r) => {
    const req = r.request(), u = new URL(req.url())
    if (req.method() === 'OPTIONS') return r.fulfill({ status: 204, headers: cors })
    steps.push(`${req.method()} ${u.host.split('.')[0]}${u.pathname}`)
    if (u.pathname.startsWith('/_put/')) { puts[decodeURIComponent(u.pathname.slice(6))] = req.postDataBuffer() || Buffer.alloc(0); return r.fulfill({ status: 200, headers: cors, body: '' }) }
    if (u.pathname.endsWith('/lease')) return json(r, { lease_id: 'L1' })
    if (u.pathname.endsWith('/upload-url')) {
      declared = (req.postDataJSON() || {}).files || []
      return json(r, { uploads: declared.map(f => ({ path: f.path, method: 'PUT', url: `https://storage.worldlines.gg/_put/${encodeURIComponent(f.path)}`, headers: {} })) })
    }
    if (u.pathname.endsWith('/publish')) return json(r, { resource: { status: 'published' } })
    if (u.pathname.endsWith('/v1/moments')) return json(r, { id: 'm1', url: 'https://sns.example/m/m1', zone: 'open' }, 201)
    return json(r, {}, 201)
  })
  await page.goto('/play/bench.html?tpl=pct-house&lang=zh&new=1')
  await page.waitForFunction(() => (window as any).WLPLAY && (window as any).WLPLAY.ready, null, { timeout: 300_000 })
  // 开场那一拍(新开一局时引擎自己跑的)落定以后再说话(和 play.spec 的 ready() 同一个条件)
  await page.waitForSelector('#min', { timeout: 120_000 })
  await page.waitForFunction(() => { try { const E = (0, eval)('E'); return !E.busy && E.s && E.s.feed.length > 0 } catch { return false } }, null, { timeout: 120_000 })
  await page.waitForTimeout(500)
  const out = await page.evaluate(async () => {
    const e = (window as any).WLPLAY.engine
    await e.ready
    const done = await e.sayAndWait('我四处看看')
    const r = await fetch('/api/v1/local/replay/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lang: 'zh', text: 'e2e' }) })
    return { done: done && done.success, status: r.status, body: await r.json() }
  })
  expect(out.done).toBe(true)
  expect(out.status, JSON.stringify(out.body)).toBe(200)
  expect(out.body.ref).toMatch(/^hub\/replay\//)
  const names = Object.keys(puts).sort()
  expect(names).toContain('timeline.json')
  const pics = names.filter(n => n === 'cover.png' || n.startsWith('assets/'))
  expect(pics.length, names.join(', ')).toBeGreaterThan(0)
  expect(names.some(n => n.startsWith('assets/place.scene/')), names.join(', ')).toBe(true)   // 场景图(浏览器版的局里没有,取模板的)
  const magic = (b: Buffer) => b.subarray(0, 4).toString('hex')
  console.log('uploaded:', names.map(n => `${n} ${puts[n].length}B`).join(' · '))
  for (const n of pics) {
    const b = puts[n], d = declared.find(f => f.path === n)
    expect(b.length, n).toBe(d ? d.size : -1)   // 原样的字节:大小和登记的一样(不是 base64 文字)
    expect(['89504e47', 'ffd8ffe0', 'ffd8ffe1', 'ffd8ffdb', 'ffd8ffee', '52494646'], `${n} ${magic(b)}`).toContain(magic(b))   // PNG / JPEG / RIFF(webp)
  }
  const tl = JSON.parse(puts['timeline.json'].toString('utf-8'))
  expect(tl.format).toBe('worldlines.replay/1')
  expect(JSON.stringify(tl)).not.toContain('"board"')
  expect(steps.filter(s => s.startsWith('POST')).map(s => s.replace(/hub\/replay\/[^/]+/, 'R'))).toEqual([
    'POST auth/v1/resources', 'POST auth/v1/resources/R/lease', 'POST storage/v1/objects/R/upload-url',
    'POST storage/v1/objects/R/complete', 'POST auth/v1/resources/R/publish', 'POST sns/api/v1/moments'])
})
