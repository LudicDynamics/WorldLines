// M31 · 大地图(WorldMap)—— Observatory `map` 镜头的 xyflow 世界图。
// 地点为节点、souls 落位其上、玩家高亮、点节点看该地点详情。
// 数据来自当前 trace 的 souls(reason 里解析地点),不需新 API;纯只读、不改引擎。
// 后置:接 world_map 底图(locations connections=edges)、挂 CG、点节点出图。
import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

export type SoulAct = { sid?: string; instance_id?: string; reason?: string }

// 与 ObservatoryShell 同款:从 soul.reason 解析所在地点。
function soulLoc(reason?: string): string {
  const m = (reason || '').match(/at '([^']+)'|group '([^']+)'/)
  const raw = m?.[1] || m?.[2] || ''
  return raw.split('/').pop() || raw
}

function LocNode({ loc, here, isPlayer }: { loc: string; here: SoulAct[]; isPlayer: boolean }) {
  return (
    <div style={{ textAlign: 'center', minWidth: 72 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: isPlayer ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-text, #e7e2d6)' }}>
        {loc}{isPlayer ? ' · 你' : ''}
      </div>
      {here.length ? (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'center', flexWrap: 'wrap', marginTop: 6 }}>
          {here.map((s) => (
            <span
              key={s.instance_id || s.sid}
              title={s.sid}
              style={{ width: 22, height: 22, borderRadius: '50%', background: '#ec489922', color: '#ec4899', display: 'grid', placeItems: 'center', fontSize: 10, fontWeight: 700 }}
            >
              {(s.sid || '?').slice(0, 1).toUpperCase()}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function WorldMapCanvas({ souls, playerLoc }: { souls: SoulAct[]; playerLoc: string }) {
  const [selected, setSelected] = useState<string | null>(null)

  const { nodes, byLoc } = useMemo(() => {
    const byLoc: Record<string, SoulAct[]> = {}
    for (const s of souls) {
      const loc = soulLoc(s.reason) || '未知'
      ;(byLoc[loc] ||= []).push(s)
    }
    const locs = Object.keys(byLoc)
    if (playerLoc && !locs.includes(playerLoc)) locs.unshift(playerLoc)
    const R = locs.length > 1 ? 190 : 0
    const nodes: Node[] = locs.map((loc, i) => {
      const ang = (i / Math.max(locs.length, 1)) * Math.PI * 2 - Math.PI / 2
      const here = byLoc[loc] || []
      const isPlayer = loc === playerLoc
      return {
        id: loc,
        position: { x: 260 + Math.cos(ang) * R, y: 190 + Math.sin(ang) * R },
        data: { label: <LocNode loc={loc} here={here} isPlayer={isPlayer} /> },
        style: {
          border: `2px solid ${isPlayer ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-line, #2a2f38)'}`,
          borderRadius: 12,
          background: 'var(--lc-panel, #14171d)',
          padding: 8,
          width: 'auto',
          boxShadow: isPlayer ? '0 0 14px var(--lc-candle, #e8b45a)' : 'none',
        },
      }
    })
    return { nodes, byLoc }
  }, [souls, playerLoc])

  const here = selected ? byLoc[selected] || [] : []

  return (
    <div style={{ position: 'relative', height: 360, marginTop: 16, borderRadius: 14, border: '1px solid var(--lc-line)', overflow: 'hidden', background: 'radial-gradient(circle at 42% 40%, #16191f, #0e1014)' }}>
      <ReactFlow
        nodes={nodes}
        edges={[]}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, n) => setSelected(n.id)}
        onPaneClick={() => setSelected(null)}
      >
        <Background color="#2a2f38" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
      {selected ? (
        <div style={{ position: 'absolute', right: 10, top: 10, width: 200, maxHeight: 320, overflow: 'auto', padding: 12, borderRadius: 12, border: '1px solid var(--lc-line)', background: 'var(--lc-panel, #14171d)', boxShadow: '0 6px 24px #0008' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--lc-candle, #e8b45a)', marginBottom: 8 }}>{selected}</div>
          {here.length ? here.map((s) => (
            <div key={s.instance_id || s.sid} style={{ fontSize: 11, color: 'var(--lc-dim, #9aa0aa)', lineHeight: 1.6, marginBottom: 6 }}>
              <span style={{ color: 'var(--lc-text, #e7e2d6)', fontWeight: 600 }}>{s.sid}</span>
              {s.reason ? <div style={{ color: 'var(--lc-faint, #6b7280)' }}>{s.reason}</div> : null}
            </div>
          )) : <div style={{ fontSize: 11, color: 'var(--lc-faint)' }}>此地暂无角色。</div>}
        </div>
      ) : null}
    </div>
  )
}
