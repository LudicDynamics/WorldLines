// hosted 后端(HUB-GOLIVE §P2 根治后的形态):沙盒引擎跑完整 `neonrp web`
// 面,路由把 /api/v1/play/engine/<rest> 剥前缀直通 —— 本文件从 188 行的
// 协议翻译层收缩成**纯路径前缀出装**,traces/回滚/soul 事件/开机剧场全部
// 与 local 同源(内核零分叉,caps 全开)。
//
// 会话绑定仍是店面的事(HubPrePlay → POST /api/v1/play/session,引擎原生
// 绑定面);配额 429 由路由在 /engine/cmd 边界拦,经 StageClient.postCmd
// 的 error 通道上屏。
//
// P2 已知边界(HUB_AUTH_REQUIRED=1 时):EventSource 带不了 Authorization
// 头,fetch 面也未注入 Bearer —— 上真实鉴权时路由侧需换 cookie 或签名
// query(见 HUB-GOLIVE §P2 网关侧改动);本地栈(auth 关)不受影响。

import { makeEngineBackend, type StageBackend } from '../stage/backend'

export type HostedOpts = {
  /** play 网关基路径(默认同源,经 nginx)。 */
  base?: string
  /** 预留:Bearer 取用器(见上方 P2 边界注)。 */
  token?: () => string | null
  opening?: string
  worldName?: string
}

export function makeHostedBackend(_sid: string, opts: HostedOpts = {}): StageBackend {
  const gw = (opts.base ?? '/api/v1/play').replace(/\/$/, '')
  return makeEngineBackend(`${gw}/engine`, 'hosted')
}
