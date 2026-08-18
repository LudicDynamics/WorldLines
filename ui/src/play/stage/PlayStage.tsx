// PlayStage (D5) — the classic `neonrp web` play surface grown into the SPA.
// Full-bleed over the LocalApp chrome (position:fixed), themed by the inherited
// --lc-* tokens so black/white both read. Same-origin endpoints only; the
// engine API is untouched. The boot theater (D7) overlays the feed while a
// fresh game's opening turn is being composed.
//
// NOT a descendant of the Hub-blooded PlayPage — this is a fresh port of the
// content architecture in src/neonrp/webui/index.html.

import { Link } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { BootTheater } from '../boot/BootTheater'
import { AgentLanes } from './AgentLanes'
import { ChatDrawer, RoomChatDrawer } from './ChatDrawer'
import { InputBar } from './InputBar'
import { MapPanel } from './MapPanel'
import { ReplayBar, SettingsPopover } from './ReplayBar'
import { Transcript } from './Transcript'
import { usePlayStage } from './usePlayStage'
import { StageBackendProvider, localBackend, type StageBackend } from './backend'
import { computeOrigin } from '../playClient'
import './stage.css'

// 外壳:注入后端(默认同源 local),内核组件树一份代码两后端(D3/D5)。
export function PlayStage({ backend }: { backend?: StageBackend } = {}) {
  return (
    <StageBackendProvider value={backend ?? localBackend}>
      <StageInner />
    </StageBackendProvider>
  )
}

function StageInner() {
  const s = usePlayStage()
  const { state, t } = s
  const [draft, setDraft] = useState('')
  // 对话拍(T1/T2):当前打开的轻聊天 — 直聊(dm)或房间群聊(room);null=关。
  const [chat, setChat] = useState<
    { mode: 'dm'; iid: string; name: string } | { mode: 'room' } | null
  >(null)

  // 寻址接口(M24 §0.5):输入框打 @名字/# = TUI native 语法在 Web 的镜像。
  // 引擎统一解析(/say);@→开直聊抽屉(交换已落线程),#→开房间;
  // lane=world 或解析失败 → 原样走世界拍,寻址永不吞输入。
  const routedSend = useCallback(
    async (text: string) => {
      const tr = text.trim()
      if (/^[@@##]/.test(tr)) {
        try {
          const r = await fetch(`${computeOrigin()}/api/v1/play/say`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ text: tr }),
          })
          const d = (await r.json()) as {
            lane?: string
            target?: string
            name?: string
            text?: string
          }
          if (d.lane === 'dialogue' && d.target) {
            setChat({ mode: 'dm', iid: d.target, name: d.name || '' })
            return
          }
          if (d.lane === 'room') {
            setChat({ mode: 'room' })
            return
          }
          s.send(d.text ?? text)
          return
        } catch {
          /* 解析服务不可达 → 世界拍兜底 */
        }
      }
      s.send(text)
    },
    [s, setChat],
  )

  // 跳秒计时:回合真在生成(rail.running)时每秒刷新,给"生成中"提示条一个
  // 活着的信号 —— 治慢模型(如 Kimi 多智能体)下 boot 剧场 12→30s 消失后
  // world-agent 仍在生成、屏幕却空白、看着像卡死(niko 实测)。
  // No synchronous seed inside the effect (react-hooks/set-state-in-effect):
  // a stale `now` from an earlier run is always older than the new startedAt,
  // so the clamp below reads 0 until the first tick — which is exactly what
  // the seeded version showed during that first second anyway.
  const [now, setNow] = useState(0)
  useEffect(() => {
    if (!state.rail.running) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [state.rail.running])
  const genSecs =
    state.rail.running && state.rail.startedAt
      ? Math.max(0, Math.floor((now - state.rail.startedAt) / 1000))
      : 0

  if (s.noSession) {
    return (
      <div className="lc-stage" data-testid="stage-root">
        <div className="lc-head">
          <span className="lc-title">W O R L D L I N E S</span>
          <span style={{ flex: 1 }} />
          <Link to="/local" className="lc-link">
            {t('stage.back_study')}
          </Link>
        </div>
        <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: 'var(--lc-dim)', padding: 32, textAlign: 'center' }}>
          {t('stage.no_session')}
        </div>
      </div>
    )
  }

  return (
    <div className="lc-stage" data-testid="stage-root">
      <div className="lc-head">
        <span className="lc-title">W O R L D L I N E S</span>
        <span className="lc-meta" data-testid="stage-world">
          {state.world ? state.world.name : t('boot.waking')}
        </span>
        <span style={{ flex: 1 }} />
        <Link to="/local" className="lc-link" title={t('stage.back_study')}>
          {t('stage.back_study')}
        </Link>
        <SettingsPopover dev={s.dev} setDev={s.setDev} t={t} />
        {s.caps.traces ? (
        <ReplayBar
          open={s.replay.open}
          idx={s.replay.idx}
          total={s.replay.total}
          onOpen={s.openReplay}
          onStep={s.stepReplay}
          onClose={s.closeReplay}
          onRollback={() => {
            const rb = s.replay.block?.rollback
            if (rb) s.rollback(rb.commit, rb.turnSeq)
          }}
          canRollback={!!s.replay.block?.rollback}
          t={t}
        />
        ) : null}
      </div>

      <div className="lc-body">
        <div className="lc-left" data-testid="stage-transcript">
          <Transcript
            turns={state.turns}
            player={state.player}
            places={state.places}
            resume={s.resume}
            replayBlock={s.replay.open ? s.replay.block : null}
            bootActive={state.boot.active}
            rail={state.rail}
            turnSoulState={state.turnSoulState}
            lanes={state.lanes}
            castLocs={state.castLocs}
            boot={
              <BootTheater
                boot={state.boot}
                worldName={state.world?.name || ''}
                lanes={state.lanes}
                order={state.laneOrder}
                turnSoulState={state.turnSoulState}
                t={t}
              />
            }
            t={t}
            onRollback={s.rollback}
          />
          {state.rail.running && !state.boot.active ? (
            <div className="lc-status" data-testid="stage-generating" style={{ padding: '6px 14px' }}>
              <span className="lc-spin" />
              <span>
                {t('stage.generating')}
                {genSecs ? `（${genSecs}s）` : ''}
              </span>
            </div>
          ) : null}
          {state.choices.length ? (
            <div className="lc-choices" data-testid="stage-choices">
              {state.choices.map((opt, i) => (
                <button key={i} onClick={() => setDraft(opt)}>
                  {opt}
                </button>
              ))}
            </div>
          ) : null}
          <InputBar draft={draft} setDraft={setDraft} busy={state.busyInput} onSend={routedSend} t={t} />
        </div>

        <AgentLanes
          lanes={state.lanes}
          order={state.laneOrder}
          t={t}
          onChat={(iid, name) => setChat({ mode: 'dm', iid, name })}
          onRoomChat={() => setChat({ mode: 'room' })}
        />
        {chat?.mode === 'dm' ? (
          <ChatDrawer
            iid={chat.iid}
            fallbackName={chat.name}
            onClose={() => setChat(null)}
            onWorldAction={(text) => {
              setChat(null)
              s.send(text)
            }}
            t={t}
          />
        ) : null}
        {chat?.mode === 'room' ? (
          <RoomChatDrawer
            onClose={() => setChat(null)}
            onWorldAction={(text) => {
              setChat(null)
              s.send(text)
            }}
            t={t}
          />
        ) : null}
      </div>

      {state.timeline.length ? (
        <div className="lc-timeline" data-testid="stage-timeline">
          <span style={{ color: 'var(--lc-faint)' }}>timeline:</span>
          {state.timeline.map((row, i) => (
            <span key={i}>
              <span className="t">#{row.seq}</span> {state.places[row.loc.replace(/^loc:/, '')] || row.loc} · {row.commit}
            </span>
          ))}
        </div>
      ) : null}

      <MapPanel
        player={state.player}
        lanes={state.lanes}
        order={state.laneOrder}
        places={state.places}
        castLocs={state.castLocs}
        worldMap={state.worldMap}
        t={t}
      />
    </div>
  )
}
