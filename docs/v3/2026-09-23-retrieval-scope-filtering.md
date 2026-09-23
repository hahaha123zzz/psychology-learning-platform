# V3 检索范围过滤

`POST /api/v1/knowledge/search` 的 `chapter_scope` 和 `object_types` 现已在 BM25 与向量候选查询中、RRF 排序之前生效。

- `chapter_scope` 接受章节 `KnowledgeObject.id`，而不是显示名称或章节序号；这样修改标题不会改变范围含义。
- `object_types` 对来源知识对象类型过滤。
- 当前索引构建策略为 `paragraph-child`，所以 `paragraph` 是已索引类型；请求 `figure`、`table` 或 `formula` 不会回退为段落命中，直到对应对象和检索表示真实建成。

权限、可检索版本、向量相似度门槛和哈希模式的关键词拒答都先于或同时受该范围约束，不能通过缩小范围绕过这些限制。
