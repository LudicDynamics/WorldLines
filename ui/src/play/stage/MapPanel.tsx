// AGENT MAP — full port of the classic page's two-level world map
// (src/neonrp/webui/index.html renderMap/setupMapPanZoom). World level =
// authored world_map nodes + roads(城镇可下钻,虚线圈);drill level = that
// town's sub-locations. Cast dots fan around the node they occupy. Pan(拖拽)
// + wheel/± zoom + double-click reset/pop-out. Worlds with no world_map fall
// back to a synthetic ring of occupied towns. Legend = per-cast precise place.

import { useMemo, useRef, useState } from 'react'
import type { WorldMap } from './events'
import type { Lane } from './stageState'
import type { T } from './strings'

const CAST_COLORS = ['#6ee7d8', '#ffd166', '#ff8fb1', '#9ad1ff', '#b4f08c', '#e3a8ff']
const W = 340
const H = 200

type Cast = { name: string; loc: string; town: string; color: string; isPlayer: boolean }
type NodePos = Record<string, { x: number; y: number }>

function scaler(nodes: { pos: number[] }[]) {
  const pad = 34
  const bpad = 26
  const xs = nodes.map((n) => n.pos[0])
  const ys = nodes.map((n) => n.pos[1])
  const minx = Math.min(...xs)
  const maxx = Math.max(...xs)
  const miny = Math.min(...ys)
  const maxy = Math.max(...ys)
  return {
    sx: (v: number) => (maxx === minx ? W / 2 : pad + ((v - minx) / (maxx - minx)) * (W - 2 * pad)),
    sy: (v: number) => (maxy === miny ? (H - bpad) / 2 : pad + ((v - miny) / (maxy - miny)) * (H - pad - bpad)),
  }
}

export function MapPanel({
  player,
  lanes,
  order,
  places,
  castLocs,
  worldMap,
  t,
}: {
  player: { name?: string; location?: string }
  lanes: Record<string, Lane>
  order: string[]
  places: Record<string, string>
  castLocs: Record<string, string>
  worldMap: WorldMap | null
  t: T
}) {
  const [min, setMin] = useState(false)
  const [drillTown, setDrillTown] = useState<string | null>(null)
  const [view, setView] = useState({ tx: 0, ty: 0, s: 1 })
  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<{ sx: number; sy: number; tx: number; ty: number; moved: boolean } | null>(null)

  const placeName = (raw: string) =>
    places[String(raw || '').replace(/^loc:/, '')] || String(raw || '').replace(/^loc:/, '')

  const wm = worldMap || {}
  const sub2town = wm.subloc_to_town || {}
  const townMaps = wm.town_maps || {}
  const townOf = (loc: string) =>
    String(loc).indexOf('/') >= 0 ? String(loc).split('/')[0] : sub2town[loc] || loc

  // Cast: player first(accent),then souls;loc = raw id(precise),
  // town = which world node it belongs to.
  const cast = useMemo<Cast[]>(() => {
    const out: Cast[] = [
      {
        name: player.name || t('role.player'),
        loc: String(player.location || '').trim() || t('map.unknown'),
        town: '',
        color: 'var(--lc-candle)',
        isPlayer: true,
      },
    ]
    let i = 0
    for (const id of order) {
      const lane = lanes[id]
      if (!lane || lane.kind !== 'soul') continue
      out.push({
        name: lane.name,
        // castLocs(raw id,hello 起就播种)→ lane.where(人话展示)→ 本地化
        // 占位。niko 实测:resume 后满屏「(unknown)」— 永远别裸奔英文占位。
        loc: String(castLocs[id] || '').trim() || String(lane.where || '').trim() || t('map.unknown'),
        town: '',
        color: CAST_COLORS[i % CAST_COLORS.length],
        isPlayer: false,
      })
      i += 1
    }
    for (const c of out) c.town = townOf(c.loc)
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [player.name, player.location, lanes, order, castLocs, worldMap])

  const drill = drillTown && townMaps[drillTown] ? drillTown : null

  // Layout: positions + node list + edges for the current level.
  const layout = useMemo(() => {
    const pos: NodePos = {}
    const nodeList: { id: string; name?: string }[] = []
    const edges: [string, string][] = []
    let placeOfCast: (c: Cast) => string | null = (c) => c.town
    let drillableOf: (id: string) => string | null = () => null

    if (drill) {
      const tm = townMaps[drill]
      const sn = (tm.nodes || []).filter((n) => Array.isArray(n.pos) && n.pos.length >= 2) as {
        id: string
        name?: string
        pos: number[]
      }[]
      const { sx, sy } = scaler(sn.length ? sn : [{ pos: [0, 0] }])
      for (const n of sn) {
        pos[n.id] = { x: sx(n.pos[0]), y: sy(n.pos[1]) }
        nodeList.push({ id: n.id, name: n.name })
      }
      for (const e of tm.edges || []) if (pos[e[0]] && pos[e[1]]) edges.push([e[0], e[1]])
      const byName: Record<string, string> = {}
      for (const n of sn) if (n.name) byName[n.name] = n.id
      const resolveSub = (loc: string): string | null => {
        const np = String(loc || '').indexOf('/') >= 0 ? String(loc).split('/')[1] : String(loc || '')
        if (pos[np]) return np
        if (pos[loc]) return loc
        const nm = placeName(loc) || String(loc || '')
        const tail = nm.indexOf('·') >= 0 ? nm.split('·').pop()! : nm
        if (byName[tail]) return byName[tail]
        for (const n of sn) if (n.name && nm && (nm.indexOf(n.name) >= 0 || n.name.indexOf(tail) >= 0)) return n.id
        return sn.length ? sn[0].id : null
      }
      placeOfCast = (c) => (c.town === drill ? resolveSub(c.loc) : null)
    } else {
      const wmNodes = ((wm.nodes || []) as { id: string; name?: string; pos?: number[] }[]).filter(
        (n) => Array.isArray(n.pos) && n.pos!.length >= 2,
      ) as { id: string; name?: string; pos: number[] }[]
      if (wmNodes.length) {
        const { sx, sy } = scaler(wmNodes)
        for (const n of wmNodes) {
          pos[n.id] = { x: sx(n.pos[0]), y: sy(n.pos[1]) }
          nodeList.push({ id: n.id, name: n.name })
        }
        for (const e of wm.edges || []) if (pos[e[0]] && pos[e[1]]) edges.push([e[0], e[1]])
        drillableOf = (id) => (townMaps[id] ? id : null)
      } else {
        // Fallback: synthetic ring of occupied towns(无 world_map 的世界)
        const locs: string[] = []
        for (const c of cast) if (c.town && !locs.includes(c.town)) locs.push(c.town)
        const cx = W / 2
        const cy = H / 2 - 6
        const R = Math.min(W, H) / 2 - 40
        locs.forEach((l, i) => {
          const a = (Math.PI * 2 * i) / Math.max(locs.length, 1) - Math.PI / 2
          pos[l] = {
            x: cx + (locs.length === 1 ? 0 : R * Math.cos(a)),
            y: cy + (locs.length === 1 ? 0 : R * Math.sin(a)),
          }
          nodeList.push({ id: l, name: placeName(l) })
        })
        if (locs.length > 1) {
          pos['__hub__'] = { x: cx, y: cy }
          for (const l of locs) edges.push(['__hub__', l])
        }
      }
      // Never drop a present character: unknown towns get ad-hoc bottom nodes.
      const orphans: string[] = []
      for (const c of cast) if (c.town && !pos[c.town] && !orphans.includes(c.town)) orphans.push(c.town)
      orphans.forEach((tn, i) => {
        pos[tn] = { x: 40 + ((i + 1) * (W - 80)) / (orphans.length + 1), y: H - 12 }
        nodeList.push({ id: tn, name: placeName(tn) })
      })
    }

    const dotAt: Record<string, Cast[]> = {}
    for (const c of cast) {
      const id = placeOfCast(c)
      if (id) (dotAt[id] = dotAt[id] || []).push(c)
    }
    return { pos, nodeList, edges, dotAt, drillableOf }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cast, drill, worldMap, places])

  // ── pan / zoom(classic setupMapPanZoom 的 React 版)────────────────
  function zoom(f: number, vx = W / 2, vy = H / 2) {
    setView((v) => {
      const ns = Math.max(0.5, Math.min(6, v.s * f))
      const cx = (vx - v.tx) / v.s
      const cy = (vy - v.ty) / v.s
      return { s: ns, tx: vx - cx * ns, ty: vy - cy * ns }
    })
  }
  const toView = (clientX: number, clientY: number) => {
    const r = svgRef.current!.getBoundingClientRect()
    return { x: ((clientX - r.left) / r.width) * W, y: ((clientY - r.top) / r.height) * H }
  }

  function onPointerDown(e: React.PointerEvent<SVGSVGElement>) {
    svgRef.current?.setPointerCapture(e.pointerId)
    dragRef.current = { sx: e.clientX, sy: e.clientY, tx: view.tx, ty: view.ty, moved: false }
  }
  function onPointerMove(e: React.PointerEvent<SVGSVGElement>) {
    const d = dragRef.current
    if (!d) return
    const r = svgRef.current!.getBoundingClientRect()
    if (Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) > 4) d.moved = true
    setView((v) => ({
      ...v,
      tx: d.tx + (e.clientX - d.sx) * (W / r.width),
      ty: d.ty + (e.clientY - d.sy) * (H / r.height),
    }))
  }
  function onPointerUp(e: React.PointerEvent<SVGSVGElement>) {
    const wasDragged = dragRef.current?.moved
    try {
      svgRef.current?.releasePointerCapture(e.pointerId)
    } catch {
      /* released */
    }
    dragRef.current = null
    if (wasDragged) return
    // Tap:drill into a drillable town under the pointer(hit-test 真实点)
    const el = document.elementFromPoint(e.clientX, e.clientY)
    const g = el?.closest?.('g[data-drill]')
    const tid = g?.getAttribute('data-drill')
    if (tid && townMaps[tid]) {
      setDrillTown(tid)
      setView({ tx: 0, ty: 0, s: 1 })
    }
  }
  function onWheel(e: React.WheelEvent<SVGSVGElement>) {
    const p = toView(e.clientX, e.clientY)
    zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, p.x, p.y)
  }
  function onDblClick() {
    if (drill) {
      setDrillTown(null)
      setView({ tx: 0, ty: 0, s: 1 })
      return
    }
    setView({ tx: 0, ty: 0, s: 1 })
  }

  const title = drill ? `${t('map.back_hint')} · ${placeName(drill)}` : `🗺 ${t('map.title')}`
  const { pos, nodeList, edges, dotAt, drillableOf } = layout

  return (
    <div className="lc-map" data-testid="stage-map">
      <h4>
        <span
          style={drill ? { cursor: 'pointer' } : undefined}
          onClick={() => {
            if (drill) {
              setDrillTown(null)
              setView({ tx: 0, ty: 0, s: 1 })
            }
          }}
        >
          {title}
        </span>
        <button aria-label="minimize" title="minimize" onClick={() => setMin((m) => !m)}>
          {min ? '▢' : '–'}
        </button>
      </h4>
      {min ? null : (
        <>
          <div style={{ position: 'relative' }}>
            <svg
              ref={svgRef}
              viewBox={`0 0 ${W} ${H}`}
              style={{ touchAction: 'none', cursor: 'grab' }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onWheel={onWheel}
              onDoubleClick={onDblClick}
            >
              <g transform={`translate(${view.tx} ${view.ty}) scale(${view.s})`}>
                {edges.map(([a, b], i) => (
                  <line
                    key={i}
                    x1={pos[a].x}
                    y1={pos[a].y}
                    x2={pos[b].x}
                    y2={pos[b].y}
                    stroke="var(--lc-line)"
                    strokeWidth={1.5}
                  />
                ))}
                {pos['__hub__'] && <circle cx={pos['__hub__'].x} cy={pos['__hub__'].y} r={3} fill="var(--lc-line)" />}
                {nodeList.map((nd) => {
                  const p = pos[nd.id]
                  if (!p) return null
                  const occupied = (dotAt[nd.id] || []).length > 0
                  const did = drillableOf(nd.id)
                  const nm = nd.name || placeName(nd.id)
                  const label = nm.length > 12 ? nm.slice(0, 11) + '…' : nm
                  return (
                    <g key={nd.id} data-drill={did || undefined} style={did ? { cursor: 'pointer' } : undefined}>
                      {did && <title>{`${t('map.drill_tip')} · ${nm}`}</title>}
                      <circle
                        cx={p.x}
                        cy={p.y}
                        r={11}
                        fill={occupied ? 'var(--lc-candle-soft)' : 'var(--lc-panel2)'}
                        stroke={occupied ? 'var(--lc-candle)' : 'var(--lc-line)'}
                        strokeWidth={1.5}
                        strokeDasharray={did ? '3 2' : undefined}
                      />
                      <text x={p.x} y={p.y + 23} textAnchor="middle" fontSize={9} fill="var(--lc-dim)">
                        {label}
                      </text>
                    </g>
                  )
                })}
                {Object.entries(dotAt).map(([id, cs]) => {
                  const p = pos[id]
                  if (!p) return null
                  return cs.map((c, n) => {
                    const a = -Math.PI / 2 + n * 0.7
                    return (
                      <circle
                        key={`${id}-${n}`}
                        cx={p.x + 15 * Math.cos(a)}
                        cy={p.y + 15 * Math.sin(a)}
                        r={c.isPlayer ? 5 : 4}
                        fill={c.color}
                      />
                    )
                  })
                })}
              </g>
            </svg>
            <div style={{ position: 'absolute', right: 4, bottom: 4, display: 'flex', gap: 4 }}>
              <button className="lc-mapzoom" onClick={() => zoom(1.3)}>
                +
              </button>
              <button className="lc-mapzoom" onClick={() => zoom(1 / 1.3)}>
                −
              </button>
            </div>
          </div>
          <div style={{ padding: '4px 0 8px' }}>
            {cast.map((c, i) => (
              <div className="legrow" key={i}>
                <span className="legdot" style={{ background: c.color }} />
                <span>{c.name}</span>
                <span className="legplace"> · {placeName(c.loc)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
