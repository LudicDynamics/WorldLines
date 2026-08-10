/**
 * Client for the LOCAL engine server (`neonrp web`) — the LocalShell's
 * data layer (docs/WEBUI-UNIFICATION.md L1).
 *
 * Talks two API layers of the same server:
 *  - contract:   /api/v1/meta · /api/v1/play/* · /api/v1/create/*
 *  - local shell: /api/v1/local/*  (library / souls / settings)
 *
 * No auth — the local engine is single-user (meta.auth === "none").
 */

// VITE_PLAY_ENDPOINT is three-state (docs/WEBUI-UNIFICATION.md §7.5 LP1):
//  - explicit '' (wheel build: `VITE_PLAY_ENDPOINT= npm run build`) → same-origin
//    mode: the engine itself serves this SPA, so all fetches use relative paths;
//  - undefined (plain dev `npm run dev`)                            → the local
//    engine's default port, http://127.0.0.1:8787;
//  - any other value                                                → used as-is.
import { computeOrigin } from '../play/playClient'

const RAW_LOCAL = import.meta.env.VITE_PLAY_ENDPOINT as string | undefined
const DEFAULT_ENDPOINT = RAW_LOCAL === '' ? '' : RAW_LOCAL ?? 'http://127.0.0.1:8787'

// 可变基址(HUB-GOLIVE §P1.5 同源化):local 入口保持默认;hub 入口在
// main-hub 顶层 setLocalApiBase('/api/v1/play/engine') —— 同一批组件
// (创作门/工坊/导入/PrePlay/资料)经沙盒路由直通账户引擎的 local API,
// 组件零分叉。
let LOCAL_ENDPOINT = DEFAULT_ENDPOINT

export function setLocalApiBase(base: string): void {
  LOCAL_ENDPOINT = base.replace(/\/$/, '')
}

export function localEndpoint(): string {
  return LOCAL_ENDPOINT
}

// ── shapes ──────────────────────────────────────────────────────────────

export type LocalMeta = {
  implementation: string
  engine_version: string
  auth: string
  capabilities: Record<string, boolean>
}

export type LocalSave = {
  session_id: string
  kind: string
  slug: string
  name: string
  started?: string | null
  last_modified: number
  in_memory: boolean
  feed_tease: string
  feed_time: string
  waiting: string[]
}

export type LocalWorld = {
  id: string
  name: string
  name_local?: string
  display_name?: string
  desc?: string
  owned?: boolean
  origin?: 'created' | 'downloaded'
  hidden?: boolean
}

export type LocalSoul = {
  sid: string
  dir_name?: string
  name?: string
  name_local?: string
  display_name?: string
  source?: string
  mtime?: number
}

export type PresetInfo = {
  id: string
  display: string
  available: boolean
  from_user_config?: boolean
}

export type TreeFile = { path: string; size: number }

export type EditEvent =
  | { kind: 'thinking'; text: string }
  | { kind: 'chunk'; text: string }
  | { kind: 'tool_use'; name: string; path: string }
  | { kind: 'tool_result'; name: string; path: string; summary: string }
  | { kind: 'error'; error: string }
  | { kind: 'done'; success: boolean; assistant_message: string; world_id: string }

// ── plumbing ────────────────────────────────────────────────────────────

// credentials:'include' — 分层部署(Hub 页面在 CloudFront、compute 在
// 另一子域)是同站跨源,play cookie 只有带上凭据才会随行;同源部署无影响。
async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${LOCAL_ENDPOINT}${path}`, { credentials: 'include' })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return (await r.json()) as T
}

async function jsend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${LOCAL_ENDPOINT}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'include',
  })
  if (!r.ok) throw new Error(`${path} → ${r.status} ${await r.text().catch(() => '')}`)
  return (await r.json()) as T
}

// ── contract: meta / play ───────────────────────────────────────────────

export const getMeta = () => jget<LocalMeta>('/api/v1/meta')

export const listLocalSaves = async (): Promise<LocalSave[]> =>
  (await jget<{ saves: LocalSave[] }>('/api/v1/play/saves')).saves

/** Bind the wrapped play session to a save (session_id), an owned world id,
 * or a built-in world id (scaffolds a fresh run). Returns the run slug.
 * opts.preset 写进本局 run 的 config;opts.souls 只对新建 run 投放(Casting)。 */
export async function bindPlaySession(
  slug: string,
  opts: { preset?: string; souls?: string[] } = {},
): Promise<string> {
  const d = await jsend<{ slug: string }>('POST', '/api/v1/play/session', {
    slug,
    preset: opts.preset || undefined,
    souls: opts.souls?.length ? opts.souls : undefined,
  })
  return d.slug
}

export const deleteSave = (sid: string) =>
  jsend<{ ok: boolean }>('DELETE', `/api/v1/play/saves/${encodeURIComponent(sid)}`)

// ── local shell: library / souls / settings ─────────────────────────────

export const listLocalWorlds = () =>
  jget<{ worlds: LocalWorld[]; builtin: LocalWorld[] }>('/api/v1/local/worlds')

export const deleteLocalWorld = (id: string) =>
  jsend<{ ok: boolean }>('DELETE', `/api/v1/local/worlds/${encodeURIComponent(id)}`)

export const worldCoverUrl = (id: string) =>
  `${LOCAL_ENDPOINT}/api/v1/local/worlds/${encodeURIComponent(id)}/cover`

export const worldExportUrl = (id: string) =>
  `${LOCAL_ENDPOINT}/api/v1/local/worlds/${encodeURIComponent(id)}/export`

/** 世界 zip → 库(B2)。返回落地的 world_id(重名自动带时间戳后缀)。 */
export async function importWorldZip(file: File): Promise<string> {
  const r = await fetch(`${LOCAL_ENDPOINT}/api/v1/local/import/world`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/zip' },
    body: file,
  })
  const d = (await r.json()) as { ok: boolean; world_id?: string; error?: string }
  if (!r.ok || !d.ok) throw new Error(d.error || `import → ${r.status}`)
  return d.world_id!
}

/** 卡片入工坊(新导入 UX):秒回,零 LLM —— 建工作台 + 持久化源卡,
 *  转换路径(①计划-分批/②一次性/③手动)在工坊三选项面板里选。 */
export type ImportCardResult = {
  ok: boolean
  world_id: string
  kind: 'world' | 'soul'
  import: {
    source_rel: string
    format: string
    bytes: number
    entries: number
    recommend_plan: boolean
  }
}
export async function importCardToStudio(
  file: File,
  kind: 'world' | 'soul',
): Promise<ImportCardResult> {
  const q = new URLSearchParams({ filename: file.name, kind })
  const r = await fetch(`${LOCAL_ENDPOINT}/api/v1/local/import/card?${q}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  })
  const d = (await r.json()) as ImportCardResult & { error?: string }
  if (!r.ok || !d.ok) throw new Error(d.error || `import → ${r.status}`)
  return d
}

/** 工坊导入面板的数据源:源卡/估计/计划进度/三条开场指令。 */
export type ImportStatus = {
  has_source: boolean
  source_rel?: string
  kind?: 'world' | 'soul'
  format?: string
  bytes?: number
  entries?: number
  recommend_plan?: boolean
  plan?: { done: number; total: number; next_title: string; complete: boolean } | null
  start_command?: string
  resume_command?: string | null
  oneshot_command?: string
}
export const getImportStatus = () =>
  jget<ImportStatus>('/api/v1/create/session/edit-local/import-status')
export const importSourceUrl = () =>
  `${LOCAL_ENDPOINT}/api/v1/create/session/edit-local/import-source`

/** 上传 owned 世界 / 库 soul 到 Hub(B9)。token = worldlines.gg/account。 */
export const hubUpload = (opts: {
  kind: 'worlds' | 'souls'
  id: string
  token: string
  name?: string
  version?: string
  changelog?: string
  unlisted?: boolean
}) =>
  jsend<{ ok: boolean; entry?: Record<string, unknown>; error?: string }>(
    'POST', '/api/v1/local/hub/upload', opts)

export const listLocalSouls = () =>
  jget<{ souls: LocalSoul[]; avatars: unknown[] }>('/api/v1/local/souls')

export const deleteLocalSoul = (dirName: string) =>
  jsend<{ ok: boolean }>('DELETE', `/api/v1/local/souls/${encodeURIComponent(dirName)}`)

export type ImageSettings = {
  backend: string
  comfyui_url: string
  comfyui_ckpt: string
  comfyui_workflow: string
  comfyui_input_node: string
  comfyui_neg_node: string
  comfyui_output_node: string
  comfyui_seed_node: string
  openai_model: string
  openai_key_set: boolean
  configured: boolean
}

export const getSettings = () =>
  jget<{ presets: PresetInfo[]; create_provider: string | null; image?: ImageSettings }>(
    '/api/v1/local/settings')

export const setCreateProvider = (presetId: string | null) =>
  jsend<{ ok: boolean }>('PUT', '/api/v1/local/settings/create-provider', {
    preset_id: presetId,
  })

export const putImageSettings = (patch: Partial<Record<
  | 'backend' | 'comfyui_url' | 'comfyui_ckpt' | 'comfyui_workflow'
  | 'comfyui_input_node' | 'comfyui_neg_node' | 'comfyui_output_node'
  | 'comfyui_seed_node' | 'openai_key' | 'openai_model', string>>) =>
  jsend<{ ok: boolean; configured: boolean }>('PUT', '/api/v1/local/settings/image', patch)

export const deleteSettingsEntry = (entryId: string) =>
  jsend<{ ok: boolean; presets: PresetInfo[] }>(
    'DELETE', `/api/v1/local/settings/entry/${encodeURIComponent(entryId)}`)

export const testAllProviders = () =>
  jsend<{ results: Array<{ id: string; ok?: boolean; error?: string; latency_ms?: number }> }>(
    'POST', '/api/v1/local/settings/test-all', {})

export const saveProviderKey = (presetId: string, apiKey: string, modelOverride?: string) =>
  jsend<{ ok: boolean; presets: PresetInfo[] }>('PUT', '/api/v1/local/settings/key', {
    preset_id: presetId,
    api_key: apiKey,
    model_override: modelOverride,
  })

export const testProvider = (presetId: string) =>
  jsend<Record<string, unknown>>('POST', '/api/v1/local/settings/test', {
    preset_id: presetId,
  })

// 添加自定义 OpenAI 兼容 API 端点(自建/本地 LLM:填 base_url + 模型名 + 可选 key)。
export const addCustomModel = (m: { id: string; base_url: string; model: string; api_key?: string }) =>
  jsend<{ ok: boolean; id: string; presets: PresetInfo[] }>('PUT', '/api/v1/local/settings/custom-model', m)

// ── contract: create (edit sessions) ────────────────────────────────────

export type CreateSession = {
  session_id: string
  world_id: string
  template: string | null
  files: TreeFile[]
}

export const openCreateSession = (opts: { template?: string; world_id?: string; name?: string }) =>
  jsend<CreateSession>('POST', '/api/v1/create/session', opts)

export const getEditTree = () =>
  jget<{ world_id: string; world_name?: string; files: TreeFile[] }>(
    '/api/v1/create/session/edit-local/tree')

export const readEditFile = (path: string) =>
  jget<{ path: string; content: string }>(
    `/api/v1/create/session/edit-local/file?path=${encodeURIComponent(path)}`,
  )

export const renameEditWorld = (name: string) =>
  jsend<{ ok: boolean; world_name: string }>(
    'PUT', '/api/v1/create/session/edit-local/name', { name })

export const setEditLlm = (presetId: string) =>
  jsend<{ ok: boolean; preset: string }>(
    'PUT', '/api/v1/create/session/edit-local/llm', { preset_id: presetId })

export const playtestEditWorld = () =>
  jsend<{ slug: string }>('POST', '/api/v1/create/session/edit-local/playtest', {})

/** One edit turn as a stream of typed events (SSE over fetch — same manual
 * parser approach as playClient's sendTurnStream). */
export async function sendEditMessage(
  input: string,
  onEvent: (ev: EditEvent) => void,
): Promise<void> {
  const resp = await fetch(
    `${LOCAL_ENDPOINT}/api/v1/create/session/edit-local/message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
    },
  )
  if (!resp.ok || !resp.body) throw new Error(`message → ${resp.status}`)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let eventName = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    for (;;) {
      const nl = buf.indexOf('\n')
      if (nl < 0) break
      const line = buf.slice(0, nl).replace(/\r$/, '')
      buf = buf.slice(nl + 1)
      if (line.startsWith('event: ')) {
        eventName = line.slice(7)
      } else if (line.startsWith('data: ') && eventName) {
        try {
          const data = JSON.parse(line.slice(6))
          onEvent({ kind: eventName, ...data } as EditEvent)
        } catch {
          /* malformed frame — skip */
        }
        if (eventName === 'done' || eventName === 'error') return
        eventName = ''
      }
    }
  }
}

// ── 审查线(HUB-GOLIVE §P5)────────────────────────────────────────────
// submit 走引擎面(打包+POST registry);状态查询走路由 owner 面
// (/api/v1/play/submissions,绝对路径 —— 只在 hub 栈里有意义)。

export type SubmissionMeta = {
  kind: string
  slug: string
  stamp: string
  name: string
  summary: string
  version: string
  uploader: string
  status: 'pending' | 'approved' | 'rejected'
  review_note: string
  submitted_at: string
  reviewed_at: string | null
  hash: string
  size_bytes: number
  precheck: {
    playable: boolean
    flavor?: string
    blockers?: { summary?: string }[]
    blockers_count?: number
    warnings_count?: number
  }
}

export async function submitForReview(
  kind: 'worlds' | 'souls',
  id: string,
  name?: string,
  summary?: string,
): Promise<SubmissionMeta> {
  const r = await jsend<{ ok: boolean; meta: SubmissionMeta }>(
    'POST',
    '/api/v1/local/hub/submit',
    { kind, id, name, summary },
  )
  return r.meta
}

export async function mySubmissions(): Promise<SubmissionMeta[]> {
  // owner 面挂在路由(compute)上,不走引擎前缀 —— 分层部署时需 compute origin。
  const r = await fetch(`${computeOrigin()}/api/v1/play/submissions`, { credentials: 'include' })
  if (!r.ok) throw new Error(`submissions → ${r.status}`)
  const d = (await r.json()) as { submissions: SubmissionMeta[] }
  return d.submissions || []
}
