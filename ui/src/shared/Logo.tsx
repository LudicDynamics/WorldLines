import { Link } from 'react-router-dom'

export function Logo({ size = 'default' }: { size?: 'default' | 'small' }) {
  const markSize = size === 'small' ? 24 : 28
  return (
    <Link to="/" className="flex items-center" style={{ gap: 10 }}>
      <img
        src="/logo-mark.png"
        alt="WorldLines"
        style={{
          width: markSize,
          height: markSize,
          objectFit: 'contain',
          borderRadius: 4,
        }}
      />
      <span
        className="text-[var(--color-text-primary)]"
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: size === 'small' ? 14 : 16,
          fontWeight: 400,
          letterSpacing: 0.5,
        }}
      >
        Worldlines
      </span>
      <span
        className="font-mono text-[10px] text-[var(--color-accent-dim)] tracking-[0.18em] ml-1 px-1.5 py-0.5 border border-[var(--color-accent-faint)] rounded-sm"
        style={{ fontFamily: 'var(--font-mono)' }}
      >
        HUB
      </span>
    </Link>
  )
}
