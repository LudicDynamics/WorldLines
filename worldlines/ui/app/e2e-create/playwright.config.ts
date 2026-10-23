// 创作台「用一句话说」e2e。服务由 run.sh 先起好(隔离 HOME 的本机引擎 + 假模型),这里只跑浏览器。
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts/,
  timeout: 1_200_000,
  expect: { timeout: 30_000 },
  workers: 1,
  fullyParallel: false,
  outputDir: '../../test-results/e2e-create',
  use: { trace: 'retain-on-failure', locale: 'zh-CN', actionTimeout: 30_000, viewport: { width: 1366, height: 900 } },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
