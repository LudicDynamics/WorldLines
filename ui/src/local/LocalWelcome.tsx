// 游戏门面(Welcome)— 对标 rp-visionrp Tauri 的 start screen:
// 封面图 + LUDIC DYNAMICS / WorldLines / tagline + 菜单。
// 首次打开 LocalShell 自动落这(LocalApp 里 wl-local-welcomed 判定);
// 「▸ 开启旅程」时没有可用 preset → 就地展开模型接入引导,配好才放行。
// 刻意单主题(夜色门扉),不随 ☀/☾ 切换 —— 这是标题画面,不是工作界面。
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSettings, putImageSettings, saveProviderKey } from './localClient'
import { Link } from 'react-router-dom'
import { ModelAccessPanel, REMEMBER_PRESET_KEY, type ModelAccessState } from '../play/ModelAccessPanel'
import { LANGS, LANG_LABEL, useLocalT } from './i18n'
import doorArt from './welcome-door.jpg'

export const WELCOMED_KEY = 'wl-local-welcomed'

// welcome 页自带夜色 token(不进 LocalApp 的主题系统)
const NIGHT: React.CSSProperties = {
  '--lc-text': '#F5F5F7',
  '--lc-panel': 'rgba(15,15,30,0.78)',
  '--lc-panel2': 'rgba(10,10,20,0.85)',
  '--lc-line': '#2E2E36',
  '--lc-dim': '#9A9AA0',
  '--lc-faint': '#6E6E76',
  '--lc-candle': '#34E879',
  '--lc-candle-soft': '#34E87925',
  '--lc-live': '#06B6D4',
} as React.CSSProperties

export function LocalWelcome() {
  const nav = useNavigate()
  const { t, lang, setLang } = useLocalT()
  const [access, setAccess] = useState<ModelAccessState>({
    picked: null,
    needsKey: false,
    key: '',
    ready: false,
  })
  const [showApi, setShowApi] = useState(false)
  const [apiTab, setApiTab] = useState<'model' | 'image'>('model')
  const [imgBackend, setImgBackend] = useState('')
  const [imgUrl, setImgUrl] = useState('')
  const [imgMsg, setImgMsg] = useState('')
  useEffect(() => {
    if (!showApi) return
    getSettings()
      .then((d) => {
        if (d.image) {
          setImgBackend(d.image.backend)
          setImgUrl(d.image.comfyui_url)
        }
      })
      .catch(() => {})
  }, [showApi])
  const [busy, setBusy] = useState(false)

  function markWelcomed() {
    try {
      sessionStorage.setItem(WELCOMED_KEY, '1')
      if (access.picked) localStorage.setItem(REMEMBER_PRESET_KEY, access.picked.id)
    } catch {
      /* storage off */
    }
  }

  async function begin() {
    if (busy) return
    // 没配好模型 → 先展开引导,不放行
    if (!access.ready) {
      setShowApi(true)
      return
    }
    setBusy(true)
    try {
      if (access.needsKey && access.key.trim() && access.picked) {
        await saveProviderKey(access.picked.id, access.key.trim())
      }
      markWelcomed()
      nav('/local')
    } catch (e) {
      setBusy(false)
      alert(String(e))
    }
  }

  return (
    <div
      className="fixed inset-0 flex flex-col items-center justify-center overflow-y-auto"
      style={{
        color: 'var(--lc-text)',
        fontFamily: "'Inter',-apple-system,'PingFang SC',sans-serif",
        background: '#08080F',
        ...NIGHT,
      }}
    >
      {/* 三层背景:封面图 + 线性/径向 vignette(visionrp bg-layer)*/}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: `url(${doorArt}) center/cover no-repeat` }}
      />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(180deg, rgba(8,8,15,0.3) 0%, rgba(8,8,15,0.85) 100%)' }}
      />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'radial-gradient(ellipse at center, transparent 30%, rgba(8,8,15,0.9) 100%)' }}
      />

      {/* 语言切换 — 第一屏就能选(niko:从用户角度,门面必须可切语言) */}
      <div className="absolute top-5 right-6 z-[2] flex gap-1.5">
        {LANGS.map((l) => (
          <button
            key={l}
            onClick={() => setLang(l)}
            className="text-[12px] rounded-lg px-2.5 py-1 cursor-pointer border"
            style={
              l === lang
                ? { borderColor: 'var(--lc-candle)', background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                : { borderColor: 'var(--lc-line)', background: 'rgba(15,15,30,0.6)', color: 'var(--lc-dim)' }
            }
          >
            {LANG_LABEL[l]}
          </button>
        ))}
      </div>
      <header className="relative text-center mb-10 z-[1]">
        <div className="text-[12px] font-semibold" style={{ letterSpacing: '6px', color: 'var(--lc-dim)' }}>
          LUDIC DYNAMICS
        </div>
        <h1 className="m-0 my-2 font-bold" style={{ fontSize: 64, letterSpacing: '-2px' }}>
          WorldLines
        </h1>
        <div className="text-[14px]" style={{ letterSpacing: '2px', color: 'var(--lc-dim)' }}>
          {t('welcome.tagline')}
        </div>
      </header>

      <nav className="relative z-[1] flex flex-col gap-2.5 w-[320px]">
        <button
          onClick={begin}
          className="w-full text-left text-[16px] font-semibold rounded-xl px-6 py-3.5 cursor-pointer border"
          style={{
            background: 'rgba(15,15,30,0.85)',
            borderColor: 'var(--lc-candle)',
            color: 'var(--lc-text)',
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? t('welcome.saving') : t('welcome.begin')}
        </button>
        <button
          onClick={() => setShowApi((v) => !v)}
          className="w-full text-left text-[14px] rounded-xl px-6 py-3 cursor-pointer border"
          style={{ background: 'rgba(15,15,30,0.6)', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }}
        >
          {t('welcome.apiSettings')}
        </button>
      </nav>

      {/* 引导展开:模型接入(visionrp api-panel 的就地版)*/}
      {showApi && (
        <div
          className="relative z-[1] mt-5 w-[420px] max-w-[90vw] rounded-xl border p-5"
          style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)', backdropFilter: 'blur(8px)' }}
        >
          <div className="flex gap-1 mb-3">
            {(
              [
                ['model', t('welcome.modelAccess')],
                ['image', t('welcome.imageTab')],
              ] as ['model' | 'image', string][]
            ).map(([k, label]) => (
              <button key={k} onClick={() => setApiTab(k)}
                className="text-[12.5px] rounded-lg px-3 py-1 cursor-pointer border-0"
                style={
                  apiTab === k
                    ? { background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                    : { background: 'transparent', color: 'var(--lc-dim)' }
                }>
                {label}
              </button>
            ))}
          </div>
          {apiTab === 'model' && (
            <>
              <p className="mt-0 mb-4 text-[12px]" style={{ color: 'var(--lc-faint)' }}>
                {t('welcome.modelAccessHint')}
              </p>
              <ModelAccessPanel onState={setAccess} />
            </>
          )}
          {apiTab === 'image' && (
            <div className="flex flex-col gap-2.5">
              <p className="m-0 text-[12px]" style={{ color: 'var(--lc-faint)' }}>
                {t('welcome.imageDesc')}
              </p>
              <div className="flex gap-1.5">
                {(
                  [
                    ['', t('lib.imgOff')],
                    ['comfyui', 'ComfyUI'],
                    ['openai', 'OpenAI'],
                  ] as [string, string][]
                ).map(([v, label]) => (
                  <button key={v || 'off'} onClick={() => setImgBackend(v)}
                    className="text-[12px] rounded-full px-3 py-1 cursor-pointer border"
                    style={
                      imgBackend === v
                        ? { borderColor: 'var(--lc-candle)', background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                        : { borderColor: 'var(--lc-line)', background: 'transparent', color: 'var(--lc-dim)' }
                    }>
                    {label}
                  </button>
                ))}
              </div>
              {imgBackend === 'comfyui' && (
                <input value={imgUrl} onChange={(e) => setImgUrl(e.target.value)}
                  placeholder="http://127.0.0.1:8188"
                  className="w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
                  style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
              )}
              <div className="flex items-center gap-3">
                <button
                  onClick={async () => {
                    setImgMsg('')
                    try {
                      const d = await putImageSettings({ backend: imgBackend, comfyui_url: imgUrl.trim() })
                      setImgMsg(d.configured ? t('lib.imgSaved') : t('lib.imgSavedOff'))
                    } catch (e) {
                      setImgMsg(`✗ ${e}`)
                    }
                  }}
                  className="text-[12.5px] font-semibold rounded-lg px-4 py-2 cursor-pointer border-0"
                  style={{ background: 'var(--lc-candle)', color: '#0A0A0A' }}>
                  {t('lib.save')}
                </button>
                <Link to="/local/settings" className="text-[11.5px]" style={{ color: 'var(--lc-dim)' }}>
                  {t('welcome.imageAdvanced')} →
                </Link>
                {imgMsg && (
                  <span className="text-[11px] font-mono" style={{ color: imgMsg.startsWith('✗') ? '#FF6B8A' : 'var(--lc-live)' }}>
                    {imgMsg}
                  </span>
                )}
              </div>
            </div>
          )}
          <button
            onClick={begin}
            disabled={!access.ready || busy}
            className="mt-5 w-full text-[14px] font-semibold rounded-lg px-4 py-2.5 cursor-pointer border-0"
            style={{
              background: 'var(--lc-candle)',
              color: '#0A0A0A',
              opacity: access.ready && !busy ? 1 : 0.5,
            }}
          >
            {access.needsKey ? t('welcome.saveAndBegin') : t('welcome.beginShort')}
          </button>
        </div>
      )}

      <footer
        className="absolute bottom-5 left-0 right-0 flex justify-between px-8 text-[11px] z-[1]"
        style={{ color: 'var(--lc-faint)' }}
      >
        <span>local · preview</span>
        <span>© Ludic Dynamics</span>
      </footer>
    </div>
  )
}
