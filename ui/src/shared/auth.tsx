/**
 * Global Hub auth state. One source of truth so the account control
 * lives in the header (top-right) while the create studio reuses the
 * same session. Wraps lib/identity; degrades quietly when the
 * identity gateway is unreachable.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import {
  requestLink as apiRequestLink,
  verify as apiVerify,
  passwordLogin as apiPasswordLogin,
  completeRegistration as apiCompleteRegistration,
  me as apiMe,
  signOut as apiSignOut,
  sessionToken,
  IdentityError,
} from './identity'
import { track, identify, resetIdentity } from './analytics'
import { computeOrigin } from '../play/playClient'

type AuthCtx = {
  handle: string | null
  tier: string
  signedIn: boolean
  /** 服务端声明的鉴权替身模式(HUB_AUTH_REQUIRED=0 的本地/dev 栈):
   *  同一 bundle 通吃各环境 —— stub 下以 dev 账户视作已登录,
   *  登录/登出流整体退位;端点缺席/非 200 一律按 required(fail-safe)。 */
  devStub: boolean
  /** account hasn't completed the one-time registration step yet */
  needsSetup: boolean
  /** returns a dev token when SMTP is not configured (local only) */
  requestLink: (email: string) => Promise<{ sent: boolean; devToken?: string }>
  verify: (token: string) => Promise<void>
  passwordLogin: (email: string, password: string) => Promise<void>
  completeRegistration: (opts: {
    password: string
    handle?: string
    displayName?: string
  }) => Promise<void>
  signOut: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

// Per-page-load guard: a magic-link token must only be verified ONCE,
// even if useEffect fires twice (React StrictMode in dev, navigation,
// browser link-prefetcher). Without this guard the first verify marks
// the link used; the second hits 400; the user ends up with no
// localStorage session despite the server having issued one.
const _consumedTokens = new Set<string>()

/** Bearer → HttpOnly play cookie(SANDBOX-AUDIT 🔴-3)。
 *  EventSource(/events SSE)带不了 Authorization,真实鉴权环境下
 *  登录成功后用 Bearer 换一枚 path=/api/v1/play 的 cookie,SSE 靠它
 *  认账户。fire-and-forget:stub 栈/老网关缺此端点都静默无害。 */
function exchangePlayCookie(): void {
  const tok = sessionToken()
  if (!tok) return
  // 分层部署(页面在 CloudFront、API 在 compute 域)是同站跨源:
  // credentials:'include' 才能让 Set-Cookie 落地(SameSite=Lax 放行同站)。
  fetch(`${computeOrigin()}/api/v1/play/auth/cookie`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${tok}` },
    credentials: 'include',
  }).catch(() => {})
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [handle, setHandle] = useState<string | null>(null)
  const [tier, setTier] = useState<string>('free')
  const [needsSetup, setNeedsSetup] = useState(false)
  const [devStub, setDevStub] = useState(false)

  // Resume an existing session on load, and consume a ?token= return
  // from a magic link regardless of which route it lands on.
  useEffect(() => {
    let cancelled = false
    // 先问服务端鉴权模式(同源 play 面;本地/dev 栈 nginx 直达路由)。
    // stub → 视作已登录 dev,跳过 token/me 流;失败/缺席 → required。
    ;(async () => {
      try {
        const ctrl = new AbortController()
        const timer = setTimeout(() => ctrl.abort(), 2000)
        const r = await fetch(`${computeOrigin()}/api/v1/play/authmode`, { signal: ctrl.signal })
        clearTimeout(timer)
        if (!cancelled && r.ok) {
          const d = (await r.json()) as { auth?: string; handle?: string }
          if (d.auth === 'stub') {
            setDevStub(true)
            setHandle(d.handle || 'dev')
            setTier('dev')
            setNeedsSetup(false)
          }
        }
      } catch {
        /* required(fail-safe) */
      }
    })()
    ;(async () => {
      const url = new URL(window.location.href)
      const tok = url.searchParams.get('token')
      if (tok) {
        // Strip the token from the URL synchronously BEFORE the async
        // verify call, and dedupe against the in-page consumed set.
        // Both prevent the second parallel verify the server would 400.
        url.searchParams.delete('token')
        window.history.replaceState({}, '', url.toString())
        if (_consumedTokens.has(tok)) return
        _consumedTokens.add(tok)

        let verified = false
        try {
          const v = await apiVerify(tok)
          if (!cancelled) {
            setHandle(v.handle)
            setNeedsSetup(v.needsSetup)
            identify(v.handle) // bridge anonymous events → this handle
            track('signup_verified')
            exchangePlayCookie()
            verified = true
          }
        } catch {
          /* invalid/expired */
        }
        // If signup was initiated from another site, bounce back. The
        // pending-return is stashed by SignupPage before request-link
        // and is already host-allowlisted at that point.
        if (verified) {
          try {
            const ret = localStorage.getItem('rp-hub:pending-return')
            if (ret) {
              localStorage.removeItem('rp-hub:pending-return')
              window.location.replace(ret)
              return
            }
          } catch {
            /* storage blocked — stay on hub */
          }
        }
        return
      }
      if (sessionToken()) {
        try {
          const m = await apiMe()
          if (!cancelled) {
            setHandle(m.handle)
            setTier(m.tier || 'free')
            // Only nag when the gateway explicitly says unregistered —
            // an older gateway (field absent) must not trigger the gate.
            setNeedsSetup(m.registered === false)
            identify(m.handle) // resuming an existing session
            exchangePlayCookie() // 恢复会话也补一枚 SSE cookie
          }
        } catch {
          /* stale / gateway down — stay anon */
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const value: AuthCtx = {
    handle,
    tier,
    signedIn: !!handle,
    devStub,
    needsSetup,
    async requestLink(email) {
      const r = await apiRequestLink(email)
      return { sent: r.sent, devToken: r.devToken }
    },
    async verify(token) {
      const v = await apiVerify(token)
      setHandle(v.handle)
      setNeedsSetup(v.needsSetup)
      // Fetch full profile to get tier after verification
      try {
        const m = await apiMe()
        setTier(m.tier || 'free')
      } catch { /* ignore */ }
      identify(v.handle)
      exchangePlayCookie()
    },
    async passwordLogin(email, password) {
      const v = await apiPasswordLogin(email, password)
      setHandle(v.handle)
      setNeedsSetup(v.needsSetup)
      try {
        const m = await apiMe()
        setTier(m.tier || 'free')
      } catch { /* ignore */ }
      identify(v.handle)
      track('password_login')
      exchangePlayCookie()
    },
    async completeRegistration(opts) {
      const r = await apiCompleteRegistration(opts)
      setHandle(r.handle)
      setNeedsSetup(false)
      track('registration_completed')
    },
    signOut() {
      if (devStub) return // 替身模式没有可登出的真实会话
      resetIdentity()
      apiSignOut()
      setHandle(null)
      setTier('free')
      setNeedsSetup(false)
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}

export { IdentityError }
