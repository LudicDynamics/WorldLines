# 潮池镇 · 灯塔熄灭的那晚

id: tidepool
lang: zh
pack: rpg
contract: open-adventure@1
ending: multi
freedom: semi
pitch: 海边小镇的灯塔三天没亮。守塔人不见了,渡船照常开,只有摆渡的阿汐不肯靠近北礁。
tags: 海边, 小镇, 寻人, 开放冒险

## Premise
潮池镇是一座靠渡船和晒盐过日子的海边小镇。三天前的夜里,北礁灯塔熄了,守塔人老顾再没下来。
镇长说他喝多了掉进了海里,可他的小船还拴在码头。玩家是刚坐渡船到镇上的旅人,住进了码头边的潮声旅店。

## Places
T001 潮池镇 — 渡船、盐田和一座熄灭的灯塔。
- pier · 渡船码头 · gate · connects: square, inn · 镇子唯一的进出口,渡船一天两班
- square · 盐田广场 · street · connects: pier, inn, lighthouse_path · 晒盐架排成行,镇上人在这里交换消息
- inn · 潮声旅店 · facility · connects: pier, square · 两层木楼,楼下是饭堂
- lighthouse_path · 北礁石道 · road · connects: square, lighthouse · 退潮时才露出来的石道
- lighthouse · 北礁灯塔 · facility · connects: lighthouse_path · 白漆剥落的塔,门从里面闩着

## People
### axi · 阿汐
- where: pier
- looks / voice: 二十出头,晒得发黑,袖口总是湿的。说话短,先看人再开口,爱用「行」「不行」收尾。
- wants: 渡船不停;知道老顾那晚为什么点了三次灯又灭掉
- will / won't: 肯载人绕到北礁外看一眼,收双倍船钱;退潮前绝不上石道;有人提她父亲的船难就转身走

- innkeeper · 钟婶(旅店老板娘) · innkeeper · at inn

## Opening
渡船靠岸时天快黑了。码头上只有一盏风灯,北边礁石上的灯塔黑着,像一根没点的蜡烛。
摆渡的姑娘把缆绳绕上桩子,头也不回:「旅店往前走,别往北看。」
- 跟阿汐打听灯塔的事
- 先去潮声旅店落脚
- 走到广场看看
- 直接朝北礁走

## Plot and endings
stages: 打听 → 上礁 → 塔里
- E1 · true · 第四次灯 · reached when: 玩家在塔里找到守塔日志,并把它交给阿汐
- E2 · fail · 涨潮 · reached when: 涨潮时还在北礁石道上

## World data
- 船钱:一程 5 铜;绕北礁 10 铜
- 旅店:一晚 8 铜,含晚饭
- 潮汐:每天 06:00 和 18:00 前后退潮,石道露出约两小时
- 镇上的称呼:守塔人叫「塔公」

## Art
style: 水彩,冷灰海色,唯一暖色是风灯的橙光
cover: 黄昏的码头,远处黑着的灯塔,摆渡姑娘背影
