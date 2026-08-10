// 自适应显示缩放 — 字号 / 图标 / 间距随窗口尺寸自动伸缩。
//
// niko: 窗口变大变小就该自适应屏幕,不该让用户手动拉挡位。所以这里
// 没有任何控件 —— 一层 CSS `zoom` 作用在 <html>,zoom 值 = 视口尺寸的
// 函数,窗口 resize 时自动重算。
//
// 为什么是 zoom:整个 UI 用了 400+ 处写死的 px(text-[12px] 等,散在
// 43 个组件),zoom 是唯一能「一处等比伸缩全部字 / 图标 / 间距 / 容器
// 宽」的手段;它随视口走,所以是真·自适应,而不是固定缩放。超宽屏
// (含没开系统缩放的 4K)自动放大,治「字太小」并顺带把 max-w 容器
// 视觉撑宽、缓解「内容挤中间」;窄窗口自动收敛。
//
// zoom 后 getBoundingClientRect 与鼠标 clientX/Y 一致(Chromium /
// WebKit 皆然),地图 pan/zoom 等自算坐标的交互不受影响。
//
// 两入口(main-local / main-hub)`import './shared/uiScale'` 即生效。

// 设计基准:约 1280px 宽的视口 → zoom≈1(当前设计手感)。曲线参数
// (基准 / 上下限)是纯手感值,按实机拉窗口再调。
const BASE_W = 1280
const BASE_H = 760
const MIN = 0.85
const MAX = 1.6

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v))
}

/** 视口尺寸 → zoom。主看宽度;用高度设一个上限,避免矮宽窗口字过大。 */
function computeScale(): number {
  if (typeof window === 'undefined') return 1
  const byW = window.innerWidth / BASE_W
  const byH = window.innerHeight / BASE_H
  return clamp(Math.min(byW, byH * 1.15), MIN, MAX)
}

function apply(): void {
  if (typeof document === 'undefined') return
  const s = computeScale()
  // zoom:1 清空,避免留一个恒等 zoom 影响个别 fixed 元素的定位计算。
  document.documentElement.style.zoom = s === 1 ? '' : String(Number(s.toFixed(3)))
}

// resize 节流(rAF)—— 拖动窗口时不高频写 style,跟手不掉帧。
let raf = 0
function onResize(): void {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    apply()
  })
}

if (typeof window !== 'undefined') {
  apply()
  window.addEventListener('resize', onResize)
}
