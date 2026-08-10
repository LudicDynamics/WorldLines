/**
 * ManagePage — publish-management for an already-published world/soul.
 *
 * Reached from the account page "Manage" action (replaces the old jump
 * straight into the create studio). Here the owner edits the catalog
 * name + description, uploads a cover and 立绘 (character portraits),
 * toggles visibility, and — only once cover (+ a soul's portrait) are
 * present — flips the asset public. "Edit content" still hands off to
 * the create studio for the underlying world/soul values.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, ImagePlus, Loader2, Pencil, Trash2 } from 'lucide-react'
import { useAuth } from '../shared/auth'
import { useI18n } from '../shared/i18n'
import {
  getPublished,
  updatePublishedMeta,
  uploadCover,
  uploadPortrait,
  setVisibility,
  unpublish,
  type PublishedRecord,
} from '../shared/identity'

export function ManagePage() {
  const { t } = useI18n()
  const { signedIn } = useAuth()
  const navigate = useNavigate()
  const { kind = '', slug = '' } = useParams()
  const isSoul = kind === 'soul'
  const accent = isSoul ? 'var(--color-soul)' : 'var(--color-world)'

  const [rec, setRec] = useState<PublishedRecord | null>(null)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [coverUrl, setCoverUrl] = useState<string | undefined>(undefined)
  const [portraitUrl, setPortraitUrl] = useState<string | undefined>(undefined)
  const [unlisted, setUnlisted] = useState(true)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    if (!signedIn) {
      navigate('/signup')
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const d = await getPublished(kind, slug)
        if (cancelled) return
        const r = d.record
        setRec(r)
        setName(r.name ?? slug)
        setDesc(r.description ?? '')
        setCoverUrl(r.entry?.cover_url)
        setPortraitUrl(r.entry?.portraits?.self)
        setUnlisted(r.entry?.unlisted !== false)
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [kind, slug, signedIn, navigate])

  // Hard publish gate: a cover is always required; a soul also needs its
  // own 立绘. (Per-NPC world portraits are a follow-up — worlds gate on
  // cover only for now.)
  const canGoPublic = useMemo(() => {
    if (!coverUrl) return false
    if (isSoul && !portraitUrl) return false
    return true
  }, [coverUrl, portraitUrl, isSoul])

  async function saveMeta() {
    if (busy) return
    setBusy('meta')
    setErr(null)
    setNote(null)
    try {
      await updatePublishedMeta(kind, slug, { name: name.trim(), description: desc })
      setNote(t('manage.saved'))
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  async function onCover(file: File) {
    setBusy('cover')
    setErr(null)
    try {
      const r = await uploadCover(kind as 'world' | 'soul', slug, file)
      setCoverUrl(r.cover_url)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  async function onPortrait(file: File) {
    setBusy('portrait')
    setErr(null)
    try {
      const r = await uploadPortrait(kind as 'world' | 'soul', slug, file, 'self')
      setPortraitUrl(r.portrait_url)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  async function toggleVisibility() {
    if (busy) return
    const next = !unlisted
    if (!next && !canGoPublic) return // gate: can't go public without art
    setBusy('vis')
    setErr(null)
    try {
      await setVisibility(kind, slug, next)
      setUnlisted(next)
      setNote(next ? t('manage.nowHidden') : t('manage.nowPublic'))
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  async function editContent() {
    // Hand off to the create studio with the published values pre-seeded
    // (same channel resumed drafts use).
    setBusy('edit')
    try {
      const d = await getPublished(kind, slug)
      const values = (d.record.values ?? {}) as Record<string, string>
      const draft = { kind, values, step: 0 }
      const route = isSoul ? '/create/soul' : '/create/world?g='
      navigate(route, { state: { resume: { draft_id: '', draft } } })
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setBusy(null)
    }
  }

  async function doUnpublish() {
    if (busy) return
    if (!window.confirm(t('manage.unpublishConfirm'))) return
    setBusy('unpub')
    try {
      await unpublish(kind, slug)
      navigate('/account')
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
      setBusy(null)
    }
  }

  if (loading)
    return (
      <main className="mx-auto max-w-2xl px-6 py-16 flex items-center gap-2 text-[var(--color-text-secondary)]">
        <Loader2 className="w-4 h-4 animate-spin" /> {t('manage.loading')}
      </main>
    )

  if (!rec)
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <button
          onClick={() => navigate('/account')}
          className="hover-link inline-flex items-center gap-1 text-[12px] text-[var(--color-text-tertiary)] mb-4"
        >
          <ChevronLeft className="w-4 h-4" /> {t('manage.back')}
        </button>
        <p className="text-[13px] text-[#f87171]">
          {err ?? t('manage.notFound')}
        </p>
      </main>
    )

  const field =
    'w-full bg-transparent border border-[var(--color-border)] rounded-md px-3 py-2 text-[14px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent-dim)]'

  return (
    <main className="mx-auto max-w-2xl px-6 py-12 flex flex-col gap-6">
      <button
        onClick={() => navigate('/account')}
        className="hover-link inline-flex items-center gap-1 text-[12px] text-[var(--color-text-tertiary)] self-start"
      >
        <ChevronLeft className="w-4 h-4" /> {t('manage.back')}
      </button>

      <div className="flex items-center gap-2">
        <span
          className="font-mono text-[10px] tracking-[0.18em] px-2 py-0.5 rounded"
          style={{ color: accent, border: `1px solid ${accent}55` }}
        >
          {isSoul ? 'SOUL' : 'WORLD'}
        </span>
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
          {t('manage.title')}
        </h1>
      </div>

      {/* Name + description */}
      <div className="flex flex-col gap-3 rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--color-text-tertiary)]">
            {t('manage.name')}
          </span>
          <input value={name} onChange={(e) => setName(e.target.value)} className={field} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--color-text-tertiary)]">
            {t('manage.description')}
          </span>
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            rows={4}
            placeholder={t('manage.descPlaceholder')}
            className={field + ' resize-y leading-relaxed'}
          />
        </label>
        <button
          onClick={saveMeta}
          disabled={busy === 'meta' || !name.trim()}
          className="hover-btn self-start inline-flex items-center gap-2 px-4 py-2 rounded-md text-[13px] font-medium disabled:opacity-40"
          style={{ background: accent, color: '#0A0A0A' }}
        >
          {busy === 'meta' ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          {t('manage.save')}
        </button>
      </div>

      {/* Images: cover + 立绘 */}
      <div className="grid grid-cols-2 gap-3">
        <ImageSlot
          label={t('manage.cover')}
          url={coverUrl}
          busy={busy === 'cover'}
          onPick={onCover}
          accent={accent}
          pickLabel={t('manage.upload')}
        />
        <ImageSlot
          label={isSoul ? t('manage.portraitSoul') : t('manage.portraitWorld')}
          url={portraitUrl}
          busy={busy === 'portrait'}
          onPick={onPortrait}
          accent={accent}
          pickLabel={t('manage.upload')}
        />
      </div>

      {/* Visibility + publish gate */}
      <div className="flex flex-col gap-2 rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4">
        <div className="flex items-center justify-between">
          <span className="text-[13px] text-[var(--color-text-primary)]">
            {unlisted ? t('manage.hidden') : t('manage.public')}
          </span>
          <button
            onClick={toggleVisibility}
            disabled={busy === 'vis' || (unlisted && !canGoPublic)}
            className="hover-btn inline-flex items-center gap-2 px-4 py-2 rounded-md text-[13px] font-medium disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: unlisted ? accent : 'transparent',
              color: unlisted ? '#0A0A0A' : 'var(--color-text-secondary)',
              border: unlisted ? 'none' : '1px solid var(--color-border-light)',
            }}
          >
            {busy === 'vis' ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {unlisted ? t('manage.goPublic') : t('manage.makeHidden')}
          </button>
        </div>
        {unlisted && !canGoPublic && (
          <p className="text-[11px] text-[var(--color-text-tertiary)]">
            {isSoul ? t('manage.gateSoul') : t('manage.gateWorld')}
          </p>
        )}
      </div>

      {(err || note) && (
        <p
          className="text-[12px]"
          style={{ color: err ? '#f87171' : accent }}
        >
          {err ?? note}
        </p>
      )}

      {/* Content edit + unpublish */}
      <div className="flex items-center gap-2 pt-2 border-t border-[var(--color-border)]">
        <button
          onClick={editContent}
          disabled={busy === 'edit'}
          className="hover-link inline-flex items-center gap-1.5 text-[12px] text-[var(--color-text-secondary)] px-3 py-2 rounded-md border border-[var(--color-border-light)] disabled:opacity-40"
        >
          <Pencil className="w-3.5 h-3.5" /> {t('manage.editContent')}
        </button>
        <button
          onClick={doUnpublish}
          disabled={busy === 'unpub'}
          className="hover-link inline-flex items-center gap-1.5 text-[12px] text-[var(--color-text-tertiary)] px-3 py-2 rounded-md disabled:opacity-40 ml-auto"
        >
          <Trash2 className="w-3.5 h-3.5" /> {t('manage.unpublish')}
        </button>
      </div>
    </main>
  )
}

function ImageSlot({
  label,
  url,
  busy,
  onPick,
  accent,
  pickLabel,
}: {
  label: string
  url?: string
  busy: boolean
  onPick: (f: File) => void
  accent: string
  pickLabel: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--color-text-tertiary)]">
        {label}
      </span>
      <label
        className="relative aspect-[3/4] rounded-lg border border-dashed overflow-hidden cursor-pointer flex items-center justify-center"
        style={{ borderColor: 'var(--color-border-light)' }}
      >
        {url ? (
          // eslint-disable-next-line jsx-a11y/img-redundant-alt
          <img src={url} alt={label} className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
            <ImagePlus className="w-5 h-5" style={{ color: accent }} />
            {pickLabel}
          </span>
        )}
        {busy && (
          <span className="absolute inset-0 flex items-center justify-center bg-black/50">
            <Loader2 className="w-5 h-5 animate-spin" style={{ color: accent }} />
          </span>
        )}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) onPick(f)
            e.currentTarget.value = ''
          }}
        />
      </label>
    </div>
  )
}

export default ManagePage
