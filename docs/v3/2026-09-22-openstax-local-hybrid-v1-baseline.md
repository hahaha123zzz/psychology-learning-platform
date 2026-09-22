# OpenStax《Psychology 2e》本地 Hybrid V1 基线

## 结论

首轮真实开放教材本地基线已跑通，但只证明了“页级文本检索可用”，尚不能证明精确对象检索、视觉检索、bbox 定位或端到端生成质量。

| 指标 | 结果 | 解释 |
| --- | ---: | --- |
| Page Recall@5 | 1.000000 | 5 个可回答问题的相关物理页均进入前 5。 |
| Page NDCG@5 | 0.926186 | 经典条件作用图所在页排第 2，其余相关页排第 1。 |
| Top-1 Page Accuracy | 0.800000 | 5 题中 4 题首位页正确。 |
| Refusal Accuracy | 0.833333 | 教材外的麻婆豆腐问题仍返回无关结果，拒答失败。 |
| Mean Latency | 42.426 ms | 本机、6 次查询、`hash-v1 + BM25 + RRF`，不代表生产性能。 |

精确对象 Recall/NDCG、bbox IoU、引用精确率/召回率和主张支持率均为 `null`。当前 `KnowledgeChunk` 没有可用于评测的稳定 `KnowledgeObject/RetrievalUnit` 映射，PDF 解析器也不提供经验证 bbox；本轮没有调用生成模型，因此这些指标不进入分母。

## 运行输入

- 数据集：`contracts/rag-eval/openstax-psychology-2e-local-v1.json`
- 运行记录：`contracts/rag-eval/openstax-psychology-2e-local-hybrid-v1-run.json`
- 评分报告：`contracts/rag-eval/openstax-psychology-2e-local-hybrid-v1-report.json`
- PDF SHA-256：`2f08113c78127bc684922ad6a819db22bd4705ce9fcf28a07f36a2041b1474e2`
- 检索版本：`hybrid-v1`
- Embedding：本地确定性 `hash-v1`
- Top K：5（API 实际取回 8 条，评分观察前 5）

OpenStax 教材仅在本地离线解析和检索。本轮未把正文、图像、表格或问题上下文发送给任何外部生成或嵌入 API。

## 解析与索引验证

真实首次解析暴露了目录误判：目录页同时出现 `Chapter 1` 至 `Chapter 16`，旧规则把它们全部当作第 14 页的章节边界。修复后的规则忽略同页多章目录，并用章首页的 `CHAPTER OUTLINE + N.1` 恢复真实章边界。

- 物理页数：755
- 章节数：16
- 章节起始页：19、47、83、121、157、193、225、259、291、333、371、411、457、495、547、609
- 章节内对象总数：4122
- 重解析耗时：约 15.3 秒（20:45:55—20:46:10，本机单次观测）
- `hash-v1` 重建索引耗时：约 7.2 秒（20:47:44—20:47:51，本机单次观测）

重新解析草稿版本会先删除旧 `KnowledgeChunk`，使旧索引失效；在新索引完成前发布门禁返回 `MATERIAL_INDEX_NOT_READY`。已发布版本仍禁止原地重解析，必须创建新版本。

## 发现的问题与下一步

1. **优先建立稳定对象映射。** `RetrievalUnit` 应记录其来源 `KnowledgeObject`，否则只能评页命中，无法严谨计算段落、图片、表格或公式命中率。
2. **增加拒答门槛。** 当前 RRF 总会给教材外查询排出相对靠前的候选；需要绝对相关性门槛或查询范围判定，不能把“有 Top K”当作“有证据”。
3. **视觉检索尚未开始选型。** 图题只命中了相关页的文本 chunk，不能表述为图片命中；ColPali、ColQwen、VisRAG、CLIP 和多向量 Late Interaction 仍需在可合法处理的语料上对照。
4. **bbox 仍是硬缺口。** `StubPdfParser` 无法提供段落、图片、表格、公式的可验证坐标，必须先接入版面解析并做人工抽样，才能验收点击跳转与高亮。
5. **生成指标尚未评测。** 本轮是检索基线，没有调用大模型；引用正确性、主张支持率和教材严格约束应在合法语料与已配置供应商上另跑端到端评测。

本报告只代表本地单机真实语料验证，不代表生产部署、容量、真实班级或教师验收完成。
