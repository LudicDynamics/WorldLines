/* 反馈(10-25 闭环检查:PyPI 引擎 / 本机网页没有反馈入口,只有 iOS 和 neonrp 站页脚有)
   顶栏一个「反馈」→ 一句话(可空)→ 引擎 POST /api/v1/local/feedback → 平台 data /v1/feedback/hub(引擎用自己的账号会话,
   没登录用游客令牌;页面不拿令牌)。带当前页面、当前模板 / 存档 id、最近 5 条报错;不带存档内容和 key。 */
(function () {
  const FB = { open: false, busy: false, msg: '' };
  const ERRS = [];
  const note = s => { ERRS.push(String(s || '').slice(0, 300)); ERRS.splice(0, ERRS.length - 5); };
  addEventListener('error', e => note(e.message || e.error));
  addEventListener('unhandledrejection', e => note((e.reason && e.reason.message) || e.reason));
  const lang = () => { try { return localStorage.getItem('wl-local-lang') || window.WLANG || 'zh'; } catch { return window.WLANG || 'zh'; } };
  const LOCALE = { zh: 'zh-CN', en: 'en', ja: 'ja', ko: 'ko' };

  function drawer() {
    let el = $('#fbdrawer');
    if (!el) { el = document.createElement('aside'); el.id = 'fbdrawer'; el.className = 'shelf glass setdrawer'; document.body.appendChild(el); }
    el.classList.toggle('on', FB.open);
    if (!FB.open) return;
    if (el.querySelector('#fbText')) { const m = el.querySelector('.setmsg'); if (m) { m.textContent = FB.msg; m.hidden = !FB.msg; } el.querySelector('[data-fbsend]').disabled = FB.busy; return; }
    el.innerHTML = `<button class="x" data-fbclose aria-label="${T('关闭')}">×</button><div class="tag">FEEDBACK</div><h2>${T('反馈')}</h2>
      <div class="sub" style="margin:6px 0 10px">${T('说说哪里不对、卡在哪。会带上当前页面和最近的报错,不带存档和 key。')}</div>
      <textarea id="fbText" class="cell" rows="6" maxlength="1000" style="width:100%;box-sizing:border-box;resize:vertical" placeholder="${T('写在这里(可以留空)')}"></textarea>
      <div class="row" style="gap:6px;margin-top:10px"><button class="btn" data-fbsend ${FB.busy ? 'disabled' : ''}>${T('发送')}</button></div>
      <div class="setmsg" style="margin-top:8px" ${FB.msg ? '' : 'hidden'}>${esc(FB.msg)}</div>`;
  }

  async function send() {
    if (FB.busy) return;
    FB.busy = true; FB.msg = ''; drawer();
    const tpl = (typeof V3 !== 'undefined' && V3.template && V3.template.id) || (window.LIVE && (LIVE.bound || LIVE.tpl)) || '';
    const body = { text: (($('#fbText') || {}).value || '').slice(0, 1000), template_id: tpl || undefined, save_id: (window.LIVE && LIVE.slug) || undefined,
      page: location.pathname + location.hash, errors: ERRS.slice(), locale: LOCALE[lang()] || undefined };
    let ok = false;
    try { const r = await fetch('/api/v1/local/feedback', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); ok = r.ok; } catch { ok = false; }
    FB.busy = false;
    if (ok) { const tx = $('#fbText'); if (tx) tx.value = ''; FB.msg = T('发出去了,谢谢'); drawer(); return; }
    FB.msg = T('没发出去,稍后再试'); drawer();
  }

  const _render = render;
  render = function () {
    _render();
    const ctx = $('#ctx'); if (ctx && !ctx.querySelector('[data-fbopen]')) ctx.insertAdjacentHTML('beforeend', `<button class="chip" data-fbopen title="${T('反馈')}">${T('反馈')}</button>`);
    drawer();
  };
  document.addEventListener('click', e => {
    const q = s => e.target.closest(s);
    if (q('[data-fbopen]')) { FB.open = !FB.open; FB.msg = ''; if (window.SETTINGS) SETTINGS.open = false; render(); if (FB.open) setTimeout(() => $('#fbText') && $('#fbText').focus(), 0); return; }
    if (q('[data-fbclose]')) { FB.open = false; render(); return; }
    if (q('[data-fbsend]')) { send(); }
  });
  window.FEEDBACK_LOCAL = FB;
})();
