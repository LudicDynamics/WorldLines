# Changelog

> 发布版本号见 `pyproject.toml`（当前 v1.0.3）。下方 v0.9.x 是早期 docs-pack 旧编号，保留作历史。

## neonrp 1.0.3 (2026-10-24)

本地版(TUI + 本机网页)从这一版起以 GitHub 仓库 LudicDynamics/WorldLines 为主要安装入口,worldlines.gg 只放在线游玩;`neonrp` 裸命令进「Welcome to WorldLines」启动器,启动时自动检查并更新到最新版。

- **TUI 去掉 `--mcp` 模式和 Claude Code 预设**(1.0.2 的勘误条:当时没进包),连带删掉早已不用的面板和旧命令;`neonrp tui --from` 只认模板包
- **没有判官也能谈妥**:没有 Jev、没登录、没配判断模型时,商量拍「谈没谈妥」这一题改由这局自己的模型回答(`turn.plan_loop_own_judge`,默认开;deepseek 实测每拍多 3–9 秒),不再只认「定 / 就这么办 / @dm」;`/status` 显示「由你的模型判断」;本局第一个商量拍下面一行淡字说明谁在判、`/login` 可开 Jev
- **自动更新**:正式安装(pip / uv tool / pipx)启动时发现新版就直接更新并重启进新版(`updates.mode = auto`,默认);想先问一声 `/update mode prompt`,只提示 `/update mode notify`;源码安装照旧只提示
- **启动器**:记住的模型现在跑不了(Worldlines 会话过期、key 删了)时回选模型页,不再掉进命令行的「Paste API key」;明确选 Worldlines 但没登录时提示 `/login`,访问密钥粘贴只是备选
- **修:TUI 快捷栏按钮没字**(Textual 7.5 的 Button 自带上下边框吃掉了一行高的按钮;改用 compact 按钮)
- 模板补上石津镇 P20 / 艾琳娜 P10 / 狼人村 P01 的结局图(1.0.2 缺)
- **iOS 创作台**:本地 / iOS 也能提交到默认区、「我的作品」改版再提交,同一模板可以有好几份作品;生图额度不够时接 App 内方案页
- **小手机推进(阶段 B)**:订阅角色按节奏记账、点进聊天补跑,世界执行时别的角色异地执行并产出世界卡;跨进程锁
- **编排节奏**:创作台「照常 / 快商量」各出一张只读图,节点上标出设定
- **角色名跟界面语言走**,缺那种语言先退英文
- **举报 AI 内容**:游玩页和小手机都能举报、屏蔽,四语
- **Hub 载入**提示
- **开源仓**:加贡献者许可协议(CLA)和许可证边界检查
- **创作台说明里的语言名**用界面语言的叫法
- **新产品图标**(三体轨道 · 夜空三星球):网页、桌面版换上;Hub 顶栏徽记、载入中徽记呼吸
- **角色立绘可以指向自己的另一张图**:`soul.json` 写 `"assets": {"sprite": "portrait"}` = 站姿就用全身立绘,不复制文件;香料魔女乐师 / 塞维林用上
- **修:剧情图多语言名字**按叙事语言显示(之前显示 `[object Object]`),改名只写回当前语言
- **修:商量拍数值设成 0 就是 0**(之前被读回默认)

## neonrp 1.0.2 (2026-10-23)

PyPI 上第一个 1.0 版本:1.0.1 只打了本地包没有发出,它的条目随这一版一起到用户手里。

- **修:写状态里的增减写法被丢掉**。`<vars>` 里 `player.gold -6` / `-= 6` / `+= 2` 这类相对写法,10-04 起的解析器只认 `名字 = 值`,整行跳过、钱没扣(40 拍里 deepseek 快写 5 拍、慢写 2 拍);现在按 09-27 的变量简写规则算成增减,和 `<files>` 一致
- **不在玩家身边的角色跨镇也走远行规则**:要去别的镇就上自己的那条驿路,世界日期过够路程天数才到对面城门(之前 69 例回归里 21 例罗文开局就从碧石镇直接出现在石津镇北门);他写的地名只在他自己的镇里解析,没有就拒绝并列出能去的地方;异地行里别的镇的地点带镇名(「翠晶酒馆(碧石镇)」);修读档时角色裸地名被挂到玩家所在镇
- **慢写有了自己的提示词位**:引擎多读一个 `transition_slow` 单元,只拼给开思考的后台修正,快写看不到;开源引擎不带这个文件。私有层用它放「思考预算」(10-23 C:同样 40 拍离线三遍,准确率持平,慢写最慢 15.6 → 9.8 秒、没有一次超过 10 秒,三遍答案一致的拍 20 → 27;真机 12 用例确认在 A 的波动范围内)
- **回归套件**:等上一拍的后台修正落地再快照(之前修正落到下一拍窗口里,被当成「商量拍改了状态」)
- ~~TUI 去掉 `--mcp` 模式和 Claude Code 预设~~ **勘误(10-24)**:这一条没有进 1.0.2 的包(feat/tui-slim-2 当时合进的是 fix/away-soul 分支,不是 integrate/next);1.0.2 里 `--mcp` 和 Claude Code 预设还在。10-24 已合进 integrate/next,随 1.0.3 发

## neonrp 1.0.1 (2026-10-23,未发出,并入 1.0.2;worldlines 这一版不发)

1.0.0 只打过本地 tag,没有发出。自 1.0.0 起 746 个提交,这里只列要点;下面「Unreleased」几条也在这一版里。

- **写状态先快后修正**:一拍先用关思考的快版本写下状态,开思考的慢版本在后台复核、1–3 秒后修正;玩家先行动就取消;最多 90 秒;TUI / 网页都看得到「复核中 → 修正了什么」
- 后台复核回来时这一拍还在收尾:**等它收尾再修正**(之前当成「忙」丢掉,真模型下 64% 的修正这样没了);只有玩家真的发了下一句才取消
- **账号用户的后台复核模型按账号权益走**(默认`turn.transition_slow_model = auto`);没登录 / 没额度用这一拍自己的模型
- **商量里谈定的钱由引擎直接结**:计划板上的「花费」行,清算时对钱包,够就落账、不够就不扣;不再靠状态转移去猜
- **修:deepseek 回合卡 60 秒**(流式读线程丢了「关思考」设置)
- **登录 Worldlines 后新开的局默认走 Worldlines 模型**;在 /settings 里自己选过的仍优先
- **TUI**:`/status` 变成可左右切换的页签面板(玩家 · 每个角色 · 用量);`/` 补全列出技能(数值 + 说明)、`/技能 ` 列出对象、`@` 人、句中 `#` 地点和物品;输入框上方快捷栏;骰子结果下写「为什么 / 为了」;已登录也能直接 `/login` 换账号;修 `/status account`、`/login` 崩溃
- 两拍编排由模板打开、小手机角色推进、联网同桌、标准前端(Hub / iOS 游玩页)等 10-08 以来的工作

## Unreleased

- **公开发布门槛**:上传前扫密钥(会进包的文本里 `sk-`/`AKIA`/`api_key` 等,及 `.env`/`*.pem`),命中一律拒;封面与每个角色的立绘、中英日韩四语标题/简介(`game/meta/hub.json`,表单里 ✦ 自动翻译)不齐只能传草稿;CLI 公开上传同样把关(`--force` 不跳密钥)
- **上传 = 草稿**:Hub 侧 draft → review → published,自己不能翻公开,管理页「申请上架」,审核通过才上目录
- **存档 → 回放**:`neonrp replay export/upload <run>`;launcher 上传面里「存档」条目走回放线(只带 story / feed / 幕后 / 封面);Hub 回放馆 `/replays`
- 新地点自动进所在镇的 `town_map`,cast 的角色自动进镇名册 / 有位置;角色库卡片 `b` 回它的工坊;play prompt 不再让 world agent 扫 `souls/`

## v0.4.2 (2026-09-11)

更新逻辑分包:`neonrp` 只升引擎,`worldlines` 升 shim(带它钉死的引擎)。

- **`neonrp` 裸命令也有启动时更新横幅**(之前只有 `worldlines` 有);TUI `/update apply` 按入口选包,不再写死 neonrp
- **`releases.json` v2**:`packages.neonrp` / `packages.worldlines` 各自版本;顶层 `latest.stable` 留给老客户端、按 worldlines 填;由 `scripts/build_release_manifest.py` 合并生成,两个仓各改自己那条
- 修:导出包带回 `.neonrp/manifest.json`,hub 下载 / 导入模板式世界恢复

## v0.4.1 (2026-09-11)

TUI 变成世界的 coding agent:build / play 在同一个地方切,角色和地点由 agent 著述,Obsidian 观察台从上方看世界;世界三语;launcher 回到仪表盘、一键进最近存档。

- **`/mode` 在世界内真切 build↔play**;build agent 自己建角色并入世(`cast_soul` 走确定性注册,playthrough 不由 LLM 手写)
- **命令面 48 → 17**:`/open` 收编 `/worlds` `/worldlines` `/continue`;角色四动词 `/create` `/cast` `/remove` `/reset`;`/import` 一个入口按内容分派;退役命令归档在 `legacy_commands.py`
- **`/init` 从零建世界**、**`/vault` 一键进 Obsidian**(立绘/封面进 `素材/`,`世界.canvas` 几何层级:角色卡⊂地点框⊂世界框)、裸 `/open` `/init` `/cast` 弹选单引导、`/auth` 走设置界面
- **修:新局不再落 stub** —— 之前 scaffold 取 `list_presets()[0]`,装了 `claude` CLI 时那格是 Claude Code 虚拟预设 = stub;现在 `default_model_ref()` + 继承当前世界的模型
- **launcher 仪表盘回归**:PLAY 行 + 世界库(创作 / 上传 / 一览游玩)+ 角色库(对话 / 创作 / 上传 / 一览对话)+ 设置/退出;**⚡ 接着上次**一键进最近存档;一览改卡片(图在框里、字在上下);选完模型直接进 build 或 play,TUI 里不再出现浏览器选项
- **修:输入卡顿** —— play 面立绘的 matrix 动画每帧 ~0.5-1 s 在 UI 线程跑,按键排在帧后面;帧挪到 worker 线程 + 打字时暂停 + 渲染缓存;`NEONRP_PORTRAIT_STATIC=1` 可只画一帧
- **修:右上角状态栏真能滚**(之前叶子 Static 的 overflow 是死的),带滚动条与 ▲▼;报错面板加「⚙ 换模型」
- **世界三语**:stoneford-elena / kagura-island 的 zh/en/ja 平行世界,叙事与 soul 提示按 `output_lang`
- **CLI 分叉**:`neonrp` 裸 = TUI launcher,`worldlines` 裸 = Web;导出安全边界 deny-by-default(不再泄露 `.neonrp` 密钥/存档)
- hash-first 假说③根除(compose 与 land 的 version_hash 同源)

## v0.4.0 (2026-08-14)

一个更大拆分的早期切片:引擎正在变成两件专注的产品 —— 命令行驱动的超轻量模拟工具(agent 自己决定何时互相说话)与从外部观察活世界的专用观察工具。详见 `docs/releases/v0.4.0.md`。

- **引擎 / 前端分离**:Web UI 与桌面壳移到开源 WorldLines 仓;本版 wheel 仍内嵌 SPA(形态 A)
- **模式收敛为二**:orchestrator + MT Agent Team,fast 退役并 normalize 到 orch
- **Play DB(services/ledger)+ §14.5 契约地基**落地(multi-agent,85 test)
- **两趟回合 + 跨组校准 + 本地编排 debug 视图**;Elena desync 根因修复

## v0.3.6 (2026-07-25)

命令行回归 TUI + 位置一致性引擎修 + 一批体验修复。

- **命令行 `worldlines` 默认进 TUI** —— Web Launcher 归 Tauri 桌面壳(经 `neonrp web`);终端用户直接进游玩启动器
- **修:玩家位置随剧情真实落地** —— 过去只有角色会移动,玩家状态永远停在出生点(叙事进了主街、状态还在北门);现在玩家与角色走同一条"世界裁定 → 地图校验 → 写回"落地链
- **修:位置裁定成为每回合结算义务** —— 世界代理漏报移动会被引擎检测并在下回合强制补结算,叙事与状态不再渐行渐远
- **修:远方角色不再被话术拉回场** —— 角色和你不在同一地点时,即便你点名召唤,world-agent 也如实呈现"其人不在此处"(引擎硬注入物理在场事实)
- **回合生成中有可见反馈** —— "世界推演中"跳秒提示常驻到出字为止;进场动画完整覆盖"灵魂并行唤醒"阶段,慢模型下不再中途空白像卡死
- **自适应显示缩放** —— 字和图标随窗口大小自动等比缩放,治 4K / 高 DPI 太小
- **进场不再白屏一瞬** —— 进游戏 / 工坊试玩改客户端跳转,消除整页 reload 白屏
- **JSON / 文件查看加折行开关** —— 默认折行、可切不折行;不折行时按钮不再被 agent 面板挤走
- **内置 Kimi K3 provider** —— 设置可选、填 key 即用(该模型仅接受 temperature=1,已内置)
- 内部:删 12 件 hub 死代码;移动链契约对齐(soul moved_to 明确为提案)

## v0.3.5 (2026-07-17)

Hosted Hub 引擎地基 + 自带 API 端点(dev 沙盒栈锁这版 wheel)。

- **自定义 OpenAI 兼容 API 端点回归**:设置页与首启/开局前的模型面板都能填自定义 provider(Base URL + 可选 key + 自由填模型名)——SiliconFlow、本地网关、自建代理直接接入。TUI 一直有、新 web launcher 丢了的入口补回,酒馆式表单
- **下载/导入的多智能体世界新开局不再退化成单一叙述者**:它们的 `playthrough.json` 落在包根而非 `.neonrp/`;开局创建时在咽喉处迁移,一并治好下载、导入与手搓世界
- **世界提审 × 审查线**:工坊提交卡 + 管理员审查队列(待审/通过/驳回,自动可玩性预检,一键通过 / 附言驳回)
- 登录换取 SSE 鉴权 cookie;hub 构建零烤死端点(运行时同源解析)
- (内部)Hub/Compute 分层引擎面:registry 下载入库、可覆盖 registry 基址(隔离栈结构上碰不到生产存储)

## v0.3.4 (2026-07-15)

升级死循环终结版(壳↔引擎版本对齐闭环)。

- **自动更新打破钉版**:壳引导装引擎会在 uv 收据里留下 `==版本` 钉;`uv tool upgrade` 尊重钉版 → 永远无操作,用户每次启动被问"更新?"、答应了也停在原版本。uv 路线改 `uv tool install --force`,重新解析最新并改写收据
- **壳启动版本对齐**:壳读 uv tool venv 的 dist-info 拿引擎实际版本,低于壳版本自动钉装升级——"壳新引擎旧"(0.3.3 壳复用 0.3.2 引擎导致看门狗 bug 复发)不再可能

## v0.3.3 (2026-07-15)

Windows 桌面壳致命修复:引擎不再"开门 2 秒后自杀"。

- **父进程看门狗 Windows 语义修复**:`os.kill(pid, 0)` 探活在 Windows 上是 CTRL_C_EVENT,对壳的 pid 调用必抛错 → 看门狗把活着的壳当死了 → 引擎启动 2 秒后自杀(Tauri 里 Welcome 渲染后 API 全灭、模型面板卡"读取中"的根因;手动 `worldlines` 不带 --parent-pid 所以一直没事)。Windows 改走 OpenProcess 探活
- **壳看护**:引擎跳转后死亡不再静默变砖——全屏浮层给出退出码 + stderr 尾巴
- **模型面板**:读取失败改为报具体错误 + 每 3 秒自动重连,不再永远"读取中"

## v0.3.2 (2026-07-15)

hosted Hub 的引擎侧地基版(dev-hub 沙盒栈依赖此版 wheel)。

- **修复:下载/导入形状的 multi-agent 世界新开局静默降级成单叙述者**(playthrough 在根而非 `.neonrp/`,`instantiate_run` 现在在所有 run 创建的咽喉处迁移)——souls 不展开 + 每回合权限报错的根因
- hosted 融合引擎面:`/api/v1/local/hub/download`(registry 下载进账户库)、`/api/v1/local/hub/submit`(工坊提交审查)、registry 基址可覆盖(隔离栈结构上摸不到生产 S3)
- 登录 cookie 换发(SSE 鉴权通道)、hub 构建零烘焙生产端点(运行时同源解析)
- 工坊「提交审查」卡 + Admin 审查队列(pending/approved/rejected 三态,自动预审红旗,一键通过/留言退回)

## v0.3.1 (2026-07-14)

v0.3.0 的 CI 修补版 + 门面配置动线收尾。

- **Windows 修复**:引擎全部文本读写强制 UTF-8(此前 Windows 默认 cp1252,中文世界一读就崩,CI 抓到);导入指令里的路径统一正斜杠
- **设置动线重排**(用户视角):设置升为顶部导航一级页 `/local/settings`;Welcome 第一屏加语言切换 + API 面板拆「模型接入 | 图像(可选)」两页签(ComfyUI 精简配置第一屏可达,高级 workflow 走设置页)
- 图像生成完整配置面板对齐 TUI(自定义 workflow + 4 节点 id)
- 档案室:角色立绘缩略/上传;世界与角色工坊补封面/立绘生成页签

## v0.3.0 (2026-07-13)

Web Local 版 —— WorldLines 从终端工具长成完整的本地 Web 产品。

- **⚠ 入口变更**:`worldlines` 现在默认**打开 Web 界面**(起引擎+浏览器进 LocalShell);终端 TUI 改为 `worldlines tui`。双击启动器自动继承新默认
- **全新游玩界面(stage)**:多角色 lanes(立绘头像)、逐回合回滚、AGENT MAP、**回合过程轨**——世界思考→角色行动(每 soul 状态芯片+思考心声)→位置裁定→叙事成稿,逐段点亮,完成收起为一行;立绘按竖/横图自适应
- **设计统一**:一套暗阶+烛绿贯穿店面/书房/工坊/游玩(Hub 紫退役);字体对齐 www(JetBrains Mono / Young Serif);白主题(档案纸+赤陶)一键切换
- **导入重做**:世界卡(PNG 图卡/JSON/ZIP)和角色卡导入都进**工坊编辑流程**——源卡原样留档+界面可见,右侧三选项:①**制定转换计划分批执行**(大卡推荐;逐批落盘、中断可续)②一次性转换 ③手动;不再直通库
- **秘密系统**:世界秘密迁入 `game/secrets/`(audience 定向),非 GM agent 结构上看不见;trust/flag/visited 条件确定性解锁进台账(随回滚回退);"侦查成功"类模糊条件由 keeper 每回合一次批裁;GM 叙事说漏未解锁秘密会被检测并在下回合矫正

- **LocalShell**：引擎直接 serve 完整 Web 产品——游戏门面(`/local/welcome`)、书房(继续游玩/世界库)、创作门、PrePlay 进场界面(模型接入 + 本局确认后再进世界)、游玩工具条
- **备团工作台**：工坊 + 三画布(世界/角色/剧本)+ AI 起草落地，STUDIO_HOME 成为第四个 home
- **引擎防线三件套**：
  - LLM 写坏的 JSON 在写入边界修复或拒绝(deepseek 引号转义问题的完整防线：确定性修复 → agent 重写 → 专职修复请求兜底)，坏文件不再静默落盘
  - `neonrp validate` 换成世界可玩性体检：JSON/playthrough/souls/位置引用/开局 分层检查，输出"✗ 2 个阻断 + fix 提示"而不是 schema 报错墙
  - **位置裁判**：world-agent 的角色移动按地图连接图裁定——镇内自由、跨镇每回合一镇且必须过城门，瞬移物理上不可能；裁定结果注入下回合叙事
- 中文世界名(猫岛等)的封面/删除/继续游玩全修(URL 先 unquote)
- Playwright e2e 测试地基(首批 8 用例)+ CI 发布门禁(测试不绿不发版)
- 修复：换游戏不再 409；tauri splash 源文件误伤
- 进壳每次都过游戏门面(Welcome)；PrePlay 确认后直接进入内容详细的经典游玩页——不再出现第二道 Hub 式入场屏，新开局立即开演
- PrePlay 重做成单页纵向分步，内容对齐 TUI 启动流；前端完成 play/shared/hub/local 四包重排(一份游玩代码两个后端)

## v0.2.15 (2026-07-02)
- 修复：世界导入完成后跑 `/validate`（或其它转发到 CLI 的斜杠命令）直接崩溃退出。导入收尾会把工作目录改名/移走，命令跑完切回原目录时 `os.chdir` 抛 `FileNotFoundError` 炸掉整个 app。现在切回目录做了兜底（旧目录没了就退回世界根目录 / home），不再崩

## v0.2.14 (2026-07-02)
- 生成世界的访谈现在会把 AI 的思考**实时流式显示、自动滚动**（一行行暗色文字流出来，问题生成后自动隐去），不再是一个看起来像卡住的静止 spinner——和生成角色的体验对齐

## v0.2.13 (2026-07-02)
- 修复「生成世界 / 生成角色」一进访谈就永远卡在「◐ 思考中…」、出不来任何问题（所有人都中招）。根因：创建界面把后台 LLM 结果送回界面的内部函数 `_ct` 错写成调用它自己 → 无限递归被静默吞掉 → 2 秒就算完的结果永远到不了界面。两个创建界面（世界 / 角色）都修了
- 防御：从主菜单进入任意流程会先清掉「导入角色卡」的残留状态，避免它劫持之后的创建流程

## v0.2.12 (2026-07-02)
- 修复 v0.2.11 的角色卡导入直接报错 `'WorldLinesLauncherApp' object has no attribute '_get_effective_provider_config'`：导入现在先让你**选一个模型（preset）**，再用那个 preset 的真实 LLM 把卡片补齐成完整 soul——启动器没有游戏内的"当前 provider"，默认配置又常解析成占位模型，所以必须走 preset

## v0.2.11 (2026-07-02)
- 导入 SillyTavern 角色卡现在真正把它变成一个**完整、可复用的 soul**存进角色库：新增 `soul-card-authoring` 技能，用 LLM 把卡片的少量字段**补齐/转化**成完整 soul bundle（persona 内核、背景故事、RPG 机制、行为规则），忠实于卡片人物；导入后可选「立刻开 Soul Talk 玩 / 回角色库」
- 修复：TUI 导入角色卡后启动直接崩成空白终端（根因：导入路径没设 world_id，CLI 静默返回）——现在正常进入；导入失败会明确报错、不再空白
- Windows 双击 `WorldLines.bat` 优先在 **Windows Terminal** 里打开（不再落进 Git Bash/MinTTY —— 那会字体乱、复制粘贴失效）
- 防御：启动选择里没有世界时打印可诊断信息，不再静默黑屏

## v0.2.10 (2026-07-02)
- `neonrp web` 新增「回滚到历史回合」：每个回合下方挂一个内联 ↶ 按钮（REPLAY 条里也有 ⟲），点击即在该回合分叉出一条新分支——git 式，当前这条线原样保留（不丢），game 与所有 soul 恢复到那回合，从那里接着玩
- 底层新增 `commit_subsystem.rollback_to_commit`：基于 M17 commit DAG，fork 时会物化新 soul instance 的文件夹并接续其 `.commits`（补上 `branch_from_head` 缺的一步，分叉出的分支才真正可玩）
- 回滚 UI 走四语 i18n（en/zh/ja/ko）；修复回放关闭后停在回放界面、回不到正常游玩；`neonrp web` 吞掉浏览器 reload 触发的 BrokenPipe 控制台噪音
- 修复 `neonrp web` 输入框的中日韩 IME 回车 bug：输入法组字过程中按回车只确认候选词，不再直接把半成品拼音提交成一回合（`isComposing` 守卫）

## v0.2.9 (2026-06-28)
- 角色移动决定权收归 world-agent：soul 不再自报 moved_to，去向统一由 world-agent 裁定——修复"角色状态说在镇里、叙事说出了镇"的 state/story desync（trial-beta）
- world-agent 的机读控制块（⟦CORRECTIONS⟧）不再泄漏到叙事屏幕：渲染层在流式与最终两处都过滤
- 容错 world-agent 移动块里的 key 错别字（movedto / "moved to"），一个小拼写不再让整条移动丢失

## v0.2.8 (2026-06-28)
- 实体文件可放进子文件夹：`game/<kind>/.../<id>.json` 任意深度都能被索引/检索（kind 仍取 game 下第一层、id 取文件名；扁平世界不变）
- 两段式 soul 移动（propose→correct→apply）+ 共位感知：同场景的 soul 能看到你这回合声明的动作，别处的看不到
- 修复 soul 跨镇瞬移：裸目标只在本镇解析，跨镇必须显式 `T###/node`，否则原地不动
- soul 锁定第一人称视角；话痨模型的碎 JSON（speech 里未转义引号 / `"…"+旁白+"…"`）自动修复，不再丢动作
- Windows 安装后当前 shell 立即可跑 `worldlines`，不必新开终端
- `neonrp web` 关系图：滚轮 + 双指 pinch + ＋/− 按钮缩放；新增最小化/恢复按钮（折叠状态跨回合保持）
- 内置石津世界艾琳娜回归治愈师（去剑系漂移、4 语言重写、Big-Five/fears 富 persona、银发、正名艾琳娜）

## v0.2.7 (2026-06-23)
- 修复 macOS 上中文/日文无法输入：把 textual 钉到 <8（8.x 改了 IME 处理、装机时现解析到 8.x 才坏；Windows 不受影响）
- pip 安装的用户也能自动更新：updater 按实际安装方式（uv tool / pipx / pip）选升级命令，不再对 pip 装的 no-op
- 新版本检测更快：启动时更新检查缓存从 6 小时缩到 1 小时（`neonrp self-update` 始终直连）
- 修复 Windows CI 的 imagegen 测试（`~` 展开同时认 USERPROFILE）

## v0.2.6 (2026-06-23)
- 自动更新对已安装用户真正生效：按 y 能升级（PATH 没 uv 也能找到、成功后自动重启进新版、失败给明确手动命令）；重跑安装脚本也升到最新
- 显示的版本号正确：改成从安装的发行版元数据自动取，不再「显示 0.2.4 功能 0.2.5」
- launcher 单行框能输中文/日文：focus 时把终端光标锚到 caret，IME 候选框不再飘到角落（世界/角色名、API key、casting、对局内回答、游玩输入框）

## v0.2.5 (2026-06-23)
- 新建世界现在是真正可玩的 multi-agent 世界：完整初始化、每个角色独立 soul-agent、自带主角，且进入世界库
- `~/.worldlines/` 拆分为 `worlds/`（你拥有的世界库）+ `plays/`（游玩实例）；首次启动自动迁移旧 `games/`（幂等、不删数据）
- 世界库新增「世界一览 / 角色一览」可浏览 + 删除（内置只读，删世界连带清理其 run）
- `neonrp web` 地图：真实世界图 + 镇内二级地图下钻 + 拖动/缩放，统一到 Hub「关系图·谁在哪」观感
- web 玩法升级：编排进度条、灵魂心象面板、故事排版、玩家 HUD、响应式、继续游戏自动回放上一轮、⚙ 设置弹窗
- 新增 OpenCode Zen provider；ComfyUI 自定义工作流 + 节点 id 映射（引擎 + launcher 设置）
- 地图按真实地名显示且角色不再跨镇跳转（scoped 地址）；修复创建世界 "not initialized"、返回误进游戏、计数过期、端口占用、裸 JSON 泄漏等

## v0.2.3 (2026-06-14)
- `neonrp web` agent lanes 改人话：顶部说明行 + 每角色「此刻在X，不在你身边 / 在X，没注意到你来了」，地点 code 解析友好名（T004→碧石镇），每回合刷新
- `neonrp web` play 栏只剩故事：线索/状态表折叠进角落，`## 时间/地点` 标题 + 工具标记从叙事剥离

## v0.2.2 (2026-06-14)
- 场景感知 placement（multi-agent）：选角界面从世界自带 cast 起步——原生 souls（在场预勾、可取消）+ prior 主角，外部 souls/avatars 叠加
- 神楽島改为真 multi-agent：7 个 soul 在选角出现、进游戏激活（原误标 orchestrator）
- play-loop 叙事累计进可滚动 log（orchestrator/multi-agent ask_user 回合），实时显示在选项上方
- 修：导入酒馆卡不再卡死（build 模式保留 import/write 工具）
- 修：托管存档 zip 下载后 `load-world` 出现在续玩列表
- 修：切换语言后 launcher 全部标签（含 section 标题/导入上传按钮）都重渲

## v0.2.1 (2026-06-12)
**Launcher / 创作流**
- 单屏 launcher dashboard（双入口 IA）+ 开场动画
- Casting 屏：分身（avatar，独立本地存储）选择 + bring-in NPC 同屏放置预览 + game-mode 选择器
- 放置（placement）：mode-aware soul casting、force-confirm NPC 起始位置、land placement via `placement.py`
- Soul authoring 流程（TUI 屏 + CLI 入口）+ `soul-talk` 最小示例世界

**导入 / 卡片**
- 原生文件选择器 + 粘贴-JSON 导入屏；支持拖拽路径导入
- 卡片 i18n 数据模型：world/soul 卡 locale-aware 显示（en/zh/ja/ko）

**Hub / 联机**
- 非阻塞浏览器登录 + 粘贴-token UX；修正 token URL；Hub 上传（browser auth）
- 修 SelectionList 崩溃

**引擎 / 平台**
- orchestrator 委派 + tool-round 优雅上限
- Windows：加固 `install.ps1` + `WorldLines.bat`
- 依赖：Pillow + rich-pixels 转为核心依赖（缺 PIL 不再 SystemExit）
- play-screen 标签 en/zh/ja/ko 本地化

## v0.2.0 (2026-06-xx)
- gameplay 修复一批；casting 屏雏形（game-mode selector、单选 avatar、只读 world 模式）
- 下载的 souls 落入 `souls/` 并出现在 casting picker
- examples：`soul-talk`；templates：stoneford-elena → multi-agent 执行模式

## Unreleased
- Added V0 player-facing run artifacts (visionRP/Obsidian file contract, see `docs/PLAYER_ARTIFACTS_V0.md`):
  - `story.md` append-only narrative log, `feed.jsonl` + `feed.md` "今日动态" digest, `tree.json` worldline snapshot — emitted per landed multi-agent turn next to the orchestration trace
  - `inbox/pending/` directive channel: other clients (Obsidian / Dashboard / Claude Code) drop `.md`/`.txt` directives that join the next turn at the raw-input boundary, then move to `inbox/consumed/`
  - new module `src/neonrp/core/player_artifacts.py`; all writes best-effort (never break a turn); coverage in `tests/test_player_artifacts.py`

## v0.9.3 (2026-03-29)
- TUI build mode now works immediately after `neonrp init` in fresh directories, without requiring local agent scaffolding first.
- Added packaged builtin skills under `src/neonrp/builtin_skills/` and project-level skill loading now falls back to those builtin skills automatically.
- Added TUI Tavern import entry points:
  - `neonrp tui --import-card <file> [--import-id <id>]`
  - `/import sillytavern-card <file> [--id <id>]`
- Improved SillyTavern import ergonomics:
  - PNG/JSON import tool is exposed to build-mode agents as `import_sillytavern_card(...)`
  - non-ASCII card names now derive stable ASCII entity IDs instead of collapsing to `unnamed`
  - agent tool can set destination path and visible name explicitly.
- Fixed Tavern "convert into full game" workflow:
  - added `ensure_playable_scaffold(...)` to copy missing play agents/runtime scaffold
  - normalized `game/meta/active-agent.json` to the canonical top-level `active_agent` protocol
  - updated Tavern import skill/prompt guidance so generated worlds only claim playability after scaffold exists.

## v0.9.2 (2026-02-16)
- Added optional embedding-based retrieval pipeline:
  - new `src/neonrp/core/embedding.py` (adapters + vector index persistence)
  - hybrid fuzzy + vector ranking in `read_context` / `context`
  - automatic fuzzy-only fallback when embedding is unavailable.
- `index build` now precomputes embeddings by default when `embedding.enabled=true`.
- Simplified embedding config workflow:
  - supports minimal config with `embedding.enabled + embedding.model_ref`
  - inherits provider/model/auth/base_url from `models[model_ref]`.
- Applied fixes from `reviews/code_review_20260216.md` across apply/save-load/permissions/CLI consistency paths.
- Added regression coverage for embedding and fuzzy retrieval:
  - `tests/test_embedding.py`
  - `tests/test_retrieval_fuzzy.py`

## v0.9.1 (2026-02-10)
- Added provider-specific request passthrough via model-level `extra` config (`models.<name>.extra`), including OpenRouter reasoning payloads.
- Fixed OpenAI-compatible extra parameter compatibility:
  - unknown extra fields are now routed through `extra_body` instead of top-level kwargs
  - avoids SDK errors like `unexpected keyword argument 'reasoning'`.
- Improved retry behavior for transient streaming failures:
  - conversation loop now retries with fixed backoff `2s -> 7s -> 15s -> 30s`, then stops.
  - streaming/network errors are now classified as retryable and propagated correctly.
- Improved `ask_user` UX in TUI:
  - selected answer is shown inline in the conversation as a user-visible message
  - restored sessions re-render historical `ask_user` selections
  - tool card detail now shows `selected: ...` for `ask_user`.
- Test coverage updates for new behavior:
  - added `tests/test_llm_openai_extra.py`
  - expanded coverage in `test_conversation.py`, `test_conversation_edges.py`, `test_app_v2.py`, `test_llm_retry.py`, `test_llm_streaming.py`, `test_config.py`, `test_per_agent_llm.py`.

## v0.9
- **M10.1 delivered**: TUI/Conversation reliability and operability upgrades.
- Added **ESC interrupt** for in-flight LLM turns in conversational TUI.
- Added configurable per-turn tool-call ceiling via `tui.max_tool_rounds` in config.
- Added **incremental session history saving** (Claude Code-style persistence behavior).
- Added startup/session controls:
  - `neonrp tui --continue` / `--new` / `--verbose`
  - `/sessions` picker modal + `/continue` + `/new`
  - `/verbose on|off|status` with debug JSONL logs.
- Improved TUI telemetry and lifecycle:
  - real-time local token estimation in status bar
  - safer quit path (`Ctrl+Q`) while requests are running.
- Todo workflow compatibility fixes:
  - TodoWrite prompt now includes a **minimal valid example**
  - todo validation aligned to mainstream UX (`<=1 in_progress`, `activeForm` optional, `done` alias accepted)
  - todo rendering stabilized with literal markers ``[x]`` / ``[>]`` / ``[ ]``
  - `/continue` now restores todo list from tool history.
- Documentation refresh:
  - synced `README.md`, `DEV_README.md`, `docs/TUTORIAL.md`, `docs/ROADMAP.md` with latest TUI/session behavior.

## v0.8
- **M9 + M10 stabilization delivered** (conversation-first TUI, ask_user modal, markdown transcript, slash suggestion UX)
- Added coverage补测 wave focused on real runtime paths (not stub-only):
  - `tests/test_conversation_edges.py`
  - `tests/test_retrieval.py`
  - `tests/test_tui_suggestions.py`
  - `tests/test_llm_real_endpoint.py` (real endpoint e2e via `~/.neonrp/config.json`)
- Coverage report updated (`reviews/coverage_report_20260209.md`):
  - Total coverage: **63% → 65%**
  - `core/conversation.py`: 80% → 99%
  - `core/retrieval.py`: 33% → 95%
  - `tui/suggestions.py`: 0% → 99%
- Regression status updated: `803 passed, 7 skipped`

## v0.7
- **M4 Implementation**: Sandbox + Replay milestone complete (290 tests)
- **Pre-M4 Housekeeping**:
  - H7: Fixed `load` command crash-safety (atomic rename strategy)
  - H8: Fixed deprecated `datetime.utcnow()` → `datetime.now(timezone.utc)`
  - H9: Added PNG character card import (pure Python tEXt chunk reader, no Pillow)
- Added `neonrp sandbox new|list|switch|drop` CLI commands
- Added `neonrp replay verify|checkout` CLI commands
- Added `core/hashing.py` — deterministic world tree hash utility
- Added `core/replay.py` — replay engine (staging-based, non-destructive)
- Added `core/system_proposal.py` — system proposal factory for import/game commands
- Added `core/paths.py:validate_branch_name()` — path traversal protection
- Extended `BranchMetadata` with `kind`/`parent`/`fork_event`/`base_save` for sandbox support
- Save now includes `meta.json` (game_hash, head_event, branch) and `events.jsonl` copy
- Atomic `events.jsonl` copy via temp file + `os.replace`
- Import and `game new` now generate system proposals through apply pipeline
- Sandbox switch invalidates `manifest.entities` with `index build` prompt
- Bumped manifest.version to `"0.3"`
- ADR 0011 (sandbox branch model), ADR 0012 (replay and determinism contract)

## v0.6
- **M3 Implementation**: LLM Integration + Skills + Import milestone complete (219 tests)
- **Pre-M3 Housekeeping**:
  - H3: Fixed `agent.py:393` active_branch bug
  - H4: Atomic world/ directory replacement in `apply.py`
  - H5: Empty index warning in `retrieval.py`
  - H6: Standardized delete hunk header in `diffing.py`
- Added LLM adapter Protocol (`core/llm.py`) with stub, OpenAI, and GLM providers
- Added skill tool registry (`core/skills.py`) with per-file deny-first permissions and JSONL audit logging
- Added `neonrp agent run <id> --query "..." [--provider] [--apply] [--json]` LLM-driven agent execution
- Added `neonrp import sillytavern-card` with v1/v2 JSON card support, ID conflict resolution, raw payload preservation
- Added `neonrp game new` scaffolding command with `--force`/`--json`
- Added project config `.neonrp/config.json` with provider/model/CLI defaults
- Added `.env` file loader for API key management
- ADR 0008 (LLM adapter), ADR 0009 (skill registry), ADR 0010 (SillyTavern import)

## v0.5
- **M2 Implementation**: Agents + Plan/Diff/Apply milestone complete (110 tests)
- Added `neonrp agent new|list|show|path` CLI commands with template generation
- Added `core/proposal.py` — Proposal/Op models with path validation
- Added `core/permissions.py` — deny-first glob matching permission engine
- Added `core/diffing.py` — stable unified diff generation
- Added `core/apply.py` — staging + validate + atomic swap apply pipeline
- Added `core/retrieval.py` — agent-scoped context retrieval
- Added `neonrp agent run --proposal --apply` and `neonrp agent logs` commands
- GameEvent model extended with `actor` field for agent attribution
- ADR 0006 (agent spec and permissions), ADR 0007 (proposal format)

## v0.4
- **M1 Implementation**: Validation + Indexing milestone complete (41 tests)
- Added `neonrp validate` CLI with `--json` support and exit codes 0/1/2
- Added `neonrp index build|update` CLI for entity indexing
- Added `neonrp find` CLI with --id/--tag/--kind/keyword search
- Added `neonrp context` CLI with explainable scoring and snippets
- Fixed `scan_entities()` to handle partial failures (index valid, skip invalid)
- Migrated to Pydantic v2 patterns (`ConfigDict`, `datetime.now(UTC)`)
- Bumped manifest.version to `"0.2"`

## v0.3
- **M0 Implementation**: Skeleton + Core Lifecycle milestone complete
- ARCHITECTURE: added write atomicity & crash recovery strategy; defined manifest.json minimal structure
- QUALITY_GATES: added three-layer test strategy (unit/integration/E2E); added code review process
- Replaced scripts/qa.sh with cross-platform scripts/qa.py

## v0.2
- Added ADRs: CLI framework (click), event storage format (NDJSON), snapshot & branch strategy
- ROADMAP: split T4 into T4a (undo/redo) + T4b (branch); added R-number cross-references
- QUALITY_GATES: added code review unrecoverable failure policy

## v0.1
- Initial documentation set: requirements, architecture, roadmap, progress, quality gates
- Added opencode review gate and code review prompt

