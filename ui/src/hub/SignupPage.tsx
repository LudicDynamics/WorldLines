/**
 * SignupPage — full-page magic-link signup.
 *
 * Canonical signup entry for the whole platform. Other sites (www,
 * ludics.space, ludicdynamics.com) link here with ?return=<url> so
 * that, after the user verifies via the email link, the hub bounces
 * them back to where they came from.
 *
 * Trust model: ?return= MUST be validated against ALLOWED_RETURN_HOSTS
 * to prevent open-redirect abuse. The return URL is stashed in
 * sessionStorage (per-tab, scoped to hub.worldlines.gg) before the
 * magic link is requested, and consumed by auth.tsx after verify
 * succeeds — the magic-link URL itself does not carry the return so
 * the backend stays unchanged.
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Mail, ArrowRight, ChevronLeft } from 'lucide-react'
import { useAuth, IdentityError } from '../shared/auth'
import { useI18n } from '../shared/i18n'
import { track } from '../shared/analytics'

const ALLOWED_RETURN_HOSTS = new Set([
  'worldlines.gg',
  'www.worldlines.gg',
  'docs.worldlines.gg',
  'hub.worldlines.gg',
  'dev-hub.worldlines.gg',
  'ludics.space',
  'www.ludics.space',
  'ludicdynamics.com',
  'www.ludicdynamics.com',
  // local dev
  'localhost:5173',
  '127.0.0.1:5173',
  'localhost:4173',
  '127.0.0.1:4173',
])

export const PENDING_RETURN_KEY = 'rp-hub:pending-return'

export function sanitizeReturn(raw: string | null): string | null {
  if (!raw) return null
  try {
    const u = new URL(raw)
    const allowHttp =
      u.hostname === 'localhost' || u.hostname === '127.0.0.1'
    if (u.protocol !== 'https:' && !allowHttp) return null
    const hostKey = u.port ? `${u.hostname}:${u.port}` : u.hostname
    if (!ALLOWED_RETURN_HOSTS.has(hostKey)) return null
    // Strip any embedded credentials / fragment / extra noise; rebuild canonically.
    return `${u.protocol}//${u.host}${u.pathname}${u.search}`
  } catch {
    return null
  }
}

export function SignupPage() {
  const { t } = useI18n()
  const { signedIn, handle, requestLink, verify, passwordLogin } = useAuth()
  const [params] = useSearchParams()

  const returnUrl = useMemo(
    () => sanitizeReturn(params.get('return')),
    [params],
  )

  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  // 'login'  — email + password, the standard one-step sign-in (default).
  // 'email'  — email-only screen reached via "no password / forgot it":
  //            requests a magic link to register or reset a password.
  // 'sent'   — link emailed.
  const [phase, setPhase] = useState<'login' | 'email' | 'sent'>('login')
  const [devToken, setDevToken] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Password sign-in — no email round-trip. The pending-return bounce
  // mirrors the magic-link path so cross-site sign-ins still complete.
  async function loginWithPassword() {
    if (!email.trim() || !pw || busy) return
    setBusy(true)
    setNote(null)
    try {
      await passwordLogin(email.trim(), pw)
      track('signup_verified', { via: 'password' })
      const ret =
        (() => {
          try {
            return localStorage.getItem(PENDING_RETURN_KEY)
          } catch {
            return null
          }
        })() ?? null
      if (ret) {
        try {
          localStorage.removeItem(PENDING_RETURN_KEY)
        } catch {
          /* ignore */
        }
        window.location.replace(ret)
      }
      // No return URL → stay; the signed-in state + RegistrationGate
      // (if setup is pending) take over.
    } catch (e) {
      setNote(e instanceof IdentityError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  // Stash the return URL the moment we know it's safe — survives the
  // round-trip through email even if the user opens the magic link in
  // a fresh tab on the same origin.
  useEffect(() => {
    if (returnUrl) {
      try {
        localStorage.setItem(PENDING_RETURN_KEY, returnUrl)
      } catch {
        /* storage blocked — verify-side will fall back to staying on hub */
      }
    }
  }, [returnUrl])

  // Already signed in? Bounce immediately to where they came from.
  useEffect(() => {
    if (signedIn && returnUrl) {
      track('signup_already_signed_in')
      window.location.replace(returnUrl)
    }
  }, [signedIn, returnUrl])

  async function send() {
    if (!email.trim() || busy) return
    setBusy(true)
    setNote(null)
    try {
      const r = await requestLink(email.trim())
      track('signup_started', { from: returnUrl ?? 'hub' })
      setPhase('sent')
      setDevToken(r.devToken ?? null)
      // The 'sent' phase already shows the reason-specific copy; only add
      // the dev-mode hint when SMTP is off (a dev sign-in button appears).
      setNote(r.sent ? null : t('auth.devMode'))
    } catch (e) {
      setNote(
        e instanceof IdentityError && e.status === 0
          ? t('auth.unavailable')
          : e instanceof IdentityError
            ? e.message
            : String(e),
      )
    } finally {
      setBusy(false)
    }
  }

  async function devSignIn() {
    if (!devToken) return
    setBusy(true)
    try {
      await verify(devToken)
      track('signup_verified', { via: 'dev' })
      // AuthProvider's verify-effect consumes ?token=… elsewhere; here
      // we manually finish the journey because the dev path skips email.
      const ret =
        (() => {
          try {
            return localStorage.getItem(PENDING_RETURN_KEY)
          } catch {
            return null
          }
        })() ?? '/'
      try {
        localStorage.removeItem(PENDING_RETURN_KEY)
      } catch {
        /* ignore */
      }
      window.location.replace(ret)
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  // Public-launch gate: build-time flag. Defaults to false, so prod
  // bundles ship with signup gated to "coming soon" until the hub is
  // playable end-to-end. Local dev sets VITE_SIGNUP_ENABLED=true.
  const signupEnabled = import.meta.env.VITE_SIGNUP_ENABLED === 'true'

  if (!signupEnabled) {
    return (
      <main className="mx-auto max-w-md px-6 py-16">
        <div
          className="rounded-xl border p-6 shadow-xl"
          style={{
            background: 'var(--color-bg-card)',
            borderColor: 'var(--color-border-light)',
          }}
        >
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-accent)] mb-2">
            // coming soon
          </div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
            {t('signup.comingSoonTitle')}
          </h1>
          <p className="text-[13px] text-[var(--color-text-secondary)] mb-4">
            {t('signup.comingSoonBody')}
          </p>
          <a
            href="https://discord.gg/worldlines"
            target="_blank"
            rel="noreferrer"
            className="hover-btn inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md text-[13px] font-medium"
            style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
          >
            {t('signup.comingSoonCta')}
          </a>
        </div>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <div
        className="rounded-xl border p-6 shadow-xl"
        style={{
          background: 'var(--color-bg-card)',
          borderColor: 'var(--color-border-light)',
        }}
      >
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)] mb-2">
          {t('signup.title')}
        </h1>
        <p className="text-[13px] text-[var(--color-text-secondary)] mb-6">
          {t('signup.subtitle')}
        </p>

        {returnUrl && (
          <p
            className="mb-4 inline-flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]"
            title={returnUrl}
          >
            <ArrowRight className="w-3 h-3" />
            {t('signup.returnAfter')}: {new URL(returnUrl).host}
          </p>
        )}

        {signedIn ? (
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t('auth.signedInAs')} <strong>{handle}</strong>.{' '}
            {returnUrl ? t('signup.bouncing') : t('signup.goExplore')}
          </p>
        ) : phase === 'login' ? (
          // Standard sign-in: email + password, one step.
          <div className="flex flex-col gap-3">
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) =>
                e.key === 'Enter' && !e.nativeEvent.isComposing && loginWithPassword()
              }
              type="email"
              autoComplete="username"
              autoFocus
              placeholder={t('auth.email')}
              className="bg-transparent border border-[var(--color-border)] rounded-md px-3 py-2.5 text-[14px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent-dim)]"
            />
            <input
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              onKeyDown={(e) =>
                e.key === 'Enter' && !e.nativeEvent.isComposing && loginWithPassword()
              }
              type="password"
              autoComplete="current-password"
              placeholder={t('auth.password')}
              className="bg-transparent border border-[var(--color-border)] rounded-md px-3 py-2.5 text-[14px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent-dim)]"
            />
            <button
              onClick={loginWithPassword}
              disabled={busy || !email.trim() || !pw}
              className="hover-btn inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-md text-[13px] font-medium disabled:opacity-40"
              style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
            >
              {t('auth.loginBtn')}
            </button>
            {/* No password yet, or forgot it → email-link register/reset. */}
            <button
              onClick={() => {
                setPhase('email')
                setNote(null)
              }}
              disabled={busy}
              className="hover-link inline-flex items-center justify-center gap-2 px-3 py-1.5 text-[12px] text-[var(--color-text-secondary)] disabled:opacity-40"
            >
              <Mail className="w-3.5 h-3.5" /> {t('auth.noPwRegister')}
            </button>
            {note && (
              <p className="text-[12px] text-[var(--color-text-tertiary)]">
                {note}
              </p>
            )}
          </div>
        ) : phase === 'email' ? (
          // Email-only → request a magic link to register / reset password.
          <div className="flex flex-col gap-3">
            <button
              onClick={() => {
                setPhase('login')
                setNote(null)
              }}
              className="hover-link self-start inline-flex items-center gap-1 text-[11px] text-[var(--color-text-tertiary)]"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> {t('auth.loginBtn')}
            </button>
            <p className="text-[13px] text-[var(--color-text-secondary)]">
              {t('auth.registerHint')}
            </p>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) =>
                e.key === 'Enter' && !e.nativeEvent.isComposing && send()
              }
              type="email"
              autoFocus
              placeholder={t('auth.email')}
              className="bg-transparent border border-[var(--color-border)] rounded-md px-3 py-2.5 text-[14px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent-dim)]"
            />
            <button
              onClick={send}
              disabled={busy || !email.trim()}
              className="hover-btn inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-md text-[13px] font-medium disabled:opacity-40"
              style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
            >
              <Mail className="w-3.5 h-3.5" /> {t('auth.registerViaLink')}
            </button>
            {note && (
              <p className="text-[12px] text-[var(--color-text-tertiary)]">
                {note}
              </p>
            )}
          </div>
        ) : (
          // 'sent' — link emailed (register or reset).
          <div className="flex flex-col gap-3">
            <p className="text-[13px] text-[var(--color-text-secondary)]">
              {t('auth.linkSetup')}
            </p>
            {note && (
              <p className="text-[12px] text-[var(--color-text-tertiary)]">
                {note}
              </p>
            )}
            {devToken && (
              <button
                onClick={devSignIn}
                disabled={busy}
                className="hover-btn rounded-md px-3 py-2.5 text-[13px] font-medium disabled:opacity-40"
                style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
              >
                {t('auth.devSignIn')}
              </button>
            )}
          </div>
        )}

        <p className="mt-6 text-[11px] text-[var(--color-text-tertiary)]">
          {t('signup.legalNote')}
        </p>
      </div>
    </main>
  )
}

export default SignupPage
