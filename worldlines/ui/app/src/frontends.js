/* 前端台做实(10-17):不再是写死的 FE_FILES / 假对话 / 假试玩。一排工作台,每个 = 一个真的重前端文件夹:
     Godot 客户端(examples/clients/godot)· TS 重前端(标准前端 ui/player → /player.html · 协议示例 examples/clients/ts,Vite 构建出 dist/)·
     小手机(ui/player/chat → /chat.html)· 这个世界自己的前端(模板里 frontends/<name>/ + frontend.json,「+ 新建」或从内置的派生)
   每个工作台四页:试玩(真预览)· 事件流(fe.js 那套,真 /engine/beats + /events)· 文件(真文件树,引擎 /api/v1/local/frontends 读)·
   契约(contract?fmt=ts|gd|json,能写进这个前端);左栏 = 前端 agent(引擎 …/agent:只改这个前端文件夹;内置的只读 → 先派生)。全部跟着当前世界 WL_WORLD(),听 'wl:world'。
   10-19 文件工作台:内置的只读 →「复制一份到这个世界」(…/fork)· 文件页先改草稿、明确「保存」、没存的看得见、离开页面提醒 ·
   agent 直接写盘、文件上标「已写入」· 导出 zip(内置的也能)· 导入 zip(引擎先查 frontend.json,不合格列原因不写盘)。
   每个工作台两种模式(10-19):试玩 = 真预览接本机引擎;编辑 = 文件 · 事件流 · 契约(+ 挂进来的页签)。内置的在编辑模式只读,先复制。
   页签由 TABS 一张表声明:FXDESK.addTab({id, label, mode: 'edit', editable: true, own?: true, when(desk), render(desk)})
   (own: true = 这一页能不能写不看前端文件夹,内置台上也不出「只读 · 先复制」那条)
   (小手机的「编排」之后挂进编辑模式,可改:render 拿到 desk.writable 决定能不能写)。
   引擎接口:src/neonrp/webui/frontend_routes.py。iframe 一挪就重载,所以和 stdfe.js 一样只建一次、挂在 body 上、每次重画后盖到占位格上。 */
(() => {
  const P = '/api/v1/local/frontends';
  const L = window.LIVE;
  const F = window.FXDESK = { tsSub: 'player', havePlayer: null, build: null, key: null, list: null, loadedFor: null, sel: 'builtin.godot', view: 'play', tree: {}, file: {}, contract: {}, cfmt: 'ts',
    godot: null, smoke: null, busy: {}, souls: null, soul: {}, agent: {}, msg: '', nf: { kind: 'web-ts', name: '', title: '' }, edit: {}, wrote: {}, fork: null, imp: null, mode: 'play', editView: 'files' };
  const enc = encodeURIComponent;
  const world = () => (window.WL_WORLD && window.WL_WORLD()) || L.bound || '';   // 当前世界(没选过 = 这一局的)
  const wkey = () => world() || '_';
  const tplT = id => { const t = (L.templates || []).find(x => x.id === id); return t ? ((t.card && t.card.title) || t.id) : (id || ''); };
  const api = (p, opt) => V3.j(P + p, opt);
  const post = (p, body) => V3.post(P + p, body);

  // 工作台:内置的(引擎列出来的)按这个顺序;TS 两个子项(标准前端 · 协议示例)合成一个台
  const DESKS = [['builtin.godot', 'Godot'], ['ts', T('TS 重前端')], ['builtin.chat', T('小手机')]];
  const TSSUB = [['player', 'builtin.player', T('标准前端')], ['ts', 'builtin.ts', T('协议示例')]];
  const fidOf = sel => sel === 'ts' ? (TSSUB.find(x => x[0] === F.tsSub) || TSSUB[0])[1] : sel;   // 工作台 → 真正的前端文件夹
  const row = id => (F.list && F.list.frontends || []).find(x => x.id === id) || null;
  const kindOf = id => (row(id) || {}).kind || (id === 'builtin.godot' ? 'godot' : id === 'builtin.chat' ? 'chat' : 'web-ts');

  /* ---------- 读 ---------- */
  async function loadList(force) {
    const k = wkey(); if (!force && F.loadedFor === k) return; F.loadedFor = k;
    try { F.list = await api('/' + enc(k)); } catch (e) { F.list = { error: String(e.message || e), frontends: [] }; }
    if (!row(fidOf(F.sel)) && !DESKS.some(d => d[0] === F.sel) && F.sel !== 'new') F.sel = 'builtin.godot';
    rer();
  }
  async function loadTree(id, force) {
    const k = wkey() + '|' + id; if (!force && F.tree[k]) return;
    F.tree[k] = { loading: true, files: [] };
    try { F.tree[k] = await api(`/${enc(wkey())}/${enc(id)}/tree`); } catch (e) { F.tree[k] = { error: e.status === 404 ? T('这个安装没带内置前端的源码(只有源码仓库才有)') : String(e.message || e), files: [] }; }
    rer();
  }
  async function loadFile(id, path) {
    const k = wkey() + '|' + id + '|' + path; if (F.file[k] && !F.file[k].error) return;
    F.file[k] = { loading: true };
    try { F.file[k] = await api(`/${enc(wkey())}/${enc(id)}/file?path=${enc(path)}`); } catch (e) { F.file[k] = { error: e.status === 400 ? T('二进制或太大的文件,不在这里显示') : String(e.message || e) }; }
    rer();
  }
  async function loadContract(fmt) {
    const w = world(), k = w + '|' + fmt; if (!w || F.contract[k]) return;
    F.contract[k] = { loading: true };
    const u = V3.url(`/api/v1/local/templates/${enc(w)}/contract${fmt === 'json' ? '' : '?fmt=' + fmt}`);
    try { const r = await fetch(u, { credentials: 'include' }); if (!r.ok) throw new Error(String(r.status)); const t = await r.text(); F.contract[k] = { text: fmt === 'json' ? JSON.stringify(JSON.parse(t), null, 2) : t }; }
    catch (e) { F.contract[k] = { error: T('契约没生成出来({e}):去 Template 页看 lint', { e: e.message }) }; }
    rer();
  }
  async function loadGodot(force) {
    if (F.godot && !force) return;
    try { F.godot = await api('/_/godot'); } catch { F.godot = { bin: null, running: [] }; }
    rer();
  }
  async function loadSouls(force) {
    if (F.souls && !force) return;
    try { F.souls = (await V3.j('/api/v1/chat/souls?lang=zh')).souls || []; } catch (e) { F.souls = []; F.soulsErr = e.status === 404 ? T('这个引擎没有小手机接口') : String(e.message || e); }
    rer();
  }
  function probePlayer() {   // 开源构建没有 /player.html(标准前端不开源)
    if (F.havePlayer !== null) return; F.havePlayer = false;
    fetch(V3.url('/player.html'), { credentials: 'include' }).then(r => { F.havePlayer = r.ok; r.body && r.body.cancel(); rer(); }).catch(() => { /* none */ });
  }
  const rer = () => { if (S.screen === 'fe') renderFe(); };

  /* ---------- 一直挂着的 iframe ---------- */
  const FR = { el: null, src: '' };
  function frame(src) {
    if (!FR.el) { const f = FR.el = document.createElement('iframe'); f.id = 'fxframe'; f.title = T('前端预览'); f.style.cssText = 'position:fixed;z-index:3;border:0;border-radius:16px;background:#07080c;display:none;box-shadow:0 0 0 1px var(--line2)'; document.body.appendChild(f); }
    if (FR.src !== src) { FR.src = src; FR.el.src = src; }
    return FR.el;
  }
  function place() {
    const slot = S.screen === 'fe' ? [...document.querySelectorAll('.fxslot')].find(x => x.getClientRects().length) : null;
    if (!slot) { if (FR.el) FR.el.style.display = 'none'; return; }
    const f = frame(slot.dataset.src), r = slot.getBoundingClientRect();
    Object.assign(f.style, r.width && r.height ? { display: 'block', left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' } : { display: 'none' });
  }
  window.addEventListener('resize', place);
  document.addEventListener('scroll', place, true);
  const slot = (src, style = '') => `<div class="fxslot" data-src="${esc(src)}" style="${style}"></div>`;

  /* ---------- 局对不上 ---------- */
  // 测试台 / 标准前端 / Godot 连的都是引擎上开着的那一局;它不是当前世界的就明说,开局要点按钮(不偷偷 ?tpl= 换局)
  function runBar() {
    const w = world(), b = L.bound;
    if (!w) return `<div class="mbanner ro fxbar"><b>${T('还没选世界')}</b><span>${T('顶栏选一个')}</span></div>`;
    if (b === w) return '';
    return `<div class="mbanner ro fxbar"><b>${b ? T('引擎上开着的是「{w}」', { w: esc(tplT(b)) }) : T('引擎上开着的是……没有一局')}</b><span>${T('预览 / 冒烟连的是开着的那一局,不是当前世界「{w}」', { w: esc(tplT(w)) })}</span><div class="r"><button class="btn p" data-wlopen>${T('开「{w}」的一局', { w: esc(tplT(w)) })}</button></div></div>`;
  }

  /* ---------- 试玩 ---------- */
  function playGodot(id) {
    loadGodot(); const g = F.godot, r = row(id) || {}, mine = (g && g.running || []);
    const sm = F.smoke && F.smoke.id === id ? F.smoke : null;
    const cmd = `cd ${r.dir || 'worldlines/examples/clients/godot'}\nWL_HOST=${location.origin.replace('localhost', '127.0.0.1')} WL_TOKEN=<${T('令牌')}> godot --path .                        # ${T('进标题页 → 进入')}\nWL_HOST=… WL_TOKEN=<${T('令牌')}> godot --headless --path . -s tests/smoke.gd   # ${T('无界面走一句')}`;
    return `<div class="fxpad scroll">${runBar()}
      <div class="fxgrid">
        <div class="glass deep fxcard"><span class="tag">${T('本机的 Godot')}</span>
          ${!g ? `<div class="sub">${T('找 Godot……')}</div>` : g.bin ? `<div class="row" style="margin-top:8px"><span class="dot ok"></span><span class="mono" style="font-size:12px">${esc(g.version || 'Godot')}</span></div><div class="mono fxpath">${esc(g.bin)}</div>`
            : `<div class="row" style="margin-top:8px"><span class="dot bad"></span>${T('没找到 Godot')}</div><div class="sub" style="font-size:12.5px">${T('装 Godot 4.5,或者起引擎前设 GODOT=/path/to/godot')}</div>`}
          <div class="row" style="margin-top:12px;gap:8px;flex-wrap:wrap"><button class="btn p" data-fxlaunch ${g && g.bin && r.have_source !== false ? '' : 'disabled'}>${T('启动 Godot 连这个引擎')}</button>
            ${mine.map(p => `<span class="chip sage">${T('运行中')} · PID ${p.pid}</span><button class="chip" data-fxstop="${p.pid}">${T('停止')}</button>`).join('')}</div>
          <div class="sub" style="font-size:12px">${T('开一个 Godot 窗口,地址 / 令牌 / 世界已经填好(WL_HOST · WL_TOKEN · WL_WORLD);只关这里起的那个进程。')}</div></div>
        <div class="glass deep fxcard"><span class="tag">${T('无界面冒烟')} · tests/smoke.gd</span>
          <div class="sub" style="font-size:12.5px">${T('Godot 的客户端节点连上本机引擎,发一句、收完流式叙事和拍事件。')}<b style="color:var(--crit)">${T('会在引擎上开着的这一局里真走一回合')}</b>${T('(花一次模型调用)。')}</div>
          <div class="row" style="margin-top:10px;gap:8px"><input class="cell" id="fxline" value="${esc(F.smokeLine || '看看四周')}" style="flex:1"><button class="btn p" data-fxsmoke ${g && g.bin && L.bound && !F.busy.smoke ? '' : 'disabled'}>${F.busy.smoke ? T('跑着……') : T('跑一句(真回合)')}</button></div>
          ${!L.bound ? `<div class="sub" style="font-size:12px">${T('引擎上还没开局,先开一局')}</div>` : ''}
          ${sm ? `<div class="fxres ${sm.ok ? 'ok' : 'bad'}"><div class="row"><span class="dot ${sm.ok ? 'ok' : 'bad'}"></span><b>${sm.ok ? T('通过') : T('没通过')}</b><span class="tag" style="margin-left:auto">${T('退出码')} ${esc(sm.code)}</span></div>
            ${[sm.connected, sm.turn, sm.events].filter(Boolean).map(x => `<div class="mono" style="font-size:12px">${esc(x)}</div>`).join('')}<pre class="code fxout">${esc(sm.error || String(sm.output || '').split('\n').filter(x => ![sm.connected, sm.turn, sm.events].includes(x)).join('\n'))}</pre></div>` : ''}</div>
      </div>
      <div class="glass deep fxcard" style="margin-top:14px"><span class="tag">${T('自己在终端里跑')}</span><pre class="code fxout">${esc(cmd)}</pre>
        <div class="row" style="gap:8px"><button class="chip" data-fxtoken>${T('复制令牌')}</button><span class="sub" style="font-size:12px;margin:0">${T('令牌 = 本机引擎的 /rpc 凭证,只在本机给')}</span></div></div></div>`;
  }
  function playChat() {
    loadSouls(); const w = world(), all = F.souls || [], mine = all.filter(s => s.tpl === w);
    const sid = (F.soul[w] && mine.some(s => s.sid === F.soul[w])) ? F.soul[w] : (mine[0] || {}).sid;
    if (!F.souls) return `<div class="fxpad"><div class="sub">${T('读这个世界能聊的角色……')}</div></div>`;
    if (!mine.length) {
      const others = [...new Set(all.map(s => s.tpl).filter(t => t && !t.startsWith('lib:') && (L.templates || []).some(x => x.id === t)))];
      return `<div class="fxpad"><div class="glass deep fxcard"><span class="tag">${T('小手机')} · ${esc(tplT(w))}</span><div class="sub">${esc(F.soulsErr || T('「{w}」里没有能单独聊的角色(角色要 standalone,或者在游戏里获得过)。', { w: tplT(w) }))}</div>
        ${others.length ? `<div class="row" style="margin-top:10px;gap:6px;flex-wrap:wrap"><span class="tag">${T('有角色能聊的世界')}</span>${others.map(t => `<button class="chip" data-fxworld="${esc(t)}">${esc(tplT(t))}</button>`).join('')}</div>` : ''}</div></div>`;
    }
    const src = V3.url(`/chat.html?tpl=${enc(w)}&sid=${enc(sid)}&lang=zh&back=${enc('about:blank')}`);
    return `<div class="fxchat"><div class="fxsouls glass deep"><span class="tag">${esc(tplT(w))} · ${T('能聊的')}</span>${mine.map(s => `<button class="fxsoul ${s.sid === sid ? 'on' : ''}" data-fxsoul="${esc(s.sid)}"><img src="${esc(V3.url(s.avatar_url || ''))}" alt="" onerror="this.style.visibility='hidden'"><span><b>${esc(s.name)}</b><small>${s.obtained ? T('已获得 · 完整记忆') : s.standalone ? T('可以直接聊 · 试聊') : ''}</small></span></button>`).join('')}
      <div class="sub" style="font-size:12px;margin-top:10px">${T('右边就是 /chat.html(玩家在 Hub / iOS 上的那个小手机),连本机引擎:发一句是真的一次模型调用。')}</div></div>
      <div class="fxphone">${slot(src, 'position:absolute;inset:0')}</div></div>`;
  }
  function playPlayer() {
    probePlayer();
    if (F.havePlayer === false) return `<div class="fxpad"><div class="glass deep fxcard"><span class="tag">${T('标准前端')}</span><div class="sub">${T('这次构建没有 /player.html(开源版不带标准前端;源码仓库里 node worldlines/ui/app/build.mjs 会一起构建)。')}</div></div></div>`;
    return `<div class="fxcol">${runBar()}<div class="fxnote"><span class="tag">/player.html</span><span>${T('Hub / iOS 玩家看到的那个重前端(worldlines/ui/player),接引擎上开着的这一局;在这里说一句 = 真回合')}</span></div>
      <div class="fxstage">${F.havePlayer ? slot(V3.url('/player.html'), 'position:absolute;inset:0') : `<div class="sub" style="padding:18px">${T('找标准前端……')}</div>`}</div></div>`;
  }
  function playTs() {
    const r = row('builtin.ts') || {}, b = F.build;
    const cmds = `cd ${r.dir || 'worldlines/examples/clients/ts'}\nnpm install && npx vite build --base ./        # ${T('构建 → dist/,这里的预览就是它')}\nWL_HOST=${location.origin.replace('localhost', '127.0.0.1')} npm run dev     # ${T('或者开 Vite 开发服务器 → http://localhost:5180')}`;
    const head = `<div class="fxnote"><span class="tag">${T('协议示例')}</span><span>${T('只认联网协议(JSON-RPC /rpc + SSE /rpc/events)的 TS 小游戏;进入时要令牌')}</span>
      <button class="chip" data-fxtoken>${T('复制令牌')}</button><button class="chip" data-fxbuild ${F.busy.build ? 'disabled' : ''}>${F.busy.build ? T('构建中……') : r.site_built ? T('重新构建') : T('构建')}</button></div>`;
    const res = b ? `<div class="fxres ${b.ok ? 'ok' : 'bad'}" style="margin:0 0 10px"><div class="row"><span class="dot ${b.ok ? 'ok' : 'bad'}"></span><b>${b.ok ? T('构建好了') : T('没构建成')}</b><span class="tag" style="margin-left:auto">${T('退出码')} ${esc(b.code)}</span></div><pre class="code fxout">${esc(b.error || b.output || '')}</pre></div>` : '';
    if (r.have_source === false) return `<div class="fxpad"><div class="sub">${T('这个安装没带协议示例的源码')}</div></div>`;
    if (!r.site_built) return `<div class="fxpad">${runBar()}${head}${res}<div class="glass deep fxcard" style="margin-top:12px"><span class="tag">${T('还没构建')}</span><div class="sub">${T('点「构建」(第一次会 npm install),或者在终端里:')}</div><pre class="code fxout">${esc(cmds)}</pre></div></div>`;
    return `<div class="fxcol">${runBar()}${head}${res}<div class="fxstage">${slot(V3.url(`${P}/${enc(wkey())}/builtin.ts/site/index.html?world=${enc(world())}`), 'position:absolute;inset:0')}</div></div>`;
  }
  // 这个世界自己的网页 / 小手机前端:引擎把文件夹当站点服务(同源,直接连本机引擎);改了文件 → 重新载入
  function playOwn(id) {
    const r = row(id) || {}, q = r.kind === 'chat' ? `?tpl=${enc(world())}` : '';
    const src = V3.url(`${P}/${enc(wkey())}/${enc(id)}/site/${String(r.entry || 'index.html').split('/').map(enc).join('/')}${q}`) + (F.rev ? (q ? '&' : '?') + 'r=' + F.rev : '');
    return `<div class="fxcol">${r.kind === 'chat' ? '' : runBar()}<div class="fxnote"><span class="tag">${esc(r.dir)}/${esc(r.entry || '')}</span><span>${r.kind === 'chat' ? T('这个世界自己的小手机,引擎直接服务这个文件夹') : T('这个世界自己的网页前端,引擎直接服务这个文件夹')}</span><button class="chip" data-fxreload>${T('重新载入')}</button></div>
      <div class="fxstage">${slot(src, 'position:absolute;inset:0')}</div></div>`;
  }
  // 新建:模板里 frontends/<name>/ + frontend.json;内置模板不可写 → 先去 Template「复制成我的」
  function newDesk() {
    const w = world(), n = F.nf, ok = F.list && F.list.writable;
    if (!w) return `<div class="fxpad"><div class="sub">${T('先在顶栏选一个世界')}</div></div>`;
    const K = [['web-ts', T('网页(TS / JS)'), T('无打包的 index.html + main.js + 这个世界的 contract.ts,改完直接预览')], ['godot', 'Godot', T('拷一份 Godot 客户端(连接节点 · 场景 · 冒烟测试)')], ['chat', T('小手机'), T('一页跟这个世界的角色单独聊天')]];
    return `<div class="fxpad"><div class="glass deep fxcard" style="max-width:640px"><span class="tag">${T('新建重前端')} · ${esc(tplT(w))}</span>
      ${ok ? '' : `<div class="sub">${T('「{w}」是内置的,不能直接往里加前端:先复制一份成你自己的世界,再在那份里建。', { w: esc(tplT(w)) })}</div><div class="row" style="margin-top:10px"><button class="btn p" data-fxfork>${T('去 Template 复制成我的')}</button></div>`}
      <div class="fxkinds">${K.map(([k, l, d]) => `<button class="fxkind ${n.kind === k ? 'on' : ''}" data-fxkind="${k}" ${ok ? '' : 'disabled'}><b>${l}</b><small>${d}</small></button>`).join('')}</div>
      <div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap"><input class="cell" id="fxnname" placeholder="${T('文件夹名,例 my-web')}" value="${esc(n.name)}" style="max-width:200px" ${ok ? '' : 'disabled'}>
        <input class="cell" id="fxntitle" placeholder="${T('名字,例 灰橡宅 · 竖屏版')}" value="${esc(n.title)}" style="flex:1;min-width:180px" ${ok ? '' : 'disabled'}><button class="btn p" data-fxcreate ${ok ? '' : 'disabled'}>${T('建')}</button></div>
      ${F.msg ? `<div class="sub" style="color:var(--fail)">${esc(F.msg)}</div>` : ''}
      <div class="fximp"><span class="tag">${T('或者导入一个导出的前端(zip)')}</span><div class="row" style="gap:8px;margin-top:8px;flex-wrap:wrap">
        <input class="cell" id="fximpname" placeholder="${T('导入成的文件夹名')}" value="${esc(F.impName || '')}" style="max-width:200px" ${ok ? '' : 'disabled'}><label class="btn ${ok ? '' : 'disabled'}">${T('选 zip 导入…')}<input type="file" accept=".zip" id="fximpfile" hidden ${ok ? '' : 'disabled'}></label></div>
        ${F.imp ? (F.imp.ok ? `<div class="sub" style="color:var(--pass)">${T('导入好了:')}frontends/${esc(F.imp.id)}/</div>` : `<div class="sub" style="color:var(--fail)">${T('没导入(什么都没写):')}${esc(F.imp.error || '')}</div>${(F.imp.problems || []).map(p => `<div class="mono fxprob">${esc(p.code)} · ${esc(p.message)}</div>`).join('')}`) : ''}</div>
      <div class="sub" style="font-size:12px">${T('放在 <span class="mono">frontends/&lt;文件夹名&gt;/</span>,带一份 frontend.json(worldlines.frontend/1:类型 · 入口 · 订阅的事件 · targets)。模板 lint 认它;现在只在本机生效,Hub / iOS 以后按 targets 选用;不进局、不进导出包。')}</div></div></div>`;
  }
  const PLAY = { godot: playGodot, chat: playChat, 'builtin.player': playPlayer, 'builtin.ts': playTs };

  /* ---------- 文件:草稿 / 保存 ---------- */
  // 草稿 = F.edit[世界|前端|路径];和磁盘上读来的 F.file 不同 = 没保存
  const isDirty = key => F.edit[key] !== undefined && !(F.file[key] && F.file[key].content === F.edit[key]);
  const dirtyKeys = prefix => Object.keys(F.edit).filter(x => (!prefix || x.startsWith(prefix + '|')) && isDirty(x));
  window.addEventListener('beforeunload', e => { if (dirtyKeys().length) { e.preventDefault(); e.returnValue = ''; } });   // 离开页面:还有没保存的就问一声
  function files(id) {
    const k = wkey() + '|' + id; loadTree(id); const tr = F.tree[k] || { loading: true, files: [] };
    if (tr.error) return `<div class="fxpad"><div class="sub">${esc(tr.error)}</div></div>`;
    const fs = tr.files || [], sel = F.fsel && F.fsel.id === id && fs.some(f => f.path === F.fsel.path) ? F.fsel.path : (fs.find(f => f.path === (row(id) || {}).entry) || fs.find(f => /README|\.gd$|\.js$|\.html$/.test(f.path)) || fs[0] || {}).path;
    if (sel) loadFile(id, sel);
    const fc = sel ? F.file[k + '|' + sel] || { loading: true } : null;
    const wrote = F.wrote[k] || new Set(), dirtyOf = p => isDirty(k + '|' + p);
    const tree = fs.map(f => { const dep = f.path.split('/').length - 1; return `<span class="f ${f.path === sel ? 'on' : ''}" data-fxf="${esc(f.path)}" style="padding-left:${6 + dep * 12}px" title="${esc(f.path)} · ${f.size} B">${dirtyOf(f.path) ? `<b class="fxdot" title="${T('没保存')}">●</b> ` : ''}${esc(f.path.split('/').pop())}${wrote.has(f.path) ? ` <i class="fxwrote">${T('已写入')}</i>` : ''}${dep ? `<i class="fxdir">${esc(f.path.split('/').slice(0, -1).join('/'))}</i>` : ''}</span>`; }).join('');
    const ek = k + '|' + sel, draft = F.edit[ek], dirty = isDirty(ek);
    const pane = !fc ? '' : fc.loading ? `<pre class="code">${T('读……')}</pre>` : fc.error ? `<pre class="code">${esc(fc.error)}</pre>`
      : tr.writable ? `<div class="fxed"><div class="fxedh"><span class="mono">${esc(sel)}</span><span class="fxstate">${dirty ? `<span class="chip rust">${T('草稿 · 没保存')}</span>` : `<span class="chip sage">${T('已保存')}</span>`}</span>${wrote.has(sel) ? `<span class="chip blue">${T('agent 已写入')}${dirty ? ' · ' + T('你的草稿还没存') : ''}</span>` : ''}
          <button class="chip" data-fxdiscard ${dirty ? '' : 'disabled'}>${T('放弃改动')}</button><button class="btn p" data-fxsave ${dirty ? '' : 'disabled'}>${T('保存')}</button></div><textarea class="code" id="fxedit" spellcheck="false">${esc(draft !== undefined ? draft : fc.content)}</textarea></div>`
      : `<pre class="code">${esc(fc.content)}</pre>`;
    const nd = dirtyKeys(k).length;
    return `<div class="fsv"><div class="tree"><div class="tag" style="margin-bottom:6px">${esc((row(id) || {}).dir || '')}/ · ${T('{n} 个文件', { n: fs.length })}${tr.writable ? '' : ' · ' + T('只读')}${nd ? ` · <span style="color:var(--rust)">${T('{n} 个没保存', { n: nd })}</span>` : ''}</div>${tr.loading ? `<div class="sub">${T('读……')}</div>` : tree}</div>${pane}</div>`;
  }

  /* ---------- 契约 ---------- */
  function contract(id) {
    const fmt = F.cfmt; loadContract(fmt); const c = F.contract[world() + '|' + fmt] || { loading: true };
    return `<div class="fxpad" style="display:flex;flex-direction:column;gap:10px"><div class="row" style="gap:8px"><div class="seg">${[['ts', 'TypeScript'], ['gd', 'GDScript'], ['json', 'JSON']].map(([k, l]) => `<button class="${fmt === k ? 'on' : ''}" data-fxcf="${k}">${l}</button>`).join('')}</div>
      ${(row(id) || {}).writable && fmt !== 'json' ? `<button class="chip" data-fxcwrite>${T('写进这个前端')} · ${fmt === 'gd' ? 'addons/worldlines/contract.gd' : 'contract.ts'}</button>` : ''}
      <span class="sub" style="margin:0;font-size:12.5px">${T('这个世界({w})的契约:变量 · 类 · op · 拍事件 · 视图 · 素材槽位;', { w: esc(tplT(world())) })}GET /api/v1/local/templates/${esc(world())}/contract${fmt === 'json' ? '' : '?fmt=' + fmt}</span></div>
      <pre class="code glass deep" style="flex:1;min-height:0;border-radius:16px">${c.loading ? T('生成契约……') : esc(c.error || c.text)}</pre></div>`;
  }

  /* ---------- 复制一份到这个世界(…/fork)---------- */
  function forkBox(id, r) {
    if (!F.list || !F.list.writable) return `<br><span class="sub" style="font-size:12px">${T('「{w}」是内置的世界,不能往里放前端:', { w: esc(tplT(world())) })}</span><br><button class="chip" data-fxfork style="margin-top:6px">${T('去 Template 复制成我的世界')}</button>`;
    const f = F.fork && F.fork.id === id ? F.fork : null;
    if (!f) return `<br><button class="chip lime" data-fxforkopen style="margin-top:8px">${T('复制一份到这个世界')}</button>`;
    return `<div class="fxforkf"><input class="cell" id="fxforkname" placeholder="${T('文件夹名,例')} my-${esc(r.kind === 'godot' ? 'godot' : r.kind === 'chat' ? 'phone' : 'web')}" value="${esc(f.name || '')}">
      <button class="btn p" data-fxforkgo>${T('复制')}</button><button class="chip" data-fxforkx>${T('取消')}</button>${f.msg ? `<div class="sub" style="color:var(--fail);font-size:12px">${esc(f.msg)}</div>` : ''}</div>`;
  }

  /* ---------- 前端 agent ---------- */
  function side(id) {
    const r = row(id) || {}, msgs = F.agent[wkey() + '|' + id] || [];
    const ro = !r.writable || id === 'new';
    return `<div class="side"><div class="glass"><div class="side-h"><b>${T('前端 agent')}</b> <span class="tag">${T('只改 {d}/', { d: esc(r.dir || T('这个前端文件夹')) })}</span>
        <div class="sub" style="font-size:12.5px">${T('它看得到这个文件夹的文件和这个世界的契约,写整份文件;别的地方一概不碰。')}</div></div>
      <div class="chat" id="fxchat">${id === 'new' ? `<div class="m agent">${T('建好之后,在这里跟我说要什么样的界面:我读这个文件夹和这个世界的契约,写整份文件,右边随时预览。')}</div>`
        : ro ? `<div class="m agent">${r.source === 'builtin' ? T('这是内置的「{t}」,产品自己的代码,在这里只读。', { t: esc(r.title || id) }) : T('这是一个只读的前端,在这里只读。')}${T('想按这个世界改,先复制一份到这个世界(放进模板的 frontends/),之后我改那一份。')}${F.mode === 'edit' ? '' : forkBox(id, r)}</div>`
        : msgs.length ? '' : `<div class="m agent">${T('我是这个前端的 agent,只改 {d}/。说你想要什么样的界面。', { d: esc(r.dir) })}</div>`}
        ${msgs.map(m => `<div class="m ${m.t}">${m.h}</div>`).join('')}</div>
      <div class="compose"><div class="in"><input id="fxin" placeholder="${ro ? T('内置前端只读') : T('例如:加一个背包按钮')}" autocomplete="off" ${ro || F.busy.agent ? 'disabled' : ''}><button class="send" id="fxsend" aria-label="${T('发送')}" ${ro || F.busy.agent ? 'disabled' : ''}>➤</button></div>
        ${ro ? '' : `<div class="sugg">${['加一个背包按钮', '对话框改成竖排', '结局时全屏放 CG'].map(x => `<button class="chip" data-fxsay="${x}">${T(x)}</button>`).join('')}</div>`}</div></div></div>`;
  }

  /* ---------- 整页 ---------- */
  // 页签:一张表声明(id · 名字 · 哪些台有 · 怎么画);别的模块用 FXDESK.addTab 加(小手机的「编排」之后挂在这里)
  const TABS = [
    { id: 'play', label: T('试玩'), mode: 'play', render: d => ((d.row || {}).source === 'template' && d.kind !== 'godot' ? playOwn : PLAY[d.id] || PLAY[d.kind] || (() => `<div class="fxpad"><div class="sub">${T('这一类的预览还没做')}</div></div>`))(d.id) },
    { id: 'files', label: T('文件'), mode: 'edit', editable: true, render: d => files(d.id) },
    { id: 'events', label: T('事件流'), mode: 'edit', render: () => feEvents() },
    { id: 'contract', label: T('契约'), mode: 'edit', editable: true, render: d => contract(d.id) },
  ];
  F.addTab = tab => { tab = { mode: 'edit', ...tab }; const i = TABS.findIndex(x => x.id === tab.id); if (i >= 0) TABS[i] = tab; else TABS.push(tab); rer(); };
  const tabsOf = d => TABS.filter(x => (x.mode || 'edit') === F.mode && (!x.when || x.when(d)));
  const goEdit = v => { F.mode = 'edit'; F.editView = v || F.editView; };
  renderFe = function () {
    const el = $('#s-fe'); if (!el) return;
    loadList();
    const id = fidOf(F.sel), kind = kindOf(id);
    S.wview = F.view; S.target = kind === 'godot' ? 'godot' : 'web';   // fe.js 的事件流按这两个出代码片段 / 自动刷新
    const own = (F.list && F.list.frontends || []).filter(x => x.source === 'template');
    const bad = x => (x.problems || []).some(p => p.level === 'block');
    const desks = [...DESKS, ...own.map(x => [x.id, x.title])].map(([k, l]) => `<button class="${k === F.sel ? 'on' : ''}" data-fxdesk="${esc(k)}" title="${esc((row(fidOf(k)) || {}).dir || '')}">${esc(l)}${row(k) && bad(row(k)) ? ' <i class="fxwarn">!</i>' : ''}</button>`).join('')
      + `<button class="${F.sel === 'new' ? 'on' : ''}" data-fxdesk="new" title="${T('给这个世界做一个自己的重前端')}">+ ${T('新建')}</button>`;
    const probs = (row(id) || {}).problems || [];
    const tsSeg = F.sel === 'ts' ? `<div class="seg fxsub">${TSSUB.map(([k, , l]) => `<button class="${F.tsSub === k ? 'on' : ''}" data-fxsub="${k}">${l}</button>`).join('')}</div>` : '';
    const desk = { id, sel: F.sel, kind, row: row(id), world: world(), mode: F.mode, writable: !!(row(id) || {}).writable }, tabs = tabsOf(desk);
    F.view = F.mode === 'play' ? (tabs[0] || {}).id || 'play' : tabs.some(x => x.id === F.editView) ? F.editView : (F.editView = (tabs[0] || {}).id || 'files');
    S.wview = F.view;
    const tab = tabs.find(x => x.id === F.view) || tabs[0];
    // own: true = 这一页和前端文件夹能不能写无关(小手机编排写本地覆盖层):不出「只读 · 先复制」那条
    const ro = F.mode === 'edit' && id !== 'new' && row(id) && !row(id).writable && !(tab && tab.own);
    const body = id === 'new' ? newDesk() : (ro ? `<div class="fxrobar"><b>${T('只读')}</b><span>${(row(id) || {}).source === 'builtin' ? T('内置前端要先复制一份到这个世界才能编辑') : T('这个前端要先复制一份到这个世界才能编辑')}</span>${forkBox(id, row(id) || {})}</div>` : '') + tab.render(desk);
    const nd = dirtyKeys().length;
    el.innerHTML = `<div class="agw">${side(id)}<div class="work"><div class="crumb"><div class="seg fxdesks">${desks}</div>${tsSeg}<span class="sep">·</span>
        ${id === 'new' ? '' : `<div class="seg fxmode">${[['play', T('试玩')], ['edit', T('编辑')]].map(([k, l]) => `<button class="${F.mode === k ? 'on' : ''}" data-fxmode="${k}">${l}</button>`).join('')}</div>`}
        ${id === 'new' || F.mode !== 'edit' ? '' : tabs.map(x => `<button class="${F.view === x.id ? 'on' : ''}" data-fxv="${esc(x.id)}">${esc(x.label)}</button>`).join('')}
        <div class="r">${nd ? `<span class="chip rust fxdirty" title="${T('离开页面前记得保存')}">${T('{n} 个文件没保存', { n: nd })}</span>` : ''}${id !== 'new' && row(id) && F.mode === 'edit' ? `<a class="chip" data-fxexport href="${esc(V3.url(`${P}/${enc(wkey())}/${enc(id)}/export`))}" download="${esc(id)}.frontend.zip" title="${T('把这个前端文件夹打成 zip(不带 node_modules / .godot / dist)')}">${T('导出 zip')}</a>` : ''}<span class="tag">${T('当前世界')}</span><span class="chip">${esc(tplT(world()) || '—')}</span></div></div>
      ${probs.length ? `<div class="fxprobs">${probs.map(p => `<span class="chip ${p.level === 'block' ? 'rust' : ''}" title="${esc(p.where)}">${esc(p.code)} · ${esc(p.message)}</span>`).join('')}</div>` : ''}
      ${brick('wk', null, body)}</div></div>`;
    const c = $('#fxchat'); if (c) c.scrollTop = c.scrollHeight;
    if (F.view === 'events') { const l = document.getElementById('fevl'); if (l && window.FEEVENTS && window.FEEVENTS.follow) l.scrollTop = l.scrollHeight; }
    requestAnimationFrame(place);
  };

  /* ---------- 动作 ---------- */
  async function smoke() {
    const id = fidOf(F.sel), line = (($('#fxline') || {}).value || '').trim() || '看看四周'; F.smokeLine = line;
    F.busy.smoke = true; F.smoke = null; rer();
    try { F.smoke = { id, ...(await post(`/${enc(wkey())}/${enc(id)}/godot/smoke`, { line })) }; }
    catch (e) { F.smoke = { id, ok: false, code: e.status || '—', error: T('冒烟没跑起来:') + e.message }; }
    F.busy.smoke = false; rer();
  }
  async function launch() {
    try { await post(`/${enc(wkey())}/${enc(fidOf(F.sel))}/godot/launch`, {}); } catch (e) { toast2(T('没启动起来:') + e.message); }
    loadGodot(true);
  }
  async function buildTs() {
    F.busy.build = true; F.build = null; rer();
    try { F.build = await post(`/${enc(wkey())}/builtin.ts/build`, {}); } catch (e) { F.build = { ok: false, code: e.status || '—', error: T('构建没跑起来:') + e.message }; }
    F.busy.build = false; F.tree = {}; FR.src = ''; await loadList(true);
  }
  async function create() {
    const n = F.nf; n.name = (($('#fxnname') || {}).value || '').trim(); n.title = (($('#fxntitle') || {}).value || '').trim(); F.msg = '';
    try { const r = await post(`/${enc(wkey())}/new`, { name: n.name, kind: n.kind, title: n.title }); F.nf = { kind: n.kind, name: '', title: '' }; await loadList(true); F.sel = r.id; F.mode = 'play'; }
    catch (e) { F.msg = T('没建成:') + (e.status === 400 ? T('名字只能是小写字母 / 数字 / -,而且不能和已有的重名') : e.message); }
    rer();
  }
  async function save() {
    const id = fidOf(F.sel), t = $('#fxedit'), path = F.fsel && F.fsel.id === id ? F.fsel.path : ((t && t.closest('.fxed').querySelector('.mono')) || {}).textContent;
    if (!t || !path) return;
    try { await post(`/${enc(wkey())}/${enc(id)}/file`, { path, content: t.value }); const k = wkey() + '|' + id + '|' + path; F.file[k] = { path, content: t.value }; delete F.edit[k]; F.rev = Date.now(); await loadList(true); }
    catch (e) { toast2(T('没保存上:') + e.message); }
    rer();
  }
  async function writeContract() {
    const id = fidOf(F.sel), r = row(id) || {}, fmt = F.cfmt, c = F.contract[world() + '|' + fmt];
    if (!c || !c.text) return;
    const path = fmt === 'gd' ? 'addons/worldlines/contract.gd' : 'contract.ts';
    try { await post(`/${enc(wkey())}/${enc(id)}/file`, { path, content: c.text }); delete F.tree[wkey() + '|' + id]; delete F.file[wkey() + '|' + id + '|' + path]; toast2(T('写好了:') + `${r.dir}/${path}`); } catch (e) { toast2(T('没写上:') + e.message); }
    rer();
  }
  // 前端 agent 一回合:引擎 SSE(chunk · tool_use · done · error),和创作会话同一种格式
  async function agentSay(x) {
    const id = fidOf(F.sel), k = wkey() + '|' + id, list = F.agent[k] = F.agent[k] || [];
    F.wrote[k] = new Set();   // 这一回合写了哪些:文件页上标「已写入」(agent 直接写盘,不走草稿)
    const hist = list.filter(m => m.raw).map(m => ({ role: m.t === 'me' ? 'user' : 'assistant', content: m.raw }));
    list.push({ t: 'me', h: esc(x), raw: x });
    const msg = { t: 'agent', h: '<span class="dots">…</span>' }; list.push(msg); F.busy.agent = true; rer();
    let text = '', calls = [];
    try {
      const r = await fetch(V3.url(`${P}/${enc(wkey())}/${enc(id)}/agent`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ input: x, history: hist }) });
      if (!r.ok || !r.body) throw new Error((await r.json().catch(() => ({}))).error || 'agent → ' + r.status);
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', ev = '';
      for (;;) { const { done, value } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true });
        let nl; while ((nl = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, nl).replace(/\r$/, ''); buf = buf.slice(nl + 1);
          if (line.startsWith('event: ')) ev = line.slice(7);
          else if (line.startsWith('data: ') && ev) { let d = {}; try { d = JSON.parse(line.slice(6)); } catch { /* skip */ }
            if (ev === 'chunk') text += d.text || ''; else if (ev === 'tool_use') { calls.push(`${d.name} ${d.path || ''}${d.error ? ' ✗ ' + d.error : ''}`); if (d.name === 'write_file' && !d.error && d.path) (F.wrote[k] = F.wrote[k] || new Set()).add(d.path); } else if (ev === 'done') { text = d.assistant_message || text; msg.raw = text; } else if (ev === 'error') text += '\n' + T('出错:') + (/no model|model_ref|provider/i.test(d.error || '') ? T('还没选模型:到设置里选一个模型') : d.error || '');
            msg.h = `${esc(text.replace(/<file path="[^"]*">[\s\S]*?(<\/file>|$)/g, '').trim()) || '<span class="dots">…</span>'}${calls.length ? `<span class="call">${esc(calls.slice(-8).join(' · '))}</span>` : ''}`; rer(); ev = ''; } } }
      if (F.wrote[k].size) msg.h += `<span class="call">${T('已写入:')}${esc([...F.wrote[k]].join(' · '))}</span>`;
    } catch (err) { msg.h = T('没连上前端 agent:') + esc(err.message); }
    F.busy.agent = false; delete F.tree[k]; Object.keys(F.file).forEach(x => { if (x.startsWith(k + '|')) delete F.file[x]; }); F.rev = Date.now(); FR.src = ''; await loadList(true);
    rer(); setTimeout(() => $('#fxin') && $('#fxin').focus(), 0);
  }
  async function forkGo() {
    const id = fidOf(F.sel), name = ((($('#fxforkname') || {}).value) || (F.fork && F.fork.name) || '').trim();
    F.fork = { id, name };
    try { const r = await post(`/${enc(wkey())}/${enc(id)}/fork`, { name, title: '' }); F.fork = null; await loadList(true); F.sel = r.id; goEdit('files'); F.fsel = null; toast2(T('复制好了:') + `frontends/${r.id}/`); }
    catch (e) { F.fork = { id, name, msg: T('没复制成:') + (e.status === 400 ? T('名字只能是小写字母 / 数字 / -,而且不能和已有的重名') : e.message) }; }
    rer();
  }
  async function importZip(file) {
    const name = ((($('#fximpname') || {}).value) || F.impName || '').trim() || String(file.name || '').replace(/\.frontend\.zip$|\.zip$/i, '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
    F.imp = null; rer();
    try {
      const r = await fetch(V3.url(`${P}/${enc(wkey())}/import?name=${enc(name)}&lang=zh`), { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/zip' }, body: file });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { F.imp = { ok: false, error: b.error || r.status, problems: b.problems }; rer(); return; }
      F.imp = { ok: true, id: b.id }; F.impName = ''; await loadList(true); F.sel = b.id; goEdit('files'); F.fsel = null;
    } catch (e) { F.imp = { ok: false, error: e.message }; }
    rer();
  }
  const toast2 = m => { if (typeof toast === 'function') toast(m); else alert(m); };
  document.addEventListener('click', async e => {
    if (S.screen !== 'fe') return;
    let t;
    if ((t = e.target.closest('[data-fxdesk]'))) { F.sel = t.dataset.fxdesk; F.fsel = null; renderFe(); return; }
    if ((t = e.target.closest('[data-fxmode]'))) { F.mode = t.dataset.fxmode; renderFe(); return; }
    if ((t = e.target.closest('[data-fxv]'))) { goEdit(t.dataset.fxv); renderFe(); return; }
    if ((t = e.target.closest('[data-fxsub]'))) { F.tsSub = t.dataset.fxsub; F.fsel = null; renderFe(); return; }
    if ((t = e.target.closest('[data-fxf]'))) { F.fsel = { id: fidOf(F.sel), path: t.dataset.fxf }; renderFe(); return; }
    if (e.target.closest('[data-fxbuild]')) { buildTs(); return; }
    if ((t = e.target.closest('[data-fxkind]'))) { F.nf.kind = t.dataset.fxkind; F.nf.name = (($('#fxnname') || {}).value || ''); F.nf.title = (($('#fxntitle') || {}).value || ''); renderFe(); return; }
    if (e.target.closest('[data-fxcreate]')) { create(); return; }
    if (e.target.closest('[data-fxforkopen]')) { F.fork = { id: fidOf(F.sel), name: '' }; renderFe(); setTimeout(() => $('#fxforkname') && $('#fxforkname').focus(), 0); return; }
    if (e.target.closest('[data-fxforkx]')) { F.fork = null; renderFe(); return; }
    if (e.target.closest('[data-fxforkgo]')) { forkGo(); return; }
    if (e.target.closest('[data-fxdiscard]')) { const id = fidOf(F.sel), p = F.fsel && F.fsel.id === id ? F.fsel.path : ($('.fxed .mono') || {}).textContent; delete F.edit[wkey() + '|' + id + '|' + p]; renderFe(); return; }
    if (e.target.closest('[data-fxfork]')) { window.LIVE_openTpl && window.LIVE_openTpl(world()); return; }
    if (e.target.closest('[data-fxsave]')) { save(); return; }
    if (e.target.closest('[data-fxcwrite]')) { writeContract(); return; }
    if (e.target.closest('[data-fxreload]')) { F.rev = Date.now(); renderFe(); return; }
    if ((t = e.target.closest('[data-fxsay]'))) { if (!F.busy.agent) agentSay(t.dataset.fxsay); return; }
    if (e.target.closest('#fxsend')) { const v = (($('#fxin') || {}).value || '').trim(); if (v && !F.busy.agent) agentSay(v); return; }
    if ((t = e.target.closest('[data-fxcf]'))) { F.cfmt = t.dataset.fxcf; renderFe(); return; }
    if ((t = e.target.closest('[data-fxsoul]'))) { F.soul[world()] = t.dataset.fxsoul; renderFe(); return; }
    if ((t = e.target.closest('[data-fxworld]'))) { window.WL_setWorld && window.WL_setWorld(t.dataset.fxworld); return; }
    if (e.target.closest('[data-fxsmoke]')) { smoke(); return; }
    if (e.target.closest('[data-fxlaunch]')) { launch(); return; }
    if ((t = e.target.closest('[data-fxstop]'))) { await post('/_/godot/stop', { pid: +t.dataset.fxstop }).catch(() => null); loadGodot(true); return; }
    if (e.target.closest('[data-fxtoken]')) {
      try { const c = await api('/_/connect'); await navigator.clipboard.writeText(c.token); toast2(T('令牌复制好了')); } catch (err) { toast2(T('拿不到令牌:') + (err.message || err)); }
    }
  });
  document.addEventListener('keydown', e => {
    if (S.screen !== 'fe' || e.key !== 'Enter' || e.isComposing) return;
    if (e.target.id === 'fxin') { const v = e.target.value.trim(); if (v && !F.busy.agent) agentSay(v); }
    if (e.target.id === 'fxforkname') forkGo();
  });
  document.addEventListener('change', e => { if (S.screen === 'fe' && e.target.id === 'fximpfile' && e.target.files && e.target.files[0]) importZip(e.target.files[0]); });
  // 编辑器里打的字记下来:重画(实时事件来了)不丢
  document.addEventListener('input', e => {   // 表单里打的字记在 F 上:实时事件 / 列表回来会重画
    if (e.target.id === 'fxforkname' && F.fork) F.fork.name = e.target.value;
    if (e.target.id === 'fxnname') F.nf.name = e.target.value;
    if (e.target.id === 'fxntitle') F.nf.title = e.target.value;
    if (e.target.id === 'fximpname') F.impName = e.target.value;
  });
  document.addEventListener('input', e => { if (e.target.id !== 'fxedit') return; const id = fidOf(F.sel), p = F.fsel && F.fsel.id === id ? F.fsel.path : (e.target.closest('.fxed').querySelector('.mono') || {}).textContent; F.edit[wkey() + '|' + id + '|' + p] = e.target.value;
    markDirty(wkey() + '|' + id, p); });
  // 打字时不整页重画(会丢光标):只改「草稿 / 已保存」· 树上的点 · 顶上的计数
  function markDirty(k, p) {
    const d = isDirty(k + '|' + p), n = dirtyKeys().length;
    const st = document.querySelector('.fxedh .fxstate'); if (st) st.innerHTML = d ? `<span class="chip rust">${T('草稿 · 没保存')}</span>` : `<span class="chip sage">${T('已保存')}</span>`;
    document.querySelectorAll('[data-fxsave], [data-fxdiscard]').forEach(b => { b.disabled = !d; });
    const f = [...document.querySelectorAll('#s-fe .tree [data-fxf]')].find(x => x.dataset.fxf === p);
    if (f) { const dot = f.querySelector('.fxdot'); if (d && !dot) f.insertAdjacentHTML('afterbegin', `<b class="fxdot" title="${T('没保存')}">●</b> `); if (!d && dot) { dot.nextSibling && dot.nextSibling.nodeType === 3 && dot.nextSibling.remove(); dot.remove(); } }
    const r = document.querySelector('#s-fe .crumb .r'); if (r) { let c = r.querySelector('.fxdirty'); if (n && !c) { r.insertAdjacentHTML('afterbegin', '<span class="chip rust fxdirty"></span>'); c = r.querySelector('.fxdirty'); } if (c) { if (n) c.textContent = T('{n} 个文件没保存', { n }); else c.remove(); } }
  }
  window.addEventListener('wl:world', () => { F.fsel = null; F.smoke = null; if (S.screen === 'fe') { loadList(true); renderFe(); } });

  const _render = render;
  render = function () { _render.apply(this, arguments); requestAnimationFrame(place); };

  document.head.insertAdjacentHTML('beforeend', `<style>
    .fxpad{position:absolute;inset:0;padding:16px 18px;overflow:auto}
    .fxgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
    .fxcard{padding:14px 16px;border-radius:18px}
    .fxpath{font-size:11px;color:var(--faint);margin-top:2px;word-break:break-all}
    .fxres{margin-top:12px;border-radius:14px;padding:10px 12px;background:var(--well)} .fxres.ok{box-shadow:inset 0 0 0 1px rgba(159,224,176,.35)} .fxres.bad{box-shadow:inset 0 0 0 1px rgba(255,179,168,.4)}
    .fxout{font-size:11.5px;white-space:pre-wrap;max-height:260px;padding:10px 12px;margin-top:8px;background:rgba(0,0,0,.3);border-radius:12px}
    .fxbar{margin-bottom:14px}
    .fxchat{position:absolute;inset:0;display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:16px;padding:16px}
    .fxsouls{padding:14px;border-radius:18px;overflow:auto;display:flex;flex-direction:column;gap:6px}
    .fxsoul{display:flex;gap:10px;align-items:center;text-align:left;border:1px solid transparent;background:none;border-radius:14px;padding:6px 8px}
    .fxsoul img{width:38px;height:38px;border-radius:50%;object-fit:cover;background:var(--well)} .fxsoul small{display:block;color:var(--muted);font-size:11.5px}
    .fxsoul.on{border-color:var(--line2);background:var(--fill)} .fxsoul:hover{background:var(--hover)}
    .fxphone{position:relative;justify-self:center;width:min(100%,400px);height:100%;max-height:820px}
    .fxcol{position:absolute;inset:0;display:flex;flex-direction:column;padding:14px 16px;gap:10px}
    .fxcol > .fxbar{margin:0}
    .fxnote{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}
    .fxstage{position:relative;flex:1;min-height:360px}
    .fxsub{margin-left:4px}
    .fxkinds{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}
    .fxkind{text-align:left;border:1px solid var(--line2);background:var(--well);border-radius:14px;padding:10px 12px} .fxkind small{display:block;color:var(--muted);font-size:11.5px;margin-top:3px}
    .fxkind.on{border-color:var(--lime);background:rgba(201,242,122,.08)} .fxkind:disabled{opacity:.4}
    .fxed{display:flex;flex-direction:column;min-height:0} .fxedh{display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--line);font-size:12px} .fxedh .btn{margin-left:auto}
    .fxed textarea{flex:1;min-height:0;border:0;outline:none;resize:none;background:transparent;width:100%}
    .fxprobs{display:flex;gap:6px;flex-wrap:wrap;margin:-4px 0 10px} .fxwarn{font-style:normal;color:var(--rust)}
    .fxforkf{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px} .fxforkf .cell{max-width:170px}
    .fxdot{color:var(--rust);font-size:9px} .fxwrote{font-style:normal;font-size:10px;color:var(--blue);margin-left:4px}
    .fxstate{display:inline-flex} .fximp{margin-top:16px;padding-top:12px;border-top:1px solid var(--line)} .fxprob{font-size:11.5px;color:var(--fail);margin-top:4px}
    .btn.disabled{opacity:.35;pointer-events:none}
    .fxmode{margin-right:2px} .fxrobar{position:absolute;left:0;right:0;top:0;z-index:2;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 16px;background:rgba(6,7,12,.92);border-bottom:1px solid var(--line);font-size:12.5px;color:var(--muted)}
    .fxrobar b{color:var(--ink)} .fxrobar br{display:none} .fxrobar + .fsv,.fxrobar + .fev,.fxrobar + .fxpad{top:46px}
    .fxdir{font-style:normal;color:var(--faint);margin-left:6px;font-size:10.5px}
    #s-fe .tree .f{padding-right:6px}
  </style>`);
})();
