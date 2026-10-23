/* 第 1 步:能用起来 —— 设置(模型 · 密钥 · 生图 · 语言)· 首次启动引导 · 存档(继续 / 新开 / 删除)。
   接口全是引擎现成的:/api/v1/local/settings* · /api/v1/play/saves · /api/v1/play/session。 */
(function () {
  const L = window.LIVE;
  const LANGS = [['zh', '中文'], ['en', 'English'], ['ja', '日本語'], ['ko', '한국어']];
  const lang = () => { try { return localStorage.getItem('wl-local-lang') || 'zh'; } catch { return 'zh'; } };
  const setLang = v => { try { localStorage.setItem('wl-local-lang', v); } catch { /* storage off */ } };
  const SET = window.SETTINGS = { open: false, data: null, saves: [], busy: '', msg: '', keyFor: null, testRes: {} };

  /* ---------- 数据 ---------- */
  async function loadSettings() { SET.data = await V3.j('/api/v1/local/settings').catch(() => null); }
  async function loadSaves() { const d = await V3.j('/api/v1/play/saves').catch(() => ({ saves: [] })); SET.saves = d.saves || []; L.slug = (SET.saves.find(s => s.in_memory) || {}).session_id || L.slug; }
  const anyModel = () => !!(SET.data && SET.data.presets.some(p => p.available));
  const send = (method, path, body) => fetch(V3.url(path), { method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }).then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || `${r.status}`); return j; });

  /* ---------- 绑定一局:存档(session_id)或模板(tpl--id) ---------- */
  L.play = async function ({ slug, preset }) {
    L.binding = true; S.screen = 'test'; render();
    try {
      await V3.post('/api/v1/play/session', { slug, preset: preset || undefined, output_lang: lang() }); E.relisten && E.relisten();
      await E.load(); L.bound = (V3.template && V3.template.id) || L.bound; L.tpl = L.bound; L.mapPicked = false;
      await loadSaves();
      if (window.LIVE_buildMap) window.LIVE_buildMap();
    } catch (e) { L.err = '开局失败:' + (e.message || e); }
    L.binding = false; render();
  };

  /* ---------- 设置抽屉 ---------- */
  function drawer() {
    const d = SET.data;
    if (!d) return `<div class="sub">读设置……</div>`;
    const img = d.image || {};
    const preset = p => {
      const t = SET.testRes[p.id];
      return `<li class="setrow ${p.available ? '' : 'off'}"><span class="dot ${p.available ? 'ok' : ''}"></span>
        <div><b>${esc(p.display.replace(/\s*✓$/, ''))}</b><small>${p.available ? '可用' : '没配密钥'}${p.from_user_config ? ' · 你自己加的' : ''}${t ? ` · ${t.ok ? `通 ${t.latency_ms || ''}ms` : '不通:' + esc(t.error || '')}` : ''}</small>
          ${SET.keyFor === p.id ? `<div class="row" style="margin-top:6px"><input class="cell" id="setKey" type="password" placeholder="粘贴 API key(只存在这台机器上)" autocomplete="off"><button class="btn p" data-setkeysave="${p.id}">存</button></div>` : ''}</div>
        <div class="row" style="gap:4px">${p.id === d.create_provider ? '<span class="chip lime">创作用</span>' : p.available ? `<button class="chip" data-setcreate="${p.id}">设为创作用</button>` : ''}
          ${p.available ? `<button class="chip" data-settest="${p.id}">测</button>` : ''}<button class="chip" data-setkey="${p.id}">${p.available ? '换 key' : '填 key'}</button></div></li>`;
    };
    return `<div class="tag">语言 · 开局时按它出叙事</div><div class="seg" style="margin:8px 0 18px">${LANGS.map(([k, l]) => `<button class="${lang() === k ? 'on' : ''}" data-setlang="${k}">${l}</button>`).join('')}</div>
      <div class="row"><div class="tag">模型</div><button class="chip" data-settestall style="margin-left:auto">${SET.busy === 'testall' ? '测试中……' : '全部测一遍'}</button></div>
      <ul class="setlist">${d.presets.map(preset).join('')}</ul>
      <details class="setmore"><summary>加一个 OpenAI 兼容的端点(本地模型 / 自建)</summary>
        <div class="setgrid"><input class="cell" id="cmId" placeholder="名字(英文,例 my-local)"><input class="cell" id="cmUrl" placeholder="base_url,例 http://127.0.0.1:11434/v1"><input class="cell" id="cmModel" placeholder="模型名"><input class="cell" id="cmKey" type="password" placeholder="key(可空)"></div>
        <button class="btn" data-setcustom style="margin-top:8px">加</button></details>
      <div class="tag" style="margin-top:20px">生图</div>
      <div class="seg" style="margin:8px 0 10px">${[['comfyui', 'ComfyUI'], ['openai', 'OpenAI'], ['none', '不生图']].map(([k, l]) => `<button class="${(img.backend || 'none') === k ? 'on' : ''}" data-setimg="${k}">${l}</button>`).join('')}</div>
      ${img.backend === 'comfyui' ? `<div class="setgrid"><input class="cell" id="imgUrl" value="${esc(img.comfyui_url || '')}" placeholder="ComfyUI 地址"><input class="cell" id="imgCkpt" value="${esc(img.comfyui_ckpt || '')}" placeholder="checkpoint"></div><button class="btn" data-setimgsave style="margin-top:8px">存</button>`
        : img.backend === 'openai' ? `<div class="setgrid"><input class="cell" id="imgKey" type="password" placeholder="${img.openai_key_set ? '已存(留空不改)' : 'OpenAI key'}"><input class="cell" id="imgModel" value="${esc(img.openai_model || '')}" placeholder="模型"></div><button class="btn" data-setimgsave style="margin-top:8px">存</button>` : ''}
      ${SET.msg ? `<div class="setmsg">${esc(SET.msg)}</div>` : ''}`;
  }
  function renderDrawer() {
    let el = $('#setdrawer');
    if (!el) { el = document.createElement('aside'); el.id = 'setdrawer'; el.className = 'shelf glass setdrawer'; document.body.appendChild(el); }
    el.classList.toggle('on', SET.open);
    if (!SET.open) return;
    el.innerHTML = `<button class="x" data-setclose aria-label="关闭">×</button><div class="tag">SETTINGS</div><h2>设置</h2>
      ${!anyModel() ? '<div class="setmsg warn">还没有能用的模型:给下面任意一个填上 key,就能开始玩</div>' : ''}<div class="scroll" style="flex:1;min-height:0">${drawer()}</div>`;
  }

  /* ---------- 存档(书架抽屉里) ---------- */
  function savesFor(tid) { return SET.saves.filter(s => s.slug === 'tpl-' + tid || s.slug === tid).sort((a, b) => (b.last_modified || 0) - (a.last_modified || 0)); }
  function savesBox(tid) {
    const list = savesFor(tid), when = t => t ? new Date(t * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
    const ps = (SET.data && SET.data.presets.filter(p => p.available)) || [];
    return `<div class="row" style="margin:4px 0 10px"><select class="btn" id="newPreset" style="flex:1;text-transform:none;letter-spacing:0">${ps.map(p => `<option value="${p.id}" ${p.id === (SET.data && SET.data.create_provider) ? 'selected' : ''}>${esc(p.display.replace(/\s*✓$/, ''))}</option>`).join('') || '<option value="">先在设置里配一个模型</option>'}</select><button class="btn p" data-savenew="${esc(tid)}">新开一局</button></div>
      <div class="tag" style="margin:14px 0 4px">存档 · ${list.length}</div>
      <ul class="sh-list">${list.slice(0, 6).map(s => `<li><span class="n">${s.in_memory ? '●' : '◦'}</span><div><b>${esc(s.feed_time || '刚开始')}${s.in_memory ? ' · 正在玩' : ''}</b><small>${esc(when(s.last_modified))} · ${esc((s.feed_tease || '').slice(0, 42))}</small></div>
        <div class="row" style="gap:4px"><button class="chip lime" data-saveplay="${esc(s.session_id)}">继续</button>${SET.confirmDel === s.session_id ? `<button class="chip rust" data-savedelok="${esc(s.session_id)}">确认删除</button>` : `<button class="chip" data-savedel="${esc(s.session_id)}">删</button>`}</div></li>`).join('') || '<li><div><small>还没有存档</small></div></li>'}</ul>`;
  }

  /* ---------- 接到页面 ---------- */
  const _render = render;
  render = function () {
    _render();
    // 顶栏右侧:设置齿轮
    const ctx = $('#ctx'); if (ctx && !ctx.querySelector('[data-setopen]')) ctx.insertAdjacentHTML('beforeend', `<button class="chip ${anyModel() || !SET.data ? '' : 'rust'}" data-setopen title="设置">${SET.data && !anyModel() ? '⚙ 先配模型' : '⚙ 设置'}</button>`);
    // 首次启动:没有能用的模型 → 一览上放一张提示卡(不挡路,点了打开设置)
    let nt = $('#setupNote');
    if (S.screen === 'cat' && SET.data && !anyModel()) { if (!nt) { $('#s-cat').insertAdjacentHTML('beforeend', '<button class="note" id="setupNote" data-setopen style="left:auto;right:28px;top:72px;border:0;cursor:pointer;text-align:left">还没有能用的模型<small>点这里填一个 API key,就能开始玩</small></button>'); } }
    else if (nt) nt.remove();
    renderDrawer();
  };
  // 书架抽屉:真实模板 → 存档区替换原型的「试玩」按钮(书架自己重画时也要补上)
  const _shelf = renderShelf;
  renderShelf = function (list) {
    _shelf(list);
    const sh = $('#shelf');
    if (sh && sh.classList.contains('on') && L.templates.some(t => t.id === S.sel)) {
      const act = sh.querySelector('.sh-act'); if (act) act.querySelector('[data-go="test"]')?.remove();
      const box = sh.querySelector('.scroll'); if (box) box.insertAdjacentHTML('afterbegin', `<div class="savesbox">${savesBox(S.sel)}</div>`);
    }
  };
  document.addEventListener('click', async e => {
    const q = s => e.target.closest(s); let t;
    if (q('[data-setopen]')) { SET.open = true; SET.msg = ''; if (!SET.data) await loadSettings(); render(); return; }
    if (q('[data-setclose]')) { SET.open = false; render(); return; }
    if ((t = q('[data-setlang]'))) { setLang(t.dataset.setlang); SET.msg = '下一次开局起生效'; render(); return; }
    if ((t = q('[data-setkey]'))) { SET.keyFor = SET.keyFor === t.dataset.setkey ? null : t.dataset.setkey; render(); setTimeout(() => $('#setKey') && $('#setKey').focus(), 0); return; }
    if ((t = q('[data-setkeysave]'))) { const k = ($('#setKey') || {}).value || ''; if (!k.trim()) return; try { await send('PUT', '/api/v1/local/settings/key', { preset_id: t.dataset.setkeysave, api_key: k.trim() }); SET.msg = '存好了'; SET.keyFor = null; await loadSettings(); } catch (err) { SET.msg = '没存上:' + err.message; } render(); return; }
    if ((t = q('[data-settest]'))) { const id = t.dataset.settest; SET.testRes[id] = { ok: false, error: '测试中……' }; render(); try { const r = await send('POST', '/api/v1/local/settings/test', { preset_id: id }); SET.testRes[id] = { ok: r.ok !== false && !r.error, error: r.error, latency_ms: r.latency_ms }; } catch (err) { SET.testRes[id] = { ok: false, error: err.message }; } render(); return; }
    if (q('[data-settestall]')) { SET.busy = 'testall'; render(); try { const r = await send('POST', '/api/v1/local/settings/test-all', {}); (r.results || []).forEach(x => (SET.testRes[x.id] = x)); } catch (err) { SET.msg = err.message; } SET.busy = ''; render(); return; }
    if ((t = q('[data-setcreate]'))) { await send('PUT', '/api/v1/local/settings/create-provider', { preset_id: t.dataset.setcreate }).catch(err => (SET.msg = err.message)); await loadSettings(); render(); return; }
    if (q('[data-setcustom]')) { const v = id => ($('#' + id) || {}).value || ''; if (!v('cmId') || !v('cmUrl') || !v('cmModel')) { SET.msg = '名字、base_url、模型名都要填'; render(); return; }
      try { await send('PUT', '/api/v1/local/settings/custom-model', { id: v('cmId').trim(), base_url: v('cmUrl').trim(), model: v('cmModel').trim(), api_key: v('cmKey').trim() || undefined }); SET.msg = '加好了'; await loadSettings(); } catch (err) { SET.msg = '没加上:' + err.message; } render(); return; }
    if ((t = q('[data-setimg]'))) { await send('PUT', '/api/v1/local/settings/image', { backend: t.dataset.setimg }).catch(err => (SET.msg = err.message)); await loadSettings(); render(); return; }
    if (q('[data-setimgsave]')) { const v = id => ($('#' + id) || {}).value; const patch = {}; if (v('imgUrl') !== undefined) patch.comfyui_url = v('imgUrl'); if (v('imgCkpt') !== undefined) patch.comfyui_ckpt = v('imgCkpt'); if (v('imgKey')) patch.openai_key = v('imgKey'); if (v('imgModel') !== undefined) patch.openai_model = v('imgModel');
      try { const r = await send('PUT', '/api/v1/local/settings/image', patch); SET.msg = r.configured ? '存好了' : '存了,但还不完整'; await loadSettings(); } catch (err) { SET.msg = err.message; } render(); return; }
    if ((t = q('[data-saveplay]'))) { L.play({ slug: t.dataset.saveplay }); return; }
    if ((t = q('[data-savenew]'))) { L.play({ slug: `tpl--${t.dataset.savenew}`, preset: ($('#newPreset') || {}).value }); return; }
    if ((t = q('[data-savedel]'))) { SET.confirmDel = t.dataset.savedel; renderCat(); return; }
    if ((t = q('[data-savedelok]'))) { await send('DELETE', `/api/v1/play/saves/${encodeURIComponent(t.dataset.savedelok)}`).catch(err => (SET.msg = err.message)); SET.confirmDel = null; await loadSaves(); renderCat(); return; }
  });

  // 首次启动:没有任何能用的模型 → 直接打开设置
  // ?settings=1:别处(小手机「还没选模型 → 去设置选模型」)直接打开设置
  (async () => { await Promise.all([loadSettings(), loadSaves()]); if (/[?&]settings=1(&|$)/.test(location.search)) SET.open = true; render(); })();
})();
