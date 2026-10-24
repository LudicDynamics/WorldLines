/* 前端台 · 事件流(10-07):进出节点 / 拍 / 掷骰 / 工具 / 状态变化 / 结局 —— 重前端要处理的就是这几种(拍的名字查 BEATS)。
   打开时先用 GET /api/v1/play/engine/beats 补这一局到现在的事件,之后接 /events 上的实时流(engine.js 收)。
   一行一条,点开看原始数据 + 在 Godot / 网页 TS 里怎么接。只读,不改这一局。 */
(() => {
  const NAMES = ['node.enter', 'node.leave', 'plan.beat', 'resolve.beat', 'dice', 'tool', 'state.changed', 'run.settled'];
  const ZH = { 'node.enter': T('进节点'), 'node.leave': T('出节点'), 'plan.beat': T('拍'), 'resolve.beat': T('拍'), ...BEATS.events, dice: T('掷骰'), tool: T('工具'), 'state.changed': T('状态变化'), 'run.settled': T('结局') };
  const TONE = { 'node.enter': 'blue', 'node.leave': 'blue', 'plan.beat': 'lime', 'resolve.beat': 'lime', dice: 'gold', tool: '', 'state.changed': 'rust', 'run.settled': 'sage' };
  const NODE = { ...BEATS.nodes, turn: T('回合'), combat: T('战斗层'), dungeon: T('地穴'), referee: T('规则裁判'), day: T('白天'), night: T('夜里') };
  const ADV = { event: T('外部事件'), host: T('主持推进'), always: T('直接落账'), ...BEATS.adv };
  const F = { hide: new Set(), sel: null, follow: true, loadedFor: null, loading: false, timer: 0 };
  window.FEEVENTS = F;

  const clip = (x, n) => { x = String(x ?? '').replace(/\s+/g, ' ').trim(); return x.length > n ? x.slice(0, n) + '…' : x; };
  const lineOf = l => typeof l === 'string' ? l : l && (l.text || l.line) ? `${l.who ? l.who + ':' : ''}${l.text || l.line}` : JSON.stringify(l);
  const opLine = o => o.op === 'move_to' ? `${o.who} → ${o.to}` : o.var ? `${o.var}${o.from !== undefined ? ' ' + o.from + ' →' : ' ='} ${o.to ?? o.value ?? o.delta ?? ''}` : `${o.op || ''} ${o.who || o.target || o.id || ''}`.trim();
  function summary(m) {
    switch (m.kind) {
      case 'node.enter': return T('进入 {x}', { x: NODE[m.node] || m.node });
      case 'node.leave': return T('离开 {x}', { x: NODE[m.node] || m.node });
      case 'plan.beat': { const sc = (m.script || []).map(lineOf); const mic = (m.mic || []).map(x => typeof x === 'string' ? x : x.to || x.who || '').filter(Boolean);
        return `${m.opening ? T('开场') + ' · ' : ''}${clip(sc[0] || m.text, 60)}${mic.length ? ' · ' + T('递话筒 {x}', { x: mic.join(T('、')) }) : ''}${(m.checks || []).length ? ' · ' + T('约检定 {n}', { n: m.checks.length }) : ''}`; }
      case 'resolve.beat': return `${m.advanced_by ? (ADV[m.advanced_by] || m.advanced_by) + ' · ' : ''}${clip(m.text, 70)}`;
      case 'dice': return `${clip(m.request, 40)} → ${clip(m.answer, 40)}`;
      case 'tool': return `${clip(m.request, 60)}${m.async ? ' · ' + T('异步') : ''}`;
      case 'state.changed': { const a = m.applied || [], c = m.created || [], r = m.refused || [];
        return `${T('{n} 条写入', { n: a.length })}${c.length ? ' · ' + T('新建 {n}', { n: c.length }) : ''}${r.length ? ' · ' + T('被拒 {n}', { n: r.length }) : ''}${a.length ? ' · ' + a.slice(0, 2).map(opLine).join(' · ') : ''}`; }
      case 'run.settled': return `${T('结局')} ${m.ending_id || m.ending || m.id || ''} ${m.title ? T('「{t}」', { t: m.title }) : ''}`;
      default: return clip(JSON.stringify(m), 80);
    }
  }
  // 这条事件在前端里怎么接(Godot 的 signal beat / 网页 TS 的 BeatEvent,见文件页的契约导出)
  const FIELDS = { 'node.enter': ['node'], 'node.leave': ['node'], 'plan.beat': ['script', 'mic', 'board', 'checks'], 'resolve.beat': ['text', 'options', 'rolled'],
    dice: ['request', 'answer'], tool: ['request', 'answer'], 'state.changed': ['applied', 'created', 'refused'], 'run.settled': ['ending_id'] };
  const WHO = { 'node.enter': ['MapView', 'switch_layer'], 'node.leave': ['MapView', 'leave_layer'], 'plan.beat': ['Dialogue', 'show_plan'], 'resolve.beat': ['Dialogue', 'show_prose'],
    dice: ['DiceOverlay', 'roll'], tool: ['Toast', 'show_tool'], 'state.changed': ['Hud', 'apply_changes'], 'run.settled': ['Gallery', 'show_ending'] };
  function snippet(kind) {
    const f = FIELDS[kind] || [], [node, fn] = WHO[kind] || ['Main', 'handle'];
    if (S.target === 'godot') return `# addons/worldlines/client.gd ${T('发出 beat(event, data)')}\nfunc _on_beat(event: String, data: Dictionary) -> void:\n\tmatch event:\n\t\t"${kind}":\n\t\t\t$${node}.${fn}(${f.map(k => `data.${k}`).join(', ')})`;
    const camel = fn.replace(/_(\w)/g, (_, c) => c.toUpperCase());
    return `// ${T('src/contract.ts 里的 BeatEvent')}\nclient.on('beat', (event: BeatEvent, data) => {\n  if (event === '${kind}') ${node[0].toLowerCase() + node.slice(1)}.${camel}(${f.map(k => `data.${k}`).join(', ')})\n})`;
  }

  async function catchUp() {
    const key = (window.LIVE && window.LIVE.bound) || '-';
    if (F.loading || F.loadedFor === key) return;
    F.loading = true;
    const r = await V3.j('/api/v1/play/engine/beats').catch(e => { F.err = /409/.test(String(e && e.message)) ? 'nosession' : 'fail'; return null; });
    if (r) F.err = null;
    if (r && Array.isArray(r.events)) {
      const live = E.beats.list.filter(x => x.live);
      E.beats.list.length = 0;
      r.events.forEach(ev => E.beats.list.push({ ...ev, at: null, live: false }));
      live.forEach(x => E.beats.list.push(x));
      F.loadedFor = key;
    }
    F.loading = false;
    if (S.screen === 'fe' && S.wview === 'events') renderFe();
  }
  E.beats.subs.push(() => {
    if (!(S.screen === 'fe' && S.wview === 'events')) return;
    clearTimeout(F.timer); F.timer = setTimeout(() => { if (F.follow) F.sel = null; renderFe(); }, 150);
  });

  feEvents = function () {
    // 实时流断了就重连,但最多每 5 秒一次(之前每次重画都重连 —— 一断一连地刷)
    if (typeof E.listen === 'function' && !E.streaming && Date.now() - (F.lastListen || 0) > 5000) { F.lastListen = Date.now(); E.listen(); }
    catchUp();
    const all = E.beats.list.map((m, i) => ({ m, i })), rows = all.filter(x => !F.hide.has(x.m.kind));
    const counts = {}; all.forEach(x => { counts[x.m.kind] = (counts[x.m.kind] || 0) + 1; });
    const sel = F.sel != null && E.beats.list[F.sel] ? F.sel : (rows.length ? rows[rows.length - 1].i : null);
    const m = sel != null ? E.beats.list[sel] : null;
    const t = x => x.at ? new Date(x.at).toTimeString().slice(0, 8) : T('之前');
    return `<div class="fev"><div class="fevh"><span class="chip ${E.streaming ? 'sage' : 'rust'}">${E.streaming ? T('● 实时') : T('○ 没连上实时流')}</span>
        <span class="tag">${T('{n} 条 · 本次新来 {m}', { n: all.length, m: E.beats.live })}</span>
        <div class="row" style="gap:5px;flex-wrap:wrap;margin-left:auto">${NAMES.map(k => `<button class="chip ${F.hide.has(k) ? '' : TONE[k] || 'solid'}" data-evk="${k}" title="${k}">${ZH[k]} <i style="opacity:.6;font-style:normal">${counts[k] || 0}</i></button>`).join('')}</div></div>
      <div class="fevb"><div class="fevl" id="fevl">${rows.length ? rows.map(({ m: x, i }) => `<div class="fevr ${i === sel ? 'on' : ''} ${x.live ? 'new' : ''}" data-evi="${i}"><span class="mono t">${t(x)}</span><span class="mono t">#${x.turn ?? '–'}</span><span class="chip ${TONE[x.kind] || ''}">${ZH[x.kind] || x.kind}</span><span class="s">${esc(summary(x))}</span></div>`).join('')
        : `<div class="sub" style="padding:18px">${F.loading ? T('读这一局的事件……') : F.err === 'nosession' ? T('还没开局:去游玩一览挑一个模板开一局,事件会出现在这里') : T('还没有事件。在测试台说一句,这里会实时出现每一拍 / 掷骰 / 状态变化……')}</div>`}</div>
        <div class="fevd">${m ? `<div class="tag">${esc(m.kind)} · ${ZH[m.kind] || ''}</div><h3 style="margin:4px 0 8px">${esc(summary(m))}</h3>
          <div class="tag" style="margin-top:6px">${T('前端里怎么接')} · ${S.target === 'godot' ? 'Godot' : T('网页 TS')}</div><pre class="code">${esc(snippet(m.kind))}</pre>
          <div class="tag" style="margin-top:10px">${T('原始数据')}</div><pre class="code">${esc(JSON.stringify(Object.fromEntries(Object.entries(m).filter(([k]) => !['at', 'live'].includes(k))), null, 2))}</pre>` : `<div class="sub">${T('点左边一条')}</div>`}</div></div>
      <div class="bhint">${T('读自引擎:打开时 GET /api/v1/play/engine/beats 补历史 · 之后是 /events 上的实时流 · 和契约导出的 BeatEvent / signal beat 同名')}</div></div>`;
  };
  document.addEventListener('click', e => {
    if (!(S.screen === 'fe' && S.wview === 'events')) return;
    let t;
    if ((t = e.target.closest('[data-evk]'))) { const k = t.dataset.evk; F.hide.has(k) ? F.hide.delete(k) : F.hide.add(k); renderFe(); return; }
    if ((t = e.target.closest('[data-evi]'))) { F.sel = +t.dataset.evi; F.follow = F.sel === E.beats.list.length - 1; renderFe(); }
  });
  const _fe = renderFe;
  renderFe = function () { _fe.apply(this, arguments); const l = document.getElementById('fevl'); if (l && F.follow) l.scrollTop = l.scrollHeight; };
})();
