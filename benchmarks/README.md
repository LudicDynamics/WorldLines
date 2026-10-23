# NeonRP / WorldLines 引擎 benchmark

引擎的最终逻辑靠 benchmark 迭代出来;每个技术选择都要有实验佐证。这个文件夹是那套实验的家。
**原则:跑过的不重跑。** 每次跑都归档,归档带代码指纹;代码没变就直接读归档,页面、对照、评审全部离线可出。

## 三十秒上手

```
cd NeonRP
uv run python benchmarks/bench.py status              # 每套题最近一次跑在哪份代码上,过了几题,新鲜还是 STALE
uv run python benchmarks/bench.py run aliveness       # 代码没变 → 直接 skip 并指向归档;变了才真跑(≈3 min)
uv run python benchmarks/bench.py all                 # 四套题里 STALE 的那些,串行跑完自动归档
uv run python benchmarks/bench.py all --failed-only   # 只重跑上次有失败的套题
uv run python benchmarks/bench.py show aliveness      # 最近一次归档逐回合看:分数、失败项、艾琳娜台词(零调用)
uv run python benchmarks/bench.py compare             # 对照页(全部历史跑次并排),离线
uv run python benchmarks/bench.py compare --critique  # + deepseek 逐回合评审;只评还没评过的回合(增量)
uv run python docs/benchmarks/reading.py              # 读本:给人读的全文页(每回合各版本全文 + 你的判断 + 盲读)
uv run python docs/benchmarks/ablation.py             # 消融矩阵 + 论文式页面(ablation_prose.json 是分析稿)
uv run python benchmarks/bench.py play v3-sjudge      # 新脚手架一个 stoneford-elena,按这个臂的开关开 TUI 试玩
uv run python benchmarks/bench.py play v2b --repl     # 同上,进 neonrp play REPL(/trace /debug 可看编排)
```

臂名 = `common.ARMS` 的键:`v3-sjudge`(完整)· `v3-speak`(无判断器)· `v3-act`(角色自跑 loop)· `v2b`(旧引擎)· `v3-noloop` · `v3-noadj` · `v3-lean` · `v3-split`。试玩世界落在 `~/.neonrp-bench/<臂>-<号>/`,每次新开,互不影响。

需要:`~/.neonrp/config.json` 里有 provider preset(默认 deepseek)与 Jev key(`models.typesafe.api_key`)。真机臂**串行、错峰**跑(deepseek 深夜拥塞过,单次 100–270 s,同时跑两个臂时间作废)。

## 公开的题库与实验记录(10-13)

论文和开源仓用的是这一份:`benchmarks/index.html`(全部用例 + 全部实验)· `benchmarks/catalog.json`(用例一览:类别 · 玩家目标 · 检查项 · 来源)·
`benchmarks/records/<实验>/`(每个实验一页 `index.html`,含每一遍的检查和完整对局文字)。原始跑次仍在 `docs/playrecords/`(不导出),`import` 只拷能公开的部分。

```
uv run python benchmarks/site.py catalog                     # 用例改了 → 重出 catalog.json
uv run python benchmarks/site.py import <实验> --title … --question … --group "名字|commit|label1,label2" [--summary kpi.md] [--src 旧 worktree/docs/playrecords]
uv run python benchmarks/site.py build                       # 重出全部页面
```

## 文件夹

10-03 起分两处:**`benchmarks/` 只放可以公开的**(套题、用例、跑法、公共框架;导出到开源仓);
**不能公开的放 `docs/benchmarks/`**(继续进 git,但 `docs/` 永不导出):artifact 快照、实验脚本、页面生成器及其产物。

```
benchmarks/                    ← 可公开
  bench.py            入口:status / run / all / show / import / compare(见上)
  common.py           臂定义、脚手架世界、Turn、Jev 评分、风格指标、页面渲染、loop_stats
  compare.py          对照台生成器:读归档 → 一页并排 + LLM 评审(compare_page.html 是模板;bench.py compare 用)
  fulllog.py          整局日志渲染(adversarial.py 用)
  adversarial.py      对抗用例第一批
  adversarial2.py     对抗用例第二批 + 长用例(A–I · GTA · N1–N8 · J / K 组)
  plan_cases.py       先商量、后清算的用例(PL1–PL15):目标、台词、检查(公开)
  plan_loop.py        这些用例怎么一拍一拍跑(私有层,不导出;suite.py 真跑时才需要)
  testbed.py          三玩法对照(石津剧情包 · 狼人杀 · 大富翁)
  suites/
    aliveness.py      E7 活人感五条(每场景先把艾琳娜锚回玩家身边)
    consistency.py    E5 一致性:异地 / 同行 / 分开重逢 / 跨镇
    negotiation.py    E6 协商:说服裁决,轻自判 / 重掷骰,K 局
    speed.py          E1 速度:同 8 句 × 臂
    judge.py          E0 判断器一致性:Jev vs 替身
  runs/               临时输出(git 忽略);bench.py 跑完即复制进归档

docs/benchmarks/               ← 私有,永不导出
  archive/            历次跑分 / 整局日志 / 对照页的 artifact 快照(含完整提示词;INDEX.md 是目录)
  ablation.py · report.py · reading.py · catalog.py · compare_labels.py · history_all.py · fulllog_tabs.py · world_diff.py ·
  isolation_page.py · judge_compare_page.py · nego_page.py · per_question_page.py · testbed_page.py · adversarial2_page.py ·
  shape.py · adv_shape.py · raw_compare.py · sections_report.py · marks_probe.py · marks_report.py · probe_forms.py
                      实验 / 探针 / 页面生成器(从仓库根跑:uv run python docs/benchmarks/<x>.py)
  CATALOG.md · catalog.html · ablation_page.html · ablation_prose.json · reading_page.html   生成的页面与模板

docs/playrecords/bench/<suite>/<date>-<label>-<fp7>/   归档(进 git,私有):out.json · trace.jsonl · html · page.html
docs/playrecords/bench/INDEX.json                      索引:suite · arm · label · date · git · fingerprint · summary · path
docs/playrecords/e{1,5,6,7}-0925/                      09-25 之前的手工归档(compare.py 也读)
docs/playrecords/compare-0925/                         对照页 + 评审原文的一次快照
```

## 新鲜 / STALE 怎么判

`fingerprint(suite)` = `src/neonrp/core/*.py` + `benchmarks/common.py` + 套题文件三者内容的 sha256 前 10 位。
同 suite + arm + fingerprint 已有归档 → `run` 直接 skip 并打印那条归档;`--force` 才重跑。
改了引擎核心任何一个文件,四套题全部 STALE —— 这是故意的:数字只对产生它的代码负责。
只改了 `bench.py` / `compare.py` / 页面模板不算(它们不改变数字)。

`import` 把已有的记录文件夹登记进索引而不重跑(`--as-current` 声明引擎核心自那次以后没变)。

## 评什么:活人感五条 + 文字两条

| # | 活人感 | 哪套题在测 | 怎么判 |
|---|---|---|---|
| 1 | 我说出需求时,角色不会无视我的需求 | 协商 N1 / N2 · 活人感 A1 | Jev:「角色回应了玩家的需求吗」;裁决链里 asked / outcome |
| 2 | 角色不会过于执着于自己的需求而忽视外界 | 协商 N3–N5(ignored 分)· 活人感 A2 | Jev:「角色注意到外界的变化了吗」「是否只顾自己的事」 |
| 3 | 角色理解现在的环境,有独立的思考过程 | 一致性 C1 / C3 · 活人感 A3 · S-judge 的判断链 | 确定性:视角 / 位置;Jev:「台词体现了对当前环境的理解吗」;思考链公开在回包 |
| 4 | 危险和绝境中能找到巧妙的决策路径 | 活人感 A4 | Jev:「角色提出了具体可行的应对吗(不是空喊)」 |
| 5 | RP 过程中与玩家共情 | 活人感 A5 | Jev:「角色表现出共情了吗(不是敷衍、不是转移话题)」;S-judge 的 confides 读数 |
| + | 文字风格易读 | 所有套题的每回合 | 字数 / 句长 / 对白比 + Jev「过于凌乱 / 恰当 / 过于简洁」「容易读吗」 |
| + | 说话方式像个人 | 所有套题的每回合 | Jev「像真实的人,而不是旁白 / 说明书 / 客服吗」 |

另外两条工程指标:**速度**(整回合墙钟中位 / p90,spans 分段)和**一致性**(位置 / 在场 / 视角的确定性检查)。

## 套题

| 套题 | 实验 | 输入 | 测什么 | 一次多久 |
|---|---|---|---|---|
| aliveness | E7 | 五条各 2 句(A1–A5)+ 文字两条 | 活人感五条的 Jev 评分 + 风格 | ≈3 min |
| consistency | E5 | 异地询问 · 同行三跳 · 分开重逢 · 跨镇两拍(11 句) | 位置 / 在场的确定性检查 + Jev 评分 + 环统计(R9) | ≈3 min |
| negotiation | E6 | 6 句说服,轻 / 重交替,K 局 | 分量判对、意愿、骰 / 目标、结局、台词≈结局、不理玩家率 | ≈6 min(3 局) |
| speed | E1 | 同世界同 8 句 × 臂 | 墙钟、spans、ops 合法率 | ≈3 min / 臂 |
| judge | E0 | 记录里的情境 × 判断器后端 | Jev vs 替身的一致率与延迟 | ≈1 min |

每套题的输出:`out.json`(每回合全记录:输入、预判、角色回包与判断链、叙事全文、ops、位置、评分、风格、spans、每次直出的 proposals)+ 每臂 `trace.jsonl` + `trace html` 报告 + `page.html`(可直接发成 artifact)。

## 臂(engine 配置)

`common.ARMS`:`v2b`(今天的 main)· `v3-speak`(无判断器,soul 一次问答)· `v3-jev`(Jev 预判 + settle)· `v3-sjudge`(Jev + S-judge 判断链 + 说服裁决,当前默认)。每套题对每个臂跑同一份脚本,臂与臂的差就是那个开关的价钱。

## 判据(过 / 不过)

- 确定性检查:全过才算这一回合过。
- Jev 评分:p ≥ .5 视为「是」;与期望一致才过。Jev 是评分器不是裁判,人看全文页定最终。
- 速度:中位 ≤ 10 s(E1 已达);p90 记录但不作门槛(provider 抖动)。
- 风格:三档分布 + 字数 / 句长 / 对白比,只记录,由人定。
- LLM 评审(`compare --critique`):deepseek 给同一回合的各版本排名 + 一句话 + 套题总评。它是第二双眼睛,不是分数;它和 Jev 不一致的地方(E1:最快的 v3-sjudge 不是文字最好的)才是要看的。

## 一次改引擎的标准流程

1. 改 `src/neonrp/core/`,`uv run pytest tests/test_engine_v3.py -q`。
2. `bench.py status` → 全部 STALE。`bench.py all`(或只跑相关套题)→ 自动归档 + 索引。
3. `bench.py show <suite>` 看失败项;有失败就回到 1,修法带回归测试。
4. `bench.py compare --critique` → 页面进 artifact;数字进决策日志对应的 R/S 行。
5. 提交:归档 + 索引 + 决策日志一起。

## 与文档的关系

选择与证据登记在开发仓的决策日志;各次实验的结果见 `benchmarks/records/`;原始跑次在开发仓的 `docs/playrecords/`(不导出)。
