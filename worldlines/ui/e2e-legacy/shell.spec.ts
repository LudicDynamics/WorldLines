// LocalShell 冒烟(T2.5 首批):门面/首页/游玩门/PrePlay。
// 全部不依赖 LLM —— 只走导航、scaffold、静态渲染路径。
import { test, expect, type Page } from '@playwright/test'

// 多数用例跳过首次引导;首次引导本身单独测
async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh') // 断言全是中文文案 — 钉死语言
  })
}

test('首次打开 → 直接进壳(去掉 /local/welcome 整页封面)', async ({ page }) => {
  // niko 2026-09-18:去掉整页门艺术封面;首开直接进壳,无 key 时弹 ConfigTutorial 引导。
  await page.addInitScript(() => localStorage.setItem('wl-local-lang', 'zh'))
  await page.goto('/local')
  await expect(page).not.toHaveURL(/\/local\/welcome/)
  await expect(page.getByText('WorldLines').first()).toBeVisible()
})

test('门面只挡壳根路由:深链不被劫持', async ({ page }) => {
  // 未 welcomed 直接访问深链 → 不应被拽去 welcome(PLAY-FUSION §四.1)
  await page.addInitScript(() => localStorage.setItem('wl-local-lang', 'zh'))
  await page.goto('/local/play')
  await expect(page).toHaveURL(/\/local\/play/)
  await expect(page.getByText('内置世界')).toBeVisible()
})

test('首页:世界展示 + 创建入口 + 主题切换持久', async ({ page }) => {
  // niko 2026-09-18 改版:去掉抽象"四门",一进来就是「世界展示 + 创建指引」。
  await welcomed(page)
  await page.goto('/local')
  // 世界展示区(取代旧四门)——header 标题 + 至少一张世界卡
  await expect(page.getByText('开新局 · 选个世界')).toBeVisible()
  await expect(page.locator('.wl-world-card').first()).toBeVisible()
  // 切主题在非 home 页测(home 首开无 key 时被 ConfigTutorial 弹窗遮挡点击)
  await page.goto('/local/library')
  await page.getByRole('button', { name: '切换配色' }).click()
  await page.reload()
  const stored = await page.evaluate(() => localStorage.getItem('wl-local-theme'))
  expect(stored).toBe('light')
})

test('游玩门:内置世界封面卡可见', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/play')
  await expect(page.getByText('内置世界')).toBeVisible()
  // 打包内置至少有 kagura-island / stoneford-elena 两张卡
  await expect(page.locator('a[href*="/local/play/"]').first()).toBeVisible()
})

test('世界详情 → PrePlay:分步 ①②③ 结构(世界确认/带入角色/模型接入)', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/play')
  await page.locator('a[href*="/local/play/"]').first().click()
  await page.getByRole('button', { name: '新开一局', exact: true }).click()
  await expect(page).toHaveURL(/\/local\/preplay\//)
  // TUI 启动流的三步分区(D4):世界确认 → 带入角色 → 模型接入
  await expect(page.getByRole('heading', { name: '世界确认', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '带入角色', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '模型接入', exact: true })).toBeVisible()
  // 进入键可见;禁用与否取决于环境里是否有免 key preset(GLM free /
  // Claude Code CLI 探测),不做硬断言 —— 与「无 preset 则禁用」的逻辑
  // 由 ModelAccessPanel 单元行为保证
  await expect(page.getByRole('button', { name: /进入世界/ })).toBeVisible()
})

test('PrePlay 模型接入:＋自定义 API 端点 → 保存 → 就地成可选 pill', async ({ page }) => {
  // 回归护栏:自定义 API 端点也要能从首访/进场的模型接入面板里加(不止 /local/settings)。
  await welcomed(page)
  await page.goto('/local/play')
  await page.locator('a[href*="/local/play/"]').first().click()
  await page.getByRole('button', { name: '新开一局', exact: true }).click()
  await expect(page.getByRole('heading', { name: '模型接入', exact: true })).toBeVisible()
  // 点开内联表单 → 填模型名 + id(base_url 有默认)→ 保存端点
  await page.getByRole('button', { name: '＋ 自定义 API 端点' }).click()
  await page.getByPlaceholder('qwen2.5:14b').fill('llama3.1:8b')
  await page.getByPlaceholder('my-llama').fill('welcome-llm')
  await page.getByRole('button', { name: '保存端点', exact: true }).click()
  // 新 provider 就地成为可选 pill(本地端点无 key → label 即 id)
  await expect(page.getByRole('button', { name: 'welcome-llm', exact: true })).toBeVisible({ timeout: 8_000 })
})

test('书房:三个 tab 渲染;设置列出 preset', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/library')
  await page.getByRole('button', { name: '设置' }).click()
  await expect(page.getByText('创作用 LLM')).toBeVisible()
  await expect(page.getByText('图像生成')).toBeVisible()
  await page.getByRole('button', { name: '角色库' }).click()
  await expect(page.getByText(/角色库是空的|对话/).first()).toBeVisible()
})
