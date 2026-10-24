/* Worldlines 工作室 · 原型 v3
   六个台子:游玩一览 · 编排 · 世界与角色 · Template · 测试台 · 前端。数据是石津镇真实模板;引擎行为在页面里模拟。 */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const IMG = n => (/^(\/|https?:)/.test(n) ? n : `img/${n}`);  // 引擎给的图是绝对地址
/* 玻璃砖:封面(或玻璃底)+ 折射边 + 色散边 + 斜面高光。所有卡片共用。 */
const brick = (cls, img, inner, attrs = '') => `<div class="brick ${img ? 'img' : ''} ${cls}" ${attrs}>${img ? `<img class="bimg" src="${IMG(img)}" alt=""><span class="rim"><span style="background-image:url(${IMG(img)})"></span></span>` : '<span class="rim glass"><span></span></span>'}<span class="fringe"></span><span class="sheen"></span><div class="body">${inner}</div></div>`;
const AMB = { cat: 'cover-elena.jpg', orch: 'map-t001.jpg', duo: 'map-t001.jpg', tpl: 'cover-towns.jpg', test: 'place-dock.jpg', fe: 'map-t001.jpg' };

/* ================================================================ 数据 */
const CONTRACTS = {
  'mystery-trpg': { short: '沙盒跑团', title: '沙盒跑团', pitch: '一桩案子、一组固定的人;谈好再查,骰子决定线索,走到结局才揭晓真相。',
    entry: '开场必须由世界自带;角色固定', exit: '到达结局;谜底必须在结局时揭晓', endings: { min: 3, require: 'true' },
    rewards: { player: ['结局 CG', '线索图鉴'], soul: ['信任', '记忆延续'], world: ['案件结果写回世界'] },
    outputs: ['结局 id', '解锁的 CG', '尾声', '奖励发放', '回放包'], publish: '跑通一个结局' },
  'open-adventure': { short: '开放冒险', title: '开放冒险', pitch: '自选出发点,世界自己在走;不要求结局,按天结算,带走地图、关系和新长出来的地方。',
    entry: '开场由世界自带;可以带自己的角色', exit: '按「一天」结算一段', endings: { min: 0 },
    rewards: { player: ['地图解锁', '收藏'], soul: ['关系成长'], world: ['新长出的地点保留'] },
    outputs: ['段落 id', '奖励发放', '尾声', '回放包'], publish: '结算一段' },
  'murder-mystery': { short: '剧本杀', title: '解谜型剧本杀', pitch: '一桌人各有一份剧本和秘密;搜证、对质、指认真凶,复盘时所有剧本摊开。',
    entry: '开场由世界自带;角色固定,按剧本分配身份', exit: '指认真凶后进入结局;真相必须揭晓', endings: { min: 2, require: 'true' },
    rewards: { player: ['结局 CG', '复盘剧本'], soul: ['记忆延续'], world: ['案件结果写回世界'] },
    outputs: ['结局 id', '指认结果', '真相揭晓', '解锁的 CG', '奖励发放', '回放包'], publish: '跑通一个结局' },
  'romance-companion': { short: '恋爱陪伴', title: '恋爱陪伴', pitch: '和固定的那个人过日子:每次约会结算一段,好感和回忆留下来;线路结局可选。',
    entry: '开场由世界自带;对象固定', exit: '按「一次约会」结算一段', endings: { min: 0 },
    rewards: { player: ['约会 CG', '回忆相册'], soul: ['好感', '记忆延续'], world: [] },
    outputs: ['段落 id', '好感变化', '解锁的 CG', '尾声', '奖励发放', '回放包'], publish: '结算一段' },
};

const TOOLS = {
  read:       { kind: 'tool',    sync: true,  fields: 'target',          validator: '',                    src: 'engine',        doc: '读世界数据:价目、路程、谁在哪' },
  mic:        { kind: 'tool',    sync: true,  fields: 'who, ask',        validator: '',                    src: 'engine',        doc: '把话筒递给在场角色' },
  board:      { kind: 'update',  sync: true,  fields: 'key, value',      validator: '',                    src: 'engine',        doc: '改计划板' },
  need:       { kind: 'request', sync: true,  fields: 'who',             validator: '',                    src: 'engine',        doc: '要某角色先表态' },
  roll:       { kind: 'tool',    sync: true,  fields: 'who, attr, dc',   validator: 'roll_check',          src: 'pack rpg',      doc: '掷约好的检定' },
  dice:       { kind: 'tool',    sync: true,  fields: 'expr, vs',        validator: '',                    src: 'pack rpg',      doc: '掷骰,正文停下等点数' },
  move:       { kind: 'action',  sync: true,  fields: 'who, to',         validator: 'judge_move',          src: 'pack rpg',      doc: '移动' },
  buy:        { kind: 'action',  sync: true,  fields: 'item, qty',       validator: 'judge_buy',           src: 'pack rpg',      doc: '买东西' },
  trade:      { kind: 'action',  sync: true,  fields: 'good, qty',       validator: 'economy:judge_trade', src: 'mixin economy', doc: '在镇上买卖货物' },
  flag:       { kind: 'update',  sync: true,  fields: 'key',             validator: '',                    src: 'engine',        doc: '剧情标记' },
  set:        { kind: 'update',  sync: true,  fields: 'var, value',      validator: 'schema',              src: 'engine',        doc: '改变量' },
  combat:     { kind: 'mode',    sync: true,  fields: 'roster, note',    validator: 'combat_grounds',      src: 'pack rpg',      doc: '进入战斗层' },
  end_combat: { kind: 'update',  sync: true,  fields: '',                validator: '',                    src: 'pack rpg',      doc: '退出战斗层' },
  referee:    { kind: 'mode',    sync: true,  fields: 'question',        validator: '',                    src: 'pack rpg',      doc: '请规则裁判裁定一次' },
  map:        { kind: 'tool',    sync: false, fields: 'level',           validator: '',                    src: 'pack rpg',      doc: '画地图给玩家(异步,不等)' },
  sheet:      { kind: 'tool',    sync: false, fields: '',                validator: '',                    src: 'pack rpg',      doc: '显示属性面板(异步)' },
  accuse:     { kind: 'action',  sync: true,  fields: 'who',             validator: 'judge_accuse',        src: '—',             doc: '指认真凶(剧本杀)' },
};

// 编排台的演示图(原型 · ?demo=1)。开源版只有通用的单拍回合;我们的两拍图在私有层(PRIVATE_UI.graphs)
const PRIV = window.PRIVATE_UI || {};
const GRAPHS = {
  'turn-default': { title: '通用回合 · 单拍', start: 'turn', demo: ['去杂货铺', '看看四周'],
    nodes: {
      turn:  { kind: 'loop', title: '回合', x: 120, y: 160, tools: ['dice', 'move', 'buy', 'flag', 'set'], prompt: 'turn', knobs: {},
               steps: [['engine', '掷骰'], ['par', ['在场角色'], '角色各自回应'], ['llm', '叙事'], ['engine', '校验 → 落账'], ['engine', '推进']] },
      ticks: { kind: 'tick', title: '后台单位', x: 480, y: 160, tools: ['set'], prompt: '—(0 token)', knobs: { when: '每回合后' },
               steps: [['par', ['时钟'], '同一时刻触发的单位并行'], ['engine', '改动按单位归属']] },
    },
    edges: [{ id: 't1', from: 'turn', to: 'ticks', on: 'always', val: '' }, { id: 't2', from: 'ticks', to: 'turn', on: 'always', val: '' }] },
  ...(PRIV.graphs || {}),
};
const TRIG = { words: '玩家用词', dm: '@主持', judge: '判断器', gate: 'gate 预判', op: 'op 调用', here: '地点类', var: '变量条件', tick: '时钟', always: '总是' };
const KIND = { loop: 'agent loop', mode: '模式层', one: '一次性', tick: '后台单位' };
// 只显示、不出「+ 加节点」按钮的节点种类(插件自己的节点:游戏客户端的交互)
const kindName = k => KIND[k] || ({ interaction: '交互 · 客户端' })[k] || k;

const PLACES = {
  gate:   { name: '北门', x: 17, y: 17, img: 'place-gate.jpg', data: { id: 'T001/gate_north', 'links': '主街 8 分钟', '守卫': '夜里换岗' } },
  guild:  { name: '冒险者公会', x: 39, y: 26, img: 'place-guild.jpg', data: { id: 'T001/guild', '委托': '3 条', '会长': '巴斯' } },
  shop:   { name: '老苇杂货铺', x: 51, y: 35, img: '', data: { id: 'T001/shop', '小治疗药水': '10 金', '绳子': '2 金', '老板': '能讲价' } },
  inn:    { name: '河灯旅店', x: 64, y: 44, img: 'place-inn.jpg', data: { id: 'T001/inn', '住宿': '3 金 / 晚', '传闻': '码头夜里有人卸货' } },
  street: { name: '主街', x: 50, y: 54, img: '', data: { id: 'T001/main_street', 'links': '杂货铺 10 分 · 旅店 6 分 · 码头 15 分' } },
  dock:   { name: '北码头', x: 24, y: 82, img: 'place-dock.jpg', data: { id: 'T001/dock', '雾': '最浓', '工头': '收钱就不多问' } },
};
const SOULS = {
  elena: { name: '艾琳娜', img: 'elena.jpg', line: '失去过去的治疗师', at: 'gate', say: '「行,我陪你去,价钱我来谈。不过谈下来的差价,一半归我。」',
           data: { 说话: '短句,先讲条件再答应', 会同意: '治伤 · 陪同 · 替你讲价(要分成)', 会拒绝: '伤害无辜 · 谈她的过去', trust: '2 / 10', mood: '平静' }, haunts: ['gate', 'inn'] },
  rowan: { name: '罗文', img: 'rowan.jpg', line: '想成传奇的冒险者', at: 'guild', say: '「旧地图上标着码头底下有条路。我们今晚就去?」',
           data: { 说话: '急,爱夸口,但守信', 会同意: '冒险 · 打架 · 夜探', 会拒绝: '丢下同伴', trust: '4 / 10', mood: '兴奋' }, haunts: ['guild', 'dock'] },
};

const S = {
  screen: 'cat',
  // 模板当前状态(Template / lint / 一览共用)
  ctr: 'mystery-trpg', graph: PRIV.defaultGraph || 'turn-default', mixins: { economy: true, factions: true },
  endings: [{ id: 'E10', title: '记忆归来', kind: 'true', cg: true }, { id: 'E11', title: '雾中的新名字', kind: 'alt', cg: false }, { id: 'E19', title: '倒在雾里', kind: 'fail', cg: false }],
  clues: false, scripts: false, affection: false, accuse: false, dateCg: false, cert: false, submitted: false,
  // 一览
  pan: { x: -40, y: 0 }, catFilter: 'all', sel: null, reviews: { 'fog-lamp': 'review' },
  // 编排
  layer: 'graph', node: PRIV.defaultNode || 'turn', edge: null, cur: null, stack: [], liveEdge: null, chat: null, toolsOver: {},
  // 世界 · 角色
  face: 'world', pick: { t: 'place', id: 'gate' }, insp: 'data', gen: {},
  // 测试台
  round: 0, mtab: 'play', mout: 'html', extra: [],
  // 前端
  wview: 'play', target: 'godot', fsel: 'scenes/Main.tscn', fe: null,
};
const G = () => GRAPHS[S.graph];
// 10-17:引擎读来的世界图上,节点的步骤 / 工具 / 提示词 / 参数引擎还不读(只读 state 和边)—— 画成灰的只读,不让人以为改了会生效
const unreadOf = g => !!(g && g.raw && !g.soul);
const UNREAD = '<span class="unread-tag">引擎尚未读取</span>';
const C = () => CONTRACTS[S.ctr];
const nodeTools = id => S.toolsOver[S.graph + ':' + id] || (G().nodes[id] ? G().nodes[id].tools : []);
const packTools = () => [...new Set(Object.keys(G().nodes).flatMap(nodeTools))].concat(S.accuse ? ['accuse'] : []);

/* ================================================================ lint(按合约) */
function lint() {
  const c = C(), out = [], ends = S.endings, tl = packTools();
  if (c.endings.min && ends.length < c.endings.min) out.push({ lv: 'block', code: 'contract.endings', msg: `至少 ${c.endings.min} 个结局,现在 ${ends.length} 个`, go: 'duo' });
  if (c.endings.require && !ends.some(e => e.kind === 'true')) out.push({ lv: 'block', code: 'contract.endings', msg: '缺真相结局(kind=true)', go: 'duo' });
  if (c.rewards.player.includes('结局 CG')) ends.filter(e => !e.cg).forEach(e => out.push({ lv: 'block', code: 'contract.rewards', msg: `结局 ${e.id}「${e.title}」没有 CG`, fix: 'cg:' + e.id }));
  if (c.rewards.player.includes('线索图鉴') && !S.clues) out.push({ lv: 'block', code: 'contract.rewards', msg: '合约要线索图鉴,世界里没有 clue 数据', fix: 'clues', go: 'duo' });
  if (c.rewards.player.includes('复盘剧本') && !S.scripts) out.push({ lv: 'block', code: 'contract.entry', msg: '每个角色要一份剧本和秘密(按剧本分配身份)', fix: 'scripts', go: 'duo' });
  if (S.ctr === 'murder-mystery' && !tl.includes('accuse')) out.push({ lv: 'block', code: 'contract.exit', msg: '出口是「指认」,Pack 的编排里没有 accuse 工具', fix: 'accuse', go: 'orch' });
  if (c.rewards.soul.includes('好感') && !S.affection) out.push({ lv: 'block', code: 'contract.rewards', msg: '合约要好感,角色 schema 里没有 affection 变量', fix: 'affection', go: 'duo' });
  if (c.rewards.player.includes('约会 CG') && !S.dateCg) out.push({ lv: 'warn', code: 'contract.rewards', msg: '约会 CG 槽是空的,结算时不会解锁图', fix: 'dateCg' });
  if (c.rewards.player.includes('收藏')) out.push({ lv: 'warn', code: 'contract.rewards', msg: '没有声明可收藏物,收藏奖励会是空的' });
  out.push({ lv: 'ok', code: 'contract.entry', msg: '开场写在 game-start.json,开局不调模型' });
  out.push({ lv: 'ok', code: 'contract.exit', msg: c.exit });
  out.push({ lv: 'ok', code: 'schema.view', msg: '7 个 view 的 widget 都认识' });
  out.push({ lv: 'ok', code: 'assets.card', msg: '封面 assets/cover.png 已填' });
  return out;
}
const blocks = () => lint().filter(x => x.lv === 'block');

/* ================================================================ 外壳 */
const SCREENS = [['cat', '游玩一览', 'dusk'], ['orch', '编排', ''], ['duo', '世界 · 角色', ''], ['tpl', 'Template', ''], ['test', '测试台', 'dusk'], ['fe', '前端', '']];
function go(s) { S.screen = s; render(); }
function render() {
  const sc = SCREENS.find(x => x[0] === S.screen);
  const amb = $('#amb'); if (amb && !amb.src.endsWith(AMB[S.screen])) amb.src = IMG(AMB[S.screen]);
  $('#nav').innerHTML = SCREENS.map(([k, l]) => `<button class="${S.screen === k ? 'on' : ''}" data-go="${k}">${l}</button>`).join('');
  const b = blocks().length;
  $('#ctx').innerHTML = S.screen === 'cat' ? `<span class="chip">本地 · 6 个世界</span>` :
    `<span class="chip">stoneford-elena</span><span class="chip ${b ? 'rust' : 'sage'}">${C().short} · ${b ? b + ' 个 block' : 'lint 清零'}</span>`;
  $$('.screen').forEach(e => e.classList.toggle('on', e.id === 's-' + S.screen));
  ({ cat: renderCat, orch: renderOrch, duo: renderDuo, tpl: renderTpl, test: renderTest, fe: renderFe })[S.screen]();
}
document.addEventListener('click', e => {
  const g = e.target.closest('[data-go]'); if (g) { go(g.dataset.go); return; }
  const f = e.target.closest('[data-fix]'); if (f) { applyFix(f.dataset.fix); render(); }
});
function applyFix(f) {
  if (f.startsWith('cg:')) S.endings.find(x => x.id === f.slice(3)).cg = true;
  else if (f === 'accuse') { S.accuse = true; const nk = G().nodes.resolve ? 'resolve' : G().start, k = S.graph + ':' + nk; S.toolsOver[k] = [...nodeTools(nk), 'accuse']; }
  else S[f] = true;
  S.submitted = false;
}

/* ================================================================ ⑥ 游玩一览 */
function catalog() {
  const b = blocks().length;
  const me = { id: 'stoneford-elena', title: '石津镇 · 艾琳娜与罗文', img: 'cover-elena.jpg', ctr: S.ctr, pitch: '雾里的港镇,一个失去过去的治疗师,一个想成传奇的冒险者。',
    status: S.submitted ? 'review' : 'draft', meta: S.ctr === 'mystery-trpg' ? `${S.endings.length} 结局 · ${S.endings.filter(e => e.cg).length} CG` : C().short,
    gaps: [...blocks().map(x => ({ t: x.msg, code: x.code, go: x.go || 'tpl', fix: x.fix })), ...(S.cert ? [] : [{ t: '还没有试玩凭证:测试台跑到出口一次', code: 'publish.test_run', go: 'test' }])], mine: true };
  return [
    me,
    { id: 'stoneford-market', title: '石津镇 · 驿路与商队', img: 'place-dock.jpg', ctr: 'open-adventure', pitch: '粮价会涨,商队会被劫,矿工会罢工——你不来,世界也在走。', status: 'live', meta: '按天结算 · 经济 · 势力', gaps: [] },
    { id: 'three-towns', title: '灰雾北境 · 三镇驿路', img: 'cover-towns.jpg', ctr: 'open-adventure', pitch: '三个集市、两条商路;Godot 前端可玩。', status: 'live', meta: '基础前端 · Godot', gaps: [] },
    { id: 'fog-lamp', title: '雾灯下的约定', img: 'place-inn.jpg', ctr: 'romance-companion', pitch: '河灯旅店的二楼,她每晚都在窗边等雾散。', status: S.reviews['fog-lamp'], meta: '按约会结算 · 12 CG', gaps: [], review: true },
    { id: 'dock-case', title: '北码头 · 封蜡案', img: 'place-gate.jpg', ctr: 'murder-mystery', pitch: '雾夜里码头少了一箱货,五个人都说自己不在场。', status: 'draft', meta: '5 人 · 2 结局',
      gaps: [{ t: '出口是「指认」,Pack 里没有 accuse 工具', code: 'contract.exit', go: 'orch' }, { t: '5 个角色里 2 个没有剧本', code: 'contract.entry', go: 'duo' }] },
    { id: 'werewolf', title: '夜半村 · 狼人杀', img: 'place-guild.jpg', ctr: null, pitch: '六个座位、两只狼、一位预言家。', status: 'local', meta: '本地可玩', gaps: [{ t: '没有声明玩法合约 → 不能进 Hub', code: 'contract.unknown', go: 'tpl' }] },
  ];
}
const STATUS = { draft: ['草稿', 'rust'], review: ['审核中', 'blue'], live: ['已上架', 'sage'], local: ['只在本地', ''], rejected: ['被退回', 'rust'] };
function renderCat() {
  const list = catalog();
  const counts = { all: list.length }; list.forEach(w => { const k = w.ctr || 'none'; counts[k] = (counts[k] || 0) + 1; });
  $('#catbar').innerHTML = [['all', '全部'], ...Object.entries(CONTRACTS).map(([k, v]) => [k, v.short]), ['none', '未声明合约']]
    .map(([k, l]) => `<button class="${S.catFilter === k ? 'on' : ''}" data-cf="${k}">${l} <span style="opacity:.6">${counts[k] || 0}</span></button>`).join('');
  const shown = list.filter(w => S.catFilter === 'all' || (w.ctr || 'none') === S.catFilter);
  const cards = [...shown, { make: true }];
  $('#catPlane').style.transform = `translate(${S.pan.x}px,${S.pan.y}px)`;
  $('#catPlane').innerHTML = cards.map((w, i) => {
    const col = i % 3, row = Math.floor(i / 3), x = 60 + col * 480 + (row % 2) * 120, y = 120 + row * 300;
    if (w.make) return brick('wc make hov', null, `<div class="meta"><span><i>${String(i + 1).padStart(2, '0')}</i>WORKSHOP</span></div><div class="plus">+</div><div class="cap"><b style="opacity:.8">做一个世界</b><small>世界和角色一起捏 · 选一份合约 · 跑到出口就能提交</small></div>`, `style="left:${x}px;top:${y}px" data-go="duo"`);
    const st = STATUS[w.status];
    return brick(`wc hov ${S.sel === w.id ? 'on' : ''}`, w.img, `<div class="meta"><span><i>${String(i + 1).padStart(2, '0')}</i>${w.ctr ? CONTRACTS[w.ctr].short : '未声明合约'}</span><span>${esc(w.meta)}</span></div>
      <div class="state"><span class="chip ${st[1]}">${st[0]}${w.gaps.length ? ' · 缺 ' + w.gaps.length : ''}</span></div>
      <div class="cap"><b>${esc(w.title)}</b><small>${esc(w.pitch)}</small></div>`, `style="left:${x}px;top:${y}px" data-w="${w.id}"`);
  }).join('');
  renderShelf(list);
}
function renderShelf(list) {
  const el = $('#shelf'), w = list.find(x => x.id === S.sel);
  el.classList.toggle('on', !!w);
  if (!w) return;
  const st = STATUS[w.status], ok = !w.gaps.length;
  const reviewing = w.status === 'review';
  el.innerHTML = `<button class="x" data-shx aria-label="关闭">×</button>
    <div class="tag">WORLD SHELF · ${w.ctr ? CONTRACTS[w.ctr].short : '未声明合约'}</div>
    <h2>${esc(w.title)}</h2><div class="row" style="gap:6px;margin-bottom:10px"><span class="chip ${st[1]}">${st[0]}</span><span class="chip">${esc(w.meta)}</span></div>
    <div class="scroll" style="flex:1;min-height:0">
      <div class="tag" style="margin:6px 0 2px">合约体检 · ${ok ? '都满足' : '还缺 ' + w.gaps.length + ' 项'}</div>
      <ul class="sh-list">${ok ? `<li><span class="n">✓</span><div><b>入口 · 出口 · 结局 · 奖励都满足</b><small>${w.ctr ? '有试玩凭证 · 回放包已附' : ''}</small></div></li>` :
        w.gaps.map((g, i) => `<li><span class="n">${String(i + 1).padStart(2, '0')}</span><div style="flex:1"><b>${esc(g.t)}</b><small class="mono">${g.code}</small></div>${w.mine ? `${g.fix ? `<button class="chip rust" data-fix="${g.fix}">修</button>` : ''}<button class="chip" data-go="${g.go}">去改 ↗</button>` : ''}</li>`).join('')}</ul>
      ${w.ctr ? `<div class="tag" style="margin:14px 0 2px">玩家会带走</div><ul class="sh-list"><li><span class="n">◆</span><div><b>${[...CONTRACTS[w.ctr].rewards.player, ...CONTRACTS[w.ctr].rewards.soul].join(' · ')}</b><small>勋章:走过全部结局 · 一局里没人倒下</small></div></li></ul>` : ''}
      ${w.review && reviewing ? `<div class="review well"><div class="tag">审查 · 你是审核人</div>
        ${['内容:无密钥 / 无他人版权图', '合约:静态 lint 无 block', '凭证:回放能播到出口', '四语卡面齐全'].map((t, i) => `<label><input type="checkbox" data-rv="${i}" ${S['rv' + i] ? 'checked' : ''}> ${t}</label>`).join('')}
        <textarea placeholder="给作者的话(退回时必填)" id="rvNote"></textarea>
        <div class="row" style="margin-top:8px"><button class="btn p" data-rvok>通过 · 上架</button><button class="btn" data-rvno>退回</button></div></div>` : ''}
    </div>
    <div class="sh-act">
      <button data-go="test">▶ 试玩</button>
      ${w.mine ? `<button class="p" data-submit ${ok && !S.submitted ? '' : 'disabled'}>${S.submitted ? '已提交 · 等审核' : '提交审查'}</button>` : ''}
      <button>回放 · 看别人的一局</button>
    </div>`;
}
(function wireCat() {
  const sc = $('#s-cat'); let drag = null, moved = false;
  sc.addEventListener('pointerdown', e => { if (e.target.closest('.shelf,.catbar,button')) return; drag = { x: e.clientX, y: e.clientY, px: S.pan.x, py: S.pan.y }; moved = false; });
  window.addEventListener('pointermove', e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 4) { moved = true; sc.classList.add('drag'); }
    S.pan = { x: drag.px + dx, y: drag.py + dy }; $('#catPlane').style.transform = `translate(${S.pan.x}px,${S.pan.y}px)`; });
  window.addEventListener('pointerup', () => { drag = null; sc.classList.remove('drag'); });
  sc.addEventListener('mousemove', e => { if (drag) return; const r = sc.getBoundingClientRect(), tx = (e.clientX - r.left) / r.width * 2 - 1, ty = (e.clientY - r.top) / r.height * 2 - 1; $('#catTilt').style.transform = `rotateY(${tx * 6}deg) rotateX(${ty * -4}deg) scale(1.04)`; });
  sc.addEventListener('wheel', e => { if (e.target.closest('.shelf')) return; e.preventDefault(); S.pan = { x: S.pan.x - e.deltaX, y: S.pan.y - e.deltaY }; $('#catPlane').style.transform = `translate(${S.pan.x}px,${S.pan.y}px)`; }, { passive: false });
  sc.addEventListener('click', e => {
    if (moved) { moved = false; return; }
    const c = e.target.closest('[data-cf]'); if (c) { S.catFilter = c.dataset.cf; renderCat(); return; }
    const w = e.target.closest('[data-w]'); if (w) { S.sel = w.dataset.w; renderCat(); return; }
    if (e.target.closest('[data-shx]')) { S.sel = null; renderCat(); return; }
    if (e.target.closest('[data-submit]')) { S.submitted = true; render(); return; }
    const rv = e.target.closest('[data-rv]'); if (rv) { S['rv' + rv.dataset.rv] = rv.checked; return; }
    if (e.target.closest('[data-rvok]')) { if (![0, 1, 2, 3].every(i => S['rv' + i])) { $('#rvNote').placeholder = '四项都勾上才能通过'; return; } S.reviews['fog-lamp'] = 'live'; renderCat(); return; }
    if (e.target.closest('[data-rvno]')) { if (!$('#rvNote').value.trim()) { $('#rvNote').placeholder = '退回要写一句原因'; $('#rvNote').focus(); return; } S.reviews['fog-lamp'] = 'rejected'; renderCat(); }
  });
})();

/* ================================================================ ① 编排台 */
function renderOrch() {
  const el = $('#s-orch'), g = G();
  const crumbs = [['graph', '状态机图'], ['node', '节点 · ' + (g.nodes[S.node] ? g.nodes[S.node].title : '—')], ['tools', '工具注册表']];
  el.innerHTML = `<div class="ws"><div class="ws-main">
    <div class="crumb">${crumbs.map(([k, l], i) => `${i ? '<span class="sep">/</span>' : ''}<button class="${S.layer === k ? 'on' : ''}" data-layer="${k}">${l}</button>`).join('')}
      <div class="r"><span class="tag">编排图</span><select class="btn" id="gsel">${Object.entries(GRAPHS).map(([k, v]) => `<option value="${k}" ${k === S.graph ? 'selected' : ''}>${v.title}</option>`).join('')}</select></div></div>
    <div class="board" id="board"></div></div>
    <div class="side"><div class="glass"><div class="side-h"><b>对话测试</b> ${g.raw && g.tpl ? (window.ORCHLINT && window.ORCHLINT.sideHead ? window.ORCHLINT.sideHead() : '') : g.raw ? '<span class="tag" style="color:#f2c66b">演示 · 不跑引擎</span><div class="sub" style="font-size:12.5px">只在页面里按图上的边走一遍:推进词靠关键字猜,回复是占位,不是引擎的回合。真的回合去测试台跑。</div>' : '<span class="tag">空白世界 · stub 模型</span><div class="sub" style="font-size:12.5px">像玩家一样说话,看状态怎么走、调了哪些工具。不定 schema。</div>'}</div>
      <div class="chat" id="ochat"></div>
      <div class="compose"><div class="in"><input id="oin" placeholder="说一句,例如「拔剑」" autocomplete="off"><button class="send" id="osend" aria-label="发送">➤</button></div>
      <div class="sugg">${['去杂货铺', '定', '拔剑', '[end_combat]', '[referee] 能偷袭吗', '@DM'].map(s => `<button class="chip" data-os="${esc(s)}">${esc(s)}</button>`).join('')}<button class="chip solid" data-orun>跑全套</button><button class="chip" data-oreset>重来</button></div></div></div></div></div>`;
  $('#gsel').onchange = e => { S.graph = e.target.value; S.node = G().start; S.edge = null; S.cur = null; S.chat = null; S.stack = []; if (G().tpl && window.WL_setWorld) window.WL_setWorld(G().tpl, { quiet: true }); render(); };   // 这张图的模板 = 当前世界
  if (!S.chat) resetChat();
  drawChat();
  ({ graph: drawGraph, node: drawNode, tools: drawTools })[S.layer]();
}
function resetChat() { S.cur = G().start; S.stack = []; S.liveEdge = null; S.hit = new Set(); S.chat = [{ t: 'sys', h: `<span class="go">● 开局</span> 当前节点:${G().nodes[G().start].title}` }]; }
function drawChat() { const c = $('#ochat'); if (!c) return; c.innerHTML = S.chat.map(m => `<div class="m ${m.t}">${m.h}</div>`).join(''); c.scrollTop = c.scrollHeight; }

function drawGraph() {
  const b = $('#board'), g = G();
  const W = 190, H = 84;
  const pos = id => g.nodes[id];
  let wires = '', labels = '';
  g.edges.forEach(e => {
    const a = pos(e.from); let d, lx, ly;
    if (e.to === '@return') { const x = a.x + W - 30; d = `M${x},${a.y + H} C${x},${a.y + H + 40} ${x - 40},${a.y + H + 50} ${x - 70},${a.y + H + 50}`; lx = x - 50; ly = a.y + H + 50; }
    else if (e.to === e.from) { const x = a.x + W / 2; d = `M${x - 40},${a.y} C${x - 70},${a.y - 80} ${x + 70},${a.y - 80} ${x + 40},${a.y}`; lx = x; ly = a.y - 60; }
    else { const t = pos(e.to); const x1 = a.x + W, y1 = a.y + H / 2, x2 = t.x, y2 = t.y + H / 2;
      if (e.arc) { const yt = Math.min(a.y, t.y) - 50; d = `M${a.x + W / 2},${a.y} C${a.x + W / 2},${yt} ${t.x + W / 2},${yt} ${t.x + W / 2},${t.y}`; lx = (a.x + t.x + W) / 2; ly = yt + 12; }
      else if (x2 < x1) { const yb = Math.max(a.y, t.y) + H + 60; d = `M${a.x + W / 2},${a.y + H} C${a.x + W / 2},${yb} ${t.x + W / 2},${yb} ${t.x + W / 2},${t.y + H}`; lx = (a.x + t.x + W) / 2; ly = yb - 14; }
      else { const mx = (x1 + x2) / 2; d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`; lx = mx; ly = (y1 + y2) / 2 - 2; } }
    const cls = ['w', S.edge === e.id ? 'on' : '', S.liveEdge === e.id ? 'live' : '', e.to === '@return' ? 'ret' : ''].join(' ');
    wires += `<path class="hit" d="${d}" data-e="${e.id}"/><path class="${cls}" d="${d}" marker-end="url(#ah)" data-e="${e.id}"/>`;
    const txt = e.to === '@return' ? `${e.val} → 返回` : (e.on === 'always' ? (e.val || '总是') : `${TRIG[e.on]}:${e.val}`);
    labels += `<div class="elabel ${S.edge === e.id ? 'on' : ''}" style="left:${lx}px;top:${ly}px" data-e="${e.id}">${esc(txt)}</div>`;
  });
  const nodes = Object.entries(g.nodes).map(([id, n]) => `<div class="nd ${n.kind} ${S.node === id && !S.edge ? 'sel' : ''} ${S.cur === id ? 'cur' : ''}" style="left:${n.x}px;top:${n.y}px" data-n="${id}">
    ${g.start === id ? '<span class="start">START</span>' : ''}${brick('sm', null, `<div class="k"><i>●</i>${kindName(n.kind)}</div><div class="n">${esc(n.title)}</div>
    <div class="tl">${nodeTools(id).slice(0, 6).map(t => `<span>${t}</span>`).join('')}${nodeTools(id).length > 6 ? `<span>+${nodeTools(id).length - 6}</span>` : ''}${!nodeTools(id).length ? '<span>不调工具</span>' : ''}</div>`)}
    <span class="port i"></span><span class="port o" data-port="${id}" title="拖到另一个节点上 = 新建迁移"></span></div>`).join('');
  b.innerHTML = `<div class="pzv"><svg class="wires"><defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="rgba(255,255,255,.5)"/></marker></defs>${wires}<path class="ghost" id="ghost" d=""/></svg>${labels}${nodes}</div>
    <div class="tb">${Object.entries(KIND).map(([k, l]) => `<button class="btn" data-add="${k}">+ ${l}</button>`).join('')}<button class="btn" data-layer="node">打开节点内部 →</button></div>
    <div class="note ednote" style="position:absolute;transform:rotate(1deg)">拖节点移动 · 从右边小圆点拖到另一个节点 = 新建迁移<small>点连线改触发条件;双击节点看里面的 agent loop</small></div>
    <div id="pop"></div>`;
  wireBoard(b);
  if (S.edge) edgePop();
}
function wireBoard(b) {
  const g = G(); let drag = null, link = null;
  const pv = $('.pzv', b), V = pv ? panZoom(b, pv, 'orch', true) : { x: 0, y: 0, z: 1 };
  const local = e => { const r = (pv || b).getBoundingClientRect(); return [(e.clientX - r.left) / V.z, (e.clientY - r.top) / V.z]; };
  b.onpointerdown = e => {
    const p = e.target.closest('[data-port]');
    if (p) { const [x0, y0] = local(e); link = { from: p.dataset.port, x0, y0 }; e.preventDefault(); return; }
    const n = e.target.closest('[data-n]');
    if (n) { try { b.setPointerCapture(e.pointerId); } catch {} e.preventDefault(); } if (n) { const id = n.dataset.n; drag = { id, sx: e.clientX, sy: e.clientY, x: g.nodes[id].x, y: g.nodes[id].y, moved: false }; }
  };
  b.onpointermove = e => {
    if (link) { const [x, y] = local(e); $('#ghost').setAttribute('d', `M${link.x0},${link.y0} C${(link.x0 + x) / 2},${link.y0} ${(link.x0 + x) / 2},${y} ${x},${y}`); return; }
    if (!drag) return;
    const dx = (e.clientX - drag.sx) / V.z, dy = (e.clientY - drag.sy) / V.z; if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    g.nodes[drag.id].x = Math.max(6, drag.x + dx); g.nodes[drag.id].y = Math.max(6, drag.y + dy);
    const el = b.querySelector(`[data-n="${drag.id}"]`); el.style.left = g.nodes[drag.id].x + 'px'; el.style.top = g.nodes[drag.id].y + 'px';
  };
  b.onpointerup = e => {
    if (link) { const t = document.elementFromPoint(e.clientX, e.clientY); const n = t && t.closest('[data-n]');
      if (n && n.dataset.n !== link.from) { const id = 'n' + (g.edges.length + 1); g.edges.push({ id, from: link.from, to: n.dataset.n, on: 'op', val: '' }); S.edge = id; }
      link = null; drawGraph(); return; }
    if (drag) { const was = drag; drag = null; if (was.moved) { drawGraph(); return; } S.node = was.id; S.edge = null; drawGraph(); return; }
  };
  b.ondblclick = e => { const n = e.target.closest('[data-n]'); if (n) { S.node = n.dataset.n; S.layer = 'node'; renderOrch(); } };
  b.onclick = e => {
    const ed = e.target.closest('[data-e]'); if (ed) { S.edge = ed.dataset.e; drawGraph(); return; }
    const a = e.target.closest('[data-add]'); if (a) { const k = a.dataset.add, id = k + Object.keys(g.nodes).length; g.nodes[id] = { kind: k, title: '新的' + KIND[k], x: 120 + Math.random() * 300, y: 60 + Math.random() * 60, tools: [], prompt: '(未设)', knobs: {}, steps: [['llm', '主调用']] }; S.node = id; S.edge = null; drawGraph(); return; }
    if (e.target.closest('[data-pdel]')) { g.edges = g.edges.filter(x => x.id !== S.edge); S.edge = null; drawGraph(); return; }
    if (e.target.closest('[data-pclose]')) { S.edge = null; drawGraph(); }
  };
}
function edgePop() {
  const g = G(), e = g.edges.find(x => x.id === S.edge); if (!e) return;
  const a = g.nodes[e.from];
  const pop = $('#pop'); pop.className = 'pop glass'; pop.style.left = Math.min(a.x + 200, $('#board').clientWidth - 310) + 'px'; pop.style.top = (a.y + 100) + 'px';
  pop.innerHTML = `<h4>迁移 ${e.id}</h4><div class="tag">从 ${g.nodes[e.from].title} → ${e.to === '@return' ? '返回栈顶' : e.to === e.from ? '自己' : g.nodes[e.to].title}</div>
    <label class="tag" style="display:block;margin-top:10px">触发</label><select id="pon" ${e.all ? 'disabled' : ''}>${Object.entries(TRIG).map(([k, l]) => `<option value="${k}" ${k === e.on ? 'selected' : ''}>${l}</option>`).join('')}</select>
    <label class="tag">值</label><input id="pval" value="${esc(e.val)}" placeholder="例:combat / 定 · @DM / here_class room" ${e.all ? 'disabled' : ''}>
    ${e.all ? '<div class="sub" style="font-size:12px;margin-top:4px">几条推进合成了一条显示,不能在这里一起改;要改先删掉,再连一条新的</div>' : ''}
    <label class="tag">守卫(读变量,可空)${g.soul ? UNREAD : ''}</label><input id="pgd" value="${esc(e.guard || '')}" placeholder="例:journey.stop != null" ${g.soul ? 'disabled' : ''}>
    <div class="sub" id="pgdw" style="font-size:12px;margin-top:4px;color:var(--rust,#d98a6f)"></div>
    <div class="row"><button class="btn" data-pdel>删除</button><button class="btn ink" data-pclose style="margin-left:auto">好</button></div>`;
  const gw = () => { const w = $('#pgdw'); if (w) w.textContent = e.guard && window.ORCH_guard && window.ORCH_guard(e.guard) === null ? '看不懂这个守卫:写成「变量 比较 值」(== != < <= > >=),或者引擎的 JSON' : ''; };
  $('#pon').onchange = ev => { e.on = ev.target.value; };
  $('#pval').oninput = ev => { e.val = ev.target.value; };
  $('#pgd').oninput = ev => { e.guard = ev.target.value; gw(); };
  gw();
}
function drawNode() {
  const b = $('#board'), g = G(), id = g.nodes[S.node] ? S.node : g.start, n = g.nodes[id], on = nodeTools(id), ro = unreadOf(g);
  const stepH = s => s[0] === 'par' ? `<div class="par"><span class="k">并行组 · ${esc(s[2] || '')}</span>${s[1].map(x => brick('stp llm sm', null, `<div class="k">LLM</div><b>${esc(x)}</b>`)).join('')}</div>`
    : brick(`stp ${s[0]} sm`, null, `<div class="k">${{ engine: '引擎', llm: 'LLM', hook: '钩子' }[s[0]]}</div><b>${esc(s[1])}</b>`);
  b.innerHTML = `<div class="flow">
    <div class="row" style="align-items:flex-end"><div><div class="tag">${kindName(n.kind)}${g.start === id ? ' · START' : ''}</div><h2 class="h1" style="font-size:26px">${esc(n.title)}</h2></div>
      <div style="margin-left:auto" class="row">${Object.keys(g.nodes).map(k => `<button class="chip ${k === id ? 'solid' : ''}" data-pick="${k}">${g.nodes[k].title}</button>`).join('')}</div></div>
    <div class="tag" style="margin-top:20px">FLOW · 线性步骤 + 并行组(不做任意分支)${ro ? UNREAD + '<span class="muted" style="text-transform:none;letter-spacing:0;margin-left:6px">步骤是引擎写死的说明,改这里不改回合</span>' : ''}</div>
    <div class="lane ${ro ? 'unread' : ''}">${n.steps.map((s, i) => (i ? '<span class="arrow"></span>' : '') + stepH(s)).join('')}</div>
    <div style="display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:16px">
      <div><div class="tag">${ro ? '这个节点能用的工具' + UNREAD + '<span class="muted" style="text-transform:none;letter-spacing:0;margin-left:6px">这份清单只是说明:能调什么由玩法包注册表和所在的层决定,verify 把关</span>' : '这个节点能用的工具 · 把下面的工具拖进来,点一下移走'}</div>
        <div class="drop ${ro ? 'unread' : ''}" id="drop">${on.map(t => `<span class="tool on ${TOOLS[t] && !TOOLS[t].sync ? 'async' : ''}" data-untool="${t}">${t}</span>`).join('') || '<span class="muted" style="font-size:12.5px">一个工具都没有:这个节点只能写文字或输出 JSON</span>'}</div>
        <div class="tag" style="margin-top:14px">工具注册表 · 实线同步 / 虚线异步</div>
        <div class="tray ${ro ? 'unread' : ''}">${Object.keys(TOOLS).filter(t => !on.includes(t)).map(t => `<span class="tool ${TOOLS[t].sync ? '' : 'async'}" draggable="true" data-tool="${t}" title="${esc(TOOLS[t].doc)}">${t}</span>`).join('')}</div></div>
      <div class="well" style="padding:16px"><div class="tag">提示词与参数${ro ? UNREAD : ''}</div>
        <dl class="kv ${ro ? 'unread' : ''}"><dt>提示词</dt><dd class="mono" style="font-size:12px">${esc(n.prompt)}</dd>${Object.entries(n.knobs).map(([k, v]) => `<dt>${k}</dt><dd><input class="btn" style="width:120px;padding:4px 10px" value="${esc(v)}" ${ro ? 'disabled' : ''}></dd>`).join('')}</dl>
        <div class="note" style="position:relative;margin-top:8px">提示词覆盖要等引擎 O2<small>现在回合的提示词还在引擎包里</small></div></div></div></div>`;
  b.onpointerdown = b.onpointermove = b.onpointerup = b.ondblclick = null;
  b.onclick = e => {
    const p = e.target.closest('[data-pick]'); if (p) { S.node = p.dataset.pick; renderOrch(); return; }
    if (ro) return;
    const u = e.target.closest('[data-untool]'); if (u) { setTools(id, on.filter(x => x !== u.dataset.untool)); renderOrch(); return; }
    const t = e.target.closest('[data-tool]'); if (t) { setTools(id, [...on, t.dataset.tool]); renderOrch(); }
  };
  if (ro) return;
  b.querySelectorAll('[data-tool]').forEach(t => t.ondragstart = ev => ev.dataTransfer.setData('text/plain', t.dataset.tool));
  const d = $('#drop'); d.ondragover = ev => { ev.preventDefault(); d.classList.add('over'); }; d.ondragleave = () => d.classList.remove('over');
  d.ondrop = ev => { ev.preventDefault(); const k = ev.dataTransfer.getData('text/plain'); if (k && !on.includes(k)) setTools(id, [...on, k]); renderOrch(); };
}
function setTools(id, list) { S.toolsOver[S.graph + ':' + id] = list; }
function drawTools() {
  const b = $('#board'), g = G();
  const used = t => Object.keys(g.nodes).filter(id => nodeTools(id).includes(t));
  b.innerHTML = `<div class="flow"><div class="row" style="align-items:flex-end"><div><div class="tag">registry · ActionSpec</div><h2 class="h1" style="font-size:26px">工具注册表</h2>
    <p class="sub">引擎、玩法包、mixin 各自注册;编排图里的节点只能从这里选。kind 决定它是动作、更新、请求、工具还是进入模式层;同步的工具会让正文停下等结果。</p></div></div>
    <div class="glass deep" style="margin-top:14px;overflow:auto;padding:6px 8px"><table class="t"><tr><th>工具</th><th>kind</th><th>同步</th><th>字段</th><th>校验</th><th>来源</th><th>用在哪些节点</th><th>说明</th></tr>
    ${Object.entries(TOOLS).map(([k, t]) => `<tr><td class="mono"><b>${k}</b></td><td class="mono">${t.kind}</td><td>${t.sync ? '同步' : '<span style="color:var(--blue)">异步</span>'}</td><td class="mono" style="font-size:11.5px">${t.fields || '—'}</td><td class="mono" style="font-size:11.5px">${t.validator || '—'}</td><td><span class="chip ${t.src.startsWith('mixin') ? 'sage' : t.src.startsWith('pack') ? 'blue' : ''}">${t.src}</span></td>
      <td>${used(k).map(id => `<button class="chip" data-pick="${id}">${g.nodes[id].title}</button>`).join(' ') || '<span class="muted">没用到</span>'}</td><td>${esc(t.doc)}</td></tr>`).join('')}
    ${g.raw ? `<tr><td colspan="8" class="muted" style="font-size:12.5px;padding:10px">工具由引擎、玩法包、mixin 在代码里注册${UNREAD}这里还不能新注册:加一行只是画在页面上,回合不会调用</td></tr>` : `<tr><td><input class="btn" id="ntName" placeholder="新工具名" style="width:110px;padding:4px 10px"></td><td><select class="btn" id="ntKind" style="padding:4px 8px">${['action', 'update', 'request', 'tool', 'mode'].map(k => `<option>${k}</option>`).join('')}</select></td>
      <td><label class="mono" style="font-size:12px"><input type="checkbox" id="ntAsync"> 异步</label></td><td colspan="4"><input class="btn" id="ntDoc" placeholder="说明(四语之一)" style="width:100%;padding:4px 10px"></td><td><button class="btn p" id="ntAdd">注册</button></td></tr>`}</table></div></div>`;
  b.onpointerdown = b.onpointermove = b.onpointerup = b.ondblclick = null;
  b.onclick = e => { const p = e.target.closest('[data-pick]'); if (p) { S.node = p.dataset.pick; S.layer = 'node'; renderOrch(); } };
  if ($('#ntAdd')) $('#ntAdd').onclick = () => { const n = $('#ntName').value.trim().replace(/\W+/g, '_'); if (!n || TOOLS[n]) return; TOOLS[n] = { kind: $('#ntKind').value, sync: !$('#ntAsync').checked, fields: '', validator: '', src: 'template', doc: $('#ntDoc').value || '(创作者注册)' }; drawTools(); };
}
/* 对话测试:stub 引擎按编排图走 */
// 私有层的桩回复(PRIVATE_UI.stubs)只给 ?demo=1 的演示图用:引擎读来的图上冒出「d20=15」像真回合(10-17)
const DEMO_UI = /[?&]demo(=|&|$)/.test(location.search);
const STUB = DEMO_UI ? {
  turn: { say: '主持:你走进杂货铺,老苇抬了抬眼。', calls: ['move'] },
  ticks: { say: '后台:时钟 08:30 → 09:10', calls: ['set'] },
  ...(PRIV.stubs || {}),
} : {};
function matchEdge(text, from, auto) {
  const g = G(), out = g.edges.filter(e => e.from === from);
  const hit = e => {
    if (e.on === 'words') return String(e.val || '').split(/\s*·\s*/).filter(Boolean).some(w => text.includes(w));   // 边上写的推进词
    if (e.on === 'dm') return /@(DM|GM|主持)/i.test(text);
    if (e.on === 'judge') return auto && /结束|再见|晚安/.test(text);
    if (e.on === 'gate') return /拔剑|攻击|动手|砍/.test(text);
    if (e.on === 'op') return e.val && text.includes('[' + e.val);
    if (e.on === 'here') return /走进|房间|地穴/.test(text);
    return false;
  };
  return out.find(e => e.on !== 'always' && hit(e)) || (auto ? out.find(e => e.on === 'always') : null);
}
function step(text) {
  const g = G(), log = S.chat;
  log.push({ t: 'me', h: esc(text) });
  let moves = 0, first = true;
  const run = (nodeId, auto) => {
    const n = g.nodes[nodeId], stub = STUB[nodeId] || { say: n.title + (g.raw ? ':(演示占位 · 没跑引擎)' : ':(stub)'), calls: [] };
    const allowed = nodeTools(nodeId);
    const calls = nodeId === 'combat' && text.includes('[end_combat]') ? ['end_combat'] : stub.calls;
    const bad = calls.filter(c => !allowed.includes(c));
    log.push({ t: 'sys', h: `<span class="go">● ${n.title}</span> · 调用 ${calls.length ? calls.map(c => bad.includes(c) ? `<span class="bad">${c}✗</span>` : `<span class="ok">${c}</span>`).join(' ') : '—'}${bad.length ? ` <span class="bad">没注册 → verify 拒绝</span>` : ''}` });
    if (!(nodeId === 'combat' && text.includes('[end_combat]'))) log.push({ t: 'human', h: esc(stub.say) });
  };
  const follow = (e) => {
    S.hit.add(e.id); S.liveEdge = e.id;
    let to = e.to;
    if (to === '@return') { to = S.stack.pop() || g.start; }
    else if (['mode', 'one'].includes(g.nodes[to].kind)) S.stack.push(S.cur !== g.start && g.nodes[S.cur].kind === 'loop' && g.nodes[g.start] ? g.start : S.cur);   // 从另一个主循环进层:回到起点那个
    log.push({ t: 'sys', h: `<span class="go">→ ${e.id}</span> ${e.on === 'always' ? '总是' : TRIG[e.on] + ':' + esc(e.val)} → ${g.nodes[to].title}` });
    S.cur = to;
  };
  // 当前节点先处理这句话,再看出边;自动节点(起点以外的主循环 / 后台 / 一次性)跑完继续走
  let e = matchEdge(text, S.cur, false);
  if (!e) { run(S.cur, false); e = matchEdge(text, S.cur, true); if (e && e.to === e.from) { S.hit.add(e.id); e = null; } }
  while (e && moves < 6) {
    follow(e); moves++;
    const k = g.nodes[S.cur].kind;
    if (k === 'loop' && S.cur !== g.start || k === 'tick' || k === 'one' || (k === 'mode' && text.includes('['))) { run(S.cur, true); e = matchEdge(text, S.cur, true); if (e && e.to === e.from) { S.hit.add(e.id); e = null; } }
    else { run(S.cur, false); e = null; }
  }
  const tot = g.edges.length, cov = S.hit.size;
  log.push({ t: 'sys', h: `<span class="mono" style="color:var(--muted)">停在 ${g.nodes[S.cur].title}${S.stack.length ? ' · 返回栈 ' + S.stack.map(x => g.nodes[x].title).join('›') : ''} · 边覆盖 ${cov}/${tot}</span>` });
}
document.addEventListener('click', e => {
  if (S.screen !== 'orch') return;
  const l = e.target.closest('[data-layer]'); if (l) { S.layer = l.dataset.layer; renderOrch(); return; }
  const s = e.target.closest('[data-os]'); if (s) { step(s.dataset.os); renderOrch(); return; }
  if (e.target.closest('#osend')) { const v = $('#oin').value.trim(); if (v) { step(v); renderOrch(); } return; }
  if (e.target.closest('[data-oreset]')) { resetChat(); renderOrch(); return; }
  if (e.target.closest('[data-orun]')) {
    resetChat(); const script = G().demo || ['看看四周'];
    script.forEach(x => step(x));
    const un = G().edges.filter(x => !S.hit.has(x.id)).map(x => x.id);
    S.chat.push({ t: 'agent', h: `<b>全套脚本跑完</b> · ${script.length} 句 · 边覆盖 ${S.hit.size}/${G().edges.length}${un.length ? ` · 没走到 ${un.join(', ')}` : ' · 每条边都走到了'}<span class="call">检查:状态切换 · 每个节点只调注册给它的工具 · 返回栈弹回正确</span>` });
    renderOrch();
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'oin') { const v = e.target.value.trim(); if (v) { step(v); renderOrch(); $('#oin').focus(); } } });

/* ================================================================ ② 世界 · 角色(一个文件夹的两面)
   世界面:地图图 · 剧情图 · Schema · 数据;角色面:卡片 · 关系图 · Schema · 数据。右栏:创作 agent + 检查器。
   三张图共用一个节点编辑器(拖节点、从圆点拖线建边、点边改条件)。数据页的表单由 Schema 生成。 */
const MAPG = {
  nodes: Object.fromEntries(Object.entries(PLACES).map(([k, p]) => [k, { x: p.x, y: p.y, title: p.name }])),
  edges: [{ id: 'r1', from: 'gate', to: 'street', label: '8 分钟' }, { id: 'r2', from: 'guild', to: 'street', label: '6 分钟' }, { id: 'r3', from: 'shop', to: 'street', label: '10 分钟' },
    { id: 'r4', from: 'inn', to: 'street', label: '6 分钟' }, { id: 'r5', from: 'street', to: 'dock', label: '15 分钟' }],
};
const PLOT = {
  nodes: {
    s0: { x: 44, y: 10, kind: 'stage', title: '序章 · 雾夜醒来', note: 'opening_scene' },
    s1: { x: 44, y: 34, kind: 'stage', title: '第一幕 · 码头的货', note: '可去:码头 · 旅店' },
    s2: { x: 44, y: 58, kind: 'stage', title: '第二幕 · 封蜡', note: '揭示前:真相锁住' },
    E10: { x: 16, y: 86, kind: 'ending', title: 'E10 记忆归来' }, E11: { x: 42, y: 86, kind: 'ending', title: 'E11 雾中的新名字' }, E19: { x: 80, y: 46, kind: 'ending', title: 'E19 倒在雾里' },
  },
  edges: [{ id: 't1', from: 's0', to: 's1', label: 'flag woke' }, { id: 't2', from: 's1', to: 's2', label: 'clue.found ≥ 1' },
    { id: 't3', from: 's2', to: 'E10', label: 'clue ≥ 3 且 trust ≥ 5' }, { id: 't4', from: 's2', to: 'E11', label: 'trust ≥ 5 · clue < 3' }, { id: 't5', from: 's1', to: 'E19', label: 'player.hp ≤ 0' }],
};
const REL = {
  nodes: { player: { x: 50, y: 52, title: '你', img: '' }, elena: { x: 24, y: 28, title: '艾琳娜', img: 'elena.jpg' }, rowan: { x: 76, y: 28, title: '罗文', img: 'rowan.jpg' },
    laowei: { x: 18, y: 66, title: '老苇(NPC)' }, foreman: { x: 76, y: 80, title: '码头工头(NPC)' } },
  edges: [{ id: 'q1', from: 'elena', to: 'player', label: '信任 2' }, { id: 'q2', from: 'rowan', to: 'player', label: '信任 4' }, { id: 'q3', from: 'elena', to: 'rowan', label: '同伴' },
    { id: 'q4', from: 'laowei', to: 'player', label: '熟客' }, { id: 'q5', from: 'foreman', to: 'rowan', label: '敌意' }],
};
const WSCHEMA = {
  location: { folder: 'game/locations', props: [{ k: 'name', t: 'str' }, { k: 'region', t: 'enum', v: '石津镇 · 灰雾北境' }, { k: 'fog', t: 'enum', v: '薄 · 浓 · 夜雾', mut: true }, { k: 'danger', t: 'int', v: '0–5', mut: true }, { k: 'open_at_night', t: 'bool', mut: true }] },
  npc: { folder: 'game/npcs', props: [{ k: 'name', t: 'str' }, { k: 'where', t: 'ref', v: 'location', mut: true }, { k: 'wants', t: 'str' }, { k: 'mood', t: 'enum', v: '平静 · 警惕', mut: true }] },
  item: { folder: 'game/items', props: [{ k: 'name', t: 'str' }, { k: 'price', t: 'int', v: '≥ 0' }, { k: 'effect', t: 'str' }] },
};
const WVARS = [{ k: 'player.gold', t: 'int', v: '≥ 0' }, { k: 'clock.day', t: 'int', v: '≥ 1' }, { k: 'fog.level', t: 'enum', v: '薄 · 浓 · 夜雾' }, { k: 'case.stage', t: 'enum', v: 's0 · s1 · s2' }];
const SSCHEMA = [{ k: 'persona', t: 'open', v: '说话方式 · 底线 · 想要什么' }, { k: 'trust', t: 'int', v: '0–10', mut: true }, { k: 'memory', t: 'list', mut: true }, { k: 'mood', t: 'enum', v: '平静 · 警惕 · 高兴', mut: true }];
const PVAL = { gate: { region: '石津镇', fog: '浓', danger: 1, open_at_night: false }, guild: { region: '石津镇', fog: '薄', danger: 0, open_at_night: true }, shop: { region: '石津镇', fog: '薄', danger: 0, open_at_night: false },
  inn: { region: '石津镇', fog: '薄', danger: 0, open_at_night: true }, street: { region: '石津镇', fog: '浓', danger: 1, open_at_night: true }, dock: { region: '石津镇', fog: '夜雾', danger: 3, open_at_night: true } };
const SVAL = { elena: { persona: '短句,先讲条件再答应;不谈过去', trust: 2, memory: ['北门的雾', '你替她付过药钱'], mood: '平静', affection: 12 }, rowan: { persona: '急,爱夸口,但守信', trust: 4, memory: ['旧地图'], mood: '高兴', affection: 0 } };
S.duoTab = { world: 'map', soul: 'cards' }; S.rtab = 'agent'; S.gsel = null; S.schemaCls = 'location';
S.wagent = [
  { t: 'agent', h: '我按 <span class="mono">documents/spec/world</span> 和 <span class="mono">soul</span> 读了这个文件夹:6 个地点、3 个类、2 个角色、1 条主线 3 个结局。想改什么直接说,我改完会在左边的图里亮出来。<span class="call">read game/** · souls/** · registry/classes.json</span>' },
];
const WTABS = { world: [['map', '地图'], ['plot', '剧情'], ['schema', 'Schema'], ['data', '数据']], soul: [['cards', '卡片'], ['rel', '关系'], ['schema', 'Schema'], ['data', '数据']] };

/* 通用节点编辑器:位置用百分比,随容器缩放 */
/* 画板的平移 / 缩放(10-06:「拖动背景这个 board 不会移动」):
   在空白处按住拖 = 平移 · 触控板双指 / 滚轮 = 平移 · ⌘/Ctrl + 滚轮或双指捏合 = 缩放(以指针为中心)· 双击空白 = 复位。
   host 收事件、画点阵背景;target 是被移动的那一层(节点 / 连线 / 标签)。每块板的视图按 key 记住,重画不丢。 */
const VIEWS = {};
const PZ_SKIP = '[data-gn],[data-gp],[data-ge],[data-mn],[data-me],[data-n],[data-port],[data-e],.mport,.elabel,button,input,select,textarea,a,.tb,.mptb,.mpleg,.ednote,#pop';
function panZoom(host, target, key, grid = true) {
  const v = VIEWS[key] = VIEWS[key] || { x: 0, y: 0, z: 1 };
  const apply = () => {
    target.style.transformOrigin = '0 0'; target.style.transform = `translate(${v.x}px,${v.y}px) scale(${v.z})`;
    if (grid) { host.classList.add('pzgrid'); host.style.backgroundPosition = `${v.x}px ${v.y}px`; host.style.backgroundSize = `${26 * v.z}px ${26 * v.z}px`; }
  };
  apply();
  if (host._pz) { host._pz.v = v; host._pz.apply = apply; host._pz.target = target; return v; }
  const st = host._pz = { v, apply, target, pan: null };
  host.addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest(PZ_SKIP)) return;
    st.pan = { sx: e.clientX, sy: e.clientY, x: st.v.x, y: st.v.y }; host.classList.add('panning');
    try { host.setPointerCapture(e.pointerId); } catch { /* 有些浏览器在合成事件上会拒绝 */ }
  });
  host.addEventListener('pointermove', e => { if (!st.pan) return; st.v.x = st.pan.x + e.clientX - st.pan.sx; st.v.y = st.pan.y + e.clientY - st.pan.sy; st.apply(); });
  const end = () => { st.pan = null; host.classList.remove('panning'); };
  host.addEventListener('pointerup', end); host.addEventListener('pointercancel', end);
  host.addEventListener('wheel', e => {
    if (e.target.closest('.tb,.mptb,#pop,textarea,select')) return;
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const r = st.target.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      const z2 = Math.min(2.5, Math.max(.35, st.v.z * Math.exp(-e.deltaY * (Math.abs(e.deltaY) < 30 ? .01 : .0015)))), k = z2 / st.v.z;
      st.v.x += px * (1 - k); st.v.y += py * (1 - k); st.v.z = z2;
    } else { st.v.x -= e.deltaX; st.v.y -= e.deltaY; }
    st.apply();
  }, { passive: false });
  host.addEventListener('dblclick', e => { if (e.target.closest(PZ_SKIP)) return; st.v.x = st.v.y = 0; st.v.z = 1; st.apply(); });
  return v;
}
const GESTATE = {};
function graphEdit(el, M, o) {
  const draw = () => {
    const W = el.clientWidth, H = el.clientHeight, P = id => [M.nodes[id].x / 100 * W, M.nodes[id].y / 100 * H];
    let wires = '', labels = '';
    M.edges.forEach(e => {
      if (!M.nodes[e.from] || !M.nodes[e.to]) return;
      const [x1, y1] = P(e.from), [x2, y2] = P(e.to), len = Math.hypot(x2 - x1, y2 - y1) || 1, bend = o.bend ? len * o.bend : 0;
      const nx = -(y2 - y1) / len, ny = (x2 - x1) / len, cx = (x1 + x2) / 2 + nx * bend, cy = (y1 + y2) / 2 + ny * bend;
      const mx = (x1 + x2) / 4 + cx / 2, my = (y1 + y2) / 4 + cy / 2;  // 二次曲线 t=.5 处
      const d = bend ? `M${x1},${y1} Q${cx},${cy} ${x2},${y2}` : `M${x1},${y1} L${x2},${y2}`;
      const on = S.gsel && S.gsel.t === 'edge' && S.gsel.id === e.id;
      wires += `<path class="hit" d="${d}" data-ge="${e.id}"/><path class="w ${on ? 'on' : ''} ${e.fresh ? 'live' : ''}" d="${d}" marker-end="url(#gah)"/>`;
      labels += `<div class="elabel ${on ? 'on' : ''}" style="left:${mx}px;top:${my}px" data-ge="${e.id}">${esc(e.label || '—')}</div>`;
    });
    el.innerHTML = (o.bg || '') + `<svg class="wires"><defs><marker id="gah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="rgba(255,255,255,.55)"/></marker></defs>${wires}<path class="ghost" id="gghost" d=""/></svg>${labels}`
      + Object.entries(M.nodes).map(([id, n]) => { const [x, y] = P(id), on = S.gsel && S.gsel.t === 'node' && S.gsel.id === id;
        return `<div class="gn ${on ? 'sel' : ''} ${n.fresh ? 'fresh' : ''}" style="left:${x}px;top:${y}px" data-gn="${id}">${o.node(n, id)}<span class="gp" data-gp="${id}" title="拖到另一个节点 = 连线"></span></div>`; }).join('');
  };
  draw();
  const V = el.parentElement ? panZoom(el.parentElement, el, 'g:' + (el.className || ''), true) : { z: 1 };
  // 拖拽 / 拖线的状态放在函数外(按画布):拖到一半数据回来、整块重画,新的这份接着用 —— 之前存在闭包里,重画就丢了,松手什么都不做
  const st = GESTATE[el.className || 'g'] || (GESTATE[el.className || 'g'] = { drag: null, link: null });
  el.onpointerdown = e => {
    const p = e.target.closest('[data-gp]'); const r = el.getBoundingClientRect();
    if (p) { st.link = { from: p.dataset.gp, x0: (e.clientX - r.left) / V.z, y0: (e.clientY - r.top) / V.z }; e.preventDefault(); return; }
    const n = e.target.closest('[data-gn]'); if (n && !e.target.closest('button')) { try { el.setPointerCapture(e.pointerId); } catch {} e.preventDefault(); } if (n && !e.target.closest('button')) st.drag = { id: n.dataset.gn, sx: e.clientX, sy: e.clientY, x: M.nodes[n.dataset.gn].x, y: M.nodes[n.dataset.gn].y, moved: false };
  };
  el.onpointermove = e => {
    const r = el.getBoundingClientRect();
    if (st.link) { const x = (e.clientX - r.left) / V.z, y = (e.clientY - r.top) / V.z; const g = $('#gghost', el); g && g.setAttribute('d', `M${st.link.x0},${st.link.y0} L${x},${y}`); return; }
    if (!st.drag) return; const dx = e.clientX - st.drag.sx, dy = e.clientY - st.drag.sy; if (Math.abs(dx) + Math.abs(dy) > 3) st.drag.moved = true;
    M.nodes[st.drag.id].x = Math.min(97, Math.max(3, st.drag.x + dx / r.width * 100)); M.nodes[st.drag.id].y = Math.min(95, Math.max(5, st.drag.y + dy / r.height * 100)); draw();
  };
  el.onpointerup = e => {
    if (st.link) { const t = document.elementFromPoint(e.clientX, e.clientY), n = t && t.closest('[data-gn]');
      if (n && n.dataset.gn !== st.link.from) { const id = 'x' + Date.now() % 100000; M.edges.push({ id, from: st.link.from, to: n.dataset.gn, label: o.newLabel || '新连线' }); S.gsel = { t: 'edge', id }; S.rtab = 'insp'; }
      st.link = null; renderDuo(); return; }
    if (st.drag) { const d = st.drag; st.drag = null; if (!d.moved) { S.gsel = { t: 'node', id: d.id }; S.rtab = 'insp'; o.onPick && o.onPick(d.id); renderDuo(); } }
  };
  el.onclick = e => { const g = e.target.closest('[data-ge]'); if (g) { S.gsel = { t: 'edge', id: g.dataset.ge }; S.rtab = 'insp'; renderDuo(); } };
}
const curM = () => S.face === 'world' ? (S.duoTab.world === 'plot' ? PLOT : MAPG) : REL;

function renderDuo() {
  const el = $('#s-duo'), f = S.face, tab = S.duoTab[f];
  const tree = [
    ['d', 'stoneford-elena/'], ['d', '  game/'], ['d', '    locations/'], ...Object.keys(MAPG.nodes).map(k => ['f', `      ${(PLACES[k] ? PLACES[k].data.id.split('/')[1] : k)}.json`, 'world', 'map', k]),
    ['d', '    plots/main/'], ['f', '      plot.json', 'world', 'plot', null], ['d', '    meta/'], ['f', '      vars.json', 'world', 'schema', null],
    ['d', '  souls/'], ...Object.keys(SOULS).flatMap(k => [['d', `    ${k}/`], ['f', '      soul.json', 'soul', 'data', k], ['f', '      persona.json', 'soul', 'data', k]]),
    ['f', '  souls/_schema.json', 'soul', 'schema', null], ['f', '  souls/_relations.json', 'soul', 'rel', null], ['d', '  registry/'], ['f', '    classes.json', 'world', 'schema', null],
  ];
  el.innerHTML = `<div class="duo2 ${f === 'world' && tab === 'map' ? 'wide' : ''}">
    <div class="glass tree"><div class="tag" style="margin-bottom:8px">一个文件夹 · 两面</div>${tree.map(([k, t, fc, tb, id]) => k === 'd' ? `<span class="d" style="white-space:pre">${esc(t)}</span><br>` :
      `<span class="f ${fc === 'soul' ? 'soulf' : 'worldf'} ${fc === f && tb === tab ? 'on' : ''}" style="white-space:pre" data-tf="${fc}:${tb}:${id || ''}">${esc(t)}</span>`).join('')}</div>
    <div class="ed">
      <div class="edhd"><div class="seg">${[['world', '世界面'], ['soul', '角色面']].map(([k, l]) => `<button class="${f === k ? 'on' : ''}" data-face="${k}">${l}</button>`).join('')}</div>
        <div class="tabs sm">${WTABS[f].map(([k, l]) => `<button class="${tab === k ? 'on' : ''}" data-dt="${k}">${l}</button>`).join('')}</div>
        <div class="r">${edActions(f, tab)}${window.WL_newBtn ? window.WL_newBtn(f) : ''}</div></div>
      <div class="edbody ${S.flipping ? 'flipin' : ''}" id="edbody">${edBody(f, tab)}</div></div>
    <div class="glass rside"><div class="rtabs"><div class="seg">${[['agent', '创作 agent'], ['insp', '检查器']].map(([k, l]) => `<button class="${S.rtab === k ? 'on' : ''}" data-rt="${k}">${l}</button>`).join('')}</div></div>
      ${S.rtab === 'agent' ? agentPane() : `<div class="insp">${inspector2()}</div>`}</div></div>`;
  S.flipping = false;
  const me = $('#mapEd'); if (me && window.mapEditor) window.mapEditor(me);
  const g = $('#gcanvas');
  if (g) {
    if (S.face === 'world' && tab === 'map') graphEdit(g, MAPG, { bg: `<img class="mapimg" src="${IMG('map-t001.jpg')}" alt="">`, newLabel: '? 分钟', node: (n, id) => {
      const here = Object.entries(SOULS).filter(([, s]) => s.at === id);
      return `<span class="lb">${esc(n.title)}</span><span class="pin"></span>${here.length ? `<span class="row" style="gap:0;justify-content:center">${here.map(([k, s]) => `<img class="tok" src="${IMG(s.img)}" alt="${s.name}">`).join('')}</span>` : ''}`; } });
    if (S.face === 'world' && tab === 'plot') graphEdit(g, PLOT, { bend: .16, newLabel: '条件?', node: (n, id) => n.kind === 'ending'
      ? brick(`pn end ${(S.endings.find(x => x.id === id) || {}).kind || ''}`, null, `<div class="k">结局 · ${(S.endings.find(x => x.id === id) || { kind: 'alt' }).kind}</div><b>${esc(n.title)}</b><div class="row" style="gap:6px;margin-top:6px">${(S.endings.find(x => x.id === id) || {}).cg ? '<span class="chip sage">CG ✓</span>' : `<button class="chip rust" data-fix="cg:${id}">去生成 CG</button>`}</div>`)
      : brick('pn', null, `<div class="k">阶段</div><b>${esc(n.title)}</b><div class="mono" style="font-size:11px;color:var(--muted);margin-top:4px">${esc(n.note || '')}</div>`) });
    if (S.face === 'soul' && tab === 'rel') graphEdit(g, REL, { bend: .2, newLabel: '关系?', node: (n) => n.img ? `<img class="relp" src="${IMG(n.img)}" alt=""><span class="lb">${esc(n.title)}</span>` : `<span class="relp blank">${esc(n.title.slice(0, 1))}</span><span class="lb">${esc(n.title)}</span>` });
  }
  const c = $('#achat'); if (c) c.scrollTop = c.scrollHeight;
}
function edActions(f, tab) {
  if (tab === 'map') return `<span class="tag">文件夹 = 层级 · 每层一张连通图 · 生成后才有坐标</span>`;
  if (tab === 'plot') return `<button class="btn" data-addn="stage">+ 阶段</button><button class="btn" data-addn="ending">+ 结局</button>`;
  if (tab === 'rel') return `<button class="btn" data-addn="npc">+ 人物</button><span class="tag">连线 = 关系</span>`;
  if (tab === 'schema') return `<span class="tag">改这里 → 数据页的表单跟着变</span>`;
  if (tab === 'cards') return `<button class="btn" data-gen="soul">+ 让 agent 捏一个</button>`;
  return `<span class="tag">表单由 Schema 生成</span>`;
}
function edBody(f, tab) {
  if (tab === 'map') return `<div class="mapEd" id="mapEd"></div>`;
  if (['plot', 'rel'].includes(tab)) return `<div class="gcanvas ${tab}" id="gcanvas"></div>`;
  if (tab === 'cards') return `<div class="souls">${Object.entries(SOULS).map(([k, s]) => brick(`sc hov ${S.pick.t === 'soul' && S.pick.id === k ? 'on' : ''}`, s.img, `<div class="meta"><span><i>${k === 'elena' ? '01' : '02'}</i>souls/${k}</span><span>${SVAL[k].mood}</span></div>
    <div class="cap"><b>${s.name}</b><small class="human" style="font-size:15px">${s.line}</small><div class="hs">${s.haunts.map(h => `<button class="chip" data-goplace="${h}">常去 · ${PLACES[h].name}</button>`).join('')}</div></div>`, `data-soul="${k}"`)).join('')}</div>`;
  if (tab === 'schema') return f === 'world' ? schemaWorld() : schemaSoul();
  return f === 'world' ? dataWorld() : dataSoul();
}
const TYPES = ['str', 'int', 'enum', 'bool', 'list', 'ref', 'open'];
const propRow = (p, i, scope) => `<tr><td><input class="cell mono" value="${esc(p.k)}" data-sp="${scope}:${i}:k"></td><td><select class="cell" data-sp="${scope}:${i}:t">${TYPES.map(t => `<option ${t === p.t ? 'selected' : ''}>${t}</option>`).join('')}</select></td>
  <td><input class="cell" value="${esc(p.v || '')}" placeholder="约束 / 取值" data-sp="${scope}:${i}:v"></td><td style="text-align:center"><input type="checkbox" ${p.mut ? 'checked' : ''} data-sp="${scope}:${i}:mut"></td><td><button class="chip" data-sdel="${scope}:${i}">删</button></td></tr>`;
function schemaWorld() {
  const cls = WSCHEMA[S.schemaCls];
  return `<div class="schw scroll"><div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:12px"><span class="tag">开放 schema 的类</span>${Object.keys(WSCHEMA).map(k => `<button class="chip ${k === S.schemaCls ? 'solid' : ''}" data-scls="${k}">${k}</button>`).join('')}<button class="chip" data-snew>+ 类</button></div>
    <div class="glass deep" style="padding:8px 10px"><div class="row" style="padding:6px 6px 10px"><b style="font-size:17px">${S.schemaCls}</b><span class="mono" style="font-size:12px;color:var(--muted)">${cls.folder}/*.json</span><span class="tag" style="margin-left:auto">mutable = 游玩时能被 patch</span></div>
      <table class="t"><tr><th>属性</th><th>类型</th><th>约束</th><th>可变</th><th></th></tr>${cls.props.map((p, i) => propRow(p, i, 'c')).join('')}</table><button class="btn" data-sadd="c" style="margin:10px 6px 4px">+ 属性</button></div>
    <div class="tag" style="margin:18px 0 8px">世界变量 · 树形存储(game/meta/*.json)</div>
    <div class="glass deep" style="padding:8px 10px"><table class="t"><tr><th>变量</th><th>类型</th><th>约束</th><th>可变</th><th></th></tr>${WVARS.map((p, i) => propRow(p, i, 'v')).join('')}</table><button class="btn" data-sadd="v" style="margin:10px 6px 4px">+ 变量</button></div></div>`;
}
function schemaSoul() {
  return `<div class="schw scroll"><div class="tag" style="margin-bottom:10px">角色 schema · 每个角色按这份来(souls/_schema.json)</div>
    <div class="glass deep" style="padding:8px 10px"><table class="t"><tr><th>字段</th><th>类型</th><th>约束</th><th>可变</th><th></th></tr>${SSCHEMA.map((p, i) => propRow(p, i, 's')).join('')}</table>
    <div class="row" style="margin:10px 6px 4px"><button class="btn" data-sadd="s">+ 字段</button>${SSCHEMA.some(x => x.k === 'affection') ? '' : '<button class="btn" data-fix="affection">+ affection(恋爱陪伴要)</button>'}</div></div>
    <div class="note" style="position:relative;margin-top:16px;transform:rotate(-.6deg)">open = 开放文本,模型读;其余是闭 schema<small>引擎每回合结算 trust / memory / mood,不用预先写满</small></div></div>`;
}
function field(p, val, path) {
  const v = val === undefined ? '' : val;
  if (p.t === 'int') return `<div class="row"><input class="cell mono" type="number" value="${v}" style="width:90px" data-fv="${path}"><input type="range" min="0" max="${/100/.test(p.v || '') ? 100 : 10}" value="${v || 0}" data-fv="${path}" style="flex:1"></div>`;
  if (p.t === 'enum') return `<select class="cell" data-fv="${path}">${String(p.v || '').split(/\s*·\s*/).map(o => `<option ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
  if (p.t === 'bool') return `<button class="tg ${v ? 'on' : ''}" data-fb="${path}" aria-label="${p.k}"></button>`;
  if (p.t === 'list') return `<div class="row" style="flex-wrap:wrap;gap:5px">${(Array.isArray(v) ? v : []).map(x => `<span class="chip">${esc(x)}</span>`).join('')}<button class="chip">+</button></div>`;
  if (p.t === 'open') return `<textarea class="cell human" rows="2" data-fv="${path}">${esc(v)}</textarea>`;
  if (p.t === 'ref') return `<select class="cell">${Object.values(PLACES).map(x => `<option>${x.name}</option>`).join('')}</select>`;
  return `<input class="cell" value="${esc(v)}" data-fv="${path}">`;
}
function dataWorld() {
  const id = S.pick.t === 'place' && MAPG.nodes[S.pick.id] ? S.pick.id : 'gate', cls = WSCHEMA.location, vals = { name: MAPG.nodes[id].title, ...(PVAL[id] || {}) };
  return `<div class="schw scroll"><div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:12px"><span class="tag">location 实例</span>${Object.entries(MAPG.nodes).map(([k, n]) => `<button class="chip ${k === id ? 'solid' : ''}" data-pickp="${k}">${esc(n.title)}</button>`).join('')}</div>
    <div class="dform">${PLACES[id] && PLACES[id].img ? brick('placeimg', PLACES[id].img, '') : brick('placeimg', null, `<div style="position:absolute;inset:0;display:grid;place-items:center"><button class="btn" data-gen="${id}">${S.gen[id] ? '生成中…' : '生成地点图'}</button></div>`)}
      <div class="glass deep" style="padding:16px 18px"><div class="row"><b style="font-size:20px" class="human">${esc(vals.name)}</b><span class="mono" style="font-size:12px;color:var(--muted)">${cls.folder}/${id}.json</span></div>
      <dl class="kv">${cls.props.map(p => `<dt>${p.k} <span style="opacity:.6">${p.t}</span></dt><dd>${field(p, vals[p.k], 'place:' + id + ':' + p.k)}</dd>`).join('')}</dl>
      <div class="tag">这里的人</div><div class="row" style="margin-top:6px">${Object.entries(SOULS).filter(([, s]) => s.at === id).map(([k, s]) => `<button class="chip" data-soul="${k}">${s.name} ↺ 角色面</button>`).join('') || '<span style="color:var(--muted)">没人</span>'}</div></div></div></div>`;
}
function dataSoul() {
  const id = S.pick.t === 'soul' ? S.pick.id : 'elena', s = SOULS[id], vals = SVAL[id];
  return `<div class="schw scroll"><div class="row" style="gap:6px;margin-bottom:12px"><span class="tag">角色</span>${Object.entries(SOULS).map(([k, x]) => `<button class="chip ${k === id ? 'solid' : ''}" data-soul="${k}">${x.name}</button>`).join('')}</div>
    <div class="dform">${brick('placeimg tall', s.img, '')}
      <div class="glass deep" style="padding:16px 18px"><div class="row"><b style="font-size:22px" class="human">${s.name}</b><span class="mono" style="font-size:12px;color:var(--muted)">souls/${id}/persona.json</span></div>
      <div class="say">${s.say}</div>
      <dl class="kv">${SSCHEMA.map(p => `<dt>${p.k} <span style="opacity:.6">${p.t}</span></dt><dd>${field(p, vals[p.k], 'soul:' + id + ':' + p.k)}</dd>`).join('')}<dt>现在在</dt><dd><button class="chip" data-goplace="${s.at}">${PLACES[s.at].name} ↺ 世界面</button></dd></dl>
      <div class="row"><button class="btn" data-gen="${id}">${S.gen[id] ? '生成中…' : '重生一张立绘'}</button></div></div></div></div>`;
}
function inspector2() {
  const M = curM(), sel = S.gsel;
  if (sel && sel.t === 'edge') { const e = M.edges.find(x => x.id === sel.id); if (e) return `<div class="tag">${S.face === 'world' ? (S.duoTab.world === 'plot' ? '触发条件' : '路') : '关系'}</div><h3>${esc((M.nodes[e.from] || {}).title)} → ${esc((M.nodes[e.to] || {}).title)}</h3>
    <label class="tag" style="display:block;margin-top:14px">${S.duoTab.world === 'plot' && S.face === 'world' ? '条件(读变量)' : '标签'}</label><input class="cell" style="width:100%;margin:6px 0 12px" value="${esc(e.label)}" data-elabel="${e.id}">
    ${S.duoTab.world === 'plot' && S.face === 'world' ? '<div class="tag">可用变量</div><div class="row" style="flex-wrap:wrap;gap:5px;margin-top:6px">' + ['clue.found', 'elena.trust', 'player.hp', 'flag.woke', 'clock.day'].map(v => `<span class="chip">${v}</span>`).join('') + '</div>' : ''}
    <div class="row" style="margin-top:16px"><button class="btn" data-edel="${e.id}">删除</button></div>`; }
  if (sel && sel.t === 'node' && M.nodes[sel.id]) { const n = M.nodes[sel.id];
    return `<div class="tag">${S.face === 'world' ? (S.duoTab.world === 'plot' ? (n.kind === 'ending' ? '结局' : '阶段') : '地点') : '人物'}</div><h3>${esc(n.title)}</h3>
      <label class="tag" style="display:block;margin-top:14px">名字</label><input class="cell" style="width:100%;margin:6px 0 12px" value="${esc(n.title)}" data-ntitle="${sel.id}">
      <div class="tag">连着</div><div style="margin-top:6px">${M.edges.filter(e => e.from === sel.id || e.to === sel.id).map(e => `<div class="row" style="padding:4px 0;font-size:13px"><span class="dot"></span>${esc((M.nodes[e.from] || {}).title)} → ${esc((M.nodes[e.to] || {}).title)} <span class="mono" style="color:var(--muted);margin-left:auto">${esc(e.label)}</span></div>`).join('') || '<span style="color:var(--muted)">还没连线</span>'}</div>
      <div class="row" style="margin-top:16px">${S.face === 'world' && S.duoTab.world === 'map' ? `<button class="btn" data-pickp="${sel.id}" data-dt2="data">编辑数据 →</button>` : ''}<button class="btn" data-ndel="${sel.id}">删除</button></div>`; }
  return `<div class="tag">检查器</div><h3>点图里的节点或连线</h3><p class="sub">节点能改名、看它连着谁;连线能改条件 / 路程 / 关系。表格和表单的改动直接写回文件。</p>`;
}
function agentPane() {
  return `<div class="chat" id="achat">${S.wagent.map(m => `<div class="m ${m.t}">${m.h}</div>`).join('')}</div>
    <div class="compose"><div class="in"><input id="ain" placeholder="例如:加一个结局「雾里的约定」" autocomplete="off"><button class="send" id="asend" aria-label="发送">➤</button></div>
    <div class="sugg">${['加一个结局「雾里的约定」', '给角色加好感变量', '加一个地点:灯塔', '让罗文和老苇是旧识'].map(s => `<button class="chip" data-as="${s}">${s}</button>`).join('')}</div></div>`;
}
function agentDo(x) {
  S.wagent.push({ t: 'me', h: esc(x) });
  const clear = M => { Object.values(M.nodes).forEach(n => delete n.fresh); M.edges.forEach(e => delete e.fresh); };
  [MAPG, PLOT, REL].forEach(clear);
  let h, call;
  if (/结局/.test(x)) { const nm = (x.match(/「(.+?)」/) || [, '新的结局'])[1], id = 'E' + (12 + S.endings.length);
    PLOT.nodes[id] = { x: 68, y: 86, kind: 'ending', title: `${id} ${nm}`, fresh: true }; PLOT.edges.push({ id: 't' + Date.now() % 1e5, from: 's2', to: id, label: 'trust ≥ 7 · 没去码头', fresh: true });
    S.endings.push({ id, title: nm, kind: 'alt', cg: false }); S.face = 'world'; S.duoTab.world = 'plot';
    h = `加好了:结局 ${id}「${esc(nm)}」,从第二幕分出来,条件先写成 trust ≥ 7 且没去码头,你可以在图上点那条线改。它还没有 CG,合约会因此多一条 block。`; call = `write game/plots/main/plot.json · endings.${id} · triggers +1`; }
  else if (/路|连/.test(x) && /码头|旅店/.test(x)) { MAPG.edges.push({ id: 'r' + Date.now() % 1e5, from: 'dock', to: 'inn', label: '12 分钟', fresh: true }); S.face = 'world'; S.duoTab.world = 'map';
    h = '北码头 → 河灯旅店,沿河走 12 分钟。主持之后算路程会用它。'; call = 'write game/locations/dock.json · links +inn(12)'; }
  else if (/好感/.test(x)) { if (!SSCHEMA.some(p => p.k === 'affection')) SSCHEMA.push({ k: 'affection', t: 'int', v: '0–100', mut: true }); S.affection = true; S.face = 'soul'; S.duoTab.soul = 'schema';
    h = '角色 schema 加了 affection(0–100,可变)。艾琳娜现在是 12,罗文 0;数据页的表单已经多了一栏。'; call = 'write souls/_schema.json · souls/elena/persona.json · souls/rowan/persona.json'; }
  else if (/地点/.test(x)) { const nm = (x.match(/[::](.+)$/) || [, '新地点'])[1].trim(), id = 'p' + Date.now() % 1e5; MAPG.nodes[id] = { x: 86, y: 70, title: nm, fresh: true }; MAPG.edges.push({ id: 'r' + id, from: id, to: 'dock', label: '20 分钟', fresh: true }); PVAL[id] = { region: '石津镇', fog: '夜雾', danger: 2, open_at_night: true }; S.face = 'world'; S.duoTab.world = 'map';
    h = `新地点「${esc(nm)}」放在码头东边,连到北码头 20 分钟。地点图还没有,数据页能一键生成。`; call = `write game/locations/${id}.json`; }
  else if (/旧识|关系/.test(x)) { REL.edges.push({ id: 'q' + Date.now() % 1e5, from: 'rowan', to: 'laowei', label: '旧识', fresh: true }); S.face = 'soul'; S.duoTab.soul = 'rel';
    h = '罗文 → 老苇:旧识。老苇对罗文讲价会松一点(主持读关系)。'; call = 'write souls/_relations.json'; }
  else { h = '我可以改地图、剧情、schema、角色和关系。说具体一点,比如「给北门加一个夜里关门的规则」。'; call = 'read documents/spec/world · soul'; }
  S.wagent.push({ t: 'agent', h: `${h}<span class="call">${call}</span>` });
  renderDuo();
}
document.addEventListener('click', e => {
  if (S.screen !== 'duo') return;
  const q = sel => e.target.closest(sel);
  let t;
  if ((t = q('[data-face]'))) { S.face = t.dataset.face; S.gsel = null; S.flipping = true; renderDuo(); return; }
  if ((t = q('[data-dt]'))) { S.duoTab[S.face] = t.dataset.dt; S.gsel = null; renderDuo(); return; }
  if ((t = q('[data-rt]'))) { S.rtab = t.dataset.rt; renderDuo(); return; }
  if ((t = q('[data-tf]'))) { const [fc, tb, id] = t.dataset.tf.split(':'); S.face = fc; S.duoTab[fc] = tb; if (id) S.pick = { t: fc === 'soul' ? 'soul' : 'place', id }; renderDuo(); return; }
  if ((t = q('[data-as]'))) { agentDo(t.dataset.as); return; }
  if (q('#asend')) { const v = $('#ain').value.trim(); if (v) agentDo(v); return; }
  if ((t = q('[data-soul]')) && !q('[data-goplace]')) { S.pick = { t: 'soul', id: t.dataset.soul }; if (S.face !== 'soul') { S.face = 'soul'; S.flipping = true; } S.duoTab.soul = S.duoTab.soul === 'cards' && !q('.chip') ? 'cards' : 'data'; renderDuo(); return; }
  if ((t = q('[data-goplace]'))) { S.pick = { t: 'place', id: t.dataset.goplace }; S.face = 'world'; S.duoTab.world = 'data'; S.flipping = true; renderDuo(); return; }
  if ((t = q('[data-pickp]'))) { S.pick = { t: 'place', id: t.dataset.pickp }; if (t.dataset.dt2) S.duoTab.world = 'data'; renderDuo(); return; }
  if ((t = q('[data-scls]'))) { S.schemaCls = t.dataset.scls; renderDuo(); return; }
  if (q('[data-snew]')) { const k = 'class' + Object.keys(WSCHEMA).length; WSCHEMA[k] = { folder: 'game/' + k + 's', props: [{ k: 'name', t: 'str' }] }; S.schemaCls = k; renderDuo(); return; }
  if ((t = q('[data-sadd]'))) { const sc = t.dataset.sadd; (sc === 'c' ? WSCHEMA[S.schemaCls].props : sc === 'v' ? WVARS : SSCHEMA).push({ k: 'new_' + Date.now() % 1000, t: 'str', mut: true }); renderDuo(); return; }
  if ((t = q('[data-sdel]'))) { const [sc, i] = t.dataset.sdel.split(':'); (sc === 'c' ? WSCHEMA[S.schemaCls].props : sc === 'v' ? WVARS : SSCHEMA).splice(+i, 1); renderDuo(); return; }
  if ((t = q('[data-fb]'))) { const [kind, id, k] = t.dataset.fb.split(':'); const box = kind === 'place' ? (PVAL[id] = PVAL[id] || {}) : SVAL[id]; box[k] = !box[k]; renderDuo(); return; }
  if ((t = q('[data-addn]'))) { const k = t.dataset.addn, M = k === 'npc' ? REL : (k === 'place' ? MAPG : PLOT), id = k[0] + Date.now() % 1e5;
    M.nodes[id] = k === 'ending' ? { x: 88, y: 86, kind: 'ending', title: id + ' 新结局', fresh: true } : k === 'stage' ? { x: 44, y: 76, kind: 'stage', title: '新阶段', note: '', fresh: true } : { x: 60, y: 60, title: k === 'npc' ? '新人物' : '新地点', fresh: true };
    if (k === 'ending') S.endings.push({ id, title: '新结局', kind: 'alt', cg: false });
    S.gsel = { t: 'node', id }; S.rtab = 'insp'; renderDuo(); return; }
  if ((t = q('[data-edel]'))) { const M = curM(); M.edges = M.edges.filter(x => x.id !== t.dataset.edel); if (M === MAPG) MAPG.edges = M.edges; if (M === PLOT) PLOT.edges = M.edges; if (M === REL) REL.edges = M.edges; S.gsel = null; renderDuo(); return; }
  if ((t = q('[data-ndel]'))) { const M = curM(), id = t.dataset.ndel; delete M.nodes[id]; M.edges = M.edges.filter(x => x.from !== id && x.to !== id); S.gsel = null; renderDuo(); return; }
  if ((t = q('[data-gen]')) && window.LIVE && window.LIVE.ok) {   // 10-17:接着真引擎时不演「捏好了」—— 捏角色交给创作 agent(edit-local/message),图在 Template 的素材槽生成
    const k = t.dataset.gen;
    if (k === 'soul') agentDo('按 documents/spec/soul 给这个世界新建一个角色:先问我两三个问题(身份、性格、和主角的关系),再写 souls/ 下的文件。');
    else { S.wagent.push({ t: 'agent', h: '图在 Template 页的「素材槽」里生成或上传(会真的写进模板)。这里先不生成。<span class="call">Template → Pack · 素材</span>' }); S.rtab = 'agent'; renderDuo(); }
    return;
  }
  if ((t = q('[data-gen]'))) { const k = t.dataset.gen; S.gen[k] = true; renderDuo(); setTimeout(() => { S.gen[k] = false; if (PLACES[k] && !PLACES[k].img) PLACES[k].img = 'place-inn.jpg'; if (k === 'soul') S.wagent.push({ t: 'agent', h: '按 soul spec 捏了一个草稿:「阿雾」,码头卖鱼的姑娘。还没立绘,确认后我再生成。<span class="call">write souls/awu/soul.json · persona.json</span>' }); if (S.screen === 'duo') renderDuo(); }, 1300); return; }
});
document.addEventListener('input', e => {
  if (S.screen !== 'duo') return;
  const d = e.target.dataset;
  if (d.sp) { const [sc, i, f] = d.sp.split(':'); const arr = sc === 'c' ? WSCHEMA[S.schemaCls].props : sc === 'v' ? WVARS : SSCHEMA; arr[+i][f] = f === 'mut' ? e.target.checked : e.target.value; if (f === 't' || f === 'mut') renderDuo(); }
  if (d.fv) { const [kind, id, k] = d.fv.split(':'); const box = kind === 'place' ? (PVAL[id] = PVAL[id] || {}) : SVAL[id]; box[k] = e.target.type === 'number' || e.target.type === 'range' ? +e.target.value : e.target.value; if (e.target.type === 'range') renderDuo(); }
  if (d.elabel) { const ed = curM().edges.find(x => x.id === d.elabel); if (ed) { ed.label = e.target.value; const l = document.querySelector(`.elabel[data-ge="${d.elabel}"]`); if (l) l.textContent = e.target.value; } }
  if (d.ntitle) { const n = curM().nodes[d.ntitle]; if (n) n.title = e.target.value; }
});
document.addEventListener('change', e => { if (S.screen === 'duo' && e.target.dataset.ntitle) renderDuo(); });
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'ain') { const v = e.target.value.trim(); if (v) agentDo(v); } });
window.addEventListener('resize', () => { if (S.screen === 'duo') renderDuo(); });

/* ================================================================ ③ Template:Pack · 合约 · Lint */
function renderTpl() {
  const el = $('#s-tpl'), b = blocks().length, tab = S.tplTab || 'pack';
  el.innerHTML = `<div class="tplw"><div class="tplhd"><div><div class="tag">stoneford-elena.template</div><h1 class="h1">石津镇 · 艾琳娜与罗文</h1></div>
    <div style="margin-left:auto" class="row"><button class="btn" data-go="test">去测试台跑 →</button></div></div>
    <div class="tabs">${[['pack', 'Pack', '装配'], ['ctr', '合约', C().short], ['lint', 'Lint', b ? b + ' block' : '清零']].map(([k, l, s]) => `<button class="${tab === k ? 'on' : ''}" data-tt="${k}">${l}<small>${s}</small></button>`).join('')}</div>
    <div class="tplbody">${({ pack: tplPack, ctr: tplCtr, lint: tplLint })[tab]()}</div></div>`;
}
function miniGraph() {
  const g = G(), xs = Object.values(g.nodes).map(n => n.x), ys = Object.values(g.nodes).map(n => n.y);
  const mx = Math.min(...xs), my = Math.min(...ys), sw = Math.max(...xs) - mx + 190, sh = Math.max(...ys) - my + 84;
  const p = id => { const n = g.nodes[id]; return [(n.x - mx + 95) / sw * 200, (n.y - my + 42) / sh * 110]; };
  return `<svg class="mini" viewBox="0 0 200 110">${g.edges.filter(e => e.to !== '@return' && e.to !== e.from).map(e => { const [a, b] = p(e.from), [c, d] = p(e.to); return `<line x1="${a}" y1="${b}" x2="${c}" y2="${d}" stroke="rgba(255,255,255,.35)"/>`; }).join('')}
    ${Object.entries(g.nodes).map(([id, n]) => { const [x, y] = p(id); return `<rect x="${x - 22}" y="${y - 9}" width="44" height="18" rx="6" fill="rgba(16,17,27,.9)" stroke="${{ loop: '#de8a63', mode: '#9fc0e8', one: '#9fe0b0', tick: '#ffd27a' }[n.kind]}"/><text x="${x}" y="${y + 3.5}" text-anchor="middle" font-size="8" font-family="Manrope" fill="#f5f3ee">${n.title}</text>`; }).join('')}</svg>`;
}
function tplPack() {
  const tools = packTools();
  return `<div class="bench">
    ${brick('slot', null, `<div class="meta"><span><i>01</i>编排图</span></div><div class="t">${G().title}</div>${miniGraph()}<button class="btn" data-go="orch" style="margin-top:auto">在编排台打开</button>`)}
    ${brick('slot', null, `<div class="meta"><span><i>02</i>工具</span><span>${tools.length}</span></div><div class="t">从注册表选进来的</div><div class="tray">${tools.map(t => `<span class="tool ${TOOLS[t] && !TOOLS[t].sync ? 'async' : ''}">${t}</span>`).join('')}</div>`)}
    ${brick('slot img hov', 'cover-elena.jpg', `<div class="meta" style="position:absolute;top:20px;left:20px;right:20px"><span><i>03</i>世界</span><span>6 地点 · 4 类</span></div><div class="cap"><b style="font-size:26px">石津镇</b><small>builtin stoneford-elena</small></div><button class="btn" data-go="duo" style="align-self:flex-start;margin-top:10px">世界面</button>`)}
    ${brick('slot', null, `<div class="meta"><span><i>04</i>角色</span><span>2</span></div><div class="t">艾琳娜 · 罗文</div><div class="por">${Object.values(SOULS).map(s => brick('', s.img, '')).join('')}</div><button class="btn" data-go="duo" onclick="S.face='soul';S.pick={t:'soul',id:'elena'}" style="margin-top:auto">角色面</button>`)}
    ${brick('slot', null, `<div class="meta"><span><i>05</i>后台单位</span><span>mixins</span></div><div class="t">世界自己在走</div>
      ${[['economy', '经济', '价格 · 库存 · 商队'], ['factions', '势力', '声望 · 劫掠 · 罢工']].map(([k, l, d]) => `<div class="sw"><span><b>${l}</b><br><small style="color:var(--muted)">${d}</small></span><button class="tg ${S.mixins[k] ? 'on' : ''}" data-mx="${k}" aria-label="${l}"></button></div>`).join('')}
      <div class="mono" style="font-size:11.5px;color:var(--muted);margin-top:auto">开了就作为 tick 节点进编排图</div>`)}
  </div>
  <div class="glass deep packjson"><pre class="code"><span class="c">// pack.json — 由上面五格生成</span>
{ <span class="k">"orchestration"</span>: <span class="s">"${S.graph}"</span>, <span class="k">"tools"</span>: [${tools.map(t => `<span class="s">"${t}"</span>`).join(', ')}],
  <span class="k">"world"</span>: { <span class="k">"builtin"</span>: <span class="s">"stoneford-elena"</span> }, <span class="k">"souls"</span>: [<span class="s">"elena"</span>, <span class="s">"rowan"</span>],
  <span class="k">"mixins"</span>: [${Object.keys(S.mixins).filter(k => S.mixins[k]).map(k => `<span class="s">"${k}"</span>`).join(', ')}] }</pre></div>`;
}
function tplCtr() {
  const c = C(), ls = lint(), bad = ls.filter(x => x.lv === 'block');
  const has = code => bad.filter(x => x.code === code);
  const clauses = [
    ['壹', '入口', c.entry, has('contract.entry')],
    ['贰', '出口', c.exit, has('contract.exit')],
    ['叁', '结局', c.endings.min ? `不少于 ${c.endings.min} 个,其中必须有一个真相结局` : '不要求结局', has('contract.endings')],
    ['肆', '奖励', `玩家带走 ${c.rewards.player.join('、')};角色得到 ${c.rewards.soul.join('、')}${c.rewards.world.length ? ';世界记下 ' + c.rewards.world.join('、') : ''}`, has('contract.rewards')],
    ['伍', '固定输出', `一局走到出口时,引擎必须产出:${c.outputs.join('、')}`, []],
    ['陆', '上架', `lint 无 block,并且测试台${c.publish}一次,附试玩凭证`, S.cert ? [] : [{ msg: '还没有试玩凭证' }]],
  ];
  const unmet = clauses.filter(x => x[3].length).length;
  return `<div class="ctrw"><div class="ctrpick"><div class="tag">选一份官方合约</div>${Object.entries(CONTRACTS).map(([k, v]) => brick(`cpk hov ${k === S.ctr ? 'on' : ''}`, null, `<b>${v.title}</b><span>${v.pitch}</span>`, `data-ctr="${k}" role="button" tabindex="0"`)).join('')}
    <div class="note" style="position:relative;transform:rotate(-1deg)">合约只管体验<small>拍怎么跑是编排台的事;同一份合约可以配不同编排</small></div></div>
    <div class="letter"><h2>玩法合约 · ${c.title}</h2><div class="meta2">WORLDLINES.PLAY-CONTRACT/1 · ${S.ctr}@1 · 立约方 stoneford-elena</div>
      ${clauses.map(([no, t, tx, miss]) => `<div class="clause"><div class="no">${no}</div><div class="tx"><b>${t}</b> · ${esc(tx)}${miss.length ? `<small>${miss.map(m => esc(m.msg)).join(' · ')}</small>` : ''}</div><div class="st"><span class="stamp ${miss.length ? 'bad' : 'ok'}">${miss.length ? '未满足' : '满足'}</span></div></div>`).join('')}
      <div class="seal ${unmet ? '' : 'ok'}">${unmet ? `尚欠<br>${unmet} 条` : '合约<br>满足'}</div></div></div>`;
}
function tplLint() {
  const ls = lint(), b = ls.filter(x => x.lv === 'block').length, w = ls.filter(x => x.lv === 'warn').length;
  const where = { orch: '编排台', duo: '世界 · 角色', tpl: 'Template' };
  return `<div class="term glass deep"><div><span class="pr">~/worlds $</span> neonrp template lint stoneford-elena.template --contract ${S.ctr}@1</div><div class="mu">读合约 worldlines/contracts/${S.ctr}.play-contract.json · 读 pack · 读 world · 读 souls</div><br>
    ${ls.map(x => `<div class="ln"><span class="${x.lv === 'block' ? 'bl' : x.lv === 'warn' ? 'wa' : 'okc'}">${x.lv === 'ok' ? 'OK' : x.lv.toUpperCase()}</span><span>${x.code}</span><span>${esc(x.msg)}</span><span>${x.fix ? `<a data-fix="${x.fix}">修</a> ` : ''}${x.go ? `<a data-go="${x.go}">去${where[x.go]}</a>` : ''}</span></div>`).join('')}
    <br><div>${b ? `<span class="bl">✗ ${b} 个 block</span> 会挡住 Hub 上架` : '<span class="okc">✓ 没有 block</span>'} · <span class="wa">${w} 个 warn</span> · <span class="mu">${ls.length} 项检查</span></div>
    <div style="margin-top:12px"><span class="pr">~/worlds $</span> <span style="border-right:8px solid #e9e3d6;animation:none"> </span></div></div>`;
}
document.addEventListener('click', e => {
  if (S.screen !== 'tpl') return;
  const t = e.target.closest('[data-tt]'); if (t) { S.tplTab = t.dataset.tt; renderTpl(); return; }
  const c = e.target.closest('[data-ctr]'); if (c) { S.ctr = c.dataset.ctr; S.cert = false; S.submitted = false; render(); return; }
  const m = e.target.closest('[data-mx]'); if (m) { S.mixins[m.dataset.mx] = !S.mixins[m.dataset.mx]; renderTpl(); }
});

/* ================================================================ ④ 测试台(Mock 3.0) */
const VIEW = {
  classes: {
    caravan: { title: '商队', folder: 'game/caravans', render: '- {id} {name}:{qty}{unit}{good} {from}→{to} {status}(还要 {left} 回合)', props: { status: { type: 'enum' }, qty: { type: 'int', min: 0 }, left: { type: 'int', min: 0, max: 6 } } },
    faction: { title: '势力', folder: 'game/factions', render: '- {id} {name} 势力{power} 立场{stance}', props: { power: { type: 'int', min: 0, max: 100 }, stance: { type: 'enum' } } },
  },
  vars: [['player.gold', '玩家的金'], ['inv.potion', '小治疗药水'], ['price.T001.grain', '石津镇 · 粮价'], ['stock.T001.grain', '石津镇 · 粮库存'], ['elena.trust', '艾琳娜 · 信任'], ['clue.found', '找到的线索'], ['clock.day', '第几天']],
  ticks: [['economy:tick', '经济', '每拍落账后', 'price.* · stock.* · caravan'], ['factions:tick', '势力', '每拍落账后', 'faction · caravan.status'], ['world_clock', '时钟', '按游戏时间', 'clock.*'], ['souls:offscreen', '不在场角色', '每 3 拍', 'souls/*/memo · LLM']],
};
const CV = (id, qty, left, status, from, to) => ({ id, name: '驿路商队', qty, unit: '斗', good: '粮', from, to, status, left });
// 测试台的演示回合(原型 · ?demo=1)。开源版是单拍:你说一句 → 主持叙事 → 落账;我们的两拍版本在私有层
const ROUNDS = PRIV.rounds ? PRIV.rounds(CV) : [
  { label: '开局', clock: '08:30', place: 'gate', vars: { 'player.gold': 18, 'inv.potion': 0, 'clock.day': 1 }, inst: { caravan: [], faction: [] },
    beats: [{ k: 'open', text: '雾从河面漫上主街。艾琳娜在北门边收拾绷带,罗文靠着墙,说他找到一张旧地图。' }], ticks: {}, spans: [], files: [] },
  { label: '买药', clock: '09:10', place: 'shop', vars: { 'player.gold': 8, 'inv.potion': 1 }, inst: { caravan: [], faction: [] },
    beats: [{ k: 'you', text: '去杂货铺买一瓶小治疗药水。' }, { k: 'res', dice: ['说服', 15, 12], text: '你在柜台前和老苇讲价,把价压到了十金。', chg: ['金 18 → 8', '+小治疗药水', '到杂货铺'] }],
    ticks: { world_clock: ['08:30 → 09:10'] },
    spans: [['turn', '掷骰', 'py', 0, 30], ['turn', '叙事', 'llm', 30, 8200], ['turn', '校验 + 落账', 'py', 8200, 8400], ['ticks', '后台', 'tk', 8400, 8460]],
    files: [['M', 'game/player/profile.json'], ['M', 'game/player/inventory.json']] },
];
const STATES = (() => { const o = []; let v = {}, inst = {}; ROUNDS.forEach(r => { v = { ...v, ...r.vars }; inst = { ...inst, ...r.inst }; o.push({ vars: { ...v }, inst: JSON.parse(JSON.stringify(inst)) }); }); return o; })();
const MTABS = [['play', '游玩'], ['orch', '本轮编排'], ['tick', '后台'], ['world', '世界'], ['vars', '变量'], ['files', '文件'], ['wl', '世界线']];
function renderTest() {
  const el = $('#s-test'), r = S.round, R = ROUNDS[r], st = STATES[r], pv = r ? STATES[r - 1] : st, P = PLACES[R.place];
  const outs = C().outputs.map(o => ({ o, ok: S.round === ROUNDS.length - 1 && S.ctr === 'mystery-trpg' && (o !== '解锁的 CG' || S.endings[0].cg) }));
  S.cert = outs.every(x => x.ok);
  const box = (title, sub, rows, keys) => { const ch = keys.some(k => st.vars[k] !== pv.vars[k]) && r; return `<div class="glass box ${ch ? 'flash' : ''}"><span class="tag">${title}</span>${rows}<div class="sub2">订阅 · ${sub}</div></div>`; };
  const vr = (k, l) => { const a = st.vars[k], b = pv.vars[k]; return `<div class="r"><span>${l}</span><span>${a}${r && a !== b ? ` <span class="${a > b ? 'd-up' : 'd-dn'}">${a > b ? '+' : ''}${a - b}</span>` : ''}</span></div>`; };
  el.innerHTML = `<div class="mk">
    <div class="mk-left"><div class="glass gl pad"><span class="tag">当前世界</span><div style="margin-top:10px">${brick('wcard', 'cover-elena.jpg', `<b>石津镇 · 艾琳娜与罗文</b><small>${C().short} · ${G().title}</small>`)}</div></div>
      <div class="glass gl pad"><span class="tag">时间 · 回合</span><div class="clock" style="margin:6px 0 2px">${R.clock}</div><div class="tag" style="text-transform:none;letter-spacing:.04em">第 ${r} 轮 · ${R.label}</div>
        <div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn" data-mnext ${r >= ROUNDS.length - 1 ? 'disabled' : ''}>跑下一轮</button><button class="btn p" data-mexit>跑到出口</button><button class="btn" data-mreset>重开</button></div></div>
      <div class="glass gl pad" style="flex:1;overflow:auto"><span class="tag">出口检查 · 合约的固定输出</span>
        ${outs.map(x => `<div class="row" style="padding:4px 0;font-size:13px"><span class="dot ${S.round === ROUNDS.length - 1 ? (x.ok ? 'ok' : 'bad') : ''}"></span>${x.o}</div>`).join('')}
        ${S.cert ? `<div class="bt set" style="margin-top:10px;font:13px var(--ui)"><div class="who">试玩凭证</div>${S.ctr}@1 · 结局 E10 · 回放包 + 结算产物<br><button class="chip sage" data-go="cat" style="margin-top:6px">去一览提交审查 ↗</button></div>` : S.ctr !== 'mystery-trpg' ? '<div class="sub" style="font-size:12px;margin-top:8px">这条测试数据是解谜跑团的结局;换了合约要重新跑</div>' : ''}</div></div>
    <div class="glass gl mk-mid"><div class="mtabs">${MTABS.map(([k, l]) => `<button class="${S.mtab === k ? 'on' : ''}" data-mt="${k}">${l}</button>`).join('')}
      <span class="r">${S.mtab !== 'play' ? `<div class="seg"><button class="${S.mout === 'html' ? 'on' : ''}" data-mo="html">HTML</button><button class="${S.mout === 'tui' ? 'on' : ''}" data-mo="tui">TUI 文字</button></div>` : '<span class="tag">灰雾北境 › 石津镇 › ' + P.name + '</span>'}</span></div>
      ${S.mtab === 'play' ? `<div class="feed" id="mfeed">${ROUNDS.slice(0, r + 1).flatMap(x => x.beats).concat(S.extra).map(beatHtml).join('')}</div>
        <div class="mcomp"><div class="in"><input id="min" placeholder="${esc(BEATS.placeholder)}" autocomplete="off"><button class="send" id="msend" aria-label="发送">➤</button></div>
        <div class="sugg">${['定', '@主持', '@艾琳娜', '@罗文'].map(s => `<button class="chip" data-ms="${s}">${s}</button>`).join('')}</div></div>` : `<div class="auto">${autoTab(r)}</div>`}</div>
    <div class="mk-right">${brick('loc', P.img || 'map-t001.jpg', `<b>${P.name}</b><small>石津镇 · ${P.data.id}</small>`)}
      ${box('位置 · 时间', 'location · time.*', `<div class="r"><span>location</span><span>${P.data.id}</span></div><div class="r"><span>time</span><span>${R.clock}</span></div>`, ['clock.day'])}
      ${box('玩家', 'player.* · inv.*', vr('player.gold', '金') + vr('inv.potion', '小治疗药水'), ['player.gold', 'inv.potion'])}
      ${box('线索', 'clue.*', vr('clue.found', '找到的线索') + '<div class="r"><span>图鉴</span><span>' + st.vars['clue.found'] + ' / 6</span></div>', ['clue.found'])}
      ${box('市场 · 石津镇', 'price.T001.* · stock.T001.*', vr('price.T001.grain', '粮价') + vr('stock.T001.grain', '粮库存'), ['price.T001.grain', 'stock.T001.grain'])}
      <div class="glass box"><span class="tag">主角团</span>${Object.entries(SOULS).map(([k, s]) => `<div class="cast"><img src="${IMG(s.img)}" alt=""><div><b class="human">${s.name}</b><small>${k === 'elena' ? '信任 ' + st.vars['elena.trust'] + ' / 10' : s.line}</small></div></div>`).join('')}</div>
      <div class="glass box"><span class="tag">最近的世界变化 · 后台</span>${Object.entries(R.ticks).flatMap(([u, l]) => l.map(x => `<div class="r" style="font-size:12.5px"><span>${esc(x)}</span><span class="tag" style="text-transform:none">${u.split(':')[0]}</span></div>`)).join('') || '<div class="sub" style="font-size:12.5px">还没有变化</div>'}</div></div></div>`;
  const f = $('#mfeed'); if (f) f.scrollTop = f.scrollHeight;
}
function beatHtml(b) {
  if (b.k === 'open') return `<div class="bt open">${esc(b.text)}</div>`;
  if (b.k === 'you') return `<div class="bt you"><div class="who">你</div>${esc(b.text)}</div>`;
  if (b.k === 'host') return `<div class="bt host"><div class="who">${esc(BEATS.host({ kind: 'host', beat: 'plan' }))}</div>${esc(b.text)}</div>`;
  if (b.k === 'mic') return `<div class="bt mic">递话筒给 <b>${b.to}</b></div>`;
  if (b.k === 'soul') { const s = SOULS[b.who]; return `<div class="bt soul"><img src="${IMG(s.img)}" alt=""><div><div class="who">${s.name}</div>${esc(b.text)}<span class="int">打算:${b.int}</span></div></div>`; }
  const dice = b.dice ? `<div class="dice">${b.dice[0]} <b>${b.dice[1]}</b> / ${b.dice[2]} ${b.dice[1] >= b.dice[2] ? '成功' : '失败'}</div>` : '';
  return brick(`bt ${b.k} sm`, null, `<div class="who">${b.k === 'set' ? '结算 · 出口' : esc(BEATS.narrWho({ kind: 'resolve' }))}</div>${dice}<div>${esc(b.text)}</div><div class="chgs">${(b.chg || []).map(c => `<span class="chip ${b.k === 'set' ? 'sage' : 'rust'}">${esc(c)}</span>`).join('')}</div>`);
}
const fill = (t, o) => t.replace(/\{(\w+)\}/g, (_, k) => o[k] ?? '');
function cell(spec, v, p) {
  const ch = p !== undefined && p !== v; let h = esc(v);
  if (spec && spec.type === 'enum') h = `<span class="chip ${/被劫|敌对/.test(v) ? 'rust' : /友好|到货/.test(v) ? 'sage' : ''}">${esc(v)}</span>`;
  else if (spec && spec.type === 'int' && spec.max !== undefined) h = `${v}<span class="bar"><i style="width:${Math.round(100 * v / spec.max)}%"></i></span>`;
  if (ch && typeof v === 'number') h += ` <span class="${v > p ? 'd-up' : 'd-dn'}">${v > p ? '+' : ''}${v - p}</span>`; else if (ch) h += ` <span class="tag" style="text-transform:none">← ${esc(p)}</span>`;
  return { h, ch };
}
function spark(vals) { const w = 110, h = 24, mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1; const pts = vals.map((v, i) => `${(i * (w - 6) / Math.max(1, vals.length - 1) + 3).toFixed(1)},${(h - 3 - (v - mn) * (h - 6) / rg).toFixed(1)}`); const l = pts[pts.length - 1].split(',');
  return `<svg width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts.join(' ')}" fill="none" stroke="var(--amber)" stroke-width="1.5"/><circle cx="${l[0]}" cy="${l[1]}" r="2.5" fill="var(--amber)"/></svg>`; }
function autoTab(r) {
  const R = ROUNDS[r], st = STATES[r], pv = r ? STATES[r - 1] : null, tui = S.mout === 'tui';
  const src = { orch: 'trace spans + 编排图', tick: 'mixin ticks + 改动归属 by=tick:*', world: 'registry 类(props 类型 · render 行模板)+ 实例文件', vars: 'VARIABLES + 每轮提交', files: '文件系统 + 本轮 diff', wl: 'commit store' }[S.mtab];
  const foot = `<div class="sub" style="font-size:12px;margin-top:12px">自动生成 · 来源:${src} · 没有手写组件</div>`;
  if (!r && ['orch', 'tick', 'files'].includes(S.mtab)) return `<div class="sub">开局还没跑过 · 点左边「跑下一轮」</div>`;
  if (S.mtab === 'world') return Object.entries(VIEW.classes).map(([cid, c]) => {
    const rows = st.inst[cid] || [], prow = pv ? pv.inst[cid] || [] : [];
    if (tui) return `<div class="tui" style="margin-bottom:10px"><b># ${c.title}</b> <em>${c.folder}</em>\n${rows.map(o => { const p = prow.find(x => x.id === o.id), l = esc(fill(c.render, o)); return !p ? `<u>${l}  [新]</u>` : JSON.stringify(p) !== JSON.stringify(o) ? `<u>${l}  [变]</u>` : l; }).join('\n') || '<em>(无)</em>'}</div>`;
    const cols = ['id', 'name', ...Object.keys(c.props), ...[...new Set((c.render.match(/\{(\w+)\}/g) || []).map(x => x.slice(1, -1)))].filter(k => !['id', 'name'].includes(k) && !(k in c.props))];
    return `<div style="margin-bottom:16px"><div class="tag">${c.title} · ${c.folder} · ${rows.length} 个</div><table class="t">${'<tr>' + cols.map(k => `<th>${k}</th>`).join('') + '</tr>'}${rows.map(o => { const p = prow.find(x => x.id === o.id); return `<tr class="${!p && r ? 'hl' : ''}">${cols.map(k => { const x = cell(c.props[k], o[k], p ? p[k] : undefined); return `<td class="${x.ch ? 'hl' : ''}">${x.h}</td>`; }).join('')}</tr>`; }).join('') || `<tr><td colspan="${cols.length}" class="sub">(无)</td></tr>`}</table><div class="tag" style="text-transform:none;letter-spacing:0;margin-top:4px">行模板 ${esc(c.render)}</div></div>`;
  }).join('') + foot;
  if (S.mtab === 'vars') return (tui ? `<div class="tui">${VIEW.vars.map(([k, d]) => { const a = st.vars[k], b = pv ? pv.vars[k] : a; return `${k.padEnd(18)} ${String(a).padStart(4)}${a !== b ? `  <u>${a > b ? '+' : ''}${a - b}</u>` : '    '}  <em>${d}</em>`; }).join('\n')}</div>`
    : `<table class="t"><tr><th>变量</th><th>值</th><th>走势</th><th>说明</th></tr>${VIEW.vars.map(([k, d]) => { const x = cell({ type: 'int' }, st.vars[k], pv ? pv.vars[k] : undefined); return `<tr class="${x.ch ? 'hl' : ''}"><td class="mono">${k}</td><td class="mono">${x.h}</td><td>${spark(STATES.slice(0, r + 1).map(s => s.vars[k]))}</td><td>${d}</td></tr>`; }).join('')}</table>`) + foot;
  if (S.mtab === 'tick') return (tui ? `<div class="tui">${VIEW.ticks.map(([id, , when, w]) => { const c = R.ticks[id]; return `<b>[${c ? '✓' : ' '}] ${id.padEnd(16)}</b> <em>${when} · 写 ${w}</em>${c ? '\n' + c.map(x => '      ' + esc(x)).join('\n') : ''}`; }).join('\n')}</div>`
    : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px">${VIEW.ticks.map(([id, t, when, w]) => { const c = R.ticks[id]; return `<div class="glass gl pad" style="${c ? '' : 'opacity:.45'}"><div class="row"><b>${t}</b><span class="chip ${c ? 'sage' : ''}" style="margin-left:auto">${c ? '本轮跑了' : '没触发'}</span></div><div class="tag" style="text-transform:none;letter-spacing:.02em;margin:4px 0">${id} · ${when}</div><div class="mono" style="font-size:11.5px;color:var(--dmute)">写 ${w}</div>${c ? c.map(x => `<div style="font-size:13px;padding-top:4px">· ${esc(x)}</div>`).join('') : ''}</div>`; }).join('')}</div>`) + foot;
  if (S.mtab === 'orch') { const tot = Math.max(...R.spans.map(x => x[4])); const nm = new Proxy({ ticks: '后台单位' }, { get: (o, k) => o[k] || BEATS.label(k) });
    return (tui ? `<div class="tui"><b>路径</b>  ${[...new Set(R.spans.map(x => x[0]))].map(x => nm[x]).join(' → ')}\n\n${R.spans.map(([ph, a, be, t0, t1]) => `${nm[ph].padEnd(6)} ${a.padEnd(12)} ${String(((t1 - t0) / 1000).toFixed(1)).padStart(5)} s  ${'█'.repeat(Math.max(1, Math.round((t1 - t0) / tot * 36)))}`).join('\n')}</div>`
    : `<div class="row" style="margin-bottom:12px">${[...new Set(R.spans.map(x => x[0]))].map((x, i) => `${i ? '<span class="tag">→</span>' : ''}<span class="chip ${x === 'ticks' ? 'sage' : 'rust'}">${nm[x]}</span>`).join('')}<span class="tag" style="margin-left:auto">共 ${(tot / 1000).toFixed(1)} s</span></div>
      <table class="t">${R.spans.map(([ph, a, be, t0, t1]) => `<tr><td>${nm[ph]}</td><td>${a}</td><td><span class="chip ${be === 'llm' ? 'rust' : ''}">${be === 'llm' ? 'LLM' : be === 'tk' ? 'tick' : 'python'}</span></td><td style="width:42%"><div class="spanbar"><i class="${be === 'py' ? 'py' : be === 'tk' ? 'tk' : ''}" style="left:${t0 / tot * 100}%;width:${Math.max(.8, (t1 - t0) / tot * 100)}%"></i></div></td><td class="mono">${((t1 - t0) / 1000).toFixed(1)} s</td></tr>`).join('')}</table>`) + foot; }
  if (S.mtab === 'files') return (tui ? `<div class="tui">${R.files.map(([m, p]) => `${m === 'A' ? '<u>A</u>' : 'M'} ${p}`).join('\n')}</div>`
    : `<table class="t">${R.files.map(([m, p]) => `<tr><td style="width:40px"><span class="chip ${m === 'A' ? 'sage' : 'rust'}">${m}</span></td><td class="mono">${p}</td><td class="sub" style="font-size:12px">${p.startsWith('souls') ? '角色面板' : p.includes('caravans') ? '商队表格' : p.includes('settlement') ? '结算产物' : '键值面板'}(按路径形状渲染)</td></tr>`).join('')}</table>`) + foot;
  if (S.mtab === 'wl') return (tui ? `<div class="tui">${ROUNDS.slice(0, r + 1).map((x, i) => `${i === r ? '<b>*</b>' : '|'} c${i}  ${x.label}`).reverse().join('\n')}</div>`
    : ROUNDS.slice(0, r + 1).map((x, i) => `<button class="glass gl pad" style="display:block;width:100%;text-align:left;margin-bottom:8px;${i === r ? 'border-color:var(--lime)' : ''}" data-mr="${i}"><b>c${i} · ${x.label}</b> <span class="tag" style="text-transform:none">${x.clock} · ${x.files.length} 个文件 · ${Object.keys(x.ticks).length} 个后台单位</span></button>`).reverse().join('') + '<div class="sub" style="font-size:12px">点一个提交 = 回到那一轮看所有 Tab(回放就是这样做的)</div>') + foot;
  return '';
}
document.addEventListener('click', e => {
  if (S.screen !== 'test') return;
  const t = e.target.closest('[data-mt]'); if (t) { S.mtab = t.dataset.mt; renderTest(); return; }
  const o = e.target.closest('[data-mo]'); if (o) { S.mout = o.dataset.mo; renderTest(); return; }
  const rr = e.target.closest('[data-mr]'); if (rr) { S.round = +rr.dataset.mr; renderTest(); return; }
  if (e.target.closest('[data-mnext]')) { S.round = Math.min(ROUNDS.length - 1, S.round + 1); S.extra = []; render(); return; }
  if (e.target.closest('[data-mexit]')) { S.round = ROUNDS.length - 1; S.extra = []; render(); return; }
  if (e.target.closest('[data-mreset]')) { S.round = 0; S.extra = []; render(); return; }
  const s = e.target.closest('[data-ms]'); if (s) { testSay(s.dataset.ms); return; }
  if (e.target.closest('#msend')) { const v = $('#min').value.trim(); if (v) testSay(v); }
});
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'min') { const v = e.target.value.trim(); if (v) testSay(v); } });
function testSay(v) {
  if (/^(定|@(DM|GM|主持))$/i.test(v) && S.round < ROUNDS.length - 1) { S.round++; S.extra = []; render(); return; }
  const m = v.match(/^@(艾琳娜|罗文)/);
  S.extra.push({ k: 'you', text: v });
  if (m) { S.extra.push({ k: 'mic', to: m[1] }); const k = m[1] === '艾琳娜' ? 'elena' : 'rowan'; S.extra.push({ k: 'soul', who: k, text: k === 'elena' ? '「你先说清楚要我做什么,我再答应。」' : '「交给我!不过先说好,打起来我冲前面。」', int: k === 'elena' ? '先问条件' : '想打头阵' }); }
  else S.extra.push({ k: 'host', text: '记下了。要做的话说「定」,或者 @ 一个人先听听她的意见。' });
  renderTest(); setTimeout(() => $('#min') && $('#min').focus(), 0);
}

/* ================================================================ ⑤ 前端:见 frontends.js(10-17 做实:真前端文件夹 · 真预览 · 前端 agent)
   这里只留两个名字:fe.js / stdfe.js 在 frontends.js 之前加载,它们包的是这两个函数。 */
function renderFe() { $('#s-fe').innerHTML = ''; }
function feEvents() { return ''; }

render();
