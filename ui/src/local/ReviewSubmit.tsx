// 「提交审查」卡(HUB-GOLIVE §P5,仅 hosted 显示)— 挂在工坊概览:
// 提交当前世界进审查队列(pending),展示最近一次提交的三态与退回留言。
// 组件零分叉:local 入口(非 hosted chrome)下渲染 null。
import { useCallback, useEffect, useState } from 'react'
import { mySubmissions, submitForReview, type SubmissionMeta } from './localClient'
import { useHostedChrome } from './hostedChrome'
import { useLocalT } from './i18n'

const STATUS_STYLE: Record<string, { labelKey: string; color: string }> = {
  pending: { labelKey: 'studio.reviewPending', color: '#F5C453' },
  approved: { labelKey: 'studio.reviewApproved', color: 'var(--lc-candle)' },
  rejected: { labelKey: 'studio.reviewRejected', color: '#F87171' },
}

export function ReviewSubmit({ worldId, worldName }: { worldId: string; worldName: string }) {
  const hosted = useHostedChrome()
  const { t } = useLocalT()
  const [latest, setLatest] = useState<SubmissionMeta | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  // Promise-chain form so react-hooks/set-state-in-effect can see that the
  // setState happens in the async continuation (it does not model await).
  const refresh = useCallback(
    () =>
      mySubmissions()
        .then((subs) => {
          setLatest(subs.find((s) => s.slug === worldId || s.name === worldName) || null)
        })
        .catch(() => {
          /* 路由面不可达(纯本地)— 卡片本就不显示 */
        }),
    [worldId, worldName],
  )

  useEffect(() => {
    if (hosted && worldId) void refresh()
  }, [hosted, worldId, refresh])

  if (!hosted || !worldId) return null

  async function doSubmit() {
    setBusy(true)
    setErr('')
    try {
      const meta = await submitForReview('worlds', worldId, worldName || worldId)
      setLatest(meta)
    } catch (e) {
      setErr(String(e).slice(0, 200))
    } finally {
      setBusy(false)
    }
  }

  const st = latest ? STATUS_STYLE[latest.status] : null
  return (
    <div
      className="rounded-xl border p-4 mt-4"
      style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)' }}
      data-testid="review-submit-card"
    >
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-mono tracking-widest" style={{ color: 'var(--lc-faint)' }}>
            {t('studio.reviewTitle')}
          </div>
          <p className="mt-1 mb-0 text-[12.5px]" style={{ color: 'var(--lc-dim)' }}>
            {t('studio.reviewHint')}
          </p>
        </div>
        {st && latest && (
          <span
            className="text-[12px] px-2.5 py-1 rounded-full border shrink-0"
            style={{ color: st.color, borderColor: st.color }}
            title={latest.submitted_at}
          >
            ● {t(st.labelKey)}
          </span>
        )}
        <button
          onClick={doSubmit}
          disabled={busy || latest?.status === 'pending'}
          className="text-[13px] px-4 py-2 rounded-lg border-0 cursor-pointer shrink-0"
          style={{
            background: 'var(--lc-candle)',
            color: 'var(--lc-on-accent)',
            opacity: busy || latest?.status === 'pending' ? 0.5 : 1,
          }}
        >
          {busy ? t('studio.reviewBusy') : latest ? t('studio.reviewResubmit') : t('studio.reviewSubmit')}
        </button>
      </div>
      {latest?.status === 'rejected' && latest.review_note && (
        <div
          className="mt-3 text-[12.5px] rounded-lg px-3 py-2"
          style={{ background: '#F8717118', color: 'var(--lc-text)' }}
        >
          {t('studio.reviewNote')}:{latest.review_note}
        </div>
      )}
      {latest?.precheck && (
        <div className="mt-2 text-[11.5px] font-mono" style={{ color: 'var(--lc-faint)' }}>
          {latest.precheck.playable ? '✓' : '✗'} {t('studio.reviewPrecheck')} ·{' '}
          {t('studio.reviewCounts', {
            blockers: latest.precheck.blockers_count || 0,
            warnings: latest.precheck.warnings_count || 0,
          })}
        </div>
      )}
      {err && (
        <div className="mt-2 text-[12px]" style={{ color: '#F87171' }}>
          {err}
        </div>
      )}
    </div>
  )
}
