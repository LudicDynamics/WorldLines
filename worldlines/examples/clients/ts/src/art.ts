// A world's art pack (examples/clients/art/<world>/art.json): which picture goes with which place, person, ending, clue.
// Missing pictures are fine — `has()` says so and the game draws a placeholder instead.
export interface Clue { id: string; title: string; text?: string; art?: string; when: { var: string; gte: number } }
export interface ArtPack {
  world: string; title?: string; subtitle?: string; pitch?: string; title_art?: string
  scenes?: Record<string, string>; fallback_scene?: string
  portraits?: Record<string, { name?: string; base?: string; variants?: Record<string, string> }>
  speakers?: Record<string, string>; npcs_by_place?: Record<string, string[]>
  endings?: Record<string, string>; clues?: Clue[]
  map?: { art?: string; rooms?: Record<string, { label: string; x: number; y: number; go?: string }>; links?: [string, string][] }
  dice?: string; meters?: Record<string, { label: string; max: number }>
}

const seen = new Map<string, Promise<boolean>>()

export class Art {
  pack: ArtPack
  private root: string
  constructor(pack: ArtPack, root: string) { this.pack = pack; this.root = root }

  static async load(world: string | null): Promise<Art> {
    const base = (import.meta as { env?: Record<string, string> }).env?.BASE_URL || '/'   // '/' under the dev server · './' when built with --base ./ (served from any folder: the studio's 前端 desk)
    if (world) {
      try {
        const r = await fetch(`${base}${world}/art.json`)
        if (r.ok) return new Art(await r.json(), `${base}${world}/`)
      } catch { /* no pack for this world */ }
    }
    return new Art({ world: world || '' }, base)
  }

  url(rel?: string): string | null { return rel ? this.root + rel : null }

  /** Does this picture exist? (asked once per file) */
  has(rel?: string): Promise<boolean> {
    const u = this.url(rel)
    if (!u) return Promise.resolve(false)
    if (!seen.has(u)) seen.set(u, new Promise(res => { const i = new Image(); i.onload = () => res(true); i.onerror = () => res(false); i.src = u }))
    return seen.get(u)!
  }

  scene(place?: string): string | undefined { return (place && this.pack.scenes?.[place]) || undefined }
  portraitOf(name: string): string | undefined {
    const id = this.pack.speakers?.[name]
    return id ? this.pack.portraits?.[id]?.base : undefined
  }
}
