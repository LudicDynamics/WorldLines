// The PlayStage reducer — a declarative port of the vanilla page's imperative
// DOM handlers (src/neonrp/webui/index.html). One dispatch per /events message
// mutates an immutable state tree; components render from it. The boot-theater
// (D7) phase advances off the SAME real events — no faked progress.

import type { CleanedNarration } from './narration'
import { cleanReason, cleanupNarration, esc, statusPhrase, stripControl } from './narration'
import type { EngineEvent, Hp, WorldMap } from './events'
import type { T } from './strings'

export type LaneKind = 'world' | 'player' | 'soul'
export type LaneLog = { id: number; html: string }
export type Psyche = {
  state?: string
  inner_voice?: string
  confidence?: number
  urgency?: number
}
export type Lane = {
  id: string
  name: string
  role: string
  where: string
  intro: string
  kind: LaneKind
  dot: string
  logs: LaneLog[]
  streaming: string | null
  psyche: Psyche | null
  memory: string[]
}
export type Turn = {
  id: number
  userText: string
  raw: string
  statusKey: string | null
  statusDetail: string
  done: boolean
  rollback: { commit: string; turnSeq?: number } | null
  cleaned: CleanedNarration | null
  // 过程轨收尾摘要(DESIGN-TOKENS §三):回合完成后轨收起成一行,
  // 数据钉在回合上(时长 ms + 参与 soul 数 + 世界回合号)。
  rail: { ms: number; souls: number; seq?: number } | null
}
export type TimelineRow = { seq: number; loc: string; commit: string }
export type BootPhase = 'connecting' | 'waking' | 'souls' | 'narrating' | 'done'
export type Boot = { active: boolean; phase: BootPhase; worldAwake: boolean; preview: string }

// 回合过程轨(DESIGN-TOKENS §三)。状态机 = FORWARD-ONLY 单调索引,
// 转移条件从 niko 真实存档的 bus_messages 顺序校准(orchestration/main.jsonl):
//   idx0 世界思考 ← turn_start
//   idx1 角色行动 ← 首个 soul_status
//   idx2 位置裁定/整合 ← souls 全部 completed/degraded(world/integrate 不在
//         直播 SSE 里 — 全员收工即该窗口开启,诚实映射)
//   idx3 叙事成稿 ← 非 subagent chunk,且仅当 idx≥2(真实流里世界铺垫 chunk
//         会先于 souls 完成到达 — 不许它把后面阶段瞬间点亮;无 soul 世界例外直进)
// 每级只增不减 →「✓角色行动 0/2」这类自相矛盾在结构上不可能。
export type RailStageId = 'world' | 'souls' | 'ruling' | 'narrate'
export const RAIL_STAGES: RailStageId[] = ['world', 'souls', 'ruling', 'narrate']
export type Rail = {
  running: boolean
  idx: number // 0..3,单调递增
  startedAt: number | null
  // 当前活跃 soul(思考尾巴轮换用):最近一个 state=running 的 iid。
  activeSoul: string | null
  // 本回合的世界回合号:resume 时由 /traces 播种(seedSeq),此后随
  // world/state 推进 — niko 实测「TURN · 进行中」号位空白的修复。
  seq: number | null
}

export type StageState = {
  connected: boolean
  world: { name: string; agentId: string } | null
  turns: Turn[]
  lanes: Record<string, Lane>
  laneOrder: string[]
  player: { name?: string; klass?: string; location?: string; hp?: Hp }
  places: Record<string, string>
  // 原始位置 id(如 "T004/guild"),按 soul instance_id 键 — 地图落位用;
  // lane.where 是人话展示文本,定位要用这个。
  castLocs: Record<string, string>
  worldMap: WorldMap | null
  choices: string[]
  timeline: TimelineRow[]
  busyInput: boolean
  boot: Boot
  rail: Rail
  // 已落地的最新世界回合号(seed + world/state 推进);rail.seq = lastSeq+1。
  lastSeq: number | null
  turnSoulState: Record<string, { name: string; state: string }>
  ids: { log: number; turn: number }
}

export const initialStageState: StageState = {
  connected: false,
  world: null,
  turns: [],
  lanes: {},
  laneOrder: [],
  player: {},
  places: {},
  castLocs: {},
  worldMap: null,
  choices: [],
  timeline: [],
  busyInput: false,
  boot: { active: false, phase: 'connecting', worldAwake: false, preview: '' },
  rail: { running: false, idx: 0, startedAt: null, activeSoul: null, seq: null },
  lastSeq: null,
  turnSoulState: {},
  ids: { log: 0, turn: 0 },
}

export type StageAction =
  | { type: 'event'; ev: EngineEvent; t: T; dev: boolean; ts?: number }
  | { type: 'busy'; v: boolean }
  | { type: 'bootStart' }
  | { type: 'bootDismiss' }
  | { type: 'seedSeq'; seq: number }
  | { type: 'choices'; options: string[] }

// ── small immutable helpers ────────────────────────────────────────────────

function ensureLane(s: StageState, id: string, name: string, role: string, kind: LaneKind): void {
  if (s.lanes[id]) return
  s.lanes[id] = {
    id,
    name,
    role,
    where: '',
    intro: '',
    kind,
    dot: '',
    logs: [],
    streaming: null,
    psyche: null,
    memory: [],
  }
  s.laneOrder = [...s.laneOrder, id]
}

function flushStream(lane: Lane): void {
  if (lane.streaming != null && lane.streaming.length) {
    lane.logs = [...lane.logs, { id: -1, html: `<span class="lc-speech">${esc(lane.streaming)}</span>` }]
  }
  lane.streaming = null
}

function laneLog(s: StageState, id: string, html: string): void {
  const lane = s.lanes[id]
  if (!lane) return
  const next = { ...lane }
  flushStream(next)
  next.logs = [...next.logs, { id: s.ids.log++, html }]
  s.lanes[id] = next
}

function laneStream(s: StageState, id: string, text: string): void {
  const lane = s.lanes[id]
  if (!lane) return
  s.lanes[id] = { ...lane, streaming: (lane.streaming || '') + text }
}

function setDot(s: StageState, id: string, state: string): void {
  const lane = s.lanes[id]
  if (!lane) return
  s.lanes[id] = { ...lane, dot: state || '' }
}

function curTurn(s: StageState): Turn | null {
  return s.turns.length ? s.turns[s.turns.length - 1] : null
}

function patchTurn(s: StageState, patch: Partial<Turn>): void {
  if (!s.turns.length) return
  const i = s.turns.length - 1
  s.turns = [...s.turns.slice(0, i), { ...s.turns[i], ...patch }]
}

// ── the event handler ───────────────────────────────────────────────────────

function applyEvent(s: StageState, ev: EngineEvent, t: T, dev: boolean, ts: number): void {
  const m = ev as Record<string, unknown>
  switch (ev.kind) {
    case 'hello': {
      s.connected = true
      s.world = { name: String(m.world_name || m.world || ''), agentId: String(m.agent_id || '') }
      ensureLane(s, 'world', String(m.agent_id || 'world'), t('role.world'), 'world')
      for (const so of (m.souls as EngineEvent[] as Record<string, unknown>[]) || []) {
        const iid = String(so.instance_id)
        ensureLane(s, iid, String(so.name || iid), String(so.where || `soul · ${so.role || ''}`), 'soul')
        s.lanes[iid] = {
          ...s.lanes[iid],
          where: String(so.where || ''),
          intro: String(so.intro || ''),
        }
        // hello 就带 raw location — 立刻播种 castLocs,地图/在场判定不用等
        // 第一个 positions 事件(否则 resume 后是一屏 "(unknown)")。
        if (so.location) s.castLocs = { ...s.castLocs, [iid]: String(so.location) }
      }
      ensureLane(s, 'player', 'player-agent', t('role.player'), 'player')
      s.lanes['player'] = { ...s.lanes['player'], intro: String(m.player_intro || '') }
      if (m.places) s.places = { ...s.places, ...(m.places as Record<string, string>) }
      if (m.world_map) s.worldMap = m.world_map as WorldMap
      s.player = {
        name: m.player_name as string,
        klass: m.player_class as string,
        location: m.player_location as string,
        hp: m.player_hp as Hp,
      }
      if (s.boot.active && s.boot.phase === 'connecting') s.boot = { ...s.boot, phase: 'waking' }
      break
    }
    case 'turn_start': {
      s.turns = [
        ...s.turns,
        {
          id: s.ids.turn++,
          userText: String(m.text || ''),
          raw: '',
          statusKey: 'play.orch_souls',
          statusDetail: '',
          done: false,
          rollback: null,
          cleaned: null,
          rail: null,
        },
      ]
      for (const id of s.laneOrder) flushStream((s.lanes[id] = { ...s.lanes[id] }))
      setDot(s, 'world', 'running')
      s.turnSoulState = {}
      s.choices = []
      s.rail = {
        running: true,
        idx: 0,
        startedAt: ts,
        activeSoul: null,
        seq: s.lastSeq != null ? s.lastSeq + 1 : null,
      }
      if (s.boot.active) s.boot = { ...s.boot, worldAwake: true }
      break
    }
    case 'chunk': {
      const text = String(m.text || '')
      const tag = text.match(/^\[\[subagent:([^\]]+)\]\]([\s\S]*)$/)
      if (tag) {
        const id = tag[1].startsWith('soul:') ? tag[1].split(':')[2] : 'world'
        laneStream(s, id, tag[2])
      } else if (/^\s*\[calling [^\]]*\]\s*$/.test(text)) {
        // engine tool-call announcement — machine state, keep the feed clean
      } else {
        const cur = curTurn(s)
        if (!cur) {
          s.turns = [
            ...s.turns,
            {
              id: s.ids.turn++,
              userText: '',
              raw: '',
              statusKey: null,
              statusDetail: '',
              done: false,
              rollback: null,
              cleaned: null,
              rail: null,
            },
          ]
        }
        patchTurn(s, { raw: (curTurn(s)!.raw || '') + text, statusKey: null })
        // 成稿阶段门控:有 soul 的世界必须先走完角色行动+裁定(idx≥2)——
        // 真实流里世界铺垫 chunk 早于 souls 完成到达,不许瞬间全亮;
        // 无 soul(orch)世界没有中间两段,直进成稿。
        if (s.rail.running && s.rail.idx < 3) {
          const hasSouls =
            Object.keys(s.turnSoulState).length > 0 ||
            Object.values(s.lanes).some((l) => l.kind === 'soul')
          if (!hasSouls || s.rail.idx >= 2) s.rail = { ...s.rail, idx: 3 }
        }
        if (s.boot.active) {
          s.boot = {
            ...s.boot,
            worldAwake: true,
            phase: 'narrating',
            preview: (s.boot.preview + stripControl(text)).slice(-400),
          }
        }
      }
      break
    }
    case 'thinking': {
      const text = String(m.text || '')
      if (!curTurn(s) || curTurn(s)!.done) {
        // 中途接入(开场回合在 bind 时就开始了):合成回合块 + 启动过程轨,
        // 让 kickoff 也有和普通回合一样的进行中提示
        s.turns = [
          ...s.turns,
          {
            id: s.ids.turn++,
            userText: '',
            raw: '',
            statusKey: 'play.orch_world',
            statusDetail: '',
            done: false,
            rollback: null,
            cleaned: null,
            rail: null,
          },
        ]
        if (!s.rail.running) {
          s.rail = {
            running: true,
            idx: 0,
            startedAt: ts,
            activeSoul: null,
            seq: s.lastSeq != null ? s.lastSeq + 1 : null,
          }
        }
        setDot(s, 'world', 'running')
      }
      if (!text.includes('[[subagent:soul:')) patchTurn(s, { statusKey: 'play.orch_world' })
      if (s.boot.active) s.boot = { ...s.boot, worldAwake: true }
      if (!dev) break
      const tag = text.match(/^\[\[subagent:([^\]]+)\]\]([\s\S]*)$/)
      const id = tag ? (tag[1].startsWith('soul:') ? tag[1].split(':')[2] : 'world') : 'world'
      laneStream(s, id, tag ? tag[2] : text)
      break
    }
    case 'agent_error': {
      const cls = m.severity === 'warning' ? 'lc-warn' : 'lc-err'
      laneLog(s, 'world', `<span class="${cls}">⚠ ${esc(String(m.error || '').slice(0, 120))}</span>`)
      break
    }
    case 'positions': {
      if (m.places) s.places = { ...s.places, ...(m.places as Record<string, string>) }
      for (const so of (m.souls as Record<string, unknown>[]) || []) {
        if (so.location) {
          s.castLocs = { ...s.castLocs, [String(so.instance_id)]: String(so.location) }
        }
      }
      s.player = {
        ...s.player,
        location: (m.player as string) ?? s.player.location,
        hp: (m.player_hp as Hp) || s.player.hp,
      }
      for (const so of (m.souls as Record<string, unknown>[]) || []) {
        const id = String(so.instance_id)
        const lane = s.lanes[id]
        if (lane) {
          s.lanes[id] = {
            ...lane,
            where: (so.where as string) || lane.where,
            intro: (so.intro as string) || lane.intro,
            role: (so.where as string) || lane.role,
          }
        }
      }
      break
    }
    case 'soul_status': {
      const statuses = (m.statuses as Record<string, { name?: string; role?: string; state?: string }>) || {}
      for (const [iid, st] of Object.entries(statuses)) {
        ensureLane(s, iid, st.name || iid, 'soul · ' + (st.role || ''), 'soul')
        setDot(s, iid, st.state || '')
        s.turnSoulState = { ...s.turnSoulState, [iid]: { name: st.name || iid, state: st.state || '' } }
      }
      const all = Object.values(s.turnSoulState)
      const done = all.filter((x) => x.state === 'completed' || x.state === 'degraded').length
      const running = all.find((x) => x.state === 'running')
      const detail = ((running ? running.name + ' ' : '') + (all.length ? `(${done}/${all.length})` : '')).trim()
      patchTurn(s, { statusKey: 'play.orch_souls', statusDetail: detail })
      // 过程轨(forward-only):首个 soul_status → idx≥1;全员收工 → idx≥2
      // (整合/裁定窗口 — world/integrate 不在直播 SSE 里,诚实合并)。
      if (s.rail.running) {
        const runningIid = Object.entries(s.turnSoulState).find(([, v]) => v.state === 'running')?.[0]
        const target = all.length && done === all.length ? 2 : 1
        s.rail = {
          ...s.rail,
          idx: Math.max(s.rail.idx, target),
          activeSoul: runningIid ?? s.rail.activeSoul,
        }
      }
      if (s.boot.active && s.boot.phase !== 'narrating') s.boot = { ...s.boot, phase: 'souls' }
      break
    }
    case 'soul_psyche': {
      const id = m.instance_id as string
      const lane = id ? s.lanes[id] : null
      if (!lane) break
      const psyche: Psyche = {
        state: m.state as string,
        inner_voice: m.inner_voice as string,
        confidence: m.confidence as number,
        urgency: m.urgency as number,
      }
      const mem = String(m.memory_delta || '').trim()
      const memory = mem ? [...lane.memory, mem].slice(-4) : lane.memory
      s.lanes[id] = { ...lane, psyche, memory }
      break
    }
    case 'tool': {
      patchTurn(s, { statusKey: 'play.orch_world', statusDetail: m.name ? '⚙ ' + m.name : '' })
      laneLog(s, 'world', `⚙ ${esc(String(m.name || ''))}`)
      break
    }
    case 'trace': {
      const tr = (m.trace as Record<string, unknown>) || {}
      const land = (tr.land as Record<string, unknown>) || {}
      const commit = land.commit_id as string | undefined
      const turnSeq = tr.turn_seq as number | undefined
      if (commit && curTurn(s) && !curTurn(s)!.rollback) patchTurn(s, { rollback: { commit, turnSeq } })
      for (const so of (tr.souls as Record<string, unknown>[]) || []) {
        const id = so.instance_id as string
        ensureLane(s, id, id, 'soul', 'soul')
        const phrase = esc(statusPhrase(so.reason, t))
        laneLog(
          s,
          id,
          so.activated
            ? `${esc(t('turn.prefix'))}${turnSeq} · ${phrase}`
            : `${esc(t('turn.prefix'))}${turnSeq} · ○ ${phrase}`,
        )
      }
      for (const bm of (tr.bus_messages as Record<string, unknown>[]) || []) {
        const topic = String(bm.topic || '')
        const p = (bm.payload as Record<string, unknown>) || {}
        if (topic.endsWith('/request')) {
          const ln = String(p.last_narration || '').replace(/\n/g, ' ')
          laneLog(
            s,
            String(p.instance_id),
            `👁 ${esc(t('narr.perceived'))}: ${esc(String(p.scene_label || '?'))}` +
              (ln ? `<br>\u3000${esc(t('narr.last_world'))}: ${esc(ln.slice(0, 120))}…` : ''),
          )
        }
        if (topic.endsWith('/response')) {
          const d = String(p.digest || '')
          const sp = d.match(/speech=([^|]+)/)
          const mv = d.match(/moved_to=([^|]+)/)
          const act = d.match(/action=([^|]+)/)
          const cand = (p.candidates as { fit?: number; action?: string }[]) || []
          if (cand.length && dev) {
            const best = Math.max(...cand.map((c) => c.fit || 0))
            const parts = cand.map(
              (c) => `${(c.fit || 0) === best ? '★' : '·'}${esc(cleanReason(c.action).slice(0, 18))}(${(c.fit || 0).toFixed(1)})`,
            )
            laneLog(s, String(p.instance_id), `<span style="opacity:.7">🎲 ${parts.join(' ')}</span>`)
          }
          if (sp) laneLog(s, String(p.instance_id), `💬 <span class="lc-speech">${esc(sp[1].trim())}</span>`)
          if (act) laneLog(s, String(p.instance_id), `→ ${esc(cleanReason(act[1]).slice(0, 80))}`)
          if (mv)
            laneLog(
              s,
              String(p.instance_id),
              `<span class="lc-move">⇒ ${esc(t('narr.moved_to'))} ${esc(mv[1].trim())}</span>`,
            )
        }
        if (topic === 'world/state') {
          const sq = Number(p.turn_seq) || 0
          if (sq) s.lastSeq = Math.max(s.lastSeq ?? 0, sq)
          s.timeline = [
            ...s.timeline,
            {
              seq: Number(p.turn_seq) || 0,
              loc: String(p.world_location || '?'),
              commit: String(p.commit_id || '').slice(0, 8),
            },
          ]
        }
        if (topic === 'player/player/output') {
          if (p.kind === 'choices' && ((p.options as string[]) || []).length) {
            s.choices = p.options as string[]
            laneLog(s, 'player', `🔘 choices ×${(p.options as string[]).length}`)
          } else {
            laneLog(s, 'player', `📜 ${String(p.text || '').length} chars · ${esc(String(p.pace || ''))}`)
          }
        }
      }
      setDot(s, 'world', 'completed')
      break
    }
    case 'turn_done': {
      if (!m.success) laneLog(s, 'world', `<span class="lc-err">error: ${esc(String(m.error || '?'))}</span>`)
      const cur = curTurn(s)
      // 过程轨收尾:时长/soul 数/世界回合号钉在回合上(trace 先于
      // turn_done 落地,timeline 尾行就是本回合的 seq),轨原位收起。
      const doneSeq =
        s.rail.seq ?? (s.timeline.length ? s.timeline[s.timeline.length - 1].seq : undefined)
      const railSummary = s.rail.running
        ? {
            ms: s.rail.startedAt ? Math.max(0, ts - s.rail.startedAt) : 0,
            souls: Object.keys(s.turnSoulState).length,
            seq: doneSeq,
          }
        : null
      if (cur) patchTurn(s, { statusKey: null, done: true, cleaned: cleanupNarration(cur.raw), rail: railSummary })
      if (doneSeq != null) s.lastSeq = Math.max(s.lastSeq ?? 0, doneSeq)
      s.rail = { running: false, idx: 0, startedAt: null, activeSoul: null, seq: null }
      const cleaned = curTurn(s)?.cleaned
      if (cleaned && cleaned.choices.length) s.choices = cleaned.choices
      s.busyInput = false
      if (s.boot.active) s.boot = { ...s.boot, active: false, phase: 'done' }
      break
    }
    default:
      break
  }
}

export function stageReducer(state: StageState, action: StageAction): StageState {
  switch (action.type) {
    case 'busy':
      return { ...state, busyInput: action.v }
    case 'bootStart':
      return {
        ...state,
        boot: { active: true, phase: state.world ? 'waking' : 'connecting', worldAwake: false, preview: '' },
      }
    case 'bootDismiss':
      return { ...state, boot: { ...state.boot, active: false, phase: 'done' } }
    case 'seedSeq': {
      // /traces 播种:已知最新回合号(fresh=0)。只在更大时更新,别倒退。
      // 竞态防护(CI 实测):慢跑道上 turn_start 会先于种子到达,运行中的
      // 轨 seq 定格 null —— 迟到的种子必须回填,收起态摘要随之继承。
      const lastSeq = Math.max(state.lastSeq ?? 0, action.seq)
      const rail =
        state.rail.running && state.rail.seq == null
          ? { ...state.rail, seq: lastSeq + 1 }
          : state.rail
      return { ...state, lastSeq, rail }
    }
    case 'choices':
      return { ...state, choices: action.options }
    case 'event': {
      // Clone the mutated slices up front; applyEvent then patches this draft
      // in place and we hand it back as the new immutable state.
      const draft: StageState = {
        ...state,
        lanes: { ...state.lanes },
        ids: { ...state.ids },
      }
      applyEvent(draft, action.ev, action.t, action.dev, action.ts ?? Date.now())
      return draft
    }
    default:
      return state
  }
}
