// ═══════════════════════════════════════════════════════════════════
// 测试台 = 游玩 + 模拟合一屏(docs/planning/TESTBENCH-AUTOVIEW-1005.md)。
// 「游玩」页签是原来的游玩界面;其余页签全部由引擎给的数据结构自动生成,不写任何专门的组件:
//   本轮编排 ← trace(spans / beat.calls / applied / refused / rolled) · 后台 ← 引擎每轮包的 units(按单位)
//   世界 ← schema 的类(render 行模板 · props · folder)+ 实例 · 变量 ← schema 变量 + 账本历史
//   文件 ← 引擎每轮包:这一拍写入的变量 / 实体所在的文件 · 世界线 ← 提交图
// 同一份数据两种出口:HTML(表格)和 TUI 文字(等宽,跟终端里看到的一样)。
// ═══════════════════════════════════════════════════════════════════
const BENCH_TABS = [['play', '游玩'], ['orch', '本轮编排'], ['tick', '后台'], ['world', '世界'], ['vars', '变量'], ['files', '文件'], ['wl', '世界线']];
U.ptab = U.ptab || 'play'; U.bout = U.bout || 'html'; U.bround = null; U.bcls = null; U.bq = '';
// 引擎的每轮包(V2,GET /api/v1/play/engine/round?i=):这一拍改了什么(applied / created / refused)+ 后台单位各自改了什么。
// 按需取、按 trace 序号缓存;取到就重画。拿不到(老引擎 / 没开局)时各页退回从 trace 推算。
const BUNDLES = {};
function bundle(i) {
  if (i == null) return null;
  const b = BUNDLES[i];
  if (b === undefined) { BUNDLES[i] = 'loading'; V3.j(`/api/v1/play/engine/round?i=${i}`).then(d => { BUNDLES[i] = d && d.diff ? d : null; }).catch(() => { BUNDLES[i] = null; }).finally(() => { if (U.ptab === 'files' || U.ptab === 'tick') renderPlay(); }); return null; }
  return b === 'loading' ? null : b;
}

function benchStrip() {
  const s = st(), R = s.rounds || [], cur = benchRound();
  const tabs = BENCH_TABS.map(([k, l]) => `<button class="${U.ptab === k ? 'on' : ''}" data-bt="${k}">${l}</button>`).join('');
  const right = U.ptab === 'play' ? `<span class="btag">回合 ${s.turn} · ${R.length} 拍</span>`
    : `${['orch', 'files'].includes(U.ptab) && R.length ? `<select class="bsel" id="bRound" aria-label="选一拍">${R.map((r, i) => `<option value="${i}" ${r === cur ? 'selected' : ''}>${benchLabel(r)}</option>`).join('')}</select>` : ''}
       <div class="seg bseg"><button class="${U.bout === 'html' ? 'on' : ''}" data-bo="html">HTML</button><button class="${U.bout === 'tui' ? 'on' : ''}" data-bo="tui">TUI 文字</button></div>`;
  return `<div class="btabs">${tabs}<span class="bsp"></span>${right}</div>`;
}
function benchLabel(r) { return `#${r.seq} · ${window.BEATS ? BEATS.label(r.kind) : r.kind} · ${String(r.input).replace(/\s+/g, ' ').slice(0, 16)}`; }
function benchRound() { const R = st().rounds || []; if (!R.length) return null; return U.bround != null && R[U.bround] ? R[U.bround] : R[R.length - 1]; }
function wireStrip(root) {
  root.querySelectorAll('[data-bt]').forEach(b => b.onclick = () => { U.ptab = b.dataset.bt; renderPlay(); });
  root.querySelectorAll('[data-bo]').forEach(b => b.onclick = () => { U.bout = b.dataset.bo; renderPlay(); });
  const sel = root.querySelector('#bRound'); if (sel) sel.onchange = () => { U.bround = +sel.value; renderPlay(); };
}

function renderBench() {
  const m = $('#pmain');
  const body = ({ orch: benchOrch, tick: benchTick, world: benchWorld, vars: benchVars, files: benchFiles, wl: benchWl })[U.ptab]();
  const src = ({ orch: 'trace · spans / beat.calls / applied / refused', tick: '引擎每轮包 · units(取不到时退回账本 by=tick)', world: 'schema 类(render 行模板 · props)+ 实例', vars: 'schema 变量 + 账本历史', files: '引擎每轮包 · 这一拍的写入 → 所在文件', wl: '提交图' })[U.ptab];
  m.innerHTML = benchStrip() + `<div class="bbody">${body}<div class="bsrc">自动生成 · 来源:${src} · 没有专门写的组件</div></div>`;
  wireStrip(m);
  m.querySelectorAll('[data-bcls]').forEach(b => b.onclick = () => { U.bcls = U.bcls === b.dataset.bcls ? null : b.dataset.bcls; renderPlay(); });
  const q = m.querySelector('#bQ'); if (q) { q.oninput = () => { U.bq = q.value; const pos = q.selectionStart; renderPlay(); const n = $('#bQ'); if (n) { n.focus(); n.setSelectionRange(pos, pos); } }; }
}
const tui = rows => `<pre class="btui">${rows}</pre>`;
const empty = t => `<div class="bempty">${t}</div>`;
const pad = (x, n) => { x = String(x); let w = 0; for (const ch of x) w += /[　-鿿＀-￯]/.test(ch) ? 2 : 1; return x + ' '.repeat(Math.max(1, n - w)); };
const val = v => v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v);

function opText(o) {
  if (o.op === 'set' || o.op === 'add') return `${o.var} ${o.from !== undefined ? val(o.from) + ' → ' : ''}${val(o.to ?? o.value ?? o.delta)}`;
  if (o.op === 'move_to') return `${nm(o.who) || o.who} → ${nm(o.to) || o.to}`;
  return [o.op, o.who, o.target || o.item || o.cls, o.to || o.name].filter(Boolean).map(x => nm(x) || x).join(' ');
}
function benchOrch() {
  const r = benchRound(); if (!r) return empty('还没有任何一拍:去「游玩」说一句话');
  const kind = window.BEATS ? BEATS.label(r.kind) : r.kind;
  const steps = r.spans.length ? r.spans.map(x => ({ who: `${x.phase} · ${x.actor}`, be: x.backend, t0: x.t0, t1: x.t1 }))
    : (() => { let t = 0; return r.calls.map(c => { const o = { who: c.who.replace(/^si-/, '').replace(/^host-?(\d*)$/, (_, n) => '主持' + (n ? ' 第' + n + '轮' : '')), be: 'llm', t0: t, t1: t + (c.ms || 0) }; t += c.ms || 0; return o; }); })();
  const tot = Math.max(1, ...steps.map(x => x.t1));
  const head = [['拍', kind], ['玩家', r.input.replace(/\s+/g, ' ').slice(0, 80)], ['地点', nm(r.loc) || r.loc], r.rounds ? ['主持轮数', r.rounds] : null, r.advanced_by ? ['推进', r.advanced_by] : null, ['耗时', `${((r.ms || tot) / 1000).toFixed(1)} s`], r.commit ? ['提交', String(r.commit).slice(0, 7)] : null,
    // 时间预算的两个标记(10-19,只在测试台显示,玩家画面不提示)
    r.truncated ? ['半句', '拍子到点 · 写出的半句当这一拍的话(beat.truncated)'] : null,
    r.deferred ? ['推进延后', `该推进但没剩时间给世界拍 · 改到玩家下一句再清算(beat.advance_deferred = ${val(r.deferred)})`] : null].filter(Boolean);
  // 主持每次调用的首字 / 总毫秒(beat.calls[].first_ms)· 这一回合全部模型调用(trace.timing.llm_calls)
  const ms = x => (x == null || x === '' ? '—' : `${(+x / 1000).toFixed(1)} s`);
  const calls = (r.calls || []).map(c => ({ who: String(c.who || ''), first: c.first_ms, ms: c.ms, trunc: !!c.truncated }));
  const llm = ((r.timing && r.timing.llm_calls) || []).map(c => ({ beat: c.beat || '—', first: c.first_ms, ms: c.ms, chars: c.chars, trunc: !!c.truncated,
    more: Object.entries(c).filter(([k]) => !['beat', 'first_ms', 'ms', 'chars', 'truncated'].includes(k)).map(([k, v]) => `${k}=${val(v)}`).join(' ') }));
  if (U.bout === 'tui') return tui([`<b>${esc(benchLabel(r))}</b>`, ...head.map(([k, v]) => `${pad(k, 10)}${esc(v)}`), '',
    ...steps.map(x => `${pad(x.who, 30)}${pad(x.be, 7)}${String(((x.t1 - x.t0) / 1000).toFixed(1)).padStart(5)} s  ${'█'.repeat(Math.max(1, Math.round((x.t1 - x.t0) / tot * 30)))}`), '',
    ...(calls.length ? ['<b>主持调用</b>  首字 / 总', ...calls.map(c => `${pad(c.who, 14)}${pad(ms(c.first), 9)}${pad(ms(c.ms), 9)}${c.trunc ? '<u>半句</u>' : ''}`), ''] : []),
    ...(llm.length ? ['<b>模型调用</b>  timing.llm_calls', ...llm.map(c => `${pad(c.beat, 10)}${pad(ms(c.first), 9)}${pad(ms(c.ms), 9)}${pad(c.chars ?? '—', 7)}${c.trunc ? '<u>半句</u> ' : ''}${esc(c.more)}`), ''] : []),
    ...r.rolled.map(d => `骰  ${esc(JSON.stringify(d))}`), ...r.applied.map(o => `<em>✓</em> ${esc(opText(o))}`), ...r.refused.map(o => `<u>✗</u> ${esc(opText(o.op || o))}  ${esc(o.why || o.reason || '')}`)].join('\n'));
  return `<div class="bgrid2"><div><table class="btab"><tbody>${head.map(([k, v]) => `<tr><th>${k}</th><td>${esc(v)}</td></tr>`).join('')}</tbody></table>
      <h4>每一步 <span>${r.spans.length ? 'spans' : 'beat.calls'} · 共 ${(tot / 1000).toFixed(1)} s</span></h4>
      ${steps.length ? `<table class="btab">${steps.map(x => `<tr><td>${esc(x.who)}</td><td><span class="pill ${x.be === 'llm' ? 'v' : ''}">${esc(x.be)}</span></td><td style="width:44%"><div class="bbar"><i class="${x.be === 'llm' ? '' : 'py'}" style="left:${x.t0 / tot * 100}%;width:${Math.max(.8, (x.t1 - x.t0) / tot * 100)}%"></i></div></td><td class="mono">${((x.t1 - x.t0) / 1000).toFixed(1)} s</td></tr>`).join('')}</table>` : empty('这一拍没有记录调用')}
      ${calls.length ? `<h4>主持调用 <span>beat.calls · 首字 / 总</span></h4><table class="btab" data-bcalls><tr><th>谁</th><th>首字</th><th>总</th><th></th></tr>${calls.map(c => `<tr><td>${esc(c.who)}</td><td class="mono">${ms(c.first)}</td><td class="mono">${ms(c.ms)}</td><td>${c.trunc ? '<span class="pill red">半句</span>' : ''}</td></tr>`).join('')}</table>` : ''}
      ${llm.length ? `<h4>模型调用 <span>trace.timing.llm_calls · 这一回合 ${llm.length} 次</span></h4><table class="btab" data-bllm><tr><th>拍</th><th>首字</th><th>总</th><th>字数</th><th></th><th>其它</th></tr>${llm.map(c => `<tr><td>${esc(c.beat)}</td><td class="mono">${ms(c.first)}</td><td class="mono">${ms(c.ms)}</td><td class="mono">${esc(c.chars ?? '—')}</td><td>${c.trunc ? '<span class="pill red">半句</span>' : ''}</td><td class="mono small">${esc(c.more)}</td></tr>`).join('')}</table>` : ''}</div>
    <div><h4>写入 <span>${r.applied.length} 条 · 被拒 ${r.refused.length}</span></h4>
      ${r.applied.length || r.refused.length ? `<table class="btab">${r.applied.map(o => `<tr><td><span class="pill ok">✓ ${esc(o.op)}</span></td><td>${esc(opText(o))}</td></tr>`).join('')}${r.refused.map(o => `<tr><td><span class="pill red">✗ ${esc((o.op && o.op.op) || o.op || '')}</span></td><td>${esc(opText(o.op || o))}<small>${esc(o.why || o.reason || '')}</small></td></tr>`).join('')}</table>` : empty((window.BEATS && (BEATS.kinds[r.kind] || {}).noWrites) || '这一拍没有写入')}
      ${r.rolled.length ? `<h4>骰子</h4><table class="btab">${r.rolled.map(d => `<tr><td>${esc(d.who || '')} ${esc(d.attr || d.skill || '')}</td><td class="mono">${esc(d.total ?? d.roll ?? '')} / ${esc(d.dc ?? '')}</td><td>${d.ok || d.success ? '<span class="pill ok">成功</span>' : '<span class="pill red">失败</span>'}</td></tr>`).join('')}</table>` : ''}
      ${r.mic.length ? `<h4>递话筒</h4><div class="bchips">${r.mic.map(x => `<span class="pill">${esc(typeof x === 'string' ? x : (x.to || x.who || JSON.stringify(x)))}</span>`).join('')}</div>` : ''}</div></div>`;
}
function benchTick() {
  // 引擎每轮包里的 units:哪个后台单位(经济 / 势力 / 时钟 …)在哪一拍改了什么
  const R = (st().rounds || []).slice(-12).reverse();
  const rows = []; let pending = false;
  for (const r of R) { const b = bundle(r.i); if (!b) { if (BUNDLES[r.i] === 'loading') pending = true; continue; }
    for (const [u, ops] of Object.entries(b.units || {})) rows.push({ r, u, ops }); }
  if (rows.length) {
    if (U.bout === 'tui') return tui(rows.map(x => `<b>${esc(benchLabel(x.r))}</b>  ${esc(x.u)}\n${x.ops.map(o => '  ' + esc(opText(o))).join('\n')}`).join('\n'));
    return `<table class="btab"><tr><th>哪一拍</th><th>单位</th><th>改了什么</th></tr>${rows.map(x => `<tr><td class="mono">${esc(benchLabel(x.r))}</td><td><span class="pill v">${esc(x.u)}</span></td><td>${x.ops.map(o => `<span class="pill">${esc(opText(o))}</span>`).join(' ')}</td></tr>`).join('')}</table>
      <div class="bhint">读自引擎的每轮包 · 最近 12 拍</div>`;
  }
  if (pending) return empty('读引擎的每轮包……');
  const ev = (st().events || []).filter(e => e.by === 'tick').slice(-30).reverse();
  if (!ev.length) return empty('还没有后台单位跑过:这个世界没开经济 / 势力等 mixin,或者还没推进过时间');
  if (U.bout === 'tui') return tui(ev.map(e => `<b>回合 ${e.turn}</b>  tick\n${e.changes.map(c => '  ' + esc(c.what) + (c.from !== undefined ? '  ' + esc(val(c.from)) + ' → ' : '  → ') + esc(val(c.to))).join('\n')}`).join('\n'));
  return `<table class="btab"><tr><th>回合</th><th>改了什么</th></tr>${ev.map(e => `<tr><td class="mono">${e.turn}</td><td>${e.changes.map(c => `<span class="pill">${esc(c.what)}${c.from !== undefined ? ' ' + esc(val(c.from)) + ' →' : ' →'} ${esc(val(c.to))}</span>`).join(' ')}</td></tr>`).join('')}</table>`;
}
function benchWorld() {
  const raw = st().schemaRaw || { classes: [], entries: {} };
  const cls = raw.classes.filter(c => (c.count || 0) > 0 || (raw.entries[c.name] || []).length);
  if (!cls.length) return empty('schema 里没有类');
  const sel = U.bcls && cls.find(c => c.name === U.bcls);
  // 类的行模板:字符串,或按语言分的 {zh, en, …}(引擎三语之后)
  const rtext = r => typeof r === 'string' ? r : r && typeof r === 'object' ? String(r[(window.SETTINGS && window.SETTINGS.lang) || 'zh'] || r.zh || r.en || Object.values(r)[0] || '') : '';
  const line = (c, e) => rtext(c.render) ? rtext(c.render).split('\n')[0].replace(/\{(?:props\.)?(\w+)\}/g, (_, k) => k === 'id' ? e.id : k === 'name' ? (e.name || '') : (e.props && e.props[k] !== undefined ? e.props[k] : e[k] ?? '')).replace(/^#+\s*/, '') : `- ${e.id} ${e.name || ''}`;
  if (U.bout === 'tui') return tui(cls.map(c => `<b># ${esc(rtext(c.title) || c.name)}</b>  <em>${esc(c.folder || '(内置)')} · ${(raw.entries[c.name] || []).length || c.count}</em>\n${(raw.entries[c.name] || []).slice(0, 12).map(e => '  ' + esc(line(c, e))).join('\n')}`).join('\n\n'));
  return `<table class="btab"><tr><th>类</th><th>父类</th><th>文件夹</th><th>实例</th><th>属性</th><th>可变</th><th>行模板</th></tr>${cls.map(c => `<tr class="${sel === c ? 'hl' : ''}"><td><button class="blink" data-bcls="${esc(c.name)}">${esc(c.name)}</button></td><td class="mono">${esc(c.parent_class || '—')}</td><td class="mono">${esc(c.folder || '(内置)')}</td><td class="mono">${(raw.entries[c.name] || []).length || c.count || 0}</td><td>${Object.entries(c.props || {}).map(([k, p]) => `<span class="pill">${esc(k)} ${esc(p.type || '')}</span>`).join(' ') || '—'}</td><td class="mono">${esc((c.mutable || []).join(' · ') || '—')}</td><td class="mono small">${esc((rtext(c.render) || '').split('\n')[0] || '—')}</td></tr>`).join('')}</table>
    ${sel ? `<h4>${esc(sel.name)} 的实例 <span>${(raw.entries[sel.name] || []).length}</span></h4><table class="btab"><tr><th>id</th><th>name</th><th>parent</th><th>按行模板</th></tr>${(raw.entries[sel.name] || []).slice(0, 200).map(e => `<tr><td class="mono">${esc(e.id)}</td><td>${esc(e.name || '')}</td><td class="mono">${esc(e.parent || '—')}</td><td class="small">${esc(line(sel, e))}</td></tr>`).join('')}</table>` : '<div class="bhint">点一个类名看它的实例</div>'}`;
}
function spark(h) {
  const v = h.map(x => +x[1]).filter(x => !isNaN(x)); if (v.length < 2) return '';
  const w = 96, hh = 22, mn = Math.min(...v), mx = Math.max(...v), rg = mx - mn || 1;
  const pts = v.map((y, i) => `${(3 + i * (w - 6) / (v.length - 1)).toFixed(1)},${(hh - 3 - (y - mn) * (hh - 6) / rg).toFixed(1)}`);
  const l = pts[pts.length - 1].split(',');
  return `<svg width="${w}" height="${hh}" aria-hidden="true"><polyline points="${pts.join(' ')}" fill="none" stroke="var(--v)" stroke-width="1.5"/><circle cx="${l[0]}" cy="${l[1]}" r="2.4" fill="var(--v)"/></svg>`;
}
function benchVars() {
  const q = U.bq.trim().toLowerCase();
  const V = Object.values(st().vars || {}).filter(v => !q || v.name.toLowerCase().includes(q) || String(v.doc || '').toLowerCase().includes(q));
  const changed = v => v.hist.length > 1;
  V.sort((a, b) => (changed(b) - changed(a)) || a.name.localeCompare(b.name));
  const filter = `<div class="bfilter"><input id="bQ" class="bsel" placeholder="筛选变量,例如 gold / time / flag" value="${esc(U.bq)}"><span class="btag">${V.length} 个 · 变过的在前</span></div>`;
  if (U.bout === 'tui') return filter + tui(V.slice(0, 300).map(v => { const h = v.hist, d = h.length > 1 ? h[h.length - 1][1] - h[h.length - 2][1] : 0; return `${pad(v.name, 34)}${pad(val(v.value), 10)}${d && !isNaN(d) ? `<u>${d > 0 ? '+' : ''}${d}</u>` : '  '}  <em>${esc(v.doc || v.path || '')}</em>`; }).join('\n'));
  return filter + `<table class="btab"><tr><th>变量</th><th>类型</th><th>值</th><th>走势</th><th>文件</th></tr>${V.slice(0, 300).map(v => { const h = v.hist, last = h.length > 1 ? h[h.length - 2][1] : undefined, d = last !== undefined ? +v.value - +last : NaN;
    return `<tr class="${changed(v) ? 'hl' : ''}"><td class="mono">${esc(v.name)}${v.doc ? `<small>${esc(v.doc)}</small>` : ''}</td><td class="mono">${esc(v.type || '')}${v.readonly ? ' · 只读' : ''}</td><td class="mono">${esc(val(v.value))}${!isNaN(d) && d ? ` <span class="${d > 0 ? 'up' : 'dn'}">${d > 0 ? '+' : ''}${d}</span>` : last !== undefined && last !== v.value ? ` <span class="dim">← ${esc(val(last))}</span>` : ''}</td><td>${spark(h)}</td><td class="mono small">${esc(v.path || '')}${v.key ? ' · ' + esc(v.key) : ''}</td></tr>`; }).join('')}</table>`;
}
function benchFiles() {
  const r = benchRound(); if (!r) return empty('还没有任何一拍');
  const V = st().vars || {}, F = new Map(), bd = bundle(r.i);
  const add = (path, why) => { if (!path) return; const a = F.get(path) || []; a.push(why); F.set(path, a); };
  const fileOf = o => (o.op === 'set' || o.op === 'add') && V[o.var] ? V[o.var].path : o.op === 'move_to' ? (o.who === 'player' ? 'game/player/profile.json' : `souls/${o.who}/…`) : `(${o.op})`;
  if (bd) {   // 引擎自己整理的这一拍:正文写入 + 每个后台单位的写入分开
    bd.diff.applied.forEach(o => add(fileOf(o), opText(o)));
    (bd.diff.created || []).forEach(c => add(`${c.folder || 'game'}/${c.id}.json`, `新建 ${c.name || c.id}`));
    Object.entries(bd.units || {}).forEach(([u, ops]) => ops.forEach(o => add(fileOf(o), `后台 · ${u} · ${opText(o)}`)));
    const refused = bd.diff.refused || [];
    if (!F.size && !refused.length) return empty((window.BEATS && (BEATS.kinds[r.kind] || {}).noFiles) || '这一拍没有改文件');
    if (U.bout === 'tui') return tui([...F.entries()].map(([p, w]) => `  M ${pad(esc(p), 40)}<em>${esc(w.join(' · '))}</em>`).concat(refused.map(o => `  <u>✗</u> ${esc(opText(o.op || o))}  ${esc(o.why || o.reason || '')}`)).join('\n'));
    return `<table class="btab"><tr><th>文件</th><th>这一拍写了什么</th></tr>${[...F.entries()].map(([p, w]) => { const d = p.includes('/') ? p.split('/').slice(0, -1).join('/') + '/' : ''; return `<tr><td class="mono"><span class="dim">${esc(d)}</span>${esc(p.split('/').pop())}</td><td>${w.map(x => `<span class="pill ${/^后台/.test(x) ? 'v' : ''}">${esc(x)}</span>`).join(' ')}</td></tr>`; }).join('')}
      ${refused.map(o => `<tr><td><span class="pill red">✗ 没写</span></td><td>${esc(opText(o.op || o))} <span class="dim">${esc(o.why || o.reason || '')}</span></td></tr>`).join('')}</table>
      <div class="bhint">读自引擎的每轮包(round?i=${r.i})· 紫色 = 后台单位写的</div>`;
  }
  r.applied.forEach(o => {
    if ((o.op === 'set' || o.op === 'add') && V[o.var]) add(V[o.var].path, opText(o));
    else if (o.op === 'move_to') add(o.who === 'player' ? 'game/player/profile.json' : `souls/${o.who}/…`, opText(o));
    else add(`(${o.op})`, opText(o));
  });
  r.created.forEach(c => add(`${c.folder || 'game'}/${c.id}.json`, `新建 ${c.name || c.id}`));
  if (!F.size) return empty((window.BEATS && (BEATS.kinds[r.kind] || {}).noFiles) || '这一拍没有改文件');
  const groups = {}; [...F.entries()].forEach(([p, w]) => { const d = p.includes('/') ? p.split('/').slice(0, -1).join('/') : ''; (groups[d] = groups[d] || []).push([p.split('/').pop(), w]); });
  if (U.bout === 'tui') return tui(Object.entries(groups).map(([d, fs]) => `<b>${esc(d || '.')}/</b>\n${fs.map(([f, w]) => `  M ${pad(esc(f), 26)}<em>${esc(w.join(' · '))}</em>`).join('\n')}`).join('\n'));
  return `<table class="btab"><tr><th>文件</th><th>这一拍写了什么</th></tr>${Object.entries(groups).flatMap(([d, fs]) => fs.map(([f, w]) => `<tr><td class="mono"><span class="dim">${esc(d)}/</span>${esc(f)}</td><td>${w.map(x => `<span class="pill">${esc(x)}</span>`).join(' ')}</td></tr>`)).join('')}</table>
    <div class="bhint">按本拍的写入推算(引擎的每轮包还没取到)</div>`;
}
function benchWl() {
  const ids = (E.G.list || []).slice().reverse(), head = st().head;
  if (!ids.length) return empty('还没有提交:这一拍落账后才有');
  if (U.bout === 'tui') return tui(ids.map(id => { const n = E.G.by[id]; return `${id === head ? '<b>*</b>' : '|'} ${n.hash}  ${esc(n.label)}  <em>${esc(n.branch || '')}</em>`; }).join('\n'));
  return `<table class="btab"><tr><th></th><th>提交</th><th>标签</th><th>分支</th><th>回合</th></tr>${ids.map(id => { const n = E.G.by[id]; return `<tr class="${id === head ? 'hl' : ''}"><td>${id === head ? '<span class="pill v">当前</span>' : ''}</td><td class="mono">${esc(n.hash)}</td><td>${esc(n.label)}</td><td class="mono">${esc(n.branch || '')}</td><td class="mono">${esc(n.turn)}</td></tr>`; }).join('')}</table>`;
}

