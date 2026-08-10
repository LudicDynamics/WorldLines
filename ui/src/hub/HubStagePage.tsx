// Hub 的游玩现场 = 共享 PlayStage × hosted 后端(HUB-GOLIVE P1.5,D5/D6 收官)。
// PlayStage 的样式面向 --lc-* token(LocalApp 注入);hub 壳没有这套变量,
// 这里包一层统一暗阶(docs/DESIGN-TOKENS.md 画布定稿值)。PlayStage 自身
// position:fixed 全屏,CSS 变量沿 DOM 祖先继承,fixed 不打断。
import { useLocation, useParams } from 'react-router-dom'
import { useMemo } from 'react'
import { PlayStage } from '../play/stage/PlayStage'
import { makeHostedBackend } from '../play/hosted/hostedBackend'
import { gatewayEndpoint } from '../play/playClient'

const LC_DARK: React.CSSProperties = {
  '--lc-text': '#F5F5F7',
  '--lc-panel': '#101014',
  '--lc-panel2': '#15151A',
  '--lc-line': '#26262C',
  '--lc-dim': '#A2A2AB',
  '--lc-faint': '#6C6C75',
  '--lc-candle': '#34E879',
  '--lc-candle-soft': '#34E87922',
  '--lc-live': '#06B6D4',
  '--lc-on-accent': '#06210F',
} as React.CSSProperties

export function HubStagePage() {
  const { sid = '' } = useParams()
  const loc = useLocation()
  const st = (loc.state ?? {}) as { opening?: string; worldName?: string }
  const backend = useMemo(
    () =>
      makeHostedBackend(sid, {
        base: `${gatewayEndpoint()}/api/v1/play`,
        token: () => {
          try {
            return localStorage.getItem('rp-hub:session')
          } catch {
            return null
          }
        },
        opening: st.opening || '',
        worldName: st.worldName || '',
      }),
    // sid 固定一次会话;state 只在导航时刻取一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sid],
  )
  if (!sid) return null
  return (
    <div style={LC_DARK}>
      <PlayStage backend={backend} />
    </div>
  )
}
