# AGENTS.md

本文件是自动化编码代理在本仓库工作的首要项目说明。除非用户另有明确要求，所有面向用户的说明、代码注释和项目文档使用简体中文；代码标识符、API 字段和工具输出保留原文。

## 1. 项目定位与当前状态

本项目是面向《实验心理学》课程的 B/S 智能学习平台，目标是形成“教师发布可信课程资料 → 学生基于教材学习、提问和练习 → 系统保存证据、掌握状态与复习任务 → 教师据此调整教学”的闭环。

> **2026-10-05 17:26 +08:00 状态覆盖（优先于下方较早快照）：** 共享迁移 head `0051_bind_chat_sessions_to_course_releases.py`。CourseRelease 草稿现在 pin 每份材料的 MaterialVersion 与 PublicationSnapshot/IndexJob/Embedding/DomainRelease；只在显式重选材料时刷新。新隔离库全量后端 **364 passed、2 warnings**，0051 `alembic check` 无差异，全仓 Ruff 通过；OpenAPI 156 paths/SHA `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`；Web Node 56/56、TypeScript、production build 24/24 通过，ESLint 0 error/2 warnings。R3-B 历史 superseded snapshot 正向 Claim 与 Branch child pin 仍待其按共享状态交付/验证。用户可查看的隔离演示 API 8000 与 Web 3000 已通：新 DB `psychology_learning_v1_preview_20261005` (0051)、Redis DB2、MinIO bucket `psych-preview-root-20261005`，健康/就绪、页面与代理均 200，合成教师登录可读取 1 门课程；未迁移 `.env` 中的旧 `psychology_learning`（只读查为 0038）。Docker CLI 管理管道仍权限拒绝，不据 TCP 推断容器状态。真实教材/机构政策/学生答案授权及生产、真实班级验收仍未完成，R3/V1 不作整体完成结论。

以下段落是 R3 之前的历史快照，不可作为当前迁移、OpenAPI、全量测试或资源状态依据。R2 集成全量隔离回归 **294 passed** 与 P2-08 专项 **43 passed** 为历史结果。V1 功能与验收边界如下，最新实施状态以本文件顶部覆盖和 `docs/v1/implementation-status.md`、`acceptance-report.md` 为准。主预览数据库 `psychology_learning_privacy_target` 仍严禁迁移或调用依赖新 schema 的管理/隐私端点。已有能力包括：

- 平台账号、HttpOnly Cookie 会话、RBAC、课程和成员、审计、幂等与乐观锁。
- 教材上传、MinIO 存储、版本、解析任务、知识对象、教师修正、质量门禁、发布与归档。
- 章节感知分块、pgvector/BM25 混合检索、RRF、权限前置过滤和短期证据票据。
- 课程问答、SSE 回合、证据包、主张校验、AI 教师状态机和 RAG 基线脚本。
- 题库、审核发布、测验、作答评分、出题任务、局部分支会话、确认合并和复习任务。
- 学习证据、掌握状态、分层记忆、模型网关、管理健康检查和隐私删除请求。
- 隐私删除具备持久 queued/running/failed/completed 工作单、同事务个人数据清除、账号即时停用、调用方预生成回执编号/随机状态凭证、凭证限时状态核验与可重派发；凭证只存哈希，保留成绩/审计/任课历史仍需机构政策，生产备份擦除不在本地验收范围。
- V3 评测数据合同、对象/表示/关系/RetrievalUnit 模型、不可变资产键与 bbox 坐标变换合同；新建文本 Chunk 已稳定关联来源对象与 RetrievalUnit。
- OpenAI-compatible 教材约束生成适配器；可通过配置切换单一供应商，未配置时保留确定性测试替身。
- OpenAI-compatible Embedding 适配器、模型版本隔离与失败时 BM25 降级；索引替换在新向量全部成功后提交。
- 发布门禁要求当前 Embedding 版本的候选索引已就绪；教师修正知识对象会立即使旧索引失效，重建后才能发布。
- 向量检索必须应用 `RETRIEVAL_MIN_VECTOR_SIMILARITY` 门槛；最近邻不等于教材证据，低于门槛时须拒答或仅保留 BM25 命中。
- 教师课程学情聚合接口提供参与、测验、掌握、章节、常见错题与复习积压口径，不返回学生私聊或记忆正文。
- 学生测验发现只列出已发布测验；草稿详情返回 404，未到开放时间或已关闭时不下发题目内容。
- 历史教材发布工作流、分片上传、解析、索引和质量审核能力仍在服务端代码中，但普通教师直接教材编写/上传现已由 `MATERIAL_LEGACY_AUTHORING_API_ENABLED=false` 默认关闭；直传、分片启动/上传/完成、解析、索引、修正、发布和归档写接口返回稳定 410。仅上传会话创建者可取消自己残留的未完成会话。隔离工程/测试可显式打开开关；这不代表课程内容管理员的新建构建工作台已完成。教师教材页现为只读状态提示。
- 解析/索引任务已接入持久任务派发（V3.2）：`TASK_BACKEND` 可切换 `celery`（默认）与 `in_process`（测试固定）；Celery Worker 由 `scripts/dev.ps1` 受管启动；`jobs` 记录心跳、尝试次数、检查点与执行后端；`app/core/job_recovery.py` + `scripts/requeue_stale_jobs.py` 提供陈旧任务扫描与安全重派发。派发异常且任务仍停留在本次恢复版本的 queued 状态时，会持久记录为脱敏的 `failed/dispatch_failed/retryable=true`，供受控重试；broker 已接收但确认响应丢失等模糊结果仍需单独做幂等/Outbox 故障验证。Celery 任务运行在 `app/core/task_loop.py` 的持久事件循环上（修复了每任务 `asyncio.run` 关闭循环导致连接池跨循环复用崩溃的问题）。
- 每次新发布会创建不可变 `PublicationSnapshot`，绑定教材版本、最近成功解析任务、成功索引任务与 Embedding 版本；历史已发布资料在没有快照时仍保持可用。
- V1 新增课程/班级运行 Scope、事件资格化、可恢复学习任务、案例推理、干预、TeacherObservation、Mini Lab 与 TeachingAsset 版本；详细状态和证据见 `docs/v1/implementation-status.md`。
- 管理员角色授予/撤销支持同机构 Scope、理由、幂等和审计；受控任务恢复仅覆盖允许重试的教材解析/索引失败任务。新课程/班级/成员治理接口采用同机构过滤、版本冲突、幂等/理由、审计和 Outbox；没有把平台管理员提升为隐式课程教师。R2 Admin 工作台的五入口与首批隔离浏览器治理操作已通过；完整 Designer/Publisher、Release assignment 与策略仍未完成，撤权后目标账号 `/me` 未验。
- 当前学生独立正式测评页支持单选、多选、判断、简答/论述、刷新恢复和逐题保存；SSE 只有收到服务端 `done/saved=true` 才视为完成，同 `client_turn_id` 对已提交回合可安全回放。R2-C 已在隔离环境验证双标签、离线保存失败、版本冲突、截止尾端、真实 TCP SSE 中断、Celery 隐私删除 Worker 回滚重投和独立 Redis 恢复；这些是本地工程故障证据，不等于生产恢复验收。

V2/V1 前端已具备真实登录、同源 API 代理和学生/教师/管理员/课程设计工作区；学生正式测评单独使用 Assessment Shell，不挂普通学习导航。普通教师教材页现为只读，后端旧写接口默认关闭；Admin 五区治理路径已接入真实 API，并由 R2-B 进行隔离浏览器验收。前端以 `/me` 的有效工作区限制导航、登录落点和路由访问；服务端仍需对每个动作重做 Scope 校验。Next API rewrite 可配置目标，Next 输出目录可用白名单配置隔离；独立构建应使用物理源码快照，避免并行 Next 改写共享 `next-env.d.ts` 或 Turbopack 丢失 junction 路由。未实现的能力不得以静态示例代替。根 `README.md` 和首页中的“基础框架/规划中”文案已落后于当前进度；判断完成度时以代码、迁移、测试和验收报告为准，不要把旧文案当作当前状态。

V2 的 D1—D40 本地业务闭环与既有 V3 离线教材检索评测结果仍可复用；当前执行用户已批准的 V1 迁移计划，以 `docs/v1/implementation-status.md` 和 `docs/v1/acceptance-report.md` 记录每项实现/验收。课程教材默认仅作本地解析和检索评测；未经逐本许可确认、供应商不留存/不训练承诺和用户明确授权，禁止把教材正文、图像或表格发送给外部生成或嵌入 API。尤其 OpenStax《Psychology 2e》官方页面明确禁止将教材摄入大语言模型或生成式 AI 服务，故只能用于本地离线对照，不能进入任何外部模型调用路径。用户当前明确不考虑生产部署、监控告警、备份恢复、性能/容量验证、教师预验收、小范围试用和学习效果验证；这些事项保留为未来范围，不得据本地验证宣称生产就绪、真实班级或学习效果验收完成。

OpenStax《Psychology 2e》首轮本地 `hybrid-v1 + hash-v1` 基线已完成，结果见 `docs/v3/2026-09-22-openstax-local-hybrid-v1-baseline.md`。页级 Recall@5 为 1.0、NDCG@5 为 0.926186，但教材外问题未拒答；精确对象、视觉、bbox、引用和生成指标尚不可评测。该历史基线暴露的 `RetrievalUnit → KnowledgeObject` 稳定映射和绝对拒答门槛问题已在后续 V2 处理。

`hybrid-v2 + hash-v1` 已完成上述两项最小改造并在同一 OpenStax 本地语料复测，结果见 `docs/v3/2026-09-23-openstax-local-hybrid-v2-baseline.md`：4160 个 Chunk、RetrievalUnit 与来源对象已一一关联；对象 Recall@5 为 0.875、NDCG@5 为 0.718752，教材外问题拒答准确率为 1.0。`hash-v1` 仅要求同段至少两个有效关键词锚点，不影响未来真实外部 Embedding 的语义通道。图题仍只命中图注段落，bbox、视觉、引用与生成指标仍不可评测；下一优先级为对象关系/相邻对象 Evidence Closure 和可验证版面解析。

检索接口现有确定性 Query Analyzer 与自适应截断：问题类型仅用于声明通道先验和候选预算；实际结果始终受调用方 `top_k` 限制，并只在 RRF 分数出现明确断层时提前停止。该策略不构成视觉检索，也不以 RRF 分数替代教材证据或生成可信度。

`/knowledge/search` 的章节和对象类型过滤已在候选查询、RRF 排序之前生效：章节范围使用稳定的章节对象 ID；当前只对 `paragraph-child` 建索引，因此请求图片、表格或公式不会伪装为段落命中，而是诚实返回空结果，直至相应对象表示真正建成。

`hybrid-v3` 已把 Query Analyzer 的文本通道先验接入 Weighted RRF：`sparse` 对应 BM25、`dense` 对应向量通道，并只在已实现文本通道中归一化。视觉先验会产生明确的文本降级提示，尚不代表视觉索引或多模态检索已完成。`hybrid-v4` 进一步明确本地 `hash-v1` 只是确定性关键词基线：禁用其不具语义含义的伪向量通道，改用 BM25 加至少两个有效关键词锚点；真实外部 Embedding 仍走相似度门槛和 Weighted RRF。

OpenStax《Psychology 2e》的本地自动化 `hybrid-v3 + hash-v1` 基线曾因伪向量干扰把页级 Recall@5/NDCG@5 降至 0.6，逐阶段排序追踪已证实准实验和图题目标页原本在 BM25 前列。修复后的 `hybrid-v4 + hash-v1`（不调用外部 API）页级 Recall@5 为 1.0、Page NDCG@5 为 0.826186、教材外拒答准确率为 1.0；精确对象 Recall@5 仍为 0.625，首项 bbox IoU 为 0.480661。11,309 个文本对象均有 bbox，两个独立渲染人工金标对对应段落的原始 bbox IoU 为 0.960721。图题仍未形成图片对象，已从精确对象指标排除；因此不能宣称 V3 的对象级、视觉或精确引用效果完成。详细运行与诊断见 `docs/v3/2026-09-24-openstax-local-hybrid-v4-baseline.md`。

本地 PyMuPDF 段落 bbox 验证已完成，见 `docs/v3/2026-09-23-local-pdf-layout-bbox.md`：同一 OpenStax PDF 的 11,293 个原生文本段落均取得 PDF 用户空间坐标。该能力只覆盖原生文本段落，仍不产生图片、表格、公式对象或视觉检索结果；重解析后必须重建索引并重新评测。

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

后端测试依赖正在运行的 PostgreSQL、Redis 和 MinIO；测试会创建并迁移 `psychology_learning_test` 数据库。测试 Redis 通过 `PSYCHOLOGY_TEST_REDIS_URL` 配置，默认使用 DB15；夹具拒绝 Redis DB0（本地预览）和 DB1（Celery broker/result），禁止测试清理共享预览或任务队列状态。并行测试应分别指定独立 PostgreSQL 与 Redis DB。

```powershell
docker compose up -d postgres redis minio

Set-Location server
$env:PSYCHOLOGY_TEST_REDIS_URL='redis://127.0.0.1:6379/15'
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
- 异步解析/索引已有本地 Celery Worker（受管脚本启动）与陈旧任务重派发；跨进程崩溃恢复只覆盖心跳超时场景，尚无生产级监控告警、队列积压观测与多 Worker 扩缩容验证。
- `infra/` 只有初步 Nginx 说明，尚缺生产 Compose、HTTPS、监控、备份、恢复和回滚验证。
- 前端已具有学生/教师/管理员/课程设计工作区、多项真实 API 投影与命令、Assessment Shell、Read-only 教材页及部分真实浏览器/Playwright 验收；仍缺完整 Designer/Publisher 工作流、全面 OpenAPI 客户端生成和 P0—P10 全需求浏览器 E2E。具体范围见 `docs/v1/remaining-scope-audit-2026-10-04.md`。

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
