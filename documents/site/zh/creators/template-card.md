---
title: "模板卡:card.yaml"
description: "世界卡 + 角色卡合一。作者只填一份简易模板,Agent 按规则把世界编出来。"
---

<!-- section: pack -->
## 包的样子

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

```text
<id>.wlcard/
  card.yaml                 ← 作者只需要填这一份
  manifest.json             ← 模板、片段、模式旋钮、主角表
  rules/world.rules.yaml    ← 世界卡规则
  rules/souls/<sid>.rules.yaml
  world/  souls/  story/  assets/
```

**卡不是新格式,卡是文件夹的索引。**

<!-- section: card -->
## card.yaml

```yaml
title: 雾镇 · 失忆旅人
pitch: 河港小镇与雾。你是失忆的旅人;治愈师在北门遇见你。
lang: zh
story: |
  黎明前的雾像湿布一样压在驿路上……
core: |
  灰雾北境。石津是河港贸易小镇,雾常年不散……
leads:
  - name: 艾琳娜
    who: 失忆的治愈师
    want: 在石津拿到第一份像样的契约
  - name: 罗文
    who: 碧石镇的冒险者
    want: 找到世界边缘的传说入口
play:
  ending: open        # open | closed
  freedom: sandbox    # sandbox | semi | linear
  time: rp+tick
template: rpg
mixins: [space, tick, economy, factions]
```

<!-- section: template -->
## 选模板与片段

`template` 选一种玩法(已实装的内置模板:`rpg`、`werewolf`);`mixins` 叠加系统片段(空间 · tick · 经济 · 势力,设计中)。引擎读 `manifest.json["template"]` 决定用哪个模板包(已实装)。

<!-- section: rules -->
## 两套规则

- **世界卡规则**:有哪些类和变量、游玩中允许新增什么、结局怎么判;
- **角色卡规则**:主角的人格数值、目标可选集、承诺、知道什么、会透露什么。

规则固化之后,开放世界、有结局、沙盒、半沙盒都只是同一套东西上的旋钮组合。
