// 审查队列(HUB-GOLIVE §P5)— AdminDashboard 的 founder 后台面板:
// pending 列表(封面/预审红旗)+ 一键 通过/退回(退回必须留言)。
// 全部经路由 /api/v1/play/review/*(路由验管理员,再持服务 token 转
// registry)—— 浏览器永远不直连 registry。
import { useCallback, useEffect, useState } from 'react'
import type { SubmissionMeta } from '../local/localClient'
import { computeOrigin } from '../play/playClient'

const API = `${computeOrigin()}/api/v1/play/review`

async function jfetch<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: 'include', ...init })
  if (!r.ok) throw new Error(`${url} → ${r.status} ${await r.text().catch(() => '')}`)
  return (await r.json()) as T
}

function Precheck({ m }: { m: SubmissionMeta }) {
  const p = m.precheck
  if (!p) return null
  const bad = !p.playable || (p.blockers_count || 0) > 0
  return (
    <div className="text-[11.5px] font-mono mt-1" style={{ color: bad ? '#F87171' : '#4ADE80' }}>
      {p.playable ? '✓ 可玩' : '✗ 不可玩'} · {p.flavor || '?'} · {p.blockers_count || 0} 阻断 ·{' '}
      {p.warnings_count || 0} 提醒
      {bad && (p.blockers || []).slice(0, 3).map((b, i) => (
        <div key={i} className="mt-0.5 opacity-80">— {b.summary || ''}</div>
      ))}
    </div>
  )
}

export function ReviewQueue() {
  const [subs, setSubs] = useState<SubmissionMeta[]>([])
  const [status, setStatus] = useState<'pending' | 'approved' | 'rejected'>('pending')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const [forbidden, setForbidden] = useState(false)

  // Written as an explicit promise chain rather than async/await: every
  // setState here already happens in the async continuation, and the .then
  // form is what makes that visible to react-hooks/set-state-in-effect, which
  // does not model the await boundary. Same requests, same ordering.
  const refresh = useCallback(
    () =>
      jfetch<{ submissions: SubmissionMeta[] }>(`${API}/submissions?status=${status}`)
        .then((d) => {
          setSubs(d.submissions || [])
          setErr('')
          setForbidden(false)
        })
        .catch((e) => {
          const msg = String(e)
          if (msg.includes('403')) setForbidden(true)
          else setErr(msg.slice(0, 200))
        }),
    [status],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function act(m: SubmissionMeta, action: 'approve' | 'reject') {
    let note = ''
    if (action === 'reject') {
      note = window.prompt('退回留言(创作者可见,必填):') || ''
      if (!note.trim()) return
    }
    setBusy(`${m.slug}/${m.stamp}`)
    try {
      await jfetch(`${API}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: m.kind, slug: m.slug, stamp: m.stamp, action, note }),
      })
      await refresh()
    } catch (e) {
      setErr(String(e).slice(0, 200))
    } finally {
      setBusy('')
    }
  }

  if (forbidden) return null // 非管理员 uid:整个面板不渲染

  return (
    <section className="mt-10" data-testid="review-queue">
      <div className="flex items-center gap-3">
        <h2 className="m-0 text-[16px] font-bold" style={{ color: 'var(--color-text-primary)' }}>
          审查队列
        </h2>
        {(['pending', 'approved', 'rejected'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className="text-[12px] px-2.5 py-1 rounded-lg border cursor-pointer"
            style={
              s === status
                ? { borderColor: 'var(--color-accent)', color: 'var(--color-accent)', background: 'var(--color-accent-10)' }
                : { borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)', background: 'transparent' }
            }
          >
            {s === 'pending' ? '待审' : s === 'approved' ? '已上架' : '已退回'}
          </button>
        ))}
        <button
          onClick={refresh}
          className="ml-auto text-[12px] px-2.5 py-1 rounded-lg border cursor-pointer"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)', background: 'transparent' }}
        >
          ⟳ 刷新
        </button>
      </div>
      {err && <div className="mt-2 text-[12px]" style={{ color: '#F87171' }}>{err}</div>}
      {subs.length === 0 && (
        <p className="mt-3 text-[13px]" style={{ color: 'var(--color-text-tertiary)' }}>
          {status === 'pending' ? '队列空 — 没有等待审查的提交。' : '暂无记录。'}
        </p>
      )}
      <div className="mt-3 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(340px,1fr))' }}>
        {subs.map((m) => {
          const key = `${m.slug}/${m.stamp}`
          return (
            <div
              key={key}
              className="rounded-xl border p-3 flex gap-3"
              style={{ background: 'var(--color-bg-card)', borderColor: 'var(--color-border)' }}
            >
              <img
                src={`${API}/file/${m.kind}/${m.slug}/${m.stamp}/cover`}
                alt=""
                className="w-[72px] h-[96px] object-cover rounded-lg shrink-0"
                style={{ background: 'var(--color-bg-card-inner)' }}
                onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')}
              />
              <div className="min-w-0 flex-1">
                <div className="font-bold text-[14px] truncate" style={{ color: 'var(--color-text-primary)' }}>
                  {m.name}
                  <span className="ml-2 font-mono text-[10.5px]" style={{ color: 'var(--color-text-tertiary)' }}>
                    {m.kind}/{m.slug}
                  </span>
                </div>
                <div className="text-[11.5px] mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  {m.uploader} · {m.submitted_at?.slice(0, 16).replace('T', ' ')} ·{' '}
                  {Math.round((m.size_bytes || 0) / 1024 / 102.4) / 10}MB
                </div>
                {m.summary && (
                  <div className="text-[12px] mt-1 line-clamp-2" style={{ color: 'var(--color-text-secondary)' }}>
                    {m.summary}
                  </div>
                )}
                <Precheck m={m} />
                {m.status === 'rejected' && m.review_note && (
                  <div className="text-[11.5px] mt-1" style={{ color: '#F5C453' }}>留言:{m.review_note}</div>
                )}
                <div className="mt-2 flex items-center gap-2">
                  {m.status === 'pending' && (
                    <>
                      <button
                        onClick={() => act(m, 'approve')}
                        disabled={busy === key}
                        className="text-[12px] px-3 py-1.5 rounded-lg border-0 cursor-pointer font-semibold"
                        style={{ background: 'var(--color-accent)', color: '#0A0A0A', opacity: busy === key ? 0.5 : 1 }}
                      >
                        通过
                      </button>
                      <button
                        onClick={() => act(m, 'reject')}
                        disabled={busy === key}
                        className="text-[12px] px-3 py-1.5 rounded-lg border cursor-pointer"
                        style={{ borderColor: '#F87171', color: '#F87171', background: 'transparent', opacity: busy === key ? 0.5 : 1 }}
                      >
                        退回
                      </button>
                    </>
                  )}
                  <a
                    href={`${API}/file/${m.kind}/${m.slug}/${m.stamp}/zip`}
                    className="text-[11.5px] ml-auto"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    ↓ zip 细查
                  </a>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
