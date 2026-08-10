// 「书房」门 — 管理面(连携层,local 专属):世界库 / 角色库 / 设置。
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  localEndpoint,
  deleteLocalSoul,
  deleteLocalWorld,
  hubUpload,
  listLocalSouls,
  listLocalWorlds,
  openCreateSession,
  worldExportUrl,
  type LocalSoul,
  type LocalWorld,
} from './localClient'
import { SettingsBody } from './LocalSettings'
import { useLocalT } from './i18n'

type Tab = 'worlds' | 'souls' | 'settings'

export function LocalLibrary() {
  const { t } = useLocalT()
  // ?tab=settings 直达(经典游玩页的「模型/API 设置」链接跳这里)
  const [tab, setTab] = useState<Tab>(() => {
    const q = new URLSearchParams(window.location.search).get('tab')
    return q === 'settings' || q === 'souls' ? q : 'worlds'
  })
  return (
    <div className="pt-8">
      <div className="flex gap-1 mb-5">
        {(
          [
            ['worlds', t('lib.worlds')],
            ['souls', t('lib.souls')],
            ['settings', t('lib.settings')],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className="text-[13px] rounded-lg px-4 py-1.5 cursor-pointer border"
            style={
              tab === k
                ? { background: 'var(--lc-candle-soft)', borderColor: '#34E87960', color: 'var(--lc-candle)' }
                : { background: 'transparent', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }
            }
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'worlds' && <WorldsTab />}
      {tab === 'souls' && <SoulsTab />}
      {tab === 'settings' && <SettingsBody />}
    </div>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl border p-3.5 flex items-center gap-3"
      style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
    >
      {children}
    </div>
  )
}

const dangerBtn = {
  borderColor: 'var(--lc-line)',
  color: '#FF6B8A',
  background: 'transparent',
} as const

function WorldsTab() {
  const { t } = useLocalT()
  const [owned, setOwned] = useState<LocalWorld[]>([])
  const nav = useNavigate()
  const load = () => listLocalWorlds().then((d) => setOwned(d.worlds)).catch(() => {})
  useEffect(() => {
    load()
  }, [])

  async function remove(id: string) {
    if (!confirm(t('lib.deleteWorldConfirm', { id }))) return
    await deleteLocalWorld(id).catch((e) => alert(String(e)))
    load()
  }
  async function edit(id: string) {
    await openCreateSession({ world_id: id })
    nav('/local/create/studio')
  }

  return (
    <div className="flex flex-col gap-2">
      {owned.length === 0 && (
        <p className="text-[13px]" style={{ color: 'var(--lc-faint)' }}>
          {t('lib.noWorlds')}
        </p>
      )}
      {owned.map((w) => (
        <Row key={w.id}>
          <div className="min-w-0 flex-1">
            <span className="text-[14px] font-semibold">{w.display_name || w.name || w.id}</span>
            <span className="ml-3 text-[11px] font-mono" style={{ color: 'var(--lc-faint)' }}>
              {w.id} · {w.origin === 'created' ? t('lib.localCreated') : t('lib.hubDownload')}
            </span>
          </div>
          <button onClick={() => edit(w.id)} className="text-[12.5px] rounded-lg px-3.5 py-1.5 cursor-pointer border" style={{ borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)', background: 'transparent' }}>
            {t('lib.editBtn')}
          </button>
          <a
            href={worldExportUrl(w.id)}
            download
            className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border no-underline"
            style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
          >
            {t('lib.export')}
          </a>
          <HubUploadButton kind="worlds" id={w.id} label={w.display_name || w.name || w.id} />
          <button onClick={() => remove(w.id)} className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border" style={dangerBtn}>
            {t('lib.delete')}
          </button>
        </Row>
      ))}
    </div>
  )
}

function SoulsTab() {
  const { t } = useLocalT()
  const [souls, setSouls] = useState<LocalSoul[]>([])
  const nav = useNavigate()
  const load = () => listLocalSouls().then((d) => setSouls(d.souls)).catch(() => {})
  useEffect(() => {
    load()
  }, [])

  async function remove(dirName: string, label: string) {
    if (!confirm(t('lib.deleteSoulConfirm', { label }))) return
    await deleteLocalSoul(dirName).catch((e) => alert(String(e)))
    load()
  }

  return (
    <div className="flex flex-col gap-2">
      {souls.length === 0 && (
        <p className="text-[13px]" style={{ color: 'var(--lc-faint)' }}>
          {t('lib.noSouls')}
        </p>
      )}
      {souls.map((s) => (
        <Row key={s.dir_name || s.sid}>
          <SoulAvatar dir={s.dir_name || s.sid} />
          <div className="min-w-0 flex-1">
            <span className="text-[14px] font-semibold">{s.display_name || s.name || s.sid}</span>
            <span className="ml-3 text-[11px] font-mono" style={{ color: 'var(--lc-faint)' }}>
              {s.dir_name}
            </span>
          </div>
          <PortraitUpload dir={s.dir_name || s.sid} />
          <button
            onClick={() => nav(`/local/create/soul?dir=${encodeURIComponent(s.dir_name || s.sid)}`)}
            className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
            style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
          >
            {t('soul.editEntry')}
          </button>
          <button
            onClick={() => nav(`/local/preplay/soul-talk?cast=${encodeURIComponent(s.dir_name || s.sid)}`)}
            className="text-[12.5px] rounded-lg px-3.5 py-1.5 cursor-pointer border"
            style={{ borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)', background: 'transparent' }}
          >
            {t('lib.talk')}
          </button>
          <HubUploadButton kind="souls" id={s.dir_name || s.sid} label={s.display_name || s.name || s.sid} />
          <button
            onClick={() => remove(s.dir_name || s.sid, s.display_name || s.sid)}
            className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
            style={dangerBtn}
          >
            {t('lib.delete')}
          </button>
        </Row>
      ))}
    </div>
  )
}

// B9:上传到 Hub —— 点开要 token(worldlines.gg/account),记在 localStorage。
function HubUploadButton({ kind, id, label }: { kind: 'worlds' | 'souls'; id: string; label: string }) {
  const { t } = useLocalT()
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function upload() {
    let token = ''
    try {
      token = localStorage.getItem('wl-hub-token') || ''
    } catch {
      /* storage off */
    }
    if (!token) {
      token = prompt(t('lib.hubTokenPrompt'))?.trim() || ''
      if (!token) return
      try {
        localStorage.setItem('wl-hub-token', token)
      } catch {
        /* storage off */
      }
    }
    if (!confirm(t('lib.uploadConfirm', { label }))) return
    setBusy(true)
    setMsg(t('lib.uploading'))
    try {
      const d = await hubUpload({ kind, id, token })
      const e = d.entry as { slug?: string; version?: string } | undefined
      setMsg(`✓ ${e?.slug}@${e?.version}`)
    } catch (e) {
      setMsg(`✗ ${String(e).slice(0, 60)}`)
      // token 失效的话清掉,下次重新要
      if (String(e).includes('token') || String(e).includes('401')) {
        try {
          localStorage.removeItem('wl-hub-token')
        } catch {
          /* storage off */
        }
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        onClick={upload}
        disabled={busy}
        className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
        style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent', opacity: busy ? 0.5 : 1 }}
      >
        {t('lib.hubBtn')}
      </button>
      {msg && (
        <span className="text-[10.5px] font-mono" style={{ color: msg.startsWith('✓') ? 'var(--lc-live)' : '#FF6B8A' }}>
          {msg}
        </span>
      )}
    </span>
  )
}

// 角色立绘缩略(assets/portrait.png;没有就首字占位)
function SoulAvatar({ dir }: { dir: string }) {
  const [ok, setOk] = useState(true)
  const [ver, setVer] = useState(0)
  useEffect(() => {
    const on = () => {
      setOk(true)
      setVer((v) => v + 1)
    }
    window.addEventListener('wl-portrait-updated', on)
    return () => window.removeEventListener('wl-portrait-updated', on)
  }, [])
  return (
    <div
      className="flex-none rounded-lg overflow-hidden grid place-items-center"
      style={{ width: 44, height: 44, background: 'var(--lc-panel2)', border: '1px solid var(--lc-line)' }}
    >
      {ok ? (
        <img
          key={ver}
          src={`${localEndpoint()}/api/v1/local/souls/${encodeURIComponent(dir)}/portrait?v=${ver}`}
          onError={() => setOk(false)}
          alt=""
          className="w-full h-full object-cover"
        />
      ) : (
        <span className="text-[16px]" style={{ color: 'var(--lc-faint)' }}>✦</span>
      )}
    </div>
  )
}

// 档案室直接上传立绘
function PortraitUpload({ dir }: { dir: string }) {
  const { t } = useLocalT()
  const ref = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={async (e) => {
          const f = e.target.files?.[0]
          if (!f) return
          setBusy(true)
          try {
            const r = await fetch(`${localEndpoint()}/api/v1/local/souls/${encodeURIComponent(dir)}/portrait`, {
              method: 'POST',
              headers: { 'Content-Type': f.type || 'image/png' },
              body: f,
            })
            if (!r.ok) throw new Error(`upload → ${r.status}`)
            window.dispatchEvent(new Event('wl-portrait-updated'))
          } catch (err) {
            alert(String(err))
          } finally {
            setBusy(false)
          }
        }}
      />
      <button
        onClick={() => ref.current?.click()}
        disabled={busy}
        className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
        style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent', opacity: busy ? 0.5 : 1 }}
        title={t('soul.portraitUpload')}
      >
        🖼
      </button>
    </>
  )
}
