// 开机剧场 (D7) — replaces the old loading loop with the real opening
// sequence, driven entirely by the /events stream (no faked progress):
//
//   connecting → waking     world-agent awakens on the first thinking/turn
//              → souls       each soul lights up as its soul_status arrives
//              → narrating   the first narration tokens stream in, in place
//              → (fade)      the full stage cross-fades in
//
// This is a pure view over the stageState boot machine + the live lanes; the
// phase transitions and dismissal timing live in stageState / usePlayStage.

import { useEffect, useRef, useState } from 'react'
import { imageUrl } from '../stage/stageClient'
import type { Boot, Lane } from '../stage/stageState'
import type { T } from '../stage/strings'

const LEAVE_MS = 600

function BootSoul({ lane, lit }: { lane: Lane; lit: boolean }) {
  const initial = (lane.name || '?').slice(0, 1)
  const [broken, setBroken] = useState(false)
  return (
    <div className={`boot-soul${lit ? ' lit' : ''}`}>
      {broken ? (
        <div className="avatar">{initial}</div>
      ) : (
        <img className="avatar" src={imageUrl('soul', lane.id)} alt="" onError={() => setBroken(true)} />
      )}
      <span className="sname">{lane.name}</span>
    </div>
  )
}

export function BootTheater({
  boot,
  worldName,
  lanes,
  order,
  turnSoulState,
  t,
}: {
  boot: Boot
  worldName: string
  lanes: Record<string, Lane>
  order: string[]
  turnSoulState: Record<string, { name: string; state: string }>
  t: T
}) {
  // Keep the theater mounted for one fade after `active` flips off so the
  // cross-fade to the stage actually plays.
  const [leaving, setLeaving] = useState(false)
  const [gone, setGone] = useState(false)
  const wasActive = useRef(boot.active)
  useEffect(() => {
    if (wasActive.current && !boot.active) {
      setLeaving(true)
      const tm = setTimeout(() => setGone(true), LEAVE_MS)
      return () => clearTimeout(tm)
    }
    wasActive.current = boot.active
    if (boot.active) {
      setLeaving(false)
      setGone(false)
    }
  }, [boot.active])

  if (gone || (!boot.active && !leaving)) return null

  const soulLanes = order.map((id) => lanes[id]).filter((l): l is Lane => !!l && l.kind === 'soul')
  const litOf = (l: Lane) =>
    l.dot === 'running' || l.dot === 'completed' || l.dot === 'degraded' || !!turnSoulState[l.id]

  const line =
    boot.phase === 'narrating'
      ? t('boot.first_words')
      : boot.phase === 'souls'
        ? t('boot.souls_lighting')
        : t('boot.waking')

  return (
    <div className={`lc-boot${leaving ? ' leaving' : ''}`} data-testid="stage-boot">
      {worldName ? <div className="boot-world">{worldName}</div> : null}
      <div className={`boot-step${boot.worldAwake ? ' on' : ''}`}>
        <span className="mark" />
        <span>{boot.worldAwake ? t('boot.world_awake') : line}</span>
      </div>
      {soulLanes.length ? (
        <div className="boot-souls">
          {soulLanes.map((l) => (
            <BootSoul key={l.id} lane={l} lit={litOf(l)} />
          ))}
        </div>
      ) : null}
      {boot.preview ? (
        <div className="boot-preview">
          {boot.preview}
          <span className="boot-caret">&nbsp;</span>
        </div>
      ) : (
        <div className="boot-step">
          <span>{boot.phase === 'narrating' ? t('boot.enter') : line}</span>
        </div>
      )}
    </div>
  )
}
