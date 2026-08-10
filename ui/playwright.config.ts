// E2E(T2.5):对着「单进程产品形态」测 —— 引擎(隔离 HOME)serve
// vendored SPA,和用户双击拿到的东西同构。跑之前要 sync 过 spa
// (scripts/e2e.sh 会做)。
import { defineConfig } from '@playwright/test'

const PORT = process.env.E2E_PORT || '8799'
const BASE = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  // 套件变大后个别用例受首屏渲染时序影响偶发 —— 发布套件允许一次重试;
  // 稳定失败仍然红(重试也过不了)。
  retries: 1,
  expect: { timeout: 8_000 },
  workers: 1, // 单会话引擎(single-swap),串行跑
  use: {
    baseURL: BASE,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'bash ../scripts/e2e-server.sh',
    url: `${BASE}/api/v1/meta`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
