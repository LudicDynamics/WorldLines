---
title: "导出与导入"
description: "在引擎里改好的模板和角色,打成一个包带走,再导回来。"
---

<!-- section: what -->
## 一种包

> **状态:随 1.0 发布**

模板和角色用同一种包:一个 zip,根目录一份 `pack.json` 写明里面是什么。

| 包 | 里面有 | 导入到 |
|---|---|---|
| 模板包 | 模板文件夹(世界 · 剧情 · prompt · 素材,不含 `frontends/`)+ 它 link 的每个角色库角色 | 模板 → 你的模板库;角色 → 角色库,模板里照旧是 link |
| 角色包 | 角色库里的一个角色 | 角色库 |

<!-- section: how -->
## 怎么用

**网页**:模板页头部「导出」下载 `.template.zip`;「导入…」选一个包,导完自动切到它。

**命令行**:只有自由区的作品能导出。内置的灰橡宅、石津镇在默认区,先复制一份再导出:

```bash
neonrp template fork pct-house my-house --store ~/.worldlines/templates
neonrp template export ~/.worldlines/templates/my-house.template     # → ./my-house.template.zip
neonrp template export --soul mira                                   # → ./mira.soul.zip(角色库里的角色)
neonrp template import my-house.template.zip --store ~/.worldlines/templates           # 模板进你的模板库,带着的角色进角色库
neonrp template import my-house.template.zip --id my-copy --store ~/.worldlines/templates   # 换一个 id 导入
```

直接 `neonrp template export pct-house` 会被拒:默认区作品只能玩,不能导出。

模板文件夹里的 `frontends/`(世界自己的前端)不进包,只留在本机。

<!-- section: rules -->
## 撞名与安全

- 模板 id 已被占用 → 自动用下一个空的 `-2`、`-3`(用 `--id` 指定时被占就拒绝)。
- 角色库里已有同名角色:内容一模一样就复用;不一样就改名装进来,模板的 link 指过去,你本机原来的不动。
- 导入前先在临时目录里检查:有绝对路径或 `..`、链接、代码文件(`.py` `.js` `.sh` …)、太多文件或太大 → 整包拒绝,什么都不写。

<!-- section: http -->
## 接口

```
GET  /api/v1/local/templates/<id>/export     模板包
GET  /api/v1/local/souls/<名字>/export        角色包
POST /api/v1/local/import/package[?id=新id]   body = zip
```
