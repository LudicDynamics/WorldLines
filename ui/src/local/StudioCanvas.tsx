// 三画布复用组件(docs/STUDIO-CANVAS-PLAN.md C1-C3)。
// 照抄 trpgmaster 的骨架:受控 <ReactFlow>、deleteKeyCode={null}(删除只走
// 弹窗按钮)、业务字段全在 node/edge 的 data、配色渲染期注入 style 不入文件、
// snapshot 脏检测 + 800ms debounce 自动保存 + version/kind 双竞态守卫。
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
import {
  getCanvas,
  getEntities,
  putCanvas,
  operatorsFor,
  storyType,
  OPERATOR_KEYS,
  REL_COLORS,
  STORY_TYPE_COLORS,
  STORY_TYPE_KEYS,
  type CanvasKind,
  type CanvasState,
  type EdgeOperator,
  type Entities,
  type FlowEdge,
  type FlowNode,
  type RelationState,
  type Relationship,
  type StoryNodeType,
} from './canvasData'
import { useLocalT, type T } from './i18n'

const MAP_SCALE = 40 // world_map 的 pos 是逻辑格子坐标 → 画布像素

type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error'

type Snapshot = { nodes: Node[]; edges: Edge[]; viewport: Viewport }

const snap = (s: Snapshot) =>
  JSON.stringify({
    n: s.nodes.map((n) => ({ i: n.id, p: n.position, d: n.data })),
    e: s.edges.map((e) => ({ i: e.id, s: e.source, t: e.target, d: e.data })),
    v: s.viewport,
  })

export function StudioCanvas({
  kind,
  refreshKey,
  onDraft,
}: {
  kind: CanvasKind
  refreshKey: number
  onDraft?: () => void
}) {
  const { t } = useLocalT()
  const [nodes, setNodes] = useState<Node[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, zoom: 1 })
  const [entities, setEntities] = useState<Entities | null>(null)
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [status, setStatusRaw] = useState<SaveStatus>('idle')
  const setStatus = useCallback((v: SaveStatus) => {
    statusRef.current = v
    setStatusRaw(v)
  }, [])
  const [dlgNode, setDlgNode] = useState<Node | null>(null)
  const [dlgEdge, setDlgEdge] = useState<Edge | null>(null)
  const [loading, setLoading] = useState(true)

  const savedSnap = useRef('')
  const statusRef = useRef<SaveStatus>('idle')
  const rfRef = useRef<{ fitView: (o?: { padding?: number; maxZoom?: number }) => unknown } | null>(null)
  // 载入时是否带有已保存的视野 —— 没有就 fitView 居中容纳全部内容
  const hadViewport = useRef(false)
  const saveVersion = useRef(0)
  const activeKind = useRef(kind)

  // ── 载入(kind / 外部 refreshKey 变化时)────────────────────────
  const firstLoad = useRef(true)
  useEffect(() => {
    // agent 回合结束的强制刷新:画布上有未保存手改时跳过,
    // 用户编辑优先(否则 agent 一回合就把你正拖的节点冲掉)。
    if (!firstLoad.current && activeKind.current === kind
        && (statusRef.current === 'dirty' || statusRef.current === 'saving')) {
      return
    }
    firstLoad.current = false
    activeKind.current = kind
    setLoading(true)
    setDlgNode(null)
    setDlgEdge(null)
    savedSnap.current = '' // 基线在载入后的首次渲染重新定格(防跨画布误判脏)
    const load = async () => {
      const ents = await getEntities().catch(() => null)
      if (activeKind.current !== kind) return
      setEntities(ents)
      if (kind === 'relation') {
        const st = await getCanvas<RelationState>('relation').catch(() => null)
        if (activeKind.current !== kind) return
        const rels = st?.relationships ?? []
        setRelationships(rels)
        const pos = st?.layout?.positions ?? {}
        // 节点 = NPC + 原生角色,但两类分离标识(niko:Soul 与 NPC 必须分开)
        // — soul 带 ✦ 前缀 + isSoul 标记(渲染期给专属描边色)
        const ents2 = [
          ...(ents?.npcs ?? []).map((e) => ({ ...e, isSoul: false })),
          ...(ents?.souls ?? []).map((e) => ({ ...e, isSoul: true })),
        ]
        const rf = ents2.map((en, i) => ({
          id: en.id,
          position: pos[en.id]
            ? { x: pos[en.id][0], y: pos[en.id][1] }
            : { x: 80 + (i % 4) * 190, y: 80 + Math.floor(i / 4) * 140 },
          data: { label: (en.isSoul ? '✦ ' : '') + en.name, isSoul: en.isSoul },
        }))
        setNodes(rf)
        setEdges(relsToEdges(rels))
        const vp = st?.layout?.viewport
        hadViewport.current = !!(vp && (vp.x || vp.y || (vp.zoom && vp.zoom !== 1)))
        setViewport({ x: vp?.x ?? 0, y: vp?.y ?? 0, zoom: vp?.zoom ?? 1 })
        savedSnap.current = '' // 由下方 effect 在首次渲染后填
      } else {
        const st = await getCanvas<CanvasState>(kind).catch(() => null)
        if (activeKind.current !== kind) return
        const scale = kind === 'map' ? MAP_SCALE : 1
        setNodes(
          (st?.nodes ?? []).map((n) => ({
            id: n.id,
            position: { x: (n.pos?.[0] ?? 0) * scale, y: (n.pos?.[1] ?? 0) * scale },
            data: { ...n.data },
          })),
        )
        setEdges(
          (st?.edges ?? []).map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            animated: kind === 'story',
            label: edgeLabel(kind, e.data, t),
            data: { ...e.data },
          })),
        )
        const vp2 = st?.viewport
        hadViewport.current = !!(vp2 && (vp2.x || vp2.y || (vp2.zoom && vp2.zoom !== 1)))
        setViewport({
          x: vp2?.x ?? 0,
          y: vp2?.y ?? 0,
          zoom: vp2?.zoom ?? 1,
        })
      }
      // 载入完成的状态作为已保存基线
      setStatus('saved')
      setLoading(false)
    }
    void load()
  }, [kind, refreshKey])

  // 基线快照:载入完成后第一次渲染时定格
  useEffect(() => {
    if (!loading && savedSnap.current === '') {
      savedSnap.current = snap({ nodes, edges, viewport })
    }
  }, [loading, nodes, edges, viewport])

  // 初始视野:没有保存过视野时,fitView 把全部内容居中容纳
  // (niko 实测:世界图开局偏移、两侧大片空白)。fitView 会触发
  // onViewportChange → 存入 viewport;之后以用户的拖拽/缩放为准。
  useEffect(() => {
    if (loading || hadViewport.current || !nodes.length) return
    const id = window.setTimeout(() => {
      rfRef.current?.fitView({ padding: 0.18, maxZoom: 1.6 })
      hadViewport.current = true
    }, 60)
    return () => window.clearTimeout(id)
  }, [loading, nodes.length])

  // ── 自动保存(snapshot 脏检测 + 800ms debounce + 竞态守卫)──────
  useEffect(() => {
    if (loading) return
    const current = snap({ nodes, edges, viewport })
    if (current === savedSnap.current) {
      setStatus('saved')
      return
    }
    setStatus('dirty')
    const version = ++saveVersion.current
    const k = kind
    const handle = window.setTimeout(async () => {
      setStatus('saving')
      try {
        if (k === 'relation') {
          const payload: RelationState = {
            relationships,
            layout: {
              positions: Object.fromEntries(
                nodes.map((n) => [n.id, [Math.round(n.position.x), Math.round(n.position.y)]]),
              ) as Record<string, [number, number]>,
              viewport,
            },
          }
          await putCanvas('relation', payload)
        } else {
          const scale = k === 'map' ? MAP_SCALE : 1
          const payload: CanvasState = {
            nodes: nodes.map((n) => ({
              id: n.id,
              pos: [n.position.x / scale, n.position.y / scale] as [number, number],
              data: n.data as FlowNode['data'],
            })),
            edges: edges.map((e) => ({
              id: e.id,
              source: e.source,
              target: e.target,
              data: (e.data ?? {}) as FlowEdge['data'],
            })),
            viewport,
          }
          await putCanvas(k, payload)
        }
        if (version !== saveVersion.current || activeKind.current !== k) return
        savedSnap.current = current
        setStatus('saved')
      } catch {
        if (version === saveVersion.current && activeKind.current === k) setStatus('error')
      }
    }, 800)
    return () => window.clearTimeout(handle)
  }, [nodes, edges, viewport, relationships, kind, loading])

  // ── React Flow handlers ───────────────────────────────────────
  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((cur) => applyNodeChanges(changes, cur)),
    [],
  )
  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((cur) => applyEdgeChanges(changes, cur)),
    [],
  )
  const onConnect: OnConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target || conn.source === conn.target) return
      if (kind === 'relation') {
        // 关系画布:连线 = 建一条关系(SoT 是 relationships 列表,边是派生)
        const rel: Relationship = {
          id: `rel-${Date.now()}`,
          source: conn.source,
          target: conn.target,
          relation_type: t('canvas.relationDefault'),
          description: '',
          direction: 'directed',
          strength: 3,
        }
        setRelationships((cur) => {
          const next = [...cur, rel]
          setEdges(relsToEdges(next))
          return next
        })
        return
      }
      const id = `${kind === 'map' ? 'R' : 'se'}-${Date.now()}`
      const data =
        kind === 'map'
          ? { kind: 'road' }
          : { label: '', flag_key: '', operator: 'is_true', compare_value: '', condition_text: '' }
      setEdges((cur) =>
        addEdge(
          { id, source: conn.source!, target: conn.target!, animated: kind === 'story', data },
          cur,
        ),
      )
    },
    [kind],
  )

  // ── 渲染期样式注入(不入文件,trpgmaster styledCanvasNodes 同款)──
  const styledNodes = useMemo(() => {
    if (kind === 'story') {
      return nodes.map((n) => {
        const c = STORY_TYPE_COLORS[storyType((n.data as Record<string, unknown>).node_type)]
        return {
          ...n,
          data: { ...n.data, label: String((n.data as Record<string, unknown>).label || t('canvas.unnamed')) },
          style: { background: c.background, border: `1px solid ${c.border}`, color: '#0f172a' },
        }
      })
    }
    if (kind === 'relation') {
      return nodes.map((n, i) => {
        const isSoul = Boolean((n.data as Record<string, unknown>).isSoul)
        const c = REL_COLORS[i % REL_COLORS.length]
        return {
          ...n,
          style: isSoul
            ? { background: c.background, border: '2px dashed #f472b6', color: '#0f172a' }
            : { background: c.background, border: `1px solid ${c.border}`, color: '#0f172a' },
        }
      })
    }
    return nodes.map((n) => ({
      ...n,
      style: { background: '#eff6ff', border: '1px solid #60a5fa', color: '#0f172a' },
    }))
  }, [nodes, kind])

  function addNode() {
    const count = nodes.length
    const id = kind === 'map' ? `T${String(Date.now()).slice(-6)}` : `sf-${Date.now()}`
    const fresh: Node = {
      id,
      position: { x: 120 + count * 18, y: 90 + count * 18 }, // 对角线错位防叠
      data:
        kind === 'map'
          ? { label: t('canvas.newLocation'), summary: '' }
          : {
              label: t('canvas.newStoryNode'), node_type: 'scene', player_text: '', gm_text: '',
              trigger_condition: '', related_ids: [], clue_ids: [], fail_safe: '',
            },
    }
    setNodes((cur) => [...cur, fresh])
    setDlgNode(fresh)
  }

  function deleteNode(id: string) {
    setNodes((cur) => cur.filter((n) => n.id !== id))
    setEdges((cur) => cur.filter((e) => e.source !== id && e.target !== id)) // 连带清挂接边
    setDlgNode(null)
  }

  function deleteEdge(id: string) {
    if (kind === 'relation') {
      setRelationships((cur) => {
        const next = cur.filter((r) => r.id !== id)
        setEdges(relsToEdges(next))
        return next
      })
    } else {
      setEdges((cur) => cur.filter((e) => e.id !== id))
    }
    setDlgEdge(null)
  }

  const statusLabel = {
    idle: '',
    dirty: t('canvas.dirty'),
    saving: t('canvas.saving'),
    saved: t('canvas.saved'),
    error: t('canvas.error'),
  }[status]

  return (
    <div className="relative w-full h-full min-h-[420px]">
      <div className="absolute z-10 top-2 left-2 flex items-center gap-2">
        {kind !== 'relation' && (
          <button
            onClick={addNode}
            className="text-[12px] rounded-lg px-3 py-1.5 cursor-pointer border"
            style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          >
            ＋ {kind === 'map' ? t('canvas.location') : t('canvas.node')}
          </button>
        )}
        <span className="text-[11px] font-mono" style={{ color: status === 'error' ? '#FF6B8A' : 'var(--lc-faint)' }}>
          {statusLabel}
        </span>
        <span className="text-[11px]" style={{ color: 'var(--lc-faint)' }}>
          {kind === 'relation' ? t('canvas.relHint') : t('canvas.flowHint')}
        </span>
      </div>
      <ReactFlow
        nodes={styledNodes}
        edges={edges}
        deleteKeyCode={null}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        viewport={viewport}
        onViewportChange={setViewport}
        onInit={(inst) => {
          rfRef.current = inst
        }}
        onNodeClick={(_, n) => setDlgNode(n)}
        onEdgeClick={(_, e) => setDlgEdge(e)}
        onPaneClick={() => {
          setDlgNode(null)
          setDlgEdge(null)
        }}
        fitView={false}
        proOptions={{ hideAttribution: true }}
      >
        <MiniMap pannable zoomable />
        <Controls />
        <Background />
      </ReactFlow>
      {!loading && kind !== 'map' && nodes.length === 0 && (kind !== 'relation' || relationships.length === 0) && (
        <div className="absolute inset-0 z-[5] grid place-items-center pointer-events-none">
          <div className="pointer-events-auto rounded-xl border p-5 text-center max-w-[360px]"
            style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}>
            <div className="text-[14px] font-semibold">{t(t2Key(kind, 'emptyTitle'))}</div>
            <p className="mt-1 mb-3 text-[12px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
              {t(t2Key(kind, 'emptyDesc'))}
            </p>
            {onDraft && (
              <button onClick={onDraft}
                className="text-[13px] font-semibold rounded-lg px-4 py-2 cursor-pointer border-0 mr-2"
                style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}>
                ✦ {t(t2Key(kind, 'emptyDraft'))}
              </button>
            )}
            {kind === 'story' && (
              <button onClick={addNode}
                className="text-[13px] rounded-lg px-4 py-2 cursor-pointer border"
                style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}>
                ＋ {t(t2Key(kind, 'emptyManual'))}
              </button>
            )}
          </div>
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 grid place-items-center text-[12px]" style={{ color: 'var(--lc-faint)' }}>
          {t('canvas.loading')}
        </div>
      )}
      {dlgNode && kind === 'relation' && (
        <div className={dlgWrap} style={dlgStyle}>
          <div className="text-[13px] font-semibold">
            {String((dlgNode.data as Record<string, unknown>).label || dlgNode.id)} · 关系
          </div>
          {relationships.filter((r) => r.source === dlgNode.id || r.target === dlgNode.id).length === 0 && (
            <p className="text-[12px] m-0" style={{ color: 'var(--lc-faint)' }}>
              还没有关系 —— 拖这个节点边缘的圆点连到另一个角色即可建立。
            </p>
          )}
          {relationships
            .filter((r) => r.source === dlgNode.id || r.target === dlgNode.id)
            .map((r) => (
              <div key={r.id} className="flex items-center gap-2 text-[12px] rounded-lg border px-2.5 py-1.5"
                style={{ borderColor: 'var(--lc-line)' }}>
                <span className="min-w-0 flex-1 truncate">
                  {r.source === dlgNode.id ? `→ ${r.target}` : `← ${r.source}`} · {r.relation_type}
                  {r.description ? ` · ${r.description.slice(0, 24)}` : ''}
                </span>
                <button
                  onClick={() => {
                    const edge = edges.find((e) => e.id === r.id)
                    setDlgNode(null)
                    if (edge) setDlgEdge(edge)
                  }}
                  className="text-[11px] rounded px-2 py-0.5 cursor-pointer border"
                  style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-candle)', background: 'transparent' }}
                >
                  编辑
                </button>
                <button
                  onClick={() => deleteEdge(r.id)}
                  className="text-[11px] rounded px-2 py-0.5 cursor-pointer border"
                  style={{ borderColor: 'var(--lc-line)', color: '#FF6B8A', background: 'transparent' }}
                >
                  删
                </button>
              </div>
            ))}
          <button
            onClick={() => setDlgNode(null)}
            className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border mt-1"
            style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
          >
            关闭
          </button>
        </div>
      )}
      {dlgNode && kind !== 'relation' && (
        <NodeDialog
          kind={kind}
          node={dlgNode}
          entities={entities}
          onSave={(data) => {
            setNodes((cur) => cur.map((n) => (n.id === dlgNode.id ? { ...n, data } : n)))
            setDlgNode(null)
          }}
          onDelete={() => deleteNode(dlgNode.id)}
          onClose={() => setDlgNode(null)}
        />
      )}
      {dlgEdge && (
        <EdgeDialog
          kind={kind}
          edge={dlgEdge}
          entities={entities}
          relationships={relationships}
          onSave={(data) => {
            if (kind === 'relation') {
              setRelationships((cur) => {
                const next = cur.map((r) =>
                  r.id === dlgEdge.id ? { ...r, ...(data as Partial<Relationship>) } : r,
                )
                setEdges(relsToEdges(next))
                return next
              })
            } else {
              setEdges((cur) =>
                cur.map((e) =>
                  e.id === dlgEdge.id
                    ? { ...e, data, label: edgeLabel(kind, data as Record<string, unknown>, t) }
                    : e,
                ),
              )
            }
            setDlgEdge(null)
          }}
          onDelete={() => deleteEdge(dlgEdge.id)}
          onClose={() => setDlgEdge(null)}
        />
      )}
    </div>
  )
}

function relsToEdges(rels: Relationship[]): Edge[] {
  return rels.map((r) => ({
    id: r.id,
    source: r.source,
    target: r.target,
    label: r.relation_type + (r.description ? ` · ${r.description.slice(0, 18)}` : ''),
    data: { ...r },
  }))
}

function edgeLabel(kind: CanvasKind, data: Record<string, unknown> | undefined, t: T): string {
  if (!data) return ''
  if (kind === 'map') return String(data.kind || '')
  const short = String(data.label || '')
  if (short) return short
  const flag = String(data.flag_key || '')
  if (flag) {
    const opKey = OPERATOR_KEYS[(data.operator as EdgeOperator) || 'is_true']
    const op = opKey ? t(opKey) : ''
    const cv = String(data.compare_value ?? '')
    return `${flag} ${op} ${cv}`.trim()
  }
  return String(data.condition_text || '').slice(0, 24)
}

// ── 弹窗(节点/连线;删除只在这里)─────────────────────────────────
const dlgWrap =
  'absolute z-20 top-10 right-2 w-[320px] max-h-[calc(100%-60px)] overflow-y-auto rounded-xl border p-4 flex flex-col gap-2.5'
const dlgStyle = { background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }
const fieldCls = 'w-full rounded-lg border px-2.5 py-1.5 text-[12.5px] outline-none'
const fieldStyle = {
  background: 'var(--lc-panel2)',
  borderColor: 'var(--lc-line)',
  color: 'var(--lc-text)',
} as const

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--lc-dim)' }}>
      {label}
      {children}
    </label>
  )
}

function NodeDialog({
  kind, node, entities, onSave, onDelete, onClose,
}: {
  kind: CanvasKind
  node: Node
  entities: Entities | null
  onSave: (data: Record<string, unknown>) => void
  onDelete: () => void
  onClose: () => void
}) {
  const { t } = useLocalT()
  const d = node.data as Record<string, unknown>
  const [form, setForm] = useState<Record<string, unknown>>({ ...d })
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))
  const refs = [
    ...(entities?.npcs ?? []),
    ...(entities?.locations ?? []),
    ...(entities?.quests ?? []),
  ]
  const related = new Set((form.related_ids as string[]) ?? [])

  return (
    <div className={dlgWrap} style={dlgStyle}>
      <div className="text-[13px] font-semibold">{kind === 'map' ? t('canvas.location') : t('canvas.storyNode')} · {node.id}</div>
      <Field label={t('canvas.name')}>
        <input
          className={fieldCls}
          style={fieldStyle}
          value={String(form.label ?? '')}
          onChange={(e) => set('label', e.target.value)}
        />
      </Field>
      {kind === 'map' ? (
        <>
          <Field label={t('canvas.summary')}>
            <textarea
              className={fieldCls}
              style={fieldStyle}
              rows={3}
              value={String(form.summary ?? '')}
              onChange={(e) => set('summary', e.target.value)}
            />
          </Field>
          {form.extra && Object.keys(form.extra as Record<string, unknown>).length > 0 && (
            <div className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
              {t('canvas.extraFields')}
              <div className="mt-1 rounded-lg border p-2 flex flex-col gap-1" style={{ borderColor: 'var(--lc-line)' }}>
                {Object.entries(form.extra as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-[11px]">
                    <span className="font-mono shrink-0" style={{ color: 'var(--lc-faint)' }}>{k}</span>
                    <span className="min-w-0 break-words" style={{ color: 'var(--lc-text)' }}>
                      {typeof v === 'string' ? v : JSON.stringify(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          <Field label={t('canvas.type')}>
            <select
              className={fieldCls}
              style={fieldStyle}
              value={storyType(form.node_type)}
              onChange={(e) => set('node_type', e.target.value as StoryNodeType)}
            >
              {Object.entries(STORY_TYPE_KEYS).map(([k, labelKey]) => (
                <option key={k} value={k}>{t(labelKey)}</option>
              ))}
            </select>
          </Field>
          <Field label={t('canvas.playerText')}>
            <textarea className={fieldCls} style={fieldStyle} rows={3}
              value={String(form.player_text ?? '')} onChange={(e) => set('player_text', e.target.value)} />
          </Field>
          <Field label={t('canvas.gmText')}>
            <textarea className={fieldCls} style={fieldStyle} rows={3}
              value={String(form.gm_text ?? '')} onChange={(e) => set('gm_text', e.target.value)} />
          </Field>
          <Field label={t('canvas.trigger')}>
            <textarea className={fieldCls} style={fieldStyle} rows={2}
              value={String(form.trigger_condition ?? '')} onChange={(e) => set('trigger_condition', e.target.value)} />
          </Field>
          <Field label={t('canvas.failsafe')}>
            <textarea className={fieldCls} style={fieldStyle} rows={2}
              value={String(form.fail_safe ?? '')} onChange={(e) => set('fail_safe', e.target.value)} />
          </Field>
          {refs.length > 0 && (
            <Field label={t('canvas.relatedEntities', { n: related.size })}>
              <div className="flex flex-wrap gap-1 max-h-[100px] overflow-y-auto">
                {refs.map((r) => {
                  const on = related.has(r.id)
                  return (
                    <button
                      key={r.id}
                      onClick={() => {
                        const next = new Set(related)
                        if (next.has(r.id)) next.delete(r.id)
                        else next.add(r.id)
                        set('related_ids', [...next])
                      }}
                      className="text-[10.5px] rounded-full px-2 py-0.5 cursor-pointer border"
                      style={
                        on
                          ? { background: 'var(--lc-candle-soft)', borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)' }
                          : { background: 'transparent', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }
                      }
                    >
                      {r.name}
                    </button>
                  )
                })}
              </div>
            </Field>
          )}
        </>
      )}
      <div className="flex gap-2 mt-1">
        <button
          onClick={() => onSave(form)}
          disabled={!String(form.label ?? '').trim()}
          className="flex-1 text-[12.5px] font-semibold rounded-lg px-3 py-1.5 cursor-pointer border-0"
          style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}
        >
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

function EdgeDialog({
  kind, edge, entities, relationships, onSave, onDelete, onClose,
}: {
  kind: CanvasKind
  edge: Edge
  entities: Entities | null
  relationships: Relationship[]
  onSave: (data: Record<string, unknown>) => void
  onDelete: () => void
  onClose: () => void
}) {
  const { t } = useLocalT()
  const base =
    kind === 'relation'
      ? ((relationships.find((r) => r.id === edge.id) ?? {}) as Record<string, unknown>)
      : ((edge.data ?? {}) as Record<string, unknown>)
  const [form, setForm] = useState<Record<string, unknown>>({ ...base })
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  const flags = entities?.flags ?? []
  const pickedFlag = flags.find((f) => f.key === String(form.flag_key || ''))
  const ops = operatorsFor(pickedFlag?.type)

  return (
    <div className={dlgWrap} style={dlgStyle}>
      <div className="text-[13px] font-semibold">
        {kind === 'map' ? t('canvas.route') : kind === 'story' ? t('canvas.storyEdge') : t('canvas.relation')} · {edge.source} → {edge.target}
      </div>
      {kind === 'map' && (
        <>
          <Field label={t('canvas.edgeKind')}>
            <input className={fieldCls} style={fieldStyle} value={String(form.kind ?? 'road')}
              onChange={(e) => set('kind', e.target.value)} />
          </Field>
          <Field label={t('canvas.distance')}>
            <input className={fieldCls} style={fieldStyle} type="number" value={String(form.distance ?? '')}
              onChange={(e) => set('distance', e.target.value === '' ? undefined : Number(e.target.value))} />
          </Field>
        </>
      )}
      {kind === 'story' && (
        <>
          <Field label={t('canvas.bindFlag')}>
            <select
              className={fieldCls} style={fieldStyle} value={String(form.flag_key ?? '')}
              onChange={(e) => {
                const key = e.target.value
                const ft = flags.find((f) => f.key === key)?.type
                // 选变量联动重置运算符(trpgmaster App.tsx:8892 同款)
                set('flag_key', key)
                set('operator', ft === 'boolean' ? 'is_true' : 'equals')
                set('compare_value', '')
              }}
            >
              <option value="">{t('canvas.noBind')}</option>
              {flags.map((f) => (
                <option key={f.key} value={f.key}>{f.key}({f.type})</option>
              ))}
            </select>
          </Field>
          {form.flag_key ? (
            <Field label={t('canvas.compare')}>
              <select className={fieldCls} style={fieldStyle} value={String(form.operator ?? ops[0])}
                onChange={(e) => set('operator', e.target.value as EdgeOperator)}>
                {ops.map((op) => (
                  <option key={op} value={op}>{t(OPERATOR_KEYS[op])}</option>
                ))}
              </select>
            </Field>
          ) : null}
          {form.flag_key && form.operator !== 'is_true' && form.operator !== 'is_false' ? (
            <Field label={t('canvas.expectedValue')}>
              <input className={fieldCls} style={fieldStyle}
                type={pickedFlag?.type === 'number' ? 'number' : 'text'}
                value={String(form.compare_value ?? '')}
                onChange={(e) => set('compare_value', e.target.value)} />
            </Field>
          ) : null}
          <Field label={t('canvas.conditionText')}>
            <textarea className={fieldCls} style={fieldStyle} rows={2}
              value={String(form.condition_text ?? '')} onChange={(e) => set('condition_text', e.target.value)} />
          </Field>
          <Field label={t('canvas.edgeLabel')}>
            <input className={fieldCls} style={fieldStyle} value={String(form.label ?? '')}
              onChange={(e) => set('label', e.target.value)} />
          </Field>
        </>
      )}
      {kind === 'relation' && (
        <>
          <Field label={t('canvas.relationType')}>
            <input className={fieldCls} style={fieldStyle} value={String(form.relation_type ?? '')}
              onChange={(e) => set('relation_type', e.target.value)} />
          </Field>
          <Field label={t('canvas.description')}>
            <textarea className={fieldCls} style={fieldStyle} rows={2}
              value={String(form.description ?? '')} onChange={(e) => set('description', e.target.value)} />
          </Field>
          <Field label={t('canvas.strength', { n: String(form.strength ?? 3) })}>
            <input className={fieldCls} style={fieldStyle} type="range" min={1} max={5}
              value={Number(form.strength ?? 3)} onChange={(e) => set('strength', Number(e.target.value))} />
          </Field>
        </>
      )}
      <div className="flex gap-2 mt-1">
        <button onClick={() => onSave(form)}
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

// 空态文案按画布种类取 key(story/relation)
function t2Key(kind: CanvasKind, part: string): string {
  return `canvas.${kind}.${part}`
}
