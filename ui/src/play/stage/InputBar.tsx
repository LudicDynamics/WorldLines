// Bottom input: the player's line for the turn. Enter submits — except while
// an IME composition is in flight (CJK candidate confirmation), handled by the
// shared useImeGuard. Disabled while a turn is running.

import { useImeGuard } from '../../shared/ime'
import type { T } from './strings'

export function InputBar({
  draft,
  setDraft,
  busy,
  onSend,
  t,
}: {
  draft: string
  setDraft: (v: string) => void
  busy: boolean
  onSend: (text: string) => void
  t: T
}) {
  const { onCompositionEnd, isImeEnter } = useImeGuard()
  function submit() {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    onSend(text)
  }
  return (
    <div className="lc-inputbar">
      <input
        data-testid="stage-input"
        autoComplete="off"
        placeholder={t('input.placeholder')}
        value={draft}
        disabled={busy}
        onChange={(e) => setDraft(e.target.value)}
        onCompositionEnd={onCompositionEnd}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !isImeEnter(e)) {
            e.preventDefault()
            submit()
          }
        }}
      />
      <button data-testid="stage-send" disabled={busy} onClick={submit}>
        {t('send')}
      </button>
    </div>
  )
}
