// 回合过程轨 + 立绘自适应 + soul 位置解析回归。
// mock 流按 niko 真实存档校准(orchestration/main.jsonl 的 bus 顺序 +
// web.py 的 SSE 转发面):真 iid 形如 si-elena0001;statuses 渐进演化;
// **世界铺垫 chunk 在 souls 完成前就会到达**(全亮缺陷的根因,钉死);
// rowan 的位置是展示文本「T004·碧石镇·旅店」(误归幕后缺陷的根因,钉死)。
import { test, expect, type Page } from '@playwright/test'

const TALL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAAECAIAAAArjXluAAAAEElEQVR4nGMweVEJRAzYKACvJAypbKYroAAAAABJRU5ErkJggg==',
  'base64',
)
const WIDE_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAQAAAACCAIAAADwyuo0AAAAEElEQVR4nGMweVEJRwzIHACiegypOVYVdwAAAABJRU5ErkJggg==',
  'base64',
)

const sse = (events: object[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')

// 真实形状:iid = si-<sid>0001;玩家位置常是 bare 节点(gate_north);
// elena canonical、rowan 展示文本 —— 三种真实格式并存。
const HELLO = {
  kind: 'hello',
  world: 'stone-ford',
  world_name: '石津镇',
  agent_id: 'world-agent',
  player_name: '旅人',
  player_location: 'gate_north',
  souls: [
    { instance_id: 'si-elena0001', name: '艾琳娜', role: 'heroine', where: '北门', location: 'T001/gate_north' },
    { instance_id: 'si-rowan0001', name: '罗文', role: 'npc', where: '旅店', location: 'T004·碧石镇·旅店' },
  ],
}

async function welcomed(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('wl-local-welcomed', '1')
    localStorage.setItem('wl-local-lang', 'zh')
  })
}

// resume 路径(避开开机剧场):最后一回合 turn_seq=47 → 本回合 TURN 48。
async function mockBase(page: Page) {
  await page.route('**/traces', (r) => r.fulfill({ json: { turns: [{ i: 0, turn_seq: 47 }] } }))
  await page.route('**/trace?*', (r) => r.fulfill({ json: { turn_seq: 47, bus_messages: [] } }))
  await page.route('**/image?*', (r) => {
    const url = new URL(r.request().url())
    const tall = (url.searchParams.get('id') || '').startsWith('si-elena')
    r.fulfill({ contentType: 'image/png', body: tall ? TALL_PNG : WIDE_PNG })
  })
}

const statuses = (e: string, r: string) => ({
  kind: 'soul_status',
  statuses: {
    'si-elena0001': { name: '艾琳娜', state: e },
    'si-rowan0001': { name: '罗文', state: r },
  },
})

test('过程轨:渐进点亮 — 铺垫 chunk 先到不许点亮成稿;在场判定容忍展示文本', async ({ page }) => {
  await welcomed(page)
  await mockBase(page)
  let first = true
  await page.route('**/events', (r) => {
    const body = first
      ? sse([
          HELLO,
          { kind: 'turn_start', text: '把灯接过来' },
          { kind: 'chunk', text: '雾气先漫过门槛——' }, // 真实流:铺垫先到!
          statuses('queued', 'queued'),
          statuses('completed', 'running'),
          {
            kind: 'soul_psyche',
            instance_id: 'si-rowan0001',
            inner_voice: '塌方的事要不要现在说',
            state: 'running',
          },
        ])
      : sse([HELLO])
    first = false
    r.fulfill({ status: 200, contentType: 'text/event-stream', body })
  })
  await page.goto('/local/stage')

  const rail = page.getByTestId('stage-rail')
  await expect(rail).toBeVisible({ timeout: 10_000 })
  // forward-only:铺垫 chunk 已到,但 souls 1/2 → 成稿必须仍是待办,
  // 角色行动是 active(自相矛盾的「✓ 0/2」在结构上不可能)
  await expect(rail.locator('[data-stage="souls"]')).toHaveAttribute('data-st', 'active')
  await expect(rail.locator('[data-stage="narrate"]')).toHaveAttribute('data-st', 'wait')
  await expect(rail).toContainText('1/2')
  // TURN 号:seed 47 → 48
  await expect(page.getByTestId('rail-title')).toContainText('TURN 48')
  // 在场判定:rowan 位置是展示文本(不可比)→ 默认在场,两枚芯片,无幕后
  await expect(rail.getByTestId('rail-chip').filter({ hasText: '艾琳娜' })).toBeVisible()
  await expect(rail.getByTestId('rail-chip').filter({ hasText: '罗文' })).toBeVisible()
  await expect(rail.getByTestId('rail-backstage')).toHaveCount(0)
  // 思考尾巴 = 活跃 soul 的 inner_voice;active 点在呼吸
  await expect(page.getByTestId('rail-tease')).toContainText('塌方的事')
  await expect(rail.locator('.lc-rail-dot.active').first()).toBeVisible()
  await expect(page.getByTestId('stage-root')).not.toContainText('(unknown)')
})

test('过程轨:全序列走完 → 收起成一行 TURN 摘要(原位)', async ({ page }) => {
  await welcomed(page)
  await mockBase(page)
  let first = true
  await page.route('**/events', (r) => {
    const body = first
      ? sse([
          HELLO,
          { kind: 'turn_start', text: '把灯接过来' },
          { kind: 'chunk', text: '雾气先漫过门槛——' },
          statuses('queued', 'queued'),
          statuses('running', 'queued'),
          statuses('completed', 'running'),
          statuses('completed', 'completed'), // → 裁定窗口
          { kind: 'chunk', text: '雾从河面爬上石阶。' }, // idx≥2 后才点亮成稿
          {
            kind: 'trace',
            trace: {
              turn_seq: 48,
              land: { commit_id: 'abcd1234' },
              souls: [],
              bus_messages: [
                {
                  topic: 'world/state',
                  payload: { turn_seq: 48, world_location: 'T001/gate_north', commit_id: 'abcd1234' },
                },
              ],
            },
          },
          { kind: 'turn_done', success: true },
        ])
      : sse([HELLO])
    first = false
    r.fulfill({ status: 200, contentType: 'text/event-stream', body })
  })
  await page.goto('/local/stage')

  const summary = page.getByTestId('stage-rail-summary')
  await expect(summary).toBeVisible({ timeout: 10_000 })
  await expect(summary).toContainText('TURN 48')
  await expect(summary).toContainText('2 souls')
  await expect(page.getByTestId('stage-rail')).toHaveCount(0)
  await expect(page.getByTestId('stage-feed')).toContainText('雾从河面爬上石阶')
})

test('过程轨:/traces 迟到于 turn_start — 种子回填 TURN 号(CI 竞态回归)', async ({ page }) => {
  await welcomed(page)
  // 与 mockBase 相同,但 /traces 延迟 1.5s 返回 — 流(含 turn_start)先跑。
  await page.route('**/traces', async (r) => {
    await new Promise((res) => setTimeout(res, 1500))
    r.fulfill({ json: { turns: [{ i: 0, turn_seq: 47 }] } })
  })
  await page.route('**/trace?*', (r) => r.fulfill({ json: { turn_seq: 47, bus_messages: [] } }))
  await page.route('**/image?*', (r) => r.fulfill({ contentType: 'image/png', body: WIDE_PNG }))
  let first = true
  await page.route('**/events', (r) => {
    const body = first
      ? sse([HELLO, { kind: 'turn_start', text: '把灯接过来' }, statuses('completed', 'running')])
      : sse([HELLO])
    first = false
    r.fulfill({ status: 200, contentType: 'text/event-stream', body })
  })
  await page.goto('/local/stage')

  // 轨先以无号标题出现(不许出现 '?'),种子落地后回填出 TURN 48。
  const title = page.getByTestId('rail-title')
  await expect(title).toBeVisible({ timeout: 10_000 })
  await expect(title).not.toContainText('?')
  await expect(title).toContainText('TURN 48', { timeout: 10_000 })
})

test('立绘自适应:竖图走英雄块(带位置角标),横图走 banner', async ({ page }) => {
  await welcomed(page)
  await mockBase(page)
  await page.route('**/events', (r) =>
    r.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([HELLO]) }),
  )
  await page.goto('/local/stage')

  await expect(page.getByTestId('portrait-tall').first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId('portrait-tall').first()).toContainText('北门')
  await expect(page.getByTestId('portrait-banner').first()).toBeVisible()
})
