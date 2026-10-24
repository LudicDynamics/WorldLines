// 界面词典覆盖检查(10-25):把源码里每个 T('…') / TT('…') 的中文原文抽出来,en / ja / ko 三本词典缺一条就失败。
// 用法:node worldlines/ui/app/i18n-check.mjs   (--unused 顺带列出词典里没人用的词条)
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

const here = dirname(fileURLToPath(import.meta.url))
const LANGS = ['en', 'ja', 'ko']
const files = [
  ...readdirSync(join(here, 'src')).filter((f) => f.endsWith('.js')).map((f) => join('src', f)),
  ...readdirSync(join(here, 'real')).filter((f) => f.endsWith('.js') && !f.startsWith('i18n')).map((f) => join('real', f)),
  'src/index.html',
]

// 只认字面量参数:T('…') · T("…") · T(`…`)(反引号里不能有 ${});T(变量) 不算(那种要在定义处包)
const CALL = /(?<![\w$.])TT?\(\s*('(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\$])*`)/g
const keys = new Map()   // key → 第一次出现的位置
const add = (k, where) => { if (!keys.has(k)) keys.set(k, where) }
for (const f of files) {
  const src = readFileSync(join(here, f), 'utf-8')
  for (const m of src.matchAll(CALL)) add(new Function(`return ${m[1]}`)(), `${f}:${src.slice(0, m.index).split('\n').length}`)
  if (f.endsWith('.html')) {
    // 页面里写死的字:data-i18n(第一个文本节点)· data-i18n-small(<small>)· data-i18n-title / -placeholder · <title>
    for (const m of src.matchAll(/<(\w+)[^>]*\sdata-i18n(?:-small)?[^>]*>([^<]*)(?:<small>([^<]*)<\/small>)?/g)) {
      const tag = m[0]
      if (/\sdata-i18n[\s>=]/.test(tag) && m[2].trim()) add(m[2].trim(), f)
      if (/data-i18n-small/.test(tag) && m[3]) add(m[3], f)
    }
    for (const m of src.matchAll(/data-i18n-(title|placeholder)[^>]*\s\1="([^"]*)"|\s(title|placeholder)="([^"]*)"[^>]*data-i18n-\3/g)) add(m[2] || m[4], f)
    const t = src.match(/<title>([^<]*)<\/title>/); if (t) add(t[1], f)
  }
}
add('入口', 'real/i18n.js')   // CSS 角标,i18n.js 里用 T(JSON) 拼进 style

const ctx = { window: {} }
vm.createContext(ctx)
for (const l of LANGS) {
  const p = join(here, 'real', `i18n-${l}.js`)
  if (existsSync(p)) vm.runInContext(readFileSync(p, 'utf-8'), ctx, { filename: p })
}
const dict = ctx.window.WL_I18N || {}

let bad = 0
for (const l of LANGS) {
  const d = dict[l] || {}
  const miss = [...keys].filter(([k]) => typeof d[k] !== 'string' || (!d[k].trim() && k.trim()))
  // 占位符要对得上:{n} 在原文里有,译文里也得有
  const ph = (s) => (s.match(/\{\w+\}/g) || []).sort().join(',')
  const phBad = [...keys].filter(([k]) => typeof d[k] === 'string' && ph(k) !== ph(d[k]))
  if (miss.length || phBad.length) bad++
  console.log(`${l}: ${keys.size - miss.length}/${keys.size} keys${miss.length ? ` · missing ${miss.length}` : ''}${phBad.length ? ` · placeholder mismatch ${phBad.length}` : ''}`)
  for (const [k, w] of miss.slice(0, 40)) console.log(`  missing  ${JSON.stringify(k)}  (${w})`)
  for (const [k, w] of phBad.slice(0, 40)) console.log(`  placeholder  ${JSON.stringify(k)} → ${JSON.stringify(d[k])}  (${w})`)
  if (process.argv.includes('--unused')) for (const k of Object.keys(d)) if (!keys.has(k)) console.log(`  unused  ${JSON.stringify(k)}`)
}
if (bad) { console.error('i18n-check: FAIL'); process.exit(1) }
console.log(`i18n-check: OK · ${keys.size} keys × ${LANGS.length} languages`)
