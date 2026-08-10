// Stage i18n. The engine already localizes every play string the vanilla page
// reads (role.world, play.orch_souls, turn.prefix, …) — the stage fetches that
// table from GET /i18n and looks up keys there first. Boot-theater strings are
// stage-only (the engine never emitted them), so we carry a small fallback
// dict here in the four engine languages. T(key): engine table → local dict →
// key itself (so a missing string is visible, never blank).

import { useEffect, useState } from 'react'
import { useStageBackend } from './backend'

type Lang = 'en' | 'zh' | 'ja' | 'ko'

const BOOT: Record<string, Partial<Record<Lang, string>> & { en: string }> = {
  'boot.waking': {
    en: 'The world is waking…',
    zh: '世界正在苏醒…',
    ja: '世界が目覚めていく…',
    ko: '세계가 깨어나고 있습니다…',
  },
  'boot.world_awake': {
    en: 'World-agent awakened',
    zh: 'world-agent 已苏醒',
    ja: 'world-agent が目覚めた',
    ko: 'world-agent 가 깨어남',
  },
  'boot.souls_lighting': {
    en: 'Souls are lighting up…',
    zh: '灵魂逐个点亮…',
    ja: 'ソウルが灯っていく…',
    ko: '소울이 하나씩 켜집니다…',
  },
  'boot.first_words': {
    en: 'The first words are forming…',
    zh: '第一段叙事正在浮现…',
    ja: '最初の物語が浮かび上がる…',
    ko: '첫 이야기가 떠오릅니다…',
  },
  'boot.enter': {
    en: 'Entering the scene',
    zh: '正在进入现场',
    ja: '現場に入ります',
    ko: '현장으로 들어갑니다',
  },
  'stage.no_session': {
    en: 'No world is bound yet. Pick one from the archive.',
    zh: '还没有绑定世界。回档案室挑一个吧。',
    ja: 'まだ世界がありません。資料室から選んでください。',
    ko: '아직 바인딩된 세계가 없습니다. 자료실에서 골라주세요.',
  },
  'stage.back_study': {
    en: '⌂ Archive',
    zh: '⌂ 档案室',
    ja: '⌂ 資料室',
    ko: '⌂ 자료실',
  },
  'chat.open': { en: 'Chat', zh: '闲聊', ja: '会話', ko: '대화' },
  'chat.subtitle': {
    en: 'interlude · clock paused',
    zh: '幕间 · 时钟不走',
    ja: '幕間 · 時計は止まったまま',
    ko: '막간 · 시계는 멈춤',
  },
  'chat.close': { en: 'Close', zh: '收起', ja: '閉じる', ko: '닫기' },
  'chat.offsite': {
    en: 'She is not by your side right now.',
    zh: 'TA 现在不在你身边。',
    ja: '相手は今そばにいません。',
    ko: '상대는 지금 곁에 없습니다.',
  },
  'chat.placeholder': {
    en: 'Say something… (light chat, no turn passes)',
    zh: '说点什么…(轻聊,不消耗回合)',
    ja: '何か話す…(軽い会話,ターンは進みません)',
    ko: '말을 걸어보세요… (가벼운 대화, 턴 소모 없음)',
  },
  'chat.typing': { en: 'typing…', zh: '正在输入…', ja: '入力中…', ko: '입력 중…' },
  'chat.send': { en: 'Send', zh: '发送', ja: '送信', ko: '보내기' },
  'chat.you': { en: 'You', zh: '你', ja: 'あなた', ko: '나' },
  'chat.room_open': { en: '💬 Talk to the room', zh: '💬 此地闲聊', ja: '💬 この場で話す', ko: '💬 이곳에서 대화' },
  'chat.room_title': { en: 'Here', zh: '此地', ja: 'この場', ko: '이곳' },
  'chat.room_placeholder': {
    en: 'Say something to everyone here…',
    zh: '对在场所有人说点什么…',
    ja: 'この場の全員に話しかける…',
    ko: '이곳의 모두에게 말해보세요…',
  },
  'chat.room_empty': {
    en: 'No one else is here right now.',
    zh: '此刻这里没有别人。',
    ja: '今ここには誰もいません。',
    ko: '지금 여기엔 아무도 없습니다.',
  },
  'chat.listening': {
    en: 'is listening',
    zh: '在听(没接话)',
    ja: 'は聞いている',
    ko: '듣고 있음',
  },
  'stage.generating': {
    en: 'The world is unfolding… the model is composing, please wait',
    zh: '世界推演中… 模型正在生成，稍候',
    ja: '世界が展開中… モデルが生成しています、お待ちください',
    ko: '세계가 전개되는 중… 모델이 생성 중입니다, 잠시만요',
  },
  'stage.map': { en: 'Map', zh: '地图', ja: '地図', ko: '지도' },
  'map.unknown': { en: 'somewhere', zh: '未知之处', ja: 'どこか', ko: '어딘가' },
  'rail.turn_running_pending': {
    en: 'TURN · in progress',
    zh: 'TURN · 进行中',
    ja: 'TURN · 進行中',
    ko: 'TURN · 진행 중',
  },
  'rail.turn_running': {
    en: 'TURN {seq} · in progress',
    zh: 'TURN {seq} · 进行中',
    ja: 'TURN {seq} · 進行中',
    ko: 'TURN {seq} · 진행 중',
  },
  'rail.stage_world': { en: 'World thinking', zh: '世界思考', ja: '世界の思考', ko: '세계 사고' },
  'rail.stage_souls': { en: 'Souls acting', zh: '角色行动', ja: 'ソウル行動', ko: '소울 행동' },
  'rail.stage_ruling': { en: 'Ruling', zh: '位置裁定', ja: '裁定', ko: '판정' },
  'rail.stage_narrate': { en: 'Narrating', zh: '叙事成稿', ja: '物語生成', ko: '서사 작성' },
  'rail.acting': { en: '{name} is acting…', zh: '{name} 行动中…', ja: '{name} が動いている…', ko: '{name} 행동 중…' },
  'rail.acting_suffix': { en: 'acting', zh: '行动中', ja: '行動中', ko: '행동 중' },
  'rail.backstage': {
    en: 'backstage {n} · {done}✓',
    zh: '幕后 {n} 人 · {done}✓',
    ja: '舞台裏 {n} 人 · {done}✓',
    ko: '무대 뒤 {n}명 · {done}✓',
  },
  'rail.summary': {
    en: 'TURN {seq} · {n} souls · {s}s',
    zh: 'TURN {seq} · {n} souls · {s}s',
    ja: 'TURN {seq} · {n} souls · {s}s',
    ko: 'TURN {seq} · {n} souls · {s}s',
  },
}

export type T = (key: string, vars?: Record<string, string | number>) => string

function fill(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
}

export function makeT(engine: Record<string, string>, locale: string): T {
  const lang = (['en', 'zh', 'ja', 'ko'].includes(locale) ? locale : 'en') as Lang
  return (key, vars) => {
    if (Object.prototype.hasOwnProperty.call(engine, key)) return fill(engine[key], vars)
    const b = BOOT[key]
    if (b) return fill(b[lang] ?? b.en, vars)
    return fill(key, vars)
  }
}

// Fetch the engine string table once, expose a ready T. Falls back to the
// boot dict + key echo before the fetch resolves, so nothing flashes blank.
export function useStageStrings(): { t: T; locale: string } {
  const [table, setTable] = useState<{ strings: Record<string, string>; locale: string }>({
    strings: {},
    locale: 'en',
  })
  const backend = useStageBackend()
  useEffect(() => {
    let alive = true
    backend.getI18n().then((d) => {
      if (alive) setTable({ strings: d.strings || {}, locale: d.locale || 'en' })
    })
    return () => {
      alive = false
    }
  }, [])
  // 语言统一:stageClient.getI18n 带上 LocalShell 的 wl-local-lang pin,
  // 引擎直接返回该语言的完整表 —— 这里拿到什么就是什么。
  return { t: makeT(table.strings, table.locale), locale: table.locale }
}
