/* 捏人(面板玩家,10-14):模板的 player.builder 声明字段和规则,这一屏照着渲染,不 fit 任何字段。
   引擎 template/builder.py 是唯一的规则:这里的检查只为了提示(剩余点数、还差什么),开局时引擎再校验一遍,不过就 400 不开局。
   入口:BUILDER.start(模板 id, 语言) —— 模板没声明 = 照旧直接开局;声明了 = 先捏人 → 选同伴 → 开场。
   BUILDER.panel(card) 是同一张面板,游玩中右栏的「面板」页签用它画这一局的玩家卡。 */
(function () {
  const LANGS = ['zh', 'en', 'ja', 'ko'];
  const lang = () => { const q = new URLSearchParams(location.search).get('lang'); let v = q || ''; if (!v) { try { v = localStorage.getItem('wl.hub.lang') || localStorage.getItem('wl-local-lang') || ''; } catch { /* no storage */ } }
    v = String(v || navigator.language || 'zh').slice(0, 2).toLowerCase(); return LANGS.includes(v) ? v : 'zh'; };
  const T = {
    zh: { title: '捏一个角色', who: '角色', pick: '同伴', go: '开场', next: '下一步', back: '上一步', start: '开场', starting: '正在开局…(复制世界 + 生成开场,第一次要十几秒)',
      random: '随机一个', save: '保存草稿', saved: '草稿已保存', cancel: '取消', left: n => `剩余 ${n} 点`, over: n => `超了 ${n} 点`, all: '点数要正好用完', required: '必填',
      chooseN: (a, b) => b > a ? `选 ${a}–${b} 个` : `选 ${a} 个`, companion: '选一个同伴', none: '还没选', missing: '还差这些才能开场', engine: '引擎没让开局', preview: '面板',
      gen: '随机生成', genning: '生成中…', noPortrait: '没有立绘', grants: '带来', ready: '都齐了,可以开场', yourCard: '你的面板' },
    en: { title: 'Make your character', who: 'Character', pick: 'Companion', go: 'Begin', next: 'Next', back: 'Back', start: 'Begin', starting: 'Opening the run… (copying the world and writing the opening; the first time takes a while)',
      random: 'Randomize', save: 'Save draft', saved: 'Draft saved', cancel: 'Cancel', left: n => `${n} points left`, over: n => `${n} points over`, all: 'spend every point', required: 'required',
      chooseN: (a, b) => b > a ? `pick ${a}–${b}` : `pick ${a}`, companion: 'Pick a companion', none: 'not picked yet', missing: 'Still needed before you can begin', engine: 'The engine refused to start', preview: 'Sheet',
      gen: 'Generate', genning: 'Writing…', noPortrait: 'no portrait', grants: 'brings', ready: 'All set — you can begin', yourCard: 'Your sheet' },
    ja: { title: 'キャラクターを作る', who: 'キャラクター', pick: '相棒', go: '開幕', next: '次へ', back: '戻る', start: '開幕する', starting: '開局中…(世界のコピーと開幕の生成。初回は少しかかります)',
      random: 'ランダム', save: '下書きを保存', saved: '下書きを保存しました', cancel: 'キャンセル', left: n => `残り ${n} ポイント`, over: n => `${n} ポイント超過`, all: 'ポイントを使い切ってください', required: '必須',
      chooseN: (a, b) => b > a ? `${a}〜${b} 個選ぶ` : `${a} 個選ぶ`, companion: '相棒を選ぶ', none: 'まだ選んでいません', missing: '開幕にはまだこれが必要です', engine: 'エンジンが開局を拒否しました', preview: 'シート',
      gen: '自動生成', genning: '生成中…', noPortrait: '立ち絵なし', grants: '得るもの', ready: '準備完了 — 開幕できます', yourCard: 'あなたのシート' },
    ko: { title: '캐릭터 만들기', who: '캐릭터', pick: '동료', go: '시작', next: '다음', back: '이전', start: '시작하기', starting: '게임을 여는 중…(세계 복사 + 오프닝 생성, 처음엔 시간이 좀 걸립니다)',
      random: '무작위', save: '초안 저장', saved: '초안을 저장했습니다', cancel: '취소', left: n => `${n}점 남음`, over: n => `${n}점 초과`, all: '포인트를 모두 써야 합니다', required: '필수',
      chooseN: (a, b) => b > a ? `${a}–${b}개 선택` : `${a}개 선택`, companion: '동료 고르기', none: '아직 고르지 않음', missing: '시작하려면 아직 필요한 것', engine: '엔진이 시작을 거부했습니다', preview: '시트',
      gen: '자동 생성', genning: '생성 중…', noPortrait: '초상화 없음', grants: '얻는 것', ready: '준비 완료 — 시작할 수 있습니다', yourCard: '나의 시트' },
  };
  const L = () => T[lang()];
  const tx = v => { if (v && typeof v === 'object' && !Array.isArray(v)) { const lg = lang(); return String(v[lg] || v.zh || v.en || Object.values(v)[0] || ''); } return v == null ? '' : String(v); };
  const h = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const enc = encodeURIComponent;
  const pick1 = a => a[Math.floor(Math.random() * a.length)];
  // 头像跟着性别走(10-15:选「女」随机出过男性头像):不认字段名,认选项 id 的写法 —— 选择题的选项 id 是 female / male(f / m),
  // 头像选项 id 以 -f / -m 结尾(后面可带数字),两边按这个字母对上;别的(不指定 · 中性头像 -n / -hood)不对。
  // 模板要指定跟哪个字段就在头像字段写 follows: "<选择字段 id>"。
  const sexOf = id => { const x = String(id || '').toLowerCase(); return /^(female|woman|f)$/.test(x) ? 'f' : /^(male|man|m)$/.test(x) ? 'm' : ''; };
  const faceSex = id => (String(id || '').toLowerCase().match(/-([fm])\d*$/) || [])[1] || '';
  function faceLinks(builder) {
    const fs = fieldsOf(builder), out = [];
    for (const face of fs.filter(f => f.kind === 'portrait' && (f.options || []).some(o => faceSex(o.id)))) {
      const by = face.follows ? fs.find(f => f.id === face.follows) : fs.find(f => f.kind === 'choice' && (f.options || []).some(o => sexOf(o.id)));
      if (by) out.push({ face, by });
    }
    return out;
  }
  // 这个性别该配哪些头像:对上的;没指定性别 = 中性的(没有中性的就全部)
  function facesFor(face, choice) {
    const ids = (face.options || []).map(o => o.id), sx = sexOf(choice);
    const hit = ids.filter(i => faceSex(i) === sx && sx), neutral = ids.filter(i => !faceSex(i));
    return hit.length ? hit : sx ? [] : neutral.length ? neutral : ids;
  }

  const STYLE = `
.pb{position:fixed;inset:0;z-index:300;display:flex;flex-direction:column;background:radial-gradient(ellipse at 30% 20%,#1a2133 0%,#07080f 70%);color:var(--ink,#f5f3ee);font:14px/1.55 var(--glass-font,system-ui)}
.pb *{box-sizing:border-box}
.pb-top{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line,rgba(255,255,255,.12));flex-wrap:wrap}
.pb-top h1{margin:0;font:700 19px/1.2 var(--glass-font,system-ui);letter-spacing:-.01em}
.pb-steps{display:flex;gap:6px;flex-wrap:wrap}
.pb-steps button{border:1px solid var(--line2,rgba(255,255,255,.22));background:transparent;border-radius:99px;padding:5px 12px;font:500 12px var(--machine,monospace);color:var(--muted,#aaa)}
.pb-steps button.on{background:var(--pressed,#eee);color:var(--pressed-ink,#07080f);border-color:transparent}
.pb-steps button.done{color:var(--lime,#c9f27a)}
.pb-sp{flex:1}
.pb-btn{border:1px solid var(--line2,rgba(255,255,255,.22));background:var(--well,rgba(255,255,255,.06));border-radius:12px;padding:8px 14px;font-weight:600}
.pb-btn:hover{background:var(--hover,rgba(255,255,255,.14))}
.pb-btn.go{background:var(--lime,#c9f27a);color:#10140a;border-color:transparent}
.pb-btn[disabled]{opacity:.4;cursor:not-allowed}
.pb-main{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(300px,.75fr);gap:20px;padding:20px 22px;overflow:auto}
.pb-col{min-width:0;display:flex;flex-direction:column;gap:14px}
.pb-f{background:var(--fill,rgba(16,17,27,.62));border:1px solid var(--line,rgba(255,255,255,.12));border-radius:18px;padding:14px 16px}
.pb-f > label,.pb-lab{display:flex;align-items:baseline;gap:8px;font-weight:700;margin-bottom:8px}
.pb-lab small,.pb-f > label small{font:500 11px var(--machine,monospace);color:var(--faint,#888);letter-spacing:.06em}
.pb-req{color:var(--rust,#de8a63);font:500 11px var(--machine,monospace)}
.pb-hint{font-size:12.5px;color:var(--muted,#aaa);margin:-4px 0 8px}
.pb-in{width:100%;background:rgba(0,0,0,.28);border:1px solid var(--line2,rgba(255,255,255,.22));border-radius:12px;padding:9px 12px;color:inherit}
textarea.pb-in{min-height:76px;field-sizing:content;max-height:46vh;resize:vertical;font-family:var(--human,serif);font-size:15px}
.pb-row{display:flex;gap:8px;align-items:center}
.pb-dice{white-space:nowrap;flex:none;border:1px solid var(--line2,rgba(255,255,255,.22));background:transparent;border-radius:10px;padding:8px 10px}
.pb-opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.pb-opt{text-align:left;border:1px solid var(--line2,rgba(255,255,255,.22));background:rgba(255,255,255,.03);border-radius:14px;padding:10px 12px;display:flex;flex-direction:column;gap:3px}
.pb-opt b{font-size:14px}.pb-opt span{font-size:12px;color:var(--muted,#aaa)}
.pb-opt.on{border-color:var(--lime,#c9f27a);box-shadow:0 0 0 1px var(--lime,#c9f27a) inset;background:rgba(201,242,122,.08)}
.pb-gr{font:500 11px var(--machine,monospace);color:var(--lime,#c9f27a)!important}
.pb-chips{display:flex;flex-wrap:wrap;gap:6px}
.pb-chip{border:1px solid var(--line2,rgba(255,255,255,.22));background:transparent;border-radius:99px;padding:5px 12px}
.pb-chip.on{background:var(--pressed,#eee);color:var(--pressed-ink,#07080f)}
.pb-pts{display:flex;flex-direction:column;gap:8px}
.pb-pt{display:grid;grid-template-columns:minmax(64px,auto) 1fr auto;gap:10px;align-items:center}
.pb-pt .nm b{display:block}.pb-pt .nm small{display:block;font-size:11.5px;color:var(--faint,#888);max-width:28ch}
.pb-bar{height:8px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden}
.pb-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--blue,#9fc0e8),var(--lime,#c9f27a));border-radius:inherit}
.pb-step{display:flex;align-items:center;gap:6px}
.pb-step button{width:30px;height:30px;border-radius:9px;border:1px solid var(--line2,rgba(255,255,255,.22));background:transparent;font-weight:700}
.pb-step b{min-width:2ch;text-align:center;font:600 16px var(--machine,monospace)}
.pb-left{font:600 12px var(--machine,monospace);padding:3px 10px;border-radius:99px;background:rgba(201,242,122,.14);color:var(--lime,#c9f27a)}
.pb-left.bad{background:var(--fail-fill,rgba(230,90,80,.18));color:var(--fail,#ffb3a8)}
.pb-faces{display:flex;flex-wrap:wrap;gap:8px}
.pb-face{width:76px;height:96px;border-radius:14px;border:1px solid var(--line2,rgba(255,255,255,.22));padding:0;overflow:hidden;background:#111}
.pb-face img{width:100%;height:100%;object-fit:cover;display:block}
.pb-face.on{box-shadow:0 0 0 2px var(--lime,#c9f27a)}
.pb-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.pb-card{text-align:left;border:1px solid var(--line2,rgba(255,255,255,.22));background:var(--fill,rgba(16,17,27,.62));border-radius:20px;padding:0;overflow:hidden;display:flex;flex-direction:column}
.pb-card.on{box-shadow:0 0 0 2px var(--lime,#c9f27a)}
.pb-card .art{aspect-ratio:4/3;background:linear-gradient(135deg,#232a3d,#0d0f18);display:grid;place-items:center;overflow:hidden}
.pb-card .art img{width:100%;height:100%;object-fit:cover;object-position:top}
.pb-ini{font:700 44px var(--human,serif);color:rgba(255,255,255,.5)}
.pb-card .tx{padding:12px 14px;display:flex;flex-direction:column;gap:5px}
.pb-card .tx b{font-size:16px}.pb-card .tx em{font-style:normal;font-size:12px;color:var(--muted,#aaa)}
.pb-tier{align-self:flex-start;font:600 11px var(--machine,monospace);padding:2px 8px;border-radius:99px;background:rgba(159,192,232,.16);color:var(--blue,#9fc0e8)}
.pb-card p{margin:0;font-size:12.5px;color:var(--muted,#ccc)}
.pb-card dl{margin:4px 0 0;display:grid;gap:4px}.pb-card dt{font:600 11px var(--machine,monospace);color:var(--faint,#888)}.pb-card dd{margin:0;font-size:12px}
.pb-err{background:var(--fail-fill,rgba(230,90,80,.18));border:1px solid rgba(255,179,168,.35);border-radius:14px;padding:10px 14px;font-size:13px}
.pb-err ul{margin:4px 0 0;padding-left:18px}
.pb-ok{color:var(--pass,#9fe0b0);font-weight:600}
.pb-foot{display:flex;gap:10px;align-items:center;padding:12px 22px;border-top:1px solid var(--line,rgba(255,255,255,.12));flex-wrap:wrap}
.pb-note{font-size:12.5px;color:var(--muted,#aaa)}
.pb-busy{position:absolute;inset:0;display:grid;place-items:center;background:rgba(4,5,12,.7);font-size:15px;z-index:2;padding:24px;text-align:center}
/* 面板(捏人预览 · 游玩右栏共用) */
.pcard{background:linear-gradient(160deg,rgba(30,36,54,.9),rgba(12,13,22,.92));border:1px solid var(--line2,rgba(255,255,255,.22));border-radius:22px;padding:16px;display:flex;flex-direction:column;gap:12px}
.pcard .pc-hd{display:flex;gap:12px;align-items:center}
.pcard .pc-av{width:64px;height:80px;border-radius:14px;overflow:hidden;background:linear-gradient(135deg,#2a3149,#11131d);display:grid;place-items:center;flex:none;border:1px solid var(--line,rgba(255,255,255,.12))}
.pcard .pc-av img{width:100%;height:100%;object-fit:cover}
.pcard .pc-nm b{display:block;font:700 20px/1.2 var(--human,serif)}.pcard .pc-nm small{display:block;font:500 11px var(--machine,monospace);color:var(--lime,#c9f27a);letter-spacing:.08em;margin-top:4px}
.pcard .pc-sec{font:600 10.5px var(--machine,monospace);letter-spacing:.14em;text-transform:uppercase;color:var(--faint,#888)}
.pcard .pc-stat{display:grid;grid-template-columns:minmax(3.5em,max-content) 1fr 2.5em;gap:8px;align-items:center;font-size:12.5px}
.pcard .pc-stat span:last-child{text-align:right;font-family:var(--machine,monospace)}
.pcard .pc-txt{font-family:var(--human,serif);font-size:14px;line-height:1.6}
.pcard .pc-tags{display:flex;flex-wrap:wrap;gap:5px}.pcard .pc-tags span{font-size:11.5px;padding:2px 9px;border-radius:99px;border:1px solid var(--line2,rgba(255,255,255,.22))}
.pcard .pc-cmp{display:flex;gap:10px;align-items:center;border-top:1px solid var(--line,rgba(255,255,255,.12));padding-top:10px}
.pcard .pc-cmp .av{width:42px;height:52px;border-radius:10px}
.pcard .pc-dim{color:var(--faint,#888);font-size:12.5px}
@media (max-width:760px){
  .pb-top,.pb-foot{padding:10px 16px}.pb-main{grid-template-columns:1fr;padding:14px 16px;gap:14px}
  .pb-pt{grid-template-columns:1fr auto}.pb-pt .pb-bar{grid-column:1 / -1;order:3}
  .pb-cards{grid-template-columns:1fr}.pb-top h1{font-size:16px;width:100%}
}`;
  function css() { if (document.getElementById('pb-css')) return; const s = document.createElement('style'); s.id = 'pb-css'; s.textContent = STYLE; document.head.appendChild(s); }

  /* ---------- 草稿的检查(只为提示;规则在引擎) ---------- */
  const fieldsOf = b => (b.fields || []).filter(f => f && f.id);
  function ptsState(f, v) {
    const stats = (f.stats || []), lo = +(f.min ?? 0), total = +(f.total ?? 0);
    const spent = stats.reduce((n, s) => n + (+((v || {})[s.id] ?? lo)), 0);
    return { spent, total, left: total - spent, lo, hi: +(f.max ?? 99) };
  }
  function problemsOf(view, d) {
    const out = []; const t = L();
    for (const f of fieldsOf(view.builder)) {
      const v = d.fields[f.id], name = tx(f.label) || f.id;
      if (f.kind === 'text') { if (f.required && !String(v || '').trim()) out.push(`${name}:${t.required}`); }
      else if (f.kind === 'choice' || f.kind === 'portrait') { if (f.required && !v) out.push(`${name}:${t.required}`); }
      else if (f.kind === 'multi') { const n = (v || []).length, lo = f.min ?? (f.required ? 1 : 0), hi = f.max ?? (f.options || []).length; if (n < lo || n > hi) out.push(`${name}:${t.chooseN(lo, hi)}`); }
      else if (f.kind === 'points') { const p = ptsState(f, v); if (p.left < 0) out.push(`${name}:${t.over(-p.left)}`); else if (f.exact && p.left > 0) out.push(`${name}:${t.all}(${t.left(p.left)})`); }
    }
    const c = view.companion;
    if (c && c.required !== false && (d.companion || []).length < (c.pick || 1)) out.push(`${tx(c.title || c.label) || t.companion}:${t.chooseN(c.pick || 1, c.pick || 1)}`);
    return out;
  }
  function defaults(view) {
    const fields = {};
    for (const f of fieldsOf(view.builder)) {
      if (f.kind === 'points') { fields[f.id] = Object.fromEntries((f.stats || []).map(s => [s.id, +(f.min ?? 0)])); }
      else if (f.kind === 'multi') fields[f.id] = [];
    }
    return { fields, companion: [] };
  }
  function randomize(view) {
    const d = defaults(view);
    for (const f of fieldsOf(view.builder)) {
      const opts = (f.options || []).map(o => o.id);
      // 文字:random 列表 → 模板的 example(生成字段的示例)→ 留空(必填且能生成的,随机完再请引擎写)
      const ex = f.example == null ? [] : Array.isArray(f.example) ? f.example : [f.example];
      if (f.kind === 'text' && (f.random || []).length) d.fields[f.id] = pick1(f.random.map(tx));
      else if (f.kind === 'text' && ex.length) d.fields[f.id] = pick1(ex.map(tx));
      else if ((f.kind === 'choice' || f.kind === 'portrait') && opts.length) d.fields[f.id] = pick1(opts);
      else if (f.kind === 'multi' && opts.length) { const lo = f.min ?? (f.required ? 1 : 0), hi = Math.min(f.max ?? opts.length, opts.length); const n = lo + Math.floor(Math.random() * (hi - lo + 1)); d.fields[f.id] = [...opts].sort(() => Math.random() - 0.5).slice(0, n); }
      else if (f.kind === 'points') {
        const p = ptsState(f, d.fields[f.id]); let left = p.left; const v = d.fields[f.id]; const ids = (f.stats || []).map(s => s.id);
        for (let guard = 0; left > 0 && guard < 10000; guard++) { const k = pick1(ids); if (v[k] < p.hi) { v[k]++; left--; } if (ids.every(i => v[i] >= p.hi)) break; }
      }
    }
    for (const { face, by } of faceLinks(view.builder)) { const ok = facesFor(face, d.fields[by.id]); if (ok.length && !ok.includes(d.fields[face.id])) d.fields[face.id] = pick1(ok); }
    const c = view.companion; if (c && (c.candidates || []).length) d.companion = [...c.candidates].sort(() => Math.random() - 0.5).slice(0, c.pick || 1).map(x => x.sid);
    return d;
  }
  // 选项带来的东西:引擎算好的 brings(GET …/builder 给每个带 grants 的选项)—— 数字用模板的 labels / 点数栏的名字,
  // 列表里加的东西用它的 name;没名字的数字才退回键名(lint 会提醒模板补 labels)
  function grantText(o) {
    return (o.brings || []).map(x => x.add != null ? `${tx(x.label) || x.key} ${x.add >= 0 ? '+' : ''}${x.add}` : tx(x.label)).filter(Boolean).join(' · ');
  }
  // 预览里的派生值(引擎开局时按写进去的数再算一遍,含出身带来的加成;这里只按分配的点数估)
  function derive1(b, dv, values) {
    const st = {}; for (const f of fieldsOf(b)) if (f.kind === 'points') Object.assign(st, values[f.id] || {});
    let acc = 0; for (const [k, m] of Object.entries(dv.per || {})) acc += (+st[k] || 0) * m;
    const div = Math.max(1, Math.floor(+dv.div || 1)); return (+dv.base || 0) + (div > 1 ? Math.floor(acc / div) : acc);
  }
  /* ---------- 面板(预览 / 游玩右栏) ---------- */
  function panel(b, values, opt) {
    opt = opt || {}; const t = L(); values = values || {};
    const F = fieldsOf(b || {});
    const textF = F.filter(f => f.kind === 'text'), nameF = textF.find(f => f.id === 'name') || textF[0];
    const name = nameF ? String(values[nameF.id] || '') : '';
    const sub = F.filter(f => f.kind === 'choice').map(f => { const o = (f.options || []).find(x => x.id === values[f.id]); return o ? tx(o.label) : ''; }).filter(Boolean).join(' · ');
    const face = opt.portrait || '';
    const av = face ? `<img src="${h(face)}" alt="">` : `<span class="pb-ini">${h((name || '?').slice(0, 1))}</span>`;
    let html = `<div class="pcard"><div class="pc-hd"><div class="pc-av">${av}</div><div class="pc-nm"><b>${h(name || '—')}</b>${sub ? `<small>${h(sub)}</small>` : ''}</div></div>`;
    for (const f of F) {
      const v = values[f.id];
      if (f === nameF || f.kind === 'choice' || f.kind === 'portrait') continue;
      if (f.kind === 'points') {
        const hi = +(f.max ?? 10);
        html += `<div class="pc-sec">${h(tx(f.label) || f.id)}</div>` + (f.stats || []).map(s => { const x = +((v || {})[s.id] ?? 0); return `<div class="pc-stat"><span>${h(tx(s.label) || s.id)}</span><div class="pb-bar"><i style="width:${Math.max(0, Math.min(100, x / Math.max(hi, x, 1) * 100))}%"></i></div><span>${x}</span></div>`; }).join('');
      } else if (f.kind === 'multi') {
        const ls = (v || []).map(id => { const o = (f.options || []).find(x => x.id === id); return o ? tx(o.label) : id; });
        if (ls.length) html += `<div class="pc-sec">${h(tx(f.label) || f.id)}</div><div class="pc-tags">${ls.map(x => `<span>${h(x)}</span>`).join('')}</div>`;
      } else if (String(v || '').trim()) html += `<div class="pc-sec">${h(tx(f.label) || f.id)}</div><div class="pc-txt">${h(v)}</div>`;
    }
    for (const dv of (b && b.derive) || []) {
      if (!dv || !dv.label) continue;
      const v = opt.derived ? opt.derived[dv.to] : derive1(b, dv, values);
      if (v != null) html += `<div class="pc-stat"><span>${h(tx(dv.label))}</span><span></span><span>${h(v)}</span></div>`;
    }
    const cs = opt.companions || [];
    for (const c of cs) html += `<div class="pc-cmp"><div class="pc-av">${c.img ? `<img src="${h(c.img)}" alt="">` : `<span class="pb-ini" style="font-size:22px">${h(String(c.name || '?').slice(0, 1))}</span>`}</div><div><div class="pc-sec">${h(opt.companionTitle || t.pick)}</div><b>${h(c.name)}</b>${c.title ? ` <span class="pc-dim">${h(c.title)}</span>` : ''}</div></div>`;
    if (opt.companionTitle !== undefined && !cs.length) html += `<div class="pc-cmp"><span class="pc-dim">${h(opt.companionTitle)} · ${h(t.none)}</span></div>`;
    return html + '</div>';
  }
  // 游玩中这一局的玩家卡(GET /api/v1/play/engine/player-card):live = 现在的值(玩的过程中会变)
  function runPanel(card) {
    if (!card || !card.builder) return '';
    const values = { ...(card.values || {}), ...(card.live || {}) };
    const cmp = (card.companion || []).map(sid => { const c = (card.companion_cards || {})[sid] || {}; return { name: c.name || sid, img: c.portrait ? V3.url(`/api/v1/play/portrait?id=${enc(sid)}`) : '' }; });   // 没立绘 = 首字头像,不去要一张 404
    return panel(card.builder, values, { derived: (card.live || {}).__derived || card.derived || {}, portrait: card.portrait ? V3.url('/api/v1/play/portrait?id=player') : '', companions: cmp });
  }

  /* ---------- 这一屏 ---------- */
  function steps(view) {
    const b = view.builder, c = view.companion, t = L();
    const declared = (b.steps || []).filter(s => s && s.id);
    if (declared.length) {
      const ids = declared.map(s => s.id);
      const out = declared.map(s => ({ id: s.id, title: tx(s.title) || s.id, fields: fieldsOf(b).filter(f => (f.step || ids[0]) === s.id), comp: !!c && (c.step || '') === s.id }));
      if (c && !out.some(s => s.comp)) out.splice(out.length - (out[out.length - 1].fields.length ? 0 : 1), 0, { id: '_pick', title: t.pick, fields: [], comp: true });
      if (out[out.length - 1].fields.length || out[out.length - 1].comp) out.push({ id: '_go', title: t.go, fields: [], comp: false });
      return out;
    }
    return [{ id: '_who', title: t.who, fields: fieldsOf(b), comp: false }, ...(c ? [{ id: '_pick', title: t.pick, fields: [], comp: true }] : []), { id: '_go', title: t.go, fields: [], comp: false }];
  }

  function start(tid, outLang, o) {
    o = o || {};
    const sess = player => V3.post('/api/v1/play/session', { slug: `tpl--${tid}`, output_lang: outLang || lang(), ...(player ? { player } : {}) });
    return V3.j(`/api/v1/local/templates/${enc(tid)}/builder`).catch(() => ({ declared: false })).then(view => {
      if (!view || !view.declared) return sess(null);
      return new Promise((resolve, reject) => open(tid, view, { resolve, reject, sess, cancel: o.cancel }));
    });
  }

  function open(tid, view, ctl) {
    css();
    const KEY = `wl-pb-${tid}`;
    let d = defaults(view);
    try { const s = JSON.parse(localStorage.getItem(KEY) || 'null'); if (s && s.fields) d = { fields: { ...d.fields, ...s.fields }, companion: s.companion || [], touched: s.touched || {} }; } catch { /* no draft */ }
    const ST = { step: 0, errs: [], busy: false, note: '' };
    const SS = steps(view);
    const root = document.createElement('div'); root.className = 'pb'; root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true');
    document.body.appendChild(root);
    const save = (quiet) => { try { localStorage.setItem(KEY, JSON.stringify(d)); if (!quiet) { ST.note = L().saved; draw(); setTimeout(() => { ST.note = ''; draw(); }, 1600); } } catch { /* no storage */ } };
    const img = (q) => V3.url(`/api/v1/local/templates/${enc(tid)}/builder/image?${q}`);
    const cands = (view.companion && view.companion.candidates) || [];
    const card = sid => ({ ...cands.find(c => c.sid === sid) || { sid, name: sid }, ...((view.companion && view.companion.cards) || {})[sid] });
    const cmpList = () => (d.companion || []).map(sid => { const c = card(sid); return { name: tx(c.name) || sid, title: tx(c.title), img: c.portrait ? img(`sid=${enc(sid)}`) : '' }; });
    const facePick = () => { const f = fieldsOf(view.builder).find(x => x.kind === 'portrait'); return f && d.fields[f.id] ? img(`field=${enc(f.id)}&option=${enc(d.fields[f.id])}`) : ''; };

    function fieldHTML(f) {
      const t = L(), v = d.fields[f.id];
      const head = `<label class="pb-lab">${h(tx(f.label) || f.id)}${f.required ? ` <span class="pb-req">${t.required}</span>` : ''}${f.kind === 'multi' ? ` <small>${t.chooseN(f.min ?? (f.required ? 1 : 0), f.max ?? (f.options || []).length)}</small>` : ''}</label>${f.hint ? `<div class="pb-hint">${h(tx(f.hint))}</div>` : ''}`;
      if (f.kind === 'text') {
        const ph = h(tx(f.placeholder)), max = f.max ? ` maxlength="${+f.max}"` : '';
        const input = f.multiline || (f.max || 0) > 60 ? `<textarea class="pb-in" data-pbt="${h(f.id)}" placeholder="${ph}"${max}>${h(v || '')}</textarea>` : `<input class="pb-in" data-pbt="${h(f.id)}" value="${h(v || '')}" placeholder="${ph}"${max}>`;
        const gen = f.generate ? `<button class="pb-dice" data-pbg="${h(f.id)}" ${ST.gen === f.id ? 'disabled' : ''}>✨ ${h(ST.gen === f.id ? t.genning : t.gen)}</button>` : '';
        return `<div class="pb-f">${head}<div class="pb-row" style="align-items:flex-start">${input}${(f.random || []).length ? `<button class="pb-dice" data-pbr="${h(f.id)}" title="${h(t.random)}" aria-label="${h(t.random)}">🎲</button>` : ''}${gen}</div></div>`;
      }
      if (f.kind === 'choice' || f.kind === 'multi') {
        const on = id => f.kind === 'multi' ? (v || []).includes(id) : v === id;
        const rich = (f.options || []).some(o => o.desc || o.grants);
        const body = rich ? `<div class="pb-opts">${(f.options || []).map(o => { const g = grantText(o); return `<button class="pb-opt ${on(o.id) ? 'on' : ''}" data-pbo="${h(f.id)}" data-v="${h(o.id)}" aria-pressed="${on(o.id)}"><b>${h(tx(o.label) || o.id)}</b>${o.desc ? `<span>${h(tx(o.desc))}</span>` : ''}${g ? `<span class="pb-gr">${h(L().grants)} ${h(g)}</span>` : ''}</button>`; }).join('')}</div>`
          : `<div class="pb-chips">${(f.options || []).map(o => `<button class="pb-chip ${on(o.id) ? 'on' : ''}" data-pbo="${h(f.id)}" data-v="${h(o.id)}" aria-pressed="${on(o.id)}">${h(tx(o.label) || o.id)}</button>`).join('')}</div>`;
        return `<div class="pb-f">${head}${body}</div>`;
      }
      if (f.kind === 'points') {
        const p = ptsState(f, v);
        const badge = p.left < 0 ? `<span class="pb-left bad">${h(t.over(-p.left))}</span>` : `<span class="pb-left ${f.exact && p.left ? '' : ''}">${h(t.left(p.left))}</span>`;
        return `<div class="pb-f"><div class="pb-lab" style="justify-content:space-between"><span>${h(tx(f.label) || f.id)} <small>${p.spent} / ${p.total}${f.exact ? ' · ' + h(t.all) : ''}</small></span>${badge}</div>${f.hint ? `<div class="pb-hint">${h(tx(f.hint))}</div>` : ''}
          <div class="pb-pts">${(f.stats || []).map(s => { const x = +((v || {})[s.id] ?? p.lo); return `<div class="pb-pt"><div class="pc-nm"><b>${h(tx(s.label) || s.id)}</b>${s.desc ? `<small>${h(tx(s.desc))}</small>` : ''}</div>
            <div class="pb-bar"><i style="width:${(x / Math.max(p.hi, 1)) * 100}%"></i></div>
            <div class="pb-step"><button data-pbp="${h(f.id)}" data-s="${h(s.id)}" data-d="-1" ${x <= p.lo ? 'disabled' : ''} aria-label="−">−</button><b data-pbv="${h(f.id)}.${h(s.id)}">${x}</b><button data-pbp="${h(f.id)}" data-s="${h(s.id)}" data-d="1" ${x >= p.hi ? 'disabled' : ''} aria-label="+">+</button></div></div>`; }).join('')}</div></div>`;
      }
      if (f.kind === 'portrait') {
        return `<div class="pb-f">${head}<div class="pb-faces">${(f.options || []).map(o => `<button class="pb-face ${v === o.id ? 'on' : ''}" data-pbo="${h(f.id)}" data-v="${h(o.id)}" aria-pressed="${v === o.id}" title="${h(tx(o.label) || o.id)}">${o.image ? `<img src="${h(img(`field=${enc(f.id)}&option=${enc(o.id)}`))}" alt="${h(tx(o.label) || o.id)}">` : h(tx(o.label) || o.id)}</button>`).join('')}</div></div>`;
      }
      return '';
    }
    function compHTML() {
      const c = view.companion, t = L(); const rows = c.rows || [];
      const known = new Set(['sid', 'from', 'lib', 'name', 'name_en', 'intro', 'tags', 'portrait', 'title', 'tier', 'blurb', ...rows.map(r => r.key)]);
      return `<div class="pb-f"><div class="pb-lab">${h(tx(c.title || c.label) || t.companion)} <small>${t.chooseN(c.pick || 1, c.pick || 1)}</small></div><div class="pb-cards">${cands.map(x0 => {
        const x = card(x0.sid), on = (d.companion || []).includes(x.sid);
        const extra = [...rows.map(r => [tx(r.label) || r.key, x[r.key]]), ...Object.keys(x).filter(k => !known.has(k)).map(k => ['', x[k]])].filter(([, v]) => v != null && tx(v));
        return `<button class="pb-card ${on ? 'on' : ''}" data-pbc="${h(x.sid)}" aria-pressed="${on}"><div class="art">${x.portrait ? `<img src="${h(img(`sid=${enc(x.sid)}`))}" alt="">` : `<span class="pb-ini">${h(tx(x.name).slice(0, 1) || '?')}</span>`}</div>
          <div class="tx"><b>${h(tx(x.name) || x.sid)}</b>${x.title ? `<em>${h(tx(x.title))}</em>` : ''}${x.tier ? `<span class="pb-tier">${h(tx(x.tier))}</span>` : ''}
          ${x.blurb || x.intro ? `<p>${h(tx(x.blurb || x.intro))}</p>` : ''}${extra.length ? `<dl>${extra.map(([k, v]) => `${k ? `<dt>${h(k)}</dt>` : ''}<dd>${h(tx(v))}</dd>`).join('')}</dl>` : ''}</div></button>`; }).join('')}</div></div>`;
    }
    function draw() {
      const t = L(), S = SS[ST.step], last = ST.step === SS.length - 1, probs = problemsOf(view, d);
      const ae = document.activeElement, keep = ae && ae.dataset && ae.dataset.pbt ? { id: ae.dataset.pbt, s: ae.selectionStart, e: ae.selectionEnd } : null;
      let left = S.fields.map(fieldHTML).join('');
      if (S.comp) left += compHTML();
      if (!S.fields.length && !S.comp) left += `<div class="pb-f">${probs.length ? `<div class="pb-err"><b>${h(t.missing)}</b><ul>${probs.map(p => `<li>${h(p)}</li>`).join('')}</ul></div>` : `<div class="pb-ok">${h(t.ready)}</div>`}</div>`;
      if (ST.errs.length) left = `<div class="pb-err" role="alert"><b>${h(t.engine)}</b><ul>${ST.errs.map(e => `<li>${h(e)}</li>`).join('')}</ul></div>` + left;
      root.innerHTML = `<div class="pb-top"><h1>${h(tx(view.builder.title) || t.title)}</h1><div class="pb-steps">${SS.map((s, i) => `<button data-pbs="${i}" class="${i === ST.step ? 'on' : i < ST.step ? 'done' : ''}">${i + 1} · ${h(s.title)}</button>`).join('')}</div><span class="pb-sp"></span>
          <button class="pb-btn" data-pbx="rand">🎲 ${h(t.random)}</button><button class="pb-btn" data-pbx="save">${h(t.save)}</button>${ctl.cancel ? `<button class="pb-btn" data-pbx="cancel">${h(t.cancel)}</button>` : ''}</div>
        <div class="pb-main"><div class="pb-col">${left}</div><div class="pb-col"><div class="pb-lab"><small>${h(t.preview)}</small></div>${panel(view.builder, d.fields, { portrait: facePick(), companions: cmpList(), companionTitle: view.companion ? (tx(view.companion.title || view.companion.label) || t.pick) : undefined })}</div></div>
        <div class="pb-foot"><button class="pb-btn" data-pbx="back" ${ST.step === 0 ? 'disabled' : ''}>${h(t.back)}</button><span class="pb-note" aria-live="polite">${h(ST.note || (last && probs.length ? probs[0] : ''))}</span><span class="pb-sp"></span>
          ${last ? `<button class="pb-btn go" data-pbx="go" ${probs.length || ST.busy ? 'disabled' : ''}>${h(t.start)}</button>` : `<button class="pb-btn go" data-pbx="next">${h(t.next)}</button>`}</div>
        ${ST.busy ? `<div class="pb-busy">${h(t.starting)}</div>` : ''}`;
      if (keep) { const el = root.querySelector(`[data-pbt="${CSS.escape(keep.id)}"]`); if (el) { el.focus(); try { el.setSelectionRange(keep.s, keep.e); } catch { /* not text */ } } }
    }
    async function go() {
      ST.errs = []; ST.busy = true; draw();
      const player = { fields: d.fields, companion: (d.companion || []).length === 1 ? d.companion[0] : d.companion };
      try {
        const r = await ctl.sess(player);
        save(true); root.remove(); ctl.resolve(r);
      } catch (e) {
        let errs = [String(e.message || e)];
        try { const r2 = await fetch(V3.base + '/api/v1/local/templates/' + enc(tid) + '/builder/check', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(player) }); const j = await r2.json(); if (j.errors && j.errors.length) errs = j.errors; } catch { /* keep the status line */ }
        ST.busy = false; ST.errs = errs; draw();
      }
    }
    root.addEventListener('input', e => { const id = e.target.dataset && e.target.dataset.pbt; if (!id) return; d.fields[id] = e.target.value; save(true); draw(); });
    root.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b || b.disabled) return;
      const F = id => fieldsOf(view.builder).find(f => f.id === id);
      if (b.dataset.pbs) { ST.step = +b.dataset.pbs; draw(); return; }
      if (b.dataset.pbg) { const id = b.dataset.pbg; ST.gen = id; draw();
        V3.post(`/api/v1/local/templates/${enc(tid)}/builder/generate`, { field: id, fields: d.fields, lang: lang() })
          .then(r => { if (r && r.text) { d.fields[id] = r.text; save(true); } }).catch(() => {}).finally(() => { ST.gen = ''; draw(); }); return; }
      if (b.dataset.pbr) { const f = F(b.dataset.pbr); d.fields[f.id] = pick1(f.random.map(tx)); save(true); draw(); return; }
      if (b.dataset.pbo) { const f = F(b.dataset.pbo), v = b.dataset.v;
        if (f.kind === 'multi') { const cur = d.fields[f.id] || []; const max = f.max ?? (f.options || []).length; d.fields[f.id] = cur.includes(v) ? cur.filter(x => x !== v) : cur.length < max ? [...cur, v] : max === 1 ? [v] : cur; }
        else d.fields[f.id] = d.fields[f.id] === v && !f.required ? undefined : v;
        // 自己点过的头像不再动;没点过的,改了性别就换成配得上的第一张
        if (f.kind === 'portrait') d.touched = { ...(d.touched || {}), [f.id]: true };
        for (const { face, by } of faceLinks(view.builder)) if (by.id === f.id && !(d.touched || {})[face.id]) { const ok = facesFor(face, d.fields[f.id]); if (ok.length && !ok.includes(d.fields[face.id])) d.fields[face.id] = ok[0]; }
        save(true); draw(); return; }
      if (b.dataset.pbp) { const f = F(b.dataset.pbp), s = b.dataset.s, p = ptsState(f, d.fields[f.id]); const cur = +((d.fields[f.id] || {})[s] ?? p.lo);
        d.fields[f.id] = { ...(d.fields[f.id] || {}), [s]: Math.max(p.lo, Math.min(p.hi, cur + +b.dataset.d)) }; save(true); draw(); return; }
      if (b.dataset.pbc) { const c = view.companion, sid = b.dataset.pbc, cur = d.companion || [], n = c.pick || 1;
        d.companion = cur.includes(sid) ? cur.filter(x => x !== sid) : n === 1 ? [sid] : cur.length < n ? [...cur, sid] : cur; save(true); draw(); return; }
      const x = b.dataset.pbx;
      if (x === 'rand') {
        d = randomize(view); save(true); draw();
        // 必填、能生成、还空着的文字(模板没给 random / example):让引擎写一段,不然随机完还开不了场
        for (const f of fieldsOf(view.builder)) if (f.kind === 'text' && f.required && f.generate && !String(d.fields[f.id] || '').trim()) {
          const id = f.id; ST.gen = id; draw();
          V3.post(`/api/v1/local/templates/${enc(tid)}/builder/generate`, { field: id, fields: d.fields, lang: lang() })
            .then(r => { if (r && r.text && !String(d.fields[id] || '').trim()) { d.fields[id] = r.text; save(true); } }).catch(() => {}).finally(() => { ST.gen = ''; draw(); });
        }
      }
      else if (x === 'save') save(false);
      else if (x === 'cancel') { root.remove(); ctl.reject(Object.assign(new Error('cancelled'), { cancelled: true })); }
      else if (x === 'back') { ST.step = Math.max(0, ST.step - 1); draw(); }
      else if (x === 'next') { ST.step = Math.min(SS.length - 1, ST.step + 1); draw(); root.querySelector('.pb-main').scrollTop = 0; }
      else if (x === 'go') go();
    });
    draw();
  }

  window.BUILDER = { start, panel, runPanel, lang, t: k => L()[k] };
})();
