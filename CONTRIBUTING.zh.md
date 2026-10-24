# 为 WorldLines 贡献

**语言:** [English](./CONTRIBUTING.md) · [简体中文](./CONTRIBUTING.zh.md) · [日本語](./CONTRIBUTING.ja.md) · [한국어](./CONTRIBUTING.ko.md)

感谢你考虑贡献——bug 报告、修复、世界和想法都欢迎。

## 这个仓库怎么运作

这个仓库是 WorldLines 的公开发布仓。开发在上游(一个私有的开发仓库)进行;每次发布在这里落成**一个发布提交**
(压缩后的快照)。所以这里不会有细粒度的提交历史——想知道改了什么,请看发布说明。

## Issue

- **Bug:** 请写上 neonrp / worldlines 的版本、操作系统、复现步骤,以及预期结果和实际结果。附上日志或截图会更好。
- **想法:** 欢迎功能建议、新玩法包、世界或模板的提案——开个 issue 一起聊。

## Pull request

PR 请直接提到这个仓库。

1. 接受的 PR 会**先合进这个仓库**,你的署名留在这里的公开历史中。
2. 之后再带回上游,随下一次发布一起发出。
3. 维护者会在 PR 里注明它进了哪一次发布。

一个 PR 只做一件事,并写清楚*改了什么*和*为什么改*。较大的改动请先开 issue,对齐范围后再动手写代码。

### 贡献者许可协议(CLA)

第一次提 PR 时,合并前需要签署我们的[贡献者许可协议](./CLA.md)(CLA,英文原文具有约束力)。机器人会在 PR 下留言,照它给的那句话回复即可完成签署。只需签一次,之后的贡献都适用。著作权仍归你所有;CLA 让我们可以按本仓库的许可证发布你的贡献,也可以用在基于它的 WorldLines 产品里(在线服务和应用商店里的 App)。

## 目录与许可

| 目录 | 是什么 | 许可 |
|---|---|---|
| `neonrp/` | 引擎(Python) | Apache-2.0 |
| `worldlines/` | 产品:网页界面(`worldlines/ui`)、桌面壳(只有代码,还没有发布)、启动器包、模板、示例世界 | AGPL-3.0 |
| `documents/` | 规格与文档站正文 | CC BY 4.0 |
| `benchmarks/` | 引擎设计决定背后的测试套件 | 代码 Apache-2.0 · 数据 CC BY 4.0 |

贡献按你改动的那个目录的许可接收,另加 [CLA](./CLA.md) 里授予的权利。

## 开发环境

引擎:

```bash
cd neonrp
uv sync --all-extras --dev
uv run ruff check src tests
uv run pytest -q
```

网页界面:

```bash
cd worldlines/ui
npm ci
npm run lint
npm run build:local
```

提 PR 前请确认相关检查都通过。

## 创作世界、角色和模板

用 Claude Code 或 Codex 打开仓库,使用工作台(仓库根目录的 `CLAUDE.md` / `AGENTS.md`),配合
[`documents/spec/`](./documents/spec) 里的规格。提交前用 `neonrp template lint`(模板)和 `neonrp validate`(世界)检查。

## 密钥

永远不要提交密钥。API key 只放在你自己机器上的 `~/.neonrp/config.json`——不要出现在世界、模板、测试或截图里。

## 行为准则与安全

请保持得体。预设善意。批评观点,而非批评人。完整规范见 [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)。
安全漏洞请按 [SECURITY.md](./SECURITY.md) 私下报告,不要发公开 issue。

## 联系

- Issues:https://github.com/LudicDynamics/WorldLines/issues
- Discord:https://discord.gg/HJYWbdqWrE
- Email:`info@worldlines.gg`
