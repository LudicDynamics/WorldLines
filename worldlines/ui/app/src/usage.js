/* 使用数据(10-25,docs/planning/USAGE-DATA-CONTRACT-1025.md):回到游玩一览 = 一次 lobby_view。只告诉引擎「一览在眼前」,
   其余(开局 · 回合 · 离开)引擎自己数;设置里关掉「发送使用数据」就什么都不发(引擎那边判断)。 */
(function () {
  let was = '';
  const _render = render;
  render = function () {
    _render();
    if (S.screen === 'cat' && was !== 'cat') fetch('/api/v1/local/usage', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: '{"name":"lobby_view"}' }).catch(() => {});
    was = S.screen;
  };
})();
