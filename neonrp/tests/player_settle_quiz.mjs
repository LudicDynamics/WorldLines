// tests/test_player_settle_quiz.py 用:标准前端结算屏「真相三问」(settle.js)—— 发额度,不再选人带走(10-20 / 10-21)。
//   node tests/player_settle_quiz.mjs <player/src> <playwright 所在的 package.json> <截图目录>
// 页面只装 i18n.js + settle.js,FX / API / WORLD / TOUCH / APP 是桩;引擎回包按三种情形给(真形状 = core/truth_quiz)。
import { createRequire } from 'module'
import { readFileSync, mkdirSync } from 'fs'
import { join } from 'path'

const [src, pkg, shots] = process.argv.slice(2)
mkdirSync(shots, { recursive: true })
const { chromium } = createRequire(pkg)('playwright')
const js = f => readFileSync(join(src, f), 'utf-8')
const stubs = `
const FX = { h: s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]), watch() {}, toast(s) { window.__toast = s }, async collect(c) { (window.__collected ||= []).push(c.name) }, face: () => '' };
const TOUCH = { haptic() {} }; const APP = { state: () => ({}) };
const WORLD = { hue: () => 0, portraitOf: () => '', fbOf: () => '', W: { slots: {}, cover: '' }, slotUrl: () => '', sceneOf: () => null };
const API = { soft: async () => window.__Q, post: async (p, b) => { window.__posted = b; return window.__R } };`
const html = `<!doctype html><html><head><meta charset="utf-8"><style>${js('player.css')}</style></head><body style="margin:0;min-height:100vh"><div class="fx" style="position:fixed"></div>
<script>${stubs}</script><script>${js('i18n.js')}</script><script>${js('settle.js')}</script></body></html>`
const QS = [{ id: 0, q: '谁把钥匙藏进了井里?', options: ['莲妹', '族长', '没人'] }, { id: 1, q: '钥匙开哪扇门?', options: ['祠堂', '仓房'] }, { id: 2, q: '他为什么藏?', options: ['怕人看见族谱', '忘了', '开玩笑'] }]
const PTS = { settle: 200, per_right: 100, fallback: 0 }
const CASES = {
  wrong: { Q: { state: 'open', questions: QS, reward_soul: { iid: 'si-x', sid: 'xiulian', name: '莲妹' }, points: PTS },
           R: { score: 1, total: 3, all_right: false, right: [true, false, false], answer: [1, 0, 0], gained: [], delivered: false, fallback: true, no_questions: false, achievements: [],
                rewards: [{ id: 'a', kind: 'points', amount: 300, status: 'pending', source: 'settlement:quiz' }], platform: 'own_key' }, answers: [1, 1, 1] },
  home: { Q: { state: 'open', questions: QS, reward_soul: { iid: 'si-x', sid: 'xiulian', name: '莲妹' }, points: PTS },
          R: { score: 3, total: 3, all_right: true, right: [true, true, true], answer: [1, 0, 0], gained: [], delivered: false, fallback: true, no_questions: false, achievements: [],
               rewards: [{ id: 'a', kind: 'points', amount: 500, status: 'pending', source: 'settlement:quiz' }] }, answers: [1, 0, 0] },
  noq: { Q: { state: 'unavailable', questions: [], reward_soul: null, points: PTS },
         R: { score: 0, total: 0, all_right: false, right: [], answer: [], gained: [], delivered: false, fallback: true, no_questions: true, achievements: [],
              rewards: [{ id: 'a', kind: 'points', amount: 200, status: 'pending', source: 'settlement:quiz' }], platform: 'reported' }, answers: [] },
}
const b = await chromium.launch()
const out = {}
for (const [name, c] of Object.entries(CASES)) {
  const ctx = await b.newContext({ viewport: { width: 430, height: 900 }, locale: 'zh-CN' })
  await ctx.addInitScript(() => { try { localStorage.setItem('wl.lang', 'zh') } catch { /* */ } })
  const p = await ctx.newPage(), errs = []
  p.on('pageerror', e => errs.push(e.message))
  await p.setContent(html)
  await p.evaluate(([Q, R]) => { I18N.set('zh'); window.__Q = Q; window.__R = R }, [c.Q, c.R])
  const done = p.evaluate(() => SETTLE.quiz())
  await p.waitForSelector('.veil.quiz [data-go]')
  const ask = { hint: (await p.textContent('.veil.quiz .qz-hint')).trim(), take: await p.locator('[data-take], .qz-people').count(), go: (await p.textContent('[data-go]')).trim() }
  for (const [i, k] of c.answers.entries()) await p.click(`.qz-q[data-q="${i}"] .qz-o[data-o="${k}"]`)
  await p.waitForTimeout(450)
  await p.screenshot({ path: join(shots, `${name}-1-ask.png`) })
  await p.click('[data-go]')
  await p.waitForSelector('.veil.quiz.res')
  const res = { text: (await p.textContent('.veil.quiz.res')).replace(/\s+/g, ' ').trim() }
  await p.waitForTimeout(450)
  await p.screenshot({ path: join(shots, `${name}-2-result.png`) })
  await p.click('.veil.quiz.res [data-x]')
  await done
  out[name] = { ask, res, posted: await p.evaluate(() => window.__posted), collected: await p.evaluate(() => window.__collected || []), errs }
  await ctx.close()
}
await b.close()
console.log(JSON.stringify(out))
