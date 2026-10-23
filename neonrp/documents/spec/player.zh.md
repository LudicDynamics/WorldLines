# 玩家侧数据规范(分身 · 玩家数据 · 聊天记录)

玩家自己的东西:捏的分身、跨局的记录(获得的角色、聊过的角色、结局、成就、待发奖励)、和角色的私聊。全部在 `~/.worldlines/` 下,归 launcher 管,**从不写进模板或一局的文件夹**(引擎 / launcher 主权线)。本机和浏览器版用同一套 HTTP。

> 状态标注:**已实装**(代码里有、有测试)· **约定**(约好的做法)· **设计中**。

## 1. 放在哪

| 东西 | 路径 | 状态 |
|---|---|---|
| 分身 | `~/.worldlines/players/<file>.json`(一个分身一个文件,文件名按名字生成) | 已实装 |
| 当前分身 | `~/.worldlines/players/.current`(里面是 file 名;没设过且只有一个分身时就是它) | 已实装 |
| 分身立绘 | `~/.worldlines/players/<file>.portrait.<png\|jpg\|webp>` | 已实装 |
| 玩家数据 | `~/.worldlines/player-data/<player>.json` | 已实装 |
| 获得角色的记忆快照 | `~/.worldlines/player-data/<player>/souls/<tpl>/<sid>/`(获得那一刻这一局的角色文件夹,`assets/` 不复制) | 已实装 |
| 和角色的聊天记录 | `~/.worldlines/player-data/<player>/chats/<tpl>__<sid>.jsonl`(一行一条消息) | 已实装 |

`<player>` 默认是 `local`;环境变量 `WORLDLINES_PLAYER_ID` 可以指定(登录的账号用自己的文件)。代码:`src/neonrp/core/player_data.py:player_id`。

## 2. 分身

分身是玩家给自己捏的主角,只在本机、不发布,和角色库(`~/.worldlines/souls/`)分开:角色不能当分身,分身也不会变成角色。代码:`src/neonrp/players.py`。

### 2.1 字段

| 字段 | 说明 | 状态 |
|---|---|---|
| `name` | 名字(新建时必填) | 已实装 |
| `summary` | 简介 | 已实装 |
| `gender` · `personality` · `appearance` · `backstory` | 性别 · 性格 · 外貌 · 背景 | 已实装 |

只收这六个字段,其他的忽略。

### 2.2 接口

| 接口 | 说明 | 状态 |
|---|---|---|
| `GET /api/v1/local/avatar[?tpl=<模板 id>]` | `{current, avatar, avatars: [{file, name, summary, data, current, portrait_url}]}`;带 `tpl` 时多一个 `prefill: {fields: {<字段 id>: 值}}`(见 2.4) | 已实装 |
| `POST` / `PUT /api/v1/local/avatar` `{name?, summary?, …, file?}` | 带 `file` = 编辑那一个(没传的字段保留);不带 = 新建(要 `name`,缺了 400)。写完它就是当前分身。返回 `{ok, file}` | 已实装 |
| `POST /api/v1/local/avatar/current {file}` | 切换当前分身;没有这个分身 404 | 已实装 |
| `POST /api/v1/local/avatar/portrait?file=` | 请求体直接是图片字节(png / jpg / webp),返回 `{ok, portrait_url}`;不是图片或没有这个分身 400 | 已实装 |
| `GET /api/v1/local/avatar/portrait?file=` | 立绘图片(带 ETag) | 已实装 |
| `GET /api/v1/local/souls` 的 `avatars` | 同一份列表,每行带 `current`、`portrait_url` | 已实装 |

### 2.3 开局用分身当主角

`POST /api/v1/play/session {slug, avatar: "current" | <file>}`:只对**这次新开的一局**、而且**没走捏人台**(没带 `player`)时生效。分身的字段盖到这一局的 `game/player/profile.json`(它写了的字段,世界原来的多语言版本 `name_i18n` / `intro_i18n` / `<字段>_i18n` 一并去掉);有立绘就换成这一局主角的立绘(`game/player/assets/portrait.*`)。没有 `profile.json` 的老世界走 TUI 开局同一条合并路径。引擎**不会自动**套用分身,不带 `avatar` 就是世界原来的主角。代码:`src/neonrp/players.py:apply_avatar_to_run`、`src/neonrp/webui/engine_routes.py`。 已实装

世界的主角是哪种，看模板 meta 的 `pc: {fixed, builder}`(`GET /api/v1/local/templates` 每行、`/api/v1/local/templates/<id>` 都带):`fixed` = 世界自己写好了主角(`playthrough.json` 的 `players[0].name` 是具体名字，不是脚手架的 "Player");`builder` = 有捏人台。「用我的分身开局」只在 `builder` 为真或 `fixed` 为假时给。模板可以直接写 `template.json` `player.fixed: true | false`。代码:`src/neonrp/template/__init__.py:pc_meta`。 已实装

### 2.4 捏人台预填

模板有捏人台(`template.json` `player.builder`)时,`GET /api/v1/local/avatar?tpl=<id>` 的 `prefill.fields` 给出能从当前分身填的字段:捏人台里 `kind: text`、`to` 写到 `player/profile.json:<name|summary|gender|personality|appearance|backstory>` 的字段,值取分身的同名字段(按字段的 `max` 截断)。前端把它并进草稿;开局仍然走捏人台的校验。代码:`src/neonrp/players.py:builder_prefill`。 已实装

## 3. 玩家数据

一个玩家一个文件,`GET /api/v1/local/player-data[?player=<id>&lang=]`:

```
{player,
 characters: [{sid, name, world, how, memory: full|fresh, at}],
 talked:     [{sid, name, world, at}],
 endings:    [{id, title, world, at}],
 achievements: [{id, world, source, at, title?, desc?, points?, scope?}],
 rewards:    [{id, kind, amount?, cg?, world, source, status: pending, at}]}
```

`world` 都是模板 id(一局 `game/meta/template.json` 的 `id`;不是从模板建的局就是那一局的文件夹名)。

| 记录 | 什么时候写 | 状态 |
|---|---|---|
| `characters`(获得的角色) | 角色的 `take_when` 满足时(`companion_at_ending` = 结局落下时是同伴且在场;`ending:<id>` = 那个结局落下),或结算时带走(`how` = settlement · truth_quiz)。只有 `takeable` 的角色能获得。`memory: full` 时同时做记忆快照(见 1) | 已实装 |
| `talked`(聊过) | 第一次和 `standalone` 角色说上话:直聊,或在一局里它用话回了玩家。**不算获得**,不进 `characters` | 已实装 |
| `endings` | 一局落下结局时(每个世界每个结局一条) | 已实装 |
| `achievements` | 解锁时(`core/achievements.py`)。读的时候按 `lang` 带上 `title` / `desc` / `points` / `scope`:内置成就从四语表来,模板自带的从那个模板的 `template.json` `achievements` 来;认不出的 id 原样返回 | 已实装 |
| `rewards` | 结算 / 里程碑 / 成就挣到、平台还没发的奖励,写成 `pending`,平台发完改 `granted` | 已实装 |

角色的两个开关(`standalone`、`takeable` / `take_when`)写在角色的 `soul.json`,见 [soul.zh.md](soul.zh.md) 3.1。

## 4. 继续世界

| 接口 | 说明 | 状态 |
|---|---|---|
| `GET /api/v1/local/plays?lang=[&all=1]` | `{plays: [{session_id, template, world, turns, last_modified, cover_url, in_memory}]}`,新的在前;默认只列走过至少一回合的局,`all=1` 全列。`world` = 模板按 `lang` 本地化的标题;`cover_url` = 模板卡面(模板没封面是 null),老世界是 `/api/v1/local/worlds/<slug>/cover` | 已实装 |
| `GET /api/v1/play/saves` | 存档列表(每行带 `template`、`turns`) | 已实装 |
| 接着玩 | `POST /api/v1/play/session {slug: <session_id>}` | 已实装 |

## 5. 聊天记录

和角色的私聊(手机聊天界面)。接口、能和谁聊、角色知道什么、表情,见 [soul.zh.md](soul.zh.md) 4.5。玩家这一侧只记两样:

| 事 | 规则 | 状态 |
|---|---|---|
| 记录文件 | `chats/<tpl>__<sid>.jsonl`,一行 `{id, from: me\|soul, kind: text\|sticker, text?, sticker?, at}`;发送失败的那一次不写 | 已实装 |
| 记忆来源 | 已获得的角色读 `souls/<tpl>/<sid>/` 快照(`memory: full`);没获得的读模板里的角色文件夹(`memory: trial`) | 已实装 |

## 6. 参考实现位置

| 东西 | 代码 |
|---|---|
| 分身 | `src/neonrp/players.py` |
| 分身接口 | `src/neonrp/webui/launcher_routes.py:_avatar_route` |
| 玩家数据 | `src/neonrp/core/player_data.py` |
| 成就 | `src/neonrp/core/achievements.py` |
| 继续世界 | `src/neonrp/commands/web.py:_local_plays` · `_library_saves` |
| 直聊 | `src/neonrp/core/soul_chat.py` |
| 测试 | `tests/test_hub_my_page_local.py` · `tests/test_standalone_player_data.py` · `tests/test_soul_chat.py` |
