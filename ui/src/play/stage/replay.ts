// Replay / resume block rendering — the "where you left off" context on a
// continued game, and the ⏪ REPLAY step-through. Ported from renderReplayTurn
// in src/neonrp/webui/index.html. Returns escaped HTML (rendered with
// dangerouslySetInnerHTML) plus the restore commit for a rollback button.

import { esc } from './narration'
import type { TraceRecord } from './events'
import type { T } from './strings'

export type ReplayBlock = { html: string; rollback: { commit: string; turnSeq?: number } | null }

function placeName(node: unknown, places: Record<string, string>): string {
  const n = String(node || '').replace(/^loc:/, '')
  return places[n] || n
}

export function renderReplayTurn(
  tr: TraceRecord,
  opts: { resume?: boolean },
  t: T,
  places: Record<string, string>,
): ReplayBlock {
  const land = tr.land || {}
  const head = opts.resume ? t('replay.resume') : t('replay.head')
  let html =
    `<div class="lc-rphead">⏪ ${esc(head)} · turn_seq=${esc(tr.turn_seq)} · ${esc(tr.world_location || '?')}` +
    ` · ${esc((land.commit_id || '').slice(0, 8))} · ${esc((tr.ts || '').slice(11, 19))}</div>`
  const input = tr.player?.input || ''
  if (input) html += `<div class="lc-you">${esc(input)}</div>`
  for (const m of tr.bus_messages || []) {
    if (m.topic !== 'world/narration') continue
    const p = (m.payload as Record<string, unknown>) || {}
    const text = String(p.text || '').slice(0, 1500)
    if (String(p.world_agent_id || '').startsWith('loc:')) {
      html += `<div class="lc-locnarr">📍 ${esc(placeName(p.location || p.world_agent_id, places))}:<br>${esc(text)}</div>`
    } else if (text) {
      html += `<div class="lc-narr">${esc(text)}</div>`
    }
  }
  for (const m of tr.bus_messages || []) {
    const p = (m.payload as Record<string, unknown>) || {}
    const topic = String(m.topic || '')
    if (topic.endsWith('/request')) {
      html += `<div class="lc-agentline">👁 <b>${esc(p.instance_id || '?')}</b> ${esc(t('replay.perceive'))}: ${esc(
        p.scene_label || '?',
      )}</div>`
    }
    if (topic.endsWith('/response') && p.digest) {
      const d = String(p.digest)
      const sp = d.match(/speech=([^|]+)/)
      const act = d.match(/action=([^|]+)/)
      const mv = d.match(/moved_to=([^|]+)/)
      let line = `<b>${esc(p.instance_id || '?')}</b>`
      if (sp) line += ` 💬 ${esc(sp[1].trim().slice(0, 100))}`
      if (act) line += ` → ${esc(act[1].trim().slice(0, 80))}`
      if (mv) line += ` <span class="lc-move">⇒ ${esc(mv[1].trim())}</span>`
      html += `<div class="lc-agentline">${line}</div>`
    }
  }
  return { html, rollback: land.commit_id ? { commit: land.commit_id, turnSeq: tr.turn_seq } : null }
}
