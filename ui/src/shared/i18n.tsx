/**
 * Dependency-free i18n. Four languages (matches the NeonRP engine):
 * en · zh · ja · ko. Language persists in localStorage and is
 * switchable from the header. `t(key)` falls back to English, then to
 * the key itself, so a missing translation is never a blank UI.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

export const LANGS = ['en', 'zh', 'ja', 'ko'] as const
export type Lang = (typeof LANGS)[number]

export const LANG_LABEL: Record<Lang, string> = {
  en: 'EN',
  zh: '中文',
  ja: '日本語',
  ko: '한국어',
}

type Dict = Record<string, Partial<Record<Lang, string>> & { en: string }>

// Functional / chrome strings. Marketing prose on the catalog pages is
// tracked separately (see docs/TASKS.md) to keep translation quality
// high rather than machine-rough.
const STRINGS: Dict = {
  'header.localTestAccount': { en: 'local test account', zh: '本地测试账户', ja: 'ローカルテストアカウント', ko: '로컬 테스트 계정' },
  'review.playable': { en: 'playable', zh: '可玩', ja: 'プレイ可能', ko: '플레이 가능' },
  'review.notPlayable': { en: 'not playable', zh: '不可玩', ja: 'プレイ不可', ko: '플레이 불가' },
  'review.blockers': { en: 'blockers', zh: '阻断', ja: 'ブロッカー', ko: '차단' },
  'review.warnings': { en: 'warnings', zh: '提醒', ja: '警告', ko: '경고' },
  'review.rejectPrompt': { en: 'Return note (visible to the creator, required):', zh: '退回留言(创作者可见,必填):', ja: '差し戻し理由（作成者に表示・必須）:', ko: '반려 사유(제작자에게 표시, 필수):' },
  'review.title': { en: 'Review queue', zh: '审查队列', ja: '審査キュー', ko: '심사 대기열' },
  'review.status.pending': { en: 'Pending', zh: '待审', ja: '審査待ち', ko: '심사 대기' },
  'review.status.approved': { en: 'Published', zh: '已上架', ja: '公開済み', ko: '게시됨' },
  'review.status.rejected': { en: 'Returned', zh: '已退回', ja: '差し戻し', ko: '반려됨' },
  'review.refresh': { en: 'Refresh', zh: '刷新', ja: '更新', ko: '새로고침' },
  'review.emptyPending': { en: 'The queue is empty — no submissions are waiting for review.', zh: '队列空 — 没有等待审查的提交。', ja: 'キューは空です — 審査待ちの提出はありません。', ko: '대기열이 비었습니다 — 심사 대기 제출물이 없습니다.' },
  'review.empty': { en: 'No records.', zh: '暂无记录。', ja: '記録はありません。', ko: '기록이 없습니다.' },
  'review.note': { en: 'Note', zh: '留言', ja: 'コメント', ko: '메모' },
  'review.approve': { en: 'Approve', zh: '通过', ja: '承認', ko: '승인' },
  'review.reject': { en: 'Return', zh: '退回', ja: '差し戻す', ko: '반려' },
  'review.inspectZip': { en: 'Inspect zip', zh: 'zip 细查', ja: 'zipを確認', ko: 'zip 검사' },
  'nav.worlds': { en: 'Worlds', zh: '世界', ja: 'ワールド', ko: '월드' },
  'nav.souls': { en: 'Souls', zh: '灵魂', ja: 'ソウル', ko: '소울' },
  'nav.create': { en: 'Create', zh: '创作', ja: '創作', ko: '창작' },
  'nav.docs': { en: 'Docs', zh: '文档', ja: 'ドキュメント', ko: '문서' },
  'nav.site': { en: 'Site', zh: '官网', ja: 'サイト', ko: '사이트' },
  'nav.download': { en: 'Download', zh: '下载', ja: 'ダウンロード', ko: '다운로드' },
  'play.downloadApp': { en: 'Get the app', zh: '下载应用', ja: 'アプリを入手', ko: '앱 받기' },

  'auth.signIn': { en: 'Sign in', zh: '登录', ja: 'ログイン', ko: '로그인' },
  'auth.signOut': { en: 'Sign out', zh: '退出', ja: 'ログアウト', ko: '로그아웃' },
  'auth.account': { en: 'Account', zh: '账号', ja: 'アカウント', ko: '계정' },
  // ── /account page ──────────────────────────────────────────
  'account.tag': {
    en: '// account',
    zh: '// 账号',
    ja: '// アカウント',
    ko: '// 계정',
  },
  'account.plays': { en: 'Plays', zh: '存档', ja: 'プレイ履歴', ko: '플레이' },
  'account.playsSub': {
    en: 'Worlds and souls you have entered. Tap to resume the scene.',
    zh: '你进入过的世界和角色。点击继续。',
    ja: '入ったことのある世界とキャラクター。タップで続き。',
    ko: '들어가본 세계와 영혼. 탭하여 이어하기.',
  },
  'account.playsEmpty': {
    en: 'No plays yet. Pick a world or soul to start.',
    zh: '还没有玩过。挑一个世界或角色开始。',
    ja: 'まだプレイがありません。世界かキャラクターを選んでください。',
    ko: '아직 플레이 기록이 없습니다.',
  },
  'account.warm': { en: 'warm', zh: '热载', ja: 'ホット', ko: '활성' },
  'account.savesWord': { en: 'saves', zh: '存档', ja: 'セーブ', ko: '세이브' },
  'account.public': { en: 'Public', zh: '公开', ja: '公開', ko: '공개' },
  'account.hidden': { en: 'Hidden', zh: '隐藏', ja: '非公開', ko: '비공개' },
  'account.makePublic': {
    en: 'Make public — show on the Hub',
    zh: '设为公开 — 显示在 Hub',
    ja: '公開する — Hub に表示',
    ko: '공개로 — 허브에 표시',
  },
  'account.makeHidden': {
    en: 'Hide — keep it only in your account',
    zh: '隐藏 — 只留在你的账号里',
    ja: '非公開 — アカウント内のみ',
    ko: '숨기기 — 내 계정에만',
  },
  'account.drafts': { en: 'Drafts', zh: '草稿', ja: 'ドラフト', ko: '초안' },
  'account.draftsSub': {
    en: 'In-progress creations. Tap to resume the interview.',
    zh: '进行中的创作。点击继续创作。',
    ja: '作成中。タップで続き。',
    ko: '진행 중인 창작.',
  },
  'account.draftsEmpty': {
    en: 'No drafts. Start a new world or soul.',
    zh: '还没有草稿。开始创作世界或角色。',
    ja: 'ドラフトはまだありません。',
    ko: '초안이 없습니다.',
  },
  'account.published': {
    en: 'Published',
    zh: '已入库',
    ja: '公開済み',
    ko: '게시됨',
  },
  'account.builtIn': {
    en: 'built in',
    zh: '建于',
    ja: '出身',
    ko: '출신',
  },
  'account.publishedSub': {
    en: 'Your entries on WorldHub / SoulHub.',
    zh: '你在 WorldHub / SoulHub 上的作品。',
    ja: 'WorldHub / SoulHub 上のあなたの作品。',
    ko: 'WorldHub / SoulHub 의 당신 작품.',
  },
  'account.publishedEmpty': {
    en: 'You have not published anything yet.',
    zh: '还没有入库任何作品。',
    ja: 'まだ公開していません。',
    ko: '아직 게시한 작품이 없습니다.',
  },
  'account.edit': {
    en: 'Edit',
    zh: '继续编辑',
    ja: '編集',
    ko: '편집',
  },
  // Owner toolbar on the detail page (shown only for assets you own)
  'owner.bar': {
    en: 'YOUR ASSET',
    zh: '你的作品',
    ja: 'あなたの作品',
    ko: '내 작품',
  },
  'owner.download': {
    en: 'Download',
    zh: '下载',
    ja: 'ダウンロード',
    ko: '다운로드',
  },
  'owner.replaceCover': {
    en: 'Replace cover',
    zh: '更换封面',
    ja: 'カバーを変更',
    ko: '커버 교체',
  },
  'owner.edit': {
    en: 'Edit',
    zh: '编辑',
    ja: '編集',
    ko: '편집',
  },
  'owner.unpublish': {
    en: 'Unpublish',
    zh: '下架',
    ja: '公開停止',
    ko: '게시 취소',
  },
  'owner.unpublishConfirm': {
    en: 'Remove "{name}" from your published list? The bundle stays reachable by hash.',
    zh: '把「{name}」从你的入库列表移除?包仍可通过 hash 访问。',
    ja: '「{name}」を公開リストから外しますか?バンドルはハッシュで引き続き取得できます。',
    ko: '"{name}" 을(를) 게시 목록에서 제거할까요? 번들은 해시로 계속 접근할 수 있습니다.',
  },
  // Soul seed (name + one-liner → generate, no interview) + templates
  'soulSeed.descPlaceholder': {
    en: 'One line — who are they? (optional)',
    zh: '一句话——他/她是谁?(可留空)',
    ja: '一言で——どんな人?(任意)',
    ko: '한 줄로 — 그/그녀는 누구인가요? (선택)',
  },
  // World seed one-liner — optional premise concept; blank = full interview.
  'worldSeed.descPlaceholder': {
    en: 'One line — what is this world? (optional)',
    zh: '一句话——这是个什么世界?(可留空)',
    ja: '一言で——どんな世界?(任意)',
    ko: '한 줄로 — 어떤 세계인가요? (선택)',
  },
  'soulSeed.orTemplate': {
    en: 'OR GENERATE FROM A TEMPLATE',
    zh: '或从模板生成',
    ja: 'またはテンプレートから生成',
    ko: '또는 템플릿에서 생성',
  },
  'tpl.elena.name': { en: 'Elena', zh: '艾琳娜', ja: 'エレナ', ko: '엘레나' },
  'tpl.elena.desc': {
    en: 'A gentle amnesiac healer',
    zh: '温柔的失忆治愈师',
    ja: '記憶を失くした優しい癒し手',
    ko: '기억을 잃은 다정한 치유사',
  },
  'tpl.baiheng.name': { en: 'Baiheng', zh: '白蘅', ja: '白蘅', ko: '백형' },
  'tpl.baiheng.desc': {
    en: 'A singer who lost their face in the yokai market',
    zh: '妖市中丢了脸的唱者',
    ja: '妖市で顔を失くした唄い手',
    ko: '요괴 시장에서 얼굴을 잃은 가인',
  },
  'tpl.yanyan.name': { en: 'Yanyan', zh: '盐砚英', ja: '塩硯英', ko: '염연영' },
  'tpl.yanyan.desc': {
    en: 'A silver-masked inquisitor',
    zh: '戴银面的审判官',
    ja: '銀の面を着けた審判官',
    ko: '은가면을 쓴 심판관',
  },
  'create.worldExplorer': {
    en: 'World Explorer',
    zh: '世界探索',
    ja: 'ワールド探索',
    ko: '월드 탐색',
  },
  'create.soulTalk': {
    en: 'Soul Talk',
    zh: '角色对话',
    ja: 'ソウル対話',
    ko: '소울 대화',
  },
  // Soul psyche panel (play page, soul only)
  'psyche.title': {
    en: 'INNER STATE',
    zh: '内心状态',
    ja: '内なる状態',
    ko: '내면 상태',
  },
  'lanes.title': {
    en: 'SOULS IN SCENE',
    zh: '在场灵魂',
    ja: '在場の魂',
    ko: '현장의 영혼',
  },
  'lanes.mapTitle': {
    en: 'MAP · WHO IS WHERE',
    zh: '地图 · 谁在哪',
    ja: 'マップ · 誰がどこに',
    ko: '지도 · 누가 어디에',
  },
  'play.you': { en: 'you', zh: '你', ja: 'あなた', ko: '당신' },
  'play.history': { en: 'HISTORY', zh: '对话履历', ja: '会話履歴', ko: '대화 기록' },
  'manage.title': { en: 'Manage & publish', zh: '管理与发布', ja: '管理と公開', ko: '관리 및 게시' },
  'manage.back': { en: 'Account', zh: '返回账号', ja: 'アカウント', ko: '계정' },
  'manage.loading': { en: 'Loading…', zh: '加载中…', ja: '読み込み中…', ko: '불러오는 중…' },
  'manage.notFound': { en: 'Not found.', zh: '未找到。', ja: '見つかりません。', ko: '찾을 수 없습니다.' },
  'manage.name': { en: 'Name', zh: '名称', ja: '名前', ko: '이름' },
  'manage.description': { en: 'Description', zh: '简介', ja: '説明', ko: '설명' },
  'manage.descPlaceholder': {
    en: 'A short blurb players see in the catalog…',
    zh: '玩家在目录里看到的一句话简介…',
    ja: 'カタログに表示される短い紹介文…',
    ko: '카탈로그에 표시될 짧은 소개…',
  },
  'manage.save': { en: 'Save', zh: '保存', ja: '保存', ko: '저장' },
  'manage.saved': { en: 'Saved.', zh: '已保存。', ja: '保存しました。', ko: '저장됨.' },
  'manage.cover': { en: 'Cover', zh: '封面', ja: 'カバー', ko: '커버' },
  'manage.portraitSoul': { en: 'Portrait (立绘)', zh: '立绘', ja: '立ち絵', ko: '일러스트' },
  'manage.portraitWorld': { en: 'Soul portrait', zh: '内置 soul 立绘', ja: 'ソウル立ち絵', ko: '소울 일러스트' },
  'manage.upload': { en: 'Upload', zh: '上传', ja: 'アップロード', ko: '업로드' },
  'manage.hidden': { en: 'Hidden (unlisted)', zh: '隐藏(未公开)', ja: '非公開', ko: '비공개' },
  'manage.public': { en: 'Public', zh: '公开', ja: '公開', ko: '공개' },
  'manage.goPublic': { en: 'Make public', zh: '公开发布', ja: '公開する', ko: '공개하기' },
  'manage.makeHidden': { en: 'Make hidden', zh: '设为隐藏', ja: '非公開にする', ko: '비공개로' },
  'manage.nowPublic': { en: 'Now public.', zh: '已公开。', ja: '公開しました。', ko: '공개됨.' },
  'manage.nowHidden': { en: 'Now hidden.', zh: '已隐藏。', ja: '非公開にしました。', ko: '비공개됨.' },
  'manage.gateSoul': {
    en: 'Add a cover and a 立绘 before going public.',
    zh: '补齐封面和立绘后才能公开发布。',
    ja: 'カバーと立ち絵を追加すると公開できます。',
    ko: '커버와 일러스트를 추가하면 공개할 수 있습니다.',
  },
  'manage.gateWorld': {
    en: 'Add a cover before going public.',
    zh: '补齐封面后才能公开发布。',
    ja: 'カバーを追加すると公開できます。',
    ko: '커버를 추가하면 공개할 수 있습니다.',
  },
  'manage.editContent': { en: 'Edit content', zh: '编辑内容', ja: '内容を編集', ko: '내용 편집' },
  'manage.unpublish': { en: 'Unpublish', zh: '下架', ja: '公開停止', ko: '게시 취소' },
  'manage.unpublishConfirm': {
    en: 'Remove this from your published list?',
    zh: '从你的已发布列表中移除?',
    ja: '公開リストから削除しますか?',
    ko: '게시 목록에서 제거할까요?',
  },
  'psyche.confidence': { en: 'Confidence', zh: '确信', ja: '確信', ko: '확신' },
  'psyche.urgency': { en: 'Urgency', zh: '紧迫', ja: '切迫', ko: '긴박' },
  'psyche.intent': { en: 'Intent', zh: '意图', ja: '意図', ko: '의도' },
  'psyche.innerVoice': {
    en: 'Inner voice',
    zh: '内心独白',
    ja: '内心の声',
    ko: '내면의 목소리',
  },
  'psyche.memory': { en: 'Memory', zh: '记忆', ja: '記憶', ko: '기억' },
  'psyche.needsWorld': {
    en: 'needs world',
    zh: '待世界裁定',
    ja: '世界判断待ち',
    ko: '세계 판단 대기',
  },
  // Upload (zip → WorldHub / SoulHub)
  'account.upload': {
    en: 'Upload from library',
    zh: '上传到 Hub',
    ja: 'ライブラリから公開',
    ko: '라이브러리에서 게시',
  },
  'account.uploadSub': {
    en: 'Drop in a zip bundle of a world or soul you authored locally — it goes straight to WorldHub / SoulHub. No CLI, no AWS keys needed.',
    zh: '把本地做好的世界或角色 zip 拖进来 —— 直接上 WorldHub / SoulHub。不需要 CLI,不需要 AWS 凭据。',
    ja: 'ローカルで作ったワールドかソウルの zip をそのまま WorldHub / SoulHub へ。CLI も AWS 認証も不要です。',
    ko: '로컬에서 만든 월드나 소울의 zip 을 그대로 WorldHub / SoulHub 로 — CLI 도 AWS 인증도 필요 없습니다.',
  },
  'account.uploadWorld': {
    en: 'World',
    zh: '世界',
    ja: 'ワールド',
    ko: '월드',
  },
  'account.uploadSoul': {
    en: 'Soul',
    zh: '角色',
    ja: 'ソウル',
    ko: '소울',
  },
  'account.uploadPickZip': {
    en: 'Choose a .zip file (max 20 MB)…',
    zh: '选择一个 .zip 文件(最大 20 MB)…',
    ja: '.zip ファイルを選択(最大 20 MB)…',
    ko: '.zip 파일 선택(최대 20 MB)…',
  },
  'account.uploadSlugPh': {
    en: 'slug (optional — derived if blank)',
    zh: 'slug(可选,留空则自动)',
    ja: 'スラッグ(任意:空欄なら自動)',
    ko: '슬러그(선택,비워두면 자동)',
  },
  'account.uploadNamePh': {
    en: 'Display name (optional)',
    zh: '显示名称(可选)',
    ja: '表示名(任意)',
    ko: '표시 이름(선택)',
  },
  'account.uploadUnlisted': {
    en: 'Keep unlisted (still reachable by hash, hidden from catalog list)',
    zh: '保持未公开(他人通过 hash 仍可访问,但不出现在目录列表)',
    ja: '非公開のまま(ハッシュからは到達可能、カタログ一覧には出ません)',
    ko: '비공개 유지(해시로는 접근 가능, 카탈로그 목록에는 안 뜸)',
  },
  'account.uploadGo': {
    en: 'Upload to Hub',
    zh: '上传到 Hub',
    ja: 'Hub に公開',
    ko: 'Hub 에 게시',
  },
  'account.uploadOk': {
    en: 'Uploaded as {slug}',
    zh: '已上传为 {slug}',
    ja: '{slug} として公開',
    ko: '{slug} 으로 게시됨',
  },
  'account.uploadHint': {
    en: 'World zip must contain .neonrp/manifest.json. Soul zip must contain manifest.json (per SOUL-PROTOCOL). Daily cap: 20 uploads / account.',
    zh: '世界 zip 需含 .neonrp/manifest.json;角色 zip 需含 manifest.json(SOUL-PROTOCOL)。每账号每天上限 20 次。',
    ja: 'ワールド zip は .neonrp/manifest.json 必須、ソウル zip は manifest.json 必須(SOUL-PROTOCOL)。1 日 20 件 / アカウント上限。',
    ko: '월드 zip 은 .neonrp/manifest.json, 소울 zip 은 manifest.json (SOUL-PROTOCOL) 필수. 계정당 일 20 건 한도.',
  },
  'account.unpublish': {
    en: 'Remove from my list',
    zh: '从我的库存中移除',
    ja: 'マイリストから削除',
    ko: '내 목록에서 제거',
  },
  'account.unpublishConfirm': {
    en: 'Remove "{name}" from your published list? The catalog entry stays at its hash for anyone who already has it — this only clears your view.',
    zh: '把 "{name}" 从你的库存中移除? 公共目录里的版本仍然保留(任何人通过 hash 都能访问),只是你的账号页不再显示。',
    ja: '"{name}" をマイリストから削除しますか? カタログの版はハッシュで参照されている人には残ります — あなたのビューだけが消えます。',
    ko: '"{name}" 을(를) 내 목록에서 제거하시겠습니까? 카탈로그 항목은 해시로 이미 접근하는 사람들에게는 남고, 이 화면에서만 사라집니다.',
  },
  'account.sessions': {
    en: 'Sessions',
    zh: '会话',
    ja: 'セッション',
    ko: '세션',
  },
  'account.sessionsSub': {
    en: 'Devices currently signed in to this account. Revoke any you don\'t recognize.',
    zh: '当前已登录的设备。看到不认识的请撤销。',
    ja: '現在サインイン中のデバイス。見覚えがなければ取り消してください。',
    ko: '현재 로그인된 기기. 모르는 항목은 취소하세요.',
  },
  'account.sessionsEmpty': {
    en: 'No active sessions.',
    zh: '没有活跃的会话。',
    ja: 'アクティブなセッションはありません。',
    ko: '활성 세션이 없습니다.',
  },
  'account.thisDevice': {
    en: 'this device',
    zh: '当前设备',
    ja: 'このデバイス',
    ko: '이 기기',
  },
  'account.unknownDevice': {
    en: 'unknown device',
    zh: '未知设备',
    ja: '不明なデバイス',
    ko: '알 수 없는 기기',
  },
  'account.lastSeen': {
    en: 'last seen',
    zh: '最近活动',
    ja: '最終ログイン',
    ko: '최근 활동',
  },
  'account.revoke': {
    en: 'Revoke',
    zh: '撤销',
    ja: '取り消し',
    ko: '취소',
  },
  'account.revokeOthers': {
    en: 'Sign out everywhere except this device',
    zh: '退出此设备外的所有会话',
    ja: 'このデバイス以外すべてサインアウト',
    ko: '이 기기를 제외한 모든 곳에서 로그아웃',
  },
  'account.revokeOthersConfirm': {
    en: 'Sign out of all other devices? They will need to sign in again.',
    zh: '退出其他设备的所有会话？他们需要重新登录。',
    ja: '他のすべてのデバイスからサインアウトしますか？再ログインが必要です。',
    ko: '다른 모든 기기에서 로그아웃하시겠어요? 다시 로그인해야 합니다.',
  },
  'account.apiTokens': { en: 'API Tokens', zh: 'API 令牌', ja: 'APIトークン', ko: 'API 토큰' },
  'account.apiTokensSub': {
    en: 'Create tokens for the NeonRP CLI or CI. Each token can publish worlds and souls. Revoke any token at any time.',
    zh: '为 NeonRP 命令行或 CI 创建令牌。每个令牌可以发布世界和角色。随时可以撤销。',
    ja: 'NeonRP CLI や CI 用のトークンを作成します。各トークンは世界とソウルを公開できます。いつでも無効化できます。',
    ko: 'NeonRP CLI 또는 CI용 토큰을 생성합니다. 각 토큰은 세계와 소울을 게시할 수 있습니다. 언제든지 취소할 수 있습니다.',
  },
  'account.apiTokenLabel': { en: 'Label (e.g. "Mac Studio")', zh: '标签（如 "Mac Studio"）', ja: 'ラベル（例: "Mac Studio"）', ko: '라벨 (예: "Mac Studio")' },
  'account.apiTokenCreate': { en: 'Create Token', zh: '创建令牌', ja: 'トークン作成', ko: '토큰 생성' },
  'account.apiTokenNew': {
    en: 'Copy this token now — it won\'t be shown again.',
    zh: '立即复制此令牌——它不会再显示。',
    ja: 'このトークンは二度と表示されません。今コピーしてください。',
    ko: '지금 복사하세요 — 이 토큰은 다시 표시되지 않습니다.',
  },
  'account.apiTokenUsage': {
    en: 'export HUB_API_TOKEN=<token>',
    zh: 'export HUB_API_TOKEN=<令牌>',
    ja: 'export HUB_API_TOKEN=<トークン>',
    ko: 'export HUB_API_TOKEN=<토큰>',
  },
  'account.apiTokenRevoke': { en: 'Revoke', zh: '撤销', ja: '無効化', ko: '취소' },
  'account.apiTokenRevokeConfirm': {
    en: 'Revoke this token? Any CLI or CI using it will stop working.',
    zh: '撤销此令牌？使用它的 CLI 或 CI 将无法继续工作。',
    ja: 'このトークンを無効化しますか？使用中のCLI/CIは動作しなくなります。',
    ko: '이 토큰을 취소하시겠어요? 사용 중인 CLI/CI가 작동하지 않게 됩니다.',
  },
  'account.apiTokenNeverUsed': { en: 'never used', zh: '从未使用', ja: '未使用', ko: '사용 안 함' },
  'auth.email': {
    en: 'you@email.com',
    zh: '你的邮箱',
    ja: 'メールアドレス',
    ko: '이메일',
  },
  'auth.sendLink': {
    en: 'Send link',
    zh: '发送链接',
    ja: 'リンク送信',
    ko: '링크 보내기',
  },
  'auth.checkEmail': {
    en: 'Check your email for the sign-in link.',
    zh: '请查收邮件里的登录链接。',
    ja: 'サインインリンクをメールで確認してください。',
    ko: '이메일의 로그인 링크를 확인하세요.',
  },
  'auth.devMode': {
    en: 'Dev mode (no email configured) — sign in directly:',
    zh: 'Dev 模式(未配置邮件)—— 直接登录:',
    ja: 'Devモード(メール未設定)— 直接サインイン:',
    ko: 'Dev 모드(이메일 미설정) — 바로 로그인:',
  },
  'auth.devSignIn': {
    en: 'Dev sign-in',
    zh: 'Dev 登录',
    ja: 'Devサインイン',
    ko: 'Dev 로그인',
  },
  'auth.signedInAs': {
    en: 'signed in as',
    zh: '已登录',
    ja: 'ログイン中',
    ko: '로그인됨',
  },
  'auth.unavailable': {
    en: 'Sign-in unavailable — creation still works, drafts stay local.',
    zh: '登录暂不可用 —— 创作仍可用,草稿留在本地。',
    ja: 'サインイン不可 — 創作は可能、下書きはローカル保存。',
    ko: '로그인 불가 — 창작은 가능, 초안은 로컬 저장.',
  },

  'signup.title': {
    en: 'Sign in to WorldLines',
    zh: '登录 WorldLines',
    ja: 'WorldLines にサインイン',
    ko: 'WorldLines 로그인',
  },
  'signup.subtitle': {
    en: 'One account across the hub, the archive, and the engine. Sign in with your email and password — no password yet, or forgot it? Register with an email link.',
    zh: '一个账号通用于 hub、archive、引擎。用邮箱 + 密码登录;还没有密码或忘记了,就用邮件链接注册。',
    ja: 'hub、archive、エンジンを一つのアカウントで。メールとパスワードでサインイン — パスワードが未設定/お忘れなら、メールリンクで登録。',
    ko: 'hub, archive, 엔진을 하나의 계정으로. 이메일과 비밀번호로 로그인 — 비밀번호가 없거나 잊으셨다면 이메일 링크로 가입하세요.',
  },
  'signup.returnAfter': {
    en: "After signing in we'll send you back to",
    zh: '登录成功后将跳回',
    ja: 'サインイン後、戻る先',
    ko: '로그인 후 돌아갈 곳',
  },
  'signup.bouncing': {
    en: 'Sending you back…',
    zh: '正在跳回……',
    ja: '戻ります…',
    ko: '돌아가는 중…',
  },
  'signup.goExplore': {
    en: 'Explore the worlds and souls catalog.',
    zh: '去看看 worlds / souls 目录。',
    ja: 'worlds と souls のカタログを見に行こう。',
    ko: 'worlds 와 souls 카탈로그를 둘러보세요.',
  },
  'signup.legalNote': {
    en: 'By signing up you agree we may store your email to send the link and remember your handle.',
    zh: '注册即表示同意我们存储邮箱用于发送登录链接,并记住你的 handle。',
    ja: 'サインアップにより、ログインリンクの送信とハンドルの記録のためにメールアドレスを保管することに同意します。',
    ko: '가입은 로그인 링크 전송 및 핸들 저장을 위해 이메일을 보관하는 것에 동의함을 의미합니다.',
  },
  'signup.comingSoonTitle': {
    en: 'Signup opens after launch',
    zh: '注册正式开放前预热中',
    ja: 'サインアップは正式公開時に開放',
    ko: '정식 출시 후 가입 가능',
  },
  'signup.comingSoonBody': {
    en: "We're polishing the experience end-to-end before opening accounts. Join Discord — that's where we'll announce when signup goes live.",
    zh: '正在打磨完整体验,稳定后开放账号注册。先去 Discord —— 那里第一时间通知开放。',
    ja: 'まずは体験を仕上げてからアカウントを開放します。Discord でいち早く開放のお知らせをします。',
    ko: '먼저 경험을 다듬은 뒤 가입을 엽니다. Discord 에서 가장 먼저 알려드립니다.',
  },
  'signup.comingSoonCta': {
    en: 'Join the Discord',
    zh: '加入 Discord',
    ja: 'Discord に参加',
    ko: 'Discord 참여',
  },

  // ── /pricing page ──────────────────────────────────────────
  'pricing.title': {
    en: 'Simple pricing, no surprises',
    zh: '简单定价，无隐藏费用',
    ja: 'シンプルな料金、隠れた費用なし',
    ko: '간단한 요금, 숨은 비용 없음',
  },
  'pricing.subtitle': {
    en: 'Start free. Upgrade when you need more.',
    zh: '免费开始。需要更多时再升级。',
    ja: '無料で始めて、必要なときにアップグレード。',
    ko: '무료로 시작하고 필요할 때 업그레이드.',
  },
  'pricing.freeLabel': {
    en: 'Free',
    zh: '免费',
    ja: '無料',
    ko: '무료',
  },
  'pricing.paidLabel': {
    en: 'Supporter',
    zh: '支持者',
    ja: 'サポーター',
    ko: '서포터',
  },
  'pricing.month': {
    en: 'mo',
    zh: '月',
    ja: '月',
    ko: '월',
  },
  'pricing.freePlays': {
    en: '10 plays/day · relaxed during beta',
    zh: '每天 10 局 · 公测期暂时放开',
    ja: '1日10プレイ・ベータ中は緩和',
    ko: '하루 10회 · 베타 기간 완화',
  },
  'account.betaUnlimited': {
    en: 'Beta — unlimited for now',
    zh: '公测期 · 暂不限次',
    ja: 'ベータ中 · 今は無制限',
    ko: '베타 · 지금은 무제한',
  },
  'account.subEnding': {
    en: 'Canceled — active until {date}',
    zh: '已退订 · 可用至 {date}',
    ja: '解約済み · {date} まで利用可',
    ko: '해지됨 · {date} 까지 이용 가능',
  },
  'pricing.freeCreate': {
    en: 'Create worlds & souls',
    zh: '创建世界与角色',
    ja: '世界とソウルを作成',
    ko: '세계와 소울 제작',
  },
  'pricing.freeCatalog': {
    en: 'Browse public catalog',
    zh: '浏览公开目录',
    ja: '公開カタログを閲覧',
    ko: '공개 카탈로그 탐색',
  },
  'pricing.paidPlays': {
    en: 'Unlimited plays + priority',
    zh: '无限游玩 + 优先',
    ja: 'プレイ無制限＋優先',
    ko: '무제한 플레이 + 우선',
  },
  'pricing.paidCreate': {
    en: 'Priority creation queue',
    zh: '优先创作队列',
    ja: '優先作成キュー',
    ko: '우선 제작 큐',
  },
  'pricing.paidSupport': {
    en: 'Keep the servers running',
    zh: '支持服务器运营',
    ja: 'サーバー運用を支援',
    ko: '서버 운영 지원',
  },
  'pricing.upgrade': {
    en: 'Upgrade',
    zh: '升级',
    ja: 'アップグレード',
    ko: '업그레이드',
  },
  'pricing.currentPlan': {
    en: 'Current plan',
    zh: '当前方案',
    ja: '現在のプラン',
    ko: '현재 플랜',
  },
  'pricing.yourPlan': {
    en: 'YOUR PLAN',
    zh: '你的方案',
    ja: 'あなたのプラン',
    ko: '현재 플랜',
  },
  'pricing.footer': {
    en: 'Cancel anytime. Questions? hop in Discord.',
    zh: '随时可取消。有问题？来 Discord 聊。',
    ja: 'いつでもキャンセル可。質問はDiscordまで。',
    ko: '언제든지 취소 가능. 문의는 Discord에서.',
  },
  'pricing.whyTitle': {
    en: 'Why we charge',
    zh: '为什么收费',
    ja: 'なぜ有料か',
    ko: '왜 유료인가',
  },
  'pricing.whyBody': {
    en: "WorldLines runs AI agents on cloud servers — every play sends tokens to a model on our side. $5/month covers the cloud cost for one player. The free tier is 10 plays a day; during beta we've relaxed it, so play freely. If the servers get overloaded we'll switch the 10/day limit back on — and unlimited (supporter) players always get priority.",
    zh: 'WorldLines 的 AI 代理跑在云端——每局都会把 token 送到我们的模型。每月 5 美元覆盖一个玩家的云端成本。免费版基准是每天 10 局;公测期我们暂时放开,你可以尽情玩。一旦服务器超载,我们会重新启用每天 10 局的限制——而不限次(Supporter)玩家始终优先。',
    ja: 'WorldLines は AI エージェントをクラウドで動かしています——プレイごとにトークンがモデルへ送られます。月5ドルで1プレイヤー分のクラウド代を賄えます。無料枠の基準は1日10プレイ;ベータ中は緩和しているので存分に遊べます。サーバーが過負荷になったら1日10プレイ制限を再び有効にします——無制限(サポーター)プレイヤーは常に優先されます。',
    ko: 'WorldLines는 AI 에이전트를 클라우드에서 실행합니다 — 플레이마다 토큰이 모델로 전송됩니다. 월 $5로 한 명분의 클라우드 비용을 충당합니다. 무료 기준은 하루 10회; 베타 기간에는 완화하여 자유롭게 즐길 수 있습니다. 서버가 과부하되면 하루 10회 제한을 다시 켜며, 무제한(서포터) 플레이어가 항상 우선합니다.',
  },
  'pricing.selfHostTitle': {
    en: 'Prefer to self-host? It is free.',
    zh: '想自己部署？完全免费',
    ja: '自分でホストすることもできる（無料）',
    ko: '직접 호스팅하기 (무료)',
  },
  'pricing.selfHostBody': {
    en: 'If you play on mobile, $5 / month is the easiest path — we run the agents for you. If you have a PC and your own model, clone our open-source TUI (Win / Mac) and run everything locally for free. A self-hostable web edition is coming next. Subscribers will also unlock persistent-world mode when it ships.',
    zh: '手机用户：5 美元/月最方便，云端我们替你跑。PC 用户：可以拉我们开源的 TUI（支持 Win / Mac），用自己的模型在本地跑，完全免费。开源 Web 端也在路上。订阅者将来还会解锁"常驻世界"模式。',
    ja: 'スマホ派なら月 5 ドルが最も手軽です——クラウドはこちらで動かします。PC とご自身のモデルをお持ちの方は、オープンソースの TUI（Win / Mac 対応）をクローンして、すべてローカルで無料実行できます。セルフホスト版の Web も近日公開。サブスクライバーは「常駐ワールド」モード（リリース時）も解放されます。',
    ko: '모바일 사용자: 월 $5가 가장 간편합니다 — 에이전트는 저희가 운영합니다. PC와 자체 모델이 있다면 오픈 소스 TUI(Win / Mac)를 클론해 로컬에서 무료로 실행하세요. 셀프 호스트 가능한 웹 버전도 곧 공개됩니다. 구독자는 출시 시 "상주 월드" 모드도 잠금 해제됩니다.',
  },
  'pricing.selfHostCta': {
    en: 'Open-source TUI on GitHub →',
    zh: '在 GitHub 上看开源 TUI →',
    ja: 'GitHub のオープンソース TUI を見る →',
    ko: 'GitHub에서 오픈 소스 TUI 보기 →',
  },

  'create.title': {
    en: 'Build it by talking.',
    zh: '用对话来创造。',
    ja: '対話でつくる。',
    ko: '대화로 만든다.',
  },
  'create.subtitle': {
    en: 'No forms, no folders. Answer a few questions — the studio assembles a runnable bundle and shows you the architecture as it grows.',
    zh: '没有表单,没有文件夹。回答几个问题 —— 工作室会拼出可运行的包,并实时展示架构。',
    ja: 'フォームもフォルダもなし。いくつかの質問に答えると、実行可能なバンドルが組み上がり、構造がリアルタイムで見えます。',
    ko: '폼도 폴더도 없이. 몇 가지 질문에 답하면 실행 가능한 번들이 조립되고 구조가 실시간으로 보입니다.',
  },
  'create.world': {
    en: 'Create a World',
    zh: '创造世界',
    ja: 'ワールドを創る',
    ko: '월드 만들기',
  },
  'create.soul': {
    en: 'Create a Soul',
    zh: '创造灵魂',
    ja: 'ソウルを創る',
    ko: '소울 만들기',
  },
  'create.worldBlurb': {
    en: 'A place that runs and remembers — premise, a map, the things that live in it. Guided, step by step.',
    zh: '一个会运行、会记住的地方 —— 设定、地图、住在其中的存在。一步步引导。',
    ja: '動いて記憶する場所 — 設定、地図、そこに棲むもの。一歩ずつ導きます。',
    ko: '돌아가고 기억하는 장소 — 설정, 지도, 그 안의 존재들. 단계별로 안내.',
  },
  'create.soulBlurb': {
    en: 'A character with a persona, a voice, and the full six-agent mind. Played by you, or run by a world.',
    zh: '一个有人格、有声音、具备完整六智能体心智的角色。你来扮演,或由世界驱动。',
    ja: '人格と声、完全な6エージェントの心を持つキャラクター。あなたが演じるか、世界が動かす。',
    ko: '인격과 목소리, 완전한 6에이전트 마음을 가진 캐릭터. 당신이 연기하거나 월드가 구동.',
  },
  // ── 5-step studio guidance (worlds + souls) ────────────────
  'create.nameStep': {
    en: 'STEP 1 / 5',
    zh: '第 1 步 / 共 5 步',
    ja: 'ステップ 1 / 5',
    ko: '단계 1 / 5',
  },
  'create.step1World': {
    en: 'Name your world',
    zh: '命名世界',
    ja: 'ワールド名',
    ko: '월드 이름',
  },
  'create.step1Soul': {
    en: 'Name your soul',
    zh: '命名角色',
    ja: 'ソウル名',
    ko: '소울 이름',
  },
  'create.step2': {
    en: 'Answer to build',
    zh: '回答构建',
    ja: '対話で構築',
    ko: '문답으로 구축',
  },
  'create.step3': {
    en: 'Review & edit',
    zh: '查看修改',
    ja: '確認と編集',
    ko: '확인·편집',
  },
  'create.step4': {
    en: 'Refine via agent',
    zh: '智能体精修',
    ja: 'エージェント精修',
    ko: '에이전트 정제',
  },
  'create.step5': {
    en: 'Save / Publish',
    zh: '保存 / 入库',
    ja: '保存 / 公開',
    ko: '저장 / 게시',
  },
  'create.nameWorld': {
    en: 'What is your world called?',
    zh: '你的世界叫什么名字？',
    ja: 'あなたの世界の名前は？',
    ko: '당신의 월드 이름은?',
  },
  'create.nameSoul': {
    en: 'What is your soul called?',
    zh: '你的角色叫什么名字？',
    ja: 'あなたのソウルの名前は？',
    ko: '당신의 소울 이름은?',
  },
  'create.nameHelp': {
    en: 'A working title is fine — you can rename it later. Once you continue, the system will ask interactive questions to build the rest, you can browse and edit what is generated, refine specific pieces by agent, and finally save or publish to WorldHub.',
    zh: '取一个工作标题就好,之后还能改。点击继续后,系统会通过交互问答帮你构建内容,你可以查看生成的素材并修改,选中某项让 agent 进一步精修,最后保存或入库到 WorldHub。',
    ja: '仮タイトルで構いません(あとから変更可)。続けると、対話で内容を作り、生成物を確認・編集し、特定の部分をエージェントに精修させ、最後に保存または WorldHub に公開できます。',
    ko: '임시 제목이어도 됩니다(나중에 바꿀 수 있음). 계속하면 문답으로 콘텐츠를 만들고, 생성된 자료를 확인·편집하며, 일부를 에이전트로 정제한 뒤, 저장하거나 WorldHub 에 게시합니다.',
  },
  'create.namePlaceholder': {
    en: 'e.g. The Dark Train, Ashfall Harbor, ...',
    zh: '比如:暗夜列车 / 灰落港 / ...',
    ja: '例: ダークトレイン、灰落港、…',
    ko: '예: 다크 트레인, 잿빛 항구, …',
  },
  'create.namePlaceholderSoul': {
    en: 'e.g. Elena Voss, Captain Reyes, the Oracle, ...',
    zh: '比如:艾莲娜 / 雷耶斯船长 / 神谕者 / ...',
    ja: '例: エレナ、レイズ船長、神託者、…',
    ko: '예: 엘레나, 레예스 선장, 오라클, …',
  },
  'create.nameContinue': {
    en: 'Continue →',
    zh: '继续 →',
    ja: '続ける →',
    ko: '계속 →',
  },
  'create.nameStudioLoading': {
    en: 'Studio is warming up — you can already name your {kind}.',
    zh: '工作室正在预热 —— 你可以先为{kind}取名。',
    ja: 'スタジオを準備中 —— 先に{kind}の名前をどうぞ。',
    ko: '스튜디오 준비 중 — 먼저 {kind} 이름을 지어주세요.',
  },
  'create.nameQueued': {
    en: 'Starting…',
    zh: '启动中…',
    ja: '起動中…',
    ko: '시작 중…',
  },
  'create.startOver': {
    en: 'start over',
    zh: '重新开始',
    ja: 'やり直す',
    ko: '다시 시작',
  },
  'create.home': {
    en: 'creation home',
    zh: '创作首页',
    ja: '創作ホーム',
    ko: '창작 홈',
  },
  'create.worldStudio': {
    en: 'World studio',
    zh: '世界工作室',
    ja: 'ワールドスタジオ',
    ko: '월드 스튜디오',
  },
  'create.soulStudio': {
    en: 'Soul studio',
    zh: '灵魂工作室',
    ja: 'ソウルスタジオ',
    ko: '소울 스튜디오',
  },
  'create.thinking': {
    en: 'thinking',
    zh: '思考过程',
    ja: '思考',
    ko: '사고 과정',
  },
  'create.typeAnswer': {
    en: 'type your answer…',
    zh: '输入你的回答…',
    ja: '回答を入力…',
    ko: '답을 입력…',
  },
  'create.thinkingBusy': {
    en: 'thinking…',
    zh: '思考中…',
    ja: '考え中…',
    ko: '생각 중…',
  },
  'admin.title': {
    en: 'Hub admin',
    zh: 'Hub 管理',
    ja: 'Hub 管理',
    ko: 'Hub 관리',
  },
  'admin.token': {
    en: 'TOKEN',
    zh: 'TOKEN',
    ja: 'TOKEN',
    ko: 'TOKEN',
  },
  'admin.save': {
    en: 'Save',
    zh: '保存',
    ja: '保存',
    ko: '저장',
  },
  'admin.reset': {
    en: 'Reset to default',
    zh: '恢复默认',
    ja: 'デフォルトに戻す',
    ko: '기본값으로',
  },
  'admin.genreTree': {
    en: 'Genre tree (bubble picker, 3 levels)',
    zh: '类型树(气泡 picker,三级)',
    ja: 'ジャンルツリー(バブル選択, 3階)',
    ko: '장르 트리(버블 선택, 3단계)',
  },
  'admin.genreTreeHint': {
    en: 'JSON array of GenreNode. Saving takes effect on the next /create/world load — no restart.',
    zh: 'GenreNode 数组(JSON)。保存即生效,下一次进入 /create/world 即用新树 —— 不用重启。',
    ja: 'GenreNode の JSON 配列。保存後、次に /create/world を開くと即反映 — 再起動不要。',
    ko: 'GenreNode JSON 배열. 저장하면 다음 /create/world 진입 시 바로 반영 — 재시작 불필요.',
  },
  'admin.next': {
    en: 'Coming: editable interview / author prompts, agent rule systems (CoC / 5e D&D / sandbox / custom), generated bubble icons.',
    zh: '即将上线:可编辑访谈 / 编排 prompt,agents 规则系统(类 CoC / 类 5e D&D / 沙盒 / 自定义),生成的气泡图标。',
    ja: '今後: 取材/オーサのプロンプト編集、エージェントのルール系(CoC風 / 5eD&D風 / サンドボックス / カスタム)、生成バブルアイコン。',
    ko: '예정: 인터뷰/오서 프롬프트 편집, 에이전트 규칙 체계(CoC계 / 5eD&D계 / 샌드박스 / 커스텀), 생성 버블 아이콘.',
  },
  'genre.back': {
    en: 'back',
    zh: '上一层',
    ja: '戻る',
    ko: '뒤로',
  },
  'create.playDraft': {
    en: '试玩 · play locally',
    zh: '试玩这个世界',
    ja: 'このワールドを試遊',
    ko: '이 월드 시연',
  },
  'create.playDraftHint': {
    en: 'Open the bundle in your local Worldlines runtime, or download the .zip and load it yourself.',
    zh: '在本地的 Worldlines 里打开这份世界包,或者下载 .zip 自己加载。',
    ja: 'ローカルの Worldlines で開くか、.zip をダウンロードして自前で読み込み。',
    ko: '로컬 Worldlines 에서 열거나, .zip 을 받아 직접 로드.',
  },
  'create.playDraftSoul': {
    en: '试玩 · talk to this soul',
    zh: '试玩这个灵魂',
    ja: 'このソウルと対話',
    ko: '이 소울과 대화',
  },
  'create.playDraftSoulHint': {
    en: 'Drops this soul into a talk scene and opens a hosted single-agent conversation in your browser — no local install. Download the .zip to run it (with full multi-agent) in your local Worldlines.',
    zh: '把这个灵魂放进一个对话场景(soul-talk),在浏览器里开一段 hosted 单 agent 对话,不用本地装。要完整 multi-agent 就下载 .zip 在本地 Worldlines 里跑。',
    ja: 'このソウルを対話シーン(soul-talk)に配置し、ブラウザでホスト型シングルエージェント会話を開始 — ローカルインストール不要。フルのマルチエージェントは .zip を保存してローカル Worldlines で。',
    ko: '이 소울을 대화 씬(soul-talk)에 배치하고 브라우저에서 호스티드 싱글 에이전트 대화를 엽니다 — 로컬 설치 불필요. 풀 멀티 에이전트는 .zip 을 받아 로컬 Worldlines 에서.',
  },
  'create.playInBrowser': {
    en: '▷ Play in browser',
    zh: '▷ 在浏览器里试玩',
    ja: '▷ ブラウザで試遊',
    ko: '▷ 브라우저에서 시연',
  },
  'create.playInBrowserHint': {
    en: 'Runs the bundle straight from your workdir via the play gateway — no local install needed. Download the .zip to play in any other Worldlines runtime.',
    zh: '直接通过 play 网关从你的 workdir 跑这个世界包,不用本地装客户端。要在别的 Worldlines runtime 玩就下载 .zip。',
    ja: 'play ゲートウェイ経由でワークディレクトリから直接実行 — ローカルインストール不要。他の Worldlines ランタイムで遊ぶなら .zip を保存。',
    ko: 'play 게이트웨이를 통해 workdir 에서 직접 실행 — 로컬 설치 불필요. 다른 Worldlines 런타임에서 놀려면 .zip 다운로드.',
  },
  'create.downloadZip': {
    en: 'Download .zip',
    zh: '下载 .zip',
    ja: '.zip をダウンロード',
    ko: '.zip 다운로드',
  },
  'create.cliFallback': {
    en: 'or run from terminal',
    zh: '或者命令行直跑',
    ja: 'またはターミナルから直接実行',
    ko: '또는 터미널에서 직접 실행',
  },
  'create.copyCmd': {
    en: 'Copy command',
    zh: '复制命令',
    ja: 'コマンドをコピー',
    ko: '명령어 복사',
  },
  'cover.title': {
    en: 'WORLD COVER',
    zh: '世界封面',
    ja: 'ワールドカバー',
    ko: '월드 커버',
  },
  'cover.reroll': {
    en: 'reroll ↻',
    zh: '换一张 ↻',
    ja: '別の絵 ↻',
    ko: '다시 뽑기 ↻',
  },
  'cover.rolling': {
    en: 'rolling…',
    zh: '生成中…',
    ja: '生成中…',
    ko: '생성 중…',
  },
  'cover.generating': {
    en: 'generating cover…',
    zh: '封面生成中…',
    ja: 'カバー生成中…',
    ko: '커버 생성 중…',
  },
  'begin.title': {
    en: 'How would you like to begin?',
    zh: '想怎么开始?',
    ja: 'どこから始めますか？',
    ko: '어디서 시작하시겠어요?',
  },
  'begin.subtitle': {
    en: 'Three doors in — pick the one that fits where you are.',
    zh: '三条路并排,挑一个顺手的。',
    ja: '入口は三つ — 今ある状態に合うものを。',
    ko: '입구는 세 개 — 지금 상황에 맞는 것을 고르세요.',
  },
  'begin.write': {
    en: 'Just write it',
    zh: '直接写',
    ja: 'そのまま書く',
    ko: '바로 쓰기',
  },
  'begin.writeDesc': {
    en: "I already know — skip the gates and let me talk to the studio.",
    zh: '我有想法 —— 跳过引导,直接进 studio 开始对话。',
    ja: 'もう決まってる — 案内をスキップしてスタジオで対話。',
    ko: '이미 정해졌어 — 안내를 건너뛰고 스튜디오에서 바로 대화.',
  },
  'begin.upload': {
    en: 'Drop a doc',
    zh: '导入文档',
    ja: 'ドキュメントを取り込む',
    ko: '문서 가져오기',
  },
  'begin.uploadDesc': {
    en: 'Paste or upload a markdown / pdf / txt; we parse it into a starting concept.',
    zh: '粘贴或上传 md / pdf / txt,我们解析成起点 concept。',
    ja: 'md / pdf / txt を貼るか送る — concept のたたきに変換します。',
    ko: 'md / pdf / txt 붙여넣거나 업로드 — 시작 컨셉으로 변환합니다.',
  },
  'begin.vibe': {
    en: 'Pick a vibe',
    zh: '挑个氛围',
    ja: '雰囲気から選ぶ',
    ko: '분위기로 고르기',
  },
  'begin.vibeDesc': {
    en: 'Eight worlds with cover art — for when you want a tonic, not a brief.',
    zh: '八个世界封面 —— 需要灵感而不是方案时翻一翻。',
    ja: 'カバー画つきの 8 世界 — 案ではなくきっかけが欲しいとき。',
    ko: '커버 8 개 — 안이 아니라 영감이 필요할 때.',
  },
  // ── Soul creation gate (ChoosePath equivalent) ─────────────
  'soulStart.title': {
    en: 'How would you like to create this soul?',
    zh: '想如何创建这个灵魂？',
    ja: 'このソウルをどのように作りますか？',
    ko: '이 소울을 어떻게 만드시겠어요?',
  },
  'soulStart.subtitle': {
    en: 'Three paths — talk to the studio, paste a character card, or upload a file.',
    zh: '三条路 —— 与 studio 对话、粘贴角色卡、或上传文件。',
    ja: '三つの入り口 — スタジオと対話、キャラクターカードを貼り付け、またはファイルをアップロード。',
    ko: '세 가지 길 — 스튜디오와 대화, 캐릭터 카드 붙여넣기, 또는 파일 업로드.',
  },
  'soulStart.interview': {
    en: 'Interview',
    zh: '对话创建',
    ja: '対話作成',
    ko: '대화로 만들기',
  },
  'soulStart.interviewDesc': {
    en: 'Answer a few questions — the studio authors a full six-agent soul from your answers.',
    zh: '回答几个问题 —— studio 会根据你的回答创作完整的六智能体灵魂。',
    ja: 'いくつかの質問に答える — スタジオがあなたの回答から完全な 6 エージェントのソウルを作ります。',
    ko: '몇 가지 질문에 답하면 — 스튜디오가 답변에서 완전한 6에이전트 소울을 만듭니다.',
  },
  'soulStart.pasteCard': {
    en: 'Paste a card',
    zh: '粘贴角色卡',
    ja: 'カードを貼り付け',
    ko: '카드 붙여넣기',
  },
  'soulStart.pasteCardDesc': {
    en: 'Paste a SillyTavern or RisuAI character card (V1/V2 JSON). Your soul is built from it.',
    zh: '粘贴 SillyTavern 或 RisuAI 角色卡(V1/V2 JSON)。从卡片构建灵魂。',
    ja: 'SillyTavern または RisuAI のキャラクターカード (V1/V2 JSON) を貼り付け。それからソウルを作ります。',
    ko: 'SillyTavern 또는 RisuAI 캐릭터 카드(V1/V2 JSON)를 붙여넣기. 거기서 소울을 만듭니다.',
  },
  'soulStart.importFile': {
    en: 'Import a file',
    zh: '导入文件',
    ja: 'ファイルを取り込む',
    ko: '파일 가져오기',
  },
  'soulStart.importFileDesc': {
    en: 'Upload a .png character card or .json card file. Parsed and turned into a soul.',
    zh: '上传 .png 角色卡或 .json 卡片文件。解析并转化为灵魂。',
    ja: '.png キャラクターカードか .json カードファイルをアップロード。解析してソウルに変換。',
    ko: '.png 캐릭터 카드 또는 .json 카드 파일 업로드. 파싱하여 소울로 변환.',
  },
  'soulStart.pasteLabel': {
    en: 'Paste the character card JSON here',
    zh: '在此粘贴角色卡 JSON',
    ja: 'ここにキャラクターカード JSON を貼り付け',
    ko: '여기에 캐릭터 카드 JSON 붙여넣기',
  },
  'soulStart.pasteInvalid': {
    en: 'Not a valid character card — check the JSON and try again.',
    zh: '不是有效的角色卡 —— 请检查 JSON 后重试。',
    ja: '有効なキャラクターカードではありません — JSON を確認して再試行。',
    ko: '유효한 캐릭터 카드가 아닙니다 — JSON 확인 후 다시 시도.',
  },
  'soulStart.pasteGo': {
    en: 'Build from this card →',
    zh: '从卡片构建 →',
    ja: 'このカードから作る →',
    ko: '이 카드로 만들기 →',
  },
  'soulStart.pickFile': {
    en: 'Choose a .png or .json character card…',
    zh: '选择一个 .png 或 .json 角色卡…',
    ja: '.png または .json のキャラクターカードを選択…',
    ko: '.png 또는 .json 캐릭터 카드 선택…',
  },
  'soulStart.importing': {
    en: 'Parsing card…',
    zh: '正在解析卡片…',
    ja: 'カード解析中…',
    ko: '카드 파싱 중…',
  },
  'soulStart.importFailed': {
    en: 'Could not parse this file — check that it is a SillyTavern character card.',
    zh: '无法解析此文件 —— 请检查是否为 SillyTavern 角色卡。',
    ja: 'このファイルを解析できません — SillyTavern キャラクターカードか確認してください。',
    ko: '이 파일을 파싱할 수 없습니다 — SillyTavern 캐릭터 카드인지 확인하세요.',
  },
  'soulStart.back': {
    en: '← back',
    zh: '← 返回',
    ja: '← 戻る',
    ko: '← 뒤로',
  },
  'genre.rootHint': {
    en: 'Pick a sphere',
    zh: '选一个领域',
    ja: '世界圏を選択',
    ko: '영역을 선택',
  },
  'genre.title': {
    en: 'Pick a setting to start from.',
    zh: '挑一个起点设定。',
    ja: 'スタートの世界観を選んでください。',
    ko: '시작할 세계관을 골라주세요.',
  },
  'genre.subtitle': {
    en: 'A genre seeds the director\'s first question and the names the world author bakes in. You can always type your own.',
    zh: '所选类型会作为前置条件,决定第一个问题的方向以及编排时用到的名字风格。也可以自己写。',
    ja: 'ジャンルは最初の問いとオーサが付ける名前の指向に効きます。自由入力も可。',
    ko: '장르는 첫 질문 방향과 작성기가 만드는 이름 스타일에 영향을 줍니다. 직접 입력도 가능.',
  },
  'genre.customLabel': {
    en: 'CUSTOM',
    zh: '自定义',
    ja: 'カスタム',
    ko: '직접 입력',
  },
  'genre.customPlaceholder': {
    en: 'e.g. cosmic horror, kaiju, biopunk…',
    zh: '例如 末日朋克 / 怪兽 / 神话 …',
    ja: '例: コズミックホラー / 怪獣 / 神話 …',
    ko: '예: 코스믹 호러 / 카이주 / 신화 …',
  },
  'genre.go': {
    en: 'Start',
    zh: '开始',
    ja: '開始',
    ko: '시작',
  },
  'genre.skip': {
    en: 'skip — start without a genre',
    zh: '跳过 —— 不指定类型开始',
    ja: 'スキップ — ジャンルなしで開始',
    ko: '건너뛰기 — 장르 없이 시작',
  },
  'file.title': {
    en: 'FILE',
    zh: '文件',
    ja: 'ファイル',
    ko: '파일',
  },
  'file.save': {
    en: 'Save',
    zh: '保存',
    ja: '保存',
    ko: '저장',
  },
  'file.saved': {
    en: 'saved',
    zh: '已保存',
    ja: '保存しました',
    ko: '저장됨',
  },
  'file.close': {
    en: 'Close',
    zh: '关闭',
    ja: '閉じる',
    ko: '닫기',
  },
  'file.loading': {
    en: 'loading…',
    zh: '加载中…',
    ja: '読込中…',
    ko: '불러오는 중…',
  },
  'file.invalidJson': {
    en: 'Invalid JSON — fix before saving.',
    zh: 'JSON 格式错误,保存前请先修复。',
    ja: 'JSON が不正です。保存前に修正してください。',
    ko: 'JSON 형식 오류 — 저장 전에 고쳐주세요.',
  },
  'create.expandHere': {
    en: 'expand here ›',
    zh: '在此拓展 ›',
    ja: 'ここを拡張 ›',
    ko: '여기 확장 ›',
  },
  'create.expandHint': {
    en: 'Prefills the input so your next message targets this folder.',
    zh: '在输入框中预填,下一条消息就会针对这个文件夹拓展。',
    ja: '入力欄に下書きします — 次の発言はこのフォルダ向けになります。',
    ko: '입력란에 미리 채워집니다 — 다음 메시지는 이 폴더를 대상으로 합니다.',
  },
  'create.authoring': {
    en: 'authoring',
    zh: '正在写入',
    ja: '書き込み中',
    ko: '작성 중',
  },
  'create.streamError': {
    en: 'The director hit a snag mid-thought. Your answer is kept — send it again to retry.',
    zh: '导演在思考中断了一下。你的回答还在 —— 再发一次即可重试。',
    ja: 'ディレクターが思考中につまずきました。回答は保持されています — もう一度送信して再試行してください。',
    ko: '디렉터가 생각 도중 문제를 만났습니다. 답변은 유지됩니다 — 다시 보내 재시도하세요.',
  },
  // Assessment groups + fields — backend ships English `label`s; we
  // translate by stable `id`. Missing keys fall back to the backend
  // label (see Visualiser).
  'assess.group.world': { en: 'World', zh: '世界', ja: 'ワールド', ko: '월드' },
  'assess.group.map': { en: 'Map', zh: '地图', ja: 'マップ', ko: '맵' },
  'assess.group.cast': { en: 'Cast & Lore', zh: '角色与传说', ja: 'キャスト & 伝承', ko: '캐스트 & 전승' },
  'assess.group.engine': { en: 'Engine scaffold', zh: '引擎脚手架', ja: 'エンジン基盤', ko: '엔진 골격' },
  'assess.group.identity': { en: 'Identity', zh: '身份', ja: 'アイデンティティ', ko: '정체성' },
  'assess.group.persona': { en: 'Persona', zh: '性格', ja: 'ペルソナ', ko: '페르소나' },
  'assess.group.binding': { en: 'Binding', zh: '绑定', ja: 'バインディング', ko: '바인딩' },
  'assess.group.agents': { en: 'Agent architecture', zh: 'Agent 架构', ja: 'エージェント構成', ko: '에이전트 구성' },
  'assess.field.world_name': { en: 'Name', zh: '名称', ja: '名称', ko: '이름' },
  'assess.field.premise': { en: 'Premise', zh: '前提', ja: '前提', ko: '전제' },
  'assess.field.tone': { en: 'Tone', zh: '基调', ja: 'トーン', ko: '톤' },
  'assess.field.opening_location': { en: 'Opening location', zh: '开场地点', ja: '開幕地', ko: '시작 장소' },
  'assess.field.second_location': { en: 'A place beyond it', zh: '另一处地点', ja: 'もう一つの場所', ko: '또 다른 장소' },
  'assess.field.key_npc': { en: 'A presence', zh: '一位存在', ja: 'ある存在', ko: '존재' },
  'assess.field.conflict': { en: 'The pull', zh: '张力', ja: '緊張', ko: '긴장' },
  'assess.field.soul_name': { en: 'Name', zh: '名字', ja: '名前', ko: '이름' },
  'assess.field.archetype': { en: 'Archetype', zh: '原型', ja: '原型', ko: '원형' },
  'assess.field.core_traits': { en: 'Core traits', zh: '核心特质', ja: 'コア特性', ko: '핵심 특성' },
  'assess.field.motivation': { en: 'Motivation', zh: '动机', ja: '動機', ko: '동기' },
  'assess.field.voice': { en: 'Voice', zh: '声音', ja: '声', ko: '목소리' },
  'assess.field.background': { en: 'Background', zh: '背景', ja: '背景', ko: '배경' },
  'assess.field.binding': { en: 'Bind as', zh: '绑定为', ja: 'バインド先', ko: '바인딩 대상' },
  'assess.field.wid': { en: 'wid', zh: 'wid', ja: 'wid', ko: 'wid' },
  'assess.field.schema_version': { en: 'schema_version', zh: 'schema_version', ja: 'schema_version', ko: 'schema_version' },
  'assess.field.neonrp': { en: 'neonrp runtime', zh: 'neonrp 运行时', ja: 'neonrp ランタイム', ko: 'neonrp 런타임' },
  'assess.field.world_map': { en: 'world-map', zh: '世界地图', ja: 'ワールドマップ', ko: '월드 맵' },
  'assess.field.sid': { en: 'sid', zh: 'sid', ja: 'sid', ko: 'sid' },
  'assess.field.manifest': { en: 'manifest', zh: '清单', ja: 'マニフェスト', ko: '매니페스트' },
  'assess.field.directories': { en: 'directories', zh: '目录', ja: 'ディレクトリ', ko: '디렉터리' },
  'create.stage.opening': {
    en: 'Preparing the first question',
    zh: '正在准备第一个问题',
    ja: '最初の問いを準備中',
    ko: '첫 질문을 준비하는 중',
  },
  'create.stage.read': {
    en: 'Reading your answer',
    zh: '读取你的回答',
    ja: '回答を読み取り中',
    ko: '답변을 읽는 중',
  },
  'create.stage.reason': {
    en: 'Working out the setting',
    zh: '推演设定',
    ja: '設定を推敲中',
    ko: '설정을 다듬는 중',
  },
  'create.stage.compose': {
    en: 'Authoring the bundle',
    zh: '编排作品包',
    ja: 'バンドルを構成中',
    ko: '번들을 구성하는 중',
  },
  'create.stage.write': {
    en: 'Writing files to disk',
    zh: '落盘文件',
    ja: 'ファイルを書き込み中',
    ko: '파일을 기록하는 중',
  },
  'create.stage.deepenRead': {
    en: 'Reading the current world tree',
    zh: '读取当前世界树',
    ja: '現在のワールドツリーを読込中',
    ko: '현재 월드 트리를 읽는 중',
  },
  'create.stage.deepenApply': {
    en: 'Applying your change',
    zh: '应用你的修改',
    ja: '変更を適用中',
    ko: '변경을 적용하는 중',
  },
  'create.stage.deepenRelayout': {
    en: 'Re-laying out the structure',
    zh: '重排结构',
    ja: '構成を再配置中',
    ko: '구조를 재배치하는 중',
  },
  'create.architecture': {
    en: 'ARCHITECTURE',
    zh: '架构',
    ja: '構造',
    ko: '구조',
  },
  'create.required': {
    en: 'required',
    zh: '必备',
    ja: '必須',
    ko: '필수',
  },
  // Per-field status badges (right architecture panel)
  'assess.status.done': {
    en: '已完成',
    zh: '已完成',
    ja: '完了',
    ko: '완료',
  },
  'assess.status.missing': {
    en: '待完成',
    zh: '待完成',
    ja: '未完了',
    ko: '미완료',
  },
  'assess.status.recommended': {
    en: '建议',
    zh: '建议',
    ja: '推奨',
    ko: '권장',
  },
  'assess.status.auto': {
    en: '自动',
    zh: '自动',
    ja: '自動',
    ko: '자동',
  },
  // Left-chat interview-progress chip
  'create.progressLabel': {
    en: 'BUILDING',
    zh: '构建中',
    ja: '構築中',
    ko: '구축 중',
  },
  'create.progressRemaining': {
    en: '~{n} more question{n,plural,=1{}other{s}} until generation',
    zh: '约还有 {n} 题,之后开始生成',
    ja: 'あと約 {n} 問で生成開始',
    ko: '약 {n} 문제 더, 그 후 생성 시작',
  },
  'create.progressGen': {
    en: 'Generating your world…',
    zh: '正在生成你的世界…',
    ja: '世界を生成中…',
    ko: '세계 생성 중…',
  },
  'create.progressGenSoul': {
    en: 'Generating your soul…',
    zh: '正在生成你的灵魂…',
    ja: 'ソウルを生成中…',
    ko: '소울 생성 중…',
  },
  // Right architecture panel — tutorial caption
  'create.archLabel': {
    en: 'ARCH',
    zh: '右栏',
    ja: '右パネル',
    ko: '오른쪽',
  },
  'create.archTutorialEmpty': {
    en: 'Your world\'s anatomy will appear here as you answer — each piece marked 已完成 / 待完成 / 建议, so you can see what\'s done and what\'s left.',
    zh: '你的世界结构会随着回答在这里逐步显现 —— 每一项标注「已完成 / 待完成 / 建议」,一目了然还差什么。',
    ja: '回答するごとに世界の構造がここに現れます — 各項目に「完了 / 未完了 / 推奨」が表示されるので、残りが一目でわかります。',
    ko: '답할 때마다 세계의 구조가 여기에 나타납니다 — 각 항목에 「완료 / 미완료 / 권장」 표시가 있어 남은 작업이 한눈에 보입니다.',
  },
  'create.archTutorialEmptySoul': {
    en: 'Your soul\'s anatomy will appear here as you answer — each piece marked 已完成 / 待完成 / 建议, so you can see what\'s done and what\'s left.',
    zh: '你的灵魂结构会随着回答在这里逐步显现 —— 每一项标注「已完成 / 待完成 / 建议」,一目了然还差什么。',
    ja: '回答するごとにソウルの構造がここに現れます — 各項目に「完了 / 未完了 / 推奨」が表示されるので、残りが一目でわかります。',
    ko: '답할 때마다 소울의 구조가 여기에 나타납니다 — 각 항목에 「완료 / 미완료 / 권장」 표시가 있어 남은 작업이 한눈에 보입니다.',
  },
  'create.archTutorialFilled': {
    en: 'Click any file to edit it. Click a section to ask the agent to refine it. Anything marked 待完成 is what to type next.',
    zh: '点击任何文件即可编辑;点击某项可以让 agent 进一步精修。还标着「待完成」的就是接下来要补的。',
    ja: 'ファイルをクリックすれば編集できます。項目を選べばエージェントに精修依頼。「未完了」のままが次に補う部分です。',
    ko: '파일을 클릭하면 편집할 수 있습니다. 항목을 선택하면 에이전트가 정제합니다. 「미완료」가 다음에 채울 부분입니다.',
  },
  'create.saveDraft': {
    en: 'Save draft (private)',
    zh: '保存草稿(私有)',
    ja: '下書き保存(非公開)',
    ko: '초안 저장(비공개)',
  },
  'create.publishSoon': {
    en: 'Publishing to the public catalog is a separate, guided flow (cover + 立绘 + name + description required) — under construction, stay tuned. For now, save your draft and play it yourself.',
    zh: '公开发布是一个独立的引导流程(需封面 + 立绘 + 名字 + 简介)—— 正在构建中,敬请期待。现在可以先保存草稿、自己试玩。',
    ja: '公開公開は別の案内付きフロー(カバー+立ち絵+名前+説明が必要)—— 構築中です。今は下書きを保存して自分でプレイできます。',
    ko: '공개 게시는 별도의 안내 흐름입니다(커버+일러스트+이름+설명 필요) — 구축 중입니다. 지금은 초안을 저장하고 직접 플레이할 수 있습니다.',
  },
  'create.saving': {
    en: 'Saving…',
    zh: '保存中…',
    ja: '保存中…',
    ko: '저장 중…',
  },
  'create.backToWorld': {
    en: 'Back to the world playtest',
    zh: '返回世界试玩',
    ja: 'ワールド試遊に戻る',
    ko: '월드 시연으로 돌아가기',
  },
  'create.toWorldPlay': {
    en: 'Play the world with this avatar',
    zh: '带这个角色进入世界试玩',
    ja: 'このアバターでワールドを試遊',
    ko: '이 아바타로 월드 플레이',
  },
  'create.savedOk': {
    en: 'Draft saved to your account.',
    zh: '草稿已保存到你的账户。',
    ja: '下書きをアカウントに保存しました。',
    ko: '초안이 계정에 저장되었습니다.',
  },
  'create.publishReady': {
    en: '入库 — mint a',
    zh: '入库 —— 铸造',
    ja: '登録 — 発行',
    ko: '등록 — 발급',
  },
  'create.publishNotReady': {
    en: '入库 (finish required steps)',
    zh: '入库(先完成必备步骤)',
    ja: '登録(必須項目を完了)',
    ko: '등록(필수 단계 완료 필요)',
  },
  'create.signInToSave': {
    en: 'Sign in (top-right) to save or mint an id',
    zh: '右上角登录后可保存或铸造 id',
    ja: '保存・ID発行は右上からサインイン',
    ko: '저장·ID 발급은 우측 상단에서 로그인',
  },
  'create.yourCreations': {
    en: 'Your creations',
    zh: '我的创作',
    ja: 'あなたの作品',
    ko: '내 창작물',
  },
  'create.savedDrafts': {
    en: 'saved drafts',
    zh: '已存草稿',
    ja: '下書き',
    ko: '저장된 초안',
  },
  'create.publishedItems': {
    en: 'published',
    zh: '已入库',
    ja: '登録済み',
    ko: '등록됨',
  },
  'create.nothingYet': {
    en: 'Nothing yet — build a world or soul, then Save or 入库.',
    zh: '还没有 —— 造一个世界或灵魂,然后保存或入库。',
    ja: 'まだありません — ワールドかソウルを作り、保存か登録を。',
    ko: '아직 없음 — 월드나 소울을 만들고 저장 또는 등록하세요.',
  },
  'create.worldTree': {
    en: 'WORLD CONTENT',
    zh: '世界内容',
    ja: 'ワールド内容',
    ko: '월드 콘텐츠',
  },
  'create.soulTree': {
    en: 'SOUL CONTENT',
    zh: '灵魂内容',
    ja: 'ソウル内容',
    ko: '소울 콘텐츠',
  },
  'create.continueEdit': {
    en: 'continue editing',
    zh: '继续编辑',
    ja: '編集を続ける',
    ko: '계속 편집',
  },
  'create.savedSeeHere': {
    en: 'Saved — see it under “Your creations” on the create home.',
    zh: '已保存 —— 在创作首页「我的创作」里可见。',
    ja: '保存しました —「あなたの作品」(創作ホーム)で確認できます。',
    ko: '저장됨 — 창작 홈의 "내 창작물"에서 확인하세요.',
  },
  'create.signInToCreate': {
    en: 'Sign in (top-right) to create. The studio runs on our model — building a world/soul is model-driven, for registered users.',
    zh: '右上角登录后开始创作。工作室跑在我们的模型上 —— 造世界/灵魂是模型驱动的,仅限注册用户。',
    ja: '右上からサインインで創作開始。スタジオは当方のモデルで動きます — ワールド/ソウル制作はモデル駆動、登録ユーザー限定です。',
    ko: '우측 상단에서 로그인 후 창작. 스튜디오는 our 모델로 구동 — 월드/소울 제작은 모델 기반, 등록 사용자 전용입니다.',
  },
  'create.drafting': {
    en: 'Authoring the bundle from your answers…',
    zh: '正在按你的回答编排作品包…',
    ja: '回答に基づきバンドルを構成中…',
    ko: '답변을 바탕으로 번들을 구성하는 중…',
  },
  'create.refineHint': {
    en: 'Bundle authored — the folder on the right is the real thing. Say what to change and it gets reworked: a place, a tone, a name. Keep expanding it.',
    zh: '已编排成包 —— 右侧文件夹就是真实内容。说要改什么就改什么:某个地点、基调、名字。可以继续拓展。',
    ja: 'バンドルを構成しました。右のフォルダが実体です。変えたい点を言えば反映します — 場所、トーン、名前。そのまま拡張できます。',
    ko: '번들을 구성했습니다. 오른쪽 폴더가 실체입니다. 바꿀 점을 말하면 반영됩니다 — 장소, 톤, 이름. 계속 확장하세요.',
  },
  'create.refinePlaceholder': {
    en: 'describe a change…',
    zh: '描述一处修改…',
    ja: '変更したい点を…',
    ko: '바꿀 점을 설명…',
  },
  'create.published': {
    en: 'Published — id minted',
    zh: '已入库 —— id 已铸造',
    ja: '登録完了 — ID発行済み',
    ko: '등록 완료 — ID 발급됨',
  },

  // Landing
  'land.tag': { en: 'WORLDLINES · HUB', zh: 'WORLDLINES · HUB', ja: 'WORLDLINES · HUB', ko: 'WORLDLINES · HUB' },
  'land.h1a': {
    en: 'Living worlds.',
    zh: '活着的世界。',
    ja: '生きた世界。',
    ko: '살아있는 세계.',
  },
  'land.h1b': {
    en: 'Souls that remember.',
    zh: '会记得的灵魂。',
    ja: '記憶するソウル。',
    ko: '기억하는 소울.',
  },
  'land.lede': {
    en: 'The catalog for WorldLines. Pick a world, bind a soul, and play — every action has consequence, every character has memory. Share a slug; anyone with WorldLines can run it.',
    zh: 'WorldLines 的目录。挑一个世界,绑一个灵魂,开始游玩 —— 每个行动都有后果,每个角色都有记忆。分享一个 slug,任何装了 WorldLines 的人都能运行。',
    ja: 'WorldLines のカタログ。ワールドを選び、ソウルを結びつけ、遊ぶ — すべての行動に結果が、すべてのキャラに記憶がある。slug を共有すれば、WorldLines があれば誰でも動かせる。',
    ko: 'WorldLines 카탈로그. 월드를 고르고 소울을 묶어 플레이 — 모든 행동에 결과가, 모든 캐릭터에 기억이. slug 를 공유하면 WorldLines 가 있는 누구나 실행.',
  },
  'land.browseWorlds': {
    en: 'Browse worlds',
    zh: '浏览世界',
    ja: 'ワールドを見る',
    ko: '월드 둘러보기',
  },
  'land.browseSouls': {
    en: 'Browse souls',
    zh: '浏览灵魂',
    ja: 'ソウルを見る',
    ko: '소울 둘러보기',
  },
  'land.doorWorlds': { en: 'WorldHub', zh: 'WorldHub', ja: 'WorldHub', ko: 'WorldHub' },
  'land.doorSouls': { en: 'SoulHub', zh: 'SoulHub', ja: 'SoulHub', ko: 'SoulHub' },
  'land.doorCreateWorld': {
    en: 'Create a World',
    zh: '创建世界',
    ja: 'ワールドを作る',
    ko: '월드 만들기',
  },
  'land.doorCreateWorldBlurb': {
    en: 'Author a region, a cast, the rules — a place that will remember what you did.',
    zh: '撰写地域、人物、规则 —— 一个会记住你所作所为的地方。',
    ja: '地域、登場人物、ルールを書く — あなたの行いを覚える場所を。',
    ko: '지역, 등장인물, 규칙을 쓴다 — 당신의 행적을 기억할 장소를.',
  },
  'land.doorCreateSoul': {
    en: 'Create a Soul',
    zh: '创建角色',
    ja: 'ソウルを作る',
    ko: '소울 만들기',
  },
  'land.doorCreateSoulBlurb': {
    en: 'Author a persona, voice, memory — a character anyone can talk to and take into any world.',
    zh: '撰写人格、声音、记忆 —— 一个可以被对话、可以被带入任何世界的角色。',
    ja: 'ペルソナ・声・記憶を書く — 誰でも話しかけられ、どの世界にも連れて行けるキャラクターを。',
    ko: '페르소나·목소리·기억을 쓴다 — 누구든 대화할 수 있고, 어느 월드든 데려갈 수 있는 캐릭터를.',
  },
  'land.create': { en: 'Create', zh: '创建', ja: '作る', ko: '만들기' },
  'land.doorWorldsBlurb': {
    en: 'Regions, NPCs, factions, lore, rules. A place to drop into. Pick one, run it, it remembers.',
    zh: '地域、NPC、势力、传说、规则。一个可以踏入的地方。挑一个、运行它,它会记得。',
    ja: '地域・NPC・勢力・伝承・ルール。踏み込める場所。選んで動かせば、記憶する。',
    ko: '지역·NPC·세력·전승·규칙. 들어갈 수 있는 장소. 골라 실행하면 기억한다.',
  },
  'land.doorSoulsBlurb': {
    en: 'Self-contained agent bundles — persona, memory, goals. Bind one to a world as a player or NPC.',
    zh: '自包含的智能体包 —— 人格、记忆、目标。把它作为玩家或 NPC 绑定到世界。',
    ja: '自己完結のエージェント束 — ペルソナ・記憶・目標。プレイヤーかNPCとして世界に結ぶ。',
    ko: '자기완결 에이전트 번들 — 페르소나·기억·목표. 플레이어나 NPC로 월드에 묶기.',
  },
  'land.enter': { en: 'Enter', zh: '进入', ja: '入る', ko: '들어가기' },
  'land.featured': { en: 'FEATURED', zh: '精选', ja: '注目', ko: '추천' },
  'land.all': { en: 'all', zh: '全部', ja: 'すべて', ko: '전체' },
  'land.playNow': {
    en: '▶ PLAY NOW — IN YOUR BROWSER',
    zh: '▶ 立即游玩 —— 就在浏览器里',
    ja: '▶ 今すぐプレイ — ブラウザで',
    ko: '▶ 지금 플레이 — 브라우저에서',
  },
  'land.playNote': {
    en: 'server-side · cost-capped',
    zh: '服务端运行 · 成本封顶',
    ja: 'サーバー実行 · コスト上限',
    ko: '서버 실행 · 비용 상한',
  },
  'land.playCta': { en: 'Play now', zh: '立即游玩', ja: '今すぐプレイ', ko: '지금 플레이' },
  'land.how': { en: 'HOW IT WORKS', zh: '运作方式', ja: '仕組み', ko: '작동 방식' },
  'land.step1h': { en: '1 · Pick', zh: '1 · 挑选', ja: '1 · 選ぶ', ko: '1 · 고르기' },
  'land.step1b': {
    en: 'A world and a soul from the catalog.',
    zh: '从目录里选一个世界和一个灵魂。',
    ja: 'カタログからワールドとソウルを。',
    ko: '카탈로그에서 월드와 소울을.',
  },
  'land.step2h': { en: '2 · Get', zh: '2 · 获取', ja: '2 · 入手', ko: '2 · 받기' },
  'land.step2b': {
    en: 'worldlines world download <slug> — or play online.',
    zh: 'worldlines world download <slug> —— 或直接在线玩。',
    ja: 'worldlines world download <slug> — またはオンラインで。',
    ko: 'worldlines world download <slug> — 또는 온라인으로.',
  },
  'land.step3h': { en: '3 · Live', zh: '3 · 活', ja: '3 · 生きる', ko: '3 · 살기' },
  'land.step3b': {
    en: 'The world runs, remembers, and evolves with you.',
    zh: '世界运行、记忆,并与你一同演变。',
    ja: '世界は動き、記憶し、あなたと共に変わる。',
    ko: '세계는 돌아가고 기억하며 당신과 함께 변한다.',
  },

  // Catalog
  'cat.worldsLabel': {
    en: 'WORLDHUB · DISTRIBUTION',
    zh: 'WORLDHUB · 分发',
    ja: 'WORLDHUB · 配信',
    ko: 'WORLDHUB · 배포',
  },
  'cat.soulsLabel': {
    en: 'SOULHUB · DISTRIBUTION',
    zh: 'SOULHUB · 分发',
    ja: 'SOULHUB · 配信',
    ko: 'SOULHUB · 배포',
  },
  'cat.worldsTitle': {
    en: 'Worlds you can drop into.',
    zh: '可以踏入的世界。',
    ja: '踏み込めるワールド。',
    ko: '들어갈 수 있는 월드.',
  },
  'cat.soulsTitle': {
    en: 'Souls who can play with you.',
    zh: '能陪你玩的灵魂。',
    ja: '一緒に遊べるソウル。',
    ko: '함께 노는 소울.',
  },
  'cat.worldsSub': {
    en: 'Hash-addressable bundles of regions, NPCs, factions, and rules. Pick a slug, run worldlines world download, and the launcher picks it up next time.',
    zh: '按哈希寻址的包:地域、NPC、势力与规则。挑一个 slug,运行 worldlines world download,启动器下次就会识别。',
    ja: 'ハッシュ参照の束:地域・NPC・勢力・ルール。slug を選び worldlines world download を実行すれば次回ランチャーが認識。',
    ko: '해시 주소 번들: 지역·NPC·세력·규칙. slug 를 골라 worldlines world download 실행하면 다음에 런처가 인식.',
  },
  'cat.soulsSub': {
    en: 'Self-contained agent bundles — persona, memory, goals. Download one and the launcher lets you bind it to a world as a player or NPC.',
    zh: '自包含的智能体包 —— 人格、记忆、目标。下载后启动器可把它作为玩家或 NPC 绑定到世界。',
    ja: '自己完結のエージェント束 — ペルソナ・記憶・目標。DLすればランチャーでプレイヤーかNPCとして世界に結べる。',
    ko: '자기완결 에이전트 번들 — 페르소나·기억·목표. 받으면 런처에서 플레이어나 NPC로 월드에 묶을 수 있다.',
  },
  'cat.worldsEmpty': {
    en: 'No worlds published yet.',
    zh: '还没有发布的世界。',
    ja: 'まだ公開ワールドはありません。',
    ko: '아직 공개된 월드가 없습니다.',
  },
  'cat.soulsEmpty': {
    en: 'No souls published yet.',
    zh: '还没有发布的灵魂。',
    ja: 'まだ公開ソウルはありません。',
    ko: '아직 공개된 소울이 없습니다.',
  },
  'cat.oneliner': { en: 'ONE-LINER', zh: '一行命令', ja: 'ワンライナー', ko: '한 줄 명령' },
  'cat.loading': {
    en: 'loading registry…',
    zh: '正在加载注册表…',
    ja: 'レジストリ読み込み中…',
    ko: '레지스트리 로딩 중…',
  },

  // EntryCard
  'card.playable': {
    en: 'PLAYABLE',
    zh: '可游玩',
    ja: 'プレイ可',
    ko: '플레이 가능',
  },

  // Footer
  'foot.tagline': {
    en: 'Browse and download worlds and souls for WorldLines. Share a slug — anyone can play.',
    zh: '浏览并下载 WorldLines 的世界与灵魂。分享一个 slug —— 任何人都能玩。',
    ja: 'WorldLines のワールドとソウルを閲覧・DL。slug を共有すれば誰でも遊べる。',
    ko: 'WorldLines 의 월드·소울 둘러보기·다운로드. slug 를 공유하면 누구나 플레이.',
  },
  'foot.product': { en: 'Product', zh: '产品', ja: 'プロダクト', ko: '제품' },
  'foot.community': { en: 'Community', zh: '社区', ja: 'コミュニティ', ko: '커뮤니티' },
  'foot.hub': { en: 'Hub', zh: 'Hub', ja: 'Hub', ko: 'Hub' },
  'foot.company': { en: 'Company', zh: '公司', ja: '会社', ko: '회사' },
  'foot.documentation': {
    en: 'Documentation',
    zh: '文档',
    ja: 'ドキュメント',
    ko: '문서',
  },
  'foot.starter': {
    en: 'Starter template',
    zh: '起步模板',
    ja: 'スターターテンプレート',
    ko: '스타터 템플릿',
  },
  'foot.archive': {
    en: 'World archive',
    zh: '世界档案',
    ja: 'ワールドアーカイブ',
    ko: '월드 아카이브',
  },
  'foot.worldhubSpec': {
    en: 'WorldHub spec',
    zh: 'WorldHub 规范',
    ja: 'WorldHub 仕様',
    ko: 'WorldHub 명세',
  },
  'foot.soulhubSpec': {
    en: 'SoulHub spec',
    zh: 'SoulHub 规范',
    ja: 'SoulHub 仕様',
    ko: 'SoulHub 명세',
  },
  'foot.about': { en: 'About', zh: '关于', ja: '会社概要', ko: '소개' },
  'foot.blog': { en: 'Blog', zh: '博客', ja: 'ブログ', ko: '블로그' },
  'foot.rights': {
    en: 'Hash-addressable hub for WorldLines content',
    zh: 'WorldLines 内容的哈希寻址 Hub',
    ja: 'WorldLines コンテンツのハッシュ参照 Hub',
    ko: 'WorldLines 콘텐츠의 해시 주소 Hub',
  },

  // Detail page
  'detail.loading': { en: 'loading…', zh: '加载中…', ja: '読み込み中…', ko: '로딩 중…' },
  'detail.notFound': {
    en: 'slug not found in the {kind} registry',
    zh: '{kind} 注册表中未找到该 slug',
    ja: '{kind} レジストリに該当 slug がありません',
    ko: '{kind} 레지스트리에 해당 slug 없음',
  },
  'detail.notHostedYet': {
    en: 'not published to the registry yet — but you can still play it hosted',
    zh: '尚未发布到注册表 —— 但你仍可在线游玩',
    ja: 'まだレジストリ未公開 — でもホスト版で遊べます',
    ko: '아직 레지스트리 미공개 — 하지만 호스팅 플레이 가능',
  },
  'detail.playInBrowser': {
    en: 'Play in browser',
    zh: '在浏览器中游玩',
    ja: 'ブラウザでプレイ',
    ko: '브라우저에서 플레이',
  },
  'detail.back': { en: 'back to {kind}', zh: '返回{kind}', ja: '{kind}へ戻る', ko: '{kind}로 돌아가기' },
  'detail.playSoul': {
    en: 'Play with this soul in browser',
    zh: '用这个灵魂在浏览器中游玩',
    ja: 'このソウルでブラウザプレイ',
    ko: '이 소울로 브라우저 플레이',
  },
  'detail.playWorld': {
    en: 'Play this world in browser',
    zh: '在浏览器中游玩这个世界',
    ja: 'このワールドをブラウザプレイ',
    ko: '이 월드를 브라우저 플레이',
  },
  'detail.hostedNote': {
    en: 'hosted · no install · cost-capped',
    zh: '在线托管 · 免安装 · 成本封顶',
    ja: 'ホスト · インストール不要 · コスト上限',
    ko: '호스팅 · 설치 불필요 · 비용 상한',
  },
  'detail.downloadLocal': {
    en: 'Download to play locally',
    zh: '下载以本地游玩',
    ja: 'DLしてローカルで遊ぶ',
    ko: '다운로드해 로컬 플레이',
  },
  'detail.notHostedParen': {
    en: '(browser play not hosted yet)',
    zh: '(尚未提供浏览器游玩)',
    ja: '(ブラウザプレイ未提供)',
    ko: '(브라우저 플레이 미제공)',
  },
  'detail.whatsInside': {
    en: "WHAT'S INSIDE",
    zh: '包含什么',
    ja: '中身',
    ko: '구성',
  },
  'detail.download': { en: 'DOWNLOAD', zh: '下载', ja: 'ダウンロード', ko: '다운로드' },
  'detail.dlLatest': { en: 'latest', zh: '最新', ja: '最新', ko: '최신' },
  'detail.dlVersion': { en: 'this version', zh: '此版本', ja: 'このバージョン', ko: '이 버전' },
  'detail.byHash': { en: 'by hash', zh: '按哈希', ja: 'ハッシュ指定', ko: '해시로' },
  'detail.directZip': { en: 'direct zip', zh: '直接 zip', ja: '直接 zip', ko: '직접 zip' },
  'detail.versions': { en: 'VERSIONS', zh: '版本', ja: 'バージョン', ko: '버전' },
  'detail.latestBadge': { en: 'LATEST', zh: '最新', ja: '最新', ko: '최신' },
  'detail.noChangelog': {
    en: '(no changelog)',
    zh: '(无更新日志)',
    ja: '(変更履歴なし)',
    ko: '(변경 내역 없음)',
  },
  'detail.latestLine': { en: 'latest', zh: '最新', ja: '最新', ko: '최신' },

  'agent.orchestrator': {
    en: 'Sequences the soul’s reaction each player turn.',
    zh: '在每个玩家回合编排灵魂的反应。',
    ja: '各プレイヤーターンでソウルの反応を順序付け。',
    ko: '플레이어 턴마다 소울 반응을 배열.',
  },
  'agent.mind': {
    en: 'Persona-aligned situational analysis + decision.',
    zh: '贴合人格的情境分析与决策。',
    ja: 'ペルソナに沿った状況分析と意思決定。',
    ko: '페르소나 정렬 상황 분석·결정.',
  },
  'agent.action': {
    en: 'Executes movement, items, NPC interaction, rest.',
    zh: '执行移动、物品、NPC 互动、休息。',
    ja: '移動・アイテム・NPC対話・休息を実行。',
    ko: '이동·아이템·NPC 상호작용·휴식 실행.',
  },
  'agent.memory': {
    en: 'Stores perceptions; consolidates short→long term.',
    zh: '存储感知;将短期记忆固化为长期。',
    ja: '知覚を保存;短期→長期へ統合。',
    ko: '지각 저장; 단기→장기 통합.',
  },
  'agent.dialogue': {
    en: 'Generates speech; voice / mood / trust filter.',
    zh: '生成话语;语气 / 情绪 / 信任过滤。',
    ja: '発話を生成;声・気分・信頼でフィルタ。',
    ko: '발화 생성; 목소리·기분·신뢰 필터.',
  },
  'agent.narrative': {
    en: 'Liaises with the world’s narrative agent.',
    zh: '与世界的叙事智能体对接。',
    ja: '世界の物語エージェントと連携。',
    ko: '월드의 서사 에이전트와 연계.',
  },
  'sdir.persona': {
    en: 'core_traits · values · motivations · relationships',
    zh: '核心特质 · 价值观 · 动机 · 关系',
    ja: 'core_traits · 価値観 · 動機 · 関係',
    ko: 'core_traits · 가치관 · 동기 · 관계',
  },
  'sdir.character': {
    en: 'profile · stats · status · equipment · inventory · wallet',
    zh: '档案 · 属性 · 状态 · 装备 · 物品 · 钱包',
    ja: 'プロフィール · ステータス · 状態 · 装備 · 所持品 · 財布',
    ko: '프로필 · 능력치 · 상태 · 장비 · 인벤토리 · 지갑',
  },
  'sdir.background': {
    en: 'origin · history · secrets (prose)',
    zh: '出身 · 历史 · 秘密(散文)',
    ja: '出自 · 来歴 · 秘密(散文)',
    ko: '기원 · 내력 · 비밀(산문)',
  },
  'sdir.memo': {
    en: 'long-term + short-term memory, trajectory log',
    zh: '长期 + 短期记忆,轨迹日志',
    ja: '長期+短期記憶、軌跡ログ',
    ko: '장기+단기 기억, 궤적 로그',
  },
  'sdir.agents': {
    en: 'the 6-agent set + manifest',
    zh: '六智能体组 + 清单',
    ja: '6エージェント群 + マニフェスト',
    ko: '6에이전트 세트 + 매니페스트',
  },
  'wdir.map': {
    en: 'top-level navigation graph',
    zh: '顶层导航图',
    ja: '最上位ナビゲーショングラフ',
    ko: '최상위 내비게이션 그래프',
  },
  'wdir.entities': {
    en: 'towns · dungeons · npcs · factions · quests · lore',
    zh: '城镇 · 地牢 · NPC · 势力 · 任务 · 传说',
    ja: '町 · ダンジョン · NPC · 勢力 · クエスト · 伝承',
    ko: '마을 · 던전 · NPC · 세력 · 퀘스트 · 전승',
  },
  'wdir.agents': {
    en: 'optional custom agent set + routing',
    zh: '可选自定义智能体组 + 路由',
    ja: '任意のカスタムエージェント群 + ルーティング',
    ko: '선택적 커스텀 에이전트 + 라우팅',
  },
  'wdir.rules': {
    en: 'optional rule-agent (mechanics, time, combat)',
    zh: '可选规则智能体(机制、时间、战斗)',
    ja: '任意のルールエージェント(機構・時間・戦闘)',
    ko: '선택적 룰 에이전트(메커닉·시간·전투)',
  },
  'wdir.neonrp': {
    en: 'engine manifest + event log (saved runs)',
    zh: '引擎清单 + 事件日志(存档运行)',
    ja: 'エンジンマニフェスト + イベントログ(保存実行)',
    ko: '엔진 매니페스트 + 이벤트 로그(저장된 실행)',
  },

  // Play page chrome
  'play.back': { en: 'back to', zh: '返回', ja: '戻る', ko: '돌아가기' },
  'play.hostedPlay': {
    en: 'HOSTED PLAY',
    zh: '在线游玩',
    ja: 'ホストプレイ',
    ko: '호스팅 플레이',
  },
  'play.blurbFallback': {
    en: 'Runs server-side — nothing to install. Cost-capped, idle-evicted.',
    zh: '服务端运行 —— 无需安装。成本封顶,空闲自动回收。',
    ja: 'サーバー実行 — インストール不要。コスト上限、アイドルで回収。',
    ko: '서버 실행 — 설치 불필요. 비용 상한, 유휴 시 회수.',
  },
  'play.entering': { en: 'entering…', zh: '进入中…', ja: '入場中…', ko: '입장 중…' },
  // Auto-kickoff: silently sent as the first turn so the world's
  // opening scene plays without the user having to type. The text
  // EXPLICITLY names the language so the LLM doesn't fall back to
  // English (its system-prompt default) and instead opens the scene
  // in the player's locale.
  'play.kickoff': {
    en: 'Start the game in English.',
    zh: '用中文开始游戏。',
    ja: '日本語でゲームを始めて。',
    ko: '한국어로 게임을 시작해.',
  },
  // Souls are conversational: you're meeting a character, not starting
  // a game. Same purpose as play.kickoff (force the LLM to open in the
  // player's locale) but phrased as "say hello / introduce yourself".
  'play.kickoffSoul': {
    en: 'Greet me in English and introduce yourself.',
    zh: '用中文跟我打招呼，介绍一下你自己。',
    ja: '日本語で話しかけて、自己紹介してください。',
    ko: '한국어로 인사하고 자기소개를 해줘.',
  },
  'play.enterScene': {
    en: 'Enter the scene',
    zh: '进入场景',
    ja: 'シーンに入る',
    ko: '장면 진입',
  },
  'play.continueTitle': {
    en: 'CONTINUE',
    zh: '继续游戏',
    ja: '続きから',
    ko: '이어하기',
  },
  'play.continueSave': {
    en: 'Continue',
    zh: '继续',
    ja: '続ける',
    ko: '계속',
  },
  'play.deleteSave': {
    en: 'Delete save',
    zh: '删除存档',
    ja: 'セーブを削除',
    ko: '세이브 삭제',
  },
  'play.newGame': {
    en: 'New game',
    zh: '新建游戏',
    ja: '新しいゲーム',
    ko: '새 게임',
  },
  'play.resumed': {
    en: 'You return to where you left off. Say something to {name} to continue.',
    zh: '你回到了离开时的地方。对 {name} 说点什么继续。',
    ja: '中断したところに戻った。{name} に話しかけて続けよう。',
    ko: '중단했던 곳으로 돌아왔다. {name} 에게 말을 걸어 이어가세요.',
  },
  'play.mode': { en: 'PLAY MODE', zh: '游玩模式', ja: 'プレイモード', ko: '플레이 모드' },
  'play.modeAdvanced': { en: 'ADVANCED · ENGINE MODE', zh: '高级 · 引擎模式', ja: '詳細 · エンジンモード', ko: '고급 · 엔진 모드' },
  'play.modeFast': {
    en: 'World only · no characters',
    zh: '只有世界 · 无角色',
    ja: '世界のみ · キャラなし',
    ko: '월드만 · 캐릭터 없음',
  },
  'play.modeOrch': {
    en: 'One director voices all NPCs',
    zh: '单导演 · voice 全部 NPC',
    ja: '一人の進行役が全NPCを演じる',
    ko: '한 진행자가 모든 NPC 연기',
  },
  'play.modeMulti': {
    en: 'Each character its own agent · local',
    zh: '每角色独立 agent · 本地',
    ja: '各キャラが独立エージェント · ローカル',
    ko: '각 캐릭터 독립 에이전트 · 로컬',
  },
  'play.modeMultiLocked': {
    en: 'multi-agent runs locally via the NeonRP TUI/CLI',
    zh: 'multi-agent 仅在本地 NeonRP（TUI/CLI）可用',
    ja: 'multi-agent はローカルの NeonRP（TUI/CLI）のみ',
    ko: 'multi-agent 는 로컬 NeonRP(TUI/CLI)에서만',
  },
  'play.avatar': {
    en: 'YOUR AVATAR (分身)',
    zh: '你的分身',
    ja: 'あなたの分身',
    ko: '당신의 분신',
  },
  // ── Password auth + one-time registration ──
  'auth.password': {
    en: 'Password',
    zh: '密码',
    ja: 'パスワード',
    ko: '비밀번호',
  },
  'auth.loginBtn': {
    en: 'Sign in',
    zh: '登录',
    ja: 'ログイン',
    ko: '로그인',
  },
  'auth.continue': {
    en: 'Continue',
    zh: '继续',
    ja: '続ける',
    ko: '계속',
  },
  'auth.forgotPw': {
    en: 'Forgot password? Email me a sign-in link',
    zh: '忘记密码?发送邮件登录链接',
    ja: 'パスワードを忘れた? メールでログインリンク',
    ko: '비밀번호를 잊으셨나요? 이메일로 로그인 링크',
  },
  'auth.linkNew': {
    en: "Welcome! Check your email for a sign-in link — click it and we'll set up your account.",
    zh: '欢迎!查收邮件里的登录链接,点击后即可完善账号。',
    ja: 'ようこそ!メールのログインリンクを確認 — クリックでアカウントを設定します。',
    ko: '환영합니다! 이메일의 로그인 링크를 확인하세요 — 클릭하면 계정을 설정합니다.',
  },
  'auth.linkSetup': {
    en: "Check your email for a sign-in link. After you click it, you can set a password and finish your profile.",
    zh: '查收邮件里的登录链接。点击后即可设置密码、完善资料。',
    ja: 'メールのログインリンクを確認。クリック後にパスワード設定とプロフィール完成ができます。',
    ko: '이메일의 로그인 링크를 확인하세요. 클릭 후 비밀번호 설정과 프로필 완성이 가능합니다.',
  },
  'auth.orLink': {
    en: 'New here / forgot password? Email me a sign-in link',
    zh: '新用户 / 忘记密码?发送邮件登录链接',
    ja: '新規 / パスワードを忘れた? メールリンクでログイン',
    ko: '신규 / 비밀번호를 잊으셨나요? 이메일 링크로 로그인',
  },
  // Login screen → the secondary path: no password yet, or forgot it →
  // go register / recover via an email link.
  'auth.noPwRegister': {
    en: 'No password / forgot it? Register with an email link',
    zh: '没有密码 / 忘记密码?用邮件链接注册',
    ja: 'パスワードがない / 忘れた? メールリンクで登録',
    ko: '비밀번호가 없거나 잊으셨나요? 이메일 링크로 가입',
  },
  // Email-only screen: request the link.
  'auth.registerViaLink': {
    en: 'Register with an email link',
    zh: '用邮件链接注册',
    ja: 'メールリンクで登録',
    ko: '이메일 링크로 가입',
  },
  'auth.registerHint': {
    en: 'Enter your email — we’ll send a link to register or reset your password.',
    zh: '输入邮箱 —— 我们会发一封链接,用来注册或重设密码。',
    ja: 'メールを入力 —— 登録またはパスワード再設定用のリンクを送ります。',
    ko: '이메일을 입력하세요 —— 가입 또는 비밀번호 재설정 링크를 보내드립니다.',
  },
  'setup.title': {
    en: 'Finish setting up your account',
    zh: '完成账号注册',
    ja: 'アカウント登録を完了',
    ko: '계정 등록 완료',
  },
  'setup.sub': {
    en: 'Your email is verified. Pick your name and set a password for everyday sign-in — the email link keeps working as a backup.',
    zh: '邮箱已验证。选择你的名字,并设置日常登录密码——邮件链接仍可随时使用。',
    ja: 'メール認証は完了。名前を選び、日常ログイン用のパスワードを設定してください — メールリンクも引き続き使えます。',
    ko: '이메일 인증 완료. 이름을 정하고 일상 로그인용 비밀번호를 설정하세요 — 이메일 링크도 계속 사용할 수 있습니다.',
  },
  'setup.handle': {
    en: 'Handle (unique ID, optional)',
    zh: '用户名(唯一ID,可留空)',
    ja: 'ハンドル(一意のID・任意)',
    ko: '핸들 (고유 ID, 선택)',
  },
  'setup.displayName': {
    en: 'Display name (optional)',
    zh: '昵称(可留空)',
    ja: '表示名(任意)',
    ko: '표시 이름 (선택)',
  },
  'setup.password': {
    en: 'Password (min 8 characters)',
    zh: '密码(至少 8 位)',
    ja: 'パスワード(8文字以上)',
    ko: '비밀번호 (8자 이상)',
  },
  'setup.submit': {
    en: 'Complete registration',
    zh: '完成注册',
    ja: '登録を完了',
    ko: '등록 완료',
  },
  'setup.later': {
    en: 'Later',
    zh: '稍后再说',
    ja: 'あとで',
    ko: '나중에',
  },
  'play.stop': {
    en: 'Stop',
    zh: '停止',
    ja: '停止',
    ko: '중지',
  },
  'play.downloadSave': {
    en: 'Download save (continue locally)',
    zh: '下载存档(可在本地版继续玩)',
    ja: 'セーブをDL(ローカル版で続行可)',
    ko: '세이브 다운로드 (로컬에서 이어하기)',
  },
  'play.downloadSaveShort': {
    en: 'Save',
    zh: '下载存档',
    ja: 'セーブDL',
    ko: '세이브',
  },
  'play.avatarNone': {
    en: 'Default — the Turned (amnesiac)',
    zh: '默认 · 转身者(失忆者)',
    ja: 'デフォルト · 転身者(記憶喪失)',
    ko: '기본 · 전신자(기억상실)',
  },
  'play.avatarCreate': {
    en: 'Create avatar',
    zh: '创建分身',
    ja: '分身を作る',
    ko: '분신 만들기',
  },
  'play.avatarSoon': {
    en: 'Avatars are under maintenance — playing with your default identity for now.',
    zh: '分身功能调试中,暂用默认身份',
    ja: '分身機能は調整中です。当面はデフォルトの身分でプレイします',
    ko: '분신 기능 점검 중입니다. 당분간 기본 신분으로 플레이합니다',
  },
  'play.gateway': { en: 'gateway', zh: '网关', ja: 'ゲートウェイ', ko: '게이트웨이' },
  'play.couldNotStart': {
    en: 'Could not start:',
    zh: '无法启动:',
    ja: '開始できません:',
    ko: '시작할 수 없음:',
  },
  'play.startGatewayHint': {
    en: '  ·  start the gateway first (see README)',
    zh: '  ·  请先启动网关(见 README)',
    ja: '  ·  先にゲートウェイを起動(README参照)',
    ko: '  ·  먼저 게이트웨이 실행(README 참고)',
  },
  'play.leaveScene': {
    en: 'leave scene',
    zh: '离开场景',
    ja: 'シーンを出る',
    ko: '장면 나가기',
  },
  'play.skip': {
    en: 'Skip',
    zh: '跳过',
    ja: 'スキップ',
    ko: '건너뛰기',
  },
  'play.clickSkip': {
    en: 'click to skip',
    zh: '点击跳过',
    ja: 'クリックでスキップ',
    ko: '클릭해 건너뛰기',
  },
  'play.narration': { en: 'Narration', zh: '旁白', ja: 'ナレーション', ko: '내레이션' },
  'play.thinking': {
    en: '{name} is thinking…',
    zh: '{name} 正在思考…',
    ja: '{name} は考え中…',
    ko: '{name} 생각 중…',
  },
  // First-turn loading: the model needs 1.5–3 min on cold context.
  // Set the right expectation; this title sits above the scrolling
  // thinking log so the user knows the wait is real and bounded.
  'play.openingTitleWorld': {
    en: 'Opening the world…',
    zh: '正在开启世界…',
    ja: '世界を開いています…',
    ko: '세계를 여는 중…',
  },
  'play.openingTitleSoul': {
    en: 'Reaching {name}…',
    zh: '正在唤起 {name}…',
    ja: '{name} と接続中…',
    ko: '{name} 에게 다가가는 중…',
  },
  // Honest framing of the wait. "Average ~1.5 min + complex scenes
  // run live simulation + expect surprises" — promise of depth, not
  // apology for slowness. We're closer to a slow-cooked simulation
  // than a fast assistant; the copy should set that brand expectation
  // before the player starts reading.
  'play.openingExpect': {
    en: 'About 1.5 min on average. Complex scenes spin up live simulation — longer thinking, richer roleplay, surprises in store.',
    zh: '平均思考约 1 分半。遇到复杂场景会启动实时推演——思考越久,角色扮演越细腻,会有惊喜在等你。',
    ja: '平均約 1 分半。複雑な場面ではリアルタイム推論が走ります——長く考えるほど、ロールプレイは細やかに、驚きが待っています。',
    ko: '평균 약 1분 30초. 복잡한 장면은 실시간 추론을 가동합니다——더 오래 생각할수록 롤플레이는 섬세해지고, 깜짝 놀랄 일이 기다립니다.',
  },
  'play.waits': {
    en: '{name} waits for you to speak.',
    zh: '{name} 等着你开口。',
    ja: '{name} はあなたの言葉を待っている。',
    ko: '{name} 이(가) 당신의 말을 기다린다.',
  },
  'play.sayTo': {
    en: 'say something to {name}…',
    zh: '对 {name} 说点什么…',
    ja: '{name} に話しかける…',
    ko: '{name} 에게 말 걸기…',
  },
  'play.whatDo': {
    en: 'what do you do?',
    zh: '你要做什么?',
    ja: 'どうする?',
    ko: '무엇을 하나요?',
  },
  'play.footer': {
    en: 'server-side · cost-capped · idle-evicted · reuse keeps it cheap',
    zh: '服务端 · 成本封顶 · 空闲回收 · 复用更省',
    ja: 'サーバー側 · コスト上限 · アイドル回収 · 再利用で節約',
    ko: '서버측 · 비용 상한 · 유휴 회수 · 재사용으로 절약',
  },
  'play.budgetWall': {
    en: 'Budget wall:',
    zh: '预算上限:',
    ja: '予算上限:',
    ko: '예산 한도:',
  },
  'play.expired': {
    en: 'Session expired (idle). Start again.',
    zh: '会话已过期(空闲)。请重新开始。',
    ja: 'セッション期限切れ(アイドル)。再開してください。',
    ko: '세션 만료(유휴). 다시 시작하세요.',
  },
  'play.errOverload': {
    en: 'The model is overloaded right now (the provider is busy). Your message was kept — press send again in a moment.',
    zh: '模型当前过载(服务商繁忙)。你的消息已保留 —— 稍候再点发送。',
    ja: 'モデルが過負荷です(プロバイダ混雑)。メッセージは保持 — 少し待って再送信を。',
    ko: '모델이 과부하입니다(제공자 혼잡). 메시지는 보관됨 — 잠시 후 다시 전송.',
  },
  'play.signInToPlay': {
    en: 'Sign in (top-right) to play — hosted play runs on our model and is for registered users.',
    zh: '右上角登录后即可游玩 —— 在线游玩跑在我们的模型上,仅限注册用户。',
    ja: '右上からサインインで遊べます — ホストプレイは当方のモデルで動き、登録ユーザー限定です。',
    ko: '우측 상단에서 로그인하면 플레이 — 호스팅 플레이는 our 모델로 구동되며 등록 사용자 전용입니다.',
  },
  'play.errTimeout': {
    en: 'That turn timed out before the model answered. Your message was kept — try again.',
    zh: '该回合在模型回应前超时。你的消息已保留 —— 请重试。',
    ja: 'モデル応答前にターンがタイムアウト。メッセージは保持 — 再試行を。',
    ko: '모델 응답 전 턴 시간 초과. 메시지는 보관됨 — 다시 시도.',
  },
}

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string }
const LangCtx = createContext<Ctx | null>(null)

function initialLang(): Lang {
  // 1. ?lang=ja query param — cross-domain links always win, so the
  //    language follows the user from the source page.
  try {
    const p = new URLSearchParams(window.location.search).get('lang')
    if (p && (LANGS as readonly string[]).includes(p)) {
      try { localStorage.setItem('rp-hub:lang', p) } catch { /* ignore */ }
      return p as Lang
    }
  } catch {
    /* SSR / no window */
  }
  // 2. localStorage (survives reloads, but never overrides ?lang=).
  try {
    const s = localStorage.getItem('rp-hub:lang') as Lang | null
    if (s && (LANGS as readonly string[]).includes(s)) return s
  } catch {
    /* storage off */
  }
  // 3. Browser/system language.
  const nav = typeof navigator !== 'undefined' ? navigator.language : 'en'
  if (nav.startsWith('zh')) return 'zh'
  if (nav.startsWith('ja')) return 'ja'
  if (nav.startsWith('ko')) return 'ko'
  return 'en'
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)
  // Persist the URL ?lang= into localStorage so it survives past this
  // first page-load (cross-domain links carry it; subsequent clicks keep it).
  useEffect(() => {
    try {
      if (!localStorage.getItem('rp-hub:lang')) {
        const p = new URLSearchParams(window.location.search).get('lang')
        if (p && (LANGS as readonly string[]).includes(p)) {
          localStorage.setItem('rp-hub:lang', p)
        }
      }
    } catch {
      /* ignore */
    }
  }, [])
  const setLang = (l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem('rp-hub:lang', l)
    } catch {
      /* ignore */
    }
  }
  const t = (k: string) => {
    const e = STRINGS[k]
    if (!e) return k
    return e[lang] ?? e.en ?? k
  }
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>
}

export function useI18n(): Ctx {
  const c = useContext(LangCtx)
  if (!c) throw new Error('useI18n outside LangProvider')
  return c
}
