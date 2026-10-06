// LocalShell i18n (en · zh · ja · ko) — the local engine's own string table.
//
// Distinct from shared/i18n.tsx (that one is the Hub's, keyed on `rp-hub:lang`
// with a Hub-only dict). This surface has its own register and its own default
// rule: the language follows the engine locale (GET /i18n → {locale}) unless
// the user pins one from the header. The pin lives in localStorage under
// `wl-local-lang` and always wins.
//
// No React context / provider — LocalApp mounts from main-local.tsx which this
// module cannot wrap. Instead the current language is a tiny module-level store
// read through useSyncExternalStore, so every /local/* page can call useLocalT()
// with no ancestor setup. `t(key)` falls back to English, then to the key
// itself, so a missing string is visible, never blank.
import { useSyncExternalStore } from 'react'
import { localEndpoint } from './localClient'

export const LANGS = ['en', 'zh', 'ja', 'ko'] as const
export type Lang = (typeof LANGS)[number]

export const LANG_LABEL: Record<Lang, string> = {
  en: 'EN',
  zh: '中',
  ja: '日',
  ko: '한',
}

const STORE_KEY = 'wl-local-lang'

function normalize(v: string | null | undefined): Lang | null {
  const s = (v || '').toLowerCase()
  if (s.startsWith('zh')) return 'zh'
  if (s.startsWith('ja')) return 'ja'
  if (s.startsWith('ko')) return 'ko'
  if (s.startsWith('en')) return 'en'
  return null
}

function pinned(): Lang | null {
  try {
    return normalize(localStorage.getItem(STORE_KEY))
  } catch {
    return null
  }
}

function initialLang(): Lang {
  // A user pin always wins; otherwise a provisional guess from the browser so
  // nothing flashes before the async engine-locale fetch resolves.
  return pinned() ?? normalize(typeof navigator !== 'undefined' ? navigator.language : 'en') ?? 'en'
}

// ── module-level store ────────────────────────────────────────────────────
let current: Lang = initialLang()
const listeners = new Set<() => void>()

function setLang(l: Lang, persist = true) {
  if (!(LANGS as readonly string[]).includes(l)) return
  current = l
  if (persist) {
    try {
      localStorage.setItem(STORE_KEY, l)
    } catch {
      /* storage off */
    }
  }
  listeners.forEach((f) => f())
}

// Default = engine locale, fetched once. Only applied while the user has not
// pinned a language (a pin, present now or set during the fetch, wins).
let bootstrapped = false
function bootstrap() {
  if (bootstrapped) return
  bootstrapped = true
  if (pinned()) return
  fetch(`${localEndpoint()}/i18n`, { credentials: 'include' })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      const loc = normalize(d?.locale)
      if (loc && !pinned()) setLang(loc, false)
    })
    .catch(() => {
      /* engine down — keep the provisional guess */
    })
}
// C10:严禁模块顶层调用 —— import 时 main-hub 的 setLocalApiBase 还没
// 执行,localEndpoint() 落在 VITE_PLAY_ENDPOINT 裸值上(hosted 下 =
// compute 根),/i18n 无引擎前缀直打 → CORS 拦截。改为 useLocalT 首次
// 订阅时惰性引导(bootstrapped 幂等)。

function subscribe(cb: () => void): () => void {
  bootstrap()
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

// ── lookup ────────────────────────────────────────────────────────────────
export type T = (key: string, vars?: Record<string, string | number>) => string

function fill(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
}

export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const e = STRINGS[key]
  if (!e) return fill(key, vars)
  return fill(e[lang] ?? e.en ?? key, vars)
}

export function useLocalT(): { lang: Lang; setLang: (l: Lang) => void; t: T } {
  const lang = useSyncExternalStore(subscribe, () => current, () => current)
  return {
    lang,
    setLang: (l: Lang) => setLang(l, true),
    t: (key, vars) => translate(lang, key, vars),
  }
}

// ── string table ──────────────────────────────────────────────────────────
// zh is the baseline (existing hardcoded wording, verbatim). Terminology kept
// in sync with the engine tables (src/neonrp/webui/i18n.py, tui/i18n.py):
// 档案室 = Library / 資料室 / 자료실 · 世界 = World / ワールド / 월드.
type Entry = Partial<Record<Lang, string>> & { en: string }

const STRINGS: Record<string, Entry> = {
  // ── Observatory ──────────────────────────────────────────────
  'observe.error.traces': { en: 'Could not read traces — {error}', zh: 'trace 读取出错 —— {error}', ja: 'トレースの読み込みに失敗しました — {error}', ko: '트레이스를 읽지 못했습니다 — {error}' },
  'observe.error.bindSave': { en: 'Could not open save — {error}', zh: '绑定存档出错 —— {error}', ja: 'セーブデータを開けませんでした — {error}', ko: '저장 데이터를 열지 못했습니다 — {error}' },
  'observe.error.start': { en: 'Could not start game — {error}', zh: '开局出错 —— {error}', ja: 'ゲームを開始できませんでした — {error}', ko: '게임을 시작하지 못했습니다 — {error}' },
  'observe.error.saves': { en: 'Could not read saves — {error}', zh: '存档列表读取出错 —— {error}', ja: 'セーブ一覧の読み込みに失敗しました — {error}', ko: '저장 목록을 읽지 못했습니다 — {error}' },
  'observe.error.partial': { en: '(Showing the data that is still available.)', zh: '(仍显示能读到的部分,不崩)', ja: '（取得できたデータのみ表示しています）', ko: '(가져온 데이터만 표시합니다.)' },
  'observe.choose.title': { en: 'Choose a world to return to', zh: '选一个世界回去', ja: '戻るワールドを選ぶ', ko: '돌아갈 월드 선택' },
  'observe.choose.description': { en: 'Observe from the outside — start a world or return to an old story. You can step in and play at any time.', zh: '观察是隔着看 —— 挑个世界开新局,或回到一段旧的;进去随时可附身下场。', ja: '外から世界を眺める画面です。新しく始めるか、以前の物語へ戻りましょう。いつでも中に入ってプレイできます。', ko: '밖에서 월드를 관찰합니다. 새로 시작하거나 지난 이야기로 돌아가세요. 언제든 직접 들어가 플레이할 수 있습니다.' },
  'observe.choose.new': { en: 'New game · Choose a world', zh: '开新局 · 选个世界', ja: 'ニューゲーム · ワールドを選択', ko: '새 게임 · 월드 선택' },
  'observe.choose.worldHint': { en: 'Start here and watch it come alive.', zh: '开一局,下场看它活起来。', ja: 'ここから始めて、動き出す世界を見届ける。', ko: '여기서 시작해 살아 움직이는 월드를 만나세요.' },
  'observe.choose.resume': { en: 'Saved games · Continue a story', zh: '回到存档 · 续一段', ja: 'セーブデータ · 物語の続きを見る', ko: '저장 데이터 · 이야기 계속하기' },
  'observe.choose.last': { en: 'Last: {time}', zh: '上次 {time}', ja: '前回 {time}', ko: '최근 {time}' },
  'observe.choose.noStory': { en: 'No story yet — enter to begin.', zh: '还没有故事 —— 进去开始。', ja: '物語はまだありません — 入って始めましょう。', ko: '아직 이야기가 없습니다 — 들어가서 시작하세요.' },
  'observe.choose.noSaves': { en: 'No saved games yet — choose a world above to begin.', zh: '还没有存档 —— 从上面挑个世界开一局。', ja: 'セーブデータはまだありません — 上からワールドを選んで始めましょう。', ko: '저장 데이터가 없습니다 — 위에서 월드를 골라 시작하세요.' },
  'observe.changeWorld': { en: 'Choose another world', zh: '换一个世界', ja: '別のワールドを選ぶ', ko: '다른 월드 선택' },
  'observe.watch.title': { en: 'Watch', zh: '挂机 · Watch', ja: 'ウォッチ · Watch', ko: '관찰 · Watch' },
  'observe.turnCount': { en: '{count} turns', zh: '回合 {count}', ja: '{count} ターン', ko: '{count} 턴' },
  'observe.watch.active': { en: 'Watching · every {seconds}s', zh: '挂机中 · 每 {seconds}s', ja: '監視中 · {seconds}秒ごと', ko: '관찰 중 · {seconds}초마다' },
  'observe.watch.start': { en: 'Watch (auto refresh)', zh: '挂机(自动刷新)', ja: 'ウォッチ（自動更新）', ko: '관찰(자동 새로고침)' },
  'observe.watch.interval': { en: 'Interval', zh: '间隔', ja: '間隔', ko: '간격' },
  'observe.seconds': { en: '{count} sec', zh: '{count} 秒', ja: '{count} 秒', ko: '{count}초' },
  'observe.minutes': { en: '{count} min', zh: '{count} 分', ja: '{count} 分', ko: '{count}분' },
  'observe.watch.refresh': { en: 'Refresh now', zh: '手动刷新一次', ja: '今すぐ更新', ko: '지금 새로고침' },
  'observe.watch.note': { en: 'Engine auto-tick is not connected yet; this currently refreshes the observation.', zh: '后台自动推进(引擎 auto-tick)待接;现为观察刷新。', ja: 'エンジンの自動進行は未接続です。現在は観測データのみ更新します。', ko: '엔진 자동 진행은 아직 연결되지 않았으며 현재 관찰 데이터만 새로고침합니다.' },
  'observe.replay.title': { en: 'Timeline · Replay', zh: '时间轴 · Replay', ja: 'タイムライン · Replay', ko: '타임라인 · Replay' },
  'observe.replay.position': { en: 'Turn {current}/{total}', zh: '回合 {current}/{total}', ja: 'ターン {current}/{total}', ko: '턴 {current}/{total}' },
  'observe.replay.playing': { en: 'Replaying', zh: '回放中', ja: 'リプレイ中', ko: '리플레이 중' },
  'observe.replay.play': { en: 'Replay', zh: '回放', ja: 'リプレイ', ko: '리플레이' },
  'observe.replay.returnNow': { en: 'Return to now', zh: '回到现在', ja: '現在に戻る', ko: '현재로 돌아가기' },
  'observe.now': { en: 'Now', zh: '现在', ja: '現在', ko: '현재' },
  'observe.channels': { en: 'Channels', zh: '频道 · Channels', ja: 'チャンネル · Channels', ko: '채널 · Channels' },
  'observe.channel.world': { en: 'World', zh: '世界', ja: 'ワールド', ko: '월드' },
  'observe.channel.here': { en: 'Here', zh: '此地', ja: 'この場所', ko: '이곳' },
  'observe.channel.play': { en: 'Play · clock runs', zh: '下场·时钟走', ja: 'プレイ · 時間進行', ko: '플레이 · 시간 진행' },
  'observe.channel.interlude': { en: 'Interlude', zh: '幕间', ja: '幕間', ko: '막간' },
  'observe.sameScene': { en: 'Here', zh: '同场', ja: '同じ場所', ko: '같은 장소' },
  'observe.withYou': { en: 'With you', zh: '与你同场', ja: 'あなたと同じ場所', ko: '나와 같은 장소' },
  'observe.elsewhere': { en: 'Elsewhere', zh: '在别处', ja: '別の場所', ko: '다른 장소' },
  'observe.lenses': { en: 'Lenses', zh: '镜头 · Lenses', ja: 'レンズ · Lenses', ko: '렌즈 · Lenses' },
  'observe.channel.help': { en: '◉ World = play (clock runs) · @/#/lenses = interlude (clock stops). Full-screen stage: ', zh: '◉ 世界=下场(时钟走)· @/#/镜头=幕间(时钟停)。旧全屏舞台: ', ja: '◉ ワールド＝プレイ（時間進行）· @/#/レンズ＝幕間（時間停止）。全画面ステージ: ', ko: '◉ 월드=플레이(시간 진행) · @/#/렌즈=막간(시간 정지). 전체 화면 스테이지: ' },
  'observe.open': { en: 'Open', zh: '打开', ja: '開く', ko: '열기' },
  'observe.present': { en: 'Present', zh: '在场 · Present', ja: '登場中 · Present', ko: '등장 중 · Present' },
  'observe.present.empty': { en: '(After one turn, characters present here will appear.)', zh: '(走一回合后,这里显示谁在场)', ja: '（1ターン進むと、ここにいるキャラクターが表示されます）', ko: '(한 턴 진행하면 이곳의 캐릭터가 표시됩니다.)' },
  'observe.module.now': { en: 'World now', zh: '世界此刻', ja: '現在のワールド', ko: '지금의 월드' },
  'observe.module.feed': { en: 'World feed', zh: '世界动态', ja: 'ワールドフィード', ko: '월드 피드' },
  'observe.module.map': { en: 'Map', zh: '地图', ja: 'マップ', ko: '지도' },
  'observe.module.characters': { en: 'Characters', zh: '角色', ja: 'キャラクター', ko: '캐릭터' },
  'observe.module.places': { en: 'Places', zh: '地点', ja: '場所', ko: '장소' },
  'observe.module.debug': { en: 'Debug', zh: 'Debug', ja: 'デバッグ', ko: '디버그' },
  'observe.empty.noWorld': { en: 'There is no world to observe. Import or create one in the studio first.', zh: '没有世界可观察。先在书房导入 / 创建一个世界。', ja: '観測できるワールドがありません。先に創作画面でインポートまたは作成してください。', ko: '관찰할 월드가 없습니다. 먼저 제작 화면에서 가져오거나 만드세요.' },
  'observe.empty.feed': { en: 'This session has no turns yet — play a world and its turn-by-turn activity will appear here.', zh: '当前会话还没有回合 —— 先玩一个世界,它的逐回合动态会在这里流动。', ja: 'このセッションにはまだターンがありません。プレイすると、ターンごとの動きがここに表示されます。', ko: '이 세션에는 아직 턴이 없습니다. 플레이하면 턴별 움직임이 여기에 표시됩니다.' },
  'observe.empty.now': { en: 'This session has no turns yet — the current world will appear here.', zh: '当前会话还没有回合 —— 世界此刻会显示在这里。', ja: 'このセッションにはまだターンがありません。現在のワールドがここに表示されます。', ko: '이 세션에는 아직 턴이 없습니다. 현재 월드가 여기에 표시됩니다.' },
  'observe.empty.places': { en: 'This session has no turns yet — places and their occupants will appear here.', zh: '当前会话还没有回合 —— 地点与占用者会显示在这里。', ja: 'このセッションにはまだターンがありません。場所とそこにいる人物がここに表示されます。', ko: '이 세션에는 아직 턴이 없습니다. 장소와 그곳의 인물이 여기에 표시됩니다.' },
  'observe.empty.map': { en: 'This session has no turns yet — the map will show where everyone is.', zh: '当前会话还没有回合 —— 地图会显示谁在哪。', ja: 'このセッションにはまだターンがありません。マップに皆の居場所が表示されます。', ko: '이 세션에는 아직 턴이 없습니다. 지도에 모두의 위치가 표시됩니다.' },
  'observe.empty.pending': { en: 'Data connection pending.', zh: '待接数据。', ja: 'データ接続は準備中です。', ko: '데이터 연결 준비 중입니다.' },
  'observe.feed.summary': { en: 'Observing current session · {count} turns', zh: '观察:当前会话 · {count} 回合', ja: '現在のセッションを観測中 · {count} ターン', ko: '현재 세션 관찰 중 · {count} 턴' },
  'observe.unknown': { en: 'Unknown', zh: '未知', ja: '不明', ko: '알 수 없음' },
  'observe.youAreHere': { en: 'You are here', zh: '你在这里', ja: '現在地', ko: '현재 위치' },
  'observe.place.empty': { en: '(No one here now)', zh: '（此刻无人）', ja: '（現在は誰もいません）', ko: '(현재 아무도 없음)' },
  'observe.map.help': { en: 'World map · See who is where (drag to pan · scroll to zoom · select a node for details · world_map background coming later)', zh: '世界大地图 · 谁在哪(可拖拽缩放 · 点节点看详情 · world_map 底图待接)', ja: 'ワールドマップ · 居場所を確認（ドラッグで移動 · スクロールで拡大縮小 · ノード選択で詳細 · world_map 背景は準備中）', ko: '월드 지도 · 위치 확인(드래그 이동 · 스크롤 확대/축소 · 노드 선택으로 상세 보기 · world_map 배경 준비 중)' },
  'observe.debug.description': { en: 'Fourth lens — the current tavern-style play view and raw trace are collected here. Player only.', zh: '第四镜头 —— 现酒馆式游玩界面 + 原始 trace 收进这里(SIMULATION-PLATFORM:Debug 第四页)。仅 player 看。', ja: '第4レンズ — 現在のTavern形式プレイ画面と生のトレースをまとめて表示します。プレイヤー専用です。', ko: '네 번째 렌즈 — 현재 Tavern 형식 플레이 화면과 원본 트레이스를 함께 표시합니다. 플레이어 전용입니다.' },
  'observe.debug.noTrace': { en: '(No trace in this session)', zh: '(当前会话无 trace)', ja: '（このセッションにはトレースがありません）', ko: '(이 세션에는 트레이스가 없습니다)' },

  // ── LocalApp (chrome) ────────────────────────────────────────
  'app.local': { en: 'local', zh: '本地', ja: 'ローカル', ko: '로컬' },
  'nav.home': { en: 'Home', zh: '首页', ja: 'ホーム', ko: '홈' },
  'nav.play': { en: 'Play', zh: '游玩', ja: 'プレイ', ko: '플레이' },
  'nav.observe': { en: 'Play · Observe', zh: '游玩 · 观察', ja: 'プレイ · 観測', ko: '플레이 · 관찰' },
  'nav.create': { en: 'Create', zh: '创作', ja: '創作', ko: '창작' },
  'nav.library': { en: 'Archive', zh: '档案室', ja: '資料室', ko: '자료실' },
  'nav.settings': { en: 'Settings', zh: '设置', ja: '設定', ko: '설정' },
  'welcome.imageTab': { en: 'Images (optional)', zh: '图像(可选)', ja: '画像(任意)', ko: '이미지(선택)' },
  'welcome.imageDesc': {
    en: 'Portrait & cover generation. Optional — you can play without it.',
    zh: '立绘与封面生成。可选 —— 不配也能正常游玩。',
    ja: '立ち絵とカバー生成。任意 —— なくてもプレイできます。',
    ko: '일러스트와 커버 생성. 선택 사항 — 없어도 플레이 가능합니다.',
  },
  'welcome.imageAdvanced': {
    en: 'Advanced options', zh: '高级选项', ja: '詳細設定', ko: '고급 옵션',
  },
  'settings.language': { en: 'Language', zh: '语言', ja: '言語', ko: '언어' },
  'settings.languageDesc': {
    en: 'Defaults to the engine locale; your pick here wins everywhere (UI + play surface).',
    zh: '默认跟随引擎语言;在这里选定后,全站(界面+游玩现场)以你的选择为准。',
    ja: '既定はエンジンの言語。ここで選ぶと全体(UI+プレイ画面)に適用されます。',
    ko: '기본은 엔진 언어. 여기서 선택하면 전체(UI+플레이)에 적용됩니다.',
  },
  'app.themeToggle': { en: 'Switch palette', zh: '切换配色', ja: 'テーマ切替', ko: '테마 전환' },
  'app.toLight': { en: 'Switch to light', zh: '切到白色', ja: 'ライトに切替', ko: '라이트로 전환' },
  'app.toDark': { en: 'Switch to dark', zh: '切到黑色', ja: 'ダークに切替', ko: '다크로 전환' },
  'app.engineDown': {
    en: '● engine not running — run `neonrp web` first',
    zh: '● 引擎未启动 — 先跑 `neonrp web`',
    ja: '● エンジン未起動 — 先に `neonrp web` を実行',
    ko: '● 엔진 미실행 — 먼저 `neonrp web` 실행',
  },
  'app.localEngine': { en: 'local engine', zh: 'local engine', ja: 'local engine', ko: 'local engine' },
  'app.connecting': { en: 'connecting…', zh: 'connecting…', ja: 'connecting…', ko: 'connecting…' },
  'app.cantConnect': {
    en: 'Cannot reach the local engine ({ep}).',
    zh: '连接不上本地引擎({ep})。',
    ja: 'ローカルエンジンに接続できません({ep})。',
    ko: '로컬 엔진에 연결할 수 없습니다({ep}).',
  },

  // ── LocalWelcome ─────────────────────────────────────────────
  'welcome.tagline': {
    en: 'Cross the threshold　weave your world lines',
    zh: '跨越门扉　编织你的世界线',
    ja: '扉を越え　あなたの世界線を紡ぐ',
    ko: '문을 넘어　당신의 세계선을 엮다',
  },
  'welcome.saving': { en: 'Saving…', zh: '保存中…', ja: '保存中…', ko: '저장 중…' },
  'welcome.begin': { en: '▸　Begin the journey', zh: '▸　开启旅程', ja: '▸　旅を始める', ko: '▸　여정 시작' },
  'welcome.apiSettings': { en: 'API　settings', zh: 'API　设置', ja: 'API　設定', ko: 'API　설정' },
  'welcome.modelAccess': { en: 'Model access', zh: '模型接入', ja: 'モデル接続', ko: '모델 연결' },
  'welcome.modelAccessHint': {
    en: 'Pick an LLM to start your first journey. Credentials stay on this machine (~/.neonrp/config.json).',
    zh: '选一个 LLM,开始你的第一段旅程。凭证只存本机(~/.neonrp/config.json)。',
    ja: 'LLM を選んで最初の旅を始めましょう。認証情報はこの端末のみに保存(~/.neonrp/config.json)。',
    ko: 'LLM 을 골라 첫 여정을 시작하세요. 자격 증명은 이 기기에만 저장됩니다(~/.neonrp/config.json).',
  },
  'welcome.saveAndBegin': { en: 'Save & begin', zh: '保存并开启旅程', ja: '保存して旅を始める', ko: '저장하고 시작' },
  'welcome.beginShort': { en: '▸ Begin the journey', zh: '▸ 开启旅程', ja: '▸ 旅を始める', ko: '▸ 여정 시작' },

  // ── LocalHome ────────────────────────────────────────────────
  'home.continue': { en: 'CONTINUE', zh: '继续 · CONTINUE', ja: '続き · CONTINUE', ko: '이어하기 · CONTINUE' },
  'home.minAgo': { en: '{n} min ago', zh: '{n} 分钟前', ja: '{n} 分前', ko: '{n} 분 전' },
  'home.hourAgo': { en: '{n} h ago', zh: '{n} 小时前', ja: '{n} 時間前', ko: '{n} 시간 전' },
  'home.dayAgo': { en: '{n} d ago', zh: '{n} 天前', ja: '{n} 日前', ko: '{n} 일 전' },
  'home.waitingForYou': { en: '{names} waiting for you', zh: '{names} 在等你', ja: '{names} が待っています', ko: '{names} 님이 기다립니다' },
  'home.respond': { en: 'Respond ▸', zh: '回应 ▸', ja: '応じる ▸', ko: '응답 ▸' },
  'home.doors': { en: 'DOORS', zh: '入口 · DOORS', ja: '入口 · DOORS', ko: '입구 · DOORS' },
  'home.playTitle': { en: 'Play', zh: '游玩', ja: 'プレイ', ko: '플레이' },
  'home.playDesc': {
    en: 'Resume or start a run — built-in worlds and your own',
    zh: '继续或新开一局 — 内置世界与你的世界',
    ja: '続きまたは新規プレイ — 内蔵ワールドとあなたのワールド',
    ko: '이어하기 또는 새 플레이 — 내장 월드와 내 월드',
  },
  'home.createTitle': { en: 'Create', zh: '创作', ja: '創作', ko: '창작' },
  'home.createDesc': {
    en: 'Build a world by talking · edit an existing one · import',
    zh: '白模板对话造世界 · 修改现有世界 · 导入',
    ja: '対話でワールドを作る · 既存を編集 · インポート',
    ko: '대화로 월드 만들기 · 기존 편집 · 가져오기',
  },
  'home.libraryTitle': { en: 'Library', zh: '档案室', ja: '資料室', ko: '자료실' },
  'home.libraryDesc': {
    en: 'World library · character library · engine & API settings',
    zh: '世界库 · 角色库 · 引擎与 API 设置',
    ja: 'ワールド庫 · キャラクター庫 · エンジンと API 設定',
    ko: '월드 라이브러리 · 캐릭터 라이브러리 · 엔진 및 API 설정',
  },
  'home.hubDesc': {
    en: "Beam to everyone's worlds — discover and play instantly",
    zh: '传送到大家的世界 — 发现与即玩',
    ja: 'みんなのワールドへ — 発見してすぐ遊ぶ',
    ko: '모두의 월드로 — 발견하고 바로 플레이',
  },

  // ── LocalPlayGate ────────────────────────────────────────────
  'play.myWorlds': { en: 'MY WORLDS', zh: '我的世界 · MY WORLDS', ja: 'マイワールド · MY WORLDS', ko: '내 월드 · MY WORLDS' },
  'play.builtin': { en: 'BUILT-IN', zh: '内置世界 · BUILT-IN', ja: '内蔵ワールド · BUILT-IN', ko: '내장 월드 · BUILT-IN' },
  'play.badgeCreated': { en: 'created', zh: '创作', ja: '創作', ko: '창작' },
  'play.badgeDownloaded': { en: 'download', zh: '下载', ja: 'DL', ko: '다운' },

  // ── LocalWorldDetail ─────────────────────────────────────────
  'detail.backPlay': { en: '← Play', zh: '← 游玩', ja: '← プレイ', ko: '← 플레이' },
  'detail.deleteSaveConfirm': {
    en: 'Delete save {sid}? This cannot be undone.',
    zh: '删除存档 {sid}?不可恢复。',
    ja: 'セーブ {sid} を削除しますか?元に戻せません。',
    ko: '세이브 {sid} 을(를) 삭제할까요? 되돌릴 수 없습니다.',
  },
  'detail.building': { en: 'Building…', zh: '搭建中…', ja: '構築中…', ko: '구축 중…' },
  'detail.newRun': { en: 'Start a new run', zh: '新开一局', ja: '新規プレイ', ko: '새 플레이' },
  'detail.openingStudio': { en: 'Opening studio…', zh: '打开工坊…', ja: 'スタジオを開く…', ko: '스튜디오 여는 중…' },
  'detail.editThisWorld': { en: '✳ Edit this world', zh: '✳ 修改这个世界', ja: '✳ このワールドを編集', ko: '✳ 이 월드 편집' },
  'detail.savesTitle': { en: 'SAVES', zh: '这个世界的存档 · SAVES', ja: 'このワールドのセーブ · SAVES', ko: '이 월드의 세이브 · SAVES' },
  'detail.noSaves': {
    en: 'No saves yet — start from "Start a new run".',
    zh: '还没有存档 — 从「新开一局」开始。',
    ja: 'まだセーブがありません — 「新規プレイ」から始めましょう。',
    ko: '아직 세이브가 없습니다 — "새 플레이"로 시작하세요.',
  },
  'detail.current': { en: 'current', zh: '当前', ja: '現在', ko: '현재' },
  'detail.resume': { en: 'Resume', zh: '继续', ja: '続き', ko: '이어하기' },
  'detail.delete': { en: 'Delete', zh: '删除', ja: '削除', ko: '삭제' },

  // ── LocalCreateGate ──────────────────────────────────────────
  'create.newWorld': { en: '✳ New world', zh: '✳ 新的世界', ja: '✳ 新しいワールド', ko: '✳ 새 월드' },
  'studio.llm': { en: 'Model', zh: '模型', ja: 'モデル', ko: '모델' },
  'studio.working2': { en: 'Thinking…', zh: '思考中…', ja: '考え中…', ko: '생각 중…' },
  'studio.secGame': {
    en: 'WORLD CONTENT', zh: '游戏内容', ja: 'ワールド内容', ko: '월드 콘텐츠',
  },
  'studio.secSouls': {
    en: 'NATIVE CAST · ships with the world', zh: '原生角色 · 随世界发布', ja: 'ネイティブキャスト · ワールドと共に', ko: '네이티브 캐스트 · 월드와 함께',
  },
  'studio.secRest': { en: 'ENGINE / MISC', zh: '引擎 / 其它', ja: 'エンジン / その他', ko: '엔진 / 기타' },
  'studio.openerTitle': {
    en: 'Where shall we take “{name}”?', zh: '「{name}」从哪开始?', ja: '「{name}」をどこから?', ko: '“{name}” 어디서부터?',
  },
  'studio.openerDesc': {
    en: 'This world may still be mostly the blank template. Pick how to begin:',
    zh: '这个世界可能大部分还是白模板。选一个开始方式:',
    ja: 'このワールドはまだ白紙テンプレのままかも。始め方を選んでください:',
    ko: '이 월드는 아직 대부분 빈 템플릿일 수 있습니다. 시작 방법을 고르세요:',
  },
  'studio.openerAnalyze': {
    en: 'Analyze the gap first', zh: '先分析差距', ja: 'まずギャップを分析', ko: '먼저 격차 분석',
  },
  'studio.openerAnalyzeSub': {
    en: 'The agent reads everything, compares concept vs. reality, and proposes a build plan — no files touched yet.',
    zh: 'agent 通读全部内容,对比「概念 vs 现状」,给出改造计划 —— 先不动任何文件。',
    ja: 'agent が全体を読み、構想と現状を比較して計画を提案 —— まだファイルは触りません。',
    ko: 'agent 가 전체를 읽고 구상과 현실을 비교해 계획을 제안 — 아직 파일은 건드리지 않음.',
  },
  'studio.openerAnalyzePrompt': {
    en: 'Read through this whole world. Compare the concept implied by its name “{name}” against what the files actually contain. Give me a concrete build plan (what to do, which files), do NOT modify anything yet, and finish by asking whether to start.',
    zh: '通读这个世界的全部内容,对比世界名「{name}」蕴含的概念与文件的实际现状,给我一份具体的改造计划(要做什么、动哪些文件)。先不要修改任何文件,最后问我是否开始执行。',
    ja: 'このワールド全体を読み、名前「{name}」が示す構想とファイルの現状を比較し、具体的な改造計画(何をするか・どのファイルか)を提示してください。まだ何も変更せず、最後に開始するか私に確認してください。',
    ko: '이 월드 전체를 읽고 이름 “{name}” 이 암시하는 구상과 파일의 실제 상태를 비교해 구체적인 개조 계획(무엇을, 어떤 파일)을 제시하세요. 아직 아무것도 수정하지 말고 마지막에 시작할지 물어보세요.',
  },
  'studio.openerBuild': {
    en: 'Just start building', zh: '直接开工', ja: 'すぐ作り始める', ko: '바로 시작',
  },
  'studio.openerBuildSub': {
    en: 'The agent starts reshaping the template into this world right away, narrating each change.',
    zh: 'agent 立刻按世界概念开始改造模板,每一步说明改了什么。',
    ja: 'agent が構想に沿ってすぐ改造を開始し、各ステップで変更内容を説明します。',
    ko: 'agent 가 즉시 구상대로 개조를 시작하고 매 단계 변경 내용을 설명합니다.',
  },
  'studio.openerBuildPrompt': {
    en: 'Start reshaping this blank template into the world implied by its name “{name}”: worldview, map, town, NPCs, quests, story — step by step, explaining each change as you go.',
    zh: '按世界名「{name}」蕴含的概念,直接开始把白模板改造成这个世界:世界观、地图、城镇、NPC、任务、故事逐步落地,每一步说明你改了什么。',
    ja: '名前「{name}」が示す構想に沿って、白紙テンプレをこのワールドへ改造してください:世界観・地図・町・NPC・クエスト・物語を段階的に、変更を説明しながら。',
    ko: '이름 “{name}” 이 암시하는 구상대로 빈 템플릿을 이 월드로 개조하세요: 세계관·지도·마을·NPC·퀘스트·이야기를 단계별로, 변경을 설명하며.',
  },
  'studio.openerManual': {
    en: 'I will edit manually', zh: '我手动修改', ja: '手動で編集する', ko: '수동으로 편집',
  },
  'studio.openerManualSub': {
    en: 'Dismiss this — use the file tree and canvases yourself; the agent stays available.',
    zh: '收起这个卡 —— 自己用文件树和画布改,agent 随时待命。',
    ja: 'このカードを閉じ、ファイルツリーとキャンバスで自分で編集。agent は待機。',
    ko: '이 카드를 닫고 파일 트리와 캔버스로 직접 편집. agent 는 대기.',
  },
  'studio.doingRead': { en: 'Reading {f}', zh: '正在阅读 {f}', ja: '{f} を読んでいる', ko: '{f} 읽는 중' },
  'studio.doingWrite': { en: 'Writing {f}', zh: '正在改写 {f}', ja: '{f} を書いている', ko: '{f} 쓰는 중' },
  'studio.doingDelete': { en: 'Removing {f}', zh: '正在删除 {f}', ja: '{f} を削除中', ko: '{f} 삭제 중' },
  'soul.title': { en: 'Character studio', zh: '角色工坊', ja: 'キャラクター工房', ko: '캐릭터 공방' },
  'soul.phaseInterview': { en: 'interview', zh: '访谈', ja: 'インタビュー', ko: '인터뷰' },
  'soul.phaseGen': { en: 'creating…', zh: '生成中…', ja: '生成中…', ko: '생성 중…' },
  'soul.phaseEdit': { en: 'refine', zh: '精修', ja: '仕上げ', ko: '다듬기' },
  'soul.seedEcho': {
    en: 'Seed: {name} — {seed}', zh: '种子:{name} — {seed}', ja: 'シード:{name} — {seed}', ko: '시드: {name} — {seed}',
  },
  'soul.generating': {
    en: 'The character is taking shape… files light up below as they are written',
    zh: '角色正在成形…写好的文件会在下方逐个点亮',
    ja: 'キャラクターが形になっていく…書き上がったファイルが下に灯ります',
    ko: '캐릭터가 만들어지는 중… 완성된 파일이 아래에 켜집니다',
  },
  'soul.pickFile': { en: '(pick a file on the left)', zh: '(点左边的文件预览)', ja: '(左のファイルを選択)', ko: '(왼쪽 파일을 선택)' },
  'soul.answerPh': { en: 'Answer, or tap a chip above', zh: '回答,或点上面的选项', ja: '回答するか上のチップを', ko: '답하거나 위 칩을 탭' },
  'soul.refinePh': { en: 'Tell the agent what to change', zh: '想改哪里,直接说', ja: '直したい所を伝えて', ko: '고칠 부분을 말하세요' },
  'soul.skip': { en: 'Skip → generate', zh: '跳过 → 直接生成', ja: 'スキップ→生成', ko: '건너뛰고 생성' },
  'soul.skipTitle': {
    en: 'Generate now with what we have', zh: '就按现有信息直接生成', ja: '今の情報で生成', ko: '지금 정보로 생성',
  },
  'soul.save': { en: 'Save to archive', zh: '入库', ja: '登録', ko: '저장' },
  'soul.saveTalk': { en: 'Save & talk', zh: '入库并试聊', ja: '登録して会話', ko: '저장 후 대화' },
  'studio.working': {
    en: 'The agent is writing… (each tool card below = one file touched)',
    zh: 'agent 正在创作中…(下方每张工具卡 = 动了一个文件)',
    ja: 'agent が作成中…(下のツールカード = 変更されたファイル)',
    ko: 'agent 작성 중… (아래 도구 카드 = 수정된 파일)',
  },
  'studio.llmTitle': {
    en: 'Creation model', zh: '创作用模型', ja: '創作用モデル', ko: '창작용 모델',
  },
  'studio.llmDesc': {
    en: 'Which LLM the studio agent uses. Applies to this world now and becomes the creation default.',
    zh: '工坊 agent 用哪个 LLM。立即对当前世界生效,并成为之后创作的默认。',
    ja: 'スタジオの agent が使う LLM。今のワールドに即時適用され、以後の創作の既定になります。',
    ko: '스튜디오 agent 가 사용할 LLM. 현재 월드에 즉시 적용되고 이후 창작의 기본값이 됩니다.',
  },
  'studio.llmApply': { en: 'Apply', zh: '应用', ja: '適用', ko: '적용' },
  'studio.rename': { en: 'Rename', zh: '改名', ja: '名前を変更', ko: '이름 변경' },
  'studio.renamePh': {
    en: 'New world name:', zh: '世界的新名字:', ja: '新しいワールド名:', ko: '새 월드 이름:',
  },
  'create.llm_modal_title': {
    en: 'Connect a model first',
    zh: '先接入一个模型',
    ja: 'まずモデルを接続',
    ko: '먼저 모델을 연결하세요',
  },
  'create.llm_modal_desc': {
    en: 'Creation needs an LLM. Pick a provider and drop in a key — saved locally, then we retry right away.',
    zh: '创作需要一个 LLM。选一个 provider 填上 key(只存本机),配好立刻继续刚才的操作。',
    ja: '創作には LLM が必要です。プロバイダを選んでキーを入力(ローカル保存)、設定後すぐ再開します。',
    ko: '창작에는 LLM이 필요합니다. 프로바이더를 선택하고 키를 입력하세요(로컬 저장). 설정 후 바로 이어집니다.',
  },
  'create.llm_modal_go': {
    en: 'Save & continue',
    zh: '保存并继续',
    ja: '保存して続行',
    ko: '저장하고 계속',
  },
  'create.newWorldDesc': {
    en: 'Start from a white template: a fully structured, instantly playable empty world (one starting town + two blank character slots). Then write it into your own by talking — every line, the agent edits the world files directly.',
    zh: '从白模板开始:一个结构完整、立即可玩的空世界(一座起点镇 + 两个空白角色位)。然后用对话把它写成你的 —— 每句话,agent 都直接改世界的文件。',
    ja: '白テンプレートから開始:構造が整い、すぐ遊べる空のワールド(始まりの町 1 つ + 空のキャラクター枠 2 つ)。あとは対話であなたのものに書き上げる —— 一言ごとに、エージェントがワールドのファイルを直接編集します。',
    ko: '백지 템플릿에서 시작: 구조가 완성되어 바로 플레이 가능한 빈 월드(시작 마을 1 + 빈 캐릭터 자리 2). 이후 대화로 당신의 것으로 완성 — 한 마디마다 에이전트가 월드 파일을 직접 수정합니다.',
  },
  'create.worldNamePh': { en: 'World name (optional)', zh: '世界的名字(可留空)', ja: 'ワールド名(任意)', ko: '월드 이름(선택)' },
  'create.spreadingPaper': { en: 'Spreading the paper…', zh: '铺开白纸…', ja: '白紙を広げる…', ko: '백지를 펼치는 중…' },
  'create.startCreating': { en: 'Start creating', zh: '开始创作', ja: '創作を始める', ko: '창작 시작' },
  'create.newSoul': { en: '✦ New character', zh: '✦ 新的角色', ja: '✦ 新しいキャラクター', ko: '✦ 새 캐릭터' },
  'create.newSoulDesc': {
    en: 'A name + one line, and the AI writes a complete character (personality / background / memory / voice) into the library — then talk to them alone, or bring them into any world.',
    zh: '名字 + 一句话,AI 写出完整角色(性格/背景/记忆/口吻)入库 —— 之后可以单独对话,也可以带进任何世界。',
    ja: '名前 + 一言で、AI が完全なキャラクター(性格/背景/記憶/口調)を書いて庫に登録 —— あとは単独で対話も、どのワールドにも連れて行けます。',
    ko: '이름 + 한 줄이면 AI 가 완전한 캐릭터(성격/배경/기억/말투)를 만들어 라이브러리에 등록 — 이후 단독 대화도, 어떤 월드에도 데려갈 수 있습니다.',
  },
  'create.soulNamePh': { en: 'Character name (e.g. Elena)', zh: '角色名(如:艾琳娜)', ja: 'キャラクター名(例: エレナ)', ko: '캐릭터 이름(예: 엘레나)' },
  'create.soulSeedPh': {
    en: 'One line: who are they? (e.g. a healer burdened by the past)',
    zh: '一句话:她/他是谁?(如:一位背负往事的治愈师)',
    ja: '一言で:どんな人?(例: 過去を背負う癒し手)',
    ko: '한 줄로: 그/그녀는 누구? (예: 과거를 짊어진 치유사)',
  },
  'create.soulForming': { en: 'Character taking shape…', zh: '角色成形中…', ja: 'キャラクター生成中…', ko: '캐릭터 생성 중…' },
  'create.genSoul': { en: 'Generate character', zh: '生成角色', ja: 'キャラクター生成', ko: '캐릭터 생성' },
  'create.soulCreating': {
    en: 'Creating… (the LLM writes a full character, ~1 min)',
    zh: '创作中…(LLM 生成完整角色,约 1 分钟)',
    ja: '作成中…(LLM が完全なキャラクターを生成、約 1 分)',
    ko: '생성 중… (LLM 이 완전한 캐릭터를 만듭니다, 약 1 분)',
  },
  'create.soulDone': { en: '✓ {name} added to library', zh: '✓ {name} 已入库', ja: '✓ {name} を庫に登録', ko: '✓ {name} 라이브러리에 등록' },
  'create.editWorld': { en: '✎ Edit world', zh: '✎ 修改世界', ja: '✎ ワールド編集', ko: '✎ 월드 편집' },
  'create.editWorldDesc': {
    en: 'Open an edit session on any world in your library — add locations, write characters, change hidden threads. You edit the library source, so every new run uses the new version.',
    zh: '对你库里的任何世界开一个编辑会话 —— 加地点、写角色、改暗线,改的是库源,之后每次新开局都是新版。',
    ja: '庫内のどのワールドにも編集セッションを開けます —— 地点を足し、キャラクターを書き、伏線を変える。編集対象は庫のソースなので、以後の新規プレイは新版になります。',
    ko: '라이브러리의 어떤 월드든 편집 세션을 엽니다 — 장소 추가, 캐릭터 작성, 숨은 실마리 수정. 라이브러리 원본을 수정하므로 이후 모든 새 플레이가 새 버전입니다.',
  },
  'create.pickWorld': { en: 'Pick a world…', zh: '选择一个世界…', ja: 'ワールドを選択…', ko: '월드 선택…' },
  'create.openStudio': { en: 'Open studio', zh: '打开工坊', ja: 'スタジオを開く', ko: '스튜디오 열기' },
  'create.openingStudio': { en: 'Opening studio…', zh: '打开工坊…', ja: 'スタジオを開く…', ko: '스튜디오 여는 중…' },
  'create.noOwnedWorlds': {
    en: '(No worlds of yours in the library yet — start one from the white template first)',
    zh: '(库里还没有你的世界 — 先从白模板开一个)',
    ja: '(庫にまだあなたのワールドがありません — まず白テンプレートから 1 つ)',
    ko: '(라이브러리에 아직 내 월드가 없습니다 — 먼저 백지 템플릿으로 하나)',
  },
  'create.import': { en: '⇣ Import', zh: '⇣ 导入', ja: '⇣ インポート', ko: '⇣ 가져오기' },
  'create.importDesc': {
    en: 'A tavern character card → a full soul; a world zip → the library; a lore text → the AI turns it into a playable world in the studio.',
    zh: '酒馆角色卡 → 完整 soul;世界 zip → 库;设定文本 → AI 在工坊里编成可玩世界。',
    ja: '酒場キャラクターカード → 完全なソウル;ワールド zip → 庫;設定テキスト → AI がスタジオで遊べるワールドに編みます。',
    ko: '태번 캐릭터 카드 → 완전한 소울; 월드 zip → 라이브러리; 설정 텍스트 → AI 가 스튜디오에서 플레이 가능한 월드로.',
  },
  'create.cardBtn': { en: 'Character card (.png/.json)', zh: '角色卡(.png/.json)', ja: 'キャラクターカード(.png/.json)', ko: '캐릭터 카드(.png/.json)' },
  'create.zipBtn': { en: 'World bundle (.zip)', zh: '世界包(.zip)', ja: 'ワールドパック(.zip)', ko: '월드 팩(.zip)' },
  'create.lorePh': {
    en: 'Or: paste a setting / lore, and the AI weaves it into a world in the studio…',
    zh: '或者:直接粘贴一段设定/lore,AI 在工坊里把它编成世界…',
    ja: 'または:設定/lore を貼り付け、AI がスタジオでワールドに編みます…',
    ko: '또는: 설정/lore 를 붙여넣으면 AI 가 스튜디오에서 월드로 엮습니다…',
  },
  'create.enterStudio': { en: 'Entering studio…', zh: '进工坊…', ja: 'スタジオへ…', ko: '스튜디오로…' },
  'create.compileLore': { en: 'Weave the setting into a world', zh: '把设定编成世界', ja: '設定をワールドに編む', ko: '설정을 월드로 엮기' },
  'create.cardWriting': {
    en: 'Writing… (the AI turns {name} into a full character, ~1-2 min)',
    zh: '编写中…(AI 把 {name} 写成完整角色,约 1-2 分钟)',
    ja: '執筆中…(AI が {name} を完全なキャラクターに、約 1-2 分)',
    ko: '작성 중… (AI 가 {name} 을(를) 완전한 캐릭터로, 약 1-2 분)',
  },
  'create.cardDone': {
    en: '✓ Character added: {dir} (visible in the library)',
    zh: '✓ 角色已入库:{dir}(档案室可见)',
    ja: '✓ キャラクター登録:{dir}(資料室で表示)',
    ko: '✓ 캐릭터 등록: {dir} (자료실에서 표시)',
  },
  'create.zipImporting': { en: 'Importing {name}…', zh: '导入 {name}…', ja: '{name} をインポート…', ko: '{name} 가져오는 중…' },
  'create.zipDone': { en: '✓ World imported: {id}', zh: '✓ 世界已入库:{id}', ja: '✓ ワールド登録:{id}', ko: '✓ 월드 등록: {id}' },
  'create.loreKickoff': {
    en: 'Using the setting below, write this white template into a full, playable world:\n\n{lore}',
    zh: '根据下面的设定把这个白模板写成完整可玩的世界:\n\n{lore}',
    ja: '以下の設定に基づき、この白テンプレートを完全に遊べるワールドに書き上げてください:\n\n{lore}',
    ko: '아래 설정에 따라 이 백지 템플릿을 완전히 플레이 가능한 월드로 작성해 주세요:\n\n{lore}',
  },
  'create.worldCardBtn': { en: 'World card', zh: '世界卡', ja: 'ワールドカード', ko: '월드 카드' },
  'create.cardToStudio': { en: 'Opening studio with {name}…', zh: '带 {name} 进工坊…', ja: '{name} を工房へ…', ko: '{name} 공방으로…' },

  // ── 导入三选项面板(ImportOptionsPanel:卡片入工坊后的转换路径)──
  'imp.title': {
    en: 'Imported — choose how to convert',
    zh: '已导入 · 选择转换方式',
    ja: 'インポート済み · 変換方法を選択',
    ko: '가져옴 · 변환 방식 선택',
  },
  'imp.source': { en: 'Source card', zh: '源卡', ja: '元カード', ko: '원본 카드' },
  'imp.entries': { en: '{n} entries', zh: '{n} 条目', ja: '{n} 項目', ko: '{n} 항목' },
  'imp.recommend': {
    en: 'Large card — batched conversion recommended.',
    zh: '卡片较大 —— 建议分批转换。',
    ja: 'カードが大きいため、分割変換を推奨します。',
    ko: '카드가 커서 배치 변환을 권장합니다.',
  },
  'imp.recommended': { en: 'recommended', zh: '推荐', ja: '推奨', ko: '추천' },
  'imp.opt1': { en: 'Make a conversion plan', zh: '制定转换计划', ja: '変換計画を立てる', ko: '변환 계획 세우기' },
  'imp.opt1Sub': {
    en: 'Plan first, then convert batch by batch — resumable anytime.',
    zh: '先出计划,再逐批转换 —— 随时可中断续跑。',
    ja: '計画を立ててからバッチごとに変換 — いつでも再開可能。',
    ko: '계획 후 배치별 변환 — 언제든 이어서 가능.',
  },
  'imp.opt2': { en: 'One-shot conversion', zh: '一次性转换', ja: '一括変換', ko: '일괄 변환' },
  'imp.opt2Sub': {
    en: 'Convert the whole card in one go (small cards).',
    zh: '整卡一口气转完(适合小卡)。',
    ja: 'カード全体を一度に変換(小さいカード向け)。',
    ko: '카드 전체를 한 번에 변환(작은 카드용).',
  },
  'imp.opt3': { en: 'Edit manually', zh: '手动修改', ja: '手動で編集', ko: '수동 편집' },
  'imp.opt3Sub': {
    en: 'Skip conversion — work the folder yourself with the agent.',
    zh: '跳过转换,和 agent 一起手动打磨。',
    ja: '変換をスキップし、agent と手動で仕上げる。',
    ko: '변환 건너뛰고 agent와 직접 다듬기.',
  },
  'imp.progress': { en: 'Import plan {done}/{total}', zh: '导入计划 {done}/{total}', ja: 'インポート計画 {done}/{total}', ko: '가져오기 계획 {done}/{total}' },
  'imp.next': { en: 'next: {title}', zh: '下一批:{title}', ja: '次:{title}', ko: '다음: {title}' },
  'imp.continue': { en: 'Continue next batch', zh: '继续下一批', ja: '次のバッチへ', ko: '다음 배치 계속' },

  // ── LocalStudio ──────────────────────────────────────────────
  'studio.reviewTitle': { en: 'SUBMIT FOR REVIEW', zh: '提交审查', ja: '審査に提出', ko: '심사 제출' },
  'studio.reviewHint': { en: 'Publish this world to the Hub catalog — it goes live after review.', zh: '把这个世界发布到 Hub 目录 —— 审查通过后上架。', ja: 'このワールドをHubカタログへ公開 —— 審査通過後に掲載。', ko: '이 월드를 Hub 카탈로그에 게시 — 심사 통과 후 공개됩니다.' },
  'studio.reviewSubmit': { en: 'Submit', zh: '提交审查', ja: '提出する', ko: '제출' },
  'studio.reviewResubmit': { en: 'Resubmit', zh: '重新提交', ja: '再提出', ko: '재제출' },
  'studio.reviewBusy': { en: 'Submitting…', zh: '提交中…', ja: '提出中…', ko: '제출 중…' },
  'studio.reviewNote': { en: 'Reviewer note', zh: '审查留言', ja: '審査コメント', ko: '심사 코멘트' },
  'studio.reviewPrecheck': { en: 'precheck', zh: '自动预审', ja: '自動プリチェック', ko: '자동 사전검사' },
  'studio.reviewPending': { en: 'Under review', zh: '审查中', ja: '審査中', ko: '심사 중' },
  'studio.reviewApproved': { en: 'Published', zh: '已上架', ja: '公開済み', ko: '게시됨' },
  'studio.reviewRejected': { en: 'Returned', zh: '已退回', ja: '差し戻し', ko: '반려됨' },
  'studio.reviewCounts': { en: '{blockers} blockers · {warnings} warnings', zh: '{blockers} 阻断 · {warnings} 提醒', ja: 'ブロッカー {blockers}件 · 警告 {warnings}件', ko: '차단 {blockers}건 · 경고 {warnings}건' },
  'studio.toggleWrap': { en: 'Toggle wrapping for long lines', zh: '切换长行折行 / 不折行', ja: '長い行の折り返しを切り替え', ko: '긴 줄 줄바꿈 전환' },
  'studio.wrap': { en: 'Wrap', zh: '折行', ja: '折り返す', ko: '줄바꿈' },
  'studio.noWrap': { en: 'No wrap', zh: '不折行', ja: '折り返さない', ko: '줄바꿈 안 함' },
  'studio.tabOverview': { en: 'Overview', zh: '概览', ja: '概要', ko: '개요' },
  'studio.tabFiles': { en: 'Files', zh: '资料', ja: '資料', ko: '자료' },
  'studio.tabMap': { en: 'World map', zh: '世界图', ja: 'ワールド図', ko: '월드 맵' },
  'studio.tabStory': { en: 'Story blueprint', zh: '剧情蓝图', ja: 'ストーリー設計図', ko: '스토리 청사진' }, // issue #14 方案C:避免暗示画布驱动运行时剧情
  'studio.tabCover': { en: 'Cover', zh: '封面', ja: 'カバー', ko: '커버' },
  'studio.coverGen': { en: 'Generate cover', zh: '生成封面', ja: 'カバー生成', ko: '커버 생성' },
  'studio.coverDesc': {
    en: 'The world cover (assets/cover.png) — shown on world cards, PrePlay and the play stage. Generate from the world’s lore via the image backend, or upload.',
    zh: '世界封面(assets/cover.png)—— 封面卡、进场页、游玩现场都用它。可按世界设定用图像后端生成,或自己上传。',
    ja: 'ワールドカバー(assets/cover.png)。カードや入場画面で使用。設定から生成、またはアップロード。',
    ko: '월드 커버(assets/cover.png). 카드와 입장 화면에 사용. 설정에서 생성하거나 업로드하세요.',
  },
  'studio.tabRelation': { en: 'Relations', zh: '关系网络', ja: '関係網', ko: '관계망' },
  'studio.loadingFile': { en: '(loading…)', zh: '(加载中…)', ja: '(読み込み中…)', ko: '(불러오는 중…)' },
  'studio.cantRead': { en: '(cannot read: {e})', zh: '(读不出来:{e})', ja: '(読めません:{e})', ko: '(읽을 수 없음: {e})' },
  'studio.done': { en: '(done)', zh: '(完成)', ja: '(完了)', ko: '(완료)' },
  'studio.draftInvalid': {
    en: '⚠ Draft JSON failed validation: {e}',
    zh: '⚠ 起草 JSON 未通过校验:{e}',
    ja: '⚠ ドラフト JSON が検証に失敗:{e}',
    ko: '⚠ 초안 JSON 검증 실패: {e}',
  },
  'studio.draftRelationsPrompt': {
    en: 'Read every character (town npcs.json files, game/npc/, native souls) and the lore. Infer the web of relationships between them. Output ONLY one ```json code block shaped {"relationships":[{"source":"<npc id>","target":"<npc id>","relation_type":"债务|亲属|仇怨|盟友|暗恋|师徒|…","description":"one line","direction":"directed|bidirectional","strength":1-5}]}. Use their exact ids. Do not write any files.',
    zh: '通读所有角色(towns 的 npcs.json、game/npc/、原生 souls)与故事设定,推断他们之间的关系网。只输出一个 ```json 代码块,形如 {"relationships":[{"source":"<角色id>","target":"<角色id>","relation_type":"债务|亲属|仇怨|盟友|暗恋|师徒|…","description":"一句话","direction":"directed|bidirectional","strength":1-5}]}。必须用角色的准确 id,不要写任何文件。',
    ja: '全キャラクター(towns の npcs.json、game/npc/、ネイティブ souls)と設定を読み、関係網を推定してください。```json ブロックを 1 つだけ出力:{"relationships":[{"source":"<id>","target":"<id>","relation_type":"…","description":"一行","direction":"directed|bidirectional","strength":1-5}]}。正確な id を使い、ファイルは書かないこと。',
    ko: '모든 캐릭터(towns 의 npcs.json, game/npc/, 네이티브 souls)와 설정을 읽고 관계망을 추론하세요. ```json 블록 하나만 출력: {"relationships":[{"source":"<id>","target":"<id>","relation_type":"…","description":"한 줄","direction":"directed|bidirectional","strength":1-5}]}. 정확한 id 를 쓰고 파일은 쓰지 마세요.',
  },
  'canvas.extraFields': {
    en: 'Authored fields (read-only, kept on save)', zh: '内容字段(只读,保存时原样保留)',
    ja: '作成済みフィールド(読み取り専用)', ko: '작성된 필드(읽기 전용)',
  },
  'canvas.story.emptyTitle': {
    en: 'No story beats yet', zh: '剧情画布还是空的', ja: 'ストーリーはまだ空', ko: '스토리가 비어 있음',
  },
  'canvas.story.emptyDesc': {
    en: 'Your world may already have lore & quests — let the agent draft a flow from them, or lay beats by hand.',
    zh: '世界里可能已经有故事和任务 —— 让 agent 从现有内容起草一张剧情流程,或手动摆节点。',
    ja: 'ワールドには既に物語やクエストがあるかも —— agent に起草させるか、手で配置を。',
    ko: '월드에 이미 이야기와 퀘스트가 있을 수 있습니다 — agent 에게 초안을 맡기거나 직접 배치하세요.',
  },
  'canvas.story.emptyDraft': {
    en: 'Draft from world content', zh: '让 agent 从现有内容起草', ja: '既存内容から起草', ko: '기존 내용에서 초안',
  },
  'canvas.story.emptyManual': { en: 'Add by hand', zh: '手动添加', ja: '手動で追加', ko: '직접 추가' },
  'canvas.relation.emptyTitle': {
    en: 'No relationships yet', zh: '还没有关系', ja: '関係はまだなし', ko: '아직 관계 없음',
  },
  'canvas.relation.emptyDesc': {
    en: 'Characters exist but no ties are drawn. Let the agent infer relationships from their bios & the lore, or drag between nodes.',
    zh: '角色已经在了,但还没有连线。让 agent 从人设与故事里推断关系,或直接在节点间拖线。',
    ja: 'キャラクターはいるが繋がりがない。agent に推定させるか、ノード間をドラッグ。',
    ko: '캐릭터는 있지만 연결이 없습니다. agent 에게 추론시키거나 노드 사이를 드래그하세요.',
  },
  'canvas.relation.emptyDraft': {
    en: 'Infer from bios & lore', zh: '让 agent 从人设推断', ja: '人物設定から推定', ko: '인물 설정에서 추론',
  },
  'studio.noDraftJson': {
    en: '⚠ No usable canvas JSON in the reply — try again or rephrase.',
    zh: '⚠ 回复里没找到可用的画布 JSON,再试一次或换个说法。',
    ja: '⚠ 返信に使えるキャンバス JSON がありません。再試行か言い換えを。',
    ko: '⚠ 응답에 사용할 캔버스 JSON 이 없습니다. 다시 시도하거나 다르게 표현하세요.',
  },
  'studio.draftPrompt': {
    en:
      'Read through this world\'s locations, NPCs, quests and hidden threads, and draft a story-flow diagram for me. ' +
      'Output only one ```json code block, shaped like {"nodes":[{"id":"sf-1","pos":[120,90],' +
      '"data":{"label":"...","node_type":"scene|event|choice|check|combat|clue|location|reward|ending|condition",' +
      '"player_text":"...","gm_text":"...","trigger_condition":"...","related_ids":[],"clue_ids":[],"fail_safe":"..."}}],' +
      '"edges":[{"id":"se-1","source":"sf-1","target":"sf-2","data":{"label":"","condition_text":"..."}}],"viewport":{}}. ' +
      '8-14 nodes; lay the main line left-to-right with side branches above/below (pos is in pixels, ~220 horizontal spacing). Do not write any files.',
    zh:
      '通读这个世界的地点、NPC、任务和暗线,替我起草一份剧情流程图。' +
      '只输出一个 ```json 代码块,形如 {"nodes":[{"id":"sf-1","pos":[120,90],' +
      '"data":{"label":"...","node_type":"scene|event|choice|check|combat|clue|location|reward|ending|condition",' +
      '"player_text":"...","gm_text":"...","trigger_condition":"...","related_ids":[],"clue_ids":[],"fail_safe":"..."}}],' +
      '"edges":[{"id":"se-1","source":"sf-1","target":"sf-2","data":{"label":"","condition_text":"..."}}],"viewport":{}}。' +
      '节点 8-14 个,布局从左到右主线、支线上下展开(pos 单位是像素,横向间距约 220)。不要写任何文件。',
    ja:
      'このワールドの地点、NPC、クエスト、伏線を通読し、ストーリーフロー図を起草してください。' +
      '出力は ```json コードブロック 1 つだけ、形は {"nodes":[{"id":"sf-1","pos":[120,90],' +
      '"data":{"label":"...","node_type":"scene|event|choice|check|combat|clue|location|reward|ending|condition",' +
      '"player_text":"...","gm_text":"...","trigger_condition":"...","related_ids":[],"clue_ids":[],"fail_safe":"..."}}],' +
      '"edges":[{"id":"se-1","source":"sf-1","target":"sf-2","data":{"label":"","condition_text":"..."}}],"viewport":{}}。' +
      'ノードは 8-14 個、本線は左から右、支線は上下に展開(pos はピクセル、横間隔約 220)。ファイルは一切書かないこと。',
    ko:
      '이 월드의 장소, NPC, 퀘스트, 숨은 실마리를 통독하고 스토리 흐름도를 초안으로 작성해 주세요. ' +
      '출력은 ```json 코드 블록 하나만, 형태는 {"nodes":[{"id":"sf-1","pos":[120,90],' +
      '"data":{"label":"...","node_type":"scene|event|choice|check|combat|clue|location|reward|ending|condition",' +
      '"player_text":"...","gm_text":"...","trigger_condition":"...","related_ids":[],"clue_ids":[],"fail_safe":"..."}}],' +
      '"edges":[{"id":"se-1","source":"sf-1","target":"sf-2","data":{"label":"","condition_text":"..."}}],"viewport":{}}. ' +
      '노드 8-14 개, 본선은 좌에서 우로, 지선은 상하로 전개(pos 는 픽셀, 가로 간격 약 220). 파일은 절대 쓰지 마세요.',
  },
  'studio.groundPrompt': {
    en:
      'Below is the flow I arranged on the story canvas (an editor by-product — you can\'t read its file, so treat this JSON as authoritative). ' +
      'Ground it into real game content: write quests into the relevant town\'s quests.json, hang key events on hooks/hidden threads, ' +
      'write the involved NPCs\' relationships into their fields; update existing content incrementally, don\'t duplicate. ' +
      'When done, note per node which file it landed in.\n\n```json\n{json}\n```',
    zh:
      '下面是我在剧情画布上排好的流程(编辑副产物,你读不到它的文件,以这份 JSON 为准)。' +
      '请把它落成真实的游戏内容:任务写进对应 town 的 quests.json、关键事件挂进钩子/暗线、' +
      '涉及的 NPC 关系写进他们的字段;已存在的内容做增量更新不要重复。' +
      '落完逐节点说明落到了哪个文件。\n\n```json\n{json}\n```',
    ja:
      '以下は私がストーリーキャンバスで並べたフロー(編集の副産物で、あなたはそのファイルを読めないので、この JSON を正とする)。' +
      'これを実際のゲーム内容に落としてください:クエストは該当 town の quests.json へ、重要イベントはフック/伏線へ、' +
      '関わる NPC の関係は各フィールドへ;既存内容は増分更新で重複させないこと。' +
      '完了後、ノードごとにどのファイルに落としたか説明してください。\n\n```json\n{json}\n```',
    ko:
      '아래는 제가 스토리 캔버스에 배치한 흐름입니다(편집 부산물이라 파일을 읽을 수 없으니 이 JSON 을 기준으로 하세요). ' +
      '이를 실제 게임 콘텐츠로 반영해 주세요: 퀘스트는 해당 town 의 quests.json 에, 핵심 이벤트는 훅/숨은 실마리에, ' +
      '관련 NPC 관계는 각 필드에; 기존 콘텐츠는 증분 업데이트로 중복 없이. ' +
      '완료 후 노드별로 어느 파일에 반영했는지 설명해 주세요.\n\n```json\n{json}\n```',
  },
  'studio.noEditSessionPre': {
    en: 'No edit session in progress — come in from',
    zh: '没有进行中的编辑会话 —— 从',
    ja: '進行中の編集セッションがありません ——',
    ko: '진행 중인 편집 세션이 없습니다 —',
  },
  'studio.noEditSessionLink': { en: 'Create', zh: '创作', ja: '創作', ko: '창작' },
  'studio.noEditSessionPost': { en: '.', zh: '进来。', ja: 'から入ってください。', ko: '에서 들어오세요.' },
  'studio.backCreate': { en: '← Create', zh: '← 创作', ja: '← 創作', ko: '← 창작' },
  'studio.collapse': { en: '⇥ Collapse', zh: '⇥ 收起', ja: '⇥ 折りたたむ', ko: '⇥ 접기' },
  'studio.expand': { en: '⇤ Chat', zh: '⇤ 对话', ja: '⇤ 対話', ko: '⇤ 대화' },
  'studio.collapseChat': { en: 'Collapse chat', zh: '收起对话', ja: '対話を折りたたむ', ko: '대화 접기' },
  'studio.expandChat': { en: 'Expand chat', zh: '展开对话', ja: '対話を展開', ko: '대화 펼치기' },
  'studio.starting': { en: 'Starting…', zh: '开局中…', ja: '開始中…', ko: '시작 중…' },
  'studio.playtest': { en: '▶ Playtest', zh: '▶ 试玩', ja: '▶ 試遊', ko: '▶ 시연' },
  'studio.currentWorld': { en: 'CURRENT WORLD', zh: '当前世界', ja: '現在のワールド', ko: '현재 월드' },
  'studio.overviewHint': {
    en: 'Say what you want to change in the chat on the right and the agent writes it into the files; or open a canvas to lay out the world, story and relations visually.',
    zh: '在右侧对话里说想改什么,agent 直接写进文件;或进画布可视化地排世界、剧情与关系。',
    ja: '右の対話で変えたいことを言えばエージェントがファイルに書き込みます;またはキャンバスでワールド・ストーリー・関係を視覚的に配置。',
    ko: '오른쪽 대화에서 바꾸고 싶은 것을 말하면 에이전트가 파일에 씁니다; 또는 캔버스에서 월드·스토리·관계를 시각적으로 배치하세요.',
  },
  'studio.editScript': { en: '✎ Edit script', zh: '✎ 编辑剧本', ja: '✎ 脚本を編集', ko: '✎ 각본 편집' },
  'studio.editScriptKick': {
    en: 'Help me flesh out this world\'s blurb and tone:',
    zh: '帮我完善这个世界的简介和基调:',
    ja: 'このワールドの紹介文とトーンを詰めるのを手伝って:',
    ko: '이 월드의 소개와 톤을 다듬는 것을 도와줘:',
  },
  'studio.cardFiles': { en: 'Files', zh: '资料', ja: '資料', ko: '자료' },
  'studio.filesCount': { en: '{n} files', zh: '{n} 个文件', ja: '{n} 個のファイル', ko: '파일 {n} 개' },
  'studio.cardMap': { en: 'World map', zh: '世界图', ja: 'ワールド図', ko: '월드 맵' },
  'studio.locCount': { en: '{n} locations', zh: '{n} 处地点', ja: '{n} 箇所の地点', ko: '장소 {n} 곳' },
  'studio.cardStory': { en: 'Story flow', zh: '剧情流程', ja: 'ストーリー', ko: '스토리 흐름' },
  'studio.canvas': { en: 'canvas', zh: '画布', ja: 'キャンバス', ko: '캔버스' },
  'studio.cardRelation': { en: 'Relations', zh: '关系网络', ja: '関係網', ko: '관계망' },
  'studio.npcCount': { en: '{n} characters', zh: '{n} 名角色', ja: '{n} 名のキャラクター', ko: '캐릭터 {n} 명' },
  'studio.soulsCount': { en: '{n}', zh: '{n} 个', ja: '{n} 個', ko: '{n} 개' },
  'studio.cardQuests': { en: 'Quests', zh: '任务', ja: 'クエスト', ko: '퀘스트' },
  'studio.questsCount': { en: '{n} quests', zh: '{n} 份 quests', ja: '{n} 件の quests', ko: 'quests {n} 개' },
  'studio.filePreviewHint': { en: '(click a file on the left to preview)', zh: '(点左边的文件预览)', ja: '(左のファイルをクリックでプレビュー)', ko: '(왼쪽 파일을 클릭하면 미리보기)' },
  'studio.agentDraft': { en: '✦ Let the agent draft', zh: '✦ 让 agent 起草', ja: '✦ エージェントに起草させる', ko: '✦ 에이전트에게 초안 맡기기' },
  'studio.groundToContent': { en: '⇓ Ground into content', zh: '⇓ 落地成内容', ja: '⇓ 内容に落とす', ko: '⇓ 콘텐츠로 반영' },
  'studio.agent': { en: '✦ agent', zh: '✦ agent', ja: '✦ agent', ko: '✦ agent' },
  'studio.everyLineWrites': { en: 'every line is written into the files', zh: '每句话都会写进文件', ja: '一言ごとにファイルへ書き込みます', ko: '모든 말이 파일에 기록됩니다' },
  'studio.chatEmpty': {
    en: 'Tell the agent what this world is like. For example: "This is a fog-bound island; the town is called Fogtide Port; character A is the lighthouse keeper who remembers the name of every wreck."',
    zh: '告诉 agent 这个世界是什么样的。比如:「这是一座常年起雾的海岛,镇子叫雾汐港;角色A是灯塔守,记得所有沉船的名字。」',
    ja: 'このワールドがどんな場所か、エージェントに伝えてください。例:「常に霧に包まれた島。町の名は霧汐港。キャラクターA は灯台守で、すべての沈没船の名を覚えている。」',
    ko: '이 월드가 어떤 곳인지 에이전트에게 말해 주세요. 예: "늘 안개에 싸인 섬. 마을 이름은 무석항. 캐릭터 A 는 등대지기로 모든 난파선의 이름을 기억한다."',
  },
  'studio.turnChanges': { en: 'This turn · {n} files', zh: '本回合改动 · {n} 个文件', ja: 'この回の変更 · {n} 個のファイル', ko: '이번 턴 변경 · 파일 {n} 개' },
  'studio.chatPh': { en: 'Say what to add or change, directly', zh: '想加什么、改什么,直接说', ja: '追加・変更したいことを直接どうぞ', ko: '추가·변경할 것을 바로 말하세요' },
  'studio.chatPhBusy': { en: 'the agent is editing the world…', zh: 'agent 正在改世界…', ja: 'エージェントがワールドを編集中…', ko: '에이전트가 월드를 수정 중…' },
  'studio.say': { en: 'Send', zh: '说', ja: '送信', ko: '전송' },
  'studio.truncated': { en: '\n…(truncated)', zh: '\n…(截断)', ja: '\n…(省略)', ko: '\n…(잘림)' },

  // ── StudioCanvas ─────────────────────────────────────────────
  'canvas.dirty': { en: 'unsaved…', zh: '未保存…', ja: '未保存…', ko: '저장 안 됨…' },
  'canvas.saving': { en: 'saving…', zh: '保存中…', ja: '保存中…', ko: '저장 중…' },
  'canvas.saved': { en: '✓ saved', zh: '✓ 已保存', ja: '✓ 保存済み', ko: '✓ 저장됨' },
  'canvas.error': { en: '✗ save failed', zh: '✗ 保存失败', ja: '✗ 保存失敗', ko: '✗ 저장 실패' },
  'canvas.location': { en: 'Location', zh: '地点', ja: '地点', ko: '장소' },
  'canvas.node': { en: 'Node', zh: '节点', ja: 'ノード', ko: '노드' },
  'canvas.relHint': {
    en: 'Drag to arrange · drag node dots to link relations · click an edge to edit',
    zh: '拖拽排布 · 拖节点圆点连关系 · 单击连线编辑',
    ja: 'ドラッグで配置 · ノードの点をドラッグで関係を結ぶ · 連線をクリックで編集',
    ko: '드래그로 배치 · 노드 점을 드래그해 관계 연결 · 연결선 클릭으로 편집',
  },
  'canvas.flowHint': {
    en: 'Click a node/edge to edit · drag node dots to link',
    zh: '单击节点/连线看详情 · 拖节点圆点连线',
    ja: 'ノード/連線をクリックで編集 · ノードの点をドラッグで結線',
    ko: '노드/연결선 클릭으로 편집 · 노드 점을 드래그해 연결',
  },
  'canvas.loading': { en: 'Loading canvas…', zh: '画布加载中…', ja: 'キャンバス読み込み中…', ko: '캔버스 불러오는 중…' },
  'canvas.newLocation': { en: 'New location', zh: '新地点', ja: '新しい地点', ko: '새 장소' },
  'canvas.newStoryNode': { en: 'New story node', zh: '新剧情节点', ja: '新しいストーリーノード', ko: '새 스토리 노드' },
  'canvas.relationDefault': { en: 'relation', zh: '关系', ja: '関係', ko: '관계' },
  'canvas.unnamed': { en: 'Unnamed', zh: '未命名', ja: '無題', ko: '이름 없음' },
  'canvas.storyNode': { en: 'Story node', zh: '剧情节点', ja: 'ストーリーノード', ko: '스토리 노드' },
  'canvas.name': { en: 'Name', zh: '名称', ja: '名称', ko: '이름' },
  'canvas.summary': { en: 'Summary', zh: '简介', ja: '概要', ko: '요약' },
  'canvas.type': { en: 'Type', zh: '类型', ja: 'タイプ', ko: '유형' },
  'canvas.playerText': { en: 'Player-visible description', zh: '玩家可见描述', ja: 'プレイヤー可視の説明', ko: '플레이어에게 보이는 설명' },
  'canvas.gmText': { en: 'GM description (world-agent view)', zh: 'GM 描述(world-agent 视角)', ja: 'GM 説明(world-agent 視点)', ko: 'GM 설명(world-agent 시점)' },
  'canvas.trigger': { en: 'Trigger condition (free text)', zh: '触发条件(自由文本)', ja: 'トリガー条件(自由記述)', ko: '발동 조건(자유 서술)' },
  'canvas.failsafe': { en: 'Fail-safe', zh: '失败保护 fail-safe', ja: 'フェイルセーフ', ko: '페일세이프' },
  'canvas.relatedEntities': { en: 'Related entities ({n})', zh: '关联实体({n})', ja: '関連エンティティ({n})', ko: '연관 엔티티({n})' },
  'canvas.save': { en: 'Save', zh: '保存', ja: '保存', ko: '저장' },
  'arc.untitled': { en: 'untitled', zh: '未命名', ja: '無題', ko: '무제' },
  'arc.newNode': { en: 'New beat', zh: '新节点', ja: '新しいビート', ko: '새 비트' },
  'arc.addNode': { en: 'Beat', zh: '节点', ja: 'ビート', ko: '비트' },
  'arc.hint': {
    en: 'The character’s personal arc — ships inside the soul (trajectory/arc.json)',
    zh: '角色的个人剧情弧线 —— 存进 soul 包(trajectory/arc.json),随角色走',
    ja: 'キャラクターの物語アーク —— soul 内(trajectory/arc.json)に保存',
    ko: '캐릭터의 서사 아크 — soul 안(trajectory/arc.json)에 저장',
  },
  'arc.nodeTitle': { en: 'Arc beat', zh: '弧线节点', ja: 'アークビート', ko: '아크 비트' },
  'arc.fieldLabel': { en: 'Title', zh: '标题', ja: 'タイトル', ko: '제목' },
  'arc.fieldType': { en: 'Type', zh: '类型', ja: '種類', ko: '유형' },
  'arc.fieldText': {
    en: 'What happens / what it means to her', zh: '发生了什么 / 对她意味着什么',
    ja: '何が起き / 彼女にとって何を意味するか', ko: '무슨 일이 / 그녀에게 어떤 의미인지',
  },
  'arc.type.memory': { en: 'Memory', zh: '记忆', ja: '記憶', ko: '기억' },
  'arc.type.wound': { en: 'Wound', zh: '心结', ja: '心の傷', ko: '상처' },
  'arc.type.desire': { en: 'Desire', zh: '欲望', ja: '願望', ko: '욕망' },
  'arc.type.bond': { en: 'Bond', zh: '羁绊', ja: '絆', ko: '유대' },
  'arc.type.turning': { en: 'Turning point', zh: '转折', ja: '転機', ko: '전환점' },
  'arc.type.choice': { en: 'Choice', zh: '抉择', ja: '選択', ko: '선택' },
  'arc.type.ending': { en: 'Ending', zh: '结局', ja: '結末', ko: '결말' },
  'soul.tabFiles': { en: 'Files', zh: '资料', ja: '資料', ko: '자료' },
  'soul.tabPortrait': { en: 'Portrait', zh: '立绘', ja: '立ち絵', ko: '일러스트' },
  'soul.defaultName': { en: 'New character', zh: '新角色', ja: '新キャラクター', ko: '새 캐릭터' },
  'soul.secSoul': { en: 'CHARACTER', zh: '角色内容', ja: 'キャラクター', ko: '캐릭터' },
  'soul.tryTalk': { en: 'Try talking', zh: '试聊', ja: '会話してみる', ko: '대화해 보기' },
  'soul.chatSub': {
    en: 'every word edits her files', zh: '每句话都会写进她的文件',
    ja: '一言ごとにファイルへ', ko: '말할 때마다 파일에 기록',
  },
  'soul.inputPh': {
    en: 'What to change about her — just say it', zh: '想改她哪里,直接说',
    ja: '直したい所をそのまま', ko: '고칠 부분을 그냥 말하세요',
  },
  'soul.openerTitle': {
    en: 'Shape “{name}”', zh: '塑造「{name}」', ja: '「{name}」を形づくる', ko: '“{name}” 빚기',
  },
  'soul.openerDesc': {
    en: 'She starts as the template character (Elena). Pick how to make her yours:',
    zh: '她现在还是白模角色(艾琳娜)。选一个开始方式:',
    ja: '今はテンプレキャラ(エレナ)のまま。始め方を選んで:',
    ko: '지금은 템플릿 캐릭터(엘레나) 그대로입니다. 시작 방법을 고르세요:',
  },
  'soul.openerAnalyze': {
    en: 'Analyze the migration first', zh: '先分析迁移差距', ja: 'まず移行ギャップを分析', ko: '먼저 이전 격차 분석',
  },
  'soul.openerAnalyzeSub': {
    en: 'The agent reads the template character, compares her against your concept, and proposes a rewrite plan — no files touched yet.',
    zh: 'agent 通读白模角色,对比你的概念,给出改写计划 —— 先不动任何文件。',
    ja: 'agent がテンプレを読み、構想と比較して計画を提案 —— まだ変更しません。',
    ko: 'agent 가 템플릿을 읽고 구상과 비교해 계획을 제안 — 아직 수정 없음.',
  },
  'soul.openerAnalyzePrompt': {
    en: 'This character folder is a template (Elena). My concept is “{name} — {seed}”. Read through all her files (persona, background, memories, trajectory/story.md), compare template vs. concept, and give me a concrete rewrite plan (what to change, which files). Do NOT modify anything yet; finish by asking whether to start.',
    zh: '这个角色文件夹目前是白模(艾琳娜)。我的概念是「{name} — {seed}」。通读她的全部文件(persona、background、记忆、trajectory/story.md),对比白模与概念的差距,给我一份具体的改写计划(要改什么、动哪些文件)。先不要修改任何文件,最后问我是否开始。',
    ja: 'このキャラクターはテンプレ(エレナ)のままです。構想は「{name} — {seed}」。全ファイルを読み、テンプレと構想の差を比較し、具体的な書き換え計画を提示してください。まだ変更せず、最後に開始するか確認を。',
    ko: '이 캐릭터는 템플릿(엘레나) 상태입니다. 구상은 “{name} — {seed}”. 모든 파일을 읽고 템플릿과 구상의 차이를 비교해 구체적인 수정 계획을 제시하세요. 아직 수정하지 말고 마지막에 시작 여부를 물어보세요.',
  },
  'soul.openerBuild': {
    en: 'Just rewrite her now', zh: '直接开始改写', ja: 'すぐ書き換える', ko: '바로 다시 쓰기',
  },
  'soul.openerBuildSub': {
    en: 'The agent starts rewriting the template into your character right away — persona, backstory, memories, story arc.',
    zh: 'agent 立刻把白模改写成你的角色:人设、背景、记忆、剧情弧线逐步落地。',
    ja: 'agent がすぐテンプレをあなたのキャラへ書き換えます。',
    ko: 'agent 가 즉시 템플릿을 당신의 캐릭터로 다시 씁니다.',
  },
  'soul.openerBuildPrompt': {
    en: 'This character folder is a template (Elena). Rewrite her into my concept “{name} — {seed}”: persona files, background, memories, and trajectory/story.md + trajectory/arc.json (keep the arc.json JSON structure: nodes[{id,pos,data:{label,arc_type,text}}], edges). Step by step, explaining each change. Her name is {name}.',
    zh: '这个角色文件夹目前是白模(艾琳娜)。请把她改写成我的概念「{name} — {seed}」:人设(persona)、背景(background)、记忆、以及 trajectory/story.md 和 trajectory/arc.json(保持 arc.json 的 JSON 结构:nodes[{id,pos,data:{label,arc_type,text}}], edges)。逐步进行,每步说明改了什么。她的名字是 {name}。',
    ja: 'このキャラクターはテンプレ(エレナ)です。構想「{name} — {seed}」へ書き換えてください:persona、background、記憶、trajectory/story.md と arc.json(JSON 構造を維持)。段階的に、変更を説明しながら。名前は {name}。',
    ko: '이 캐릭터는 템플릿(엘레나)입니다. 구상 “{name} — {seed}” 으로 다시 쓰세요: persona, background, 기억, trajectory/story.md 와 arc.json(JSON 구조 유지). 단계별로 설명하며. 이름은 {name}.',
  },
  'soul.portraitDesc': {
    en: 'Portrait ships inside the soul (assets/portrait.png). Generate with the image backend from Archive settings, or upload your own.',
    zh: '立绘存进 soul 包(assets/portrait.png)。用档案室设置里配的图像后端生成,或自己上传。',
    ja: '立ち絵は soul 内(assets/portrait.png)。資料室設定の画像バックエンドで生成、または自分でアップロード。',
    ko: '일러스트는 soul 안(assets/portrait.png)에 저장됩니다. 자료실 설정의 이미지 백엔드로 생성하거나 직접 업로드하세요.',
  },
  'soul.portraitGen': { en: 'Generate', zh: '生成立绘', ja: '生成', ko: '생성' },
  'soul.portraitBusy': { en: 'Painting… (~1 min)', zh: '绘制中…(约 1 分钟)', ja: '描画中…(約1分)', ko: '그리는 중… (약 1분)' },
  'soul.portraitUpload': { en: 'Upload', zh: '上传', ja: 'アップロード', ko: '업로드' },
  'soul.tabArc': { en: 'Story arc', zh: '剧情弧线', ja: 'ストーリーアーク', ko: '서사 아크' },
  'soul.arcDocumentTitle': {
    en: 'Life trajectory (mirrors trajectory/arc.json; canvas edits rewrite this file)',
    zh: '人生轨迹(与 trajectory/arc.json 一一对应,画布修改会实时重写本文件)',
    ja: '人生の軌跡（trajectory/arc.json と対応し、キャンバスの編集でこのファイルも更新されます）',
    ko: '삶의 궤적(trajectory/arc.json과 대응하며 캔버스 편집 시 이 파일도 갱신됨)',
  },
  'soul.untitled': { en: 'Untitled', zh: '未命名', ja: '無題', ko: '제목 없음' },
  'soul.saveOnly': { en: 'Save', zh: '保存', ja: '保存', ko: '저장' },
  'soul.editEntry': { en: '✎ Edit', zh: '✎ 修改', ja: '✎ 編集', ko: '✎ 편집' },
  'canvas.cancel': { en: 'Cancel', zh: '取消', ja: 'キャンセル', ko: '취소' },
  'canvas.delete': { en: 'Delete', zh: '删除', ja: '削除', ko: '삭제' },
  'canvas.route': { en: 'Route', zh: '路线', ja: 'ルート', ko: '경로' },
  'canvas.storyEdge': { en: 'Story edge · condition', zh: '剧情连线 · 条件', ja: 'ストーリー連線 · 条件', ko: '스토리 연결 · 조건' },
  'canvas.relation': { en: 'Relation', zh: '关系', ja: '関係', ko: '관계' },
  'canvas.relationEmpty': {
    en: 'No relations yet — drag the connector on this node to another character to create one.',
    zh: '还没有关系 —— 拖这个节点边缘的圆点连到另一个角色即可建立。',
    ja: '関係はまだありません。このノード端の丸い接続点から別のキャラクターへドラッグすると作成できます。',
    ko: '아직 관계가 없습니다. 이 노드 가장자리의 연결점을 다른 캐릭터로 드래그해 만드세요.',
  },
  'canvas.edit': { en: 'Edit', zh: '编辑', ja: '編集', ko: '편집' },
  'canvas.close': { en: 'Close', zh: '关闭', ja: '閉じる', ko: '닫기' },
  'canvas.edgeKind': { en: 'Kind (road/trail/river…)', zh: '类型(road/trail/river…)', ja: '種類(road/trail/river…)', ko: '종류(road/trail/river…)' },
  'canvas.distance': { en: 'Distance', zh: '距离', ja: '距離', ko: '거리' },
  'canvas.bindFlag': { en: 'Bind flag (player/flags.json)', zh: '绑定 flag(player/flags.json)', ja: 'flag を紐付け(player/flags.json)', ko: 'flag 연결(player/flags.json)' },
  'canvas.noBind': { en: 'No binding', zh: '不绑定', ja: '紐付けなし', ko: '연결 안 함' },
  'canvas.compare': { en: 'Compare', zh: '比较', ja: '比較', ko: '비교' },
  'canvas.expectedValue': { en: 'Expected value', zh: '期望值', ja: '期待値', ko: '기댓값' },
  'canvas.conditionText': { en: 'Condition note (free text)', zh: '条件说明(自由文本)', ja: '条件説明(自由記述)', ko: '조건 설명(자유 서술)' },
  'canvas.edgeLabel': { en: 'Edge label (optional, for display)', zh: '连线标签(可空,显示用)', ja: '連線ラベル(任意、表示用)', ko: '연결 라벨(선택, 표시용)' },
  'canvas.relationType': { en: 'Relation type (debt/kin/grudge…)', zh: '关系类型(债务/亲属/仇怨…)', ja: '関係タイプ(負債/親族/遺恨…)', ko: '관계 유형(부채/친족/원한…)' },
  'canvas.description': { en: 'Note', zh: '说明', ja: '説明', ko: '설명' },
  'canvas.strength': { en: 'Strength ({n}/5)', zh: '强度({n}/5)', ja: '強度({n}/5)', ko: '강도({n}/5)' },
  'worldMap.you': { en: 'You', zh: '你', ja: 'あなた', ko: '나' },
  'worldMap.youAreHere': { en: 'You are here', zh: '你在此', ja: '現在地', ko: '현재 위치' },
  'worldMap.noCharacters': { en: 'No characters here.', zh: '此地暂无角色。', ja: 'ここにはキャラクターがいません。', ko: '이곳에는 캐릭터가 없습니다.' },

  // STORY_TYPE_LABELS (canvasData) — story node types
  'canvas.story.scene': { en: 'Scene', zh: '场景', ja: 'シーン', ko: '장면' },
  'canvas.story.event': { en: 'Event', zh: '事件', ja: 'イベント', ko: '이벤트' },
  'canvas.story.choice': { en: 'Choice', zh: '选择', ja: '選択', ko: '선택' },
  'canvas.story.check': { en: 'Check', zh: '判定', ja: '判定', ko: '판정' },
  'canvas.story.combat': { en: 'Combat', zh: '战斗', ja: '戦闘', ko: '전투' },
  'canvas.story.clue': { en: 'Clue', zh: '线索', ja: '手掛かり', ko: '단서' },
  'canvas.story.location': { en: 'Location', zh: '地点', ja: '地点', ko: '장소' },
  'canvas.story.reward': { en: 'Reward', zh: '奖励', ja: '報酬', ko: '보상' },
  'canvas.story.ending': { en: 'Ending', zh: '结局', ja: 'エンディング', ko: '결말' },
  'canvas.story.condition': { en: 'Condition', zh: '条件', ja: '条件', ko: '조건' },

  // OPERATOR_LABELS (canvasData) — edge condition operators
  'canvas.op.is_true': { en: 'is true', zh: '为真', ja: '真', ko: '참' },
  'canvas.op.is_false': { en: 'is false', zh: '为假', ja: '偽', ko: '거짓' },
  'canvas.op.equals': { en: 'equals', zh: '等于', ja: '等しい', ko: '같음' },
  'canvas.op.not_equals': { en: 'not equals', zh: '不等于', ja: '等しくない', ko: '다름' },
  'canvas.op.gte': { en: '≥', zh: '≥', ja: '≥', ko: '≥' },
  'canvas.op.lte': { en: '≤', zh: '≤', ja: '≤', ko: '≤' },

  // ── ModelAccessPanel ─────────────────────────────────────────
  'ma.readingProviders': {
    en: 'Loading… (if the engine is not running, start `neonrp web`)',
    zh: '读取中…(引擎未启动的话先跑 `neonrp web`)',
    ja: '読み込み中…(エンジン未起動なら先に `neonrp web`)',
    ko: '불러오는 중… (엔진 미실행 시 먼저 `neonrp web`)',
  },
  'ma.loadFailed': {
    en: 'Cannot reach the engine ({err}) — retrying every 3s…',
    zh: '连不上引擎({err})— 每 3 秒自动重试中…',
    ja: 'エンジンに接続できません({err})— 3 秒ごとに再試行中…',
    ko: '엔진에 연결할 수 없습니다 ({err}) — 3초마다 재시도 중…',
  },
  'ma.needKey': {
    en: 'This provider has no API key yet — enter it now, saved on the next step:',
    zh: '这个 provider 还没有 API key — 现在填,下一步保存:',
    ja: 'この provider にはまだ API key がありません — 今入力し、次のステップで保存:',
    ko: '이 provider 에 아직 API key 가 없습니다 — 지금 입력하면 다음 단계에서 저장:',
  },
  'ma.testConn': { en: 'Test connection', zh: '测连通', ja: '接続テスト', ko: '연결 테스트' },
  'ma.addCustom': { en: '＋ Custom API endpoint', zh: '＋ 自定义 API 端点', ja: '＋ カスタム API エンドポイント', ko: '＋ 사용자 지정 API 엔드포인트' },
  'ma.keyOptionalPlaceholder': { en: 'sk-… (optional for Ollama/LM Studio)', zh: 'sk-… (Ollama/LM Studio 可留空)', ja: 'sk-…（Ollama/LM Studio は空欄可）', ko: 'sk-… (Ollama/LM Studio는 비워도 됨)' },
  'ma.testing': { en: 'Testing…', zh: '测试中…', ja: 'テスト中…', ko: '테스트 중…' },
  'ma.connected': { en: '✓ connected ({ms}ms)', zh: '✓ 连通({ms}ms)', ja: '✓ 接続({ms}ms)', ko: '✓ 연결({ms}ms)' },
  'ma.failed': { en: '✗ {err}', zh: '✗ {err}', ja: '✗ {err}', ko: '✗ {err}' },
  'ma.failDefault': { en: 'failed', zh: '失败', ja: '失敗', ko: '실패' },

  // ── LocalPrePlay ─────────────────────────────────────────────
  'preplay.back': { en: '← Back', zh: '← 返回', ja: '← 戻る', ko: '← 뒤로' },
  'preplay.title': { en: 'Getting ready', zh: '进入前的准备', ja: '入場前の準備', ko: '입장 전 준비' },
  'preplay.subtitle': {
    en: 'World check · casting · model access',
    zh: '世界确认 · 带入角色 · 模型接入',
    ja: 'ワールド確認 · キャスティング · モデル接続',
    ko: '월드 확인 · 캐스팅 · 모델 연결',
  },
  'preplay.step1Title': { en: 'World check', zh: '世界确认', ja: 'ワールド確認', ko: '월드 확인' },
  'preplay.resumeSave': { en: 'Resume save', zh: '继续存档', ja: 'セーブを続ける', ko: '세이브 이어하기' },
  'preplay.newRun': { en: 'New run', zh: '新开一局', ja: '新規プレイ', ko: '새 플레이' },
  'preplay.resumeSaveWith': { en: 'Resume save · {sid}', zh: '继续存档 · {sid}', ja: 'セーブを続ける · {sid}', ko: '세이브 이어하기 · {sid}' },
  'preplay.step2Title': { en: 'Casting', zh: '带入角色', ja: 'キャスティング', ko: '캐스팅' },
  'preplay.castHint': { en: 'Casting · optional', zh: 'Casting · 可选', ja: 'Casting · 任意', ko: 'Casting · 선택' },
  'preplay.castNote': {
    en: 'The chosen characters appear as NPCs at the opening (same placement as the TUI\'s Casting).',
    zh: '选中的角色会作为 NPC 出现在开场(与 TUI 的 Casting 同一套投放)。',
    ja: '選んだキャラクターは開幕に NPC として登場します(TUI の Casting と同じ投入)。',
    ko: '선택한 캐릭터는 시작 시 NPC 로 등장합니다(TUI 의 Casting 과 동일한 배치).',
  },
  'preplay.castEmpty': {
    en: 'The character library is empty — this run has only the world\'s native characters. You can create characters in the library first.',
    zh: '角色库是空的 —— 这一局只有世界原生角色。可以先在档案室创建角色。',
    ja: 'キャラクター庫が空です —— この回はワールド固有のキャラクターのみ。先に資料室で作成できます。',
    ko: '캐릭터 라이브러리가 비었습니다 — 이번 플레이는 월드 고유 캐릭터만. 먼저 자료실에서 만들 수 있습니다.',
  },
  'preplay.step3Title': { en: 'Model access', zh: '模型接入', ja: 'モデル接続', ko: '모델 연결' },
  'preplay.modelHint': { en: 'Which LLM for this run', zh: '本局用哪个 LLM', ja: 'この回に使う LLM', ko: '이번 플레이에 쓸 LLM' },
  'preplay.credNote': {
    en: 'Credentials stay on this machine (~/.neonrp/config.json, same source as the TUI).',
    zh: '凭证只存本机(~/.neonrp/config.json,与 TUI 同源)。',
    ja: '認証情報はこの端末のみに保存(~/.neonrp/config.json、TUI と同源)。',
    ko: '자격 증명은 이 기기에만 저장(~/.neonrp/config.json, TUI 와 동일 소스).',
  },
  'preplay.entering': { en: 'Entering…', zh: '进入中…', ja: '入場中…', ko: '입장 중…' },
  'preplay.buildingWorld': { en: 'Building the world…', zh: '搭建世界中…', ja: 'ワールド構築中…', ko: '월드 구축 중…' },
  'preplay.enterWorld': { en: '▸ Enter the world', zh: '▸ 进入世界', ja: '▸ 世界に入る', ko: '▸ 세계로 들어가기' },

  // ── LocalLibrary ─────────────────────────────────────────────
  'lib.worlds': { en: 'World library', zh: '世界库', ja: 'ワールド庫', ko: '월드 라이브러리' },
  'lib.souls': { en: 'Character library', zh: '角色库', ja: 'キャラクター庫', ko: '캐릭터 라이브러리' },
  'lib.settings': { en: 'Settings', zh: '设置', ja: '設定', ko: '설정' },
  'lib.deleteWorldConfirm': {
    en: 'Delete world {id}? All its saves are cleared too, and this cannot be undone.',
    zh: '删除世界 {id}?它的所有存档一并清除,不可恢复。',
    ja: 'ワールド {id} を削除しますか?すべてのセーブも消え、元に戻せません。',
    ko: '월드 {id} 을(를) 삭제할까요? 모든 세이브도 삭제되며 되돌릴 수 없습니다.',
  },
  'lib.noWorlds': {
    en: 'No worlds of yours in the library yet — go to Create and start one from the white template, or download from the Hub.',
    zh: '库里还没有你的世界 — 去「创作」从白模板开一个,或从 Hub 下载。',
    ja: '庫にまだあなたのワールドがありません — 「創作」で白テンプレートから、または Hub からダウンロード。',
    ko: '라이브러리에 아직 내 월드가 없습니다 — "창작"에서 백지 템플릿으로 시작하거나 Hub 에서 다운로드하세요.',
  },
  'lib.localCreated': { en: 'created locally', zh: '本地创作', ja: 'ローカル創作', ko: '로컬 창작' },
  'lib.hubDownload': { en: 'Hub download', zh: 'Hub 下载', ja: 'Hub ダウンロード', ko: 'Hub 다운로드' },
  'lib.editBtn': { en: '✳ Edit', zh: '✳ 修改', ja: '✳ 編集', ko: '✳ 편집' },
  'lib.export': { en: '⇩ Export', zh: '⇩ 导出', ja: '⇩ エクスポート', ko: '⇩ 내보내기' },
  'lib.delete': { en: 'Delete', zh: '删除', ja: '削除', ko: '삭제' },
  'lib.deleteSoulConfirm': {
    en: 'Delete character {label}? This cannot be undone.',
    zh: '删除角色 {label}?不可恢复。',
    ja: 'キャラクター {label} を削除しますか?元に戻せません。',
    ko: '캐릭터 {label} 을(를) 삭제할까요? 되돌릴 수 없습니다.',
  },
  'lib.noSouls': {
    en: 'The character library is empty — go to Create to generate a character, import a tavern card, or download from the Hub.',
    zh: '角色库是空的 — 去「创作」生成一个角色、导入酒馆卡,或从 Hub 下载。',
    ja: 'キャラクター庫が空です — 「創作」で生成、酒場カードをインポート、または Hub からダウンロード。',
    ko: '캐릭터 라이브러리가 비었습니다 — "창작"에서 생성, 태번 카드 가져오기, 또는 Hub 에서 다운로드하세요.',
  },
  'lib.talk': { en: '▸ Talk', zh: '▸ 对话', ja: '▸ 対話', ko: '▸ 대화' },
  'lib.settingsIntroPre': { en: 'Models & API keys (stored in', zh: '模型与 API key(存入', ja: 'モデルと API key(保存先', ko: '모델 및 API key(저장 위치' },
  'lib.settingsIntroPost': {
    en: ', same source as the TUI settings).',
    zh: ',与 TUI 设置同源)。',
    ja: '、TUI 設定と同源)。',
    ko: ', TUI 설정과 동일 소스).',
  },
  'lib.connected': { en: '✓ connected ({ms}ms)', zh: '✓ 连通({ms}ms)', ja: '✓ 接続({ms}ms)', ko: '✓ 연결({ms}ms)' },
  'lib.failDefault': { en: 'failed', zh: '失败', ja: '失敗', ko: '실패' },
  'lib.pasteKey': { en: 'Paste API key', zh: '粘贴 API key', ja: 'API key を貼り付け', ko: 'API key 붙여넣기' },
  'lib.save': { en: 'Save', zh: '保存', ja: '保存', ko: '저장' },
  'lib.cancel': { en: 'Cancel', zh: '取消', ja: 'キャンセル', ko: '취소' },
  'lib.changeKey': { en: 'Change key', zh: '换 key', ja: 'key を変更', ko: 'key 변경' },
  'lib.setKey': { en: 'Set key', zh: '设 key', ja: 'key を設定', ko: 'key 설정' },
  'lib.test': { en: 'Test', zh: '测试', ja: 'テスト', ko: '테스트' },
  'lib.del': { en: 'Del', zh: '删', ja: '削', ko: '삭제' },
  'lib.testing': { en: 'Testing…', zh: '测试中…', ja: 'テスト中…', ko: '테스트 중…' },
  'lib.testingAll': { en: 'Testing each…', zh: '逐个测试中…', ja: '順にテスト中…', ko: '차례로 테스트 중…' },
  'lib.testAll': { en: '⟳ Test all', zh: '⟳ 测试全部', ja: '⟳ すべてテスト', ko: '⟳ 전체 테스트' },
  'lib.customTitle': { en: 'Add custom API endpoint', zh: '添加自定义 API 端点', ja: 'カスタム API エンドポイントを追加', ko: '사용자 지정 API 엔드포인트 추가' },
  'lib.customDesc': {
    en: 'Point at any OpenAI-compatible endpoint (local Ollama / LM Studio / vLLM / self-hosted). It shows up as a selectable provider above and can be deleted.',
    zh: '接入任意 OpenAI 兼容端点(本地 Ollama / LM Studio / vLLM / 自建)。保存后会作为可选 provider 出现在上面,可随时删除。',
    ja: 'OpenAI 互換の任意エンドポイント(ローカル Ollama / LM Studio / vLLM / 自前ホスト)を指定。保存すると上の一覧に選択可能な provider として表示され、削除もできます。',
    ko: 'OpenAI 호환 엔드포인트(로컬 Ollama / LM Studio / vLLM / 자체 호스팅)를 지정. 저장하면 위 목록에 선택 가능한 provider 로 표시되며 삭제할 수 있습니다.',
  },
  'lib.customId': { en: 'ID (unique)', zh: 'ID(唯一)', ja: 'ID(一意)', ko: 'ID(고유)' },
  'lib.customModel': { en: 'Model name', zh: '模型名', ja: 'モデル名', ko: '모델 이름' },
  'lib.customBaseUrl': { en: 'Base URL', zh: 'API 端点 base_url', ja: 'ベース URL', ko: '베이스 URL' },
  'lib.customKey': { en: 'API key (optional)', zh: 'API key(可选)', ja: 'API キー(任意)', ko: 'API 키(선택)' },
  'lib.customSave': { en: 'Add endpoint', zh: '保存端点', ja: 'エンドポイントを追加', ko: '엔드포인트 추가' },
  'lib.customTest': { en: 'Save & test connection', zh: '保存并测试连接', ja: '保存して接続テスト', ko: '저장 후 연결 테스트' },
  'lib.customNeedFields': { en: 'ID / model / base URL are required', zh: 'ID / 模型名 / base_url 必填', ja: 'ID / モデル名 / ベース URL は必須', ko: 'ID / 모델 이름 / 베이스 URL 은 필수' },
  'lib.customAdded': { en: '✓ Added {id}', zh: '✓ 已添加 {id}', ja: '✓ {id} を追加しました', ko: '✓ {id} 추가됨' },
  'lib.createLLM': { en: 'Creation LLM', zh: '创作用 LLM', ja: '創作用 LLM', ko: '창작용 LLM' },
  'lib.createLLMDesc': {
    en: 'Which model the "new world / new character / import" creation flows use (independent of the preset picked for play).',
    zh: '「新的世界 / 新的角色 / 导入」这些创作流用哪个模型(与游玩时选的 preset 无关)。',
    ja: '「新しいワールド / 新しいキャラクター / インポート」の創作フローで使うモデル(プレイ時に選ぶ preset とは無関係)。',
    ko: '"새 월드 / 새 캐릭터 / 가져오기" 창작 흐름에 쓰는 모델(플레이 시 고른 preset 과 무관).',
  },
  'lib.autoFirst': { en: 'Auto (first available)', zh: '自动(第一个可用的)', ja: '自動(最初に使えるもの)', ko: '자동(사용 가능한 첫 번째)' },
  'lib.imgOff': { en: 'Off', zh: '关闭', ja: 'オフ', ko: '끄기' },
  'lib.imgAdvanced': { en: 'Advanced (custom workflow)', zh: '高级(自定义 workflow)', ja: '詳細(カスタム workflow)', ko: '고급(커스텀 workflow)' },
  'lib.imgWorkflowLabel': { en: 'Workflow (API JSON path or inline)', zh: 'workflow(API JSON 路径或内联)', ja: 'ワークフロー（API JSON のパスまたはインライン）', ko: '워크플로(API JSON 경로 또는 인라인)' },
  'lib.imgAdvancedDesc': {
    en: 'Bring your own ComfyUI API-format workflow: paste JSON or a file path, then name the nodes that receive the prompt / negative / seed and the output image node. Leave empty to use the built-in graph.',
    zh: '自带 ComfyUI workflow(API 格式):粘贴 JSON 或文件路径,并指定接收 prompt/负面/seed 的节点 id 与输出图像节点。留空 = 用内置默认图。',
    ja: '独自の ComfyUI workflow(API 形式):JSON かパスを貼り、prompt/negative/seed を受けるノード id と出力ノードを指定。空欄なら内蔵グラフ。',
    ko: '자체 ComfyUI workflow(API 형식): JSON 또는 경로를 붙여넣고 prompt/negative/seed 노드 id 와 출력 노드를 지정. 비우면 내장 그래프.',
  },
  'lib.imgEmptyDefault': { en: 'empty = built-in', zh: '留空=内置', ja: '空=内蔵', ko: '비움=내장' },
  'lib.imgKeySet': { en: 'key saved', zh: '已存 key', ja: 'キー保存済み', ko: '키 저장됨' },
  'lib.imgSaved': { en: '✓ saved & active', zh: '✓ 已保存并生效', ja: '✓ 保存して有効', ko: '✓ 저장·활성' },
  'lib.imgSavedOff': { en: '✓ saved (backend off/incomplete)', zh: '✓ 已保存(后端关闭或未配全)', ja: '✓ 保存(バックエンド未完)', ko: '✓ 저장(백엔드 미완)' },
  'lib.imageGen': { en: 'Image generation', zh: '图像生成', ja: '画像生成', ko: '이미지 생성' },
  'lib.configured': { en: '● configured', zh: '● 已配置', ja: '● 設定済み', ko: '● 설정됨' },
  'lib.imageGenDesc': {
    en: 'ComfyUI address (for portrait/cover generation; blank = off).',
    zh: 'ComfyUI 地址(立绘/封面生成用;留空 = 关闭)。',
    ja: 'ComfyUI アドレス(立ち絵/カバー生成用;空欄 = オフ)。',
    ko: 'ComfyUI 주소(일러스트/커버 생성용; 비우면 = 끔).',
  },
  'lib.deleteEntryConfirm': {
    en: 'Delete the local config for entry {id}?',
    zh: '删除条目 {id} 的本机配置?',
    ja: '項目 {id} のローカル設定を削除しますか?',
    ko: '항목 {id} 의 로컬 설정을 삭제할까요?',
  },
  'lib.hubTokenPrompt': {
    en: 'WorldHub token (get it at worldlines.gg/account, stored on this machine only):',
    zh: 'WorldHub token(worldlines.gg/account 获取,只存本机):',
    ja: 'WorldHub token(worldlines.gg/account で取得、この端末のみに保存):',
    ko: 'WorldHub token (worldlines.gg/account 에서 발급, 이 기기에만 저장):',
  },
  'lib.uploadConfirm': {
    en: 'Upload "{label}" to the Hub? Uploading publishes it publicly (can be unlisted later).',
    zh: '把「{label}」上传到 Hub?上传即对外发布(可下架)。',
    ja: '「{label}」を Hub にアップロードしますか?アップロード即公開(後で取り下げ可)。',
    ko: '"{label}" 을(를) Hub 에 업로드할까요? 업로드 시 공개됩니다(나중에 내릴 수 있음).',
  },
  'lib.uploading': { en: 'Uploading…', zh: '上传中…', ja: 'アップロード中…', ko: '업로드 중…' },
  'lib.hubBtn': { en: '⇪ Hub', zh: '⇪ Hub', ja: '⇪ Hub', ko: '⇪ Hub' },
}
