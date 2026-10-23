// Plain reads the host answers over HTTP (besides the JSON-RPC session): who is where, the variables, the template,
// the settlement at the end. Every one is optional — a host without it just gives the client less to draw.
export interface HostState {
  player_location?: string
  player_name?: string
  player_hp?: { current: number; max: number }
  places?: Record<string, string>
  souls?: { sid: string; instance_id: string; name: string; location: string; where?: string }[]
}
export interface Settlement {
  exit?: { kind: string; id?: string; turn?: number }
  epilogue?: string
  cg_unlocked?: string[]
  truth_reveal?: { text?: string }
  deaths?: { who: string; name?: string }[]
  rewards?: Record<string, Record<string, unknown>>
}

export class HostReads {
  private base: string
  private token: string
  constructor(base: string, token: string) { this.base = base; this.token = token }

  private async get<T>(path: string): Promise<T | null> {
    try {
      const r = await fetch(`${this.base}${path}`, { headers: { Authorization: `Bearer ${this.token}` } })
      return r.ok ? ((await r.json()) as T) : null
    } catch { return null }
  }

  state(): Promise<HostState | null> { return this.get<HostState>('/state') }

  /** The run's variables with their specs (max · doc), for a screen that needs more than the values. */
  async schema(): Promise<{ name: string; value: unknown; max?: number; doc?: string }[]> {
    const d = await this.get<{ variables?: { name: string; value: unknown; max?: number; doc?: string }[] }>('/api/v1/play/schema')
    return d?.variables || []
  }

  async templateId(): Promise<string | null> {
    const d = await this.get<{ template?: { id?: string } }>('/api/v1/play/engine/template')
    return d?.template?.id || null
  }

  /** The run's variables, name → value (player.hp, player.san, time.clock, P01.stage …). */
  async vars(): Promise<Record<string, unknown>> {
    const d = await this.get<{ variables?: { name: string; value: unknown }[] }>('/api/v1/play/schema')
    return Object.fromEntries((d?.variables || []).map(v => [v.name, v.value]))
  }

  async settlement(): Promise<Settlement | null> {
    const d = await this.get<Settlement>('/api/v1/play/engine/settlement')
    return d && d.exit ? d : null
  }

  async conditions(): Promise<{ name: string; props: Record<string, unknown> }[]> {
    const d = await this.get<{ entities?: { name: string; parent?: string; props?: Record<string, unknown> }[] }>('/api/v1/play/engine/entities?cls=status')
    return (d?.entities || []).filter(e => !e.parent || e.parent === 'player').map(e => ({ name: e.name, props: e.props || {} }))
  }
}
