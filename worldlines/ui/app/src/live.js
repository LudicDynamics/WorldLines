/* 真引擎层:把原型里接得上的几屏换成 neonrp 的真实数据。
   接上的:游玩一览(模板库)· 测试台(一局的对话流 + 自动视图页签)· 世界面的地图(/api/v1/play/map 的层、边、图、钉子)·
   编排 / Template / 前端 / 世界·角色(10-17 工作台两批,顶栏右侧写着这一页读的是什么)。
   原型的演示数据(编排演示图 · 地图里的石津镇 / 暮色群岛)只在 ?demo=1 时出现,默认界面不显示。
   适配层(../real/*.js:V3 / E)来自 3.0,不在前端做任何规则判断。 */
(function () {
  const L = window.LIVE = { ok: false, templates: [], tpl: null, bound: null, err: '' };
  const tplTitle = t => (t.card && t.card.title) || t.id;

  /* ---------- 测试台复用 bench.js 的自动视图:它要的几个全局 ---------- */
  window.st = () => E.s;
  window.nm = a => (E.s && E.s.nodes && E.s.nodes[a] && E.s.nodes[a].name) || (V3.names && V3.names[a]) || a;
  window.renderPlay = () => renderTest();

  // 加载失败过的图记下来,之后不再请求(回合进行中每 0.12 秒重画一次,不记的话同一张 404 会被要几十遍)
  const BADIMG = new Set();
  window.BADIMG = BADIMG;
  document.addEventListener('error', e => { const t = e.target; if (t && t.tagName === 'IMG' && t.src) { BADIMG.add(t.src); BADIMG.add(t.getAttribute('src')); t.style.visibility = 'hidden'; } }, true);

  /* ---------- 启动 ---------- */
  async function boot() {
    try {
      V3.setBase(await V3.detectBase());
      const ts = await V3.j('/api/v1/local/templates').catch(() => ({ templates: [] }));
      L.templates = ts.templates || [];
      // 引擎刚起时模板列表先不带 lint(后台在检查):过几秒再取,把「能不能发布」补上
      const poll = async (n) => { if (!L.templates.some(t => t.checking) || n > 30) return; await new Promise(r => setTimeout(r, 3000));
        const t2 = await V3.j('/api/v1/local/templates').catch(() => null); if (t2 && t2.templates) { L.templates = t2.templates; render(); } poll(n + 1); };
      poll(0);
      const r = await V3.bind();
      await E.load();
      loadCard(true);
      // 这一局的模板 id:引擎的 run view 给;没给(老的局 / 引擎还在开)就看地址里的 ?tpl= 和局名 tpl-<id>-<日期>(10-17:以前退成局名,
      // 当前世界认不出它 → 落到列表第一个世界「归乡」)
      const has = id => !!id && L.templates.some(t => t.id === id), slug = String((r && r.slug) || '');
      const fromSlug = (slug.match(/^tpl-+(.+?)(?:-\d{8}-\d{6})?$/) || [])[1];
      L.bound = [V3.template && V3.template.id, new URLSearchParams(location.search).get('tpl'), fromSlug].find(has) || slug || null;
      L.tpl = L.tpl || L.bound;
      
      E.subscribe(() => {
        if (S.screen === 'test') render();
      });
      E.listen && E.listen();
      L.ok = true;
      // 深链接(10-18 orch-preview:创作台「到编排台编辑」):?screen=orch&edit=<模板 id> 直接进编排台、当前世界 = 这个模板。
      // 不用 ?tpl=:那个会开一局(V3.bind),这里只是打开编辑
      const q = new URLSearchParams(location.search), want = q.get('screen'), wt = q.get('edit');
      if (wt && L.templates.some(t => t.id === wt)) { S.world = wt; S.worldBy = 'chosen'; }
      if (want && SCREENS.some(x => x[0] === want)) S.screen = want;
    } catch (e) { L.err = String(e.message || e); console.error(e); }
    render();
  }

  /* ---------- 游玩一览 = 模板库 ---------- */
  catalog = function () {
    if (!L.ok && !L.templates.length) return [];
    return L.templates.map(t => {
      const pc = String(t.play_contract || '').split('@')[0] || null;
      const ctr = pc && CONTRACTS[pc] ? pc : null;
      const modes = [{ open: '开放结局', single: '有结局', multi: '多结局' }[t.mode && t.mode.ending] || '', { free: '沙盒', semi: '半沙盒', guided: '引导' }[t.mode && t.mode.freedom] || ''].filter(Boolean).join(' · ');
      const gaps = ctr ? [{ t: '合约检查要等引擎 R1(按合约 lint)', code: 'contract.*', go: 'tpl' }] : [{ t: '没有声明玩法合约 → 还不能进 Hub', code: 'contract.unknown', go: 'tpl' }];
      return { id: t.id, title: tplTitle(t), img: t.card && t.card.cover ? V3.url(`/api/v1/local/templates/${encodeURIComponent(t.id)}/cover`) : 'cover-elena.jpg',
        ctr, pitch: (t.card && t.card.pitch) || '', status: 'local', meta: [t.id === L.bound ? '当前这一局' : '', modes, String(t.pack || '').split('+').slice(1).join(' · ')].filter(Boolean).join(' · ') || (t.pack || ''),
        gaps, mine: true, bound: t.id === L.bound };
    });
  };
  // 一览卡片上的「试玩」:记下选的模板,进测试台时绑这一局
  document.addEventListener('click', e => {
    const b = e.target.closest('.shelf [data-go="test"], .wc [data-go="test"]');
    if (b && S.sel) { L.tpl = S.sel; setWorld(S.sel, { quiet: true }); }   // 一览上点「试玩」= 当前世界换成它,并开它的一局
  }, true);

  /* ---------- 测试台 ---------- */
  // 还没好时说清楚在干什么(10-08 实测被当成「引擎没打开」:其实是正在开局,十几秒)
  const waitText = () => { const t = L.tpl && (L.templates.find(x => x.id === L.tpl) || {}); return L.tpl && L.tpl !== L.bound ? `正在开一局「${t && t.card ? tplTitle(t) : L.tpl}」…(复制世界 + 生成开场,第一次要十几秒)` : '连接引擎……'; };
  async function ensureBound() {
    if (!L.tpl || L.tpl === L.bound || L.binding) return;
    L.binding = true; render();
    try {
      // 模板声明了捏人(player.builder):先捏人 → 选同伴 → 开场(src/builder.js);取消 = 回到原来那一局
      if (window.BUILDER) await window.BUILDER.start(L.tpl, 'zh', { cancel: true }); else await V3.post('/api/v1/play/session', { slug: `tpl--${L.tpl}`, output_lang: 'zh' });
      E.relisten && E.relisten(); await E.load(); L.bound = L.tpl; loadCard(true); setWorld(L.bound, { quiet: true });
    }
    catch (e) { if (e && e.cancelled) L.tpl = L.bound; else L.err = String(e.message || e); }
    L.binding = false; render();
  }
  // 地点 / 角色的显示名:没去过的地方引擎不给名字(信息边界),就说「哪个镇 · 没去过的地方」
  const placeName = a => { a = String(a || ''); if (!a) return ''; const n = nm(a); if (n && n !== a) return n; const t = a.split('/')[0], tn = nm(t); return a.includes('/') && tn && tn !== t ? `${tn} · 没去过的地方` : a; };
  const whoName = id => { id = String(id || '').replace(/\.at$/, ''); if (id === 'player') return '你'; const ss = Object.values((E.s && E.s.souls) || {}), bare = id.replace(/^si-/, '').replace(/\d+$/, '');
    const so = ss.find(x => x.iid === id || x.id === id || 'si-' + x.iid === id) || ss.find(x => x.id === bare);   // 实例 id(si-elena0001)也认
    return so ? so.name : nm(id) || id; };
  window.LIVE_placeName = placeName;
  // ── 游玩层的文字渲染(10-08:以叙事的流式文字为主线,先把文字体验做好;拍的样子查 BEATS) ──
  // 叙事里的引擎标记:[op 参数] = 同步(这一拍等它回来)· [~op 参数] = 异步(后台去做)· <…> = 引擎的话 —— 不再原文漏出来
  const richText = t => esc(String(t || ''))
    .replace(/\[(~?)([a-z_]+)([^\]\n]*)\]/g, (_, a, op, rest) => `<span class="opp ${a ? 'async' : 'sync'}" title="${a ? '异步:后台去做,不挡这一拍' : '同步:这一拍等它回来'}">${a ? '↻ ' : ''}${op}${rest.trim() ? ' ' + rest.trim() : ''}</span>`)
    .replace(/&lt;([^&\n]{1,80})&gt;/g, '<span class="engmsg">$1</span>');
  const paras = t => String(t || '').split(/\n+/).filter(Boolean).map(p => `<p>${richText(p)}</p>`).join('');
  const LV = { 大成功: 'crit', 极难成功: 'great', 困难成功: 'good', 成功: 'ok', 失败: 'bad', 大失败: 'fumble' };
  function diceHtml(d) {
    const lv = d.level || (d.ok ? '成功' : d.res ? '失败' : '');
    const kind = d.sides === 100 ? '百分骰' : d.sides ? 'd' + d.sides : '骰';
    return `<div class="dicecard ${LV[lv] || (d.ok ? 'ok' : 'bad')}"><span class="die">${kind}</span><div class="dmain"><b>${esc(whoName(d.who) || d.who || '')}</b> ${esc(d.skill || d.attr || '')}<small>${d.total != null ? esc(d.total) : '?'}${d.dc != null ? ` ${d.under ? '≤' : '≥'} ${esc(d.dc)}` : ''}${d.vs ? ' · 对抗' : ''}${d.why ? ' · ' + esc(d.why) : ''}</small></div><span class="dres">${esc(lv || d.res || '')}</span></div>`;
  }
  // 状态变化:扣血红 · 加血绿 · 归零 = 倒地 · SAN 紫;移动是普通标签
  function changeChip(c) {
    if (c.kind === 'status') return `<span class="chip st cond">＋${esc(c.to)}</span>`;
    if (c.kind === 'node') return `<span class="chip">＋${esc(c.to)}</span>`;
    if (c.kind === 'move') return `<span class="chip">${esc(`${whoName(c.who || String(c.what).replace(/\.at$/, ''))} → ${placeName(c.to)}`)}</span>`;
    const what = String(c.what || ''), owner = what.includes('.') ? what.split('.')[0] : '', key = what.split('.').pop();
    const name = owner && owner !== 'player' ? whoName(owner) : owner === 'player' ? '你' : '';
    const a = Number(c.from), b = Number(c.to), num = !isNaN(a) && !isNaN(b) && c.from !== undefined;
    let cls = 'rust', tag = '';
    if (num && /^(hp|health|生命)$/i.test(key)) { cls = b < a ? 'hurt' : 'heal'; if (b <= 0) tag = b < 0 ? '阵亡' : '倒地'; }
    else if (num && /^san$/i.test(key)) cls = 'san';
    else if (num) cls = b < a ? 'dn' : 'up';
    return `<span class="chip st ${cls}">${esc(name ? name + ' ' : '')}${esc(key)} ${num ? `${esc(c.from)} → ${esc(c.to)}` : `→ ${esc(c.to)}`}${tag ? ` · <b>${tag}</b>` : ''}</span>`;
  }
  // 身上的状态(status 类的实例:中毒 / 流血 … 剩几次结算)+ 结局(settlement)—— 每拍变化后重读一次
  const PX = { key: null, status: [], settle: null, plots: null, plotsFor: null };
  async function loadPlayExtras() {
    const key = `${L.bound}:${(E.s.rounds || []).length}:${E.s.turn}`;
    if (PX.key === key || PX.loading) return; PX.loading = true; PX.key = key;
    const [st, se] = await Promise.all([V3.j('/api/v1/play/engine/entities?cls=status').catch(() => null), V3.j('/api/v1/play/engine/settlement').catch(() => null)]);
    PX.status = (st && st.entities) || []; PX.settle = se && se.exit ? se : null;
    if (PX.settle && PX.plotsFor !== L.bound) { PX.plotsFor = L.bound; PX.plots = await V3.j(`/api/v1/local/templates/${encodeURIComponent(L.bound)}/plots`).catch(() => null); }
    PX.loading = false;
    if (S.screen === 'test') render();
  }
  const CONDTONE = s => /毒|poison/i.test(s) ? 'poison' : /血|bleed/i.test(s) ? 'bleed' : /倒地|昏|down|unconscious/i.test(s) ? 'down' : /疯|恐|san|panic/i.test(s) ? 'san' : '';
  function statusBox() {
    const v = Object.values(E.s.vars || {}), hp = v.find(x => x.name === 'player.hp'), san = v.find(x => x.name === 'player.san');
    const rows = PX.status.map(e => { const p = e.props || {}; return `<div class="cond ${CONDTONE(e.name + (p.rule || ''))}"><b>${esc(e.name)}</b>${p.turns != null ? `<span class="chip">剩 ${esc(p.turns)} 次结算</span>` : ''}${p.until_text ? `<span class="chip">到 ${esc(p.until_text)}</span>` : ''}${p.rule || p.note ? `<small>${esc([p.rule, p.note].filter(Boolean).join(' · '))}</small>` : ''}</div>`; }).join('');
    if (!hp && !san && !rows) return '';
    const down = hp && Number(hp.value) <= 0;
    return `<div class="glass box"><span class="tag">你的状态</span>
      ${hp ? `<div class="r"><span>生命</span><span class="${down ? 'vhurt' : ''}">${esc(hp.value)}${down ? ' · 倒地' : ''}</span></div>` : ''}${san ? `<div class="r"><span>理智 SAN</span><span class="vsan">${esc(san.value)}</span></div>` : ''}
      ${rows ? `<div class="conds">${rows}</div>` : '<div class="sub2">身上没有状态</div>'}</div>`;
  }
  const KINDZH = { true: '真相', alt: '分支', fail: '失败', death: '死亡' };
  function endingCard() {
    const st = PX.settle; if (!st) return '';
    const id = st.exit && st.exit.id, rows = (PX.plots && PX.plots.plots) || [];
    let ending = null, slot = null;
    for (const p of rows) { const e = ((p.data || {}).endings || {})[id]; if (e) { ending = e; slot = `plot:${p.path.replace(/\/plot\.json$/, '')}:ending:${id}`; break; } }
    const kind = (ending && ending.kind) || st.exit.kind || '';
    const cg = slot && (st.cg_unlocked || []).includes(id) ? V3.url(`/api/v1/local/templates/${encodeURIComponent(L.bound)}/assets/file?slot=${encodeURIComponent(slot)}`) : '';
    const truth = st.truth_reveal && st.truth_reveal.text;
    const rw = st.rewards && st.rewards.player ? Object.entries(st.rewards.player).filter(([, v]) => v && (!Array.isArray(v) || v.length)) : [];
    return `<div class="ending-card ${esc(kind)}">${cg ? `<img class="ecg" src="${cg}" alt="">` : ''}<div class="ebody">
      <div class="tag">结局 · ${esc(KINDZH[kind] || kind)} · 第 ${esc(st.exit.turn ?? '?')} 回合</div>
      <h2 class="human">${esc((ending && ending.title) || st.epilogue || id)}</h2>
      ${st.epilogue && ending && st.epilogue !== ending.title ? `<p>${esc(st.epilogue)}</p>` : ''}
      ${truth ? `<div class="truth"><span class="tag">真相</span><p>${esc(truth)}</p></div>` : ''}
      ${(st.deaths || []).length ? `<div class="sub2">倒下的:${esc(st.deaths.map(d => whoName(d.who || d.id || '')).join('、'))}</div>` : ''}
      ${rw.length ? `<div class="row" style="flex-wrap:wrap;gap:6px;margin-top:10px">${rw.map(([k, v]) => `<span class="chip lime">${esc({ ending_cg: '结局 CG', clue_codex: '线索图鉴', debrief_scripts: '复盘剧本', memory_carry: '角色记得你' }[k] || k)}${Array.isArray(v) ? ' · ' + v.length : ''}</span>`).join('')}</div>` : ''}
      </div></div>`;
  }
  // 回合进行中:按引擎的流式片段画(谁在说 · 哪一拍,样子查 BEATS),工具调用挂在片段后面,最后一段有光标
  function streamCards() {
    const v = E.liveView || { segs: [] }, souls = Object.values(E.s.souls || {});
    if (!v.segs.length) {   // 还没出字:写上等了几秒,太久了说清楚是模型慢(deepseek 首字常要 20 秒上下),不是卡死
      const sec = Math.round((Date.now() - (L.sentAt || Date.now())) / 1000);
      return `<div class="bt host live"><div class="who">主持 · 在想<span class="dots">…</span> <span class="mono" style="opacity:.7">${sec}s</span></div>${sec >= 15 ? '<div class="sub" style="font-size:12px;margin:4px 0 0">模型这回比较慢,第一个字还没出来;回合没有卡住,出字后会接着往下写</div>' : ''}</div>`;
    }
    let prev = null;
    return v.segs.map((g, i) => {
      const last = i === v.segs.length - 1, so = souls.find(x => x.name === g.who || x.id === g.who);
      const div = BEATS.divider(prev, g.beat);
      prev = g.beat || prev;
      const tools = (g.tools || []).map(t => `<span class="opp ${String(t.name).startsWith('~') ? 'async' : 'sync'} run">${esc(t.name)}</span>`).join('');
      // 最后一个字出来 2.5 秒后还没结束 = 引擎在把这一拍落成状态(校验 · 写入 · 角色事后结算),说清楚,别像卡住
      const idle = last && v.lastChunk ? Math.round((Date.now() - v.lastChunk) / 1000) : 0;
      const tail = !last ? '' : idle >= 3 ? `<div class="settling"><span class="dots">…</span> 落定中:校验 · 写入 · 角色事后结算 · ${idle}s</div>` : '<span class="cursor"></span>';
      const body = `${paras(g.text)}${tools ? `<div class="ops">${tools}</div>` : ''}${tail}`;
      if (so) return div + `<div class="bt soul live">${so.av ? `<img src="${V3.IMG[so.av]}" alt="">` : ''}<div><div class="who">${esc(so.name)} · ${last ? '正在说' : '说'}</div>${body}</div></div>`;
      const sg = BEATS.seg(g.beat, last);
      return div + `<div class="bt ${sg.cls} live"><div class="who">${esc(sg.who)}</div>${body}</div>`;
    }).join('');
  }
  function feedItem(f) {
    const s = E.s, so = f.who && s.souls[f.who];
    const av = so && so.av ? V3.IMG[so.av] : '';
    if (f.kind === 'you') return `<div class="bt you"><div class="who">${esc(BEATS.you(f))}</div>${esc(f.text)}</div>`;
    if (f.kind === 'opening') return `<div class="bt open">${esc(f.text)}</div>`;
    if (f.kind === 'host') return `<div class="bt host ${esc(BEATS.hostCls(f))}"><div class="who">${esc(BEATS.host(f))}</div>${richText(f.text)}</div>`;
    if (f.kind === 'mic') return `<div class="bt mic">递话筒给 <b>${esc(f.to)}</b>${f.text ? ' · ' + esc(f.text) : ''}</div>`;
    if (f.kind === 'soul') return `<div class="bt soul">${av ? `<img src="${av}" alt="">` : ''}<div><div class="who">${esc((so && so.name) || f.name || '')}</div>${richText(f.text)}${f.intent ? `<span class="int">打算:${esc(f.intent)}</span>` : ''}</div></div>`;
    if (f.kind === 'sys') return `<div class="bt mic">${esc(f.text)}</div>`;
    const dice = (f.dice || []).map(diceHtml).join('');
    const who = whoName, place = placeName;
    void who; void place;
    const ch = (f.changes || []).filter(c => c.kind === 'move' || String(c.from) !== String(c.to)).map(changeChip).join('');   // 没变的不列
    const ref = (f.refused || []).map(r => `<span class="chip">没成:${esc(r.why || '')}</span>`).join('');
    return BEATS.narrDivider(f) + brick('bt res', null, `<div class="who">${esc(BEATS.narrWho(f))}${f.by ? ' · ' + esc(BEATS.adv[f.by] || f.by) : ''}</div>${dice}<div class="prose">${paras(f.text)}</div>${ch || ref ? `<div class="chgs">${ch}${ref}</div>` : ''}`);
  }
  function chips() {
    const s = E.s, out = [];
    (s.options || []).slice(0, 4).forEach(o => out.push(o));
    BEATS.chips(s, out);
    Object.values(s.souls || {}).slice(0, 3).forEach(so => out.push('@' + so.name));
    return out;
  }
  // 右栏「角色」页:每个角色的状态(回合进行中显示在想 / 在说)和她身上的变量(hp、SAN、状态……)
  const SST = { thinking: '在想', speaking: '在说', planning: '在想', acting: '在做', idle: '空闲', done: '说完了' };
  function castPanel(cast) {
    if (!cast.length) return '<div class="glass box"><span class="tag">角色</span><div class="sub" style="font-size:12.5px">这一局没有角色</div></div>';
    const st = (E.liveView && E.liveView.souls) || {}, V = Object.values(E.s.vars || {});
    return cast.map(so => { const status = st[so.iid] || st[so.id] || st[so.name], mine = V.filter(v => v.name.startsWith((so.iid || so.id) + '.') || v.name.startsWith(so.id + '.')).slice(0, 6);
      const hp = mine.find(v => /\.hp$/.test(v.name)), down = hp && Number(hp.value) <= 0;
      return `<div class="glass box"><div class="cast">${so.av ? `<img src="${V3.IMG[so.av]}" alt="">` : ''}<div style="flex:1"><b class="human">${esc(so.name)}</b><small>${esc(placeName((E.where(so.id) || {}).at))}</small></div>
        ${down ? '<span class="chip st hurt"><b>倒地</b></span>' : status && E.busy ? `<span class="chip ${/speak|act/.test(status) ? 'lime' : 'sage'}">${esc(SST[status] || status)}</span>` : ''}</div>
        ${mine.map(v => `<div class="r"><span>${esc(v.name.split('.').slice(1).join('.'))}</span><span>${esc(typeof v.value === 'object' ? JSON.stringify(v.value) : v.value)}</span></div>`).join('')}
        ${so.mood || so.intention ? `<div class="sub2">${esc([so.mood, so.intention].filter(Boolean).join(' · '))}</div>` : ''}</div>`; }).join('');
  }
  // 地图 · 节点图(10-11):没有生成的地图图片时也能看 —— 这一层的地点 = 节点,连通的路 = 连线,
  // 你在哪亮起来,角色在哪标点;点一个地点 = 把「我去……」填进输入框(不替你发)
  function mapGraph(s, at) {
    const here = s.nodes[at]; if (!here) return '';
    const level = here.parent || 'world', top = s.nodes[level];
    const kids = Object.values(s.nodes).filter(n => n.parent === level && (s.known[n.addr] || n.addr === at));
    if (kids.length < 2) return '';
    const W = 100, H = 70, pos = {};
    kids.forEach((n, i) => {
      const a = (i / kids.length) * Math.PI * 2 - Math.PI / 2;
      pos[n.addr] = n.pos ? [n.pos[0] / 100 * (W - 16) + 8, n.pos[1] / 100 * (H - 14) + 7] : [W / 2 + Math.cos(a) * 36, H / 2 + Math.sin(a) * 24];
    });
    // the map's pins can sit in one corner of the picture: stretch them over the box so the names do not pile up
    const ps = Object.values(pos), xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    for (const k of Object.keys(pos)) pos[k] = [x1 > x0 ? 10 + (pos[k][0] - x0) / (x1 - x0) * (W - 20) : W / 2, y1 > y0 ? 8 + (pos[k][1] - y0) / (y1 - y0) * (H - 20) : H / 2];
    const edges = Object.values(s.edges).filter(e => e.level === level && pos[e.from] && pos[e.to]);
    const who = {}; Object.values(s.souls || {}).forEach(so => { const w = E.where(so.id); if (w.at && pos[w.at]) (who[w.at] ||= []).push(so.name); });
    const lines = edges.map(e => `<line x1="${pos[e.from][0]}" y1="${pos[e.from][1]}" x2="${pos[e.to][0]}" y2="${pos[e.to][1]}" class="${e.blocked ? 'blk' : ''}"/>`).join('');
    const dots = kids.map(n => { const [x, y] = pos[n.addr], me = n.addr === at, sub = Object.values(s.nodes).some(c => c.parent === n.addr);
      return `<g class="mg ${me ? 'me' : ''}" data-mgo="${esc(n.name)}"><circle cx="${x}" cy="${y}" r="${me ? 3.2 : 2.4}"/>${sub ? `<circle cx="${x}" cy="${y}" r="4.4" class="ring"/>` : ''}
        <text x="${x}" y="${y + 6.6}">${esc(n.name)}</text>${(who[n.addr] || []).map((nm2, k) => `<text class="who" x="${x + 4}" y="${y - 3 - k * 3.4}">● ${esc(nm2)}</text>`).join('')}</g>`; }).join('');
    return `<div class="glass box mapg"><span class="tag">地图 · ${esc(top ? top.name : level)}</span>
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${lines}${dots}</svg>
      <div class="sub2">点一个地点 = 把「我去……」放进输入框 · 订阅 location · map</div></div>`;
  }
  // pointerdown, not click: the bench redraws while a turn streams, and a node replaced between press and release eats the click
  document.addEventListener('pointerdown', e => {
    const g = e.target.closest && e.target.closest('[data-mgo]'); if (!g || S.screen !== 'test') return;
    const inp = document.getElementById('min'); if (!inp || inp.disabled) return;
    inp.value = `我去${g.dataset.mgo}。`; U.minDraft = inp.value; inp.focus();
  });
  function boardBox() {
    const b = E.s.board; if (!b || !BEATS.board) return '';
    return BEATS.board(b);
  }
  renderTest = function () {
    const el = $('#s-test');
    if (!L.ok) { el.innerHTML = `<div class="mk"><div></div><div class="glass gl pad" style="display:grid;place-items:center">${L.err ? `连不上引擎:${esc(L.err)}` : esc(waitText())}</div></div>`; return; }
    if (L.tpl && L.tpl !== L.bound) { ensureBound(); el.innerHTML = `<div class="mk"><div></div><div class="glass gl pad" style="display:grid;place-items:center">${esc(waitText())}</div></div>`; return; }
    loadPlayExtras();
    const old = $('#mfeed'), keep = old ? { top: old.scrollTop, near: old.scrollHeight - old.scrollTop - old.clientHeight < 80 } : null;   // 往上翻的时候别把人拉回底部
    const s = E.s, pp = E.where('player'), at = pp.at, place = at && s.nodes[at];
    const t = L.templates.find(x => x.id === L.bound) || {};
    let scene = at && V3.SCENE[at] ? V3.IMG[V3.SCENE[at]] : V3.IMG.map_world;
    if (BADIMG.has(scene)) scene = null;   // 没有这张图(比如还没生成层地图):别每次重画都再要一遍
    const vars = Object.values(s.vars).filter(v => /^player\./.test(v.name) && !/^player\.(hp|san)$/.test(v.name));   // hp / SAN 在「你的状态」里
    const cast = Object.values(s.souls || {});
    const center = U.ptab === 'play'
      ? `${benchStrip()}<div class="feed" id="mfeed">${(s.feed || []).slice(-80).map(feedItem).join('')}${E.busy ? streamCards() : endingCard()}</div>
        <div class="mcomp"><div class="in"><input id="min" placeholder="${esc(BEATS.placeholder)}" autocomplete="off" value="${esc(U.minDraft || '')}" ${E.busy ? 'disabled' : ''}>${E.busy ? `<button class="btn stopb" id="mstop" ${L.stopping ? 'disabled' : ''}>${L.stopping ? '停下中…' : '■ 停止'}</button>` : '<button class="send" id="msend" aria-label="发送">➤</button>'}</div>
        <div class="sugg">${chips().map(c => `<button class="chip" data-lsay="${esc(c)}">${esc(c)}</button>`).join('')}</div></div>`
      : null;
    el.innerHTML = `<div class="mk">
      <div class="mk-left"><div class="glass gl pad"><span class="tag">当前世界</span><div style="margin-top:10px">${brick('wcard', t.card && t.card.cover ? V3.url(`/api/v1/local/templates/${encodeURIComponent(t.id)}/cover`) : 'cover-elena.jpg', `<b>${esc(tplTitle(t))}</b><small>${esc((t.card && t.card.pitch || '').slice(0, 40))}</small>`)}</div></div>
        <div class="glass gl pad"><span class="tag">时间 · 回合</span><div class="clock" style="margin:6px 0 2px">第 ${s.day} 天 · ${E.clock()}</div><div class="tag" style="text-transform:none;letter-spacing:.04em">回合 ${s.turn} · ${(s.rounds || []).length} 拍 · tick ${s.tick}</div>
          <div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn" data-ltick>推进一格</button></div></div>
        <div class="glass gl pad"><span class="tag">出口检查 · 合约的固定输出</span><div class="sub" style="font-size:12.5px;margin-top:6px">${t.play_contract ? '合约 ' + esc(t.play_contract) + ' · ' : '这个模板没声明合约 · '}结算产物要等引擎 R5</div></div></div>
      <div class="glass gl mk-mid">${center !== null ? center : '<div id="lbench" style="display:flex;flex-direction:column;flex:1;min-height:0"></div>'}</div>
      <div class="mk-right"><div class="seg rsw">${[['player', '玩家'], ['cast', '角色'], ...(L.card ? [['card', window.BUILDER ? window.BUILDER.t('preview') : '面板']] : [])].map(([k, l]) => `<button class="${(U.rside || 'player') === k ? 'on' : ''}" data-rside="${k}">${l}</button>`).join('')}</div>${(U.rside || 'player') === 'card' && L.card ? cardPanel() : (U.rside || 'player') === 'cast' ? castPanel(cast) : `${scene ? brick('loc', scene, `<b>${esc(place ? place.name : '在路上')}</b><small>${esc(nm(String(at || '').split('/')[0]) || '')}</small>`) : ''}
        ${mapGraph(s, at)}
        <div class="glass box"><span class="tag">位置 · 时间</span><div class="r"><span>在</span><span>${esc(nm(at) || at || '—')}</span></div><div class="r"><span>时间</span><span>第 ${s.day} 天 ${E.clock()}</span></div><div class="sub2">订阅 · location · time.*</div></div>
        ${vars.length ? `<div class="glass box"><span class="tag">玩家</span>${vars.map(v => `<div class="r"><span>${esc(v.name.replace(/^player\./, ''))}</span><span>${esc(v.value)}</span></div>`).join('')}<div class="sub2">订阅 · player.*</div></div>` : ''}
        ${statusBox()}
        ${boardBox()}

        <div class="glass box"><span class="tag">最近的世界变化</span>${(s.events || []).slice(-6).reverse().flatMap(ev => ev.changes.slice(0, 2).map(c => c.kind === 'move' || /\.at$/.test(c.what) ? `<div class="r" style="font-size:12.5px"><span>${esc(whoName(c.who || c.what))}</span><span>→ ${esc(placeName(c.to))}</span></div>` : `<div class="r" style="font-size:12.5px"><span>${esc(c.what)}</span><span>${esc(c.to)}</span></div>`)).join('') || '<div class="sub" style="font-size:12.5px">还没有变化</div>'}</div>`}</div></div>`;
    if (center === null) { const host = $('#lbench'); renderBenchInto(host); }
    const f = $('#mfeed');
    if (f) {
      f.scrollTop = !keep || keep.near ? f.scrollHeight : keep.top;
      if (keep && !keep.near) f.insertAdjacentHTML('afterend', '<button class="chip lime tolatest" data-tolatest>↓ 回到最新</button>');
    }
    wireStrip(el);
  };
  // 面板玩家(10-14):这一局开局时捏的角色卡(GET /api/v1/play/engine/player-card,引擎从写进去的文件读回现在的值)。
  // 没捏人的局没有这张卡,页签不出现;打开页签时每 5 秒最多取一次(玩的过程中属性会变)
  async function loadCard(force) {
    if (!force && Date.now() - (L.cardAt || 0) < 5000) return;
    L.cardAt = Date.now();
    const c = await V3.j('/api/v1/play/engine/player-card').catch(() => null);
    const had = JSON.stringify(L.card || null); L.card = c && c.builder ? c : null;
    if (!L.card && U.rside === 'card') U.rside = 'player';
    if (JSON.stringify(L.card || null) !== had && S.screen === 'test') render();
  }
  function cardPanel() { if (!E.busy) loadCard(false); return `<div class="glass box" style="padding:10px">${window.BUILDER ? window.BUILDER.runPanel(L.card) : ''}<div class="sub2">player-card · game/player/card.json</div></div>`; }
  // bench.js 的 renderBench 写死 #pmain:这里给它一个容器
  function renderBenchInto(host) {
    if (!host) return;
    host.id = 'pmain'; renderBench(); host.id = 'lbench';
  }
  async function say(text) {
    if (!text || E.busy) return;
    L.sentAt = Date.now();
    const tick = setInterval(() => { const v = E.liveView; if (S.screen === 'test' && E.busy && (!(v.segs || []).length || Date.now() - (v.lastChunk || 0) > 2500)) render(); }, 1000);   // 等第一个字 / 落定中:每秒刷新秒数
    const p = E.say(text); render(); try { await p; } finally { clearInterval(tick); render(); }
  }
  // 输入框里打的字记在 U 上:回合进行中消息一来就会重画,不记的话打到一半就没了
  document.addEventListener('input', e => { if (e.target.id === 'min') U.minDraft = e.target.value; });
  document.addEventListener('click', e => {
    if (S.screen !== 'test') return;
    const rs = e.target.closest('[data-rside]'); if (rs) { U.rside = rs.dataset.rside; render(); return; }
    if (e.target.closest('[data-tolatest]')) { const f = $('#mfeed'); if (f) f.scrollTop = f.scrollHeight; render(); return; }
    if (e.target.closest('#mstop')) { L.stopping = true; render(); E.cancel().then(r => { if (r && r.ok === false && typeof toast === 'function') toast('停不下来:' + (r.error || '')); }).finally(() => { setTimeout(() => { L.stopping = false; render(); }, 800); }); return; }
    const b = e.target.closest('[data-lsay]'); if (b) { const v = b.dataset.lsay; if (v.startsWith('@') && !/^@(DM|GM|主持)$/i.test(v)) { const i = $('#min'); if (i) { i.value = v + ' '; i.focus(); } return; } say(v); return; }
    if (e.target.closest('#msend')) { const i = $('#min'), v = ((i && i.value) || U.minDraft || '').trim(); if (v) { U.minDraft = ''; say(v); } return; }
    if (e.target.closest('[data-ltick]')) { E.tick(true); }
  });
  document.addEventListener('keydown', e => { if (S.screen === 'test' && e.key === 'Enter' && e.target.id === 'min' && e.target.value.trim()) { const v = e.target.value.trim(); U.minDraft = ''; say(v); } });

  /* ---------- 世界面 · 地图 = /api/v1/play/map ---------- */
  // 地图层:编辑会话读的是世界源文件(全部真相,可写)
  const EDIT = '/api/v1/create/session/edit-local';
  const scaleOf = n => ({ world: '世界', town: '镇', city: '城', dungeon: '地穴', region: '地区' })[n && n.kind] || '地点';
  function levelsFrom(map, img, editable) {
    const N = map.nodes || {}, levels = {};
    const lvKeys = new Set(['world', ...Object.keys(map.levels || {}), ...Object.values(N).filter(n => (n.children || []).length).map(n => n.addr)]);
    for (const lv of lvKeys) {
      const self = N[lv] || { name: map.root && map.root.name || '世界', kind: 'world' }, info = (map.levels || {})[lv] || {};
      const kids = Object.values(N).filter(n => (n.parent || null) === (lv === 'world' ? 'world' : lv) && n.addr !== lv);
      if (!kids.length) continue;
      const nodes = {};
      kids.forEach(n => { const hs = (info.hotspots || {})[n.addr]; nodes[n.addr] = { name: n.name || '未探索 · ' + n.addr.split('/').pop(), fog: !n.name, type: n.kind, pos: hs ? { x: hs[0], y: hs[1] } : null, child: (n.children || []).length ? n.addr : undefined, img: n.has_scene ? img.scene(n.addr) : undefined }; });
      const edges = (self.edges || []).filter(e => nodes[e.from] && nodes[e.to]).map((e, i) => ({ id: e.id || `${lv}#${i}`, a: e.from, b: e.to, d: e.distance != null ? String(e.distance) : '' }));
      const drawable = editable && (map.levels || {})[lv] !== undefined;
      levels[lv] = { title: lv === 'world' ? (self.name || '世界') : self.name, scale: lv === 'world' ? '世界' : scaleOf(self), parent: lv === 'world' ? undefined : (self.parent || 'world'),
        file: self.source || (lv === 'world' ? 'game/world/world_map.json' : `game/locations/${lv}/`), image: info.has_image ? img.map(lv) + (info.generated_at ? '&v=' + encodeURIComponent(info.generated_at) : '') : null, aspect: 1.5, frozen: !!info.has_image,
        stale: !!info.stale, fitNote: info.has_image ? `assets/maps/${lv}.json · ${info.backend || ''} ${info.stale ? '· stale' : ''}` : '', nodes, edges, ports: [], live: true,
        editable: drawable, canAdd: drawable && self.kind !== 'dungeon', job: (map.jobs || {})['map:' + lv] };
    }
    return levels;
  }
  window.LIVE_buildMap = () => loadEdit();
  // 世界 · 角色是编辑界面:编辑的就是选中的那个世界(10-06:「这个本来就是一个编辑界面,真正的游玩是在测试台里面」)。
  // 引擎只允许编辑「我的世界」,所以第一次编辑某个模板时在后台建一份工作副本(以后一直用它),界面上不出现这层。
  const COPIES = () => { try { return JSON.parse(localStorage.getItem('wl-edit-copies') || '{}'); } catch { return {}; } };
  const saveCopy = (tid, wid) => { try { const m = COPIES(); m[tid] = wid; localStorage.setItem('wl-edit-copies', JSON.stringify(m)); } catch { /* storage off */ } };
  L.wtpl = null;  // 世界 · 角色正在编辑的模板
  async function openWorld(tid) {
    if (!tid) return; setWorld(tid, { quiet: true }); L.wtpl = tid; L.opening = true; L.openFail = null; delete window.MAPW.edit; if (S.screen === 'duo') render();
    try {
      const cur = await V3.j(EDIT + '/tree').catch(() => null), want = COPIES()[tid];
      if (!(cur && want && cur.world_id === want)) {
        const r = want ? await V3.post('/api/v1/create/session', { world_id: want }).catch(() => null) : null;
        if (!r) { const t = L.templates.find(x => x.id === tid) || {}; const n = await V3.post('/api/v1/create/session', { template: tid, name: tplTitle(t) }); saveCopy(tid, n.world_id); }
      }
      await loadEdit(false);
    } catch (e) { L.openFail = { tid, msg: String(e.message || e) }; }   // 记下来,不自动重试(之前会一直重发)
    L.opening = false; if (S.screen === 'duo') render();
  }
  async function buildMapWorld() {
    if (!window.MAPW) return;
    if (!window.LIVE_DEMO) for (const k of Object.keys(window.MAPW)) if (k !== 'edit') delete window.MAPW[k];
    const tid = S.world || L.wtpl || L.bound || (L.templates[0] || {}).id;
    if (L.openFail && L.openFail.tid === tid) return;
    if (!L.edit || L.wtpl !== tid) return openWorld(tid);
    await loadEdit();
  }
  async function loadEdit(rerender = true) {
    const tree = await V3.j(EDIT + '/tree').catch(() => null);
    if (!tree) { delete window.MAPW.edit; L.edit = null; return; }
    const map = await V3.j(EDIT + '/map').catch(() => null); if (!map) return;
    L.edit = { world_id: tree.world_id, name: tree.world_name || tree.world_id };
    const v = Date.now();
    const levels = levelsFrom(map, { map: lv => V3.url(`${EDIT}/map/image?level=${encodeURIComponent(lv)}&t=${v}`), scene: a => V3.url(`${EDIT}/place-image?addr=${encodeURIComponent(a)}`) }, true);
    window.MAPW.edit = { title: L.edit.name, root: 'world', levels, editable: true };
    if (window.MAPM.world !== 'edit' || !levels[window.MAPM.level]) { window.MAPM.world = 'edit'; window.MAPM.level = levels.T001 ? 'T001' : 'world'; }
    const running = Object.entries(map.jobs || {}).filter(([, j]) => j.state === 'running');
    clearTimeout(L.jobTimer); if (running.length) L.jobTimer = setTimeout(() => loadEdit(true), 2500);
    if (rerender && S.screen === 'duo' && !(window.MAPM && window.MAPM.dragging)) render();
  }
  window.LIVE_openWorld = openWorld;
  // 模板换了一份新世界(live2「＋ 新建世界」):旧的编辑副本作废,按新世界重建一份
  window.LIVE_reopenWorld = tid => { try { const m = COPIES(); delete m[tid]; localStorage.setItem('wl-edit-copies', JSON.stringify(m)); } catch { /* storage off */ }
    L.edit = null; L.wtpl = null; L.openFail = null; delete window.MAPW.edit; return openWorld(tid); };
  // 地图编辑器的写回(map.js 在可编辑的层上调这些)
  window.MAPHOOK = {
    async move(level, addr, x, y) { await fetch(V3.url(EDIT + '/map/node'), { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level, addr, x, y }) }); await loadEdit(); },
    async add(level, name, x, y, link) { const r = await fetch(V3.url(EDIT + '/map/node'), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level, name, x, y, link_to: link || '' }) }); const d = await r.json().catch(() => ({})); await loadEdit(); return d; },
    async road(level, a, b, opt) {   // 建路 / 删路 / 改路程(1.0 创作写回):POST map/edge
      const r = await fetch(V3.url(EDIT + '/map/edge'), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level, a, b, ...(opt || {}) }) });
      const d = await r.json().catch(() => ({})); if (!r.ok) L.err = '路没写成:' + (d.error || r.status);
      await loadEdit(); return d;
    },
    async generate(level) { await V3.post(EDIT + '/map/generate', { level }).catch(e => { L.err = '生成失败:' + e.message; }); await loadEdit(); },
    get edit() { return L.edit; }, get opening() { return !!L.opening; }, get openFail() { return L.openFail; }, get wtpl() { return L.wtpl; },
  };

  // 顶栏右侧:这一页读的是什么(10-17:以前编排 / Template / 前端 / 世界·角色写着过时的「演示数据 · 等引擎 …」)
  const what = () => ({
    orch: window.SOULORCH && window.SOULORCH.mode === 'soul' ? '角色图读自引擎 · 写回后小手机下一句就按它回' : '编排图读自引擎 · 写回后下一局生效',
    tpl: '真引擎 · 模板库', fe: '真引擎 · 前端文件夹 · 预览连本机引擎',
    duo: L.edit && !L.opening ? `真引擎 · 编辑副本${L.edit.name ? ' ' + L.edit.name : ''}` : L.openFail ? '这个世界没打开' : '正在打开世界……',
  })[S.screen];
  // Hub(/hub.html)的入口:只在本机引擎(浏览器版没有这一页)。小手机不放顶栏(10-24:本地顶栏不要,小手机在测试台右栏和线上网页里)
  //   (这次构建有哪几页:build.mjs 写进 window.WL_PAGES)
  const NAVX = [['hub', '/hub.html', 'Hub ↗', 'Hub:世界 · 角色 · 我的']];
  const navLinks = () => {
    const n = $('#nav'), pages = window.WL_PAGES || { hub: true }; if (!n || !L.ok || V3.base !== '') return;
    NAVX.forEach(([k, u, l, tt]) => { if (pages[k] && !n.querySelector(`[data-navx=${k}]`)) n.insertAdjacentHTML('beforeend', `<a class="navx" href="${u}" target="_blank" rel="noopener" data-navx="${k}" title="${tt}">${l}</a>`); });
  };
  const _render = render;
  render = function () {
    if (L.ok) { initWorld(); syncWorld(); }
    if (S.screen === 'duo' && L.ok && window.MAPW && !window.MAPW.edit && !L.opening && !L.openFail) buildMapWorld();
    _render();
    const t = L.templates.find(x => x.id === L.bound), w = what();
    $('#ctx').innerHTML = !L.ok ? `<span class="chip" ${L.err ? `title="${esc(L.err)}" data-err="${esc(L.err)}"` : ''}>${L.err ? (/^\d{3} \//.test(L.err) || /fetch|network/i.test(L.err) ? '连不上引擎' : esc(L.err)) : esc(waitText())}</span>`
      : w ? `<span class="chip blue">${esc(w)}</span>` : `<span class="chip" title="引擎绑着的这一局">${esc(t ? '这一局 · ' + tplTitle(t) : '未开局')}</span><span class="chip sage">真引擎 · neonrp</span>`;
    worldSel(); testBanner(); navLinks();
  };
  // 10-17「前端没法选用哪个世界」:一个全局的「当前世界」S.world(模板 id)—— 顶栏一个选择器,各页都跟着它:
  //   编排 = 那个模板的图 · 世界·角色 = 那个模板的编辑副本 · Template = 那个模板 · 前端 = 那个模板的契约 ·
  //   测试台 = 这一局(引擎绑着的那局,L.bound);和 S.world 不一样时先问一声再开(开局要十几秒),不自动开
  // 别的模块:读 S.world / window.WL_WORLD(),听 window 上的 'wl:world' 事件({detail: {id}});改用 window.WL_setWorld(id)
  const WKEY = 'wl-world';
  const known = id => !!id && L.templates.some(t => t.id === id);
  window.WL_WORLD = () => S.world || null;
  function setWorld(id, { quiet } = {}) {
    if (!known(id)) return;
    if (id === S.world) { S.worldBy = 'chosen'; return; }
    S.world = id; S.worldBy = 'chosen';
    try { localStorage.setItem(WKEY, id); } catch { /* storage off */ }
    window.dispatchEvent(new CustomEvent('wl:world', { detail: { id } }));
    if (!quiet) render();
  }
  window.WL_setWorld = setWorld;
  function initWorld() {
    if (S.world && S.worldBy !== 'fallback') return;   // 只有「没得选才落到第一个」的那种,之后这一局认出来了再换
    let saved = null; try { saved = localStorage.getItem(WKEY); } catch { /* storage off */ }
    const asked = /[?&](tpl|save|world)=/.test(location.search);   // 地址里点名了哪一局:当前世界就是它;否则接着上次选的
    // 第一次打开:这一局的世界;记住的世界还在就接着用它(删掉了就不认,退回这一局的 → 列表第一个)
    const pick = (asked ? [L.bound, saved] : [saved, L.bound]).find(known);
    S.world = pick || (L.templates[0] || {}).id || null;
    S.worldBy = pick ? 'chosen' : 'fallback';
  }
  // 进到一页时把这一页对齐到 S.world(各页自己的选择器改了也回写 S.world,见下面几处)
  function syncWorld() {
    const id = S.world; if (!L.ok || !known(id)) return;
    if (S.screen === 'orch' && !(window.SOULORCH && window.SOULORCH.mode === 'soul')) {
      const g = G(); if (g && g.tpl === id) return;
      if (id === L.bound && !L.graphPicked) return;   // 当前世界就是这一局:等引擎生效图(live2.loadGraph 会选它),不另取模板图
      if (id === L.bound && GRAPHS.live) { S.graph = 'live'; S.node = GRAPHS.live.start; S.edge = null; S.cur = null; S.chat = null; S.stack = []; return; }
      const k = 'tpl:' + id, t = L.templates.find(x => x.id === id) || {};
      if (!GRAPHS[k]) GRAPHS[k] = { title: `模板 · ${tplTitle(t)}`, start: 'plan', nodes: {}, edges: [], pending: true, tpl: id };
      if (GRAPHS[k].pending) delete GRAPHS[k].err;   // 上次没取到:再来就再取
      S.graph = k; S.node = GRAPHS[k].start; S.edge = null; S.cur = null; S.chat = null; S.stack = []; S.layer = 'graph';
      L.graphPicked = true;   // 编排图第一次读回来时不再跳回「这一局」(live2.loadGraph)
    }
    if (S.screen === 'duo' && L.wtpl !== id && !L.opening) openWorld(id);
    if (S.screen === 'tpl' && window.TPL && window.TPL.id && window.TPL.id !== id && window.TPL_load) window.TPL_load(id);
  }
  const SEL_ON = ['orch', 'duo', 'tpl', 'test', 'fe'];
  function worldSel() {
    if (!L.ok || !L.templates.length || !SEL_ON.includes(S.screen)) return;
    const cur = S.world;   // 角色面也显示:角色在「当前世界」里的那一拍(in_world)按它读
    $('#ctx').insertAdjacentHTML('afterbegin', `<select class="btn" id="wlWorld" aria-label="当前世界" title="当前世界:编排 · 世界·角色 · Template · 测试台 · 前端都跟着它" style="text-transform:none;letter-spacing:0;max-width:160px;overflow:hidden;text-overflow:ellipsis">${known(cur) ? '' : '<option value="" selected>选一个世界</option>'}${L.templates.map(t => `<option value="${esc(t.id)}" ${t.id === cur ? 'selected' : ''}>${esc(tplTitle(t))}</option>`).join('')}</select>`);
  }
  // 测试台:当前世界不是这一局的世界 → 一条横幅,点了(确认后)才开那一局
  function testBanner() {
    if (S.screen !== 'test' || !L.ok || L.binding || !known(S.world) || S.world === L.bound) return;
    const el = $('#s-test .mk-main') || $('#s-test .mk'); if (!el || $('#wlTestBar')) return;
    const w = L.templates.find(x => x.id === S.world) || {}, b = L.templates.find(x => x.id === L.bound);
    el.insertAdjacentHTML('afterbegin', `<div class="mbanner ro" id="wlTestBar" style="grid-column:1/-1;order:-1"><b>当前世界是「${esc(tplTitle(w))}」</b><span>测试台还开着${b ? `「${esc(tplTitle(b))}」` : '别的'}这一局</span>
      <div class="r"><button class="btn p" data-wlopen>开「${esc(tplTitle(w))}」的一局</button>${b ? `<button class="btn" data-wlback>回到这一局的世界</button>` : ''}</div></div>`);
  }
  function openTest(id) {
    const t = L.templates.find(x => x.id === id) || {};
    if (!confirm(`开一局「${tplTitle(t)}」?\n现在这一局留在存档里,之后还能继续。`)) return false;
    L.tpl = id; ensureBound(); return true;
  }
  document.addEventListener('change', e => {
    if (e.target.id !== 'wlWorld' || !e.target.value) return;
    const id = e.target.value, prev = S.world;
    if (S.screen === 'test' && id !== L.bound && !openTest(id)) { e.target.value = prev || ''; return; }   // 测试台:先问,不开就不换
    setWorld(id);
  });
  document.addEventListener('click', e => {
    if (e.target.closest('[data-wlopen]')) { openTest(S.world); return; }
    if (e.target.closest('[data-wlback]') && L.bound) setWorld(L.bound);
  });
  window.LIVE_DEMO = new URLSearchParams(location.search).has('demo');
  if (!window.LIVE_DEMO && window.MAPW) for (const k of Object.keys(window.MAPW)) delete window.MAPW[k];  // 演示世界只在 ?demo=1 时出现:真实地图读回来之前显示「正在读」
  render();
  boot();
})();
