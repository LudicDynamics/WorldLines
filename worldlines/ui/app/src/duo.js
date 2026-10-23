/* 世界 · 角色 = 编辑中的这个世界的真实文件夹(10-06)。文件系统是唯一真相,界面只是它的几种看法:
   · 文件树 = edit-local/tree(+ 模板层的 plots/,剧情属于模板)。点文件跳到能编辑它的那一页。
   · 角色卡 = souls/<dir>/soul.json(名字 · 简介)+ 模板素材槽里的立绘。
   · 关系图 = 每个角色的 souls/<dir>/persona/relationships.json(游玩时角色读的就是它):连线 = 一条关系,标签 = disposition。
   · 数据页 = 选一个文件,按它的字段出表单(字符串 / 数字 / 开关 / 嵌套的给 JSON),保存 = PUT edit-local/file。
   写回都走 PUT edit-local/file;关系图的位置只是排版,存在本机。 */
(() => {
  const EDIT = '/api/v1/create/session/edit-local';
  const D = { wid: null, files: [], souls: {}, open: new Set(['game', 'souls', '~plots']), cache: {}, dirty: {}, fv: {}, sel: { world: null, soul: {} }, msg: '', loading: false };
  window.DUO = D;
  const ready = () => !!D.wid && window.MAPHOOK && window.MAPHOOK.edit && D.wid === window.MAPHOOK.edit.world_id;
  D.ready = ready;
  const tpl = () => (window.MAPHOOK && window.MAPHOOK.wtpl) || '';
  const getFile = p => V3.j(`${EDIT}/file?path=${encodeURIComponent(p)}`).then(r => (typeof r.content === 'string' ? r.content : JSON.stringify(r.content, null, 2)));
  const putFile = async (p, text) => {
    const r = await fetch(V3.url(EDIT + '/file'), { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: p, content: text }) });
    if (!r.ok) throw new Error('写回失败 ' + r.status);
    D.cache[p] = text; delete D.dirty[p]; delete D.fv[p];
  };
  const parse = t => { try { return JSON.parse(t); } catch { return undefined; } };
  const LK = () => 'wl-rel-layout:' + D.wid;
  const layout = () => { try { return JSON.parse(localStorage.getItem(LK()) || '{}'); } catch { return {}; } };
  const saveLayout = () => { try { localStorage.setItem(LK(), JSON.stringify(Object.fromEntries(Object.entries(REL.nodes).map(([k, n]) => [k, [n.x, n.y]])))); } catch { /* storage off */ } };

  async function load() {
    const h = window.MAPHOOK; if (!h || !h.edit || D.loading) return;
    D.loading = true; const wid = h.edit.world_id;
    try {
      const tree = await V3.j(EDIT + '/tree');
      D.files = (tree.files || []).map(f => f.path).filter(p => !/^\.(neonrp|claude)\//.test(p)).sort();   // 引擎内部 / agent 工作文件不给作者看
      D.cache = {}; D.dirty = {}; D.fv = {}; D.souls = {}; D.persona = {}; D.sel = { world: null, soul: {} };
      const dirs = [...new Set(D.files.filter(p => /^souls\/[^/]+\/soul\.json$/.test(p)).map(p => p.split('/')[1]))];
      const got = {};   // 先全读完,再按文件夹顺序放进 D.souls(之前按读完的先后,默认显示哪个角色是随机的)
      await Promise.all(dirs.map(async dir => {
        const soul = parse(await getFile(`souls/${dir}/soul.json`).catch(() => '{}')) || {};
        const relPath = `souls/${dir}/persona/relationships.json`;
        const rel = D.files.includes(relPath) ? parse(await getFile(relPath).catch(() => '{}')) || {} : {};
        const sid = soul.sid || dir.split('-si-')[0];
        const intro = soul.intro_i18n || {};
        got[dir] = { sid, dir, name: soul.name_local || soul.name || sid, intro: intro.zh || intro.en || soul.intro || '', relPath, rel, tags: soul.tags || [] };
      }));
      dirs.forEach(dir => { if (got[dir]) D.souls[got[dir].sid] = got[dir]; });
      D.wid = wid; D.msg = '';
      apply();
    } catch (e) { D.msg = '读世界文件失败:' + (e.message || e); }
    D.loading = false;
    if (S.screen === 'duo') renderDuo();
  }

  // 角色卡 / 关系图的数据换成这个世界的
  function apply() {
    for (const k of Object.keys(SOULS)) delete SOULS[k];
    const firstPlace = Object.keys(PLACES)[0];
    for (const s of Object.values(D.souls)) {
      SOULS[s.sid] = { name: s.name, img: tpl() ? V3.url(`/api/v1/local/templates/${encodeURIComponent(tpl())}/assets/file?slot=${encodeURIComponent('soul.portrait:' + s.sid)}`) : '',
        line: s.intro.slice(0, 60) + (s.intro.length > 60 ? '…' : ''), at: firstPlace, say: '', data: {}, haunts: [] };
      SVAL[s.sid] = { mood: (s.tags || [])[0] || '' };
    }
    if (S.pick.t === 'soul' && !SOULS[S.pick.id]) S.pick = { t: 'soul', id: Object.keys(SOULS)[0] };
    buildRel();
  }
  const relOf = s => (s.rel && s.rel.relationships && !Array.isArray(s.rel.relationships) ? s.rel.relationships : {});
  function buildRel() {
    for (const k of Object.keys(REL.nodes)) delete REL.nodes[k];
    REL.edges.length = 0;
    const L = layout(), ids = ['player', ...Object.keys(D.souls)];
    for (const s of Object.values(D.souls)) for (const o of Object.keys(relOf(s))) if (!ids.includes(o)) ids.push(o);
    ids.forEach((id, i) => {
      const a = (i / ids.length) * Math.PI * 2 - Math.PI / 2, at = L[id], s = D.souls[id];
      REL.nodes[id] = { x: at ? at[0] : 50 + Math.cos(a) * 32, y: at ? at[1] : 50 + Math.sin(a) * 34, title: id === 'player' ? '你' : s ? s.name : id,
        img: s && SOULS[id] ? SOULS[id].img : '', soul: !!s };
    });
    for (const s of Object.values(D.souls)) for (const [o, r] of Object.entries(relOf(s))) {
      const lab = [r.disposition, r.known === false ? '未相识' : ''].filter(Boolean).join(' · ') || '关系';
      REL.edges.push({ id: `${s.sid}>${o}`, from: s.sid, to: o, label: lab, real: true });
    }
  }
  async function writeRel(sid, note) {
    const s = D.souls[sid]; if (!s) return;
    const j = s.rel && typeof s.rel === 'object' ? s.rel : {};
    if (!j.relationships || Array.isArray(j.relationships)) j.relationships = {};
    j.sid = j.sid || sid; s.rel = j;
    try { await putFile(s.relPath, JSON.stringify(j, null, 2) + '\n'); D.msg = `写回 ${s.relPath} · ${note}`; } catch (e) { D.msg = e.message; }
    buildRel(); renderDuo();
  }

  /* ---------- 文件树 ---------- */
  function nest(paths) {
    const root = {};
    for (const p of paths) { let cur = root; const parts = p.split('/'); parts.forEach((x, i) => { if (i === parts.length - 1) (cur.$f = cur.$f || []).push(p); else cur = cur[x] = cur[x] || {}; }); }
    return root;
  }
  function treeHtml(node, prefix, depth) {
    let out = '';
    for (const k of Object.keys(node).filter(k => k !== '$f').sort()) {
      const key = prefix + k, on = D.open.has(key);
      const n = countFiles(node[k]);
      out += `<div class="tr d" style="padding-left:${depth * 12}px" data-tdir="${esc(key)}"><span class="car">${on ? '▾' : '▸'}</span>${esc(k)}/<i>${n}</i></div>`;
      if (on) out += treeHtml(node[k], key + '/', depth + 1);
    }
    for (const p of node.$f || []) {
      const cur = curFile(), name = p.split('/').pop();
      out += `<div class="tr f ${fileFace(p)}f ${cur === p ? 'on' : ''}" style="padding-left:${depth * 12 + 12}px" data-tfile="${esc(p)}" title="${esc(p)}">${esc(name.replace(/^~plots\//, ''))}</div>`;
    }
    return out;
  }
  const countFiles = n => (n.$f || []).length + Object.keys(n).filter(k => k !== '$f').reduce((a, k) => a + countFiles(n[k]), 0);
  const fileFace = p => (p.startsWith('souls/') ? 'soul' : 'world');
  const curFile = () => (S.face === 'soul' ? D.sel.soul[curSoul()] : D.sel.world);
  function tree() {
    const plots = window.PLOTLIVE ? Object.keys(window.PLOTLIVE.files || {}).map(p => '~' + p) : [];
    const t = nest([...D.files, ...plots]);
    const name = (window.MAPHOOK.edit || {}).name || '';
    return `<div class="tag" style="margin-bottom:6px">一个文件夹 · 两面</div><div class="mono" style="font-size:11px;color:var(--muted);margin-bottom:8px">${esc(name)} · ${D.files.length} 个文件</div><div class="ftree">${treeHtml(t, '', 0)}</div>`;
  }
  function openFile(p) {
    if (p.startsWith('~plots/')) { S.face = 'world'; S.duoTab.world = 'plot'; return; }
    if (/^(game\/meta|registry)\//.test(p) && /schema|classes|vars|variables/.test(p)) { S.face = 'world'; S.duoTab.world = 'schema'; D.sel.world = p; return; }
    const m = p.match(/^souls\/([^/]+)\//);
    if (m) { const s = Object.values(D.souls).find(x => x.dir === m[1]); const sid = s ? s.sid : m[1];
      S.face = 'soul'; S.pick = { t: 'soul', id: sid };
      if (/persona\/relationships\.json$/.test(p)) { S.duoTab.soul = 'rel'; return; }
      D.sel.soul[sid] = p; S.duoTab.soul = 'data'; return; }
    S.face = 'world'; S.duoTab.world = 'data'; D.sel.world = p;
  }

  /* ---------- 数据页:任何一个文件 → 表单 ---------- */
  // 这个文件是哪个类的哪个实例(schema 的 entries:类 → [{id}])+ 哪些字段被注册成了变量
  function annot(p) {
    const sc = D.schema; if (!sc || D.schemaFor !== D.wid) { schemaLoad(); return null; }
    const ids = [];
    let m;
    if ((m = p.match(/^game\/[^/]+\/(.+?)(?:\/location)?\.json$/))) ids.push(m[1], m[1].split('/').pop());
    if ((m = p.match(/^souls\/([^/]+)\//))) { const s = Object.values(D.souls).find(x => x.dir === m[1]); if (s && /\/(soul|character\/stats)\.json$/.test(p)) ids.push(s.sid, 'si-' + s.sid, 'si-' + (m[1].split('-si-')[1] || s.sid)); }
    let cls = null, inst = null;
    for (const [k, rows] of Object.entries(sc.entries || {})) { const hit = (rows || []).find(r => ids.includes(r.id)); if (hit) { cls = sc.classes.find(c => c.name === k); inst = hit; break; } }
    const vars = {};
    for (const v of sc.variables || []) if (v.path === p) { const top = String(v.key || '').split('.')[0]; (vars[top] = vars[top] || []).push(v.name); }
    // 角色的一个类拆在两个文件里:soul.json 有名字(必填),character/stats.json 有 hp 这类属性
    const part = /\/soul\.json$/.test(p) ? 'req' : /character\/stats\.json$/.test(p) ? 'props' : 'all';
    return { cls, inst, vars, part };
  }
  function fileForm(p) {
    if (!p) return '<div class="sub">左边点一个文件,或者在上面选。</div>';
    if (D.cache[p] === undefined) { getFile(p).then(t => { D.cache[p] = t; renderDuo(); }).catch(e => { D.cache[p] = null; D.msg = e.message; renderDuo(); }); return '<div class="sub">读文件……</div>'; }
    if (D.cache[p] === null) return `<div class="sub">读不到 ${esc(p)}</div>`;
    const fv = D.fv[p] || {}, has = k => Object.prototype.hasOwnProperty.call(fv, k);   // 没保存的输入(重画时从这里恢复)
    const txt = D.cache[p], j = /\.json$/.test(p) ? parse(txt) : undefined, raw = D.raw === p || j === undefined || typeof j !== 'object' || Array.isArray(j);
    const head = `<div class="row" style="margin-bottom:10px"><b class="mono" style="font-size:13px">${esc(p)}</b><span class="tag" style="margin-left:auto">${D.dirty[p] ? '改了 · 没保存' : ''}</span>
      ${j !== undefined && !Array.isArray(j) && typeof j === 'object' ? `<button class="chip" data-draw="${esc(p)}">${D.raw === p ? '表单' : '原文'}</button>` : ''}<button class="btn ${D.dirty[p] ? 'p' : ''}" data-dsave="${esc(p)}" ${D.dirty[p] ? '' : 'disabled'}>保存</button></div>`;
    if (raw) return head + `<textarea class="cell mono" data-draw-text="${esc(p)}" spellcheck="false" style="width:100%;min-height:420px;font-size:12px;line-height:1.55">${esc(fv.__raw !== undefined ? fv.__raw : txt)}</textarea>`;
    const an = annot(p), cls = an && an.cls, req = new Set((cls && an.part !== 'props' && cls.required) || []), mut = new Set((cls && cls.mutable) || []), props = (cls && an.part !== 'req' && cls.props) || {};
    const tags = k => [req.has(k) ? '<span class="chip sage" title="这个类要求必须有">必填</span>' : '', mut.has(k) ? '<span class="chip" title="游玩时引擎可以改它">可变</span>' : '',
      ...(an && an.vars[k] ? [`<span class="chip lime" title="${esc(an.vars[k].join(' · '))}">变量 ${esc(an.vars[k][0])}${an.vars[k].length > 1 ? ' +' + (an.vars[k].length - 1) : ''}</span>`] : []),
      props[k] && props[k].type ? `<span class="chip" title="schema 声明的类型">${esc(props[k].type)}${props[k].min !== undefined ? ' ≥ ' + props[k].min : ''}</span>` : ''].join('');
    const missing = [...new Set([...req, ...Object.keys(props)])].filter(k => !(k in j));
    const missRows = missing.map(k => { const pt = (props[k] || {}).type || 'str', t = ['int', 'float'].includes(pt) ? 'number' : pt === 'bool' ? 'boolean' : 'string';
      return `<dt class="miss">${esc(k)} <span style="opacity:.6">${esc(pt)}</span><div class="dtags">${req.has(k) ? '<span class="chip rust">必填 · 缺</span>' : '<span class="chip">schema 里有 · 文件里没有</span>'}</div></dt><dd>${t === 'boolean' ? `<input type="checkbox" ${has(k) && fv[k] ? 'checked' : ''} data-dk="${esc(k)}" data-dty="boolean" data-dp="${esc(p)}" data-dmiss="1">` : `<input class="cell" ${t === 'number' ? 'type="number" step="any"' : ''} style="width:100%" placeholder="${req.has(k) ? '要填' : '可以不填'}" value="${esc(has(k) ? fv[k] : '')}" data-dk="${esc(k)}" data-dty="${t === 'number' ? 'number' : 'string'}" data-dp="${esc(p)}" data-dmiss="1">`}</dd>`; }).join('');
    const clsLine = cls ? `<div class="sub" style="font-size:12px;margin:-4px 0 10px">类 <b class="mono">${esc(cls.name)}</b>${an.inst ? ` · 实例 <span class="mono">${esc(an.inst.id)}</span>` : ''}${cls.parent_class ? ` · 父类 ${esc(cls.parent_class)}` : ''}${missing.filter(k => req.has(k)).length ? ' · <span style="color:var(--fail)">有必填字段没写</span>' : ''}</div>` : '';
    const rows = Object.entries(j).map(([k, v]) => {
      const t = v === null ? 'null' : Array.isArray(v) ? 'json' : typeof v;
      const at = `data-dk="${esc(k)}" data-dty="${t}" data-dp="${esc(p)}"`;
      const d = has(k) ? fv[k] : null;
      const ctl = t === 'boolean' ? `<input type="checkbox" ${(has(k) ? d : v) ? 'checked' : ''} ${at}>`
        : t === 'number' ? `<input class="cell" type="number" step="any" value="${esc(has(k) ? d : v)}" ${at}>`
        : t === 'string' && v.length < 70 && !v.includes('\n') ? `<input class="cell" style="width:100%" value="${esc(has(k) ? d : v)}" ${at}>`
        : t === 'string' ? `<textarea class="cell" style="width:100%;min-height:70px" ${at}>${esc(has(k) ? d : v)}</textarea>`
        : `<textarea class="cell mono" style="width:100%;min-height:${Math.min(220, 40 + JSON.stringify(v).length / 3)}px;font-size:11.5px" ${at.replace(`data-dty="${t}"`, 'data-dty="json"')}>${esc(has(k) ? d : JSON.stringify(v, null, 2))}</textarea>`;
      return `<dt>${esc(k)} <span style="opacity:.6">${t === 'json' || t === 'object' ? (Array.isArray(v) ? 'list' : 'obj') : t}</span><div class="dtags">${tags(k)}</div></dt><dd>${ctl}</dd>`;
    }).join('');
    return head + clsLine + `<dl class="kv">${rows}${missRows}</dl>`;
  }
  function collect(p) {
    const j = {}; let bad = '';
    document.querySelectorAll(`[data-dp="${CSS.escape(p)}"]`).forEach(el => {
      const k = el.dataset.dk, t = el.dataset.dty;
      if (el.dataset.dmiss && (t === 'boolean' ? !el.checked : el.value === '')) return;   // schema 里有、文件里没有、也没填的:不写
      if (t === 'boolean') j[k] = el.checked;
      else if (t === 'number') j[k] = el.value === '' ? null : +el.value;
      else if (t === 'null') j[k] = el.value === '' ? null : el.value;
      else if (t === 'json' || t === 'object') { const v = parse(el.value); if (v === undefined) bad = k; else j[k] = v; }
      else j[k] = el.value;
    });
    return [j, bad];
  }
  const worldFiles = () => D.files.filter(p => p.startsWith('game/') || p.startsWith('registry/') || p.startsWith('rules/'));
  function dataWorldReal() {
    const groups = {};
    for (const p of worldFiles()) { const g = p.split('/').slice(0, 2).join('/'); (groups[g] = groups[g] || []).push(p); }
    const cur = D.sel.world && worldFiles().includes(D.sel.world) ? D.sel.world : null;
    const g0 = cur ? cur.split('/').slice(0, 2).join('/') : D.dg || ['game/locations', 'game/towns', 'game/meta'].find(g => groups[g]) || Object.keys(groups)[0];
    return `<div class="schw scroll"><div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:10px"><span class="tag">文件夹</span>${Object.keys(groups).map(g => `<button class="chip ${g === g0 ? 'solid' : ''}" data-dg="${esc(g)}">${esc(g.replace(/^game\//, ''))} <i style="opacity:.6">${groups[g].length}</i></button>`).join('')}</div>
      <div class="row" style="flex-wrap:wrap;gap:5px;margin-bottom:14px">${(groups[g0] || []).slice(0, 60).map(p => `<button class="chip ${p === cur ? 'lime' : ''}" data-dfile="${esc(p)}">${esc(p.slice(g0.length + 1))}</button>`).join('')}</div>
      <div class="glass deep" style="padding:16px 18px">${fileForm(cur)}</div>${D.msg ? `<div class="sub" style="margin-top:8px;font-size:12px">${esc(D.msg)}</div>` : ''}</div>`;
  }
  const curSoul = () => (S.pick.t === 'soul' && D.souls[S.pick.id] ? S.pick.id : Object.keys(D.souls)[0]);
  function dataSoulReal() {
    const id = curSoul(), s = D.souls[id];
    if (!s) return '<div class="schw"><div class="sub">这个世界没有角色(souls/)</div></div>';
    const mine = D.files.filter(p => p.startsWith(`souls/${s.dir}/`) && /\.(json|md)$/.test(p) && !/short-term-memo|trajectory|run_state/.test(p));
    const cur = D.sel.soul[id] && mine.includes(D.sel.soul[id]) ? D.sel.soul[id] : `souls/${s.dir}/soul.json`;
    return `<div class="schw scroll"><div class="row" style="gap:6px;margin-bottom:10px"><span class="tag">角色</span>${Object.values(D.souls).map(x => `<button class="chip ${x.sid === id ? 'solid' : ''}" data-dsoul="${esc(x.sid)}">${esc(x.name)}</button>`).join('')}</div>
      <div class="dform">${brick('placeimg tall', SOULS[id] && SOULS[id].img, '')}
        <div><div class="row" style="flex-wrap:wrap;gap:5px;margin-bottom:12px">${mine.map(p => `<button class="chip ${p === cur ? 'lime' : ''}" data-dfile="${esc(p)}">${esc(p.slice(`souls/${s.dir}/`.length))}</button>`).join('')}</div>
        <div class="glass deep" style="padding:16px 18px">${fileForm(cur)}</div>${D.msg ? `<div class="sub" style="margin-top:8px;font-size:12px">${esc(D.msg)}</div>` : ''}</div></div></div>`;
  }

  /* ---------- Schema 页:编辑中的世界的开放 schema(类)+ 闭 schema(变量),注册 / 注销写进这个世界 ---------- */
  function schemaLoad() { if (D.schemaFor === D.wid || D.schemaLoading) return; D.schemaLoading = true;
    V3.j(EDIT + '/schema').then(v => { D.schema = v; D.schemaFor = D.wid; }).catch(e => { D.schema = null; D.msg = '读 schema 失败:' + e.message; D.schemaFor = D.wid; })
      .finally(() => { D.schemaLoading = false; if (S.screen === 'duo') renderDuo(); }); }
  function schemaReal(face) {
    if (D.schemaFor !== D.wid) { schemaLoad(); return '<div class="schw"><div class="sub">读 schema……</div></div>'; }
    const sc = D.schema; if (!sc) return `<div class="schw"><div class="sub">${esc(D.msg || '没有 schema')}</div></div>`;
    const soulCls = c => ['soul', 'npc'].includes(c.name) || c.parent_class === 'soul' || c.parent_class === 'npc';
    const cls = sc.classes.filter(c => (face === 'soul' ? soulCls(c) : !soulCls(c)) && ((c.count || 0) > 0 || Object.keys(c.props || {}).length || face === 'soul'));
    const vars = sc.variables.filter(v => (face === 'soul') === String(v.path || '').startsWith('souls/'));
    const firstSoul = Object.values(D.souls)[0];
    const defPath = face === 'soul' ? (firstSoul ? `souls/${firstSoul.dir}/character/stats.json` : 'souls/<id>/character/stats.json') : 'game/meta/vars.json';
    return `<div class="schw scroll"><div class="sub" style="margin-bottom:12px">${face === 'soul' ? '角色的' : '世界的'}开放 schema(类 = 一个文件夹里的一种东西)和闭 schema(变量 = 某个文件里的某个值)。读自编辑中的世界;注册 / 注销写进它的 game/meta。</div>
      <div class="glass deep" style="padding:8px 10px"><div class="tag" style="padding:6px">类 · ${cls.length}</div><table class="t"><tr><th>类</th><th>父类</th><th>文件夹</th><th>实例</th><th>属性</th><th>可变</th></tr>${cls.map(c => `<tr><td class="mono">${esc(c.name)}</td><td class="mono">${esc(c.parent_class || '—')}</td><td class="mono" style="font-size:11px">${esc(c.folder || '(内置)')}</td><td class="mono">${c.count || 0}</td><td>${Object.entries(c.props || {}).map(([k, p]) => `<span class="chip">${esc(k)} ${esc(p.type || '')}</span>`).join(' ') || '—'}</td><td class="mono">${esc((c.mutable || []).join(' · ') || '—')}</td></tr>`).join('')}</table></div>
      <div class="glass deep" style="padding:8px 10px;margin-top:14px"><div class="tag" style="padding:6px">变量 · ${vars.length}</div><table class="t"><tr><th>变量</th><th>类型</th><th>现在的值</th><th>文件 · 位置</th><th></th></tr>${vars.map(v => `<tr><td class="mono">${esc(v.name)}</td><td class="mono">${esc(v.type || '')}${v.readonly ? ' · 只读' : ''}</td><td class="mono">${esc(typeof v.value === 'object' ? JSON.stringify(v.value) : v.value)}</td><td class="mono" style="font-size:11px">${esc(v.path || '')}${v.key ? ' · ' + esc(v.key) : ''}</td><td>${v.readonly ? '' : `<button class="chip" data-vun="${esc(v.name)}">注销</button>`}</td></tr>`).join('')}</table>
        <div class="row" style="padding:10px 6px;flex-wrap:wrap;gap:6px"><input class="cell" id="dvId" placeholder="${face === 'soul' ? '新变量,例 elena.trust' : '新变量,例 fog.level'}" style="max-width:190px"><select class="cell" id="dvType" style="max-width:90px">${['int', 'float', 'str', 'bool'].map(x => `<option>${x}</option>`).join('')}</select>
          <input class="cell" id="dvPath" value="${esc(defPath)}" style="max-width:260px" title="存在哪个文件"><input class="cell" id="dvKey" placeholder="文件里的位置(默认 = 名字最后一段)" style="max-width:220px"><button class="btn p" data-vreg>注册</button></div></div>
      ${D.msg ? `<div class="sub" style="margin-top:8px;font-size:12px">${esc(D.msg)}</div>` : ''}</div>`;
  }
  async function schemaPost(path, body, note) {
    const r = await fetch(V3.url(EDIT + path), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    D.msg = r.ok && d.ok !== false ? note : `${note}失败:${d.error || d.detail || r.status}`;
    D.schemaFor = null; renderDuo();
  }

  /* ---------- 人格控制台:souls/<dir>/persona/{core_traits,values,motivations}.json + character/status.json ----------
     角色 agent 每回合读自己的人格目录;light_chat / placement 也读 core_traits。这里调的就是游玩时用的那几个数。 */
  const PF = { traits: 'persona/core_traits.json', values: 'persona/values.json', motiv: 'persona/motivations.json', status: 'character/status.json' };
  D.persona = {};
  function personaLoad(sid) {
    const s = D.souls[sid]; if (!s || D.persona[sid]) return;
    D.persona[sid] = { loading: true, dirty: new Set() };
    Promise.all(Object.entries(PF).map(([k, f]) => { const p = `souls/${s.dir}/${f}`;
      return (D.files.includes(p) ? getFile(p).then(t => [k, parse(t) || {}]) : Promise.resolve([k, null])); }))
      .then(rows => { const m = D.persona[sid] = { dirty: new Set(), raw: Object.fromEntries(rows) };
        const tr = m.raw.traits || {};
        m.shape = Array.isArray(tr.core_traits) ? 'list' : tr.traits && typeof tr.traits === 'object' ? 'dict' : 'list';
        m.traits = m.shape === 'list' ? (tr.core_traits || []).map(x => ({ trait: x.trait || '', intensity: +x.intensity || 0, description: x.description || '' }))
          : Object.entries(tr.traits).map(([k, v]) => ({ trait: k, intensity: typeof v === 'number' ? v : +(v && v.intensity) || 0, description: (v && v.description) || '' }));
        m.ptype = tr.personality_type || '';
        m.values = ((m.raw.values || {}).values || []).slice();
        m.motiv = ((m.raw.motiv || {}).motivations || []).slice();
        m.status = { ...(m.raw.status || {}) }; m.status.flags = { ...(m.status.flags || {}) };
        renderDuo(); })
      .catch(e => { D.persona[sid] = { err: e.message, dirty: new Set() }; renderDuo(); });
  }
  function personaPage() {
    const sid = curSoul(), s = D.souls[sid];
    if (!s) return '<div class="schw"><div class="sub">这个世界没有角色(souls/)</div></div>';
    const m = D.persona[sid]; if (!m || m.loading) { personaLoad(sid); return '<div class="schw"><div class="sub">读人格文件……</div></div>'; }
    if (m.err) return `<div class="schw"><div class="sub">${esc(m.err)}</div></div>`;
    const rels = Object.entries(relOf(s));
    const trait = (t, i) => `<div class="ptr"><input class="cell" value="${esc(t.trait)}" data-pt="${i}:trait" style="width:120px"><input type="range" min="0" max="100" value="${t.intensity}" data-pt="${i}:intensity"><b class="mono pv">${t.intensity}</b>
      <input class="cell" value="${esc(t.description)}" data-pt="${i}:description" placeholder="这个特质具体是什么样" style="flex:1;min-width:160px"><button class="chip" data-ptdel="${i}" title="删掉这个特质">×</button></div>`;
    const flags = Object.entries(m.status.flags || {});
    return `<div class="schw scroll"><div class="row" style="gap:6px;margin-bottom:12px"><span class="tag">角色</span>${Object.values(D.souls).map(x => `<button class="chip ${x.sid === sid ? 'solid' : ''}" data-dsoul="${esc(x.sid)}">${esc(x.name)}</button>`).join('')}
        <span class="tag" style="margin-left:auto">${m.dirty.size ? '改了 ' + [...m.dirty].map(k => PF[k].split('/').pop()).join(' · ') + ' · 没保存' : '和文件一致'}</span><button class="btn ${m.dirty.size ? 'p' : ''}" data-psave ${m.dirty.size ? '' : 'disabled'}>保存</button></div>
      <div class="dform">${brick('placeimg tall', SOULS[sid] && SOULS[sid].img, '')}
        <div style="display:grid;gap:14px;min-width:0">
          <div class="glass deep" style="padding:14px 16px"><div class="tag">性格 · 一句话</div><textarea class="cell" data-pk="ptype" style="width:100%;min-height:54px;margin-top:6px">${esc(m.ptype)}</textarea>
            <div class="row" style="margin:12px 0 4px"><span class="tag">特质 · 强度 0–100</span><span class="sub" style="margin:0 0 0 auto;font-size:11.5px">${esc(PF.traits)}</span></div>
            <div class="ptraits">${m.traits.map(trait).join('') || '<div class="sub">还没有特质</div>'}</div><button class="btn" data-ptadd style="margin-top:8px">+ 特质</button></div>
          <div class="glass deep" style="padding:14px 16px"><div class="row" style="gap:18px;flex-wrap:wrap;align-items:flex-start">
            <label style="display:grid;gap:6px"><span class="tag">心情 · mood</span><input class="cell" data-pk="mood" value="${esc(m.status.mood || '')}" list="pmoods" style="width:160px"><datalist id="pmoods">${['calm', 'alert', 'happy', 'anxious', 'angry', 'sad', 'tired'].map(x => `<option value="${x}">`).join('')}</datalist></label>
            <label style="display:grid;gap:6px"><span class="tag">记忆 · memory</span><input class="cell" data-pk="memory" value="${esc(m.status.memory || '')}" style="width:160px"></label>
            <div style="display:grid;gap:6px"><span class="tag">状态标记 · flags</span><div class="row" style="flex-wrap:wrap;gap:6px">${flags.map(([k, v]) => `<label class="chip ${v ? 'lime' : ''}" style="cursor:pointer"><input type="checkbox" ${v ? 'checked' : ''} data-pflag="${esc(k)}" style="margin-right:4px">${esc(k)}</label>`).join('') || '<span class="sub">—</span>'}</div></div></div></div>
          <div class="mgrid2"><div class="glass deep" style="padding:14px 16px"><div class="tag">价值观 · 一行一条</div><textarea class="cell" data-pk="values" style="width:100%;min-height:96px;margin-top:6px">${esc(m.values.join('\n'))}</textarea></div>
            <div class="glass deep" style="padding:14px 16px"><div class="tag">动机 · 一行一条</div><textarea class="cell" data-pk="motiv" style="width:100%;min-height:96px;margin-top:6px">${esc(m.motiv.join('\n'))}</textarea></div></div>
          <div class="glass deep" style="padding:14px 16px"><div class="row"><span class="tag">对别人的看法 · ${rels.length}</span><button class="chip" style="margin-left:auto" data-dsoul="${esc(sid)}" data-dgo="rel">在关系图里改 →</button></div>
            ${rels.map(([o, r]) => `<div class="row" style="padding:4px 0;font-size:13px"><span class="dot"></span><b>${esc((D.souls[o] || {}).name || (o === 'player' ? '你' : o))}</b><span class="chip">${esc(r.disposition || '—')}</span>${r.known === false ? '<span class="sub" style="margin:0;font-size:11.5px">还不认识</span>' : ''}</div>`).join('') || '<div class="sub" style="font-size:12.5px">没有记录</div>'}</div>
        </div></div>${D.msg ? `<div class="sub" style="margin-top:8px;font-size:12px">${esc(D.msg)}</div>` : ''}</div>`;
  }
  async function personaSave(sid) {
    const s = D.souls[sid], m = D.persona[sid]; if (!s || !m) return;
    const out = [];
    for (const k of m.dirty) {
      let j;
      if (k === 'traits') { j = { ...(m.raw.traits || {}), sid: (m.raw.traits || {}).sid || sid, personality_type: m.ptype };
        if (m.shape === 'list') j.core_traits = m.traits.filter(t => t.trait.trim()).map(t => ({ trait: t.trait.trim(), intensity: Math.round(t.intensity), description: t.description }));
        else j.traits = Object.fromEntries(m.traits.filter(t => t.trait.trim()).map(t => [t.trait.trim(), Math.round(t.intensity)])); }
      if (k === 'values') j = { ...(m.raw.values || {}), sid, values: m.values.map(x => x.trim()).filter(Boolean) };
      if (k === 'motiv') j = { ...(m.raw.motiv || {}), sid, motivations: m.motiv.map(x => x.trim()).filter(Boolean) };
      if (k === 'status') j = { ...(m.raw.status || {}), ...m.status, sid };
      const p = `souls/${s.dir}/${PF[k]}`;
      try { await putFile(p, JSON.stringify(j, null, 2) + '\n'); m.raw[k] = j; out.push(PF[k].split('/').pop()); if (!D.files.includes(p)) D.files.push(p); }
      catch (e) { D.msg = e.message; renderDuo(); return; }
    }
    m.dirty.clear(); D.msg = `写回 ${out.join(' · ')}(${s.name})`; renderDuo();
  }
  WTABS.soul.splice(1, 0, ['persona', '人格']);
  const _body2 = edBody;
  edBody = function (f, tab) { return f === 'soul' && tab === 'persona' && ready() ? personaPage() : _body2(f, tab); };
  document.addEventListener('input', e => {
    if (!(S.screen === 'duo' && ready() && S.face === 'soul' && S.duoTab.soul === 'persona')) return;
    const m = D.persona[curSoul()]; if (!m || !m.traits) return; const d = e.target.dataset;
    if (d.pt) { const [i, k] = d.pt.split(':'); m.traits[+i][k] = k === 'intensity' ? +e.target.value : e.target.value; m.dirty.add('traits');
      if (k === 'intensity') { const v = e.target.parentElement.querySelector('.pv'); if (v) v.textContent = e.target.value; } }
    else if (d.pk === 'ptype') { m.ptype = e.target.value; m.dirty.add('traits'); }
    else if (d.pk === 'values' || d.pk === 'motiv') { m[d.pk] = e.target.value.split('\n'); m.dirty.add(d.pk); }
    else if (d.pk === 'mood' || d.pk === 'memory') { m.status[d.pk] = e.target.value; m.dirty.add('status'); }
    else return;
    const b = document.querySelector('[data-psave]'); if (b) { b.disabled = false; b.classList.add('p'); }
  });
  document.addEventListener('click', e => {
    if (!(S.screen === 'duo' && ready() && S.face === 'soul' && S.duoTab.soul === 'persona')) return;
    const m = D.persona[curSoul()]; if (!m || !m.traits) return; const q = s => e.target.closest(s); let t;
    if (q('[data-ptadd]')) { m.traits.push({ trait: '新特质', intensity: 50, description: '' }); m.dirty.add('traits'); renderDuo(); return; }
    if ((t = q('[data-ptdel]'))) { m.traits.splice(+t.dataset.ptdel, 1); m.dirty.add('traits'); renderDuo(); return; }
    if ((t = q('[data-pflag]'))) { m.status.flags[t.dataset.pflag] = t.checked; m.dirty.add('status'); renderDuo(); return; }
    if (q('[data-psave]')) { personaSave(curSoul()); return; }
  });

  /* ---------- 接到 app.js 的画法上 ---------- */
  const _dw = dataWorld, _ds = dataSoul, _act = edActions, _insp = inspector2;
  const _sw = schemaWorld, _ss = schemaSoul;
  schemaWorld = function () { return ready() ? schemaReal('world') : _sw(); };
  schemaSoul = function () { return ready() ? schemaReal('soul') : _ss(); };
  dataWorld = function () { return ready() ? dataWorldReal() : _dw(); };
  dataSoul = function () { return ready() ? dataSoulReal() : _ds(); };
  edActions = function (f, tab) {
    if (!ready()) return _act(f, tab);
    if (f === 'soul' && tab === 'rel') return `<span class="tag">${esc(D.msg || '连线 = 一条关系 · 从角色拖到别人 = 新关系 · 写进 persona/relationships.json')}</span>`;
    if (f === 'soul' && tab === 'persona') return '<span class="tag">角色 agent 每回合读这些 · 改完保存就是下一回合的她</span>';
    if (f === 'soul' && tab === 'cards') return `<span class="tag">souls/ · ${Object.keys(D.souls).length} 个角色</span>`;
    if (tab === 'data') return '<span class="tag">表单按文件里的字段生成 · 保存 = 写回这个文件</span>';
    return _act(f, tab);
  };
  inspector2 = function () {
    if (!(ready() && S.face === 'soul' && S.duoTab.soul === 'rel')) return _insp();
    const sel = S.gsel;
    if (sel && sel.t === 'edge') { const e = REL.edges.find(x => x.id === sel.id); if (e && e.real) { const r = relOf(D.souls[e.from])[e.to] || {};
      return `<div class="tag">关系 · ${esc(D.souls[e.from].relPath)}</div><h3>${esc(REL.nodes[e.from].title)} → ${esc((REL.nodes[e.to] || {}).title || e.to)}</h3>
        <label class="tag" style="display:block;margin-top:14px">disposition(她怎么看对方)</label><input class="cell" style="width:100%;margin:6px 0 10px" value="${esc(r.disposition || '')}" data-rk="disposition" data-re="${esc(e.id)}">
        <label class="row" style="gap:8px;font-size:13px"><input type="checkbox" ${r.known === false ? '' : 'checked'} data-rk="known" data-re="${esc(e.id)}">已经认识</label>
        <label class="tag" style="display:block;margin-top:12px">truth(只有主持知道的真相)</label><textarea class="cell" style="width:100%;min-height:80px;margin-top:6px" data-rk="truth" data-re="${esc(e.id)}">${esc(r.truth || '')}</textarea>
        <div class="row" style="margin-top:14px"><button class="btn" data-rdel="${esc(e.id)}">删掉这条关系</button></div>`; } }
    if (sel && sel.t === 'node' && REL.nodes[sel.id]) { const n = REL.nodes[sel.id], s = D.souls[sel.id];
      return `<div class="tag">${s ? '角色 · souls/' + esc(s.dir) : sel.id === 'player' ? '玩家' : '不是角色(只出现在别人的关系里)'}</div><h3>${esc(n.title)}</h3>
        ${s ? `<p class="sub">${esc(s.intro)}</p><div class="row"><button class="btn" data-dsoul="${esc(s.sid)}" data-dgo="data">打开角色文件 →</button></div>` : '<p class="sub">只有角色(souls/)才有自己的关系文件;从角色拖一条线到这里就是新关系。</p>'}`; }
    return `<div class="tag">检查器 · 关系</div><h3>点人或连线</h3><p class="sub">每个角色自己记着对别人的看法(persona/relationships.json)。连线从「谁的看法」指向「看谁」。</p>`;
  };
  const _duo = renderDuo;
  renderDuo = function () {
    const h = window.MAPHOOK;
    if (S.screen === 'duo' && h && h.edit && D.wid !== h.edit.world_id && !D.loading) load();
    // 关系图上拖出来的新线:从角色出发才有文件可写
    if (ready() && REL.edges.some(e => !e.real)) {
      const fresh = REL.edges.filter(e => !e.real);
      for (const e of fresh) REL.edges.splice(REL.edges.indexOf(e), 1);
      const e = fresh[0], s = D.souls[e.from];
      if (!s) { D.msg = '关系要从一个角色拖出去(只有角色有自己的关系文件)'; }
      else { const rs = relOf(s); if (!s.rel.relationships || Array.isArray(s.rel.relationships)) s.rel.relationships = rs; rs[e.to] = rs[e.to] || { disposition: '认识', known: true }; S.gsel = { t: 'edge', id: `${s.sid}>${e.to}` }; S.rtab = 'insp'; writeRel(s.sid, `+ ${e.to}`); }
    }
    _duo();
    if (ready()) { const t = document.querySelector('#s-duo .tree'); if (t) t.innerHTML = tree(); }
  };
  if (window.LIVE_buildMap) { const _bm = window.LIVE_buildMap; window.LIVE_buildMap = function () { D.wid = null; return _bm.apply(this, arguments); }; }   // 创作 agent 改完文件 → 重读

  document.addEventListener('click', e => {
    if (S.screen !== 'duo' || !ready()) return;
    const q = s => e.target.closest(s); let t;
    if ((t = q('[data-tdir]'))) { const k = t.dataset.tdir; D.open.has(k) ? D.open.delete(k) : D.open.add(k); renderDuo(); return; }
    if ((t = q('[data-tfile]'))) { openFile(t.dataset.tfile); S.gsel = null; renderDuo(); return; }
    if ((t = q('[data-dg]'))) { D.dg = t.dataset.dg; D.sel.world = null; renderDuo(); return; }
    if ((t = q('[data-dfile]'))) { const p = t.dataset.dfile; if (S.face === 'soul') D.sel.soul[curSoul()] = p; else D.sel.world = p; renderDuo(); return; }
    if ((t = q('[data-dsoul]'))) { S.pick = { t: 'soul', id: t.dataset.dsoul }; if (t.dataset.dgo) { S.face = 'soul'; S.duoTab.soul = t.dataset.dgo; } renderDuo(); return; }
    if ((t = q('[data-draw]'))) { const p = t.dataset.draw; if (D.raw === p) { const r = (D.fv[p] || {}).__raw; if (r !== undefined && parse(r) !== undefined) { D.cache[p] = r; D.fv[p] = {}; } D.raw = null; } else { if (D.dirty[p]) { const [j] = collect(p); D.cache[p] = JSON.stringify(j, null, 2) + '\n'; D.fv[p] = {}; } D.raw = p; } renderDuo(); return; }
    if ((t = q('[data-dsave]'))) { const p = t.dataset.dsave; let text;
      const ta = document.querySelector(`[data-draw-text="${CSS.escape(p)}"]`);
      if (ta) { text = ta.value; if (/\.json$/.test(p) && parse(text) === undefined) { D.msg = '不是合法的 JSON,没保存'; renderDuo(); return; } }
      else { const [j, bad] = collect(p); if (bad) { D.msg = `「${bad}」不是合法的 JSON,没保存`; renderDuo(); return; } text = JSON.stringify(j, null, 2) + '\n'; }
      putFile(p, text).then(() => { D.msg = `写回 ${p}`; const s = Object.values(D.souls).find(x => p.startsWith(`souls/${x.dir}/`)); if (s && /soul\.json|relationships\.json/.test(p)) D.wid = null; renderDuo(); }).catch(err => { D.msg = err.message; renderDuo(); });
      return; }
    if (q('[data-vreg]')) { const v = id => ((document.getElementById(id) || {}).value || '').trim(); const id = v('dvId'); if (!id || !v('dvPath')) { D.msg = '变量名和文件都要填'; renderDuo(); return; }
      schemaPost('/schema/register', { table: 'variables', id, spec: { type: v('dvType'), path: v('dvPath'), key: v('dvKey') || id.split('.').pop() } }, `注册 ${id}`); return; }
    if ((t = q('[data-vun]'))) { schemaPost('/schema/unregister', { table: 'variables', id: t.dataset.vun }, `注销 ${t.dataset.vun}`); return; }
    if ((t = q('[data-rdel]'))) { const [from, to] = t.dataset.rdel.split('>'); delete relOf(D.souls[from])[to]; S.gsel = null; writeRel(from, `删 ${to}`); return; }
  });
  // 关系图:拦掉演示的删节点 / 加人 / 删边(删边用检查器里的按钮,写文件)
  document.addEventListener('click', e => {
    if (!(S.screen === 'duo' && ready() && S.face === 'soul' && S.duoTab.soul === 'rel')) return;
    const t = e.target.closest('[data-ndel],[data-edel],[data-addn="npc"]'); if (!t) return;
    e.stopImmediatePropagation();
    if (t.dataset.edel) { const [from, to] = t.dataset.edel.split('>'); if (D.souls[from]) { delete relOf(D.souls[from])[to]; S.gsel = null; writeRel(from, `删 ${to}`); } return; }
    D.msg = '新角色让创作 agent 捏(会建 souls/<id>/ 一整套文件)'; S.rtab = 'agent'; renderDuo(); const i = document.getElementById('ain'); if (i) { i.value = '捏一个新角色:'; i.focus(); }
  }, true);
  document.addEventListener('input', e => {
    if (S.screen !== 'duo' || !ready()) return;
    const d = e.target.dataset;
    if (d.dp || d.drawText) { const p = d.dp || d.drawText; const f = D.fv[p] = D.fv[p] || {};
      if (d.drawText) f.__raw = e.target.value; else f[d.dk] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
      if (!D.dirty[p]) { D.dirty[p] = true; const b = document.querySelector(`[data-dsave="${CSS.escape(p)}"]`); if (b) { b.disabled = false; b.classList.add('p'); } } }
  });
  document.addEventListener('change', e => {
    if (S.screen !== 'duo' || !ready()) return;
    const d = e.target.dataset;
    if (d.dty === 'boolean') { const p = d.dp; D.dirty[p] = true; (D.fv[p] = D.fv[p] || {})[d.dk] = e.target.checked; const b = document.querySelector(`[data-dsave="${CSS.escape(p)}"]`); if (b) { b.disabled = false; b.classList.add('p'); } }
    if (d.re) { const [from, to] = d.re.split('>'), r = relOf(D.souls[from])[to]; if (!r) return;
      r[d.rk] = d.rk === 'known' ? e.target.checked : e.target.value; writeRel(from, `${to}.${d.rk}`); }
    if (d.elabel && S.face === 'soul') { const [from, to] = d.elabel.split('>'), r = D.souls[from] && relOf(D.souls[from])[to]; if (r) { r.disposition = e.target.value.replace(/ · 未相识$/, ''); writeRel(from, `${to}.disposition`); } }
  });
  document.addEventListener('pointerup', () => { if (S.screen === 'duo' && ready() && S.face === 'soul' && S.duoTab.soul === 'rel') setTimeout(saveLayout, 0); });
})();
