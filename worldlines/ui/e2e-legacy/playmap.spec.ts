// 地图优先游玩 E2E:开局落「地图」频道 → 图片地图 + 地点针(北门=你在这里)→
// 点北门进地点 → 空间里站着艾琳娜的立绘 → 点她开 VN 对话框 → 面包屑回世界层 →
// 3D 切换出画布 → 点别处「前往」送出行动。全程不依赖 LLM:/say 与 /cmd 用
// page.route 拦截,只断言 UI 与发出的请求。
import { test, expect, type Page } from '@playwright/test'

async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh')
  })
}

test('地图优先:地图 → 地点(对话/空间)→ VN 对话 → 世界层 → 3D → 前往', async ({ page }) => {
  await welcomed(page)
  const cmds: string[] = []
  await page.route('**/cmd', (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    cmds.push(String(route.request().postDataJSON()?.text ?? ''))
    return route.fulfill({ status: 202, contentType: 'application/json', body: '{}' })
  })
  await page.route('**/api/v1/play/say', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ lane: 'dialogue', target: 'si-elena0001', ok: true, reply: '雾还没散呢。' }),
    }),
  )

  await page.goto('/local/observe?world=stoneford-elena')

  // 开局默认 = 地图频道,落在玩家所在的镇(T001),北门是「你在这里」
  await expect(page.getByTestId('chan-map-stage')).toBeVisible({ timeout: 20_000 })
  const map = page.getByTestId('image-map')
  await expect(map).toHaveAttribute('data-level', 'T001')
  expect(await map.locator('.wlm-pin').count()).toBeGreaterThan(3)
  const gate = map.locator('.wlm-pin[data-addr="T001/gate_north"]')
  await expect(gate).toHaveClass(/is-here/)

  // 点北门(玩家所在)→ 地点视图,默认「对话」= 常驻的 PlayStage
  await gate.click()
  await expect(page.getByTestId('place-head')).toBeVisible()
  await expect(page.getByTestId('place-tab-chat')).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('chan-world-stage')).toBeVisible()

  // 空间 → 艾琳娜的立绘;点她 → VN 对话框,回话显示在框里
  await page.getByTestId('place-tab-space').click()
  await expect(page.getByTestId('space-view')).toBeVisible()
  const elena = page.getByTestId('sprite-elena')
  await expect(elena).toBeVisible()
  await elena.click()
  await expect(page.getByTestId('vn-box')).toBeVisible()
  await page.getByTestId('vn-input').fill('这里是哪里？')
  await page.getByTestId('vn-send').click()
  await expect(page.getByTestId('vn-box')).toContainText('雾还没散呢。')

  // 回地图 → 面包屑上一级 = 世界层
  await page.getByTestId('place-back-map').click()
  await page.getByTestId('map-crumbs').getByRole('button').first().click()
  await expect(page.getByTestId('image-map')).toHaveAttribute('data-level', 'world')

  // 3D 切换出 WebGL 画布
  await page.getByTestId('map-3d-toggle').click()
  await expect(page.getByTestId('map-3d').locator('canvas').first()).toBeVisible()

  // 回 2D,钻回镇上,点另一个地点 →「前往」卡 → 送出「前往…」并切到地点·对话
  await page.getByTestId('map-2d').click()
  await page.getByTestId('image-map').locator('.wlm-pin[data-addr="T001"]').click()
  await expect(page.getByTestId('image-map')).toHaveAttribute('data-level', 'T001')
  await page.getByTestId('image-map').locator('.wlm-pin[data-addr="T001/inn"]').click()
  await expect(page.getByTestId('go-card')).toBeVisible()
  await page.getByTestId('go-btn').click()
  await expect.poll(() => cmds.find((c) => c.startsWith('前往'))).toBeTruthy()
  await expect(page.getByTestId('place-head')).toContainText('正在前往')
  await expect(page.getByTestId('place-tab-chat')).toHaveAttribute('aria-selected', 'true')
})
