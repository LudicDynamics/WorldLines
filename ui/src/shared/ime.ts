/**
 * IME-safe Enter detection for CJK input.
 *
 * Chinese/Japanese/Korean mobile keyboards confirm a conversion with
 * Enter; that keypress must NOT submit the form. Three signals, because
 * browsers disagree:
 *  - `isComposing` — Chrome/Android fire the confirm-Enter during
 *    composition (the existing guard).
 *  - `keyCode === 229` — legacy "IME processing" marker some Android
 *    keyboards still emit with isComposing unset.
 *  - recent `compositionend` — iOS Safari fires the confirm-Enter
 *    *after* compositionend with isComposing=false; treat any Enter
 *    landing within 100 ms of a compositionend as part of the IME.
 */
import { useCallback, useRef } from 'react'

export function useImeGuard() {
  const lastEnd = useRef(0)
  const onCompositionEnd = useCallback(() => {
    lastEnd.current = Date.now()
  }, [])
  const isImeEnter = useCallback((e: React.KeyboardEvent) => {
    const ne = e.nativeEvent as KeyboardEvent & { keyCode?: number }
    return (
      ne.isComposing ||
      ne.keyCode === 229 ||
      Date.now() - lastEnd.current < 100
    )
  }, [])
  return { onCompositionEnd, isImeEnter }
}
