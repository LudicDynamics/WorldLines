// PlayStage 冒烟(D5+D7):bind 一个内置世界会话后进 /local/stage,游玩现场
// 的骨架必须渲染 —— transcript 主栏 + 底部输入条 + 右栏 agent lanes,全部
// 零 LLM(只走 /api/v1/play/session 绑定 + /events hello + 静态渲染)。
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh') // 断言全是中文文案 — 钉死语言
  })
}

// 绑定引擎的单会话到一个内置世界(scaffold 新 run,零 LLM)。返回世界 id。
async function bindBuiltin(request: APIRequestContext): Promise<string> {
  const wr = await request.get('/api/v1/local/worlds')
  expect(wr.ok()).toBe(true)
  const worlds = (await wr.json()) as { builtin?: { id: string }[] }
  const id = worlds.builtin?.[0]?.id
  expect(id, '至少一个内置世界').toBeTruthy()
  const br = await request.post('/api/v1/play/session', { data: { slug: id } })
  expect(br.ok()).toBe(true)
  return id!
}

test('游玩现场:bind 内置世界 → /local/stage 渲染骨架(无 LLM)', async ({ page, request }) => {
  await welcomed(page)
  await bindBuiltin(request)
  await page.goto('/local/stage')

  // 骨架三件套:主栏 transcript + 输入条 + 右栏 lanes —— 都不依赖回合生成
  await expect(page.getByTestId('stage-root')).toBeVisible()
  await expect(page.getByTestId('stage-transcript')).toBeVisible()
  await expect(page.getByTestId('stage-input')).toBeVisible()
  await expect(page.getByTestId('stage-lanes')).toBeVisible()

  // /events 的 hello 落地后,世界名出现在顶栏,右栏至少长出 world/player lane
  await expect(page.getByTestId('stage-world')).not.toBeEmpty({ timeout: 15_000 })
  await expect(page.locator('[data-lane]').first()).toBeVisible({ timeout: 15_000 })

  // 回书房链接在游玩现场顶栏(限定在 stage 内、按 href 命中,避开 LocalApp
   // 自身导航 + 语言差异 —— 引擎 locale 决定 ⌂书房/書斎/Study 文案)
  await expect(page.getByTestId('stage-root').locator('a.lc-link[href="/local"]')).toBeVisible()
})
