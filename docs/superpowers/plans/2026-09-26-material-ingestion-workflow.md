# 教材上传、解析、审核与发布 V3.1 执行计划

> 日期：2026-09-26  
> 依据：`教材上传解析审核发布优化方案.md` 与当前代码、迁移、测试  
> 本期目标：在不引入 Celery、Uppy、OCR/Docling 的前提下，让现有教材流程可信、可观察、可审核、可追溯。

## 1. 范围与实施原则

本期实施 V3.1，覆盖：

- 教材工作流状态聚合与明确的下一步操作。
- 解析、索引任务的持续进度、阶段、失败原因和可重试信息。
- 教师选择性审核与发布阻塞原因。
- `READY_TO_PUBLISH` 业务状态。
- `PublicationSnapshot` 与原子发布记录。
- 教师端五阶段流程条、单一主操作、后台任务区和上传进度。

本期不实施：

- Uppy、MinIO Multipart、断点续传。
- Celery/独立 Worker、页级 Checkpoint、Heartbeat 自动接管。
- OCR、Docling、MinerU、视觉检索。

现有 `Job` 已承担 `IngestionJob` 的核心职责，且包含 `kind/status/progress/stage/error/retryable`；现有 `ParseReviewIssue` 已承担 `QualityIssue`。本期复用并补全这些模型，不新增语义重复的表。

## 2. 目标状态机

工作流对外统一为：

```text
UPLOADING
→ UPLOADED
→ PARSING
→ REVIEW_REQUIRED / INDEX_REQUIRED
→ INDEXING
→ READY_TO_PUBLISH
→ PUBLISHED

任一后台处理步骤可进入 FAILED，并暴露 retryable、error 和建议操作。
```

该状态由服务端根据以下事实计算：

- `MaterialVersion.status`
- `quality_gate_status`
- 未关闭的解析审核问题数量与严重度
- 当前 Embedding 版本的有效索引数量
- 最新解析/索引任务状态
- 当前版本是否已有生效的发布快照

不在 `MaterialVersion` 中冗余保存 `READY_TO_PUBLISH`，防止任务、审核和索引变化后出现双状态漂移。

## 3. 后端与数据层

### 3.1 PublicationSnapshot

新增 Alembic 迁移与 ORM 模型，字段包括：

- `id`
- `material_id`
- `material_version_id`
- `parse_job_id`
- `index_job_id`
- `embedding_version`
- `published_by`
- `published_at`
- `superseded_at`

约束：

- 同一教材同时只能有一个未被替代的当前快照。
- 快照只引用已完成的解析版本和成功索引任务。
- 历史快照不删除，以支持历史引用和学习证据追溯。

发布事务内：锁定教材、重新执行全部门禁、将旧快照标记为 superseded、创建新快照、切换 `current_version_id` 与 `visibility`，最后一次性提交。

### 3.2 工作流聚合服务

新增独立工作流聚合函数，统一生成：

- `state`
- 五个步骤的 `status/progress/message`
- 当前任务及最近任务。
- 阻塞原因列表。
- `allowed_actions`。
- 审核问题统计。
- 当前发布快照。

所有按钮规则由服务端事实驱动，前端不自行猜测门禁。

### 3.3 API

新增：

- `GET /material-versions/{version_id}/workflow`
  - 返回单版本完整工作流视图。
- `GET /courses/{course_id}/material-jobs`
  - 返回课程下解析/索引任务，供后台任务区恢复展示。

调整：

- 教师资料列表补充 `workflow_state` 与 `published_snapshot_id`，用于快速渲染。
- 发布接口返回 `publication_snapshot_id`。
- 任务输出继续使用现有 `progress/stage/error/retryable`，补充稳定的用户可读阶段映射由前端完成。

### 3.4 错误与重试

- 解析和索引失败保留具体 `error`，不得只返回“任务失败”。
- 前端显示 `ApiError.code/details/retryable`。
- 可重试任务使用现有触发接口重新创建新 Job；不可覆盖历史失败 Job。
- 阻塞性解析问题仍必须重新解析，不能被人工忽略。

## 4. 前端工作台

### 4.1 页面结构

教师教材页调整为：

```text
课程侧栏
└─ 主区
   ├─ 教材发布五阶段流程条
   ├─ 上传卡片
   ├─ 教材版本列表
   ├─ 当前版本状态与唯一主操作
   ├─ 选择性审核问题
   └─ 后台任务区
```

### 4.2 上传体验

- 使用 `XMLHttpRequest` 上传，以获得真实客户端上传百分比。
- 显示文件名、大小、百分比和进度条。
- 上传期间注册 `beforeunload` 提示，明确当前版本不支持断点续传。
- 上传失败展示错误码、原因、详情和重试建议。
- 不实现虚假的暂停/恢复按钮。

### 4.3 工作流与按钮规则

- 未上传：`上传教材`
- 已上传/解析失败：`开始解析` 或 `重试解析`
- 解析中：无可重复提交主按钮，显示进度
- 待审核：`处理审核问题`
- 待索引：`构建候选索引`
- 索引中：显示进度
- 可发布：`发布给学生`
- 已发布：显示成功状态和快照信息

每个状态只突出一个主操作。不能执行的操作不伪装为可用按钮；阻塞原因直接展示。

### 4.4 后台任务区

- 按课程读取解析/索引任务。
- queued/running 任务持续轮询直到终态，不再限定 12 秒。
- 展示任务类型、教材名称、阶段、百分比、失败原因和重试性。
- 页面刷新后从后端恢复，不依赖仅存在于组件内存的状态。

## 5. 测试与验收

### 5.1 后端测试

- 工作流状态覆盖：uploaded、parsing、review_required、index_required、indexing、ready_to_publish、published、failed。
- 学生无权读取教师工作流与后台任务。
- 课程隔离与 404 防枚举。
- 发布快照创建、旧快照替代与当前版本原子切换。
- 未解析、阻塞问题、索引缺失、归档资料均不能创建快照。
- 重复发布同一版本保持幂等语义或返回明确当前状态。
- Job 列表仅返回材料解析/索引任务，不泄漏其他任务负载。

### 5.2 前端测试

- 五阶段状态映射与唯一主按钮。
- 任务失败原因和 `retryable` 展示。
- 上传进度与离页提示。
- active Job 持续轮询并在完成后刷新资料和工作流。
- 发布前后文案及学生可见提示。

### 5.3 验证命令

```powershell
Set-Location server
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
Set-Location ..

server\.venv\Scripts\python.exe scripts\export_openapi.py
git diff --exit-code contracts/openapi.json

Set-Location web
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

## 6. 实施顺序

1. 新增发布快照模型与迁移。
2. 实现工作流聚合服务和课程任务查询。
3. 改造发布事务并补充 API 契约。
4. 补齐后端状态、权限、原子发布测试。
5. 抽取前端工作流类型与上传 API。
6. 重构教师教材工作台与后台任务区。
7. 补齐前端契约测试和交互测试。
8. 更新 OpenAPI、项目状态文档与 `AGENTS.md`。
9. 执行完整验证，记录尚未实现的 V3.2/V3.3 边界。

## 7. 完成标准

- 教师能从一个页面理解教材当前阶段、进度、失败原因与唯一下一步操作。
- 刷新或切回教材页后可恢复查看解析/索引任务状态。
- 只有解析、审核和当前索引全部通过时，服务端才返回 `READY_TO_PUBLISH`。
- 每次成功发布均产生不可变快照，学生只读取当前生效版本。
- 前端不展示断点续传、OCR、视觉检索等尚未实现能力。
- 相关后端、前端、迁移、OpenAPI 和文档验证全部通过。
