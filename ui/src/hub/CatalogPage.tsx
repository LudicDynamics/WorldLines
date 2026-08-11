import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchRegistry, groupBySlug, type Kind, type Story } from '../shared/registry'
import { EntryCard } from './EntryCard'
import { useI18n } from '../shared/i18n'

const COPY: Record<
  Kind,
  { label: string; title: string; subtitle: string; empty: string }
> = {
  worlds: {
    label: 'cat.worldsLabel',
    title: 'cat.worldsTitle',
    subtitle: 'cat.worldsSub',
    empty: 'cat.worldsEmpty',
  },
  souls: {
    label: 'cat.soulsLabel',
    title: 'cat.soulsTitle',
    subtitle: 'cat.soulsSub',
    empty: 'cat.soulsEmpty',
  },
}

const TABS: { kind: Kind; labelKey: string }[] = [
  { kind: 'worlds', labelKey: 'nav.worlds' },
  { kind: 'souls', labelKey: 'nav.souls' },
]

export function CatalogPage({ kind }: { kind: Kind }) {
  const { t } = useI18n()
  // The load result carries the kind it belongs to, so switching kinds reads
  // as "loading" by derivation instead of a synchronous reset inside the
  // effect (react-hooks/set-state-in-effect) — one render pass fewer, same
  // visible sequence.
  const [loaded, setLoaded] = useState<{
    kind: Kind
    stories: Story[]
    error: string | null
  } | null>(null)
  const current = loaded && loaded.kind === kind ? loaded : null
  const stories = current ? current.stories : null
  const error = current ? current.error : null
  const copy = COPY[kind]

  useEffect(() => {
    let cancelled = false
    fetchRegistry(kind)
      .then((reg) => {
        if (cancelled) return
        const list = (reg[kind] ?? []) as NonNullable<typeof reg.worlds>
        setLoaded({ kind, stories: groupBySlug(list), error: null })
      })
      .catch((err) => {
        if (cancelled) return
        setLoaded({ kind, stories: [], error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [kind])

  return (
    <section className="relative w-full px-5 md:px-12 py-16 md:py-20 flex flex-col items-center">
      <div className="flex flex-col items-center text-center max-w-[820px]">
        <span
          className="font-mono text-[11px] text-[var(--color-accent-dim)]"
          style={{ letterSpacing: 2, fontFamily: 'var(--font-mono)' }}
        >
          {t(copy.label)}
        </span>
        <h1
          className="text-[var(--color-text-primary)] mt-2"
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(28px, 4.5vw, 44px)',
            lineHeight: 1.15,
          }}
        >
          {t(copy.title)}
        </h1>
        <p
          className="text-[var(--color-text-tertiary)] mt-3 max-w-[640px]"
          style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.55 }}
        >
          {t(copy.subtitle)}
        </p>

        {/* Inline how-to */}
        <div className="mt-6 w-full max-w-[640px] rounded border border-[var(--color-border)] bg-[var(--color-bg-card-inner)] px-4 py-3 text-left">
          <span
            className="font-mono text-[10px] text-[var(--color-text-muted)] tracking-[0.18em]"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {t('cat.oneliner')}
          </span>
          <pre
            className="mt-1 font-mono text-[12px] text-[var(--color-text-secondary)] whitespace-pre-wrap"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {kind === 'worlds'
              ? 'worldlines world download <slug>'
              : 'worldlines world download <slug> --kind souls'}
          </pre>
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-10 flex items-center gap-1 border border-[var(--color-border-light)] rounded p-1 bg-[var(--color-bg-card-inner)]">
        {TABS.map((tab) => (
          <Link
            key={tab.kind}
            to={`/${tab.kind}`}
            className="px-4 py-1.5 rounded text-[12px] font-medium transition-colors"
            style={{
              fontFamily: 'var(--font-sans)',
              background:
                kind === tab.kind ? 'var(--color-bg)' : 'transparent',
              color:
                kind === tab.kind
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-tertiary)',
              border:
                kind === tab.kind
                  ? `1px solid var(--color-${tab.kind === 'worlds' ? 'world' : 'soul'}-faint)`
                  : '1px solid transparent',
              textDecoration: 'none',
            }}
          >
            {t(tab.labelKey)}
          </Link>
        ))}
      </div>

      {/* Grid */}
      <div className="mt-8 w-full max-w-[1100px]">
        {stories === null && (
          <div className="text-center py-20 text-[var(--color-text-tertiary)] font-mono text-[12px]">
            {t('cat.loading')}
          </div>
        )}
        {error && (
          <div className="text-center py-20 text-[var(--color-text-tertiary)] font-mono text-[12px]">
            {error}
          </div>
        )}
        {stories && stories.length === 0 && !error && (
          <div className="text-center py-20 text-[var(--color-text-tertiary)] font-mono text-[12px]">
            {t(copy.empty)}
          </div>
        )}
        {stories && stories.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5">
            {stories.map((s) => (
              <EntryCard key={s.slug} kind={kind} story={s} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
