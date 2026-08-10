export function formatBytes(n: number): string {
  if (!n || n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(2)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toISOString().slice(0, 10)
  } catch {
    return iso
  }
}

export function relativeDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso).getTime()
  const now = Date.now()
  const diffSec = Math.max(0, Math.round((now - d) / 1000))
  if (diffSec < 60) return `${diffSec}s ago`
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  if (diffSec < 86400 * 30) return `${Math.floor(diffSec / 86400)}d ago`
  if (diffSec < 86400 * 365) return `${Math.floor(diffSec / 86400 / 30)}mo ago`
  return `${Math.floor(diffSec / 86400 / 365)}y ago`
}
