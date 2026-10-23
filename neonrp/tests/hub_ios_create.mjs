// tests/test_hub_ios_create.py 用:iOS 那样打开的本地 Hub(window.HUB = {openZone:false, createSubmit, createArt, noPayLinks},
// 手机 390×844),引擎接口用 page.route 假装 —— 社区作品举报 / 屏蔽 / 取消屏蔽 · 创作台存 → 提交到默认区(引擎账号)· 生图走引擎代理 ·
// 额度不足不给外部充值链接 · 窄屏一列。
//   node tests/hub_ios_create.mjs <page.html> <api.json> <playwright 所在的 package.json> [截图目录]
import { createRequire } from 'module'
import { readFileSync } from 'fs'

const [html, apiFile, pkg, shots] = process.argv.slice(2)
const { chromium } = createRequire(pkg)('playwright')
const page0 = readFileSync(html, 'utf-8')
const api = JSON.parse(readFileSync(apiFile, 'utf-8'))
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
await ctx.addInitScript(() => { try { localStorage.setItem('wl.hub.lang', 'zh'); localStorage.setItem('wl.hub.intro', '1') } catch { /* no storage */ } })
const p = await ctx.newPage()
const errs = [], posts = [], gets = []
p.on('pageerror', e => errs.push(e.message))
p.on('dialog', d => d.accept())
await p.route('**/*', r => {
  const u = new URL(r.request().url())
  if (u.host !== 'hub.test') return r.abort()
  if (u.pathname.startsWith('/api/')) {
    const m = r.request().method()
    if (m === 'POST') {
      posts.push([u.pathname, JSON.parse(r.request().postData() || '{}')])
      const a = api['POST ' + u.pathname]
      return r.fulfill({ status: a ? a[0] : 404, contentType: 'application/json', body: JSON.stringify(a ? a[1] : {}) })
    }
    gets.push(u.pathname + u.search)
    return r.fulfill({ contentType: 'application/json', body: JSON.stringify(api[u.pathname] || {}) })
  }
  return r.fulfill({ contentType: 'text/html', body: page0 })
})
const shot = async n => { if (shots) await p.screenshot({ path: `${shots}/${n}.png`, fullPage: true }) }
const out = { errs, posts, gets }
const W = 'comm-fog-aaaaaa'
await p.goto('http://hub.test/#/')
await p.waitForSelector(`.wcard[href$="#/t/${W}"]`, { timeout: 15000 })
await shot('01-find')
// 社区作品:举报 → 「已举报」;屏蔽作者 → 发现页里没有它,「我的」里能看到、能取消
await p.goto(`http://hub.test/#/t/${W}`)
await p.waitForSelector('[data-report]')
out.detailCtas = await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim()))
await p.click('[data-report]')
await p.fill('#fzWhy', '盗用了别人的角色')
out.reportSheet = await p.textContent('.sheet')
await p.click('[data-report-go]')
await p.waitForSelector('.ctas .chip')
out.afterReport = await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim()))
await shot('02-reported')
await p.click('[data-block]')
await p.waitForTimeout(400)
out.afterBlockUrl = p.url()
out.findAfterBlock = await p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, ''))))
await p.goto('http://hub.test/#/me')
await p.waitForSelector('[data-ugc-blocked]')
out.meBlocked = await p.textContent('[data-ugc-blocked]')
await shot('03-me-blocked')
await p.click('[data-ugc-blocked] [data-unblock]')
await p.goto('http://hub.test/#/')
await p.waitForTimeout(300)
out.findAfterUnblock = await p.$$eval('.cards .wcard', a => a.map(x => decodeURIComponent(x.getAttribute('href').replace(/^.*\/t\//, ''))))
// 创作台:手机一列 · 存 → 提交到默认区(引擎账号,协议 + 联系方式)· 生图走引擎代理,额度不足没有外部充值链接
await p.goto('http://hub.test/#/t/stoneford-town/create')
await p.waitForSelector('[data-cf-card="zh.title"]')
out.cardFirst = await p.$eval('[data-cf-card="zh.title"]', el => el.value)
out.revealFirst = await p.$eval('[data-cf-reveal]', el => el.value)   // 第一次进:卡面带着模板的标题
out.rowDir = await p.$eval('.cfrow', el => getComputedStyle(el).flexDirection)
out.overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
await p.fill('[data-cf-card="zh.title"]', '雾夜猎人')
await p.fill('[data-cf-card="zh.pitch"]', '雾里有人在追脚印。')
await p.fill('[data-sec="soul"][data-name="name"]', '阿青')
await p.fill('[data-sec="soul"][data-name="persona"]', '沉默的猎人')
out.artBtn = !!(await p.$('[data-art-open]'))
if (out.artBtn) {
  await p.click('[data-art-open]')
  await p.waitForSelector('[data-art-go]')
  await p.click('[data-art-go]')
  await p.waitForSelector('[data-art-err]')
  out.artErr = await p.$eval('[data-art-err]', el => ({ text: el.textContent, links: el.querySelectorAll('a').length }))
  await shot('04-art-no-paylink')
  await p.click('[data-art-close]')
}
await p.click('[data-cf-save]')
await p.waitForSelector('[data-cf-submit]:not([disabled])')
await shot('05-saved')
await p.click('[data-cf-submit]')
await p.waitForSelector('[data-cf-submit-go]:not([disabled])')
out.submitSheet = await p.textContent('.sheet')
await shot('06-submit-sheet')
await p.click('[data-cf-submit-go]')
await p.waitForFunction(() => /已提交/.test((document.querySelector('.sheet') || {}).textContent || ''))
out.submitted = await p.textContent('.sheet')
await shot('07-submitted')
await p.click('.sheet a[href="#/me"]')   // 提交页的「去『我的作品』看状态」:关掉提交页
// 开局按钮(app 里不说「在浏览器里」)· 别人的社区作品(获取下来的)只能玩,不给「在这个模板上创作」,创作台也不开
await p.goto('http://hub.test/#/t/stoneford-town')
await p.waitForSelector('[data-start]')
out.officialCtas = await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim()))
await p.goto('http://hub.test/#/t/comm-fog-bbbbbb')
await p.waitForSelector('[data-start]')
out.gotCtas = await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim()))
await p.goto('http://hub.test/#/t/comm-fog-bbbbbb/create')
await p.waitForFunction(() => /没有开放|…/.test(document.body.textContent) && !/^…$/.test((document.querySelector('.glass.empty') || {}).textContent || '…'))
out.gotCreate = await p.textContent('main') || await p.textContent('body')
out.gotForm = !!(await p.$('[data-cf-card]'))
await p.goto('http://hub.test/#/t/pct-house')
await p.waitForSelector('[data-start]')
out.closedCtas = await p.$$eval('.ctas > *', a => a.map(x => x.textContent.trim()))
// 「我的」→「新的创作」/ 本机存了没提交的 → 创作台
await p.goto('http://hub.test/#/me')
await p.waitForSelector('.meworks .menew summary')
out.meNew = (await p.textContent('.meworks .menew summary')).trim()
await p.click('.meworks .menew summary')
out.meNewList = await p.$$eval('.meworks .menew [data-wk-new]', a => a.map(x => x.getAttribute('href')))
out.meDrafts = await p.$$eval('.meworks .medrafts [data-wk-new]', a => a.map(x => x.getAttribute('href')))
await shot('08-me-new')
await p.click('.meworks .menew [data-wk-new]')
await p.waitForSelector('[data-cf-card="zh.title"]')
out.fromMe = await p.$$eval('[data-cf-card="zh.title"]', a => a.length)
out.secondCard = await p.$eval('[data-cf-card="zh.title"]', el => el.value)
await p.fill('[data-sec="soul"][data-name="name"]', '阿白')
await p.fill('[data-sec="soul"][data-name="persona"]', '爱说话的向导')
await p.click('[data-cf-save]')
await p.waitForSelector('[data-cf-submit]:not([disabled])')
await p.goto('http://hub.test/#/t/stoneford-town/create')
await p.waitForSelector('[data-cf-card="zh.title"]')
out.firstAgain = await p.$eval('[data-cf-card="zh.title"]', el => el.value)
// 「角色」页 · 角色详情:名字跟界面语言走(界面语言用切换,页面加载时测试的 init 脚本会把它设回中文)
out.souls = {}
for (const lg of ['zh', 'en', 'ja', 'ko']) {
  await p.goto('http://hub.test/#/souls')
  await p.selectOption('#lang', lg)
  await p.waitForSelector('.cards.souls h3')
  const list = await p.$$eval('.cards.souls h3', a => a.map(x => x.textContent.trim()))
  await p.click('.cards.souls a')
  await p.waitForSelector('.hero .info h1')
  out.souls[lg] = [list, (await p.textContent('.hero .info h1')).trim()]
}
// 创作台卡面说明:「X 必须写」里的语言名用界面语言的叫法(韩文界面写「중국어」,不是「中文」)
out.cardHint = {}
for (const lg of ['en', 'ja', 'ko']) {
  await p.goto('http://hub.test/#/t/stoneford-town/create')
  await p.selectOption('#lang', lg)
  await p.waitForSelector('[data-cf-card="zh.title"]')
  out.cardHint[lg] = (await p.$$eval('.cfmsg.wide', a => a.map(x => x.textContent)))[0] || ''
}
await b.close()
console.log(JSON.stringify(out))
