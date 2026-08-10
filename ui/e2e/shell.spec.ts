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

test('首次打开 → 游戏门面(标题画面 + API 引导展开)', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('wl-local-lang', 'zh'))
  await page.goto('/local')
  await expect(page).toHaveURL(/\/local\/welcome/)
  await expect(page.getByText('WorldLines', { exact: true })).toBeVisible()
  await expect(page.getByText('跨越门扉')).toBeVisible()
  // 没配 key:「开启旅程」应展开模型接入引导而不是放行
  await page.getByRole('button', { name: /开启旅程/ }).first().click()
  await expect(page.getByText('模型接入').first()).toBeVisible()
})

test('门面只挡壳根路由:深链不被劫持', async ({ page }) => {
  // 未 welcomed 直接访问深链 → 不应被拽去 welcome(PLAY-FUSION §四.1)
  await page.addInitScript(() => localStorage.setItem('wl-local-lang', 'zh'))
  await page.goto('/local/play')
  await expect(page).toHaveURL(/\/local\/play/)
  await expect(page.getByText('内置世界')).toBeVisible()
})

test('首页:四门 + 主题切换持久', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local')
  for (const label of ['游玩', '创作', '档案室']) {
    await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible()
  }
  // 切主题 → 刷新后仍是白
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
