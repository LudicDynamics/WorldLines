// 引擎面客户端(经典 `neonrp web` 协议)。默认同源('' base)—— wheel/
// 桌面/local 栈下引擎自己 serve 这份 SPA,/cmd · /events · /traces ·
// /rollback 直落当前会话;hosted 下同一协议经沙盒路由前缀直通每账户引擎
// (HUB-GOLIVE §P2 根治项:一份协议两个部署位,makeStageClient(base) 出装)。
// No Bearer here: binding a session is the shell's job(localClient.
// bindPlaySession / HubPrePlay),and the wrapped engine is single-swap。

import type { TraceRecord, TraceSummaryRow } from './events'

export type StageClient = {
  postCmd(text: string): Promise<{ ok: boolean; busy: boolean; error?: string }>
  postStart(): Promise<void>
  getTraces(): Promise<TraceSummaryRow[]>
  getTrace(i: number): Promise<TraceRecord | null>
  postRollback(commit: string): Promise<{ ok: boolean; error?: string }>
  getI18n(): Promise<{ locale: string; strings: Record<string, string> }>
  imageUrl(kind: 'world' | 'player' | 'soul', id?: string): string
}

export function makeStageClient(base = ''): StageClient {
  const B = base.replace(/\/$/, '')
  return {
    // Send the player's line for this turn. 409 = a turn is already running;
    // 429 = 配额墙(hosted 路由边界),以 error 面向内核呈现。
    async postCmd(text) {
      const r = await fetch(`${B}/cmd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
        credentials: 'include', // 分层部署下 play cookie 随行(同源无影响)
      })
      if (r.status === 409) return { ok: false, busy: true }
      if (r.status === 429) {
        const d = (await r.json().catch(() => ({}))) as { error?: string }
        return { ok: false, busy: false, error: d.error || 'quota exceeded' }
      }
      return { ok: r.ok, busy: false }
    },

    // Fire the localized opening once on a fresh game. Idempotent on the
    // server, so this is safe to call on every stage mount.
    async postStart() {
      await fetch(`${B}/start`, { method: 'POST', credentials: 'include' }).catch(() => {})
    },

    async getTraces() {
      try {
        const r = await fetch(`${B}/traces`, { credentials: 'include' })
        if (!r.ok) return []
        const d = (await r.json()) as { turns?: TraceSummaryRow[] }
        return d.turns ?? []
      } catch {
        return []
      }
    },

    async getTrace(i) {
      try {
        const r = await fetch(`${B}/trace?i=${i}`, { credentials: 'include' })
        if (!r.ok) return null
        return (await r.json()) as TraceRecord
      } catch {
        return null
      }
    },

    // Roll back onto a fresh branch at `commit`. The caller reloads on
    // success — the whole surface re-syncs from the new HEAD.
    async postRollback(commit) {
      try {
        const r = await fetch(`${B}/rollback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ commit }),
          credentials: 'include',
        })
        const d = (await r.json().catch(() => ({}))) as { ok?: boolean; error?: string }
        if (!r.ok || !d.ok) return { ok: false, error: d.error || `HTTP ${r.status}` }
        return { ok: true }
      } catch (e) {
        return { ok: false, error: String(e) }
      }
    },

    // Localized play string table, the same one the vanilla page reads
    // from window.__I18N__. strings is a flat key→text map.
    async getI18n() {
      try {
        let pin = ''
        try {
          pin = localStorage.getItem('wl-local-lang') || ''
        } catch {
          /* storage off */
        }
        const r = await fetch(pin ? `${B}/i18n?locale=${pin}` : `${B}/i18n`, { credentials: 'include' })
        if (!r.ok) return { locale: 'en', strings: {} }
        return (await r.json()) as { locale: string; strings: Record<string, string> }
      } catch {
        return { locale: 'en', strings: {} }
      }
    },

    // Portrait / cover art. `kind`: world · player · soul (needs id).
    imageUrl(kind, id) {
      const q = new URLSearchParams({ kind })
      if (id) q.set('id', id)
      return `${B}/image?${q.toString()}`
    },
  }
}

// 同源默认实例 —— 既有 local 调用面原样保留(拆工厂前逐字节同行为)。
const sameOrigin = makeStageClient('')
export const postCmd = sameOrigin.postCmd
export const postStart = sameOrigin.postStart
export const getTraces = sameOrigin.getTraces
export const getTrace = sameOrigin.getTrace
export const postRollback = sameOrigin.postRollback
export const getI18n = sameOrigin.getI18n
export const imageUrl = sameOrigin.imageUrl
