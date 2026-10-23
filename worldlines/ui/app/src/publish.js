/* 发布到自由区(niko 10-16 · core/template_publish):书架抽屉里原型的「提交审查」换成真的 —— 用 Worldlines 账号把这个模板发到 Hub 自由区。
   检查(密钥 · lint · 四语卡面 · 封面)和上传都在引擎里(GET / POST /api/v1/local/templates/<id>/publish);这里只显示结果:
   作品编号(ref)· 状态 · 驳回 / 下架理由;没登录 = 点一下用浏览器登录(POST /api/v1/local/account/login)。之后可以撤下 / 申请进默认区。 */
(function () {
  const PB = window.PUBLISH = { tid: null, st: null, busy: '', msg: '', err: null, problems: null }
  const lang = () => { let v = 'zh'; try { v = localStorage.getItem('wl-local-lang') || 'zh' } catch { /* private window */ } return /^(zh|en|ja|ko)/.test(v) ? v.slice(0, 2) : 'zh' }
  const W = {
    zh: { h: '发布到自由区', p: '用 Worldlines 账号发布:检查通过就直接公开在 Hub 自由区(先上后管),大家能下载到本地玩;之后可以申请进默认区。', go: '用账号发布到自由区', again: '发布新版本', busy: '正在检查并上传…', checking: '正在检查…',
      ok: '检查都过了', fix: '还要改', signin: '还没登录 Worldlines 账号', signGo: '用浏览器登录', signWait: '在浏览器里登录完,回到这里', ref: '作品编号', pub: '公开中 · 自由区', pubDef: '公开中 · 默认区', draft: '已撤下', pend: '申请默认区 · 审核中', rej: '默认区申请被驳回', down: '被管理员下架', why: '理由',
      unpub: '撤下', apply: '申请进默认区', go2: '去改 ↗', rev: n => `第 ${n} 版`, off: '发布为官方', offP: '官方账号:发到默认区(作品编号 = 模板 id),登录的本地玩家就能获取;每次发布前先把版本号调高。' },
    en: { h: 'Publish to the Free Zone', p: 'Publish with your Worldlines account: once the checks pass it is public in the Hub Free Zone right away (moderated after), and anyone can download it to play locally. You can apply for the Default Zone later.', go: 'Publish to the Free Zone', again: 'Publish a new version', busy: 'Checking and uploading…', checking: 'Checking…',
      ok: 'All checks pass', fix: 'To fix', signin: 'Not signed in to Worldlines', signGo: 'Sign in in the browser', signWait: 'Finish signing in in the browser, then come back', ref: 'Work id', pub: 'Public · Free Zone', pubDef: 'Public · Default Zone', draft: 'Taken off', pend: 'Default Zone · in review', rej: 'Default Zone application rejected', down: 'Taken down by an admin', why: 'Reason',
      unpub: 'Take off', apply: 'Apply for the Default Zone', go2: 'Fix ↗', rev: n => `revision ${n}`, off: 'Publish as official', offP: 'Official account: to the Default Zone (work id = template id), where signed-in local players can get it. Raise the version before each publish.' },
    ja: { h: 'フリーエリアに公開', p: 'Worldlines アカウントで公開します。チェックを通ればすぐ Hub のフリーエリアに公開され(管理はあとから)、だれでもダウンロードしてローカルで遊べます。あとでデフォルトエリアに申請できます。', go: 'アカウントでフリーエリアに公開', again: '新しい版を公開', busy: 'チェックしてアップロード中…', checking: 'チェック中…',
      ok: 'チェックはすべて通過', fix: '直すところ', signin: 'Worldlines にログインしていません', signGo: 'ブラウザでログイン', signWait: 'ブラウザでログインを済ませてから戻ってください', ref: '作品 ID', pub: '公開中 · フリーエリア', pubDef: '公開中 · デフォルトエリア', draft: '取り下げ済み', pend: 'デフォルトエリア申請 · 審査中', rej: 'デフォルトエリア申請は差し戻し', down: '管理者により非公開', why: '理由',
      unpub: '取り下げる', apply: 'デフォルトエリアに申請', go2: '直す ↗', rev: n => `第 ${n} 版`, off: '公式として公開', offP: '公式アカウント:デフォルトエリアに公開します(作品 ID = テンプレート id)。ログインしたローカルのプレイヤーが入手できます。公開のたびに先にバージョンを上げてください。' },
    ko: { h: '자유 구역에 공개', p: 'Worldlines 계정으로 공개합니다. 검사를 통과하면 바로 Hub 자유 구역에 공개되고(관리는 나중에), 누구나 내려받아 로컬에서 플레이할 수 있습니다. 나중에 기본 구역을 신청할 수 있습니다.', go: '계정으로 자유 구역에 공개', again: '새 버전 공개', busy: '검사하고 올리는 중…', checking: '검사 중…',
      ok: '검사를 모두 통과', fix: '고칠 것', signin: 'Worldlines에 로그인하지 않았습니다', signGo: '브라우저로 로그인', signWait: '브라우저에서 로그인을 마치고 돌아오세요', ref: '작품 ID', pub: '공개 중 · 자유 구역', pubDef: '공개 중 · 기본 구역', draft: '내림', pend: '기본 구역 신청 · 심사 중', rej: '기본 구역 신청 반려', down: '관리자가 내림', why: '사유',
      unpub: '내리기', apply: '기본 구역 신청', go2: '고치기 ↗', rev: n => `${n}번째 버전`, off: '공식으로 공개', offP: '공식 계정: 기본 구역에 공개합니다(작품 ID = 템플릿 id). 로그인한 로컬 플레이어가 받을 수 있습니다. 공개할 때마다 먼저 버전을 올리세요.' },
  }
  const w = k => (W[lang()] || W.zh)[k] ?? W.zh[k]
  const send = async (method, path, body) => {
    const r = await fetch(V3.url(path), { method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) }).catch(() => null)
    const b = r ? await r.json().catch(() => ({})) : {}
    return { ok: !!(r && r.ok), status: r ? r.status : 0, body: b || {} }
  }
  const redraw = () => { if (S.screen === 'cat') renderCat() }
  async function load(tid) {
    PB.busy = 'checking'; redraw()
    const r = await send('GET', V3.tplUrl(tid, `publish?lang=${lang()}`))
    if (PB.tid !== tid) return
    PB.busy = ''
    PB.st = r.ok ? r.body : null
    PB.problems = r.ok ? (r.body.checks || {}).problems || [] : null
    if (!r.ok) PB.err = r.body.message || `${r.status}`
    redraw()
  }
  async function publish(official = false) {   // official(10-17):「发布为官方」→ 默认区(引擎 template_publish.publish_official)
    const tid = PB.tid
    PB.busy = 'busy'; PB.msg = ''; PB.err = null; redraw()
    const r = await send('POST', V3.tplUrl(tid, 'publish'), { lang: lang(), ...(official ? { official: true } : {}) })
    PB.busy = ''
    if (r.ok) { PB.msg = r.body.message || '✓'; await load(tid); PB.msg = r.body.message || '✓'; loadWorks() }
    else { PB.err = r.body.message || `${r.status}`; if (r.body.problems) PB.problems = r.body.problems; if (r.status === 401 && PB.st) PB.st.signed_in = false }
    redraw()
  }
  async function act(sub, id) {
    PB.busy = 'busy'; redraw()
    const r = await send('POST', `/api/v1/local/hub/${sub}`, { id, lang: lang() })
    PB.busy = ''
    if (r.ok) PB.msg = r.body.message || '✓'; else PB.err = r.body.message || `${r.status}`
    await load(PB.tid); if (r.ok) loadWorks()
    if (r.ok) PB.msg = r.body.message || '✓'; else PB.err = r.body.message || `${r.status}`
    redraw()
  }
  async function login() {
    await send('POST', '/api/v1/local/account/login')
    PB.msg = w('signWait'); redraw()
    const until = Date.now() + 320000   // 引擎那边等 300 秒(local_login);以前 180 秒就不问了,登完也不知道(10-17)
    const tick = async () => { const a = await send('GET', '/api/v1/local/account'); if (a.body.signed_in) { PB.msg = ''; return load(PB.tid) } if (Date.now() < until && a.body.login === 'running') { setTimeout(tick, 2000) } else if (a.body.login_error) { PB.err = a.body.login_error; redraw() } }
    setTimeout(tick, 2000)
  }
  // → [[文字, 颜色], …] + 理由:公开状态一枚;申请默认区的审核另起一枚(审核期间作品照常在自由区公开)
  function state(wk) {
    const rv = wk.review || {}
    if (wk.takedown) return [[[w('down'), 'rust']], wk.takedown.reason]
    const chips = [wk.status === 'published' ? [wk.zone === 'reviewed' ? w('pubDef') : w('pub'), 'sage'] : [w('draft'), '']]
    if (rv.state === 'pending') chips.push([w('pend'), 'blue'])
    if (rv.state === 'rejected') chips.push([w('rej'), 'rust'])
    return [chips, rv.state === 'rejected' ? rv.note : '']
  }
  function panel() {
    const st = PB.st, wk = st && st.work, probs = PB.problems || []
    const head = `<div class="tag" style="margin:14px 0 2px">${w('h')}</div><p class="sub" style="font-size:12.5px;margin:2px 0 6px">${w('p')}</p>`
    if (PB.busy === 'checking' && !st) return `<div class="pubbox">${head}<p class="sub">${w('checking')}</p></div>`
    const sg = wk ? state(wk) : null
    const work = wk ? `<ul class="sh-list"><li><span class="n">◆</span><div style="flex:1"><b>${sg[0].map(([l, c]) => `<span class="chip ${c}">${esc(l)}</span>`).join(' ')}</b><small class="mono">${w('ref')} · ${esc(wk.ref)}${wk.revision ? ` · ${esc(w('rev')(wk.revision))}` : ''}</small>${sg[1] ? `<small>${w('why')}:${esc(sg[1])}</small>` : ''}</div>
      <div class="row" style="gap:4px">${wk.status === 'published' ? `<button class="chip" data-pub-unpub="${esc(wk.id)}">${w('unpub')}</button>` : ''}${wk.status === 'published' && wk.zone !== 'reviewed' && (wk.review || {}).state !== 'pending' ? `<button class="chip" data-pub-apply="${esc(wk.id)}">${w('apply')}</button>` : ''}</div></li></ul>` : ''
    const checks = st ? (probs.length ? `<div class="tag" style="margin:8px 0 2px">${w('fix')} · ${probs.length}</div><ul class="sh-list">${probs.map((p, i) => `<li><span class="n">${String(i + 1).padStart(2, '0')}</span><div style="flex:1"><b>${esc(p.message)}</b>${(p.items || []).map(x => `<small class="mono">${esc(x.code)} · ${esc(x.where || '')} · ${esc(x.message || '')}</small>`).join('')}<small class="mono">${esc(p.code)}</small></div>${p.code === 'lint' || p.code === 'cover' || p.code === 'langs' ? `<button class="chip" data-go="tpl">${w('go2')}</button>` : ''}</li>`).join('')}</ul>`
      : `<ul class="sh-list"><li><span class="n">✓</span><div><b>${w('ok')}</b></div></li></ul>`) : ''
    const sign = st && !st.signed_in ? `<div class="row" style="margin-top:6px"><span class="chip rust">${w('signin')}</span><button class="chip lime" data-pub-login>${w('signGo')}</button></div>` : ''
    const msg = PB.err ? `<p class="sub" style="color:var(--rust,#d77)">${esc(PB.err)}</p>` : PB.msg ? `<p class="sub">${esc(PB.msg)}</p>` : ''
    const off = st && st.official ? `<p class="sub" style="font-size:12.5px;margin:6px 0 0">${w('offP')}</p>` : ''
    return `<div class="pubbox">${head}${work}${checks}${sign}${off}${msg}</div>`
  }
  function button() {
    const st = PB.st, can = st && st.signed_in && st.checks && st.checks.ok && !PB.busy && !(st.work && st.work.takedown)
    const off = st && st.official ? `<button data-pub-official ${can ? '' : 'disabled'}>${w('off')}</button>` : ''   // 只有官方账号看得到(引擎问 /v1/me)
    return `<button class="p" data-pub-go ${can ? '' : 'disabled'}>${PB.busy === 'busy' ? w('busy') : st && st.work ? w('again') : w('go')}</button>${off}`
  }
  // 一览卡片上的状态 = 真实状态(10-16,原来一律「只在本地」):默认区(官方世界)· 自由区公开中 · 审核中 · 被下架 · 已撤下;
  //   账号里的作品读一次 /api/v1/local/hub/mine(没登录 = 读不到,只标默认区),发布 / 撤下 / 申请之后再读
  Object.assign(STATUS, { def: ['默认区', 'sage'], free: ['自由区 · 公开中', 'sage'], pend: ['自由区 · 申请默认区中', 'blue'], down: ['被下架', 'rust'], off: ['已撤下', ''] })
  PB.works = null
  async function loadWorks() {
    const r = await send('GET', `/api/v1/local/hub/mine?lang=${lang()}`)
    PB.works = r.ok ? r.body.works || [] : []
    redraw()
  }
  const workState = id => {
    const t = (window.LIVE && LIVE.templates || []).find(x => x.id === id)
    if (t && t.zone === 'reviewed') return 'def'
    const wk = (PB.works || []).filter(w => w.source === id).sort((a, b) => String(a.updated_at || '').localeCompare(String(b.updated_at || ''))).pop()
    if (!wk) return null
    if (wk.takedown) return 'down'
    if (wk.status !== 'published') return 'off'
    return (wk.review || {}).state === 'pending' ? 'pend' : wk.zone === 'reviewed' ? 'def' : 'free'
  }
  const _catalog = catalog
  catalog = function () {
    if (PB.works === null) { PB.works = []; loadWorks() }
    return _catalog().map(w => { const st = w.status === 'local' && workState(w.id); return st ? { ...w, status: st } : w })
  }
  const _shelf = renderShelf
  renderShelf = function (list) {
    _shelf(list)
    const sh = $('#shelf')
    if (!sh || !sh.classList.contains('on') || !window.LIVE || !LIVE.templates.some(t => t.id === S.sel)) return
    sh.querySelector('[data-submit]')?.remove()   // 原型的假按钮
    if (PB.tid !== S.sel) { Object.assign(PB, { tid: S.sel, st: null, msg: '', err: null, problems: null }); load(S.sel) }
    sh.querySelector('.scroll')?.insertAdjacentHTML('beforeend', panel())
    sh.querySelector('.sh-act')?.insertAdjacentHTML('afterbegin', button())
  }
  document.addEventListener('click', e => {
    const q = s => e.target.closest(s); let t
    if (q('[data-pub-go]')) { e.stopPropagation(); return publish() }
    if (q('[data-pub-official]')) { e.stopPropagation(); return publish(true) }
    if (q('[data-pub-login]')) { e.stopPropagation(); return login() }
    if ((t = q('[data-pub-unpub]'))) { e.stopPropagation(); return act('unpublish', t.dataset.pubUnpub) }
    if ((t = q('[data-pub-apply]'))) { e.stopPropagation(); return act('submit', t.dataset.pubApply) }
  }, true)
})();
