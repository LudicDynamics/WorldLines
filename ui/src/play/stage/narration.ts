// Narration text transforms, ported verbatim in behaviour from
// src/neonrp/webui/index.html (stripControl / cleanupNarration /
// formatNarration / cleanReason / statusPhrase). Pure functions — they take
// raw engine text and return escaped, span-wrapped HTML the components render
// with dangerouslySetInnerHTML. Escaping happens HERE, before any markup is
// injected, so untrusted narration can never inject nodes.

export function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

// Strip the world-agent's machine control block (⟦CORRECTIONS⟧…) — the engine
// removes it from the final record, but streamed tokens arrive raw.
export function stripControl(s: string): string {
  if (!s) return s
  return s
    .replace(/⟦CORRECTIONS⟧[\s\S]*?⟦\/CORRECTIONS⟧/g, '')
    .replace(/⟦CORRECTIONS⟧[\s\S]*$/g, '')
    .replace(/⟦\/?CORRECTIONS⟧/g, '')
}

function stripInlineMd(s: string): string {
  return String(s).replace(/\*\*(.+?)\*\*/g, '$1').replace(/[*_`]/g, '')
}

function choiceLabel(s: string): string {
  // "**住通铺（3铜）**：恢复 HP/MP" → "住通铺（3铜）" — the actionable title.
  const v = stripInlineMd(s).trim()
  const m = v.match(/^(.+?)\s*[：:]/)
  return (m ? m[1] : v).trim()
}

// A conservative post-pass that distinguishes spoken dialogue from inner
// thought from plain prose. Runs on COMPLETED narration (after streaming),
// never per-token. Escapes first, then wraps only unambiguous conventions.
function formatNarration(text: string): string {
  let s = esc(text)
  s = s.replace(
    /(「[^「」\n]{1,200}」|『[^『』\n]{1,200}』|“[^”\n]{1,200}”|"[^"\n]{1,200}")/g,
    '<span class="lc-speech">$1</span>',
  )
  s = s.replace(/(?<!\*)\*([^*\n]{1,120})\*(?!\*)/g, '<span class="lc-think">$1</span>')
  s = s.replace(/(（[^（）\n]{1,120}）|\([^()\n]{1,120}\))/g, '<span class="lc-think">$1</span>')
  s = s.replace(/[*_`]/g, '')
  return s
}

export type CleanedNarration = { html: string; table: string | null; choices: string[] }

// Lift machine-state out of the narration at turn end: the clue/status table
// folds away, `## time/location` headers + tool-echo lines drop, and the
// "你可以：" choice list is extracted. Conservative — only unambiguous machine
// lines are touched.
export function cleanupNarration(rawIn: string): CleanedNarration {
  const raw = stripControl(rawIn || '')
  if (!raw.trim()) return { html: '', table: null, choices: [] }
  const prose: string[] = []
  const tbl: string[] = []
  const choices: string[] = []
  let inChoices = false
  for (const ln of raw.split('\n')) {
    const t = ln.trim()
    if (!inChoices && /^(你可以|可选行动|你的选择)\s*[：:]\s*\*{0,2}\s*$/.test(t)) {
      inChoices = true
      continue
    }
    if (inChoices) {
      const item = t.match(/^(?:\d+[.、)]\s*|[-*•]\s*)(.+)$/)
      if (item) {
        choices.push(choiceLabel(item[1]))
        continue
      }
      if (!t) continue
      inChoices = false
    }
    if (/^\|.*\|?$/.test(t) || (t && /^:?-{2,}/.test(t.replace(/\|/g, '').trim()))) {
      tbl.push(ln)
      continue
    }
    if (/^[✦⚙▸▍]/.test(t)) continue
    if (/^#{1,6}\s/.test(t)) continue
    prose.push(ln)
  }
  const clean = prose
    .join('\n')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/[_`]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return {
    html: formatNarration(clean),
    table: tbl.length >= 2 ? tbl.join('\n').trim() : null,
    choices,
  }
}

// Strip engine internals out of an agent's stated reason/intent so a lane
// reads like a person thinking, not a debugger.
export function cleanReason(s: unknown): string {
  return String(s || '')
    .replace(/\s*\(\s*[01]?\.\d+\s*\)/g, '')
    .replace(/\s*\(\s*away from player\s*\)/gi, '')
    .replace(/\s*\bin (?:the )?location group\b[^,.;，。]*/gi, '')
    .replace(/\s*\bgroup\s+['"]?[A-Za-z]\d{2,}['"]?/g, '')
    .replace(/\s*['"][A-Za-z]\d{2,}['"]/g, '')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

// The per-soul diagnostic "reason" → plain-language register, localized via T.
export function statusPhrase(reason: unknown, t: (k: string) => string): string {
  const s = String(reason || '').toLowerCase()
  if (s.includes('co-located') || s.includes('kept with player')) return t('status.with_you')
  if (s.startsWith('active')) return t('status.active_away')
  if (s.startsWith('inactive')) return t('status.offstage')
  return cleanReason(reason)
}
