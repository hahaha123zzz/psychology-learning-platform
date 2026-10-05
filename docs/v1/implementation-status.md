# V1 实施状态记录

更新时间：2026-10-05 17:26（R3 共享发布固定、全量后端/前端验收、隔离预览启动）

> **2026-10-05 17:26 最新状态：** migration head 0051。CourseRelease manifest 固定材料版本和有序 PublicationSnapshot/IndexJob/Embedding/Domain 快照，元数据编辑不漂移、显式重选刷新。root final 专库全量后端 **364 passed、2 warnings**；Alembic check/全仓 Ruff 通过；OpenAPI 156 paths，SHA `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`；前端 Node 56/56、typecheck、独立 production build 24/24 通过，lint 0 errors/2 warnings。另有隔离演示 API/Web 于 8000/3000 可访问，详情见状态文件 17:26 节。Tutor 历史 superseded snapshot 正向 Claim 与 Branch child assignment/release 继承仍待 R3-B 交付；真实教材/机构政策和生产验证不伪称通过。

> **2026-10-05 离散数学输入补记：** `TEXTBOOK/` 10 个 OLE `.doc` SHA-256 与来源台账一致；逐个本地格式识别成功，但解析全部因 `parser_unavailable` 阻断。本轮隔离材料/解析/编译/检索 fixture 回归 **51 passed、2 warnings**；没有把这记作离散数学教材导入或命中。原件未转换/上传；需本地 DOCX/PDF 输入或可用本地 renderer。详见 [`离散数学本地测试教材导入核验`](discrete-math-local-import-2026-10-05.md)。

本文只记录已经落地的代码和可复现验证，不把设计目标或未运行的数据库测试写成完成事实。

## R2 集成复核（2026-10-04）

- 当前工作树迁移为 `0047_evidence_pointer_multi_page_anchors.py`，`alembic heads` 为 `0047 (head)`；全新隔离库 `psychology_learning_v1_r2_root_full_20261004b` 完成 Alembic upgrade/check。全量后端 **294 passed**、2 条 FastAPI/Starlette/httpx 弃用警告；全仓 Ruff 通过。此前 `0045` 的 275 passed 是历史基线，不再代表当前集成树。
- `contracts/openapi.json` 由导出脚本重复生成保持稳定：**133 paths**，SHA-256 `615D6C248AC69A5780262088C6B0C8BBE466C88FAA916D3A06CE7ABF45CCF9AE`。运行预览 Web/API 健康检查仍 200；API 已热重载为 133 paths，但演示数据库 `psychology_learning_privacy_target` 仍为 0044，未执行升级或调用依赖新 schema 的端点。
- P2-08 普通教师历史教材作者入口默认关闭：`.env.example` 与配置默认 `MATERIAL_LEGACY_AUTHORING_API_ENABLED=false`。上传、分片签名/记录/完成、解析、索引、对象修订、发布、归档写请求先校验课程 Scope，越权保持 404，有权限教师得到 410；只允许原上传会话创建者取消其未完成会话。当前教师教材页与未挂载的旧 `TeacherWorkspace` 均只读；新隔离库上传/资料/任务/发布和门禁专项 **43 passed**。Course Content Admin 新构建/审校工作台尚未实现。
- R2-A 交付：无页码 DOCX 对象保持 `physical_page=null`；编译 manifest、失败/LKG、保守对象映射和多锚点 Reader 已编码。合成 PDF 真实 API/浏览器验收过页切换、bbox、高亮、键盘缩放/旋转；DOCX 仅显示文字降级快照。当前环境没有 Word/LibreOffice 等可靠 `.doc` renderer，`TEXTBOOK/` 10 个 OLE DOC 未读取正文、未转换、未索引、未发外部服务，也没有真实教材固定页/人工金标结论。
- R2-B 交付：Admin 五入口连接真实 API；隔离浏览器读概览、IAM、课程班级成员、任务、审计，并实际完成角色授予/撤销、班级和两类成员治理、任课分配/结束，服务端返回 201/200、冲突/版本回执及审计记录。撤权后活动授权列表不再显示目标；目标账号 `/me` 因没有已知口令未验证。其 E2E 库发现来源未完全归因的旧授权/班级和 18:12—18:16 并发审计写入，均保留；列表绝对总数不作验收证据。
- R2-C 交付：独立浏览器验证测评双标签、离线保存失败/恢复、版本冲突、刷新恢复与截止；真实 TCP SSE 在首个 delta 与保存后 `done` 前分别断开并同 ID 重试，无重复业务写入；真实 Celery Worker 删除事务中断/Redis late-ack 重投完成幂等恢复，独立 Redis 不可用时请求返回可重试失败。只证明隔离工程故障切片，不代表生产级可用性。
- Next 代理支持独立 API origin 与白名单 distDir；`prepare-r2-web-runtime.ps1 -Snapshot` 创建物理源码副本并隔离 Next 写入。最终快照 `web/.r2-runtime/r2-root-final-b` 的 Next 16.3.5 production build 成功；全量 Node **41/41**、TypeScript 通过、ESLint **0 errors / 3 个既有 hook warnings**。ESLint 已忽略隔离运行副本和 `.next-r2-*` 输出，不再扫描生成物。所有 R2 自启 Web/API 已按所有权停下；预览 3000/8000/MinIO 不变，R2-C 独立 Redis 6381 保留。
- 来源台账已更正并复核 `TEXTBOOK/` 10 个 `.doc` 的文件名、大小、SHA-256 **10/10 匹配**。第 10 本此前只是在台账中误录了一个 hash 字符段，源文件没有变化。

R2 并不等于 V1 全计划完成；P0—P10 其余缺口、外部输入和验收边界见 [`remaining-scope-audit-2026-10-04.md`](remaining-scope-audit-2026-10-04.md) 与最新 [`acceptance-report.md`](acceptance-report.md)。

## 已落地

### 设计交付包

- `README.md`、`api-contract-catalog.md`、`state-machine-catalog.md`、`acceptance-matrix.md` 和 `visual/page-specs.md` 已补齐，形成从产品语义到 API、状态、页面和验收的闭环。
- `acceptance-report.md` 已记录 L1—L6 分层结论、已验证闭环、真实内容/生产边界和复现命令。
- 11 组代表页面均明确了桌面/平板/手机布局，以及 loading、empty、error、conflict/recovery 状态；页面规格不产生静态业务数据。

### 来源驱动的第一批实现

- 新增 `LearningBlock` 白名单协议和前端安全降级渲染器；现有学习会话兼容旧 `tutor_message`，同时返回 `TutorExplanation`、`Transition` 或 `TaskCompletion`。
- 该批次只借鉴 OpenTutor 的 block workspace 结构，没有复制外部仓库代码；来源、许可证和复用边界登记在 `source-ledger.md`。
- 后端新增 2 个不依赖数据库的单元测试，验证 Block schema、白名单类型和“活动完成不等于掌握”。
- 按 jsPsych 官方运行时接入 `MiniLabRuntime`：固定 Intro → Predict → Run → Inspect → Explain → Summary Timeline，TrialData 与学习证据分轨，结果只生成 `mini-lab.v1` 候选记录。
- 新增 Mini Lab 服务端会话与结果合同（Alembic `0029`）：白名单 Catalog、不可变 definition snapshot、乐观锁版本、六阶段顺序/响应范围校验、DerivedMeasure 和 `lab_trial_completed` 待资格化事件；学生练习页已接入真实 Catalog、会话创建和结果回流。
- Qualification 现在只从服务端已完成 MiniLabSession 生成 `transfer`/独立 Evidence，Explanation 或 Transfer 未完成时拒绝资格化；反应时仅保留为实验数据摘要，不直接作为能力结论。
- 新增 `TeachingAssetVersion` 与 Alembic `0030`：资产模板、动作白名单、Evidence refs、文本 fallback 和 CourseRelease 绑定均由服务端校验；只有绑定已发布 Release 的资产可由学生读取，未知/不安全内容在前端降级为文本。
- Course Designer 新增 TeachingAsset 编辑入口与真实 API 客户端；可创建草稿、查看版本并绑定当前课程已发布 Release，不用静态资产冒充已发布内容。
- 已固定 `jspsych@8.3.0` 与 `@jspsych/plugin-html-button-response@2.1.0`，版本和复用边界登记在 `source-ledger.md`。

### P0 规格与契约

- `requirements-traceability.md`：需求到领域、页面、接口和测试的追踪矩阵。
- `backend-domain-spec.md`：身份、课程、教材、证据、学习记录和教学运行时的领域边界。
- `api-state-contract-spec.md`：响应格式、权限 Scope、状态机、幂等、SSE 和 Projection 约束。
- `component-spec.md`：按钮、Drawer、Evidence、Learning Block、Assessment/Lab Shell 的组件契约。
- `migration-plan.md`：旧模型映射、兼容窗口、Feature Flag 和数据风险处理。
- `visual/README.md`：视觉稿和代表页面验收入口。

### P1-01/P1-05/P1-06 第一切片

- 新增 `role_assignments` 表、模型和 Alembic `0015` 迁移。
- `GET /me` 读取有效的平台级 `RoleAssignment`，可返回 `course_designer`、`course_publisher` 等显式工作区角色；撤销后即时消失。
- `GET /me` 现在同时返回 `capabilities` 投影（学习、教学、设计、发布、Admin 审计）；该投影只用于导航和能力提示，所有实际动作仍由服务端课程 Scope 再校验。
- 课程列表、课程详情、课程角色、教材、知识检索、测验读取和任务状态均不再因 `is_platform_admin` 自动穿透课程 Scope。
- 前端新增 V1 Design Tokens、Button、ContextDrawer、课程设计工作区路由和角色守卫；未接后端能力的页面显示真实空状态，不伪造业务数据。

### P1-03 Outbox 第一切片

- 新增 `outbox_events`、`outbox_consumer_receipts` 及 Alembic `0016` 迁移。
- `app/core/outbox.py` 提供事务内追加、锁定待投递、成功/失败标记和消费者幂等记账；课程创建已在同一事务写入 `course.created`。
- 新增 `outbox.publish_pending` Celery Worker：以 Redis Stream 为内部投递边界，逐条记录失败并可重试，成功后才写入 `published_at`；投递字段包含事件版本、追踪号和完整 payload。
- 当前只完成持久化和确定性测试替身，尚未接入生产消息代理或监控告警。

### P1-02 Class/TeacherAssignment 第一切片

- 新增 `course_classes`、`teacher_assignments` 及 Alembic `0017` 迁移。
- 新增课程班级创建/列表、显式教师任课分配/列表接口；教师必须先是课程成员，学生和无权账号不能创建或分配。
- 班级创建与任课分配同时写入审计和 Outbox 事件，重复编码/重复分配返回稳定 409。

### P1-04/P1-07 第一切片

- 新增 `course_releases` 及 Alembic `0018`；课程 Release 使用不可变版本号和 manifest，发布会弃用旧版本并校验教材属于当前课程且已发布。
- 新增 `web/lib/course-api.ts` 类型化班级、任课和 Release 客户端；新增 `web/lib/sse.ts`，统一 SSE 多行 data、CRLF、取消和坏 JSON 降级处理。
- CourseRelease 已提供草稿创建、课程资料归属校验、发布、旧版本弃用和重复发布回放；Domain/Pedagogy/Assessment Pack 编辑器已通过真实草稿接口保存。
- Domain Pack 已加入服务端图校验：跨类型稳定 key 唯一；Experiment/Misconception 的知识点引用必须存在；当前只允许知识点之间的 `prerequisite` 有向无环 Relation；EvidenceBinding 必须引用已声明对象。发布还要求每条事实有证据绑定，且教材 ID/版本匹配当前 Release 的已发布快照；未知 Pack 字段返回可定位错误。
- Course Designer 的四个页面均接入真实课程和草稿状态；无草稿时明确提示先创建版本，不伪造未实现资产。
- Teacher 成员页面已接入班级创建、课程教师选择和显式任课分配；学生成员不会获得班级管理入口。

### P3 学习证据原始事件第一切片

- 新增不可变 `learning_events` 表和 Alembic `0019`；事件包含课程、来源、客户端幂等键、发生时间、原始 payload 与资格化状态。
- 新增 `POST /learning-events` 与 `GET /me/learning-events`；服务端先校验课程 Scope，重复幂等键仅在内容完全一致时回放，冲突返回 409。
- 客户端事件始终以 `pending` 写入，不直接改变 `LearningEvidence`、`MasteryState`、评分或记忆；这保留了后续资格化、去重、撤销和重算边界。
- 前端新增 `web/lib/learning-events.ts` 类型化客户端；学生学习会话开始和服务端回合完成时已追加 `task_viewed`/`tutor_responded` 原始事件，埋点失败不阻塞教学状态机。

### P3 Qualification 与测评证据投影

- 新增 `learning_qualifications` 表和 Alembic `0020`，按事件唯一约束保存资格化状态、理由、算法版本和生成的证据 ID 集合。
- 正式测评提交不再直接信任客户端答案字段写入掌握度：服务端先完成 `AttemptAnswer` 判分，再追加 `answer_submitted` 原始事件，由 Qualification 服务校验 Attempt、Assessment、QuestionVersion 和服务端判分结果后投影 `LearningEvidence`。
- 资格化结果可重放且同一事件不会重复生成证据；不具备权威作答引用的事件会被拒绝，不改变掌握度或记忆。
- 新增持久 Worker 批处理函数、Celery 任务 `learning_events.qualify_pending` 及本地命令 `scripts/qualify_learning_events.py`；多 Worker 通过 `FOR UPDATE SKIP LOCKED` 领取事件，失败事件不会被静默标记为合格。

### P6 教师干预生命周期第一切片

- 新增 `interventions` 表和 Alembic `0021`；干预保存 `target_snapshot`、执行计划、乐观锁版本和独立的效果 `outcome`。
- 新增创建、列表、排程、开始、完成、效果评估接口；只有课程教师可变更，助教只读，班级必须属于当前课程。
- 完成干预不会直接改变 `LearningEvidence`、`MasteryState` 或评分；只有后续资格化证据才可进入学习状态聚合。
- 学情页已接入真实干预面板和类型化客户端，页面不生成静态指标。
- 新增 `intervention_runs`（迁移 `0022`）：教师可将已排程/进行中的干预派发给课程学生，学生可查看、开始和完成自己的执行实例；执行状态和学生反思与干预总体完成/效果评估分离，重复派发按学生幂等。

### P1-04 CourseRelease Pack 编辑第一切片

- CourseRelease manifest 现在显式携带 `domain_pack`、`pedagogy_pack`、`assessment_pack`，草稿支持带版本的 PATCH 编辑。
- 发布后仍保持不可变；跨课程教材校验、乐观锁冲突和 Outbox/audit 记录均覆盖，Course Designer 发布页已可录入三类 Pack JSON。

### P2-04 / P9-01 Domain Pack 确定性图校验

- Domain Pack 创建、编辑和发布前均执行确定性校验；发布阶段会重验历史草稿，拒绝重复/非规范对象 key、悬空关系端点、自引用、重复边、错误端点类型和先修关系环。
- 当前只允许契约已定义的 `prerequisite` 关系类型；实验与误区可引用已声明的 KnowledgePoint，EvidenceBinding 必须引用已声明对象及已选教材版本中的来源对象。
- 教材事实在发布前必须绑定有效 Evidence；未知 Pack 字段和未审核 AI 候选字段不会被静默执行或发布。
- Course Designer 编辑器展示结构问题并保留本地内容；乐观锁冲突时提供显式重新载入服务端草稿操作。
- ExperimentSchema 已按总体设计文档补齐研究问题、假设、IV/DV、操作化、控制/混淆变量、设计、流程、预测、结果模式、解释、限制和 `textbook_evidence` 字段；`textbook_evidence` 是 EvidenceBinding 稳定 key 数组，与 `evidence_binding_keys` 兼容等价，同时填写必须一致。对文本类型/长度、控制与混淆列表的形状和大小实施服务端验证，并在 Designer 中明确提示教材未提供时应留空。MisconceptionDefinition 扩展模型、EvidenceBinding 坐标/引用精度策略尚待补齐；未定义的 Relation 类型继续 fail-closed。

### P2-06 EvidencePointer 持久恢复第一切片

- 新增 `EvidencePointer` 与 Alembic `0040`：检索命中时冻结课程/教材/版本、来源对象、RetrievalUnit、页码/阅读顺序、原文摘录及 SHA-256、bbox 和坐标空间；短期 `EvidenceTicket` 单独保留并指向该快照。Alembic `0041` 将来源对象 ID 明确作为历史快照字段而非强外键，避免解析重建清除旧 `KnowledgeObject` 时阻断或损坏引用。
- 新增 `GET /evidence-pointers/{pointer_id}`：票据过期后可用持久 pointer 恢复引用；读取重新校验课程权限、学生 AI Policy、资料可见状态和该版本已发布快照，撤权/归档后对学生返回 404。教材滚动到新版本后，历史已发布版本 pointer 仍指向原版快照。Tutor SSE 与已存引用同步携带稳定 pointer ID。
- A 窗口新增 `GET /evidence-pointers/{pointer_id}/page-image` 与学生端页级 `EvidencePointerDrawer`：服务端重新鉴权后按不可变教材版本的 PDF 源文件 SHA-256 生成/读取固定 PyMuPDF PNG 页图及仿射坐标变换；缓存元数据和图像分别验证渲染器版本、源摘要、页码、像素尺寸及图像摘要。Reader 定向测试 **7/7 passed**，前端合同测试通过；OpenAPI 已统一导出包含该端点。
- 当前 P2-06/07 仍未完整：旧教材版仅在该版本曾有已发布快照且当前课程/资料仍可访问时恢复；更细的运行中 Activity/Release assignment 授权、Claim 四态与一次有界补检索、DOCX 固定渲染及复杂高亮验收仍缺。页图 Reader 目前只以 PDF 为固定源，不能替代最终 DOCX 固定版面和真实教材人工定位验收。

### P9 Admin 治理与运行恢复首批切片

- 管理员可按同机构账号搜索最小身份字段、查看课程 Scope 选项并读取授权审计；可授予/撤销平台工作区角色和单课程角色，操作要求 Idempotency-Key、理由与撤销乐观锁版本，写入审计。迁移 `0039` 增加活跃 Scope 唯一索引，避免并发产生重复角色；遇到历史重复时迁移安全失败且不删除记录。
- 平台工作区仅开放 assistant/course_designer/course_publisher；单课程可授予 teacher/assistant/course_designer/course_publisher；禁止跨机构、停用账号、自我授予和直接用 RoleAssignment 创建 class scope。班级学生/任课关系使用 ClassMember/TeacherAssignment 专门流程；管理员班级任课分配首批入口已实现，完整 IAM/课程班级治理工作台仍待实现。平台管理员身份本身不会因此取得课程正文或学生私聊权限；课程授权撤销后，`/courses` 和课程资源的下一次请求立即重新鉴权。
- 管理员任务面板已新增同机构教材解析/索引任务的最小状态投影；仅 `failed && retryable`、最新且尝试次数未达 5 的任务可重试。重试要求当前 Job 版本、理由和 Idempotency-Key，写入审计；并发状态冲突返回 409，派发失败以脱敏信息恢复到可重试状态。列表不返回 payload、学生/教材正文或原始错误。
- 管理员班级任课入口现已落地：查询同机构课程的班级、已入课教师/助教和任课记录；可授予或结束 `TeacherAssignment`。服务端校验课程成员、机构和班级归属，使用幂等键、理由审计、结束版本锁及 Outbox；管理员不会因此获得课程教学读取权。完整 IAM/课程班级治理工作台仍待实现。

### P4/P5 Current Learning Task 可恢复工作区第一切片

- `GET /student/learning/tasks/{task_id}` 提供服务端权威的 `LearningWorkspaceView`：任务/状态版本、教材上下文、结构化 Blocks、允许动作和完成状态；读取会重新校验当前课程 Scope。
- `POST /student/learning/tasks/{task_id}/respond` 复用现有状态机并强制单一 `respond_task` 动作；版本不一致仍返回 409，响应不会直接写入掌握度、记忆或长期学习证据。
- 旧 `/learning-sessions/{id}` 读写接口保留兼容，同时返回同一工作区投影，避免前端通过多个底层接口拼装任务状态。
- 学生引导学习页已保存当前 task id，刷新后从工作区接口恢复；遇到版本冲突会拉取最新回合并要求重新确认，而不是自动重放旧回答。
- `GET /student/home` 已提供真实学生首页投影：在 SQL 查询阶段先按当前有效学生课程成员过滤，再聚合可继续/暂停任务队列、跨授权课程的到期复习、最近任务和 Planner 决策；首页消费该接口，`/student/learning` 直接挂载 Tutor 状态机，可从另一设备用服务端任务 ID 恢复。
- 新增带 `state_version` 的 `pause`/`resume` 命令；暂停保留原教学状态和上下文，恢复前必须重新通过版本校验，暂停期间不能提交学生回答。
- 正式测评 `ai_policy=disabled` 进行中时，创建、回答和恢复引导学习任务会复用服务端考试限制，不能从学习入口绕过 Policy。
- 新增运行时聚合迁移 `0032`：新建学习会话同时创建 `CurrentLearningTask`、`TeachingSession` 和复用型 `LearningEpisode`，响应/暂停/恢复同步状态、版本和 Episode 计数，工作区返回 runtime refs。
- 新增向前迁移 `0033`：为 `0032` 前创建的学习会话回填运行时聚合；历史无法可靠还原的目标、Release 快照和回合数均标记为 legacy/unknown，不伪造历史数据。新旧会话统一可返回 runtime refs。
- P4-07 安全语境区分：Tutor 不再仅因出现“自杀/自残”等词就退出课程问答；明确个人意图和身边人的现实风险优先进入支持回复，明确教材/研究/定义语境中的概念讨论继续走正常证据检索。支持回复指向全国统一心理援助热线 12356，但不宣称各地均为 24 小时服务。

### P5 Me 显式偏好第一切片

- 新增 `user_preferences` 与 Alembic `0023`；`GET/PATCH /me/preferences` 提供提示密度、字号、减少动画和站内提醒偏好，带乐观锁版本。
- 偏好只改变表示和通知，不会解除考试、权限、证据或安全策略；学生隐私页面已接入真实读取与保存表单。

### P5 Growth 投影第一切片

- 新增 `GET /student/growth/overview` 与 `GET /student/growth/knowledge`；服务端按课程 Scope 聚合关注知识点、状态、证据数量、到期复习和下一步行动，不下发原始正确率。
- 学习首页、成长页和兼容学习空间已改读上述投影，展示可解释状态与行动建议，不再展示原始正确率百分比。
- Growth 页已接入四视图切换：知识、技能、误区、轨迹；误区仅显示未过时的个人学习记忆，轨迹按日期汇总学习证据数量。
- 新增 `notifications` 与 Alembic `0024`；`GET /me/notifications`、`POST /me/notifications/{id}/read` 提供站内通知读取/已读幂等操作，教师派发干预时在同一事务为目标学生创建通知。
- 新增结构化 CourseRelease Pack 校验：Domain/Pedagogy/Assessment 仍允许渐进式草稿字段，但已校验 JSON 大小、数组类型、知识点/关系/实验/Flow/题目/Rubric 的关键字段和危险字段；无效 Pack 在创建或编辑阶段返回 422。
- 新增 `teacher_observations` 与 Alembic `0027`；教师可创建、列表和复核误区/策略/支持需求/进展观察。观察保留证据引用、复核理由和算法版本，复核不会覆盖原始作答、LearningEvidence 或 MasteryState。
- 案例推理事件已接入确定性 Qualification：Worker 只读取服务端 `CaseSession` 完成快照生成 practice Evidence，并重算该课程掌握投影；客户端提交的分数和答案字段不作为权威来源。
- 案例目录已扩展为五类服务端固定模板（混淆变量、实验拆解、设计板、结果解释、批判性检查），学生端从 `/student/cases/catalog` 选择类型后再创建不可变案例快照。
- 学生案例读取投影不再下发 `expected_confound` 等标准答案字段；草稿通过 `CaseSession.response` 与版本号保存，提交时由服务端锁定并按服务端案例快照评分。首轮确定性评分检查选项与理由的完整性，不等于设计推理语义质量评估。
- `LearningEvidence` 已新增维度（Recall/Understand/Discriminate/Apply/Transfer/Retention）、独立性、情境、质量状态和失效理由；`MasteryState` 记录情境数与独立证据数。教师可通过失效接口触发确定性掌握重算，失效证据保留不删除。
- ReviewTask 已新增延迟验证资格状态（迁移 `0031`）：到期复习下发不含答案的题目快照，学生可提交服务端版本校验的选择，Qualification 以 `retention` 维度写入独立 Evidence；错误复习也会保留为可解释的负向保持证据。
- 掌握算法升级至 `mastery-v2-independent-context`（迁移 `0034`）：熟练至少需要2条独立证据、已掌握至少需要3条，均覆盖至少2种情境；受提示证据不计入独立数；MasteryState 保存算法版本与中文状态理由，旧状态按新门槛回算。

### P7-03 正式测评截止锁补强

- 自动保存接口读取服务端 Assessment 状态和 `closes_at`；测验被关闭或超过截止时间后返回 `ASSESSMENT_CLOSED`，不接受迟到写入。客户端 `client_saved_at` 不参与截止裁决。
- 新增确定性集成回归，冻结服务端时钟验证截止前保存成功、截止后即使伪造较早客户端时间仍返回 409。
- 恢复进行中的 Attempt 时，接口返回已保存的学生答案和 `answer_version`，不下发标准答案；教师独立测评页与课程练习页在刷新/重新进入后恢复单选题状态，并从服务端版本继续乐观锁写入。
- 迁移 `0035` 为已保存答案增加持久化标记；学生仅能对已作答题目标记/取消标记，状态与答案共用乐观锁版本，截止/提交后拒绝修改。两处学生入口均可查看恢复后的标记状态；标记不参与评分、掌握度或学习证据。
- P7-04 `/student/assessments` 已启用独立 Assessment Shell，与普通练习路由分离；包含开考前确认、进行中测评刷新恢复、截止提示/倒计时、题号导航、未答/标记检查清单和提交前确认。单选、多选、判断及短答/论述均按后端 response 契约逐题自动保存，提交被保存中/失败状态阻止；多选按键数组、判断按布尔值持久化，逐题队列避免快速操作造成乐观锁版本竞争。窗口 B 补充截止尾端恢复：超时关闭当前尝试，学生可对服务端给出的当前 `attempt_id` 显式封存/恢复且不取回题目正文；定向后端 1 项与 Node 2/2 通过。真实浏览器网络中断后的自动续传/提交仍未验收。
- P4-04/P10-02 Tutor SSE 恢复：相同 `client_turn_id` 与请求正文重试会重放已持久化答案及 `done(saved=true)`，同键不同正文冲突；消费端中断时关闭流迭代器。前端仅在收到已保存完成事件后清除输入，EOF/错误时恢复输入并移除未确认的乐观消息。ASGI body iterator 断开专项 2 项、Node 3/3 通过；不是 TCP 断网、Worker 崩溃或 Redis 故障端到端证据。输入和幂等键仅在当前页面内存，不承诺刷新恢复。

### P7-06 主观题人工评分首轮

- 迁移 `0036` 新增不可变 `TeacherGradingDecision` 与版本化 `ScoreRecord`；人工决定按主观题追加，正式成绩只追加快照，旧版本通过 `supersedes_id` 保留。覆盖需当前成绩版本和非空理由，并写审计；相同 `Idempotency-Key`/请求回放原成绩，不重复评分版本。
- 新增教师专属评分队列、提交详情与评分接口；队列和响应读取都先验证当前课程教师 Scope。学生自己的 Attempt 在待人工评分期间看不到分数、单题得分或正确性；全部主观题评分后由服务端发布时间并展示最终成绩。
- 教师测验页面新增待评分/已评分记录切换、学生作答与 Rubric、逐题评分理由、历史决定和有理由的覆盖工作区。由于当前没有获准处理学生答案的本地/外部模型，不生成 AI 建议、不向外部服务发送学生作答；AIGradingSuggestion、机构级延迟发布策略与主观题学习证据资格化仍未完成。

### P7-05 正式测评期间 AI/学习支持隔离

- 新增统一服务端考试期策略检查；账号存在进行中的正式 Attempt 时，课程问答/题目辅导会话的创建、历史读取、列表和继续，学习会话创建/响应/恢复，分支合并、复习任务、学生教材读取、知识检索及证据读取均 fail-closed，不能通过旧会话或其他入口绕过。
- 当前 `direction_only` 没有具备可验证输出限制的执行器，因此不会伪装成已支持；考试期间按禁用处理。`full_after_submit` 的标准解析只有在 Attempt 已提交或评分后释放。
- 服务端隔离矩阵覆盖 `disabled`、`direction_only`、`full_after_submit` 与 `course_qa`/`question_coach` 组合；机构级正式测评策略界面尚未实现。

### P7-07 / P7-08 题目质量反馈与测评可靠性

- Alembic `0037` 新增最小化错题追踪与题目质量反馈，不重复保存学生答案正文；学生反馈幂等且按课程/题目版本授权，教师可受理、驳回或归档，题目版本并发冲突返回 409。
- 题目归档阻止新 Attempt；已开始 Attempt 仍依据冻结快照完成，但归档后不再生成新的学习证据/复习任务。受影响证据、复习资格和候选状态失效时保留历史记录。
- 正式测评可靠性回归覆盖多标签答案版本冲突、标记与答案共用版本、重复提交/评分无重复副作用、跨课程 IDOR、截止与终态行为。首次答案保存会推进版本，旧标签页的写入不能覆盖新答案。

### P8-06 Mini Lab 阶段检查点与恢复

- 新增学生进行中 Mini Lab 查询和服务端阶段检查点追加接口；六阶段运行状态按版本追加，刷新/重新进入从服务端检查点恢复，前端等候服务端确认后再进入下一阶段。
- 幂等重放、并发推进和完成回放保持稳定；实验原始 TrialData 仍与学习证据分离，只有服务端已完成会话可进入既有 Qualification。
- 当前仍使用确定性开发实验定义；尚未绑定最终教材中的 2—3 个实验，也未完成真实班级浏览器验收。

### P3-06 隐私删除本地工作单

- Alembic `0042` 新增 `PrivacyDeletionRequest`，`0043` 更正计数字段，`0044` 增加状态凭证哈希，`0045` 增加 queued/running/failed/completed 状态、请求时间、尝试计数、安全错误代码与重试标记，并允许未完成单据的 `completed_at` 为空。历史 0042/0043 回执仍无查询凭证，按 404 隐藏处理。
- 调用方在请求前生成 ULID 回执编号和 32 字节随机状态凭证；前端展示两项并要求用户确认已保存后才发送。服务端仅存凭证 SHA-256 哈希和 30 天过期时间；因此受理事务提交后即使 HTTP 响应丢失，用户仍可凭预先保存的编号/凭证无登录查询，无需仅凭可枚举编号重签 bearer secret。
- `POST /me/privacy/delete-request` 清理登录失败缓存；同一数据库事务内写入 queued 工作单、停用/去标识账号并撤销全部登录会话，然后尝试派发 Celery Worker。派发失败保留 retryable failed 状态。`POST /privacy/deletion-status` 可无登录查询；`POST /privacy/deletion-status/retry` 可凭相同凭证重派发 queued/failed 单据。
- Worker 使用工作单行锁，在一个数据库事务内幂等删除聊天正文、Tutor 学习任务/Episode、Case/MiniLab、干预执行、TeacherObservation、Review/WrongAnswer/反馈、LearningEvent/Qualification/Evidence/Mastery、EvidenceTicket、记忆、偏好、通知、课程/班级成员与幂等记录，并解除 ModelCallLog 用户关联。只有事务提交后才写 `completed_with_retention`、计数及完成时间；处理失败以固定 `deletion_processing_failed` 记录并允许凭证重试。任务启用 late ack/worker-lost reject；相同工作单重放以行锁串行，完成单变成 no-op。
- 当前没有按学生建立的检索向量索引；教材检索索引属于课程教材对象，不因用户删除而清理。当前个人 Redis 数据仅有邮箱哈希登录失败限流键，并在受理时清除；无其他应用层个人派生缓存。学习证据与 MasteryState 一并删除，因此不对被删用户重算出新状态。
- 正式测评作答/成绩、审计和课程创建/任课历史不擅自物理删除，回执明确列出待机构/法律策略处理的保留类别；这属于去标识化而非不可逆匿名化。机构保留依据、外部备份/生产索引擦除仍未验证，不能称为所有环境下的完整删除闭环或生产擦除完成。
- 隔离专项验证调用方预置凭证、受理响应丢失后查询、无登录撤权、凭证错误/过期、派发失败、处理事务失败、凭证重试、完成任务重复回放、个人数据删除与保留类别，`test_mastery_memory.py` **9/9 passed**。真实 Celery broker/worker kill 与重投、真实 Redis/进程崩溃未做端到端故障实验；运行 Worker 的新任务注册需后续在非主预览环境验证。隐私 API schema 已纳入 `PrivacyDeletionResponse`/`PrivacyDeletionStatusResponse` OpenAPI。

### V3.2 陈旧任务派发失败恢复补强

- 陈旧任务从 `running` 恢复为 `queued` 时递增任务版本并清空旧完成时间，记录恢复来源版本检查点；若派发抛错且数据库任务仍处于本次恢复版本的 `queued`，则持久记录为 `failed / dispatch_failed / retryable=true`，保存完成时间和检查点，错误信息脱敏，使任务可进入既有管理员受控重试流程。
- 若并发 Worker 已推进任务状态或版本，恢复器不会用迟到的 broker 异常覆盖新状态；批次错误不包含底层 broker 地址/凭据。目标测试 `tests/test_job_recovery.py` **3/3 passed**。Broker 对“消息已接收但确认丢失”的模糊超时仍可能需要 Outbox/任务认领来进一步约束重复投递，未宣称 exactly-once 或生产故障恢复完成。

## 已验证

> 本节是 0045 集成阶段的历史验证快照。当前工作树为 0047；最新测试、OpenAPI、预览数据库和剩余边界以文首“R2 集成复核（2026-10-04）”及验收报告为准。

- Web：本轮 Node 测试 **32/32**、TypeScript 和全仓 `pnpm lint` 通过；全仓 lint 为 0 errors、3 个既有 `react-hooks/exhaustive-deps` warnings。为避免扫描 Git 忽略的 Corepack 缓存，ESLint 已忽略 `web/tmp/`；相关缓存保留未删除。生产构建未重建，以免覆盖正在提供预览的 `.next`。
- Server：代码迁移头现为 `0045`。隔离库 `psychology_learning_privacy_jobs_20261004` 已通过 `alembic check`（无待生成迁移），P3-06 `test_mastery_memory.py` **9/9 passed**，全仓 Ruff 通过。0045 集成后的全量 `pytest -q` 在隔离库 `psychology_learning_v1_final_20261004c` **275 passed**，耗时 2144.61 秒；3 条警告为 FastAPI/Starlette/httpx 弃用提示与 pytest cache 权限警告。OpenAPI 快照由脚本生成并与运行应用核对为 **127 paths**，重复导出 SHA-256 稳定；ExperimentSchema 含总体设计字段与教材证据稳定 key。管理员治理/课程路由专项 **32/32 passed**、Domain Pack/课程路由专项 **43/43 passed** 为历史专项。G0 冒烟历史结果 **5/5**，本轮未重跑。
- 本轮 Tutor 回归测试 7/7 通过，覆盖刷新恢复投影、任务版本、非法动作、版本冲突、暂停/恢复和兼容旧接口。
- 来源驱动实现：后端 Learning Block 单元测试 2/2 通过；Mini Lab 适配器已完成类型检查、构建和前端回归。
- Domain Pack 纯单元测试 19/19 通过；`test_courses.py`、`test_domain_pack_graph.py` 与 `test_domain_pack_validation.py` 在独立 `psychology_learning_window_a_test` 数据库副本中合计 39/39 通过，未争用共享测试库。Ruff check 通过；前端 Node 测试 8/8、`pnpm run typecheck --incremental false` 通过；OpenAPI 生成前后 SHA-256 一致。
- 本地预览：Web `http://localhost:3000`、API `/api/v1/health/live` 与 `/api/v1/health/ready` 均返回 200；就绪检查确认数据库与 Redis 可用。运行 API 与工作区 OpenAPI 快照均为 **127 paths**；`/privacy/deletion-status` 页面返回 200。预览数据库 `psychology_learning_privacy_target` 仍处于 Alembic `0044`，未升级到代码 `0045`，本轮未通过预览 API 触碰新删除工作单字段。两服务仍连接隔离开发库（仅演示教师/学生和空演示课程），未修改原有演示数据。

## 当前阻塞/未宣称完成

- P1-03 已完成 Outbox 持久化、消费去重、失败重试和 Redis Stream 投递 Worker；Release 目前是课程版本基础，不等同于完整 Domain/Pedagogy/Assessment Pack 发布向导。
- Domain Pack 当前只接受声明的 JSON 字段，Relation 词表仅有 `prerequisite`；EvidenceBinding 的 `source_object_id` 已在发布时校验为同一教材版本中的 `KnowledgeObject`。更广的 Relation 词表、独立 Canonical 审核状态或 AI 候选工作流仍未实现；当前没有 AI Domain 生成写入路径。
- 平台管理员不会被改造成隐式课程教师；同机构平台/课程角色授权、撤销、理由、幂等与审计，以及最小化任务状态列表和受控重试均已实现。管理员班级任课分配入口已实现并通过针对性测试；完整 IAM/课程班级治理工作台仍未实现。
- Mini Lab 当前已具备服务端会话、六阶段检查点恢复、结果校验和首个自编确定性 fixture，尚未绑定最终教材中的 2—3 个实验内容，也未完成真实班级浏览器 E2E 与学习效果验证。
- TeachingAsset 已具备版本注册、草稿、发布门禁、课程 Scope 和安全降级渲染；尚未覆盖完整教材资产包、图表/公式固定布局和跨设备浏览器 E2E。
- P3 当前已完成原始事件接收、正式测评/案例推理/Tutor 检查回合/Mini Lab 完整回合/到期复习验证资格化、通用批处理 Worker、证据维度/独立性/情境门槛和失效重算；多知识技能模型及更丰富的跨情境验证任务仍未完成。
- P4-07 已区分课程术语讨论与个人/他人现实风险；没有明确学术语境的匹配内容仍保守进入支持回复。它是文本规则，不是临床风险评估，不得作为危机分级或诊断工具。
- P6-04 TeacherObservation 已接入班级 Scope、来源 Evidence 校验、幂等创建、教师复核与独立再验证关联。仅班级 lead 可创建/复核/再验证，已授权教师/助教可读；创建要求学生仍属于该课程和班级，且来源 Evidence 属于同一学生/课程并有效。
- TeacherObservation 的教师接受复核只记录 `review_decision=accepted`，资格状态仍为 `pending`；拒绝为终态。再验证候选只暴露通过正式 Qualification 的事件摘要，不返回事件 payload；再验证要求同学生/课程、观察后新形成的有效独立 Evidence、不同学习情境和目标知识点，并关联既有 qualified LearningEvent/LearningQualification，不生成或覆盖 Evidence/Mastery。
- 再验证关联保留事件、资格、Evidence ID、算法版本和原因，受乐观锁与审计保护；同一事件不能重复用于其他观察，重试幂等。来源或再验证 Evidence 后续失效时，读取投影标记 `invalidated`，历史关联保留。迁移 `0038` 对唯一可判定的历史班级回填 Scope；旧的直接 qualified 状态降为 pending，并保留原复核字段供审计。
- 在未定义学生知情/可见/保留政策前，观察正文仅教师/助教可见，不提供学生展示入口；不读取私聊，也不允许教师观察直接修改掌握度。
- P4/P5 已为新旧会话同步 `CurrentLearningTask/TeachingSession/Episode`，通过学生首页展示多任务队列并聚合到期复习；更复杂的跨任务调度/排序策略仍未完成。
- P5 已有显式偏好读写、完整 Growth 四 Tab、站内通知中心和五类服务端案例推理工作区；学生端支持变量/设计选择、理由草稿保存及恢复，不返回标准答案字段，正式提交由服务端固定快照评定并进入待资格化流程。当前评分只检查说明完整度，尚非语义质量评估；完整 Case/Experiment Decomposer 题型库的进阶交互与跨设备浏览器 E2E 仍未覆盖。
- Student Home 已接入确定性 Planner 适配器，输出 `continue/review/remediate/complete` 四态进度决策、原因和安全 fallback；不直接修改掌握度或正式测评状态。
- 新增 CaseSession 与 Alembic `0025`；案例草稿更新使用乐观锁版本，提交后锁定响应并由 Worker 读取服务端快照生成练习证据，不直接信任客户端评分。窗口 B 案例后端 3 项、Node 4/4 通过；浏览器 E2E 未运行。
- P6 干预工作台新增效果 Read Model：区分执行完成率与即时/延迟检查测量，未有测量时明确返回 `not_measured`，不生成学习效果结论。
- ClassMember 独立班级 Scope 已通过 Alembic `0026` 和教师/助教只读接口接入。
- P6-04 定向验证：`test_interventions.py` 5/5 通过；Alembic `upgrade head` 与 `alembic check` 通过；相关 Ruff 检查、前端 `pnpm test` 8/8、`pnpm typecheck` 和定向 ESLint 通过。测试使用隔离临时 PostgreSQL 数据库，未争用共享测试库；教师观察 OpenAPI 与导出契约一致。
- P5 案例推理的当前实现与验证范围见上方 P5 条目；完整 Case/Experiment Decomposer 题型库进阶交互和跨设备浏览器 E2E 仍未覆盖。
- 课程设计 Domain/Pedagogy/Assessment 页面已接入真实 CourseRelease 草稿 Pack 读取与乐观锁保存；发布页继续负责服务端门禁和不可变版本发布。
- CourseRelease 草稿编辑权限已允许课程级 `course_designer`，发布权限仍限定教师或 `course_publisher`；新增越权回归覆盖。
- P9 当前已完成平台/课程 Scope 的管理员授权授予与撤销、同机构教材任务状态投影与安全重试、管理员班级任课分配首批切片及审计；完整 IAM/课程班级治理工作台仍未完成。班级任课使用 `TeacherAssignment`，不写入权限依赖不识别的 `RoleAssignment` Scope。迁移 `0039` 以活跃 Scope 唯一索引防止并发重复授权，并在发现历史重复时安全失败、不删除记录。

## R3 共享协调检查点（2026-10-04）

- 主窗口新增迁移 `0048`，共享 `DomainRelease`/`DomainReviewDecision`、CourseRelease/PublicationSnapshot/RetrievalUnit 的 DomainRelease 绑定、Memory 来源/时效/冲突字段、Branch merge 收据及 Mini Lab 作废收据字段。R3-A 专属数据库 `psychology_learning_v1_r3_a_20261004` 已从原有迁移升至 `0048 (head)`；隔离 `alembic check` 返回 `No new upgrade operations detected`。本地 vector type 比较警告仍存在，未改变检查结果。
- 主窗口新增迁移 `0049`：CourseReleaseAssignment、TeachingActivityVersion/Run、TeacherTimelineEvent、TeacherAnnotation、RubricVersion、QuestionPurposeApproval，以及 Assessment purpose/result visibility/ReleaseAssignment 与 AssessmentItem→Rubric 字段。新的根验证库 `psychology_learning_v1_r3_shared_20261004` 已从 0001 全历史 upgrade 至 `0049 (head)`；`alembic check` 通过。R3-A 库仍保持 0048，避免主窗口越权动用其窗口测试库。
- R3-A—G 的共享语义决定记录于 `R3-shared-contract-decisions-2026-10-04.md`。目前受限可施工范围为 A 的 knowledge 子域、B 不依赖 Domain 的 memory service/Tutor/Branch/Planner 子集、C 指定学生页面与案例、D 现有干预效果读模型安全化、E P7-08 可靠性、F 真实 Release 数据只读 Designer 子项、G 通用 Mini Lab 作废恢复/TeachingAsset fallback。Growth 规范技能/误区、AI 评分建议、获准教材与最终实验内容不在已验收范围。
- D 可实现 0049 之上的活动/运行/时间线/Annotation 模块 API 和专测；根 router aggregation、OpenAPI、公共 fixture 仍由主窗口维护。E 可实现 Rubric/用途资格/结果可见及可靠性模块 API；AIGradingSuggestion 不启用。F 仅做现有真实 CourseRelease 数据的只读 UI；Review/Preview/Diff/Gate/Impact/Publisher 与 CourseReleaseAssignment 服务/API 仍待主窗口实现。合同及 schema 不等于服务/API 已实现。
- `scripts/r3-baseline-fingerprint.ps1` 为所有未提交文件建立可复现的 status+SHA-256+path 指纹，排除仅自引用的状态文档和易变 `.pnpm-store/`。原 R3 指纹因旧文件清单/排除口径无法重建，不作为阻断条件；窗口需用新脚本记录共同基线增量。
- R3-C/G/E/F 已通过实际物理源码副本、独立 Next production build、API proxy stub 和 Chromium 375px 页面/API 检查；只证明构建隔离及基础 shell，不等于业务页面、真实教材、浏览器流程或完整 V1 验收。全量后端最新既有回归仍为 R2 的 294 passed；0048/0049 后全量回归尚待主窗口统一运行。

## R3 主协调最新复核（2026-10-04 23:24 +08:00）

- 当前代码/迁移 head 为 `0049`；主窗口共享迁移库、全量测试专库均为 `0049`，R3-A/B/C/E 分配库现为 `0049`，D/F/G 分配库现场仍无 `alembic_version`/业务表。主预览数据库 `psychology_learning_privacy_target` 仍为 `0044`，未迁移、未写入；Web/API 3000/8000 保持在线，`/api/v1/health/live`、`/api/v1/health/ready` HTTP 200。不得以 ready 检查代替 schema/head 核验。
- 当前 OpenAPI 已重新导出，148 paths、SHA-256 `EAF93FEEC24BF1116508A57534889CBB125936C2CD295EFCDA4DA7CC5FA6DC61`。包含 A/E 的实际模块路由及主窗口 CourseRelease Preview/Diff/Gate/Review/Impact/Assignment API；TeachingActivity 路由仍未进入 OpenAPI。旧无请求体 Release publish 分支仍可绕开新 Review Gate，未关闭。
- 主窗口针对用户级 Memory API 的 Scope 聚合修正位于 `server/app/modules/memory/router.py`：无课程参数的 `/me/memory` 与 `/me/memory/items` 现在逐一汇总本人全局及各课程 Scope，未修改 B 独占的 `memory/service.py`。原 `test_memory_summary_and_weakness_candidates` 复现后通过（1 passed）。共享旧集成测试确认进行中 Attempt 请求 `/result` 必须按 R3-E 结果策略 fail-closed，已更新为断言 403 `ASSESSMENT_RESULT_NOT_RELEASED`；对应 6 种 AI policy/chat mode 组合与 Memory 用例定向回归共 7 passed。
- 0049 后端全量回归曾在运行树变动期间得到 **302 passed、7 failed**（1102.02 秒）：1 条是上述用户级 Memory API Scope 丢失，已由主窗口修正；6 条是旧 `test_question_bank.py` 假定进行中 Attempt 的 `/result` 返回 200，与 0049 后 R3-E 策略要求的 fail-closed 不一致，现已同步测试合同并通过 6 组定向用例。测试期间 `assessments/router.py` 时间戳显示仍有窗口写入，故该全量结果不是静止共同快照，不能算整套回归通过；收到窗口交接/写入冻结后必须重跑全量。
- 主窗口复核时 root shared DB `alembic check` 为 `No new upgrade operations detected`，全仓 Ruff 通过；前端 Node 46/46、typecheck 通过，ESLint 0 errors/3 个既有 warning。CourseRelease/课程/Assessment 定向 31 passed 是先前快照证据，须在 E 交接及冻结后复跑；此前的隔离 build/Chromium 仅验证 C/G/E/F 基础 shell、proxy 和输出隔离，不是业务页浏览器验收。
- PostgreSQL A/B/C/E/shared/root-test 均可连且为 0049/72 张业务表；D/F/G 仍为空。Redis DB3/4/5/6/7/8/10/11 均 PING、0 keys；MinIO A—G 与 root 专属测试 bucket 存在。现场监听仅见预览 3000/8000；R3 3210—3216、8210—8216、9310—9316 无监听。Docker Engine 仍因本地命名管道权限问题未核验。
- 各窗口 R3-A—G 报告仍未形成可审查交付；代码存在不等于交付。主窗口在共享启动状态文件发布短期写入冻结/交接广播后，将统一复核逐窗文件差异、独立测试和业务验收。无获准教材/最终实验内容/机构保留与成绩可见政策/学生答案 AI 授权等外部输入继续作为对应范围阻塞；不阻塞其余可独立工程工作。R3 与 V1 均未整体验收完成。

## R3 主窗口稳定复核（2026-10-05）

- 当前共同代码树全量后端隔离回归 **313 passed、2 warnings，1082.31 秒**；之前 302 passed/7 failed 是修复前且运行期间文件仍变动的历史结果，已被本次全量结果取代。R3-A—G 仍需各自提交范围、实际测试和未决项的完整交接；本次结果不等于逐窗验收。
- root shared DB `psychology_learning_v1_r3_shared_20261004` 为 `0049`，`alembic check` 无新操作；OpenAPI **148 paths**，SHA-256 `EAF93FEEC24BF1116508A57534889CBB125936C2CD295EFCDA4DA7CC5FA6DC61`；全仓 Ruff 通过。前端 Node **46/46**、typecheck 通过、lint 0 errors/3 个既有 warnings。
- 主预览 Web/API 3000/8000 当前 HTTP 200；预览数据库仍为 `0044`，未迁移或写入。PostgreSQL/Redis/MinIO 依赖端口可连接；Docker CLI 对 Engine named pipe 返回 permission denied，容器状态未由 CLI 确认。
- 保留的关键未验收：CourseRelease legacy 无请求体发布路径可绕过 Gate；Release Impact 因缺证据版本绑定保持 `not_measured`；TeachingActivity endpoints 未进入 OpenAPI；C/D/E/F/G 的业务浏览器或真实内容验收不齐；无获准教材/教案、机构保留/评分可见规则及答案 AI 授权；V1 不宣称完成。

## R3 主窗口发布合同收敛与复验（2026-10-05）

- 根因已复现：CourseRelease `/publish` 在无请求体时允许 teacher/course_publisher，跳过 expected version、幂等、Review Gate 和警告理由校验，合法草稿可直接发布。现对此兼容分支返回 `422 RELEASE_PUBLISH_REQUEST_REQUIRED`；受控发布只接受 `course_publisher`、请求体版本、`Idempotency-Key`、当前版本独立审核和 Gate；警告必须给理由。OpenAPI 发布操作 requestBody 标为 required。主预览请求代码热重载对旧请求也会 fail-closed；预览库仍 0044，不做该端点新 schema 冒烟。
- 新增回归复现旧行为（修复前无请求体请求为 200、测试失败）；修改后无请求体拒绝、受控独立审核/版本/幂等流程覆盖。课程、Release、Domain Pack 和 TeachingAsset 相关定向套件最终 **26 passed**。旧 312 passed/2 failed 的测试依赖也已改为受控审核发布 helper 或断言 legacy 拒绝。
- 改动后在专属 PostgreSQL `psychology_learning_v1_r3_release_tests_20261004`、Redis DB11、`v1-r3-root-tests-20261004` MinIO bucket 执行完整后端测试：**315 passed、2 warnings、1144.22 秒**。Root shared DB 当前 `0049`，`alembic check` 无新操作；全仓 Ruff 通过。最新 OpenAPI **149 paths**，SHA-256 `7F0CF080423A0875564A7075C25BC681507F1FF4F56A8E64603C4085E18ABFFB`。
- 该修复关闭一个共享权限/发布门禁缺口，但不完成 Course Designer 浏览器验收、Impact 版本绑定（仍为 `not_measured`）、D Activity API 或 A—G 最终交接；V1 仍未完成。

## R3 主窗口接手 Branch 学生页与契约复核（2026-10-05）

- `/student/branches` 路由此前错误挂载 `StudentCaseWorkbench`，且旧 `StudentBranches` 调用与后端合同不一致：分支来源选错为 Tutor 回合，合并请求遗漏 `confirmed` 与 `merge_key`。主窗口已将页面切换到真实分支工作台，限定来源为学生本人发言内的连续原文片段；合并需学生显式确认、填写本人说明，并用稳定幂等键保护响应丢失重试。AI 分支结论不会自动并入或转化为学习记忆。
- 新增 `web/tests/branch-workbench-contract.test.mjs` 3 项；当前 Web `pnpm test` 为 **49/49 passed**，`pnpm typecheck` 通过，`pnpm lint` 为 0 errors、3 条既有 warnings。尚未运行后端 Branch 专项、隔离 API 或业务 Chromium；故目前只标“前端已编码/合同通过”。
- Mini Lab invalidate OpenAPI exporter 连续两次生成稳定（149 paths，SHA-256 `7F0CF080423A0875564A7075C25BC681507F1FF4F56A8E64603C4085E18ABFFB`）；请求体合同正确且 required，但成功响应仍呈空 schema `{}`。此模块文件归 R3-G，主窗口未越界修改；待 G 在其限定文件内补响应模型/测试后再导出。
- 本次检查时 PostgreSQL/Redis/MinIO、主预览及 R3 Web/API/CDP 端口无监听。数据库回归/浏览器验收待隔离资源重新确认；未把该阻塞扩大到纯前端实现。

### P10-02 跨角色浏览器关键路径验收

- 2026-10-03 使用独立临时 PostgreSQL 数据库、API 8001 和现有 Web 3000 完成本地 Chromium 跨角色实测；没有重启已有 Web/Worker，没有改动演示课程和作答数据，也没有安装 Playwright 依赖。
- 教师登录、建课、测评发布，学生作答保存、双标签乐观锁冲突、截止/提交锁、`pending_teacher` 成绩隐藏、教师评分与有理由覆盖均取得真实浏览器/API 证据；最终覆盖成绩版本 2 为 2/2。
- 学生学习页的教材问答 SSE 收到真实 `text/event-stream`；Chromium 离线后请求以 `net::ERR_INTERNET_DISCONNECTED` 失败，恢复网络重试后服务端只记录成功回合，但 UI 保留失败问题、重复显示重试问题且旧失败提示未清除，存在本地/服务端对话状态分歧。
- P10-02 首轮未通过全部 UI 恢复门槛：进行中测评刷新后学生页无法恢复作答；学生练习页没有论述题输入框；课程成员/题目/测验创建接口成功时前端出现通用失败提示且列表需刷新才更新；SSE 弱网重试后 UI 状态未与服务端同步。测评刷新恢复、简答/论述输入、创建后表单刷新、SSE 失败回滚均已补实现并通过自动回归；隔离 Chromium 复验确认教师创建题目/成员/测验后列表即时更新，学生刷新后恢复本人答案、论述文本自动保存并可恢复；发送前离线再重试和收到部分 delta 后流结束的 UI 状态均通过可控浏览器模拟复验。真实服务端传输中断和 Worker/Redis 故障恢复仍未验证。详细首轮与复验范围见 `docs/v1/P10-02-本地浏览器验收记录-2026-10-03.md`。
- 原有旧 API 进程已退出；当前 8000 运行的是工作区版本，但仅连接隔离开发测试库，不代表生产或原有演示数据环境已迁移。

## R3 主窗口最新进度分层（2026-10-05 13:32 +08:00）

- **已编码/集成：** 主窗口已注册 R3-D `teaching_activities` router，并通过 FastAPI exporter 将两条 TeachingActivity 路径及 R3-G `MiniLabResponse` 响应纳入 OpenAPI。两次连续导出均为 156 paths、SHA-256 `02241A429DD2284E20C409B8C4436121277C3D6F207F8C753DE85028FF216900`。Branch 学生页仍由主窗口独占，已按后端合同编码；业务浏览器尚未复验。
- **当前 Web 自动化/静态质量门：** 当前共同 checkout `pnpm test` **55/55 passed**、`pnpm typecheck` 通过、`pnpm lint` 0 errors / 3 个 React Hook dependency warnings。此轮未运行 `pnpm build`，也未做整站业务浏览器验收。
- **D 局部后端检查：** 主窗口对 API router 与 TeachingActivity 运行 Ruff 通过；不依赖数据库的合同/逻辑测试 **16 passed、1 个数据库集成用例 deselected、2 warnings**。完整 Activity/Run/Timeline/Annotation 数据库链、`/effect` 数据库口径及 E2E 尚未验收。
- **服务现场：** 13:30 TCP 检查显示 PostgreSQL/Redis/MinIO 与共享预览端口可连接，R3 A—G 专属 Web/API/CDP 端口均无监听。端口可达不等于数据库 revision、Redis DB、bucket 和 API 行为全部验证；本轮未对预览库写入。
- **全量后端边界：** 已记录的 315 passed/2 warnings 是早于 D 路由集成和本轮 A—G 后续变更的历史静止快照，不代表当前全树。当前共同代码树的完整后端回归、迁移 `alembic check` 和业务浏览器矩阵仍待执行。各窗口的已编码/局部测试与剩余 HOLD 详见 `docs/v1/V1并行启动状态.md` 最新检查点；不据局部进度宣称 R3 或 V1 完成。

## R3 主窗口 Domain 快照落地与 D 集成复核（2026-10-05 13:57 +08:00）

- **已编码：** CourseRelease 创建/更新可绑定同课程已发布 DomainRelease；Pack 必须与不可变 manifest 精确一致，缺省时从所选发布版本带入规范 Pack。切换 DomainRelease 会推进版本并令旧审核失效；结构化 Pack 未绑定发布版本时 Gate fail closed。教材发布可指定 DomainRelease，并将同一 ID 写入 PublicationSnapshot；CourseRelease Gate 联查发布快照、成功 embed Job 的 payload 与该版本下 ready RetrievalUnit，拒绝跨版本或缺证据发布。无需新迁移，Audit/outbox 增加对应标识。
- **专项验证：** 独立 root PostgreSQL `psychology_learning_v1_r3_root_domain_20261005a`（0049）、Redis DB11、MinIO bucket `v1-r3-root-tests-20261004` 上，`test_jobs_publish.py` 与 `test_r3_release_workflow.py` **21 passed**；`alembic check` 无新操作；相关 Ruff 与 compileall 通过。OpenAPI 连续导出稳定为 156 paths，SHA-256 `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`。
- **集成发现：** D Router 已由主窗口注册，`test_teaching_activities.py` 与 `test_interventions.py` 为 **21 passed、1 failed**。唯一失败在 D 所有的 `teaching_activities/router.py` Run action：commit 后序列化访问未刷新的 `updated_at` 触发 `MissingGreenlet`。已在共享启动状态中交给 D 修复；主窗口不越界改 D 文件。
- **仍待主窗口：** CourseReleaseAssignment 尚未端到端注入学生学习/测评/活动运行 Scope，Impact 继续为 `not_measured`；历史 Release→历史 PublicationSnapshot 的检索/运行固定链仍待接线；Tutor Claim 四态/至多一次受限补检索持久化待 B 与主窗口落地。D 修复后需复跑其隔离 E2E。上述定向通过不替代当前工作树完整后端、全前端或真实课程验收。

## R3 主窗口 Assignment 运行快照共享底座（2026-10-05 14:06 +08:00）

- **共享模型/迁移已编码：** `LearningSession`、`Attempt`、`LearningEvidence` 新增 nullable `course_release_assignment_id` 与 `course_release_id`，迁移为 `0050_bind_learning_runs_to_release_assignments.py`。FK 使用 `RESTRICT`，两列须成对为空/非空，并添加 assignment 查询索引；旧记录均保留 NULL，没有按当前指派猜测回填。`TeachingActivityRun` 原已有相同绑定字段。
- **验证：** 在全新 root 专库 `psychology_learning_v1_r3_root_assignment_20261005a`（Redis DB13、独立 MinIO bucket 名未创建，本用例未调用对象存储）运行 Release workflow **5 passed、2 warnings、24.69 秒**；fixture 将空库迁移至 `0050 (head)`。另将保留既有 Domain 测试数据的 root 专库从 `0049` 向前升级至 `0050`，复核 revision 与 `alembic check` 均通过，没有截断/清理数据。migration/models Ruff 与 compileall 通过。
- **模块施工交接：** 共享合同与并行状态已给 B（Tutor LearningSession/LearningEvidence）、E（Assessment Attempt）限定模块接线 GO；各自不得改 models/Alembic/OpenAPI。接线前须在自己的隔离库安全升级 0050 并记录 revision。Impact 仍不可测，直到证据写入并能稳定关联具体 assignment/release，且满足独立复测/时间窗/样本门槛。
- **其余未验收：** Domain 历史 PublicationSnapshot 按旧 Release/Assignment 回读、Tutor Claim 跨模块持久化、D 的 `MissingGreenlet` 修复仍待窗口交付；完整后端、全前端与真实课程输入验收仍未运行/未获得。V1 不宣称完成。

## R3-F 真实 API 只读页面准备（2026-10-05 14:22 +08:00）

- F 专属空库 `psychology_learning_v1_r3_f_20261004` 经 root 统一迁移所有权升级至 `0050 (head)` 并通过 `alembic check`；用 root seed helper 经真实 API 创建了两个 manifest 不同、无教材材料的合成已发布 Release。seed helper `server/tests/r3_f_browser_seed.py` 可为 F 专属库重建额外合成数据，用户/课程/Release 记录保留、不清理。
- root 在 F 的 API 端口 8215 启动隔离 API PID 40572；live、cookie 登录、课程列表与 Release 列表均 HTTP 200，实际返回两项版本数据。API 保持运行供 F 在 3215/9315 完成只读真实 UI 浏览器验收；当前尚无该页面 Chromium 证据。
- B 库当前也确认 0050/check 通过；E 库检测到活动连接，主窗口不并行迁移，E 的数据库集成范围仍等安全空闲与实际 revision 记录。

## 当前共同树质量门复核（2026-10-05 14:22 +08:00）

- OpenAPI 两次导出一致：156 paths，SHA-256 `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`。全仓 Ruff 通过；`git diff --check` 无空白错误，只有既有 CRLF 转换提示。
- Web 当前共同 checkout `pnpm test` **56/56 passed**，`pnpm typecheck` 通过，`pnpm lint` 0 errors/2 个 React Hook dependency warnings。全量隔离后端未在本 checkpoint 重跑，历史 315/2 仍不得代表 0050 与并行窗口最新增量。

## R3-C/D 服务环境重新开放（2026-10-05 14:25 +08:00）

- 依赖现场已恢复：C 专库原 0049/73 表、无活动连接；D 专库为空、无活动连接；各自 Redis DB5/6 PING 且 0 keys、专属 bucket 存在、3212/8212/9312 与 3213/8213/9313 空闲。主窗口仅迁移 schema，没有运行会清表的 pytest。
- C 专库前向迁移到 0050 并 check 通过、数据保留；D 专库从空库到 0050 并 check 通过。C 服务/API/浏览器范围现解除 HOLD；D 专属复现/修复 Run action `MissingGreenlet` 子项 GO。两窗仍未提交本轮新验收证据，不能标浏览器或全模块通过。

## R3-F Designer 页面账号补正（2026-10-05 14:33 +08:00）

- 原 seed 的 course-only designer scope 不足以通过前端全局 workspace guard。已将 `r3_f_browser_seed.py` 改为由合成平台管理员经真实角色授权 API 授予 platform `course_designer`；最新 `/me` 实测该平台角色与 `course_design=true`，8215 live/login/courses/releases 再次 200。F 可用共享状态登记的最新合成账号与两条 Release 做浏览器验收；此前合成记录保留。
- 当前全仓 Ruff 通过、`git diff --check` 无空白错误（3 条既有 CRLF 提示）。仍未有 F 页面 Chromium 截图/trace。

## R3-A/G 并行子项准备（2026-10-05 14:36 +08:00）

- A 已获明确的无服务 GO：在 knowledge `/search` 响应补充被权限过滤的 PublicationSnapshot 元数据数组，并覆盖 DomainRelease 双版本/学生与 staff 快照权限负例；A 原有排他范围不变。
- G 专库从 `0049` 前向升级到 `0050 (head)`，保留原数据库状态；Redis DB10 为 0 keys、bucket 存在、G 专属端口空闲。`alembic check` 无差异；G 可恢复既定服务依赖测试及 Chromium 验收，未以此标记模块验收完成。

## R3 主窗口 Tutor 会话版本固定（2026-10-05 15:00 +08:00）

- **P1/P2 Tutor Claim 前置底座：已编码、迁移验证通过。** `ChatSession` 新增成对 nullable `course_release_assignment_id` / `course_release_id`；新增 migration `0051`，含 FK(RESTRICT)、检查约束与索引。历史 NULL 不回填。B 专库从 0050 升到 0051，`alembic check` 无差异；root 全新专库 `psychology_learning_v1_r3_root_session_20261005a` 经迁移运行 `test_r3_release_workflow.py` **5 passed、2 warnings**，显式目标 URL 的 `alembic current=0051`/`alembic check` 通过；模型/迁移 Ruff 通过。
- **待 B 接线：** ChatSession 创建时依据学生 active 班级成员与唯一 active assignment 固定 Release；turn 对固定 CourseRelease manifest 和 A 的同版本 PublicationSnapshot 构造完整 Scope，接入 bounded Claim helper 并持久四态/稳定证据引用/次数/拒答原因；换版不得漂移、撤权 fail closed、NULL 历史会话保持兼容。已在共享合同与并行状态下发受限 GO，未将 schema 通过等同 SSE 业务完成。
- **待主窗口集成：** A 的直接构造快照搜索测试不能替代“真实材料发布产生快照→assigned release 精确检索”的端到端验证；A DB 发现活动连接时暂停迁移。迁移对现有其它隔离库的批量升级须先逐库检查版本和活动连接。

