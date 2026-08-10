// Minimal admin dashboard — the genre tree first (the bubble picker
// reads this), more sections (prompts, agents-rules) drop in next.
// Auth: a Bearer token stored in localStorage under rp-hub:admin.
// If the gateway has no HUB_ADMIN_TOKEN set, the dev backend is open
// and any token (including empty) works.
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useI18n } from '../shared/i18n'
import { GENRE_TREE } from './genres'

const CREATE_ENDPOINT =
  (import.meta.env.VITE_CREATE_ENDPOINT as string | undefined) ??
  'http://127.0.0.1:8098'

const TOK_KEY = 'rp-hub:admin'

function getTok(): string {
  try {
    return localStorage.getItem(TOK_KEY) || ''
  } catch {
    return ''
  }
}
function setTok(t: string) {
  try {
    if (t) localStorage.setItem(TOK_KEY, t)
    else localStorage.removeItem(TOK_KEY)
  } catch {
    /* storage off */
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'content-type': 'application/json' }
  const t = getTok()
  if (t) h.authorization = `Bearer ${t}`
  return h
}

export function AdminPage() {
  const { t } = useI18n()
  const [tok, setTokState] = useState(getTok())
  const [text, setText] = useState('')
  const [original, setOriginal] = useState('')
  const [status, setStatus] = useState<
    'idle' | 'loading' | 'saving' | 'saved' | 'error'
  >('loading')
  const [error, setError] = useState('')

  const defaultJson = JSON.stringify(GENRE_TREE, null, 2)

  const load = useCallback(async () => {
    setStatus('loading')
    setError('')
    try {
      const r = await fetch(
        `${CREATE_ENDPOINT}/api/v1/admin/genre_tree`,
        { headers: headers() },
      )
      if (!r.ok) throw new Error(`${r.status}`)
      const d = await r.json()
      const ov = (d.override || '').trim()
      const initial = ov || defaultJson
      setText(initial)
      setOriginal(initial)
      setStatus('idle')
    } catch (e) {
      setStatus('error')
      setError(String(e))
    }
  }, [defaultJson])

  useEffect(() => {
    load()
  }, [load])

  let jsonErr = ''
  if (text.trim()) {
    try {
      const v = JSON.parse(text)
      if (!Array.isArray(v)) jsonErr = 'root must be an array'
    } catch (e) {
      jsonErr = String((e as Error).message)
    }
  }

  const save = useCallback(async () => {
    if (jsonErr) return
    setStatus('saving')
    setError('')
    try {
      const r = await fetch(
        `${CREATE_ENDPOINT}/api/v1/admin/genre_tree`,
        {
          method: 'PUT',
          headers: headers(),
          body: JSON.stringify({ override: text }),
        },
      )
      if (!r.ok) {
        const body = await r.text()
        throw new Error(body || `${r.status}`)
      }
      setOriginal(text)
      setStatus('saved')
      setTimeout(() => setStatus('idle'), 1400)
    } catch (e) {
      setStatus('error')
      setError(String(e))
    }
  }, [text, jsonErr])

  const reset = useCallback(async () => {
    if (!confirm('Reset the genre tree to the bundled default?')) return
    setStatus('saving')
    try {
      const r = await fetch(
        `${CREATE_ENDPOINT}/api/v1/admin/genre_tree`,
        {
          method: 'PUT',
          headers: headers(),
          body: JSON.stringify({ override: '' }),
        },
      )
      if (!r.ok) throw new Error(`${r.status}`)
      setText(defaultJson)
      setOriginal(defaultJson)
      setStatus('saved')
      setTimeout(() => setStatus('idle'), 1400)
    } catch (e) {
      setStatus('error')
      setError(String(e))
    }
  }, [defaultJson])

  const dirty = text !== original

  return (
    <section className="w-full max-w-[1080px] px-5 md:px-12 py-10 flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <span
          className="font-mono text-[11px] text-[var(--color-accent-dim)]"
          style={{ letterSpacing: 2 }}
        >
          WORLDLINES · ADMIN
        </span>
        <div className="flex items-end justify-between flex-wrap gap-3">
          <h1
            className="text-[var(--color-text-primary)]"
            style={{ fontFamily: 'var(--font-display)', fontSize: 28 }}
          >
            {t('admin.title')}
          </h1>
          <Link
            to="/admin/dashboard"
            className="font-mono text-[11px] text-[var(--color-accent)] hover:opacity-80"
          >
            Dashboard →
          </Link>
        </div>
      </header>

      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] tracking-[0.16em] text-[var(--color-text-tertiary)]">
          {t('admin.token')}
        </span>
        <input
          value={tok}
          onChange={(e) => setTokState(e.target.value)}
          onBlur={() => {
            setTok(tok)
            load()
          }}
          placeholder="HUB_ADMIN_TOKEN (or empty for dev)"
          className="flex-1 bg-transparent border border-[var(--color-border)] rounded-md px-3 py-1.5 font-mono text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent-dim)]"
        />
      </div>

      <div className="rounded-lg border border-[var(--color-border-light)] p-4 flex flex-col gap-3 bg-[var(--color-bg-card)]">
        <div className="flex items-center justify-between">
          <h2
            className="text-[15px] text-[var(--color-text-primary)]"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            {t('admin.genreTree')}
          </h2>
          <div className="flex items-center gap-2">
            {status === 'saved' && (
              <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                saved
              </span>
            )}
            {status === 'saving' && (
              <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                …
              </span>
            )}
            <button
              onClick={reset}
              className="hover-btn px-3 py-1 rounded-md text-[12px] border border-[var(--color-border-light)] text-[var(--color-text-secondary)]"
            >
              {t('admin.reset')}
            </button>
            <button
              onClick={save}
              disabled={!dirty || !!jsonErr || status === 'saving'}
              className="hover-btn px-3 py-1 rounded-md text-[12px] disabled:opacity-40"
              style={{
                background: 'var(--color-accent)',
                color: '#0A0A0A',
              }}
            >
              {t('admin.save')}
            </button>
          </div>
        </div>

        <p className="text-[12px] text-[var(--color-text-tertiary)] leading-[1.6]">
          {t('admin.genreTreeHint')}
        </p>

        {status === 'loading' ? (
          <div className="text-[12px] text-[var(--color-text-muted)] py-6 text-center">
            {t('file.loading')}
          </div>
        ) : (
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
            className="w-full min-h-[480px] p-3 rounded-md font-mono text-[11.5px] outline-none resize-vertical"
            style={{
              background: 'var(--color-bg-card-inner)',
              color: 'var(--color-text-primary)',
              border: '1px solid var(--color-border-light)',
              lineHeight: 1.5,
            }}
          />
        )}
        {jsonErr && (
          <div className="font-mono text-[10.5px] text-[rgb(220,110,110)]">
            {jsonErr}
          </div>
        )}
        {status === 'error' && (
          <div className="font-mono text-[10.5px] text-[rgb(220,110,110)]">
            {error}
          </div>
        )}
      </div>

      <p className="text-[11px] text-[var(--color-text-muted)]">
        {t('admin.next')}
      </p>
    </section>
  )
}
