---
title: "路线图"
description: "已经发了什么、正在做什么、接下来想做什么。不写日期。"
---

<!-- section: shipped -->
## 已发布:1.0.x

完整记录见[更新日志](/docs/changelog)。要点:

- **两种本地界面**:`worldlines`(本地网页)和 `neonrp`(终端启动器),从 PyPI 或 GitHub 安装,启动时自己更新;在线玩在 [worldlines.gg](https://worldlines.gg) 和 iOS App
- **两拍回合**:先商量、再清算;判官(Jev,或这局自己的模型)判断谈没谈妥
- **状态先写下、后台再复核**,改了什么会告诉你
- **模板和玩法合约**:四份官方合约(解谜跑团 · 开放冒险 · 剧本杀 · 恋爱陪伴),发布前按合约检查
- **角色库独立**:世界里只放角色的 link,一个角色进很多世界
- **导出 / 导入**:模板和角色打成一个包带走;SillyTavern 角色卡直接导入
- **本地内置两个世界**:灰橡宅、石津镇;其他官方世界在 Hub 里
- **开源**:引擎 NeonRP(Apache-2.0)和产品 WorldLines(AGPL-3.0)都在 [GitHub](https://github.com/LudicDynamics/WorldLines)

<!-- section: now -->
## 正在做

- **发布流程**:上传的世界先成草稿,审核后上架;上传前检查密钥、封面、立绘和四种语言的标题简介
- **存档变回放**:把玩过的一局导出成回放,分享到 Hub
- **更多官方世界**,以及让现有两个世界更稳、更好玩

<!-- section: next -->
## 下一步

- 开局时从角色库挑一个角色当你扮演的主角
- 网页上也能撤销、回到某一回合
- 文档的日语和韩语版本

桌面版:macOS(Apple 芯片)有 [NeonRP 桌面 app](https://worldlines.gg/downloads/NeonRP_aarch64.dmg),第一次启动时自己装好引擎;没有公证,首次打开要在「系统设置 › 隐私与安全性」点「仍要打开」。Windows 和 Intel Mac 还没有安装包,请用 `pip install worldlines`。

<!-- section: protocol -->
## 开放规格

世界、角色、模板、玩法合约和规则包的规格都是公开的,见[规格](/docs/developers/specs)。
