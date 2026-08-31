// 频道玻璃 E2E(M24 §7 / v0.4.0 通宵认证):层阶入口 → 频道结构 → 世界频道
// 内嵌舞台 → 房间抽屉。全程不依赖 LLM(不发回合,只走导航/绑定/静态渲染)。
import { test, expect, type Page } from '@playwright/test'

async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'ja')
  })
}

test('観測画面: 最初にワールド選択を表示する', async ({ page }) => {
  await welcomed(page)
  await page.goto('/local/observe')
  await expect(page.getByText('戻るワールドを選ぶ')).toBeVisible()
  // 套件内其他 spec 可能已造存档 —— 空态文案与存档卡二者必居其一。
  const empty = page.getByText('セーブデータはまだありません — 上からワールドを選んで始めましょう。')
  const card = page.locator('.obs-save-card').first()
  await expect(empty.or(card)).toBeVisible()
})

test('観測画面: チャンネル、レンズ、登場中からプレイとチャットへ移動できる', async ({
  page,
  request,
}) => {
  // 先经引擎 API 绑一个内置世界(scaffold 出一个可观察的存档;无 LLM)
  const bind = await request.post('/api/v1/play/session', {
    data: { slug: 'stoneford-elena' },
  })
  expect(bind.ok()).toBeTruthy()

  await welcomed(page)
  await page.goto('/local/observe')
  // 第一层:存档大卡出现
  await expect(page.getByText('戻るワールドを選ぶ')).toBeVisible()
  const card = page.locator('.obs-save-card').first()
  await expect(card).toBeVisible()
  await card.click()

  // 第二层:频道玻璃 —— 频道段 + 镜头段 + 右栏「在场」
  await expect(page.getByTestId('chan-world')).toBeVisible()
  await expect(page.getByTestId('chan-room')).toBeVisible()
  await expect(page.getByText('チャンネル · Channels')).toBeVisible()
  await expect(page.getByText('レンズ · Lenses')).toBeVisible()
  await expect(page.getByText('登場中 · Present')).toBeVisible()

  // ◉ 世界频道 = 内嵌完整游玩舞台(时钟走的那一档)
  await page.getByTestId('chan-world').click()
  await expect(page.getByTestId('chan-world-stage')).toBeVisible()
  await expect(page.locator('.obs-embed .lc-stage')).toBeVisible()

  // # 此地 = 房间群聊抽屉(幕间)
  await page.getByTestId('chan-room').click()
  await expect(page.getByTestId('room-drawer')).toBeVisible()

  // 回镜头(观察)
  await page.getByText('ワールドフィード').click()
  await expect(page.getByText('WORLD FEED')).toBeVisible()
})
