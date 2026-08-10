// WorldLines 桌面壳(Electron 候选)— docs/WEBUI-UNIFICATION.md §7.5 LP2/LP3。
//
// 薄壳三件事,不含任何产品逻辑(SoT = neonrp web + 本仓 ui/ 的 LocalShell):
//   1. 起引擎:装机走已安装的 neonrp;开发机走 uv run neonrp(见下)
//   2. 等就绪:轮询 /api/v1/meta 到 200
//   3. 开窗口:指向 http://127.0.0.1:8791/local;退出时杀引擎
const { app, BrowserWindow } = require('electron')
const { spawn } = require('node:child_process')
const http = require('node:http')
const path = require('node:path')
const fs = require('node:fs')

const PORT = 8791
const URL_LOCAL = `http://127.0.0.1:${PORT}/local`

let engine = null

// GUI 进程的 PATH 不含 homebrew/.local(双击启动时)— 显式找 uv
function findUv() {
  const cands = [
    path.join(process.env.HOME || '', '.local/bin/uv'),
    '/opt/homebrew/bin/uv',
    '/usr/local/bin/uv',
  ]
  for (const c of cands) if (fs.existsSync(c)) return c
  return 'uv'
}

// 装机形态:找用户已安装的 neonrp(install.sh/ps1 的落点)。GUI 双击启动时
// PATH 极简,按固定落点显式探测,最后才信 PATH。
function findInstalledEngine() {
  const home = process.env.HOME || process.env.USERPROFILE || ''
  const cands = [
    path.join(home, '.local/share/uv/tools/worldlines/bin/neonrp'),
    path.join(home, '.local/bin/neonrp'),
    '/opt/homebrew/bin/neonrp',
    '/usr/local/bin/neonrp',
  ]
  for (const c of cands) if (fs.existsSync(c)) return c
  return null
}

// 引擎源码不在本仓 —— WorldLines 是开源壳,NeonRP 引擎专有、单独分发。
// 开发机跑本地引擎签出要显式指路:WORLDLINES_ENGINE_REPO=/path/to/NeonRP。
// 拆仓前这里是 __dirname/../..(= 引擎仓根),现在那个路径指向壳仓自己。
function engineRepo() {
  const root = process.env.WORLDLINES_ENGINE_REPO
  if (root && fs.existsSync(path.join(root, 'pyproject.toml'))) return root
  return null
}

const ENGINE_ARGS = ['web', '--port', String(PORT), '--parent-pid', String(process.pid), '--no-browser']

function startEngine() {
  const repo = engineRepo()
  const installed = repo ? null : findInstalledEngine()
  if (!repo && !installed) {
    // Tauri 壳有 splash 内引导安装(S1);Electron 候选保持薄,只报错。
    console.error('engine not found: install WorldLines, or set WORLDLINES_ENGINE_REPO')
    return
  }
  engine = repo
    ? spawn(findUv(), ['run', 'neonrp', ...ENGINE_ARGS], { cwd: repo, stdio: 'ignore', detached: false })
    : spawn(installed, ENGINE_ARGS, { stdio: 'ignore', detached: false })
  engine.on('exit', (code) => {
    engine = null
    if (code && !app.isQuiting) console.error(`engine exited: ${code}`)
  })
}

function waitReady(timeoutMs = 30000) {
  const t0 = Date.now()
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(`http://127.0.0.1:${PORT}/api/v1/meta`, (res) => {
          res.resume()
          if (res.statusCode === 200) return resolve()
          retry()
        })
        .on('error', retry)
    }
    const retry = () => {
      if (Date.now() - t0 > timeoutMs) return reject(new Error('engine not ready in 30s'))
      setTimeout(tick, 250)
    }
    tick()
  })
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'WorldLines',
    backgroundColor: '#0A0A0A',
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  })
  win.loadFile(path.join(__dirname, 'splash.html'))
  try {
    await waitReady()
    win.loadURL(URL_LOCAL)
  } catch (e) {
    win.loadFile(path.join(__dirname, 'splash.html'), { query: { error: String(e) } })
  }
}

app.whenReady().then(() => {
  startEngine()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  app.isQuiting = true
  app.quit()
})

app.on('will-quit', () => {
  if (engine) {
    try {
      engine.kill('SIGTERM')
    } catch {
      /* already gone */
    }
  }
})
