---
title: "Lint:发布前的检查"
description: "查引用可解析、素材填满、提示词占位符、token 预算。过不了就不能发布。"
---

<!-- section: what -->
## 什么时候跑

> **状态:随 1.0 发布** —— `neonrp template lint`、Template 页「Lint」一栏;每一项的代码见模板文件夹里的 `spec/template.md` §7。

WorldLines 先把模板包 + 片段 + 世界内容 + 主角 + 素材 + 提示词 + 规则**组装**起来,再跑 **Lint**。Lint 过不了,就不能发布。每一项分两级:**拦下**,或**只警告**。

<!-- section: checks -->
## 四类检查

| 类 | 检查什么 | 被拦的例子 |
|---|---|---|
| **引用** | 规则、触发器、视图用到的变量都已注册;每个 op 都有处理器;扩展没装时它的变量和 op 不能被引用 | 视图「集市」绑定 `price.{town}.*`,但经济片段没装 |
| **素材** | 每个 `required: publish` 的槽位都有文件,而且没过期 | 石津地图过期:路上长出了新地点,热点对不上 |
| **提示词** | 每个 `{占位符}` 都能从变量或配方上下文取到 | 提示词引用 `{weather}`,但没注册 |
| **token 预算** | 干跑回合,算每回合平均 token,超过模板声明的预算就拦 | 每回合均值 24,000,预算 20,000 |

<!-- section: today -->
## 现在实际查的

除了上面四类,还会查:**世界和玩法包**能加载、**角色**能找到(角色库的 link 断了也算)、**剧情**能解析且结局可达、**结局模式**(单结局 / 多结局 / 开放)对得上、**卡面**有标题和封面,以及按你声明的[玩法合约](/docs/creators/contracts)查开场、阵容、结局数、真相、结局 CG。

```bash
neonrp template lint <模板>          # 每行 [级别] 代码 位置: 说明;最后一行 publishable / NOT publishable
neonrp template lint <模板> --json
```

引擎会在临时目录里「全员到场」地建一局来查,所以剧情和素材槽是对着真实世界检查的。

<!-- section: after -->
## 通过之后

Lint 通过后导出[接口契约](/docs/developers/contract) `world.contract.json`,然后走[本地审批 → Hub](/docs/creators/publish)。
