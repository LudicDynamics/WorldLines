// Wire shapes for the classic `neonrp web` broadcast (/events, native
// EventSource). Ported from src/neonrp/webui/index.html — one `kind` per
// message. The PlayStage is a React port of that vanilla page, so these
// mirror the engine's `topic world/state` / soul_status / thinking / chunk /
// trace stream exactly.

export type HelloSoul = {
  instance_id: string
  name: string
  role?: string
  where?: string
  intro?: string
}

export type Hello = {
  kind: 'hello'
  world?: string
  world_name?: string
  agent_id?: string
  souls?: HelloSoul[]
  places?: Record<string, string>
  world_map?: WorldMap
  player_name?: string
  player_class?: string
  player_location?: string
  player_hp?: Hp
  player_intro?: string
}

export type Hp = { current?: number; max?: number }

export type WorldMapNode = { id: string; name?: string; pos?: number[]; type?: string }
export type WorldMap = {
  nodes?: WorldMapNode[]
  edges?: [string, string][]
  subloc_to_town?: Record<string, string>
  town_maps?: Record<string, { nodes?: WorldMapNode[]; edges?: [string, string][] }>
}

export type TurnStart = { kind: 'turn_start'; text?: string }
// 多智能体总线在 kickoff 流里用的变体名(stageState 归一到 turn_start)
export type TurnStarted = { kind: 'turn_started'; text?: string }
export type Chunk = { kind: 'chunk'; text?: string }
export type Thinking = { kind: 'thinking'; text?: string }
export type AgentError = { kind: 'agent_error'; error?: string; severity?: string }

export type Positions = {
  kind: 'positions'
  places?: Record<string, string>
  player?: string
  player_hp?: Hp
  souls?: { instance_id: string; where?: string; intro?: string; location?: string; name?: string }[]
}

export type SoulStatuses = {
  kind: 'soul_status'
  statuses: Record<string, { name?: string; role?: string; state?: string }>
}

export type SoulPsyche = {
  kind: 'soul_psyche'
  instance_id?: string
  state?: string
  inner_voice?: string
  confidence?: number
  urgency?: number
  memory_delta?: string
}

export type ToolEvent = { kind: 'tool'; name?: string }

export type BusMessage = { topic?: string; payload?: Record<string, unknown>; seq?: number }
export type Trace = {
  kind: 'trace'
  trace?: {
    turn_seq?: number
    world_location?: string
    land?: { commit_id?: string }
    souls?: { instance_id: string; activated?: boolean; reason?: string }[]
    bus_messages?: BusMessage[]
  }
}

export type TurnDone = { kind: 'turn_done'; success?: boolean; error?: string }

export type EngineEvent =
  | Hello
  | TurnStart
  | TurnStarted
  | Chunk
  | Thinking
  | AgentError
  | Positions
  | SoulStatuses
  | SoulPsyche
  | ToolEvent
  | Trace
  | TurnDone
  | { kind: string; [k: string]: unknown }

// A trace fetched via GET /trace?i=<n> (for replay / resume rendering).
// 引擎实际返回的字段比历史定义多 —— souls(谁在哪 + 状态)、location 别名、
// 玩家意图等,观察窗的 pulse / 地图靠它们。scene_label 在 bus_messages 的
// world/scene topic 里(见 ObservatoryShell 解析)。
export type TraceSoul = {
  sid?: string
  instance_id: string
  activated?: boolean
  reason?: string // "active · co-located at 'T001/gate_north'" / "location group 'T004' (away from player)"
  state?: string
  speech?: string
}
export type TraceRecord = {
  turn_seq?: number
  world_location?: string
  location?: string
  ts?: string
  land?: { commit_id?: string }
  player?: { input?: string; intent_kind?: string }
  souls?: TraceSoul[]
  bus_messages?: BusMessage[]
}

export type TraceSummaryRow = {
  i: number
  turn_seq?: number
  commit?: string
  world_location?: string
  location?: string // 引擎 /traces 实际返回的字段名(world_location 为历史别名)
}
