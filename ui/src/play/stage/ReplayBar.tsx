// Header controls: the ⏪ REPLAY step-through (◀ position ▶ + ⟲ rollback),
// and a ⚙ settings popover whose one toggle reveals each agent's raw
// reasoning (off by default — machine internals that break immersion).

import { useEffect, useRef, useState } from 'react'
import type { T } from './strings'

export function SettingsPopover({ dev, setDev, t }: { dev: boolean; setDev: (v: boolean) => void; t: T }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [open])
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        title={t('settings.title')}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
      >
        ⚙
      </button>
      {open ? (
        <div className="lc-pop" onClick={(e) => e.stopPropagation()}>
          <div className="ptitle">{t('settings.title')}</div>
          <label>
            <input type="checkbox" checked={dev} onChange={(e) => setDev(e.target.checked)} />
            <span>
              <span className="plabel">{t('settings.dev_reasoning')}</span>
              <br />
              <span className="pdesc">{t('settings.dev_reasoning_desc')}</span>
            </span>
          </label>
        </div>
      ) : null}
    </div>
  )
}

export function ReplayBar({
  open,
  idx,
  total,
  onOpen,
  onStep,
  onClose,
  onRollback,
  canRollback,
  t,
}: {
  open: boolean
  idx: number
  total: number
  onOpen: () => void
  onStep: (delta: number) => void
  onClose: () => void
  onRollback: () => void
  canRollback: boolean
  t: T
}) {
  if (!open) {
    return (
      <button title={t('replay.title')} onClick={onOpen}>
        ⏪ {t('replay.btn')}
      </button>
    )
  }
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
      <button onClick={() => onStep(-1)}>◀</button>
      <span className="lc-meta">
        {idx + 1}/{total}
      </span>
      <button onClick={() => onStep(1)}>▶</button>
      <button title={t('rollback.title')} disabled={!canRollback} onClick={onRollback}>
        {t('rollback.btn')}
      </button>
      <button onClick={onClose}>✕</button>
    </span>
  )
}
