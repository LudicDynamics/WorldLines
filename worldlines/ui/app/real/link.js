// ═══════════════════════════════════════════════════════════════════
// 真引擎版「组装 · Lint」数据:Mock 的 link.js 页面原样,数据换成这一局所用 template 的真实内容。
//   ui(包 < mixins < 模板 的槽位 / 视图 / 提示词 / 配方 / 预算)· 素材槽位实例 · 聚合 lint · 契约(JSON / TS / GDScript)
//   全部来自引擎 /api/v1/local/templates/<id>/…;创作者 op 写回模板(template/author.py,全有或全无)。
//   内置模板只读 —— 「另存为新模板」后才能改;素材定稿进模板,同时镜像到 worldlines-assets/worlds/<id>/。
// ═══════════════════════════════════════════════════════════════════
V3.LINK = { tid: null, view: null, rows: [], lint: null, contract: null, ts: '', gd: '', error: null };
V3.TPL_OPS = ['register_class', 'add_slot', 'remove_slot', 'edit_prompt', 'edit_recipe', 'set_view', 'remove_view', 'set_budget', 'set_mixins', 'edit_card', 'set_mode', 'set_world_data', 'set_policy'];

V3.tplUrl = (tid, sub = '') => `/api/v1/local/templates/${encodeURIComponent(tid)}${sub ? '/' + sub : ''}`;

// 拉一遍模板的创作数据(本地引擎才有;Hub 上没有模板创作 → st.link 为空,组装页提示去本地)
V3.loadLink = async function (s) {
  const tid = V3.template && V3.template.id;
  const L = V3.LINK;
  L.tid = tid; L.error = null;
  if (!tid) { s.link = null; return; }
  try {
    const [view, assets, lint, contract, ts, gd] = await Promise.all([
      V3.j(V3.tplUrl(tid, 'ui')), V3.j(V3.tplUrl(tid, 'assets')), V3.j(V3.tplUrl(tid, 'lint')), V3.j(V3.tplUrl(tid, 'contract')),
      fetch(V3.url(V3.tplUrl(tid, 'contract?fmt=ts'))).then(r => (r.ok ? r.text() : '')), fetch(V3.url(V3.tplUrl(tid, 'contract?fmt=gd'))).then(r => (r.ok ? r.text() : '')),
    ]);
    Object.assign(L, { view, rows: assets.slots || [], lint, contract, ts, gd });
  } catch (e) {
    L.error = String(e && e.message || e); s.link = null; return;
  }
  const u = L.view.ui || {};
  const prev = s.link || {};
  s.link = {
    tid, writable: !!L.view.writable, forkedFrom: L.view.forked_from || null,
    mixins: ['rpg', 'space', 'tick', ...(L.view.mixins || [])], available: L.view.mixins_available || [],
    slots: (u.slots || []).map(x => ({ ...x, required: x.required || 'optional', kind: x.kind || 'image' })),
    prompts: { ...(u.prompts || {}) },
    recipe: { backend: '', style: '', ...(u.recipe || {}), ran: prev.recipe?.ran || {}, lastRun: prev.recipe?.lastRun },
    views: (u.views || []).map(v => ({ ...v, title: typeof v.title === 'object' ? (v.title.zh || v.title.en || v.id) : (v.title || v.id), bind: v.bind || [], layout: v.layout || {} })),
    budget: u.budget || 20000, filled: prev.filled || {}, worldData: L.view.world_data || {},
  };
};

// 槽位实例:引擎的 slot rows → Mock 的形状 {sl, key, inst, name, img, filled, gen, stale, grown, empty}
V3.slotInstances = function (s) {
  const L = s.link; if (!L) return [];
  const out = [];
  for (const r of V3.LINK.rows) {
    if (r.cls === 'card' || r.cls === 'ending') continue;  // 模板级(封面 / 结局图)不在类槽位里
    const sl = L.slots.find(x => x.cls === r.cls && x.slot === r.name) || { cls: r.cls, slot: r.name, kind: r.kind || 'image', required: r.required || 'optional', recipe: r.recipe };
    const key = r.slot;
    if (r.empty) { out.push({ sl, key, inst: '∅', name: T('（还没有实例）'), filled: true, empty: true }); continue; }
    out.push({ sl, key, inst: r.inst, name: r.label || r.inst, img: r.have ? `slot:${key}` : null, filled: !!r.have, gen: false, stale: !!r.stale, grown: !!r.grown,
      prompt: r.prompt, row: r });
  }
  return out;
};

// 检查:引擎的聚合 lint(meta / 引用 / 包 / 角色 / 提示词 / 剧情 / 闭环 / 素材 / token)→ Mock 的四格
V3.linkChecks = function (s) {
  const R = [], lint = V3.LINK.lint;
  if (!lint) return [{ cat: 'schema', lvl: 'warn', text: V3.LINK.error ? T('拿不到模板检查:{e}', { e: V3.LINK.error }) : T('检查结果加载中…'), fix: '' }];
  const cat = code => (/^asset/.test(code) ? 'asset' : /^prompt/.test(code) ? 'prompt' : /^token/.test(code) ? 'token' : 'schema');
  for (const p of lint.problems || []) {
    if (p.code === 'v3.lint' && p.where && /^(asset|prompt|token|schema)/.test(p.where)) continue;
    R.push({ cat: cat(p.code), lvl: p.level === 'block' ? 'block' : 'warn', text: `${p.msg}${p.where ? `  · ${p.where}` : ''}`, fix: '' });
  }
  const ok = { schema: T('模板 {tid} · {n} 个视图 · 引用的变量和 op 全部解析得到', { tid: V3.LINK.tid, n: s.link?.views.length || 0 }), asset: T('必需槽位全部就绪'), prompt: T('{n} 段提示词的占位符全部可解析', { n: Object.keys(s.link?.prompts || {}).length }), token: T('每回合 token 在预算内') };
  for (const k of Object.keys(ok)) if (!R.some(r => r.cat === k)) R.push({ cat: k, lvl: 'ok', text: ok[k], fix: '' });
  return R;
};

// 配方图的层 = 模板里有地图槽位的层级
V3.levels = () => { const ls = [...new Set(V3.LINK.rows.filter(r => r.cls === 'level').map(r => r.inst))]; return ls.length ? ls : ['world']; };

// 契约:引擎生成(worldlines.contract/0.1;TS / GDScript 也由引擎出,与 Godot 端同源)
V3.buildContract = function () {
  const c = V3.LINK.contract || { version: '—', hash: '—', vars: [], classes: [], ops: [], triggers: [] };
  return { ...c, hooks: c.hooks || c.triggers || [] };
};

// 创作者 op → 模板(全有或全无)。set_policy 同时改这一局(立刻生效)。返回 Promise<{ok, applied, refused}>
V3.tplOps = async function (ops) {
  const L = V3.LINK;
  if (!L.tid) throw new Error(T('这一局不是从模板开的'));
  const r = await fetch(V3.url(V3.tplUrl(L.tid, 'ops')), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ops }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && !d.refused) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
};

// 素材:生成(引擎配置的图片后端)/ 上传
V3.fillSlot = async function (slot, prompt) {
  const L = V3.LINK;
  const r = await fetch(V3.url(V3.tplUrl(L.tid, 'assets/generate')), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slot, ...(prompt ? { prompt } : {}) }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d.slot;
};
V3.uploadSlot = async function (slot, file) {
  const L = V3.LINK;
  const ext = '.' + (file.name.split('.').pop() || 'png').toLowerCase();
  const r = await fetch(V3.url(V3.tplUrl(L.tid, `assets/upload?slot=${encodeURIComponent(slot)}&ext=${encodeURIComponent(ext)}`)), { method: 'POST', body: file });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d.slot;
};

// 另存为新模板(世界页「＋ 新建世界」/ 组装页的只读提示):fork → 用新模板开一局
V3.forkTemplate = async function (title) {
  const base = V3.template && V3.template.id;
  if (!base) throw new Error(T('这一局不是从模板开的'));
  const id = `${base.replace(/-f[a-z0-9]{4}$/, '').slice(0, 42)}-f${Date.now().toString(36).slice(-4)}`;  // 另存的再另存:换掉上一次的 -fXXXX
  const r = await fetch(V3.url(V3.tplUrl(base, 'fork')), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, title: title || undefined }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d.template;
};
