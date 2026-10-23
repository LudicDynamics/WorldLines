/* 剧情图 = 世界源文件里的 plots/<id>/plot.json(编辑会话读写,和地图同一份工作副本)。
   一张 plot:stages[i] 是 <id>.stage = i 时的阶段;triggers 把阶段往前推(then 里 set <id>.stage)或者走到结局(then 里 end);endings 是结局。
   图上:阶段 / 结局 = 节点,触发器 = 连线(条件读自 when / if)。
   写回:改阶段 / 结局的名字、加阶段、加结局、删没被指向的结局、删触发器 → PUT edit-local/file。
   触发器的条件是结构化的(说到哪些词 / 进哪个地点 / 变量),图上不手写,跟创作 agent 说。位置只是排版,存在本机。 */
(() => {
  const EDIT = '/api/v1/create/session/edit-local';
  const P = { wid: null, files: {}, assets: new Set(), loading: false, msg: '', drafts: {} };   // drafts[path][tid]:拖出来还没填完条件的触发器,只在界面上
  window.PLOTLIVE = P;
  const real = () => !!P.wid && Object.keys(P.files).length > 0;
  const ours = () => !!P.wid && P.wid === TPL() && (real() || P.writable);   // 有剧情,或者是自己的模板(可以建第一张)
  const onPlot = () => S.screen === 'duo' && S.face === 'world' && S.duoTab.world === 'plot';
  const LK = () => 'wl-plot-layout:' + P.wid;
  const layout = () => { try { return JSON.parse(localStorage.getItem(LK()) || '{}'); } catch { return {}; } };
  const saveLayout = () => { try { localStorage.setItem(LK(), JSON.stringify(Object.fromEntries(Object.entries(PLOT.nodes).map(([k, n]) => [k, [Math.round(n.x * 10) / 10, Math.round(n.y * 10) / 10]])))); } catch { /* storage off */ } };
  const OPS = { '>=': '≥', '<=': '≤', '>': '>', '<': '<', '==': '=', '!=': '≠' };
  // 地点名:先查编辑中的世界地图(全部真相),再退回这一局的
  const pname = a => { const lv = (window.MAPW && window.MAPW.edit && window.MAPW.edit.levels) || {};
    for (const L of Object.values(lv)) { const n = (L.nodes || {})[a]; if (n && n.name && !n.fog) return n.name; }
    return window.LIVE_placeName ? window.LIVE_placeName(a) : a; };

  // 剧情是模板层的(plots/ 和 template.json 平级),不在世界副本里:读 世界 · 角色 选中的那个模板
  const TPL = () => (window.MAPHOOK && window.MAPHOOK.wtpl) || (window.LIVE && window.LIVE.bound) || null;
  // 触发器 ↔ 表单:只动认得的那几块(when · 一条非阶段的 if · once · 一条旁白),其余原样保留
  const OPSET = ['<=', '<', '==', '!=', '>=', '>'];
  const trigOf = e => ((P.files[e.path] || {}).triggers || {})[e.tid] || (P.drafts[e.path] || {})[e.tid];
  function trigForm(tr, e) {
    const w = tr.when || {}, sv = `${(PLOT.nodes[e.from] || {}).pid}.stage`, ifs = tr.if || [];
    const textC = ifs.find(c => c.text), varC = ifs.find(c => c.var && c.var !== sv), stageC = ifs.find(c => c.var === sv);
    const kind = w.entry ? 'entry' : w.var && !w.text ? 'var' : 'text';
    const vop = varC ? OPSET.find(o => varC[o] !== undefined) || '<=' : '<=';
    const narr = ((tr.then || []).find(t => t.to === 'narration') || {}).text || '';
    const words = textC ? [].concat(textC.text) : [];
    const toN = PLOT.nodes[e.to] || {};
    return { kind, words, playerOnly: (textC && textC.in === 'player') || w.text === 'player', entry: w.entry || '', vname: varC ? varC.var : (w.var || ''), vop, vval: varC ? String(varC[vop] ?? '') : '',
      narr, stageNote: stageC ? `${sv} ${OPSET.find(o => stageC[o] !== undefined)} ${stageC[OPSET.find(o => stageC[o] !== undefined)]}` : '任何阶段',
      then: toN.kind === 'ending' ? `走到结局 ${toN.eid}` : `${sv} = ${toN.idx}`,
      incomplete: kind === 'text' ? !words.filter(Boolean).length : kind === 'entry' ? !w.entry : !(varC || w.var) };
  }
  function applyForm(tr, e, k, v) {
    const sv = `${(PLOT.nodes[e.from] || {}).pid}.stage`;
    tr.if = (tr.if || []).filter(Boolean);
    const others = () => tr.if.filter(c => c.var === sv || (!c.text && !c.var));   // 阶段条件和不认识的,留着
    const f = trigForm(tr, e);
    if (k === 'once') { tr.once = !!v; return; }
    if (k === 'narr') { tr.then = (tr.then || []).filter(t => t.to !== 'narration'); if (String(v).trim()) tr.then.push({ to: 'narration', text: String(v) }); return; }
    const kind = k === 'kind' ? v : f.kind;
    const words = k === 'words' ? String(v).split(/[,,、]/).map(x => x.trim()).filter(Boolean) : f.words;
    const player = k === 'player' ? !!v : f.playerOnly;
    if (kind === 'text') { tr.when = { text: player ? 'player' : 'both' }; tr.if = [...others(), { text: words, ...(player ? { in: 'player' } : {}) }]; }
    else if (kind === 'entry') { tr.when = { entry: k === 'entry' ? String(v).trim() : f.entry, event: 'enter' }; tr.if = others(); }
    else { const name = k === 'vname' ? String(v).trim() : f.vname, op = k === 'vop' ? v : f.vop, raw = k === 'vval' ? v : f.vval, num = Number(raw);
      tr.when = { var: name }; tr.if = [...others(), ...(name ? [{ var: name, [op]: raw === '' || isNaN(num) ? raw : num }] : [])]; }
  }
  function placeOpts() {
    const lv = (window.MAPW && window.MAPW.edit && window.MAPW.edit.levels) || {}, out = [];
    for (const L of Object.values(lv)) for (const [a, n] of Object.entries(L.nodes || {})) out.push(`<option value="${esc(a)}">${esc(n.name || a)}</option>`);
    return out.join('');
  }
  function newTrigger(e) {
    const from = PLOT.nodes[e.from], to = PLOT.nodes[e.to];
    if (!from || !to || from.kind !== 'stage' || from.path !== to.path) return '触发器要从一个阶段连到同一张剧情里的阶段或结局';
    const j = P.files[from.path], sv = `${from.pid}.stage`, dr = P.drafts[from.path] = P.drafts[from.path] || {};
    let n = Object.keys(j.triggers || {}).length + Object.keys(dr).length + 1, tid; do tid = `${from.pid}.t${n++}`; while ((j.triggers || {})[tid] || dr[tid]);
    // 条件没填的触发器引擎认为剧情文件有错(建局会失败),所以先当草稿留在界面上,填完才写进 plot.json
    dr[tid] = { when: { text: 'both' }, if: [{ var: sv, '>=': from.idx }, { text: [] }], once: true,
      then: [to.kind === 'ending' ? { to: 'end', ending: to.eid } : { to: 'var', var: sv, set: to.idx }] };
    S.gsel = { t: 'edge', id: `${from.pid}#t:${tid}` }; S.rtab = 'insp';
    P.msg = `新触发器 ${tid}(草稿):在右边填条件,填完才写进文件`; build();
    return '';
  }

  async function load(force) {
    const tid = TPL(); if (!tid) return;
    if (P.loading || (!force && P.wid === tid)) return;
    if (P.wid !== tid) P.drafts = {};   // 换了模板:上一个模板的草稿不带过来
    P.loading = true; P.wid = tid;
    try {
      const v = await V3.j(`/api/v1/local/templates/${encodeURIComponent(tid)}/plots`);
      P.writable = !!v.writable; P.forkable = v.forkable !== false; P.files = {}; P.assets = new Set();
      for (const r of v.plots || []) if (r.data) { P.files[r.path] = r.data; (r.files || []).forEach(f => P.assets.add(r.path.replace(/plot\.json$/, f))); }
      if (!force) P.msg = '';
      build();
    } catch (e) { P.msg = '读剧情失败:' + (e.message || e); }
    P.loading = false;
    if (onPlot()) renderDuo();
  }

  const sid = (p, i) => `${p}#s${i}`, eid = (p, e) => `${p}#${e}`;
  function stageFrom(tr, sv, to) {
    for (const c of tr.if || []) if (c.var === sv) {
      if (c['>='] !== undefined) return +c['>='];
      if (c['>'] !== undefined) return +c['>'] + 1;
      if (c['=='] !== undefined) return +c['=='];
      if (c['<'] !== undefined) return Math.max(0, +c['<'] - 1);
      if (c['<='] !== undefined) return +c['<='];
    }
    return typeof to === 'number' ? Math.max(0, to - 1) : 0;
  }
  function describe(tr, sv) {
    const w = tr.when || {}, out = [];
    if (w.entry) out.push(`${w.event === 'leave' ? '离开' : '进入'} ${pname(w.entry)}`);
    for (const c of tr.if || []) {
      if (c.var === sv) continue;
      if (c.text) out.push([].concat(c.text).filter(Boolean).length ? `说到「${[].concat(c.text).slice(0, 3).join(' / ')}」${c.in === 'player' ? '(你说)' : ''}` : '说到…(还没填词)');
      else if (c.var) { const op = Object.keys(OPS).find(k => c[k] !== undefined); out.push(op ? `${c.var} ${OPS[op]} ${c[op]}` : c.var); }
    }
    if (!out.length && w.var) out.push(`${w.var} 变了`);
    return out.join(' · ') || '无条件';
  }
  function build() {
    for (const k of Object.keys(PLOT.nodes)) delete PLOT.nodes[k];
    PLOT.edges.length = 0; S.endings.length = 0;
    const L = layout(), files = Object.entries(P.files), n = files.length;
    files.forEach(([path, j], pi) => {
      const pid = j.id || path.split('/')[1], sv = `${pid}.stage`, folder = path.split('/')[1];
      const stages = (j.stages && j.stages.length ? j.stages : ['开始']), ends = Object.entries(j.endings || {});
      const x0 = (pi + .5) / n * 100, colW = 100 / n;
      stages.forEach((s, i) => {
        const id = sid(pid, i), at = L[id];
        PLOT.nodes[id] = { x: at ? at[0] : Math.max(6, x0 - colW * .18), y: at ? at[1] : 10 + i * (56 / Math.max(1, stages.length - 1 || 1)), kind: 'stage', title: LOC(s),
          note: i === 0 ? `${LOC(j.title) || pid} · ${sv} = 0` : `${sv} = ${i}`, path, pid, idx: i };
      });
      ends.forEach(([e, v], k) => {
        const id = eid(pid, e), at = L[id];
        const img = v.assets && v.assets.image ? `plots/${folder}/${v.assets.image}` : `plots/${folder}/${e.toLowerCase()}.png`;
        PLOT.nodes[id] = { x: at ? at[0] : x0 - colW * .4 + (k + .5) * (colW * .8 / ends.length), y: at ? at[1] : 86, kind: 'ending', title: `${e} ${LOC(v.title)}`.trim(), path, pid, eid: e };
        S.endings.push({ id, title: LOC(v.title) || e, kind: v.kind || 'alt', cg: P.assets.has(img) });
      });
      const drafts = P.drafts[path] || {};
      for (const [tid, tr] of [...Object.entries(j.triggers || {}), ...Object.entries(drafts).filter(([k]) => !(j.triggers || {})[k])]) {
        const then = tr.then || [];
        const set = then.find(t => t.to === 'var' && t.var === sv && typeof t.set === 'number'), end = then.find(t => t.to === 'end');
        const to = end ? eid(pid, end.ending) : set ? sid(pid, set.set) : null;
        if (!to || !PLOT.nodes[to]) continue;   // 只播旁白 / 只改别的变量的触发器不画线
        const from = sid(pid, Math.min(stages.length - 1, stageFrom(tr, sv, set ? set.set : null)));
        const draft = !!drafts[tid];
        PLOT.edges.push({ id: `${pid}#t:${tid}`, from, to, label: (draft ? '草稿 · ' : '') + describe(tr, sv), path, tid, real: true, draft });
      }
    });
  }

  async function write(path, j, note) {
    if (!P.writable) { P.msg = 'readonly'; await load(true); return; }   // 内置模板:先复制成自己的(操作条上有按钮)
    const r = await fetch(V3.url(`/api/v1/local/templates/${encodeURIComponent(P.wid)}/plots`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, data: j }) });
    const d = await r.json().catch(() => ({}));
    const blocks = ((d.lint || {}).counts || {}).block || 0;
    P.msg = r.ok ? `写回 ${path} · ${note}${blocks ? ` · lint ${blocks} 个 block` : ''}` : `写回失败:${d.error || r.status}`;
    await load(true);
  }
  const plotOf = id => { const n = PLOT.nodes[id]; return n && P.files[n.path] ? [n, P.files[n.path]] : [null, null]; };

  // 图上:操作条 + 检查器换成真实文件的语义
  const _act = edActions;
  edActions = function (f, tab) {
    if (tab !== 'plot' || !ours()) return tab === 'plot' && P.loading ? '<span class="tag">读剧情……</span>' : _act(f, tab);
    const ro = !P.writable ? `${P.forkable === false ? '' : '<button class="btn p" data-pfork>复制成我的模板再改</button>'}<span class="tag">${P.forkable === false ? '官方世界 · 只能玩,不能复制 · ' : ''}${P.msg === 'readonly' ? '内置模板不能直接改 · ' : ''}剧情属于模板 ${esc(P.wid)}(内置,只读)</span>` : '';
    return `${ro}<button class="btn" data-addn="stage" ${P.writable ? '' : 'disabled'}>+ 阶段</button><button class="btn" data-addn="ending" ${P.writable ? '' : 'disabled'}>+ 结局</button>${P.writable ? `<span class="tag">${esc(P.msg || '模板 ' + P.wid + ' · ' + Object.keys(P.files).join(' · '))}</span>` : ''}`;
  };
  const _body = edBody;
  edBody = function (f, tab) {
    if (tab === 'plot' && !real() && !P.loading && P.wid && P.wid === TPL())
      return `<div class="mpempty"><div class="mpe"><img src="img/icon-frames.png" alt=""><b>这个世界还没有剧情</b><span>剧情在模板的 plots/&lt;id&gt;/plot.json:阶段、触发器、结局。</span></div></div>`;
    return _body(f, tab);
  };
  const _insp = inspector2;
  inspector2 = function () {
    if (!(onPlot() && real())) return _insp();
    const sel = S.gsel;
    if (sel && sel.t === 'edge') {
      const e = PLOT.edges.find(x => x.id === sel.id); if (!e) return _insp();
      const tr = trigOf(e) || {}, f = trigForm(tr, e);
      const ro = !P.writable ? 'disabled' : '', at = k => `data-tf2="${esc(e.id)}:${k}" ${ro}`;
      return `<div class="tag">触发器 · ${esc(e.tid)}</div><h3>${esc((PLOT.nodes[e.from] || {}).title)} → ${esc((PLOT.nodes[e.to] || {}).title)}</h3>
        <label class="tag" style="display:block;margin-top:12px">怎么触发</label>
        <select class="cell" style="width:100%;margin:6px 0 10px" ${at('kind')}>${[['text', '说到某些词'], ['entry', '进入某个地点'], ['var', '某个变量变了']].map(([k, l]) => `<option value="${k}" ${f.kind === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
        ${f.kind === 'text' ? `<label class="tag" style="display:block">说到哪些词 · 逗号分开(任一个就算)</label><input class="cell" style="width:100%;margin:6px 0 8px" value="${esc(f.words.join(', '))}" placeholder="护身符, 徽记" ${at('words')}>
          <label class="row" style="gap:8px;font-size:13px;margin-bottom:6px"><input type="checkbox" ${f.playerOnly ? 'checked' : ''} ${at('player')}>只算玩家说的(不算主持 / 角色)</label>`
        : f.kind === 'entry' ? `<label class="tag" style="display:block">哪个地点(地址)</label><input class="cell mono" style="width:100%;margin:6px 0 8px" value="${esc(f.entry)}" placeholder="T004/chapel" list="ptplaces" ${at('entry')}><datalist id="ptplaces">${placeOpts()}</datalist>`
        : `<label class="tag" style="display:block">变量条件</label><div class="row" style="gap:6px;margin:6px 0 8px"><input class="cell mono" style="flex:1" value="${esc(f.vname)}" placeholder="player.hp" ${at('vname')}>
          <select class="cell" ${at('vop')}>${['<=', '<', '==', '!=', '>=', '>'].map(o => `<option ${f.vop === o ? 'selected' : ''}>${o}</option>`).join('')}</select><input class="cell mono" style="width:70px" value="${esc(f.vval)}" ${at('vval')}></div>`}
        <label class="row" style="gap:8px;font-size:13px;margin:4px 0 10px"><input type="checkbox" ${tr.once ? 'checked' : ''} ${at('once')}>只触发一次</label>
        <label class="tag" style="display:block">触发时的旁白(可空)</label><textarea class="cell" style="width:100%;min-height:60px;margin-top:6px" ${at('narr')}>${esc(f.narr)}</textarea>
        <div class="sub" style="font-size:12px;margin-top:8px">阶段条件跟着连线的起点:${esc(f.stageNote)} · 结果:${esc(f.then)}</div>
        ${f.incomplete ? '<div class="iss block" style="margin-top:8px"><span class="dot bad"></span><div><b>条件还没填</b><small>这个触发器现在不会触发</small></div></div>' : ''}
        <div class="row" style="margin-top:12px"><button class="btn" data-pdeltrig="${esc(e.id)}" ${ro}>删掉这个触发器</button></div>`;
    }
    if (sel && sel.t === 'node' && PLOT.nodes[sel.id]) {
      const n = PLOT.nodes[sel.id], ins = PLOT.edges.filter(e => e.to === sel.id), outs = PLOT.edges.filter(e => e.from === sel.id);
      const en = n.kind === 'ending' ? S.endings.find(x => x.id === sel.id) : null;
      const v = n.kind === 'ending' ? (P.files[n.path].endings || {})[n.eid] || {} : null;
      return `<div class="tag">${n.kind === 'ending' ? '结局 · ' + esc(n.eid) : '阶段 · ' + esc(n.note)}</div><h3>${esc(n.kind === 'ending' ? LOC(v.title) || n.eid : n.title)}</h3>
        <label class="tag" style="display:block;margin-top:14px">名字</label><input class="cell" style="width:100%;margin:6px 0 12px" value="${esc(n.kind === 'ending' ? LOC(v.title) : n.title)}" data-ptitle="${esc(sel.id)}">
        ${n.kind === 'ending' ? `<label class="tag" style="display:block">类型</label><select class="cell" style="width:100%;margin:6px 0 12px" data-pkind="${esc(sel.id)}">${[['true', '真相'], ['alt', '分支'], ['fail', '失败']].map(([k, l]) => `<option value="${k}" ${v.kind === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <div class="row" style="gap:6px">${en && en.cg ? '<span class="chip sage">CG ✓</span>' : '<span class="chip rust">还没有 CG · Template 的素材槽里生成</span>'}</div>` : ''}
        <div class="tag" style="margin-top:14px">进来 ${ins.length} · 出去 ${outs.length}</div><div style="margin-top:6px">${[...ins, ...outs].map(e => `<div class="row" style="padding:4px 0;font-size:12.5px"><span class="dot"></span>${esc((PLOT.nodes[e.from] || {}).title)} → ${esc((PLOT.nodes[e.to] || {}).title)}<span class="sub" style="margin:0 0 0 6px;font-size:11.5px">${esc(e.label)}</span></div>`).join('') || '<div class="sub" style="font-size:12px">还没有触发器连到这里</div>'}</div>
        ${n.kind === 'ending' ? `<div class="row" style="margin-top:16px"><button class="btn" data-pdelend="${esc(sel.id)}" ${ins.length ? 'disabled title="先删掉指向它的触发器"' : ''}>删除这个结局</button></div>` : ''}`;
    }
    return `<div class="tag">检查器 · 剧情</div><h3>点阶段、结局或连线</h3><p class="sub">名字、结局类型直接写回 plot.json;连线是触发器,条件跟创作 agent 说。</p>`;
  };

  // 加 / 删 / 改名 都写回文件;拦在 app.js 的演示处理之前
  document.addEventListener('click', e => {
    if (!(onPlot() && ours())) return;
    const q = s => e.target.closest(s); let t;
    const pick = () => { const id = S.gsel && S.gsel.id, n = id && PLOT.nodes[id]; if (n) return n.path; const k = Object.keys(P.files)[0] || 'plots/main/plot.json'; P.files[k] = P.files[k] || { id: 'main', title: '主线', stages: ['开始'], triggers: {}, endings: {} }; return k; };
    if ((t = q('[data-addn]')) && ['stage', 'ending'].includes(t.dataset.addn)) {
      e.stopImmediatePropagation();
      const path = pick(), j = P.files[path];
      if (t.dataset.addn === 'stage') { j.stages = (j.stages && j.stages.length ? j.stages : ['开始']).concat('新阶段'); S.gsel = { t: 'node', id: sid(j.id || path.split('/')[1], j.stages.length - 1) }; write(path, j, '+ 阶段'); }
      else { j.endings = j.endings || {}; let i = Object.keys(j.endings).length + 1, k; do k = 'E' + String(i++).padStart(2, '0'); while (j.endings[k]); j.endings[k] = { title: '新结局', kind: 'alt' }; S.gsel = { t: 'node', id: eid(j.id || path.split('/')[1], k) }; write(path, j, `+ 结局 ${k}`); }
      S.rtab = 'insp'; return;
    }
    if (q('[data-pfork]')) { (async () => { const base = P.wid, nid = (base + '-mine').slice(0, 40);
      const r = await fetch(V3.url(`/api/v1/local/templates/${encodeURIComponent(base)}/fork`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: nid, title: ((window.LIVE.templates.find(x => x.id === base) || {}).card || {}).title + '(我的)' }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { P.msg = '复制失败:' + (d.error || r.status); renderDuo(); return; }
      const ts = await V3.j('/api/v1/local/templates').catch(() => null); if (ts) window.LIVE.templates.splice(0, window.LIVE.templates.length, ...ts.templates);
      P.msg = `复制好了:${d.id || nid},现在改的是你自己的模板`;
      if (window.LIVE_openWorld) await window.LIVE_openWorld(d.id || nid); load(true); })(); return; }
    if ((t = q('[data-fix^="cg:"]'))) { e.stopImmediatePropagation(); if (window.LIVE_openTpl) window.LIVE_openTpl(P.wid); return; }   // CG 在 Template 的素材槽里生成
    if ((t = q('[data-pdeltrig]'))) { const ed = PLOT.edges.find(x => x.id === t.dataset.pdeltrig); if (!ed) return; S.gsel = null;
      if ((P.drafts[ed.path] || {})[ed.tid]) { delete P.drafts[ed.path][ed.tid]; build(); renderDuo(); return; }
      delete P.files[ed.path].triggers[ed.tid]; write(ed.path, P.files[ed.path], `删触发器 ${ed.tid}`); return; }
    if ((t = q('[data-pdelend]'))) { const [n, j] = plotOf(t.dataset.pdelend); if (n) { delete j.endings[n.eid]; S.gsel = null; write(n.path, j, `删结局 ${n.eid}`); } return; }
    if (q('[data-ndel]') || q('[data-edel]')) { e.stopImmediatePropagation(); }
  }, true);
  document.addEventListener('change', e => {
    if (!(onPlot() && real())) return;
    const d = e.target.dataset;
    if (d.tf2) { const [eid, k] = [d.tf2.slice(0, d.tf2.lastIndexOf(':')), d.tf2.slice(d.tf2.lastIndexOf(':') + 1)];
      const ed = PLOT.edges.find(x => x.id === eid); if (!ed || !P.writable) return;
      const j = P.files[ed.path], tr = trigOf(ed); if (!tr) return;
      applyForm(tr, ed, k, e.target.type === 'checkbox' ? e.target.checked : e.target.value);
      const dr = P.drafts[ed.path] || {};
      if (dr[ed.tid]) {
        if (trigForm(tr, ed).incomplete) { build(); renderDuo(); return; }   // 还没填完:留在草稿
        (j.triggers = j.triggers || {})[ed.tid] = tr; delete dr[ed.tid];
        write(ed.path, j, `+ 触发器 ${ed.tid}`); return;
      }
      write(ed.path, j, `触发器 ${ed.tid} · ${k}`); return; }
    if (d.ptitle) { const [n, j] = plotOf(d.ptitle); const v = e.target.value.trim(); if (!n || !v) return;
      if (n.kind === 'ending') { j.endings[n.eid].title = LOCSET(j.endings[n.eid].title, v); write(n.path, j, `结局 ${n.eid} 改名`); } else { j.stages[n.idx] = LOCSET(j.stages[n.idx], v); write(n.path, j, `阶段 ${n.idx} 改名`); } }
    if (d.pkind) { const [n, j] = plotOf(d.pkind); if (n) { j.endings[n.eid].kind = e.target.value; write(n.path, j, `结局 ${n.eid} 类型`); } }
  });
  // 拖完记住位置(只是排版,不写文件)
  document.addEventListener('pointerup', () => { if (onPlot() && real()) setTimeout(saveLayout, 0); });

  // 切到剧情页 / 换了世界 → 读
  const _duo = renderDuo;
  renderDuo = function () {
    if (onPlot() && TPL() && P.wid !== TPL() && !P.loading) { for (const k of Object.keys(PLOT.nodes)) delete PLOT.nodes[k]; PLOT.edges.length = 0; P.files = {}; load(); }
    if (onPlot() && real() && PLOT.edges.some(e => !e.real)) {   // 图上拖出来的线 = 新触发器(条件在检查器里填)
      const fresh = PLOT.edges.filter(e => !e.real);
      for (let i = PLOT.edges.length - 1; i >= 0; i--) if (!PLOT.edges[i].real) PLOT.edges.splice(i, 1);
      if (S.gsel && S.gsel.t === 'edge' && !PLOT.edges.some(e => e.id === S.gsel.id)) S.gsel = null;
      if (!P.writable) P.msg = '内置模板只读:先「复制成我的模板再改」';
      else { const why = newTrigger(fresh[0]); if (why) P.msg = why; }
    }
    _duo();
  };
  window.LIVE_reloadPlots = () => load(true);
  const _bm = window.LIVE_buildMap;   // 创作 agent 改完文件会重读地图:剧情跟着重读
  window.LIVE_buildMap = function () { if (P.wid) load(true); return _bm && _bm.apply(this, arguments); };
})();
