// WorldLines 1.0 的界面(10-05 定:UI/UX 固定为 docs/planning/prototypes/v3 这一版,旧 React LocalShell 与 Mock 3.0 舍弃)。
// 源:app/src(页面 · 样式 · 原型逻辑 · live.js 真引擎层)+ app/real(引擎适配层,源自 3.0)。
// 产物:dist-local/index.html(单页,脚本内联)+ dist-local/assets/wl/*(图)。引擎把 /local/* 指到 index.html、/assets/* 指到静态文件,
// 所以 worldlines 打开根路径就是这个界面;sync_play_ui.sh 照旧把 dist-local 拷进 wheel。
import { readFileSync, writeFileSync, rmSync, mkdirSync, cpSync, readdirSync, existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
// 产品图标(10-24):<head> 的几行 + 文件拷到 dist-local 根(引擎把顶层文件原样给);开源导出 / 只拷了部分源码时没有 → 不放
const { iconLinks, copyIcons } = await import('../brand.mjs').catch(() => ({ iconLinks: () => '', copyIcons: () => [] }))
const withIcons = (page) => { const l = iconLinks('/'); return l ? page.replace('</title>', `</title>\n${l}`) : page }

const here = dirname(fileURLToPath(import.meta.url))
const rd = (p) => readFileSync(join(here, p), 'utf-8')
const out = join(here, '..', 'dist-local')
const ASSET = '/assets/wl/'
const fixImg = (t) => t.replace(/(["'`(])img\//g, `$1${ASSET}`)

// 私有层的界面(10-08 引擎开源 · 编排私有):worldlines/private/ui/*.js 有就带上,排在 beats.js 之后、app.js 之前 ——
// 它们只往 BEATS / PRIVATE_UI 里登记(我们的两拍)。没有 = 开源版界面(单拍)。WL_PRIVATE_UI=off 强制构建开源版。
// private/ 来自 NeonRP-private(copy-to-worldlines.sh),已 gitignore、导出排除、导出时按内容哈希守门。
const PRIV_UI = join(here, '..', '..', 'private', 'ui')
const privUi = process.env.WL_PRIVATE_UI === 'off' || !existsSync(PRIV_UI) ? []
  : readdirSync(PRIV_UI).filter((f) => f.endsWith('.js')).sort().map((f) => `../../private/ui/${f}`)
const SRC = ['src/beats.js', ...privUi, 'src/app.js', 'src/map.js', 'src/builder.js', 'src/live.js', 'src/settings.js', 'src/publish.js', 'src/live2.js', 'src/orch.js', 'src/soulorch.js', 'src/plot.js', 'src/duo.js', 'src/fe.js', ...(existsSync(join(here, 'src', 'stdfe.js')) ? ['src/stdfe.js'] : []), 'src/frontends.js']   // stdfe.js = 嵌标准前端,不开源(导出里没有)· frontends.js = 前端台(10-17,真文件夹 / 真预览,排最后:接管 renderFe)

// 界面语言(10-25):词典(i18n-en / ja / ko)+ T() / WLANG,排在所有脚本最前;页面里的字都经 T() 取
const I18N = ['real/i18n-en.js', 'real/i18n-ja.js', 'real/i18n-ko.js', 'real/i18n.js']

// bench.js(测试台自动视图)和页面代码有同名函数:包一层,只把三个入口挂出来;它要的 U 先备好
// 私有层的演示数据(demo*.js:演示图 · 桩回复 · 演示回合)只在 ?demo=1 时生效(10-17 审计 2.x:以前正式界面里也在,
// 引擎读来的图上冒出「d20=15」像真回合);包一层 if,不改私有层文件。demo*.js 里没有顶层声明,包进块里不影响别的脚本
const DEMO_ONLY = (f) => f.startsWith('../') && /^demo[^/]*\.js$/.test(f.split('/').pop())
const src = (f) => DEMO_ONLY(f) ? `if (/[?&]demo(=|&|$)/.test(location.search)) {\n${rd(f)}\n}` : f === 'real/bench.js'
  ? `window.U = window.U || { ptab: 'play', bout: 'html', bround: null, bcls: null, bq: '' };\n(function () {\n${rd(f)}\nwindow.benchStrip = benchStrip; window.wireStrip = wireStrip; window.renderBench = renderBench;\n})();`
  : rd(f)
const js = [
  ...I18N, ...['real/ext.js', 'real/engine.js', 'real/link.js', 'real/bench.js'],
  ...SRC,
].map((f) => `<script>/* ${f.startsWith('../') ? 'private/ui/' + f.split('/').pop() : f} */\n${fixImg(src(f)).replace(/<\/script>/g, '<\\/script>')}\n</script>`).join('\n')

// 每个文件先单独过一遍语法:模板字符串嵌套错一个反引号,整页脚本都不跑,而界面只会停在「连接引擎……」(10-08 踩过)
for (const f of [...I18N, 'real/ext.js', 'real/engine.js', 'real/link.js', 'real/bench.js', ...SRC]) {
  try { new Function(src(f)) } catch (e) { throw new Error(`${f}: ${e.message}`) }
}

let html = fixImg(rd('src/index.html'))
if (!html.includes('<!--SCRIPTS-->')) throw new Error('index.html has no <!--SCRIPTS--> slot')
// 这次构建有哪几页(10-17 导航「小手机 / Hub」入口):chat.html 跟着标准前端出(下面),开源导出 / WL_PLAYER=off 没有
// Hub 不开源(10-15:导出白名单不带 ui/app/hub/):没有就不出 hub.html,顶栏也不放「Hub ↗」
const HAS_HUB = existsSync(join(here, 'hub', 'hub.js'))
const pages = { hub: HAS_HUB, chat: process.env.WL_PLAYER !== 'off' && existsSync(join(here, '..', 'player', 'build.mjs')) }
html = html.replace('<!--SCRIPTS-->', () => `<script>window.WL_PAGES = ${JSON.stringify(pages)}</script>\n` + js)

rmSync(out, { recursive: true, force: true })
mkdirSync(join(out, 'assets', 'wl'), { recursive: true })
writeFileSync(join(out, 'index.html'), withIcons(html))
copyIcons(out)
cpSync(join(here, 'src', 'img'), join(out, 'assets', 'wl'), { recursive: true })
// Hub 新版(10-11 · docs/planning/HUB-V3-PLAN-1011.md):单页 hub.html,引擎把顶层文件原样服务(/hub.html)
if (HAS_HUB) {
  // 几段脚本拼成一个 <script>:每段之间补 `;`,前一段结尾的 `})()` 没分号时下一段 `(() => {` 不会被当成函数调用(10-18 打挂过本地 Hub)
  const glue = (...xs) => xs.join(';\n')
  const hubJs = glue(rd('hub/create_assist.js'), rd('hub/hub.js'))   // 创作台「用一句话说」(10-18)在 hub.js 前面
  try { new Function(hubJs) } catch (e) { throw new Error(`hub/hub.js: ${e.message}`) }
  const tqJs = rd('hub/truthquiz.js')   // 创作台「真相三问」(10-18,truth-quiz)在 hub.js 前面
  try { new Function(tqJs) } catch (e) { throw new Error(`hub/truthquiz.js: ${e.message}`) }
  const rpJs = rd('hub/runpoints.js')   // 「我的」· 对局积分(10-21,truth-quiz)
  try { new Function(rpJs) } catch (e) { throw new Error(`hub/runpoints.js: ${e.message}`) }
  const caJs = rd('hub/create-art.js')   // 创作台 AI 生图(10-18,create-art):本地 / iOS 经引擎代理 /api/v1/local/ai(web-create 10-21)
  try { new Function(caJs) } catch (e) { throw new Error(`hub/create-art.js: ${e.message}`) }
  const ovJs = rd('hub/orchview.js')   // 创作台「编排系统」只读执行图(10-18,orch-preview)在 hub.js 前面
  try { new Function(ovJs) } catch (e) { throw new Error(`hub/orchview.js: ${e.message}`) }
  // 没图时的剪影(标准前端的 assets/fallback/,和 player.html 同一份;开源导出没有 ui/player → 不带,hub.js 照旧空玻璃砖)
  const fbJs = existsSync(join(here, '..', 'player', 'assets', 'fallback', 'inline.mjs'))
    ? `<script>\n${(await import('../player/assets/fallback/inline.mjs')).fbartJs().replace(/<\/script>/g, '<\\/script>')}\n</script>\n` : ''
  writeFileSync(join(out, 'hub.html'), withIcons(rd('hub/index.html')).replace('<!--SCRIPT-->', () => `${fbJs}<script>\n${glue(caJs, ovJs, tqJs, rpJs, hubJs).replace(/<\/script>/g, '<\\/script>')}\n</script>`))
}
console.log('app built', join(out, 'index.html'), Math.round(html.length / 1024), 'KB ·', readdirSync(join(out, 'assets', 'wl')).length, 'images ·', privUi.length ? `private ui: ${privUi.map((f) => f.split('/').pop()).join(', ')}` : 'public ui (no private layer)')
// 标准前端(Hub / iOS 的重前端,worldlines/ui/player,不开源;10-15):有就调它自己的 build.mjs 出 dist-local/player.html,
// 测试台右栏的「标准前端」页签和前端台「网页 TS」的试玩打开的就是它(src/stdfe.js)。开源导出没有 ui/player → 跳过;WL_PLAYER=off 也跳过
{
  const player = join(here, '..', 'player', 'build.mjs')
  if (process.env.WL_PLAYER !== 'off' && existsSync(player)) execFileSync(process.execPath, [player, '--out', out], { stdio: 'inherit' })
}
