// StageBackend — 内核的后端接缝(一份代码两后端,PLAY-FUSION D3/D5)。
// 组件与 usePlayStage 只面向这个接口。HUB-GOLIVE §P2 根治后,local 与
// hosted 是**同一引擎协议的两个部署位**:local = 同源;hosted = 沙盒路由的
// /api/v1/play/engine 前缀直通每账户引擎 —— makeEngineBackend(base) 一个
// 工厂两处出装,caps 全开,内核零分叉。

import { createContext, useContext } from 'react'
import type { EngineEvent } from './events'
import { makeStageClient } from './stageClient'

export type StageBackendCaps = {
  /** 有回合 trace 面(REPLAY 条 / resume 播种)。 */
  traces: boolean
  /** 有回滚面(逐回合 ⟲)。 */
  rollback: boolean
}

export type StageBackend = {
  kind: 'local' | 'hosted'
  caps: StageBackendCaps
  postCmd(text: string): Promise<{ ok: boolean; busy: boolean; error?: string }>
  postStart(): Promise<void>
  /** 订阅引擎事件流;返回关闭函数。onDown 表示流已死且无会话可绑。 */
  openEvents(onEvent: (ev: EngineEvent) => void, onDown: () => void): () => void
  getTraces: ReturnType<typeof makeStageClient>['getTraces']
  getTrace: ReturnType<typeof makeStageClient>['getTrace']
  postRollback: ReturnType<typeof makeStageClient>['postRollback']
  imageUrl: ReturnType<typeof makeStageClient>['imageUrl']
  getI18n: ReturnType<typeof makeStageClient>['getI18n']
}

/** 引擎协议后端工厂:base='' 同源(local);base='/api/v1/play/engine'
 *  即沙盒路由直通(hosted)。行为与拆接缝前逐字节一致。 */
export function makeEngineBackend(base: string, kind: 'local' | 'hosted'): StageBackend {
  const c = makeStageClient(base)
  const B = base.replace(/\/$/, '')
  return {
    kind,
    caps: { traces: true, rollback: true },
    postCmd: c.postCmd,
    postStart: c.postStart,
    openEvents(onEvent, onDown) {
      // withCredentials:分层部署(hub 页面 → compute 域)时 SSE 携 play
      // cookie(🔴-3 鉴权通道);同源部署行为不变。
      const es = new EventSource(`${B}/events`, { withCredentials: true })
      let failures = 0
      es.onmessage = (e) => {
        failures = 0
        try {
          onEvent(JSON.parse(e.data) as EngineEvent)
        } catch {
          /* 坏帧跳过 */
        }
      }
      es.onerror = () => {
        // 409(未绑会话)会让浏览器彻底关闭流(CLOSED,不再重连)→ 空态;
        // CONNECTING 是正常断线重连,不误判。
        failures += 1
        if (es.readyState === EventSource.CLOSED && failures >= 1) onDown()
      }
      return () => es.close()
    },
    getTraces: c.getTraces,
    getTrace: c.getTrace,
    postRollback: c.postRollback,
    imageUrl: c.imageUrl,
    getI18n: c.getI18n,
  }
}

/** 同源引擎面(wheel/桌面/local 栈)。 */
export const localBackend: StageBackend = makeEngineBackend('', 'local')

const StageBackendContext = createContext<StageBackend>(localBackend)
export const StageBackendProvider = StageBackendContext.Provider

export function useStageBackend(): StageBackend {
  return useContext(StageBackendContext)
}
