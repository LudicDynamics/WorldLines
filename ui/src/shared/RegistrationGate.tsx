/**
 * One-time registration gate. Shows site-wide (blocking modal) when the
 * signed-in account hasn't completed registration: pick a handle /
 * display name and set a password for everyday sign-in. The email is
 * already verified by the magic link that minted this session. "Later"
 * defers for this browser session only.
 */
import { useState } from 'react'
import { useAuth, IdentityError } from './auth'
import { useI18n } from './i18n'

const DEFER_KEY = 'rp-hub:setup-deferred'

export function RegistrationGate() {
  const { signedIn, needsSetup, handle, completeRegistration } = useAuth()
  const { t } = useI18n()
  const [h, setH] = useState('')
  const [name, setName] = useState('')
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [deferred, setDeferred] = useState(() => {
    try {
      return sessionStorage.getItem(DEFER_KEY) === '1'
    } catch {
      return false
    }
  })

  if (!signedIn || !needsSetup || deferred) return null

  async function submit() {
    if (busy || pw.length < 8) return
    setBusy(true)
    setErr('')
    try {
      await completeRegistration({
        password: pw,
        handle: h.trim() || undefined,
        displayName: name.trim() || undefined,
      })
    } catch (e) {
      setErr(e instanceof IdentityError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function defer() {
    setDeferred(true)
    try {
      sessionStorage.setItem(DEFER_KEY, '1')
    } catch {
      /* ignore */
    }
  }

  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center px-4"
      style={{ background: 'rgba(6,6,8,0.82)', backdropFilter: 'blur(4px)' }}
    >
      <div
        className="w-full max-w-[420px] rounded-lg border p-6 flex flex-col gap-4"
        style={{
          background: 'var(--color-bg-card)',
          borderColor: 'var(--color-border-light)',
        }}
      >
        <h2
          className="text-[18px] text-[var(--color-text-primary)]"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          {t('setup.title')}
        </h2>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t('setup.sub')}
        </p>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--color-text-tertiary)]">
            {t('setup.handle')}
          </span>
          <input
            value={h}
            onChange={(e) => setH(e.target.value)}
            placeholder={handle ?? ''}
            className="px-3 py-2 rounded-md border bg-transparent text-[14px] text-[var(--color-text-primary)] outline-none"
            style={{ borderColor: 'var(--color-border-light)' }}
            data-gramm="false"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--color-text-tertiary)]">
            {t('setup.displayName')}
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="px-3 py-2 rounded-md border bg-transparent text-[14px] text-[var(--color-text-primary)] outline-none"
            style={{ borderColor: 'var(--color-border-light)' }}
            data-gramm="false"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--color-text-tertiary)]">
            {t('setup.password')}
          </span>
          <input
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) submit()
            }}
            autoComplete="new-password"
            className="px-3 py-2 rounded-md border bg-transparent text-[14px] text-[var(--color-text-primary)] outline-none"
            style={{ borderColor: 'var(--color-border-light)' }}
          />
        </label>
        {err && (
          <span className="text-[12px]" style={{ color: 'var(--color-danger, #e5484d)' }}>
            {err}
          </span>
        )}
        <button
          onClick={submit}
          disabled={busy || pw.length < 8}
          className="hover-btn px-5 py-2.5 rounded-md text-[14px] font-semibold disabled:opacity-40"
          style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
        >
          {t('setup.submit')}
        </button>
        <button
          onClick={defer}
          className="hover-link self-center text-[12px] text-[var(--color-text-tertiary)]"
        >
          {t('setup.later')}
        </button>
      </div>
    </div>
  )
}
