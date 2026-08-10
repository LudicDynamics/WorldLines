// 工作台 + 画布 E2E(T2.5):白模板 scaffold 是机械路径(零 LLM),
// 世界图画布的「加节点→自动保存→world_map.json 落盘」全链路可测。
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh') // 断言全是中文文案 — 钉死语言
  })
}

// 用例自洽:每条画布用例自己开一个白模板编辑会话(scaffold 是机械路径,
// 零 LLM;单会话引擎,后开的替换先开的)
async function openSession(request: APIRequestContext, name: string) {
  const r = await request.post('/api/v1/create/session', {
    data: { template: 'white-blank', name },
  })
  expect(r.ok()).toBe(true)
}

test('创作:白模板 scaffold → 工作台(tabs/概览/资料树)', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/create')
  await page.getByPlaceholder('世界的名字(可留空)').fill('e2e-world')
  await page.getByRole('button', { name: '开始创作' }).click()
  await expect(page).toHaveURL(/\/local\/create\/studio/, { timeout: 20_000 })

  // 工作台骨架:tabs + 概览计数卡
  for (const tab of ['概览', '资料', '世界图', '剧情蓝图', '关系网络']) {
    await expect(page.getByRole('button', { name: tab, exact: true })).toBeVisible()
  }
  await expect(page.getByText('当前世界')).toBeVisible()

  // 资料 tab:白模板文件树非空,点开一个文件出预览
  await page.getByRole('button', { name: '资料', exact: true }).click()
  await expect(page.getByText(/game\//).first()).toBeVisible()
})

test('世界图画布:加地点 → 自动保存 → world_map.json 落盘', async ({ page, request }) => {
  await welcomed(page)
  await openSession(request, 'e2e-map')
  await page.goto('/local/create/studio')
  await expect(page.getByRole('button', { name: '世界图', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '世界图', exact: true }).click()

  // 画布加载(React Flow 挂载)
  await expect(page.locator('.react-flow')).toBeVisible({ timeout: 10_000 })

  // ＋地点 → 弹窗 → 命名 → 保存
  await page.getByRole('button', { name: /＋ 地点/ }).click()
  const nameInput = page.locator('label:has-text("名称") input')
  await nameInput.fill('雾汐港')
  await page.getByRole('button', { name: '保存', exact: true }).click()

  // 自动保存(800ms debounce)→ 状态回到已保存
  await expect(page.getByText('✓ 已保存')).toBeVisible({ timeout: 8_000 })

  // 落盘验证(轮询:✓已保存 可能来自前一笔视野保存,内容 PUT 或仍在途)
  await expect
    .poll(
      async () =>
        page.evaluate(async () => {
          const r = await fetch(
            '/api/v1/create/session/edit-local/file?path=' +
              encodeURIComponent('game/world/world_map.json'),
          )
          return r.ok ? ((await r.json()) as { content: string }).content : ''
        }),
      { timeout: 8_000 },
    )
    .toContain('雾汐港')
})

test('剧情画布:studio 副产物落盘,世界目录零污染', async ({ page, request }) => {
  await welcomed(page)
  await openSession(request, 'e2e-story')
  await page.goto('/local/create/studio')
  await page.getByRole('button', { name: '剧情蓝图', exact: true }).click()
  await expect(page.locator('.react-flow')).toBeVisible({ timeout: 10_000 })

  await page.getByRole('button', { name: /＋ 节点/ }).click()
  const nameInput = page.locator('label:has-text("名称") input')
  await nameInput.fill('入镇')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('✓ 已保存')).toBeVisible({ timeout: 8_000 })

  // 画布数据来自 canvas 端点(STUDIO_HOME),不在世界文件树里
  const canvas = await page.evaluate(async () => {
    const r = await fetch('/api/v1/create/session/edit-local/canvas/story')
    return (await r.json()) as { nodes: unknown[] }
  })
  expect(canvas.nodes.length).toBeGreaterThan(0)
  const tree = await page.evaluate(async () => {
    const r = await fetch('/api/v1/create/session/edit-local/tree')
    return (await r.json()) as { files: { path: string }[] }
  })
  expect(tree.files.some((f) => f.path.includes('flow.json'))).toBe(false)
})
