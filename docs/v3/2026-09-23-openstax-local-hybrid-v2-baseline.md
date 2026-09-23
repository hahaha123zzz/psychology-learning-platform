# OpenStax《Psychology 2e》本地 Hybrid V2 基线

## 本轮结果

`hybrid-v2 + hash-v1` 已将每个 `KnowledgeChunk` 显式关联到一个 `RetrievalUnit` 和一个来源 `KnowledgeObject`。对同一份 755 页 OpenStax 教材重建后，共有 4160 个分块、4160 个 RetrievalUnit，三者映射均完整。

| 指标 | 结果 | 说明 |
| --- | ---: | --- |
| Object Recall@5 | 0.875000 | 4 个可对象评测问题平均；主动复述只找回两段必要证据中的一段。 |
| Object NDCG@5 | 0.718752 | 准实验和记忆三阶段的精确对象在第 2 位；主动复述第二段排第 7。 |
| Page Recall@5 | 1.000000 | 5 个可回答问题的相关页均进入前 5。 |
| Page NDCG@5 | 0.926186 | 页级排名仍优于对象级排名，说明“命中页”不等于“命中对象”。 |
| Top-1 Page Accuracy | 0.800000 | 准实验题第 1 条仍不是相关页。 |
| Refusal Accuracy | 1.000000 | 教材外麻婆豆腐问题返回 0 条证据并拒答。 |
| Mean Latency | 87.110 ms | 本机 6 次观测，包含冷启动波动，不代表生产性能。 |

图题只命中了第 197 页的图注段落；当前 `StubPdfParser` 没有产生 `figure` 对象，因此它不进入对象级指标分母。bbox、引用和生成指标仍为 `null`：没有可验证版面坐标，且本轮没有调用生成模型。

## 与 V1 的差异

V1 的旧合并 chunk 可跨页，导致它把第 68 页的准实验内容和第 263 页的主动复述内容锚定到前一页。V2 保留 V1 作为历史页级对照，并采用单对象 RetrievalUnit 后重新标注真实对象页和文本锚点：

- 准实验因果性：物理第 68 页；
- 主动复述：物理第 263 页，答案分布在两个相邻文本对象；
- 经典条件反射：物理第 197 页的图对象仍不可由现有解析器恢复。

运行文件和评分报告分别为：

- `contracts/rag-eval/openstax-psychology-2e-local-v2.json`
- `contracts/rag-eval/openstax-psychology-2e-local-hybrid-v2-run.json`
- `contracts/rag-eval/openstax-psychology-2e-local-hybrid-v2-report.json`

## 拒答策略

本地 `hash-v1` 只是确定性测试替身，并不具备真实语义判断能力。V2 对它启用“至少两个有效关键词同段命中”的锚点规则；这避免教材偶然含有 `authentic` 一词时，把“麻婆豆腐”误认为教材问题。该规则仅作用于 `hash-v1`，配置了真实外部 Embedding 后仍可按向量相似度门槛进行语义召回。

## 下一步

1. 用对象关系或相邻对象闭包补齐主动复述这类跨对象答案。
2. 接入可验证版面解析，产生 `figure/table/formula` 对象与 bbox。
3. 在许可允许的非 OpenStax 语料上比较视觉检索、Embedding 与融合策略；本教材不进入外部模型路径。
