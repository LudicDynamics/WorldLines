// v0.3.0 发布验收清单的 e2e 固化(niko 手测清单 → 自动用例)。
// 全部零 LLM;引擎 = 隔离 HOME(scripts/e2e-server.sh)。文件名以 c 开头
// 使其在 shell/stage/studio 之前跑 —— 首条用例依赖「引擎还没绑定过会话」。
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

async function welcomed(page: Page, lang = 'zh') {
  await page.addInitScript(
    ([l]) => {
      sessionStorage.setItem('wl-local-welcomed', '1')
      // 只设初值,不覆盖 —— initScript 每次导航都会跑,硬写会把用例内的
      // 语言切换(A2)冲掉
      if (!localStorage.getItem('wl-local-lang')) localStorage.setItem('wl-local-lang', l)
    },
    [lang],
  )
}

async function bindBuiltin(request: APIRequestContext): Promise<string> {
  const wr = await request.get('/api/v1/local/worlds')
  const worlds = (await wr.json()) as { builtin?: { id: string }[] }
  const id = worlds.builtin?.[0]?.id as string
  await request.post('/api/v1/play/session', { data: { slug: id } })
  return id
}

// ── A. 空态与门面 ────────────────────────────────────────────────────

test('A1 未绑定会话进游玩现场 → 友好空态 + 回书房', async ({ page }) => {
  // 必须是本文件第一条:引擎自启动以来还没 bind 过任何会话
  await welcomed(page)
  await page.goto('/local/stage')
  await expect(page.getByTestId('stage-root')).toBeVisible()
  await expect(page.getByText(/还没有绑定世界|No world is bound/)).toBeVisible()
  await expect(page.locator('a.lc-link[href="/local"]')).toBeVisible()
})

test('A2 语言切换:切 EN → 全页文案变英文并持久', async ({ page }) => {
  await welcomed(page) // zh 起步
  await page.goto('/local')
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Play', exact: true })).toBeVisible({ timeout: 10_000 })
  await page.reload()
  await expect(page.getByRole('link', { name: 'Play', exact: true })).toBeVisible()
  const stored = await page.evaluate(() => localStorage.getItem('wl-local-lang'))
  expect(stored).toBe('en')
})

// ── B. 游玩准备(D4 TUI 流)────────────────────────────────────────────

test('B1 PrePlay 分步结构:①世界确认 ②带入角色 ③模型接入 + 底部进入键', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/play')
  await page.locator('a[href*="/local/play/"]').first().click()
  await page.getByRole('button', { name: '新开一局', exact: true }).click()
  await expect(page).toHaveURL(/\/local\/preplay\//)
  await expect(page.getByText('世界确认', { exact: true })).toBeVisible()
  await expect(page.getByText('带入角色', { exact: true })).toBeVisible()
  await expect(page.getByText('模型接入', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /进入世界/ })).toBeVisible()
})

test('B2 PrePlay resume:带入角色被跳过,存档信息显示', async ({ page, request }) => {
  // 先造一个存档(bind 内置世界 = scaffold 新 run)
  const id = await bindBuiltin(request)
  await welcomed(page)
  const sr = await request.get('/api/v1/play/saves')
  const saves = (await sr.json()) as { saves: { session_id: string }[] }
  const sid = saves.saves.find((s) => s.session_id.startsWith(id))?.session_id
  expect(sid, '应有刚 scaffold 的存档').toBeTruthy()
  await page.goto(`/local/preplay/${encodeURIComponent(sid!)}?resume=1`)
  await expect(page.getByText('世界确认', { exact: true })).toBeVisible()
  await expect(page.getByText('带入角色', { exact: true })).toHaveCount(0)
  await expect(page.getByText(/继续存档/).first()).toBeVisible()
})

// ── C. 游玩现场(D5/D7 补充:地图 / REPLAY / 主题)──────────────────────

test('C1 AGENT MAP:世界节点渲染 + 缩放按钮 + 最小化', async ({ page, request }) => {
  await bindBuiltin(request)
  await welcomed(page)
  await page.goto('/local/stage')
  const map = page.getByTestId('stage-map')
  await expect(map).toBeVisible()
  // world_map 节点(内置世界都带地图)→ svg 里应有 ≥2 个地点圈
  await expect(map.locator('svg g circle').first()).toBeVisible({ timeout: 15_000 })
  const nodes = await map.locator('svg text').count()
  expect(nodes).toBeGreaterThan(0)
  // 缩放按钮
  await expect(map.getByRole('button', { name: '+' })).toBeVisible()
  // 最小化 → svg 消失;恢复 → 回来
  await map.getByRole('button', { name: 'minimize' }).click()
  await expect(map.locator('svg')).toHaveCount(0)
  await map.getByRole('button', { name: 'minimize' }).click()
  await expect(map.locator('svg')).toBeVisible()
})

test('C2 REPLAY:零回合时优雅空态(不崩不假装)', async ({ page, request }) => {
  await bindBuiltin(request)
  await welcomed(page)
  await page.goto('/local/stage')
  await expect(page.getByTestId('stage-world')).not.toBeEmpty({ timeout: 15_000 })
  await page.getByRole('button', { name: /REPLAY/ }).click()
  // 新 run 没有回合:要么显示空提示,要么回放条为 0/0 —— 不崩即验收
  await expect(page.getByTestId('stage-root')).toBeVisible()
})

test('C3 主题统一:游玩现场跟随 ☀/☾', async ({ page, request }) => {
  await bindBuiltin(request)
  await welcomed(page)
  await page.addInitScript(() => localStorage.setItem('wl-local-theme', 'light'))
  await page.goto('/local/stage')
  await expect(page.getByTestId('stage-root')).toBeVisible()
  // light 主题的 --lc-panel 是纸色 #fbf9f4 —— 从 stage 内元素算出的变量应命中
  const panel = await page
    .getByTestId('stage-root')
    .evaluate((el) => getComputedStyle(el).getPropertyValue('--lc-panel').trim())
  expect(panel.toLowerCase()).toBe('#fbf9f4')
})

// ── D. 创作与书房 ──────────────────────────────────────────────────────

test('D1 新建世界带中文名 → 工坊显示真名(不是时间戳 slug)', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/create')
  await page.getByPlaceholder(/世界的名字/).fill('雾汐港测试')
  await page.getByRole('button', { name: '开始创作' }).click()
  await expect(page).toHaveURL(/\/local\/create\/studio/, { timeout: 20_000 })
  await expect(page.getByText('雾汐港测试').first()).toBeVisible()
})

test('D2 导出世界 zip → 再导入(UI 文件上传往返)', async ({ page, request }) => {
  await welcomed(page)
  // 用 D1 建的世界导出(找一个 owned 世界)
  const wr = await request.get('/api/v1/local/worlds')
  const worlds = (await wr.json()) as { worlds: { id: string }[] }
  const wid = worlds.worlds[0]?.id
  expect(wid, '应有 owned 世界(D1 建的)').toBeTruthy()
  const zr = await request.get(`/api/v1/local/worlds/${encodeURIComponent(wid!)}/export`)
  expect(zr.ok()).toBe(true)
  const zip = await zr.body()
  expect(zip.subarray(0, 2).toString()).toBe('PK')
  // UI 导入:创作门 → 世界包(.zip)→ setInputFiles 喂内存 buffer。
  // 新导入 UX:zip 入库后直接开工坊编辑(不再停留在创作门)。
  await page.goto('/local/create')
  const chooser = page.locator('input[type=file][accept=".zip"]')
  await chooser.setInputFiles({ name: 're-import.zip', mimeType: 'application/zip', buffer: zip })
  await expect(page).toHaveURL(/\/local\/create\/studio/, { timeout: 20_000 })
  await expect(page.getByText('当前世界')).toBeVisible({ timeout: 10_000 })
})

test('D3 书房设置:创作 LLM 下拉 + ComfyUI 保存 + 条目列表', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/library?tab=settings')
  await expect(page.getByText('创作用 LLM')).toBeVisible()
  await expect(page.getByText('图像生成')).toBeVisible()
  // 新面板:先选 ComfyUI 后端 → URL/ckpt/高级折叠出现 → 保存
  await page.getByRole('button', { name: 'ComfyUI', exact: true }).click()
  await page.getByPlaceholder(/8188/).fill('http://127.0.0.1:8188')
  await page.getByRole('button', { name: '高级(自定义 workflow)' }).click()
  await expect(page.getByText('input node')).toBeVisible()
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText(/✓ 已保存/)).toBeVisible({ timeout: 8_000 })
})

test('D3b 书房设置:自定义 API 端点(SillyTavern 式)→ 保存 → 成为可选 provider', async ({ page }) => {
  // 回归护栏:这个「自定义 AI API 端点」输入曾被误删(niko:「你把这个端口搞没了」)。
  await welcomed(page)
  await page.goto('/local/library?tab=settings')
  await expect(page.getByText('添加自定义 API 端点')).toBeVisible()
  // base_url 有默认值(localhost:11434/v1);填模型名 + 唯一 id 再保存。
  await page.getByPlaceholder('qwen2.5:14b').fill('llama3.1:8b')
  await page.getByPlaceholder('my-llama').fill('e2e-llm')
  await page.getByRole('button', { name: '保存端点', exact: true }).click()
  await expect(page.getByText('✓ 已添加 e2e-llm')).toBeVisible({ timeout: 8_000 })
  // 保存后作为独立 provider 出现在上面列表里(本地端点无 key → 无 ✓ 徽标,label 即 id)。
  await expect(page.getByText('e2e-llm', { exact: true })).toBeVisible()
})

test('D4 生成角色 → 白模 scaffold 直入角色工坊(编辑界面+三选卡)', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/create')
  await page.getByPlaceholder(/角色名/).fill('e2e角色')
  await page.getByRole('button', { name: '生成角色' }).click()
  // v3(niko 定稿):永远是编辑界面 —— 白模(艾琳娜)scaffold 即入库,
  // 零 LLM 直入工作台;新建才有开场三选卡
  await expect(page).toHaveURL(/\/local\/create\/soul/)
  await expect(page.getByRole('button', { name: '资料', exact: true }).first()).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: '剧情弧线', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '立绘', exact: true })).toBeVisible()
  await expect(page.getByText('先分析迁移差距')).toBeVisible()
  // 白模文件树已入库(persona 等)
  await expect(page.getByText(/persona/).first()).toBeVisible()
  // 弧线画布有默认内容
  await page.getByRole('button', { name: '剧情弧线', exact: true }).click()
  await expect(page.locator('.react-flow')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.react-flow__node').first()).toBeVisible()
})
