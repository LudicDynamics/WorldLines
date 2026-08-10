// 角色弧线画布(niko 洞察:剧情 graph 属于角色,不属于世界)。
// 弧线是 soul 包自身的内容 —— 存 trajectory/arc.json,随角色入库/发布,
// 游玩时 soul-agent 可读(角色带着自己的故事走)。trpgmaster 没有这个
// 概念,是我们的新东西。工程骨架同 StudioCanvas(防误删/自动保存)。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type Viewport,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useLocalT, type T } from './i18n'

// 7 类弧线节点:过去 → 内在 → 走向(配色区别于世界剧情画布)
export type ArcType = 'memory' | 'wound' | 'desire' | 'bond' | 'turning' | 'choice' | 'ending'
export const ARC_TYPES: ArcType[] = ['memory', 'wound', 'desire', 'bond', 'turning', 'choice', 'ending']
const ARC_COLORS: Record<ArcType, { background: string; border: string }> = {
  memory: { background: '#f0f9ff', border: '#7dd3fc' },
  wound: { background: '#fef2f2', border: '#f87171' },
  desire: { background: '#fff7ed', border: '#fb923c' },
  bond: { background: '#fdf2f8', border: '#f472b6' },
  turning: { background: '#fefce8', border: '#eab308' },
  choice: { background: '#eef2ff', border: '#818cf8' },
  ending: { background: '#f5f3ff', border: '#a78bfa' },
}
function arcType(v: unknown): ArcType {
  return typeof v === 'string' && (ARC_TYPES as string[]).includes(v) ? (v as ArcType) : 'memory'
}

export type ArcState = {
  nodes: { id: string; pos: [number, number]; data: Record<string, unknown> }[]
  edges: { id: string; source: string; target: string; data: Record<string, unknown> }[]
  viewport: { x?: number; y?: number; zoom?: number }
}

export function parseArc(raw: unknown): ArcState {
  try {
    const v = typeof raw === 'string' ? (JSON.parse(raw) as ArcState) : (raw as ArcState)
    if (v && Array.isArray(v.nodes)) return { nodes: v.nodes, edges: v.edges ?? [], viewport: v.viewport ?? {} }
  } catch {
    /* fresh */
  }
  return { nodes: [], edges: [], viewport: {} }
}

export function SoulArcCanvas({
  initial,
  onPersist,
}: {
  initial: ArcState
  onPersist: (json: string) => Promise<void>
}) {
  const { t } = useLocalT()
  const [nodes, setNodes] = useState<Node[]>(() =>
    initial.nodes.map((n) => ({
      id: n.id,
      position: { x: n.pos?.[0] ?? 0, y: n.pos?.[1] ?? 0 },
      data: { ...n.data },
    })),
  )
  const [edges, setEdges] = useState<Edge[]>(() =>
    initial.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      animated: true,
      label: String(e.data?.label || ''),
      data: { ...e.data },
    })),
  )
  const [viewport, setViewport] = useState<Viewport>({
    x: initial.viewport.x ?? 0,
    y: initial.viewport.y ?? 0,
    zoom: initial.viewport.zoom ?? 1,
  })
  const [dlg, setDlg] = useState<Node | null>(null)
  const [status, setStatus] = useState<'saved' | 'dirty' | 'saving' | 'error'>('saved')
  const saveVersion = useRef(0)
  const first = useRef(true)

  // 自动保存(800ms debounce → trajectory/arc.json)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    setStatus('dirty')
    const version = ++saveVersion.current
    const handle = window.setTimeout(async () => {
      setStatus('saving')
      const payload: ArcState = {
        nodes: nodes.map((n) => ({
          id: n.id,
          pos: [Math.round(n.position.x), Math.round(n.position.y)] as [number, number],
          data: n.data as Record<string, unknown>,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          data: (e.data ?? {}) as Record<string, unknown>,
        })),
        viewport,
      }
      try {
        await onPersist(JSON.stringify(payload, null, 1))
        if (version === saveVersion.current) setStatus('saved')
      } catch {
        if (version === saveVersion.current) setStatus('error')
      }
    }, 800)
    return () => window.clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, viewport])

  const onNodesChange: OnNodesChange = useCallback((ch) => setNodes((c) => applyNodeChanges(ch, c)), [])
  const onEdgesChange: OnEdgesChange = useCallback((ch) => setEdges((c) => applyEdgeChanges(ch, c)), [])
  const onConnect: OnConnect = useCallback((conn: Connection) => {
    if (!conn.source || !conn.target || conn.source === conn.target) return
    setEdges((c) =>
      addEdge(
        { id: `ae-${Date.now()}`, source: conn.source!, target: conn.target!, animated: true, data: { label: '' } },
        c,
      ),
    )
  }, [])

  const styled = useMemo(
    () =>
      nodes.map((n) => {
        const c = ARC_COLORS[arcType((n.data as Record<string, unknown>).arc_type)]
        return {
          ...n,
          data: { ...n.data, label: String((n.data as Record<string, unknown>).label || t('arc.untitled')) },
          style: { background: c.background, border: `1px solid ${c.border}`, color: '#0f172a' },
        }
      }),
    [nodes, t],
  )

  function addNode() {
    const fresh: Node = {
      id: `arc-${Date.now()}`,
      position: { x: 120 + nodes.length * 18, y: 90 + nodes.length * 18 },
      data: { label: t('arc.newNode'), arc_type: 'memory', text: '' },
    }
    setNodes((c) => [...c, fresh])
    setDlg(fresh)
  }

  return (
    <div className="relative w-full h-full min-h-[380px]">
      <div className="absolute z-10 top-2 left-2 flex items-center gap-2">
        <button
          onClick={addNode}
          className="text-[12px] rounded-lg px-3 py-1.5 cursor-pointer border"
          style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
        >
          ＋ {t('arc.addNode')}
        </button>
        <span className="text-[11px] font-mono" style={{ color: status === 'error' ? '#FF6B8A' : 'var(--lc-faint)' }}>
          {status === 'saved' ? t('canvas.saved') : status === 'saving' ? t('canvas.saving') : status === 'dirty' ? t('canvas.dirty') : t('canvas.error')}
        </span>
        <span className="text-[11px]" style={{ color: 'var(--lc-faint)' }}>
          {t('arc.hint')}
        </span>
      </div>
      <ReactFlow
        nodes={styled}
        edges={edges}
        deleteKeyCode={null}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        viewport={viewport}
        onViewportChange={setViewport}
        onNodeClick={(_, n) => setDlg(n)}
        onPaneClick={() => setDlg(null)}
        fitView={initial.nodes.length > 0}
        proOptions={{ hideAttribution: true }}
      >
        <MiniMap pannable zoomable />
        <Controls />
        <Background />
      </ReactFlow>
      {dlg && (
        <ArcNodeDialog
          node={dlg}
          t={t}
          onSave={(data) => {
            setNodes((c) => c.map((n) => (n.id === dlg.id ? { ...n, data } : n)))
            setDlg(null)
          }}
          onDelete={() => {
            setNodes((c) => c.filter((n) => n.id !== dlg.id))
            setEdges((c) => c.filter((e) => e.source !== dlg.id && e.target !== dlg.id))
            setDlg(null)
          }}
          onClose={() => setDlg(null)}
        />
      )}
    </div>
  )
}

function ArcNodeDialog({
  node, t, onSave, onDelete, onClose,
}: {
  node: Node
  t: T
  onSave: (d: Record<string, unknown>) => void
  onDelete: () => void
  onClose: () => void
}) {
  const [form, setForm] = useState<Record<string, unknown>>({ ...(node.data as Record<string, unknown>) })
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))
  const field = 'w-full rounded-lg border px-2.5 py-1.5 text-[12.5px] outline-none'
  const fieldStyle = { background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' } as const

  return (
    <div
      className="absolute z-20 top-10 right-2 w-[300px] rounded-xl border p-4 flex flex-col gap-2.5"
      style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
    >
      <div className="text-[13px] font-semibold">{t('arc.nodeTitle')} · {node.id}</div>
      <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--lc-dim)' }}>
        {t('arc.fieldLabel')}
        <input className={field} style={fieldStyle} value={String(form.label ?? '')} onChange={(e) => set('label', e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--lc-dim)' }}>
        {t('arc.fieldType')}
        <select className={field} style={fieldStyle} value={arcType(form.arc_type)} onChange={(e) => set('arc_type', e.target.value)}>
          {ARC_TYPES.map((k) => (
            <option key={k} value={k}>{t(`arc.type.${k}`)}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--lc-dim)' }}>
        {t('arc.fieldText')}
        <textarea className={field} style={fieldStyle} rows={4} value={String(form.text ?? '')} onChange={(e) => set('text', e.target.value)} />
      </label>
      <div className="flex gap-2 mt-1">
        <button onClick={() => onSave(form)} disabled={!String(form.label ?? '').trim()}
          className="flex-1 text-[12.5px] font-semibold rounded-lg px-3 py-1.5 cursor-pointer border-0"
          style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}>
          {t('canvas.save')}
        </button>
        <button onClick={onClose} className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
          style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}>
          {t('canvas.cancel')}
        </button>
        <button onClick={onDelete} className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
          style={{ borderColor: 'var(--lc-line)', color: '#FF6B8A', background: 'transparent' }}>
          {t('canvas.delete')}
        </button>
      </div>
    </div>
  )
}
