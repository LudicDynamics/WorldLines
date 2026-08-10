// 设置 — 一级页(niko:从客户角度,凡是 API/模型入口都该通到全部设置,
// 不该埋在档案室第三个 tab)。模型条目 / 创作用 LLM / 图像生成(ComfyUI
// 高级)全在这里;所有「API 设置」触点(导航/门面/PrePlay/游玩 ⚙)指向本页。
import { useEffect, useState } from 'react'
import {
  addCustomModel,
  deleteSettingsEntry,
  getSettings,
  putImageSettings,
  saveProviderKey,
  setCreateProvider,
  testAllProviders,
  testProvider,
  type ImageSettings,
  type PresetInfo,
} from './localClient'
import { LANGS, LANG_LABEL, useLocalT } from './i18n'

const dangerBtn = {
  borderColor: 'var(--lc-line)',
  color: '#FF6B8A',
  background: 'transparent',
} as const

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

export function LocalSettings() {
  const { t, lang, setLang } = useLocalT()
  return (
    <div className="pt-8">
      <h1 className="m-0 mb-5 text-[20px] font-bold">⚙ {t('nav.settings')}</h1>
      {/* 语言(niko:默认进来是中文不合理 —— 默认跟引擎 locale,在这里可改) */}
      <div className="rounded-xl border p-4 mb-3 max-w-[640px]" style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}>
        <div className="text-[13.5px] font-semibold">{t('settings.language')}</div>
        <p className="mt-1 text-[12px]" style={{ color: 'var(--lc-faint)' }}>{t('settings.languageDesc')}</p>
        <div className="mt-2 flex gap-1.5">
          {LANGS.map((l) => (
            <button key={l} onClick={() => setLang(l)}
              className="text-[12.5px] rounded-lg px-3.5 py-1.5 cursor-pointer border"
              style={
                l === lang
                  ? { borderColor: 'var(--lc-candle)', background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                  : { borderColor: 'var(--lc-line)', background: 'transparent', color: 'var(--lc-dim)' }
              }>
              {LANG_LABEL[l]}
            </button>
          ))}
        </div>
      </div>
      <SettingsBody />
    </div>
  )
}

export function SettingsBody() {
  const { t } = useLocalT()
  const [presets, setPresets] = useState<PresetInfo[]>([])
  const [editing, setEditing] = useState('')
  const [key, setKey] = useState('')
  const [testResult, setTestResult] = useState<Record<string, string>>({})
  const [createProv, setCreateProv] = useState<string>('')
  const [image, setImage] = useState<ImageSettings | null>(null)
  const [imgForm, setImgForm] = useState<Record<string, string>>({})
  const [imgAdv, setImgAdv] = useState(false)
  const [imgMsg, setImgMsg] = useState('')
  const [testingAll, setTestingAll] = useState(false)
  const [custom, setCustom] = useState({ id: '', base_url: 'http://localhost:11434/v1', model: '', api_key: '' })
  const [customMsg, setCustomMsg] = useState('')
  const [customBusy, setCustomBusy] = useState(false)

  useEffect(() => {
    getSettings()
      .then((d) => {
        setPresets(d.presets)
        setCreateProv(d.create_provider || '')
        if (d.image) {
          setImage(d.image)
          setImgForm({
            backend: d.image.backend,
            comfyui_url: d.image.comfyui_url,
            comfyui_ckpt: d.image.comfyui_ckpt,
            comfyui_workflow: d.image.comfyui_workflow,
            comfyui_input_node: d.image.comfyui_input_node,
            comfyui_neg_node: d.image.comfyui_neg_node,
            comfyui_output_node: d.image.comfyui_output_node,
            comfyui_seed_node: d.image.comfyui_seed_node,
            openai_model: d.image.openai_model,
            openai_key: '',
          })
        }
      })
      .catch(() => {})
  }, [])

  async function pickCreateProvider(pid: string) {
    setCreateProv(pid)
    try {
      await setCreateProvider(pid || null)
    } catch (e) {
      alert(String(e))
    }
  }

  async function saveImage() {
    setImgMsg('')
    try {
      const patch: Record<string, string> = { ...imgForm }
      if (!patch.openai_key) delete patch.openai_key // 只写:空 = 不动
      const d = await putImageSettings(patch)
      setImage((prev) => (prev ? { ...prev, ...imgForm, configured: d.configured } : prev))
      setImgMsg(d.configured ? t('lib.imgSaved') : t('lib.imgSavedOff'))
    } catch (e) {
      setImgMsg(`✗ ${e}`)
    }
  }
  const setImg = (k: string, v: string) => setImgForm((f) => ({ ...f, [k]: v }))

  async function testAll() {
    setTestingAll(true)
    try {
      const d = await testAllProviders()
      const next: Record<string, string> = {}
      for (const r of d.results) {
        next[r.id] = r.ok ? t('lib.connected', { ms: r.latency_ms ?? '?' }) : `✗ ${r.error ?? t('lib.failDefault')}`
      }
      setTestResult(next)
    } catch (e) {
      alert(String(e))
    } finally {
      setTestingAll(false)
    }
  }

  async function removeEntry(pid: string) {
    if (!confirm(t('lib.deleteEntryConfirm', { id: pid }))) return
    try {
      const d = await deleteSettingsEntry(pid)
      setPresets(d.presets)
    } catch (e) {
      alert(String(e))
    }
  }

  // SillyTavern「Custom (OpenAI-compatible)」parity:base_url + 可选 key + 自由填 model
  // = 一个可用 provider。保存后作为独立 pill 出现在上面列表,可测试/删除。
  // alsoTest=true 复用 testProvider(先保存再连一次,给 ✓ connected / ✗ error 反馈)。
  async function saveCustom(alsoTest: boolean) {
    if (!custom.id.trim() || !custom.base_url.trim() || !custom.model.trim()) {
      setCustomMsg(`✗ ${t('lib.customNeedFields')}`)
      return
    }
    setCustomBusy(true)
    setCustomMsg('')
    const cid = custom.id.trim()
    try {
      const d = await addCustomModel({
        id: cid,
        base_url: custom.base_url.trim(),
        model: custom.model.trim(),
        api_key: custom.api_key.trim() || undefined,
      })
      setPresets(d.presets)
      if (alsoTest) {
        setCustomMsg(t('lib.testing'))
        const r = await testProvider(d.id)
        const msg = r.ok
          ? t('lib.connected', { ms: String((r as { latency_ms?: number }).latency_ms ?? '?') })
          : `✗ ${(r as { error?: string }).error ?? t('lib.failDefault')}`
        setTestResult((tr) => ({ ...tr, [d.id]: msg }))
        setCustomMsg(msg)
      } else {
        setCustomMsg(t('lib.customAdded', { id: d.id }))
      }
      setCustom({ id: '', base_url: 'http://localhost:11434/v1', model: '', api_key: '' })
    } catch (e) {
      setCustomMsg(`✗ ${e}`)
    } finally {
      setCustomBusy(false)
    }
  }
  const setC = (k: 'id' | 'base_url' | 'model' | 'api_key', v: string) => setCustom((c) => ({ ...c, [k]: v }))

  async function save(pid: string) {
    if (!key.trim()) return
    try {
      const d = await saveProviderKey(pid, key.trim())
      setPresets(d.presets)
      setEditing('')
      setKey('')
    } catch (e) {
      alert(String(e))
    }
  }

  async function test(pid: string) {
    setTestResult((r) => ({ ...r, [pid]: t('lib.testing') }))
    try {
      const d = await testProvider(pid)
      setTestResult((r) => ({
        ...r,
        [pid]: d.ok ? t('lib.connected', { ms: String(d.latency_ms ?? '?') }) : `✗ ${d.error ?? t('lib.failDefault')}`,
      }))
    } catch (e) {
      setTestResult((r) => ({ ...r, [pid]: `✗ ${e}` }))
    }
  }

  return (
    <div className="flex flex-col gap-2 max-w-[640px]">
      <p className="text-[12.5px] mb-1" style={{ color: 'var(--lc-dim)' }}>
        {t('lib.settingsIntroPre')} <code className="font-mono text-[11px]">~/.neonrp/config.json</code>{t('lib.settingsIntroPost')}
      </p>
      {presets.map((p) => (
        <Row key={p.id}>
          <div className="min-w-0 flex-1">
            <span className="text-[13.5px]">{p.display}</span>
            {testResult[p.id] && (
              <span className="ml-3 text-[11.5px] font-mono" style={{ color: testResult[p.id].startsWith('✓') ? 'var(--lc-live)' : '#FF6B8A' }}>
                {testResult[p.id]}
              </span>
            )}
          </div>
          {editing === p.id ? (
            <>
              <input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={t('lib.pasteKey')}
                type="password"
                className="w-[200px] rounded-lg border px-2.5 py-1.5 text-[12px] font-mono outline-none"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
              />
              <button onClick={() => save(p.id)} className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border-0" style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}>
                {t('lib.save')}
              </button>
              <button onClick={() => setEditing('')} className="text-[12.5px] rounded-lg px-2.5 py-1.5 cursor-pointer border" style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}>
                {t('lib.cancel')}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => {
                  setEditing(p.id)
                  setKey('')
                }}
                className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border"
                style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
              >
                {p.available ? t('lib.changeKey') : t('lib.setKey')}
              </button>
              <button onClick={() => test(p.id)} className="text-[12.5px] rounded-lg px-3 py-1.5 cursor-pointer border" style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}>
                {t('lib.test')}
              </button>
              {p.from_user_config && (
                <button onClick={() => removeEntry(p.id)} className="text-[12.5px] rounded-lg px-2.5 py-1.5 cursor-pointer border" style={dangerBtn}>
                  {t('lib.del')}
                </button>
              )}
            </>
          )}
        </Row>
      ))}

      <div className="mt-1">
        <button
          onClick={testAll}
          disabled={testingAll}
          className="text-[12.5px] rounded-lg px-3.5 py-1.5 cursor-pointer border"
          style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent', opacity: testingAll ? 0.5 : 1 }}
        >
          {testingAll ? t('lib.testingAll') : t('lib.testAll')}
        </button>
      </div>

      {/* 添加自定义 API 端点 — 自建/本地 LLM(OpenAI 兼容:base_url + 模型名 + 可选 key)。
          保存后作为可选 provider 出现在上面列表里,可删除。对齐 TUI settings「+ 自定义」。 */}
      <div className="rounded-xl border p-4 mt-3" style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}>
        <div className="text-[13.5px] font-semibold">{t('lib.customTitle')}</div>
        <p className="mt-1 text-[12px]" style={{ color: 'var(--lc-faint)' }}>{t('lib.customDesc')}</p>
        {/* SillyTavern「Custom (OpenAI-compatible)」字段顺序:Base URL → API Key → Model → 名称 */}
        <label className="mt-3 block text-[11px]" style={{ color: 'var(--lc-dim)' }}>
          {t('lib.customBaseUrl')}
          <input value={custom.base_url} onChange={(e) => setC('base_url', e.target.value)} placeholder="http://localhost:11434/v1"
            className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
        </label>
        <label className="mt-2 block text-[11px]" style={{ color: 'var(--lc-dim)' }}>
          {t('lib.customKey')}
          <input value={custom.api_key} onChange={(e) => setC('api_key', e.target.value)} type="password" placeholder="sk-… (Ollama/LM Studio 可留空)"
            className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
        </label>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
            {t('lib.customModel')}
            <input value={custom.model} onChange={(e) => setC('model', e.target.value)} placeholder="qwen2.5:14b"
              className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
              style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
          </label>
          <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
            {t('lib.customId')}
            <input value={custom.id} onChange={(e) => setC('id', e.target.value)} placeholder="my-llama"
              className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
              style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <button onClick={() => saveCustom(false)} disabled={customBusy}
            className="text-[12.5px] rounded-lg px-4 py-2 cursor-pointer border-0"
            style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)', opacity: customBusy ? 0.5 : 1 }}>
            {t('lib.customSave')}
          </button>
          <button onClick={() => saveCustom(true)} disabled={customBusy}
            className="text-[12.5px] rounded-lg px-4 py-2 cursor-pointer"
            style={{ background: 'transparent', color: 'var(--lc-text)', border: '1px solid var(--lc-line)', opacity: customBusy ? 0.5 : 1 }}>
            {t('lib.customTest')}
          </button>
          {customMsg && (
            <span className="text-[11.5px] font-mono" style={{ color: customMsg.startsWith('✗') ? '#FF6B8A' : 'var(--lc-live)' }}>
              {customMsg}
            </span>
          )}
        </div>
      </div>

      {/* creation LLM(B7)— 创作/导入用的模型,独立于游玩 preset */}
      <div className="rounded-xl border p-4 mt-3" style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}>
        <div className="text-[13.5px] font-semibold">{t('lib.createLLM')}</div>
        <p className="mt-1 text-[12px]" style={{ color: 'var(--lc-faint)' }}>
          {t('lib.createLLMDesc')}
        </p>
        <select
          value={createProv}
          onChange={(e) => pickCreateProvider(e.target.value)}
          className="mt-2 w-full rounded-lg border px-3 py-2 text-[13px]"
          style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
        >
          <option value="">{t('lib.autoFirst')}</option>
          {presets.filter((p) => p.available).map((p) => (
            <option key={p.id} value={p.id}>{p.display}</option>
          ))}
        </select>
      </div>

      {/* 图像生成 — 完整配置面板(对齐 TUI settings 图像菜单) */}
      <div className="rounded-xl border p-4" style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}>
        <div className="text-[13.5px] font-semibold">
          {t('lib.imageGen')}
          {image?.configured && (
            <span className="ml-2 text-[11px] font-mono" style={{ color: 'var(--lc-live)' }}>{t('lib.configured')}</span>
          )}
        </div>
        <p className="mt-1 text-[12px]" style={{ color: 'var(--lc-faint)' }}>
          {t('lib.imageGenDesc')}
        </p>
        {/* 后端选择 */}
        <div className="mt-3 flex gap-1.5">
          {(
            [
              ['', t('lib.imgOff')],
              ['comfyui', 'ComfyUI'],
              ['openai', 'OpenAI'],
            ] as [string, string][]
          ).map(([v, label]) => (
            <button key={v || 'off'} onClick={() => setImg('backend', v)}
              className="text-[12px] rounded-full px-3 py-1 cursor-pointer border"
              style={
                (imgForm.backend || '') === v
                  ? { borderColor: 'var(--lc-candle)', background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                  : { borderColor: 'var(--lc-line)', background: 'transparent', color: 'var(--lc-dim)' }
              }>
              {label}
            </button>
          ))}
        </div>
        {imgForm.backend === 'comfyui' && (
          <div className="mt-3 flex flex-col gap-2">
            <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
              URL
              <input value={imgForm.comfyui_url || ''} onChange={(e) => setImg('comfyui_url', e.target.value)}
                placeholder="http://127.0.0.1:8188"
                className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
            </label>
            <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
              ckpt
              <input value={imgForm.comfyui_ckpt || ''} onChange={(e) => setImg('comfyui_ckpt', e.target.value)}
                placeholder="animagineXL31.safetensors"
                className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
            </label>
            <button onClick={() => setImgAdv((v) => !v)}
              className="self-start text-[11.5px] cursor-pointer border-0 bg-transparent px-0"
              style={{ color: 'var(--lc-candle)' }}>
              {imgAdv ? '▾' : '▸'} {t('lib.imgAdvanced')}
            </button>
            {imgAdv && (
              <div className="flex flex-col gap-2 rounded-lg border p-3" style={{ borderColor: 'var(--lc-line)' }}>
                <p className="m-0 text-[11px]" style={{ color: 'var(--lc-faint)' }}>{t('lib.imgAdvancedDesc')}</p>
                <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
                  workflow(API JSON 路径或内联;{t('lib.imgEmptyDefault')})
                  <textarea value={imgForm.comfyui_workflow || ''} onChange={(e) => setImg('comfyui_workflow', e.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded-lg border px-3 py-2 text-[11.5px] font-mono outline-none resize-y"
                    style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {(
                    [
                      ['comfyui_input_node', 'input node'],
                      ['comfyui_neg_node', 'negative node'],
                      ['comfyui_output_node', 'output node'],
                      ['comfyui_seed_node', 'seed node'],
                    ] as [string, string][]
                  ).map(([k, label]) => (
                    <label key={k} className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
                      {label}
                      <input value={imgForm[k] || ''} onChange={(e) => setImg(k, e.target.value)}
                        className="mt-1 w-full rounded-lg border px-2.5 py-1.5 text-[11.5px] font-mono outline-none"
                        style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {imgForm.backend === 'openai' && (
          <div className="mt-3 flex flex-col gap-2">
            <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
              API key{image?.openai_key_set ? `(${t('lib.imgKeySet')})` : ''}
              <input value={imgForm.openai_key || ''} onChange={(e) => setImg('openai_key', e.target.value)}
                type="password" placeholder="sk-…"
                className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
            </label>
            <label className="text-[11px]" style={{ color: 'var(--lc-dim)' }}>
              model
              <input value={imgForm.openai_model || ''} onChange={(e) => setImg('openai_model', e.target.value)}
                placeholder="gpt-image-1"
                className="mt-1 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }} />
            </label>
          </div>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button onClick={saveImage}
            className="text-[12.5px] rounded-lg px-4 py-2 cursor-pointer border-0"
            style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}>
            {t('lib.save')}
          </button>
          {imgMsg && (
            <span className="text-[11.5px] font-mono" style={{ color: imgMsg.startsWith('✗') ? '#FF6B8A' : 'var(--lc-live)' }}>
              {imgMsg}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

