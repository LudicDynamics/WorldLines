// 世界详情 — 封面 hero + 该世界的存档(继续)+ 新开一局 + (我的世界)修改。
// 「一览呈现」(rp-visionrp:树/地图/关系网)后续在此页扩展。
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  deleteSave,
  listLocalSaves,
  listLocalWorlds,
  openCreateSession,
  worldCoverUrl,
  type LocalSave,
  type LocalWorld,
} from './localClient'
import { coverFallback } from './LocalPlayGate'
import { useLocalT } from './i18n'

export function LocalWorldDetail() {
  const { worldId = '' } = useParams<{ worldId: string }>()
  const { t } = useLocalT()
  const [world, setWorld] = useState<LocalWorld | null>(null)
  const [saves, setSaves] = useState<LocalSave[]>([])
  const [imgOk, setImgOk] = useState(true)
  const [busy, setBusy] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    listLocalWorlds()
      .then((d) => {
        const all = [...d.worlds, ...d.builtin]
        setWorld(all.find((w) => w.id === worldId) ?? null)
      })
      .catch(() => {})
    listLocalSaves()
      .then((all) => setSaves(all.filter((s) => s.slug === worldId)))
      .catch(() => {})
  }, [worldId])

  const name = useMemo(
    () => world?.display_name || world?.name_local || world?.name || worldId,
    [world, worldId],
  )

  function enter(slug: string) {
    // 经进场页(PrePlay);存档带 resume=1,世界 id 走新开
    const resume = slug !== worldId ? '?resume=1' : ''
    nav(`/local/preplay/${encodeURIComponent(slug)}${resume}`)
  }

  async function editWorld() {
    setBusy('edit')
    try {
      await openCreateSession({ world_id: worldId })
      nav('/local/create/studio')
    } catch (e) {
      setBusy('')
      alert(String(e))
    }
  }

  async function removeSave(sid: string) {
    if (!confirm(t('detail.deleteSaveConfirm', { sid }))) return
    await deleteSave(sid).catch((e) => alert(String(e)))
    setSaves((xs) => xs.filter((s) => s.session_id !== sid))
  }

  return (
    <div className="pt-8">
      <Link to="/local/play" className="text-[12px]" style={{ color: 'var(--lc-faint)' }}>
        {t('detail.backPlay')}
      </Link>
      <div
        className="mt-3 rounded-2xl overflow-hidden border flex flex-col sm:flex-row"
        style={{ borderColor: 'var(--lc-line)', background: 'var(--lc-panel)' }}
      >
        <div className="relative w-full sm:w-[280px] h-[180px] flex-none" style={{ background: coverFallback(worldId) }}>
          {imgOk && (
            <img
              src={worldCoverUrl(worldId)}
              onError={() => setImgOk(false)}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
            />
          )}
        </div>
        <div className="p-6 flex-1 min-w-0">
          <h1 className="text-[22px] font-semibold m-0" style={{ fontWeight: 700 }}>
            {name}
          </h1>
          {world?.desc && (
            <p className="mt-2 text-[13.5px] max-w-[60ch]" style={{ color: 'var(--lc-dim)' }}>
              {world.desc}
            </p>
          )}
          <div className="mt-4 flex gap-3 flex-wrap">
            <button
              onClick={() => enter(worldId)}
              disabled={busy !== ''}
              className="text-[13px] font-semibold rounded-lg px-5 py-2 cursor-pointer border-0"
              style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}
            >
              {busy === 'new' ? t('detail.building') : t('detail.newRun')}
            </button>
            {world?.owned && (
              <button
                onClick={editWorld}
                disabled={busy !== ''}
                className="text-[13px] rounded-lg px-5 py-2 cursor-pointer border"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }}
              >
                {busy === 'edit' ? t('detail.openingStudio') : t('detail.editThisWorld')}
              </button>
            )}
          </div>
        </div>
      </div>

      <section className="mt-8">
        <div className="text-[11px] font-mono tracking-widest mb-3" style={{ color: 'var(--lc-faint)' }}>
          {t('detail.savesTitle')}({saves.length})
        </div>
        {saves.length === 0 && (
          <p className="text-[13px]" style={{ color: 'var(--lc-faint)' }}>
            {t('detail.noSaves')}
          </p>
        )}
        <div className="flex flex-col gap-2">
          {saves.map((s) => (
            <div
              key={s.session_id}
              className="rounded-xl border p-3.5 flex items-center gap-4"
              style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-3">
                  <span className="text-[13px] font-mono truncate">{s.session_id}</span>
                  {s.in_memory && (
                    <span className="text-[10px] rounded-full px-2 py-0.5" style={{ background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }}>
                      {t('detail.current')}
                    </span>
                  )}
                </div>
                {s.feed_tease && (
                  <p className="mt-0.5 text-[12.5px] truncate" style={{ color: 'var(--lc-dim)' }}>
                    {s.feed_tease}
                  </p>
                )}
              </div>
              <button
                onClick={() => enter(s.session_id)}
                disabled={busy !== ''}
                className="flex-none text-[12.5px] rounded-lg px-4 py-1.5 cursor-pointer border"
                style={{ borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)', background: 'transparent' }}
              >
                {busy === s.session_id ? '…' : t('detail.resume')}
              </button>
              <button
                onClick={() => removeSave(s.session_id)}
                disabled={s.in_memory || busy !== ''}
                className="flex-none text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
                style={{ borderColor: 'var(--lc-line)', color: '#FF6B8A', background: 'transparent', opacity: s.in_memory ? 0.4 : 1 }}
              >
                {t('detail.delete')}
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
