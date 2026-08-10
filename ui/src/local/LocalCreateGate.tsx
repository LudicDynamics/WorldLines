// 「创作」门 — 四入口(共识:独立大门;B1/B2 落地后升级):
//   新的世界(白模板→对话工坊) / 新的角色(种子→soul) /
//   修改现有世界(同一工坊) / 导入(酒馆卡→soul、世界 zip、lore 文本)。
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  importCardToStudio,
  importWorldZip,
  listLocalWorlds,
  openCreateSession,
  type LocalWorld,
} from './localClient'
import { useLocalT } from './i18n'

export function LocalCreateGate() {
  const { t } = useLocalT()
  const [name, setName] = useState('')
  const [owned, setOwned] = useState<LocalWorld[]>([])
  const [pick, setPick] = useState('')
  const [busy, setBusy] = useState('')
  // 新的角色(B1)
  const [soulName, setSoulName] = useState('')
  const [soulSeed, setSoulSeed] = useState('')
  // 导入(B2 → 新导入 UX:卡片入工坊)
  const [importMsg, setImportMsg] = useState('')
  const [lore, setLore] = useState('')
  const cardFileRef = useRef<HTMLInputElement>(null)
  const worldCardFileRef = useRef<HTMLInputElement>(null)
  const zipFileRef = useRef<HTMLInputElement>(null)
  const nav = useNavigate()

  useEffect(() => {
    listLocalWorlds().then((d) => setOwned(d.worlds)).catch(() => {})
  }, [])

  async function newWorld() {
    setBusy('new')
    try {
      await openCreateSession({ template: 'white-blank', name: name.trim() })
      nav('/local/create/studio')
    } catch (e) {
      setBusy('')
      alert(String(e))
    }
  }

  async function editWorld() {
    if (!pick) return
    setBusy('edit')
    try {
      await openCreateSession({ world_id: pick })
      nav('/local/create/studio')
    } catch (e) {
      setBusy('')
      alert(String(e))
    }
  }

  // 角色工坊(Hub 式访谈流,niko 定稿):进编辑界面实时看生成,不再一发闷罐
  function newSoul() {
    if (!soulName.trim() || busy) return
    nav(
      `/local/create/soul?name=${encodeURIComponent(soulName.trim())}&seed=${encodeURIComponent(soulSeed.trim())}`,
    )
  }

  // 新导入 UX(niko 定稿):卡片先入工坊(秒回,零 LLM),转换方式
  // (①计划-分批/②一次性/③手动)在工坊三选项面板里选 —— 不再直通库。
  async function onCardFile(file: File | null, kind: 'world' | 'soul') {
    if (!file || busy) return
    setBusy('import')
    setImportMsg(t('create.cardToStudio', { name: file.name }))
    try {
      const d = await importCardToStudio(file, kind)
      setBusy('')
      nav(
        kind === 'soul'
          ? `/local/create/soul?dir=${encodeURIComponent(d.world_id)}`
          : '/local/create/studio',
      )
    } catch (e) {
      setBusy('')
      setImportMsg(`✗ ${e}`)
    }
  }

  // 世界 zip(NeonRP 导出包,已是结构化世界)→ 入库后直接开工坊编辑
  async function onZipFile(file: File | null) {
    if (!file || busy) return
    setBusy('import')
    setImportMsg(t('create.zipImporting', { name: file.name }))
    try {
      const wid = await importWorldZip(file)
      setImportMsg(t('create.zipDone', { id: wid }))
      await openCreateSession({ world_id: wid })
      setBusy('')
      nav('/local/create/studio')
    } catch (e) {
      setBusy('')
      setImportMsg(`✗ ${e}`)
    }
  }

  // B2 lore 文本:开白模板会话,把设定作为第一条创作指令带进工坊
  async function importLore() {
    if (!lore.trim() || busy) return
    setBusy('lore')
    try {
      await openCreateSession({ template: 'white-blank', name: '' })
      try {
        sessionStorage.setItem('wl-studio-kickoff', t('create.loreKickoff', { lore: lore.trim() }))
      } catch {
        /* storage off */
      }
      nav('/local/create/studio')
    } catch (e) {
      setBusy('')
      alert(String(e))
    }
  }

  const card = 'rounded-xl border p-6'
  const cardStyle = { background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }
  const h = { fontWeight: 700 }
  const input =
    'w-full rounded-lg border px-3 py-2 text-[13px] outline-none'
  const inputStyle = {
    background: 'var(--lc-panel2)',
    borderColor: 'var(--lc-line)',
    color: 'var(--lc-text)',
  }

  return (
    <div className="pt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* 新的世界 */}
      <div className={card} style={cardStyle}>
        <h2 className="m-0 text-[17px] font-semibold" style={h}>{t('create.newWorld')}</h2>
        <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
          {t('create.newWorldDesc')}
        </p>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('create.worldNamePh')}
          className={`mt-4 ${input}`}
          style={inputStyle}
        />
        <button
          onClick={newWorld}
          disabled={busy !== ''}
          className="mt-3 w-full text-[13px] font-semibold rounded-lg px-4 py-2.5 cursor-pointer border-0"
          style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}
        >
          {busy === 'new' ? t('create.spreadingPaper') : t('create.startCreating')}
        </button>
      </div>

      {/* 新的角色(B1) */}
      <div className={card} style={cardStyle}>
        <h2 className="m-0 text-[17px] font-semibold" style={h}>{t('create.newSoul')}</h2>
        <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
          {t('create.newSoulDesc')}
        </p>
        <input
          value={soulName}
          onChange={(e) => setSoulName(e.target.value)}
          placeholder={t('create.soulNamePh')}
          className={`mt-4 ${input}`}
          style={inputStyle}
        />
        <input
          value={soulSeed}
          onChange={(e) => setSoulSeed(e.target.value)}
          placeholder={t('create.soulSeedPh')}
          className={`mt-2 ${input}`}
          style={inputStyle}
        />
        <button
          onClick={newSoul}
          disabled={!soulName.trim() || busy !== ''}
          className="mt-3 w-full text-[13px] font-semibold rounded-lg px-4 py-2.5 cursor-pointer border-0"
          style={{
            background: 'var(--lc-candle)',
            color: 'var(--lc-on-accent)',
            opacity: soulName.trim() ? 1 : 0.5,
          }}
        >
          {busy === 'soul' ? t('create.soulForming') : t('create.genSoul')}
        </button>
      </div>

      {/* 修改现有世界 */}
      <div className={card} style={cardStyle}>
        <h2 className="m-0 text-[17px] font-semibold" style={h}>{t('create.editWorld')}</h2>
        <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
          {t('create.editWorldDesc')}
        </p>
        <select
          value={pick}
          onChange={(e) => setPick(e.target.value)}
          className={`mt-4 ${input}`}
          style={inputStyle}
        >
          <option value="">{t('create.pickWorld')}</option>
          {owned.map((w) => (
            <option key={w.id} value={w.id}>
              {w.display_name || w.name || w.id}
            </option>
          ))}
        </select>
        <button
          onClick={editWorld}
          disabled={!pick || busy !== ''}
          className="mt-3 w-full text-[13px] rounded-lg px-4 py-2.5 cursor-pointer border"
          style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)', opacity: pick ? 1 : 0.5 }}
        >
          {busy === 'edit' ? t('create.openingStudio') : t('create.openStudio')}
        </button>
        {owned.length === 0 && (
          <p className="mt-2 text-[11.5px]" style={{ color: 'var(--lc-faint)' }}>
            {t('create.noOwnedWorlds')}
          </p>
        )}
      </div>

      {/* 导入(B2) */}
      <div className={card} style={cardStyle}>
        <h2 className="m-0 text-[17px] font-semibold" style={h}>{t('create.import')}</h2>
        <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
          {t('create.importDesc')}
        </p>
        <input
          ref={cardFileRef}
          type="file"
          accept=".png,.json"
          className="hidden"
          onChange={(e) => onCardFile(e.target.files?.[0] ?? null, 'soul')}
        />
        <input
          ref={worldCardFileRef}
          type="file"
          accept=".png,.json"
          className="hidden"
          onChange={(e) => onCardFile(e.target.files?.[0] ?? null, 'world')}
        />
        <input
          ref={zipFileRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => onZipFile(e.target.files?.[0] ?? null)}
        />
        <div className="mt-4 flex gap-2">
          <button
            onClick={() => cardFileRef.current?.click()}
            disabled={busy !== ''}
            className="flex-1 text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          >
            {t('create.cardBtn')}
          </button>
          <button
            onClick={() => worldCardFileRef.current?.click()}
            disabled={busy !== ''}
            className="flex-1 text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          >
            {t('create.worldCardBtn')}
          </button>
          <button
            onClick={() => zipFileRef.current?.click()}
            disabled={busy !== ''}
            className="flex-1 text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          >
            {t('create.zipBtn')}
          </button>
        </div>
        <textarea
          value={lore}
          onChange={(e) => setLore(e.target.value)}
          placeholder={t('create.lorePh')}
          rows={3}
          className={`mt-2 ${input} resize-none`}
          style={inputStyle}
        />
        <button
          onClick={importLore}
          disabled={!lore.trim() || busy !== ''}
          className="mt-2 w-full text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
          style={{
            background: 'var(--lc-panel2)',
            borderColor: 'var(--lc-candle)',
            color: 'var(--lc-candle)',
            opacity: lore.trim() ? 1 : 0.5,
          }}
        >
          {busy === 'lore' ? t('create.enterStudio') : t('create.compileLore')}
        </button>
        {importMsg && (
          <p className="mt-2 text-[11.5px] font-mono" style={{ color: importMsg.startsWith('✗') ? '#FF6B8A' : 'var(--lc-faint)' }}>
            {importMsg}
          </p>
        )}
      </div>
    </div>
  )
}
