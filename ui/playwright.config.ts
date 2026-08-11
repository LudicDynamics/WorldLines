// E2E(T2.5):对着「单进程产品形态」测 —— 引擎(隔离 HOME)serve
// vendored SPA,和用户双击拿到的东西同构。跑之前要 sync 过 spa
// (scripts/e2e.sh 会做)。
import { defineConfig } from '@playwright/test'

const PORT = process.env.E2E_PORT || '8799'
const BASE = `http://127.0.0.1:${PORT}`

// 起引擎的脚本住在引擎仓(专有,不在本仓)。引擎的 scripts/e2e.sh 会
// export NEONRP_E2E_SERVER 指到它自己的 e2e-server.sh —— 这条缝让引擎
// 去壳(删掉自带 ui/)之后仍能跨仓跑全套 Playwright。
// 没设时回退到旧的相对路径,即壳还住在引擎仓里时的布局。
const E2E_SERVER = process.env.NEONRP_E2E_SERVER
const SERVER_COMMAND = E2E_SERVER
  ? `bash ${E2E_SERVER}`
  : 'bash ../scripts/e2e-server.sh'

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
    command: SERVER_COMMAND,
    url: `${BASE}/api/v1/meta`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
