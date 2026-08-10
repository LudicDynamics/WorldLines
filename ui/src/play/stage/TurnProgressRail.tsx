// 回合过程轨(DESIGN-TOKENS §三,pencil 画布定稿;状态机校准自 niko 真实
// 存档的 bus_messages 顺序 — 见 stageState.ts Rail 注释)。回合运行期间钉在
// 叙事流尾部:四阶段 forward-only 点亮;在场 soul 每人一枚芯片(niko 规则:
// 在场的每一位都有自己的状态),只有能"积极证明离场"的才进幕后聚合 ——
// 位置格式混乱(canonical/bare/展示文本并存)时宁多芯片不误归幕后。
// 思考尾巴永远只有一条(活跃 soul 的 soul_psyche.inner_voice)。回合完成后由
// Transcript 渲染收起态一行(turn.rail 摘要),本组件只负责运行态。

import { useEffect, useState } from 'react'
import { useStageBackend } from './backend'
import { RAIL_STAGES, type Lane, type Rail, type RailStageId } from './stageState'
import type { T } from './strings'

const STAGE_KEY: Record<RailStageId, string> = {
  world: 'rail.stage_world',
  souls: 'rail.stage_souls',
  ruling: 'rail.stage_ruling',
  narrate: 'rail.stage_narrate',
}

// 位置归一:canonical "T001/gate_north" → {town,node};bare "gate_north" →
// {node};含 "·" 的展示文本(如 "T004·碧石镇·旅店")视为不可比。
function normLoc(loc: string | undefined): { town: string; node: string; comparable: boolean } {
  const s = String(loc || '')
    .replace(/^loc:/, '')
    .trim()
  if (!s || s.includes('·')) return { town: '', node: '', comparable: false }
  if (s.includes('/')) {
    const [town, ...rest] = s.split('/')
    return { town, node: rest.join('/'), comparable: true }
  }
  return { town: '', node: s, comparable: true }
}

// 离场判定:只在双方都可比、且镇或节点有确凿差异时才算离场(积极证据
// 原则 — 同位置裁判的 refuse-only-on-positive-evidence;niko 实测:rowan 的
// run_state 位置是展示文本,曾被误归幕后)。
function isAway(soulLoc: string | undefined, playerLoc: string | undefined): boolean {
  const a = normLoc(soulLoc)
  const p = normLoc(playerLoc)
  if (!a.comparable || !p.comparable) return false
  if (a.town && p.town && a.town !== p.town) return true
  if (a.node && p.node && a.node !== p.node) return true
  return false
}

function Timer({ startedAt }: { startedAt: number | null }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(id)
  }, [])
  if (!startedAt) return null
  return <span className="lc-rail-time">{((now - startedAt) / 1000).toFixed(1)}s</span>
}

function StageDot({ st }: { st: 'done' | 'active' | 'wait' }) {
  return (
    <span className={`lc-rail-dot ${st}`}>
      {st === 'done' ? '✓' : st === 'active' ? <span className="pulse" /> : null}
    </span>
  )
}

function SoulChip({ lane, state, t }: { lane: Lane; state: string; t: T }) {
  const { imageUrl } = useStageBackend()
  const running = state === 'running'
  const done = state === 'completed' || state === 'degraded'
  return (
    <span className={`lc-rail-chip${running ? ' running' : ''}`} data-testid="rail-chip">
      <img
        className="av"
        src={imageUrl('soul', lane.id)}
        alt=""
        onError={(e) => {
          e.currentTarget.style.display = 'none'
        }}
      />
      {lane.name}
      {done ? ' ✓' : running ? ` · ${t('rail.acting_suffix')}` : ''}
    </span>
  )
}

export function TurnProgressRail({
  rail,
  turnSoulState,
  lanes,
  castLocs,
  playerLoc,
  t,
}: {
  rail: Rail
  turnSoulState: Record<string, { name: string; state: string }>
  lanes: Record<string, Lane>
  castLocs: Record<string, string>
  playerLoc?: string
  t: T
}) {
  if (!rail.running) return null

  const soulIds = Object.keys(turnSoulState)
  const all = soulIds.length
  const isDone = (id: string) =>
    turnSoulState[id].state === 'completed' || turnSoulState[id].state === 'degraded'
  const doneN = soulIds.filter(isDone).length

  // 在场每人一枚芯片(niko 规则);能积极证明离场的才聚合。
  const chipIds = soulIds.filter((id) => !isAway(castLocs[id], playerLoc))
  const restIds = soulIds.filter((id) => !chipIds.includes(id))
  const restDone = restIds.filter(isDone).length

  // 无 soul 的世界(orch):只有 世界思考 → 叙事成稿 两段。
  const hasSouls = all > 0 || Object.values(lanes).some((l) => l.kind === 'soul')
  const stages = hasSouls ? RAIL_STAGES : (['world', 'narrate'] as RailStageId[])
  const curIdx = hasSouls ? Math.min(rail.idx, stages.length - 1) : rail.idx >= 3 ? 1 : 0

  const active = rail.activeSoul ? lanes[rail.activeSoul] : null
  const voice = String(active?.psyche?.inner_voice || '').trim()
  const tease = active
    ? voice
      ? `${active.name}:${voice}`
      : t('rail.acting', { name: active.name })
    : null

  return (
    <div className="lc-rail" data-testid="stage-rail">
      <div className="lc-rail-head">
        <span className="lc-rail-title" data-testid="rail-title">
          {rail.seq != null
            ? t('rail.turn_running', { seq: rail.seq })
            : t('rail.turn_running_pending')}
        </span>
        <Timer startedAt={rail.startedAt} />
      </div>
      <div className="lc-rail-stages">
        {stages.map((sid, i) => {
          const st = i < curIdx ? 'done' : i === curIdx ? 'active' : 'wait'
          const label =
            sid === 'souls' && all ? `${t(STAGE_KEY[sid])} ${doneN}/${all}` : t(STAGE_KEY[sid])
          return (
            <span key={sid} className="lc-rail-seg" data-stage={sid} data-st={st}>
              <StageDot st={st} />
              <span className={`lc-rail-name ${st}`}>{label}</span>
              {i < stages.length - 1 ? (
                <span className={`lc-rail-link${st === 'done' ? ' lit' : ''}`} />
              ) : null}
            </span>
          )
        })}
      </div>
      {chipIds.length || restIds.length ? (
        <div className="lc-rail-souls">
          {chipIds.map((id) =>
            lanes[id] ? <SoulChip key={id} lane={lanes[id]} state={turnSoulState[id].state} t={t} /> : null,
          )}
          {restIds.length ? (
            <span className="lc-rail-chip rest" data-testid="rail-backstage">
              {t('rail.backstage', { n: restIds.length, done: restDone })}
            </span>
          ) : null}
        </div>
      ) : null}
      {tease ? (
        <div className="lc-rail-tease" data-testid="rail-tease">
          {tease}▊
        </div>
      ) : null}
    </div>
  )
}

// 收起态:回合完成后的一行摘要(turn.rail),点击展开回看最终状态。
export function RailSummary({
  rail,
  t,
}: {
  rail: { ms: number; souls: number; seq?: number }
  t: T
}) {
  const [open, setOpen] = useState(false)
  const secs = (rail.ms / 1000).toFixed(1)
  return (
    <div className="lc-rail-summary" data-testid="stage-rail-summary" onClick={() => setOpen(!open)}>
      <span>{t('rail.summary', { seq: rail.seq ?? '?', n: rail.souls, s: secs })}</span>
      <span className="chev">{open ? '▴' : '▾'}</span>
      {open ? (
        <span className="lc-rail-summary-detail">
          {t('rail.stage_world')} ✓ ·{' '}
          {rail.souls
            ? `${t('rail.stage_souls')} ${rail.souls}/${rail.souls} ✓ · ${t('rail.stage_ruling')} ✓ · `
            : ''}
          {t('rail.stage_narrate')} ✓
        </span>
      ) : null}
    </div>
  )
}
