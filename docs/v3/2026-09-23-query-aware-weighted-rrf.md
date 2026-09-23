# V3 Query-aware Weighted RRF

## 已实现

确定性 Query Analyzer 的 `channel_priors` 已输入 RRF 融合。`sparse` 映射 BM25，`dense` 映射向量检索；在可用的文本通道中重新归一化后参与排名。默认行为仍为 0.5 / 0.5。

教师检索端点会返回 `fusion.strategy = weighted_rrf-v1` 与实际文本通道权重；学生 SSE 问答也使用同一查询计划和权重。检索版本升级为 `hybrid-v3`，以区别此前固定等权的 `hybrid-v2` 基线。

## 诚实降级

`visual` 先验不等于视觉检索：图片、表格、公式问题的计划如含有未建成通道，系统会记录“当前仅使用文本检索”的警告，并只把剩余文本权重重新归一化。没有视觉表示、视觉索引或视觉评测前，不得把此实现称为多模态检索。
