// 界面语言(10-25):工作台界面的字按 wl-local-lang 换成 zh / en / ja / ko。设置里换语言 = 存进 wl-local-lang + 重载整页,
// 所以 T() 在脚本载入时求值也没问题(常量表、标签数组可以直接包)。
// 词典按中文原文作 key(real/i18n-en.js · i18n-ja.js · i18n-ko.js,排在本文件前面);缺词条 = 原样出中文。zh 时一律原样返回。
// 只包「给人看的字」:发给引擎 / LLM 的、写进文件的、拿来比对引擎输出的、当 key / 选择器 / 正则的,都不包。
// 没存过语言时按浏览器语言挑(zh / ja / ko,别的一律 en);叙事语言照旧由 engine.js 自己读 wl-local-lang(没存过 = zh)。
//
// 术语表(词典里保持一致):
//   模板 template · テンプレート · 템플릿        世界 world · ワールド · 월드
//   角色 character · キャラクター · 캐릭터       角色库 character library · キャラクターライブラリ · 캐릭터 라이브러리
//   存档 save · セーブ · 세이브                  编排 orchestration · オーケストレーション · 오케스트레이션
//   编排台 orchestration board · 編成ボード · 오케스트레이션 보드
//   回合 turn · ターン · 턴                      拍 beat · ビート · 비트
//   工作台 workbench · ワークベンチ · 워크벤치     测试台 test bench · テストベンチ · 테스트 벤치
//   前端台 frontend bench · フロントエンドベンチ · 프런트엔드 벤치   标准前端 standard frontend · 標準フロントエンド · 표준 프런트엔드
//   合约 contract · コントラクト · 계약          剧情 plot · プロット · 플롯
//   主持 host · 進行役 · 진행자                  玩家 player · プレイヤー · 플레이어
//   开局 start a run · ゲーム開始 · 게임 시작       一局 run · プレイ · 플레이
//   自由区 Free Zone · フリーゾーン · 자유 구역     默认区 Default Zone · デフォルトゾーン · 기본 구역
//   小手机 phone · スマホ · 폰                   发布 publish · 公開 · 게시
//   素材 asset · 素材 · 소재                     生图 image generation · 画像生成 · 이미지 생성
//   模型 model · モデル · 모델                   设置 settings · 設定 · 설정
//   产品名照旧:NeonRP · WorldLines · Hub · Pack · Lint · mixin · soul
(function () {
  const OK = /^(zh|en|ja|ko)$/;
  let lg = '';
  // ?lang= (the Hub passes its language when it opens a world here) · the workbench setting · the local Hub's own setting
  lg = (new URLSearchParams(location.search).get('lang') || '').slice(0, 2).toLowerCase();
  if (!OK.test(lg)) { try { lg = localStorage.getItem('wl-local-lang') || localStorage.getItem('wl.hub.lang') || ''; } catch { /* storage off */ } }
  if (!OK.test(lg)) {
    const nav = String((navigator.languages && navigator.languages[0]) || navigator.language || '').toLowerCase();
    lg = /^zh/.test(nav) ? 'zh' : /^ja/.test(nav) ? 'ja' : /^ko/.test(nav) ? 'ko' : 'en';
  }
  window.WLANG = lg;
  document.documentElement.lang = lg;
  const DICT = (window.WL_I18N && window.WL_I18N[lg]) || {};
  const fill = (s, vars) => vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : s;
  window.T = function (zh, vars) {
    const s = lg === 'zh' ? zh : (DICT[zh] != null ? DICT[zh] : zh);
    return fill(s, vars);
  };
  // 页面里写死的字(src/index.html):data-i18n = 换 textContent 的第一个文本节点;data-i18n-small = 里面 <small> 的字;
  // data-i18n-title / data-i18n-placeholder 换属性。<title> 一起换
  if (lg !== 'zh') {
    document.querySelectorAll('[data-i18n]').forEach(el => { const n = [...el.childNodes].find(x => x.nodeType === 3 && x.nodeValue.trim()); if (n) n.nodeValue = T(n.nodeValue.trim()); });
    document.querySelectorAll('[data-i18n-small]').forEach(el => { const s = el.querySelector('small'); if (s) s.textContent = T(s.textContent); });
    document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = T(el.title); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = T(el.placeholder); });
    document.title = T(document.title);
    // 地图入口节点的角标在 CSS 里(::after content)
    const st = document.createElement('style'); st.textContent = `.mnode.entry .disc::after{content:${JSON.stringify(T('入口'))}}`; document.head.appendChild(st);
  }
})();
