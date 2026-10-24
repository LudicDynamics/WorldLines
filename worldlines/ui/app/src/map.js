/* 多层地图编辑器(世界面 · 地图)
   数据 = 文件夹树:每个地点一个 location.json;它所在的文件夹 = 它属于哪一层。
   每一层 = 一张连通图:节点 = 这一层的子文件夹,边 = 同层 connections(+ 路程)。连通图没有坐标。
   跨层 = 端口:上一层的一条边(路)走进这一层时,落在哪个节点(via);往下走 = 进入节点自己的子层。
   出图 = 拿连通图排版 → 出指引图 → 模型出图 → 冻结换算(assets/maps/<层>.json),这时每个节点才有 x / y。
   这里的两份是原型数据(石津镇照 stoneford-elena 的文件与换算;暮色群岛演示「先连通图、后生成地图」),只在 ?demo=1 时出现:
   默认由 live.js 清掉,改读引擎 /api/v1/play/map 的那一个世界。 */
(function () {
  const fitPct = (f, size, x, y) => [(f.px + (x - f.x0) * f.sx) / size[0] * 100, (f.py + (y - f.y0) * f.sy) / size[1] * 100];
  const FW = { px: 170, py: 150, x0: 5, y0: 3, sx: 70.3529, sy: 60.3333 }, FT = { px: 260, py: 190, x0: 236, y0: 153, sx: 1.8955, sy: 2.3333 }, SZ = [1536, 1024];
  const P = (f, x, y) => { const [a, b] = fitPct(f, SZ, x, y); return { x: +a.toFixed(1), y: +b.toFixed(1) }; };
  const SCALE = [T('世界'), T('镇 / 城'), T('地点'), T('室内')];

  const WORLDS = {
    stoneford: {
      title: '石津镇 · 灰雾北境', root: 'world',
      levels: {
        world: { title: '灰雾北境', scale: '世界', file: 'game/world/world_map.json', image: 'map-world.jpg', aspect: 1.5, frozen: true, fitNote: 'assets/maps/world.json · fit px170 py150 sx70.35 sy60.33',
          nodes: {
            T001: { name: '石津镇', type: 'town', pos: P(FW, 12, 7), raw: [12, 7], child: 'T001' }, T002: { name: '风栈堡', type: 'town', pos: P(FW, 5, 10), raw: [5, 10] },
            T003: { name: '狼牙关', type: 'town', pos: P(FW, 10, 3), raw: [10, 3] }, T004: { name: '碧石镇', type: 'town', pos: P(FW, 18, 4), raw: [18, 4] },
            T005: { name: '雾湖城', type: 'city', pos: P(FW, 8, 15), raw: [8, 15] }, D001: { name: '苔墓地穴', type: 'dungeon', pos: P(FW, 14, 8), raw: [14, 8], child: 'D001' },
            R003: { name: '东境', type: 'region', pos: P(FW, 22, 8), raw: [22, 8] },
          },
          edges: [{ id: 'R001', a: 'T001', b: 'T002', d: '18 · 官道' }, { id: 'R002', a: 'T001', b: 'D001', d: '6 · 雾林小径' }, { id: 'R004', a: 'T001', b: 'T004', d: '45 · 有山贼' }] },
        T001: { title: '石津镇', scale: '镇', parent: 'world', file: 'game/locations/T001/', image: 'map-t001.jpg', aspect: 1.5, frozen: true, fitNote: 'assets/maps/T001.json · fit px260 py190 sx1.90 sy2.33',
          nodes: {
            gate_north: { name: '北门', type: 'gate', pos: P(FT, 236, 153), raw: [236, 153], dangling: ['old-road'] }, 'market-square': { name: '集市广场', type: 'square', pos: P(FT, 154, 116), raw: [154, 116], dangling: ['guildhall'] },
            main_street: { name: '主街', type: 'street', pos: P(FT, 504, 316), raw: [504, 316] }, guild: { name: '冒险者公会', type: 'facility', pos: P(FT, 416, 191), raw: [416, 191], child: 'T001/guild' },
            shop_general: { name: '杂货铺', type: 'facility', pos: P(FT, 512, 232), raw: [512, 232] }, inn: { name: '河灯旅店', type: 'facility', pos: P(FT, 621, 268), raw: [621, 268] },
            townhall: { name: '镇署', type: 'facility', pos: P(FT, 772, 315), raw: [772, 315] }, dock: { name: '码头', type: 'dock', pos: P(FT, 411, 429), raw: [411, 429] },
          },
          edges: [['gate_north', 'main_street', '8 分'], ['gate_north', 'market-square', '4 分'], ['main_street', 'guild', '6 分'], ['main_street', 'shop_general', '10 分'], ['main_street', 'inn', '6 分'], ['main_street', 'dock', '15 分'], ['main_street', 'townhall', '7 分'], ['inn', 'market-square', '9 分']].map(([a, b, d], i) => ({ id: 'c' + i, a, b, d })),
          ports: [{ up: 'R002', via: 'gate_north' }, { up: 'R001', via: null }, { up: 'R004', via: null }], entry: 'gate_north' },
        D001: { title: '苔墓地穴', scale: '地穴', parent: 'world', file: 'game/dungeons/D001/layout.json', image: 'map-d001.jpg', aspect: 1.5, frozen: false, oldForm: true,
          nodes: { D001_R001: { name: '潮门前室', type: 'entry', pos: null }, D001_R002: { name: '苔廊', type: 'hall', pos: null }, D001_R003: { name: '供台室', type: 'chamber', pos: null }, D001_R004: { name: '棺语内殿', type: 'boss', pos: null } },
          edges: [{ id: 'd1', a: 'D001_R001', b: 'D001_R002', d: '' }, { id: 'd2', a: 'D001_R002', b: 'D001_R003', d: '' }, { id: 'd3', a: 'D001_R002', b: 'D001_R004', d: '' }],
          ports: [{ up: 'R002', via: 'D001_R001' }], entry: 'D001_R001', genPos: { D001_R001: { x: 22, y: 60 }, D001_R002: { x: 46, y: 46 }, D001_R003: { x: 70, y: 26 }, D001_R004: { x: 74, y: 70 } } },
        'T001/guild': { title: '冒险者公会', scale: '室内', parent: 'T001', file: 'game/locations/T001/guild/', image: null, aspect: 1.5, frozen: false, nodes: {}, edges: [], ports: [{ up: 'c2', via: null }] },
      },
    },
    isles: {
      title: '暮色群岛', root: 'world',
      levels: {
        world: { title: '暮色群岛', scale: '群岛', file: 'game/world/world_map.json', image: 'isle-map.jpg', aspect: 844 / 1500, frozen: false,
          nodes: {
            compass: { name: '罗盘广场', type: 'square', pos: null, img: 'isle-plaza.jpg' }, studio: { name: '暖光画室', type: 'island', pos: null, img: 'isle-studio.jpg' },
            gatepath: { name: '城门秘径', type: 'gate', pos: null, img: 'isle-gate.jpg' }, theater: { name: '花园剧场', type: 'island', pos: null, img: 'isle-theater.jpg' },
            observatory: { name: '观象馆', type: 'island', pos: null, img: 'isle-observatory.jpg', child: 'observatory' }, harbor: { name: '布告码头', type: 'dock', pos: null, img: 'isle-plaza.jpg' },
          },
          edges: [['compass', 'studio', '拱桥'], ['compass', 'gatepath', '长阶'], ['compass', 'theater', '拱桥'], ['compass', 'observatory', '拱桥'], ['theater', 'harbor', '石阶'], ['observatory', 'harbor', '栈桥'], ['studio', 'gatepath', '海上栈道']].map(([a, b, d], i) => ({ id: 'b' + i, a, b, d })),
          genPos: { studio: { x: 22, y: 22 }, gatepath: { x: 70, y: 21 }, compass: { x: 50, y: 39 }, theater: { x: 18, y: 51 }, observatory: { x: 82, y: 50 }, harbor: { x: 56, y: 76 } } },
        observatory: { title: '观象馆', scale: '岛', parent: 'world', file: 'game/locations/observatory/', image: 'isle-observatory.jpg', aspect: 1672 / 941, frozen: false,
          nodes: { terrace: { name: '星盘露台', type: 'terrace', pos: null }, dome: { name: '望远镜穹顶', type: 'room', pos: null }, study: { name: '静谧书房', type: 'room', pos: null, img: 'isle-study.jpg' }, pier: { name: '馆前栈桥', type: 'dock', pos: null } },
          edges: [{ id: 'o1', a: 'pier', b: 'terrace', d: '石阶' }, { id: 'o2', a: 'terrace', b: 'dome', d: '' }, { id: 'o3', a: 'terrace', b: 'study', d: '' }],
          ports: [{ up: 'b3', via: 'terrace' }, { up: 'b5', via: 'pier' }], entry: 'pier',
          genPos: { terrace: { x: 56, y: 72 }, dome: { x: 68, y: 26 }, study: { x: 84, y: 52 }, pier: { x: 30, y: 84 } } },
      },
    },
  };
  const M = { world: 'stoneford', level: 'T001', view: 'graph', sel: null, gen: null, stale: {}, log: [] };
  window.MAPW = WORLDS; window.MAPM = M;  // 真引擎层(live.js)往这里加一个从 /api/v1/play/map 读出来的世界
  const W = () => WORLDS[M.world], L = () => W().levels[M.level];
  const depth = addr => { let d = 0, l = W().levels[addr]; while (l && l.parent) { d++; l = W().levels[l.parent]; } return d; };
  const chain = addr => { const out = []; let a = addr; while (a) { out.unshift(a); a = W().levels[a].parent; } return out; };
  const parentEdge = (lv, id) => { const p = W().levels[lv.parent]; return p && p.edges.find(e => e.id === id); };
  const upTarget = (lv, port) => { const e = parentEdge(lv, port.up); if (!e) return null; const pl = W().levels[lv.parent]; const self = Object.keys(pl.nodes).find(k => pl.nodes[k].child === M.level); const other = e.a === self ? e.b : e.a; return { e, name: (pl.nodes[other] || { name: other }).name }; };

  // 连通图的自动排版:无坐标,按图距离分环(入口 / 中心在里)。只是看图用,不写回文件。
  function topo(lv) {
    const ids = Object.keys(lv.nodes); if (!ids.length) return {};
    const deg = id => lv.edges.filter(e => e.a === id || e.b === id).length;
    const hub = lv.entry && lv.nodes[lv.entry] ? lv.entry : ids.slice().sort((a, b) => deg(b) - deg(a))[0];
    const dist = { [hub]: 0 }, q = [hub];
    while (q.length) { const c = q.shift(); lv.edges.forEach(e => { const o = e.a === c ? e.b : e.b === c ? e.a : null; if (o && dist[o] === undefined) { dist[o] = dist[c] + 1; q.push(o); } }); }
    const rings = {}; ids.forEach(id => { const d = dist[id] === undefined ? 9 : dist[id]; (rings[d] = rings[d] || []).push(id); });
    const out = {}; Object.entries(rings).forEach(([d, list]) => { d = +d; list.forEach((id, i) => {
      if (d === 0) { out[id] = { x: 50, y: 50 }; return; }
      const r = d === 9 ? 44 : Math.min(40, 16 + d * 14), a = (i / list.length) * Math.PI * 2 - Math.PI / 2 + d * .4;
      out[id] = { x: 50 + Math.cos(a) * r * 1.15, y: 50 + Math.sin(a) * r }; }); });
    return out;
  }

  function lint() {
    const out = [], lv = L();
    Object.entries(lv.nodes).forEach(([id, n]) => (n.dangling || []).forEach(t => out.push({ lv: 'block', msg: T('{name}.connections 里的 {t} 不是这一层的地点', { name: n.name, t }), hint: t === 'old-road' ? T('它其实是出镇的路:接成端口') : T('删掉或补这个地点'), fix: t === 'old-road' ? `bind:${id}:${t}` : `drop:${id}:${t}` })));
    (lv.ports || []).filter(p => !p.via).forEach(p => { const t = upTarget(lv, p); out.push({ lv: 'block', msg: T('上一层的路 {up} 进来后落在哪个点没写', { up: p.up + (t ? '(→ ' + t.name + ')' : '') }), hint: T('选一个节点,点端口上的「接到选中节点」') }); });
    if (lv.parent === undefined) Object.entries(lv.nodes).forEach(([id, n]) => { if (!lv.edges.some(e => e.a === id || e.b === id)) out.push({ lv: 'warn', msg: T('{name} 没有任何路连着', { name: n.name }), hint: T('孤点:玩家走不到') }); });
    if (lv.oldForm) out.push({ lv: 'warn', msg: T('还是旧格式(layout.json rooms)'), hint: T('迁移成文件夹:每个房间一个 location.json') });
    if (!lv.frozen) out.push({ lv: 'info', msg: T('这一层还没有地图:节点只有连通关系,没有坐标'), hint: T('「生成这一层的地图」后坐标才定下来') });
    if (M.stale[M.level]) out.push({ lv: 'warn', msg: T('冻结之后挪过节点:图和坐标对不上了'), hint: T('重新生成,或撤回挪动') });
    return out;
  }

  window.mapEditor = function (host) {
    if (!W()) { const k = Object.keys(WORLDS)[0]; const fail = (window.MAPHOOK || {}).openFail; if (!k) { host.innerHTML = fail
      ? `<div class="mpempty"><div class="mpe"><b>${T('这个世界打不开')}</b><span>${esc(fail.msg)}</span>${window.LIVE ? `<select class="btn" id="mwSel" style="text-transform:none;letter-spacing:0">${window.LIVE.templates.map(t => `<option value="${t.id}" ${t.id === fail.tid ? 'selected' : ''}>${esc((t.card && t.card.title) || t.id)}</option>`).join('')}</select>` : ''}<button class="btn" data-mretry>${T('再试一次')}</button></div></div>`
      : '<div class="mpempty"><div class="mpe"><b>' + T('正在打开这个世界……') + '</b><span>' + T('第一次编辑一个世界要复制它的文件,十几秒') + '</span></div></div>'; return; } M.world = k; M.level = WORLDS[k].root; }
    if (!L()) M.level = W().root;
    const lv = L(), d = depth(M.level), issues = lint();
    host.innerHTML = `<div class="mp">
      <div class="mphd">
        ${WORLDS.edit && window.LIVE ? `<select class="btn" id="mwSel" style="text-transform:none;letter-spacing:0" aria-label="${T('编辑哪个世界')}">${window.LIVE.templates.map(t => `<option value="${t.id}" ${t.id === (window.MAPHOOK || {}).wtpl ? 'selected' : ''}>${esc((t.card && t.card.title) || t.id)}</option>`).join('')}</select>` : `<div class="seg">${Object.entries(WORLDS).map(([k, w]) => `<button class="${M.world === k ? 'on' : ''}" data-mw="${k}">${w.title}</button>`).join('')}</div>`}
        <div class="crumbs">${chain(M.level).map((a, i) => `${i ? '<span class="sep">›</span>' : ''}<button class="${a === M.level ? 'on' : ''}" data-ml="${a}"><span class="lvl">${W().levels[a].scale || SCALE[i]}</span>${W().levels[a].title}</button>`).join('')}</div>
        <div class="seg r">${[['graph', T('连通图')], ['map', T('地图')], ['tree', T('树')], ['json', 'JSON']].map(([k, l]) => `<button class="${M.view === k ? 'on' : ''}" data-mv="${k}">${l}</button>`).join('')}</div></div>
      ${banner()}
      <div class="mpbody"><div class="mpmain" id="mpmain"></div>
        <div class="mpside glass deep">${side(lv, issues)}</div></div></div>`;
    const main = $('#mpmain', host);
    if (M.view === 'tree') return drawTree(main);
    if (M.view === 'json') return drawJson(main);
    drawLevel(main, lv);
  };

  function side(lv, issues) {
    if (M.selEdge && lv.nodes[M.selEdge.a] && lv.nodes[M.selEdge.b]) {   // 选中一条路
      const { a, b } = M.selEdge, e = lv.edges.find(x => (x.a === a && x.b === b) || (x.a === b && x.b === a)) || {};
      return `<div class="tag">${T('路')}</div><h3 class="human" style="font-size:22px;margin:4px 0 6px">${esc(lv.nodes[a].name)} ↔ ${esc(lv.nodes[b].name)}</h3>
        ${M.level === 'world' && lv.editable ? `<label class="tag" style="display:block;margin-top:10px">${T('路程(天)')}</label><div class="row" style="gap:6px;margin-top:6px"><input class="cell mono" id="mroadD" value="${esc(e.d || '')}" style="width:90px"><button class="btn" data-mroadd>${T('改')}</button></div>` : e.d ? `<p class="sub">${T('路程')} ${esc(e.d)}</p>` : ''}
        ${lv.editable ? `<button class="btn" data-mroaddel style="width:100%;margin-top:14px">${T('删掉这条路')}</button>` : ''}<button class="btn" data-mroadx style="width:100%;margin-top:6px">${T('取消选中')}</button>`;
    }
    const n = M.sel && lv.nodes[M.sel];
    const portList = (lv.ports || []).map((p, i) => { const t = upTarget(lv, p); return `<div class="port ${p.via ? '' : 'open'}"><img src="img/icon-gate.png" alt=""><div><b>↑ ${p.up}${t ? ' · ' + esc(t.name) : ''}</b><small>${t ? esc(t.e.d) : ''} · ${p.via ? T('落在 {name}', { name: esc(lv.nodes[p.via].name) }) : '<span style="color:var(--fail)">' + T('还没接') + '</span>'}</small></div>${!p.via && M.sel ? `<button class="chip lime" data-mport="${i}">${T('接到「{name}」', { name: esc(lv.nodes[M.sel].name) })}</button>` : ''}</div>`; }).join('');
    const nodeBox = n ? `<div class="tag">${T('节点')} · ${esc(n.type || '')}${n.child ? ' · ' + T('有子层({scale})', { scale: esc(W().levels[n.child].scale || '') }) : ''}</div><h3 class="human" style="font-size:22px;margin:4px 0 2px">${esc(n.name)}</h3>
      <div class="mono" style="font-size:11.5px;color:var(--muted)">${lv.file}${lv.file.endsWith('/') ? M.sel + '/location.json' : ''}</div>
      ${n.img ? brick('mpimg', n.img, '') : ''}
      <dl class="kv"><dt>${T('地址')}</dt><dd class="mono">${M.level === 'world' ? M.sel : M.level + '/' + M.sel}</dd><dt>${T('父')}</dt><dd>${esc(lv.title)}(${lv.scale || SCALE[depth(M.level)]})</dd>
        <dt>${T('子层')}</dt><dd>${n.child ? `<button class="chip" data-ml="${n.child}">▾ ${T('进入 {title} · {n} 个', { title: esc(W().levels[n.child].title), n: Object.keys(W().levels[n.child].nodes).length })}</button>` : `<button class="chip" data-mkchild="${M.sel}">+ ${T('建子层(文件夹)')}</button>`}</dd>
        <dt>${T('同层连接')}</dt><dd>${lv.edges.filter(e => e.a === M.sel || e.b === M.sel).map(e => `<span class="chip">${esc(lv.nodes[e.a === M.sel ? e.b : e.a].name)}${e.d ? ' · ' + esc(e.d) : ''}</span>`).join(' ') || '—'}</dd>
        <dt>${T('跨层端口')}</dt><dd>${(lv.ports || []).filter(p => p.via === M.sel).map(p => `<span class="chip lime">↑ ${p.up}</span>`).join(' ') || '—'}${lv.entry === M.sel ? ' <span class="chip">' + T('默认入口') + '</span>' : ''}</dd>
        <dt>pos</dt><dd class="mono">${n.pos ? (n.raw ? `[${n.raw.join(', ')}] → ${T('图上')} ${n.pos.x}%, ${n.pos.y}%` : `${n.pos.x}%, ${n.pos.y}%`) : '<span style="color:var(--muted)">' + T('null(连通图没有坐标)') + '</span>'}</dd></dl>` : `<div class="tag">${T('这一层')}</div><h3 class="human" style="font-size:22px;margin:4px 0 6px">${esc(lv.title)}</h3><p class="sub" style="font-size:12.5px">${T('点节点看它的父、子、同层连接和跨层端口。双击有子层的节点往下走。')}</p>`;
    return `${nodeBox}
      ${lv.parent ? `<div class="tag" style="margin-top:14px">${T('跨层端口 · 上一层的路从哪进来')}</div>${portList || `<span style="color:var(--muted);font-size:12.5px">${lv.live ? T('这一层还没有跨层端口数据') : T('没有')}</span>`}` : ''}
      <div class="tag" style="margin-top:14px">${T('这一层的图')} · ${lv.frozen ? T('已冻结') : T('未生成')}</div>
      ${lv.frozen ? `<div class="mono" style="font-size:11.5px;color:var(--muted);margin:4px 0 8px">${esc(lv.fitNote || 'assets/maps/' + M.level.replace('/', '_') + '.json')}</div>` : ''}
      ${genBox(lv)}
      <div class="tag" style="margin-top:14px">${T('检查')}</div>
      ${issues.length ? '' : '<div class="iss"><span class="dot ok"></span><div><b>' + T('这一层没有问题') + '</b><small>' + T('端口都接上了 · 没有悬空的连接') + '</small></div></div>'}${issues.map(x => `<div class="iss ${x.lv}"><span class="dot ${x.lv === 'block' ? 'bad' : x.lv === 'warn' ? 'warn' : 'blue'}"></span><div><b>${esc(x.msg)}</b><small>${esc(x.hint)}</small></div>${x.fix ? `<button class="chip" data-mfix="${x.fix}">${T('修')}</button>` : ''}</div>`).join('')}`;
  }
  function banner() { return ''; }  // 世界 · 角色就是编辑界面:不再有「只读 / 另存」
  function saveBtn() {
    const h = window.MAPHOOK; if (!h) return '';
    if (h.saving) return `<button class="btn" disabled style="width:100%;margin-top:8px">${T('另存中……')}</button>`;
    if (h.edit && WORLDS.edit) return `<button class="btn" data-mw="edit" style="width:100%;margin-top:8px">${T('打开「我的世界 · {name}」', { name: esc(h.edit.name) })}</button><button class="btn" data-msave style="width:100%;margin-top:6px">${T('再另存一份新的')}</button>`;
    return `<button class="btn p" data-msave style="width:100%;margin-top:8px">${T('另存成我的世界并编辑')}</button>`;
  }
  function genBox(lv) {
    if (lv.live) { const j = lv.job || {};
      if (j.state === 'running') return `<div class="gen"><div class="gs now"><span>…</span>${T('引擎在生成这一层的地图(连通图排版 → 指引图 → 出图 → 冻结坐标)')}</div></div>`;
      return `${j.state === 'error' ? `<div class="iss block"><span class="dot bad"></span><div><b>${T('上次生成失败')}</b><small>${esc(j.error || '')}</small></div></div>` : ''}<button class="btn ${lv.frozen && !lv.stale ? '' : 'p'}" data-mgen style="width:100%;margin-top:4px">${!lv.frozen ? T('生成这一层的地图') : lv.stale ? T('重新生成(钉子挪过了)') : T('重新生成这一层的地图')}</button>`; }
    const steps = [T('用连通图排版 → 指引图(guide.png)'), T('模型照指引出图'), T('冻结换算:每个节点写入 pos')];
    if (M.gen === M.level) return `<div class="gen">${steps.map((s, i) => `<div class="gs ${i < M.genStep ? 'done' : i === M.genStep ? 'now' : ''}"><span>${i < M.genStep ? '✓' : i + 1}</span>${s}</div>`).join('')}</div>`;
    if (!Object.keys(lv.nodes).length) return `<div class="sub" style="font-size:12.5px">${T('先加节点,再生成')}</div>`;
    return `<button class="btn ${lv.frozen ? '' : 'p'}" data-mgen style="width:100%;margin-top:4px">${lv.frozen ? (M.stale[M.level] ? T('重新生成(坐标已改)') : T('重新生成这一层的地图')) : T('生成这一层的地图')}</button>`;
  }

  function drawLevel(main, lv) {
    const isMap = M.view === 'map';
    if (isMap && !lv.frozen) { main.innerHTML = lv.live ? `<div class="mpempty"><div class="mpe"><img src="img/icon-frames.png" alt=""><b>${T('这一层还没有地图')}</b><span>${lv.editable ? T('只有连通图:生成之后坐标才定下来') : T('只有连通图。另存成我的世界之后可以生成')}</span>${lv.editable ? (lv.job && lv.job.state === 'running' ? '<span>' + T('生成中……') + '</span>' : '<button class="btn p" data-mgen>' + T('生成这一层的地图') + '</button>') : ''}</div></div>` : `<div class="mpempty">${lv.image ? brick('ghostmap', lv.image, '') : ''}<div class="mpe"><img src="img/icon-frames.png" alt=""><b>${T('这一层还没有地图')}</b><span>${T('现在只有连通图:节点和路,没有坐标。生成之后,坐标才定下来。')}</span><button class="btn p" data-mgen>${T('生成这一层的地图')}</button></div></div>`; return; }
    const lkey = M.world + ':' + M.level; M.layout = M.layout || {};
    const pos = isMap ? Object.fromEntries(Object.entries(lv.nodes).map(([k, n]) => [k, n.pos])) : { ...topo(lv), ...(M.layout[lkey] || {}) };
    const asp = isMap ? lv.aspect : null;
    main.innerHTML = `<div class="mpstage ${isMap ? 'map' : 'graph'}"><div class="mpframe" style="${asp ? `aspect-ratio:${asp};` : ''}">${isMap ? `<img class="mpbg" src="${IMG(lv.image)}" alt="">` : ''}<svg class="mpw"></svg><div class="mpn"></div></div>
      ${!isMap ? `<div class="mpleg"><span class="tag">${T('连通图没有坐标:排版只是为了看;生成地图时才冻结方位')}</span></div>` : ''}
      <div class="mptb">${lv.live && !lv.canAdd ? '' : M.adding ? `<input class="btn" id="maddName" placeholder="${T('新地点的名字')}" style="width:160px;text-transform:none" autocomplete="off" value="${esc(M.addName || '')}"><button class="btn p" data-maddok>${T('加')}</button><button class="btn" data-maddno>${T('取消')}</button>` : `<button class="btn" data-madd>+ ${T('节点(新文件夹)')}</button>${lv.editable ? `<button class="btn ${M.linking ? 'p' : ''}" data-mlink>${M.linking ? (M.linking.from ? T('从「{name}」连到…(点终点)', { name: esc((lv.nodes[M.linking.from] || {}).name || '') }) : T('点起点')) + ' · ' + T('取消') : '+ ' + T('路')}</button>` : ''}`}${lv.parent ? `<button class="btn" data-ml="${lv.parent}">↑ ${T('回到{title}', { title: esc(W().levels[lv.parent].title) })}</button>` : ''}</div></div>`;
    const frame = $('.mpframe', main);
    if (asp) { const st = $('.mpstage', main), W0 = st.clientWidth - 28, H0 = st.clientHeight - 28; let fw = W0, fh = W0 / asp; if (fh > H0) { fh = H0; fw = H0 * asp; } frame.style.width = fw + 'px'; frame.style.height = fh + 'px'; }
    else Object.keys(pos).forEach(k => { if (!(M.layout[lkey] || {})[k]) pos[k] = { x: 6 + pos[k].x * .7, y: pos[k].y }; });
    const draw = () => {
      const w = frame.clientWidth, h = frame.clientHeight, at = id => [pos[id].x / 100 * w, pos[id].y / 100 * h];
      let s = '';
      lv.edges.forEach(e => { if (!pos[e.a] || !pos[e.b]) return; const [x1, y1] = at(e.a), [x2, y2] = at(e.b);
        const on = M.selEdge && ((M.selEdge.a === e.a && M.selEdge.b === e.b) || (M.selEdge.a === e.b && M.selEdge.b === e.a));
        s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="hitln" data-me="${esc(e.a)}|${esc(e.b)}" pointer-events="stroke"/><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="${isMap ? 'road' : 'link'} ${on ? 'on' : ''}"/>${e.d ? `<foreignObject x="${(x1 + x2) / 2 - 60}" y="${(y1 + y2) / 2 - 11}" width="120" height="22"><div class="elab">${esc(e.d)}</div></foreignObject>` : ''}`; });
      const ports = (lv.ports || []); let pi = 0;
      ports.forEach(p => { const t = upTarget(lv, p), px = w - 30, py = 40 + pi++ * 58;
        if (p.via && pos[p.via]) { const [x, y] = at(p.via); s += `<path d="M${x},${y} C${(x + px) / 2},${y} ${(x + px) / 2},${py} ${px},${py}" class="portline"/>`; } });
      $('svg', frame).innerHTML = s;
      $('.mpn', frame).innerHTML = Object.entries(lv.nodes).map(([id, n]) => { if (!pos[id]) return ''; const [x, y] = at(id); const sub = n.child ? W().levels[n.child] : null;
        return `<div class="mnode ${n.fog ? 'fog' : ''} ${M.sel === id ? 'sel' : ''} ${n.dangling && n.dangling.length ? 'bad' : ''} ${lv.entry === id ? 'entry' : ''}" style="left:${x}px;top:${y}px" data-mn="${id}">
          ${isMap ? '<span class="pin"></span>' : `<span class="disc">${n.img ? `<img src="${IMG(n.img)}" alt="">` : esc(n.name.slice(0, 1))}</span>`}
          <span class="lb">${esc(n.name)}${sub ? `<i>▾ ${Object.keys(sub.nodes).length}</i>` : ''}</span></div>`; }).join('')
        + ports.map((p, i) => { const t = upTarget(lv, p); return `<div class="mport ${p.via ? '' : 'open'}" style="left:${w - 30}px;top:${40 + i * 58}px"><img src="img/icon-gate.png" alt=""><span>↑ ${p.up}${t ? ' ' + esc(t.name) : ''}</span></div>`; }).join('');
    };
    requestAnimationFrame(draw);
    panZoom($('.mpstage', main), frame, `m:${M.world}:${M.level}:${isMap ? 'map' : 'graph'}`, !isMap);   // 拖空白平移 · ⌘+滚轮缩放 · 双击空白复位
    let drag = null;
    frame.onpointerdown = e => { const n = e.target.closest('[data-mn]');
      if (M.linking && n && lv.editable) {   // 建路:点起点,再点终点
        e.preventDefault();
        if (!M.linking.from) { M.linking.from = n.dataset.mn; renderDuo(); return; }
        if (n.dataset.mn !== M.linking.from) { const a = M.linking.from, b = n.dataset.mn; M.linking = null; M.selEdge = { a, b }; M.sel = null; window.MAPHOOK.road(M.level, a, b, {}); }
        return;
      }
      const ln = e.target.closest('[data-me]'); if (ln && !n) { const [a, b] = ln.dataset.me.split('|'); M.selEdge = { a, b }; M.sel = null; renderDuo(); return; }
      if (n) { drag = { id: n.dataset.mn, sx: e.clientX, sy: e.clientY, moved: false }; M.dragging = true; try { frame.setPointerCapture(e.pointerId); } catch {} e.preventDefault(); } };
    frame.onpointermove = e => { if (!drag) return; const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy; if (Math.abs(dx) + Math.abs(dy) < 4) return; drag.moved = true;
      const r = frame.getBoundingClientRect(); pos[drag.id] = { x: Math.max(2, Math.min(98, (e.clientX - r.left) / r.width * 100)), y: Math.max(3, Math.min(97, (e.clientY - r.top) / r.height * 100)) }; draw(); };
    frame.onpointerup = () => { M.dragging = false; if (!drag) return; const d = drag; drag = null;
      if (d.moved) {
        if (!isMap) { (M.layout[lkey] = M.layout[lkey] || {})[d.id] = { ...pos[d.id] }; return; }  // 连通图没有坐标:拖动只改排版,记在这一页
        if (isMap && lv.editable) { lv.nodes[d.id].pos = { x: +pos[d.id].x.toFixed(1), y: +pos[d.id].y.toFixed(1) }; window.MAPHOOK.move(M.level, d.id, lv.nodes[d.id].pos.x, lv.nodes[d.id].pos.y); renderDuo(); return; }
        if (lv.live && !lv.editable) { pos[d.id] = { ...lv.nodes[d.id].pos }; draw(); const bn = document.querySelector('.mbanner.ro'); if (bn) { bn.classList.remove('flash'); void bn.offsetWidth; bn.classList.add('flash'); } return; }  // 只读:钉子弹回,顶部横条闪一下告诉你怎么编辑
        if (isMap) { lv.nodes[d.id].pos = { x: +pos[d.id].x.toFixed(1), y: +pos[d.id].y.toFixed(1) }; delete lv.nodes[d.id].raw; M.stale[M.level] = true; renderDuo(); } return; }
      const now = Date.now(); if (M.lastClick && M.lastClick.id === d.id && now - M.lastClick.t < 450 && lv.nodes[d.id].child) { M.level = lv.nodes[d.id].child; M.sel = null; M.lastClick = null; renderDuo(); return; }
      M.lastClick = { id: d.id, t: now }; M.sel = d.id; M.selEdge = null; renderDuo(); };
    frame.ondblclick = e => { const n = e.target.closest('[data-mn]'); if (n && lv.nodes[n.dataset.mn].child) { M.level = lv.nodes[n.dataset.mn].child; M.sel = null; renderDuo(); } };
  }

  function drawTree(main) {
    const row = (addr, d) => { const lv = W().levels[addr];
      return `<div class="tl-level" style="--d:${d}"><div class="tl-h" data-ml="${addr}"><span class="lvl">${lv.scale || SCALE[d]}</span><b>${esc(lv.title)}</b><span class="mono">${lv.file}</span><span class="chip ${lv.frozen ? 'sage' : ''}">${lv.frozen ? T('有地图') : T('只有连通图')}</span>${(lv.ports || []).length ? `<span class="chip lime">↑ ${(lv.ports || []).map(p => p.up + (p.via ? '→' + lv.nodes[p.via].name : '→?')).join(' · ')}</span>` : ''}</div>
        <div class="tl-nodes">${Object.entries(lv.nodes).map(([id, n]) => `<span class="tl-n ${n.child ? 'has' : ''}" data-mpick="${addr}|${id}">${esc(n.name)}<em>${lv.edges.filter(e => e.a === id || e.b === id).length}</em></span>`).join('') || '<span style="color:var(--muted)">' + T('(空文件夹)') + '</span>'}</div>
        ${Object.values(lv.nodes).filter(n => n.child).map(n => row(n.child, d + 1)).join('')}</div>`; };
    main.innerHTML = `<div class="tlw scroll"><div class="sub" style="margin:0 0 14px">${T('文件夹 = 层级(树);每一层自己是一张连通图(数字 = 这个点连着几条路);↑ = 上一层的路从哪个点进来。')}</div>${row(W().root, 0)}</div>`;
  }
  function drawJson(main) {
    const lv = L(), id = M.sel || Object.keys(lv.nodes)[0];
    const graph = { level: M.level, scale: lv.scale || SCALE[depth(M.level)], parent: lv.parent || null, entry: lv.entry || null, frozen: !!lv.frozen,
      nodes: Object.entries(lv.nodes).map(([k, n]) => ({ id: k, name: n.name, type: n.type, has_children: !!n.child, pos: n.pos || null })),
      edges: lv.edges.map(e => ({ a: e.a, b: e.b, cost: e.d || null })), ports: (lv.ports || []).map(p => ({ up: p.up, via: p.via })) };
    const n = lv.nodes[id];
    const loc = n ? { id, name: n.name, type: n.type, pos: n.raw ? (M.level === 'world' ? n.raw : { x: n.raw[0], y: n.raw[1] }) : (n.pos || null),
      connections: lv.edges.filter(e => e.a === id || e.b === id).map(e => e.a === id ? e.b : e.a).concat(n.dangling || []), ...((lv.ports || []).some(p => p.via === id) ? { ports: { up: (lv.ports || []).filter(p => p.via === id).map(p => p.up) } } : {}) } : null;
    main.innerHTML = `<div class="jw"><div class="glass deep jbox"><div class="tag">${T('这一层的连通图 · 引擎导出(level_graph,建议)')}</div><pre class="code">${esc(JSON.stringify(graph, null, 2))}</pre></div>
      <div class="glass deep jbox"><div class="tag">${lv.file}${lv.file.endsWith('/') ? id + '/location.json' : ''} · ${T('磁盘上的样子')}</div><pre class="code">${esc(JSON.stringify(loc, null, 2))}</pre>
      <div class="sub" style="font-size:12px;padding:0 18px 14px">${T('一个地点只写自己的事:同层 connections + 在父层里的 pos;跨层靠 <span class="mono">ports.up</span>(新增)。')}</div></div></div>`;
  }

  function generate() {
    const lv = L(); M.gen = M.level; M.genStep = 0; renderDuo();
    const tick = () => { M.genStep++; if (M.genStep < 3) { renderDuo(); setTimeout(tick, 700); return; }
      const pos = lv.genPos || topo(lv); Object.entries(lv.nodes).forEach(([k, n]) => { n.pos = { ...(pos[k] || { x: 50, y: 50 }) }; delete n.raw; });
      if (!lv.image) lv.image = 'place-guild.jpg';
      lv.frozen = true; lv.fitNote = `assets/maps/${M.level.replace('/', '_')}.json · ${T('刚生成')}`; M.stale[M.level] = false; M.gen = null; M.view = 'map'; renderDuo(); };
    setTimeout(tick, 700);
  }

  document.addEventListener('change', e => { if (e.target.id === 'mwSel' && window.LIVE_openWorld) window.LIVE_openWorld(e.target.value); });
  document.addEventListener('click', e => { if (e.target.closest('[data-mretry]') && window.LIVE_openWorld) window.LIVE_openWorld((window.MAPHOOK.openFail || {}).tid); });
  // 输入的名字记在 M 上:等待中的重画(拖钉子写回后会重读地图)换掉输入框也不丢
  document.addEventListener('input', e => { if (e.target.id === 'maddName') M.addName = e.target.value; });
  document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'maddName') { const b = document.querySelector('[data-maddok]'); b && b.click(); } });
  document.addEventListener('click', e => {
    if (S.screen !== 'duo' || S.face !== 'world' || S.duoTab.world !== 'map') return;
    const q = s => e.target.closest(s); let t;
    if ((t = q('[data-mw]'))) { const prev = M.level; M.world = t.dataset.mw; M.level = WORLDS[M.world].levels[prev] ? prev : M.world === 'stoneford' ? 'T001' : WORLDS[M.world].root; M.sel = null; M.adding = false; M.view = M.world === 'isles' ? 'graph' : M.view; renderDuo(); return; }
    if ((t = q('[data-ml]'))) { M.level = t.dataset.ml; M.sel = null; M.selEdge = null; M.linking = null; renderDuo(); return; }
    if ((t = q('[data-mv]'))) { M.view = t.dataset.mv; renderDuo(); return; }
    if ((t = q('[data-mpick]'))) { const [a, id] = t.dataset.mpick.split('|'); M.level = a; M.sel = id; M.view = 'graph'; renderDuo(); return; }
    if (q('[data-mgen]')) { if (L().editable) window.MAPHOOK.generate(M.level); else if (!L().live) generate(); return; }
    if ((t = q('[data-mport]'))) { L().ports[+t.dataset.mport].via = M.sel; renderDuo(); return; }
    if ((t = q('[data-mfix]'))) { const [k, id, tg] = t.dataset.mfix.split(':'); const n = L().nodes[id]; n.dangling = n.dangling.filter(x => x !== tg);
      if (k === 'bind') { const p = L().ports.find(p => p.up === 'R002'); if (p) p.via = id; } renderDuo(); return; }
    if ((t = q('[data-mkchild]'))) { const id = t.dataset.mkchild, addr = (M.level === 'world' ? '' : M.level + '/') + id, lv = L();
      W().levels[addr] = { title: lv.nodes[id].name, scale: T('下一层'), parent: M.level, file: lv.file.replace(/\/?$/, '/') + id + '/', image: null, aspect: 1.5, frozen: false, nodes: {}, edges: [], ports: lv.edges.filter(e => e.a === id || e.b === id).map(e => ({ up: e.id, via: null })) };
      lv.nodes[id].child = addr; M.level = addr; M.sel = null; renderDuo(); return; }
    if (q('[data-maddno]')) { M.adding = false; M.addName = ''; renderDuo(); return; }
    if (q('[data-mlink]')) { M.linking = M.linking ? null : {}; M.selEdge = null; renderDuo(); return; }
    if (q('[data-mroadx]')) { M.selEdge = null; renderDuo(); return; }
    if (q('[data-mroaddel]') && M.selEdge) { const { a, b } = M.selEdge; M.selEdge = null; window.MAPHOOK.road(M.level, a, b, { remove: true }); return; }
    if (q('[data-mroadd]') && M.selEdge) { const v = ($('#mroadD') || {}).value || ''; const n = Number(v); window.MAPHOOK.road(M.level, M.selEdge.a, M.selEdge.b, { distance: v === '' ? null : isNaN(n) ? v : n }); return; }
    if (q('[data-maddok]')) { const lv = L(), nmv = ($('#maddName') || {}).value || M.addName || ''; if (!nmv.trim()) return; M.adding = false; M.addName = '';
      const link = M.sel && lv.nodes[M.sel] ? M.sel : ''; const at = link && lv.nodes[link].pos ? { x: Math.min(95, lv.nodes[link].pos.x + 6), y: Math.min(92, lv.nodes[link].pos.y + 6) } : { x: 50, y: 50 };
      window.MAPHOOK.add(M.level, nmv.trim(), at.x, at.y, link); return; }
    if (q('[data-madd]') && L().editable) { M.adding = true; renderDuo(); setTimeout(() => { const i = $('#maddName'); i && i.focus(); }, 0); return; }
    if (q('[data-madd]')) { const lv = L(), id = 'p' + Date.now() % 10000; lv.nodes[id] = { name: '新地点', type: 'place', pos: lv.frozen ? { x: 50, y: 50 } : null };
      const hub = M.sel || lv.entry || Object.keys(lv.nodes)[0]; if (hub && hub !== id) lv.edges.push({ id: 'n' + id, a: hub, b: id, d: '' });
      if (lv.frozen) M.stale[M.level] = true; M.sel = id; renderDuo(); return; }
  });
})();
