// C1 观察窗(Observatory)—— Web = 看活世界的窗(SIMULATION-PLATFORM §二,
// M26 层栈的观察层)。
//
// 层阶体验(niko 定稿,v0.4.0):
//   第一层 · 选内容:存档大卡("选一个世界回去"),一屏专门选;
//   第二层 · 频道玻璃(M24 §7):左=频道(◉世界/#此地/@souls)+镜头 ·
//            中=当前频道的舞台 · 右=在场(点头像=开@频道)。
//   ◉世界=下场(内嵌 PlayStage,时钟走);@/#/镜头=幕间(时钟停)——
//   看↔玩=切频道,同一块玻璃,游玩不再跳走。
// 模块由数据点亮(has() 注册表);视觉复用 --lc-* 主题 token。
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  listLocalWorlds,
  listLocalSouls,
  listLocalSaves,
  bindPlaySession,
  type LocalWorld,
  type LocalSoul,
  type LocalSave,
} from './localClient'
import { getTraces, getTrace } from '../play/stage/stageClient'
import { computeOrigin } from '../play/playClient'
import type { TraceSummaryRow, TraceRecord } from '../play/stage/events'
import { PlayStage } from '../play/stage/PlayStage'
import { ChatDrawer, RoomChatDrawer } from '../play/stage/ChatDrawer'
import { WorldMapCanvas } from './WorldMapCanvas'
import { useStageStrings } from '../play/stage/strings'

// 从 trace 的 bus_messages 挖 world/scene 的 scene_label(世界此刻标题)。
function sceneLabel(trace: TraceRecord | null): string {
  for (const m of trace?.bus_messages || []) {
    if (m.topic === 'world/scene') {
      const p = m.payload as { scene_label?: string } | undefined
      if (p?.scene_label) return p.scene_label
    }
  }
  return ''
}
// 从 soul.reason 解析所在地点 + 是否与玩家同处。
function soulLoc(reason?: string): string {
  const m = (reason || '').match(/at '([^']+)'|group '([^']+)'/)
  const raw = m?.[1] || m?.[2] || ''
  return raw.split('/').pop() || raw
}
function nearPlayer(reason?: string): boolean {
  return /co-located|with player/.test(reason || '')
}

type ModuleKey = 'pulse' | 'feed' | 'map' | 'chars' | 'places' | 'debug'
type WorldData = {
  world: LocalWorld | null
  souls: LocalSoul[]
  traces: TraceSummaryRow[]
  latest: TraceRecord | null
}

// 模块注册表 —— 每个镜头声明 has(data) 谓词,有数据才进左栏导航。
const MODULES: {
  key: ModuleKey
  cn: string
  en: string
  ico: string
  has: (d: WorldData) => boolean
}[] = [
  { key: 'pulse', cn: '世界此刻', en: 'NOW', ico: '◔', has: (d) => !!d.latest },
  { key: 'feed', cn: '世界动态', en: 'WORLD FEED', ico: '✷', has: () => true },
  { key: 'map', cn: '地图', en: 'MAP', ico: '⌖', has: () => true },
  { key: 'chars', cn: '角色', en: 'CHARACTERS', ico: '✦', has: (d) => d.souls.length > 0 },
  { key: 'places', cn: '地点', en: 'PLACES', ico: '❧', has: () => true },
  { key: 'debug', cn: 'Debug', en: '4TH · RAW', ico: '⚙', has: (d) => !!d.latest },
]

const nameOf = (w: LocalWorld | null) =>
  w?.display_name || w?.name_local || w?.name || w?.id || '—'

export function ObservatoryShell() {
  const [worlds, setWorlds] = useState<LocalWorld[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [souls, setSouls] = useState<LocalSoul[]>([])
  const [saves, setSaves] = useState<LocalSave[]>([])
  const [saveId, setSaveId] = useState('')
  const [traces, setTraces] = useState<TraceSummaryRow[]>([])
  const [latest, setLatest] = useState<TraceRecord | null>(null)
  const [active, setActive] = useState<ModuleKey>('pulse')
  // P2a 挂机/tick:开启后按 tickSec 定时重拉 trace,画布/各镜头随世界推进实时更新。
  // 真·后台自动推进(引擎 auto-tick)待接;现阶段=观察刷新。
  const [autoRun, setAutoRun] = useState(false)
  const [tickSec, setTickSec] = useState(15)
  // P3 replay:replayIdx=null 跟随 latest(现在);非空=回放到该回合。displayed = replayRec ?? latest。
  const [replayIdx, setReplayIdx] = useState<number | null>(null)
  const [replayRec, setReplayRec] = useState<TraceRecord | null>(null)
  const [replayPlaying, setReplayPlaying] = useState(false)
  // 频道玻璃(M24 §7):中栏由「当前频道」决定 —— 镜头=观察,◉世界=下场
  // (时钟走),@soul=直聊,#=房间。看↔玩=切频道,同一块玻璃。
  const [chan, setChan] = useState<
    | { kind: 'lens' }
    | { kind: 'world' }
    | { kind: 'room' }
    | { kind: 'dm'; iid: string; name: string }
  >({ kind: 'lens' })
  const [dataErr, setDataErr] = useState('')
  // 频道玻璃毛边:roster 名字本地化 —— 左栏@频道/右栏「在场」把 sid(如 elena)
  // 换成 soul 展示名。每个 iid 问一次 GET /api/v1/play/chat/<iid>(返回 {name}),
  // 缓存 Map<iid,name> 优先显示;失败静默退 sid。
  const [soulNames, setSoulNames] = useState<Record<string, string>>({})
  const askedNames = useRef<Set<string>>(new Set())
  const navigate = useNavigate()
  const { t: stageT } = useStageStrings()

  // observe 的数据源 = 一个**存档**的 trace(B 方案:选有内容的存档观察,而非
  // 空的当前 session)。读某存档 = bind 它 → getTraces 就读那个存档的 root。
  const loadTraces = () => {
    getTraces()
      .then((rows) => {
        setTraces(rows)
        const last = rows[rows.length - 1]
        if (last) getTrace(last.i).then(setLatest).catch(() => {})
      })
      .catch((e) => setDataErr('trace 读取出错 —— ' + String(e).slice(0, 80)))
  }
  const observeSave = (s: LocalSave) => {
    setSaveId(s.session_id)
    if (s.slug) setSelectedId(s.slug)
    setLatest(null)
    setTraces([])
    setDataErr('')
    // 换存档 = 换一批 soul 实例,名字缓存清掉重新问
    askedNames.current = new Set()
    setSoulNames({})
    setActive('pulse') // 进门先看世界此刻
    setChan({ kind: 'lens' })
    bindPlaySession(s.session_id)
      .then(loadTraces)
      .catch((e) => setDataErr('绑定存档出错 —— ' + String(e).slice(0, 80)))
  }

  // U1:选世界 → 起新局 → 直接进 observe 的 ◉世界(下场游玩)。复用 bindPlaySession(worldId)。
  const startWorld = async (w: LocalWorld) => {
    setDataErr('')
    setLatest(null)
    setTraces([])
    askedNames.current = new Set()
    setSoulNames({})
    setActive('pulse')
    try {
      const slug = await bindPlaySession(w.id)
      setSelectedId(w.id)
      setSaveId(slug)
      setChan({ kind: 'world' })
      loadTraces()
    } catch (e) {
      setDataErr('开局出错 —— ' + String(e).slice(0, 80))
    }
  }

  useEffect(() => {
    // 层阶第一层:只备数据,不自动绑——进门先选(niko 定稿的入口体验)。
    listLocalWorlds()
      .then((d) => setWorlds([...d.worlds, ...d.builtin]))
      .catch(() => {})
    listLocalSouls()
      .then((d) => setSouls(d.souls))
      .catch(() => {})
    listLocalSaves()
      .then(setSaves)
      .catch((e) => setDataErr('存档列表读取出错 —— ' + String(e).slice(0, 80)))
  }, [])

  // P2a 挂机轮询:autoRun 且已绑存档时,定时重拉 trace → latest 变 → 画布/镜头实时刷新。
  useEffect(() => {
    if (!autoRun || !saveId) return
    const id = setInterval(() => {
      getTraces()
        .then((rows) => {
          setTraces(rows)
          const last = rows[rows.length - 1]
          if (last) getTrace(last.i).then(setLatest).catch(() => {})
        })
        .catch(() => {})
    }, Math.max(3, tickSec) * 1000)
    return () => clearInterval(id)
  }, [autoRun, tickSec, saveId])

  // P3:回放索引变 → 载入该回合 trace 作显示;null=回到现在(跟随 latest)。
  useEffect(() => {
    if (replayIdx === null) return
    const row = traces[replayIdx]
    if (!row) return
    getTrace(row.i).then(setReplayRec).catch(() => {})
  }, [replayIdx, traces])

  // P3:回放播放 → 定时前进一回合,到末尾回到"现在"(live)。
  useEffect(() => {
    if (!replayPlaying) return
    const id = setInterval(() => {
      setReplayIdx((k) => {
        const cur = k ?? 0
        if (cur >= traces.length - 1) {
          setReplayPlaying(false)
          return null
        }
        return cur + 1
      })
    }, 1300)
    return () => clearInterval(id)
  }, [replayPlaying, traces.length])

  // roster 名字本地化:latest trace 里出现的每个 iid,问一次聊天端点拿展示名。
  useEffect(() => {
    for (const s of latest?.souls || []) {
      const iid = String(s.instance_id || '')
      if (!iid || askedNames.current.has(iid)) continue
      askedNames.current.add(iid)
      fetch(`${computeOrigin()}/api/v1/play/chat/${encodeURIComponent(iid)}`, { credentials: 'include' })
        .then((r) => r.json())
        .then((d: { name?: string | null }) => {
          if (d?.name) setSoulNames((m) => ({ ...m, [iid]: String(d.name) }))
        })
        .catch(() => {}) // 静默:拿不到就继续显示 sid
    }
  }, [latest])

  const world = useMemo(() => worlds.find((w) => w.id === selectedId) ?? null, [worlds, selectedId])
  const displayed = replayIdx !== null ? (replayRec ?? latest) : latest
  const data: WorldData = { world, souls, traces, latest: displayed }
  const modules = MODULES.filter((m) => m.has(data))
  const curSave = saves.find((s) => s.session_id === saveId) ?? null

  const errBanner = dataErr ? (
    <div style={{ marginBottom: 12, padding: '10px 14px', borderRadius: 10, border: '1px solid #FF6B8A44', background: '#FF6B8A11', color: '#FF6B8A', fontSize: 12.5 }}>
      ⚠ {dataErr}(仍显示能读到的部分,不崩)
    </div>
  ) : null

  // ── 第一层 · 选内容:存档大卡,一屏专门选(层阶入口)──────────────────
  if (!saveId) {
    return (
      <div className="page-enter" style={{ paddingTop: 24, maxWidth: 980, margin: '0 auto' }}>
        {errBanner}
        <h1 style={{ fontFamily: 'var(--font-display, serif)', fontSize: 30, margin: 0, color: 'var(--lc-text)' }}>
          选一个世界回去
        </h1>
        <p style={{ fontSize: 13, color: 'var(--lc-faint)', marginTop: 8, marginBottom: 24 }}>
          观察是隔着看 —— 挑个世界开新局,或回到一段旧的;进去随时可附身下场。
        </p>

        {/* U1:开新局 —— 选世界起新局,直接进 observe 的 ◉世界(下场游玩) */}
        <div style={{ fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--lc-faint)', marginBottom: 10 }}>开新局 · 选个世界</div>
        {worlds.filter((w) => !w.hidden).length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginBottom: 30 }}>
            {worlds.filter((w) => !w.hidden).slice(0, 18).map((w) => (
              <button
                key={w.id}
                onClick={() => startWorld(w)}
                className="obs-world-card"
                style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '14px 16px', borderRadius: 12, cursor: 'pointer', textAlign: 'left', border: '1px solid var(--lc-line)', background: 'var(--lc-panel)' }}
              >
                <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--lc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {w.display_name || w.name_local || w.name}
                </span>
                {w.desc ? (
                  <span style={{ fontSize: 12, color: 'var(--lc-dim)', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{w.desc}</span>
                ) : (
                  <span style={{ fontSize: 11, color: 'var(--lc-faint)' }}>开一局,下场看它活起来。</span>
                )}
              </button>
            ))}
          </div>
        ) : null}

        <div style={{ fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--lc-faint)', marginBottom: 10 }}>回到存档 · 续一段</div>
        {saves.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
            {saves.slice(0, 24).map((s) => (
              <button
                key={s.session_id}
                onClick={() => observeSave(s)}
                className="obs-save-card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  padding: '18px 20px',
                  borderRadius: 14,
                  cursor: 'pointer',
                  textAlign: 'left',
                  border: '1px solid var(--lc-line)',
                  background: 'var(--lc-panel)',
                }}
              >
                <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--lc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.name || s.session_id}
                </span>
                {/* slug 行:能在 worlds 列表按 id 匹配到就显示 display_name/name_local */}
                <span style={{ fontSize: 11, color: 'var(--lc-faint)', letterSpacing: 1 }}>
                  {(() => {
                    const w = worlds.find((x) => x.id === s.slug)
                    return (w && (w.display_name || w.name_local || w.name)) || s.slug || s.kind || ''
                  })()}
                </span>
                {s.feed_tease ? (
                  <span style={{ fontSize: 12.5, color: 'var(--lc-dim)', lineHeight: 1.6, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {s.feed_time ? `上次 ${s.feed_time} · ` : ''}
                    {s.feed_tease}
                  </span>
                ) : (
                  <span style={{ fontSize: 12, color: 'var(--lc-faint)' }}>还没有故事 —— 进去开始。</span>
                )}
              </button>
            ))}
          </div>
        ) : (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--lc-faint)', fontSize: 13, border: '1px dashed var(--lc-line)', borderRadius: 14 }}>
            还没有存档 —— 从上面挑个世界开一局。
          </div>
        )}
      </div>
    )
  }

  // ── 第二层 · 频道玻璃(M24 §7):左=频道+镜头 · 中=当前频道的舞台 ·
  //    右=在场。◉世界=下场(时钟走);@/#/镜头=幕间(时钟停)。──────────
  const chanBtn = (on: boolean) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 13,
    padding: '8px 10px',
    borderRadius: 8,
    cursor: 'pointer',
    border: 'none',
    textAlign: 'left' as const,
    background: on ? 'var(--lc-candle-soft)' : 'transparent',
    color: on ? 'var(--lc-candle)' : 'var(--lc-dim)',
  })
  const rosterSouls = (data.latest?.souls || [])
    .map((s) => {
      const iid = String(s.instance_id || '')
      return {
        iid,
        // 名字本地化:缓存里有展示名就用,没有退 sid
        name: soulNames[iid] || String(s.sid || '?'),
        loc: soulLoc(s.reason),
        near: nearPlayer(s.reason),
      }
    })
    .filter((s) => s.iid)

  return (
    <div className="page-enter" style={{ paddingTop: 20 }}>
      {errBanner}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '220px 1fr 230px',
          gap: 1,
          background: 'var(--lc-line)',
          height: 'calc(100vh - 150px)',
          minHeight: 480,
          borderRadius: 14,
          overflow: 'hidden',
          border: '1px solid var(--lc-line)',
        }}
      >
        {/* 左栏:频道 + 镜头 */}
        <aside style={{ background: 'var(--lc-panel)', padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
          <button
            onClick={() => {
              setSaveId('')
              setLatest(null)
              setTraces([])
              setChan({ kind: 'lens' })
            }}
            style={{ alignSelf: 'flex-start', background: 'transparent', border: 'none', color: 'var(--lc-faint)', fontSize: 12, cursor: 'pointer', padding: 0 }}
          >
            ← 换一个世界
          </button>
          <div>
            <div style={{ fontFamily: 'var(--font-display, serif)', fontSize: 18, fontWeight: 700, color: 'var(--lc-text)' }}>
              {curSave?.name || nameOf(world)}
            </div>
            <div style={{ fontSize: 10, letterSpacing: 3, textTransform: 'uppercase', color: 'var(--lc-faint)', marginTop: 2 }}>
              {nameOf(world)}
            </div>
          </div>

          {saveId ? (
            <div style={{ padding: 10, borderRadius: 10, border: '1px solid var(--lc-line)', background: 'var(--lc-panel2, #0e1116)', display: 'flex', flexDirection: 'column', gap: 8 }} data-testid="tick-bar">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--lc-faint)' }}>挂机 · Watch</span>
                <span style={{ fontSize: 11, color: 'var(--lc-dim)' }}>回合 {traces.length}</span>
              </div>
              <button
                onClick={() => setAutoRun((v) => !v)}
                data-testid="tick-toggle"
                style={{ fontSize: 12, fontWeight: 600, padding: '6px 8px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${autoRun ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-line)'}`, background: autoRun ? 'rgba(232,180,90,0.13)' : 'transparent', color: autoRun ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-text)' }}
              >
                {autoRun ? `▮▮ 挂机中 · 每 ${tickSec}s` : '▶ 挂机(自动刷新)'}
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 10, color: 'var(--lc-faint)' }}>间隔</span>
                <select
                  value={tickSec}
                  onChange={(e) => setTickSec(Number(e.target.value))}
                  style={{ flex: 1, fontSize: 11, padding: '3px 4px', borderRadius: 6, background: 'var(--lc-panel)', color: 'var(--lc-text)', border: '1px solid var(--lc-line)' }}
                >
                  <option value={5}>5 秒</option>
                  <option value={15}>15 秒</option>
                  <option value={30}>30 秒</option>
                  <option value={60}>1 分</option>
                  <option value={300}>5 分</option>
                </select>
                <button onClick={loadTraces} title="手动刷新一次" style={{ fontSize: 12, padding: '3px 8px', borderRadius: 6, cursor: 'pointer', border: '1px solid var(--lc-line)', background: 'transparent', color: 'var(--lc-dim)' }}>↻</button>
              </div>
              <div style={{ fontSize: 9, color: 'var(--lc-faint)', lineHeight: 1.5 }}>后台自动推进(引擎 auto-tick)待接;现为观察刷新。</div>
            </div>
          ) : null}

          {saveId && traces.length > 1 ? (
            <div style={{ padding: 10, borderRadius: 10, border: '1px solid var(--lc-line)', background: 'var(--lc-panel2, #0e1116)', display: 'flex', flexDirection: 'column', gap: 8 }} data-testid="replay-bar">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--lc-faint)' }}>时间轴 · Replay</span>
                <span style={{ fontSize: 11, color: replayIdx === null ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-dim)' }}>
                  回合 {(replayIdx ?? traces.length - 1) + 1}/{traces.length}{replayIdx === null ? ' · 现在' : ''}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={traces.length - 1}
                value={replayIdx ?? traces.length - 1}
                onChange={(e) => {
                  const v = Number(e.target.value)
                  setAutoRun(false)
                  setReplayIdx(v >= traces.length - 1 ? null : v)
                }}
                data-testid="replay-scrub"
                style={{ width: '100%', accentColor: 'var(--lc-candle, #e8b45a)' }}
              />
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={() => {
                    if (!replayPlaying) {
                      setAutoRun(false)
                      if (replayIdx === null) setReplayIdx(0)
                    }
                    setReplayPlaying((v) => !v)
                  }}
                  data-testid="replay-play"
                  style={{ flex: 1, fontSize: 12, fontWeight: 600, padding: '5px 8px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${replayPlaying ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-line)'}`, background: replayPlaying ? 'rgba(232,180,90,0.13)' : 'transparent', color: replayPlaying ? 'var(--lc-candle, #e8b45a)' : 'var(--lc-text)' }}
                >
                  {replayPlaying ? '⏸ 回放中' : '▶ 回放'}
                </button>
                <button
                  onClick={() => { setReplayPlaying(false); setReplayIdx(null) }}
                  title="回到现在"
                  style={{ fontSize: 11, padding: '5px 8px', borderRadius: 8, cursor: 'pointer', border: '1px solid var(--lc-line)', background: 'transparent', color: 'var(--lc-dim)' }}
                >
                  ⏭ 现在
                </button>
              </div>
            </div>
          ) : null}

          <div>
            <div style={{ fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--lc-faint)', marginBottom: 4 }}>频道 · Channels</div>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <button onClick={() => setChan({ kind: 'world' })} style={chanBtn(chan.kind === 'world')} data-testid="chan-world">
                <span style={{ width: 16 }}>◉</span>
                <span>世界</span>
                <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--lc-faint)' }}>下场·时钟走</span>
              </button>
              <button onClick={() => setChan({ kind: 'room' })} style={chanBtn(chan.kind === 'room')} data-testid="chan-room">
                <span style={{ width: 16 }}>#</span>
                <span>此地</span>
                <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--lc-faint)' }}>幕间</span>
              </button>
              {rosterSouls.map((s) => (
                <button
                  key={s.iid}
                  onClick={() => setChan({ kind: 'dm', iid: s.iid, name: s.name })}
                  style={chanBtn(chan.kind === 'dm' && chan.iid === s.iid)}
                >
                  <span style={{ width: 16 }}>@</span>
                  <span>{s.name}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 9, color: s.near ? 'var(--lc-candle)' : 'var(--lc-faint)' }}>
                    {s.near ? '同场' : s.loc || '在别处'}
                  </span>
                </button>
              ))}
            </nav>
          </div>

          <div>
            <div style={{ fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: 'var(--lc-faint)', marginBottom: 4 }}>镜头 · Lenses</div>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {modules.map((m) => (
                <button
                  key={m.key}
                  onClick={() => {
                    setChan({ kind: 'lens' })
                    setActive(m.key)
                  }}
                  style={chanBtn(chan.kind === 'lens' && active === m.key)}
                >
                  <span style={{ width: 16 }}>{m.ico}</span>
                  <span>{m.cn}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 9, letterSpacing: 1.5, color: 'var(--lc-faint)' }}>{m.en}</span>
                </button>
              ))}
            </nav>
          </div>

          <span style={{ marginTop: 'auto', fontSize: 10, color: 'var(--lc-faint)', lineHeight: 1.7 }}>
            ◉ 世界=下场(时钟走)· @/#/镜头=幕间(时钟停)。旧全屏舞台:
            <button onClick={() => navigate('/local/stage')} style={{ background: 'none', border: 'none', color: 'var(--lc-dim)', cursor: 'pointer', fontSize: 10, textDecoration: 'underline', padding: 0 }}>
              打开
            </button>
          </span>
        </aside>

        {/* 中栏:当前频道的舞台 */}
        <main
          style={{
            background: 'var(--lc-panel2)',
            padding: chan.kind === 'lens' ? 28 : 0,
            overflowY: chan.kind === 'lens' ? 'auto' : 'hidden',
            position: 'relative',
          }}
        >
          {chan.kind === 'lens' ? <ModuleStage active={active} data={data} names={soulNames} /> : null}
          {chan.kind === 'world' ? (
            <div className="obs-embed" data-testid="chan-world-stage">
              <PlayStage />
            </div>
          ) : null}
          {chan.kind === 'dm' ? (
            <div className="obs-chan">
              <ChatDrawer iid={chan.iid} fallbackName={chan.name} onClose={() => setChan({ kind: 'lens' })} t={stageT} />
            </div>
          ) : null}
          {chan.kind === 'room' ? (
            <div className="obs-chan">
              <RoomChatDrawer onClose={() => setChan({ kind: 'lens' })} t={stageT} />
            </div>
          ) : null}
        </main>

        {/* 右栏:在场(此刻谁在这;点=开 @ 频道) */}
        <aside style={{ background: 'var(--lc-panel)', padding: 16, overflowY: 'auto' }}>
          <div style={{ fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--lc-faint)', marginBottom: 8 }}>在场 · Present</div>
          {data.latest ? (
            <div style={{ fontSize: 11.5, color: 'var(--lc-dim)', lineHeight: 1.6, marginBottom: 12, paddingBottom: 10, borderBottom: '1px dotted var(--lc-line)' }}>
              {sceneLabel(data.latest) || '——'}
            </div>
          ) : null}
          {rosterSouls.length ? (
            rosterSouls.map((s) => (
              <button
                key={s.iid}
                onClick={() => setChan({ kind: 'dm', iid: s.iid, name: s.name })}
                style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '7px 4px', background: 'transparent', border: 'none', borderBottom: '1px dotted var(--lc-line)', cursor: 'pointer', textAlign: 'left' }}
                title={`@${s.name}`}
              >
                <span style={{ width: 26, height: 26, borderRadius: '50%', background: s.near ? 'var(--lc-candle-soft)' : 'var(--lc-panel2)', color: s.near ? 'var(--lc-candle)' : 'var(--lc-faint)', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 700 }}>
                  {(s.name || '?').slice(0, 1).toUpperCase()}
                </span>
                <span style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: 12.5, color: 'var(--lc-text)' }}>{s.name}</span>
                  <span style={{ fontSize: 10, color: s.near ? 'var(--lc-candle)' : 'var(--lc-faint)' }}>
                    {s.near ? '● 与你同场' : `○ ${s.loc || '在别处'}`}
                  </span>
                </span>
              </button>
            ))
          ) : (
            <div style={{ fontSize: 11.5, color: 'var(--lc-faint)' }}>(走一回合后,这里显示谁在场)</div>
          )}
        </aside>
      </div>
    </div>
  )
}

function ModuleStage({ active, data, names = {} }: { active: ModuleKey; data: WorldData; names?: Record<string, string> }) {
  const { world } = data

  if (!world && !data.latest) return <Placeholder text="没有世界可观察。先在书房导入 / 创建一个世界。" />

  if (active === 'chars') {
    return (
      <div className="stage-fade">
        <ModuleTitle cn="角色" en="CHARACTERS" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(170px,1fr))', gap: 12, marginTop: 18 }}>
          {data.souls.map((s, i) => (
            <div key={i} style={{ padding: 14, borderRadius: 12, border: '1px solid var(--lc-line)', background: 'var(--lc-panel)' }}>
              <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)', display: 'grid', placeItems: 'center', fontSize: 16, fontWeight: 700 }}>
                {(s.name || '?').slice(0, 1)}
              </div>
              <div style={{ fontSize: 14, marginTop: 8, fontWeight: 600, color: 'var(--lc-text)' }}>{s.name}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (active === 'feed') {
    if (!data.traces.length) {
      return <Placeholder text="当前会话还没有回合 —— 先玩一个世界,它的逐回合动态会在这里流动。" />
    }
    return (
      <div className="stage-fade">
        <ModuleTitle cn="世界动态" en="WORLD FEED" />
        <div style={{ fontSize: 11, color: 'var(--lc-faint)', marginTop: 4 }}>观察:当前会话 · {data.traces.length} 回合</div>
        <div style={{ marginTop: 18, borderLeft: '2px solid var(--lc-line)', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {data.traces.map((tr) => {
            const loc = (tr.location || tr.world_location || '').replace(/^loc:/, '')
            return (
              <div key={tr.i} style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: -25, top: 4, width: 9, height: 9, borderRadius: '50%', background: 'var(--lc-candle)', border: '2px solid var(--lc-panel2)' }} />
                <div style={{ fontSize: 12, letterSpacing: 0.5, color: 'var(--lc-text)', fontWeight: 600 }}>
                  TURN {tr.turn_seq ?? tr.i}
                  {loc ? <span style={{ color: 'var(--lc-dim)', fontWeight: 400 }}> · {loc}</span> : null}
                </div>
                {tr.commit ? <div style={{ fontSize: 11, color: 'var(--lc-faint)', marginTop: 2, fontFamily: 'var(--font-mono, monospace)' }}>{tr.commit.slice(0, 8)}</div> : null}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (active === 'pulse') {
    if (!data.latest) return <Placeholder text="当前会话还没有回合 —— 世界此刻会显示在这里。" />
    const label = sceneLabel(data.latest)
    const activeSouls = data.latest.souls || []
    return (
      <div className="stage-fade">
        <ModuleTitle cn="世界此刻" en="NOW" />
        {label ? (
          <div style={{ fontFamily: 'var(--font-display, serif)', fontSize: 21, marginTop: 12, color: 'var(--lc-text)' }}>{label}</div>
        ) : null}
        <div style={{ marginTop: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 12 }}>
          {activeSouls.map((s) => {
            const loc = soulLoc(s.reason)
            const near = nearPlayer(s.reason)
            return (
              <div key={s.instance_id} style={{ padding: 14, borderRadius: 12, border: '1px solid var(--lc-line)', background: 'var(--lc-panel)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <span style={{ width: 34, height: 34, borderRadius: '50%', background: near ? 'var(--lc-candle-soft)' : 'var(--lc-panel2)', color: near ? 'var(--lc-candle)' : 'var(--lc-dim)', display: 'grid', placeItems: 'center', fontSize: 14, fontWeight: 700 }}>
                    {(s.sid || '?').slice(0, 1).toUpperCase()}
                  </span>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--lc-text)' }}>{s.sid || s.instance_id}</div>
                    <div style={{ fontSize: 11, color: 'var(--lc-faint)' }}>{s.state || ''}</div>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--lc-dim)', marginTop: 10 }}>
                  📍 {loc || '—'}
                  {near ? <span style={{ color: 'var(--lc-candle)' }}> · 与你同处</span> : <span style={{ color: 'var(--lc-faint)' }}> · 在别处</span>}
                </div>
                {s.speech ? <div style={{ fontSize: 12, color: 'var(--lc-dim)', marginTop: 6, fontStyle: 'italic' }}>「{s.speech}」</div> : null}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (active === 'places') {
    if (!data.latest) return <Placeholder text="当前会话还没有回合 —— 地点与占用者会显示在这里。" />
    const acts = data.latest.souls || []
    const playerLoc = (data.latest.world_location || data.latest.location || '').split('/').pop() || ''
    const byLoc: Record<string, typeof acts> = {}
    for (const s of acts) {
      const loc = soulLoc(s.reason) || '未知'
      ;(byLoc[loc] ||= []).push(s)
    }
    const locs = Object.keys(byLoc)
    if (playerLoc && !locs.includes(playerLoc)) locs.unshift(playerLoc)
    return (
      <div className="stage-fade">
        <ModuleTitle cn="地点" en="PLACES" />
        <div style={{ marginTop: 18, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {locs.map((loc) => {
            const here = byLoc[loc] || []
            const isPlayerHere = loc === playerLoc
            return (
              <div key={loc} style={{ padding: 14, borderRadius: 12, border: `1px solid ${isPlayerHere ? 'var(--lc-candle)' : 'var(--lc-line)'}`, background: 'var(--lc-panel)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--lc-text)' }}>📍 {loc}</span>
                  {isPlayerHere ? <span style={{ fontSize: 11, color: 'var(--lc-candle)' }}>· 你在这里</span> : null}
                </div>
                {here.length ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {here.map((s) => (
                      <span key={s.instance_id} style={{ fontSize: 12, padding: '3px 10px', borderRadius: 999, background: 'var(--lc-panel2)', color: 'var(--lc-dim)' }}>
                        {s.sid || s.instance_id}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: 11.5, color: 'var(--lc-faint)', marginTop: 6 }}>（此刻无人）</div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (active === 'map') {
    if (!data.latest) return <Placeholder text="当前会话还没有回合 —— 地图会显示谁在哪。" />
    const acts = data.latest.souls || []
    const playerLoc = (data.latest.world_location || data.latest.location || '').split('/').pop() || ''
    return (
      <div className="stage-fade">
        <ModuleTitle cn="地图" en="MAP" />
        <div style={{ fontSize: 11, color: 'var(--lc-faint)', marginTop: 4 }}>世界大地图 · 谁在哪(可拖拽缩放 · 点节点看详情 · world_map 底图待接)</div>
        <WorldMapCanvas souls={acts} playerLoc={playerLoc} names={names} />
      </div>
    )
  }

  if (active === 'debug') {
    return (
      <div className="stage-fade">
        <ModuleTitle cn="Debug" en="4TH · RAW" />
        <div style={{ fontSize: 12, color: 'var(--lc-faint)', marginTop: 4, lineHeight: 1.7 }}>
          第四镜头 —— 现酒馆式游玩界面 + 原始 trace 收进这里(SIMULATION-PLATFORM:Debug 第四页)。仅 player 看。
        </div>
        <pre style={{ marginTop: 16, padding: 16, borderRadius: 12, border: '1px solid var(--lc-line)', background: 'var(--lc-panel)', fontSize: 11, lineHeight: 1.6, color: 'var(--lc-dim)', overflow: 'auto', maxHeight: 460, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {data.latest ? JSON.stringify(data.latest, null, 2).slice(0, 8000) : '(当前会话无 trace)'}
        </pre>
      </div>
    )
  }

  return <Placeholder text="待接数据。" />
}

function ModuleTitle({ cn, en }: { cn: string; en: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
      <span style={{ fontFamily: 'var(--font-display, serif)', fontSize: 22, color: 'var(--lc-text)' }}>{cn}</span>
      <span style={{ fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--lc-faint)' }}>{en}</span>
    </div>
  )
}

function Placeholder({ text }: { text: string }) {
  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '60%', minHeight: 200, color: 'var(--lc-faint)', fontSize: 13, textAlign: 'center', padding: 40, lineHeight: 1.9 }}>
      {text}
    </div>
  )
}
