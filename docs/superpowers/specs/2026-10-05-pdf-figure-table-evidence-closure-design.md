# PDF 原生 Figure/Table 证据闭环设计

日期：2026-10-05  
状态：待用户审阅  
范围：学生端 V0.9 Demo 后续首个 Figure/Table 实现切片

## 目标

在本地合成 PDF 上打通原生表格检索和嵌入图像定位，使学生能从教材搜索结果查看可靠的表格数据或打开相邻图像的固定页 Reader。所有引用继续绑定不可变 `MaterialVersion`、来源对象、物理页和 PDF 用户空间 bbox；实现不调用外部模型或外部解析服务。

## 当前实现与缺口

- `StubPdfParser` 已从固定 PDF 解析原生规则网格表格文本与嵌入图像对象，并提供物理页、bbox；图像对象有原始图像资产，但没有图像语义文本。
- `KnowledgeObject`、`ObjectRelation`、`RetrievalUnit` 已支持表格/图像对象、`table_cells`/`image` 单元、已审核的相邻关系和来源对象映射。`EvidencePointer` 已保存 `source_object_id`、固定教材版本、对象类型、页码、bbox 与 anchors。
- 索引构建当前只为段落建立 `text_child` RetrievalUnit，且假设每个分块都有 dense 向量；表格需要独立的稀疏写入分支。PDF 表格单元格还可能同时被解析为普通文本块，默认混合排序不能保证表格对象出现在 `top_k` 内。
- 搜索证据闭包返回相邻对象 ID/页码/bbox，但没有持久 `EvidencePointer`，学生界面也没有相邻对象入口。当前闭包 SQL 只限制目标版本属于候选版本集合，尚未要求源对象与目标对象处于同一版本。
- Reader Drawer 已能通过 EvidencePointer 恢复授权、读取固定版本页图并高亮 bbox。
- 学生搜索请求沿用 `include_neighbors=true` 默认值；Tutor 也复用混合检索和闭包上下文，因此新增表格索引后必须限制生成输入，不能仅约束 Embedding 构建。当前 hash-v1 基线依赖明确的关键词锚点，本切片不承诺图像语义检索或中文分词泛化。
- DOCX 对象缺少可验证物理页/bbox，现有 DOCX→PDF 映射只支持唯一文本锚点，非文本 figure 映射明确 unsupported；不纳入本切片。

## 方案

采用“表格文本检索 + 图像空间定位”的保守方案。

1. 对具有有效固定物理页和 bbox 的 PDF 原生 `table` 对象，以 parser 提取的单元格文本构建 `table_cells` RetrievalUnit，并用稀疏/BM25 通道索引。该单元保留唯一 `source_object_id`、教材版本、章节和页码，`build_version` 继续绑定本次 IndexJob，满足现有 DomainRelease/PublicationSnapshot pin。表格分块的 embedding 和 embedding_version 均为空，不发送给 Embedding API；段落向量构建流程单独运行，只有表格而无段落的 PDF 也能成功建立稀疏索引。对完全落入表格 bbox、且内容已由该表格单元覆盖的 PDF 文本块做确定性去重，避免同一单元格同时成为段落证据。
2. 不从图像像素生成 OCR、标题、caption 或语义描述。闭包只沿已批准的 `previous`/`next` 阅读顺序关系，并要求源、目标 `KnowledgeObject.material_version_id` 相同。相邻 figure 必须来自固定 PDF 且有有效页码/bbox，才创建 EvidencePointer；响应和前端明确标注“阅读顺序相邻图像，仅提供位置预览”，不把相邻关系表述为图注或语义关联。
3. 表格检索命中本身创建 EvidencePointer；指针 excerpt 使用本地解析的表格文本，anchors 取知识对象实际 bbox。图像闭包指针保留空 excerpt 与对象元数据，前端显示明确的无语义解析提示；Reader 仍可打开固定物理页并高亮 bbox。
4. 前端学生检索结果在表格命中时显示表格文本和固定来源入口，并提供显式“只看表格”过滤以调用现有 `object_types=["table"]`，保证学生能稳定找到表格对象；在图像闭包存在时显示“相邻图像，仅定位”入口。Tutor 检索限制主命中为 paragraph，生成上下文过滤 table/figure 闭包对象；本切片不把新增图表对象的文本或资产送入 Tutor/Claim 模型输入。相邻段落仍作为其自身文本证据单独引用。
5. 若对象缺少有效物理页、bbox、固定版本或当前课程授权，则不提供可打开的图表指针；查询继续按现有错误/降级语义处理，不伪造坐标或跨版本回退。

## 数据流

```text
固定 PDF
  └─ StubPdfParser：table(text+bbox) / figure(asset+bbox)
      └─ KnowledgeObject + 已有阅读顺序 ObjectRelation
          ├─ table → 稀疏 table_cells RetrievalUnit → KnowledgeChunk/BM25
          │          └─ 表格 EvidencePointer → Reader 页图/bbox 高亮
          └─ figure ← 已审核 previous/next 闭包
                     └─ 仅定位 EvidencePointer → Reader 页图/bbox 高亮
```

闭包对象不提升为检索命中，不合成 caption 关系。检索权限和发布版本过滤继续先于排序及闭包读取；闭包关联限于同一 `MaterialVersion`，其图表指针使用目标对象自身的版本与来源身份。读取 EvidencePointer 时沿用当前鉴权与撤回检查。

## 数据库与公共契约

- 预期不新增 Alembic 迁移：现有 `RetrievalUnit.unit_type` 已允许 `table_cells`/`image`，EvidencePointer 已含所需定位字段。
- 搜索结果闭包项为固定版本 EvidencePointer 增加可选 `evidence_pointer_id`；保留现有 `relation_type`，字段新增保持向后兼容。
- 如实现发现 schema 实际不支持上述约束，暂停该处并提出新的契约决策，不通过临时隐式字段绕过。

## 错误与降级

- 表格文本为空、对象未固定版面或 bbox 无效：不建立可引用的 table unit，在索引任务检查点记录跳过数量和原因代码，不记录正文；段落检索继续可用。
- 图像无合格相邻闭包时不显示定位入口。若指针创建后页图读取失败或权限撤回，Reader 按现有 404/错误状态处理；搜索阶段不预判页图读取结果，也不回退到其他版本素材。
- 无论 Embedding 客户端配置为何种供应商，新增 `table_cells` 内容都不得进入其请求；Figure 数据和图像资产不进入模型调用。本地 Demo 继续强制内部模型，Tutor 生成路径排除新增图表单元及闭包。

## 验收

使用程序生成的合成 PDF，包含一张带真实线框与单元格文本的表格、一张嵌入 PNG、可区分的正文段落和固定 bbox。验证：

1. 解析输出 table/figure 的固定页、有效 bbox；figure 仍无伪造的文本描述。
2. 表格建立 `table_cells` 稀疏检索单元，`object_types=["table"]` 按原生单元格中可匹配的完整词项召回；只有表格的 PDF 也能完成索引，该单元不触发 Embedding API，表格区域不会作为重复段落证据。
3. 表格结果拥有版本固定的 EvidencePointer；相邻 figure 只在 approved reading-order、同一版本的闭包中出现并有定位 pointer，不出现 `caption_of` 或语义解释；人为构造的跨版本关系不会产出闭包图表指针。
4. 两种 pointer 的物理页与 bbox 均能在 Reader 正确高亮；无坐标对象不显示图表跳转。
5. 跨课程 IDOR、未发布/撤回版本和正式测评期间的权限规则保持现状；撤权后 pointer/page-image 读取按现有 404/策略拒绝。
6. 注入记录输入的 Embedding 与 Tutor 适配器，验证新增表格文本/图像资产未进入模型请求；已有段落生成不退化。
7. 受影响后端测试、`alembic check`、OpenAPI 漂移检查和前端类型/测试通过；不宣称真实教材、DOCX、生产或学习效果验收。

## 明确不做

- DOCX 固定版面映射和 legacy `.doc` 转换。
- 图像 OCR、视觉检索、图像语义说明、自动 caption 推断或未经审核的 `caption_of` 关系。
- 把图片或表格正文发送给外部服务；引入新的模型供应商或视觉索引。
- 新版 Designer/Publisher、图表资产管理后台或与本证据闭环无关的 UI 重构。
