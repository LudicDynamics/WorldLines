/* 拍的展示注册表(10-08 引擎开源 · 编排私有,docs/planning/OPEN-ENGINE-PRIVATE-ORCHESTRATION-1008.md)。
   开源版只认通用的「回合」:一句话 → 主持叙事 → 落账。别的拍由私有层注册
   (worldlines/private/ui/*.js,构建时有就带上):标签、颜色、分隔条、计划板、建议词都从这里取,界面不写死。
   没注册的拍,用编排图里的节点名。 */
window.BEATS = {
  kinds: { opening: { label: T('开场') }, turn: { label: T('回合') } },
  label(k) { return (this.kinds[k] && this.kinds[k].label) || String(k || ''); },
  // 回合进行中的一段流式文字:class + 「谁 · 在干什么」
  seg(beat, last) { return { cls: 'res', who: T('主持') + (last ? ' · ' + T('正在写') : '') }; },
  // 两段之间的分隔(换拍时)
  divider(prev, next) { return ''; },
  // 对话里一条已落定的记录
  you(f) { return T('你'); },
  host(f) { return T('主持'); },
  hostCls(f) { return ''; },
  narrDivider(f) { return ''; },
  narrWho(f) { return this.kinds[f.kind] ? this.label(f.kind) : T('叙事'); },
  adv: {},                                  // 谁推进的这一拍(advanced_by → 显示名)
  board: null,                              // (b) → html:进行中的计划(有这种拍的玩法才有)
  chips(s, out) { return out; },            // 输入框下的建议词
  placeholder: T('说你想做什么'),
  phase: null,                              // (raw chunk) → 这段属于哪一拍(引擎在流里写的阶段行)
  strip(t) { return t; },                   // 从流式文字里去掉阶段行
  tools: {},                                // 工具表:某种拍自带、规则包里没有的工具(op → 说明)
  events: {},                               // 前端台:拍事件的显示名(kind → 名字)
  nodes: {},                                // 前端台:编排节点的显示名
  demoScript: null,                         // 编排台演示用的脚本(按图名)
  loaded: [],                               // 构建时带上的私有层文件 / 'engine' = 引擎给了声明
};

// 引擎给的声明(玩法包的 ui.beats,GET /api/v1/play/engine/beat-kinds;docs/planning/APP-REQUESTS-PACK-BEATS-1009.md R2)
// → 上面这套函数。包是拍的唯一来源:有声明就以它为准,换到没声明的局就退回构建时的样子。没给 / 空的 → 返回 false、什么都不动。
(() => {
  const B = window.BEATS;
  let base = null;   // 构建时的样子(含私有层登记的):第一次用到时再拍,那时所有脚本都加载完了
  const snap = () => base || (base = { ...B, kinds: { ...B.kinds }, loaded: [...B.loaded] });
  const DIV = t => `<div class="beatdiv"><span>${esc(t)}</span></div>`;
  B.reset = () => { const b = snap(); Object.assign(B, { ...b, kinds: { ...b.kinds }, loaded: [...b.loaded] }); };
  B.fromSpec = spec => {
    const K = spec && spec.kinds;
    snap();
    if (!K || !Object.keys(K).length) { if (B.loaded.includes('engine')) B.reset(); return false; }
    B.reset();
    const start = spec.start && K[spec.start] ? spec.start : Object.keys(K)[0], S = K[start];
    for (const [k, v] of Object.entries(K)) B.kinds[k] = { ...(B.kinds[k] || {}), label: v.label || k, noFiles: v.no_files, noWrites: v.no_writes };
    const res = k => (K[k] || {}).tone === 'res';
    B.seg = (beat, last) => { const k = beat || start, v = K[k] || {};
      return res(k) ? { cls: 'res', who: `${v.live || B.label(k)} · ${last ? T('正在写') : T('叙事')}` }
        : { cls: `host ${v.tone || ''}`.trim(), who: (v.live || B.label(k)) + (last ? ' · ' + T('正在说') : '') }; };
    B.divider = (prev, next) => { const t = ((K[next] || {}).divider_from || {})[prev]; return t ? DIV(t) : ''; };
    B.you = f => T('你') + ' · ' + ((K[f.beat] || {}).you || T('提出'));
    B.host = f => (K[f.beat || start] || {}).host || (K[f.beat || start] || {}).live || T('主持');
    B.hostCls = f => (K[f.beat || start] || {}).tone || '';
    B.narrDivider = f => { const d = (K[f.kind] || {}).divider_from; const t = d && (d[start] || Object.values(d)[0]); return t ? DIV(t) : ''; };
    B.narrWho = f => K[f.kind] ? (K[f.kind].narr || B.label(f.kind)) : T('叙事');
    B.adv = Object.assign({}, ...Object.values(K).map(v => v.advanced_by || {}));
    B.chips = (s, out) => { if (s.board) out.push(...(S.chips_when_board || [])); out.push(...(S.chips || [])); return out; };
    B.placeholder = S.placeholder || snap().placeholder;
    B.board = S.board ? b => { const bd = S.board, rows = Object.entries(b.board || {}), checks = (b.checks || []).map(c => c.text || [c.who, c.attr, c.dc, c.why].filter(Boolean).join(' '));
      return `<div class="glass box"><span class="tag">${esc(bd.title || B.label(start))}</span>${rows.map(([k, v]) => `<div class="r"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('') || `<div class="sub" style="font-size:12.5px">${esc(bd.empty || '')}</div>`}
        ${checks.map(c => `<div class="r"><span>${esc(c)}</span><span>${esc(bd.check || '')}</span></div>`).join('')}
        <div class="row" style="margin-top:8px">${(bd.actions || []).map((a, i) => `<button class="btn ${i ? '' : 'p'}" data-lsay="${esc(a.say)}">${esc(a.label || a.say)}</button>`).join('')}</div></div>`; } : null;
    B.tools = Object.assign({}, ...Object.entries(K).map(([k, v]) => Object.fromEntries(Object.entries(v.tools || {}).map(([op, doc]) => [op, { kind: 'tool', sync: true, fields: '', validator: '', src: 'engine · ' + B.label(k), doc }]))));
    B.events = Object.fromEntries(Object.keys(K).map(k => [`${k}.beat`, B.label(k)]));
    B.nodes = Object.fromEntries(Object.keys(K).map(k => [k, B.label(k)]));
    B.loaded = [...B.loaded.filter(x => x !== 'engine'), 'engine'];
    return true;
  };
})();
