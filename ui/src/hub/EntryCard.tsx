import { Link } from 'react-router-dom'
import { ArrowUpRight, Play } from 'lucide-react'
import type { Kind, Story } from '../shared/registry'
import { coverFor } from '../shared/registry'
import { isPlayable } from '../shared/playable'
import { useI18n } from '../shared/i18n'
import { formatBytes, relativeDate } from '../shared/format'

const KIND_COLOR: Record<Kind, string> = {
  worlds: 'var(--color-world)',
  souls: 'var(--color-soul)',
}

const KIND_TAG: Record<Kind, string> = {
  worlds: 'WORLD',
  souls: 'SOUL',
}

export function EntryCard({ kind, story }: { kind: Kind; story: Story }) {
  const { t } = useI18n()
  const accent = KIND_COLOR[kind]
  const latest = story.versions[0]
  const cover = coverFor(kind, story.slug, latest)
  const playable = isPlayable(kind, story.slug)

  const playBadge = playable && (
    <span
      className="absolute top-3 right-3 inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.14em] px-2 py-1 rounded-sm bg-black/55 backdrop-blur-sm"
      style={{ color: accent, fontFamily: 'var(--font-mono)' }}
    >
      <Play className="w-2.5 h-2.5 fill-current" />
      {t('card.playable')}
    </span>
  )

  return (
    <Link
      to={`/${kind}/${story.slug}`}
      className="hover-card relative rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] flex flex-col overflow-hidden block"
      style={{ textDecoration: 'none' }}
    >
      {/* Cover image OR gradient fallback */}
      {cover ? (
        <div
          className="relative w-full overflow-hidden"
          style={{ aspectRatio: '16 / 9' }}
        >
          <img
            src={cover}
            alt={story.display_name}
            loading="lazy"
            className="w-full h-full object-cover"
          />
          {/* Bottom fade so the metadata under it stays legible */}
          <div
            className="absolute inset-x-0 bottom-0 h-2/3 pointer-events-none"
            style={{
              background:
                'linear-gradient(to bottom, transparent 0%, rgba(10,10,10,0.55) 65%, var(--color-bg-card) 100%)',
            }}
          />
          {/* Tag pinned over the image */}
          <span
            className="absolute top-3 left-3 font-mono text-[10px] tracking-[0.18em] px-2 py-1 rounded-sm bg-black/55 backdrop-blur-sm"
            style={{ color: accent, fontFamily: 'var(--font-mono)' }}
          >
            {KIND_TAG[kind]} · v{story.latest_version}
          </span>
          {playBadge}
        </div>
      ) : (
        <div
          className="relative w-full overflow-hidden flex items-start justify-between p-4"
          style={{ aspectRatio: '16 / 9' }}
        >
          <div
            className="absolute -top-12 -right-12 w-40 h-40 rounded-full opacity-30 pointer-events-none"
            style={{
              background: `radial-gradient(circle, ${accent}, transparent 70%)`,
            }}
          />
          <span
            className="relative font-mono text-[10px] tracking-[0.18em]"
            style={{ color: accent, fontFamily: 'var(--font-mono)' }}
          >
            {KIND_TAG[kind]} · v{story.latest_version}
          </span>
          {playable ? (
            playBadge
          ) : (
            <ArrowUpRight className="relative w-4 h-4 text-[var(--color-text-tertiary)]" />
          )}
        </div>
      )}

      {/* Body */}
      <div className="flex flex-col gap-2 p-5 flex-1">
        <h3
          className="text-[var(--color-text-primary)]"
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(20px, 2.4vw, 24px)',
            lineHeight: 1.15,
          }}
        >
          {story.display_name}
        </h3>

        {latest.changelog && (
          <p
            className="text-[var(--color-text-tertiary)]"
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 13,
              lineHeight: 1.5,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {latest.changelog}
          </p>
        )}

        <div className="mt-auto flex items-center justify-between pt-3">
          <span
            className="font-mono text-[10px] text-[var(--color-text-muted)]"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {story.latest_hash}
          </span>
          <span
            className="font-mono text-[10px] text-[var(--color-text-tertiary)]"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {formatBytes(latest.size_bytes)} · {relativeDate(latest.uploaded_at)}
          </span>
        </div>
      </div>
    </Link>
  )
}
