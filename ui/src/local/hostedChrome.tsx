// hosted chrome 上下文(HUB-GOLIVE §P1.5,niko:Remote 没有 Local)。
// LocalShell 组件在 hub 入口下复用时,导航语义随环境切换 —— 组件零分叉,
// 只在 chrome(LocalApp 头部)按此 flag 换链接:字标回 hub 首页、目录
// 指店面、设置隐藏(沙盒 provider 由部署注入,不给用户改)。
import { createContext, useContext } from 'react'

export const HostedChromeContext = createContext(false)

export function useHostedChrome(): boolean {
  return useContext(HostedChromeContext)
}
