// Right column: one card per agent (world · souls · your viewpoint). Each
// shows a status dot (queued/running/done), the "where" line, and a running
// log of speech/action/perception mined from the trace bus. Psyche (灵魂心象)
// renders a soul's inner life when a soul_psyche event has landed.

import { useState } from 'react'
import { useStageBackend } from './backend'
import type { Lane } from './stageState'
import type { T } from './strings'

function clamp01(n: unknown): number | null {
  const v = Number(n)
  return isNaN(v) ? null : Math.max(0, Math.min(1, v))
}

function Bar({ cls, label, value }: { cls: string; label: string; value: unknown }) {
  const f = clamp01(value)
  if (!f) return null
  const pct = Math.round(f * 100)
  return (
    <div className={`lc-bar ${cls}`}>
      <span className="lbl">{label}</span>
      <span className="track">
        <span className="fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="pct">{pct}%</span>
    </div>
  )
}

// 立绘自适应(pencil 画布「变体·soul卡 竖横立绘」):加载后按宽高比分流 —
// ratio<0.8 竖图 → 3:4 英雄块(object-position:top 保脸)+ 位置角标;
// ≥0.8 横/方图 → banner 条 + 名行小圆头像;失败 → 首字母字牌。
// 探测期用原有小缩略(同一 src,命中缓存后切换无重载)。
type PortraitMode = 'none' | 'probe' | 'tall' | 'banner'

function LaneCard({ lane, t, onChat }: { lane: Lane; t: T; onChat?: (id: string, name: string) => void }) {
  const { imageUrl } = useStageBackend()
  const [ratio, setRatio] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)
  const isChar = lane.kind !== 'world'
  const initial = (lane.name || '?').slice(0, 1)
  const src = !isChar ? '' : lane.kind === 'player' ? imageUrl('player') : imageUrl('soul', lane.id)
  const mode: PortraitMode = !isChar || failed ? 'none' : ratio == null ? 'probe' : ratio < 0.8 ? 'tall' : 'banner'
  const probe = (
    <img
      className={mode === 'banner' ? 'lc-portrait mini' : 'lc-portrait'}
      src={src}
      alt=""
      onLoad={(e) => {
        const el = e.currentTarget
        if (el.naturalHeight > 0) setRatio(el.naturalWidth / el.naturalHeight)
      }}
      onError={() => setFailed(true)}
    />
  )
  const p = lane.psyche
  const stateKey =
    p &&
    {
      completed: 'psyche.state.completed',
      interrupted: 'psyche.state.interrupted',
      degraded: 'psyche.state.degraded',
    }[String(p.state || '').toLowerCase()]
  const voice = String(p?.inner_voice || '').trim()
  return (
    <div className="lc-lane" data-lane={lane.id}>
      {mode === 'tall' ? (
        <div className="lc-portrait-hero" data-testid="portrait-tall">
          <img src={src} alt="" />
          {lane.where ? <span className="lc-portrait-badge">● {lane.where.slice(0, 18)}</span> : null}
        </div>
      ) : null}
      {mode === 'banner' ? (
        <div className="lc-portrait-banner" data-testid="portrait-banner">
          <img src={src} alt="" />
        </div>
      ) : null}
      <h3>
        {mode === 'probe' || mode === 'banner' ? probe : null}
        {mode === 'none' && isChar ? <span className="lc-portrait noimg">{initial}</span> : null}
        <span className={`lc-dot ${lane.dot}`} />
        {lane.name}
        <span className="lc-role">{lane.where || lane.role}</span>
        {onChat && lane.kind === 'soul' ? (
          <button
            className="lc-chat-btn"
            title={t('chat.open')}
            data-testid={`chat-open-${lane.id}`}
            onClick={() => onChat(lane.id, lane.name)}
          >
            💬
          </button>
        ) : null}
      </h3>
      {p && (voice || stateKey || clamp01(p.confidence) || clamp01(p.urgency)) ? (
        <div className="lc-psyche">
          {stateKey ? <span className="lc-chip">{t(stateKey)}</span> : null}
          {voice ? <div className="voice">〝{voice}〞</div> : null}
          <Bar cls="confidence" label={t('psyche.confidence')} value={p.confidence} />
          <Bar cls="urgency" label={t('psyche.urgency')} value={p.urgency} />
        </div>
      ) : null}
      <div className="lc-log">
        {lane.logs.map((l, i) => (
          <div key={l.id >= 0 ? `l${l.id}` : `s${i}`} dangerouslySetInnerHTML={{ __html: l.html }} />
        ))}
        {lane.streaming ? <div className="lc-speech">{lane.streaming}</div> : null}
      </div>
      {lane.memory.length ? (
        <div className="lc-memory">
          {lane.memory.map((m, i) => (
            <div className="mitem" key={i}>
              {m}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function AgentLanes({
  lanes,
  order,
  t,
  onChat,
  onRoomChat,
}: {
  lanes: Record<string, Lane>
  order: string[]
  t: T
  onChat?: (id: string, name: string) => void
  onRoomChat?: () => void
}) {
  return (
    <div className="lc-right" data-testid="stage-lanes">
      <div className="lc-lanes-intro">
        {t('lanes.intro')}
        {onRoomChat ? (
          <button className="lc-chat-btn lc-room-btn" data-testid="room-open" onClick={onRoomChat}>
            {t('chat.room_open')}
          </button>
        ) : null}
      </div>
      {order.map((id) => (lanes[id] ? <LaneCard key={id} lane={lanes[id]} t={t} onChat={onChat} /> : null))}
    </div>
  )
}
