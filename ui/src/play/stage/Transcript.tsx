// Main column: the narrative flow. Player HUD strip, an optional "where you
// left off" resume block, the live replay-step block, then one block per turn
// (your line · orchestration banner while waiting · streamed narration that
// settles into speech/thought-formatted prose · an inline ↶ roll-back once the
// turn's commit is known).

import { useEffect, useRef, type ReactNode } from 'react'
import { stripControl } from './narration'
import type { ReplayBlock } from './replay'
import type { Hp } from './events'
import type { Lane, Rail, Turn } from './stageState'
import type { T } from './strings'
import { RailSummary, TurnProgressRail } from './TurnProgressRail'

function PlayerHud({
  player,
  places,
  t,
}: {
  player: { name?: string; klass?: string; location?: string; hp?: Hp }
  places: Record<string, string>
  t: T
}) {
  const name = player.name || t('role.player')
  const klass = player.klass ? ` · ${player.klass}` : ''
  const placeRaw = String(player.location || '').replace(/^loc:/, '')
  const place = places[placeRaw] || placeRaw
  const hp = player.hp || {}
  if (!player.name && !place) return null
  return (
    <div className="lc-hud" data-testid="stage-hud">
      <span className="hud-name">{name + klass}</span>
      {place ? <span className="hud-place">📍 {place}</span> : null}
      {hp.current != null && hp.max ? (
        <span className="hud-hp">
          ❤ {hp.current}/{hp.max}
          <span className="hud-bar">
            <span
              className="hud-fill"
              style={{ width: `${Math.max(0, Math.min(100, (100 * hp.current) / hp.max))}%` }}
            />
          </span>
        </span>
      ) : null}
    </div>
  )
}

function ReplayView({ block, resume, onRollback }: { block: ReplayBlock; resume?: boolean; onRollback: (c: string, s?: number) => void }) {
  return (
    <div className={`lc-replay${resume ? ' resume' : ''}`}>
      <div dangerouslySetInnerHTML={{ __html: block.html }} />
      {block.rollback ? (
        <button className="lc-rb-inline" onClick={() => onRollback(block.rollback!.commit, block.rollback!.turnSeq)}>
          ↶
        </button>
      ) : null}
    </div>
  )
}

function TurnBlock({ turn, t, onRollback }: { turn: Turn; t: T; onRollback: (c: string, s?: number) => void }) {
  return (
    <div className="lc-turn">
      {turn.userText ? <div className="lc-you">{turn.userText}</div> : null}
      {/* 旧的 lc-status 横幅退役(样式类 .lc-status 仍在役:PlayStage 生成条复用,勿删 CSS) — 等待期的全部过程展示归 TurnProgressRail
          (feed 尾部,DESIGN-TOKENS §三),niko:严格按 pencil 设计。 */}
      {turn.done && turn.cleaned ? (
        <>
          <div className="lc-narration" dangerouslySetInnerHTML={{ __html: turn.cleaned.html }} />
          {turn.cleaned.table ? (
            <details className="lc-clue">
              <summary>{t('clue.label')}</summary>
              <pre>{turn.cleaned.table}</pre>
            </details>
          ) : null}
        </>
      ) : (
        <div className="lc-narration">{stripControl(turn.raw)}</div>
      )}
      {turn.rollback ? (
        <button
          className="lc-rb-inline"
          title={t('rollback.title')}
          onClick={() => onRollback(turn.rollback!.commit, turn.rollback!.turnSeq)}
        >
          ↶
        </button>
      ) : null}
      {turn.done && turn.rail ? <RailSummary rail={turn.rail} t={t} /> : null}
    </div>
  )
}

export function Transcript({
  turns,
  player,
  places,
  resume,
  replayBlock,
  boot,
  bootActive,
  rail,
  turnSoulState,
  lanes,
  castLocs,
  t,
  onRollback,
}: {
  turns: Turn[]
  player: { name?: string; klass?: string; location?: string; hp?: Hp }
  places: Record<string, string>
  resume: ReplayBlock | null
  replayBlock: ReplayBlock | null
  boot?: ReactNode
  bootActive?: boolean
  rail: Rail
  turnSoulState: Record<string, { name: string; state: string }>
  lanes: Record<string, Lane>
  castLocs: Record<string, string>
  t: T
  onRollback: (c: string, s?: number) => void
}) {
  const feedRef = useRef<HTMLDivElement>(null)
  // Follow the tail as narration streams, like the classic feed.
  useEffect(() => {
    const el = feedRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns, replayBlock, rail.idx])

  return (
    <>
      <PlayerHud player={player} places={places} t={t} />
      <div className="lc-feed" data-testid="stage-feed" ref={feedRef}>
        {resume ? <ReplayView block={resume} resume onRollback={onRollback} /> : null}
        {replayBlock ? <ReplayView block={replayBlock} onRollback={onRollback} /> : null}
        {turns.map((turn) => (
          <TurnBlock key={turn.id} turn={turn} t={t} onRollback={onRollback} />
        ))}
        {/* 运行中的回合过程轨 — 钉在叙事流尾部,开机剧场覆盖期间不重复展示 */}
        <TurnProgressRail
          rail={bootActive ? { ...rail, running: false } : rail}
          turnSoulState={turnSoulState}
          lanes={lanes}
          castLocs={castLocs}
          playerLoc={player.location}
          t={t}
        />
        {boot}
      </div>
    </>
  )
}
