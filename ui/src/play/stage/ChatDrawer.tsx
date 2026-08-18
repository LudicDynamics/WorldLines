// 对话拍(T1,HARNESS-TEAM-DESIGN)— 幕间直聊抽屉。
// lane=算力契约的 UI 面:IM 语法(气泡/正在输入),与世界拍的叙事舞台
// 视觉语法截然分开;时钟不走、回合不加。同场景门在引擎侧,这里对
// not-co-located 优雅降级(「她不在你身边」)。
// MVP 直连本地 /api/v1/play/chat;hosted 网关支持归 T2(收件箱改造)。

import { useCallback, useEffect, useRef, useState } from 'react'
import type { T } from './strings'
import { computeOrigin } from '../playClient'

type ChatRow = { role: string; text: string; ts?: string }
type RoomRow = { who: string; text: string; ts?: string }
// 升级签(M24:拍是引擎概念,边界由 UI 接驳)—— 聊天里说了移动/行动,
// 气泡下出一枚签;点了才把那句话送进世界拍,不点只是聊过。
type WorldIntent = { kind: string; target: string | null; label: string } | null

export function ChatDrawer({
  iid,
  fallbackName,
  onClose,
  onWorldAction,
  t,
}: {
  iid: string
  fallbackName: string
  onClose: () => void
  onWorldAction?: (text: string) => void
  t: T
}) {
  const [thread, setThread] = useState<ChatRow[]>([])
  const [name, setName] = useState(fallbackName)
  const [coLocated, setCoLocated] = useState<boolean | null>(null)
  const [medium, setMedium] = useState<string | null>(null) // 远程媒介(如 手机)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [intent, setIntent] = useState<{ label: string; text: string } | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)

  const scrollEnd = useCallback(() => {
    requestAnimationFrame(() => {
      const el = bodyRef.current
      if (el) el.scrollTop = el.scrollHeight
    })
  }, [])

  useEffect(() => {
    let dead = false
    ;(async () => {
      try {
        const r = await fetch(`${computeOrigin()}/api/v1/play/chat/${encodeURIComponent(iid)}`, { credentials: 'include' })
        const d = (await r.json()) as {
          ok?: boolean
          co_located?: boolean
          remote?: boolean
          medium?: string | null
          name?: string | null
          thread?: ChatRow[]
        }
        if (dead) return
        setCoLocated(!!d.co_located)
        setMedium(d.remote ? d.medium || '讯息' : null)
        if (d.name) setName(d.name)
        setThread(Array.isArray(d.thread) ? d.thread : [])
        scrollEnd()
      } catch {
        if (!dead) setCoLocated(false)
      }
    })()
    return () => {
      dead = true
    }
  }, [iid, scrollEnd])

  const send = useCallback(async () => {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    setErr('')
    setBusy(true)
    setThread((p) => [...p, { role: 'player', text }])
    scrollEnd()
    try {
      const r = await fetch(`${computeOrigin()}/api/v1/play/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ iid, text }),
      })
      const d = (await r.json()) as {
        ok?: boolean
        reply?: string
        error?: string
        world_intent?: WorldIntent
      }
      if (d.ok && d.reply) {
        setThread((p) => [...p, { role: 'soul', text: d.reply! }])
        setIntent(d.world_intent ? { label: d.world_intent.label, text } : null)
      } else {
        setErr(d.error === 'not-co-located' ? t('chat.offsite') : d.error || 'error')
      }
    } catch (e) {
      setErr(String(e).slice(0, 120))
    } finally {
      setBusy(false)
      scrollEnd()
    }
  }, [draft, busy, iid, scrollEnd, t])

  return (
    <div className="lc-chat-drawer" data-testid="chat-drawer">
      <div className="lc-chat-head">
        <span className="lc-chat-name">{name}</span>
        <span className="lc-chat-sub">
          {medium ? `📱 ${medium} · ` : ''}
          {t('chat.subtitle')}
        </span>
        <span style={{ flex: 1 }} />
        <button className="lc-chat-close" onClick={onClose} title={t('chat.close')}>
          ✕
        </button>
      </div>
      <div className="lc-chat-body" ref={bodyRef}>
        {coLocated === false ? (
          <div className="lc-chat-offsite">{t('chat.offsite')}</div>
        ) : null}
        {thread.map((r, i) => (
          <div key={i} className={`lc-chat-msg ${r.role === 'player' ? 'me' : 'her'}`}>
            {r.role !== 'player' ? <span className="who">{name}</span> : null}
            <span className="bubble">{r.text}</span>
          </div>
        ))}
        {busy ? (
          <div className="lc-chat-msg her">
            <span className="who">{name}</span>
            <span className="bubble typing">
              <span className="lc-spin" /> {t('chat.typing')}
            </span>
          </div>
        ) : null}
        {intent && onWorldAction ? (
          <div className="lc-chat-intent">
            <button
              onClick={() => {
                onWorldAction(intent.text)
                setIntent(null)
                onClose()
              }}
            >
              {intent.label}
            </button>
          </div>
        ) : null}
        {err ? <div className="lc-chat-err">⚠ {err}</div> : null}
      </div>
      <div className="lc-chat-input">
        <input
          value={draft}
          disabled={coLocated === false}
          placeholder={coLocated === false ? t('chat.offsite') : t('chat.placeholder')}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) send()
            if (e.key === 'Escape') onClose()
          }}
        />
        <button onClick={send} disabled={busy || coLocated === false}>
          {t('chat.send')}
        </button>
      </div>
    </div>
  )
}

// 群聊(T2)— 房间频道:一句话对在场所有人;谁接话由各 soul 自选,
// 沉默者显示「在听」。复用直聊抽屉的 IM 语法。
export function RoomChatDrawer({
  onClose,
  onWorldAction,
  t,
}: {
  onClose: () => void
  onWorldAction?: (text: string) => void
  t: T
}) {
  const [thread, setThread] = useState<RoomRow[]>([])
  const [names, setNames] = useState<string[]>([])
  const [listening, setListening] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [intent, setIntent] = useState<{ label: string; text: string } | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)

  const scrollEnd = useCallback(() => {
    requestAnimationFrame(() => {
      const el = bodyRef.current
      if (el) el.scrollTop = el.scrollHeight
    })
  }, [])

  useEffect(() => {
    let dead = false
    ;(async () => {
      try {
        const r = await fetch(`${computeOrigin()}/api/v1/play/chat-room`, { credentials: 'include' })
        const d = (await r.json()) as {
          ok?: boolean
          participants?: { iid: string; name: string }[]
          thread?: RoomRow[]
        }
        if (dead) return
        setNames((d.participants || []).map((p) => p.name))
        setThread(Array.isArray(d.thread) ? d.thread : [])
        scrollEnd()
      } catch {
        /* 房间为空时输入自会被拒 */
      }
    })()
    return () => {
      dead = true
    }
  }, [scrollEnd])

  const send = useCallback(async () => {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    setErr('')
    setListening([])
    setBusy(true)
    setThread((p) => [...p, { who: t('chat.you'), text }])
    scrollEnd()
    try {
      const r = await fetch(`${computeOrigin()}/api/v1/play/chat-room`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const d = (await r.json()) as {
        ok?: boolean
        error?: string
        replies?: { name: string; reply: string | null }[]
        world_intent?: WorldIntent
      }
      if (d.ok) {
        const spoke = (d.replies || []).filter((x) => x.reply)
        setThread((p) => [...p, ...spoke.map((x) => ({ who: x.name, text: x.reply! }))])
        setListening((d.replies || []).filter((x) => !x.reply).map((x) => x.name))
        setIntent(d.world_intent ? { label: d.world_intent.label, text } : null)
      } else {
        setErr(d.error === 'no-souls-here' ? t('chat.room_empty') : d.error || 'error')
      }
    } catch (e) {
      setErr(String(e).slice(0, 120))
    } finally {
      setBusy(false)
      scrollEnd()
    }
  }, [draft, busy, scrollEnd, t])

  return (
    <div className="lc-chat-drawer" data-testid="room-drawer">
      <div className="lc-chat-head">
        <span className="lc-chat-name">{t('chat.room_title')}</span>
        <span className="lc-chat-sub">
          {names.length ? names.join('、') : ''} · {t('chat.subtitle')}
        </span>
        <span style={{ flex: 1 }} />
        <button className="lc-chat-close" onClick={onClose} title={t('chat.close')}>
          ✕
        </button>
      </div>
      <div className="lc-chat-body" ref={bodyRef}>
        {thread.map((r, i) => (
          <div key={i} className={`lc-chat-msg ${r.who === t('chat.you') || r.who === '玩家' ? 'me' : 'her'}`}>
            {r.who !== t('chat.you') && r.who !== '玩家' ? <span className="who">{r.who}</span> : null}
            <span className="bubble">{r.text}</span>
          </div>
        ))}
        {busy ? (
          <div className="lc-chat-msg her">
            <span className="bubble typing">
              <span className="lc-spin" /> {t('chat.typing')}
            </span>
          </div>
        ) : null}
        {listening.length ? (
          <div className="lc-chat-listening">
            {listening.join('、')} {t('chat.listening')}
          </div>
        ) : null}
        {intent && onWorldAction ? (
          <div className="lc-chat-intent">
            <button
              onClick={() => {
                onWorldAction(intent.text)
                setIntent(null)
                onClose()
              }}
            >
              {intent.label}
            </button>
          </div>
        ) : null}
        {err ? <div className="lc-chat-err">⚠ {err}</div> : null}
      </div>
      <div className="lc-chat-input">
        <input
          value={draft}
          placeholder={t('chat.room_placeholder')}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) send()
            if (e.key === 'Escape') onClose()
          }}
        />
        <button onClick={send} disabled={busy}>
          {t('chat.send')}
        </button>
      </div>
    </div>
  )
}
