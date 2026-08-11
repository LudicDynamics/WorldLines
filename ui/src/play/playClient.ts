/**
 * Client for the hosted-play gateway (rp-infra/apps/api/play_gateway.py).
 *
 * Start a session ONCE, then reuse its id for every turn — the gateway
 * keeps the live ConversationSession in memory; a new session per
 * page-load pays the cold context re-seed (the main wasted cost the
 * gateway's budget model is built to avoid).
 *
 * Dev default targets the local gateway. Point VITE_PLAY_ENDPOINT
 * (preferred — matches VITE_CREATE_ENDPOINT naming) or the legacy
 * VITE_HOSTED_PLAY_ENDPOINT at the deployed gateway for production.
 */

// VITE_PLAY_ENDPOINT is three-state (docs/WEBUI-UNIFICATION.md §7.5 LP1):
//  - explicit '' (wheel build: `VITE_PLAY_ENDPOINT= npm run build`) → same-origin
//    mode: `neonrp web` serves this SPA itself, so fetches use relative paths;
//  - undefined → fall through to VITE_HOSTED_PLAY_ENDPOINT (Hub production
//    build) and finally the local-gateway dev default, http://127.0.0.1:8099;
//  - any other value → used as-is.
const RAW_PLAY = import.meta.env.VITE_PLAY_ENDPOINT as string | undefined
const ENDPOINT =
  RAW_PLAY === ''
    ? ''
    : RAW_PLAY ??
      (import.meta.env.VITE_HOSTED_PLAY_ENDPOINT as string | undefined) ??
      'http://127.0.0.1:8099'

/** Compute 层 origin('' = 同源部署,如本地栈/wheel;显式值 = Hub/Compute
 *  分层部署 —— 页面在 CloudFront、API 在 compute 域,HUB-GOLIVE §P2)。
 *  hub 侧所有硬编码的 /api/v1/play... 相对路径都应经此前缀。 */
export function computeOrigin(): string {
  return ENDPOINT
}

// Wider than the catalog Kind — drafts are the user's own in-progress
// bundles (workdir on create gateway, not published S3 catalog).
// play_gateway resolves a `drafts` slug to the workdir via Hub-1 §6
// uid gate. Re-exported as Kind so playClient consumers stay simple.
export type Kind = 'worlds' | 'souls' | 'drafts'

// 引擎模式二收敛(M28 §2.7):orchestrator + multi-agent(MT Agent Team)。
// multi-agent is NOT authorized on hosted play (the gateway 403s it) —
// it runs locally. 旧 "fast" 由引擎侧 normalize 到 orchestrator。
export type EngineMode = 'orchestrator' | 'multi-agent'

// Per-soul lifecycle for the multi-agent "lanes" UI.
export type SoulStatus = { name?: string; role?: string; state?: string }

// Post-turn orchestration trace — the rich per-lane source NeonRP's native
// web ui reads. Emitted once at turn end (multi-agent). `bus_messages`
// carries each soul's request (perception) + response (candidates/digest);
// `souls` is the in-scene roster; `world_location` the scene anchor.
export type TraceBusMessage = {
  topic?: string
  payload?: Record<string, unknown>
  seq?: number
}
export type TurnTrace = {
  turn_seq?: number
  world_location?: string
  souls?: Array<{
    sid?: string
    instance_id?: string
    activated?: boolean
    reason?: string
    state?: string
    speech?: string
    location?: string
  }>
  world_agent?: { narration_chars?: number }
  bus_messages?: TraceBusMessage[]
}

export type StartResult = {
  session_id: string
  kind: string
  slug: string
  scene_dir: string
  agent_id: string
  note: string
  engine_mode?: EngineMode
  // On resume: prior player-visible transcript to restore the log.
  messages?: { who: 'you' | 'narr'; text: string }[]
  // On resume (multi-agent): last turn's trace so the lanes + map repaint
  // immediately instead of showing an empty rail until the next turn.
  last_trace?: TurnTrace
}

export type StartOptions = {
  sceneDir?: string
  engineMode?: EngineMode
  avatarId?: string
  name?: string  // display name for the "my saves" list
}

export type TurnResult = {
  session_id: string
  success: boolean
  assistant_message: string
  error: string | null
  turn_tokens: number
  session_tokens: number
  session_token_cap: number
  daily_tokens: number
  daily_token_cap: number
  elapsed_ms: number
}

export class PlayError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Hub-1 §6: the session bearer gates all backend compute. Hub-5 BYOK:
// an optional user-supplied provider key, sent request-scoped only.
function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'content-type': 'application/json' }
  try {
    const s = localStorage.getItem('rp-hub:session')
    if (s) h.authorization = `Bearer ${s}`
    const k = localStorage.getItem('rp-hub:byok')
    if (k) h['X-Provider-Key'] = k
  } catch {
    /* storage off — anonymous; gateway will 401 */
  }
  return h
}

async function post<T>(path: string, body: unknown): Promise<T> {
  // Hard cap so a hung connection can never spin the UI forever.
  // 120 s — generous enough for a full non-streamed LLM turn.
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 120_000)
  let resp: Response
  try {
    resp = await fetch(`${ENDPOINT}${path}`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
      signal: ctrl.signal,
    })
  } catch (e) {
    throw new PlayError(
      0,
      e instanceof DOMException && e.name === 'AbortError'
        ? 'request timed out after 120s — please retry'
        : `Can't reach the play gateway at ${ENDPOINT}. Is it running?`,
    )
  } finally {
    clearTimeout(timer)
  }
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new PlayError(
      resp.status,
      (data && (data.detail || data.message)) || `HTTP ${resp.status}`,
    )
  }
  return data as T
}

export function gatewayEndpoint(): string {
  return ENDPOINT
}

export function startSession(
  kind: Kind,
  slug: string,
  opts?: StartOptions,
): Promise<StartResult> {
  return post<StartResult>('/api/v1/play/session', {
    kind,
    slug,
    scene_dir: opts?.sceneDir ?? null,
    engine_mode: opts?.engineMode ?? null,
    avatar_id: opts?.avatarId ?? null,
    name: opts?.name ?? null,
  })
}

// Streaming variant — same Bearer + body, but the response is SSE.
// The browser-native EventSource only does GET + can't send auth
// headers, so we do this with fetch() + a manual line parser.
//
// Wire events (see play_gateway.turn_stream):
//   event: thinking  data: {text}
//   event: chunk     data: {text}
//   event: done      data: TurnResult
//   event: error     data: {error}
//
// Returns a Promise resolving to the final TurnResult once `done`
// arrives. Callbacks fire in order; either onDone or onError will be
// called exactly once.
export type StreamHandlers = {
  onThinking?: (text: string) => void
  onChunk?: (text: string) => void
  onSoulStatus?: (statuses: Record<string, SoulStatus>) => void
  onTrace?: (trace: TurnTrace) => void
  onDone?: (final: TurnResult) => void
  onError?: (err: PlayError) => void
}

export function sendTurnStream(
  sid: string,
  input: string,
  h: StreamHandlers,
): { abort: () => void; done: Promise<TurnResult> } {
  const controller = new AbortController()
  const done = (async (): Promise<TurnResult> => {
    let resp: Response
    try {
      resp = await fetch(
        `${ENDPOINT}/api/v1/play/session/${sid}/turn/stream`,
        {
          method: 'POST',
          headers: { ...authHeaders(), accept: 'text/event-stream' },
          body: JSON.stringify({ input }),
          signal: controller.signal,
        },
      )
    } catch {
      const err = new PlayError(
        0,
        `Can't reach the play gateway at ${ENDPOINT}. Is it running?`,
      )
      h.onError?.(err)
      throw err
    }
    if (!resp.ok || !resp.body) {
      const body = await resp.text().catch(() => '')
      const err = new PlayError(resp.status, body || `HTTP ${resp.status}`)
      h.onError?.(err)
      throw err
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''
    let final: TurnResult | null = null
    let streamErr: PlayError | null = null

    // SSE parses event blocks separated by blank lines; each block has
    // 'event: <name>' and 'data: <json>' fields.
    const handleBlock = (block: string) => {
      const lines = block.split('\n')
      let event = 'message'
      const dataLines: string[] = []
      for (const line of lines) {
        if (line.startsWith(':')) continue  // comment / heartbeat
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length === 0) return
      const payload = JSON.parse(dataLines.join('\n'))
      if (event === 'thinking') h.onThinking?.(payload.text ?? '')
      else if (event === 'chunk') h.onChunk?.(payload.text ?? '')
      else if (event === 'soul_status') h.onSoulStatus?.(payload.statuses ?? {})
      else if (event === 'trace') h.onTrace?.(payload as TurnTrace)
      else if (event === 'done') final = payload as TurnResult
      else if (event === 'error')
        streamErr = new PlayError(500, payload.error ?? 'stream error')
    }

    // Stall watchdog — a half-open connection (mobile network blip,
    // proxy dropping the stream) leaves reader.read() pending forever
    // with no error, which froze the UI on an endless spinner. If no
    // bytes arrive for STALL_MS we abort and surface a retryable
    // "timed out" error instead.
    const STALL_MS = 90_000
    while (true) {
      let stallTimer: ReturnType<typeof setTimeout> | undefined
      const readP = reader.read()
      readP.catch(() => {})  // losing the race below must not be unhandled
      try {
        const { value, done: streamDone } = await Promise.race([
          readP,
          new Promise<never>((_, rej) => {
            stallTimer = setTimeout(
              () => rej(new PlayError(0, `stream timed out — no data for ${STALL_MS / 1000}s`)),
              STALL_MS,
            )
          }),
        ])
        if (streamDone) break
        buf += decoder.decode(value, { stream: true })
      } catch (e) {
        // Deliberate abort (user pressed Stop, or a superseding turn called
        // abort()): propagate the AbortError as-is so the caller can tell a
        // stop apart from a real stream failure. Wrapping it into a
        // PlayError made submit()'s catch miss the `instanceof DOMException`
        // check and fall through to the blocking-POST fallback — which
        // RE-RAN the turn, so Stop appeared to do nothing.
        if (controller.signal.aborted) {
          throw e instanceof DOMException ? e : new DOMException('aborted', 'AbortError')
        }
        controller.abort()
        streamErr = e instanceof PlayError ? e : new PlayError(0, String(e))
        break
      } finally {
        clearTimeout(stallTimer)
      }
      // Flush completed event blocks (separated by \n\n).
      let idx = buf.indexOf('\n\n')
      while (idx !== -1) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        if (block.trim()) handleBlock(block)
        idx = buf.indexOf('\n\n')
      }
    }
    if (streamErr) {
      h.onError?.(streamErr)
      throw streamErr
    }
    if (!final) {
      const err = new PlayError(0, 'stream ended without `done` event')
      h.onError?.(err)
      throw err
    }
    h.onDone?.(final)
    return final
  })()
  return { abort: () => controller.abort(), done }
}

// Per-user play saves owned by compute (the only place that has the
// `.neonrp/sessions/*.jsonl` files on disk). `in_memory:true` means the
// ConversationSession is still warm in the pool — entering the scene
// resumes instantly. `in_memory:false` = idle-evicted; today this
// means a cold start (full re-seed). When compute ships POST
// /play/resume the same slug entry warms back up from disk.
export type PlaySave = {
  session_id: string
  kind: string
  slug: string
  name?: string            // display name (for the account "my plays" list)
  started: number          // epoch seconds
  last_modified: number    // epoch seconds
  in_memory: boolean
}

export async function listSaves(): Promise<PlaySave[]> {
  const r = await fetch(`${ENDPOINT}/api/v1/play/saves`, {
    headers: authHeaders(),
  })
  if (!r.ok) {
    if (r.status === 404) return []  // older compute deploys
    throw new PlayError(r.status, `HTTP ${r.status}`)
  }
  const d = (await r.json()) as { saves?: PlaySave[] }
  return d.saves ?? []
}

// Delete a saved session — gateway evicts the warm pool entry AND
// removes the on-disk workdir, so it disappears from listSaves().
export async function deleteSave(sid: string): Promise<void> {
  const r = await fetch(
    `${ENDPOINT}/api/v1/play/session/${encodeURIComponent(sid)}`,
    { method: 'DELETE', headers: authHeaders() },
  )
  if (!r.ok && r.status !== 404)
    throw new PlayError(r.status, `HTTP ${r.status}`)
}
