// ═══════════════════════════════════════════════════════════════════
// 真引擎版 E —— Mock 3.0 的页面(pages.js / link.js / app.js)原样运行在这上面。
//   Mock 的 engine.js 是浏览器里的模拟;这里同一套接口(E.s / E.say / E.tick / E.where / E.G …),
//   状态全部来自 neonrp(地图树 · schema · 账本 · 回合 trace · 世界线 · 审批 · 模板),动作全部是引擎调用。
//   不在前端做任何规则判断:verify / apply / tick / 分岔都在引擎里。
// ═══════════════════════════════════════════════════════════════════
const V3 = (() => {
  const q = new URLSearchParams(location.search);
  let BASE = ''; // '' = 本地引擎同源;'/api/v1/play/engine' = Hub(经路由到账户引擎)
  const j = async (path, opt) => {
    const r = await fetch(BASE + path, { credentials: 'include', ...(opt || {}) });
    if (!r.ok) throw Object.assign(new Error(`${r.status} ${path}`), { status: r.status });
    return r.json();
  };
  const post = (path, body) => j(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  const url = path => BASE + path;

  // 10-17:本机引擎正忙时 /meta 偶尔连不上(ERR_SOCKET_NOT_CONNECTED),以前一次失败就当成浏览器版引擎,
  // 之后所有请求都走 /api/v1/play/engine/... 全 404 →「连不上引擎」。连不上就再试几次;答了但不是本机引擎才走浏览器版
  async function detectBase() {
    for (const wait of [0, 400, 1200, 2500]) {
      if (wait) await new Promise(r => setTimeout(r, wait));
      try {
        const r = await fetch('/api/v1/meta', { credentials: 'include' });
        if (!r.ok) break;
        return (await r.json().catch(() => ({}))).implementation === 'local-engine' ? '' : '/api/v1/play/engine';
      } catch { /* the socket did not connect: the engine may just be busy */ }
    }
    return '/api/v1/play/engine';
  }

  // 绑定一局:?save=<run> 续玩 · ?tpl=<模板 id> 新开 · ?world=<世界 id> 新开 · 都没有 = 接着当前那局(没有就开第一个模板)
  async function bind() {
    const slug = q.get('save') || (q.get('tpl') ? `tpl--${q.get('tpl')}` : q.get('world') || '');
    // 本局输出语:开局时引擎按它发「开始游戏」并写进 run_state(不传会落到引擎默认语言)
    const lang = (() => { const v = q.get('lang') || (() => { try { return localStorage.getItem('wl-local-lang'); } catch { return ''; } })() || 'zh'; return /^(zh|en|ja|ko)/i.test(v) ? v.slice(0, 2).toLowerCase() : 'zh'; })();
    // 新开一个模板:模板声明了 player.builder 就先出捏人屏(src/builder.js),捏完带着角色开局;没声明照旧
    if (q.get('tpl') && !q.get('save') && window.BUILDER) return window.BUILDER.start(q.get('tpl'), lang);
    if (slug) return post('/api/v1/play/session', { slug, output_lang: lang });
    try { await j('/api/v1/play/engine/template'); await j('/traces'); return null; } catch { /* nothing bound */ }
    const ts = await j('/api/v1/local/templates').catch(() => ({ templates: [] }));
    const first = (ts.templates || []).find(t => t.publishable) || (ts.templates || [])[0];
    if (!first) throw new Error('没有可开局的模板');
    return window.BUILDER ? window.BUILDER.start(first.id, 'zh') : post('/api/v1/play/session', { slug: `tpl--${first.id}`, output_lang: 'zh' });
  }

  const names = {};
  const townName = t => names[t] || t;
  const placeImg = {}; // addr → IMG key
  // IMG:Mock 用 key 取 base64;真引擎给 URL(层级图 · 场景图 · 立绘 / sprite · 封面)
  const IMG = new Proxy({}, {
    get(_, k) {
      k = String(k);
      if (k.startsWith('map_')) return url(`/api/v1/play/map/image?level=${encodeURIComponent(k.slice(4))}`);
      if (k.startsWith('scene:')) return url(`/api/v1/play/place-image?addr=${encodeURIComponent(k.slice(6))}`);
      if (k === 'av_player') return url('/api/v1/play/portrait?id=player');
      if (k.startsWith('av_')) return url(`/api/v1/play/portrait?id=${encodeURIComponent(k.slice(3))}`);
      if (k.startsWith('sp_')) return url(`/api/v1/play/sprite?id=${encodeURIComponent(k.slice(3))}`);
      if (k === 'cover') return V3.cover || url('/api/v1/play/map/image?level=world');
      if (k.startsWith('slot:') && V3.LINK && V3.LINK.tid) return url(`/api/v1/local/templates/${encodeURIComponent(V3.LINK.tid)}/assets/file?slot=${encodeURIComponent(k.slice(5))}&v=${V3.LINK.stamp || 0}`);
      return '';
    },
  });

  // 「① 自由行动 / ② 和守门人说话」→ 选项;正文里去掉这一行
  const OPT = /[①②③④⑤⑥⑦⑧⑨]\s*([^①②③④⑤⑥⑦⑧⑨/\n]+)/g;
  // 选项行前的「你:」(「……不肯多说。你:① …」)和选项一起拿掉,不留一个孤零零的「你」
  function splitOptions(text) {
    const lines = String(text || '').split('\n'); const options = []; const keep = [];
    for (const l of lines) {
      const hits = [...l.matchAll(OPT)].map(m => m[1].trim().replace(/[。.;;,,]+$/, '')).filter(Boolean);
      if (hits.length >= 2) { const at = l.search(/[①②③④⑤⑥⑦⑧⑨]/); const pre = l.slice(0, at).replace(/[\s/|·、::]+$/, '').replace(/(^|[。！？!?…」』\s])你$/, '$1').trim(); if (pre) keep.push(pre); options.push(...hits); } else keep.push(l);
    }
    return { text: keep.join('\n').replace(/\n+$/, ''), options };
  }
  // 「旅人 CHA 1d20+0 = 12 ≥ 8? → 成功(为了什么)」/ 叙事开头的「[旅人 CHA(为了什么): 12+0=12 >= 8] → 成功」
  const DICE_LINE = /^\[[^\]]+:\s*[^\]]*\]\s*→\s*\S+/;
  function parseRoll(line) {
    const L = String(line || '');
    const res = (/→\s*([^\s((]+)/.exec(L) || [])[1] || '';
    const why = (/[((]([^))]*)[))]\s*$/.exec(L) || [])[1] || '';
    const head = L.split('→')[0];
    const vs = /\s(?:vs|对)\s/.test(head);
    const total = (/=\s*(-?\d+)/.exec(head) || [])[1];
    const cm = /(≥|>=|≤|<=)\s*(\d+)/.exec(head), dc = cm ? cm[2] : undefined;   // d20 用 ≥ 难度,百分骰用 ≤ 技能值
    const sides = +((/\bd(\d+)/i.exec(head) || [])[1] || 0);
    const skill = (head.replace(/^\[/, '').split(':')[0].trim().split(/\s+/).slice(1).join(' ')) || '';
    const who = head.trim().replace(/^\[/, '').split(/[\s((]+/)[0] || '';
    const attr = (/\b(STR|DEX|INT|VIT|CHA|WIS|CON)\b/.exec(head) || [])[1] || '';
    const level = /大成功|大失败|极难成功|困难成功|成功|失败/.exec(res) ? /大成功|大失败|极难成功|困难成功|成功|失败/.exec(res)[0] : '';
    return { raw: L, who, attr, skill, sides, under: !!(cm && /≤|<=/.test(cm[1])), total: total != null ? +total : null, dc: dc != null ? +dc : null, vs, ok: /成功/.test(res) && !/失败/.test(res), res, level, why };
  }

  return { q, j, post, url, detectBase, bind, IMG, splitOptions, parseRoll, DICE_LINE, names, townName, placeImg, setBase: b => (BASE = b), get base() { return BASE; },
    MAPIMG: {}, SCENE: {}, TOWNS: [], TCOL: {}, LEADS: {}, MODES: {}, cover: '', template: null };
})();

const E = (() => {
  let st = null;
  const subs = [];
  const notify = () => subs.forEach(f => { try { f(st); } catch (e) { console.error(e); } });
  const EXTS = [];
  const G = { list: [], by: {}, heads: {}, n: 0, lastEv: 0 };
  const traceCache = new Map();
  const local = { feed: [], sys: [] }; // 前端自己的提示行(「真引擎思考中」),不进引擎
  let busy = false;

  const clock = () => `${String(Math.floor(st.min / 60) % 24).padStart(2, '0')}:${String(st.min % 60).padStart(2, '0')}`;
  const toMin = c => { const m = /^(\d{1,2}):(\d{2})/.exec(String(c || '')); return m ? +m[1] * 60 + +m[2] : 8 * 60; };
  const townOf = a => (a && a.includes('/') ? a.split('/')[0] : a);
  const levelOf = a => (st.nodes[a]?.parent) || 'world';
  const adj = a => Object.values(st.edges).filter(e => e.from === a || e.to === a).map(e => ({ e, other: e.from === a ? e.to : e.from }));
  function path(a, b) {
    const prev = { [a]: null }, qq = [a];
    while (qq.length) { const c = qq.shift(); if (c === b) break; for (const { other } of adj(c)) if (!(other in prev)) { prev[other] = c; qq.push(other); } }
    if (!(b in prev)) return null; const p = [b]; while (prev[p[0]]) p.unshift(prev[p[0]]); return p;
  }
  const where = who => st.pos[who] || { at: null };
  const coLocated = (a, b) => { const p = where(a), q = where(b); if (p.at && q.at) return p.at === q.at; if (p.edge && q.edge) return p.edge === q.edge && Math.abs(p.t - q.t) < 0.12; return false; };
  const worldPos = who => {
    const p = where(who); const hs = n => st.nodes[n]?.pos;
    if (p.edge) { const e = st.edges[p.edge]; const a = hs(e?.from), b = hs(e?.to); return a && b ? [a[0] + (b[0] - a[0]) * p.t, a[1] + (b[1] - a[1]) * p.t] : null; }
    const t = townOf(p.at); return hs(t) || hs(p.at);
  };
  const GATE = {};

  // 「在路上」:引擎把拦停的队伍放在 road_<from>_<to>;Mock 用 {edge, t}
  function posOf(addr, progress = 0.5) {
    if (!addr) return { at: null };
    if (st.nodes[addr]) return { at: addr };
    const m = /^road_([^_]+)_([^_]+)$/.exec(addr.split('/').pop());
    if (m) { const e = Object.values(st.edges).find(x => (x.from === m[1] && x.to === m[2]) || (x.from === m[2] && x.to === m[1])); if (e) return { edge: e.id, t: e.from === m[1] ? progress : 1 - progress, dir: 1 }; }
    const hit = Object.keys(st.nodes).find(k => k.endsWith('/' + addr));
    return { at: hit || null };
  }

  // ── 从引擎装一份 Mock 形状的状态 ──────────────────────────────────
  // 这一局的拍怎么显示(玩法包的 ui.beats):每次开局 / 换局取一次;旧引擎没有这个接口 → 用构建时的样子
  async function loadBeatKinds() {
    const d = await V3.j('/api/v1/play/engine/beat-kinds').catch(() => null);
    if (window.BEATS && window.BEATS.fromSpec) window.BEATS.fromSpec(d);
  }
  // 测试台读引擎的完整记录(debug 读,只有本机开发版 / bench.html 有;没有就退回玩家视角的读,10-15 core/play_view)
  const DBG = '/api/v1/play/engine/debug';
  const full = (dbgPath, playPath) => V3.j(DBG + dbgPath).catch(() => V3.j(playPath));
  async function load() {
    loadBeatKinds();
    const [map, schema, commits, appr, views, runv, trs, evs, eco, fac] = await Promise.all([
      V3.j('/api/v1/play/map'), full('/schema', '/api/v1/play/schema'), V3.j('/api/v1/play/engine/commits').catch(() => null),
      V3.j('/api/v1/play/engine/approvals').catch(() => ({ pending: [], policies: {} })), V3.j('/api/v1/play/engine/views').catch(() => ({ views: [], panels: [] })),
      V3.j('/api/v1/play/engine/template').catch(() => ({ template: null })), V3.j('/traces').catch(() => ({ turns: [] })),
      V3.j('/api/v1/play/schema/events?limit=3000').catch(() => []),
      V3.j('/api/v1/play/engine/world-data?name=economy').catch(() => ({})), V3.j('/api/v1/play/engine/world-data?name=factions').catch(() => ({})),
    ]);
    const hello = await full('/state', '/state').catch(() => ({ souls: [] }));  // every cast soul (the map tree only lists souls on a drawn level)
    const prev = st;
    const s = { branch: commits?.branch || 'main', head: commits?.head || null, tick: 0, turn: 0, day: 1, min: 8 * 60 + 30,
      vars: {}, classes: {}, nodes: {}, edges: {}, known: {}, pos: {}, plan: {}, souls: {}, npcs: {},
      ext: { tick: true, space: true, social: true, economy: !!eco.markets, factions: !!fac.factions, imagegen: true },
      budget: { day: 1, used: 0, perDay: 0 }, events: [], feed: [], tokens: [], pending: [], stale: {}, hooks: [], fired: [],
      seq: 0, commits: 0, grownCount: 0, link: prev?.link || null, econ: null, fac: null, panels: views.panels || [], views: views.views || [] };
    st = s; // helpers (posOf / where / clock) read st while it is being assembled

    // 地图树 → nodes / edges / known / 图片表
    const N = map.nodes || {};
    for (const [a, n] of Object.entries(N)) {
      V3.names[a] = n.name;
      const lv = n.parent, hs = lv && map.levels?.[lv] ? map.levels[lv].hotspots?.[a] : null;
      s.nodes[a] = { addr: a, name: n.name, kind: n.kind, parent: n.parent, summary: n.overview || n.summary || '', pos: hs || null, grown: n.source === 'plot' || !!n.extra?.plot };
      if (n.state?.discovered !== false) s.known[a] = true;
      (n.edges || []).forEach((e, k) => { const id = e.id || `${a}#${k}`; s.edges[id] = { id, level: a, from: e.from, to: e.to, dist: e.distance ?? (a === 'world' ? 20 : 1), kind: e.kind || 'road', tags: e.tags || [], blocked: !!e.blocked }; });
      if (n.has_scene) { V3.SCENE[a] = `scene:${a}`; }
    }
    for (const [lv, L] of Object.entries(map.levels || {})) if (L.has_image) V3.MAPIMG[lv] = `map_${lv}`;
    for (const [a, n] of Object.entries(N)) if (n.parent === 'world' || n.kind === 'town' || n.kind === 'city') {
      const gate = (n.children || []).find(c => /gate/.test(c)) || (n.children || [])[0]; if (gate) GATE[a] = gate;
    }
    V3.TOWNS = Object.keys(eco.markets || {}); V3.TOWNS.forEach((t, i) => (V3.TCOL[t] = ['#A594FF', '#F2B84B', '#5CC8E8', '#3DDC97'][i % 4]));
    v3ApplyWorldData(eco, fac);

    // schema → vars(带历史)/ classes / 时间
    const hist = {};
    for (const e of evs || []) {
      if (e.type !== 'var.changed') continue;
      const p = e.payload || {}; const h = hist[p.var] || (hist[p.var] = []);
      if (!h.length && p.from !== undefined) h.push([Math.max(0, e.turn - 1), p.from]);
      h.push([e.turn, p.to]);
      s.tick = Math.max(s.tick, e.turn || 0);
    }
    for (const v of schema.variables || []) {
      const ext = /^(price|stock|inv|econ)\./.test(v.name) ? 'economy' : /^(faction|rep|rel)\./.test(v.name) ? 'factions' : undefined;
      s.vars[v.name] = { name: v.name, type: v.type, value: v.value, min: v.min, max: v.max, path: v.path, key: v.key, readonly: v.readonly, doc: v.doc, ext,
        hist: (hist[v.name] && hist[v.name].length ? hist[v.name] : [[0, v.value]]) };
    }
    for (const c of schema.classes || []) s.classes[c.name] = { name: c.name, policy: appr.policies?.[c.name] || c.policy || 'auto', required: c.required || ['name'], ext: c.folder ? 'creator' : 'rpg', count: c.count };
    s.day = +(s.vars['time.day']?.value ?? 1); s.min = toMin(s.vars['time.clock']?.value); s.turn = +(s.vars.turn?.value ?? (trs.turns || []).length);

    // 人在哪:player / souls / npcs
    for (const ent of map.entities || []) {
      const p = posOf(ent.addr || ent.raw);
      if (ent.kind === 'player') s.pos.player = p;
      else if (ent.kind === 'soul') {
        const id = ent.id;  // map entities carry the soul's sid (elena / rowan)
        s.pos[id] = p;
        s.souls[id] = { id, iid: ent.id, name: ent.name, av: ent.has_portrait ? `av_${id}` : null, sp: ent.has_sprite ? `sp_${id}` : null,
          goals: [], intention: ent.status?.intention || '', mood: ent.status?.mood || '', companion: !!ent.status?.companion, lastLine: '', role: ent.role, traits: ent.traits || [] };
      } else if (ent.kind === 'npc') s.npcs[ent.id] = { id: ent.id, name: ent.name, at: p.at, met: !!ent.met, role: ent.role };
    }
    // 信息边界归引擎:/state 给了玩家可见的 where(「此刻在碧石镇」)= 玩家知道他在哪,Mock 的迷雾里算「见过」
    for (const so of hello.souls || []) {
      const id = so.sid; if (!id) continue;
      if (s.souls[id]) { if (so.where) s.souls[id].met = true; continue; }
      s.pos[id] = posOf(so.location);
      s.souls[id] = { id, iid: so.instance_id, name: so.name || id, av: `av_${id}`, sp: `sp_${id}`, goals: [], intention: '', mood: '', companion: false, lastLine: '', role: so.role, traits: [], met: !!so.where, whereText: so.where || '' };
    }
    s.pos.player ||= { at: null };
    if (s.pos.player.at) s.known[s.pos.player.at] = true;

    // 回合 trace → 对话流。每一拍一条 trace,trace 的 beat.kind 说是哪种拍(开源版只有叙事落账的一拍;别的拍由编排图决定,
    // 比如先只说话、世界不动的一拍,它的主持台词 / 递话筒 / 计划板也在这里拆开);开场是世界自带的一拍。
    // 没开 plan_loop 的旧局:每条 trace 是一个普通回合(玩家一句 → 角色 → 叙事)。
    const turns = trs.turns || [];
    const want = turns.slice(-40);
    await Promise.all(want.map(t => traceCache.has(t.i) ? null : full(`/trace?i=${t.i}`, `/trace?i=${t.i}`).then(d => traceCache.set(t.i, d)).catch(() => {})));
    const sidOf = name => { const so = Object.values(s.souls).find(x => x.name === name || x.id === name); return so ? so.id : null; };
    let last = null;
    const beats = { plan: 0, resolve: 0, mic: 0, dice: 0, lastBy: '' };  // 模拟工作台流程条的计数(每种拍各计几次)
    for (const t of want) {
      const d = traceCache.get(t.i); if (!d) continue;
      const day = s.day, clk = clock();
      const a = d.apply || {}, beat = a.beat || null;
      const input = d.player?.input || t.input || '';
      const changes = (a.applied || []).filter(x => x.op === 'set' || x.op === 'add').slice(0, 12).map(x => ({ kind: 'var', what: x.var, from: x.from, to: x.to }));
      const whoName = w => (w === 'player' ? '你' : (Object.values(s.souls).find(so => so.iid === w || so.id === w) || {}).name || V3.names[w] || w);
      (a.applied || []).filter(x => x.op === 'move_to').forEach(x => changes.push({ kind: 'move', what: `${whoName(x.who)}.at`, to: x.to, who: x.who, arrive: true }));
      (a.created || []).forEach(c => changes.push({ kind: c.class === 'status' ? 'status' : 'node', what: c.id, to: c.name || c.id }));   // 状态效果(中毒 / 流血 …)单独标
      const refused = (a.refused || []).map(r => ({ op: r.op || {}, why: r.why || '', pending: /等创作者批准/.test(r.why || '') }));
      if (beat && beat.kind === 'opening') {
        const text = (beat.script || []).map(x => x.text).join('\n\n') || a.narration_plain || '';
        const o = V3.splitOptions(text);
        s.feed.push({ id: ++s.seq, kind: 'opening', text: o.text, options: o.options, day, clock: clk, turn: t.turn_seq });
        last = { kind: 'opening', options: o.options };
      } else if (beat && beat.kind === 'plan') {
        const script = beat.script || [];
        if (!script.some(x => x.role === 'player') && input) s.feed.push({ id: ++s.seq, kind: 'you', text: input, day, clock: clk, turn: t.turn_seq });
        let opts = [];
        for (const x of script) {
          if (x.role === 'player') s.feed.push({ id: ++s.seq, kind: 'you', text: x.text, day, clock: clk, turn: t.turn_seq, beat: 'plan' });
          else if (x.role === 'host') { const o = V3.splitOptions(x.text); opts = o.options.length ? o.options : opts; s.feed.push({ id: ++s.seq, kind: 'host', text: o.text, options: o.options, day, clock: clk, turn: t.turn_seq }); }
          else if (x.role === 'handoff') {  // 主持把话筒递给她:「递话筒给艾琳娜:……你怎么应他?」
            const m = /^递话筒给([^::]+)[::]\s*([\s\S]*)$/.exec(x.text || '');
            const to = m ? m[1].trim() : ''; s.feed.push({ id: ++s.seq, kind: 'mic', to, who: sidOf(to), text: m ? m[2] : x.text, day, clock: clk, turn: t.turn_seq });
          } else {  // 角色自己回话;末尾的「(打算:……)」是她这一拍的打算
            const id = sidOf(x.who); const mm = /\n?[((]打算[::]([^))]*)[))]\s*$/.exec(x.text || '');
            const said = mm ? x.text.slice(0, mm.index).trim() : x.text;
            if (id && s.souls[id]) s.souls[id].lastLine = said;
            s.feed.push({ id: ++s.seq, kind: 'soul', who: id, name: x.who, text: said, intent: mm ? mm[1].trim() : '', beat: 'plan', day, clock: clk, turn: t.turn_seq }); }
        }
        if (!script.length && a.narration_plain) s.feed.push({ id: ++s.seq, kind: 'host', text: a.narration_plain, options: [], day, clock: clk, turn: t.turn_seq });
        beats.plan++; beats.mic += script.filter(x => x.role === 'handoff').length;
        last = { kind: 'plan', board: beat.board || {}, checks: beat.checks || [], mic: beat.mic || [], next: beat.next, nudged: !!beat.nudged, dm: beat.dm_called || null, reads: beat.reads || [], options: opts, ms: beat.ms };
      } else if (beat && beat.kind === 'resolve') {
        const props = a.proposals || [];
        const raw = a.narration_plain || (props.length ? props[props.length - 1].narration : '') || '';
        const dice = (beat.rolled || []).map(V3.parseRoll);
        const text = raw.split('\n').filter(l => !V3.DICE_LINE.test(l.trim())).join('\n').replace(/^\n+/, '');
        const tools = (a.tool_returns || []).map(x => ({ op: x.op || x.tool || x.name || '', text: x.text || x.summary || x.result || '' })).filter(x => x.op);
        const o = V3.splitOptions(text);
        const options = (a.options || []).map(x => (typeof x === 'string' ? x : x.text || x.label || '')).filter(Boolean);
        s.feed.push({ id: ++s.seq, kind: 'resolve', by: beat.advanced_by || '', board: beat.board || {}, dice, text: o.text, tools, changes, refused, options: options.length ? options : o.options, day, clock: clk, turn: t.turn_seq });
        beats.resolve++; beats.dice += dice.length; beats.lastBy = beat.advanced_by || '';
        last = { kind: 'resolve', options: options.length ? options : o.options };
      } else {
        if (t.turn_seq > 0 || !/^Start the game|^开始游戏|^ゲームを始め/.test(input)) s.feed.push({ id: ++s.seq, kind: 'you', text: input, day, clock: clk, turn: t.turn_seq });
        for (const so of d.souls || []) if (so.speech) {
          const id = so.sid; if (s.souls[id]) s.souls[id].lastLine = so.speech;
          s.feed.push({ id: ++s.seq, kind: 'soul', who: id, text: so.speech, judge: { attitude: so.state, confidence: '', ms: '' }, day, clock: clk, turn: t.turn_seq });
        }
        const props = a.proposals || []; const narr = props.length ? props[props.length - 1].narration : '';
        if (narr) s.feed.push({ id: ++s.seq, kind: 'wa', text: narr, engine: 'neonrp', changes, refused, day, clock: clk, turn: t.turn_seq });
        last = { kind: 'turn', options: [] };
      }
      const us = d.timing?.v3?.usage || {};
      if (us.prompt_tokens || us.total_tokens) s.tokens.push({ tick: t.turn_seq, turn: t.turn_seq, day, clock: clk, who: 'world-agent', tier: 'T0',
        prompt: us.prompt_tokens || 0, completion: us.completion_tokens || 0, cached: us.prompt_cache_hit_tokens || us.cached_tokens || 0, ms: Math.round(d.timing?.world_agent_ms || 0),
        cf: (us.prompt_tokens || 0) + (us.completion_tokens || 0) });  // cf = Mock 的「2.0 全量」反事实;真引擎没有反事实,按实际量记
    }
    // 计划板:最后一拍是只说话的那种(世界还没动)= 计划还在进行;落账之后清空
    s.beats = beats;
    s.board = last && last.kind === 'plan' ? last : null;
    s.beat = last ? last.kind : null;
    s.options = (last && last.options) || [];
    s.feed.push(...local.feed.filter(f => f.after >= turns.length));

    // 测试台的「每拍」原料(引擎还没有统一的每轮包 V2 之前,从 trace 里取):耗时 · 调用 · 写入 · 被拒 · 骰子
    s.rounds = want.map(t => {
      const d = traceCache.get(t.i); if (!d) return null;
      const a = d.apply || {}, b = a.beat || null;
      return { i: t.i, seq: d.turn_seq ?? t.turn_seq, kind: b ? b.kind : 'turn', input: String(d.player?.input || t.input || ''), loc: d.world_location || t.location || '',
        ts: d.ts || t.ts, spans: d.spans || [], calls: (b && b.calls) || [], ms: b ? b.ms : null, rounds: b ? b.rounds : null, advanced_by: b ? b.advanced_by : null,
        rolled: (b && b.rolled) || [], mic: (b && b.mic) || [], checks: (b && b.checks) || [], applied: a.applied || [], refused: a.refused || [], created: a.created || [],
        // 时间预算(10-19,引擎 45172125 / 私有 e5b7dfc):拍子到点时写出的半句留下了 · 该推进但没时间了、改到玩家下一句再清算
        truncated: !!(b && b.truncated), deferred: (b && b.advance_deferred) || null,
        timing: d.timing || null, commit: t.commit || null };
    }).filter(Boolean);
    s.schemaRaw = { classes: schema.classes || [], entries: schema.entries || {}, actions: schema.actions || [], triggers: schema.triggers || [] };

    // 账本 → 事件(按回合 × 提出者聚合)/ hook 触发
    const byKey = new Map();
    for (const e of evs || []) {
      const p = e.payload || {};
      const by = String(p.by || (e.type === 'trigger.fired' ? 'hook' : 'world-agent')).replace(/^solve$/, 'world-agent').replace(/^tick:.*/, 'tick');
      const key = `${e.turn}|${by}`;
      let ev = byKey.get(key);
      if (!ev) { ev = { id: ++s.seq, tick: e.turn, turn: e.turn, day: s.day, clock: '', by, why: by === 'tick' ? '世界规则(tick)' : '', ops: [], applied: [], refused: [], changes: [], hooks: [] }; byKey.set(key, ev); }
      if (e.type === 'var.changed') { ev.changes.push({ kind: 'var', what: p.var, from: p.from, to: p.to }); ev.applied.push({ op: 'set', var: p.var, value: p.to }); }
      else if (e.type === 'entry.entered') ev.changes.push({ kind: 'move', what: `${p.who}.at`, to: p.entry, who: p.who, arrive: true });
      else if (e.type === 'entity.created') ev.changes.push({ kind: 'node', what: p.id, to: p.name || p.id });
      else if (e.type === 'trigger.fired') { ev.hooks.push(p.id || p.trigger); s.fired.push({ hook: p.id || p.trigger, tick: e.turn }); }
    }
    s.events = [...byKey.values()].slice(-400);
    s.events.forEach(ev => { ev.ops = ev.applied.slice(); });

    // 世界规则 = 注册表的触发器(Mock 的 hook)
    s.hooks = (schema.triggers || []).map(t => {
      const w = t.when || {}; const c = (t.if || [])[0] || {};
      const cond = Object.keys(c).find(k => ['<', '<=', '>', '>=', '==', '!='].includes(k));
      return { id: t.id, kind: 'push', on: w.var || (w.entry ? `class:${w.entry}` : w.text ? 'text' : w.op ? `op:${w.op}` : 'turn'), cond: cond || 'change', val: cond ? c[cond] : undefined,
        then: ((t.then || [])[0] || {}).to || 'event', text: t.doc || ((t.then || [])[0] || {}).text || t.id, by: t.source || '世界规则' };
    });

    // 审批
    s.pending = (appr.pending || []).map(r => ({ id: r.id, op: { op: 'new', cls: r.op.class, name: r.op.name, ...r.op }, by: r.by || 'narration', clock: '', day: s.day }));

    // 经济 / 势力:实例来自视图绑定的类(caravan / rumor / quest)
    const rows = id => (s.views.find(v => v.id === id) || {}).rows || [];
    if (s.ext.economy) {
      const C = {};
      for (const c of rows('caravans')) {
        const st2 = c.status === 'delivered' ? 'arrived' : c.status;
        const eta = +(c.eta || 3), left = +(c.left || 0);
        C[c.id] = { id: c.id, name: c.name, from: c.from, to: c.to, good: c.good, qty: +c.qty || 0, buy: +c.buy || 0, owner: c.owner || 'guild', status: st2, eta, left };
        if (st2 === 'road') s.pos[c.id] = posOf(`road_${c.from}_${c.to}`, Math.max(0.05, Math.min(0.95, (eta - left) / Math.max(1, eta))));
      }
      const all = Object.values(C);
      s.econ = { caravans: C, acc: {}, n: all.length, robbed: all.filter(c => c.status === 'robbed').length, delivered: all.filter(c => c.status === 'arrived').length, volume: 0, trades: [] };
    }
    if (s.ext.factions) {
      const R = {}, Q = {};
      for (const r of rows('rumors')) { const towns = {}; String(r.towns_text || r.origin || '').split(/[、,]/).filter(Boolean).forEach(t => (towns[t] = 0)); R[r.id] = { id: r.id, text: r.text, origin: r.origin, heat: +r.heat || 0, tags: [], towns }; }
      for (const x of rows('quests')) Q[x.id] = { id: x.id, kind: x.kind, title: x.title || x.name, giver: x.giver, reward: (+x.reward_gold || 0) * 100, status: x.status };
      s.fac = { rumors: R, quests: Q, n: 0, strike: 0, lowJade: 0, lastTown: {}, log: [] };
    }

    // 世界线(提交图)
    G.list = []; G.by = {}; G.heads = {};
    if (commits) {
      for (const n of commits.nodes) {
        G.by[n.id] = { id: n.id, hash: n.id.slice(0, 7), parent: n.parent && commits.nodes.some(x => x.id === n.parent) ? n.parent : null, branch: n.branch, kind: n.turn_seq === 0 ? 'root' : 'turn',
          label: n.label || `回合 ${n.turn_seq}`, day: s.day, clock: '', tick: n.turn_seq, turn: n.turn_seq, n: 0, tags: [], bits: [], snap: null, kids: [] };
        G.list.push(n.id);
      }
      for (const id of G.list) { const p = G.by[id].parent; if (p && G.by[p]) G.by[p].kids.push(id); }
      for (const [b, info] of Object.entries(commits.branches || {})) if (info.tip && G.by[info.tip]) G.heads[b] = info.tip;
      G.n = G.list.length;
    }
    s.head = G.heads[s.branch] || s.head;

    V3.template = runv.template;
    if (runv.template?.card?.cover) V3.cover = V3.url(`/api/v1/local/templates/${encodeURIComponent(runv.template.id)}/cover`);
    st = s;
    // 组装 · Lint 的数据 = 这一局所用模板的真实内容(不用 Mock 的 LINK0);拿到后再重画
    if (prev?.link) st.link = prev.link;
    linkLoading = V3.loadLink(s).then(notify).catch(e => console.error(e));
  }
  let linkLoading = null;
  async function reloadLink() { V3.LINK.stamp = Date.now(); await V3.loadLink(st); notify(); }

  async function refresh() { await load(); notify(); }

  // ── 动作:全部交给引擎 ─────────────────────────────────────────────
  // 一句话跑完 = 引擎广播 turn_done(这句话引出的一拍或几拍都跑完)。逐字流从 chunk 来,显示在「主持在想」里。
  // 订不到事件流(Hub 等)就轮询:多了新 trace,且最后一拍不是「说完了、正要推进到下一拍」才算完。
  const live = { text: '', who: '', on: false, done: null, segs: [], beat: null, souls: {} };   // segs:流式片段 {who, beat, text, tools}(游玩层按它画)
  // 契约 1.0 拍事件(引擎 R6,core/beat_events):重前端订阅的就是这几种。和逐字流走同一条 /events;留最近 300 条给前端台的事件日志
  const BEAT_KINDS = new Set(['node.enter', 'node.leave', 'plan.beat', 'resolve.beat', 'dice', 'tool', 'state.changed', 'run.settled']);
  // ── 写状态先快后修正(10-22,core/write_down_async · docs/planning/HANDOFF-WRITE-DOWN-CORRECTION-1022.md)──
  // turn_done 之后 1–3 秒,后台的慢版本可能再改一次状态:write_down.pending → corrected(applied …)/ same / cut / timeout / failed。
  // 页面角落一行小字(不挡东西,几秒后收起;少动模式不动);改了就列出改了什么,不忙的时候 refresh() 一次。
  // 文案 = src/neonrp/tui/i18n.py 的 wd.*(tests/test_write_down_ui_i18n.py 对着查)
  const WD_T = {"zh": {"pending": "后台正在复核这一拍的状态…", "corrected": "复核后修正了状态", "same": "复核完毕：状态没有变化", "cut": "你先行动了，后台复核已取消", "timeout": "后台复核超时，状态保持不变", "failed": "后台复核失败，状态保持不变", "time": "时间", "day": "日期", "where": "位置", "got": "得到", "lost": "失去"}, "en": {"pending": "checking this beat's state in the background…", "corrected": "state corrected after a closer look", "same": "state checked: no change", "cut": "background check dropped — you moved on first", "timeout": "background check took too long — kept as it was", "failed": "background check failed — kept as it was", "time": "time", "day": "day", "where": "place", "got": "got", "lost": "lost"}, "ja": {"pending": "この場面の状態をバックグラウンドで再確認中…", "corrected": "再確認で状態を修正しました", "same": "再確認済み：状態に変更なし", "cut": "先に行動したため、再確認は取り消されました", "timeout": "再確認が時間切れ：状態はそのまま", "failed": "再確認に失敗：状態はそのまま", "time": "時刻", "day": "日付", "where": "場所", "got": "入手", "lost": "喪失"}, "ko": {"pending": "이 장면의 상태를 백그라운드에서 다시 확인하는 중…", "corrected": "다시 확인한 뒤 상태를 고쳤습니다", "same": "다시 확인 완료: 상태 변화 없음", "cut": "먼저 행동해서 백그라운드 확인이 취소되었습니다", "timeout": "백그라운드 확인 시간 초과: 상태 유지", "failed": "백그라운드 확인 실패: 상태 유지", "time": "시간", "day": "날짜", "where": "위치", "got": "얻음", "lost": "잃음"}};
  const WD_HOLD = { pending: 100000, corrected: 8000, same: 3000 };
  const wdLang = () => { const l = String(V3.q.get('lang') || (() => { try { return localStorage.getItem('wl.hub.lang'); } catch { return ''; } })() || document.documentElement.lang || 'zh').slice(0, 2); return WD_T[l] ? l : 'zh'; };
  const wd = { kind: '', text: '', detail: '', turn: null, log: [], timer: 0 };
  function wdDetail(m, T) {
    const bits = [], nm = v => { const k = String(v || ''); return k === 'time.clock' ? T.time : k === 'time.day' ? T.day : k.split('.').pop(); };
    for (const a of m.applied || []) {
      if (!a || typeof a !== 'object') continue;
      if (a.op === 'move_to' && (!a.who || a.who === 'player')) bits.push(`${T.where} → ${V3.names[a.to] || String(a.to || '').split('/').pop()}`);
      else if (a.var && 'to' in a) bits.push(`${nm(a.var)} ${a.from == null ? '' : `${a.from}→`}${a.to}`);
      else if (a.op === 'flag' && a.key) bits.push(String(a.key));
    }
    for (const g of m.gained || []) if (g && g.name && (!g.who || g.who === 'player')) bits.push(`${T.got} ${g.name}`);
    for (const g of m.lost || []) if (g && g.name && (!g.who || g.who === 'player')) bits.push(`${T.lost} ${g.name}`);
    return bits.slice(0, 4).join(' · ');
  }
  function wdPaint() {
    let el = document.getElementById('wdh');
    if (!wd.kind) { if (el) el.hidden = true; return; }
    if (!el) {
      if (!document.getElementById('wdh-css')) {
        const css = document.createElement('style'); css.id = 'wdh-css';
        css.textContent = `#wdh{position:fixed;left:16px;bottom:16px;z-index:60;max-width:min(80vw,560px);display:flex;gap:6px;align-items:baseline;pointer-events:none;font:500 12px/1.45 system-ui,sans-serif;color:#cfcbd8;padding:5px 12px 5px 10px;border-radius:12px;background:rgba(14,14,22,.78);backdrop-filter:blur(8px);box-shadow:0 0 0 1px rgba(255,255,255,.08);animation:wdhIn .25s ease both}#wdh[hidden]{display:none}#wdh i{font-style:normal;opacity:.7}#wdh em{font-style:normal;color:#f2c46b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}#wdh.pending i{animation:wdhP 1.6s ease-in-out infinite}#wdh.cut,#wdh.timeout,#wdh.failed{color:#9a97a5}@keyframes wdhIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}@keyframes wdhP{50%{opacity:.25}}@media (prefers-reduced-motion:reduce){#wdh,#wdh i{animation:none!important}}`;
        document.head.appendChild(css);
      }
      el = document.createElement('div'); el.id = 'wdh'; el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite'); document.body.appendChild(el);
    }
    const mark = { pending: '⋯', corrected: '✎', same: '✓' }[wd.kind] || '·';
    el.className = wd.kind; el.dataset.wd = wd.kind; el.hidden = false;
    el.innerHTML = `<i aria-hidden="true">${mark}</i><span></span>${wd.detail ? '<em></em>' : ''}`;
    el.querySelector('span').textContent = wd.text; if (wd.detail) el.querySelector('em').textContent = wd.detail;
  }
  function writeDown(m) {
    const kind = String(m.kind).slice('write_down.'.length), T = WD_T[wdLang()];
    if (!(kind in WD_HOLD) && !['cut', 'timeout', 'failed'].includes(kind)) return;
    clearTimeout(wd.timer);
    Object.assign(wd, { kind, text: T[kind], detail: kind === 'corrected' ? wdDetail(m, T) : '', turn: m.turn ?? null });
    wd.log.push({ kind, turn: m.turn, why: m.why || '' }); if (wd.log.length > 50) wd.log.shift();
    try { wdPaint(); } catch { /* no DOM (tests) */ }
    let left = WD_HOLD[kind] || 3500;   // 一句还在跑时不算时间
    const tick = () => { if (!busy) left -= 500; if (left <= 0) { wd.kind = ''; try { wdPaint(); } catch { /* no DOM */ } notify(); return; } wd.timer = setTimeout(tick, 500); };
    wd.timer = setTimeout(tick, 500);
    if (kind === 'corrected' && !busy) refresh().catch(() => {});
    notify();
  }
  const beats = { list: [], subs: [], live: 0 };
  function pushBeat(m, fromLive) {
    beats.list.push({ ...m, at: m.at || Date.now(), live: !!fromLive });
    if (beats.list.length > 300) beats.list.splice(0, beats.list.length - 300);
    if (fromLive) beats.live++;
    beats.subs.forEach(f => { try { f(m); } catch { /* 订阅者自己的错不挡别人 */ } });
  }
  function liveStream() {
    if (live.on || typeof EventSource === 'undefined') return;
    try {
      const es = live.es = new EventSource(V3.url('/events?debug=1'));  // 引擎不给 debug 时同 /events
      live.on = true; live.lastMsg = Date.now();
      let t = 0;
      es.onmessage = e => {
        let m; try { m = JSON.parse(e.data); } catch { return; }
        live.lastMsg = Date.now();
        if (m.kind === 'hello' && m.beat_kinds && window.BEATS && window.BEATS.fromSpec) window.BEATS.fromSpec(m.beat_kinds);
        if (m.kind === 'rebound') { es.close(); live.on = false; setTimeout(liveStream, 200); return; }   // 引擎换了局:这条流是旧一局的,重连
        if (m.kind === 'chunk' && busy) {
          const raw = String(m.text || ''); const tag = /^\[\[subagent:([^\]]+)\]\]/.exec(raw);
          const B = window.BEATS || {}, ph = m.beat || (B.phase ? B.phase(raw) : null);   // 这段属于哪一拍:引擎直接给(chunk.beat),旧引擎写阶段行、由私有层认
          if (ph) live.beat = ph;
          const txt = (B.strip ? B.strip(raw) : raw).replace(/\[\[subagent:[^\]]+\]\]/g, '');
          if (tag && tag[1] !== live.who) { live.who = tag[1]; live.text += (live.text ? '\n' : '') + `${tag[1]}:`; }
          live.text += txt;
          // 角色的每个字都带 [[subagent:名字]];主持的叙事不带 —— 没带就是主持(之前沿用上一个说话人,主持的话会接进角色的气泡里)
          const who = tag ? tag[1] : '主持', last = live.segs[live.segs.length - 1];
          live.lastChunk = Date.now();
          if (!last || last.who !== who || last.beat !== live.beat) live.segs.push({ who, beat: live.beat, text: txt.replace(/^\n+/, ''), tools: [] });
          else last.text += txt;
          if (!t) t = setTimeout(() => { t = 0; notify(); }, 120);
        } else if (m.kind === 'tool' && !('request' in m)) {   // 回合进行中的工具调用(只有名字),不是拍事件
          if (busy) { const last = live.segs[live.segs.length - 1]; (last ? last.tools : (live.segs.push({ who: live.who || '主持', beat: live.beat, text: '', tools: [] }), live.segs[0].tools)).push({ name: String(m.name || ''), at: Date.now() }); if (!t) t = setTimeout(() => { t = 0; notify(); }, 120); }
        } else if (m.kind === 'soul_status') {
          live.souls = m.statuses || {}; if (!t) t = setTimeout(() => { t = 0; notify(); }, 120);
        } else if (String(m.kind || '').startsWith('write_down.')) {
          pushBeat(m, true); writeDown(m);
        } else if (BEAT_KINDS.has(m.kind)) {
          pushBeat(m, true);
          if (m.kind === 'state.changed' && m.corrected && !busy) refresh().catch(() => {});   // 修正带来的状态变化(turn_done 之后到)
        } else if (m.kind === 'turn_done') {
          if (live.done) { const d = live.done; live.done = null; d(m); }
          else if (!busy) refresh().catch(() => {});  // 别处跑完的一句(开局自动的「开始游戏」/ 另一个标签页 / tick):马上跟上
        }
      };
      es.onerror = () => { es.close(); live.on = false; clearTimeout(live.retry); live.retry = setTimeout(liveStream, 2000); };   // 断了就过 2 秒重连
    } catch { live.on = false; }
  }
  async function waitTurn(before) {
    for (let i = 0; i < 400; i++) {
      await new Promise(r => setTimeout(r, 1500));
      if (!live.done) return true;  // turn_done 已到
      const t = await V3.j('/traces').catch(() => null);
      const rows = (t && t.turns) || [];
      // 流没连上,或者连着却 10 秒没有任何消息(比如挂在换局前的旧广播上):去查回合记录,别一直等
      if (rows.length > before && (!live.on || Date.now() - (live.lastMsg || 0) > 10000)) {
        const d = await V3.j(`/trace?i=${rows[rows.length - 1].i}`).catch(() => null);
        const b = d && d.apply && d.apply.beat;
        if (!(b && b.kind === 'plan' && b.next === 'advance')) return true;
      }
    }
    return false;
  }
  function sysLine(text, n) { local.feed.push({ id: 900000 + local.feed.length, kind: 'sys', text, day: st.day, clock: clock(), turn: st.turn, after: n }); st.feed.push(local.feed[local.feed.length - 1]); notify(); }
  // Worldlines 额度用完 / 积分不够 / 今日额度没领(core/billing_stop.py):重试没用,告诉玩家怎么办 + 链接;留在记录里直到再跑两句
  function billingStop(b, before) {
    const msg = String(b.message || '额度不够了'), url = String(b.billing_url || '');
    sysLine(url ? `${msg} ${url}` : msg, before + 2);
    toastSafe(msg);
  }
  async function say(text) {
    if (busy) return toastSafe('上一句还在跑');
    liveStream();
    busy = true; live.text = ''; live.who = ''; live.segs = []; live.beat = null; live.lastChunk = 0;
    const before = ((await V3.j('/traces').catch(() => ({ turns: [] }))).turns || []).length;
    st.feed.push({ id: ++st.seq, kind: 'you', text, day: st.day, clock: clock(), turn: st.turn });
    notify();
    try {
      const done = new Promise(r => { live.done = r; });
      const r = await fetch(V3.url('/cmd'), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
      if (r.status === 409) { live.done = null; toastSafe('上一句还在跑'); }
      else { const m = await Promise.race([done, waitTurn(before).then(() => null)]); if (m && m.billing) billingStop(m.billing, before); else if (m && m.success === false && m.error) toastSafe('这一句没跑完:' + String(m.error).slice(0, 120)); }
    } finally { busy = false; live.done = null; live.text = ''; live.segs = []; live.beat = null; local.feed = local.feed.filter(f => f.after > before + 1); await refresh(); }
  }
  async function tick() {
    try { await V3.post('/api/v1/play/engine/tick', { turns: 1 }); } catch (e) { if (e.status === 409) return; throw e; }
    await refresh();
  }
  function direct(text) { return say(`(导演)${text}`); }
  // 停止:让引擎做完当前这一步就停(POST /cancel = ConversationSession.cancel(),和 TUI 一样)
  async function cancel() { const r = await V3.post('/cancel', {}).catch(e => ({ ok: false, error: e.message })); return r; }
  function relisten() { try { live.es && live.es.close(); } catch { /* 已经关了 */ } live.on = false; liveStream(); }
  async function approve(id, yes) { await V3.post(`/api/v1/play/engine/approvals/${encodeURIComponent(String(id))}`, { approve: !!yes }).catch(e => toastSafe('审批失败:' + e.message)); await refresh(); }
  function register() { toastSafe('游玩中注册变量:在创作工坊里做(引擎只允许创作侧注册)'); return { refused: [{ why: '游玩侧不能注册' }], changes: [] }; }
  function cast() { toastSafe('cast:引擎侧还没有游玩中把 NPC 升为主角的接口'); return { changes: [] }; }
  async function branchFrom(id) {
    const r = await V3.post('/rollback', { commit: id }).catch(e => ({ ok: false, error: e.message }));
    if (!r.ok) { toastSafe('分岔失败:' + (r.error || '')); return false; }
    await refresh(); return st.branch;
  }
  const branchNew = () => branchFrom(G.heads[st.branch]);
  const branchSwitch = name => (G.heads[name] && name !== st.branch ? branchFrom(G.heads[name]) : null);
  const checkout = branchSwitch;
  const branchList = () => Object.keys(G.heads);
  const branchGet = name => (name === st.branch ? st : null);
  const stateAt = id => (id === G.heads[st.branch] ? st : null);
  async function reset() {
    const id = V3.template?.id; if (!id) return toastSafe('不是从模板开的局');
    const r = await V3.post('/api/v1/play/session', { slug: `tpl--${id}` }); history.replaceState(null, '', `?save=${encodeURIComponent(r.slug || '')}`); traceCache.clear(); await refresh();
  }
  // 创作者操作:Mock 的 propose('creator', ops) → 引擎里有对应的就调
  const API = {
    get st() { return st; }, clock: () => clock(), where, townOf, adj, path, coLocated, nameOf: w => st.souls[w]?.name || V3.names[w] || w, get GATE() { return GATE; },
    feed: item => { st.feed.push({ id: ++st.seq, day: st.day, clock: clock(), turn: st.turn, ...item }); },
    rnd: () => Math.random(), reg() {}, cls() {}, continueTrip() {}, spend() {},
    propose(by, ops, why = '') {
      const ev = { id: ++st.seq, tick: st.tick, turn: st.turn, day: st.day, clock: clock(), by, why, ops, applied: [], refused: [], changes: [], hooks: [] };
      if (by !== 'creator') { for (const op of ops) ev.refused.push({ op, why: '这一步由引擎决定,前端不能直接改世界' }); st.events.push(ev); notify(); return ev; }
      const L = st.link, tpl = [], fills = [];
      for (const op of ops) {
        if (op.op === 'set_policy') {  // 这一局立刻生效;模板可写时也写进模板(之后新开的局继承)
          ev.applied.push(op); V3.post('/api/v1/play/engine/policy', { class: op.cls, policy: op.policy }).then(refresh).catch(e => toastSafe(e.message));
          if (L?.writable) tpl.push(op);
        } else if (op.op === 'fill_asset') {
          if (!L) ev.refused.push({ op, why: '模板创作只在本地引擎上有' }); else { ev.applied.push(op); fills.push(op); }
        } else if (V3.TPL_OPS.includes(op.op)) {
          if (!L) ev.refused.push({ op, why: '模板创作只在本地引擎上有' });
          else if (!L.writable) ev.refused.push({ op, why: `「${V3.template?.card?.title || L.tid}」是内置模板(只读)——先在世界页「＋ 新建世界」另存一份,再改` });
          else { ev.applied.push(op); tpl.push(op); }
        } else ev.refused.push({ op, why: `引擎没有创作者操作 ${op.op}` });
      }
      if (tpl.length) V3.tplOps(tpl).then(d => {
        if (d.ok) toastSafe(`已写进模板 ${L.tid}:${d.applied.map(a => a.what).join(' · ')}${tpl.some(o => ['set_mixins', 'register_class', 'set_world_data'].includes(o.op)) ? '(规则类修改在新开一局后生效)' : ''}`);
        else toastSafe(`模板拒绝了:${(d.refused || []).map(r => r.why).join(';')}`);
        return reloadLink();
      }).catch(e => toastSafe(e.message));
      for (const op of fills) V3.fillSlot(op.key).then(() => { toastSafe(`素材 ${op.key} 已生成 → 进模板,并留档到素材车间`); return reloadLink(); })
        .catch(e => { toastSafe(`生成失败:${e.message}`); return reloadLink(); });
      st.events.push(ev); notify(); return ev;
    },
  };
  function act(fn) { const out = fn(API); notify(); return out; }
  function use(x) { EXTS.push(x); }  // 扩展只登记 op 归属;creator 的数据来自模板(V3.loadLink),不用 Mock 的 LINK0
  const toastSafe = t => { try { toast(t); } catch { console.log(t); } };

  return {
    get s() { return st; }, get busy() { return busy; }, get live() { return live.text; }, get wd() { return { kind: wd.kind, text: wd.text, detail: wd.detail, turn: wd.turn, log: wd.log.slice() }; }, subscribe: f => subs.push(f), notify, use, API, G, EXTS,
    load, refresh, reloadLink, listen: liveStream, relisten, cancel, beats, pushBeat, get streaming() { return live.on; }, get liveView() { return { segs: live.segs, beat: live.beat, souls: live.souls, lastChunk: live.lastChunk || 0 }; }, get linkLoading() { return linkLoading; }, tick, say, direct, approve, register, cast, act, reset,
    branchNew, branchSwitch, branchList, branchGet, branchFrom, checkout, stateAt, where, coLocated, worldPos, adj, levelOf, townOf, clock, path, GATE,
    history: n => st.vars[n]?.hist || [], get: n => st.vars[n]?.value,
  };
})();
