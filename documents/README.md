# documents/

写给外部读者的文档。

## 子目录

- `site/<lang>/<分组>/<页>.md` —— [docs.worldlines.gg](https://docs.worldlines.gg) 的正文,唯一来源。
  - 一页一个 markdown:frontmatter(`title` / `description`)+ 每节 `<!-- section: <id> -->` + `## 标题`。`<id>` 是页面锚点,改标题别改 id。
  - zh / en 是完整的;ja / ko 没有的页面在站上回落到 en。
  - 新增或删掉页面时,站点的导航和旧网址重定向也要跟着改。
- `spec/` —— 基础规格:world · soul · template · pack · player · contract(中 / 英)。改完对每个模板跑 `neonrp spec sync`,模板里的 `spec/` 副本要一致。

## 写的时候

- 短句,写读者做什么、会看到什么;不带情绪,不写内部决定。
- 不写:密钥、内部域名 / IP、个人路径、未公开的商业信息、竞品名;导出前扫描会拦。
- 状态如实标(已发布 / 设计中)。
