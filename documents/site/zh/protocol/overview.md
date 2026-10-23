---
title: "协议总览"
description: "三套开放协议 —— World、Soul、Agent —— 定义了能发布到 WorldHub 与 SoulHub 的所有内容。任何 rp-core 引擎都遵守同一份契约层。"
---

<!-- section: three-protocols -->
## 三套协议,一个生态

所有发布到 WorldLines 的内容,背后都是这三套开放协议之一:

- **[World 协议](/docs/protocol/world)** —— 提供*场景*:区域、NPC、势力、传说、空间地图、规则。通过 WorldHub 分发。
- **[Soul 协议](/docs/protocol/soul)** —— 提供*居住者*:人格、记忆、目标、情绪。通过 SoulHub 分发。(命名:正式术语是 `soul`;`character` 作为旧别名保留。)
- **[Agent 协议](/docs/protocol/agent)** —— 提供*决策者*:一个带有显式读写 glob、角色与路由条件的 LLM 单元。运行在 world 或 soul bundle 内部。

一个*可运行的 session* = 一个 world bundle + 一个 soul bundle(通常是玩家的,加上 0..N 个 NPC 的)+ 各自附带的 agent 集合。

<!-- section: why-protocols -->
## 为什么需要一层协议

没有契约层,每个 editor / engine / hub 都会发明自己的数据形状,Elena 这个 soul 就没法被 drop 进 Stoneford 这个 world。这套协议是用最少的约束达到以下效果:

- **任何 engine** 都能加载任何地方发布的 world / soul
- **任何 editor** 在保存前都能用同一份 schema 验证
- **任何 hub** 都能用统一方式索引、搜索、提供 bundle
- **任何作者** 今天发布的内容,在 v0.2 上线后仍能加载 —— 处处 `additionalProperties: true`,新字段不会破坏旧文件

完整 schema 在 [github.com/LudicDynamics/rp-shared-protocol](https://github.com/LudicDynamics) 用 Apache 2.0 许可证开源。鼓励 fork 与替代引擎。

<!-- section: design-principles -->
## 设计原则

1. **每个文件都带 schema 版本** —— `"schema_version": "0.1.0"` 用于迁移检测
2. **必填字段最少** —— entity 只要 `id`、`kind`、`name`、`schema_version` 这四个
3. **`additionalProperties: true`** —— 未知字段保留而非剥离(向前兼容)
4. **加载时校验** —— 不兼容版本直接拒绝并明确报错
5. **deny-first 权限** —— agent 契约默认 DENY ALL;每一项读写都必须显式声明
6. **folder = bundle = schema** —— 分发布局*就是*契约;上传到 S3 的 zip 必须能被对应的 `*-bundle@0.1.0` schema 校验通过

<!-- section: versioning -->
## 版本策略

当前 schema 版本:**`0.1.0`** —— 初稿,可能有破坏性改动。每个 schema 有独立的 `$id`:`ludic://schemas/<domain>/<name>@<version>`。破坏性变更需要新版本号 + 迁移脚本。目标:`1.0.0` 进入生产稳定态。

Bundle / 内容版本(上传时的 `--version`)与 schema 版本**互相独立** —— 它标记的是内容构建,不是 schema 构建。同一份 world 可以发很多个内容版本,但仍 pin 在同一个 schema 版本上。
