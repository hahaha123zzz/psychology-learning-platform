# 本地教材 RAG 评测执行器

`scripts/run_local_rag_eval.py` 从已解析的本地教材版本实际调用 `hybrid_search`，生成符合 `rag-eval/v3-run` 的结果文件；随后可由 `scripts/rag_eval_v3.py` 评分。

该执行器强制要求 `hash-v1`，并核对数据库教材版本的 SHA-256 与评测集文档一致。它不会配置或调用外部 Embedding/LLM；产生的短期 EvidenceTicket 在会话结束前回滚，不污染教材或线上会话数据。

对于评测集已有的 `text_anchor`，执行器只在同一物理页、对象类型一致且真实检索文本包含该锚点时，才把真实 `source_object_id` 映射成标注对象 ID；其余命中保留真实 ID，以避免把图注段落虚构成图片对象命中。当前 `paragraph-child` 索引不覆盖图片/表格/公式对象，相关题目会从精确对象指标中排除，但仍保留页级召回等可评估指标。

示例：

```powershell
server\.venv\Scripts\python.exe scripts\run_local_rag_eval.py `
  --dataset contracts/rag-eval/openstax-psychology-2e-local-v2.json `
  --material-version-id <本地版本ID> `
  --output contracts/rag-eval/openstax-psychology-2e-local-hybrid-v3-run.json
server\.venv\Scripts\python.exe scripts\rag_eval_v3.py `
  --dataset contracts/rag-eval/openstax-psychology-2e-local-v2.json `
  --results contracts/rag-eval/openstax-psychology-2e-local-hybrid-v3-run.json `
  --output contracts/rag-eval/openstax-psychology-2e-local-hybrid-v3-report.json
```
