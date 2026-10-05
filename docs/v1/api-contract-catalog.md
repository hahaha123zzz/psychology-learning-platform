# V1 API 与 Read Model 目录

本文把两份设计文档中的接口责任整理成开发目录。除“当前实现”列明确标注外，其余接口均为目标合同，不得以静态页面或前端假数据替代。

## 1. 公共约定

### 1.1 响应

成功：`{data, meta}`；`meta` 至少包含 `request_id`、`server_time`，列表补充 `has_more`、`next_cursor`。失败：`{error:{code,message,details,retryable},request_id}`。

资源无权时优先返回 404；策略已识别但禁止执行返回 403；版本或幂等冲突返回 409；字段验证返回 422；未登录返回 401。

### 1.2 命令头和并发

| 场景 | 必需输入 |
|---|---|
| 可重试创建/提交 | `Idempotency-Key` |
| 资源更新 | body 中的 `version` |
| 回合/分支 | `client_turn_id` 或 `merge_key` |
| 列表 | 稳定排序和 `cursor` |
| SSE 恢复 | `turn_id`、`Last-Event-ID` 或等价恢复游标 |

OpenAPI 只能由 FastAPI 应用导出；禁止手工修改 `contracts/openapi.json`。

## 2. 身份、工作区和 Scope

| 接口 | 目标返回/动作 | 权限规则 | 当前状态 |
|---|---|---|---|
| `POST /auth/login` | 创建 HttpOnly Cookie 会话 | 有效账号 | 已实现 |
| `POST /auth/refresh` | 轮换 refresh token | 有效 refresh session | 已实现 |
| `POST /auth/logout` | 撤销当前 session | 当前 session | 已实现 |
| `GET /me` | 账号、平台角色、课程成员、工作区 capability | 当前用户；角色来自显式 Assignment，动作仍需重新做课程 Scope 校验 | 已实现角色与 capability 投影；capability 不授予额外课程权限 |
| `GET /admin/role-assignment-targets?q=...` | 搜索授权目标的最小账号标识 | 平台管理员；仅同机构有效账号；最少 3 字符 | 已实现；不返回密码、学生学习数据或课程正文 |
| `GET /admin/role-assignment-courses` | 返回同机构有效课程的 Scope 选择项 | 平台管理员；仅课程 ID/标题/学期 | 已实现；不返回课程正文 |
| `GET /admin/role-assignments` | 授权元数据审计列表 | 平台管理员；可按用户、Scope、状态筛选 | 已实现 |
| `POST /admin/role-assignments` | 授予平台工作区或单课程角色 | 平台管理员；同机构账号/课程；禁止自授；必需 `Idempotency-Key` 和理由 | 已实现；平台范围限 assistant/designer/publisher，课程范围支持 teacher/assistant/designer/publisher；班级成员和任课分配走专门流程 |
| `POST /admin/role-assignments/{id}/revoke` | 撤销平台或单课程角色 | 平台管理员；同机构记录；必须带当前 `version`、理由和 `Idempotency-Key` | 已实现；权限读取按当前 Assignment 状态即时生效 |
| `GET /admin/role-assignments`、`/admin/jobs`、`/admin/audit-logs` | 同机构有限列表 | 平台管理员；稳定 `limit`/`cursor` 分页，默认 50、上限 200，返回 `meta.next_cursor`/`meta.has_more`；不返回任务 payload、正文、私聊或原始错误 | R2 实现；同机构、游标和损坏游标隔离测试通过 |
| `GET /admin/courses?status=&limit=&cursor=` | 同机构课程最少治理元数据 | 平台管理员；仅 id/title/term/status/version/created_at | R2 实现；隔离回归通过；不授予课程读取权限 |
| `GET /admin/courses/{course_id}/classes?status=&limit=&cursor=` | 班级编码/状态/版本、成员数、任课数 | 平台管理员；课程必须属于同机构；active/archived/all 过滤 | R2 实现；隔离回归通过 |
| `GET /admin/courses/{course_id}/members?status=&limit=&cursor=` | 课程成员最小 roster | 平台管理员；角色只可能是 student/teacher/assistant；不包含作答、学情或私聊 | R2 实现；同机构过滤；隔离回归通过 |
| `GET /admin/classes/{class_id}/members?status=&limit=&cursor=` | 班级成员最小 roster | 平台管理员；班级必须属于同机构；成员状态可筛选 | R2 实现；同机构过滤；隔离回归通过 |
| `POST /admin/courses/{course_id}/classes` | 创建教学班 | `{code,name,reason}` + `Idempotency-Key`；课程须同机构且 active；写审计与 Outbox | R2 实现；重放/冲突回归通过 |
| `POST /admin/courses/{course_id}/members` | 加入课程或恢复已移除成员 | `{user_id,role,reason}` + `Idempotency-Key`；有效同机构账号；role 为 student/teacher/assistant；禁止管理员自我加入 | R2 实现；资格由服务端重验 |
| `POST /admin/courses/{course_id}/members/{member_id}/remove` | 软移除课程成员 | `{version,reason}` + `Idempotency-Key`；返回 `{id,status,version}`；学生的班级归属同步软移除，教师/助教的任课关系同步结束 | R2 实现；版本冲突、幂等回放回归通过 |
| `POST /admin/classes/{class_id}/members` | 将课程内学生加入教学班 | `{user_id,reason}` + `Idempotency-Key`；学生必须先加入同机构课程 | R2 实现；资格由服务端重验 |
| `POST /admin/classes/{class_id}/members/{member_id}/remove` | 软移除班级成员 | `{version,reason}` + `Idempotency-Key`；返回 `{id,status,version}` | R2 实现；版本冲突回归通过 |
| `GET /admin/class-assignment-options`、`POST /admin/class-teacher-assignments`、`POST /admin/class-teacher-assignments/{id}/end` | 班级任课关系查询/授予/结束 | 平台管理员；教师/助教须已是课程成员；变更带理由、版本、幂等键 | 既有切片；独立流程保留，不复用 RoleAssignment(class) |
| `GET /courses` | 当前用户可见课程列表 | CourseMember 或 course Scope | Scope 隔离已实现 |
| `GET /courses/{course_id}` | 课程上下文 | CourseMember 或 course Scope | Scope 隔离已实现 |

`domain_pack.experiments[]` 的 ExperimentSchema 结构见 `api-state-contract-spec.md`：`key/title` 必需；研究问题、假设、IV/DV、操作化、控制/混淆变量、设计、流程、预测、结果模式、解释和限制均可选。教材未提供的字段省略或留空；`textbook_evidence` 使用 EvidenceBinding 稳定 key，与 `evidence_binding_keys` 兼容等价。服务端对文本长度、数组类型/数量和重复别名冲突做确定性校验，发布仍需关联当前教材版本的 EvidenceBinding。

平台 `admin` 不自动获得课程教师、教材、学情或私聊读取权限；只有明确 Course/Class Scope 才能读取对应资源。

## 3. Student Read Models 与命令

| 接口 | Projection/动作 | 关键字段 |
|---|---|---|
| `GET /student/home` | `StudentHomeProjection` | `current_task`、`task_queue`、跨已授权课程的到期 `due_reviews`、`next_actions[0..2]`、`attention_item[0..1]`、`recent_activity`、四态 `progress_decision` |
| `GET /student/learning/tasks/{task_id}` | `LearningWorkspaceView` | task/version、blocks、allowed_actions、context_refs、completion、CurrentLearningTask/TeachingSession/Episode runtime refs；刷新恢复并重新鉴权 |
| `POST /student/learning/tasks/{task_id}/respond` | `respond_task` | `action=respond_task`、task version、response；版本冲突 409，最多一个教学动作 |
| `POST /student/learning/tasks/{task_id}/pause` | `pause_task` | `state_version`；只允许 active→paused，保留原任务上下文 |
| `POST /student/learning/tasks/{task_id}/resume` | `resume_task` | `state_version`；只允许 paused→active，版本冲突 409 |
| `GET /student/growth/overview` | `GrowthOverviewView` | focus、状态汇总、到期复习 attention、freshness、explainability refs；不下发原始正确率 |
| `GET /student/growth/knowledge` | 知识状态列表 | knowledge point、状态、state_reason、algorithm_version、evidence_count、next_step、updated_at；不下发原始正确率 |
| `POST /courses/{course_id}/learning-evidence/{evidence_id}/invalidate` | 失效一条学习证据并重算掌握投影 | Teacher；记录理由和审计；重复调用幂等；不删除原始证据 |
| `GET /student/growth/tabs` | `GrowthTabsView` | 知识、技能、误区、轨迹四个可解释投影；不下发原始正确率 |
| `GET /me/notifications` | `Notification[]` | 当前用户的站内通知，可按 `unread_only` 过滤 |
| `POST /me/notifications/{notification_id}/read` | `Notification` | 当前用户通知标记已读；重复调用幂等 |
| `GET /student/cases` | `CaseSession[]` | 当前课程案例推理会话，案例快照由服务端固定 |
| `GET /student/cases/catalog` | 案例类型目录 | 服务端固定五类实验推理模板，不返回评分规则 |
| `POST /student/cases` | `CaseSession` | 创建受限案例快照，不接受客户端提交评分规则 |
| `POST /student/cases/{session_id}/respond` | `CaseSession` | 选择、文字推理与设计调整共同评分；资格化保持 pending |
| `GET /review-tasks?due_only=` | 到期复习任务与不含答案的题目快照 | 只返回本人任务；状态、版本和资格化状态由服务端提供 |
| `POST /review-tasks/{task_id}/verify` | 延迟复习验证 | 到期、版本和服务端题目版本校验；写入 `review` 原始事件后由 Qualification 生成 retention Evidence |
| `GET /courses/{course_id}/interventions/{intervention_id}/effect` | `InterventionEffectView` | 执行/完成/已测量数量与明确的效果测量边界 |
| `POST /courses/{course_id}/classes/{class_id}/members` | `ClassMember` | 将已加入课程的学生加入独立班级 Scope |
| `GET /courses/{course_id}/classes/{class_id}/members` | `ClassMember[]` | 教师/助教读取当前班级学生，按稳定姓名和 ID 排序 |
| `GET /student/growth/knowledge/{kp_id}` | 知识详情 | Evidence Coverage、为什么这样判断、可执行下一步 |
| `GET /student/practice` | Practice Read Model | 推荐训练、实验推理、Mini Lab、正式测评入口 |
| `POST /chat/sessions/{id}/branches/{branch_id}/merge` | `merge_branch` | merge key、用户确认、结构化结论；未确认不得写主线 |
| `GET /me/memory` | 记忆摘要 | 只返回本人可见的连续性信息，不返回内部 Prompt |
| `GET/PATCH /me/preferences` | 显式学习与显示偏好 | 本人；乐观锁；只影响表示/站内提醒，不越过硬 Policy |
| `POST /me/privacy/delete-request` | 受理持久删除工作单并返回 `PrivacyDeletionReceipt` | 调用方必须预先生成 ULID 回执编号与 256-bit 状态凭证；账号立即停用/去标识并清除认证会话；Worker 单事务删除个人学习数据/偏好/通知/成员关系，完成后才返回 `completed_with_retention`；正式成绩、审计及课程资源列于 `retained_categories`，不得解释为全部删除完成 |
| `POST /privacy/deletion-status` | 无需登录，凭回执编号与调用方预生成的状态凭证核验 queued/running/failed/completed 状态 | 凭证只保存 SHA-256 哈希、30 天失效；无效/过期统一返回 404；响应 `Cache-Control: no-store`，不返回被删除账号身份且不会恢复登录权限 |
| `POST /privacy/deletion-status/retry` | 无需登录，凭相同状态凭证重派发 queued/failed 删除工作单 | 仅可重派发可重试单据；Worker 按请求编号行锁幂等，已完成任务不产生副作用；失败只暴露安全错误代码 |

前端在提交删除前生成并展示编号与凭证，用户确认已保存后才发送请求；因此即使服务端已提交受理但 HTTP 响应丢失，用户仍可用预先持有的两项值无登录核验或重试，不依赖仅凭可枚举回执编号重签秘密。`0042`/`0043` 产生且没有状态凭证的历史回执仍不能通过新接口核验。外部备份/生产索引擦除及机构保留规则不属于此本地工作单能力。

学生端不显示 Mastery 百分比、AI confidence、风险分数；状态使用“比较稳定、正在学习、建议复习、证据不足”。

## 4. 教材、Evidence 和 Reader

| 接口 | 作用 | 必须满足 |
|---|---|---|
| `GET /student/textbook` | 当前 CourseRelease 的教材目录 | 只读、绑定 release |
| `GET /student/textbook/pages/{page}` | 固定页/页面图 | page 属于当前 release，撤权后重新鉴权 |
| `POST /knowledge/search` | BM25/Dense/Fusion/Closure 检索 | 权限和版本过滤在召回前；不足时拒答 |
| `GET /evidence/{evidence_id}` | 读取短期 EvidenceTicket | 票据有效、用户有权、版本未撤回；同时返回其持久 `evidence_pointer_id` |
| `GET /evidence-pointers/{pointer_id}` | 按不可变来源快照恢复教材引用 | 不依赖短期票据；每次重新校验当前课程权限及该版本曾发布的快照，撤权/归档后拒绝；返回 excerpt 哈希、对象、页码、bbox 与明确坐标空间 |
| `GET /evidence/{id}/reader-target` | Reader 跳转目标 | 尚未实现；需绑定已发布 Release、固定页资产和经验证的坐标变换 |
| `GET /teacher/annotations` | 教师覆盖层 | 不能修改 Canonical Source |
| `GET /courses/{course_id}/teaching-assets` | 教师/Designer 查看课程资产版本 | 返回草稿、已发布和归档版本；不返回其他课程资产 |
| `POST /courses/{course_id}/teaching-assets` | 创建白名单 TeachingAsset 草稿 | 模板、动作、fallback、Evidence refs 经过服务端 Contract 校验 |
| `POST /courses/{course_id}/teaching-assets/{asset_id}/publish` | 将资产绑定已发布 CourseRelease | Publisher/Teacher；版本冲突 409；Published 不原地修改 |
| `GET /student/teaching-assets/{asset_id}` | 学生读取已发布资产 | 重新校验课程 Scope 和 Release 状态；不可用时 404 |

Evidence UI 必须能回答：支持哪一句、来自哪个版本和位置、如何打开原页。任何无定位依据的对象都必须明确标记“不支持精确引用”。

普通教师不得使用历史教材作者写入口：上传（单次与分片）、分片签名/记录/完成、解析、索引、知识对象修正、发布和归档写请求，在默认 `MATERIAL_LEGACY_AUTHORING_API_ENABLED=false` 时经课程 Scope 校验后返回 `410 LEGACY_MATERIAL_AUTHORING_DISABLED`；越权课程仍返回 404，不暴露资源存在性。仅会话创建者可取消本人遗留的未完成上传会话。该变量只可在隔离工程/测试环境显式开启；本门禁不是尚未实现的 Course Content Admin 编译工作台。

## 5. Teacher Read Models 与命令

| 接口 | 作用 | 角色 |
|---|---|---|
| `GET /teacher/overview` | Teaching Control Center | Teacher @ Course/Class |
| `GET /teacher/analytics` | 知识、实验能力、误区、复习和支持分组 | Teacher @ Course/Class |
| `GET /teacher/analytics/query` | 结构化学情查询 | 固定查询类型；不是开放聊天 |
| `GET /teacher/teaching` | Planned/Actual Timeline | Teacher/Assistant 按 Scope |
| `POST /courses/{course_id}/interventions` | 创建 Intervention Activity | Teacher；审计；绑定不可变目标快照 |
| `POST /courses/{course_id}/interventions/{id}/schedule|start|complete|evaluate` | 干预状态与效果生命周期 | Teacher；乐观锁；完成与效果评估分离，不直接写掌握度 |
| `POST /courses/{course_id}/interventions/{id}/dispatch` | 按课程有效学生创建 InterventionRun | Teacher；目标校验；重复派发幂等；版本冲突 409 |
| `GET /courses/{course_id}/interventions/{id}/runs` | 教师执行实例列表 | Teacher/Assistant；不返回学生私聊或记忆正文 |
| `POST /courses/{course_id}/observations` | 创建教师观察记录 | 必须带 `Idempotency-Key`；教师须为目标班级 lead，学生须在该班级；来源必须是该学生当前有效的 `LearningEvidence`；默认教师/助教可见，不向学生暴露正文 |
| `GET /courses/{course_id}/observations` | 查看教师观察与复核状态 | Teacher/Assistant；仅返回当前有效任课班级；可按 `pending/qualified/rejected` 过滤 |
| `POST /courses/{course_id}/observations/{id}/review` | 复核教师观察 | 班级 lead Teacher；乐观锁；接受只记 `review_decision=accepted` 并保持资格状态 pending，拒绝为终态；审计不覆盖原始作答 |
| `GET /courses/{course_id}/observations/{id}/revalidation-candidates` | 读取观察之后已通过学习 Qualification 的再验证候选 | Teacher/Assistant；仅本班级；只返回事件/资格化摘要，不返回学习事件 payload |
| `POST /courses/{course_id}/observations/{id}/revalidate` | 关联独立再验证资格 | 班级 lead Teacher；要求原复核 accepted、版本匹配、同学生同课程的既有 qualified LearningEvent、有效独立 Evidence、不同情境与知识点；同一事件重试幂等、不可复用于其他观察 |
| `GET /student/intervention-runs` | 本人待执行干预 | Student；重新校验课程 Scope |
| `POST /student/intervention-runs/{id}/start|complete` | 学生开始/完成执行实例 | 仅本人；乐观锁；完成不直接写掌握度 |
| `GET /teacher/assessment` | 题库、正式测评、评分队列 | Teacher/Designer 按资源权限 |
| `POST /teacher/assessment/releases` | 创建/锁定 AssessmentRelease | Designer 编制，Publisher 发布 |
| `POST /teacher/assessment/submissions/{id}/grade` | 教师成绩决定 | Teacher/评分权限；不可由 AI 直接写分 |

教师看到的每个问题都必须能回溯到样本口径、证据覆盖、状态解释和此前干预。

## 6. Course Designer、Publisher 和 Admin

| 工作区 | 目标接口组 | 不得做 |
|---|---|---|
| Course Designer | `/course-design/domain`、`/pedagogy`、`/assessment`、草稿 Release Pack 编辑 | 不得直接发布；不得修改 Canonical TextbookObject |
| Course Publisher | `/course-design/releases`、`publish` | 不得跳过 Gate、Diff、Impact Review |
| Admin | `/admin/overview`、`/access`、`/courses`、`/jobs`、`/audit`、角色授予/撤销、班级任课分配/结束与受控任务重试 | 班级任课只允许同机构课程中已入课教师/助教，由独立 `TeacherAssignment` 表达；变更需理由、幂等键，结束操作带版本并写审计/Outbox。任务重试仅限同机构、最新、明确可重试的教材解析/索引失败任务；不返回任务 payload/原始错误，也不因治理角色获得教学正文和学生私聊 |

发布动作必须冻结 Domain/Pedagogy/Assessment 三类版本，生成不可变 CourseRelease；失败构建不得替换 Last Known Good。

## 7. 正式测评和 Mini Lab

| 接口 | 约束 |
|---|---|
| `GET /student/assessments/{release_id}` | 只返回已发布、时间可用、当前学生有权的 AssessmentShellView |
| `GET /courses/{course_id}/assessments` | 学生仅获得本人进行中 Attempt 的 `current_attempt_id`，供页面刷新后恢复作答；教师和其他学生均不获得该 ID；测验列表与复习任务需独立加载 |
| `POST /assessments/{assessment_id}/attempts` | 创建或恢复本人进行中 Attempt；恢复只返回学生作答、答案版本和标记状态，不含标准答案 |
| `PUT /attempts/{attempt_id}/answers/{question_version_id}` | answer version、自动保存；服务端截止后拒绝并返回 `ASSESSMENT_CLOSED`，不采信客户端时间 |
| `PUT /attempts/{attempt_id}/answers/{question_version_id}/flag` | 已作答题目标记/取消标记；与答案共用乐观锁版本，仅本人、进行中且未截止时可修改 |
| `POST /attempts/{attempt_id}/submit` | 幂等提交、submission lock、服务端时间裁决 |
| `GET /attempts/{attempt_id}/result` | Result Visibility Policy；评分状态分离 |
| `GET /courses/{course_id}/grading-queue?include_graded=` | 仅课程教师可读的主观题待评分/历史队列；默认不暴露学生答案 |
| `GET /teacher/attempts/{attempt_id}/grading` | 当前课程教师 Scope 校验后读取作答、Rubric、不可变决定链和最新 ScoreRecord |
| `PUT /teacher/attempts/{attempt_id}/grading` | 全部主观题一次性评分；`expected_score_version`、幂等键和必填评分理由；覆盖必须带 override reason |
| `GET /student/labs/catalog?course_id=` | 返回服务端白名单实验定义；课程参数先做学生 Scope 校验 |
| `POST /student/labs` | 创建带不可变 definition snapshot 的运行会话，返回乐观锁版本 |
| `GET /student/labs/{session_id}` | 仅返回本人且有权课程的实验会话 |
| `POST /student/labs/{session_id}/result` | 校验 `mini-lab.v1`、固定六阶段顺序、定义快照和版本；服务端生成 DerivedMeasure 与待资格化事件 |
| `POST /student/labs/{session_id}/prediction` | Prediction 与实验数据分离 |
| `POST /student/labs/{session_id}/explain` | Explanation/Transfer 才可进入学习证据 |

Assessment AI Policy：`AI_SUPPORT_DISABLED`、`TECHNICAL_ONLY`、`DIRECTION_ONLY` 必须在后端执行。Mini Lab runtime 期间隐藏 Tutor、Evidence、Branch 干扰入口；中断按规则作废，不把反应时直接转成能力结论。

## 8. 学习事件与资格化

| 接口 | 当前状态 | 边界 |
|---|---|---|
| `POST /learning-events` | 已实现原始事件追加 | 必须有课程 Scope；`event_key` 按用户幂等；事件只写入 `pending`，不能直接改变评分、掌握度或记忆 |
| `GET /me/learning-events?course_id=` | 已实现本人事件查询 | 只返回当前用户和有权课程；按发生时间倒序；不返回他人事件 |
| Qualification → `LearningEvidence` | 正式测评、案例、Tutor 检查回合、Mini Lab 完整回合和到期复习验证已实现；证据包含维度、独立性、情境和质量状态；`mastery-v2-independent-context` 另要求跨2种情境及最低独立证据数 | 服务端先完成权威来源校验；教师观察复核不会覆盖原始作答或直接生成掌握度；MasteryState 保存算法版本/理由，失效后重算。Mini Lab 仍只有首个确定性 fixture，更丰富的跨情境验证活动仍待实现 |

客户端埋点不是教学事实。任何 Tutor、Assessment 或 Mini Lab 事件在进入 Learner Model 前都必须经过服务端资格化和可重算投影。
