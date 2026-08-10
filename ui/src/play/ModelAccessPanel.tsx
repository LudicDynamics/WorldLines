// 模型接入面板 — Welcome(首次引导)与 PrePlay(每局进场)共用。
// 职责:preset 药丸 + 缺 key 就地补 + 测连通;把当前选择通过 onState 上抛,
// 保存动作(saveProviderKey)由宿主页面在各自的「继续/进入」时机执行。
import { useEffect, useState } from 'react'
import { addCustomModel, getSettings, testProvider, type PresetInfo } from '../local/localClient'
import { useLocalT } from '../local/i18n'

export type ModelAccessState = {
  picked: PresetInfo | null
  needsKey: boolean
  key: string
  /** picked 且(不缺 key 或已填)— 宿主用它点亮「继续」 */
  ready: boolean
}

export const REMEMBER_PRESET_KEY = 'wl-local-preset'

export function ModelAccessPanel({ onState }: { onState: (s: ModelAccessState) => void }) {
  const { t } = useLocalT()
  const [presets, setPresets] = useState<PresetInfo[]>([])
  const [pick, setPick] = useState<string>(() => {
    try {
      return localStorage.getItem(REMEMBER_PRESET_KEY) || ''
    } catch {
      return ''
    }
  })
  const [key, setKey] = useState('')
  const [testMsg, setTestMsg] = useState('')
  const [loadErr, setLoadErr] = useState('')
  // 首访漏斗里的「＋ 自定义 API 端点」——与 /local/settings 同一个 SillyTavern 式表单,
  // 复用 addCustomModel;保存后新 provider 作为可选 pill 就地出现并自动选中。
  const [showCustom, setShowCustom] = useState(false)
  const [custom, setCustom] = useState({ id: '', base_url: 'http://localhost:11434/v1', model: '', api_key: '' })
  const [customMsg, setCustomMsg] = useState('')
  const [customBusy, setCustomBusy] = useState(false)
  const setC = (k: 'id' | 'base_url' | 'model' | 'api_key', v: string) => setCustom((c) => ({ ...c, [k]: v }))

  async function saveCustom(alsoTest: boolean) {
    if (!custom.id.trim() || !custom.base_url.trim() || !custom.model.trim()) {
      setCustomMsg(`✗ ${t('lib.customNeedFields')}`)
      return
    }
    setCustomBusy(true)
    setCustomMsg('')
    try {
      const d = await addCustomModel({
        id: custom.id.trim(),
        base_url: custom.base_url.trim(),
        model: custom.model.trim(),
        api_key: custom.api_key.trim() || undefined,
      })
      setPresets(d.presets)
      setPick(d.id) // 新 provider 就地选中
      setKey('')
      if (alsoTest) {
        setCustomMsg(t('ma.testing'))
        const r = await testProvider(d.id)
        setCustomMsg(
          r.ok
            ? t('ma.connected', { ms: String((r as { latency_ms?: number }).latency_ms ?? '?') })
            : t('ma.failed', { err: String((r as { error?: string }).error ?? t('ma.failDefault')) }),
        )
      } else {
        setCustomMsg(t('lib.customAdded', { id: d.id }))
        setShowCustom(false)
      }
      setCustom({ id: '', base_url: 'http://localhost:11434/v1', model: '', api_key: '' })
    } catch (e) {
      setCustomMsg(`✗ ${e}`)
    } finally {
      setCustomBusy(false)
    }
  }

  useEffect(() => {
    // 一次性 fetch 失败会让面板永远卡"读取中"(引擎慢启动/短暂重启都中招)
    // —— 改成失败报具体错误 + 每 3 秒自动重连,直到拿到 presets。
    let stop = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const pull = () => {
      getSettings()
        .then((d) => {
          if (stop) return
          setPresets(d.presets)
          setLoadErr('')
          // 没记忆时默认选第一个可用的
          setPick((cur) => cur || d.presets.find((p) => p.available)?.id || '')
        })
        .catch((e) => {
          if (stop) return
          setLoadErr(String(e))
          timer = setTimeout(pull, 3000)
        })
    }
    pull()
    return () => {
      stop = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  const picked = presets.find((p) => p.id === pick) ?? null
  const needsKey = picked ? !picked.available : false

  useEffect(() => {
    onState({
      picked,
      needsKey,
      key,
      ready: !!picked && (!needsKey || key.trim().length > 0),
    })
    // onState 是宿主的 setState 包装,依赖它本身会造环
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pick, key, presets])

  async function test() {
    if (!picked) return
    setTestMsg(t('ma.testing'))
    try {
      const d = await testProvider(picked.id)
      setTestMsg(d.ok ? t('ma.connected', { ms: String(d.latency_ms ?? '?') }) : t('ma.failed', { err: String(d.error ?? t('ma.failDefault')) }))
    } catch (e) {
      setTestMsg(t('ma.failed', { err: String(e) }))
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => {
              setPick(p.id)
              setKey('')
              setTestMsg('')
            }}
            className="text-[12.5px] rounded-full px-3.5 py-1.5 cursor-pointer border"
            style={
              pick === p.id
                ? { background: 'var(--lc-candle-soft)', borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)' }
                : { background: 'transparent', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }
            }
          >
            {p.display}
          </button>
        ))}
        {/* ＋ 自定义 API 端点 — 与 TUI 的 __add_custom__ pill 同位,点开就地展开表单 */}
        <button
          onClick={() => {
            setShowCustom((v) => !v)
            setCustomMsg('')
          }}
          className="text-[12.5px] rounded-full px-3.5 py-1.5 cursor-pointer border border-dashed"
          style={
            showCustom
              ? { background: 'var(--lc-candle-soft)', borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)' }
              : { background: 'transparent', borderColor: 'var(--lc-line)', color: 'var(--lc-dim)' }
          }
        >
          {t('ma.addCustom')}
        </button>
        {presets.length === 0 && (
          <span className="text-[12px]" style={{ color: loadErr ? '#FF6B8A' : 'var(--lc-faint)' }}>
            {loadErr ? t('ma.loadFailed', { err: loadErr.slice(0, 120) }) : t('ma.readingProviders')}
          </span>
        )}
      </div>
      {showCustom && (
        <div className="mt-3 rounded-xl border p-3" style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}>
          <div className="text-[12px] font-semibold" style={{ color: 'var(--lc-text)' }}>{t('lib.customTitle')}</div>
          {/* SillyTavern 式:Base URL → API Key(可选)→ Model → 名称 */}
          <input
            value={custom.base_url}
            onChange={(e) => setC('base_url', e.target.value)}
            placeholder="http://localhost:11434/v1"
            className="mt-2 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          />
          <input
            value={custom.api_key}
            onChange={(e) => setC('api_key', e.target.value)}
            type="password"
            placeholder="sk-… (Ollama/LM Studio 可留空)"
            className="mt-2 w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          />
          <div className="mt-2 grid grid-cols-2 gap-2">
            <input
              value={custom.model}
              onChange={(e) => setC('model', e.target.value)}
              placeholder="qwen2.5:14b"
              className="w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
              style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
            />
            <input
              value={custom.id}
              onChange={(e) => setC('id', e.target.value)}
              placeholder="my-llama"
              className="w-full rounded-lg border px-3 py-2 text-[12.5px] font-mono outline-none"
              style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
            />
          </div>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <button
              onClick={() => saveCustom(false)}
              disabled={customBusy}
              className="text-[12px] rounded-lg px-3.5 py-1.5 cursor-pointer border-0"
              style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)', opacity: customBusy ? 0.5 : 1 }}
            >
              {t('lib.customSave')}
            </button>
            <button
              onClick={() => saveCustom(true)}
              disabled={customBusy}
              className="text-[12px] rounded-lg px-3.5 py-1.5 cursor-pointer border"
              style={{ background: 'transparent', color: 'var(--lc-dim)', borderColor: 'var(--lc-line)', opacity: customBusy ? 0.5 : 1 }}
            >
              {t('lib.customTest')}
            </button>
            {customMsg && (
              <span className="text-[11.5px] font-mono" style={{ color: customMsg.startsWith('✗') ? '#FF6B8A' : 'var(--lc-live)' }}>
                {customMsg}
              </span>
            )}
          </div>
        </div>
      )}
      {needsKey && (
        <div className="mt-4">
          <div className="text-[12px] mb-1.5" style={{ color: 'var(--lc-dim)' }}>
            {t('ma.needKey')}
          </div>
          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            type="password"
            placeholder="sk-…"
            className="w-full rounded-lg border px-3 py-2 text-[13px] font-mono outline-none"
            style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
          />
        </div>
      )}
      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={test}
          disabled={!picked || needsKey}
          className="text-[12.5px] rounded-lg px-3.5 py-1.5 cursor-pointer border"
          style={{
            borderColor: 'var(--lc-line)',
            color: 'var(--lc-dim)',
            background: 'transparent',
            opacity: !picked || needsKey ? 0.5 : 1,
          }}
        >
          {t('ma.testConn')}
        </button>
        {testMsg && (
          <span
            className="text-[12px] font-mono"
            style={{ color: testMsg.startsWith('✓') ? 'var(--lc-live)' : '#FF6B8A' }}
          >
            {testMsg}
          </span>
        )}
      </div>
    </div>
  )
}
