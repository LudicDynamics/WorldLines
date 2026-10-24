// E2E(T2.5):对着「单进程产品形态」测 —— 引擎(隔离 HOME)serve
// vendored SPA,和用户双击拿到的东西同构。跑之前要 sync 过 spa
// (scripts/e2e.sh 会做)。
import { defineConfig } from '@playwright/test'
import { cpSync, existsSync, rmSync } from 'node:fs'

// 私有层的界面测试(10-08 引擎开源 · 编排私有):worldlines/private/ui/e2e/ 有就同步到 e2e/private/ 一起跑
// (放在 node_modules 的下面才找得到 @playwright/test);e2e/private/ 已 gitignore、导出排除。没有私有层就只跑开源测试。
// WL_PRIVATE_UI=off 时不同步(测开源版界面)。
rmSync('./e2e/private', { recursive: true, force: true })
if (process.env.WL_PRIVATE_UI !== 'off' && existsSync('../private/ui/e2e')) cpSync('../private/ui/e2e', './e2e/private', { recursive: true })

const PORT = process.env.E2E_PORT || '8799'
const BASE = `http://127.0.0.1:${PORT}`

// 起引擎的脚本住在引擎目录(neonrp/scripts/)。引擎的 scripts/e2e.sh 会
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
    // 先发 TERM 让 e2e-server.sh 收尾(删临时 HOME),5 秒没退再强杀 —— 默认直接 SIGKILL,每跑一次漏一个临时 HOME
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
    timeout: 60_000,
  },
})
