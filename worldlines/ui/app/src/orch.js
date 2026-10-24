/* 编排台:图上的草稿也要知道「引擎跑不跑得了」(10-07)。
   引擎只在 4 处查图(拍与拍之间的推进 · 按地点类型进层 · 层的切换 / 退出 op · 阶段变量);别处新加的边、
   背后没有玩法层的新节点,画得出来但没人执行。每次改完把草稿转回引擎的图(nodes 字典 · edges 带 on 对象),
   送 POST /api/v1/local/templates/<id>/graph-lint,跑不了的节点 / 连线标红,角上列出原因。只读,不写文件。 */
(() => {
  const O = { sig: {}, lint: {}, busy: {}, timer: null };
  window.ORCHLINT = O;
  const KIND_BACK = { loop: 'loop', mode: 'mode', one: 'one_shot', tick: 'loop' };
  const ON_BACK = { here: 'here_class' };

  // 守卫:「变量 比较 值」或引擎的 JSON → 边的 when;空 = 没有守卫;看不懂 = null(不写回)
  function guard(t) {
    t = String(t || '').trim(); if (!t) return undefined;
    if (/^[[{]/.test(t)) { try { const w = JSON.parse(t); return Array.isArray(w) || (w && typeof w === 'object') ? w : null; } catch { return null; } }
    const m = t.match(/^([\w.:-]+)\s*(==|!=|<=|>=|<|>)\s*(.+)$/); if (!m) return null;
    let v = m[3].trim(); try { v = JSON.parse(v); } catch { v = v.replace(/^['"「]|['"」]$/g, ''); }
    return [{ var: m[1], [m[2]]: v }];
  }
  window.ORCH_guard = guard;
  const onOf = (e, was) => {
    const k = ON_BACK[e.on] || e.on || 'always', v = e.val === '' || e.val == null ? true : e.val;
    return { [k]: was && k in was && String(was[k]) === String(v) ? was[k] : v };   // 没改的值保留引擎原来的类型(true / 数字)
  };
  // 改过没有:toUi 记下引擎读来时的样子(合并显示的几条不能改,没有 orig)
  const changed = e => e.engine && e.orig !== undefined && JSON.stringify([e.on, e.val, e.guard || '']) !== e.orig;
  // 编排台的图 → 引擎的图:没动过的节点 / 边原样用引擎那份(raw);改过的边和新加的边按界面上的触发条件、值、守卫拼(10-17:以前改了也被 raw 盖掉)
  function toEngine(g) {
    const raw = g.raw || { nodes: {}, edges: [] };
    const nodes = {};
    for (const [id, n] of Object.entries(g.nodes)) nodes[id] = raw.nodes[id] ? raw.nodes[id] : { kind: KIND_BACK[n.kind] || 'loop', title: n.title };
    const pairs = new Set(g.edges.filter(e => e.engine && !changed(e)).map(e => e.from + '>' + e.to));
    const to = e => e.to === '@return' || e.return_to || nodes[e.to];
    // 「从任何节点」的边(from: *,gate / 地点类进层 / 遭遇)图上画不出来:原样带上 —— 以前一写回就全丢了(10-17:进战斗、进地穴都没了)
    const edges = (raw.edges || []).filter(e => (e.from === '*' ? to(e) : pairs.has(e.from + '>' + (e.to === '@return' || e.return_to ? '@return' : e.to)) && nodes[e.from] && to(e)));
    const byId = Object.fromEntries((raw.edges || []).map(e => [e.id, e]));
    g.edges.filter(e => !e.engine || changed(e)).forEach(e => {
      const was = e.engine ? byId[e.id] || {} : {}, w = guard(e.guard);
      const out = { ...was, id: e.id, from: e.from, to: e.to, on: onOf(e, was.on) };
      delete out.when; if (w) out.when = w;
      edges.push(out);
    });
    // 出状态是清算节点的参数(10-11 引擎说明):改了就写在节点上;图上的 state 只是引擎的只读报告,不回传
    if (g.stateMode && nodes.resolve) nodes.resolve = { ...nodes.resolve, state: g.stateMode };
    for (const [nid, sp] of Object.entries(g.stepParams || {})) {   // S2:这一拍的设置(草稿)写在节点的 step_params
      if (!nodes[nid]) continue;
      const n = { ...nodes[nid] };
      if (Object.keys(sp).length) n.step_params = sp; else delete n.step_params;
      nodes[nid] = n;
    }
    const out = { ...raw, nodes, edges, start: nodes[g.start] ? g.start : (nodes.resolve ? 'resolve' : Object.keys(nodes)[0]) };
    delete out.state;
    return out;
  }
  const sigOf = g => JSON.stringify([Object.keys(g.nodes).sort(), g.edges.map(e => [e.id, e.from, e.to, e.on, e.val, e.guard || '']), g.start, g.stateMode || '', g.stepParams || null]);
  // 清算拍怎么出状态(10-11 引擎 ENGINE-NOTE-STATE-MODES):两种编排模式,二选一
  const STATE = { pseudo: [T('伪代码 → JSON'), T('先写正文,再用一次大模型写伪代码,引擎解析成变更')],
                  jev: [T('文字直出 → Jev'), T('正文后顺带用文字写变化(玩家看不到),Jev 按注册工具逐句填;没把握的句子再交给伪代码')] };
  const stateNow = g => g.stateMode || (g.raw && g.raw.nodes && g.raw.nodes.resolve && g.raw.nodes.resolve.state) || (g.state && g.state.asked) || '';
  const WHYS = { no_fast_jev: T('这台机器没有 Jev,实际按伪代码跑'), unknown: T('这个值引擎不认识,实际按伪代码跑') };

  function schedule() {
    clearTimeout(O.timer);
    O.timer = setTimeout(check, 350);
  }
  async function check() {
    const key = S.graph, g = GRAPHS[key];
    if (!g || !g.raw || !g.tpl) return;
    const sig = sigOf(g);
    if (O.sig[key] === sig || O.busy[key]) return;
    O.busy[key] = true;
    try {
      const r = await fetch(V3.url(`/api/v1/local/templates/${encodeURIComponent(g.tpl)}/graph-lint`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ graph: toEngine(g) }) });
      const d = await r.json().catch(() => ({}));
      O.lint[key] = r.ok ? d.lint || [] : [{ code: 'orch.lint_failed', level: 'warn', msg: d.error || T('检查失败 {s}', { s: r.status }) }];
      O.sig[key] = sig;
    } catch (e) { O.lint[key] = [{ code: 'orch.lint_failed', level: 'warn', msg: String(e.message || e) }]; }
    O.busy[key] = false;
    if (S.screen === 'orch' && S.graph === key) mark();
    if (GRAPHS[key] && sigOf(GRAPHS[key]) !== sig) schedule();   // 检查途中又改了(加节点 / 连线):再查一次,否则这次改动一直没人查(10-17)
  }
  const WHY = { 'orch.edge_unrunnable': T('这条连线引擎不会走'), 'orch.node_no_impl': T('这个节点背后没有玩法层'), 'orch.phase_var': T('阶段变量没注册'), 'orch.lint_failed': T('没检查成') };
  // 消息以「id:」开头(节点 id 或边 id),据此把对应的节点 / 标签标红
  function mark() {
    const b = document.getElementById('board'); if (!b) return;
    b.querySelectorAll('.orchwarn').forEach(x => x.classList.remove('orchwarn'));
    const box = b.querySelector('.orchlint'); if (box) box.remove();
    const rows = O.lint[S.graph] || [];
    for (const w of rows) {
      const id = String(w.msg || '').split(':')[0].trim();
      b.querySelectorAll(`[data-n="${CSS.escape(id)}"],[data-e="${CSS.escape(id)}"]`).forEach(x => x.classList.add('orchwarn'));
    }
    if (!rows.length) return;
    b.insertAdjacentHTML('beforeend', `<div class="orchlint glass"><b>${T('引擎跑不了')} · ${rows.length}</b>${rows.map(w => `<div><span class="dot warn"></span>${esc(WHY[w.code] || w.code)}<small>${esc(w.msg)}</small></div>`).join('')}<small class="tag">${T('只是警告:局照样能玩,这些部分不会被执行')}</small></div>`);
  }
  // 写回(1.0 带创作写回,10-08):把编排台上这张图交给模板的 set_orchestration(存成相对玩法包默认图的补丁)
  O.writable = {}; O.msg = {};
  async function writable(tid) {
    if (O.writable[tid] !== undefined) return O.writable[tid];
    const u = await V3.j(`/api/v1/local/templates/${encodeURIComponent(tid)}/ui`).catch(() => null);
    return (O.writable[tid] = !!(u && u.writable));
  }
  async function save() {
    const key = S.graph, g = GRAPHS[key]; if (!g || !g.tpl || !g.raw || O.saving) return;
    const bad = g.edges.filter(e => e.guard && guard(e.guard) === null).map(e => e.id);
    if (bad.length) { O.msg[key] = T('守卫看不懂({bad}):写成「变量 比较 值」或引擎的 JSON', { bad: bad.join('、') }); mark(); saveBar(); return; }
    // 先说「写回中」(10-17:以前要等 /ui 回来、写完重画才有字,引擎忙时像没点上,会被再点一次)
    O.saving = true; O.msg[key] = T('写回中……'); mark(); saveBar();
    try { await doSave(key, g); } finally { O.saving = false; }
    if (O.after) { const f = O.after; O.after = null; f(); }   // 写回中点的「恢复默认」:等这次写完再做(10-21:被吞掉、又被这次读回的图盖掉)
  }
  async function doSave(key, g) {
    if (!(await writable(g.tpl))) { O.msg[key] = T('模板 {tpl} 是内置的(只读):先在 Template 页复制成自己的模板再改', { tpl: g.tpl }); mark(); saveBar(); return; }
    const r = await fetch(V3.url(`/api/v1/local/templates/${encodeURIComponent(g.tpl)}/ops`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ops: [{ op: 'set_orchestration', graph: toEngine(g) }] }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.ok) { O.msg[key] = T('没写成:') + ((d.refused || []).map(x => x.why).join(';') || d.error || r.status); mark(); saveBar(); return; }
    const a = (d.applied || [])[0] || {};
    const fresh = await V3.j(`/api/v1/play/engine/graph?template=${encodeURIComponent(g.tpl)}`).catch(() => null);
    if (fresh && fresh.graph && window.ORCH_toUi) { const keepTitle = g.title; GRAPHS[key] = window.ORCH_toUi(fresh.graph, keepTitle, g.tpl, fresh.default); }
    O.sig[key] = null; O.msg[key] = T('写回模板 {tpl}:{to} · 下一局开始按这张图走', { tpl: g.tpl, to: a.to || T('已保存') });
    delete O.hooks[g.tpl];   // 设置的值和出处重读(写进图的那些现在来自「编排图」)
    if (S.screen === 'orch') renderOrch();
  }
  function saveBar() {
    const b = document.getElementById('board'), g = GRAPHS[S.graph]; if (!b || !g || !g.tpl || !g.raw) return;
    const old = b.querySelector('.orchsave'); if (old) old.remove();
    if (g.savedSig === undefined) g.savedSig = sigOf(g);   // 刚从引擎读来的样子
    const dirty = sigOf(g) !== g.savedSig;
    const sel = g.nodes[S.node] && !S.edge && Object.keys(g.nodes).length > 1 ? S.node : '';
    const now = stateNow(g);
    const flow = S.layer === 'node' && b.querySelector('.flow');   // 节点页:放在内容上方,不压住标题
    (flow || b).insertAdjacentHTML(flow ? 'afterbegin' : 'beforeend', `<div class="orchsave glass" ${flow ? 'style="position:static;transform:none;margin:0 0 14px;width:max-content;max-width:100%;flex-wrap:wrap"' : ''}><span class="tag">${esc(O.msg[S.graph] || (dirty ? T('图上有改动,还没写回') : T('和模板里的一致')))}</span>
      ${g.nodes.resolve ? `<span class="tag" title="${T('双击清算节点改')}">${T('出状态:')}${esc(now ? STATE[now][0] : T('按引擎配置'))}${g.state && g.state.why && !g.stateMode ? '(' + esc(WHYS[g.state.why] || g.state.why) + ')' : ''}</span>` : ''}
      ${sel ? `<button class="btn" data-onodedel="${esc(sel)}">${T('删除节点「{t}」', { t: esc(g.nodes[sel].title) })}</button>` : ''}
      ${g.def ? `<button class="btn" data-orestore>${T('恢复默认')}</button>` : ''}
      <button class="btn ${dirty ? 'p' : ''}" data-orchsave ${dirty ? '' : 'disabled'}>${T('写回模板 {tpl}', { tpl: esc(g.tpl) })}</button></div>`);
  }
  document.addEventListener('click', e => {
    if (S.screen !== 'orch') return;
    if (e.target.closest('[data-orchsave]')) { save(); return; }
    const g = GRAPHS[S.graph]; if (!g) return;
    const st = e.target.closest('[data-ostate]');
    if (st) { const v = st.dataset.ostate, cur = (g.raw && g.raw.nodes.resolve && g.raw.nodes.resolve.state) || ''; g.stateMode = v === cur ? '' : v; renderOrch(); return; }
    const del = e.target.closest('[data-onodedel]');
    if (del) {   // 删节点(10-11):连到它的边一起删;删的是起点就从清算开始 —— 删掉商量拍 = 关掉商量拍
      const id = del.dataset.onodedel; delete g.nodes[id];
      g.edges = g.edges.filter(x => x.from !== id && x.to !== id);
      if (g.start === id) g.start = g.nodes.resolve ? 'resolve' : Object.keys(g.nodes)[0];
      S.node = g.start; S.edge = null; S.chat = null; renderOrch(); return;
    }
    if (e.target.closest('[data-orestore]') && g.def && window.ORCH_toUi) {   // 恢复默认:写回和玩法包默认一样的图,覆盖自动去掉
      const key = S.graph
      const restore = () => { const cur = GRAPHS[key]; if (!cur || !cur.def) return; GRAPHS[key] = window.ORCH_toUi(cur.def, cur.title, cur.tpl, cur.def); GRAPHS[key].savedSig = null; if (S.graph === key) S.node = GRAPHS[key].start; save(); };
      if (O.saving) { O.after = restore; return; }
      restore();
    }
  });
  function stateBox(g) {
    const now = stateNow(g), why = g.state && g.state.why;   // why 是引擎对「实际跑的」的说明
    return `<div class="well orchstate" style="padding:14px 16px;margin-top:16px"><div class="tag">${T('出状态 · 清算拍怎么把正文变成状态变更(二选一)')}</div>
      <div class="row" style="gap:8px;margin-top:8px;flex-wrap:wrap">${Object.entries(STATE).map(([k, [t, d]]) => `<button class="chip ${now === k ? 'solid' : ''}" data-ostate="${k}" title="${esc(d)}">${t}</button>`).join('')}
      ${now ? '' : `<span class="muted" style="font-size:12.5px">${T('没选:按引擎配置跑')}</span>`}</div>
      ${why && !g.stateMode ? `<div class="note" style="position:relative;margin-top:8px">${esc(WHYS[why] || why)}</div>` : ''}
      <div class="sub" style="font-size:12.5px;margin-top:6px">${esc((STATE[now] || ['', ''])[1])}</div></div>`;
  }
  // 侧栏对话测试接真引擎(10-17 第 2 批 2.3):POST /templates/<id>/graph-test {lines, graph} —— 引擎在子进程里把这一串话
  // 在一次性临时局里从头跑一遍(假模型),回来的是每句走到的节点 · 调的工具 · 谁推进的 · 走过的边;画布上的草稿一起带上
  O.lines = {}; O.running = {}; O.sess = {};
  // ④ 10-17:默认用真模型(玩家自己配的那个,会花额度),可以切回假模型先空跑;记在本机
  O.model = (() => { try { return localStorage.getItem('wl-orch-model') === 'stub' ? 'stub' : 'real'; } catch { return 'real'; } })();
  O.sideHead = () => O.model === 'real'
    ? `<span class="seg osm"><button class="on" data-omodel="real">${T('真模型')}</button><button data-omodel="stub">${T('假模型')}</button></span><span class="tag" style="color:#f2c66b">${T('会花额度')}</span><div class="sub" style="font-size:12.5px">${T('用你在设置里选的模型,在一次性的临时局里真的跑一回合(每句一回合,几次模型调用);图上没写回的草稿一起带上。玩的这一局不受影响。')}</div>`
    : `<span class="seg osm"><button data-omodel="real">${T('真模型')}</button><button class="on" data-omodel="stub">${T('假模型')}</button></span><span class="tag" style="color:var(--lime,#c9f27a)">${T('不花额度')}</span><div class="sub" style="font-size:12.5px">${T('假模型空跑:每说一句,引擎在临时局里把这几句从头跑一遍,推进 / 进层 / 工具校验都是真的,回复是占位。')}</div>`;
  const live = g => !!(g && g.raw && g.tpl && !g.soul);
  const newSess = () => Math.random().toString(36).slice(2, 12);
  const _resetChat = resetChat;
  // 重画时 S.chat 被清空(删节点 / 别处重画)不等于「重来」:同一张图就接着这段对话(10-17:整跑时偶尔清掉了,第二句「定」
  // 只剩一句、推进不了);点「重来」/ 换模型 / 换图才真的从头
  // 诊断(已知问题,10-17 S1):整跑时偶尔有人在对话中途把 S.chat 清掉,第二句「定」就只剩一句。根因还没抓到;每次清空
  // (对话里已经有话时)记下是谁清的 —— ORCHLINT.chatDrops 和控制台的 ORCHDBG,e2e 结束时打出来。找到根因后去掉
  O.chatDrops = [];
  { let chat = S.chat;
    Object.defineProperty(S, 'chat', { configurable: true, enumerable: true, get: () => chat, set: v => {
      if (v === null && chat && (O.lines[S.graph] || []).length) {
        const row = { at: new Date().toISOString(), graph: S.graph, lines: (O.lines[S.graph] || []).length, stack: String(new Error().stack || '').split('\n').slice(2, 9).join(' | ') };
        O.chatDrops.push(row); console.warn('ORCHDBG chat cleared', JSON.stringify(row));
      }
      chat = v; } }); }
  resetChat = function () {
    if (S.chat === null && O.chatKey === S.graph && O.chatLog) { S.chat = O.chatLog; return; }
    _resetChat(); O.lines[S.graph] = []; O.sess[S.graph] = newSess(); O.chatKey = S.graph; O.chatLog = S.chat;
  };
  document.addEventListener('click', e => {
    const b = S.screen === 'orch' && e.target.closest('[data-omodel]'); if (!b) return;
    O.model = b.dataset.omodel; try { localStorage.setItem('wl-orch-model', O.model); } catch { /* storage off */ }
    resetChat(); renderOrch();   // 换模型 = 重新开始这段对话
  });
  const HUMAN = { no_model: T('还没选模型:到设置里选一个模型再测'), auth: T('模型的 key 不对或过期了:去设置里检查一下'), credits: T('额度不够了:充值或换一个模型'),
    timeout: T('模型太久没回(超时),再说一次试试'), model: T('模型这次出错了') };
  const _step = step;
  step = function (text) {
    const key = S.graph, g = GRAPHS[key];
    if (!live(g)) return _step(text);
    if (O.running[key]) { S.chat.push({ t: 'sys', h: `<span class="mono" style="color:var(--muted)">${T('上一句还在跑')}</span>` }); return; }
    const lines = O.lines[key] = [...(O.lines[key] || []), text];
    S.chat.push({ t: 'me', h: esc(text) });
    const msg = { t: 'sys', h: O.model === 'real' ? `<span class="dots">…</span> ${T('真模型在临时局里跑这一回合(会花额度)')}` : `<span class="dots">…</span> ${T('引擎在临时局里跑 {n} 句(假模型)', { n: lines.length })}` };
    S.chat.push(msg);
    run(key, g, lines, msg);
  };
  async function run(key, g, lines, msg) {
    O.running[key] = true;
    try {
      const real = O.model === 'real';
      if (real && !O.sess[key]) O.sess[key] = newSess();
      const r = await fetch(V3.url(`/api/v1/local/templates/${encodeURIComponent(g.tpl)}/graph-test`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines, graph: toEngine(g), ...(real ? { model: 'real', session: O.sess[key] } : {}) }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(HUMAN[d.error] ? `${HUMAN[d.error]}${d.error === 'model' && d.message ? ':' + d.message : ''}` : (d.message || d.error || `graph-test ${r.status}`));
      const st = (d.steps || [])[(d.steps || []).length - 1] || {}, nodes = st.nodes || [];
      const name = id => (g.nodes[id] && g.nodes[id].title) || id;
      const tools = Object.entries(st.tools || {}).filter(([, v]) => v.length).map(([k, v]) => `${esc(name(k))}:${v.map(esc).join(' ')}`).join(' · ');
      const by = st.advanced_by ? ` · ${T('推进:')}${esc(st.advanced_by)}` : '';
      const tok = real ? Object.values(st.usage || {}).length ? ` · ${(st.usage.total_tokens || 0)} tokens` : '' : '';
      msg.h = `<span class="go">● ${nodes.map(n => esc(name(n))).join(' → ') || esc(name(S.cur)) + T('(没动)')}</span>${by}${tools ? ` · ${T('调用')} <span class="ok">${tools}</span>` : ''}`
        + `<span class="call">${T('引擎')} graph-test · ${real ? `${T('真模型')}${tok}${d.ran > 1 ? ` · ${T('图改过或重新开始:重放了 {n} 句', { n: d.ran })}` : ''}` : T('边覆盖 {c} · 模型调用 {n} 次(假模型)', { c: esc((d.edges || {}).coverage || ''), n: (d.model_calls || []).length })}</span>`;
      if (real && st.reply) S.chat.splice(S.chat.indexOf(msg) + 1, 0, { t: 'human', h: esc(st.reply) });
      if (nodes.length) S.cur = nodes[nodes.length - 1];
      S.hit = real ? new Set([...(S.hit || []), ...((d.edges || {}).walked || [])]) : new Set((d.edges || {}).walked || []);
      S.liveEdge = null;
      O.last = d;
    } catch (e) {
      msg.h = `<span class="bad">${T('没跑成:')}${esc(e.message || e)}</span>`;
      O.lines[key] = lines.slice(0, -1);   // 这句不算,能再说一次
      if (O.model === 'real') O.sess[key] = newSess();   // 真模型那一局状态不明:下一句从头开
    }
    O.running[key] = false;
    if (S.screen === 'orch' && S.graph === key) { drawChat(); if (S.layer === 'graph') drawGraph(); }
  }
  // 「跑全套」:真引擎的图跑一套固定的几句(商量 → 定 → 清算 → 回到商量 → @主持),一次请求,报边覆盖
  document.addEventListener('click', e => {
    if (S.screen !== 'orch' || !e.target.closest('[data-orun]')) return;
    const key = S.graph, g = GRAPHS[key]; if (!live(g)) return;
    e.stopPropagation();
    if (O.running[key]) return;
    resetChat();
    const lines = O.lines[key] = ['我四处看看', '我去杂货铺买药', '定', '@dm 继续'];
    lines.forEach(x => S.chat.push({ t: 'me', h: esc(x) }));
    const msg = { t: 'agent', h: `<span class="dots">…</span> ${T('引擎在临时局里跑全套(假模型)')}` };
    S.chat.push(msg);
    renderOrch();
    run(key, g, lines, msg).then(() => {
      const d = O.last; if (!d || msg.h.includes(T('没跑成:'))) return;
      const ed = d.edges || {};
      msg.h = `<b>${T('全套跑完')}</b> · ${T('{n} 句', { n: lines.length })} · ${T('边覆盖')} ${esc(ed.coverage || '')}${(ed.not_walked || []).length ? ` · ${T('没走到')} ${ed.not_walked.map(esc).join(', ')}` : ` · ${T('每条边都走到了')}`}`
        + `<span class="call">${(d.steps || []).map((s2, i) => `${i + 1}. ${esc(s2.line)} → ${(s2.nodes || []).map(esc).join(' → ') || '—'}`).join('<br>')}</span>`;
      if (S.screen === 'orch' && S.graph === key) drawChat();
    });
  }, true);
  // 节点内部 = 引擎的步骤目录(10-17 第 4 批 S1:GET /api/v1/play/engine/hooks?template=):这一拍真的按什么顺序跑哪些步,
  // 每一步谁来跑(python / 模型 / Jev)、用哪个可换的实现、它管的设置现在是多少、是哪一层定的。S1 只读,S2 起参数能改
  O.hooks = {};
  const BK = { python: ['engine', T('引擎')], llm: ['llm', T('模型')], jev: ['hook', 'Jev'] };
  const SRC = { default: T('默认'), builtin: T('引擎默认'), pack: T('玩法包'), contract: T('合约'), world: T('这个世界的 engine.json(旧)'), graph: T('编排图'), playthrough: T('这一局'), env: T('环境变量') };
  async function loadHooks(tpl) {
    if (!tpl || O.hooks[tpl]) return;
    O.hooks[tpl] = { loading: true };
    const d = await V3.j(`/api/v1/play/engine/hooks?template=${encodeURIComponent(tpl)}`).catch(() => null);
    O.hooks[tpl] = d || { err: true };
    if (S.screen === 'orch' && S.layer === 'node' && GRAPHS[S.graph] && GRAPHS[S.graph].tpl === tpl) renderOrch();
  }
  const stepCard = st => brick(`stp ${(BK[st.backend] || BK.python)[0]} sm`, null, `<div class="k">${(BK[st.backend] || BK.python)[1]}${st.parallel ? ' · ' + T('并行') : ''}${st.required ? ' · ' + T('必需') : ''}</div><b title="${esc(st.doc || '')}">${esc(st.title || st.id)}</b><div class="mono" style="font-size:10.5px;color:var(--muted);margin-top:2px">${esc(st.id)}${st.seam ? ' · ' + T('实现') + ' ' + esc(st.seam) : ''}</div>`, `data-step="${esc(st.id)}"`);
  // S2(10-17):设置在图上改 —— 草稿 g.stepParams[节点][步][设置],写回进模板编排图的 step_params(唯一来源);侧栏测试马上按草稿跑
  const spOf = (g, nid) => (g.stepParams && g.stepParams[nid]) || (g.raw && g.raw.nodes[nid] && g.raw.nodes[nid].step_params) || {};
  const draftVal = (g, nid, st, p) => { const v = (spOf(g, nid)[st.id] || {})[p.name]; return v === undefined ? p.value : v; };
  const input = (g, nid, st, p) => {
    const v = draftVal(g, nid, st, p), at = `data-sp="${esc(nid)}|${esc(st.id)}|${esc(p.name)}"`;
    if (p.type === 'bool') return `<input type="checkbox" ${at} ${v ? 'checked' : ''}>`;
    if (p.choices) return `<select class="btn" ${at} style="padding:3px 8px">${p.choices.map(c => `<option ${String(c) === String(v) ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`;
    return `<input class="btn" ${at} value="${esc(typeof v === 'object' ? JSON.stringify(v) : String(v))}" style="width:90px;padding:3px 8px" ${p.type === 'int' || p.type === 'float' ? `inputmode="decimal"` : ''}>`;
  };
  const paramRows = (g, nid, steps) => steps.filter(st => (st.params || []).length).map(st => `<tr><td colspan="4" class="tag" style="padding-top:10px">${esc(st.title || st.id)}</td></tr>`
    + st.params.map(p => { const mine = (spOf(g, nid)[st.id] || {})[p.name] !== undefined;
      return `<tr title="${esc(p.doc || '')}"><td style="font-size:12px">${esc(p.doc || p.name)}<div class="mono muted" style="font-size:10.5px">${esc(p.name)}</div></td><td>${input(g, nid, st, p)}</td><td class="muted" style="font-size:11.5px">${esc(mine ? T('编排图') + (p.source === 'graph' ? '' : T('(草稿)')) : (SRC[p.source] || p.source || ''))}</td><td class="mono muted" style="font-size:10.5px">${esc(p.key)}</td></tr>`; }).join('')).join('');
  document.addEventListener('change', e => {
    const el = e.target.closest && e.target.closest('[data-sp]'); if (!el || S.screen !== 'orch') return;
    const g = GRAPHS[S.graph]; if (!live(g)) return;
    const [nid, step, name] = el.dataset.sp.split('|');
    const h = O.hooks[g.tpl], st = ((h && h.steps && h.steps.nodes[nid]) || []).find(x => x.id === step), p = st && st.params.find(x => x.name === name);
    let v = el.type === 'checkbox' ? el.checked : el.value;
    if (p && (p.type === 'int' || p.type === 'float')) { const n = Number(v); if (!Number.isFinite(n) || (p.min != null && n < p.min) || (p.max != null && n > p.max) || (p.type === 'int' && !Number.isInteger(n))) { el.style.outline = '1.5px solid var(--rust,#d98a6f)'; el.title = (p.type === 'int' ? T('要整数') : T('要数字')) + (p.min != null ? ',' + p.min + '–' + p.max : ''); return; } v = n; }
    el.style.outline = '';
    g.stepParams = g.stepParams || {};
    const cur = JSON.parse(JSON.stringify(spOf(g, nid)));
    cur[step] = cur[step] || {};
    if (p && v === p.value && p.source !== 'graph') delete cur[step][name]; else cur[step][name] = v;   // 改回原值 = 不写进图
    if (!Object.keys(cur[step]).length) delete cur[step];
    g.stepParams[nid] = cur;
    saveBar(); schedule();
  });
  const _node = drawNode;
  drawNode = function () {
    _node.apply(this, arguments);
    const g = GRAPHS[S.graph], b = document.getElementById('board'); if (!g || !b || !g.raw) return;
    const id = g.nodes[S.node] ? S.node : g.start;
    if (live(g)) {
      loadHooks(g.tpl);
      const h = O.hooks[g.tpl], steps = h && h.steps && h.steps.nodes && h.steps.nodes[id];
      if (steps) {
        const lane = b.querySelector('.lane'), tag = lane && lane.previousElementSibling;
        if (tag) tag.innerHTML = `FLOW · ${T('引擎真实执行的步骤({n})', { n: steps.length })}<span class="unread-tag" style="border-color:rgba(159,224,176,.5);color:var(--pass,#9fe0b0)">${T('读自引擎 · 暂不可改')}</span><span class="muted" style="text-transform:none;letter-spacing:0;margin-left:6px">${T('删步 / 调顺序 / 换实现在后面几步接上')}</span>`;
        if (lane) { lane.classList.remove('unread'); lane.style.flexWrap = 'wrap'; lane.style.rowGap = '12px'; lane.innerHTML = steps.map((st, i) => (i ? '<span class="arrow"></span>' : '') + stepCard(st)).join(''); }
        const well = b.querySelector('.well');
        if (well && steps.some(st => (st.params || []).length)) well.insertAdjacentHTML('beforeend', `<div class="tag" style="margin-top:14px">${T('这一拍的设置 · 现在的值 · 谁定的')}<span class="unread-tag" style="border-color:rgba(159,224,176,.5);color:var(--pass,#9fe0b0)">${T('读自引擎 · 能改')}</span></div>
          <table class="t" data-stepparams style="margin-top:6px;font-size:12.5px"><tr><th>${T('设置')}</th><th>${T('值')}</th><th>${T('来自')}</th><th>${T('键')}</th></tr>${paramRows(g, id, steps)}</table>
          <div class="sub" style="font-size:12px;margin-top:6px">${T('改了 = 草稿:侧栏对话测试马上按它跑;写回模板后下一局按它跑(编排图是这些设置唯一的来处)')}</div>`);
      }
    }
    if (id === 'resolve') b.querySelector('.flow')?.insertAdjacentHTML('beforeend', stateBox(g));
    if (live(g)) saveBar();   // 节点页也能看到「有改动 / 写回」(S2:设置在这里改)
  };
  const _draw = drawGraph;
  drawGraph = function () { _draw.apply(this, arguments); mark(); saveBar(); schedule(); };
})();
