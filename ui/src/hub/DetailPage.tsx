import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ChevronLeft, Download, ExternalLink, Play, Boxes,
  Upload, Pencil, Trash2, Loader2,
} from 'lucide-react'
import {
  coverFor,
  fetchRegistry,
  groupBySlug,
  type Kind,
  type Story,
} from '../shared/registry'
import { formatBytes, formatDate, relativeDate } from '../shared/format'
import { HashCopy } from '../shared/HashCopy'
import { isPlayable } from '../shared/playable'
import { useI18n } from '../shared/i18n'
import { useAuth } from '../shared/auth'
import { me, uploadCover, unpublish, getPublished } from '../shared/identity'

const KIND_COLOR: Record<Kind, string> = {
  worlds: 'var(--color-world)',
  souls: 'var(--color-soul)',
}

const KIND_TAG: Record<Kind, string> = {
  worlds: 'WORLD',
  souls: 'SOUL',
}

// Protocol-defined bundle anatomy (same for every entry of a kind) —
// see rp-shared-protocol/docs/{WORLD,SOUL}-PROTOCOL.md.
// [path, i18n description key]
const SOUL_AGENTS: [string, string][] = [
  ['orchestrator', 'agent.orchestrator'],
  ['mind', 'agent.mind'],
  ['action', 'agent.action'],
  ['memory', 'agent.memory'],
  ['dialogue', 'agent.dialogue'],
  ['narrative', 'agent.narrative'],
]

const SOUL_DIRS: [string, string][] = [
  ['persona/', 'sdir.persona'],
  ['character/', 'sdir.character'],
  ['background/', 'sdir.background'],
  ['*-memo/', 'sdir.memo'],
  ['agents/', 'sdir.agents'],
]

const WORLD_DIRS: [string, string][] = [
  ['world/world_map.json', 'wdir.map'],
  ['world/<kind>/<id>.json', 'wdir.entities'],
  ['agents/', 'wdir.agents'],
  ['rules/', 'wdir.rules'],
  ['.neonrp/', 'wdir.neonrp'],
]

export function DetailPage({ kind }: { kind: Kind }) {
  const { slug } = useParams<{ slug: string }>()
  const { t } = useI18n()
  const { signedIn } = useAuth()
  const navigate = useNavigate()
  // Loaded data and the cover override both carry the entry they belong to,
  // so navigating to another slug reads as "loading" / "no override" by
  // derivation rather than a synchronous reset inside the effect
  // (react-hooks/set-state-in-effect).
  const entryKey = `${kind}/${slug ?? ''}`
  const [loaded, setLoaded] = useState<{ key: string; story: Story | null } | null>(null)
  const story: Story | null | undefined =
    loaded && loaded.key === entryKey ? loaded.story : undefined
  const [ownedKey, setOwnedKey] = useState<string | null>(null)
  const [coverEdit, setCoverEdit] = useState<{ key: string; url: string } | null>(null)
  const coverOverride = coverEdit && coverEdit.key === entryKey ? coverEdit.url : null
  const [ownerBusy, setOwnerBusy] = useState(false)
  const [ownerErr, setOwnerErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const accent = KIND_COLOR[kind]
  const kindWord = kind === 'worlds' ? t('nav.worlds') : t('nav.souls')
  const singularKind = kind === 'souls' ? 'soul' : 'world'

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    const key = `${kind}/${slug}`
    fetchRegistry(kind)
      .then((reg) => {
        if (cancelled) return
        const list = (reg[kind] ?? []) as NonNullable<typeof reg.worlds>
        const stories = groupBySlug(list)
        const match = stories.find((s) => s.slug === slug)
        setLoaded({ key, story: match ?? null })
      })
      .catch(() => setLoaded({ key, story: null }))
    return () => {
      cancelled = true
    }
  }, [kind, slug])

  // Owner detection: the signed-in caller owns this slug iff it's in
  // their /me published list. Drives the owner edit toolbar below.
  const owned = !!slug && signedIn && ownedKey === `${singularKind}/${slug}`
  useEffect(() => {
    if (!slug || !signedIn) return
    let cancelled = false
    me()
      .then((m) => {
        if (cancelled) return
        const isOwner = (m.published ?? []).some(
          (p) => p.id === slug && p.kind === singularKind,
        )
        setOwnedKey(isOwner ? `${singularKind}/${slug}` : null)
      })
      .catch(() => {
        if (!cancelled) setOwnedKey(null)
      })
    return () => {
      cancelled = true
    }
  }, [slug, signedIn, singularKind])

  async function onPickCover(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f || !slug || ownerBusy) return
    setOwnerBusy(true)
    setOwnerErr(null)
    try {
      const res = await uploadCover(singularKind, slug, f)
      setCoverEdit({ key: `${kind}/${slug}`, url: res.cover_url })
    } catch (err) {
      setOwnerErr(err instanceof Error ? err.message : String(err))
    } finally {
      setOwnerBusy(false)
    }
  }

  async function onEdit() {
    if (!slug || ownerBusy) return
    setOwnerBusy(true)
    setOwnerErr(null)
    try {
      // Fork the published values into a fresh create-studio draft —
      // same channel AccountPage's Edit uses.
      const detail = await getPublished(singularKind, slug)
      const values = (detail.record.values ?? {}) as Record<string, string>
      const draft = { kind: singularKind, values, step: 0 }
      const route = singularKind === 'soul' ? '/create/soul' : '/create/world?g='
      navigate(route, { state: { resume: { draft_id: '', draft } } })
    } catch (err) {
      setOwnerErr(err instanceof Error ? err.message : String(err))
      setOwnerBusy(false)
    }
  }

  async function onUnpublish() {
    if (!slug || ownerBusy) return
    if (
      !confirm(
        t('owner.unpublishConfirm').replace(
          '{name}',
          story?.display_name || slug,
        ),
      )
    )
      return
    setOwnerBusy(true)
    setOwnerErr(null)
    try {
      await unpublish(singularKind, slug)
      navigate('/account')
    } catch (err) {
      setOwnerErr(err instanceof Error ? err.message : String(err))
      setOwnerBusy(false)
    }
  }

  if (story === undefined) {
    return (
      <section className="w-full max-w-[920px] px-5 md:px-12 py-16 text-center text-[var(--color-text-tertiary)] font-mono text-[12px]">
        {t('detail.loading')}
      </section>
    )
  }

  if (story === null) {
    // Not published to S3 — but it may still be hosted-playable
    // (the gateway can run scenes that aren't in the registry).
    const canPlay = slug ? isPlayable(kind, slug) : false
    return (
      <section className="w-full max-w-[920px] px-5 md:px-12 py-16 flex flex-col items-center gap-4">
        <span className="font-mono text-[12px] text-[var(--color-text-tertiary)]">
          {canPlay
            ? t('detail.notHostedYet')
            : t('detail.notFound').replace('{kind}', kindWord)}
        </span>
        {canPlay && slug && (
          <Link
            to={`/play/${kind}/${slug}`}
            className="hover-btn inline-flex items-center gap-2 px-6 py-3 rounded text-[15px] font-medium"
            style={{
              fontFamily: 'var(--font-sans)',
              background: accent,
              color: '#0A0A0A',
              textDecoration: 'none',
            }}
          >
            <Play className="w-4 h-4 fill-current" />
            {t('detail.playInBrowser')}
          </Link>
        )}
        <Link
          to={`/${kind}`}
          className="hover-link text-[13px] text-[var(--color-text-secondary)]"
        >
          ← {t('detail.back').replace('{kind}', kindWord)}
        </Link>
      </section>
    )
  }

  const latest = story.versions[0]
  const cover = coverOverride ?? coverFor(kind, story.slug, latest)
  const dlSlug = `worldlines world download ${story.slug}${
    kind === 'souls' ? ' --kind souls' : ''
  }`
  const dlVersion = `worldlines world download ${story.slug}@${story.latest_version}${
    kind === 'souls' ? ' --kind souls' : ''
  }`

  return (
    <section className="w-full max-w-[920px] px-5 md:px-12 py-12 md:py-16 flex flex-col gap-8">
      <Link
        to={`/${kind}`}
        className="hover-link inline-flex items-center gap-1 text-[12px] text-[var(--color-text-tertiary)] self-start"
      >
        <ChevronLeft className="w-4 h-4" />
        {t('land.all')} {kindWord}
      </Link>

      {owned && (
        <div
          className="rounded border bg-[var(--color-bg-card)] p-3 flex flex-wrap items-center gap-2"
          style={{ borderColor: 'var(--color-border-light)' }}
        >
          <span
            className="font-mono text-[10px] tracking-[0.18em] mr-1"
            style={{ color: accent, fontFamily: 'var(--font-mono)' }}
          >
            {t('owner.bar')}
          </span>
          <a
            href={latest.url}
            target="_blank"
            rel="noreferrer"
            className="hover-btn inline-flex items-center gap-1.5 text-[12px] border rounded px-2.5 py-1.5"
            style={{
              borderColor: 'var(--color-border-light)',
              color: 'var(--color-text-secondary)',
              textDecoration: 'none',
            }}
          >
            <Download className="w-3.5 h-3.5" /> {t('owner.download')}
          </a>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={ownerBusy}
            className="hover-btn inline-flex items-center gap-1.5 text-[12px] border rounded px-2.5 py-1.5 disabled:opacity-50"
            style={{
              borderColor: 'var(--color-border-light)',
              color: 'var(--color-text-secondary)',
            }}
          >
            {ownerBusy ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5" />
            )}{' '}
            {t('owner.replaceCover')}
          </button>
          <button
            onClick={onEdit}
            disabled={ownerBusy}
            className="hover-btn inline-flex items-center gap-1.5 text-[12px] border rounded px-2.5 py-1.5 disabled:opacity-50"
            style={{
              borderColor: 'var(--color-border-light)',
              color: 'var(--color-text-secondary)',
            }}
          >
            <Pencil className="w-3.5 h-3.5" /> {t('owner.edit')}
          </button>
          <button
            onClick={onUnpublish}
            disabled={ownerBusy}
            className="hover-btn inline-flex items-center gap-1.5 text-[12px] border rounded px-2.5 py-1.5 disabled:opacity-50"
            style={{
              borderColor: 'var(--color-border-light)',
              color: 'var(--color-text-tertiary)',
            }}
          >
            <Trash2 className="w-3.5 h-3.5" /> {t('owner.unpublish')}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={onPickCover}
          />
          {ownerErr && (
            <span
              className="w-full text-[11px]"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {ownerErr}
            </span>
          )}
        </div>
      )}

      {cover && (
        <div
          className="relative w-full overflow-hidden rounded border border-[var(--color-border-light)]"
          style={{ aspectRatio: '21 / 9' }}
        >
          <img
            src={cover}
            alt={story.display_name}
            className="w-full h-full object-cover"
          />
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background:
                'linear-gradient(to bottom, transparent 40%, rgba(10,10,10,0.85) 100%)',
            }}
          />
        </div>
      )}

      <div className="flex flex-col gap-3">
        <span
          className="font-mono text-[10px] tracking-[0.18em]"
          style={{ color: accent, fontFamily: 'var(--font-mono)' }}
        >
          {KIND_TAG[kind]} · {story.slug}
        </span>
        <h1
          className="text-[var(--color-text-primary)]"
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(32px, 5vw, 48px)',
            lineHeight: 1.1,
          }}
        >
          {story.display_name}
        </h1>
        <p className="font-mono text-[12px] text-[var(--color-text-tertiary)]">
          {t('detail.latestLine')} v{story.latest_version} ·{' '}
          {formatBytes(latest.size_bytes)} · {relativeDate(latest.uploaded_at)}
        </p>
      </div>

      {/* Primary CTA — only hosted scenes get the in-browser Play button.
          Everything else points at the download box below instead of
          dead-ending on a gateway "scene not found". */}
      {isPlayable(kind, story.slug) ? (
        <div className="flex flex-col gap-1.5 self-start">
          <Link
            to={`/play/${kind}/${story.slug}`}
            className="hover-btn inline-flex items-center justify-center gap-2 px-6 py-3 rounded text-[15px] font-medium"
            style={{
              fontFamily: 'var(--font-sans)',
              background: accent,
              color: '#0A0A0A',
              textDecoration: 'none',
            }}
          >
            <Play className="w-4 h-4 fill-current" />
            {kind === 'souls' ? t('detail.playSoul') : t('detail.playWorld')}
          </Link>
          <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
            {t('detail.hostedNote')}
          </span>
        </div>
      ) : (
        <a
          href="#download"
          className="hover-btn inline-flex items-center gap-2 px-6 py-3 rounded text-[14px] font-medium self-start border"
          style={{
            fontFamily: 'var(--font-sans)',
            borderColor: 'var(--color-border-light)',
            color: 'var(--color-text-secondary)',
            textDecoration: 'none',
          }}
        >
          <Download className="w-4 h-4" />
          {t('detail.downloadLocal')}
          <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
            {t('detail.notHostedParen')}
          </span>
        </a>
      )}

      {/* What's inside */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Boxes className="w-4 h-4" style={{ color: accent }} />
          <span
            className="font-mono text-[11px] tracking-[0.18em]"
            style={{
              color: 'var(--color-text-secondary)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {t('detail.whatsInside')}
          </span>
        </div>

        {kind === 'souls' && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SOUL_AGENTS.map(([name, desc]) => (
                <div
                  key={name}
                  className="rounded border border-[var(--color-border)] bg-[var(--color-bg-card-inner)] p-3 flex flex-col gap-1"
                >
                  <span
                    className="font-mono text-[12px]"
                    style={{ color: accent, fontFamily: 'var(--font-mono)' }}
                  >
                    soul-{name}
                  </span>
                  <span
                    className="text-[12px] text-[var(--color-text-tertiary)]"
                    style={{ fontFamily: 'var(--font-sans)', lineHeight: 1.45 }}
                  >
                    {t(desc)}
                  </span>
                </div>
              ))}
            </div>
            <BundleTree dirs={SOUL_DIRS} />
          </div>
        )}

        {kind === 'worlds' && <BundleTree dirs={WORLD_DIRS} />}
      </div>

      {/* Download box */}
      <div
        id="download"
        className="scroll-mt-8 rounded border bg-[var(--color-bg-card)] p-5 md:p-6 flex flex-col gap-4"
        style={{ borderColor: 'var(--color-border-light)' }}
      >
        <div className="flex items-center gap-2">
          <Download className="w-4 h-4" style={{ color: accent }} />
          <span
            className="font-mono text-[11px] tracking-[0.18em]"
            style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}
          >
            {t('detail.download')}
          </span>
        </div>
        <div className="flex flex-col gap-2">
          <CommandRow label={t('detail.dlLatest')} value={dlSlug} />
          <CommandRow label={t('detail.dlVersion')} value={dlVersion} />
          <div className="flex items-center gap-2 mt-1">
            <span
              className="font-mono text-[11px] text-[var(--color-text-tertiary)] min-w-[90px]"
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              {t('detail.byHash')}
            </span>
            <HashCopy value={story.latest_hash} />
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span
              className="font-mono text-[11px] text-[var(--color-text-tertiary)] min-w-[90px]"
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              {t('detail.directZip')}
            </span>
            <a
              href={latest.url}
              target="_blank"
              rel="noreferrer"
              className="hover-btn inline-flex items-center gap-1.5 font-mono text-[12px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-[var(--color-border-light)] hover:border-[var(--color-accent-dim)] rounded px-2 py-1"
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              <ExternalLink className="w-3 h-3" />
              S3
            </a>
          </div>
        </div>
      </div>

      {/* Versions */}
      <div className="flex flex-col gap-3">
        <span
          className="font-mono text-[11px] text-[var(--color-text-tertiary)] tracking-[0.18em]"
          style={{ fontFamily: 'var(--font-mono)' }}
        >
          {t('detail.versions')}
        </span>
        <div className="flex flex-col">
          {story.versions.map((v, i) => (
            <div
              key={v.hash}
              className="flex flex-col md:flex-row md:items-center gap-2 md:gap-6 py-3 border-t border-[var(--color-border)]"
            >
              <div className="flex items-baseline gap-3 min-w-[140px]">
                <span
                  className="text-[14px] text-[var(--color-text-primary)]"
                  style={{ fontFamily: 'var(--font-display)' }}
                >
                  v{v.version}
                </span>
                {i === 0 && (
                  <span
                    className="font-mono text-[9px] px-1.5 py-0.5 rounded-sm tracking-[0.18em]"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: accent,
                      borderColor: accent,
                      border: `1px solid ${accent}40`,
                    }}
                  >
                    {t('detail.latestBadge')}
                  </span>
                )}
              </div>
              <span
                className="font-mono text-[11px] text-[var(--color-text-tertiary)] flex-1"
                style={{ fontFamily: 'var(--font-mono)' }}
              >
                {v.changelog || (
                  <em className="text-[var(--color-text-muted)]">
                    {t('detail.noChangelog')}
                  </em>
                )}
              </span>
              <div className="flex items-center gap-3">
                <HashCopy value={v.hash} />
                <span
                  className="font-mono text-[11px] text-[var(--color-text-muted)]"
                  style={{ fontFamily: 'var(--font-mono)' }}
                >
                  {formatBytes(v.size_bytes)} · {formatDate(v.uploaded_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function BundleTree({ dirs }: { dirs: [string, string][] }) {
  const { t } = useI18n()
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-card-inner)] p-4 flex flex-col gap-2">
      {dirs.map(([path, desc]) => (
        <div
          key={path}
          className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4"
        >
          <span
            className="font-mono text-[12px] text-[var(--color-text-secondary)] min-w-[200px]"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {path}
          </span>
          <span
            className="text-[12px] text-[var(--color-text-tertiary)]"
            style={{ fontFamily: 'var(--font-sans)' }}
          >
            {t(desc)}
          </span>
        </div>
      ))}
    </div>
  )
}

function CommandRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="font-mono text-[11px] text-[var(--color-text-tertiary)] min-w-[90px]"
        style={{ fontFamily: 'var(--font-mono)' }}
      >
        {label}
      </span>
      <HashCopy value={value} className="flex-1 justify-start" />
    </div>
  )
}
