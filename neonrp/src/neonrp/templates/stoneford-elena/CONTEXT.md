# 这个世界的上下文语言(引擎生成,别手改;改 manifest.json 的 prompt 后重新生成)

## 引擎每回合给模型看的(词条包)
按顺序:时间 · 镇 / 此地 / 出口 · 本镇地点 id · 在场角色与 NPC · 玩家 · 人设(在场角色) · 异地角色 · 世界笔记 / 传闻 / 背景 · 登记的类 · 引擎的消息 · 变量与变量规则 · 最近叙事。
然后是用户块:工具回包 · 角色回包 · 相关条目(命中的条目) · 玩家此刻 · (被拒时)上一次提案。

## 模型要写的(输出格式)
## 输出格式
严格按下面的格式输出,块外不写任何字。
lines:画面上按顺序显示的消息。角色的台词必须用「」包住(开头是「,结尾是」)。没有「」的消息当作地文。台词和地文不写在同一条消息里。这是 ADV 文字面板要显示的东西,一句一行。
ops:这一回合的状态变化,一行一个;没有变化就写一行 无变化。可写的行:
move <谁> <去哪>            移动:谁 = player 或在场角色 / NPC 的名字,去哪 = 本镇地点 id,或一个新地名(地图上还没有就当场建出来)。写这回合最终到达的地点,不写途经;镇内任何地点一回合都能到
[ask <谁>]                请求:需要某个在场角色先回话才能写下去;一回合最多两个
player.hp -3          变量:名字 + 数字,带 + / − 号 = 增减,不带 = 设定
flag <旗名>                story flag
new_location <名字> <上级> <相邻> 新地点(writer):new_location <名字> 加一个关系说它在地图的哪一层——near=<A>[,<B>] 和它们同层、挨着;between=<A>,<B> 在两地之间的路上;in=<A> 在 A 里面(下一层,只能从 A 进出);over=<A>,<B> 把同层的几处包进来(上一层,比如一个街区)。说不清就不写,引擎先挂在玩家旁边,回合后再按叙事挂好
link <a> <b>             新连一条路:link <地点A> <地点B>(同一个镇里本来不通的两处,比如发现了一条近道)
unlink <a> <b>           断一条路:unlink <地点A> <地点B>(桥塌了、路被封了;断了会让镇上有地方走不到就不行)
new_town <名字> <from> <days> <summary> <tags> 新城镇(writer):玩家要去一个世界地图上还没有的城镇时,世界当场长出来——new_town <名字> from=<从哪个镇修路过去> days=<路上几天> summary=<一句话> tags=<路况,逗号分隔>;之后照常赶路过去
new_npc <名字> <在哪> <角色>   新路人(writer)
new <类> <名字>             开放 schema:新建一个登记类的实例,写成 new <类> <名字> 属性=值 …(哪些类、哪些属性见词条包「可登记的类」)
patch <谁> <属性>           开放 schema:给任何一个人 / 物 / 地方写属性,写成 patch <名字> 属性=值 …;新属性直接加,写进它自己的记录(声明过的属性只限可变的;名字、id、位置不能改——让谁去哪儿用 move)
remove <谁>               开放 schema:一个实例离开世界(用光了、结束了),写成 remove <名字>
write <path>             文件:新建或覆盖世界文件夹里的一个 .json / .md / .txt 文件,写成 [~write 路径]内容[/write](JSON 要能解析;路径相对世界文件夹,见「世界文件夹」)
edit <path>              文件:改一个 JSON 文件里的键,写成 edit <路径> 键=值 …(点号表示嵌套,新键直接加)
rm <path>                文件:删除一个文件,写成 rm <路径>(只限游玩中写的、或开放 schema 目录里的)
mkdir <path>             文件夹:新建一个文件夹,写成 mkdir <路径>
rmdir <path>             文件夹:删除一个游玩中建的文件夹(连同里面的文件),写成 rmdir <路径>
define <kind> <名字>       开放 schema:世界里需要一种还没有的东西时当场定义——define class <类名> <标题> 属性=类型 …(类型 int/str/bool/list,选项写 a|b|c)mutable=可改的属性,…(effect=yes:随回合生效的状态);define var <名字> <类型> <初始值> min= max=。定义之后马上可以 new / patch / remove / 写变量
[roll <骰>]               请求:掷骰,写 1d6 / 2d10 / 2d6+1 这种,不要自己编点数
[dice <骰> <vs>]          检定:[dice 1d20+2 vs 12]写清判定什么、为什么[/dice];引擎回点数和过/未过,理由你写、点数引擎出
[~map]                   地图:[~map] 引擎按真实状态画一张当前位置的字符地图(镇内 / 地穴 / 路上)直接给玩家看;不等回包,lines 照常往下写;不要自己画图
[~sheet]                 人物卡:[~sheet] 引擎把玩家的属性 / 背包 / 钱袋画成面板直接给玩家看;不等回包;叙事里不要念数值
[referee <question>]     请求裁判:[referee 玩家想做的不确定 / 过分的事];规则裁判读规则和人物卡给裁定(能不能、要不要检定、后果),你按裁定写
[combat …]…[/combat]     切到战斗层:[combat 山贼×5 独眼虎×1]为什么打起来[/combat];标签里的 名字×数 就是对面的花名册(引擎按表生成),正文是交接词;lines 停在这一行,战斗裁判层接着写(先攻 / 命中 / 伤害都靠 [dice])
end_combat <outcome>     战斗层专用:end_combat outcome=won|fled|lost,离开战斗层
无变化
options:玩家听完这一段可能说的话或做的事,2–4 个。短(20 字以内),方向拉开(友好 / 挑衅 / 换话题 等)。一个选项一行。
动作也可以直接写在 lines 里,和 ops 里的一行等价:[~move player inn]你推开旅店的门。,或 [~flag paid]。请求(方括号)写在哪一行,lines 就停在哪一行,引擎回包后你续写。引擎给你的消息用尖括号:<event>/<end> 是已经发生的事,<say> 是角色说过的话,<roll 1d6>4</roll> 是请求的回包,<refused>是被拒的原因。

EXAMPLE OUTPUT:
<lines>
你推开河灯旅店的门,炉火的热气贴上脸。
「一间房,两个人。」
米拉从柜台后抬起头,打量了你们一眼。
「八枚一晚,先付。」
艾琳娜没说话,把斗篷上的水抖了抖。
</lines>
<ops>
move player inn
move 艾琳娜 inn
player.gold -8
</ops>
<options>
「先付一晚」
问米拉有没有见过罗文
「太贵了」
转身出去
</options>

## 上下文语言:括号形状 = 等不等回包
- `[tag args]` 同步请求:写到这一行 lines 就停,引擎回包后续写(例 `[dice 1d20+2 vs 12]理由[/dice]`、`[referee 玩家想做的事]`、`[ask 艾琳娜]`、`[combat 山贼×3]交接[/combat]`)
- `[~tag args]` 异步动作:不等回包,引擎照做,模型接着写(例 `[~move player inn]`、`[~flag paid]`、`[~player.gold -3]`、`[~map]`);和 ops 里的一行等价
- 等不等由引擎的注册表决定(每个 op 声明 wait);模型括号写错时按注册表执行,不一致记进 trace
- 旧写法 `<move player inn>` 仍然认,等同于 `[~move player inn]`
引擎给模型的消息用尖括号:`<event 规则id>已经发生的事</event>` · `<end 结局id>尾声提示</end>` · `<say 名字 attitude=…>台词</say>` · `<roll 1d6>4</roll>` · `<refused op 字段>原因;可选:…</refused>`。

## 这个世界登记的 op(从 actions 表生成)
move <谁> <去哪>            移动:谁 = player 或在场角色 / NPC 的名字,去哪 = 本镇地点 id,或一个新地名(地图上还没有就当场建出来)。写这回合最终到达的地点,不写途经;镇内任何地点一回合都能到
[ask <谁>]                请求:需要某个在场角色先回话才能写下去;一回合最多两个
player.hp -3          变量:名字 + 数字,带 + / − 号 = 增减,不带 = 设定
flag <旗名>                story flag
new_location <名字> <上级> <相邻> 新地点(writer):new_location <名字> 加一个关系说它在地图的哪一层——near=<A>[,<B>] 和它们同层、挨着;between=<A>,<B> 在两地之间的路上;in=<A> 在 A 里面(下一层,只能从 A 进出);over=<A>,<B> 把同层的几处包进来(上一层,比如一个街区)。说不清就不写,引擎先挂在玩家旁边,回合后再按叙事挂好
link <a> <b>             新连一条路:link <地点A> <地点B>(同一个镇里本来不通的两处,比如发现了一条近道)
unlink <a> <b>           断一条路:unlink <地点A> <地点B>(桥塌了、路被封了;断了会让镇上有地方走不到就不行)
new_town <名字> <from> <days> <summary> <tags> 新城镇(writer):玩家要去一个世界地图上还没有的城镇时,世界当场长出来——new_town <名字> from=<从哪个镇修路过去> days=<路上几天> summary=<一句话> tags=<路况,逗号分隔>;之后照常赶路过去
new_npc <名字> <在哪> <角色>   新路人(writer)
new <类> <名字>             开放 schema:新建一个登记类的实例,写成 new <类> <名字> 属性=值 …(哪些类、哪些属性见词条包「可登记的类」)
patch <谁> <属性>           开放 schema:给任何一个人 / 物 / 地方写属性,写成 patch <名字> 属性=值 …;新属性直接加,写进它自己的记录(声明过的属性只限可变的;名字、id、位置不能改——让谁去哪儿用 move)
remove <谁>               开放 schema:一个实例离开世界(用光了、结束了),写成 remove <名字>
write <path>             文件:新建或覆盖世界文件夹里的一个 .json / .md / .txt 文件,写成 [~write 路径]内容[/write](JSON 要能解析;路径相对世界文件夹,见「世界文件夹」)
edit <path>              文件:改一个 JSON 文件里的键,写成 edit <路径> 键=值 …(点号表示嵌套,新键直接加)
rm <path>                文件:删除一个文件,写成 rm <路径>(只限游玩中写的、或开放 schema 目录里的)
mkdir <path>             文件夹:新建一个文件夹,写成 mkdir <路径>
rmdir <path>             文件夹:删除一个游玩中建的文件夹(连同里面的文件),写成 rmdir <路径>
define <kind> <名字>       开放 schema:世界里需要一种还没有的东西时当场定义——define class <类名> <标题> 属性=类型 …(类型 int/str/bool/list,选项写 a|b|c)mutable=可改的属性,…(effect=yes:随回合生效的状态);define var <名字> <类型> <初始值> min= max=。定义之后马上可以 new / patch / remove / 写变量
[roll <骰>]               请求:掷骰,写 1d6 / 2d10 / 2d6+1 这种,不要自己编点数
[dice <骰> <vs>]          检定:[dice 1d20+2 vs 12]写清判定什么、为什么[/dice];引擎回点数和过/未过,理由你写、点数引擎出
[~map]                   地图:[~map] 引擎按真实状态画一张当前位置的字符地图(镇内 / 地穴 / 路上)直接给玩家看;不等回包,lines 照常往下写;不要自己画图
[~sheet]                 人物卡:[~sheet] 引擎把玩家的属性 / 背包 / 钱袋画成面板直接给玩家看;不等回包;叙事里不要念数值
[referee <question>]     请求裁判:[referee 玩家想做的不确定 / 过分的事];规则裁判读规则和人物卡给裁定(能不能、要不要检定、后果),你按裁定写
[combat …]…[/combat]     切到战斗层:[combat 山贼×5 独眼虎×1]为什么打起来[/combat];标签里的 名字×数 就是对面的花名册(引擎按表生成),正文是交接词;lines 停在这一行,战斗裁判层接着写(先攻 / 命中 / 伤害都靠 [dice])
end_combat <outcome>     战斗层专用:end_combat outcome=won|fled|lost,离开战斗层

## 条目(manifest.json → "prompt" → "entries";游玩中改的在 game/meta/prompt.json)
- `"when": "always"` 进系统提示词;`"post"` 放最后;条件型(`{"keyword": …}` · `{"at": …}` · `{"var": …, ">=": n}` · `{"flag": …}`)命中时贴在「玩家此刻」前面。
- `rules` / `voice` / `blocks` / `ops_docs` 也在这里改。三层:模板 pack.json < manifest.json < game/meta/prompt.json。
