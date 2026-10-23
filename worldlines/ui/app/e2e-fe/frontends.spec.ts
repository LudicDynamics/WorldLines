// 前端台做实(10-17):三个重前端工作台都接真引擎(假模型)—— Godot(真文件树 · headless 冒烟真走一回合)· 小手机(iframe /chat.html 发一句有回)·
// 文件 / 契约 / 事件流是引擎读来的。截图进 WL_FE_SHOTS。
import { test, expect, type Page, type FrameLocator } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'

const BASE = process.env.WL_FE_BASE || 'http://127.0.0.1:8799'
const SHOTS = process.env.WL_FE_SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const shot = (page: Page, name: string) => (SHOTS ? page.screenshot({ path: join(SHOTS, `${name}.png`) }) : Promise.resolve())

async function boot(page: Page) {
  await page.goto(`${BASE}/`)
  await expect(page.locator('#ctx .chip').first()).not.toHaveText(/连接引擎|正在开一局/, { timeout: 90_000 })
  expect(await page.locator('#ctx [data-err]').getAttribute('data-err').catch(() => null), '本地界面开机失败的原因').toBeNull()
}
// 当前世界 = id,并且引擎上开着它的一局(前端预览 / 冒烟连的都是开着的那一局)
async function worldWithRun(page: Page, id: string) {
  await page.locator('.nav [data-go=fe]').click()
  await page.locator('#wlWorld').selectOption(id)
  if (await page.evaluate(() => (window as any).LIVE.bound) !== id) {
    await expect(page.locator('#s-fe .fxbar [data-wlopen]')).toBeVisible({ timeout: 30_000 })   // 不一样:明说 + 按钮,不自动开
    page.once('dialog', d => d.accept())
    await page.locator('#s-fe .fxbar [data-wlopen]').click()
    await expect.poll(() => page.evaluate(() => (window as any).LIVE.bound), { timeout: 150_000 }).toBe(id)
  }
}
const frame = (page: Page): FrameLocator => page.frameLocator('#fxframe')
// 10-19:每个台两种模式 —— 试玩(真预览)/ 编辑(文件 · 事件流 · 契约页签)
async function view(page: Page, v: string) {
  if (v === 'play') { await page.locator('[data-fxmode=play]').click(); return }
  if (!(await page.locator(`[data-fxv=${v}]`).count())) await page.locator('[data-fxmode=edit]').click()
  await page.locator(`[data-fxv=${v}]`).click()
}

test('Godot 工作台:真文件树 · 契约 · 本机 Godot · headless 冒烟在这一局真走一回合 · 事件流里看得到', async ({ page }) => {
  test.setTimeout(400_000)
  await boot(page)
  await worldWithRun(page, 'pct-house')
  await page.locator('[data-fxdesk="builtin.godot"]').click()
  await expect(page.locator('#s-fe .fxbar')).toHaveCount(0)
  // 文件:examples/clients/godot 的真文件(写死的 FE_FILES 里没有 tests/smoke.gd)
  await view(page, 'files')
  await expect(page.locator('#s-fe .tree')).toContainText('smoke.gd', { timeout: 30_000 })
  await expect(page.locator('#s-fe .tree')).toContainText('只读')
  await page.locator('#s-fe [data-fxf="addons/worldlines/client.gd"]').click()
  await expect(page.locator('#s-fe pre.code')).toContainText('class_name WorldLinesClient')
  await shot(page, 'fe-01-godot-files')
  // 契约:这个世界的 GDScript
  await view(page, 'contract')
  await page.locator('[data-fxcf=gd]').click()
  await expect(page.locator('#s-fe pre.code')).toContainText('pct-house', { timeout: 60_000 })
  // 试玩:本机 Godot + 冒烟
  await view(page, 'play')
  const godot = await page.request.get(`${BASE}/api/v1/local/frontends/_/godot`).then(r => r.json())
  if (!godot.bin) { await expect(page.locator('#s-fe')).toContainText('没找到 Godot'); test.skip(true, '本机没有 Godot'); return }
  await expect(page.locator('#s-fe')).toContainText(/Godot|4\.\d/)
  await expect(page.locator('[data-fxsmoke]')).toContainText('真回合')
  const before = await page.request.get(`${BASE}/api/v1/play/engine/beats`).then(r => r.json()).then(r => (r.events || []).length)
  await page.locator('#fxline').fill('看看四周')
  await page.locator('[data-fxsmoke]').click()
  const res = page.locator('#s-fe .fxres')
  await expect(res).toBeVisible({ timeout: 240_000 })
  await expect(res).toContainText('通过')
  await expect(res).toContainText(/turn [\d.]+ s · success true/)
  await expect(res).toContainText('beat events:')
  await shot(page, 'fe-02-godot-smoke')
  // 真回合:引擎这一局多了拍事件;事件流页里看得到
  await expect.poll(() => page.request.get(`${BASE}/api/v1/play/engine/beats`).then(r => r.json()).then(r => (r.events || []).length), { timeout: 30_000 }).toBeGreaterThan(before)
  await view(page, 'events')
  await expect(page.locator('#s-fe .fevr').first()).toBeVisible({ timeout: 30_000 })
  await page.locator('#s-fe .fevr').last().click()
  await expect(page.locator('#s-fe .fevd')).toContainText('Godot')
  await shot(page, 'fe-03-godot-events')
})

test('小手机工作台:当前世界能聊的角色 · iframe 就是 /chat.html · 发一句假模型回话 · 没角色的世界说清楚', async ({ page }) => {
  test.setTimeout(300_000)
  await boot(page)
  await page.locator('.nav [data-go=fe]').click()
  await page.locator('#wlWorld').selectOption('pct-house')
  await page.locator('[data-fxdesk="builtin.chat"]').click()
  await expect(page.locator('#s-fe')).toContainText('没有能单独聊的角色', { timeout: 30_000 })
  await page.locator('#s-fe [data-fxworld="stoneford-town"]').click()
  await expect(page.locator('#wlWorld')).toHaveValue('stoneford-town')
  await expect(page.locator('#s-fe [data-fxsoul=elena]')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('#fxframe')).toBeVisible()
  expect(await page.locator('#fxframe').getAttribute('src')).toMatch(/\/chat\.html\?tpl=stoneford-town&sid=elena/)
  const f = frame(page)
  const input = f.locator('.comp textarea')
  await expect(input).toBeVisible({ timeout: 30_000 })
  await page.waitForTimeout(1500)   // 已有的对话先载完
  const soulN = await f.locator('.m.soul:not(.typing)').count()
  await input.fill('你好,今天镇上热闹吗?')
  await input.press('Enter')
  await expect.poll(async () => (await f.locator('body').innerText()).includes('你好,今天镇上热闹吗'), { timeout: 30_000 }).toBe(true)
  await expect.poll(async () => f.locator('.m.soul:not(.typing)').count(), { timeout: 60_000 }).toBeGreaterThan(soulN)
  await shot(page, 'fe-04-chat')
  // 文件:ui/player/chat 的真文件
  await view(page, 'files')
  await expect(page.locator('#fxframe')).toBeHidden()
  await expect(page.locator('#s-fe .tree')).toContainText('api.js', { timeout: 30_000 })
})

const beats = (page: Page) => page.request.get(`${BASE}/api/v1/play/engine/beats`).then(r => r.json()).then(r => (r.events || []).length as number)
// 刚开的局:开场那一回合还在跑时引擎回 409(标准前端会一直显示「世界在动…」等它)—— 等拍事件数稳住再说话
async function settled(page: Page) {
  let last = -1, same = 0
  for (let i = 0; i < 80 && same < 3; i++) { const n = await beats(page); same = n > 0 && n === last ? same + 1 : 0; last = n; await page.waitForTimeout(1500) }
}

test('TS 重前端工作台:标准前端 iframe /player.html 说一句是真回合 · 协议示例构建 → dist 预览,令牌进去也能说一句', async ({ page }) => {
  test.setTimeout(500_000)
  await boot(page)
  await worldWithRun(page, 'pct-house')
  await page.locator('[data-fxdesk=ts]').click()
  await expect(page.locator('[data-fxsub=player]')).toHaveClass(/on/)
  // ① 标准前端
  await expect(page.locator('#fxframe')).toBeVisible({ timeout: 30_000 })
  expect(await page.locator('#fxframe').getAttribute('src')).toMatch(/\/player\.html$/)
  const pf = frame(page)
  await expect(pf.locator('.bar textarea')).toBeVisible({ timeout: 60_000 })
  await settled(page)
  let n = await beats(page)
  await pf.locator('.bar textarea').fill('我四处看看')
  await pf.locator('.bar textarea').press('Enter')
  await expect.poll(() => beats(page), { timeout: 120_000 }).toBeGreaterThan(n)
  const pframe = () => page.frames().find(x => x.url().includes('/player.html'))!
  await expect.poll(() => pframe().evaluate(() => (window as any).WLPLAYER.APP.busy), { timeout: 120_000 }).toBe(false)   // 这一回合在标准前端里演完
  await page.waitForTimeout(2000)
  await shot(page, 'fe-05-ts-player')
  await view(page, 'files')
  await expect(page.locator('#s-fe .tree')).toContainText('director.js', { timeout: 30_000 })
  // ② 协议示例:没构建就点「构建」(第一次 npm install,要网;构建过就是「重新构建」)
  await page.locator('[data-fxsub=ts]').click()
  await expect(page.locator('#s-fe .tree')).toContainText('client.ts', { timeout: 30_000 })
  await view(page, 'play')
  await page.locator('[data-fxbuild]').click()   // 构建 / 重新构建:npm install(第一次,要网)+ vite build --base ./ → dist/
  await expect(page.locator('#s-fe .fxres')).toContainText('构建好了', { timeout: 300_000 })
  await expect(page.locator('#s-fe .fxres')).toContainText('vite build')
  await expect(page.locator('#fxframe')).toBeVisible({ timeout: 30_000 })
  expect(await page.locator('#fxframe').getAttribute('src')).toMatch(/\/builtin\.ts\/site\/index\.html\?world=pct-house$/)
  const token = (await page.request.get(`${BASE}/api/v1/local/frontends/_/connect`).then(x => x.json())).token
  const tf = frame(page)
  await tf.locator('#token').fill(token)
  await tf.locator('#connect button').click()
  await expect(tf.locator('#say')).toBeVisible({ timeout: 30_000 })
  await settled(page)
  n = await beats(page)
  await tf.locator('#say').fill('看看四周')
  await tf.locator('#send').click()
  await expect.poll(() => beats(page), { timeout: 120_000 }).toBeGreaterThan(n)
  await expect.poll(async () => (await tf.locator('#log').innerText()).length, { timeout: 60_000 }).toBeGreaterThan(10)
  await shot(page, 'fe-06-ts-example')
})

test('新建前端工作台:这个世界自己的网页前端(frontends/my-web)· 预览连真引擎说一句 · 改文件 → lint 认它 · 前端 agent(假模型)写文件 · 从 Godot 派生再冒烟', async ({ page }) => {
  test.setTimeout(500_000)
  await boot(page)
  await worldWithRun(page, 'pct-house')
  // + 新建 → 网页
  await page.locator('[data-fxdesk=new]').click()
  await page.locator('[data-fxkind=web-ts]').click()
  await page.locator('#fxnname').fill('my-web')
  await page.locator('#fxntitle').fill('灰橡宅 · 竖屏版')
  await page.locator('[data-fxcreate]').click()
  await expect(page.locator('[data-fxdesk=my-web]')).toHaveClass(/on/, { timeout: 30_000 })
  await expect(page.locator('#s-fe .fxprobs')).toHaveCount(0)
  // 预览 = 引擎服务这个文件夹;页面自己拿令牌连 /rpc
  await expect(page.locator('#fxframe')).toBeVisible({ timeout: 30_000 })
  expect(await page.locator('#fxframe').getAttribute('src')).toMatch(/\/pct-house\/my-web\/site\/index\.html/)
  const wf = frame(page)
  await expect(wf.locator('#status')).toHaveText('已连上', { timeout: 30_000 })
  await settled(page)
  const n = await beats(page)
  await wf.locator('#line').fill('看看四周')
  await wf.locator('#line').press('Enter')
  await expect.poll(() => beats(page), { timeout: 120_000 }).toBeGreaterThan(n)
  await expect.poll(async () => (await wf.locator('#feed').innerText()).length, { timeout: 60_000 }).toBeGreaterThan(20)
  await shot(page, 'fe-07-own-web')
  // 前端 agent:只写这个文件夹
  await page.locator('[data-fxsay="加一个背包按钮"]').click()
  await expect(page.locator('#fxchat .m.agent').last()).toContainText('背包按钮', { timeout: 60_000 })
  await expect(page.locator('#fxchat .m.agent').last()).toContainText('write_file bag.js')
  await view(page, 'files')
  await expect(page.locator('#s-fe .tree')).toContainText('bag.js', { timeout: 30_000 })
  await page.locator('#s-fe [data-fxf="bag.js"]').click()
  await expect(page.locator('#fxedit')).toHaveValue(/假模型写的/)
  await shot(page, 'fe-08-agent')
  // 文件页能改:把 frontend.json 的 kind 改坏 → 台上出 lint,模板 lint 里也有(warn,不挡发布)
  await page.locator('#s-fe [data-fxf="frontend.json"]').click()
  const ed = page.locator('#fxedit')
  const good = await ed.inputValue()
  await ed.fill(good.replace('"web-ts"', '"unity"'))
  await page.locator('[data-fxsave]').click()
  await expect(page.locator('#s-fe .fxprobs')).toContainText('frontend.manifest', { timeout: 30_000 })
  const lint = await page.request.get(`${BASE}/api/v1/local/templates/pct-house/lint`).then(r => r.json())
  expect(lint.problems.filter((p: any) => p.code.startsWith('frontend.')).map((p: any) => [p.level, p.code, p.where])).toEqual([['warn', 'frontend.manifest', 'frontends/my-web']])
  await shot(page, 'fe-09-lint')
  await page.locator('#fxedit').fill(good)
  await page.locator('[data-fxsave]').click()
  await expect(page.locator('#s-fe .fxprobs')).toHaveCount(0, { timeout: 30_000 })
  // 契约写进这个前端
  await view(page, 'contract')
  await page.locator('[data-fxcf=ts]').click()
  await expect(page.locator('[data-fxcwrite]')).toBeVisible({ timeout: 60_000 })
  // 从内置 Godot 复制 → 这个世界自己的 Godot 前端,冒烟照样跑
  await page.locator('[data-fxdesk="builtin.godot"]').click()
  await page.locator('[data-fxforkopen]').click()   // 10-19:内置的「复制一份到这个世界」(…/fork,整份拷过来)
  await page.locator('#fxforkname').fill('my-godot')
  await page.locator('[data-fxforkgo]').click()
  await expect(page.locator('[data-fxdesk=my-godot]')).toHaveClass(/on/, { timeout: 30_000 })
  await view(page, 'files')
  await expect(page.locator('#s-fe .tree')).toContainText('smoke.gd', { timeout: 30_000 })
  await expect(page.locator('#s-fe .tree')).not.toContainText('只读')
  const godot = await page.request.get(`${BASE}/api/v1/local/frontends/_/godot`).then(r => r.json())
  if (godot.bin) {
    await view(page, 'play')
    await page.locator('[data-fxsmoke]').click()
    await expect(page.locator('#s-fe .fxres')).toContainText('通过', { timeout: 240_000 })
    await shot(page, 'fe-10-own-godot-smoke')
  }
})

// 10-19 文件工作台:内置只读 → 复制一份到这个世界 → 改草稿(看得出没存 · 离开页面提醒)→ 保存 → 导出 zip → 导入成另一个名字;
// 坏包(路径穿越)导入被拒、什么都不写;agent 写的文件标「已写入」
test('文件工作台:复制内置小手机 → 改 → 保存 → 导出 → 导入成另一个名字 · 坏包被拒 · agent 已写入', async ({ page }) => {
  test.setTimeout(300_000)
  const api = (p: string) => page.request.get(`${BASE}/api/v1/local/frontends/pct-house${p}`).then(r => r.json())
  await boot(page)
  await page.locator('.nav [data-go=fe]').click()
  await page.locator('#wlWorld').selectOption('pct-house')
  await page.locator('[data-fxdesk="builtin.chat"]').click()
  await view(page, 'files')
  await expect(page.locator('#s-fe .tree')).toContainText('只读', { timeout: 30_000 })
  await expect(page.locator('#fxedit')).toHaveCount(0)   // 内置的:没有编辑器
  await expect(page.locator('#s-fe .fxrobar')).toBeVisible()
  // 挂进来的页签(小手机编排那样):own: true 不出「只读 · 先复制」;不带 own 的照旧出
  await page.evaluate(() => {
    const F = (window as any).FXDESK
    F.addTab({ id: 'probe-own', label: '探针', own: true, when: (d: any) => d.kind === 'chat', render: () => '<div class="fxpad" id="probeown">own</div>' })
    F.addTab({ id: 'probe', label: '探针2', when: (d: any) => d.kind === 'chat', render: () => '<div class="fxpad" id="probe">plain</div>' })
  })
  await view(page, 'probe-own')
  await expect(page.locator('#probeown')).toBeVisible()
  await expect(page.locator('#s-fe .fxrobar')).toHaveCount(0)
  await view(page, 'probe')
  await expect(page.locator('#probe')).toBeVisible()
  await expect(page.locator('#s-fe .fxrobar')).toBeVisible()
  await view(page, 'files')
  await page.locator('[data-fxforkopen]').click()
  await page.locator('#fxforkname').fill('phone-x')
  await page.locator('[data-fxforkgo]').click()
  await expect(page.locator('[data-fxdesk=phone-x]')).toHaveClass(/on/, { timeout: 30_000 })
  await expect(page.locator('#s-fe .tree')).not.toContainText('只读')
  // 改草稿:看得出没存
  await page.locator('#s-fe [data-fxf="index.html"]').click()
  const ed = page.locator('#fxedit')
  await expect(ed).toBeVisible()
  const orig = await ed.inputValue()
  await expect(page.locator('.fxedh')).toContainText('已保存')
  await ed.fill(orig.replace('<head>', '<head>\n<!-- 灰橡宅版 -->'))
  await expect(page.locator('.fxedh')).toContainText('草稿 · 没保存')
  await expect(page.locator('#s-fe .tree [data-fxf="index.html"] .fxdot')).toBeVisible()
  await expect(page.locator('#s-fe .crumb')).toContainText('1 个文件没保存')
  expect((await api('/phone-x/file?path=index.html')).content).toBe(orig)   // 没存:磁盘上还是原样
  // 离开页面:提醒(取消 = 留下)
  let asked = ''
  page.once('dialog', d => { asked = d.type(); d.dismiss() })
  await page.close({ runBeforeUnload: true })
  await expect.poll(() => asked).toBe('beforeunload')
  expect(page.isClosed()).toBe(false)
  await shot(page, 'fe-11-draft')
  // 保存
  await page.locator('[data-fxsave]').click()
  await expect(page.locator('.fxedh')).toContainText('已保存', { timeout: 15_000 })
  await expect(page.locator('#s-fe .crumb')).not.toContainText('没保存')
  expect((await api('/phone-x/file?path=index.html')).content).toContain('<!-- 灰橡宅版 -->')
  // 导出 zip
  const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('[data-fxexport]').click()])
  expect(dl.suggestedFilename()).toBe('phone-x.frontend.zip')
  const zipPath = join(test.info().outputDir, 'phone-x.frontend.zip')
  await dl.saveAs(zipPath)
  // 导入成另一个名字
  await page.locator('[data-fxdesk=new]').click()
  await page.locator('#fximpname').fill('phone-y')
  await page.locator('#fximpfile').setInputFiles(zipPath)
  await expect(page.locator('[data-fxdesk=phone-y]')).toHaveClass(/on/, { timeout: 30_000 })
  expect((await api('/phone-y/file?path=index.html')).content).toContain('<!-- 灰橡宅版 -->')
  // 坏包:路径穿越 → 列原因,不写盘
  const bad = execFileSync('python3', ['-c', 'import io,zipfile,sys\nb=io.BytesIO()\nz=zipfile.ZipFile(b,"w")\nz.writestr("../evil.js","x")\nz.writestr("frontend.json","{}")\nz.close()\nsys.stdout.buffer.write(b.getvalue())'])
  await page.locator('[data-fxdesk=new]').click()
  await page.locator('#fximpname').fill('evil')
  await page.locator('#fximpfile').setInputFiles({ name: 'evil.zip', mimeType: 'application/zip', buffer: bad })
  await expect(page.locator('#s-fe .fximp')).toContainText('没导入(什么都没写)', { timeout: 15_000 })
  await expect(page.locator('#s-fe .fxprob').first()).toContainText('frontend.import')
  expect((await api('')).frontends.map((x: any) => x.id)).not.toContain('evil')
  await shot(page, 'fe-12-import-refused')
  // agent 直接写盘:文件上标「已写入」
  await page.locator('[data-fxdesk=phone-y]').click()
  await page.locator('[data-fxsay="加一个背包按钮"]').click()
  await expect(page.locator('#fxchat .m.agent').last()).toContainText('已写入:bag.js', { timeout: 60_000 })
  await view(page, 'files')
  await expect(page.locator('#s-fe .tree [data-fxf="bag.js"] .fxwrote')).toHaveText('已写入', { timeout: 30_000 })
  await page.locator('#s-fe [data-fxf="bag.js"]').click()
  await expect(page.locator('.fxedh')).toContainText('agent 已写入')
  await shot(page, 'fe-13-agent-wrote')
})
