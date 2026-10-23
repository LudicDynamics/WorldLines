// 工作台 · 地图创作(图像地图):stoneford-elena 模板自带 world/T001/T004/D001
// 四层地图。拖钉 = 写回文件坐标(层级转「待重画」);加地点 = 写进 town_map;
// 生图走 page.route 假回应(e2e 没配图像后端,也不该烧钱)。
import { test, expect, type Page } from '@playwright/test'

const MAP = '/api/v1/create/session/edit-local/map'

test.use({ viewport: { width: 1440, height: 900 } })

async function openStudio(page: Page, name: string) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh')
    localStorage.setItem('wl-studio-mapmode', 'image')
  })
  const r = await page.request.post('/api/v1/create/session', {
    data: { template: 'stoneford-elena', name },
  })
  expect(r.ok()).toBe(true)
  await page.goto('/local/create/studio')
  await page.getByRole('button', { name: '世界图', exact: true }).click()
  await expect(page.getByTestId('image-map')).toBeVisible({ timeout: 10_000 })
  await page.locator('.wms-level[data-level=T001]').click()
  await expect(page.getByTestId('image-map')).toHaveAttribute('data-level', 'T001')
}

test('图像地图:钉子可见 → 拖动写回坐标 → 该层标记待重画', async ({ page }) => {
  await openStudio(page, 'e2e-mapstudio-drag')
  await expect(page.locator('.wlm-pin[data-addr="T001/inn"]')).toBeVisible()
  expect(await page.locator('.wlm-pin').count()).toBeGreaterThan(3)

  const dot = await page.locator('.wlm-pin[data-addr="T001/inn"] .wlm-dot').boundingBox()
  await page.mouse.move(dot!.x + 7, dot!.y + 7)
  await page.mouse.down()
  await page.mouse.move(dot!.x + 70, dot!.y + 40, { steps: 8 })
  await page.mouse.up()

  // 10-05 起地点按文件夹存(game/locations/<镇>/<地点>/location.json);旧世界仍写 town_map.json
  await expect(page.getByTestId('map-receipt')).toContainText(/location\.json|town_map\.json/)
  await expect
    .poll(async () => ((await (await page.request.get(MAP)).json()) as { levels: Record<string, { stale: boolean }> }).levels.T001.stale)
    .toBe(true)
  await expect(page.locator('.wms-level[data-level=T001]')).toContainText('待重画')
})

test('图像地图:添加地点 → 新钉出现并被选中', async ({ page }) => {
  await openStudio(page, 'e2e-mapstudio-add')
  const before = await page.locator('.wlm-pin').count()
  await page.getByRole('button', { name: '＋ 添加地点' }).click()
  // 空地(左侧中部没有钉);locator.click 会先滚进视口
  const fit = page.locator('.wlm-fit')
  const box = (await fit.boundingBox())!
  await fit.click({ position: { x: box.width * 0.12, y: box.height * 0.55 } })
  await expect(page.getByTestId('map-add-popover')).toBeVisible()
  await page.getByPlaceholder('例：铁匠铺').fill('铁匠铺')
  await page.getByRole('button', { name: '写入地图' }).click()

  await expect(page.locator('.wlm-pin')).toHaveCount(before + 1)
  await expect(page.locator('.wlm-pin.is-sel')).toContainText('铁匠铺')
  await expect(page.getByTestId('map-inspector')).toContainText('铁匠铺')
})

test('数据体检列表 + 点问题跳层;3D 视图出 canvas', async ({ page }) => {
  await openStudio(page, 'e2e-mapstudio-issues')
  const issues = page.getByTestId('map-issues').locator('.wms-issue')
  expect(await issues.count()).toBeGreaterThan(0)
  await page.getByTestId('map-issues').getByRole('button', { name: /dungeon\.json/ }).first().click()
  await expect(page.getByTestId('image-map')).toHaveAttribute('data-level', 'world')
  await expect(page.getByTestId('map-inspector')).toContainText('D001')

  await page.getByRole('button', { name: '3D', exact: true }).click()
  await expect(page.getByTestId('map-3d').locator('canvas')).toBeVisible({ timeout: 10_000 })
})

test('按文件重新生图:假回应 running → done,地图图片刷新', async ({ page }) => {
  let polls = 0
  await page.route('**/edit-local/map/generate', (r) =>
    r.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ ok: true, job: 'map:T001', started: true }) }),
  )
  await page.route('**/edit-local/map/jobs', (r) => {
    polls += 1
    r.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ 'map:T001': polls < 2 ? { state: 'running' } : { state: 'done' } }),
    })
  })
  await openStudio(page, 'e2e-mapstudio-gen')
  const srcBefore = await page.locator('.wlm-base').getAttribute('src')

  await page.getByTestId('map-generate').click()
  await expect(page.getByText('正在按文件坐标生图…')).toBeVisible()
  await expect(page.locator('.wms-level[data-level=T001]')).toContainText('生图中')
  await expect(page.getByText('正在按文件坐标生图…')).toBeHidden({ timeout: 15_000 })
  await expect(page.getByTestId('map-generate')).toBeEnabled()
  await expect.poll(() => page.locator('.wlm-base').getAttribute('src')).not.toBe(srcBefore)
})
