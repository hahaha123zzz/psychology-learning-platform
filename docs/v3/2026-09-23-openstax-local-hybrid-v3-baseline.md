# OpenStax《Psychology 2e》本地 `hybrid-v3 + hash-v1` 基线

## 运行边界

本次运行由 `scripts/run_local_rag_eval.py` 从本地已解析版本 `01M33P6ACK2GAFPF6FCP95Z0YZ` 实际调用检索服务；版本 SHA-256 与评测集记录一致。Embedding 固定为本地 `hash-v1`，没有向外部 Embedding 或生成 API 发送教材内容。

`hybrid-v3` 在 `hybrid-v2` 的 BM25/向量 RRF 基础上加入 Query Analyzer 的文本通道加权、范围过滤和自适应截断。OpenStax 评测题主要是通用文本问答；图题的 `visual` 优先级只产生文本降级警告，不能称为视觉检索。

## 可复现结果（K=5）

| 指标 | 结果 | 说明 |
| --- | ---: | --- |
| 页级 Recall@5 | 1.000000 | 5 个可回答题均在前 5 个候选中覆盖目标页。 |
| 页级 NDCG@5 | 0.926186 | 准实验题目标页在第 2 位，首项为第 81 页。 |
| 首项页准确率 | 0.800000 | 准实验题首项页不正确。 |
| 精确对象 Recall@5 | 0.625000 | 仅统计 4 个段落对象题。 |
| 精确对象 NDCG@5 | 0.561019 | 准实验锚点未自动匹配，主动复述题只覆盖两个目标段落之一。 |
| 教材外拒答准确率 | 1.000000 | 麻婆豆腐问题被 hash-v1 的多词锚点规则拒答。 |
| 平均检索耗时 | 18.216 ms | 本机本地数据库测量，不代表生产性能。 |

## 不可评估与审计结论

- 古典条件反射图题只命中第 197 页的段落/图注，当前索引没有 `image` RetrievalUnit；该题仍可计算页级指标，但从精确对象指标排除。
- 数据库中本轮复用的历史已解析版本尚无 bbox，故 bbox IoU 不可评估。新 PDF parser 已能提取原生文本段落 bbox；必须在重新解析并重建该教材索引后，才能以新版本重新测量。
- 本次运行不评估生成、引用精确率或主张支持率，避免把确定性抽取式输出伪装为真实供应商生成评测。
- 与历史 `hybrid-v2` 人工整理运行文件相比，本结果的对象指标较低，因为仅使用可审计的同页、同类型文本锚点自动映射；不再把图注段落计为图片对象，也不人工补齐准实验对象命中。

对应工件：

- `contracts/rag-eval/openstax-psychology-2e-local-hybrid-v3-run.json`
- `contracts/rag-eval/openstax-psychology-2e-local-hybrid-v3-report.json`
