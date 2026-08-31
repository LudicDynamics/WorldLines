// 创作工坊 → 备团工作台(docs/STUDIO-CANVAS-PLAN.md C0/C4)。
// IA 对标 trpgmaster(niko 前作):顶部 tabs(概览/资料/世界图/剧情流程/
// 关系网络)+ 右侧常驻可收起的 agent 对话。资料 = 原三栏的树+预览;
// 画布 = StudioCanvas(map 写世界文件,story/relation 写 STUDIO_HOME 副产物)。
// AI 协同:起草 = agent 在回复里输出画布 JSON → 前端解析 → PUT 校验落盘;
// 落地 = 把 flow 塞进预置指令,agent 直写世界文件(quests/钩子)。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  localEndpoint,
  getEditTree,
  getImportStatus,
  playtestEditWorld,
  readEditFile,
  sendEditMessage,
  type EditEvent,
  type ImportStatus,
  type TreeFile,
} from './localClient'
import { ImportOptionsPanel, ImportProgressPin } from './ImportOptionsPanel'
import { StudioCanvas } from './StudioCanvas'
import { buildTree, TreeView } from './fileTree'
import { ModelAccessPanel, type ModelAccessState } from '../play/ModelAccessPanel'
import { renameEditWorld, saveProviderKey, setEditLlm } from './localClient'
import { getCanvas, putCanvas, type CanvasKind, type CanvasState } from './canvasData'
import { ReviewSubmit } from './ReviewSubmit'
import { useLocalT } from './i18n'

type ChatItem =
  | { role: 'user'; text: string }
  | { role: 'assistant'; text: string; streaming?: boolean }
  | { role: 'tool'; name: string; path: string; done: boolean }
  // B10 回合动作卡:done 后聚合本回合真实改动(点击文件跳预览/画布)
  | { role: 'receipt'; paths: string[] }

type Tab = 'overview' | 'files' | 'map' | 'story' | 'relation' | 'cover'

// [tab id, i18n key] — labels resolved at render via useLocalT.
const TAB_KEYS: [Tab, string][] = [
  ['overview', 'studio.tabOverview'],
  ['files', 'studio.tabFiles'],
  ['map', 'studio.tabMap'],
  ['story', 'studio.tabStory'],
  ['relation', 'studio.tabRelation'],
  ['cover', 'studio.tabCover'],
]

export function LocalStudio() {
  const { t } = useLocalT()
  const navigate = useNavigate()
  const [worldId, setWorldId] = useState('')
  const [worldName, setWorldName] = useState('')
  const [files, setFiles] = useState<TreeFile[]>([])
  const [tab, setTab] = useState<Tab>('overview')
  const [openDirs, setOpenDirs] = useState<Set<string>>(new Set(['game', 'souls']))
  const [sel, setSel] = useState('')
  const [fileText, setFileText] = useState('')
  const [chat, setChat] = useState<ChatItem[]>([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [busyPlay, setBusyPlay] = useState(false)
  const [chatOpen, setChatOpen] = useState(() => {
    try {
      return localStorage.getItem('wl-studio-chat') !== '0'
    } catch {
      return true
    }
  })
  const [canvasRefresh, setCanvasRefresh] = useState(0)
  const [nowDoing, setNowDoing] = useState('')
  const [openerDismissed, setOpenerDismissed] = useState(false)
  const [llmOpen, setLlmOpen] = useState(false)
  const [coverVer, setCoverVer] = useState(0)
  const [coverBusy, setCoverBusy] = useState(false)
  const coverUploadRef = useRef<HTMLInputElement>(null)
  const [llmAccess, setLlmAccess] = useState<ModelAccessState>({
    picked: null, needsKey: false, key: '', ready: false,
  })
  const draftingRef = useRef<'story' | 'relation' | null>(null) // 起草中:done 后解析 JSON→PUT
  const chatEnd = useRef<HTMLDivElement>(null)
  // 导入转换态(新导入 UX):有源卡未转换 → 三选项面板;①进行中 → 进度钉
  const [importSt, setImportSt] = useState<ImportStatus | null>(null)
  const [impDismissed, setImpDismissed] = useState(false)
  const impTabbed = useRef(false)

  const refreshImportStatus = useCallback(() => {
    getImportStatus()
      .then(setImportSt)
      .catch(() => setImportSt(null))
  }, [])

  useEffect(() => {
    if (!worldId) return
    try {
      setImpDismissed(localStorage.getItem(`wl-import-dismiss:${worldId}`) === '1')
    } catch {
      /* storage off */
    }
    refreshImportStatus()
  }, [worldId, refreshImportStatus])

  // 新导入的世界卡:主区先落世界图画布(niko 定稿)
  useEffect(() => {
    if (impTabbed.current || !importSt?.has_source) return
    impTabbed.current = true
    if (!importSt.plan) setTab('map')
  }, [importSt])

  function dismissImport() {
    setImpDismissed(true)
    try {
      localStorage.setItem(`wl-import-dismiss:${worldId}`, '1')
    } catch {
      /* storage off */
    }
  }

  const refreshTree = useCallback(() => {
    getEditTree()
      .then((d) => {
        setWorldId(d.world_id)
        setWorldName(d.world_name || d.world_id)
        setFiles(d.files)
      })
      .catch(() => setWorldId(''))
  }, [])

  useEffect(() => {
    refreshTree()
  }, [refreshTree])

  // 导入门的「设定文本」入口:带着 kickoff 指令进来 → 自动作为第一句发出
  const kickoffSent = useRef(false)
  useEffect(() => {
    if (!worldId || kickoffSent.current) return
    let kick = ''
    try {
      kick = sessionStorage.getItem('wl-studio-kickoff') || ''
      sessionStorage.removeItem('wl-studio-kickoff')
    } catch {
      /* storage off */
    }
    if (kick) {
      kickoffSent.current = true
      void send(kick)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worldId])

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat])

  function toggleChat() {
    setChatOpen((v) => {
      try {
        localStorage.setItem('wl-studio-chat', v ? '0' : '1')
      } catch {
        /* storage off */
      }
      return !v
    })
  }

  async function openFile(path: string) {
    setTab('files')
    setSel(path)
    setFileText(t('studio.loadingFile'))
    try {
      const d = await readEditFile(path)
      setFileText(d.content)
    } catch (e) {
      setFileText(t('studio.cantRead', { e: String(e) }))
    }
  }

  // 回执卡点击:world_map → 世界图画布;其余 → 文件预览(C4 跳转)
  function openFromReceipt(path: string) {
    if (path.endsWith('world_map.json')) {
      setTab('map')
      setCanvasRefresh((k) => k + 1)
      return
    }
    void openFile(path)
  }

  async function send(preset?: string) {
    const text = (preset ?? input).trim()
    if (!text || running) return
    setInput('')
    setRunning(true)
    const touched: string[] = []
    setChat((c) => [...c, { role: 'user', text }, { role: 'assistant', text: '', streaming: true }])
    let finalText = ''
    try {
      await sendEditMessage(text, (ev: EditEvent) => {
        if (ev.kind === 'tool_use') setNowDoing(doingPhrase(ev.name, ev.path, t))
        if (ev.kind === 'tool_result' && ev.path && !touched.includes(ev.path)) {
          touched.push(ev.path)
        }
        if (ev.kind === 'done') finalText = ev.assistant_message || ''
        setChat((c) => {
          const out = [...c]
          const last = out[out.length - 1]
          if (ev.kind === 'chunk' && last?.role === 'assistant') {
            const clean = ev.text.replace(/^\s*\[calling [^\]]*\]\s*$/gm, '')
            out[out.length - 1] = { ...last, text: (last.text + clean).replace(/\n{3,}/g, '\n\n') }
          } else if (ev.kind === 'tool_use') {
            out.splice(out.length - 1, 0, { role: 'tool', name: ev.name, path: ev.path, done: false })
          } else if (ev.kind === 'tool_result') {
            for (let i = out.length - 1; i >= 0; i--) {
              const it = out[i]
              if (it.role === 'tool' && !it.done && it.name === ev.name) {
                out[i] = { ...it, done: true }
                break
              }
            }
          } else if (ev.kind === 'done' && last?.role === 'assistant') {
            out[out.length - 1] = {
              role: 'assistant',
              text: ev.assistant_message || last.text || t('studio.done'),
            }
            if (touched.length) out.push({ role: 'receipt', paths: [...touched] })
          } else if (ev.kind === 'error' && last?.role === 'assistant') {
            out[out.length - 1] = { role: 'assistant', text: `⚠ ${ev.error}` }
          }
          return out
        })
      })
    } catch (e) {
      setChat((c) => [...c, { role: 'assistant', text: `⚠ ${e}` }])
    } finally {
      setRunning(false)
      setNowDoing('')
      refreshTree()
      refreshImportStatus() // ① 每批结束 plan.json 变化 → 进度钉跟上
      if (sel) void readEditFile(sel).then((d) => setFileText(d.content)).catch(() => {})
      // C4:起草回合 → 从回复里解析画布 JSON,过服务端校验落进 studio
      if (draftingRef.current) {
        const kind = draftingRef.current
        draftingRef.current = null
        const parsed = kind === 'story' ? extractCanvasJson(finalText) : extractRelationsJson(finalText)
        if (parsed) {
          try {
            await putCanvas(kind, parsed)
            setTab(kind)
          } catch (e) {
            setChat((c) => [...c, { role: 'assistant', text: t('studio.draftInvalid', { e: String(e) }) }])
          }
        } else {
          setChat((c) => [...c, { role: 'assistant', text: t('studio.noDraftJson') }])
        }
      }
      // 画布 tab 激活时,agent 可能改了 world_map → refetch
      setCanvasRefresh((k) => k + 1)
    }
  }

  // 关系起草:agent 从人设/故事推断关系(输出 JSON,校验落 studio)
  function draftRelations() {
    draftingRef.current = 'relation'
    setChatOpen(true)
    void send(t('studio.draftRelationsPrompt'))
  }

  // C4 起草:agent 输出 JSON(studio 在沙箱外,不能让它直写)
  function draftStory() {
    draftingRef.current = 'story'
    void send(t('studio.draftPrompt'))
  }

  // C4 落地:flow → 真实游戏内容(目标都在沙箱内,agentic 直写)
  async function groundStory() {
    try {
      const flow = await getCanvas<CanvasState>('story')
      if (!flow.nodes.length) return
      void send(
        t('studio.groundPrompt', {
          json: JSON.stringify({ nodes: flow.nodes, edges: flow.edges }, null, 1),
        }),
      )
    } catch (e) {
      alert(String(e))
    }
  }

  async function playtest() {
    setBusyPlay(true)
    try {
      await playtestEditWorld()
      // 客户端跳转,避免整页 reload 的白屏一瞬(见 LocalPrePlay 同款修复);
      // playtest 已把会话切到试玩 run → PlayStage 挂载即进唤醒 loading。
      navigate('/local/stage')
    } catch (e) {
      setBusyPlay(false)
      alert(String(e))
    }
  }

  // 概览计数
  const counts = useMemo(() => {
    const loc = files.filter((f) => /game\/(location|locations|towns)\//.test(f.path)).length
    const npc = files.filter(
      (f) => /game\/(npc|character)\//.test(f.path) || f.path.endsWith('npcs.json'),
    ).length
    const souls = new Set(
      files.filter((f) => f.path.startsWith('souls/')).map((f) => f.path.split('/')[1]),
    ).size
    const quests = files.filter((f) => f.path.endsWith('quests.json')).length
    return { files: files.length, loc, npc, souls, quests }
  }, [files])

  // 三分区(niko:世界的 Soul 与 NPC 必须分离;souls 是原生角色区):
  // 游戏内容 game/** · 原生角色 souls/**(每个 soul 一个可折叠节点)· 其它
  const sections = useMemo(() => {
    const game: TreeFile[] = []
    const souls: TreeFile[] = []
    const rest: TreeFile[] = []
    for (const f of files) {
      if (f.path.startsWith('souls/')) souls.push(f)
      else if (f.path.startsWith('game/')) game.push(f)
      else rest.push(f)
    }
    return [
      { key: 'game', label: t('studio.secGame'), tree: buildTree(game), strip: '' },
      { key: 'souls', label: t('studio.secSouls'), tree: buildTree(souls), strip: '' },
      { key: 'rest', label: t('studio.secRest'), tree: buildTree(rest), strip: '' },
    ].filter((sec) => sec.tree.children.length || sec.tree.files.length)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files])

  if (!worldId) {
    return (
      <div className="pt-12 text-center text-[13.5px]" style={{ color: 'var(--lc-dim)' }}>
        {t('studio.noEditSessionPre')}
        <Link to="/local/create" style={{ color: 'var(--lc-candle)' }}> {t('studio.noEditSessionLink')} </Link>
        {t('studio.noEditSessionPost')}
      </div>
    )
  }

  return (
    <div className="pt-5">
      {/* 顶栏 */}
      <div className="flex items-center gap-3 mb-3">
        <Link to="/local/create" className="text-[12px]" style={{ color: 'var(--lc-faint)' }}>
          {t('studio.backCreate')}
        </Link>
        <h1 className="m-0 text-[17px] font-semibold" style={{ fontWeight: 700 }}>
          {worldName || worldId}
        </h1>
        <nav className="flex gap-0.5 ml-2">
          {TAB_KEYS.map(([k, labelKey]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className="text-[12.5px] rounded-lg px-3 py-1 cursor-pointer border-0"
              style={
                tab === k
                  ? { background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                  : { background: 'transparent', color: 'var(--lc-dim)' }
              }
            >
              {t(labelKey)}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setLlmOpen(true)}
            className="text-[12px] rounded-lg px-2.5 py-1.5 cursor-pointer border"
            style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
            title={t('studio.llmTitle')}
          >
            🔌 {t('studio.llm')}
          </button>
          <button
            onClick={toggleChat}
            className="text-[12px] rounded-lg px-2.5 py-1.5 cursor-pointer border"
            style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
            title={chatOpen ? t('studio.collapseChat') : t('studio.expandChat')}
          >
            {chatOpen ? t('studio.collapse') : t('studio.expand')}
          </button>
          <button
            onClick={playtest}
            disabled={busyPlay || running}
            className="text-[13px] font-semibold rounded-lg px-4 py-1.5 cursor-pointer border-0"
            style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}
          >
            {busyPlay ? t('studio.starting') : t('studio.playtest')}
          </button>
        </div>
      </div>

      <div
        className="grid gap-3"
        style={{
          gridTemplateColumns: chatOpen ? 'minmax(0,1fr) minmax(0,360px)' : 'minmax(0,1fr)',
          minHeight: '68vh',
        }}
      >
        {/* 主区:tab 内容 */}
        <div
          className="rounded-xl border overflow-hidden flex flex-col"
          style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)', height: '74vh' }}
        >
          {tab === 'overview' && (
            <div className="p-6 overflow-y-auto">
              <div
                className="rounded-xl border p-5 flex items-start gap-4"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)' }}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-mono tracking-widest" style={{ color: 'var(--lc-faint)' }}>
                    {t('studio.currentWorld')}
                  </div>
                  <h2 className="m-0 mt-1 text-[19px] font-bold">
                    {worldName || worldId}
                    <button
                      onClick={async () => {
                        const nm = prompt(t('studio.renamePh'), worldName)?.trim()
                        if (!nm) return
                        try {
                          await renameEditWorld(nm)
                          setWorldName(nm)
                        } catch (e) {
                          alert(String(e))
                        }
                      }}
                      className="ml-2 text-[12px] cursor-pointer border-0 bg-transparent align-middle"
                      style={{ color: 'var(--lc-dim)' }}
                      title={t('studio.rename')}
                    >
                      ✎
                    </button>
                  </h2>
                  {worldName && worldName !== worldId && (
                    <div className="text-[10.5px] font-mono mt-0.5" style={{ color: 'var(--lc-faint)' }}>{worldId}</div>
                  )}
                  <p className="mt-2 text-[13px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
                    {t('studio.overviewHint')}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setChatOpen(true)
                    setInput(t('studio.editScriptKick'))
                  }}
                  className="text-[12.5px] rounded-lg px-3.5 py-2 cursor-pointer border shrink-0"
                  style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
                >
                  {t('studio.editScript')}
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
                {(
                  [
                    ['files', t('studio.cardFiles'), t('studio.filesCount', { n: counts.files })],
                    ['map', t('studio.cardMap'), t('studio.locCount', { n: counts.loc })],
                    ['story', t('studio.cardStory'), t('studio.canvas')],
                    ['relation', t('studio.cardRelation'), t('studio.npcCount', { n: counts.npc })],
                    ['files', 'souls', t('studio.soulsCount', { n: counts.souls })],
                    ['files', t('studio.cardQuests'), t('studio.questsCount', { n: counts.quests })],
                  ] as [Tab, string, string][]
                ).map(([target, label, sub], i) => (
                  <button
                    key={i}
                    onClick={() => setTab(target)}
                    className="rounded-xl border p-4 text-left cursor-pointer"
                    style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)' }}
                  >
                    <div className="text-[14px] font-semibold">{label}</div>
                    <div className="text-[11.5px] font-mono mt-1" style={{ color: 'var(--lc-faint)' }}>
                      {sub}
                    </div>
                  </button>
                ))}
              </div>
              <ReviewSubmit worldId={worldId} worldName={worldName} />
            </div>
          )}

          {tab === 'files' && (
            <div className="grid flex-1 min-h-0" style={{ gridTemplateColumns: '220px 1fr' }}>
              <div className="border-r overflow-y-auto p-2 text-[12px]" style={{ borderColor: 'var(--lc-line)' }}>
                {sections.map((sec) => (
                  <div key={sec.key} className="mb-2">
                    <div className="px-2 pt-1 pb-0.5 text-[10px] font-mono tracking-widest" style={{ color: 'var(--lc-faint)' }}>
                      {sec.label}
                    </div>
                    <TreeView
                      node={sec.tree}
                      depth={0}
                      openDirs={openDirs}
                      toggle={(d) =>
                        setOpenDirs((prev) => {
                          const n = new Set(prev)
                          if (n.has(d)) n.delete(d)
                          else n.add(d)
                          return n
                        })
                      }
                      sel={sel}
                      onOpen={openFile}
                    />
                  </div>
                ))}
              </div>
              <div className="flex flex-col min-h-0 min-w-0">
                <StructuredPreview path={sel} text={fileText} filename={sel} hint={t('studio.filePreviewHint')} />
              </div>
            </div>
          )}

          {tab === 'cover' && (
            <div className="flex-1 min-h-0 grid place-items-center p-6 overflow-y-auto">
              <div className="text-center max-w-[560px]">
                <div
                  className="mx-auto rounded-xl border overflow-hidden grid place-items-center"
                  style={{ width: 480, height: 320, borderColor: 'var(--lc-line)', background: 'var(--lc-panel2)' }}
                >
                  <img
                    key={coverVer}
                    src={`${localEndpoint()}/api/v1/create/session/edit-local/portrait?v=${coverVer}`}
                    onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                </div>
                <p className="mt-3 text-[12px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
                  {t('studio.coverDesc')}
                </p>
                <div className="mt-3 flex justify-center gap-2">
                  <button
                    onClick={async () => {
                      setCoverBusy(true)
                      try {
                        const r = await fetch(`${localEndpoint()}/api/v1/create/session/edit-local/portrait`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({}),
                        })
                        const d = (await r.json()) as { ok: boolean; error?: string }
                        if (!d.ok) throw new Error(d.error || `cover → ${r.status}`)
                        setCoverVer((v) => v + 1)
                      } catch (e) {
                        alert(String(e))
                      } finally {
                        setCoverBusy(false)
                      }
                    }}
                    disabled={coverBusy}
                    className="text-[13px] font-semibold rounded-lg px-4 py-2 cursor-pointer border-0"
                    style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)', opacity: coverBusy ? 0.5 : 1 }}
                  >
                    {coverBusy ? t('soul.portraitBusy') : `🎨 ${t('studio.coverGen')}`}
                  </button>
                  <input ref={coverUploadRef} type="file" accept="image/*" className="hidden"
                    onChange={async (e) => {
                      const f = e.target.files?.[0]
                      if (!f) return
                      setCoverBusy(true)
                      try {
                        const r = await fetch(`${localEndpoint()}/api/v1/create/session/edit-local/portrait/upload`, {
                          method: 'POST',
                          headers: { 'Content-Type': f.type || 'image/png' },
                          body: f,
                        })
                        if (!r.ok) throw new Error(`upload → ${r.status}`)
                        setCoverVer((v) => v + 1)
                      } catch (err) {
                        alert(String(err))
                      } finally {
                        setCoverBusy(false)
                      }
                    }} />
                  <button
                    onClick={() => coverUploadRef.current?.click()}
                    disabled={coverBusy}
                    className="text-[13px] rounded-lg px-4 py-2 cursor-pointer border"
                    style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
                  >
                    ⇧ {t('soul.portraitUpload')}
                  </button>
                </div>
              </div>
            </div>
          )}

          {(tab === 'map' || tab === 'story' || tab === 'relation') && (
            <div className="flex-1 min-h-0 relative">
              {tab === 'story' && (
                <div className="absolute z-10 top-2 right-2 flex gap-1.5">
                  <button
                    onClick={draftStory}
                    disabled={running}
                    className="text-[12px] rounded-lg px-3 py-1.5 cursor-pointer border"
                    style={{
                      background: 'var(--lc-panel)',
                      borderColor: 'var(--lc-candle)',
                      color: 'var(--lc-candle)',
                      opacity: running ? 0.5 : 1,
                    }}
                  >
                    {t('studio.agentDraft')}
                  </button>
                  <button
                    onClick={groundStory}
                    disabled={running}
                    className="text-[12px] rounded-lg px-3 py-1.5 cursor-pointer border"
                    style={{
                      background: 'var(--lc-panel)',
                      borderColor: 'var(--lc-line)',
                      color: 'var(--lc-text)',
                      opacity: running ? 0.5 : 1,
                    }}
                  >
                    {t('studio.groundToContent')}
                  </button>
                </div>
              )}
              <StudioCanvas
                kind={tab as CanvasKind}
                refreshKey={canvasRefresh}
                onDraft={tab === 'story' ? draftStory : tab === 'relation' ? draftRelations : undefined}
              />
            </div>
          )}
        </div>

        {/* 右:常驻对话(可收起) */}
        {chatOpen && (
          <div
            className="rounded-xl border flex flex-col"
            style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)', height: '74vh' }}
          >
            <div
              className="px-3 py-2 border-b flex items-center gap-2 text-[12px] font-semibold"
              style={{ borderColor: 'var(--lc-line)' }}
            >
              {t('studio.agent')}
              <span className="font-normal font-mono text-[10.5px]" style={{ color: 'var(--lc-faint)' }}>
                {t('studio.everyLineWrites')}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
              {importSt?.has_source && (
                <ImportProgressPin
                  status={importSt}
                  running={running}
                  onSend={(cmd) => void send(cmd)}
                />
              )}
              {importSt?.has_source && !importSt.plan && !impDismissed && (
                <ImportOptionsPanel
                  status={importSt}
                  running={running}
                  onSend={(cmd) => {
                    setImpDismissed(true) // 面板让位;①产出 plan 后由进度钉接管
                    void send(cmd)
                  }}
                  onDismiss={dismissImport}
                />
              )}
              {chat.length === 0 && !openerDismissed && !running && !importSt?.has_source && (
                <div className="rounded-xl border p-4 flex flex-col gap-2.5"
                  style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)' }}>
                  <div className="text-[13px] font-semibold">{t('studio.openerTitle', { name: worldName || worldId })}</div>
                  <p className="m-0 text-[12px] leading-relaxed" style={{ color: 'var(--lc-dim)' }}>
                    {t('studio.openerDesc')}
                  </p>
                  <button
                    onClick={() => {
                      setOpenerDismissed(true)
                      void send(t('studio.openerAnalyzePrompt', { name: worldName || worldId }))
                    }}
                    className="text-left text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
                    style={{ borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)', background: 'transparent' }}
                  >
                    ✦ {t('studio.openerAnalyze')}
                    <span className="block text-[11px] mt-0.5" style={{ color: 'var(--lc-dim)' }}>{t('studio.openerAnalyzeSub')}</span>
                  </button>
                  <button
                    onClick={() => {
                      setOpenerDismissed(true)
                      void send(t('studio.openerBuildPrompt', { name: worldName || worldId }))
                    }}
                    className="text-left text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
                    style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-text)', background: 'transparent' }}
                  >
                    ⚡ {t('studio.openerBuild')}
                    <span className="block text-[11px] mt-0.5" style={{ color: 'var(--lc-dim)' }}>{t('studio.openerBuildSub')}</span>
                  </button>
                  <button
                    onClick={() => setOpenerDismissed(true)}
                    className="text-left text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border"
                    style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
                  >
                    ✋ {t('studio.openerManual')}
                    <span className="block text-[11px] mt-0.5" style={{ color: 'var(--lc-faint)' }}>{t('studio.openerManualSub')}</span>
                  </button>
                </div>
              )}
              {running && (
                <div
                  className="sticky top-0 z-10 self-stretch flex items-center gap-2 text-[12px] rounded-lg px-3 py-2 border"
                  style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)' }}
                >
                  <span className="lc-spin inline-block" style={{ width: 12, height: 12 }} />
                  <span className="min-w-0 truncate">{nowDoing || t('studio.working2')}</span>
                </div>
              )}
              {chat.map((m, i) =>
                m.role === 'receipt' ? (
                  <div
                    key={i}
                    className="self-start rounded-lg border px-3 py-2"
                    style={{ borderColor: 'var(--lc-line)', background: 'var(--lc-panel2)' }}
                  >
                    <div className="text-[11px] font-mono mb-1" style={{ color: 'var(--lc-faint)' }}>
                      {t('studio.turnChanges', { n: m.paths.length })}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {m.paths.map((pth) => (
                        <button
                          key={pth}
                          onClick={() => openFromReceipt(pth)}
                          className="text-[11px] font-mono rounded-full px-2 py-0.5 cursor-pointer border"
                          style={{ borderColor: 'var(--lc-line)', background: 'transparent', color: 'var(--lc-live)' }}
                          title={pth}
                        >
                          {pth.endsWith('world_map.json') ? '🗺 ' : ''}
                          {pth.split('/').pop()}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : m.role === 'tool' ? (
                  <div
                    key={i}
                    className="self-start text-[11px] font-mono rounded-md px-2.5 py-1"
                    style={{ background: 'var(--lc-panel2)', color: m.done ? 'var(--lc-live)' : 'var(--lc-dim)' }}
                  >
                    {m.done ? '✓' : '…'} {m.name}
                    {m.path ? ` · ${m.path}` : ''}
                  </div>
                ) : (
                  <div
                    key={i}
                    className="max-w-[44ch] text-[13px] leading-relaxed rounded-xl px-3 py-2 whitespace-pre-wrap"
                    style={
                      m.role === 'user'
                        ? { alignSelf: 'flex-end', background: 'var(--lc-candle-soft)', color: 'var(--lc-text)', border: '1px solid var(--lc-candle)' }
                        : { alignSelf: 'flex-start', background: 'var(--lc-panel2)', color: 'var(--lc-text)' }
                    }
                  >
                    {m.text || (m.role === 'assistant' && m.streaming ? '…' : '')}
                  </div>
                ),
              )}
              <div ref={chatEnd} />
            </div>
            <div className="p-2.5 border-t flex gap-2" style={{ borderColor: 'var(--lc-line)' }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) send()
                }}
                placeholder={running ? t('studio.chatPhBusy') : t('studio.chatPh')}
                disabled={running}
                className="flex-1 rounded-lg border px-3 py-2 text-[13px] outline-none"
                style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-line)', color: 'var(--lc-text)' }}
              />
              <button
                onClick={() => send()}
                disabled={running || !input.trim()}
                className="text-[13px] font-semibold rounded-lg px-3.5 cursor-pointer border-0"
                style={{
                  background: 'var(--lc-candle)',
                  color: 'var(--lc-on-accent)',
                  opacity: running || !input.trim() ? 0.5 : 1,
                }}
              >
                {t('studio.say')}
              </button>
            </div>
          </div>
        )}
      </div>
      {llmOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center" style={{ background: 'rgba(0,0,0,.55)' }}
          onClick={() => setLlmOpen(false)}>
          <div className="w-[440px] max-w-[92vw] rounded-xl border p-5"
            style={{ background: 'var(--lc-panel)', borderColor: 'var(--lc-line)' }}
            onClick={(e) => e.stopPropagation()}>
            <h2 className="m-0 text-[15px] font-semibold">{t('studio.llmTitle')}</h2>
            <p className="mt-1 mb-4 text-[12px]" style={{ color: 'var(--lc-faint)' }}>
              {t('studio.llmDesc')}
            </p>
            <ModelAccessPanel onState={setLlmAccess} />
            <button
              onClick={async () => {
                if (!llmAccess.picked) return
                try {
                  if (llmAccess.needsKey && llmAccess.key.trim()) {
                    await saveProviderKey(llmAccess.picked.id, llmAccess.key.trim())
                  }
                  await setEditLlm(llmAccess.picked.id)
                  setLlmOpen(false)
                } catch (e) {
                  alert(String(e))
                }
              }}
              disabled={!llmAccess.ready}
              className="mt-4 w-full text-[13.5px] font-semibold rounded-lg px-4 py-2.5 cursor-pointer border-0"
              style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)', opacity: llmAccess.ready ? 1 : 0.5 }}>
              {t('studio.llmApply')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function extractRelationsJson(text: string): { relationships: unknown[]; layout: Record<string, unknown> } | null {
  const fence = text.match(/```json\s*([\s\S]*?)```/)
  const candidates = fence ? [fence[1]] : []
  const brace = text.indexOf('{')
  if (brace >= 0) candidates.push(text.slice(brace))
  for (const c of candidates) {
    try {
      const v = JSON.parse(c) as { relationships?: unknown[] }
      if (Array.isArray(v?.relationships)) return { relationships: v.relationships, layout: {} }
    } catch {
      /* try next */
    }
  }
  return null
}

// 起草回复解析:优先 ```json 围栏,退化到「第一个含 nodes 的 {…}」
function extractCanvasJson(text: string): CanvasState | null {
  const fence = text.match(/```json\s*([\s\S]*?)```/)
  const candidates = fence ? [fence[1]] : []
  const brace = text.indexOf('{')
  if (brace >= 0) candidates.push(text.slice(brace))
  for (const c of candidates) {
    try {
      const v = JSON.parse(c) as CanvasState
      if (Array.isArray(v?.nodes)) return { nodes: v.nodes, edges: v.edges ?? [], viewport: v.viewport ?? {} }
    } catch {
      /* try next */
    }
  }
  return null
}

// B11:已知 JSON 先给结构化键值视图,raw 全文在下方。
export function StructuredPreview({ path, text, filename, hint }: { path: string; text: string; filename?: string; hint?: string }) {
  const { t } = useLocalT()
  const [wrap, setWrap] = useState(true) // 默认折行(长行看得到);可切回不折行看结构
  const parsed = useMemo(() => {
    if (!path.endsWith('.json')) return null
    try {
      const v = JSON.parse(text) as unknown
      return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
    } catch {
      return null
    }
  }, [path, text])
  return (
    <div className="flex-1 flex flex-col min-h-0 min-w-0">
      <div
        className="flex items-center gap-3 px-3 py-2 shrink-0"
        style={{ background: 'var(--lc-panel)', borderBottom: '1px solid var(--lc-line)' }}
      >
        <span className="text-[11px] font-mono truncate" style={{ color: 'var(--lc-faint)' }}>
          {filename || hint}
        </span>
        <button
          onClick={() => setWrap((w) => !w)}
          className="ml-auto shrink-0 text-[10.5px] font-mono px-2 py-0.5 rounded cursor-pointer border"
          style={{ borderColor: 'var(--lc-line)', color: wrap ? 'var(--lc-candle)' : 'var(--lc-dim)', background: 'transparent' }}
          title={t('studio.toggleWrap')}
        >
          {wrap ? `↩ ${t('studio.wrap')}` : `⇥ ${t('studio.noWrap')}`}
        </button>
      </div>
      <div className="flex-1 overflow-auto">
      {parsed && (
        <div className="p-3 border-b" style={{ borderColor: 'var(--lc-line)' }}>
          {Object.entries(parsed).map(([k, v]) => (
            <div key={k} className="flex gap-2 py-1 text-[12px]" style={{ borderBottom: '1px dotted var(--lc-line)' }}>
              <span className="font-mono shrink-0 w-[110px] truncate" style={{ color: 'var(--lc-dim)' }} title={k}>
                {k}
              </span>
              <span className="min-w-0 break-words" style={{ color: 'var(--lc-text)' }}>
                {typeof v === 'string' ? v : JSON.stringify(v)}
              </span>
            </div>
          ))}
        </div>
      )}
      <pre
        className="m-0 p-3 text-[11.5px] leading-relaxed"
        style={{
          color: parsed ? 'var(--lc-faint)' : 'var(--lc-text)',
          whiteSpace: wrap ? 'pre-wrap' : 'pre',
          wordBreak: wrap ? 'break-word' : 'normal',
        }}
      >
        {text.length > 200_000 ? text.slice(0, 200_000) + t('studio.truncated') : text}
      </pre>
      </div>
    </div>
  )
}

// 工具调用 → 「现在在做什么」的简短短语(niko:不要 [calling],要人话)
function doingPhrase(name: string, path: string, t: (k: string, v?: Record<string, string | number>) => string): string {
  const base = path ? path.split('/').pop() || path : ''
  if (/read_file|glob|find|list/.test(name)) return t('studio.doingRead', { f: base || '…' })
  if (/write|upsert|edit|apply/.test(name)) return t('studio.doingWrite', { f: base || '…' })
  if (/delete|remove/.test(name)) return t('studio.doingDelete', { f: base || '…' })
  return `⚙ ${name}${base ? ' · ' + base : ''}`
}
