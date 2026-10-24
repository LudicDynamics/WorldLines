// NeonRP 产品图标(10-24 三体轨道新图):scripts/brand_icons.py 从 assets/brand/neonrp-icon-1024.png 出的一套,
// 在 assets/brand/web/。本地界面(app/build.mjs)和标准前端 / 小手机(player/build.mjs · chat/build.mjs)从这里拿 <head> 的几行、
// 把文件拷到站点根。Hub 线上构建(hub/build_static.py)走 scripts/brand_icons.py 的 head_links() —— 两边的几行保持一样。
// 开源导出里没有 assets/brand → 不放图标,页面照旧。
import { existsSync, cpSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const BRAND = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'assets', 'brand', 'web')
const FILES = ['favicon.ico', 'icon-32.png', 'apple-touch-icon.png', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'og.png', 'site.webmanifest']
export const hasBrand = () => existsSync(join(BRAND, 'favicon.ico'))

// prefix = 页面到站点根:'' · '../' · '/'
export const iconLinks = (prefix = '') => hasBrand() ? [
  `<link rel="icon" href="${prefix}favicon.ico" sizes="any">`,
  `<link rel="icon" type="image/png" sizes="32x32" href="${prefix}icon-32.png">`,
  `<link rel="apple-touch-icon" href="${prefix}apple-touch-icon.png">`,
  `<link rel="manifest" href="${prefix}site.webmanifest">`,
].join('\n') : ''

export function copyIcons (out) {
  if (!hasBrand()) return []
  for (const f of FILES) cpSync(join(BRAND, f), join(out, f))
  return FILES
}
