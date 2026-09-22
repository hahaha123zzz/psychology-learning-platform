# AGENTS.md

本文件是自动化编码代理在本仓库工作的首要项目说明。除非用户另有明确要求，所有面向用户的说明、代码注释和项目文档使用简体中文；代码标识符、API 字段和工具输出保留原文。

## 1. 项目定位与当前状态

本项目是面向《实验心理学》课程的 B/S 智能学习平台，目标是形成“教师发布可信课程资料 → 学生基于教材学习、提问和练习 → 系统保存证据、掌握状态与复习任务 → 教师据此调整教学”的闭环。

截至 2026-09-21，后端已实现执行计划 D1—D40 的主要代码与测试，当前主干最新迁移为 `0010_rag_v3_objects.py`。已有能力包括：

- 平台账号、HttpOnly Cookie 会话、RBAC、课程和成员、审计、幂等与乐观锁。
- 教材上传、MinIO 存储、版本、解析任务、知识对象、教师修正、质量门禁、发布与归档。
- 章节感知分块、pgvector/BM25 混合检索、RRF、权限前置过滤和短期证据票据。
- 课程问答、SSE 回合、证据包、主张校验、AI 教师状态机和 RAG 基线脚本。
- 题库、审核发布、测验、作答评分、出题任务、局部分支会话、确认合并和复习任务。
- 学习证据、掌握状态、分层记忆、模型网关、管理健康检查和隐私删除请求。
- V3 评测数据合同、对象/表示/关系/RetrievalUnit 模型、不可变资产键与 bbox 坐标变换合同。
- OpenAI-compatible 教材约束生成适配器；可通过配置切换单一供应商，未配置时保留确定性测试替身。
- OpenAI-compatible Embedding 适配器、模型版本隔离与失败时 BM25 降级；索引替换在新向量全部成功后提交。
- 发布门禁要求当前 Embedding 版本的候选索引已就绪；教师修正知识对象会立即使旧索引失效，重建后才能发布。
- 向量检索必须应用 `RETRIEVAL_MIN_VECTOR_SIMILARITY` 门槛；最近邻不等于教材证据，低于门槛时须拒答或仅保留 BM25 命中。
- 教师课程学情聚合接口提供参与、测验、掌握、章节、常见错题与复习积压口径，不返回学生私聊或记忆正文。
- 学生测验发现只列出已发布测验；草稿详情返回 404，未到开放时间或已关闭时不下发题目内容。

V2 前端已具备真实登录与同源 API 代理；教师端已接入课程/成员、资料上传、解析、解析问题处理、索引构建、发布、课程聚合学情、题库审核发布、出题任务和测验创建发布；学生端已接入已发布资料、教材检索、SSE 有据问答、服务端学习状态机、测验作答与结果、分支会话确认合并、复习任务、掌握度、记忆详情与隐私删除；管理员页已接入健康与审计查询。未实现的能力不得以静态示例代替。根 `README.md` 和首页中的“基础框架/规划中”文案已落后于后端实际进度；判断完成度时以代码、迁移、测试和最近提交为准，不要把旧文案当作当前状态。

V2 的 D1—D40 本地业务闭环已收口。当前进入 V3 的“真实开放教材评测与选型”阶段：先以可复现的开放教材语料完成解析质量、文本检索、引用定位、拒答和候选模型/融合策略的对照，再决定是否新增解析、视觉索引或模型能力；不得反向以演示效果替代评测结果。首批语料和下载边界见 `docs/v3/2026-09-22-oer-test-corpus.md`，教材二进制只存入 Git 忽略的 `data/oer-textbooks/`。所有来源默认仅作本地解析和检索评测；未经逐本许可确认、供应商不留存/不训练承诺和用户明确授权，禁止把教材正文、图像或表格发送给外部生成或嵌入 API。尤其 OpenStax《Psychology 2e》官方页面明确禁止将教材摄入大语言模型或生成式 AI 服务，故只能用于本地离线对照，不能进入任何外部模型调用路径。用户当前明确不考虑 D41—D50 的生产部署、监控告警、备份恢复、性能/容量验证、教师预验收和小范围试用；这些事项保留为未来范围，不能阻塞当前 V3 本地评测，也不得据此宣称生产就绪或真实班级验收完成。

OpenStax《Psychology 2e》首轮本地 `hybrid-v1 + hash-v1` 基线已完成，结果见 `docs/v3/2026-09-22-openstax-local-hybrid-v1-baseline.md`。页级 Recall@5 为 1.0、NDCG@5 为 0.926186，但教材外问题未拒答；精确对象、视觉、bbox、引用和生成指标尚不可评测。下一优先级是建立 `RetrievalUnit → KnowledgeObject` 稳定映射与绝对拒答门槛，再进入合法语料上的视觉/Embedding/融合策略选型。

教师教材发布工作台与学生教材阅读/AI 学习空间的首轮生图提示词位于 `docs/design-prompts/2026-09-21-teacher-student-ui-image-prompts.md`；用户已于 2026-09-22 提供图稿。能力驱动的前端接入范围与明确不展示项见 `docs/superpowers/plans/2026-09-22-capability-driven-frontend.md`；不得绕过发布、权限、证据和质量门禁。

## 2. 事实来源与冲突处理

按以下优先级判断项目事实：

1. 用户在当前任务中的明确要求。
2. 当前代码、Alembic 迁移、自动化测试和 `contracts/openapi.json`。
3. `docs/执行计划/` 中的当前执行与验收规则。
4. `docs/superpowers/specs/` 和 `docs/心理学课程AI学习平台设计与功能方案.md` 中的产品设计背景。
5. 根 `README.md` 等概览文档。

设计文档描述的是目标和边界，不自动等于已实现能力。若文档、接口和实现不一致，应先报告差异，再按任务范围同步必要的代码、契约和文档。

## 3. 仓库结构

```text
web/          Next.js 16 + React 19 + TypeScript 浏览器端
server/       FastAPI + SQLAlchemy asyncio + Alembic 服务端
contracts/    提交入库的 OpenAPI 快照与跨模块事件契约
infra/        Nginx 等部署配置；目前仍不完整
scripts/      Windows 开发脚本、种子、冒烟、契约导出和 RAG 评测
docs/         产品设计、双主线执行计划、接口与联调手册
.github/      前后端 CI
compose.yaml  PostgreSQL/pgvector、Redis、MinIO 本地依赖
```

后端采用模块化单体。业务入口位于 `server/app/modules/<module>/router.py`，复杂逻辑放入同模块 `service.py`，共享基础设施位于 `server/app/core/`，ORM 模型集中在 `server/app/db/models.py`。所有 HTTP API 默认挂载于 `/api/v1`。

## 4. 技术基线与本地启动

- Windows 11 + PowerShell 为主要本地环境。
- Python 要求 `>=3.11`，CI 使用 Python 3.12。
- Node.js CI 使用 22，包管理器固定为 `pnpm@11.19.0`。
- 本地依赖：PostgreSQL 16 + pgvector、Redis 7.4、MinIO。

首次启动：

```powershell
.\scripts\dev.ps1
```

停止由启动器管理的 API 与 Web：`.\scripts\dev-stop.ps1`。Docker Desktop 必须已启动；停止脚本不会删除或停止 Docker 数据依赖。

访问地址：前端 `http://localhost:3000`，API 文档 `http://localhost:8000/docs`，MinIO 控制台 `http://localhost:9001`。

演示数据由 `scripts/seed_demo.py` 创建：

- 教师：`teacher@demo.edu` / `demo-password-123`
- 学生：`student@demo.edu` / `demo-password-123`

禁止提交 `.env`、密钥、真实学生数据、真实课程资料或运行期数据。

## 5. 常用验证命令

后端测试依赖正在运行的 PostgreSQL、Redis 和 MinIO；测试会创建并迁移 `psychology_learning_test` 数据库。

```powershell
docker compose up -d postgres redis minio

Set-Location server
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
Set-Location ..

server\.venv\Scripts\python.exe scripts/export_openapi.py
git diff --exit-code contracts/openapi.json
```

从仓库根运行 Python 脚本时使用 `server\.venv\Scripts\python.exe`，进入 `server/` 后使用 `.venv\Scripts\python.exe`。完整 G0 冒烟：

```powershell
server\.venv\Scripts\python.exe scripts/g0_smoke.py
```

前端验证：

```powershell
Set-Location web
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

按改动风险选择验证范围，但提交前至少运行受影响模块的测试。涉及迁移、公共模型、权限、响应格式或契约时必须执行完整后端测试、`alembic check` 和 OpenAPI 漂移检查；涉及前端构建链或公共路由时执行全部前端命令。

## 6. 不可破坏的工程约定

### API 与契约

- 成功响应统一为 `{data, meta}`，`meta` 至少包含 `request_id` 和 `server_time`。
- 失败响应统一为 `{error: {code, message, details, retryable}, request_id}`；业务错误使用 `ApiError`，不要临时发明另一套格式。
- `contracts/openapi.json` 由 FastAPI 应用生成，是跨端接口的提交快照，禁止手工编辑。接口变化后运行 `scripts/export_openapi.py` 并提交差异。
- 跨模块事件包含 `event_id`、`event_type`、`event_version`、`occurred_at`、`producer`、`trace_id` 和 `payload`；消费者按 `event_id` 幂等。破坏性变化必须升级事件版本。
- 列表接口使用稳定排序和游标语义；SSE 只发送真实执行事件，重试不得重复写业务结果。

### 身份、权限与隐私

- 身份以服务端 HttpOnly Cookie 会话为准，不能信任前端角色判断。
- 课程资源先鉴权再查询/检索；无权访问课程资源时统一返回 404，避免 IDOR 和资源枚举。
- 普通管理员不因此自动获得全部学生私聊、记忆或教材内容读取权。
- 日志、审计和模型调用记录不得保存密码、Token、Cookie、完整敏感 Prompt 或不必要的学生隐私。
- 危机场景逻辑不能把心理学课程内容一概误判为个人求助；修改相关规则时必须增加语境区分测试。

### 数据、迁移与任务

- ID 默认使用 26 字符 ULID；时间字段使用带时区时间。
- 已合并的 Alembic 历史迁移只读。模型变化必须新增向前迁移，并执行 `upgrade head` 与 `alembic check`。
- 不静默覆盖已发布版本、学生原始作答、评分依据或原始学习证据；修正通过新版本、替代关系或审计记录表达。
- 带 `version` 的资源遵守乐观锁；冲突返回 409 和可操作详情。
- 创建、上传、解析、生成等可重试操作保持幂等。异步任务必须暴露状态、进度、阶段、错误和 `retryable`，且进度不能倒退。
- 权限过滤必须发生在检索和排序之前；撤回或归档后，引用和证据预览需要重新鉴权。

### 业务边界

- AI 生成内容必须区分候选、已审核和已发布；候选题不得自动成为正式题。
- 模型输出不能直接改变学习状态、评分、权限或发布状态，必须经过确定性业务校验。
- 学生答案、题目、评分规则、教材引用均绑定不可变版本。
- 一次错误、自评或临时追问不能直接升级为稳定画像；记忆需保留来源、置信状态、时效与替代关系，合法删除优先于历史保留。
- 证据不足时明确拒答或降级，不得把“检索到内容”表述为“结论已被支持”。

## 7. 当前替代实现与已知缺口

以下实现适合离线开发和确定性测试，但不是生产级外部能力：

- PDF 使用基于 `pypdf` 的 `StubPdfParser`；DOCX 已有 OOXML 结构解析主路径，可提取标题、段落、表格、图片和公式对象，但不伪造页内 bbox，并会产生 `layout_bbox_unavailable` 告警。尚未接入 MinerU、OCR 和可验证的版面恢复。
- Embedding 已支持 OpenAI-compatible 外部服务；尚未配置真实 Key 联调，数据库仍固定为 384 维，供应商模型必须支持 `dimensions=384`，切换模型后必须重建索引。未配置时使用本地确定性哈希 `hash-v1`。
- 问答已具备 OpenAI-compatible 外部生成适配器和教材证据回退；尚未配置真实 Key 做供应商联调。教学状态机和出题仍以本地确定性逻辑为主。
- 异步解析/生成主要由应用进程内任务驱动，尚未形成生产 Worker、可靠队列和跨进程恢复能力。
- `infra/` 只有初步 Nginx 说明，尚缺生产 Compose、HTTPS、监控、备份、恢复和回滚验证。
- 前端只有 `/student`、`/teacher`、`/admin` 工作区骨架，完整业务页面、OpenAPI 客户端和浏览器 E2E 仍待实现。

扩展这些能力时应保留现有适配器边界和确定性测试替身，不要让外部服务调用渗透到业务模块或让单元测试依赖公网。

## 8. 修改工作流与完成标准

开始修改前：

1. 阅读相关 router、service、model、迁移和测试，再阅读对应执行手册；不要仅凭文件名或旧 README 推断行为。
2. 检查 `git status`，保留用户已有改动，不覆盖、不重置、不顺手清理无关文件。
3. 明确改动属于主线 A（课程内容与可信知识）、主线 B（学生学习与智能教学）还是公共契约。

实现时：

1. 先固定权限、状态机、版本和错误语义，再实现正常路径。
2. 同步补充成功、越权、非法状态、重复提交/幂等、并发冲突和失败恢复测试。
3. API 或模型变化同步处理 schema、迁移、OpenAPI、前端消费者和相关文档。
4. 保持模块边界：主线 B 通过服务/契约读取主线 A 的课程、题目和证据，不跨模块直接拼接内部表逻辑。

任务只有在“代码 + 必要迁移 + 契约 + 测试 + 文档 + 可复现验证”一致时才算完成。汇报时必须区分：已编码、测试通过、环境验证通过、真实数据验证通过、生产验证通过；不要用“已完成”掩盖缺少的验证层级。

## 9. 关键参考文档

- `docs/执行计划/00-双主线总执行计划-v2.md`：范围、D1—D50 路线、G0—G5 门槛。
- `docs/执行计划/01-主线A-课程内容与可信知识执行手册.md`：课程、资料、RAG、题库、模型与运维。
- `docs/执行计划/02-主线B-学生学习与智能教学执行手册.md`：学生端、AI 教师、测验、复习、记忆与统计。
- `docs/执行计划/03-接口与数据契约手册.md`：接口、错误码、状态和数据契约。
- `docs/执行计划/04-联调验收与故障排查手册.md`：联调顺序、测试矩阵与排障要求。
- `docs/心理学课程AI学习平台设计与功能方案.md`：面向教学使用者的产品方案。

若新增重大约定、完成新的执行阶段或替换上述本地实现，应在同一变更中更新本文件的状态与限制。
