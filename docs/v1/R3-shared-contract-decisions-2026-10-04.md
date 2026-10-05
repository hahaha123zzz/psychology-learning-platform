# R3 共享合同与协调决定（2026-10-04）

本文件由主协调窗口维护，消除 R3-A—G 的跨模块歧义。它是允许各窗口施工的边界，不代表相应 API、页面或验收已经完成。窗口只能按《V1 并行启动状态》中的明确 GO 行修改排他文件；共享模型、迁移、路由聚合、公共 fixture、OpenAPI 和总验收文档由主窗口维护。

## 通用合同

- 每个请求先解析用户身份、机构及课程/班级 Scope，再查找业务对象；无权访问返回统一 404。客户端角色或资源 ID 不构成授权。
- 带 `version` 的写操作要求 `expected_version`；过期返回 409，包含可操作但不泄露跨 Scope 信息的冲突摘要。列表稳定排序、分页游标不可重复或跳过同序项。
- 幂等命令按“调用者 + Scope + idempotency key”记录规范化请求摘要。同键同摘要重放原结果；同键异摘要返回 409。业务状态变化、幂等收据和审计记录必须在同一事务中提交。
- 已发布 Domain/Course/Rubric/Assessment/Activity 版本不可原地修改。撤回、替代、过期使用新状态/新版本表达；历史运行固定来源版本，读取时仍重新鉴权。
- 证据不充分用 `unknown`/`not_measured` 等显式状态表示，不靠缺字段推断成功。合成工程 fixture 必须标注，不能作为真实教材、科研效度或教学效果证据。

## R3-A：Domain Pack、误区审核、发布快照与 Claim

### 已由主窗口共享迁移实现

迁移 `0048` 新增 `DomainRelease`、追加式 `DomainReviewDecision`，并在 `CourseRelease`、`PublicationSnapshot`、`RetrievalUnit` 增加可空 `domain_release_id` 外键。历史记录保留 NULL，不做猜测式回填。`DomainRelease` 按课程递增 `version_no`、保存不可变 manifest 与 SHA-256；其状态为 draft/ready/published/deprecated。`DomainReviewDecision` 记录对象类型、稳定对象 key、决定、审核人、理由、证据引用和时间。

### 必须遵循的业务规则

- 候选误区可由具备课程设计权限的人编辑；审核必须由同 Scope、具备 publisher/lead 权限且不同于作者的人完成。拒绝或要求修改保留理由。未审核候选不能标成 canonical，也不能进入已发布 DomainRelease。AI 输出不能直接审核、晋升或发布。
- canonical 的含义是“已通过人工审核、进入不可变 published DomainRelease 的对象”，不代表普遍心理学真理。对象须包含可反驳的定义、适用条件、来源/EvidenceBinding 和稳定 key；缺来源或引用失效时 Gate 阻断发布。
- 发布时将 DomainRelease ID/hash 固定到 CourseRelease；成功解析/索引快照及 RetrievalUnit 也固定相同 DomainRelease。更换 DomainRelease、教材 PublicationSnapshot 或 Embedding 版本必须形成新快照/索引，不能让旧引用静默漂移。旧数据的 NULL 绑定仍按旧兼容路径解释，不伪称已版本绑定。
- Claim 状态精确使用 `supported`、`partially-supported`、`contradicted`、`unknown`。只有与主张同一对象、极性、范围/条件的明确反向证据才能是 `contradicted`；词面不匹配、未命中或证据不足一律不是反驳，默认为 `unknown`。部分支持必须指出支持与未支持的子主张。
- 最多一次补检索；第二次检索必须沿用同一用户、机构、课程/班级 Scope、DomainRelease、PublicationSnapshot、材料版本、索引任务、Embedding 版本及权限过滤，不得因补检索扩大资源范围或改用未授权发布版本。记录初次和补充证据、attempt=0/1、版本与最终四态；仍不足时保留 `unknown` 并拒答/降级。A 只实现 Domain/Knowledge 范围的校验与稳定读取/helper；Tutor 侧调用和回合落库归 B/主窗口，不得写 Tutor 文件。

### 尚未由 0048 实现

MisconceptionDefinition 的 schema 字段完善、候选编辑/独立审核 API、DomainRelease 发布/回滚服务、索引任务实际写入上述外键、Claim 判定与补检索集成/OpenAPI 仍需实现和验证。A 可在 GO 范围内先做 knowledge 模块与专属测试；共享 API 注册和 OpenAPI 由主窗口完成。

## R3-B：Memory、有效策略、Tutor、Branch 与 Planner

- 0048 已给 `MemoryItem` 增加 `provenance_level`（observed/inferred/explicit/teacher_confirmed）、`evidence_refs`、`valid_from`、`expires_at`、`review_after` 与冲突组/状态/理由/解决者/时间。旧 source_type 的迁移映射仅是来源等级的兼容估计，不是历史事实确认。过期记忆不得参与有效画像；`review_after` 只标记待复核，不自动晋升/降级；冲突双方保留，解决须有理由、权限和审计；记忆不能跨学生、课程或教师暴露正文。用户删除优先，删除状态/审计共享入口归主窗口，B 不改 `memory/router.py` 或隐私删除测试。
- 技能与误区的规范引用、稳定 ID 和晋升门槛依赖 A 的已审核 DomainRelease。A 合同发布前，B 可实现与 Domain 无关的来源时效、冲突、纯函数决策和迁移字段消费；不得创建伪规范技能/误区，也不得猜测引用。Domain 相关接口通过稳定 ID/服务合同衔接，不跨模块直接查询内部表。
- `effective_policy` 按最严格约束合并：系统/机构硬限制 > 当前正式测评限制 > 已发布 CourseRelease/教师策略 > 活动/干预附加限制 > 用户偏好。低优先级只能收紧，不能覆盖上层限制；未知策略 fail closed。每个 Tutor/Branch/题目教练入口使用同一解析服务并在回合记录有效策略版本/来源。
- Tutor Action 固定为 `diagnose`、`teach`、`check`、`hint`、`practice`、`summarize`、`pause`、`handoff`。support gradient 为 0—3，提示只能逐级增加且受三步预算上限约束；一次错误、自评或提示请求不能直接更改 mastery/memory。assessment 约束优先，禁止时不返回教学提示/答案。
- Branch merge 使用 0048 在 `ChatSession` 上的 merge key、规范化 payload SHA-256、结果 turn ID 和时间作为原子收据。相同 key+payload 重放相同回执；同 key 异 payload、已合并后不同 key、来源版本变化、跨用户/课程/模式或来源选区不匹配返回 409/404。只合并明确确认的学生文本/选定内容，不伪造 system 角色或 Tutor 结论；合并结果不能自动晋升记忆/掌握。B 可实现 `question_agent/**`、`tutor/**` 和新增专属测试，不改共享模型/路由聚合/OpenAPI。
- Planner 只读已发布且当前获授权的 Domain/CourseRelease、当前测评安排、有效 Evidence 与到期 ReviewTask；不得读未审核 Domain 候选或跨 Scope 记录。候选固定最多 5 项，预算/原因/来源可解释，输出 `continue`/`review`/`practice`/`handoff` 四态之一，不直接写掌握或任务状态。数据陈旧、证据未知、上游不可用或超时统一回 `continue` + 明确 safe fallback reason。

## R3-C：学生页面范围

实际活动的 Growth 与 Me 页面均位于 `web/components/StudentCourseSupportPages.tsx`；`StudentProfile.tsx` 是兼容/重定向入口，不可仅改它而遗漏真实页面。P5-07 的实际学习/SSE 页面包括 `StudentLearnPage.tsx` 与 `StudentLearningSession.tsx`。两者归 R3-C 独占施工范围；普通学生入口路由可由 C 在 `web/app/student/` 下修改，但不得碰评测、Branch、共享导航/API client/CSS 或其它窗口文件。

C 可实现 P5-04 案例工程行为、P5-06 Me/隐私透明呈现、P5-07 独立学习/SSE窄屏/键盘与恢复 UI。Growth 仅可解释现有真实状态、证据数、来源和下一步；在 B/A API 未提供时不得编造“技能”或规范“误区”状态。案例字段完整度评分必须继续标明不等同实验推理语义质量。UI 专用 API 调用可消费现有端点；新增共享字段/端点先交主窗口。

## R3-D：TeachingActivity/Run、Policy、Timeline、Annotation 与效果

- `TeachingActivity` 是课程 Scope 下不可变版本化教学活动定义；编辑生成新版本。`TeachingActivityRun` 固定 class、活动版本、CourseRelease/Assignment、目标集合摘要及发起人快照。状态 planned → ready → active/paused → completed/cancelled；禁止跳跃/复活终态。写操作用 expected_version + 幂等键。
- Planned Timeline 来自活动/干预计划记录；Actual Timeline 仅来自带 occurred_at 的持久业务事件，并显示来源与延迟。预计/实际不得合并成一个“已完成”状态；排序按时间再稳定 ID。
- Course Policy 是已发布 CourseRelease pedagogy 的不可变片段，仅可附加更严格教学/隐私约束。教师个人活动可添加覆盖层，但不得使正式测评、机构政策或用户权利更宽松。
- `TeacherAnnotation` 是教师对授权课程/班级活动的独立 overlay，包含目标对象、理由、作者、时间和版本；不改学生原始证据、作答、Domain canonical 或私聊。默认仅教师 Scope 可见，学生可见须显式允许且记录发布状态；不存不必要的敏感心理评断。
- 统计仅在授权 class Scope 内聚合；窗口使用半开 UTC `[start,end)`，默认最近 30 天、最长 90 天。有效独立学生样本 `n < 5` 时只显示“样本不足”，不显示人数、百分比、排行或可反推单人的分组；禁止小组排名。
- 干预派发时冻结目标成员集合/快照，退出班级不改变历史目标。干预完成不等于有效果；Immediate recheck 与 7—30 天 delayed recheck 分开。每个窗口至少两项合格、独立且跨情境测量才可计算描述性变化，否则为 `not_measured`。非随机/无比较组不得宣称因果效果。机构保留政策未提供，不能自定物理删除期限。

## R3-E：Rubric、测评用途、结果可见与 AI 评分边界

- `RubricVersion` 对应不可变题目版本，记录标准项、分值上限、判断锚点与依据；`AssessmentItem` 必须固定指定 RubricVersion。新题/题目版本默认仅 practice；进入 formal 必须经有权教师显式批准用途及 rubric/evidence gate。
- Assessment purpose 明确为 `practice` 或 `formal`，不能由页面入口或分值推断。草稿默认不发布。
- 结果可见策略枚举 `immediate_after_submission`（仅 practice）、`after_close`、`after_grading`、`manual_release`。Formal 默认 `after_close`（客观题）或 `after_grading`（含人工评分题）；旧数据没有策略时 fail closed，不能立即泄露答案/评分细节。每个学生请求由服务端按锁定策略授权，不信任 UI。
- `AIGradingSuggestion` 当前关闭：本轮不建可调用外部模型的评分路径，不发送学生答案、标准答案或敏感评分依据，不把模型文本存成评分建议。只有获得机构政策、学生答案/题库使用授权、获准 rubric/参考答案与供应商不留存/不训练承诺后，主窗口方可另行审批启用。若将来启用，建议必须独立、可撤销/过期、明确模型/提示版本，由教师作最终评分；永不自动写 ScoreRecord、LearningEvidence、Mastery 或反馈结论。

## R3-F：Designer Review/Preview/Diff/Gate/Impact/Publisher 与换版

- Preview 是只读渲染，绑定精确草稿 ID/version/hash 和授权 Scope；不执行任意脚本、不写学习/评分状态。
- Review 是追加式签核，记录 reviewer、角色、时间、理由、对象版本/hash；作者不可自审通过，过期/版本变化使 review 失效。Diff 只比较两个不可变快照，并展示新增/删除/字段变化与引用断裂。
- Gate 为确定性 ERROR/WARNING 清单：ERROR 阻断发布；WARNING 可在审计留理由后继续。Impact 仅返回达到最小样本门槛的聚合影响，不暴露学生原始答案、记忆或小群体结果。
- Publisher 需 `course_publisher` 对应 Scope、expected_version、幂等键、通过的 Gate 和 WARNING 理由；同键重放原发布回执，过期版本 409。发布固定 CourseRelease manifest/hash，不覆盖旧版本。
- `CourseReleaseAssignment` 绑定 class + immutable CourseRelease + 版本/指派人/时间/状态。每个班级最多一个当前 assignment；换版先关闭旧 assignment，再建立新 assignment，保留历史。新 Study/Assessment/Activity Run 固定开始时 assignment/release；运行中不漂移，换版只影响新任务。撤回/归档阻止新任务，但旧任务读取仍针对旧对象重新鉴权。
- R3-F 可先改善已有 Designer 页面和真实 API 的只读 Review/Diff/Gate 信息结构；创建/发布/换版按钮必须等主窗口实现相应服务/API、OpenAPI 和根测试后再接通，不得用静态 mock 冒充上线能力。

## R3-G：Mini Lab 作废/恢复与 TeachingAsset fallback

- 0048 已在 `MiniLabSession` 增加作废幂等 key/hash、作废者/时间/理由字段。仅运行中 session 可作废；须携带 expected_version、key 与理由。相同 key+payload 重放原结果；同 key 异 payload 或并发版本冲突为 409。完成态不可伪装成作废，作废态不可恢复、续写、提交或进入 qualification。只有服务端确认的阶段 checkpoint 可恢复；未确认试次明确显示“未保存”，不得计入数据。作废不发 `lab_trial_completed` 或任何完成资格事件。
- TeachingAsset 的 `fallback_text` 是纯文本 fallback，永不作为 HTML/JS/可执行表达式渲染。客户端按能力/模板白名单降级并返回稳定 reason code；UI 告知“当前设备/模板无法呈现交互内容，已切换纯文本说明”，不得声称与原交互等价。未知模板必须安全 fallback 并记非敏感诊断原因；不回退到不安全或跨 Scope 的资产。
- `engineering_fixture` 标记贯穿定义、运行记录和 UI；它只支持工程测试，不是教材、心理实验或科研效度结论。最终 2—3 个实验和教材图表继续等待授权材料，不阻塞通用作废/恢复/fallback 工程代码。

## 当前实现分层

## R3 模块 API 草案（与 0049 schema 对齐）

以下 URI 均相对 `/api/v1`，所有响应继续使用统一 `{data, meta}`/`ApiError` envelope；窗口实现模块内 router/service/schema，主窗口负责新增 router 注册、OpenAPI 快照和公共 fixture。若现有路径实现与此有冲突，先在共享本文件留下兼容决定，不得另造一套错误/幂等语义。

- D：`GET/POST /courses/{course_id}/teaching-activities` 列表/创建 draft；`PATCH /courses/{course_id}/teaching-activities/{activity_version_id}` 仅可修改 draft 且带 expected version。`POST/GET /courses/{course_id}/classes/{class_id}/teaching-activity-runs` 创建/列表运行，创建必须固定 activity version、班级 roster snapshot、当前 CourseReleaseAssignment 和 Release；`POST /courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run_id}/actions` 接受 `start|pause|resume|complete|cancel` + expected_version。`GET /courses/{course_id}/classes/{class_id}/timeline?start_at=&end_at=` 使用半开 UTC 窗；`POST /courses/{course_id}/classes/{class_id}/teacher-annotations` 与 `PATCH /courses/{course_id}/teacher-annotations/{annotation_id}` 创建/修订 overlay。所有端点先验证 class Scope；Timeline payload 不含私聊、记忆、原始答案。
- D 的现有 `/courses/{course_id}/interventions/{intervention_id}/effect` 是一个独立兼容端点：只接受 class-bound intervention 且教师具有该 class Scope；`start_at/end_at` 默认为最近 30 天、最大跨度 90 天、半开 UTC。唯一学生样本 `n<5` 时所有精确 count/rate 返回 null 并标 `suppressed_small_sample`。JSON `immediate_check`/`delayed_check` 只是非结构化记录，效果状态保持 `not_measured`，除非能关联到至少两项合格、独立复测；任何非实验设计均不得声称因果。
- E：在 assessments 模块实现 `GET/POST /courses/{course_id}/question-versions/{question_version_id}/rubrics`、`POST /courses/{course_id}/question-versions/{question_version_id}/purpose-approvals`、现有 Assessment create/update/publish API 的 `purpose`/`result_visibility_policy`/Release assignment 校验，以及学生结果读取门禁。Formal 发布要求当前有效人工 formal-purpose approval 与 approved RubricVersion；Practice 默认 `immediate_after_submission`，Formal 客观题默认 `after_close`、含人工评分默认 `after_grading`。Manual release 必须记录 authorized actor/time；学生看到什么由服务端策略判断。API 字段缺省/null 时 fail closed。禁止新增 AIGradingSuggestion、模型服务调用或外发学生答案。
- F：现有 CourseRelease API 保持草稿读写；待主窗口实现下列共享服务后，F 再接入相同名字的真实 API：`GET /courses/{course_id}/releases/{release_id}/preview`（只读精确版本）；`GET /courses/{course_id}/releases/{release_id}/diff?against_release_id=`；`POST /courses/{course_id}/releases/{release_id}/reviews`；`GET .../{release_id}/gate`；`GET .../{release_id}/impact?class_id=`；`GET/PUT /courses/{course_id}/classes/{class_id}/release-assignment`。Review append-only 且 reviewer 与 author 不同；Gate 报告 deterministic ERROR/WARNING；Publisher 使用既有 `POST /.../{release_id}/publish` 扩展幂等 key、expected version 与 WARNING 理由；Assignment 更新要在单事务内关闭旧 assignment、创建新 assignment，旧 Activity/Assessment run 固定旧版本。主窗口负责这些共享端点/权限/服务和 OpenAPI，F 不得自行 mock 写通路。

## 2026-10-05 主窗口 Domain 快照落地合同补充

- CourseRelease 草稿请求新增可选 `domain_release_id`。给出已发布且同课程 ID 时，服务端从 DomainRelease 不可变 manifest 取规范 Domain Pack；请求若同时带非空 Pack，必须与该快照完全一致，否则 `409 RELEASE_DOMAIN_SNAPSHOT_MISMATCH`。不同课程、未发布或不存在统一 fail closed 为 `409 RELEASE_DOMAIN_SNAPSHOT_INVALID`。切换 DomainRelease 是 draft 的版本化更新，递增 `CourseRelease.version`，旧 Review 因版本/hash 改变自动失效。结构化 Domain Pack 未绑定 DomainRelease 时可保留为不可发布草稿，Gate 返回 `RELEASE_DOMAIN_SNAPSHOT_REQUIRED`。
- 教材 `material-embed` Job 的 `payload.domain_release_id` 是索引来源事实；材料发布可带同一 `domain_release_id` 选择对应成功 Job。`PublicationSnapshot` 必须保存同一 ID、material version、成功 index Job、Embedding version，并确认当前 DomainRelease 下属于该 Job 的 `ready RetrievalUnit` 已存在。CourseRelease Gate 在事务内检查 CourseRelease Domain ID/Pack 与 DomainRelease、当前材料 PublicationSnapshot、Job payload、RetrievalUnit 同 ID；任一缺失或不相符均阻断发布。当前不复制 DomainRelease hash 到第二列，CourseRelease manifest hash 纳入 `domain_release_id`，其不可变 `pack_sha256` 通过外键对象读取。
- **R3-A 下一步响应字段合同：** `/knowledge/search` 返回 `domain_release` 时补 `publication_snapshots` 数组，每项为 `{material_id, material_version_id, publication_snapshot_id, index_job_id, embedding_version, domain_release_id}`；只返回经 Scope/发布权限过滤后的快照。允许的 `index_job_ids` 不可替代 PublicationSnapshot ID。A 在 `knowledge/**` 内补字段及测试，不改共享模型/课程/材料/Tutor文件。
- **R3-B Tutor Claim 持久合同（现在可施工，Domain 搜索字段由 A 补齐后接通）：** 在 `TutorTurn.verification` 保存 `claim_status` (`supported|partially-supported|contradicted|unknown`)、`scope`、初始与补检索证据的稳定 evidence IDs/pointers、`supplemental_retrieval_attempts`（只允许 0 或 1）、`refusal_reason` 和 Domain/Course/Publication/Index/Embedding 版本。Scope 固定包括 `user_id`、`organization_id`、`course_id`、适用时的 `class_id`、分配的 `course_release_id`/`course_release_assignment_id`、`domain_release_id` 与按材料列出的 PublicationSnapshot/MaterialVersion/IndexJob/EmbeddingVersion。补检索前后规范化 Scope 必须完全相同；不得持久化不必要的证据正文或突破权限读取其他版本。unknown/拒答为安全降级；不改变评分、Mastery、Memory 或发布状态。B 只改 Tutor/Planner/Memory service 与专测。
- **历史版本边界：** 当前 material 发布表保留被 supersede 的 PublicationSnapshot 行，但 Domain Gate 只接受当前快照，尚未给旧 CourseRelease/Assignment 的学生检索实现按 snapshot ID 回放的公开路径。因此本轮只确认“新发布版本不可混索引”，不宣称旧 Assignment 的历史检索链已完成；主窗口后续需将 CourseReleaseAssignment → Run/Study/Assessment → 固定快照 → Search 请求做端到端验收，缺该链时继续标为未验收，不允许检索静默漂到当前最新版本。

## 2026-10-05 课程版本运行与证据归因合同补充

- 新增迁移 `0050_bind_learning_runs_to_release_assignments.py`：`LearningSession`、`Attempt`、`LearningEvidence` 各自增加可空 `course_release_assignment_id` 与 `course_release_id`，并增加 FK、查询索引及“二者同时为空或同时非空”的数据库约束。已存在历史行保持 NULL；不得根据当前班级指派或现行材料版本猜测回填。
- 新建学习会话/Attempt 时，模块服务应在当前用户实际班级 Scope 中解析唯一有效的 `CourseReleaseAssignment`，校验 assignment 所指 CourseRelease 当前可供新运行，并在同一事务把 assignment ID 与 release ID 写入运行记录。若存在多个适用班级/版本且 API 没有明确 class context，必须 fail closed（建议 `409 COURSE_RELEASE_CONTEXT_AMBIGUOUS`），不得任取第一条。已进行中的 Attempt/学习会话恢复时沿用其既有绑定，绝不跟随后续换版。
- ReleaseAssignment 变更只影响新运行。历史 Run/Attempt/Evidence 保持原 assignment/release 关联；旧指派的阅读/取证仍须逐次重新鉴权，`deprecated` 或 revoked 不代表绕过权限。没有 assignment 的旧兼容运行只可继续留空，不纳入 Release Impact 样本。
- 新建 LearningEvidence 应复制来源 Attempt 或学习会话的 assignment/release ID。Impact 只有在同一 class 的有效证据可稳定连回该 assignment、release、合格事件及定义好的时间窗时才可计算；任一关系缺失仍返回 `not_measured`，不得用当前指派反推历史证据，也不得作因果结论。
- **施工边界：** 主窗口独占 models/Alembic/OpenAPI。R3-B 可在 `tutor/**` 与获准 memory/service 专测接入 LearningSession + LearningEvidence 的字段；R3-E 可在 `assessments/**` 接入 Attempt；D 的 `TeachingActivityRun` 已有 assignment/release 两字段，只需保留创建时冻结语义。F 仅消费只读接口。所有窗口在 0050 隔离迁移结果写入共享状态前，不得依赖或声称新列已在其专库可用。

## 2026-10-05 Tutor ChatSession 固定课程版本补充（0051）

- **原因：** B 已交付 `verify_domain_claim_for_tutor` adapter 和 Claim 持久化格式，但活动 Tutor SSE 路由尚未构造/传入其上下文。`ChatSession` 原 schema 没有 assignment/release 字段；若只在每个 turn 动态读取“当前指派”，班级换版会令同一对话的发布 Scope 漂移，无法满足补检索同 Scope 与版本固定合同。
- **共享 schema：** `0051_bind_chat_sessions_to_course_releases.py` 在 `chat_sessions` 新增 nullable `course_release_assignment_id`、`course_release_id`、FK（RESTRICT）、查询索引及成对空值约束。历史会话保持 NULL，不根据当前 assignment 回填。`class_id` 由不可变 assignment 关联解析，不在 ChatSession 重复存储。
- **新会话解析：** 仅学生新建的 ChatSession 可固定当前 assignment；必须按该学生实际 active `ClassMember`、active `CourseClass`、同课程 active `CourseReleaseAssignment` 和新运行可用的 published `CourseRelease` 解析。无适用 assignment 时两列均留空，维持旧兼容路径；唯一适用 assignment 同事务写入两个 ID；多班级有多个适用版本且请求未显式指定班级时 fail closed（沿用 `409 COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS`）。教师/助教会话不推断学生班级。
- **Tutor 检索：** 绑定会话的 turn 必须从固定 CourseRelease manifest 取允许的 `material_version_ids`，按其 `domain_release_id` 选择 A 返回的同版本 `publication_snapshots`，并将 `class_id`、assignment/release、DomainRelease、每个 PublicationSnapshot/material version/index Job/embedding version 纳入完整 Claim Scope。初始与最多一次补检索只可使用该固定快照集合；空快照、失效/不匹配或中途版本漂移须 `unknown` + 拒答，不得回退到当前版本/不绑定检索。TutorTurn verification 只持久化稳定 evidence IDs/pointers、四态、Scope、版本、次数和拒答原因，不持久化不必要正文。
- **恢复/兼容：** 新 turn 读取 session 已固定的 ID，不重新解析“当前 assignment”；已绑定会话允许读取对应 `published|deprecated` CourseRelease 的不可变 manifest，但仍逐次重验当前用户、课程/班级成员资格及资料可读权限。被撤权或不再有班级 Scope 时统一 404。历史 NULL 会话和无 assignment 新会话继续现有非 Domain 行为，禁止冒称已固定历史版本。
- **B 的排他施工 GO：** 仅 `server/app/modules/tutor/**`、B 获准的 `memory/service.py`、B 专测与 `docs/v1/r3-preflight/R3-B.md`。实现 ChatSession 创建时解析/固定；活动 turn 的 Scope 与快照检索、Claim adapter 接线和 SSE/数据库回归；含 assignment 换版、跨班、无快照、旧 NULL 兼容、同 key 重放不重算。不得改 models、迁移、knowledge/materials/courses、共享 router/OpenAPI/conftest、隐私 router/Audit 或前端 Branch UI。主窗口负责所有 schema/迁移/OpenAPI 及跨模块集成测试。
- **外部边界：** 学生真实课程材料/机构授权仍未提供；本合同只允许在隔离合成资料上验收，不能启用外部模型发送教材或学生答案，也不等于真实教学验证。

## 2026-10-05 CourseRelease 固定教材发布快照补充

- **课程版本清单：** `CourseRelease.manifest` 的 `materials` 顺序与下列数组一一对应：`material_version_ids` 和 `publication_snapshots`。每个快照包含 `material_id`、`material_version_id`、`publication_snapshot_id`、`index_job_id`、`embedding_version`、`domain_release_id`。新草稿创建时只绑定当前 active、published 材料的完整 PublicationSnapshot；未发布材料可暂存为草稿选择，但不会伪造版本映射，Gate 必须阻断。数组长度、顺序、ID、外键对象及所有版本字段不匹配均 fail closed。
- **更新/发布：** 创建草稿时捕获当前快照；只有 PATCH 显式提供 `material_ids` 才重新选择并刷新两组 pin。名称、Pack 或 DomainRelease 修改不得静默更新教材快照。新发布 Gate 要求每个 pin 仍是当前 active/published 材料的当前 PublicationSnapshot、其索引 Job 成功且版本 payload 一致；快照发生轮换时必须显式重新选择，递增 Release 版本并重新审核。严格 Publisher 只消费 Gate 校验过的 manifest 映射，不动态查询“最新快照”覆盖清单。
- **运行期历史固定：** 已发布 CourseRelease/Assignment/ChatSession 等运行引用只能读取其 manifest 中精确的 `publication_snapshot_id` 和对应 MaterialVersion/IndexJob/Embedding/DomainRelease，不得因材料重新发布而漂移到最新版本。历史 PublicationSnapshot 的 `superseded_at` 与历史 DomainRelease 的 `deprecated` 本身不使不可变快照失效；每次读仍须重新核对机构/课程/班级/用户权限、Material 当前 active/published 状态和指定快照的完整关联。若材料归档/撤回、快照缺失、索引 Job 版本不符、权限撤销或 RetrievalUnit 不属于该快照，返回 unknown/拒答；禁止回退到其他版本。只有显式撤销权限或资料撤回才影响既有绑定的可读性。
- **旧草稿/兼容性：** 旧 CourseRelease 缺少 pin 时 Gate 返回 `RELEASE_MATERIAL_SNAPSHOT_REQUIRED`；教师显式重新选择材料后创建 pin、递增版本并重新审核。历史 NULL ChatSession 保持旧兼容，不回填当前版本。
- **覆盖证据：** 主窗口 `test_r3_release_workflow.py` 新测已验证 API 创建快照 pin、快照被 supersede 后 Gate 阻断、名称编辑保留原 pin、显式重新选择刷新 pin（隔离库结果 6 passed）。R3-B 需在 Tutor 专测补充“真实发布快照正向读取”：固定 Release 1 的 snapshot；发布/切换到 Release 2 后，将 Release 1 DomainRelease 标为 deprecated、PublicationSnapshot supersede；旧 Assignment 的 Tutor Claim 仍只能读 Release 1 snapshot/索引且同 Scope；材料撤回或 membership 撤权应拒答/404。其报告目前仅覆盖换版后 fail-closed，尚未证明历史快照正向读取，不可宣称完成。

## 当前实现与验收层级

迁移 `0048` 已在 R3-A 隔离库验证；迁移 `0049_r3_teacher_activity_assessment_release.py` 已在新的 root 共享隔离数据库全历史升级至 `0049 (head)` 并通过 `alembic check`。0049 现在具备 D/E/F 的共享表与 Assessment/Rubric/ReleaseAssignment 字段；模块 API 与验收仍按下列最新主窗口记录和并行状态文件区分，不能由 schema 或 GO 推导完成。

## R3 主窗口新增实现记录（2026-10-04）

- F 的共享 `courses` 路由已新增真实只读 Preview、已发布快照 JSON Diff、确定性 Gate、追加 Review、Impact 和当前班级 ReleaseAssignment 读写；CourseReleaseAssignment 换版通过 expected_version 与 `Idempotency-Key`，同事务关闭旧指派并新增不可变版本绑定。Preview 返回 manifest SHA-256；Diff 只接受 published/deprecated 快照。Review 使用不可变 `AuditLog` 记录 reviewer/角色/理由/版本/hash，作者不能自审，过期/改版 Review 不参与 Gate。
- **2026-10-05 合同更新：** CourseRelease `/publish` 仅接受带 `expected_version` 的请求体；需课程 `course_publisher` Scope、当前 manifest hash 的非作者审核通过、Gate 无 ERROR、WARNING 时提供审计理由，并携带 `Idempotency-Key`。重复键返回原回执，版本陈旧为 409。无请求体 legacy 调用稳定返回 `422 RELEASE_PUBLISH_REQUEST_REQUIRED`，OpenAPI requestBody 标为必需；旧绕过分支已移除，新增回归覆盖。Publisher 的权限与门禁旁路关闭，但 Designer/Publisher 浏览器工作流、Impact 与 assignment 证据版本绑定仍未完成，整体发布工作台保持**部分验收**。
- Release Impact 有班级/历史指派权限和小群体保护，但当前 LearningEvidence 未绑定 CourseReleaseAssignment，故 endpoint 明确返回 `not_measured` 和 `RELEASE_NOT_BOUND_TO_QUALIFIED_LEARNING_EVIDENCE`，不计算版本效果或作因果归因。
- 主窗口新增 `server/tests/test_r3_release_workflow.py`，覆盖作者自审拒绝、审核 hash/版本失效、审核与严格发布幂等、immutable diff、Assignment 换版/重放和 Impact 小组抑制。Release/课程/测评定向回归共 **31 passed**（独立数据库 `psychology_learning_v1_r3_release_tests_20261004`、Redis DB11）；前端 Node **46/46**、TypeScript 通过，ESLint 0 errors/3 个既有 hook warnings。全量后端回归本轮仍在运行，结果以随后 acceptance checkpoint 为准。
- R3-E 当前共享工作树已出现 Rubric/用途相关 assessments 路由并由主窗口导出到 OpenAPI；R3-D TeachingActivity 新模块路由尚未出现在 OpenAPI。窗口代码仍是未提交共同工作树内容，必须在各自独立库完成 module 专测/报告，主窗口再据报告审查集成。没有跨对话消息工具，细分范围与资源广播写在 `V1并行启动状态.md`。
