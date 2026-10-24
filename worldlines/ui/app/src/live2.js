/* 第 2–7 步:把原型其余几块换成引擎的真实数据。
   Template:模板详情 · /ui · lint · 素材槽(生成 / 上传)· 复制(fork)· mixins(ops)
   编排:/api/v1/play/engine/graph(生效图 + 默认图)· 工具注册表 = schema.actions
   世界·角色:角色 = 这一局的 souls · Schema = 这一局的类与变量(编辑副本里可注册)· 创作 agent = edit-local/message
   前端:契约导出 /contract?fmt=ts|gd(真文件)
   引擎还不支持写回的地方(编排图、剧情图)页面上照样能拖能改,但标「草稿 · 不写回」。 */
(function () {
  const L = window.LIVE;
  const EDIT = '/api/v1/create/session/edit-local';
  const T = window.TPL = { id: null, detail: null, ui: null, lint: null, slots: null, busy: '', msg: '' };
  const send = (method, path, body, raw) => fetch(V3.url(path), { method, credentials: 'include', headers: raw ? {} : { 'Content-Type': 'application/json' }, body: raw || (body ? JSON.stringify(body) : undefined) })
    .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || j.message || `${r.status}`); return j; });
  const tplOf = id => L.templates.find(t => t.id === id) || {};
  const title = t => (t.card && t.card.title) || t.id;

  /* ================================================================ Template */
  window.LIVE_openTpl = id => { S.screen = 'tpl'; loadTpl(id); window.WL_setWorld && window.WL_setWorld(id, { quiet: true }); render(); };
  window.TPL_load = id => loadTpl(id);   // 当前世界换了(live.js syncWorld)   // 剧情图上「去生成 CG」跳过来
  async function loadTpl(id) {
    T.id = id; T.detail = T.ui = T.lint = T.slots = null; if (S.screen === 'tpl') renderTpl();
    const b = `/api/v1/local/templates/${encodeURIComponent(id)}`;
    // 各自回来就各自画(lint 要几秒,不让它挡住整页)
    const put = (k, path) => V3.j(path).catch(() => null).then(v => { if (T.id !== id) return; T[k] = v; if (S.screen === 'tpl') renderTpl(); });
    await Promise.all([put('detail', b), put('slots', b + '/assets'), put('ui', b + '/ui'), put('lint', b + '/lint')]);
  }
  const blk = () => (T.lint && T.lint.counts && T.lint.counts.block) || 0;
  renderTpl = function () {
    const el = $('#s-tpl');
    if (!L.ok) { el.innerHTML = '<div class="tplw"><div class="sub">连接引擎……</div></div>'; return; }
    if (!T.id || !L.templates.some(t => t.id === T.id)) { loadTpl(S.world || L.bound || (L.templates[0] || {}).id); }
    const tab = S.tplTab || 'pack', t = tplOf(T.id);
    el.innerHTML = `<div class="tplw"><div class="tplhd"><div><div class="tag">${esc(T.id || '')}.template ${T.ui ? (T.ui.writable ? '· 可写' : '· 内置(只读,复制后可改)') : ''}</div><h1 class="h1">${esc(title(t))}</h1></div>
      <div style="margin-left:auto" class="row"><select class="btn" id="tplSel" style="text-transform:none;letter-spacing:0">${L.templates.map(x => `<option value="${x.id}" ${x.id === T.id ? 'selected' : ''}>${esc(title(x))}</option>`).join('')}</select>
        ${newBtn('tpl')}
        ${T.ui && !T.ui.writable ? (T.ui.forkable === false ? '<span class="tag">官方世界 · 只能玩,不能复制</span>' : '<button class="btn" data-tfork>复制一份来改</button>') : ''}
        ${t.zone === 'reviewed' ? `<span class="btn" data-noexport aria-disabled="true" style="opacity:.45;cursor:not-allowed" title="默认区的作品(官方世界也在默认区)只能玩、不能导出;只有自由区的作品可以导出。想在它上面改:先「复制一份来改」,改好用账号发到自由区">导出 · 默认区不可</span>`
          : `<a class="btn" href="${V3.url(`/api/v1/local/templates/${encodeURIComponent(T.id || '')}/export`)}" download="${esc(T.id || 'template')}.template.zip" title="打成一个包带走:模板 + 它链接的角色库角色">导出</a>`}
        <label class="btn" title="把导出的包导回来(模板进你的模板库,带着的角色进角色库)">导入…<input type="file" accept=".zip" id="tplImport" hidden></label>
        <button class="btn" data-tplay>去测试台跑 →</button></div></div>
      <div class="tabs">${[['pack', 'Pack', '装配 · 素材'], ['ctr', '合约', t.play_contract || (T.detail && T.detail.play_contract) || '未声明'], ['lint', 'Lint', T.lint ? (blk() ? blk() + ' block' : '清零') : '…']].map(([k, l, s]) => `<button class="${tab === k ? 'on' : ''}" data-tt="${k}">${l}<small>${esc(s)}</small></button>`).join('')}</div>
      ${T.msg ? `<div class="setmsg" style="margin-top:10px">${esc(T.msg)}</div>` : ''}
      <div class="tplbody">${!T.detail ? '<div class="sub" style="padding:20px">读模板……</div>' : ({ pack: livePack, ctr: liveCtr, lint: liveLint })[tab]()}</div></div>`;
    const sel = $('#tplSel'); if (sel) sel.onchange = () => { T.msg = ''; loadTpl(sel.value); window.WL_setWorld && window.WL_setWorld(sel.value); };   // 这一页的选择器也改当前世界
    const imp = $('#tplImport'); if (imp) imp.onchange = () => importPackage(imp.files && imp.files[0]);
  };
  // 导入(10-08):包里的 pack.json 说是模板还是角色;模板进模板库,带着的角色进角色库,id 被占就 -2
  async function importPackage(file) {
    if (!file) return;
    T.msg = `导入 ${file.name}……`; renderTpl();
    try {
      const r = await fetch(V3.url('/api/v1/local/import/package'), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/zip' }, body: file });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error || r.status);
      const souls = (d.souls || []).map(x => `${x.name}${x.how === 'same' ? '(已有,复用)' : x.how === 'renamed' ? '(同名不同人,改名)' : '(新)'}`).join('、');
      T.msg = d.kind === 'template' ? `导入了模板 ${d.id}${d.renamed_from ? `(${d.renamed_from} 已被占用)` : ''}${souls ? ' · 角色:' + souls : ''}` : `导入了角色 ${d.id}(进了角色库)`;
      if (d.kind === 'template') { const ts = await V3.j('/api/v1/local/templates'); L.templates = ts.templates || L.templates; loadTpl(d.id); return; }
    } catch (err) { T.msg = '导入失败:' + err.message; }
    renderTpl();
  }
  function livePack() {
    const d = T.detail, u = T.ui || {}, mixins = u.mixins || [], avail = u.mixins_available || [];
    const souls = d.souls || [], cover = V3.url(`/api/v1/local/templates/${encodeURIComponent(T.id)}/cover`);
    const slots = (T.slots && T.slots.slots) || [];
    const slotImg = s => V3.url(`/api/v1/local/templates/${encodeURIComponent(T.id)}/assets/file?slot=${encodeURIComponent(s.slot)}&v=${T.stamp || 0}`);
    return `<div class="bench" style="position:relative;inset:auto">
      ${brick('slot', null, `<div class="meta"><span><i>01</i>编排图</span></div><div class="t">${esc(d.orchestration || '默认图')}</div><div class="sub" style="font-size:12.5px">玩法包 ${esc(d.pack || '')} 的默认编排;模板可在 template.json[orchestration] 覆盖</div><button class="btn" data-go="orch" style="margin-top:auto">在编排台看</button>`)}
      ${brick('slot', null, `<div class="meta"><span><i>02</i>玩法包</span></div><div class="t">${esc(d.pack || '—')}</div><div class="sub" style="font-size:12.5px">工具 = 玩法包注册的 actions(在编排台的工具注册表里看)</div>`)}
      ${brick('slot img hov', cover, `<div class="meta" style="position:absolute;top:20px;left:20px;right:20px"><span><i>03</i>世界</span><span>${esc((d.mode && d.mode.ending) || '')} · ${esc((d.mode && d.mode.freedom) || '')}</span></div><div class="cap"><b style="font-size:24px">${esc(title(d))}</b><small>${esc(((d.card && d.card.pitch) || '').slice(0, 40))}</small></div><button class="btn" data-go="duo" style="align-self:flex-start;margin-top:10px">世界面</button>`)}
      ${brick('slot', null, `<div class="meta"><span><i>04</i>角色</span><span>${souls.length}</span></div><div class="t">${souls.map(esc).join(' · ') || '—'}</div><button class="btn" data-go="duo" onclick="S.face='soul';S.duoTab.soul='cards'" style="margin-top:auto">角色面</button>`)}
      ${brick('slot', null, `<div class="meta"><span><i>05</i>后台单位</span><span>mixins</span></div><div class="t">世界自己在走</div>
        ${avail.map(k => `<div class="sw"><span><b>${({ economy: '经济', factions: '势力' })[k] || k}</b><br><small style="color:var(--muted)">${k}</small></span><button class="tg ${mixins.includes(k) ? 'on' : ''}" data-tmix="${k}" ${u.writable ? '' : 'disabled title="内置模板只读:先复制一份"'} aria-label="${k}"></button></div>`).join('') || '<div class="sub">这个玩法包没有可选的后台单位</div>'}`)}
    </div>
    <div class="tag" style="margin:18px 0 8px">素材槽 · ${slots.filter(s => s.have).length} / ${slots.length} 已填 · 发布必需 ${slots.filter(s => s.need).length}</div>
    <div class="slotgrid">${slots.map(s => `<div class="glass slotc ${s.need && !s.have ? 'need' : ''} ${s.stale ? 'stale' : ''}">
        <div class="si">${s.have ? `<img src="${slotImg(s)}" alt="" loading="lazy">` : `<span>${s.need ? '发布必需' : '可选'}</span>`}</div>
        <div class="sb"><b>${esc(s.label || s.name)}</b><small class="mono">${esc(s.slot)}</small>${s.stale ? '<small style="color:var(--crit)">输入变了,要重生成</small>' : ''}
        <div class="row" style="gap:4px;margin-top:6px"><button class="chip" data-tgen="${esc(s.slot)}" ${T.busy === s.slot ? 'disabled' : ''}>${T.busy === s.slot ? '生成中…' : s.have ? '重生成' : '生成'}</button><label class="chip" style="cursor:pointer">上传<input type="file" accept="image/png,image/jpeg,image/webp" data-tup="${esc(s.slot)}" hidden></label></div></div></div>`).join('')}</div>
    <details class="setmore" style="margin-top:14px"><summary>template.json</summary><pre class="code glass deep">${esc(JSON.stringify(d, null, 2))}</pre></details>`;
  }
  function liveCtr() {
    const ref = T.detail.play_contract || '', id = ref.split('@')[0], c = CONTRACTS[id];
    const probs = ((T.lint && T.lint.problems) || []).filter(p => /^contract\./.test(p.code));
    if (!c) return `<div class="letter" style="max-width:720px"><h2>还没有声明玩法合约</h2><div class="meta2">${esc(T.id)} · template.json 里没有 play_contract</div>
      <p class="human" style="font-size:16px;line-height:1.8">没有合约的模板可以在本地玩,但进不了 Hub。四份官方合约:${Object.entries(CONTRACTS).map(([k, v]) => `<b>${v.title}</b>(${k}@1)`).join('、')}。</p>
      <p class="sub" style="color:var(--paper-muted)">在 template.json 里加一行 <span class="mono">"play_contract": "mystery-trpg@1"</span> 就算声明;之后这里逐条显示引擎的判定。</p></div>`;
    const clauses = [['壹', '入口', c.entry, 'contract.entry'], ['贰', '出口', c.exit, 'contract.exit'], ['叁', '结局', c.endings.min ? `不少于 ${c.endings.min} 个${c.endings.require ? ',其中一个是真相结局' : ''}` : '不要求结局', 'contract.endings'],
      ['肆', '奖励', `玩家带走 ${c.rewards.player.join('、')};角色 ${c.rewards.soul.join('、')}`, 'contract.rewards'], ['伍', '固定输出', c.outputs.join('、'), 'contract.outputs'], ['陆', '上架', `lint 无 block,并且${c.publish}一次`, 'contract.publish']];
    const miss = code => probs.filter(p => p.code === code || (code === 'contract.endings' && p.code === 'contract.reveal'));
    const unmet = clauses.filter(x => miss(x[3]).some(p => p.level === 'block')).length;
    return `<div class="ctrw" style="position:relative;inset:auto"><div class="ctrpick"><div class="tag">声明的合约</div>${brick('cpk on', null, `<b>${c.title}</b><span>${c.pitch}</span>`)}<div class="sub" style="font-size:12.5px">判定来自引擎的按合约 lint(contract.*)</div></div>
      <div class="letter"><h2>玩法合约 · ${c.title}</h2><div class="meta2">WORLDLINES.PLAY-CONTRACT/1 · ${esc(ref)} · 立约方 ${esc(T.id)}</div>
      ${clauses.map(([no, t, tx, code]) => { const m = miss(code), bad = m.some(p => p.level === 'block'), warn = !bad && m.length;
        return `<div class="clause"><div class="no">${no}</div><div class="tx"><b>${t}</b> · ${esc(tx)}${m.length ? `<small>${m.map(p => esc(p.msg)).join(' · ')}</small>` : ''}</div><div class="st"><span class="stamp ${bad ? 'bad' : 'ok'}">${bad ? '未满足' : warn ? '有提醒' : '满足'}</span></div></div>`; }).join('')}
      <div class="seal ${unmet ? '' : 'ok'}">${unmet ? `尚欠<br>${unmet} 条` : '合约<br>满足'}</div></div></div>`;
  }
  function liveLint() {
    const ls = (T.lint && T.lint.problems) || [], c = (T.lint && T.lint.counts) || {};
    return `<div class="term glass deep" style="position:relative;inset:auto;min-height:420px"><div><span class="pr">~/worlds $</span> neonrp template lint ${esc(T.id)}.template</div><br>
      ${ls.map(x => `<div class="ln"><span class="${x.level === 'block' ? 'bl' : x.level === 'warn' ? 'wa' : 'okc'}">${esc(String(x.level).toUpperCase())}</span><span>${esc(x.code)}</span><span>${esc(x.msg)}${x.where ? ` <span class="mu">· ${esc(x.where)}</span>` : ''}</span><span>${/^asset\./.test(x.code) ? '<a data-tt="pack">去素材槽</a>' : /^map\./.test(x.code) ? '<a data-go="duo">去地图</a>' : /^contract\./.test(x.code) ? '<a data-tt="ctr">去合约</a>' : ''}</span></div>`).join('') || '<div class="okc">没有问题</div>'}
      <br><div>${c.block ? `<span class="bl">✗ ${c.block} 个 block</span> 会挡住 Hub 上架` : '<span class="okc">✓ 没有 block</span>'} · <span class="wa">${c.warn || 0} 个 warn</span> · ${T.lint && T.lint.publishable ? '<span class="okc">可以发布</span>' : '<span class="bl">还不能发布</span>'}</div></div>`;
  }
  // 顶栏 / 一览用的 lint = 引擎的真实 lint(当前模板)
  lint = function () { return ((T.lint && T.lint.problems) || []).map(p => ({ lv: p.level, code: p.code, msg: p.msg })); };
  document.addEventListener('click', async e => {
    if (S.screen !== 'tpl') return;
    const q = s => e.target.closest(s); let t;
    if (q('[data-tplay]')) { L.play({ slug: `tpl--${T.id}` }); return; }
    if (q('[data-tfork]')) { const nid = (T.id + '-mine').slice(0, 40); try { const r = await send('POST', `/api/v1/local/templates/${encodeURIComponent(T.id)}/fork`, { id: nid, title: title(T.detail) + '(我的)' }); T.msg = `复制好了:${r.id || nid}`; const ts = await V3.j('/api/v1/local/templates'); L.templates = ts.templates || L.templates; loadTpl(r.id || nid); window.WL_setWorld && window.WL_setWorld(r.id || nid); } catch (err) { T.msg = '复制失败:' + err.message; renderTpl(); } return; }
    if ((t = q('[data-tmix]'))) { const k = t.dataset.tmix, cur = (T.ui.mixins || []), next = cur.includes(k) ? cur.filter(x => x !== k) : [...cur, k];
      try { await send('POST', `/api/v1/local/templates/${encodeURIComponent(T.id)}/ops`, { ops: [{ op: 'set_mixins', mixins: next }] }); T.msg = ''; } catch (err) { T.msg = '没改成:' + err.message; } loadTpl(T.id); return; }
    if ((t = q('[data-tgen]'))) { T.busy = t.dataset.tgen; renderTpl(); try { await send('POST', `/api/v1/local/templates/${encodeURIComponent(T.id)}/assets/generate`, { slot: T.busy }); T.msg = '生成好了'; T.stamp = Date.now(); } catch (err) { T.msg = '生成失败:' + err.message; } T.busy = ''; loadTpl(T.id); }
  });
  document.addEventListener('change', async e => {
    const inp = e.target.closest && e.target.closest('[data-tup]'); if (!inp || !inp.files[0]) return;
    const f = inp.files[0], ext = '.' + (f.name.split('.').pop() || 'png').toLowerCase();
    try { await send('POST', `/api/v1/local/templates/${encodeURIComponent(T.id)}/assets/upload?slot=${encodeURIComponent(inp.dataset.tup)}&ext=${encodeURIComponent(ext)}`, null, f); T.msg = '上传好了'; T.stamp = Date.now(); } catch (err) { T.msg = '上传失败:' + err.message; }
    loadTpl(T.id);
  });

  /* ================================================================ 编排 */
  const ON = o => { const k = Object.keys(o || {})[0] || 'always', v = (o || {})[k]; return { on: k === 'here_class' ? 'here' : k, val: v === true ? '' : String(v ?? '') }; };
  Object.assign(TRIG, { event: '外部事件', host: '主持推进', phase: '阶段', tick: '时钟' });
  Object.assign(KIND, { place: '地点层', one_shot: '一次性', phase: '阶段' });
  async function loadGraph() {
    if (!L.ok) return;
    const [g, sc] = await Promise.all([V3.j('/api/v1/play/engine/graph').catch(() => null), V3.j('/api/v1/play/schema').catch(() => null)]);
    if (sc) {  // 工具注册表 = 这一局注册的 actions
      for (const k of Object.keys(TOOLS)) delete TOOLS[k];
      (sc.actions || []).forEach(a => { TOOLS[a.op] = { kind: a.kind, sync: a.wait !== false && !['tool'].includes(a.kind) || a.wait === true, fields: (a.fields || []).join(', '), validator: (a.validator || '').split(':').pop(), src: (a.handler || '').split('.').slice(2, 4).join('.') || 'engine', doc: a.doc || '' }; });
      Object.entries(BEATS.tools || {}).forEach(([k, v]) => { if (!TOOLS[k]) TOOLS[k] = v; });   // 某种拍自带的工具(私有层登记)
    }
    if (g && g.graph) {
      GRAPHS.live = toUi(g.graph, `这一局 · ${g.graph.id || 'default'}(引擎生效图)`, L.bound, g.default);
      if (!L.graphPicked) { S.graph = 'live'; S.node = GRAPHS.live.start; S.chat = null; L.graphPicked = true; }
      if (!window.LIVE_DEMO) for (const k of Object.keys(GRAPHS)) if (k !== 'live' && !k.startsWith('tpl:')) delete GRAPHS[k];
      if (S.screen === 'orch') renderOrch();
    }
    // 每个模板自己的图(不用开局,10-06 引擎 graph?template=):下拉框里先列出来,选中才取 ——
    // 取一张要在后台临时建一局,一次取五张会把引擎占满几秒(打开世界 / 读契约跟着超时)
    L.templates.forEach(t => { if (!GRAPHS['tpl:' + t.id]) GRAPHS['tpl:' + t.id] = { title: `模板 · ${title(t)}`, start: 'plan', nodes: {}, edges: [], pending: true, tpl: t.id }; });
    if (!GRAPHS.live && !window.LIVE_DEMO) {   // 没开局:第一张模板图当默认,原型的演示图不留
      const first = Object.keys(GRAPHS).find(k => k.startsWith('tpl:'));
      const want = L.bound && GRAPHS['tpl:' + L.bound] ? 'tpl:' + L.bound : first;
      if (want) { for (const k of Object.keys(GRAPHS)) if (!k.startsWith('tpl:')) delete GRAPHS[k]; if (!GRAPHS[S.graph]) { S.graph = want; S.chat = null; } }
    }
    L.graphsLoaded = true;
    if (S.screen === 'orch') renderOrch();
  }
  window.ORCH_toUi = (g, t, tpl, def) => toUi(g, t, tpl, def);
  // 引擎的图(nodes 是字典、edges 带 on 对象)→ 编排台画的图;raw 留着,草稿检查时转回去
  function toUi(G0, title, tpl, def) {
    const ids = Object.keys(G0.nodes), cols = { loop: 0, mode: 2, place: 1, one_shot: 2, phase: 1 };
    const perCol = {};
    const nodes = {};
    ids.forEach(id => { const n = G0.nodes[id], kind = n.kind === 'one_shot' ? 'one' : n.kind === 'place' || n.kind === 'phase' ? 'mode' : n.kind;
      const c = id === 'plan' ? 0 : id === 'resolve' ? 1 : (cols[n.kind] ?? 2) + 1, r = perCol[c] = (perCol[c] || 0) + 1;
      const tools = n.tools === '@pack.actions' ? Object.keys(TOOLS).filter(k => !['read', 'mic', 'board'].includes(k)) : (n.tools || []);
      const steps = (n.steps || [n.mode ? 'mode:' + n.mode : 'solve']).map(s => typeof s === 'object' ? ['par', ['角色各自'], '并行组 · ' + (s.parallel || '')] : [/host|solve|gate/.test(s) ? 'llm' : 'engine', s]);
      const side = ids.filter(k => k !== 'plan' && k !== 'resolve'), si = side.indexOf(id);
      const at = id === 'plan' ? [40, 110] : id === 'resolve' ? [330, 330] : [680, 40 + si * 150];
      nodes[id] = { kind, title: n.title || id, x: at[0], y: at[1], tools, prompt: n.prompt || (n.mode ? `mode ${n.mode}` : '—'), knobs: { ...(n.exit ? { exit: n.exit } : {}), ...(n.here_class ? { here_class: n.here_class } : {}) }, steps }; });
    const edges = (G0.edges || []).map(e => ({ id: e.id, from: e.from, to: e.to === '@return' || e.return_to ? '@return' : e.to, ...ON(e.on), guard: e.when ? JSON.stringify(e.when) : '' })).filter(e => nodes[e.from] && (e.to === '@return' || nodes[e.to]));
    // 同一对节点之间的多条推进边合成一条显示(一对节点之间可能有好几种推进)
    const merged = [], seen = {};
    edges.forEach(e => { const k = e.from + '>' + e.to; if (seen[k] && e.to !== '@return') { seen[k].all = (seen[k].all || [TRIG[seen[k].on] + (seen[k].val ? ':' + seen[k].val : '')]).concat(TRIG[e.on] + (e.val ? ':' + e.val : '')); seen[k].multi = (seen[k].multi || 1) + 1; seen[k].on = 'words'; seen[k].val = `${seen[k].multi} 种推进`; return; } seen[k] = e; merged.push(e); });
    merged.forEach(e => { e.engine = true; if (!e.all) e.orig = JSON.stringify([e.on, e.val, e.guard || '']); });   // orig:写回时认出哪条被改过(orch.js)
    Object.values(nodes).forEach(n => { n.engine = true; });
    // state = how the Resolve beat writes state (pseudo | jev, 10-11); def = the pack's default graph (恢复默认)
    return { title, start: G0.start || 'plan', nodes, edges: merged, live: true, raw: JSON.parse(JSON.stringify(G0)), tpl, state: G0.state || null, def: def || null };
  }
  const _pop = edgePop;
  edgePop = function () { _pop(); const e = G().edges.find(x => x.id === S.edge), pop = $('#pop'); if (e && e.all && pop) pop.insertAdjacentHTML('beforeend', `<div class="tag" style="margin-top:10px">合在一起的 ${e.all.length} 条推进(引擎里各是一条边)</div>${e.all.map(x => `<div class="mono" style="font-size:12px;padding:3px 0">· ${esc(x)}</div>`).join('')}`); };
  const _orch = renderOrch;
  async function loadTplGraph(key) {
    const g0 = GRAPHS[key]; if (!g0 || !g0.pending || g0.loading) return;
    g0.loading = true;
    const r = await V3.j(`/api/v1/play/engine/graph?template=${encodeURIComponent(g0.tpl)}`).catch(() => null);
    if (r && r.graph) { GRAPHS[key] = toUi(r.graph, `${g0.title} · ${r.pack || ''}`, g0.tpl, r.default); if (S.graph === key) { S.node = GRAPHS[key].start; S.chat = null; } }
    else { g0.loading = false; g0.err = '取不到这张图'; }
    if (S.screen === 'orch') renderOrch();
  }
  renderOrch = function () {
    if (G() && G().pending) { if (!G().err) loadTplGraph(S.graph); if (G() && G().pending) { $('#s-orch').innerHTML = `<div class="ws"><div class="ws-main"><div class="crumb"><div class="r"></div></div><div class="sub">${G().err ? `「${esc(G().title)}」${esc(G().err)}` : `读「${esc(G().title)}」的编排图……`}</div></div></div>`; return; } }   // crumb .r:角色面的「世界 / 角色」切换照样插得进来
    if (!L.graphsLoaded && L.ok && !L.graphLoading) { L.graphLoading = true; loadGraph().finally(() => (L.graphLoading = false)); } if (!G()) { $('#s-orch').innerHTML = '<div class="ws"><div class="sub">读编排图……</div></div>'; return; } _orch(); };

  /* ================================================================ 世界 · 角色 */
  function syncSouls() {
    if (window.DUO && window.DUO.ready && window.DUO.ready()) return;   // 世界 · 角色读的是编辑中的世界(duo.js),不是这一局
    if (!L.ok || !E.s) return;
    const live = Object.values(E.s.souls || {}); if (!live.length) return;
    for (const k of Object.keys(SOULS)) delete SOULS[k];
    live.forEach(so => { const at = (E.where(so.id) || {}).at || ''; SOULS[so.id] = { name: so.name, img: so.av ? V3.IMG[so.av] : 'elena.jpg', line: so.role || (so.traits || []).join(' · ') || '', at: PLACES[at] ? at : Object.keys(PLACES)[0],
      say: so.lastLine || '', data: { 现在在: nm(at) || at || '—', 心情: so.mood || '—', 打算: so.intention || '—', 特质: (so.traits || []).join(' · ') || '—' }, haunts: [] };
      SVAL[so.id] = SVAL[so.id] || { persona: (so.traits || []).join(' · '), trust: 0, memory: [], mood: so.mood || '' }; });
    if (!SOULS[S.pick.id] && S.pick.t === 'soul') S.pick = { t: 'soul', id: Object.keys(SOULS)[0] };
  }
  schemaWorld = function () {
    const sc = E.s && E.s.schemaRaw, V = Object.values((E.s && E.s.vars) || {});
    if (!sc) return '<div class="schw"><div class="sub">读 schema……</div></div>';
    const cls = sc.classes.filter(c => (c.count || 0) > 0 || Object.keys(c.props || {}).length);
    const canEdit = !!(window.MAPHOOK && window.MAPHOOK.edit);
    return `<div class="schw scroll"><div class="sub" style="margin-bottom:12px">这一局的开放 schema(类)和闭 schema(变量),读自引擎。${canEdit ? '注册新条目写进这个世界的 game/meta。' : '世界还在打开……'}</div>
      <div class="glass deep" style="padding:8px 10px"><div class="tag" style="padding:6px">类 · ${cls.length}</div><table class="t"><tr><th>类</th><th>父类</th><th>文件夹</th><th>实例</th><th>属性</th><th>可变</th></tr>${cls.map(c => `<tr><td class="mono">${esc(c.name)}</td><td class="mono">${esc(c.parent_class || '—')}</td><td class="mono" style="font-size:11px">${esc(c.folder || '(内置)')}</td><td class="mono">${c.count || 0}</td><td>${Object.entries(c.props || {}).map(([k, p]) => `<span class="chip">${esc(k)} ${esc(p.type || '')}</span>`).join(' ') || '—'}</td><td class="mono">${esc((c.mutable || []).join(' · ') || '—')}</td></tr>`).join('')}</table></div>
      <div class="glass deep" style="padding:8px 10px;margin-top:14px"><div class="tag" style="padding:6px">变量 · ${V.length}</div><table class="t"><tr><th>变量</th><th>类型</th><th>值</th><th>文件</th></tr>${V.map(v => `<tr><td class="mono">${esc(v.name)}</td><td class="mono">${esc(v.type || '')}${v.readonly ? ' · 只读' : ''}</td><td class="mono">${esc(typeof v.value === 'object' ? JSON.stringify(v.value) : v.value)}</td><td class="mono" style="font-size:11px">${esc(v.path || '')}</td></tr>`).join('')}</table>
        ${canEdit ? `<div class="row" style="padding:10px 6px"><input class="cell" id="nvId" placeholder="新变量,例 fog.level" style="max-width:200px"><select class="cell" id="nvType" style="max-width:100px">${['int', 'str', 'bool'].map(x => `<option>${x}</option>`).join('')}</select><input class="cell" id="nvPath" placeholder="文件,例 game/meta/vars.json" style="max-width:220px"><button class="btn p" data-nvadd>注册</button></div>` : ''}</div></div>`;
  };
  document.addEventListener('click', async e => {
    if (!e.target.closest('[data-nvadd]')) return;
    const v = id => (($('#' + id) || {}).value || '').trim(); if (!v('nvId') || !v('nvPath')) return;
    try { await send('POST', EDIT + '/schema/register', { table: 'variables', id: v('nvId'), spec: { type: v('nvType'), path: v('nvPath'), key: v('nvId').split('.').pop() } }); window.SETTINGS && (window.SETTINGS.msg = ''); await E.load(); } catch (err) { L.err = '注册失败:' + err.message; }
    render();
  });
  // 创作 agent:有编辑副本就走引擎的创作会话(流式);没有就提示先另存
  agentDo = async function (x) {
    S.wagent.push({ t: 'me', h: esc(x) });
    if (!(window.MAPHOOK && window.MAPHOOK.edit)) { S.wagent.push({ t: 'agent', h: '这个世界还在打开,等地图出来再跟我说。' }); renderDuo(); return; }
    const msg = { t: 'agent', h: '<span class="dots">…</span>' }; S.wagent.push(msg); renderDuo();
    let text = '', calls = [];
    try {
      const r = await fetch(V3.url(EDIT + '/message'), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ input: x }) });
      if (!r.ok || !r.body) throw new Error('message → ' + r.status);
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', ev = '';
      for (;;) { const { done, value } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true });
        let nl; while ((nl = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, nl).replace(/\r$/, ''); buf = buf.slice(nl + 1);
          if (line.startsWith('event: ')) ev = line.slice(7);
          else if (line.startsWith('data: ') && ev) { let d = {}; try { d = JSON.parse(line.slice(6)); } catch { /* skip */ }
            if (ev === 'chunk') text += d.text || ''; else if (ev === 'tool_use') calls.push(`${d.name} ${d.path || ''}`); else if (ev === 'done') text = d.assistant_message || text; else if (ev === 'error') text += '\n出错:' + (d.error || '');
            msg.h = `${esc(text) || '<span class="dots">…</span>'}${calls.length ? `<span class="call">${esc(calls.slice(-6).join(' · '))}</span>` : ''}`; renderDuo(); ev = ''; } } }
    } catch (err) { msg.h = '没连上创作会话:' + esc(err.message); }
    renderDuo(); if (window.LIVE_buildMap) window.LIVE_buildMap();
  };
  S.wagent = [{ t: 'agent', h: '我是创作 agent,改的是你正在编辑的这个世界的文件(按 documents/spec/world 和 soul)。直接说要改什么。<span class="call">edit-local/message</span>' }];
  const _duo = renderDuo;
  renderDuo = function () { syncSouls(); _duo(); };
  const _dataSoul = dataSoul;
  dataSoul = function () { syncSouls(); return Object.keys(SOULS).length ? _dataSoul() : '<div class="schw"><div class="sub">这一局没有角色</div></div>'; };

  /* ================================================================ 新建(10-24):三个入口,模板 ≠ 世界 ≠ 角色
     「＋ 新建 Template」(Template 页):Template = 玩法包 + 玩法合约 + 编排(POST /local/templates {pack, contract, orchestration});
        模板总得绑一个世界,引擎给它一份空白世界当 world/。和「复制一份来改」落在同一个模板库,建完就是当前世界。
     「＋ 新建世界」(世界·角色 · 世界面):引擎里世界不能脱离模板单独出现在工作台(世界选择器 = 模板;world 绑的是模板里的
        文件夹或引擎内置世界)→ 在当前模板里换上一份空白世界数据(POST templates/<id>/world/new);旧世界挪进模板库的
        .world-backups/,世界自带的角色跟着旧世界走,角色库 link 的留下;编辑副本按新世界重开。内置模板只读:先新建 / 复制模板。
     「＋ 新建角色」(世界·角色 · 角色面):角色库里建一个空白角色(POST /local/souls/blank,不调模型);勾着就 link 进当前世界
        (templates/<id>/souls/link —— 角色库独立,世界只放 link;编辑副本也带上它)。 */
  const NEW = { kind: null, busy: false, opts: null };
  const NEWL = { tpl: '＋ 新建 Template', world: '＋ 新建世界', soul: '＋ 新建角色' };
  const NEWT = { tpl: '玩法包 + 玩法合约 + 编排;带一份空白世界(一个起点镇、一个玩家,没有角色)', world: '在当前模板里换上一份空白世界数据', soul: '在角色库里从零建一个角色,可以顺手加进当前世界' };
  const newBtn = kind => L.ok ? `<button class="btn" data-wlnew="${kind}" title="${NEWT[kind]}">${NEWL[kind]}</button>` : '';
  window.WL_newBtn = f => newBtn(f === 'soul' ? 'soul' : 'world');
  const words = v => (v && typeof v === 'object' ? v.zh || v.en || Object.values(v)[0] : v) || '';
  const PACKW = { rpg: 'rpg · 冒险', pct: 'pct · 百分骰调查', werewolf: 'werewolf · 狼人杀', monopoly: 'monopoly · 大富翁' };
  async function newPop(kind, at) {
    let el = $('#wlNewPop'); if (!el) { el = document.createElement('div'); el.id = 'wlNewPop'; el.className = 'pop glass'; el.style.position = 'fixed'; document.body.appendChild(el); }
    NEW.kind = kind;
    const w = L.templates.find(x => x.id === S.world), sel = (id, label, rows, def) => `<label class="tag" style="display:block">${label}</label><select id="${id}">${rows.map(([v, l]) => `<option value="${esc(v)}" ${v === def ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    let body = '';
    if (kind === 'tpl') {
      NEW.opts = NEW.opts || await V3.j('/api/v1/local/templates/_new').catch(() => null);
      const o = NEW.opts || { packs: { options: ['rpg'], default: 'rpg' }, contracts: { options: [] }, orchestration: { options: [] } };
      const oa = (o.contracts.options.find(c => /^open-adventure@/.test(c.id)) || {}).id || '';
      body = `<h4>新建 Template</h4><div class="sub" style="font-size:12.5px">Template = 玩法包 + 玩法合约 + 编排。模板总要绑一个世界:先给它一份空白世界,之后在世界·角色里改,或「新建世界」换掉</div>
        <input id="wlNewName" placeholder="名字,例:雾港" maxlength="60"><input id="wlNewId" class="mono" placeholder="id(可选):小写字母 / 数字 / -,例 fog-port" maxlength="48">
        ${sel('wlNewPack', '玩法包', o.packs.options.map(k => [k, PACKW[k] || k]), o.packs.default)}
        ${sel('wlNewCtr', '玩法合约', [['', '不声明(本地能玩,进不了 Hub)'], ...o.contracts.options.map(c => [c.id, `${words(c.title)} · ${c.id}`])], oa)}
        ${sel('wlNewOrch', '编排', o.orchestration.options.map(x => [x.id, words(x.title) || x.id]), o.orchestration.default)}`;
    } else if (kind === 'world') {
      const u = w ? await V3.j(`/api/v1/local/templates/${encodeURIComponent(w.id)}/ui`).catch(() => null) : null;
      NEW.writable = !!(u && u.writable);
      body = !w ? '<h4>新建世界</h4><div class="sub">先在顶栏选一个模板</div>' : NEW.writable
        ? `<h4>新建世界</h4><div class="sub" style="font-size:12.5px">在模板「${esc(title(w))}」里换上一份空白世界(一个起点镇、一个玩家)。玩法包 / 合约 / 编排 / 剧情 / 角色库的角色都留着;旧世界(连同它自带的角色)挪进备份,不删</div>
          <input id="wlNewName" placeholder="世界的名字,例:雾港" maxlength="60">`
        : `<h4>新建世界</h4><div class="sub" style="font-size:12.5px">「${esc(title(w))}」是内置模板(只读),世界换不了。世界总是装在一个模板里:先新建一个 Template(自带空白世界),或在 Template 页「复制一份来改」</div>`;
    } else {
      body = `<h4>新建角色</h4><div class="sub" style="font-size:12.5px">进角色库(独立于世界);人设之后在角色面写,或交给创作 agent</div>
        <input id="wlNewName" placeholder="名字,例:阿雾" maxlength="40"><input id="wlNewIntro" placeholder="一句话简介(可选)" maxlength="400">
        ${w ? `<label class="row" style="gap:8px;font-size:13px;margin:0 0 10px"><input type="checkbox" id="wlNewLink" checked style="width:auto;margin:0">加进当前世界「${esc(title(w))}」</label>` : ''}`;
    }
    const go = kind !== 'world' || NEW.writable;
    el.innerHTML = body + `<div class="setmsg" id="wlNewMsg" style="display:none;margin:0 0 9px"></div><div class="row" style="justify-content:flex-end;gap:6px">${go ? '<button class="btn" data-wlnewx>取消</button><button class="btn p" data-wlnewgo>建</button>' : `<button class="btn" data-wlnewx>好</button><button class="btn p" data-wlnewtpl>去新建 Template</button>`}</div>`;
    const r = at.getBoundingClientRect();
    el.hidden = false;
    el.style.left = Math.max(8, Math.min(r.right - 300, innerWidth - 316)) + 'px'; el.style.top = Math.max(8, Math.min(r.bottom + 8, innerHeight - el.offsetHeight - 8)) + 'px';
    const n = $('#wlNewName'); if (n) n.focus();
  }
  const closeNew = () => { const el = $('#wlNewPop'); if (el) el.hidden = true; NEW.kind = null; };
  const newMsg = m => { const b = $('#wlNewMsg'); if (b) { b.style.display = m ? '' : 'none'; b.textContent = m; } };
  const val = id => (($('#' + id) || {}).value || '').trim();
  async function newGo() {
    const name = val('wlNewName');
    if (NEW.busy) return;
    if (!name) { newMsg(NEW.kind === 'soul' ? '先起个名字' : '先起个名字'); return; }
    NEW.busy = true; newMsg('建……');
    try {
      if (NEW.kind === 'tpl') {
        const r = await send('POST', '/api/v1/local/templates', { title: name, id: val('wlNewId'), pack: val('wlNewPack'), contract: val('wlNewCtr'), orchestration: val('wlNewOrch'), lang: 'zh' });
        const ts = await V3.j('/api/v1/local/templates'); L.templates = ts.templates || L.templates;
        closeNew();
        T.msg = `建好了「${name}」(${r.id}.template · 可写)`;
        window.WL_setWorld && window.WL_setWorld(r.id);   // 当前世界 = 它:各页跟着它
        if (S.screen === 'tpl') loadTpl(r.id);
      } else if (NEW.kind === 'world') {
        const tid = S.world, r = await send('POST', `/api/v1/local/templates/${encodeURIComponent(tid)}/world/new`, { title: name });
        const ts = await V3.j('/api/v1/local/templates'); L.templates = ts.templates || L.templates;
        closeNew();
        T.msg = `「${title(r.template)}」换上了新世界「${name}」` + (r.dropped && r.dropped.length ? ` · 旧世界自带的角色不再出场:${r.dropped.join('、')}` : '');
        if (window.DUO) { window.DUO.wid = null; window.DUO.msg = T.msg; }
        window.LIVE_reopenWorld && window.LIVE_reopenWorld(tid);   // 编辑副本按新世界重建
        if (T.id === tid) loadTpl(tid);
      } else {
        const r = await send('POST', '/api/v1/local/souls/blank', { name, intro: val('wlNewIntro'), lang: 'zh' });
        let note = `「${name}」进了角色库`;
        if ($('#wlNewLink') && $('#wlNewLink').checked && S.world) {
          const w = L.templates.find(x => x.id === S.world) || {};
          try {
            const k = await send('POST', `/api/v1/local/templates/${encodeURIComponent(S.world)}/souls/link`, { lib: r.soul_dir });
            note += `,也加进了「${title(w)}」`;
            if (k.edit && window.DUO) { window.DUO.wid = null; S.face = 'soul'; S.duoTab.soul = 'cards'; }   // 编辑副本里有了它:重读角色卡
            if (T.id === S.world) loadTpl(S.world);
          } catch (err) {   // 角色已经进库了:把原因留在弹窗里(不再按「建」第二次)
            newMsg(note + (/只读|read-only/.test(err.message) ? `;「${title(w)}」是内置模板(只读),先在 Template 页「复制一份来改」或新建一个 Template 再加进去` : `;没加进世界:${err.message}`));
            $('#wlNewPop .row:last-child').innerHTML = '<button class="btn" data-wlnewx>好</button>'; NEW.busy = false; return;
          }
        }
        closeNew();
        T.msg = note;
      }
    } catch (err) { newMsg('没建成:' + err.message); NEW.busy = false; return; }
    NEW.busy = false; render();
  }
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-wlnew]'); if (b) { newPop(b.dataset.wlnew, b); return; }
    if (e.target.closest('[data-wlnewgo]')) { newGo(); return; }
    if (e.target.closest('[data-wlnewx]')) { closeNew(); return; }
    if (e.target.closest('[data-wlnewtpl]')) { closeNew(); const nb = $('#nav [data-go=tpl]'); if (nb) nb.click(); setTimeout(() => { const t = $('[data-wlnew=tpl]'); if (t) newPop('tpl', t); }, 60); return; }
    if (NEW.kind && !e.target.closest('#wlNewPop')) closeNew();
  });
  document.addEventListener('keydown', e => { if (!NEW.kind) return; if (e.key === 'Escape') closeNew(); else if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.closest('#wlNewPop')) newGo(); });

  /* 前端台的契约导出:frontends.js(契约页 = 当前世界 S.world || L.bound 的 contract?fmt=ts|gd|json,10-17) */

  /* ================================================================ 测试台:出口检查 = 本局合约 + 结算产物(R5) */
  const X = { turn: -1, contract: null, settle: null };
  async function loadExit() {
    const t = (E.s && E.s.turn) ?? 0; if (X.turn === t + ':' + L.slug) return; X.turn = t + ':' + L.slug;
    [X.contract, X.settle] = await Promise.all([V3.j('/api/v1/play/engine/contract').catch(() => null), V3.j('/api/v1/play/engine/settlement').catch(() => null)]);
    if (S.screen === 'test') renderTest();
  }
  const OUT = { ending_id: '结局', cg_unlocked: '解锁的 CG', epilogue: '尾声', rewards_granted: '奖励发放', replay_bundle: '回放包', segment_id: '段落', accusation: '指认结果', truth_reveal: '真相揭晓', affection_delta: '好感变化' };
  const _test = renderTest;
  renderTest = function () {
    _test(); loadExit();
    const box = [...document.querySelectorAll('#s-test .mk-left .glass')].find(e => /出口检查/.test(e.textContent)); if (!box) return;
    const c = X.contract && X.contract.id ? X.contract : null, st = X.settle && X.settle.exit ? X.settle : null;
    const have = k => st && (k === 'ending_id' ? !!st.exit.id : k === 'cg_unlocked' ? (st.cg_unlocked || []).length > 0 : k === 'epilogue' ? !!st.epilogue : k === 'rewards_granted' ? !!st.rewards : k === 'replay_bundle' ? true : k in st);
    box.innerHTML = `<span class="tag">出口检查 · ${c ? esc(c._ref || c.id) : '这局没有合约'}</span>
      ${c ? (c.outputs || []).map(o => `<div class="row" style="padding:4px 0;font-size:13px"><span class="dot ${st ? (have(o) ? 'ok' : 'bad') : ''}"></span>${esc(OUT[o] || o)}</div>`).join('') : '<div class="sub" style="font-size:12.5px;margin-top:6px">没声明合约的局没有固定输出要查;去 Template 看怎么声明</div>'}
      ${st ? `<div class="bt set" style="margin-top:10px;font:13px var(--ui)"><div class="who">已到出口 · ${esc(st.exit.kind)} ${esc(st.exit.id || '')} · 第 ${esc(st.exit.turn)} 回合</div>${esc((st.epilogue || '').slice(0, 120))}${(st.deaths || []).length ? `<br><span class="sub">死亡记录 ${st.deaths.length} 条</span>` : ''}</div>` : c ? '<div class="sub" style="font-size:12px;margin-top:8px">还没到出口 · 到了之后这里列出结算产物</div>' : ''}`;
  };

})();
