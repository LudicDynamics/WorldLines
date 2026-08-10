import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Globe, Sparkles, PlusCircle } from 'lucide-react'
import { Play } from 'lucide-react'
import {
  fetchRegistry,
  groupBySlug,
  coverFor,
  type Kind,
  type Story,
} from '../shared/registry'
import { PLAYABLE } from '../shared/playable'
import { useI18n } from '../shared/i18n'

// The 4 primary entry points — what a signed-in user can DO from the
// hub root, beyond the small header links. Two consume (browse hubs),
// two create. Same accent palette as the rest of the surface; the
// "+" overlay icon distinguishes create from browse without needing
// another color.
type Door = {
  to: string
  labelKey: string
  blurbKey: string
  accent: string
  icon: typeof Globe
  create?: boolean
}

const DOORS: Door[] = [
  {
    to: '/worlds',
    labelKey: 'land.doorWorlds',
    blurbKey: 'land.doorWorldsBlurb',
    accent: 'var(--color-world)',
    icon: Globe,
  },
  {
    to: '/souls',
    labelKey: 'land.doorSouls',
    blurbKey: 'land.doorSoulsBlurb',
    accent: 'var(--color-soul)',
    icon: Sparkles,
  },
  {
    to: '/create/world',
    labelKey: 'land.doorCreateWorld',
    blurbKey: 'land.doorCreateWorldBlurb',
    accent: 'var(--color-world)',
    icon: Globe,
    create: true,
  },
  {
    to: '/create/soul',
    labelKey: 'land.doorCreateSoul',
    blurbKey: 'land.doorCreateSoulBlurb',
    accent: 'var(--color-soul)',
    icon: Sparkles,
    create: true,
  },
]

function FeaturedRow({ kind }: { kind: Kind }) {
  const { t } = useI18n()
  const [stories, setStories] = useState<Story[] | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchRegistry(kind)
      .then((reg) => {
        if (cancelled) return
        const list = (reg[kind] ?? []) as NonNullable<typeof reg.worlds>
        setStories(groupBySlug(list).slice(0, 3))
      })
      .catch(() => setStories([]))
    return () => {
      cancelled = true
    }
  }, [kind])

  if (!stories || stories.length === 0) return null

  return (
    <div className="flex flex-col gap-3 w-full">
      <div className="flex items-center justify-between">
        <span
          className="font-mono text-[10px] tracking-[0.18em]"
          style={{
            color:
              kind === 'worlds' ? 'var(--color-world)' : 'var(--color-soul)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {t('land.featured')}{' '}
          {kind === 'worlds' ? t('nav.worlds') : t('nav.souls')}
        </span>
        <Link
          to={`/${kind}`}
          className="hover-link inline-flex items-center gap-1 text-[12px] text-[var(--color-text-tertiary)]"
        >
          {t('land.all')}{' '}
          {kind === 'worlds' ? t('nav.worlds') : t('nav.souls')}{' '}
          <ArrowRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {stories.map((s) => {
          const cover = coverFor(kind, s.slug, s.versions[0])
          return (
            <Link
              key={s.slug}
              to={`/${kind}/${s.slug}`}
              className="hover-card relative rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] overflow-hidden block"
              style={{ textDecoration: 'none', aspectRatio: '4 / 3' }}
            >
              {cover && (
                <img
                  src={cover}
                  alt={s.display_name}
                  loading="lazy"
                  className="absolute inset-0 w-full h-full object-cover"
                />
              )}
              <div
                className="absolute inset-0"
                style={{
                  background:
                    'linear-gradient(to bottom, transparent 35%, rgba(10,10,10,0.9) 100%)',
                }}
              />
              <div className="absolute bottom-0 left-0 right-0 p-3">
                <span
                  className="text-[14px] text-[var(--color-text-primary)]"
                  style={{ fontFamily: 'var(--font-display)' }}
                >
                  {s.display_name}
                </span>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

function PlayNowRow() {
  const { t } = useI18n()
  // Prefer the registry's S3 cover_url over the static COVER_MAP so the
  // playable cards show the author's uploaded cover, not the bundled
  // placeholder. Keyed `${kind}/${slug}` → latest version's cover_url.
  const [coverUrls, setCoverUrls] = useState<Record<string, string>>({})
  useEffect(() => {
    let cancelled = false
    Promise.all([fetchRegistry('worlds'), fetchRegistry('souls')])
      .then(([w, s]) => {
        if (cancelled) return
        const map: Record<string, string> = {}
        for (const kind of ['worlds', 'souls'] as const) {
          const reg = kind === 'worlds' ? w : s
          for (const story of groupBySlug(reg[kind] ?? [])) {
            const cu = story.versions[0]?.cover_url
            if (cu) map[`${kind}/${story.slug}`] = cu
          }
        }
        setCoverUrls(map)
      })
      .catch(() => {
        /* registry unreachable — keep static fallback */
      })
    return () => {
      cancelled = true
    }
  }, [])
  if (PLAYABLE.length === 0) return null
  return (
    <div className="flex flex-col gap-3 w-full">
      <div className="flex items-center justify-between">
        <span
          className="font-mono text-[10px] tracking-[0.18em]"
          style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}
        >
          {t('land.playNow')}
        </span>
        <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
          {t('land.playNote')}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {PLAYABLE.map((p) => {
          const cover =
            coverUrls[`${p.kind}/${p.slug}`] ?? coverFor(p.kind, p.slug, null)
          const accent =
            p.kind === 'souls' ? 'var(--color-soul)' : 'var(--color-world)'
          return (
            <Link
              key={`${p.kind}/${p.slug}`}
              to={`/play/${p.kind}/${p.slug}`}
              className="hover-card relative rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] overflow-hidden block"
              style={{ textDecoration: 'none', minHeight: 168 }}
            >
              {cover && (
                <img
                  src={cover}
                  alt={p.name}
                  loading="lazy"
                  className="absolute inset-0 w-full h-full object-cover"
                  style={{ filter: 'brightness(0.5)' }}
                />
              )}
              <div
                className="absolute inset-0"
                style={{
                  background:
                    'linear-gradient(to right, rgba(10,10,10,0.92) 30%, rgba(10,10,10,0.45) 100%)',
                }}
              />
              <div className="relative z-10 p-5 flex flex-col gap-2 h-full">
                <span
                  className="font-mono text-[10px] tracking-[0.18em]"
                  style={{ color: accent }}
                >
                  {p.kind === 'souls' ? 'SOUL' : 'WORLD'}
                </span>
                <span
                  className="text-[var(--color-text-primary)]"
                  style={{ fontFamily: 'var(--font-display)', fontSize: 22 }}
                >
                  {p.name}
                </span>
                <span
                  className="text-[12px] text-[var(--color-text-tertiary)] flex-1"
                  style={{ fontFamily: 'var(--font-sans)', lineHeight: 1.5 }}
                >
                  {p.blurb}
                </span>
                <span
                  className="inline-flex items-center gap-1.5 text-[13px] font-medium"
                  style={{ color: accent }}
                >
                  <Play className="w-3.5 h-3.5 fill-current" /> {t('land.playCta')}
                </span>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

export function LandingPage() {
  const { t } = useI18n()
  const STEPS: [string, string][] = [
    [t('land.step1h'), t('land.step1b')],
    [t('land.step2h'), t('land.step2b')],
    [t('land.step3h'), t('land.step3b')],
  ]
  return (
    <section className="w-full max-w-[1100px] px-5 md:px-12 py-16 md:py-24 flex flex-col items-center gap-16">
      {/* Hero */}
      <div className="flex flex-col items-center text-center max-w-[720px] gap-5">
        <span
          className="font-mono text-[11px] text-[var(--color-accent-dim)]"
          style={{ letterSpacing: 2, fontFamily: 'var(--font-mono)' }}
        >
          {t('land.tag')}
        </span>
        <h1
          className="text-[var(--color-text-primary)]"
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(34px, 6vw, 60px)',
            lineHeight: 1.08,
          }}
        >
          {t('land.h1a')}
          <br />
          {t('land.h1b')}
        </h1>
        <p
          className="text-[var(--color-text-tertiary)] max-w-[560px]"
          style={{ fontFamily: 'var(--font-sans)', fontSize: 15, lineHeight: 1.6 }}
        >
          {t('land.lede')}
        </p>
        <div className="flex items-center gap-3 mt-2">
          <Link
            to="/worlds"
            className="hover-btn inline-flex items-center gap-2 px-5 py-2.5 rounded text-[14px] font-medium"
            style={{
              fontFamily: 'var(--font-sans)',
              background: 'var(--color-accent)',
              color: '#fff',
              textDecoration: 'none',
            }}
          >
            {t('land.browseWorlds')} <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            to="/souls"
            className="hover-btn inline-flex items-center gap-2 px-5 py-2.5 rounded text-[14px] font-medium border border-[var(--color-border-light)]"
            style={{
              fontFamily: 'var(--font-sans)',
              color: 'var(--color-text-secondary)',
              textDecoration: 'none',
            }}
          >
            {t('land.browseSouls')}
          </Link>
        </div>
      </div>

      {/* Four-door grid — the hub's primary actions. Browse (WorldHub
          / SoulHub) and Create (world / soul) get equal weight so the
          user knows from the landing page that both consumption AND
          authoring are first-class. The header still carries shortcut
          links, but this section is what someone hitting the root cold
          actually sees first.  */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 w-full">
        {DOORS.map((d) => {
          const Icon = d.icon
          return (
            <Link
              key={d.to}
              to={d.to}
              className="hover-card relative rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-5 md:p-6 flex flex-col gap-2.5 overflow-hidden"
              style={{ textDecoration: 'none', minHeight: 200 }}
            >
              <div
                className="absolute -top-14 -right-14 w-40 h-40 rounded-full opacity-25 pointer-events-none"
                style={{
                  background: `radial-gradient(circle, ${d.accent}, transparent 70%)`,
                }}
              />
              <div className="relative flex items-center gap-1.5">
                <Icon className="w-5 h-5" style={{ color: d.accent }} />
                {d.create && (
                  <PlusCircle
                    className="w-3.5 h-3.5"
                    style={{ color: d.accent, opacity: 0.85 }}
                  />
                )}
              </div>
              <span
                className="text-[var(--color-text-primary)]"
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 22,
                  lineHeight: 1.1,
                }}
              >
                {t(d.labelKey)}
              </span>
              <p
                className="text-[var(--color-text-tertiary)] flex-1"
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: 12.5,
                  lineHeight: 1.5,
                }}
              >
                {t(d.blurbKey)}
              </p>
              <span
                className="inline-flex items-center gap-1 text-[12px] mt-auto"
                style={{ color: d.accent, fontFamily: 'var(--font-sans)' }}
              >
                {d.create ? t('land.create') : t('land.enter')}{' '}
                <ArrowRight className="w-3 h-3" />
              </span>
            </Link>
          )
        })}
      </div>

      {/* Play now — curated, always clickable (not gated on S3 publish) */}
      <PlayNowRow />

      {/* Featured */}
      <div className="flex flex-col gap-10 w-full">
        <FeaturedRow kind="worlds" />
        <FeaturedRow kind="souls" />
      </div>

      {/* How it works */}
      <div className="flex flex-col gap-4 w-full max-w-[720px] items-center text-center">
        <span
          className="font-mono text-[10px] text-[var(--color-text-muted)] tracking-[0.18em]"
          style={{ fontFamily: 'var(--font-mono)' }}
        >
          {t('land.how')}
        </span>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full">
          {STEPS.map(([h, b]) => (
            <div
              key={h}
              className="rounded border border-[var(--color-border)] bg-[var(--color-bg-card-inner)] p-4 flex flex-col gap-1.5 text-left"
            >
              <span
                className="font-mono text-[11px]"
                style={{
                  color: 'var(--color-accent-dim)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {h}
              </span>
              <span
                className="text-[13px] text-[var(--color-text-tertiary)]"
                style={{ fontFamily: 'var(--font-sans)', lineHeight: 1.5 }}
              >
                {b}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
