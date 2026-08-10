// 进场界面(PrePlay)— 进入游玩之前的准备页,内容按 TUI 启动流重排
// (PLAY-FUSION-DECISIONS.md D4):单页纵向分步 —
//   ① 世界确认(封面 + 名字 + 简介 / 存档 tease)
//   ② 带入角色 Casting(多选 souls;resume 时跳过)
//   ③ 模型接入(preset 药丸 + 补 key + 测连通;与 Welcome 共用)
//   ④ 底部大按钮「▸ 进入世界」
// 进入 = bindPlaySession({slug, preset, souls}) → 桥接经典 `neonrp web`
// 游玩现场 = /local/stage(PlayStage,D5)。
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  localEndpoint,
  bindPlaySession,
  listLocalSaves,
  listLocalSouls,
  listLocalWorlds,
  saveProviderKey,
  worldCoverUrl,
  type LocalSave,
  type LocalSoul,
  type LocalWorld,
} from '../local/localClient'
import { coverFallback } from '../local/LocalPlayGate'
import { useLocalT } from '../local/i18n'
import { ModelAccessPanel, REMEMBER_PRESET_KEY, type ModelAccessState } from './ModelAccessPanel'

// 分步区块的编号标题(① 世界确认 …)。视觉延续 --lc-* token。
function StepHeader({ n, title, hint }: { n: string; title: string; hint?: string }) {
  return (
    <div className="flex items-baseline gap-2.5 mb-3">
      <span
        className="flex-none inline-flex items-center justify-center w-6 h-6 rounded-full text-[13px] font-semibold"
        style={{ background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }}
      >
        {n}
      </span>
      <h2 className="m-0 text-[15px] font-semibold">{title}</h2>
      {hint && (
        <span className="text-[12px]" style={{ color: 'var(--lc-faint)' }}>
          {hint}
        </span>
      )}
    </div>
  )
}

export function LocalPrePlay() {
  const { t } = useLocalT()
  const navigate = useNavigate()
  // slug = 存档 session_id(继续)或世界 id(新开),由入口决定
  const { slug = '' } = useParams<{ slug: string }>()
  const [sp] = useSearchParams()
  const isResume = sp.get('resume') === '1'

  const [access, setAccess] = useState<ModelAccessState>({
    picked: null,
    needsKey: false,
    key: '',
    ready: false,
  })
  const [save, setSave] = useState<LocalSave | null>(null)
  const [world, setWorld] = useState<LocalWorld | null>(null)
  const [entering, setEntering] = useState(false)
  // Casting(B6/B4):新开局可多选带入库里的角色;?cast= 预选(书房「对话」)
  const [souls, setSouls] = useState<LocalSoul[]>([])
  const [cast, setCast] = useState<Set<string>>(
    () => new Set((sp.get('cast') || '').split(',').filter(Boolean)),
  )

  const worldId = isResume ? (save?.slug ?? slug.replace(/-\d{8}-\d{6}$/, '')) : slug

  useEffect(() => {
    if (isResume) {
      listLocalSaves()
        .then((all) => setSave(all.find((s) => s.session_id === slug) ?? null))
        .catch(() => {})
    } else {
      listLocalSouls()
        .then((d) => setSouls(d.souls))
        .catch(() => {})
    }
  }, [slug, isResume])

  // 世界确认(①)要拿到简介 desc + 展示名 —— 引擎 GET /api/v1/local/worlds。
  useEffect(() => {
    listLocalWorlds()
      .then((d) => {
        const all = [...d.worlds, ...d.builtin]
        setWorld(all.find((w) => w.id === worldId) ?? null)
      })
      .catch(() => {})
  }, [worldId])

  const worldName =
    (isResume && save?.name) ||
    world?.display_name ||
    world?.name_local ||
    world?.name ||
    worldId

  async function enter() {
    if (!access.picked || entering) return
    setEntering(true)
    try {
      if (access.needsKey && access.key.trim()) {
        await saveProviderKey(access.picked.id, access.key.trim())
      }
      try {
        localStorage.setItem(REMEMBER_PRESET_KEY, access.picked.id)
      } catch {
        /* storage off */
      }
      await bindPlaySession(slug, {
        preset: access.picked.id,
        souls: isResume ? undefined : [...cast],
      })
      // PlayStage 现已是 SPA 内的路由组件(/local/stage),客户端跳转即可。
      // 原来用 window.location.href 整页 reload —— SPA 重载间隙会白屏一瞬,
      // 让人误以为卡住(其实后台在转)。navigate 无整页刷新,PrePlay 的
      // loading 无缝过渡到 PlayStage 的开机剧场。hosted 入口下 /local/stage
      // 由 main-hub 的 LegacyLocalRedirect 客户端转到 /play/stage(仍无白屏)。
      navigate('/local/stage')
    } catch (e) {
      setEntering(false)
      alert(String(e))
    }
  }

  const panel = { background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }

  return (
    <div className="pt-8 pb-24 max-w-[720px] mx-auto">
      <Link to={isResume ? '/local' : '/local/play'} className="text-[12px]" style={{ color: 'var(--lc-faint)' }}>
        {t('preplay.back')}
      </Link>
      <h1 className="mt-2 mb-6 text-[20px] font-bold m-0">
        {t('preplay.title')}
        <span className="ml-3 text-[12px] font-mono font-normal" style={{ color: 'var(--lc-faint)' }}>
          {t('preplay.subtitle')}
        </span>
      </h1>

      <div className="flex flex-col gap-4">
        {/* ① 世界确认 —— 封面 + 名字 + 简介 / 存档 tease */}
        <section className="rounded-xl border p-5" style={panel}>
          <StepHeader n="①" title={t('preplay.step1Title')} hint={isResume ? t('preplay.resumeSave') : t('preplay.newRun')} />
          <div className="rounded-lg border overflow-hidden flex flex-col sm:flex-row" style={{ borderColor: 'var(--lc-line)' }}>
            <div className="relative w-full sm:w-[220px] h-[130px] flex-none" style={{ background: coverFallback(worldId) }}>
              <img
                src={worldCoverUrl(worldId)}
                onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                alt=""
                className="absolute inset-0 w-full h-full object-cover"
              />
            </div>
            <div className="p-4 flex-1 min-w-0">
              <div className="text-[16px] font-semibold">{worldName}</div>
              <div className="text-[11px] font-mono mt-0.5" style={{ color: 'var(--lc-faint)' }}>
                {isResume ? t('preplay.resumeSaveWith', { sid: slug }) : t('preplay.newRun')}
              </div>
              {world?.desc && (
                <p className="mt-2 text-[13px] leading-relaxed max-w-[52ch]" style={{ color: 'var(--lc-dim)' }}>
                  {world.desc}
                </p>
              )}
              {isResume && save?.feed_tease && (
                <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
                  {save.feed_tease}
                </p>
              )}
            </div>
          </div>
        </section>

        {/* ② 带入角色 Casting —— resume 时跳过 */}
        {!isResume && (
          <section className="rounded-xl border p-5" style={panel}>
            <StepHeader n="②" title={t('preplay.step2Title')} hint={t('preplay.castHint')} />
            {souls.length > 0 ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {souls.map((so) => {
                    const key = so.dir_name || so.sid
                    const on = cast.has(key)
                    return (
                      <button
                        key={key}
                        onClick={() =>
                          setCast((prev) => {
                            const next = new Set(prev)
                            if (next.has(key)) next.delete(key)
                            else next.add(key)
                            return next
                          })
                        }
                        className="text-[12px] rounded-full px-3 py-1 cursor-pointer border"
                        style={
                          on
                            ? { background: 'var(--lc-candle-soft)', borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)' }
                            : { background: 'transparent', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }
                        }
                      >
                        <img
                          src={`${localEndpoint()}/api/v1/local/souls/${encodeURIComponent(key)}/portrait`}
                          onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                          alt=""
                          className="inline-block w-4 h-4 rounded-full object-cover mr-1 align-[-3px]"
                        />
                        {on ? '✓ ' : ''}
                        {so.display_name || so.name_local || so.name || key}
                      </button>
                    )
                  })}
                </div>
                <p className="mt-2 text-[11px]" style={{ color: 'var(--lc-faint)' }}>
                  {t('preplay.castNote')}
                </p>
              </>
            ) : (
              <p className="text-[12px]" style={{ color: 'var(--lc-faint)' }}>
                {t('preplay.castEmpty')}
              </p>
            )}
          </section>
        )}

        {/* ③ 模型接入 —— 与 /local/welcome 引导共用 */}
        <section className="rounded-xl border p-5" style={panel}>
          <StepHeader n={isResume ? '②' : '③'} title={t('preplay.step3Title')} hint={t('preplay.modelHint')} />
          <p className="mt-1 mb-4 text-[12px]" style={{ color: 'var(--lc-faint)' }}>
            {t('preplay.credNote')}
          </p>
          <ModelAccessPanel onState={setAccess} />
        </section>
      </div>

      {/* ④ 底部大按钮 */}
      <button
        onClick={enter}
        disabled={!access.ready || entering}
        className="mt-6 w-full text-[15px] font-semibold rounded-lg px-4 py-3 cursor-pointer border-0"
        style={{
          background: 'var(--lc-candle)',
          color: 'var(--lc-on-accent)',
          opacity: access.ready ? 1 : 0.5,
        }}
      >
        {entering ? (isResume ? t('preplay.entering') : t('preplay.buildingWorld')) : t('preplay.enterWorld')}
      </button>
    </div>
  )
}
