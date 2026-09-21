# 教材多模态 RAG V3.0 实施计划

> 依据：`docs/superpowers/specs/2026-09-21-multimodal-textbook-rag-v3-design.md`  
> 执行方式：单人、按阶段串行推进；每个阶段必须具备独立测试和回滚边界  
> 核心原则：先建立评测与数据契约，再替换解析、索引、检索和生成链路

## 完成状态约定

- `[ ]` 未开始
- `[-]` 进行中
- `[x]` 代码与约定测试完成
- `[v]` 已通过真实教材或目标环境验收

没有真实教材证据时，任务最多标记为 `[x]`，不得标记为 `[v]`。

## 阶段 0：评测基线与实验框架

### 0.1 建立纯函数评测核心 `[x]`

- [ ] 新建 `server/app/modules/knowledge/evaluation.py`。
- [ ] 实现 Recall@K、MRR、nDCG、Page Accuracy、BBox IoU、Citation Precision/Recall、Claim Support Rate 和 Refusal Accuracy。
- [ ] 指标函数只接收结构化输入，不访问数据库或外部 API。
- [ ] 新建 `server/tests/test_rag_evaluation.py`，覆盖空结果、重复结果、无答案问题、多个相关对象和无效 bbox。

验收：`python -m pytest server/tests/test_rag_evaluation.py -q` 通过，边界值有明确语义。

### 0.2 将 RAG 评测集改为外部数据驱动 `[x]`

- [ ] 新建 `contracts/rag-eval/v3-dataset.schema.json`，定义文档、对象标注、问题、答案要点和允许 Evidence 集合。
- [ ] 新建 `contracts/rag-eval/v3-sample.json`，保存可提交的最小合成样例。
- [ ] 新建 `scripts/rag_eval_v3.py`，读取数据集和检索运行结果，输出逐题及聚合指标。
- [ ] 保留 `scripts/rag_eval.py` 作为 V2 基线入口，并在输出中明确 `retrieval_version=hybrid-v1`。
- [ ] 新建 `server/tests/test_rag_eval_dataset.py`，验证 schema、ID 唯一性和标注引用完整性。

验收：同一输入重复运行得到相同报告；无真实教材时也能执行结构与指标回归。

### 0.3 建立实验记录合同 `[x]`

- [ ] 新建 `contracts/rag-eval/experiment.schema.json`。
- [ ] 记录数据集版本、Provider、模型、索引版本、RetrievalUnit 策略、Fusion、Rerank、Adaptive Cutoff、延迟、吞吐、成本和硬件/API 配额。
- [ ] 新建 `docs/adr/`，后续模型冻结使用 ADR，不直接把候选模型写死到业务代码。

验收：任何 Text/Visual/Fusion 实验都能由单个配置和报告复现。

## 阶段 1：V3 数据契约与不可变资产

### 1.1 新增数据库模型与迁移

- [ ] 新增 `server/alembic/versions/0010_rag_v3_objects.py`，不修改 0001—0009。
- [ ] 扩展 `MaterialVersion`：标准 PDF、页面清单、渲染器版本、管线版本、质量门禁状态。
- [ ] 新增 `ObjectAsset`、`ObjectRepresentation`、`ObjectRelation`、`RetrievalUnit`、`RetrievalIndexEntry`、`ParseReviewIssue` 和 V3 Evidence 表。
- [ ] 所有派生产物记录 `source_hash`、生成器/模型版本和状态。
- [ ] 为版本、对象顺序、关系、ReviewIssue 和索引版本建立必要索引与唯一约束。
- [ ] 更新 `server/app/db/models.py` 和迁移一致性测试。

验收：空库 `upgrade head` 成功；`alembic check` 无漂移；重复迁移不修改历史结构。

### 1.2 建立不可变资产服务

- [ ] 新建 `server/app/modules/materials/artifacts.py`，统一原文件、标准 PDF、Page Image 和对象裁剪的对象键。
- [ ] 对资产计算 SHA-256，禁止覆盖相同版本已有资产。
- [ ] 新建 `server/app/modules/materials/renderers/base.py`，定义 Word→PDF 与 PDF→Page Images 接口。
- [ ] 实现可替换的 LibreOffice/供应商转换适配器；缺少运行依赖时返回可诊断的阻塞 Issue。
- [ ] 将页面旋转、像素尺寸、DPI 和坐标变换写入渲染清单。
- [ ] 增加资产幂等、版本隔离和坐标变换测试。

验收：PDF 与 Word 都产生稳定的标准页面快照；重复任务不生成不同对象键。

## 阶段 2：统一解析、知识对象与教师审核

### 2.1 替换 Stub 解析主链路

- [ ] 将 `server/app/modules/materials/parsers/base.py` 扩展为 V3 Parser Adapter 合同。
- [ ] 新建 `mineru.py` 和 `docling.py` 适配器；原始响应只保存为调试资产，不泄漏到业务层。
- [ ] 将段落、图片、表格、公式、章节、页面和 bbox 映射为统一 KnowledgeObject。
- [ ] 将 Caption、表格结构、公式候选和 OCR 写入 ObjectRepresentation。
- [ ] 构建 parent/child、previous/next、caption_of、references 和 continues_on 关系。
- [ ] `StubPdfParser` 仅保留到迁移测试完成，随后从生产路由删除。

验收：相同输入与解析器版本产生稳定对象 ID/哈希；失败页不会伪装成成功对象。

### 2.2 质量门禁与抽样审核

- [ ] 新建 `server/app/modules/materials/review.py`，生成阻塞 Issue 和风险抽样清单。
- [ ] 将低置信、缺 bbox、阅读顺序冲突、跨页表格、公式不确定和关系冲突设为可配置规则。
- [ ] 扩展材料 API：质量报告、抽样对象、Issue 修正/忽略、发布检查。
- [ ] 教师修正写覆盖层或新对象版本，保留解析原值与审计。
- [ ] 未关闭阻塞 Issue 时禁止发布和学生索引。
- [ ] 增加教师、学生、越权、并发修正与版本冲突测试。

验收：200 页教材无需逐对象确认，但所有高风险对象必须被处理。

## 阶段 3：RetrievalUnit、GenerationUnit 与多模态索引

### 3.1 实现 RetrievalUnit 构建器

- [ ] 新建 `server/app/modules/knowledge/units.py`。
- [ ] 文本按语义边界创建 Child RetrievalUnit，并保存父对象和字符范围。
- [ ] 表格创建整表、行/列和关键单元格 RetrievalUnit。
- [ ] 图片、公式和页面创建文本表示与视觉区域 RetrievalUnit。
- [ ] Late Chunking 作为可选策略实现，不改变 KnowledgeObject。
- [ ] 增加稳定构建、边界、去重和版本变化测试。

验收：每个 RetrievalUnit 都能无歧义映射回原始对象与 bbox。

### 3.2 实现 GenerationUnit 组装器

- [ ] 新建 `server/app/modules/knowledge/context.py`。
- [ ] 从命中 Child 恢复 Parent Object，按需要补前后对象和关系闭包。
- [ ] 表格自动补齐表头、单位、标题和注释；公式补变量定义；图片补 Caption 和正文引用。
- [ ] 按教材覆盖范围去重，并执行 Token、页面数、对象数和延迟预算。
- [ ] 将最终上下文冻结为 EvidencePackage 快照。

验收：RetrievalUnit 仅负责召回；最终引用和生成上下文始终可回到教材事实对象。

### 3.3 Provider Adapter 与索引版本

- [ ] 扩展 `server/app/core/model_gateway.py`，为 Text Embedding、Visual Embedding、Rerank、Generation 和 Verification 定义用途接口。
- [ ] 新建 `server/app/core/providers/`，业务模块只依赖内部协议。
- [ ] 将 Provider、模型、维度、Prompt/规则和索引版本写入配置与数据库。
- [ ] 新索引构建完成并通过抽检后原子切换；失败继续使用上一有效版本。
- [ ] 供应商切换工具执行停写、重建、评测和启用流程。

验收：切换配置后不会混用旧向量空间；测试替身不访问公网。

### 3.4 文本与视觉模型选型实验

- [ ] 对 BGE-M3、候选中文/多语言模型和供应商 API Embedding 跑统一数据集。
- [ ] 对 CLIP 单向量、ColPali、ColQwen 和 VisRAG 风格路线跑统一视觉数据集。
- [ ] 比较 Dense、Sparse+Dense、Sparse+Dense+Multi-vector。
- [ ] 记录 Recall、MRR、nDCG、Figure Hit Rate、Page Recall、BBox Hit、延迟、吞吐、VRAM/API 成本和索引大小。
- [ ] 将默认组合写入 ADR，并保留至少一个可运行替代 Provider。

验收：模型选择来自可复现实验，不来自名称偏好。

## 阶段 4：Query Router、Fusion 与 Adaptive Retrieval

### 4.1 Query Analyzer

- [ ] 新建 `server/app/modules/knowledge/query.py`。
- [ ] 确定性解析章节、页码、图号、表号、公式号和显式选区。
- [ ] 模型只处理问题类型、模态、复杂度、指代、Rewrite 和有限拆解。
- [ ] Query Plan 输出范围、Channel Prior、预算和子目标。
- [ ] Rewrite/Multi-query/HyDE 与 Evidence 严格隔离。

验收：简单明确问题不强制调用分析模型；选区对象始终为强约束。

### 4.2 Query-aware Fusion

- [ ] 新建 `server/app/modules/knowledge/fusion.py`。
- [ ] 保留 RRF 作为基线，实现配置化 Weighted RRF。
- [ ] 保存 Query Type、Channel Prior、各通道贡献和 `fusion_version`。
- [ ] 实验比较分位数/z-score/校准分数融合。
- [ ] 真实标注不足时不启用 Learned Fusion。
- [ ] 增加通道缺失、重复候选和极端分数测试。

验收：每个最终排名都可解释、可复现、可做消融。

### 4.3 Adaptive Cutoff 与 Evidence Closure

- [ ] 新建 `server/app/modules/knowledge/adaptive.py` 和 `closure.py`。
- [ ] 综合分数断层、子目标覆盖、冲突、增量收益和预算决定停止。
- [ ] 闭包只沿已审核关系扩展，并对每个对象重新鉴权。
- [ ] 预算耗尽但证据不足时返回结构化拒答原因。
- [ ] 替换 `hybrid_search()` 固定 `[:top_k]` 路径，同时保留 V2 基线用于对照。

验收：不同类型问题得到不同证据规模；不能以低分候选填满固定 K。

## 阶段 5：跨模态回答、核验与精确引用

### 5.1 Evidence Package V2

- [ ] 新建版本化 Evidence DTO，包含对象、资产、bbox、关系、检索/生成版本和权限快照。
- [ ] Evidence Ticket 绑定用户、课程、旧教材版本和有效期，读取时重新鉴权。
- [ ] 已归档或新版发布不改变历史回答引用的教材版本。

验收：历史引用稳定，且不能绕过当前用户权限。

### 5.2 结构化生成与双层核验

- [ ] LLM/VLM 输出 answer、claims、evidence_ids 和 support_level。
- [ ] 实现存在性、版本、权限、定位和撤回状态的确定性核验。
- [ ] 实现文本、表格数值/单位、公式和视觉 Claim 的语义核验接口。
- [ ] 对 partial/conflict/not_found 最多进行一次有界补检索。
- [ ] 核验失败或超时的草稿不得作为正式答案展示。

验收：教材无证据问题必须拒答；模型参数知识不能进入最终答案。

### 5.3 引用与侧边栏

- [ ] 前端实现 PDF 快照查看器、对象缩略图、bbox 高亮和引用焦点恢复。
- [ ] 选中文本或框选图表创建独立分支，携带最小来源快照。
- [ ] 只有用户确认的结构化结论能够写回主线。
- [ ] 增加键盘操作、读屏标签、缩放和移动端测试。

验收：段落、图片、表格和公式引用都能跳到正确旧版本并精确高亮。

## 阶段 6：持久 Worker、性能与安全

### 6.1 替换进程内后台任务

- [ ] 引入持久 Worker/队列 Adapter，将解析、渲染、Representation、索引和重建任务迁出 Web 进程。
- [ ] 实现租约、心跳、幂等、重试、取消和安全检查点。
- [ ] Worker 重启后恢复未完成任务，过期执行者不能覆盖新结果。

验收：进程重启、重复投递和部分失败不会产生重复资产或错误发布。

### 6.2 性能与容量

- [ ] 对预计算、并行召回、在线 VLM 页面数和缓存边界进行剖析。
- [ ] 运行 30 并发的检索、文本问答、视觉问答和混合场景。
- [ ] 首个有效答案 P95 ≤ 10 秒；记录最终核验完成延迟。
- [ ] 设置队列背压、用途级并发、超时、预算和熔断。

验收：性能目标不通过跳过权限、审核或核验达成。

### 6.3 安全与隐私

- [ ] 测试 IDOR、未发布对象、旧版本、Evidence Ticket 所有者和课程隔离。
- [ ] 测试教材内提示注入、恶意文件、超大对象和模型输出越权动作。
- [ ] 日志只保存脱敏摘要、模型、耗时、Token 和状态。

验收：越权召回、未发布对象泄露和阻塞对象泄露均为 0。

## 阶段 7：真实教材验收

- [ ] 导入真实 PDF/Word 教材并完成教师风险抽样审核。
- [ ] 建立正式问题—答案—Evidence 标注集。
- [ ] 重新完成 Embedding、Visual、Fusion、Rerank 和 Adaptive Cutoff 消融。
- [ ] 调整阈值和默认模型，更新 ADR 和容量成本记录。
- [ ] 完成教师端发布、学生提问、引用跳转、分支讨论和拒答验收。

只有阶段 7 完成后，V3 才能标记为 `[v]` 并进入班级试用。
