// M31 · 大地图(WorldMap)—— Observatory `map` 镜头的 xyflow 无限画布。
// P2b:地点为「锚点节点」,每个 soul 是**自己的节点**,落在所在地点周围;
// 世界推进(souls prop 变)时 soul 节点换到新地点 → CSS transition 平滑滑行
// (角色在画布上"活着"地移动)。玩家所在地点高亮。点 soul/地点看详情。
// 数据来自当前 trace 的 souls(reason 解析地点),纯只读、不改引擎。
// 后置:接 world_map 底图(locations connections=edges)、挂 CG、点节点出图。
import { useMemo, useState } from 'react'
import { ReactFlow, Background, Controls, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

export type SoulAct = { sid?: string; instance_id?: string; reason?: string }

function soulLoc(reason?: string): string {
  const m = (reason || '').match(/at '([^']+)'|group '([^']+)'/)
  const raw = m?.[1] || m?.[2] || ''
  return raw.split('/').pop() || raw
}

// 稳定颜色:同一 sid 永远同色,画布上认得出谁。
function hueOf(key: string): number {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) % 360
  return h
}

const CENTER = { x: 320, y: 240 }

export function WorldMapCanvas({
  souls,
  playerLoc,
  names = {},
}: {
  souls: SoulAct[]
  playerLoc: string
  names?: Record<string, string>
}) {
  const [selPlace, setSelPlace] = useState<string | null>(null)

  const { nodes, byLoc } = useMemo(() => {
    const byLoc: Record<string, SoulAct[]> = {}
    for (const s of souls) {
      const loc = soulLoc(s.reason) || '未知'
      ;(byLoc[loc] ||= []).push(s)
    }
    const locs = Object.keys(byLoc)
    if (playerLoc && !locs.includes(playerLoc)) locs.unshift(playerLoc)

    // 地点锚点:环形铺开;单地点居中。
    const placePos: Record<string, { x: number; y: number }> = {}
    const R = locs.length > 1 ? 150 + locs.length * 10 : 0
    locs.forEach((loc, i) => {
      const a = (i / Math.max(locs.length, 1)) * Math.PI * 2 - Math.PI / 2
      placePos[loc] = { x: CENTER.x + Math.cos(a) * R, y: CENTER.y + Math.sin(a) * R }
    })

    const nodes: Node[] = []
    // 地点锚点节点(在下层)
    for (const loc of locs) {
      const isPlayer = loc === playerLoc
      nodes.push({
        id: `place:${loc}`,
        position: placePos[loc],
        data: {
          label: (
            <div style={{ textAlign: 'center', pointerEvents: 'none' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: isPlayer ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-dim, #9aa0aa)' }}>
                {loc}{isPlayer ? ' · 你' : ''}
              </div>
            </div>
          ),
        },
        selectable: true,
        draggable: false,
        style: {
          width: 118,
          height: 118,
          borderRadius: '50%',
          border: `1.5px dashed ${isPlayer ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-line, #2a2f38)'}`,
          background: isPlayer ? 'rgba(232,180,90,0.06)' : 'rgba(255,255,255,0.015)',
          display: 'grid',
          placeItems: 'center',
          boxShadow: isPlayer ? '0 0 18px rgba(232,180,90,0.18)' : 'none',
        },
      })
    }
    // soul 节点(在上层,落在所在地点周围)
    for (const loc of locs) {
      const here = byLoc[loc] || []
      const c = placePos[loc]
      here.forEach((s, j) => {
        const iid = String(s.instance_id || s.sid || `${loc}:${j}`)
        const ring = here.length > 1 ? 40 : 0
        const a = (j / Math.max(here.length, 1)) * Math.PI * 2
        const hue = hueOf(s.sid || iid)
        const nm = names[iid] || s.sid || '?'
        nodes.push({
          id: `soul:${iid}`,
          position: { x: c.x + Math.cos(a) * ring + 24, y: c.y + Math.sin(a) * ring + 24 },
          data: {
            label: (
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, pointerEvents: 'none' }}>
                <span style={{ width: 24, height: 24, borderRadius: '50%', background: `hsl(${hue} 60% 22%)`, color: `hsl(${hue} 80% 72%)`, border: `1.5px solid hsl(${hue} 70% 45%)`, display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 800 }}>
                  {(s.sid || '?').slice(0, 1).toUpperCase()}
                </span>
                <span style={{ fontSize: 11, color: 'var(--lc-text, #e7e2d6)', fontWeight: 600, whiteSpace: 'nowrap' }}>{nm}</span>
              </div>
            ),
          },
          selectable: false,
          draggable: false,
          zIndex: 10,
          style: { background: 'transparent', border: 'none', padding: 0, width: 'auto' },
        })
      })
    }
    return { nodes, byLoc }
  }, [souls, playerLoc, names])

  const here = selPlace ? byLoc[selPlace] || [] : []

  return (
    <div className="wl-worldmap" style={{ position: 'relative', height: 380, marginTop: 16, borderRadius: 14, border: '1px solid var(--lc-line)', overflow: 'hidden', background: 'radial-gradient(circle at 42% 40%, #16191f, #0e1014)' }}>
      {/* soul 节点位置变化时平滑滑行 = 画布上"移动" */}
      <style>{`.wl-worldmap .react-flow__node { transition: transform 0.85s cubic-bezier(.4,0,.2,1); }`}</style>
      <ReactFlow
        nodes={nodes}
        edges={[]}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        minZoom={0.3}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, n) => setSelPlace(n.id.startsWith('place:') ? n.id.slice(6) : selPlace)}
        onPaneClick={() => setSelPlace(null)}
      >
        <Background color="#2a2f38" gap={22} />
        <Controls showInteractive={false} />
      </ReactFlow>
      {selPlace ? (
        <div style={{ position: 'absolute', right: 10, top: 10, width: 210, maxHeight: 340, overflow: 'auto', padding: 12, borderRadius: 12, border: '1px solid var(--lc-line)', background: 'var(--lc-panel, #14171d)', boxShadow: '0 6px 24px #0008' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--lc-candle, #e8b45a)', marginBottom: 8 }}>{selPlace}{selPlace === playerLoc ? ' · 你在此' : ''}</div>
          {here.length ? here.map((s) => (
            <div key={s.instance_id || s.sid} style={{ fontSize: 11, color: 'var(--lc-dim, #9aa0aa)', lineHeight: 1.6, marginBottom: 6 }}>
              <span style={{ color: 'var(--lc-text, #e7e2d6)', fontWeight: 600 }}>{names[String(s.instance_id || '')] || s.sid}</span>
              {s.reason ? <div style={{ color: 'var(--lc-faint, #6b7280)' }}>{s.reason}</div> : null}
            </div>
          )) : <div style={{ fontSize: 11, color: 'var(--lc-faint)' }}>此地暂无角色。</div>}
        </div>
      ) : null}
    </div>
  )
}
