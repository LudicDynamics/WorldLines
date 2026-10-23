// ═══════════════════════════════════════════════════════════════════
// 真引擎版 ext.js:Mock 的经济 / 势力「常量与小工具」—— 数据来自世界(game/world/economy.json · factions.json),
// 规则由引擎的 mixins 跑(packs/mixins/economy · factions)。这里不模拟任何东西。
// 名字与 Mock 的 ext.js 一致(GOODS / MARKETS / FACTIONS / ROUTES / REL0 / relKey / coin / fmtCoin / goodOf / ECON / FAC),
// 页面代码(pages.js / app.js / link.js)原样使用。
// ═══════════════════════════════════════════════════════════════════
// 多语言的值(引擎 / 模板现在有不少名字是 {zh, en, ja, ko}):按设置里的叙事语言(wl-local-lang)取,缺了先退英文、再退中文;
// 剧情阶段这种 {name, goal} 取 name。niko 10-24:剧情图上一排「[object Object]」= 界面直接把对象拼进了字符串
const LOC = v => {
  if (v == null) return '';
  if (typeof v !== 'object') return String(v);
  if (Array.isArray(v)) return v.map(LOC).join(' · ');
  if ('name' in v && !('zh' in v || 'en' in v)) return LOC(v.name);
  if ('title' in v && !('zh' in v || 'en' in v)) return LOC(v.title);
  let lg = 'zh'; try { lg = localStorage.getItem('wl-local-lang') || 'zh'; } catch { /* storage off */ }
  return String(v[lg] || (lg === 'zh' ? v.zh || v.en : v.en || v.zh) || Object.values(v).find(x => typeof x === 'string') || '');
};
// 改名写回时保住原来的形状:字符串 → 新字符串;{zh, en, …} → 只改当前语言那一格;{name, goal} → 只改 name(别的语言 / goal 不丢)
const LOCSET = (old, v) => {
  if (old == null || typeof old !== 'object' || Array.isArray(old)) return v;
  if ('name' in old && !('zh' in old || 'en' in old)) return { ...old, name: LOCSET(old.name, v) };
  let lg = 'zh'; try { lg = localStorage.getItem('wl-local-lang') || 'zh'; } catch { /* storage off */ }
  return { ...old, [lg]: v };
};
const FAC_COLORS = ['#A594FF', '#5CC8E8', '#F0616D', '#F2B84B', '#3DDC97', '#E58CFF'];
let GOODS = {}, MARKETS = {}, FACTIONS = {}, ROUTES = [], REL0 = {};

function v3ApplyWorldData(eco, fac) {
  GOODS = eco.goods || {};
  MARKETS = {};
  for (const [t, m] of Object.entries(eco.markets || {})) MARKETS[t] = { name: V3.townName(t), ...m };
  ROUTES = (eco.routes || fac.routes || []).map(r => [r[0], r[1]]);
  FACTIONS = {};
  Object.entries(fac.factions || {}).forEach(([k, f], i) => { FACTIONS[k] = { ...f, c: f.color || FAC_COLORS[i % FAC_COLORS.length] }; });
  REL0 = fac.relations || {};
}
const relKey = (a, b) => (REL0[`${a}.${b}`] !== undefined ? `rel.${a}.${b}` : `rel.${b}.${a}`);
const coin = A => (+(A.st.vars['player.gold']?.value || 0)) * 100 + (+(A.st.vars['player.silver']?.value || 0)) * 10 + (+(A.st.vars['player.copper']?.value || 0));
const fmtCoin = c => { const g = Math.floor(c / 100), s = Math.floor(c % 100 / 10), k = c % 10; return [g && `${g} 金`, s && `${s} 银`, (k || (!g && !s)) && `${k} 铜`].filter(Boolean).join(' '); };
const goodOf = t => Object.entries(GOODS).find(([, g]) => t.includes(g.name))?.[0];

// 扩展登记:只给页面「这个 op 归哪个扩展」「扩展开没开」用;init 不建状态(状态是引擎的)
const ECON = { id: 'economy', name: '经济', init() {}, ops: { trade: {}, new_caravan: {}, haul: {}, deliver: {}, rob: {} } };
const FAC = {
  id: 'factions', name: '势力', init() {},
  ops: { rumor: {}, spread: {}, new_quest: {}, quest: {}, take_quest: {}, strike: {} },
  repKey: k => (FACTIONS[k]?.rep_var || `rep.${k}`),
  premium: () => 0,
};
