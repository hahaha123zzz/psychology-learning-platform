# ADR（架构决策记录）

教材多模态 RAG V3.0 的模型、索引和 Fusion 默认配置必须通过可复现实验决定。

每项 ADR 至少说明：

- 决策问题与候选项。
- 使用的数据集、版本和标注范围。
- `contracts/rag-eval/experiment.schema.json` 对应的实验记录。
- 质量、延迟、吞吐、索引大小、VRAM/API 成本及风险对比。
- 选择结论、替代方案和回滚条件。

尚无真实教材与教师标注时，ADR 只能标记为 `provisional`，不得冻结生产默认模型。
