// 新导入 UX(niko 定稿):卡片入工坊 + 三选项面板 + 计划进度钉。
// 导入本身零 LLM(秒回),①点击只断言指令进入对话(不等 LLM 回复)。
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh')
  })
}

// 大 lorebook 卡:45 条目触发 recommend_plan(阈值 40)
function bigWorldCard(): string {
  const entries = Array.from({ length: 45 }, (_, i) => ({
    keys: [`k${i}`],
    content: `雾汐港设定条目 ${i}:河雾常年不散,灯塔只在祭日点亮。`,
  }))
  return JSON.stringify({ name: '雾汐港', description: '河港世界卡', character_book: { entries } })
}

async function importCard(
  request: APIRequestContext,
  kind: 'world' | 'soul',
  filename: string,
  body: string,
): Promise<string> {
  const r = await request.post(
    `/api/v1/local/import/card?kind=${kind}&filename=${encodeURIComponent(filename)}`,
    { headers: { 'Content-Type': 'application/octet-stream' }, data: body },
  )
  expect(r.ok()).toBe(true)
  const d = (await r.json()) as { ok: boolean; world_id: string }
  expect(d.ok).toBe(true)
  return d.world_id
}

test('世界卡导入 → 工坊:源卡可见 + 三选项 + 推荐分批 + 世界图落位', async ({ page, request }) => {
  await welcomed(page)
  await importCard(request, 'world', '雾汐港.json', bigWorldCard())
  await page.goto('/local/create/studio')

  const panel = page.getByTestId('import-options')
  await expect(panel).toBeVisible({ timeout: 15_000 })
  // 源卡参考:仓内持久化路径可见
  await expect(panel.getByText(/game\/import\/source\.json/)).toBeVisible()
  // 三条路径 + 大卡推荐信号
  await expect(panel.getByText('① 制定转换计划 · 推荐')).toBeVisible()
  await expect(panel.getByText('② 一次性转换')).toBeVisible()
  await expect(panel.getByText('③ 手动修改')).toBeVisible()
  await expect(panel.getByText('卡片较大 —— 建议分批转换。')).toBeVisible()
  // 主区落在世界图画布(niko 定稿)
  await expect(page.locator('.react-flow')).toBeVisible({ timeout: 10_000 })
})

test('①制定转换计划:指令进入对话,面板让位', async ({ page, request }) => {
  await welcomed(page)
  await importCard(request, 'world', 'small.json', JSON.stringify({ name: '小卡', description: 'x' }))
  await page.goto('/local/create/studio')
  const panel = page.getByTestId('import-options')
  await expect(panel).toBeVisible({ timeout: 15_000 })

  await panel.getByText('① 制定转换计划').click()
  // 开场指令作为用户消息进入对话(不等 LLM 回复 —— e2e 引擎无 key)
  await expect(page.getByText(/计划-分批协议/).first()).toBeVisible({ timeout: 10_000 })
  await expect(panel).toBeHidden()
})

test('pending 计划 → 进度钉 + 继续下一批', async ({ page, request }) => {
  await welcomed(page)
  await importCard(request, 'world', 'resume.json', JSON.stringify({ name: '续跑', description: 'x' }))
  const plan = {
    version: 1,
    source: 'game/import/source.json',
    source_format: 'json-card',
    batches: [
      { id: 'b1', title: '骨架', items: [], status: 'done' },
      { id: 'b2', title: '地点', items: [], status: 'pending' },
    ],
  }
  const r = await request.put('/api/v1/create/session/edit-local/file', {
    data: { path: 'game/import/plan.json', content: JSON.stringify(plan) },
  })
  expect(r.ok()).toBe(true)

  await page.goto('/local/create/studio')
  const pin = page.getByTestId('import-progress')
  await expect(pin).toBeVisible({ timeout: 15_000 })
  await expect(pin.getByText('导入计划 1/2')).toBeVisible()
  await expect(pin.getByText(/下一批:地点/)).toBeVisible()
  await expect(pin.getByRole('button', { name: '继续下一批' })).toBeEnabled()
})

test('角色卡导入 → 角色工坊:资料树聚焦 + 三选项', async ({ page, request }) => {
  await welcomed(page)
  const dir = await importCard(
    request,
    'soul',
    '艾琳娜.json',
    JSON.stringify({ name: '艾琳娜', description: '河灯旅店的店主', personality: '温柔而倔强' }),
  )
  await page.goto(`/local/create/soul?dir=${encodeURIComponent(dir)}`)

  const panel = page.getByTestId('import-options')
  await expect(panel).toBeVisible({ timeout: 15_000 })
  await expect(panel.getByText('① 制定转换计划')).toBeVisible()
  // 资料树(默认 tab)展示 soul 结构
  await expect(page.getByText(/soul\.json|persona\//).first()).toBeVisible()
})
