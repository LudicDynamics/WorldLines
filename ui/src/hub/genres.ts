// 2-level 二次元 genre tree for /create/world. The outer ring is the
// world/setting (8 spheres); drilling once lands on a sub-flavour
// that becomes the chosen genre. The full path (joined with " · ")
// is shipped to the gateway as `?genre=…`. Defaults hard-coded here;
// /admin tree editor lets us override the whole tree without redeploy.
//
// Level-1 (8 spheres) gets a unique generated cover. Level-2 (6 each
// = 48 leaves) intentionally inherits the L1 cover for visual
// continuity — they're variants of the same world, so the picker
// reads as "you're inside <L1>". Visual variety at L2 comes from a
// per-id hue-rotate overlay rendered by the picker, not from more
// GPU time.
//
// IDs (the `id` field) are the stable Chinese labels used as the
// outgoing genre value — i18n labels are display-only.

export type GenreNode = {
  /** Stable identifier — also the Chinese display label + the value
   *  sent to the backend. Keep short. */
  id: string
  glyph: string
  zh: string
  en: string
  ja: string
  ko: string
  /** L1 → L2 only. Leaf has no children. */
  children?: GenreNode[]
}

const N = (
  id: string,
  glyph: string,
  i18n: { en: string; ja: string; ko: string },
  children?: GenreNode[],
): GenreNode => ({ id, zh: id, ...i18n, glyph, children })

export const GENRE_TREE: GenreNode[] = [
  N('异世界', '🌀', { en: 'Isekai', ja: '異世界', ko: '이세계' }, [
    N('死后转生', '♻️', { en: 'Death reincarnation', ja: '死後転生', ko: '사후 환생' }),
    N('勇者召唤', '⚔️', { en: 'Hero summon', ja: '勇者召喚', ko: '용사 소환' }),
    N('系统流', '⚙️', { en: 'System', ja: 'システム', ko: '시스템' }),
    N('网游系', '🎮', { en: 'Trapped in VRMMO', ja: 'VRMMO', ko: 'VRMMO' }),
    N('异世界种田系', '🌾', { en: 'Slow life farming', ja: 'スローライフ', ko: '느린 삶 농경' }),
    N('反派千金', '🌹', { en: 'Villainess', ja: '悪役令嬢', ko: '악역 영애' }),
  ]),
  N('魔法学院', '🪄', { en: 'Magic Academy', ja: '魔法学院', ko: '마법학원' }, [
    N('元素流', '🔥', { en: 'Elemental', ja: '属性', ko: '속성' }),
    N('黑魔法', '🕯️', { en: 'Dark magic', ja: '闇魔法', ko: '암흑마법' }),
    N('学院日常', '🎓', { en: 'Academy life', ja: '学院日常', ko: '학원 일상' }),
    N('召唤兽契约', '🐉', { en: 'Beast pact', ja: '使い魔契約', ko: '소환수 계약' }),
    N('古代符文', '🪶', { en: 'Ancient runes', ja: '古代ルーン', ko: '고대 룬' }),
    N('炼金术', '⚗️', { en: 'Alchemy', ja: '錬金術', ko: '연금술' }),
  ]),
  N('校园', '📚', { en: 'Campus', ja: '学園', ko: '학원' }, [
    N('现代校园', '🏫', { en: 'Modern', ja: '現代学園', ko: '현대 학원' }),
    N('异能校园', '✨', { en: 'Esper school', ja: '能力学園', ko: '능력 학원' }),
    N('学院战记', '🛡️', { en: 'Academy war', ja: '学園戦記', ko: '학원 전기' }),
    N('体育部', '⚽', { en: 'Sports club', ja: '部活', ko: '체육부' }),
    N('文艺社团', '🎨', { en: 'Arts club', ja: '文化部', ko: '문예부' }),
    N('学生会政治', '🗳️', { en: 'Student council', ja: '生徒会', ko: '학생회 정치' }),
  ]),
  N('妖怪', '👹', { en: 'Yōkai', ja: '妖怪', ko: '요괴' }, [
    N('神社系', '⛩️', { en: 'Shrine', ja: '神社', ko: '신사' }),
    N('都市妖怪', '🌃', { en: 'Urban yōkai', ja: '都市妖怪', ko: '도시 요괴' }),
    N('鬼魅传奇', '👻', { en: 'Ghost lore', ja: '怪談', ko: '괴담' }),
    N('阴阳师', '🪭', { en: 'Onmyōji', ja: '陰陽師', ko: '음양사' }),
    N('异形共生', '🤝', { en: 'Coexistence', ja: '共生', ko: '공생' }),
    N('妖怪商店', '🏮', { en: 'Yōkai shop', ja: '妖怪商店', ko: '요괴 상점' }),
  ]),
  N('末世', '⚰️', { en: 'Apocalypse', ja: '終末', ko: '종말' }, [
    N('末日生存', '🥫', { en: 'Survival', ja: '生存', ko: '생존' }),
    N('变异灾难', '🧬', { en: 'Mutation', ja: '変異', ko: '변이' }),
    N('文明遗骸', '🏚️', { en: 'Remnants', ja: '遺骸', ko: '잔해' }),
    N('病毒末日', '🦠', { en: 'Pandemic', ja: 'パンデミック', ko: '판데믹' }),
    N('末日学院', '🎒', { en: 'Doom academy', ja: '終末学園', ko: '종말 학원' }),
    N('重启文明', '🔄', { en: 'Reboot', ja: '再建', ko: '재건' }),
  ]),
  N('仙侠', '🌸', { en: 'Xianxia', ja: '仙侠', ko: '선협' }, [
    N('修真世家', '🏯', { en: 'Cultivator clan', ja: '修真世家', ko: '수진 세가' }),
    N('飞剑流派', '⚔️', { en: 'Sword school', ja: '飛剣流派', ko: '비검 유파' }),
    N('渡劫升仙', '⚡', { en: 'Ascension', ja: '渡劫', ko: '천겁' }),
    N('魔道修真', '🌑', { en: 'Demonic path', ja: '魔道', ko: '마도' }),
    N('山海异闻', '🐲', { en: 'Mountain & sea', ja: '山海異聞', ko: '산해이문' }),
    N('仙侠都市', '🏙️', { en: 'Urban xianxia', ja: '都市仙侠', ko: '도시 선협' }),
  ]),
  N('机甲科幻', '🤖', { en: 'Mecha SF', ja: 'メカSF', ko: '메카 SF' }, [
    N('巨型机甲', '🦾', { en: 'Mecha', ja: 'メカ', ko: '메카' }),
    N('星际殖民', '🚀', { en: 'Colony', ja: '宇宙植民', ko: '우주 식민' }),
    N('赛博朋克', '🌆', { en: 'Cyberpunk', ja: 'サイバーパンク', ko: '사이버펑크' }),
    N('时空旅行', '⏳', { en: 'Time travel', ja: '時空旅行', ko: '시공 여행' }),
    N('AI 觉醒', '🧠', { en: 'AI awakening', ja: 'AI覚醒', ko: 'AI 각성' }),
    N('太空歌剧', '🌌', { en: 'Space opera', ja: 'スペースオペラ', ko: '스페이스 오페라' }),
  ]),
  N('江湖武侠', '🗡️', { en: 'Wuxia', ja: '武侠', ko: '무협' }, [
    N('名门正派', '🏯', { en: 'Orthodox sect', ja: '正派', ko: '정파' }),
    N('邪魔旁门', '🐍', { en: 'Heterodox', ja: '邪派', ko: '사파' }),
    N('江湖游侠', '🐎', { en: 'Wanderer', ja: '遊侠', ko: '유협' }),
    N('镖局武林', '📦', { en: 'Escort guild', ja: '鏢局', ko: '표국' }),
    N('武林秘籍', '📖', { en: 'Lost manual', ja: '武林秘伝', ko: '무림비급' }),
    N('边塞武侠', '🏔️', { en: 'Frontier wuxia', ja: '辺境武侠', ko: '변경 무협' }),
  ]),
]
