# documents/ — 可以开源的文档

NeonRP 里文档两分(10-03 定):

| 目录 | 是什么 | 导出到开源仓 |
|---|---|---|
| `documents/`(这里) | 写给外部读者的文档 | **是**,原样导出 |
| `docs/` | 开发者文档:计划、ADR、游玩记录、设计归档、文档站工程(`docs/site`) | **永不导出** |

## 子目录

- `site/<lang>/<分组>/<页>.md` —— docs.worldlines.gg 的正文,唯一来源。站点工程在 `docs/site`,构建时从这里读。
  - 一页一个 markdown:frontmatter(`title` / `description`)+ 每节 `<!-- section: <id> -->` + `## 标题`。`<id>` 是页面锚点,改标题别改 id。
  - zh / en 是完整的 v3 页;ja / ko 目前只有 `vision` `roadmap` `changelog`,其余回落到 en。
  - 来源:10-03 从站点的 `content.v3.{zh,en}.ts`(10-01 写、从未部署)无损抽出;内容写在 10-01 之前,许可证 / 版本 / 回合流程几处待按新决定修订。
- `spec/` —— 三份基础规格:world · soul · template(中 / 英),由代码逐条核对;捏卡工作台和 README 都引用它。
- (蓝图定稿后放 `blueprint/`)

## 写的时候

- 不写:密钥、内部域名 / IP、个人路径、未公开的商业信息、竞品名;导出前扫描会拦。
- 状态如实标(已发布 / 已实装未发布 / 设计中)。
