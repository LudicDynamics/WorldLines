// 「在浏览器里玩」的 e2e(10-14):对着 build_static.py 的产物(和上 S3 的同一个目录)+ 假 ai / auth / billing(serve.py)。
// 不连真模型、不花额度。跑法:bash worldlines/ui/e2e-play/run.sh(先构建,再 Chromium + WebKit 各跑一遍)。
import { defineConfig } from '@playwright/test'

const SITE = process.env.WL_PLAY_SITE
if (!SITE) throw new Error('WL_PLAY_SITE: the build_static.py output to serve (run.sh sets it)')
// 端口:默认 8610 / 8611(play.spec 写死了 8611);只跑 chat.spec 时可以换开(WL_PLAY_PORT / WL_PLAY_AI_PORT,构建时 --ai 要指到同一个)
const PORT = process.env.WL_PLAY_PORT || '8610', AI_PORT = process.env.WL_PLAY_AI_PORT || '8611'

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts/,
  timeout: 420_000,              // 首开要从 CDN 拉 Pyodide(约 11 MB)+ 引擎 + 世界
  expect: { timeout: 30_000 },
  workers: 1,                    // 一个假 ai,记的是全部调用:串行
  fullyParallel: false,
  outputDir: '../test-results/e2e-play',
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: 'retain-on-failure', viewport: { width: 1360, height: 860 }, locale: 'zh-CN' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  webServer: {
    command: `python3 serve.py --site "${SITE}" --port ${PORT} --ai-port ${AI_PORT}`,
    url: `http://127.0.0.1:${PORT}/play/manifest.json`,
    reuseExistingServer: false,
    stdout: 'pipe',
  },
})
