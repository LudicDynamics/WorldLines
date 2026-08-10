// 画布数据层(docs/STUDIO-CANVAS-PLAN.md):三画布的 client + 类型。
// map = 世界内容(world_map.json 投影);story/relation = STUDIO_HOME 副产物。
import { localEndpoint } from './localClient'

export type CanvasKind = 'map' | 'story' | 'relation'

export type FlowNode = {
  id: string
  pos: [number, number]
  data: Record<string, unknown> & { label?: string }
}
export type FlowEdge = {
  id: string
  source: string
  target: string
  data: Record<string, unknown>
}
export type CanvasState = {
  nodes: FlowNode[]
  edges: FlowEdge[]
  viewport: { x?: number; y?: number; zoom?: number }
}

export type Relationship = {
  id: string
  source: string
  target: string
  relation_type: string
  description: string
  direction: 'directed' | 'bidirectional'
  strength: number
}
export type RelationState = {
  relationships: Relationship[]
  layout: {
    positions?: Record<string, [number, number]>
    viewport?: { x?: number; y?: number; zoom?: number }
  }
}

export type EntityRef = { id: string; name: string }
export type FlagRef = { key: string; type: 'boolean' | 'number' | 'enum' }
export type Entities = {
  npcs: EntityRef[]
  locations: EntityRef[]
  quests: EntityRef[]
  flags: FlagRef[]
  souls: EntityRef[]
}

const BASE = () => `${localEndpoint()}/api/v1/create/session/edit-local`

async function jfetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE()}${path}`, init)
  if (!r.ok) throw new Error(`${path} → ${r.status} ${await r.text().catch(() => '')}`)
  return (await r.json()) as T
}

export const getCanvas = <T = CanvasState>(kind: CanvasKind) => jfetch<T>(`/canvas/${kind}`)

export const putCanvas = <T>(kind: CanvasKind, state: T) =>
  jfetch<T>(`/canvas/${kind}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state),
  })

export const getEntities = () => jfetch<Entities>('/entities')

// ── 剧情节点 10 类型(照抄 trpgmaster 配色,数据不入库只入 style)────
export type StoryNodeType =
  | 'scene' | 'event' | 'choice' | 'check' | 'combat'
  | 'clue' | 'location' | 'reward' | 'ending' | 'condition'

// Values are i18n keys (resolved via useLocalT / translate at render — see
// local/i18n.tsx). Keeping the type keys unchanged means storyType() membership
// and iteration order are untouched; only the display text is localized.
export const STORY_TYPE_KEYS: Record<StoryNodeType, string> = {
  scene: 'canvas.story.scene', event: 'canvas.story.event', choice: 'canvas.story.choice',
  check: 'canvas.story.check', combat: 'canvas.story.combat', clue: 'canvas.story.clue',
  location: 'canvas.story.location', reward: 'canvas.story.reward', ending: 'canvas.story.ending',
  condition: 'canvas.story.condition',
}
export const STORY_TYPE_COLORS: Record<StoryNodeType, { background: string; border: string }> = {
  scene: { background: '#eff6ff', border: '#60a5fa' },
  event: { background: '#f8fafc', border: '#94a3b8' },
  choice: { background: '#fefce8', border: '#eab308' },
  check: { background: '#f0fdfa', border: '#2dd4bf' },
  combat: { background: '#fef2f2', border: '#f87171' },
  clue: { background: '#ecfdf5', border: '#34d399' },
  location: { background: '#f5f3ff', border: '#a78bfa' },
  reward: { background: '#fff7ed', border: '#fb923c' },
  ending: { background: '#fdf2f8', border: '#f472b6' },
  condition: { background: '#eef2ff', border: '#818cf8' },
}
export function storyType(v: unknown): StoryNodeType {
  return typeof v === 'string' && v in STORY_TYPE_KEYS ? (v as StoryNodeType) : 'scene'
}

// 连线条件运算符;选项随 flag 类型联动(trpgmaster App.tsx:5647 同款)
export type EdgeOperator = 'is_true' | 'is_false' | 'equals' | 'not_equals' | 'gte' | 'lte'
// i18n keys (resolved at render — see STORY_TYPE_KEYS note above).
export const OPERATOR_KEYS: Record<EdgeOperator, string> = {
  is_true: 'canvas.op.is_true', is_false: 'canvas.op.is_false', equals: 'canvas.op.equals',
  not_equals: 'canvas.op.not_equals', gte: 'canvas.op.gte', lte: 'canvas.op.lte',
}
export function operatorsFor(type: FlagRef['type'] | undefined): EdgeOperator[] {
  if (type === 'boolean') return ['is_true', 'is_false']
  if (type === 'number') return ['equals', 'not_equals', 'gte', 'lte']
  return ['equals', 'not_equals']
}

// 关系画布实体节点循环色板
export const REL_COLORS = [
  { background: '#eff6ff', border: '#60a5fa' },
  { background: '#fef2f2', border: '#f87171' },
  { background: '#ecfdf5', border: '#34d399' },
  { background: '#fefce8', border: '#eab308' },
  { background: '#f5f3ff', border: '#a78bfa' },
  { background: '#fff7ed', border: '#fb923c' },
  { background: '#fdf2f8', border: '#f472b6' },
]
