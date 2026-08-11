/**
 * AdminDashboardPage — operational metrics for the founder/admin.
 *
 * Reads /api/v1/admin/stats from api.worldlines.gg using the user's
 * existing hub session (Bearer in localStorage as `rp-hub:session`).
 * No token paste-in needed — if you're signed in here, and your handle
 * is in BOOTSTRAP_SUPER_ADMIN or ADMIN_HANDLES on the gateway, the data
 * loads automatically. 403 = signed in but not admin. 401 = sign in.
 *
 * Mirrors the older cockpit/admin.html — that local version stays
 * around as backup. This is the canonical "anywhere, any device" view.
 */
import { useEffect, useState } from 'react'
import { ReviewQueue } from './ReviewQueue'
import { Link } from 'react-router-dom'
import { useAuth } from '../shared/auth'
import { sessionToken, identityEndpoint } from '../shared/identity'

// 端点默认=运行时同源(生产由 .env.production 的 VITE_COMPUTE_ENDPOINT 显式注入)
const COMPUTE = import.meta.env.VITE_COMPUTE_ENDPOINT ?? ''

type InviteStatus = 'idle' | 'sending' | 'sent' | 'throttled' | 'bad' | 'error'
type InviteRow = { email: string; locale: string; at: number }

function InviteBox({ onSent }: { onSent: () => void }) {
  const [email, setEmail] = useState('')
  const [locale, setLocale] = useState('en')
  const [status, setStatus] = useState<InviteStatus>('idle')
  const [note, setNote] = useState('')
  const [history, setHistory] = useState<InviteRow[]>(() => {
    try {
      const raw = sessionStorage.getItem('cockpit:invite-history')
      return raw ? (JSON.parse(raw) as InviteRow[]) : []
    } catch {
      return []
    }
  })

  function pushHistory(row: InviteRow) {
    const next = [row, ...history].slice(0, 8)
    setHistory(next)
    try {
      sessionStorage.setItem('cockpit:invite-history', JSON.stringify(next))
    } catch {
      /* ignore */
    }
  }

  const validEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)

  async function send() {
    if (!validEmail || status === 'sending') return
    setStatus('sending')
    setNote('')
    try {
      const r = await fetch(`${identityEndpoint()}/api/v1/auth/request`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), locale }),
      })
      if (r.status === 200) {
        setStatus('sent')
        setNote(`✓ magic link sent to ${email} (${locale})`)
        pushHistory({ email, locale, at: Date.now() })
        setEmail('')
        // give DDB a beat then refresh stats
        setTimeout(onSent, 1500)
        return
      }
      if (r.status === 429) {
        setStatus('throttled')
        setNote('Rate-limited — 60s cooldown per email. Wait then retry.')
        return
      }
      if (r.status === 400) {
        setStatus('bad')
        const body = await r.text()
        setNote(`Invalid: ${body.slice(0, 80)}`)
        return
      }
      const body = await r.text()
      setStatus('error')
      setNote(`HTTP ${r.status} — ${body.slice(0, 80)}`)
    } catch (e) {
      setStatus('error')
      setNote(e instanceof Error ? e.message : String(e))
    }
  }

  const statusColor =
    status === 'sent'
      ? 'text-[var(--color-accent)]'
      : status === 'throttled' || status === 'bad'
        ? 'text-orange-400'
        : status === 'error'
          ? 'text-red-400'
          : 'text-[var(--color-text-tertiary)]'

  return (
    <div className="rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)]">
          Invite (closed beta)
        </h2>
        {history.length > 0 && (
          <span className="text-[11px] text-[var(--color-text-tertiary)]">
            {history.length} sent this session
          </span>
        )}
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && send()}
          placeholder="friend@example.com"
          className="flex-1 min-w-[220px] bg-transparent border border-[var(--color-border)] rounded-md px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-accent-dim)]"
        />
        <select
          value={locale}
          onChange={(e) => setLocale(e.target.value)}
          className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md px-2 py-1.5 text-[12px] font-mono"
        >
          <option value="en">EN</option>
          <option value="zh">中文</option>
          <option value="ja">日本語</option>
          <option value="ko">한국어</option>
        </select>
        <button
          onClick={send}
          disabled={!validEmail || status === 'sending'}
          className="hover-btn px-3 py-1.5 rounded-md text-[12px] font-medium disabled:opacity-40"
          style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
        >
          {status === 'sending' ? 'Sending…' : 'Send invite'}
        </button>
      </div>
      {note && <p className={`text-[12px] ${statusColor}`}>{note}</p>}
      {history.length > 0 && (
        <details className="text-[11px] text-[var(--color-text-tertiary)]">
          <summary className="cursor-pointer hover:text-[var(--color-text-secondary)]">
            session history ({history.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-0.5">
            {history.map((h, i) => (
              <li key={i}>
                <span className="font-mono">{new Date(h.at).toLocaleTimeString()}</span>
                {' · '}
                <span>{h.email}</span>
                {' · '}
                <span className="font-mono">{h.locale}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-[10px] text-[var(--color-text-tertiary)]">
        POSTs to <code>/api/v1/auth/request</code> on api.worldlines.gg ·
        SES production · per-email 60s throttle.
      </p>
    </div>
  )
}

type Recent = { handle: string; email_local: string; created: number }
type Stats = {
  users: { total: number; last_24h: number; last_7d: number; recent: Recent[] }
  sessions: { live: number; rows: number }
  magic_links: { live: number; rows: number }
  content: {
    drafts: number
    published: number
    worlds_in_catalog?: number
    souls_in_catalog?: number
    catalog_fetched_at?: number
  }
  behavior?: {
    available: boolean
    fetched_at?: number
    wau?: number | null
    d1_pct?: number | null
    replay_pct?: number | null
    creator_pct?: number | null
    errors?: Record<string, string>
    reason?: string
  }
  as_of: number
}

type ComputeAlert = { key: string; level: 'critical' | 'warn'; msg: string }
type ComputeStatus = {
  ok: boolean
  as_of: number
  service: string
  play: { live_sessions: number; max_sessions: number; pool_pct: number }
  tokens: { used_today: number; cap_today: number; pct: number; session_rate_per_min: number }
  external: {
    comfyui: { ok: boolean; url: string }
    ollama: { ok: boolean; url: string }
    deepseek: { key_present: boolean; balance_usd: number | null }
  }
  resources: { ram_pct?: number; ram_used_mb?: number; ram_total_mb?: number; disk_pct?: number; disk_used_gb?: number }
  alerts: ComputeAlert[]
}

function fmtRel(epoch?: number, now?: number): string {
  if (!epoch) return '-'
  const dt = (now ?? Date.now() / 1000) - epoch
  const abs = Math.abs(dt)
  if (abs < 60) return Math.round(abs) + 's ago'
  if (abs < 3600) return Math.round(abs / 60) + 'm ago'
  if (abs < 86400) return Math.round(abs / 3600) + 'h ago'
  return Math.round(abs / 86400) + 'd ago'
}

function CircleInput({ label }: { label: string }) {
  const key = `cockpit:circle:${label}`
  const [val, setVal] = useState(() => {
    try {
      return localStorage.getItem(key) ?? ''
    } catch {
      return ''
    }
  })

  function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value
    setVal(v)
    try {
      localStorage.setItem(key, v)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4 flex flex-col gap-2">
      <span className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)]">
        {label}
      </span>
      <input
        type="number"
        value={val}
        onChange={onChange}
        placeholder="0"
        className="w-full bg-transparent border-b border-[var(--color-border)] py-1 text-[28px] font-semibold text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent-dim)] placeholder:text-[var(--color-text-muted)]"
      />
    </div>
  )
}

function Card({
  label,
  value,
  delta,
}: {
  label: string
  value: string | number
  delta?: string
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4">
      <div className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-1.5">
        {label}
      </div>
      <div className="text-[28px] font-semibold text-[var(--color-text-primary)] leading-none">
        {value}
      </div>
      {delta && (
        <div className="text-[11px] text-[var(--color-text-tertiary)] mt-1">
          {delta}
        </div>
      )}
    </div>
  )
}

export function AdminDashboardPage() {
  const { signedIn, handle } = useAuth()
  const [data, setData] = useState<Stats | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'denied' | 'noauth' | 'error'>(
    'idle',
  )
  const [err, setErr] = useState('')
  const [compute, setCompute] = useState<ComputeStatus | null>(null)
  const [computeErr, setComputeErr] = useState('')
  const [auto, setAuto] = useState(false)

  async function fetchCompute() {
    const tok = sessionToken()
    if (!tok) return
    try {
      const r = await fetch(`${COMPUTE}/api/v1/admin/status`, {
        headers: { authorization: 'Bearer ' + tok },
      })
      if (!r.ok) {
        if (r.status === 403) { setComputeErr('not admin on compute'); return }
        setComputeErr(`compute HTTP ${r.status}`)
        return
      }
      setCompute(await r.json())
      setComputeErr('')
    } catch (e) {
      setComputeErr(e instanceof Error ? e.message : String(e))
    }
  }

  // The mount effect calls refresh(), and every transition below (noauth /
  // loading / …) is a real one we must keep — the page starts at 'idle', so
  // dropping them would change what renders. Running the body in a promise
  // continuation keeps the transitions intact while moving them out of the
  // effect body, which is what react-hooks/set-state-in-effect asks for.
  // One microtask later; the interval and button paths are unaffected.
  function refresh() {
    return Promise.resolve().then(runRefresh)
  }

  async function runRefresh() {
    if (!signedIn) {
      setState('noauth')
      return
    }
    const tok = sessionToken()
    if (!tok) {
      setState('noauth')
      return
    }
    setState('loading')
    setErr('')
    try {
      const r = await fetch(`${identityEndpoint()}/api/v1/admin/stats`, {
        headers: { authorization: 'Bearer ' + tok },
      })
      if (r.status === 401) {
        setState('noauth')
        return
      }
      if (r.status === 403) {
        setState('denied')
        return
      }
      if (!r.ok) {
        const body = await r.text()
        setErr(`HTTP ${r.status} — ${body.slice(0, 100)}`)
        setState('error')
        return
      }
      setData(await r.json())
      setState('idle')
      fetchCompute()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setState('error')
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn])

  useEffect(() => {
    if (!auto) return
    const t = setInterval(() => { refresh(); fetchCompute() }, 30000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, signedIn])

  // Auth gates
  if (!signedIn || state === 'noauth') {
    return (
      <section className="w-full max-w-[680px] px-5 md:px-12 py-10 flex flex-col gap-4">
        <h1 className="text-[24px] text-[var(--color-text-primary)]">
          Dashboard
        </h1>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          Sign in first — your existing hub session is the auth.{' '}
          <Link
            to="/signup"
            className="text-[var(--color-accent)] underline"
          >
            Sign in
          </Link>
          .
        </p>
      </section>
    )
  }
  if (state === 'denied') {
    return (
      <section className="w-full max-w-[680px] px-5 md:px-12 py-10 flex flex-col gap-4">
        <h1 className="text-[24px] text-[var(--color-text-primary)]">
          Dashboard
        </h1>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          Signed in as <strong>{handle}</strong>, but this handle isn't on the
          admin list. Ask the super-admin to grant access.
        </p>
      </section>
    )
  }

  const d = data
  const ph = d?.behavior

  return (
    <section className="w-full max-w-[1080px] px-5 md:px-12 py-10 flex flex-col gap-6">
      <header className="flex items-end justify-between flex-wrap gap-4">
        <div className="flex flex-col gap-1.5">
          <span
            className="font-mono text-[11px] text-[var(--color-accent-dim)]"
            style={{ letterSpacing: 2 }}
          >
            WORLDLINES · ADMIN · DASHBOARD
          </span>
          <h1
            className="text-[var(--color-text-primary)]"
            style={{ fontFamily: 'var(--font-display)', fontSize: 28 }}
          >
            Operational metrics
          </h1>
          <p className="text-[12px] text-[var(--color-text-tertiary)]">
            Live from <code>api.worldlines.gg/api/v1/admin/stats</code> ·{' '}
            <Link
              to="/admin"
              className="text-[var(--color-accent)] hover:opacity-80"
            >
              ← Genre editor
            </Link>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={refresh}
            disabled={state === 'loading'}
            className="hover-btn px-3 py-1.5 rounded-md text-[12px] font-medium disabled:opacity-40"
            style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
          >
            {state === 'loading' ? 'Loading…' : 'Refresh'}
          </button>
          <label className="font-mono text-[11px] text-[var(--color-text-tertiary)] flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />
            auto 30s
          </label>
        </div>
      </header>

      {state === 'error' && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-[12px] text-red-400">
          {err}
        </div>
      )}

      <InviteBox onSent={refresh} />

      {d && (
        <>
          <div>
            <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-3">
              Users
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Card
                label="total users"
                value={d.users.total}
                delta={
                  d.users.last_24h
                    ? `+${d.users.last_24h} in last 24h`
                    : 'no signups in last 24h'
                }
              />
              <Card
                label="last 7 days"
                value={d.users.last_7d}
                delta="cumulative window"
              />
              <Card label="last 24h" value={d.users.last_24h} />
            </div>
          </div>

          <div>
            <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-3">
              Signup targets (三圈)
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <CircleInput label="内圈 (Inner)" />
              <CircleInput label="中圈 (Mid)" />
              <CircleInput label="外圈 (Outer)" />
            </div>
          </div>

          <div>
            <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-3">
              Sessions · Magic-links · Content · Catalog
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Card label="live sessions" value={d.sessions.live} />
              <Card
                label="magic-links pending"
                value={d.magic_links.live}
                delta="15-min TTL"
              />
              <Card label="drafts" value={d.content.drafts} />
              <Card label="published (DDB)" value={d.content.published} />
              <Card
                label="worlds in catalog"
                value={d.content.worlds_in_catalog ?? '-'}
                delta="S3 worldhub"
              />
              <Card
                label="souls in catalog"
                value={d.content.souls_in_catalog ?? '-'}
                delta="S3 worldhub"
              />
            </div>
          </div>

          <div>
            <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-3">
              Behavior (PostHog HogQL)
              {ph && !ph.available && (
                <span className="ml-2 text-[var(--color-text-tertiary)] normal-case tracking-normal">
                  — unavailable ({ph.reason})
                </span>
              )}
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Card
                label="WAU"
                value={ph?.wau ?? '-'}
                delta="play_session_started · 7d"
              />
              <Card
                label="D1 retention"
                value={ph?.d1_pct == null ? '-' : ph.d1_pct + '%'}
                delta="signup → next-day play"
              />
              <Card
                label="replay rate"
                value={ph?.replay_pct == null ? '-' : ph.replay_pct + '%'}
                delta="≥2 sessions / ≥1"
              />
              <Card
                label="creator conv."
                value={ph?.creator_pct == null ? '-' : ph.creator_pct + '%'}
                delta="published / played"
              />
            </div>
            {ph?.errors && Object.keys(ph.errors).length > 0 && (
              <p className="mt-2 text-[11px] text-[var(--color-text-tertiary)]">
                Query errors:{' '}
                {Object.entries(ph.errors)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join('; ')}
              </p>
            )}
          </div>

          {/* ─── Compute · xserver ─── */}
          <div>
            <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-3">
              Compute · xserver
              {compute && (
                <span className="ml-2 normal-case tracking-normal">
                  · live from {COMPUTE.replace('https://', '')}
                </span>
              )}
            </h2>
            {computeErr && (
              <p className="mb-2 text-[11px] text-red-400">compute: {computeErr}</p>
            )}
            {compute ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  <Card
                    label="play sessions"
                    value={compute.play.live_sessions}
                    delta={`${compute.play.pool_pct}% of ${compute.play.max_sessions}`}
                  />
                  <Card
                    label="tokens today"
                    value={(compute.tokens.used_today / 1e6).toFixed(1) + 'M'}
                    delta={`${compute.tokens.pct}% of ${(compute.tokens.cap_today / 1e6).toFixed(0)}M cap`}
                  />
                  <Card
                    label="new sessions/min"
                    value={Math.round(compute.tokens.session_rate_per_min)}
                    delta="last 60s"
                  />
                  <Card
                    label="deepseek balance"
                    value={compute.external.deepseek.balance_usd != null
                      ? '$' + compute.external.deepseek.balance_usd.toFixed(2)
                      : '—'}
                    delta={compute.external.deepseek.key_present ? 'key set' : 'no key'}
                  />
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  <Card
                    label="container RAM"
                    value={compute.resources.ram_pct != null
                      ? compute.resources.ram_pct + '%'
                      : '—'}
                    delta={compute.resources.ram_used_mb != null
                      ? `${compute.resources.ram_used_mb} / ${compute.resources.ram_total_mb} MB`
                      : undefined}
                  />
                  <Card
                    label="disk"
                    value={compute.resources.disk_pct != null
                      ? compute.resources.disk_pct + '%'
                      : '—'}
                    delta={compute.resources.disk_used_gb != null
                      ? `${compute.resources.disk_used_gb} / ${(compute.resources.disk_used_gb ?? 0) + (compute.resources.disk_pct != null ? 0 : 0)} GB`
                      : undefined}
                  />
                  <Card
                    label="comfyui"
                    value={compute.external.comfyui.ok ? 'ok' : 'down'}
                    delta={compute.external.comfyui.url || 'unset'}
                  />
                  <Card
                    label="ollama embed"
                    value={compute.external.ollama.ok ? 'ok' : 'down'}
                    delta={compute.external.ollama.url || 'unset'}
                  />
                </div>
                {compute.alerts.length > 0 && (
                  <div className="flex flex-col gap-1 mb-3">
                    {compute.alerts.map((a) => {
                      const color = a.level === 'critical' ? '#f85149' : '#d29922'
                      const bg = a.level === 'critical' ? 'rgba(248,81,73,0.08)' : 'rgba(210,153,34,0.08)'
                      const icon = a.level === 'critical' ? '🚨' : '⚠️'
                      return (
                        <div
                          key={a.key}
                          style={{ border: `1px solid ${color}`, background: bg }}
                          className="px-3 py-2 rounded-md text-[12px]"
                        >
                          <span style={{ color }}>{icon} <strong>[{a.level.toUpperCase()}]</strong> · {a.msg}</span>
                        </div>
                      )
                    })}
                  </div>
                )}
                {compute.alerts.length === 0 && (
                  <p className="text-[11px] text-[var(--color-accent)] mb-3">
                    no alerts · checked {new Date(compute.as_of * 1000).toLocaleTimeString()}
                  </p>
                )}
              </>
            ) : (
              <p className="text-[11px] text-[var(--color-text-tertiary)] mb-3">
                {computeErr ? 'compute unreachable' : 'sign in to load compute status'}
              </p>
            )}
            <p className="text-[10px] text-[var(--color-text-tertiary)]">
              Powered by the compute tier · Discord alerts fire on critical/warn thresholds
            </p>
          </div>

          <div>
            <h2 className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-text-tertiary)] mb-3">
              Recent signups
            </h2>
            <table className="w-full rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-card)] overflow-hidden text-[12px]">
              <thead className="bg-[var(--color-bg)] text-[10px] uppercase tracking-[0.08em] text-[var(--color-text-tertiary)]">
                <tr>
                  <th className="text-left px-3 py-2">handle</th>
                  <th className="text-left px-3 py-2">email local-part</th>
                  <th className="text-left px-3 py-2">when</th>
                </tr>
              </thead>
              <tbody>
                {d.users.recent.length === 0 ? (
                  <tr>
                    <td
                      colSpan={3}
                      className="px-3 py-3 text-[var(--color-text-tertiary)]"
                    >
                      no users yet
                    </td>
                  </tr>
                ) : (
                  d.users.recent.map((r, i) => (
                    <tr
                      key={r.handle + i}
                      className="border-t border-[var(--color-border)]"
                    >
                      <td className="px-3 py-2 text-[var(--color-text-primary)]">
                        {r.handle}
                      </td>
                      <td className="px-3 py-2 text-[var(--color-text-tertiary)]">
                        {r.email_local}@…
                      </td>
                      <td className="px-3 py-2 text-[var(--color-text-tertiary)]">
                        {fmtRel(r.created, d.as_of)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <p className="text-[10px] text-[var(--color-text-tertiary)]">
            as of {new Date(d.as_of * 1000).toLocaleString()}
          </p>
        </>
      )}
      <ReviewQueue />
    </section>
  )
}

export default AdminDashboardPage
