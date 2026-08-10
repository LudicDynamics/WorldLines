/**
 * Hub identity client (Hub-5). Magic-link auth, per-user save, 入库.
 *
 * Hub-owned, separate from worldlines.gg. The session token lives in
 * localStorage and is sent as a Bearer header. When the identity
 * gateway isn't configured (`VITE_IDENTITY_ENDPOINT` unset / down) the
 * UI degrades to the gated state — creation still works offline.
 */

const ENDPOINT =
  (import.meta.env.VITE_IDENTITY_ENDPOINT as string | undefined) ??
  'http://127.0.0.1:8097'

const SESSION_KEY = 'rp-hub:session'

export type DraftEntry = {
  draft_id: string
  kind: string
  name: string
  updated: number
}
export type PlayEntry = {
  kind: string  // worlds | souls | drafts
  slug: string
  first_played: number
  last_played: number
  turn_count: number
}
export type Me = {
  /** sha256(email)[:16] — per-user storage key shared with play/create services. */
  uid?: string
  handle: string
  display_name?: string | null
  registered?: boolean
  has_password?: boolean
  sub_cancel_at_period_end?: boolean
  sub_period_end?: number | null
  tier: string  // "free" | "paid"
  plays_today?: number
  daily_cap?: number | null
  drafts: DraftEntry[]
  published: {
    id: string
    kind: string
    name: string
    values?: Record<string, string>
    entry?: { unlisted?: boolean; cover_url?: string; hash?: string }
  }[]
  plays?: PlayEntry[]
}

export type PlayQuota = {
  uid: string
  tier: string
  plays_today: number
  daily_cap: number | null
  allowed: boolean
}

export type SessionEntry = {
  id: string  // 16-char prefix of the session hash (NOT the bearer)
  issued_at?: number
  last_seen?: number
  issued_ip?: string | null
  issued_ua?: string | null
  expires?: number
  is_current?: boolean
}

export class IdentityError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function sessionToken(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}

function setSession(tok: string | null) {
  try {
    if (tok) localStorage.setItem(SESSION_KEY, tok)
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    /* storage disabled — session is in-memory only this tab */
  }
}

async function call<T>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.body) headers['content-type'] = 'application/json'
  if (opts.auth) {
    const t = sessionToken()
    if (!t) throw new IdentityError(401, 'not signed in')
    headers.authorization = `Bearer ${t}`
  }
  let r: Response
  try {
    r = await fetch(`${ENDPOINT}${path}`, {
      method: opts.method ?? (opts.body ? 'POST' : 'GET'),
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    })
  } catch {
    throw new IdentityError(0, `identity gateway unreachable at ${ENDPOINT}`)
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok)
    throw new IdentityError(r.status, data?.detail || `HTTP ${r.status}`)
  return data as T
}

export function identityEndpoint() {
  return ENDPOINT
}

function currentLocale(): string {
  // Read the hub's persisted locale; falls back to browser → English.
  try {
    const s = localStorage.getItem('rp-hub:lang')
    if (s) return s
  } catch {
    /* storage off */
  }
  if (typeof navigator !== 'undefined') {
    const n = navigator.language ?? 'en'
    if (n.startsWith('zh')) return 'zh'
    if (n.startsWith('ja')) return 'ja'
    if (n.startsWith('ko')) return 'ko'
  }
  return 'en'
}

export async function requestLink(
  email: string,
): Promise<{ sent: boolean; devLink?: string; devToken?: string }> {
  const d = await call<{
    sent: boolean
    dev_magic_link?: string
    dev_token?: string
  }>('/api/v1/auth/request', { body: { email, locale: currentLocale() } })
  return { sent: d.sent, devLink: d.dev_magic_link, devToken: d.dev_token }
}

export async function verify(
  token: string,
): Promise<{ handle: string; needsSetup: boolean }> {
  const d = await call<{
    session: string
    handle: string
    needs_setup?: boolean
  }>('/api/v1/auth/verify', { body: { token } })
  setSession(d.session)
  return { handle: d.handle, needsSetup: !!d.needs_setup }
}

// Identifier-first sign-in: look up how to proceed for this email.
// exists+has_password → password sign-in; exists w/o password OR new →
// email-link path (then the registration gate completes setup).
export async function checkEmail(
  email: string,
): Promise<{ exists: boolean; registered: boolean; hasPassword: boolean }> {
  const d = await call<{
    exists: boolean
    registered: boolean
    has_password: boolean
  }>('/api/v1/auth/check', { body: { email } })
  return { exists: d.exists, registered: d.registered, hasPassword: d.has_password }
}

// Daily sign-in with email + password — no email round-trip (the mailed
// link often opens in a different browser/webview on mobile and strands
// the original page). The magic link remains signup + recovery.
export async function passwordLogin(
  email: string,
  password: string,
): Promise<{ handle: string; needsSetup: boolean }> {
  const d = await call<{
    session: string
    handle: string
    needs_setup?: boolean
  }>('/api/v1/auth/login', { body: { email, password } })
  setSession(d.session)
  return { handle: d.handle, needsSetup: !!d.needs_setup }
}

// One-time registration completion: pick handle / display name + set the
// password. Bearer comes from the email-verified session.
export async function completeRegistration(opts: {
  password: string
  handle?: string
  displayName?: string
}): Promise<{ handle: string }> {
  const d = await call<{ ok: boolean; handle: string }>(
    '/api/v1/me/register',
    {
      auth: true,
      body: {
        password: opts.password,
        handle: opts.handle || undefined,
        display_name: opts.displayName ?? undefined,
      },
    },
  )
  return { handle: d.handle }
}

export function signOut() {
  setSession(null)
}

export async function me(): Promise<Me> {
  return call<Me>('/api/v1/me', { auth: true })
}

export async function listSessions(): Promise<SessionEntry[]> {
  const d = await call<{ sessions: SessionEntry[] }>(
    '/api/v1/me/sessions',
    { auth: true },
  )
  return d.sessions
}

export async function revokeSession(id: string): Promise<void> {
  await call(`/api/v1/me/sessions/${encodeURIComponent(id)}`, {
    auth: true,
    method: 'DELETE',
  })
}

export type PublishedRecord = {
  values?: Record<string, string>
  name?: string
  id?: string
  description?: string
  entry?: {
    hash?: string
    cover_url?: string
    unlisted?: boolean
    portraits?: Record<string, string>
  }
}

export async function getPublished(
  kind: string,
  slug: string,
): Promise<{ key: string; kind: string; slug: string; record: PublishedRecord }> {
  return call(
    `/api/v1/me/published/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}`,
    { auth: true },
  )
}

// Edit display name / catalog description of an owned published asset.
export async function updatePublishedMeta(
  kind: string,
  slug: string,
  meta: { name?: string; description?: string },
): Promise<{ kind: string; slug: string; name?: string; description?: string }> {
  return call(
    `/api/v1/me/published/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}/meta`,
    { auth: true, body: meta },
  )
}

export type UploadResult = {
  id: string
  kind: string
  name: string
  packaged: boolean
  dry_run?: boolean
  entry?: { hash: string; url: string; size_bytes: number; uploaded_at?: string }
  registry?: string
  source?: string
}

// Upload a zip bundle to WorldHub / SoulHub. Bypasses the create-studio
// path entirely — for users who hand-authored a world locally (CLI or
// rp-tauri) and just want to publish it. Server-side validates the zip,
// derives a slug, mints it, pushes to S3, records in users:published.
// Multipart (the only place we ship a file body to identity); the
// `call` JSON helper above doesn't fit, so a direct fetch here.
export async function uploadBundle(
  kind: 'world' | 'soul',
  file: File,
  opts: {
    slug?: string
    name?: string
    version?: string
    changelog?: string
    unlisted?: boolean
  } = {},
): Promise<UploadResult> {
  const tok = sessionToken()
  if (!tok) throw new IdentityError(401, 'not signed in')
  const form = new FormData()
  form.append('kind', kind)
  form.append('file', file)
  if (opts.slug) form.append('slug', opts.slug)
  if (opts.name) form.append('name', opts.name)
  if (opts.version) form.append('version', opts.version)
  if (opts.changelog) form.append('changelog', opts.changelog)
  // Default unlisted=true on the server matches Hub-9 "try-water-first"
  // safe default; expose the toggle to the caller for the explicit
  // public-publish case.
  if (opts.unlisted !== undefined)
    form.append('unlisted', opts.unlisted ? 'true' : 'false')
  let r: Response
  try {
    r = await fetch(`${ENDPOINT}/api/v1/me/upload`, {
      method: 'POST',
      headers: { authorization: `Bearer ${tok}` },
      body: form,
    })
  } catch {
    throw new IdentityError(0, `identity gateway unreachable at ${ENDPOINT}`)
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok)
    throw new IdentityError(r.status, data?.detail || `HTTP ${r.status}`)
  return data as UploadResult
}

export async function unpublish(kind: string, slug: string): Promise<void> {
  await call(
    `/api/v1/me/published/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}`,
    { auth: true, method: 'DELETE' },
  )
}

// Make a published asset public (unlisted=false) or hidden (true) by
// flipping its catalog visibility. Owner-gated server-side.
export async function setVisibility(
  kind: string,
  slug: string,
  unlisted: boolean,
): Promise<{ unlisted: boolean; changed: number }> {
  return call(
    `/api/v1/me/published/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}/visibility`,
    { auth: true, body: { unlisted } },
  )
}

// Replace the cover image of an asset the caller owns — the canonical
// image path (server uploads to S3 + patches index.json; clients never
// touch S3). Multipart, so a direct fetch like uploadBundle above.
export async function uploadCover(
  kind: 'world' | 'soul',
  slug: string,
  file: File,
): Promise<{ kind: string; slug: string; cover_url: string }> {
  const tok = sessionToken()
  if (!tok) throw new IdentityError(401, 'not signed in')
  const form = new FormData()
  form.append('file', file)
  let r: Response
  try {
    r = await fetch(
      `${ENDPOINT}/api/v1/me/published/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}/cover`,
      { method: 'POST', headers: { authorization: `Bearer ${tok}` }, body: form },
    )
  } catch {
    throw new IdentityError(0, `identity gateway unreachable at ${ENDPOINT}`)
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok)
    throw new IdentityError(r.status, data?.detail || `HTTP ${r.status}`)
  return data as { kind: string; slug: string; cover_url: string }
}

// Attach/replace a 立绘 (character portrait) for a built-in soul of an
// owned asset. soulId selects which soul ("self" for a soul bundle).
// Multipart, like uploadCover.
export async function uploadPortrait(
  kind: 'world' | 'soul',
  slug: string,
  file: File,
  soulId = 'self',
): Promise<{ kind: string; slug: string; soul_id: string; portrait_url: string }> {
  const tok = sessionToken()
  if (!tok) throw new IdentityError(401, 'not signed in')
  const form = new FormData()
  form.append('file', file)
  form.append('soul_id', soulId)
  let r: Response
  try {
    r = await fetch(
      `${ENDPOINT}/api/v1/me/published/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}/portrait`,
      { method: 'POST', headers: { authorization: `Bearer ${tok}` }, body: form },
    )
  } catch {
    throw new IdentityError(0, `identity gateway unreachable at ${ENDPOINT}`)
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok)
    throw new IdentityError(r.status, data?.detail || `HTTP ${r.status}`)
  return data as { kind: string; slug: string; soul_id: string; portrait_url: string }
}

// ── API Tokens (CLI / CI) ──────────────────────────────────

export type ApiToken = {
  tid: string
  label: string
  prefix: string
  created_at: number
  last_used: number | null
}

export type ApiTokenCreated = ApiToken & { token: string }

export async function listApiTokens(): Promise<ApiToken[]> {
  const d = await call<{ tokens: ApiToken[] }>('/api/v1/me/api-tokens', { auth: true })
  return d.tokens ?? []
}

export async function createApiToken(label: string): Promise<ApiTokenCreated> {
  return call<ApiTokenCreated>('/api/v1/me/api-tokens', {
    auth: true,
    body: { label },
  })
}

export async function revokeApiToken(tid: string): Promise<void> {
  await call(`/api/v1/me/api-tokens/${encodeURIComponent(tid)}`, {
    auth: true,
    method: 'DELETE',
  })
}

export async function revokeOtherSessions(): Promise<number> {
  const d = await call<{ revoked: number }>(
    '/api/v1/me/sessions/revoke-others',
    { auth: true, body: {} },
  )
  return d.revoked
}

/** Full stored draft, for resuming a creation (二次创作). */
export async function getDraft(
  draftId: string,
): Promise<{ draft_id: string; kind: string; draft: unknown }> {
  return call(`/api/v1/me/draft/${encodeURIComponent(draftId)}`, {
    auth: true,
  })
}

export async function saveDraft(
  kind: string,
  draft: unknown,
  draftId?: string,
): Promise<string> {
  const d = await call<{ draft_id: string }>('/api/v1/me/save', {
    auth: true,
    body: { kind, draft, draft_id: draftId },
  })
  return d.draft_id
}

export type PublishResult = {
  id: string
  kind: string
  packaged?: boolean
  dry_run?: boolean
  entry?: { hash: string; url: string; size_bytes: number }
  note?: string
}

export async function publish(
  kind: string,
  draft: unknown,
  draftId?: string,
): Promise<PublishResult> {
  // draftId → publish the persistent deepened working tree (#44 ②)
  return call<PublishResult>('/api/v1/me/publish', {
    auth: true,
    body: { kind, draft, draft_id: draftId },
  })
}

// ── Stripe ─────────────────────────────────────────────────────

export async function stripeCheckout(
  returnUrl?: string,
): Promise<{ url: string }> {
  return call<{ url: string }>('/api/v1/me/stripe/checkout', {
    auth: true,
    body: { return_url: returnUrl },
  })
}

export async function stripePortal(): Promise<{ url: string }> {
  return call<{ url: string }>('/api/v1/me/stripe/portal', {
    auth: true,
    body: {},
  })
}

export async function playStart(): Promise<PlayQuota> {
  return call<PlayQuota>('/api/v1/me/play-start', { auth: true, body: {} })
}

export async function playTouch(
  kind: string,
  slug: string,
  turnTokens: number,
  event: string,
): Promise<{ quota_exceeded: boolean }> {
  return call('/api/v1/me/play-touch', {
    auth: true,
    body: { kind, slug, turn_tokens: turnTokens, event },
  })
}
