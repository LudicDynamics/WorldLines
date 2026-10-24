/* 角色编排台(10-16:和世界编排台一体两面 —— 同一张状态机图,同一个编辑器;只在 Local,Hub 不显示)。
   编排页顶上「世界 / 角色」切换。角色面:左上「角色 ▾」= 三类角色一张表(GET /api/v1/souls/catalog:
   ① 角色库里没 link 任何世界的独立角色 ② 世界里可以单独聊的 standalone ③ 可以带走的 takeable),点哪个就画它的图
   (GET /api/v1/souls/orchestration?ref=);节点 = chat 直聊 · tick 自由行动 · reflect 记忆整理 · in_world 世界里那一拍;
   有哪些节点 / 每个节点的步骤 / 参数 / 触发 = 接口的 hooks(soul_orchestration.describe(),只含引擎真跑的),这里只翻成中文;
   「世界里那一拍」显示这个角色在它世界里的真实设置(变体 · 按 depth 分流 · 提示词名),变体写回 POST /api/v1/souls/in_world;
   哪个世界 = 全局「当前世界」S.world(live.js;?world= 传给引擎:角色库的角色在当前世界里有绑定就看它,没有看第一个绑定的;
   世界里的角色总是它自己的世界),换世界(window 'wl:world')就重读这一拍;
   工具注册表换成角色的(表情 · 记忆 · 生图 · 切图;没上线的画得出来、不会被调用);改了就送 /lint,写回
   POST /api/v1/souls/orchestration(独立角色写角色库;世界里的角色只改这个世界 = 模板覆盖;内置模板只读)。
   右栏对话测试 = 真的和这个角色聊(小手机里的同一条对话,按写回后的图回话,会花额度)。 */
(() => {
  const SO = window.SOULORCH = { mode: 'world', rows: null, err: '', tab: 'independent', q: '', open: false, key: '', graphs: {}, hooks: null,
    lint: {}, sig: {}, saved: {}, msg: {}, chat: {}, amb: {}, stk: {}, busy: false, timer: null };
  // 下面几张表只是中文名字;有什么(节点种类 · 步骤 · 参数 · 触发)以接口 hooks 为准,没在 hooks 里的不画
  const SKIND = { chat: '直聊', tick: '自由行动', reflect: '记忆整理', in_world: '世界里那一拍' };
  const STRIG = { chat: '收到消息', tick: '前台 tick', idle: '闲着(分钟)' };
  const STEP_LBL = { docs: '读文档', history: '最近几条对话', reply: '回话', bubbles: '拆气泡 · 表情', ambient: '作息 · 简单世界观', doing: '做一件小事',
    memory: '写回记忆', message: '可能发一条消息', reflect: '每 N 次 → 记忆整理', read: '读短期记忆', fold: '整理成几句', write: '写进长期 · 修剪短期',
    called: '世界回合按 depth 点到', soul_step: '按变体走一拍', settle: '世界清算' };
  const KNOB_LBL = { history: '带上最近几条对话', max_bubbles: '一次最多回几条', doc_cap: '角色文档最多读多少字', interval_min: '两次之间至少几分钟',
    daily_max: '每天最多几次', proactive_daily: '每天最多主动发几条', prompt: '提示词(空 = 引擎默认)', every: '每几次 tick 整理一次(0 = 关)', keep: '短期记忆留几条' };
  const DEPTH_LBL = { silent: '不出声', gesture: '小动作', speak: '说话', act: '行动', away: '不在玩家眼前' };
  const WKIND = Object.keys(KIND);
  Object.assign(KIND, SKIND);
  const TABS = [['independent', '独立角色'], ['standalone', '可单独聊'], ['takeable', '可带走'], ['library', '角色库全部']];
  const kinds = () => (SO.hooks && SO.hooks.node_kinds) || {};
  const stepsOf = k => ((kinds()[k] || {}).steps || []).map(x => [x.by, STEP_LBL[x.id] || x.doc]);
  const knobsOf = k => Object.entries((kinds()[k] || {}).params || {}).filter(([, v]) => v === null || typeof v !== 'object').map(([x]) => x);
  const promptOf = (k, n) => k === 'chat' ? 'soul_chat · 角色自己的文件夹' : k === 'tick' ? (n.prompt ? '节点自己的(下面 prompt)' : 'soul_tick.PROMPT(引擎默认)')
    : k === 'reflect' ? 'soul_tick.REFLECT_PROMPT · 便宜调用(≤ 400 token)' : k === 'in_world' ? '世界的 soul_step(见下面)' : '—';
  const CHAT_LBL = { library: '角色库 · 直接能聊', standalone: '可单独聊', obtained: '已获得', locked: '还没获得' };
  // 只在 Local:浏览器版引擎(Hub)的 /api/v1/souls/* 回 404,角色面就只显示一句说明
  const isSoul = () => SO.mode === 'soul';
  const curWorld = () => (window.WL_WORLD && window.WL_WORLD()) || '';
  const benchUrl = ref => `/api/v1/souls/orchestration?ref=${encodeURIComponent(ref)}${curWorld() ? '&world=' + encodeURIComponent(curWorld()) : ''}`;
  const cur = () => SO.graphs[SO.key];
  const send = (method, path, body) => fetch(V3.url(path), { method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
    .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw Object.assign(new Error(j.error || `${r.status}`), { status: r.status }); return j; });

  document.head.insertAdjacentHTML('beforeend', `<style>
    .somode{display:inline-flex;gap:4px;padding:3px;border-radius:999px;background:var(--fill);box-shadow:0 0 0 1px var(--line2)}
    .somode button{border:0;background:none;border-radius:999px;padding:5px 12px;font:600 12px var(--glass-font,system-ui);color:var(--muted)} .somode button.on{background:var(--ink);color:var(--bg,#111)}
    .sopick{position:absolute;z-index:20;top:44px;right:0;width:min(420px,92vw);max-height:62vh;display:flex;flex-direction:column;padding:12px;border-radius:18px;gap:8px}
    .sopick .rows{overflow:auto;display:grid;gap:4px} .sopick .row1{display:grid;grid-template-columns:36px 1fr auto;gap:10px;align-items:center;padding:6px 8px;border-radius:12px;cursor:pointer;border:0;background:none;text-align:left;color:inherit}
    .sopick .row1:hover,.sopick .row1.on{background:var(--fill)} .sopick img,.sopick .ph{width:36px;height:36px;border-radius:50%;object-fit:cover;background:var(--well)}
    .sopick small{display:block;color:var(--muted);font-size:11.5px} .sopick .k{font:10.5px var(--machine);color:var(--muted)}
    .sochat .m.soul{align-self:flex-start} .sochat .m.me{align-self:flex-end}
  </style>`);

  // 引擎的角色图 → 编排台画的图(和世界那张同一种:nodes 带坐标 · edges 的 on 拆成触发 + 值);raw 留着,写回时转回去
  // 一个节点在界面上的样子:步骤 · 参数(缺的用引擎默认值)都照 hooks
  function soulNode(k, n, i) {
    const P = (kinds()[k] || {}).params || {};
    return { kind: k, title: n.title || SKIND[k] || k, x: 80 + (i % 3) * 300, y: 90 + Math.floor(i / 3) * 170, tools: n.tools || [], prompt: promptOf(k, n),
      knobs: Object.fromEntries(knobsOf(k).map(x => [x, n[x] ?? P[x] ?? ''])), steps: stepsOf(k), engine: true, soul: true };
  }
  function toUi(G0, b) {
    if (b.hooks) SO.hooks = b.hooks;
    const ids = Object.keys(G0.nodes || {}), nodes = {};
    ids.forEach((id, i) => { const n = G0.nodes[id]; nodes[id] = soulNode(n.kind in kinds() ? n.kind : 'chat', n, i); });
    // 世界里那一拍不是这张图的节点:有世界就画一个(只读的图位置,写回时不带),点开看 / 改它在那个世界的真实设置
    if (b.in_world && !Object.values(nodes).some(n => n.kind === 'in_world'))
      nodes.in_world = { ...soulNode('in_world', { title: `世界里那一拍 · ${b.in_world.title}` }, ids.length), virtual: true };
    const edges = (G0.edges || []).map(e => { const on = Object.keys(e.on || {})[0] || 'always', v = (e.on || {})[on]; return { id: e.id, from: e.from, to: e.to, on, val: v === true ? '' : String(v ?? ''), engine: true }; })
      .filter(e => (e.from === '*' || nodes[e.from]) && nodes[e.to]);
    // 「从任何节点」的边(from: *)图上画不出来:原样留着,写回时带上
    return { title: `角色 · ${b.name}`, start: G0.start || ids[0], nodes, edges: edges.filter(e => e.from !== '*'), any: (G0.edges || []).filter(e => e.from === '*'), raw: JSON.parse(JSON.stringify(G0)), soul: b.ref, edit: b.edit, base: b.base, live: true, iw: b.in_world || null, iwWorld: curWorld() };
  }
  // 编排台的图 → 引擎的图:节点保留引擎原有字段,工具 / 参数 / 标题按界面上的改
  function toEngine(g, key) {
    const raw = g.raw || {}, nodes = {};
    for (const [id, n] of Object.entries(g.nodes)) {
      if (n.virtual) continue;
      const was = (raw.nodes || {})[id] || {};
      const knobs = Object.fromEntries(Object.entries(n.knobs || {}).filter(([, v]) => v !== '' && v != null).map(([k, v]) => [k, isNaN(+v) ? v : +v]));
      nodes[id] = { ...was, kind: n.kind, title: n.title, tools: S.toolsOver[key + ':' + id] || n.tools || [], ...knobs };
    }
    const edges = g.edges.filter(e => nodes[e.from] && nodes[e.to]).map(e => ({ id: e.id, from: e.from, to: e.to,
      on: { [e.on || 'always']: e.val === '' || e.val == null ? (e.on === 'chat' ? 'message' : true) : (e.on === 'idle' && !isNaN(+e.val) ? +e.val : e.val) } }))
      .concat((g.any || []).filter(e => nodes[e.to]));
    return { schema: raw.schema || 'worldlines.orchestration/1', subject: 'soul', id: raw.id || 'soul', targets: raw.targets, start: nodes[g.start] ? g.start : Object.keys(nodes)[0], nodes, edges };
  }
  const sigOf = (g, key) => JSON.stringify(toEngine(g, key));

  async function loadRows() {
    if (SO.rows || SO.busy) return;
    SO.busy = true;
    try { SO.rows = (await V3.j('/api/v1/souls/catalog')).souls || []; SO.err = ''; } catch (e) { SO.rows = []; SO.err = e.status === 404 ? '这个引擎没有角色编排台(只在 Local)' : `读不到角色列表:${e.message}`; }
    SO.busy = false;
    if (!SO.key && SO.rows.length) { const first = SO.rows.find(r => r.kinds.includes(SO.tab)) || SO.rows[0]; await openSoul(first.ref); return; }
    if (S.screen === 'orch') renderOrch();
  }
  async function openSoul(ref) {
    const key = 'soul:' + ref;
    SO.key = key; SO.open = false;
    if (!SO.graphs[key]) {
      try { const b = await V3.j(benchUrl(ref)); SO.hooks = b.hooks; SO.graphs[key] = toUi(b.graph, b); SO.lint[key] = b.lint || []; SO.saved[key] = sigOf(SO.graphs[key], key); }
      catch (e) { SO.msg[key] = `读不到这张图:${e.message}`; }
    }
    S.node = cur() ? cur().start : null; S.edge = null; S.layer = 'graph';
    if (S.screen === 'orch') renderOrch();
  }

  // 当前世界换了:只重读这一拍(图上没写回的改动留着)
  async function refreshIw(key) {
    const g = SO.graphs[key]; if (!g || g.iwWorld === curWorld()) return;
    const w = g.iwWorld = curWorld();
    let iw; try { iw = (await V3.j(benchUrl(g.soul))).in_world || null; } catch (e) { return; }
    if (g.iwWorld !== w) return;   // 又换过世界:慢回来的旧答案不盖新的
    g.iw = iw;
    const v = g.nodes.in_world;
    if (g.iw && v && v.virtual) v.title = `世界里那一拍 · ${g.iw.title}`;
    else if (g.iw && !v) g.nodes.in_world = { ...soulNode('in_world', { title: `世界里那一拍 · ${g.iw.title}` }, Object.keys(g.nodes).length), virtual: true };
    else if (!g.iw && v && v.virtual) { delete g.nodes.in_world; if (S.node === 'in_world') S.node = g.start; }
    if (isSoul() && SO.key === key && S.screen === 'orch') renderOrch();
  }
  window.addEventListener('wl:world', () => { if (SO.key) refreshIw(SO.key); });
  function lintBox(key) {
    const rows = SO.lint[key] || [], g = SO.graphs[key];
    const dirty = g && sigOf(g, key) !== SO.saved[key];
    const ro = g && g.edit && !g.edit.writable;
    const where = g && g.edit ? (g.edit.to === 'library' ? `角色库 ${g.edit.id}` : `世界 ${g.edit.id}(只改这个世界)`) : '';
    return `<div class="orchsave glass"><span class="tag">${esc(SO.msg[key] || (ro ? `${where} 是内置模板(只读):先在 Template 页复制成自己的` : dirty ? '图上有改动,还没写回' : '和写回的一致'))}</span>
      <button class="btn ${dirty && !ro ? 'p' : ''}" data-sosave ${dirty && !ro ? '' : 'disabled'}>写回${esc(where ? ' · ' + where : '')}</button></div>
      ${rows.length ? `<div class="orchlint glass"><b>检查 · ${rows.length}</b>${rows.map(w => `<div><span class="dot ${w.level === 'block' ? 'bad' : 'warn'}"></span>${esc(w.code)}<small>${esc(w.msg)}</small></div>`).join('')}</div>` : ''}`;
  }
  function relint() {
    clearTimeout(SO.timer);
    SO.timer = setTimeout(async () => {
      const key = SO.key, g = cur(); if (!g) return;
      const sig = sigOf(g, key); if (SO.sig[key] === sig) return;
      try { SO.lint[key] = (await send('POST', '/api/v1/souls/orchestration/lint', { graph: toEngine(g, key) })).lint || []; } catch (e) { SO.lint[key] = [{ level: 'warn', code: 'orch.lint_failed', msg: e.message }]; }
      SO.sig[key] = sig;
      if (isSoul() && S.screen === 'orch' && S.layer === 'graph') paintBar();
    }, 350);
  }
  function paintBar() {
    const b = document.getElementById('board'); if (!b || SO.layer) return;
    b.querySelectorAll('.orchsave,.orchlint').forEach(x => x.remove());
    b.insertAdjacentHTML('beforeend', lintBox(SO.key));
  }
  async function save() {
    const key = SO.key, g = cur(); if (!g) return;
    SO.msg[key] = '写回中……'; paintBar();
    try {
      const r = await send('POST', '/api/v1/souls/orchestration', { ref: g.soul, graph: toEngine(g, key) });
      const b = await V3.j(benchUrl(g.soul));
      Object.keys(S.toolsOver).filter(k => k.startsWith(key + ':')).forEach(k => delete S.toolsOver[k]);
      SO.graphs[key] = toUi(b.graph, b); SO.lint[key] = b.lint || []; SO.saved[key] = SO.sig[key] = sigOf(SO.graphs[key], key);
      SO.msg[key] = r.to === 'library' ? '写回角色库 · 小手机下一句就按这张图回' : `写回世界 ${r.id} · 小手机下一句就按这张图回`;
    } catch (e) { SO.msg[key] = '没写成:' + e.message; }
    renderOrch();
  }

  // 顶上「世界 / 角色」切换 + 角色面的选角色下拉(替掉世界那张图的下拉框)
  function chrome() {
    const r = document.querySelector('#s-orch .crumb .r'); if (!r) return;
    r.insertAdjacentHTML('afterbegin', `<span class="somode"><button data-somode="world" class="${isSoul() ? '' : 'on'}">世界</button><button data-somode="soul" class="${isSoul() ? 'on' : ''}">角色</button></span>`);
    if (!isSoul()) return;
    const cr = document.querySelector('#s-orch .crumb');
    if (cr && !cr.querySelector('[data-solayer]')) {
      cr.querySelectorAll('[data-layer]').forEach(x => x.classList.toggle('on', !SO.layer && x.dataset.layer === S.layer));
      r.insertAdjacentHTML('beforebegin', `<span class="sep">/</span><button class="${SO.layer === 'ambient' ? 'on' : ''}" data-solayer="ambient">简单世界观</button><span class="sep">/</span><button class="${SO.layer === 'stickers' ? 'on' : ''}" data-solayer="stickers">专属表情</button>`);
    }
    const sel = r.querySelector('#gsel'), tag = sel && sel.previousElementSibling;
    if (tag && tag.classList.contains('tag')) tag.textContent = '角色';
    const row = (SO.rows || []).find(x => 'soul:' + x.ref === SO.key);
    if (sel) sel.outerHTML = `<button class="btn" data-sopick>${esc(row ? row.name : '选一个角色')} ▾</button>`;
    r.style.position = 'relative';
    if (SO.open) r.insertAdjacentHTML('beforeend', pickPanel());
  }
  function pickPanel() {
    const q = SO.q.trim().toLowerCase();
    const rows = (SO.rows || []).filter(x => x.kinds.includes(SO.tab)).filter(x => !q || [x.name, x.world, x.ref].join(' ').toLowerCase().includes(q));
    const n = k => (SO.rows || []).filter(x => x.kinds.includes(k)).length;
    return `<div class="sopick glass"><div class="row" style="gap:6px;flex-wrap:wrap">${TABS.map(([k, l]) => `<button class="chip ${SO.tab === k ? 'solid' : ''}" data-sotab="${k}">${l} · ${n(k)}</button>`).join('')}</div>
      <input class="cell" id="soq" placeholder="搜名字 / 世界" value="${esc(SO.q)}" autocomplete="off">
      <div class="rows">${rows.map(x => `<button class="row1 ${'soul:' + x.ref === SO.key ? 'on' : ''}" data-soref="${esc(x.ref)}">${x.avatar_thumb_url ? `<img src="${esc(V3.url(x.avatar_thumb_url))}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph'}))">` : '<span class="ph"></span>'}
        <span><b>${esc(x.name)}</b><small>${esc(x.world || (x.worlds && x.worlds.length ? x.worlds.map(w => w.title || w.template).join(' · ') : '不在任何世界里'))}</small></span>
        <span class="k">${esc(CHAT_LBL[x.chat] || x.chat)}${x.edit && !x.edit.writable ? ' · 只读' : ''}</span></button>`).join('') || `<div class="sub" style="padding:8px">${esc(SO.err || (SO.rows ? '这一类还没有角色' : '读角色列表……'))}</div>`}</div></div>`;
  }
  // 右栏:真的和这个角色聊(按写回后的图;草稿要先写回)
  function chatSide() {
    const side = document.querySelector('#s-orch .side > .glass'), g = cur(); if (!side || !g) return;
    const th = SO.chat[g.soul];
    if (!th) { SO.chat[g.soul] = { messages: null, sending: false, err: '' }; V3.j(`/api/v1/chat/thread?ref=${encodeURIComponent(g.soul)}`).then(t => { SO.chat[g.soul].messages = t.messages || []; SO.chat[g.soul].access = t.access; if (isSoul()) chatSide(); }).catch(e => { SO.chat[g.soul].err = e.message; SO.chat[g.soul].messages = []; if (isSoul()) chatSide(); }); }
    const t = SO.chat[g.soul], msgs = (t.messages || []).slice(-30);
    const locked = t.access === 'locked';
    side.innerHTML = `<div class="side-h"><b>对话测试</b> <span class="tag">真角色 · 会花额度</span><div class="sub" style="font-size:12.5px">就是小手机里的那条对话:按写回后的图回话(草稿先写回)。${locked ? '这个角色玩家还没获得,小手机里聊不了。' : ''}</div></div>
      <div class="chat sochat" id="sochat">${t.messages === null ? '<div class="m sys">读对话……</div>' : msgs.map(m => `<div class="m ${m.from === 'me' ? 'me' : 'soul human'}">${m.kind === 'sticker' ? `<span class="tag">表情 ${esc(m.sticker)}</span>` : esc(m.text)}</div>`).join('') || '<div class="m sys">还没聊过</div>'}${t.sending ? '<div class="m sys">正在输入……</div>' : ''}${t.err ? `<div class="m sys"><span class="bad">${esc(t.err)}</span></div>` : ''}</div>
      <div class="compose"><div class="in"><input id="soin" placeholder="${locked ? '还不能聊' : '说一句'}" autocomplete="off" ${locked ? 'disabled' : ''}><button class="send" id="sosend" aria-label="发送" ${locked ? 'disabled' : ''}>➤</button></div></div>`;
    const c = document.getElementById('sochat'); if (c) c.scrollTop = c.scrollHeight;
  }
  async function say(text) {
    const g = cur(); if (!g || !text) return;
    const t = SO.chat[g.soul]; if (!t || t.sending) return;
    t.messages = [...(t.messages || []), { from: 'me', kind: 'text', text }]; t.sending = true; t.err = ''; chatSide();
    try { const r = await send('POST', '/api/v1/chat/send', { ref: g.soul, kind: 'text', text }); t.messages = [...t.messages, ...(r.messages || [])]; }
    catch (e) { t.err = e.status === 409 ? '上一句还在回' : /no model configured/i.test(e.message) ? '还没选模型:到设置里选一个模型再聊' : '没发出去:' + e.message; t.messages = t.messages.slice(0, -1); }
    t.sending = false; chatSide();
  }

  // 节点内部 / 工具注册表:角色面换成角色的工具
  function withSoulTools(fn) {
    const keep = { ...TOOLS };
    for (const k of Object.keys(TOOLS)) delete TOOLS[k];
    Object.entries((SO.hooks && SO.hooks.tools) || {}).forEach(([k, v]) => { TOOLS[k] = { kind: 'tool', sync: !!v.sync, fields: '', validator: '', src: v.live ? 'engine' : '还没上线', doc: v.doc || '' }; });
    try { fn(); } finally { for (const k of Object.keys(TOOLS)) delete TOOLS[k]; Object.assign(TOOLS, keep); }
  }

  const _render = renderOrch;
  renderOrch = function () {
    if (!isSoul()) { for (const k of Object.keys(GRAPHS)) if (k.startsWith('soul:')) delete GRAPHS[k]; if (!G()) S.graph = Object.keys(GRAPHS)[0]; _render(); chrome(); return; }
    if (!SO.rows) { loadRows(); $('#s-orch').innerHTML = '<div class="ws"><div class="sub">读角色列表……</div></div>'; return; }
    if (!cur()) { $('#s-orch').innerHTML = `<div class="ws"><div class="ws-main"><div class="crumb"><div class="r"><span class="tag">角色</span><select class="btn" id="gsel"></select></div></div><div class="sub">${esc(SO.msg[SO.key] || SO.err || (SO.rows.length ? '选一个角色' : '还没有可以编排的角色'))}</div></div></div>`; chrome(); return; }
    GRAPHS[SO.key] = cur(); S.graph = SO.key;
    if (cur().iwWorld !== curWorld()) refreshIw(SO.key);   // 别的角色看的时候换过世界
    if (!cur().nodes[S.node]) S.node = cur().start;
    _render(); chrome(); chatSide();
    if (SO.layer === 'ambient') ambient();
    if (SO.layer === 'stickers') stickers();
  };

  // 专属表情(S5):图(PNG)+ 含义(四语)+ 什么时候发 —— 小手机的表情面板显示含义,角色回话时照「什么时候发」挑
  const LG = ['zh', 'en', 'ja', 'ko'];
  async function loadStk(ref) { const k = SO.stk[ref] = { ...(SO.stk[ref] || {}), busy: true }; try { Object.assign(k, await V3.j(`/api/v1/souls/stickers?ref=${encodeURIComponent(ref)}`), { msg: '' }); } catch (e) { k.msg = '读不到:' + e.message; k.stickers = k.stickers || []; } k.busy = false; stickers(); }
  function stickers() {
    const g = cur(), b = document.getElementById('board'); if (!g || !b || SO.layer !== 'stickers') return;
    const k = SO.stk[g.soul]; if (!k) { loadStk(g.soul); return; }
    const rows = k.stickers || [], ro = k.writable === false;
    b.innerHTML = `<div class="flow scroll" style="overflow:auto"><div class="tag">stickers/*.png · stickers.json</div><h2 class="h1" style="font-size:26px">专属表情</h2>
      <p class="sub">这个角色自己的表情:小手机的「TA 专属」页签里列出来,角色回话时也会发(模型看得到每张的含义和什么时候发)。图只用 GPT 生成或作者上传的 PNG。</p>
      ${k.msg || ro ? `<div class="note" style="position:relative;margin:10px 0">${esc(k.msg || '内置模板只读:先在 Template 页复制成自己的')}</div>` : ''}
      <table class="t" style="margin-top:12px"><tr><th></th><th>id</th>${LG.map(l => `<th>含义 · ${l}</th>`).join('')}<th>什么时候发</th><th></th></tr>
      ${rows.map(r => `<tr><td>${r.url ? `<img src="${esc(V3.url(r.url))}" alt="" style="width:44px;height:44px;object-fit:contain">` : ''}</td><td class="mono">${esc(r.id)}</td>
        ${LG.map(l => `<td><input class="cell" data-sol="${esc(r.id)}:${l}" value="${esc((r.label && typeof r.label === 'object' ? r.label[l] : l === 'zh' ? r.label : '') || '')}" style="width:96px" ${ro ? 'disabled' : ''}></td>`).join('')}
        <td><input class="cell" data-sowhen="${esc(r.id)}" value="${esc(r.when || '')}" style="width:100%" ${ro ? 'disabled' : ''}></td><td>${ro ? '' : `<button class="chip" data-sostkdel="${esc(r.id)}">移走</button>`}</td></tr>`).join('') || `<tr><td colspan="8" class="muted">还没有专属表情</td></tr>`}</table>
      ${ro ? '' : `<div class="row" style="gap:8px;margin-top:12px;align-items:center"><input class="cell" id="sostkid" placeholder="新表情的 id(a-z 0-9 _ -)" style="width:200px"><label class="btn">选一张 PNG 上传<input type="file" accept="image/png" id="sostkfile" hidden></label></div>`}</div>`;
  }
  async function stkMeta(id) {
    const g = cur(), k = SO.stk[g.soul]; if (!k) return;
    const label = Object.fromEntries(LG.map(l => [l, ((document.querySelector(`[data-sol="${CSS.escape(id)}:${l}"]`) || {}).value || '').trim()]));
    const when = ((document.querySelector(`[data-sowhen="${CSS.escape(id)}"]`) || {}).value || '').trim();
    try { Object.assign(k, await send('POST', '/api/v1/souls/stickers/meta', { ref: g.soul, id, label, when }), { msg: '存好了' }); } catch (e) { k.msg = '没存成:' + e.message; }
    const n = document.querySelector('#board .flow .note'); if (n) n.textContent = k.msg; else stickers();
  }

  // 简单世界观(S3,core/soul_ambient):tick 在哪儿发生 —— 复刻原来的世界 / 自动生成 / 自己写;世界里的角色只改这个世界
  const SLOT = { morning: '早上', afternoon: '下午', evening: '傍晚', night: '夜里' };
  const SRC = { replicated: '复刻自原来的世界', generated: '自动生成', authored: '自己写的' };
  async function loadAmb(ref, how) {
    const a = SO.amb[ref] = { ...(SO.amb[ref] || {}), busy: how || 'read', msg: '' }; ambient();
    try {
      if (how === 'generate') { a.world = (await send('POST', '/api/v1/souls/ambient/generate', { ref })).world; a.dirty = true; a.msg = '生成好了 · 还没保存'; }
      else { const r = await V3.j(`/api/v1/souls/ambient?ref=${encodeURIComponent(ref)}${how === 'replicate' ? '&replicate=1' : ''}`); a.world = r.world; a.layers = r.layers; a.can = r.can_replicate; a.dirty = how === 'replicate'; if (how === 'replicate') a.msg = '复刻好了 · 还没保存'; }
    } catch (e) { a.msg = (how === 'generate' ? '没生成:' : '读不到:') + e.message; }
    a.busy = ''; ambient();
  }
  function ambient() {
    const g = cur(), b = document.getElementById('board'); if (!g || !b || SO.layer !== 'ambient') return;
    const a = SO.amb[g.soul];
    if (!a) { loadAmb(g.soul); return; }
    const w = a.world, ro = g.edit && !g.edit.writable;
    const places = (w && w.places) || [];
    const opt = v => places.map(p => `<option value="${esc(p.id)}" ${p.id === v ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
    b.innerHTML = `<div class="flow scroll" style="overflow:auto"><div class="row" style="align-items:flex-end;gap:12px;flex-wrap:wrap"><div><div class="tag">ambient/world.json · ${esc(w ? SRC[w.source] || w.source : '还没有')}</div><h2 class="h1" style="font-size:26px">简单世界观</h2>
      <p class="sub">角色自由行动(tick)时住在这里:一段设定 · 常去的地方 · 作息 · 认识的人。不是一个世界:不跑世界主持,只给 tick 读。</p></div>
      <div class="row" style="margin-left:auto;gap:8px">${a.can ? `<button class="btn" data-soamb="replicate" ${a.busy ? 'disabled' : ''}>复刻原来的世界</button>` : ''}<button class="btn" data-soamb="generate" ${a.busy ? 'disabled' : ''}>${a.busy === 'generate' ? '生成中……' : '自动生成(会花额度)'}</button>
      <button class="btn ${a.dirty && !ro ? 'p' : ''}" data-soamb="save" ${a.dirty && !ro && w ? '' : 'disabled'}>保存${g.edit ? (g.edit.to === 'library' ? ' · 角色库' : ' · 只改这个世界') : ''}</button></div></div>
      ${a.msg || ro ? `<div class="note" style="position:relative;margin:10px 0">${esc(a.msg || '内置模板只读:先在 Template 页复制成自己的')}</div>` : ''}
      ${!w ? `<div class="well" style="padding:16px;margin-top:14px">${a.busy ? '读……' : '这个角色还没有世界观。角色库的角色没有原来的世界可以复刻:点「自动生成」,或者直接在下面写。'}<div class="row" style="margin-top:10px"><button class="btn" data-soamb="blank">从空白开始写</button></div></div>` : `
      <div class="tag" style="margin-top:16px">设定</div><textarea class="cell" data-sow="setting" rows="3" style="width:100%">${esc(w.setting)}</textarea>
      <div class="tag" style="margin-top:14px">常去的地方 · 第一个是家(最多 6 个)</div>
      <table class="t"><tr><th>id</th><th>名字</th><th>一句话</th><th></th></tr>${places.map((p, i) => `<tr><td><input class="cell" data-sop="${i}:id" value="${esc(p.id)}" style="width:110px"></td><td><input class="cell" data-sop="${i}:name" value="${esc(p.name)}"></td><td><input class="cell" data-sop="${i}:summary" value="${esc(p.summary)}" style="width:100%"></td><td><button class="chip" data-sodel="places:${i}">移走</button></td></tr>`).join('')}</table>
      ${places.length < 6 ? '<button class="btn" data-soadd="places" style="margin-top:6px">+ 地方</button>' : ''}
      <div class="tag" style="margin-top:14px">作息</div>
      <table class="t"><tr><th>时段</th><th>在哪</th><th>在做什么</th></tr>${Object.keys(SLOT).map(k => { const r = (w.routine || []).find(x => x.at === k) || { place: '', doing: '' };
        return `<tr><td>${SLOT[k]}</td><td><select class="btn" data-sor="${k}:place"><option value="">—</option>${opt(r.place)}</select></td><td><input class="cell" data-sor="${k}:doing" value="${esc(r.doing)}" style="width:100%" placeholder="tick 时模型会照着这个来"></td></tr>`; }).join('')}</table>
      <div class="tag" style="margin-top:14px">认识的人(最多 4 个)</div>
      <table class="t"><tr><th>名字</th><th>是什么人</th><th></th></tr>${(w.people || []).map((x, i) => `<tr><td><input class="cell" data-sopp="${i}:name" value="${esc(x.name)}"></td><td><input class="cell" data-sopp="${i}:line" value="${esc(x.line)}" style="width:100%"></td><td><button class="chip" data-sodel="people:${i}">移走</button></td></tr>`).join('')}</table>
      ${(w.people || []).length < 4 ? '<button class="btn" data-soadd="people" style="margin-top:6px">+ 人</button>' : ''}`}</div>`;
  }
  function ambEdit(el) {
    const g = cur(), a = g && SO.amb[g.soul], w = a && a.world; if (!w) return false;
    const d = el.dataset;
    if (d.sow) w[d.sow] = el.value;
    else if (d.sop) { const [i, k] = d.sop.split(':'); w.places[+i][k] = el.value; }
    else if (d.sopp) { const [i, k] = d.sopp.split(':'); w.people[+i][k] = el.value; }
    else if (d.sor) { const [at, k] = d.sor.split(':'); let r = (w.routine = w.routine || []).find(x => x.at === at); if (!r) w.routine.push(r = { at, place: '', doing: '' }); r[k] = el.value; }
    else return false;
    if (w.source !== 'authored') w.source = w.source || 'authored';
    a.dirty = true; a.msg = '';
    const sv = document.querySelector('[data-soamb=save]'); if (sv && !(g.edit && !g.edit.writable)) { sv.disabled = false; sv.classList.add('p'); }
    return true;
  }
  // 角色面:触发条件只列引擎读的(hooks.on),画完换回世界的
  function withSoulTrig(fn) {
    const keep = { ...TRIG };
    for (const k of Object.keys(TRIG)) delete TRIG[k];
    Object.keys((SO.hooks && SO.hooks.on) || {}).forEach(k => { TRIG[k] = STRIG[k] || k; });
    try { fn(); } finally { for (const k of Object.keys(TRIG)) delete TRIG[k]; Object.assign(TRIG, keep); }
  }
  const _graph = drawGraph;
  drawGraph = function () {
    if (!isSoul() || !cur()) {   // 世界面:加节点的按钮里不出角色的节点种类
      _graph.apply(this, arguments);
      document.querySelectorAll('#board .tb [data-add]').forEach(x => { if (x.dataset.add in SKIND) x.remove(); }); return; }
    const g = cur();
    for (const n of Object.values(g.nodes)) if (!n.soul) Object.assign(n, soulNode(n.kind in kinds() ? n.kind : 'chat', { title: n.title }, 0), { x: n.x, y: n.y });   // 刚加的节点:照 hooks 补步骤 / 参数
    withSoulTrig(() => _graph.apply(this, arguments));
    document.querySelectorAll('#board .tb [data-add]').forEach(x => { const k = kinds()[x.dataset.add]; if (!k || k.addable === false) x.remove(); });
    const note = document.querySelector('#board .ednote'); if (note) note.innerHTML = '拖节点移动 · 从右边小圆点拖到另一个节点 = 新建迁移<small>直聊 = 小手机收到一句话怎么回 · 自由行动 = 前台 tick(触发:前台 tick / 闲着 N 分钟)· 记忆整理 = 每 N 次 tick 一次 · 世界里那一拍 = 它的世界怎么叫它</small>';
    paintBar(); relint();
  };
  const _node = drawNode;
  drawNode = function () {
    if (!isSoul() || !cur()) { _node.apply(this, arguments); return; }
    withSoulTools(() => _node.apply(this, arguments));
    const g = cur(), id = g.nodes[S.node] ? S.node : g.start, n = g.nodes[id];
    if (n.kind === 'in_world') { inWorld(g); return; }
    const R = (kinds()[n.kind] || {}).ranges || {};
    document.querySelectorAll('#board .well dl.kv dt').forEach(dt => {   // 参数按名字接(不靠顺序);prompt 换成多行
      const k = dt.textContent, el = dt.nextElementSibling && dt.nextElementSibling.querySelector('input'); if (!el || !(k in (n.knobs || {}))) return;
      dt.title = KNOB_LBL[k] || k;
      if (R[k]) el.placeholder = `${R[k][0]}–${R[k][1]}`;
      let box = el;
      if (k === 'prompt') { box = document.createElement('textarea'); box.className = 'cell'; box.rows = 5; box.style.width = '100%'; box.placeholder = '空 = 引擎默认(soul_tick.PROMPT);可用 {name} {slot} {clock} {lang}'; box.value = n.knobs[k] || ''; el.replaceWith(box); }
      box.oninput = () => { n.knobs[k] = box.value; relint(); };
    });
    const ks = Object.keys(n.knobs || {});
    const nt = document.querySelector('#board .well .note'); if (nt) nt.innerHTML = `${ks.length ? ks.map(k => `${esc(k)} = ${esc(KNOB_LBL[k] || k)}`).join(' · ') : '这个节点没有参数'}<small>改完回「状态机图」写回</small>`;
  };
  // 世界里那一拍:这个角色在它世界里的真实设置(soul_orchestration.in_world)· 变体可改,写进世界的 engine 配置(只改这个世界)
  function inWorld(g) {
    const w = g.iw, well = document.querySelector('#board .well'); if (!well) return;
    if (!w) { well.innerHTML = '<div class="tag">世界里那一拍</div><div class="sub">这个角色不在任何世界里</div>'; return; }
    const ro = !w.writable, pick = w.pick ?? (w.per_soul || '');
    well.innerHTML = `<div class="tag">世界 ${esc(w.title)} · ${esc(w.template)} · 回合 ${esc(w.mode)}${w.v3 ? '' : '(不是 v3:角色一律 legacy)'}</div>
      <dl class="kv"><dt>变体</dt><dd><select class="btn" data-soiw ${ro ? 'disabled' : ''}><option value="" ${pick ? '' : 'selected'}>跟世界默认(${esc(w.default_variant)})</option>${w.variants.map(v => `<option value="${esc(v)}" ${pick === v ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></dd>
        <dt>现在跑的</dt><dd class="mono" data-soiwnow>${esc(w.variant)} · ${esc(w.source)}</dd><dt>写在</dt><dd class="mono" style="font-size:12px">template.json → pack.engine.${esc(w.key)}</dd></dl>
      <table class="t" style="margin-top:10px"><tr><th>depth</th><th>这一拍怎么跑</th></tr>${w.depth.map(r => `<tr><td>${esc(DEPTH_LBL[r.depth] || r.depth)} <span class="mono muted">${esc(r.depth)}</span></td><td class="mono" style="font-size:12px">${esc(r.path)}</td></tr>`).join('')}</table>
      <div class="tag" style="margin-top:10px">用到的提示词(只列名字;私有层的不显示正文)</div>
      ${w.prompts.map(p => `<div class="sub" style="font-size:12px"><b>${esc(p.for === 'away' ? '不在眼前' : p.for)}</b> · ${esc(p.table)}:${p.keys.map(k => `<span class="mono">${esc(k)}</span>${p.private.includes(k) ? '<span class="tag">私有层</span>' : ''}`).join(' · ')}</div>`).join('')}
      <div class="row" style="gap:8px;margin-top:12px;align-items:center"><button class="btn ${!ro && pick !== (w.per_soul || '') ? 'p' : ''}" data-soiwsave ${ro || pick === (w.per_soul || '') ? 'disabled' : ''}>写回 · 只改世界 ${esc(w.template)}</button>
        <span class="tag" data-soiwmsg>${esc(w.msg || (ro ? '内置模板只读:先在 Template 页复制成自己的' : ''))}</span></div>`;
    const drop = document.getElementById('drop'); if (drop) { drop.parentElement.style.display = 'none'; drop.parentElement.parentElement.style.gridTemplateColumns = '1fr'; }   // 世界那一拍不调角色的工具
  }
  async function saveInWorld() {
    const g = cur(), w = g && g.iw; if (!w) return;
    w.msg = '写回中……'; inWorld(g);
    try { const r = await send('POST', '/api/v1/souls/in_world', { ref: g.soul, variant: w.pick ?? '', world: w.template }); g.iw = { ...r.in_world, msg: `写进世界 ${r.id} · 下一回合按 ${r.in_world.variant} 跑` }; }
    catch (e) { w.msg = '没写成:' + e.message; }
    inWorld(g);
  }
  const _tools = drawTools;
  drawTools = function () { if (!isSoul() || !cur()) { _tools.apply(this, arguments); return; } withSoulTools(() => _tools.apply(this, arguments)); };

  document.addEventListener('click', e => {
    if (S.screen !== 'orch') return;
    const q = s => e.target.closest(s); let t;
    if ((t = q('[data-somode]'))) { const m = t.dataset.somode; if (m === SO.mode) return; SO.mode = m; SO.layer = ''; if (m === 'world') { S.graph = Object.keys(GRAPHS).find(k => !k.startsWith('soul:')) || S.graph; S.node = G() ? G().start : S.node; } S.edge = null; S.chat = null; S.layer = 'graph'; render(); return; }   // render():顶栏的当前世界选择器跟着重画
    if (!isSoul()) return;
    if (q('[data-sopick]')) { SO.open = !SO.open; renderOrch(); return; }
    if ((t = q('[data-sotab]'))) { SO.tab = t.dataset.sotab; renderOrch(); return; }
    if ((t = q('[data-soref]'))) { openSoul(t.dataset.soref); return; }
    if (q('[data-sosave]')) { save(); return; }
    if (q('[data-soiwsave]')) { saveInWorld(); return; }
    if ((t = q('[data-solayer]'))) { SO.layer = t.dataset.solayer; renderOrch(); return; }
    if ((t = q('[data-sostkdel]'))) { const g = cur(); send('POST', '/api/v1/souls/stickers/remove', { ref: g.soul, id: t.dataset.sostkdel }).then(r => { Object.assign(SO.stk[g.soul], r); stickers(); }).catch(e => { SO.stk[g.soul].msg = e.message; stickers(); }); return; }
    if (q('.crumb [data-layer]')) SO.layer = '';
    if ((t = q('[data-soamb]'))) { const g = cur(), how = t.dataset.soamb, a = SO.amb[g.soul];
      if (how === 'save') { (async () => { try { const r = await send('POST', '/api/v1/souls/ambient', { ref: g.soul, world: a.world }); a.world = r.world; a.dirty = false; a.msg = r.to === 'library' ? '存进角色库了' : `存进世界 ${r.id}(只改这个世界)`; } catch (e) { a.msg = '没存成:' + e.message; } ambient(); })(); return; }
      if (how === 'blank') { a.world = { schema: 'worldlines.soul-ambient/1', source: 'authored', setting: '', places: [{ id: 'home', name: '家', summary: '' }], routine: [], people: [], clock: 'real' }; a.dirty = true; ambient(); return; }
      loadAmb(g.soul, how); return; }
    if ((t = q('[data-soadd]'))) { const a = SO.amb[cur().soul], w = a.world; if (t.dataset.soadd === 'places') w.places.push({ id: 'place' + (w.places.length + 1), name: '', summary: '' }); else (w.people = w.people || []).push({ name: '', line: '' }); a.dirty = true; ambient(); return; }
    if ((t = q('[data-sodel]'))) { const [k, i] = t.dataset.sodel.split(':'), a = SO.amb[cur().soul]; a.world[k].splice(+i, 1); a.dirty = true; ambient(); return; }
    if (q('#sosend')) { const v = ($('#soin') || {}).value; if (v && v.trim()) say(v.trim()); return; }
    if (SO.open && !q('.sopick')) { SO.open = false; renderOrch(); }
  }, true);
  document.addEventListener('input', e => { if (isSoul() && SO.layer === 'ambient' && ambEdit(e.target)) return; if (isSoul() && e.target.id === 'soq') { SO.q = e.target.value; const p = document.querySelector('.sopick .rows'); if (p) { const at = e.target.selectionStart; renderOrch(); const i = $('#soq'); if (i) { i.focus(); i.setSelectionRange(at, at); } } } });
  document.addEventListener('keydown', e => { if (isSoul() && e.key === 'Enter' && e.target.id === 'soin') { const v = e.target.value.trim(); if (v) say(v); } });
  document.addEventListener('change', e => {
    if (isSoul() && S.screen === 'orch' && ['pon', 'pval', 'pgd'].includes(e.target.id)) relint();
    if (isSoul() && e.target.matches && e.target.matches('[data-soiw]')) { const g = cur(); if (g && g.iw) { g.iw.pick = e.target.value; g.iw.msg = ''; inWorld(g); } return; }
    if (!isSoul() || SO.layer !== 'stickers') return;
    const d = e.target.dataset || {};
    if (d.sol || d.sowhen) { stkMeta((d.sol || '').split(':')[0] || d.sowhen); return; }
    if (e.target.id === 'sostkfile' && e.target.files[0]) {
      const g = cur(), k = SO.stk[g.soul], id = (($('#sostkid') || {}).value || e.target.files[0].name.replace(/\.png$/i, '')).trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_').slice(0, 32);
      fetch(V3.url(`/api/v1/souls/stickers?ref=${encodeURIComponent(g.soul)}&id=${encodeURIComponent(id)}`), { method: 'POST', credentials: 'include', body: e.target.files[0] })
        .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || r.status); Object.assign(k, j, { msg: `上传好了:${id}` }); }).catch(err => { k.msg = '没传上:' + err.message; }).finally(stickers);
    }
  });
})();
