// LocalShell 首屏 — 共识稿 v1(niko 拍板):继续区 + 功能四门。
// 继续区吃 /api/v1/play/saves 的 feed_tease/waiting(引擎 player-artifacts),
// 「回应」= 绑定该存档会话 → 跳共享 PlayPage(一份 play 代码,本地后端)。
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listLocalSaves, type LocalSave, worldCoverUrl } from './localClient'
import { useLocalT, type T } from './i18n'
import { coverFallback } from './LocalPlayGate'

function timeAgo(sec: number, t: T): string {
  const d = Date.now() / 1000 - sec
  if (d < 3600) return t('home.minAgo', { n: Math.max(1, Math.floor(d / 60)) })
  if (d < 86400) return t('home.hourAgo', { n: Math.floor(d / 3600) })
  return t('home.dayAgo', { n: Math.floor(d / 86400) })
}

export function LocalHome() {
  const [saves, setSaves] = useState<LocalSave[]>([])
  const nav = useNavigate()
  const { t } = useLocalT()

  useEffect(() => {
    listLocalSaves().then(setSaves).catch(() => setSaves([]))
  }, [])

  function enter(save: LocalSave) {
    // 经进场页(PrePlay):模型接入确认后再入世界
    nav(`/local/preplay/${encodeURIComponent(save.session_id)}?resume=1`)
  }

  const recent = saves.slice(0, 3)

  return (
    <div className="pt-8">
      {/* ── 继续区:最高频动作直达 ── */}
      {recent.length > 0 && (
        <section className="mb-10">
          <div className="text-[11px] font-mono tracking-widest mb-3" style={{ color: 'var(--lc-faint)' }}>
            {t('home.continue')}
          </div>
          <div className="flex flex-col gap-3">
            {recent.map((s) => (
              <button
                key={s.session_id}
                onClick={() => enter(s)}
                                className="text-left rounded-xl border p-4 flex items-center gap-4 transition-colors cursor-pointer"
                style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
              >
                <div
                  className="flex-none rounded-lg overflow-hidden"
                  style={{ width: 72, height: 48, background: coverFallback(s.slug) }}
                >
                  <img
                    src={worldCoverUrl(s.slug)}
                    onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-3 flex-wrap">
                    <span className="text-[16px] font-semibold" style={{ fontWeight: 700 }}>
                      {s.name}
                    </span>
                    <span className="text-[11px] font-mono" style={{ color: 'var(--lc-faint)' }}>
                      {s.feed_time || timeAgo(s.last_modified, t)}
                    </span>
                    {(s.waiting ?? []).length > 0 && (
                      <span
                        className="text-[11px] rounded-full border px-2.5 py-0.5"
                        style={{ color: 'var(--lc-candle)', borderColor: '#34E87960' }}
                      >
                        {t('home.waitingForYou', { names: (s.waiting ?? []).join('、') })}
                      </span>
                    )}
                  </div>
                  {s.feed_tease && (
                    <p className="mt-1 text-[13px] truncate" style={{ color: 'var(--lc-dim)' }}>
                      {s.feed_tease}
                    </p>
                  )}
                </div>
                <span
                  className="flex-none text-[13px] font-semibold rounded-lg px-4 py-2"
                  style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}
                >
                  {t('home.respond')}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* ── 功能四门 ── */}
      <div className="text-[11px] font-mono tracking-widest mb-3" style={{ color: 'var(--lc-faint)' }}>
        {t('home.doors')}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {[
          {
            to: '/local/play',
            icon: '▶',
            title: t('home.playTitle'),
            desc: t('home.playDesc'),
          },
          {
            to: '/local/create',
            icon: '✳',
            title: t('home.createTitle'),
            desc: t('home.createDesc'),
          },
          {
            to: '/local/library',
            icon: '▤',
            title: t('home.libraryTitle'),
            desc: t('home.libraryDesc'),
          },
          {
            to: 'https://hub.worldlines.gg',
            icon: '⇪',
            title: 'Hub',
            desc: t('home.hubDesc'),
            external: true,
          },
        ].map((d) =>
          d.external ? (
            <a
              key={d.title}
              href={d.to}
              target="_blank"
              rel="noreferrer"
              className="rounded-xl border p-6 transition-colors"
              style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
            >
              <DoorBody icon={d.icon} title={d.title} desc={d.desc} />
            </a>
          ) : (
            <Link
              key={d.title}
              to={d.to}
              className="rounded-xl border p-6 transition-colors"
              style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
            >
              <DoorBody icon={d.icon} title={d.title} desc={d.desc} />
            </Link>
          ),
        )}
      </div>
    </div>
  )
}

function DoorBody({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <>
      <div className="flex items-center gap-3">
        <span className="text-[18px]" style={{ color: 'var(--lc-candle)' }}>
          {icon}
        </span>
        <span className="text-[18px] font-semibold" style={{ fontWeight: 700 }}>
          {title}
        </span>
      </div>
      <p className="mt-2 text-[13px]" style={{ color: 'var(--lc-dim)' }}>
        {desc}
      </p>
    </>
  )
}
