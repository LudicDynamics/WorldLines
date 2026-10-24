// 创作台 AI 生图(create-art.js · 10-18):网页创作台每个图片槽旁的「生成」→ 选风格 / 改描述 → 剩余次数和价格 → 生成 →
// 预览 → 用这张(进草稿的槽位)。平台 ai 的 /v1/create/art 在这里拦掉,回一张占位图;不连真接口、不花额度。
// 跑法:bash worldlines/ui/e2e-play/run.sh create-art.spec.ts(截图:WL_ART_SHOTS=<目录>)
import { expect, test, type Page, type Route } from '@playwright/test'
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const TPL = process.env.WL_ART_TPL || 'wuwu'
const SHOTS = process.env.WL_ART_SHOTS || ''
const PLACEHOLDER = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../../templates/pct-house.template/assets/cover.jpg')).toString('base64')   // 1920×1080 占位

const INFO = (o: Record<string, unknown> = {}) => ({
  work_ref: `hub/template/${TPL}-mine`, model: 'gpt-image-1.5', quality: 'medium',
  allowance: { cover: { free: 1, used: 0, left: 1 }, world: { free: 4, used: 0, left: 4 } }, free_daily: { max: 12, used: 0 },
  styles: ['anime', 'semi_real', 'scifi', 'illustration', 'other'],
  kinds: { cover: { size: '1536x1024', target: '1672x941', credits: 102 }, portrait: { size: '1024x1536', target: '1024x1536', credits: 102 }, avatar: { size: '1024x1536', target: '1086x1448', credits: 102 }, scene: { size: '1536x1024', target: '1672x941', credits: 102 }, cg: { size: '1536x1024', target: '1672x941', credits: 102 }, item: { size: '1024x1024', target: '1024x1024', credits: 68 } },
  plan: { name: 'free', images_left: 3 }, ...o,
})

async function fakeArt(page: Page, answer: (body: any) => { status: number, json: any }) {
  const posts: any[] = []
  await page.route('**/v1/create/art**', async (route: Route) => {
    const req = route.request()
    const cors = { 'access-control-allow-origin': new URL(page.url()).origin, 'access-control-allow-headers': 'authorization, content-type, x-worldlines-product', 'access-control-allow-methods': 'GET, POST, OPTIONS' }
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
    if (req.method() === 'GET') return route.fulfill({ status: 200, headers: cors, contentType: 'application/json', body: JSON.stringify(INFO()) })
    const body = req.postDataJSON()
    posts.push({ body, auth: req.headers().authorization })
    const a = answer(body)
    return route.fulfill({ status: a.status, headers: cors, contentType: 'application/json', body: JSON.stringify(a.json) })
  })
  return posts
}
const drawn = (body: any, o: Record<string, unknown> = {}) => ({ status: 201, json: { b64_png: PLACEHOLDER, content_type: 'image/jpeg', work_ref: body.work_ref, kind: body.kind, style: body.style, size: '1536x1024', target: INFO().kinds[body.kind as 'cover'].target, model: 'gpt-image-1.5', paid_by: 'free_cover', credits: 0, allowance: { cover: { free: 1, used: 1, left: 0 }, world: { free: 4, used: 0, left: 4 } }, ...o } })
const shot = async (page: Page, name: string) => { if (SHOTS) { mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: join(SHOTS, name) }) } }

let errs: string[] = []
test.beforeEach(async ({ context, page }) => {
  errs = []
  page.on('pageerror', e => errs.push(e.message))
  await context.addInitScript(() => {
    try { if (!localStorage.getItem('wl.hub.auth')) localStorage.setItem('wl.hub.auth', JSON.stringify({ access: 'tok-e2e', exp: Date.now() + 3600e3, refresh: 'r-e2e', user: { id: 'u-e2e' } })) } catch { /* storage blocked */ }
  })
})
test.afterEach(() => { expect(errs, 'no pageerror').toEqual([]) })

test('封面槽:生成 → 选风格改描述 → 免费次数 → 预览(裁成 1672×941)→ 用这张进草稿;请求里只有字段,没有提示词', async ({ page }) => {
  const posts = await fakeArt(page, b => drawn(b))
  await page.goto(`/#/t/${TPL}/create`)
  const gen = page.locator('[data-art-open][data-sec="card"]')
  await expect(gen).toBeVisible({ timeout: 60_000 })
  await gen.click()
  const sheet = page.locator('#caModal [role=dialog]')
  await expect(sheet).toBeVisible()
  await expect(sheet.locator('[data-art-style]')).toHaveText(['二次元', '写实二次元', '科幻风', '插画风', '其他'])
  await expect(sheet.locator('[data-art-quota]')).toContainText('封面免费:还剩 1 次')
  await expect(sheet.locator('[data-art-go]')).toContainText('免费')
  await sheet.locator('[data-art-style="other"]').click()
  await expect(sheet.locator('[data-art-note]')).toBeVisible()
  await sheet.locator('[data-art-note]').fill('像旧明信片的水彩')
  await sheet.locator('[data-art-desc]').fill('雨夜的霓虹街口,一把红伞')
  await shot(page, '01-panel.png')
  await sheet.locator('[data-art-go]').click()
  await expect(sheet.locator('[data-art-shot]')).toBeVisible()
  await expect(sheet).toContainText('1672×941')
  await expect(sheet.locator('[data-art-quota]')).toContainText('封面免费:还剩 0 次')
  await shot(page, '02-preview.png')
  expect(posts).toHaveLength(1)
  expect(posts[0].auth).toBe('Bearer tok-e2e')
  expect(posts[0].body).toMatchObject({ work_ref: `hub/template/${TPL}-mine`, kind: 'cover', style: 'other', note: '像旧明信片的水彩', description: '雨夜的霓虹街口,一把红伞' })
  for (const k of Object.keys(posts[0].body)) expect(['work_ref', 'kind', 'style', 'description', 'setting', 'note']).toContain(k)
  await sheet.locator('[data-art-use]').click()
  await expect(page.locator('#caModal [role=dialog]')).toHaveCount(0)
  const thumb = page.locator('[data-art-open][data-sec="card"]').locator('xpath=ancestor::label[1]').locator('.cfthumb img')
  await expect(thumb).toHaveAttribute('src', /^blob:/)
  const dims = await thumb.evaluate((img: HTMLImageElement) => new Promise<number[]>(ok => (img.complete ? ok([img.naturalWidth, img.naturalHeight]) : (img.onload = () => ok([img.naturalWidth, img.naturalHeight])))))
  expect(dims).toEqual([1672, 941])
  await shot(page, '03-in-slot.png')
})

test('立绘槽可选半身 / 全身;积分不够 → 提示 + 充值链接;描述被拒 → 换个说法', async ({ page }) => {
  let n = 0
  const posts = await fakeArt(page, b => (++n === 1
    ? { status: 402, json: { error: { code: 'insufficient_credits', message: 'Not enough credits', billing_url: 'https://billing.worldlines.gg/subscribe?product=hub&reason=quota' } } }
    : n === 2 ? { status: 422, json: { error: { code: 'content_refused', message: 'This image cannot be drawn.' } } } : drawn(b, { paid_by: 'free_world' })))
  await page.goto(`/#/t/${TPL}/create`)
  const gen = page.locator('[data-art-open][data-sec="soul"]').first()
  await expect(gen).toBeVisible({ timeout: 60_000 })
  await gen.click()
  const sheet = page.locator('#caModal [role=dialog]')
  await expect(sheet.locator('[data-art-kind]')).toHaveText(['半身像 1086×1448', '全身立绘 1024×1536'])
  await sheet.locator('[data-art-kind="portrait"]').click()
  await sheet.locator('[data-art-desc]').fill('穿风衣的高个信使')
  await sheet.locator('[data-art-go]').click()
  await expect(sheet.locator('[data-art-err]')).toContainText('积分不够')
  await expect(sheet.locator('[data-art-err] a')).toHaveAttribute('href', /billing\.worldlines\.gg\/subscribe/)
  await sheet.locator('[data-art-go]').click()
  await expect(sheet.locator('[data-art-err]')).toContainText('换个说法')
  await shot(page, '04-refused.png')
  await sheet.locator('[data-art-go]').click()
  await expect(sheet).toContainText('1024×1536')
  expect(posts.map(p => p.body.kind)).toEqual(['portrait', 'portrait', 'portrait'])
  await sheet.locator('[data-art-close]').click()
  await expect(page.locator('#caModal [role=dialog]')).toHaveCount(0)
})

test('登录过期 / 引擎没登录(401 not_signed_in)→ 回到「登录后才能生成」,不报错', async ({ page }) => {
  await page.route('**/v1/create/art**', route => {
    const cors = { 'access-control-allow-origin': new URL(page.url()).origin, 'access-control-allow-headers': 'authorization, content-type, x-worldlines-product', 'access-control-allow-methods': 'GET, POST, OPTIONS' }
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
    return route.fulfill({ status: 401, headers: cors, contentType: 'application/json', body: JSON.stringify({ error: { code: 'not_signed_in', message: 'sign in to Worldlines first' } }) })
  })
  await page.goto(`/#/t/${TPL}/create`)
  const gen = page.locator('[data-art-open][data-sec="card"]')
  await expect(gen).toBeVisible({ timeout: 60_000 })
  await gen.click()
  const sheet = page.locator('#caModal [role=dialog]')
  await expect(sheet.locator('[data-art-sign]')).toBeVisible()
  await expect(sheet).toContainText('登录 Worldlines 账号后才能生成图片')
  await expect(sheet.locator('[data-art-err]')).toHaveCount(0)
})
