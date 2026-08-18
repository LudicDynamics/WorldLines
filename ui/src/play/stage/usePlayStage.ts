// The PlayStage controller: opens the /events stream, feeds every message into
// stageReducer, and owns the side-effecting bits the reducer can't (the boot
// lifecycle timers, resume/replay fetches, POST /cmd + /rollback + /start).
// Components read `state` and call the returned actions.

import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useStageBackend, type StageBackendCaps } from './backend'
import { renderReplayTurn, type ReplayBlock } from './replay'
import { initialStageState, stageReducer } from './stageState'
import { useStageStrings, type T } from './strings'

// After the first narration tokens flow, hold the boot theater a beat so the
// player sees the opening line forming, then fade into the full stage (D7).
const BOOT_NARRATE_HOLD_MS = 1400
// Safety net: if a fresh game never produces a turn (no LLM configured, an
// engine error), reveal the stage anyway instead of a stuck theater.
// 慢模型(多智能体开场,如 Kimi K3 要 world-agent + 每个 soul 各一次 LLM)
// 常超 12s;拉到 30s 让开机剧场多撑会儿。真正兜底靠 PlayStage 的「生成中」
// 提示条(跟 rail.running 走,boot 消失后接管直到 turn_done)。
const BOOT_SAFETY_MS = 30_000

export type PlayStageApi = {
  t: T
  state: ReturnType<typeof stageReducer>
  caps: StageBackendCaps
  dev: boolean
  setDev: (v: boolean) => void
  noSession: boolean
  resume: ReplayBlock | null
  replay: { open: boolean; idx: number; total: number; block: ReplayBlock | null }
  send: (text: string) => Promise<void>
  rollback: (commit: string, turnSeq?: number) => Promise<void>
  openReplay: () => Promise<void>
  stepReplay: (delta: number) => Promise<void>
  closeReplay: () => void
}

export function usePlayStage(): PlayStageApi {
  const backend = useStageBackend()
  const { t } = useStageStrings()
  const [state, dispatch] = useReducer(stageReducer, initialStageState)
  const [dev, setDev] = useState(false)
  const [noSession, setNoSession] = useState(false)
  const [resume, setResume] = useState<ReplayBlock | null>(null)
  const [replay, setReplay] = useState<{
    open: boolean
    idx: number
    total: number
    rows: { i: number }[]
    block: ReplayBlock | null
  }>({ open: false, idx: -1, total: 0, rows: [], block: null })

  // Refs so the once-mounted EventSource handler reads live t / dev / places.
  // Written after commit rather than during render (react-hooks/refs): every
  // reader is an async callback or event handler, so a post-commit write is
  // the same value they would have seen — and useRef seeds the first one.
  const tRef = useRef(t)
  const devRef = useRef(dev)
  const placesRef = useRef(state.places)
  useEffect(() => {
    tRef.current = t
    devRef.current = dev
    placesRef.current = state.places
  })

  // ── 事件流(local=EventSource /events;hosted=网关流适配)────────────────
  useEffect(() => {
    const close = backend.openEvents(
      (ev) => dispatch({ type: 'event', ev, t: tRef.current, dev: devRef.current, ts: Date.now() }),
      () => setNoSession(true),
    )
    return close
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── boot + resume: decide once whether this is a fresh game ──────────────
  useEffect(() => {
    let alive = true
    ;(async () => {
      // 无 trace 面的后端(现 hosted 网关):不播种、不判 resume —— 会话由
      // PrePlay 刚创建,直接跑开机剧场;seq 从 turn_start 事件侧收敛。
      if (!backend.caps.traces) {
        dispatch({ type: 'seedSeq', seq: 0 })
        dispatch({ type: 'bootStart' })
        backend.postStart()
        return
      }
      const turns = await backend.getTraces()
      if (!alive) return
      // 播种世界回合号(niko 实测:「TURN · 进行中」号位空白)—— resume 时
      // 取最后一行的 turn_seq,fresh 游戏播 0(下一回合就是 TURN 1)。
      const last = turns.length ? turns[turns.length - 1] : null
      dispatch({ type: 'seedSeq', seq: Number(last?.turn_seq ?? turns.length) || 0 })
      if (turns.length === 0) {
        // Fresh game → run the opening theater against real progress.
        dispatch({ type: 'bootStart' })
        backend.postStart()
      } else {
        // Continuing → drop the last turn in as "where you left off".
        const tr = await backend.getTrace(turns[turns.length - 1].i)
        if (alive && tr) setResume(renderReplayTurn(tr, { resume: true }, tRef.current, placesRef.current))
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── boot dismissal: fade after the first line, plus a safety timeout ─────
  // 进场 initial 动画覆盖整个进场:「world-agent 苏醒 + 在场灵魂并行」都属于
  // 进场,不能被超时截断当成「已进游戏」(niko 反馈:souls 并行阶段被误归类)。
  // 只有还卡在 connecting(连引擎都没连上)才用超时兜底退出;一旦开跑
  // (waking/souls/narrating),交给 narrating fade + turn_done(stageState 里
  // turn_done 会置 boot.active=false)关闭 —— souls 并行阶段 boot 全程持续到出字。
  useEffect(() => {
    if (!state.boot.active) return
    if (state.boot.phase !== 'connecting') return
    const safety = setTimeout(() => dispatch({ type: 'bootDismiss' }), BOOT_SAFETY_MS)
    return () => clearTimeout(safety)
  }, [state.boot.active, state.boot.phase])

  useEffect(() => {
    if (state.boot.active && state.boot.phase === 'narrating') {
      const fade = setTimeout(() => dispatch({ type: 'bootDismiss' }), BOOT_NARRATE_HOLD_MS)
      return () => clearTimeout(fade)
    }
  }, [state.boot.active, state.boot.phase])

  // ── actions ──────────────────────────────────────────────────────────────
  const send = useCallback(async (text: string) => {
    const clean = text.trim()
    if (!clean) return
    dispatch({ type: 'busy', v: true })
    dispatch({ type: 'choices', options: [] })
    const r = await backend.postCmd(clean)
    if (r.busy) {
      dispatch({ type: 'busy', v: false })
      alert(tRef.current('turn.in_progress'))
    } else if (!r.ok && r.error) {
      // 后端边界错误(hosted 路由的 429 配额墙等):明说,不留转圈。
      dispatch({ type: 'busy', v: false })
      alert(r.error)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const rollback = useCallback(async (commit: string, turnSeq?: number) => {
    if (!commit) return
    if (!confirm(tRef.current('rollback.confirm', { turn: turnSeq ?? '?' }))) return
    const r = await backend.postRollback(commit)
    if (!r.ok) {
      alert(tRef.current('rollback.failed') + (r.error || ''))
      return
    }
    // Rolled back onto a fresh branch — reload to re-sync the whole surface.
    location.reload()
  }, [backend])

  const openReplay = useCallback(async () => {
    const rows = await backend.getTraces()
    if (!rows.length) {
      alert(tRef.current('replay.none'))
      return
    }
    setReplay({ open: true, idx: -1, total: rows.length, rows, block: null })
    // step to the first turn
    const tr = await backend.getTrace(rows[0].i)
    setReplay((r) => ({
      ...r,
      idx: 0,
      block: tr ? renderReplayTurn(tr, {}, tRef.current, placesRef.current) : null,
    }))
  }, [backend])

  const stepReplay = useCallback(async (delta: number) => {
    setReplay((r) => {
      if (!r.rows.length) return r
      const idx = Math.max(0, Math.min(r.rows.length - 1, r.idx + delta))
      backend.getTrace(r.rows[idx].i).then((tr) =>
        setReplay((rr) => ({
          ...rr,
          idx,
          block: tr ? renderReplayTurn(tr, {}, tRef.current, placesRef.current) : rr.block,
        })),
      )
      return { ...r, idx }
    })
  }, [backend])

  const closeReplay = useCallback(() => setReplay((r) => ({ ...r, open: false, block: null })), [])

  return {
    t,
    state,
    caps: backend.caps,
    dev,
    setDev,
    noSession,
    resume,
    replay: { open: replay.open, idx: replay.idx, total: replay.total, block: replay.block },
    send,
    rollback,
    openReplay,
    stepReplay,
    closeReplay,
  }
}
