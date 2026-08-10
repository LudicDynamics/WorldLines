import { useState } from 'react'
import { Copy, Check } from 'lucide-react'

export function HashCopy({
  value,
  label,
  className = '',
}: {
  value: string
  label?: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      // Clipboard blocked — fall back to selecting (browser limitation).
    }
  }

  return (
    <button
      onClick={onCopy}
      className={`hover-btn inline-flex items-center gap-2 font-mono text-[12px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-[var(--color-border-light)] hover:border-[var(--color-accent-dim)] rounded px-2 py-1 ${className}`}
      style={{ fontFamily: 'var(--font-mono)' }}
      aria-label={`Copy ${label ?? value}`}
    >
      {copied ? (
        <Check className="w-3 h-3 text-[var(--color-command)]" />
      ) : (
        <Copy className="w-3 h-3" />
      )}
      <span>{label ?? value}</span>
    </button>
  )
}
