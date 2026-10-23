// tests/test_player_replay.py 用:标准前端的回放播放器(worldlines/ui/player/src/replayer.js · player.html?replay=<id>),引擎接口用 page.route 假装。
//   node tests/player_replay.mjs <player.html> <doc.json> <playwright 所在的 package.json>
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, docFile, pkg] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const doc = JSON.parse(readFileSync(docFile, 'utf-8'))
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64')
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1280, height: 860 } })
const errs = [], files = []
p.on('pageerror', e => errs.push(e.message))
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host !== 'pl.test') return r.abort()
  if (u.pathname === '/api/v1/local/replays/r1') return json(r, { ...doc, id: 'r1', local: { id: 'r1', cover_url: null } })
  if (u.pathname === '/api/v1/local/replays/r1/file') { files.push(u.searchParams.get('path')); return r.fulfill({ contentType: 'image/png', body: PNG }) }
  if (u.pathname.startsWith('/api/v1/local/templates/')) return json(r, { slots: [] })
  if (u.pathname.startsWith('/api/') || u.pathname === '/events' || u.pathname === '/cmd') { errs.push('engine call ' + u.pathname); return json(r, {}, 404) }
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
const st = () => p.evaluate(() => ({ at: REPLAYER.at, n: REPLAYER.steps.length, paused: REPLAYER.paused, speed: REPLAYER.speed, lines: document.querySelectorAll('.log .p').length, you: [...document.querySelectorAll('.log .you')].map(x => x.textContent), end: !!document.querySelector('.end') }))
await p.goto('http://pl.test/player.html?replay=r1&lang=en')
await p.waitForSelector('.rpbar', { timeout: 60000 })
const out = { start: await st(), composer: await p.$eval('.bar', el => getComputedStyle(el).display) }
await p.click('[data-rp-play]')   // 暂停
const a0 = (await st()).at; await p.waitForTimeout(1500); out.pausedHeld = (await st()).at === a0 && (await st()).paused
await p.click('[data-rp-speed="16"]')
await p.click('[data-rp-play]')   // 接着放,16×
await p.waitForSelector('.end', { timeout: 60000 })
out.ended = await st()
out.endTitle = await p.textContent('.end h1')
out.endArt = await p.$eval('.end .art', el => el.style.backgroundImage)
out.barTop = await p.$eval('.rpbar', el => el.classList.contains('top'))
await p.evaluate(() => REPLAYER.setPaused(true))
await p.evaluate(() => REPLAYER.seek(2))
await p.waitForTimeout(300)
out.seek = await st()
out.files = [...new Set(files)].sort()
out.errs = errs
console.log(JSON.stringify(out))
await b.close()
