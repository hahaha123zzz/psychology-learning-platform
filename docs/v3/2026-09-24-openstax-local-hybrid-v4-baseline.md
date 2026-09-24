# OpenStax《Psychology 2e》本地 `hybrid-v4 + hash-v1` 基线

## 修复依据

`hybrid-v3` 的逐阶段排序追踪保存在
`contracts/rag-eval/openstax-psychology-2e-local-hybrid-v3-trace.json`。它证明两道漏召回题的目标页本已在 BM25 候选中：准实验题为第 1 位、古典条件反射图题为第 3 位；但 `hash-v1` 的确定性哈希向量不具备语义含义，仍参与 Weighted RRF 后引入无关页面，前者还被自适应截断移除。

因此 `hybrid-v4` 只对本地 `hash-v1` 禁用伪向量通道，改用 **BM25 + 至少两个有效关键词锚点**。真实 OpenAI-compatible Embedding Provider 继续使用向量检索、最小相似度门槛与 Weighted RRF；本改动不等同于确定最终模型选型。

## 可复现结果（K=5）

| 指标 | `hybrid-v3 + hash-v1` | `hybrid-v4 + hash-v1` |
| --- | ---: | ---: |
| 页级 Recall@5 | 0.600000 | 1.000000 |
| 页级 NDCG@5 | 0.600000 | 0.826186 |
| 首项页准确率 | 0.600000 | 0.600000 |
| 精确对象 Recall@5 | 0.625000 | 0.625000 |
| 精确对象 NDCG@5 | 0.561019 | 0.561019 |
| 教材外拒答准确率 | 1.000000 | 1.000000 |
| 首项 bbox IoU | 0.960721 | 0.480661 |

`hybrid-v4` 的页级召回恢复，但精确对象和 bbox 指标没有同步提升：页面内可能有多个段落，BM25 的第一条结果并不必然是人工标注段落。当前评测仍没有图片、表格、公式的 `RetrievalUnit` 或视觉索引，古典条件反射题仅以图注/文本段落命中目标页，不能称为图片检索成功。

运行工件：

- `contracts/rag-eval/openstax-psychology-2e-local-hybrid-v4-run.json`
- `contracts/rag-eval/openstax-psychology-2e-local-hybrid-v4-report.json`

## 后续决策

在没有合规的真实 Embedding 供应商实验前，`hash-v1` 仅作为可重复的离线关键词基线；它不用于证明语义检索、视觉检索或模型供应商效果。下一步应优先建设图片/表格/公式对象及可验证表示，再在获得许可的语料上比较真实文本与视觉模型。
