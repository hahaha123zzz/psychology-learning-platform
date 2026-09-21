# 教材多模态 RAG V3.0 设计方案

> 日期：2026-09-21  
> 状态：设计已完成讨论，待用户复核书面规格  
> 输入材料：`教材RAG优化讨论整理.md`、当前仓库代码与 V2.0 执行手册

## 1. 背景与决策

当前代码已建立课程、资料版本、知识对象、混合检索、证据票据、问答、审核、权限和审计等业务底座，但 RAG 实现仍是开发期基线：PDF 使用 `StubPdfParser`，Embedding 使用本地 `hash-v1`，检索以文本 Chunk、BM25、向量召回和固定 `top_k` 为主，尚未形成真实 Reranker、视觉检索、自适应取证、对象级引用和跨模态核验。

V3 不保留这些落后实现的运行兼容性，允许清空开发数据并重建索引。历史 Alembic 迁移仍保持只读，通过新增迁移建立 V3 数据结构。改造保留可靠的业务底座，包括 `Material/MaterialVersion`、不可变版本、对象存储、Parser Adapter、统一任务状态、幂等、审计、RBAC、教师审核发布、模型网关和侧边栏分支隔离。

总体路线确定为：

> 以教材对象为事实核心，同时建设文本与视觉检索通道；页面视觉检索是补充通道，不替代结构化解析。

## 2. 目标、约束与非目标

### 2.1 目标

1. 支持有文本层的 PDF 和 Word 教材。
2. 保留段落、图片、表格、公式、页面布局和对象关系，不把教材压扁为纯文本。
3. 根据问题类型动态选择 Sparse、Dense、Visual、表格或公式检索。
4. 引用精确绑定教材版本、页面、对象和 `bbox`，点击后可跳转并高亮。
5. 回答严格以已发布教材为唯一事实来源；证据不足时拒答。
6. 支持从段落、图片、表格或公式选区发起侧边栏分支提问，只有用户确认的结论才能回传主线。
7. 单门课程初始容量按约 200 页设计，峰值支持 30 个并发问答，首个有效答案 P95 不超过 10 秒。
8. 允许调用第三方模型 API。单次部署默认使用一组供应商配置，但通过 Provider Adapter 支持 DeepSeek、MiMo 或其他供应商切换。

### 2.2 约束

- 供应商切换允许停机，并允许重建全部不兼容索引。
- 教材原文、页面截图和学生提问允许发送至经批准的第三方 API。
- 教师抽样检查解析质量；所有阻塞级问题必须处理后才能发布。
- 历史回答永久绑定生成时使用的旧教材版本，不自动迁移到新版本。
- Word 必须先渲染为不可变的标准 PDF 快照，引用不直接依赖可重排的 Word 页码。

### 2.3 首期非目标

- 扫描版 PDF 的完整 OCR 支持不是首期硬要求；无可靠文本层时标记为不支持或阻塞发布。
- 不建设 GraphRAG、通用知识图谱、大量自治 Agent 或按请求动态供应商路由。
- 不允许模型用参数知识补足教材中没有的内容。
- 不为早期开发数据维护双写、兼容读取或旧索引在线迁移。

## 3. 总体架构

```text
PDF / Word
    │
    ├─ 原文件永久保存
    ├─ Word → 标准 PDF 快照
    └─ PDF 快照 → Page Images
             │
      Parser Adapter
      ├─ MinerU primary
      └─ Docling fallback / comparison
             │
      Knowledge Objects
      ├─ text / section / page
      ├─ image / table / equation
      ├─ assets and representations
      └─ object relations
             │
      Review + Quality Gate
             │
      Multimodal Index
      ├─ Sparse
      ├─ Dense
      └─ Visual
             │
Question → Query Analyzer / Router
             │
      Hierarchical Scope Filter
             │
      Parallel Retrieval → Fusion → Rerank
             │
      Adaptive Cutoff → Evidence Closure
             │
      Multimodal Evidence Package
             │
      LLM / VLM Generation
             │
      Claim-Evidence Verification
             │
      Verified Answer + Object Citations
```

## 4. 不可变教材资产

每个 `MaterialVersion` 保存：

- 用户上传的原始文件。
- 用于解析和引用的标准 PDF 快照。
- 每页固定分辨率的 Page Image。
- 页面尺寸、旋转角度、渲染 DPI、字体替换记录和渲染器版本。
- 文件哈希、处理配置和产物清单。

坐标统一保存为相对于未旋转标准页面的归一化坐标 `[x1, y1, x2, y2]`，同时保留解析器原坐标和页面像素尺寸。前端依据标准页面变换矩阵完成缩放、高亮和滚动定位。

原始文件、快照和页面图不可被新版本覆盖。教材新版本创建新的 `MaterialVersion` 和资产集合；历史回答继续读取旧版本资产。

## 5. 核心数据模型

### 5.1 KnowledgeObject

教材事实对象，不承担模型专属索引职责：

```text
id
material_id
material_version_id
object_type
chapter_path
page_no
bbox_normalized
reading_order
parent_id
raw_content
normalized_content
parser
parser_version
confidence
review_status
content_hash
created_at / updated_at
```

`object_type` 至少支持 `section`、`paragraph`、`image`、`table`、`equation` 和 `page`。对象修正使用覆盖层或新对象版本表达，不静默修改解析原始值。

### 5.2 ObjectAsset

保存页面图、图片裁剪、表格截图和公式截图：

```text
id
knowledge_object_id
asset_type
object_key
mime_type
width / height
sha256
render_version
```

### 5.3 ObjectRepresentation

保存可重建的派生表示：

- OCR 文本。
- 图片 Caption 和 VLM Description。
- 表格 Markdown、HTML/JSON、单元格结构、单位和摘要。
- 公式 LaTeX 候选、OCR 候选和语义描述。
- 检索文本与 Late Chunking 表示。

每项记录生成方式、Provider、模型、Prompt/规则版本、置信度和来源依赖。Representation 不是教材事实，不能单独作为最终引用。

### 5.4 ObjectRelation

关系类型至少包括：

- `parent_of` / `child_of`
- `previous` / `next`
- `caption_of`
- `references`
- `continues_on`
- `explains`
- `same_table` / `same_figure`

关系记录来源、置信度和审核状态，用于 Evidence Closure，但不能绕过发布和权限过滤。

### 5.5 RetrievalUnit 与 GenerationUnit

`KnowledgeObject` 是教材事实对象，但检索粒度与生成上下文不能等同。V3 显式区分两个概念：

#### RetrievalUnit

`RetrievalUnit` 是用于召回和排序的可重建派生单元，可以比教材对象更小或更适合特定检索通道。例如：

- 长段落按语义边界形成 Child Chunk。
- 表格形成整表、行、列或关键单元格组合。
- 图片形成图片裁剪、Caption/OCR 文本和视觉 Patch 表示。
- 页面形成供多向量视觉检索使用的 Page Unit。
- 公式形成 LaTeX、语义描述和公式裁剪表示。

每个 RetrievalUnit 必须记录其来源 `KnowledgeObject`、字符范围或 `bbox`、构建策略、Representation 版本和覆盖范围。Sparse、Dense、Visual 和 Multi-vector 索引都建立在 RetrievalUnit 上，而不是默认直接对整个 Paragraph Object 建索引。RetrievalUnit 只能用于找回教材，不能单独成为最终事实引用。

#### GenerationUnit

`GenerationUnit` 是检索完成后为回答临时组装的最小充分上下文。它通常包含命中 RetrievalUnit 对应的完整父对象、必要前后对象以及 Evidence Closure 补入的图、表、公式、标题、单位和定义。GenerationUnit 在进入模型前冻结为 EvidencePackage 快照，并受 Token、视觉页数和延迟预算约束。

典型规则为：

```text
Child Chunk 用于召回
→ Parent Object 用于理解
→ Relation Closure 用于补齐证据
→ GenerationUnit 用于生成与核验
```

表格问题可以按单元格或行召回，但生成时必须携带足以解释该数值的表头、单位、标题和注释；视觉页面可以按 Patch 召回，但生成时只发送相关页面区域及其关系对象。去重以 GenerationUnit 的教材覆盖范围为准，避免多个 Child Chunk 重复占用上下文。

Late Chunking 只是一种 RetrievalUnit 表示策略：先在较大的父上下文中编码，再取得局部单元表示。它不能替代父对象、原始内容或 GenerationUnit 的显式组装。

### 5.6 RetrievalIndexEntry

索引条目关联对象或表示，记录：

```text
channel: sparse | dense | visual
provider
model
model_version
dimension
index_version
source_hash
status
```

不同 Embedding 模型的向量绝不混用。新索引完整构建、抽检通过后原子切换为当前版本。

### 5.7 Evidence

Evidence 绑定：

- 用户、课程和教材版本。
- 知识对象、对象类型、页面和 `bbox`。
- 原始内容、相关资产与必要关系闭包。
- 检索版本、生成时间、有效期和撤销状态。

Evidence 读取时重新校验课程成员、发布状态和版本可用性。对历史回答，允许读取其旧版本证据，但不能借此访问用户从未拥有权限的教材。

### 5.8 ParseReviewIssue

记录低置信对象、阅读顺序异常、跨页表格、公式不确定、Caption 缺失、图文关系冲突、页面渲染失败等问题。阻塞级 Issue 全部关闭后，教师才可确认发布。

## 6. 解析、审核与发布

1. 上传 PDF 或 Word，保存原文件并计算哈希。
2. Word 在固定字体、页面尺寸和渲染器版本下生成标准 PDF。
3. PDF 生成 Page Images。
4. MinerU Adapter 产出对象、坐标和关系；失败或质量异常时调用 Docling Adapter 对照或回退。
5. 对图片、表格和公式生成裁剪资产及派生表示。
6. 运行阅读顺序、坐标、对象完整性、跨页和关系一致性检查。
7. 生成风险驱动抽样清单：全部低置信对象、全部异常对象，加上按类型和章节分层的随机样本。
8. 教师处理所有阻塞项并确认质量报告。
9. 构建文本与视觉索引，通过索引抽检后发布。

发布是版本级原子操作。任一必要资产、Review Issue 或索引构建失败时，版本保持不可发布状态。

## 7. Query Analyzer 与范围路由

Query Analyzer 输入用户问题、课程、当前页面、显式选区和会话上下文，输出结构化计划：

```text
target_documents
target_chapters
target_objects
modalities
question_type
complexity
rewrite_required
decomposition[]
retrieval_budget
```

页码、章节号、图号、表号和公式编号优先用确定性规则提取。模型只处理指代、模糊表述、术语差异和综合问题。

- 定义题：Sparse + Dense。
- 图片、流程和布局题：Visual 为主，文本为辅。
- 表格数值题：结构化表格检索 + Visual 复核。
- 公式题：LaTeX/周边文本检索 + 公式裁剪复核。
- 对比和跨章节题：受限 Multi-query 或问题拆解。
- 显式选区题：选中对象是强约束，检索仅补充其必要关系对象。

Rewrite、Multi-query 和 HyDE 仅用于查找教材，输出不进入 Evidence，也不能成为回答事实。

## 8. 自适应多模态检索

### 8.1 分层范围过滤

先按 `Course → Document → Chapter → Object` 缩小范围。课程成员、版本发布状态和对象审核状态必须在任何召回与排序之前过滤。

### 8.2 并行召回与融合

在允许的范围内并行运行 Sparse、Dense 和 Visual 召回。每个通道取较宽候选集，Fusion 记录各通道排名、原始分数、归一化分数和命中原因。

Query Analyzer 输出 `channel_priors`，表达当前问题对各通道的先验重要性。例如图片问题提高 Visual 优先级，定义题提高 Sparse/Dense 优先级；先验参数来自评测配置，不能在业务代码中写死。通道不可用时必须显式记录降级原因，不能简单把剩余权重重新归一化后假装检索完整。

Fusion 采用可替换、可版本化的策略接口，并按同一评测集依次比较：

1. RRF，作为与分数量纲无关的稳定基线。
2. Weighted RRF，作为首期推荐实现，用 Query Type 的 Channel Prior 调整各通道贡献。
3. Score Normalization Fusion，比较分位数、z-score 或校准后的跨通道分数融合。
4. Learned Fusion，仅在真实教材和足够人工相关性标注到位后评估，首期不以小规模模拟集训练线上排序器。

每次 Fusion 输出 `fusion_version`、Query Type、Channel Prior、各候选通道贡献和最终排名，保证离线复现和消融评测。Reranker 在 Fusion 候选上继续综合：

- 文本与视觉相关性。
- 问题目标与对象类型是否一致。
- 章节、页面和显式选区距离。
- 图号、表号和对象关系的确定性命中。
- 对象审核状态与解析置信度。

### 8.3 Adaptive Cutoff

不使用单一固定 `top_k`。停止条件同时考虑：

- Reranker 分数和相邻分数断层。
- 每个问题子目标是否有至少一个直接证据。
- 是否存在相互冲突的候选。
- Token、视觉页面数、时间和调用预算。
- 新增候选是否仍带来有效覆盖增量。

达到充分性条件或预算上限即停止。达到预算但证据仍不足时返回拒答，不用低质量候选凑数。

### 8.4 Evidence Closure

对最终候选沿已审核关系补齐最小证据闭包，例如：

- 正文“见图 4-3”补入 Figure 4-3、Caption 和必要图例。
- 表格补入标题、表头、单位、注释和跨页延续部分。
- 公式补入变量定义和紧邻解释段落。
- 指代词补入必要父段落或前置定义。

闭包扩展受深度、对象数和 Token 预算限制，且每个补入对象都重新执行权限和版本校验。

## 9. 回答生成与 Claim-Evidence 核验

服务端形成不可变 `EvidencePackage`，只包含少量原始对象、必要页面裁剪、关系和定位信息。模型输出结构化草稿：

```text
answer
claims[]
  text
  evidence_ids[]
  support_level
```

核验分为两层：

1. 确定性核验：Evidence 存在、课程和版本一致、用户可访问、对象已发布、定位可恢复、内容未撤回。
2. 语义核验：Claim 是否被引用直接支持；表格数值、单位、方向、比较关系及公式含义是否一致。

`partial`、`conflict` 或 `not_found` Claim 必须删除、降级表述或触发一次有界补检索。补检索后仍不足则明确说明教材未提供足够依据。模型参数知识不得出现在最终答案中。

SSE 可以先返回检索、生成和核验进度，但未经核验的文本不得显示为已确认教材结论。Generation 成功而 Verification 超时或失败时，不发布该答案。

## 10. 引用与侧边栏交互

引用卡片显示材料、版本、章节、页码、对象类型、审核状态以及段落原文或图表缩略图。点击后：

1. 打开回答生成时的旧版本 PDF 快照。
2. 跳转到绑定页面。
3. 按标准坐标变换高亮 `bbox`。
4. 允许查看关联 Caption、表格结构或公式候选，但明确区分原始证据与模型派生说明。

学生选择段落或框选图表后，可以直接创建侧边栏分支：

- 分支保存选中对象和最小来源快照。
- 分支检索以选中对象为强约束。
- 关闭分支不修改主会话。
- 只有用户点击“带回主线”并确认的结构化结论可以写入主线摘要。
- 分支探索文本、错误猜测和未确认结论不自动合并。

## 11. Provider 与模型治理

Provider Adapter 对业务层暴露统一用途接口：

- Document/Vision Understanding
- Text Embedding
- Visual Embedding
- Rerank
- Answer Generation
- Claim Verification

单次部署使用一组明确配置。每次调用记录用途、Provider、模型、版本、状态、耗时和 Token，但不记录完整教材、学生隐私、Token 或 Cookie。按用途设置并发池、队列上限、超时、预算和熔断。

供应商切换流程：停用写入 → 修改配置 → 重建不兼容 Representation/Index → 运行评测和抽检 → 原子启用新索引 → 恢复服务。教材事实对象和引用资产不因供应商切换而改变。

## 12. 持久任务与故障处理

解析、渲染、对象抽取、表示生成、Embedding、视觉索引和索引切换均通过持久 Worker 执行：

- 记录输入版本、配置、阶段、进度、尝试次数、错误、可重试性和产物版本。
- Worker 重启后从安全检查点恢复。
- 相同幂等键不重复创建任务、资产或外部计费调用。
- 部分产物不能进入当前有效索引。
- 新索引失败时继续保留上一有效索引。

在线问答降级规则：

- 纯文本问题的 Visual 通道失败时，可在证据充分的前提下退化为文本链路。
- 视觉问题的 Visual 通道失败时，明确说明暂时无法可靠回答。
- 排队超过上限时返回可重试状态，不降低证据标准。
- Rerank、Generation 或 Verification 超时均记录具体阶段和 `request_id`。

## 13. 性能设计

性能目标为 30 并发下首个有效答案 P95 ≤ 10 秒。为此：

- 在入库阶段预计算 OCR、Caption、表格结构、公式候选、文本 Embedding 和 Visual Embedding。
- Sparse、Dense 和 Visual 召回并行执行。
- 在线 VLM 只读取 Rerank 后的少量对象裁剪或页面区域。
- Query Analyzer 优先使用确定性解析，避免简单问题调用额外模型。
- 为检索、Rerank、生成和核验分别设置延迟预算；预算耗尽时停止扩展并执行证据充分性判断。
- 缓存仅复用版本、权限范围和模型版本完全一致的派生产物，不缓存跨用户 Evidence Ticket。

性能目标不得通过跳过权限过滤、教师审核或 Claim Verification 达成。

## 14. 评测与验收

### 14.1 临时评测集

真实教材到位前，创建可提交仓库的自制或公开授权 PDF/Word 测试资料，覆盖正文、跨页内容、流程图、统计图、复杂表格、公式、图注、脚注和正文引用关系。为关键对象标注页码、类型、`bbox`、阅读顺序和关系。

问题集覆盖定义、图表、数值、比较、跨章节、模糊表达、无答案和提示注入。每题保存答案要点和允许引用的对象集合，而不只保存页码。

### 14.2 指标

| 层级 | 指标 |
|---|---|
| 解析 | 对象召回率、阅读顺序准确率、表格结构准确率、公式候选准确率 |
| 定位 | Page Accuracy、BBox IoU、对象类型准确率、引用跳转成功率 |
| 检索 | Recall@K、MRR、nDCG、Figure/Table/Equation Hit Rate |
| 证据 | Evidence Closure 完整率、Citation Precision、Citation Recall |
| 回答 | Claim Support Rate、Hallucination Rate、Refusal Accuracy |
| 性能 | 30 并发下首个有效答案 P95 ≤ 10 秒 |
| 安全 | 越权召回、未发布对象泄露、阻塞对象泄露均为 0 |

### 14.3 门槛

- 硬门槛：权限泄露、版本错引、无效 `bbox`、未审核对象进入学生检索必须为零。
- 回归门槛：任何合并不得降低现有测试集关键指标。
- 效果门槛：记录当前实现基线，要求 V3 在文本、视觉、表格和拒答指标上分别提升。
- 真实教材到位后，由教师建立正式问题—答案—证据集，替换模拟资料产生的效果结论；未完成真实教材验收前不得宣称达到生产教学质量。

候选供应商必须在相同测试集、配置和并发条件下对照，综合质量、延迟、稳定性和成本选择默认配置。

### 14.4 文本与视觉模型选型实验

架构层只冻结能力接口，不预先指定某个模型。实施前必须用同一教材评测集和固定硬件/API 配额完成模型选型实验，并把结论记录为独立 ADR。

视觉检索候选至少覆盖以下技术路线：

- ColPali 类页面多向量 Late Interaction。
- ColQwen 类中文/多语言文档视觉多向量模型。
- VisRAG 风格的页面召回后 VLM 阅读链路。
- CLIP 类单向量视觉基线。

比较指标包括 Figure Hit Rate、Page Recall@K、对象/BBox 命中率、P95 延迟、并发吞吐、VRAM 或 API 成本、索引大小和构建时间。最终选择 Pareto 合理方案，不能只看单项 Recall；单向量方案即使速度更快，也只有在复杂图表和布局测试达到门槛时才能成为默认通道。

文本检索候选至少包含 BGE-M3、其他中文/多语言 Embedding 以及候选供应商的 API Embedding。实验矩阵比较：

```text
Dense only
Sparse + Dense
Sparse + Dense + Multi-vector
```

统一报告 Recall@K、MRR、nDCG、中文术语与模糊表达命中率、延迟、吞吐、索引大小和调用成本。BGE-M3 只是候选，不因设计阶段曾被提及而直接成为默认模型。Embedding、Visual Retrieval、Rerank 和 Fusion 分别做消融实验，避免把组合提升错误归因给单一模型。

## 15. 分阶段实施顺序

### 阶段 0：基线与评测夹具

- 固定当前 V2 检索基线。
- 制作 PDF/Word 多模态测试资料和标注集。
- 建立解析、检索、引用、回答、拒答和性能报告格式。
- 建立 Text/Visual Retrieval 与 Fusion 的统一实验 Harness，用相同问题集完成候选 Provider 和模型初筛。

### 阶段 1：不可变资产与对象模型

- 新增 V3 数据迁移。
- 建立 Word → PDF、PDF → Page Image 链路。
- 实现 KnowledgeObject、Asset、Representation、Relation、RetrievalUnit、GenerationUnit 和 ReviewIssue。
- 接入 MinerU Adapter，并建立 Docling 回退接口。

### 阶段 2：教师审核与质量门禁

- 建立风险驱动抽样、阻塞问题处理和版本级发布。
- 完成段落、图、表、公式的对象预览与 `bbox` 高亮校验。

### 阶段 3：真实多模态索引

- 替换 `hash-v1`，接入真实 Text/Visual Embedding。
- 建立 Sparse、Dense、Visual 索引和版本切换。
- 完成文本 Embedding、视觉单向量/多向量路线、真实 Reranker 与 Provider 对照评测，并用 ADR 冻结首期默认组合。

### 阶段 4：Query Router 与 Adaptive Retrieval

- 实现确定性范围解析、模态分类和受限 Query Rewrite。
- 实现 Query Type → Channel Prior、RRF/Weighted RRF 基线、并行召回、Query-aware Fusion、Adaptive Cutoff 和 Evidence Closure。
- 对 Fusion、Rerank、Adaptive Cutoff 分别进行消融评测；真实标注不足时不启用 Learned Fusion。
- 将教材问答和题目生成统一迁移到新 Evidence 接口。

### 阶段 5：跨模态回答与引用

- 建立 Multimodal Evidence Package、结构化 Claim 输出和双层核验。
- 实现段落、图片、表格和公式引用卡片及精确跳转。
- 完成选区侧边栏分支和显式回传主线。

### 阶段 6：可靠任务与性能安全

- 将进程内任务迁移到持久 Worker。
- 完成限流、队列、超时、熔断、索引原子切换和恢复测试。
- 在 30 并发下优化并验证 P95 10 秒目标。
- 完成 IDOR、提示注入、未发布内容泄露和日志脱敏测试。

### 阶段 7：真实教材验收

- 导入真实教材并由教师完成抽样审核。
- 建立正式评测集，重新比较 Provider 和检索策略。
- 只依据真实教材结果调整阈值、召回规模、路由和模型配置。
- 达到硬门槛和约定效果后，才进入班级试用。

## 16. 完成定义

V3 不能仅以“API 已接入”或“能够回答问题”作为完成标准。完成必须同时满足：

- PDF 与 Word 能稳定生成不可变快照、页面图和知识对象。
- 教师能够发现并处理阻塞问题，再发布完整版本。
- 文本、图片、表格和公式问题均通过相应检索通道获得正确对象。
- 回答严格由教材 Evidence 支持，证据不足时正确拒答。
- 引用可打开生成时的教材版本并精确高亮 `bbox`。
- 分支会话保持隔离，只有用户确认内容回传主线。
- 供应商可通过配置和重建流程切换。
- 30 并发下满足 P95 10 秒，且不牺牲权限、审核和核验。
- 自动化评测、权限测试、故障恢复和真实教材教师验收均有可复现证据。
