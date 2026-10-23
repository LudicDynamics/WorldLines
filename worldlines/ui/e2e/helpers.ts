// e2e 的公共辅助(开源 · 私有层的测试 e2e/private/*.spec.ts 也用)
import { expect, type Page } from '@playwright/test'

export const SHOTS = process.env.WL_SHOTS || ''   // 设了就把游玩层截图存下来(人看)

export async function ready(page: Page) {
  await expect(page.locator('#ctx')).toContainText('真引擎', { timeout: 60_000 })
}

// 用一组回合记录顶替引擎的 /traces、/trace?i=(测渲染,不跑模型)
export async function useTraces(page: Page, traces: unknown[]) {
  await page.route(/\/traces(\?.*)?$/, r => r.fulfill({ json: { turns: traces.map((t, i) => ({ i, ts: '', turn_seq: (t as { turn_seq: number }).turn_seq, input: (t as { player: { input: string } }).player.input })) } }))
  await page.route(/\/trace\?i=\d+$/, r => r.fulfill({ json: traces[Number(new URL(r.request().url()).searchParams.get('i'))] }))
}
