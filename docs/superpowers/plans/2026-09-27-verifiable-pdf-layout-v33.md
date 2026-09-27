# V3.3：可验证 PDF 版面对象与页级恢复执行计划

> 设计依据：`docs/superpowers/specs/2026-09-27-verifiable-pdf-layout-v33-design.md`。
> 范围：原生数字 PDF；不引入 OCR、MinerU/Docling、外部模型或视觉检索。
>
> 状态（2026-09-27）：§1 的页级状态迁移、§2 的原生图片/规则网格表格/保守公式对象提取、§3 的逐页提交/恢复主路径及 §4 的教师页级进度展示已编码；解析器与关键解析/重解析回归已通过。OpenStax 的首轮离线对象统计已完成，报告见 `docs/v3/2026-09-27-openstax-native-layout-v33.md`；对象抽样人工核验、完整后端与前端全量验证仍待完成，不能据此宣称视觉检索完成。

## 1. 基线与迁移

1. 检查 `KnowledgeObject`、`ObjectAsset`、`ParseReviewIssue` 的现有约束，新增 `ParsedPage`（版本、解析器版本、页码、状态、对象/资产计数、内容哈希、错误详情、时间）或等价页级状态表。
2. 增加唯一约束 `(material_version_id, parser_version, physical_page)`，使完成页可以在重试中稳定跳过。
3. 为页面状态、版本和状态建立索引；保留既有迁移，只新增前向 Alembic 迁移。
4. 执行 `alembic upgrade head` 与 `alembic check`。

## 2. 原生 PDF 页面布局解析器

1. 将 `stub_pdf.py` 重构为可单页调用的布局适配器；保留 `StubPdfParser` 兼容入口，版本改为 `native-layout-v3.3`。
2. 对每页提取文本块、原生图片块、绘制路径和页面尺寸，并统一输出 PDF 用户空间 `bbox`。
3. 保留已验证的章节识别规则；让页内对象按阅读顺序输出，章节上下文可跨页传递。
4. 建立保守图片对象：仅当 PDF 图片块可用且坐标合法时生成 `figure`，不以图注替代。
5. 建立保守表格/公式候选：只在网格/布局或独立数学文本块证据充分时建立对象；不确定时写解析问题，不伪造对象。
6. 为图注/表题建立可选的待审核关系，关系证据不足时不连边。

## 3. 页面资产与幂等持久化

1. 增加对象资产键生成函数，键包含版本、解析器版本、页码、对象序号和内容 Hash。
2. 用现有 MinIO 适配器写入图片原始数据或页面裁剪；写入 `ObjectAsset` 的 Hash、尺寸、bbox、页码和版本。
3. 将“单页对象 + 资产元数据 + 解析页状态 + Job checkpoint”置于同一数据库提交边界；对象存储失败时该页不完成。
4. 改造 `run_parse_job`：读取检查点，已完成页跳过；单页完成即更新心跳、进度、计数与 `last_page`；失败时保存错误页和可重试信息。
5. 所有页面完成后才做质量汇总、对象关系序列化、旧索引失效与版本状态切换。

## 4. 质量、任务状态与前端展示

1. 标准化页级问题码：`page_parse_failed`、`layout_bbox_missing`、`asset_write_failed`、`table_detection_uncertain`、`formula_detection_uncertain`、`cross_page_object_uncertain`。
2. 使任务查询返回真实的 `completed_pages`、`total_pages`、对象数、资产数、失败页和下一步操作。
3. 教师工作台复用现有资料工作流：显示“逐页解析”加载状态、页级进度及失败原因；只展示真实任务字段。
4. 不增加学生侧草稿资产入口、不添加“视觉检索”按钮；发布门禁和角色限制保持不变。

## 5. 检索边界与回归

1. 保持 `build_chunk_rows` 只从段落生成文本 `RetrievalUnit`，禁止本版本把 figure/table/formula 误接入文本或视觉索引。
2. 重解析或对象变化仍按现有逻辑删除旧 `RetrievalUnit` 与 `RetrievalIndexEntry`，索引必须重建。
3. 验证对象过滤请求不会以段落命中伪装图表公式结果。

## 6. 测试

1. 扩充 `server/tests/test_materials.py`：文本 bbox、图片对象、无证据不建对象、候选告警、坐标转换和读取顺序。
2. 新增页面持久化/恢复测试：中途失败、重试从下一页继续、同页不重复、资产失败回滚、最终质量报告。
3. 扩展路由测试：教师任务详情页级检查点、学生无权读取草稿对象/资产、发布门禁仍有效。
4. 运行受影响测试、Ruff、迁移检查、OpenAPI 导出和前端 typecheck/lint/build。
5. 使用本地 OER PDF 做解析验证并生成 V3.3 报告，明确区分对象产出与检索/视觉效果。

## 7. 完成标准

1. 迁移、服务、解析器、任务、API、前端文案和测试保持一致。
2. 本地 OER 运行能证明逐页 checkpoint 及真实 `bbox`/对象资产产出。
3. 不宣称扫描件解析、视觉检索、表格语义理解或外部模型效果已完成。
