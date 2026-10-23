// WorldLines client — the whole protocol in one file (copy it into your own project).
//
// A WorldLines host (`neonrp serve`) runs the world; a client sends lines and listens:
//   POST /rpc          JSON-RPC 2.0 requests: session.hello · turn.send · turn.cancel · session.state · reply
//   GET  /rpc/events   server-sent events, one JSON-RPC message each:
//                        notification  { method: "bus.message", params: { topic, seq, payload } }
//                        request       { id, method: "ask_user", params: { question, options } }  → answer with `reply`
//   GET  /api/v1/play/engine/beat-kinds   how this run's beats are shown (declared by the play pack; {kinds: {}} = one plain turn)
// Auth: `Authorization: Bearer <token>` (printed by `neonrp serve`).
//
// The client knows no particular beat. Whatever the run's orchestration has (a plain turn, or planning + resolve, or
// day / night …), its names, tones and hints come from beat-kinds — the same code shows every kind of game.

export const PROTOCOL = 'worldlines.net/1'

// ── what the host sends ─────────────────────────────────────────────────────────────────────────────────────────────
export interface BeatKind {
  label?: string                      // the beat's name
  tone?: string                       // a style hint ("plan", "res" …); unknown → neutral
  live?: string                       // title while it streams
  host?: string                       // title of a landed host line
  narr?: string                       // title of the narration it lands
  you?: string                        // subtitle of the player's line
  placeholder?: string                // input placeholder while this beat leads
  chips?: string[]                    // suggestions under the input
  divider_from?: Record<string, string>  // a divider when entering this beat from another
}
export interface BeatKinds { start?: string; kinds: Record<string, BeatKind> }

/** One beat event (engine/beat): node.enter / node.leave / <node>.beat / dice / tool / state.changed / run.settled / away … */
export interface BeatEvent { kind: string; turn?: number; [field: string]: unknown }
export interface TurnResult { success: boolean; error?: string | null; assistant_message?: string; options?: string[]; cancelled?: boolean }

export interface Handlers {
  /** a piece of prose as it is written; `beat` = the node it belongs to (absent before the first beat) */
  onChunk?(text: string, beat: string | undefined): void
  onBeat?(event: BeatEvent): void
  onTurnStarted?(): void
  onTurnFinished?(ok: boolean, error: string | null): void
  /** the world asks the player something; return the chosen answer (or null to skip) */
  onAsk?(question: string, options: string[]): Promise<string | null> | string | null
  onConnection?(state: 'open' | 'retrying', detail?: string): void
}

export class RpcError extends Error {
  code: number
  constructor(code: number, message: string) { super(message); this.code = code }
}

/** JSON-RPC error codes the host uses (besides the spec's). */
export const ERR = { UNAUTHORIZED: -32001, BUSY: -32002, VERSION_MISMATCH: -32003, NO_SESSION: -32004 } as const

export class WorldLinesClient {
  private nextId = 1
  private seq: number | null = null
  private stop = false
  private abort: AbortController | null = null
  readonly clientId = Math.random().toString(16).slice(2, 10)

  private base: string
  private token: string
  private on: Handlers

  /** `base` = the host URL ("" when a dev proxy serves the page from the same origin). */
  constructor(base: string, token: string, on: Handlers = {}) { this.base = base; this.token = token; this.on = on }

  /** Hand the stream to another screen (the title screen connects; a game screen takes over). */
  setHandlers(on: Handlers): void { this.on = on }

  private headers(): Record<string, string> {
    return { 'Content-Type': 'application/json', Authorization: `Bearer ${this.token}` }
  }

  async call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    let r: Response
    try {
      r = await fetch(`${this.base}/rpc`, { method: 'POST', headers: this.headers(), body: JSON.stringify({ jsonrpc: '2.0', id: this.nextId++, method, params }) })
    } catch (e) {
      throw new RpcError(0, `cannot reach the host at ${this.base || location.origin} — is \`neonrp serve\` running?`)
    }
    const msg = await r.json().catch(() => null)
    if (!msg) throw new RpcError(r.status, `HTTP ${r.status}`)
    if (msg.error) throw new RpcError(msg.error.code, msg.error.message)
    return msg.result as T
  }

  /** Handshake + start listening. Throws a readable RpcError (bad token, wrong protocol, no host). */
  async connect(): Promise<{ protocol: string; world: string | null; agent_id: string | null }> {
    const hello = await this.call<{ protocol: string; world: string | null; agent_id: string | null }>('session.hello', { protocol: PROTOCOL })
    void this.listen()
    return hello
  }

  close(): void { this.stop = true; this.abort?.abort() }

  /** How this run's beats are shown. No session yet / an older host → no declarations (show a plain turn). */
  async beatKinds(): Promise<BeatKinds> {
    try {
      const r = await fetch(`${this.base}/api/v1/play/engine/beat-kinds`, { headers: this.headers() })
      return r.ok ? await r.json() : { kinds: {} }
    } catch { return { kinds: {} } }
  }

  /** Play one line; resolves when the turn is over (prose arrives meanwhile through onChunk / onBeat). */
  send(text: string): Promise<TurnResult> {
    return this.call<TurnResult>('turn.send', { text, client: this.clientId })
  }

  cancel(): Promise<unknown> { return this.call('turn.cancel') }

  // ── the event stream: fetch (not EventSource) so the token can ride in a header; reconnects with `since` ──────────
  private async listen(): Promise<void> {
    while (!this.stop) {
      const q = `?client=${this.clientId}` + (this.seq !== null ? `&since=${this.seq}` : '')
      try {
        this.abort = new AbortController()
        const r = await fetch(`${this.base}/rpc/events${q}`, { headers: this.headers(), signal: this.abort.signal })
        if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`)
        this.on.onConnection?.('open')
        const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
        let buf = ''
        for (;;) {
          const { value, done } = await reader.read()
          if (done || this.stop) break
          buf += value
          let i: number
          while ((i = buf.indexOf('\n\n')) >= 0) {
            const frame = buf.slice(0, i); buf = buf.slice(i + 2)
            for (const line of frame.split('\n')) if (line.startsWith('data: ')) this.dispatch(JSON.parse(line.slice(6)))
          }
        }
      } catch (e) {
        if (this.stop) return   // closed on purpose
        this.on.onConnection?.('retrying', String((e as Error).message || e))
      }
      if (!this.stop) await new Promise(res => setTimeout(res, 1000))
    }
  }

  private dispatch(msg: { id?: string | number; method?: string; params?: Record<string, any> }): void {
    const p = msg.params || {}
    if (msg.method === 'ask_user' && msg.id !== undefined) {
      Promise.resolve(this.on.onAsk ? this.on.onAsk(String(p.question || ''), (p.options as string[]) || []) : null)
        .then(ans => this.call('reply', { id: msg.id, result: ans }))
        .catch(() => {})
      return
    }
    if (msg.method !== 'bus.message') return
    this.seq = Number(p.seq ?? this.seq ?? 0)
    const topic = String(p.topic || ''), pl = (p.payload || {}) as Record<string, any>
    if (topic === 'engine/stream' && pl.kind === 'chunk') this.on.onChunk?.(String(pl.text || ''), pl.beat as string | undefined)
    else if (topic === 'engine/beat') this.on.onBeat?.(pl as BeatEvent)
    else if (topic === 'engine/event' && pl.kind === 'turn_started') this.on.onTurnStarted?.()
    else if (topic === 'engine/event' && pl.kind === 'turn_finished') this.on.onTurnFinished?.(!!pl.success, (pl.error as string) ?? null)
  }
}

/** Who wrote a chunk: a character's words carry [[subagent:<name>]] (on every piece); a chunk without it is the host.
 *  Returns the speaker ('' = the host) and the text without markers. */
export function speaker(text: string): { who: string; text: string } {
  const m = /^\[\[subagent:([^\]]+)\]\]/.exec(text)
  return { who: m ? m[1] : '', text: text.replace(/\[\[subagent:[^\]]+\]\]/g, '') }
}

/** A readable sentence for the errors a player can actually hit. */
export function explain(e: unknown): string {
  if (e instanceof RpcError) {
    if (e.code === ERR.UNAUTHORIZED) return 'The token is wrong — use the one `neonrp serve` printed.'
    if (e.code === ERR.BUSY) return 'A turn is still running — wait for it to finish.'
    if (e.code === ERR.VERSION_MISMATCH) return `This host speaks another protocol version (${e.message}).`
    if (e.code === ERR.NO_SESSION) return 'The host has no world open yet.'
    return e.message
  }
  return String((e as Error)?.message || e)
}
