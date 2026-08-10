/**
 * Read-only client for the WorldHub / SoulHub S3 registries.
 *
 * The registries are public-read JSON at:
 *   https://worldlines-hub.s3.ap-northeast-1.amazonaws.com/<kind>/index.json
 *
 * Schema is defined in rp-hub/WORLDHUB.md §"index.json schema".
 */

export type Kind = 'worlds' | 'souls'

export type RegistryEntry = {
  hash: string
  slug: string
  name: string
  version: string
  changelog: string
  url: string
  size_bytes: number
  uploaded_at: string
  cover_url?: string
  unlisted?: boolean
}

export type Registry = {
  schema_version: number
  kind: Kind
  worlds?: RegistryEntry[]
  souls?: RegistryEntry[]
}

export type Story = {
  slug: string
  display_name: string
  latest_version: string
  latest_hash: string
  versions: RegistryEntry[]
}

// Single knob for where the catalog reads from. Keep the raw S3 origin
// out of marketing/UI surfaces — flip HUB_BASE to the worldlines.gg
// Cloudflare alias the moment that 302 rule is live (runbook:
// rp-hub/aws/cloudflare-routes.md). Until then we read S3 directly
// because the browser needs *some* CORS-enabled origin and the alias
// doesn't exist yet — this is the only place the bucket host appears
// in shipped code, by design.
//
//   alias live  → HUB_BASE = 'https://worldlines.gg/hub'
//   alias absent → HUB_BASE = the raw S3 origin (current)
const S3_ORIGIN = 'https://worldlines-hub.s3.ap-northeast-1.amazonaws.com'
const HUB_BASE = import.meta.env.VITE_HUB_BASE ?? S3_ORIGIN

export function registryUrl(kind: Kind): string {
  return `${HUB_BASE}/${kind}/index.json`
}

// C8:index 里的资产地址(cover_url / url)按 registry 惯例是根相对路径
// (如 /hubindex/worlds/x.png)。分层部署下页面在 dev-hub、资产在
// dev-compute —— 根相对会错解析到页面源。凡 HUB_BASE 是绝对 URL,就把
// 根相对资产钉到 HUB_BASE 的 origin;同源部署(HUB_BASE 相对)原样保留。
export function hubAssetUrl(u: string | undefined): string | undefined {
  if (!u) return u
  if (/^https?:\/\//i.test(u)) return u
  if (!/^https?:\/\//i.test(HUB_BASE)) return u
  if (!u.startsWith('/')) return u
  return new URL(u, HUB_BASE).toString()
}

export async function fetchRegistry(kind: Kind): Promise<Registry> {
  const url = registryUrl(kind)
  const resp = await fetch(url, { cache: 'no-cache' })
  if (resp.status === 404) {
    return { schema_version: 1, kind, [kind]: [] } as Registry
  }
  if (!resp.ok) {
    throw new Error(`Failed to fetch ${kind} registry: HTTP ${resp.status}`)
  }
  const data = (await resp.json()) as Registry
  // Defensive: backfill missing slug from name (parity with worldhub.py).
  const entries = (data[kind] ?? []) as RegistryEntry[]
  for (const e of entries) {
    if (!e.slug) e.slug = slugify(e.name || e.hash || 'unknown')
    if (e.changelog === undefined) e.changelog = ''
    // C8:在唯一入口处绝对化,所有消费方(封面/下载)免感知部署形态。
    e.url = hubAssetUrl(e.url) ?? e.url
    e.cover_url = hubAssetUrl(e.cover_url)
  }
  return { ...data, [kind]: entries }
}

function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

/**
 * Per-slug cover image map — fallback only. When the registry entry
 * carries a `cover_url` (S3-hosted), that takes priority over this
 * static map. New publishes carry `cover_url` via the v0.2 protocol
 * bump in rp-backend/registry_api.py.
 */
const COVER_MAP: Record<'worlds' | 'souls', Record<string, string>> = {
  worlds: {
    'stone-ford': '/covers/stone-ford.png',
    'dark-train': '/covers/dark-train.png',
  },
  souls: {
    elena: '/covers/elena.png',
    'elena-talk': '/covers/elena.png',
  },
}

export function coverFor(
  kind: Kind,
  slug: string,
  entry?: RegistryEntry | null,
): string | undefined {
  if (entry?.cover_url) return entry.cover_url
  return COVER_MAP[kind]?.[slug]
}

/** Group entries by slug, latest first. Skips unlisted entries. */
export function groupBySlug(entries: RegistryEntry[]): Story[] {
  const bySlug = new Map<string, RegistryEntry[]>()
  for (const e of entries) {
    if (e.unlisted) continue
    const list = bySlug.get(e.slug) ?? []
    list.push(e)
    bySlug.set(e.slug, list)
  }
  const stories: Story[] = []
  for (const [slug, vs] of bySlug) {
    vs.sort((a, b) => (b.uploaded_at ?? '').localeCompare(a.uploaded_at ?? ''))
    const latest = vs[0]
    stories.push({
      slug,
      display_name: latest.name ?? slug,
      latest_version: latest.version ?? '?',
      latest_hash: latest.hash ?? '',
      versions: vs,
    })
  }
  stories.sort((a, b) =>
    (b.versions[0].uploaded_at ?? '').localeCompare(a.versions[0].uploaded_at ?? ''),
  )
  return stories
}
