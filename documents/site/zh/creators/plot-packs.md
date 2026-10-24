---
title: "剧情包"
description: "关键道具、新地点、if/else、结局,和前端要展示的素材 —— 一个可以检查的包。"
---

<!-- section: what -->
## 是什么

> **状态:随 1.0 发布**

放在 `plots/<id>/plot.json`:`stages`(自动声明 `<id>.stage` 变量)· `classes` / `vars` · `entries`(关键道具、新地点、NPC,可带 `assets`)· `triggers` · `endings`。

还可以写:`stage_var`(用别的变量当阶段)· `stage_cg`(进某个阶段时播的图)· `prompt`(追加给讲述者的提示)· `reveal`(谜底,结局时揭晓)· `truth_quiz`(结算后的真相三问)· `collect`(世界里哪些角色、在什么条件下能被收集)。石津镇的 `plots/P20` 和灰橡宅的 `plots/P01` 是两个完整的例子。

<!-- section: example -->
## 例子

```json
{
  "id": "P01", "title": "雾里的钥匙", "stages": ["起", "承", "转", "合"],
  "entries": {
    "I900": {"class": "item", "name": "锈钥匙", "parent": "T001/well", "assets": {"image": "key.png"}},
    "T001/crypt": {"class": "place", "name": "地窖", "parent": "T001", "links": ["T001/well"],
                   "assets": {"image": "crypt.png", "bgm": "crypt.mp3"}}
  },
  "triggers": {
    "P01.end_fog": {"when": {"var": "P01.stage"}, "if": [{"var": "P01.stage", ">=": 3}],
                    "then": [{"to": "end", "ending": "E01"}],
                    "else": [{"to": "narration", "text": "雾还没散。"}]}
  },
  "endings": {"E01": {"title": "雾散", "assets": {"image": "e01.png", "video": "e01.mp4"}}}
}
```

<!-- section: lint -->
## 检查与安装

剧情包自带检查:每个引用的文件都要存在,并且是前端认得的类型(image / portrait / video / audio / bgm / sfx)。安装时通过和 `neonrp schema register` 同一个入口登记进世界,并把文件夹拷进 `game/plots/<id>/`,跟着世界走。
