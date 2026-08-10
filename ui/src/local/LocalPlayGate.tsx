// 「游玩」门 — 封面卡网格(共识:ludics 式封面墙)。内置 + 我的世界合并;
// 封面走 /api/v1/local/worlds/<id>/cover,没有就回退到画风锚渐变。
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listLocalWorlds, worldCoverUrl, type LocalWorld } from './localClient'
import { useLocalT } from './i18n'

// 无封面时的确定性渐变(按 id 哈希取色相 — 每个世界有稳定的"底色")。
// 可视化随主题(不只面板换色):饱和/明度经 --lc-cov* token 由主题给——
// 黑 = visionrp 夜色深渐变;白 = archive-room 水彩纸色(淡彩、高明度,
// 对标其 .card .ph 的 tan→sage)。图形元素与主题同气质,见 LocalApp THEMES。
export function coverFallback(id: string): string {
  let h = 0
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360
  return `linear-gradient(160deg,
    hsl(${h} var(--lc-cov1, 32% 30%)) 0%,
    hsl(${(h + 40) % 360} var(--lc-cov2, 28% 18%)) 60%,
    hsl(${(h + 80) % 360} var(--lc-cov3, 24% 12%)) 100%)`
}

export function WorldCard({ w, badge }: { w: LocalWorld; badge?: string }) {
  const [imgOk, setImgOk] = useState(true)
  const name = w.display_name || w.name_local || w.name || w.id
  return (
    <Link
      to={`/local/play/${encodeURIComponent(w.id)}`}
      className="rounded-xl overflow-hidden border transition-transform hover:-translate-y-0.5"
      style={{ borderColor: 'var(--lc-line)', background: 'var(--lc-panel)' }}
    >
      <div className="relative h-[150px]" style={{ background: coverFallback(w.id) }}>
        {imgOk && (
          <img
            src={worldCoverUrl(w.id)}
            onError={() => setImgOk(false)}
            alt=""
            className="absolute inset-0 w-full h-full object-cover"
          />
        )}
        {badge && (
          <span
            className="absolute top-2 right-2 text-[10px] font-mono rounded-full px-2 py-0.5"
            style={{ background: 'rgba(0,0,0,.55)', color: 'var(--lc-candle)' }}
          >
            {badge}
          </span>
        )}
      </div>
      <div className="p-3">
        <div className="text-[14.5px] font-semibold truncate" style={{ fontWeight: 700 }}>
          {name}
        </div>
        {w.desc && (
          <p className="mt-1 text-[12px] leading-relaxed line-clamp-2" style={{ color: 'var(--lc-dim)' }}>
            {w.desc}
          </p>
        )}
      </div>
    </Link>
  )
}

export function LocalPlayGate() {
  const [owned, setOwned] = useState<LocalWorld[]>([])
  const [builtin, setBuiltin] = useState<LocalWorld[]>([])
  const { t } = useLocalT()

  useEffect(() => {
    listLocalWorlds()
      .then((d) => {
        setOwned(d.worlds)
        // list_worlds() 的内置列表会把自建世界也并进来(TUI 选择器语义)—
        // 这里按 id 去重,只留真正的打包内置
        const ownedIds = new Set(d.worlds.map((w) => w.id))
        setBuiltin(d.builtin.filter((w) => !w.hidden && !ownedIds.has(w.id)))
      })
      .catch(() => {})
  }, [])

  return (
    <div className="pt-8">
      {owned.length > 0 && (
        <section className="mb-10">
          <div className="text-[11px] font-mono tracking-widest mb-3" style={{ color: 'var(--lc-faint)' }}>
            {t('play.myWorlds')}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {owned.map((w) => (
              <WorldCard key={w.id} w={w} badge={w.origin === 'created' ? t('play.badgeCreated') : t('play.badgeDownloaded')} />
            ))}
          </div>
        </section>
      )}
      <section>
        <div className="text-[11px] font-mono tracking-widest mb-3" style={{ color: 'var(--lc-faint)' }}>
          {t('play.builtin')}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {builtin.map((w) => (
            <WorldCard key={w.id} w={w} />
          ))}
        </div>
      </section>
    </div>
  )
}
