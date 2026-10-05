## R3-A

- **现状与缺口：** Domain Pack 的基础结构、图关系/先修环和发布前 EvidenceBinding 校验已在 `courses/service.py`；但 Misconception 仍只有基础字段和知识点/证据引用，缺少完整定义、审核者/时间/状态及 Canonical 候选边界。`CourseRelease` 有不可变 manifest，`PublicationSnapshot` 绑定教材版本、索引任务与 Embedding 版本；尚无 DomainRelease 标识/摘要与索引 manifest 的不可变绑定。Tutor `verify_claims` 目前用词项重合给出 `supported`、`partial`、`not_found`，没有 `contradicted`，兜底是对原证据包重新生成而非补检索。
- **拟修改文件：** GO 后限于 `server/app/modules/knowledge/**` 及获分配的 Domain Pack、检索、Evidence 专项测试。预期实现位置为新增 Domain Pack/DomainRelease/Claim helper 模块，并按契约调整 knowledge `service.py`、`router.py`；拟覆盖 `server/tests/test_domain_pack_graph.py`、`test_domain_pack_validation.py`、`test_search.py` 与新增的 knowledge 专项测试。当前 `knowledge/router.py`、`knowledge/service.py`、`test_search.py` 有既存未提交改动，Domain Pack 两个测试文件目前未跟踪；均须保留并在 GO 后复核归属。
- **需要主对话处理的共享接口、模型、迁移或 fixture：** 请主对话决定用独立 DomainRelease 模型/表，还是在既有 Release/Publication manifest 中保存 `domain_release_id`、`domain_pack_sha256` 与索引绑定；如需字段、约束或审核状态持久化，由主对话修改 `models.py` 并新增向前迁移。需确定 Misconception 候选/审核/Canonical 字段和动作 API、发布门禁、错误与 409 语义；主对话负责路由注册、OpenAPI、公共 fixture。Claim 可先存现有 `TutorTurn.verification` JSON；如需独立审计模型，请主对话定 schema。R3-B 持有 `tutor/**`，需接入 A 提供的四态校验与一次补检索接口；A 不修改 Tutor 文件。R3-F 依赖 Domain API 与 CourseRelease 发布合同。
- **所需独立数据库、Redis 和端口（仅需求，不自行分配）：** 需要一个本窗口专属、可清表迁移的 PostgreSQL 测试数据库；专属 Redis logical DB 与独立 Celery queue；如需真实 API 集成，需独立 Web/API 端口。状态文档当前预留为 `psychology_learning_v1_r3_a_20261004`、`redis://127.0.0.1:6379/3`、queue `v1-r3-a`、bucket `v1-r3-a`、Web/API `3210/8210`。本次只读现场核验：数据库可连且 `public` 表数为 0，Redis PING 成功且 0 keys，bucket 存在，3210/8210 无监听；GO 前仍需复核并使用配置显式锁定这些资源。
- **风险、依赖和无法确认的事项：** 当前状态文档 R3-A 仍为 HOLD、GO 总项为 NO；旧 R2/A/B/C/D GO 不适用。HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04` 与 R3 状态记录一致；状态记录基线指纹为 `17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`，但本次没有独立重建该 696 条记录指纹，须由主对话在 GO 前复核。Claim 四态要求分别校验事实支持、部分支持、证据矛盾和未知；补检索必须最多一次，且固定原用户权限、课程及发布版本，仍不足时降级/拒答。词面重合不能可靠判定事实矛盾，需明确确定性判据和审计合同。真实心理学误区质量评测依赖获准教材/证据；合成 fixture 只能验工程规则。未运行测试、迁移或服务。
- **建议：HOLD。** 报告完成不等于 GO；等待主对话复核共享合同、当前基线和文件归属，并在并行状态文档明确将 R3-A 标为 GO 后再实施。

## 历史重复报告：R3-B（原误标 R3-X；保留原文）

本节对应 R3-B：P3-03/05、P4-02/03/05/06（memory、tutor、question_agent）。这是 GO 前只读准备报告，不代表获准开工。

### 现状与缺口

- P3-03：`MasteryState` 只按知识点聚合，已有证据数、算法版本和理由；Growth 投影中的“技能”仍复用知识点状态，“误区”从粗粒度 Memory 文本临时映射。缺独立技能/误区状态、规范领域对象引用及各自的证据晋升/失效规则。
- P3-05：`MemoryItem` 当前有 L1/L2/L3、粗粒度 `source_type/source_ref`、置信度、stale 与替代关系。缺 observed/inferred/explicit/teacher-confirmed 来源等级、证据引用、有效期/复核时间、冲突解决和完整状态合同。已读到的写入路径由测验提交生成候选；没有看到 Branch 写入 Memory 的路径。
- P4-02/03：进行中正式测评的 AI 支持已有 fail-closed 检查，并由多处 Tutor/Branch/题目教练入口调用；目前没有 System、Assessment、Teacher、Intervention、Preference 的统一有效策略解析。Tutor 有服务端状态机和静态提示阶梯，但缺固定 Action schema、完整诊断状态及可审计的 support gradient/提示预算合同。
- P4-05：Branch 有独立会话和选区字段；当前合并接收自由文本并自动选取分支最近 Tutor 回答，没有计划中的结构化类型、显式确认和可重放 `merge_id` 合同。当前重复合并返回 409。创建路径还需补验来源回合和选区绑定。
- P4-06：Planner 目前只按当前任务状态和到期复习数量输出四态、理由和固定 `continue` fallback；没有已发布候选/先修图/预算的完整合同，也没有 Planner 专项测试。

### 拟修改文件

- `server/app/modules/memory/service.py`、`router.py`：状态/记忆领域规则与投影；`router.py` 同时承载管理员和隐私删除路径，任何实施须精确保留共同基线已有改动。
- `server/app/modules/tutor/service.py`、`router.py`、`planner.py`：统一策略消费、动作/提示规则、Planner 决策。
- `server/app/modules/question_agent/router.py`、`service.py`：Branch 来源校验、结构化合并和幂等回放。
- 对应回归：`server/tests/test_mastery_memory.py`、`test_mastery_rules.py`、`test_tutor.py`、`test_question_agent_branches.py`；可新增纯函数 Planner 专项测试。

上述目标文件在准备检查时已有未提交修改或未跟踪状态；这不是可覆盖的授权。工作开始前必须按 R3 实际基线重新核对 `git status` 和逐文件归属。

### 需要主对话处理的共享接口、模型、迁移或 fixture

1. P3 状态/Memory：确认稳定 Domain/KnowledgePoint 引用、技能/误区状态和算法解释字段；确认 Memory 的来源等级、证据引用、有效期、复核、冲突与替代字段，以及旧数据映射和删除边界。预计涉及 `server/app/db/models.py` 和新 Alembic 迁移。P2-04 的规范误区对象/审核状态是上游合同。
2. P4-02：请主对话定义可调用的 `effective_policy` 解析接口、优先级和不可覆盖的硬限制。现有 assessment policy helper 只处理进行中 Attempt。若 Teacher/Intervention 策略需持久字段，模型和迁移由主对话统一处理；本窗口不改 assessments、共享 core 或 OpenAPI。
3. P4-05：确认结构化 merge 类型、显式确认、同键同内容回放/同键异内容冲突及返回回执。可评估复用 `ChatTurn.client_turn_id` 唯一约束和 `verification` JSON 存储来避免新增模型；若要求真正 `system` 角色，当前 ChatTurn 角色约束仅允许 `student/tutor`，需主对话决定共享模型/迁移。还需确认 merge 对应文本是否应继续作为 tutor turn。
4. P4-06：确认已发布候选、先修关系、测评安排授权和证据不足的共享读取合同；R3-A Domain 语义尚未交付的部分先等待其合同。
5. 所有新增路由、公共字段、事件、OpenAPI 以及测试 fixture 变更交主对话；不在本窗口直接修改。

### 所需独立资源（需求，不作分配）

- 一个仅供本窗口测试、与预览库及其他窗口隔离的 PostgreSQL 数据库；测试须显式配置连接串/测试库名。
- 一个专用 Redis 实例或明确独立逻辑 DB，并使用独立 Celery queue；不得使用 DB0、DB1、默认共享测试配置或其他窗口 Redis。
- 如需 API/浏览器验收，分配独立 API 端口；本任务为后端范围，不预设 Web 端口，也不自行占用/分配端口。
- 只有收到 R3-B 明确 GO 后，才按主对话分配值复核资源并运行会写库的测试或服务。

### 风险、依赖和无法确认的事项

- 当前状态文档已预留 R3-B 资源，但状态明确为 HOLD，且 R3 总规则记为 GO=NO；资源预留不等于授权。应由主对话登记本报告、确认共同基线和排他文件后单独发出 R3-B GO。
- 旧 R2 交接曾将 `memory/router.py`、删除任务和共享审计相关测试列为主窗口所有；R3 表虽将 `memory/**` 列为候选排他范围，但必须以 R3 明确交接为准，特别保护隐私删除和审计实现。
- 技能/误区建模依赖 R3-A/P2-04 Domain 对象与审核合同；在其未定前只能明确边界，不能把文本标签升级为规范课程事实。
- 计划手册与当前实现的 API 细节存在差异；尚未获得统一策略层级、Branch note 角色、结构化字段、状态晋升阈值及 Planner 候选预算的主对话决策。
- 本准备阶段未运行测试、未启动服务、未执行数据库或 Redis 写入；没有新测试或环境验收证据。不得据此宣称 P3/P4 或 V1 已验收。
## R3-D

### 现状与缺口

- 已有 `Intervention`/`InterventionRun` 生命周期、教师观察审核和资格化再验证；课程学情接口目前以课程为 Scope，教师页仅展示少量聚合指标。
- P6-01/02 仍缺班级级统计视图、半开 UTC 时间窗口径与更新时间呈现、Evidence Coverage/分组、少样本保护及分析页浏览器验收。
- P6-03 尚无 TeachingActivity/Run、Planned/Actual Timeline、Inspector 或 Course Policy 工作流。R3 共享合同已规定 Activity 版本不可变，Run 固定班级、版本、CourseRelease/Assignment、目标摘要和发起人；状态 planned→ready→active/paused→completed/cancelled，带版本和幂等。
- P6-05 已有完成与评估分离，但尚无冻结的完整干预/复测证据闭环。当前效果投影偏执行统计，UI 的 `teacher_recorded` 不是复测证据。共享合同要求冻结目标；即时与 7–30 天延迟复测分开；每个窗口至少两项合格、独立且跨情境测量才计算描述性变化，否则 `not_measured`；无随机/比较组不得作因果结论。
- P6-06 尚无课程内容只读覆盖层、资源收藏/反馈或 TeacherAnnotation 数据/API。合同要求 Annotation 为独立 overlay，不改原始证据、作答或 canonical；默认教师 Scope 可见，学生可见须显式发布；不记录不必要的敏感心理评断。

### 拟修改文件（仅获 GO 后）

- `server/app/modules/interventions/**`：目标快照、班级目标校验、即时/延迟复测和描述性效果读取。
- 新增 `server/app/modules/teaching_activities/**`：活动命令、Timeline 和 Inspector 的专属服务/路由/Schema。
- 教师专属组件及其 API 客户端：`web/components/TeacherCourseSupportPages.tsx`、`TeacherInterventionsPanel.tsx`、`TeacherObservationsPanel.tsx`、`web/lib/interventions-api.ts`；拟新增教学 Timeline/Inspector、课程只读内容/覆盖层和专属 API client。
- 定向后端/前端测试：`server/tests/test_interventions.py`、`test_analytics.py`、新增 TeachingActivity 测试及教师专属合同/浏览器测试。共享导航、课程路由注册等文件须主对话明确归属。

### 需要主对话处理的共享接口、模型、迁移或 fixture

- 状态文档目前记录主对话正在实现 TeachingActivity/Run、Timeline/Annotation/Policy 的共享模型、API、路由注册与迁移；在该 tranche 合入并确认 OpenAPI 前，不实现依赖字段的写路径。
- 遵循 `R3-shared-contract-decisions-2026-10-04.md`：统计仅限已授权 class Scope；窗口为 UTC 半开 `[start,end)`，默认最近 30 天、最长 90 天；独立学生样本 `n < 5` 时只显示“样本不足”，不显示人数/百分比/排行/可反推分组。Planned 与 Actual 分开；Actual 仅由含 `occurred_at` 的持久业务事件生成。Course Policy 是已发布 CourseRelease pedagogy 的不可变片段，活动只可收紧限制。
- 共享合同另规定 TeacherAnnotation 的目标对象、理由、作者、时间、版本与可见状态；干预复测引用的资格证据及作用域需有共享字段/端点支撑。请主对话统一处理 `models.py`、Alembic 向前迁移、课程路由注册、OpenAPI 和公共测试 fixture；本窗口不修改这些共享文件。
- 权限应在查询前依据 CourseClass/ClassMember/TeacherAssignment 及当前课程 Scope 校验。学生完成活动本身不产生 Mastery；复测依赖资格化、独立、跨情境证据。

### 所需独立数据库、Redis 和端口（只列需求，不自行分配）

- 一个 R3-D 专用空 PostgreSQL 测试库；若需要浏览器持久种子数据，另需独立 E2E 库。
- 一个专属 Redis logical DB 或独立实例，并隔离 Celery broker/result 与 queue。
- 若做 API/浏览器验证，各需独立 API 与 Web 端口；Worker 不需要入站端口。由主对话分配具体值；状态文档当前预留值只供之后按要求复核，不是本报告的分配。

### 风险、依赖和无法确认的事项

- R3-D 当前仍为 `HOLD`；共享 tranche 尚在主对话实现中。本报告不是 GO。开始前须重读状态和合同、重核基线/文件归属/数据库 revision、Redis、bucket 与端口。
- CourseRelease/Assignment 冻结版本、班级成员变更后的目标快照处理、复测证据有效性与机构保留政策由共享合同/后续实现决定；报告阶段不能推断。
- 真实课程教材、教学活动内容及真实班级效果未提供或验证。小样本只读保护、效果描述性解释和教师 Scope 需通过隔离浏览器验收；本轮未运行测试、迁移或服务。
- 目前共同基线指纹记录为 `17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`，HEAD 记录为 `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；GO 到达后仍按状态文档要求重核新基线增量。
- 独立环境需求由主对话分配；资源预留不代表已确认当前无冲突，也不授权启动服务或写数据库。
## R3-B

本节对应 R3-B：P3-03/05、P4-02/03/05/06（memory、tutor、question_agent）。这是 GO 前只读准备报告，不代表获准开工。

### 现状与缺口

- P3-03：`MasteryState` 只按知识点聚合，已有证据数、算法版本和理由；Growth 投影中的“技能”仍复用知识点状态，“误区”从粗粒度 Memory 文本临时映射。缺独立技能/误区状态、规范领域对象引用及各自的证据晋升/失效规则。
- P3-05：`MemoryItem` 当前有 L1/L2/L3、粗粒度 `source_type/source_ref`、置信度、stale 与替代关系。缺 observed/inferred/explicit/teacher-confirmed 来源等级、证据引用、有效期/复核时间、冲突解决和完整状态合同。已读到的写入路径由测验提交生成候选；没有看到 Branch 写入 Memory 的路径。
- P4-02/03：进行中正式测评的 AI 支持已有 fail-closed 检查，并由多处 Tutor/Branch/题目教练入口调用；目前没有 System、Assessment、Teacher、Intervention、Preference 的统一有效策略解析。Tutor 有服务端状态机和静态提示阶梯，但缺固定 Action schema、完整诊断状态及可审计的 support gradient/提示预算合同。
- P4-05：Branch 有独立会话和选区字段；当前合并接收自由文本并自动选取分支最近 Tutor 回答，没有计划中的结构化类型、显式确认和可重放 `merge_id` 合同。当前重复合并返回 409。创建路径还需补验来源回合和选区绑定。
- P4-06：Planner 目前只按当前任务状态和到期复习数量输出四态、理由和固定 `continue` fallback；没有已发布候选/先修图/预算的完整合同，也没有 Planner 专项测试。

### 拟修改文件

- `server/app/modules/memory/service.py`、`router.py`：状态/记忆领域规则与投影；`router.py` 同时承载管理员和隐私删除路径，任何实施须精确保留共同基线已有改动。
- `server/app/modules/tutor/service.py`、`router.py`、`planner.py`：统一策略消费、动作/提示规则、Planner 决策。
- `server/app/modules/question_agent/router.py`、`service.py`：Branch 来源校验、结构化合并和幂等回放。
- 对应回归：`server/tests/test_mastery_memory.py`、`test_mastery_rules.py`、`test_tutor.py`、`test_question_agent_branches.py`；可新增纯函数 Planner 专项测试。

上述目标文件在准备检查时已有未提交修改或未跟踪状态；这不是可覆盖的授权。工作开始前必须按 R3 实际基线重新核对 `git status` 和逐文件归属。

### 需要主对话处理的共享接口、模型、迁移或 fixture

1. P3 状态/Memory：确认稳定 Domain/KnowledgePoint 引用、技能/误区状态和算法解释字段；确认 Memory 的来源等级、证据引用、有效期、复核、冲突与替代字段，以及旧数据映射和删除边界。预计涉及 `server/app/db/models.py` 和新 Alembic 迁移。P2-04 的规范误区对象/审核状态是上游合同。
2. P4-02：请主对话定义可调用的 `effective_policy` 解析接口、优先级和不可覆盖的硬限制。现有 assessment policy helper 只处理进行中 Attempt。若 Teacher/Intervention 策略需持久字段，模型和迁移由主对话统一处理；本窗口不改 assessments、共享 core 或 OpenAPI。
3. P4-05：确认结构化 merge 类型、显式确认、同键同内容回放/同键异内容冲突及返回回执。可评估复用 `ChatTurn.client_turn_id` 唯一约束和 `verification` JSON 存储来避免新增模型；若要求真正 `system` 角色，当前 ChatTurn 角色约束仅允许 `student/tutor`，需主对话决定共享模型/迁移。还需确认 merge 对应文本是否继续作为 tutor turn。
4. P4-06：确认已发布候选、先修关系、测评安排授权和证据不足的共享读取合同；R3-A Domain 语义尚未交付的部分先等待其合同。
5. 所有新增路由、公共字段、事件、OpenAPI 以及测试 fixture 变更交主对话；不在本窗口直接修改。

### 所需独立数据库、Redis 和端口（只列需求，不自行分配）

- 一个仅供本窗口测试、与预览库及其他窗口隔离的 PostgreSQL 数据库；测试须显式配置连接串/测试库名。
- 一个专用 Redis 实例或明确独立逻辑 DB，并使用独立 Celery queue；不得使用 DB0、DB1、默认共享测试配置或其他窗口 Redis。
- 如需 API/浏览器验收，分配独立 API 端口；本任务为后端范围，不预设 Web 端口，也不自行占用/分配端口。
- 只有收到 R3-B 明确 GO 后，才按主对话分配值复核资源并运行会写库的测试或服务。

### 风险、依赖和无法确认的事项

- 当前状态文档已预留 R3-B 资源，但状态明确为 HOLD，且 R3 总规则记为 GO=NO；资源预留不等于授权。应由主对话登记本报告、确认共同基线和排他文件后单独发出 R3-B GO。
- 旧 R2 交接曾将 `memory/router.py`、删除任务和共享审计相关测试列为主窗口所有；R3 表虽将 `memory/**` 列为候选排他范围，但必须以 R3 明确交接为准，特别保护隐私删除和审计实现。
- 技能/误区建模依赖 R3-A/P2-04 Domain 对象与审核合同；在其未定前不能把文本标签升级为规范课程事实。
- 计划手册与当前实现的 API 细节存在差异；尚未获得统一策略层级、Branch note 角色、结构化字段、状态晋升阈值及 Planner 候选预算的主对话决策。
- 本准备阶段未运行测试、未启动服务、未执行数据库或 Redis 写入；没有新测试或环境验收证据。不得据此宣称 P3/P4 或 V1 已验收。

## R3-C

检查时间：2026-10-04 20:09 +08:00。当前结论：**HOLD**；主状态文档仍将所有 R3 窗口标为 NO/HOLD，报告提交不构成 GO。

### 现状与缺口

- P5-04 案例已有五类服务端案例、固定快照、草稿版本/冲突恢复、提交锁定与后续资格化。当前评分依据选择命中、理由长度/关键词包含、设计说明长度，属于说明完整度检查，不是实验推理语义评分；scaffold 渐退和键盘/触控等价尚无浏览器证据。
- P5-05 已有 Growth 四 Tab 和状态/证据数/部分原因与下一步投影；失效后的主动刷新、清晰可追溯解释及反馈入口仍不完整。
- P5-06 偏好、通知和隐私删除组件/API 已存在，但活动课程 Me 页面由 `StudentCourseSupportPages.tsx` 的 `StudentMePage` 承载；`StudentProfile.tsx` 引用了偏好/通知组件，却未发现活动路由引用该组件。真实入口整合和个人数据透明呈现需补齐。
- P5-07 有若干窄屏 CSS 和原生控件，但 360px、键盘焦点、大字/减少动画、弱网恢复和课程切换不串任务尚未完整验收。学习/SSE路径可能涉及 `StudentLearnPage.tsx`、`StudentLearningSession.tsx`，两者目前未列入 R3-C 排他范围。

### 拟修改文件

以状态文档登记范围为准：`server/app/modules/cases/**`、`server/tests/test_cases.py`、`web/components/StudentCaseWorkbench.tsx`、`StudentHomeDashboard.tsx`、`StudentProfile.tsx`、`StudentPreferencesPanel.tsx`、`StudentNotificationsPanel.tsx` 和学生专测。当前工作区中 cases 目录、案例测试、案例工作台、Home Dashboard、偏好/通知组件及相应测试为未跟踪；`StudentProfile.tsx` 已修改。均为共同工作树已有内容，实施前须按 GO 要求复核归属并保留。

范围缺口请主对话确认：活动 Growth/Me 页面在 `web/components/StudentCourseSupportPages.tsx`，不在排他清单；P5-07 的学习/SSE体验可能涉及 `StudentLearnPage.tsx`、`StudentLearningSession.tsx`，也未列入。共享导航/CSS、测评、分支页面仍不在本窗口范围。

### 需要主对话处理的共享接口、模型、迁移或 fixture

当前案例使用 `CaseSession`/`LearningEvent`，偏好使用 `UserPreference`，Growth 与隐私 API 已有；初步没有必须新增的共享模型/迁移。若案例资格化、状态解释、Me/隐私接口需要新增字段、事件或端点，请主对话先定合同并负责 `models.py`、向前迁移、共享路由注册、OpenAPI 和 `conftest.py`/公共 fixture。本窗口只接入真实 API，不以静态数据替代能力。不得编辑共享模型、迁移、fixture、OpenAPI 或路由注册。

### 所需独立数据库、Redis 和端口（仅需求，不自行分配）

需要专属可迁移的 PostgreSQL 测试库、独立 Redis logical DB 与 Celery queue、独立 MinIO bucket，以及 Web/API 端口和隔离 Next 物理快照；若 Playwright/CDP 使用端口，也须由主对话单独确认。当前状态文档登记的候选资源是 PostgreSQL `psychology_learning_v1_r3_c_20261004`、Redis DB5、bucket `v1-r3-c`、Web/API `3212/8212`、queue `v1-r3-c`。这里只转述已有预留，不自行分配或保证当前空闲；获 GO 前需主对话/窗口按流程重新只读核验并显式配置，禁止回落共享库、DB0/DB1、3000/8000。

### 风险、依赖和无法确认事项

- 现有评分不可宣称语义质量；心理学推理的有效金标/内容来源未在本窗口确认，合成题只能验证工程行为。
- Growth、Me/隐私合同变化由主对话统一处理；活动 Growth/Me 页面及 P5-07 学习/SSE组件的排他权尚未明确，影响 P5-05/06/07 是否能完整交付。
- 主状态记录共同基线 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、工作树指纹 `17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`；本窗口未重算全树指纹，且状态文档提示有瞬时缓存路径消失，须在 GO 前核对基线一致和文件归属。
- R3 Next helper smoke 7/7 与脚本语法记录已存在；R3-C 物理快照启动/构建和隔离浏览器路径尚未验证。目标数据库/Redis/端口需要临开工重核。
- 本次未运行测试/迁移、未启动服务，也没有浏览器证据。旧 A/B/C/D、R2 GO 不适用；等待主对话在状态文档为 R3-C 明确写入 GO。
## R3-F

窗口身份：本节为本对话负责的 R3-F（P9-01/02/03/04/06）只读准备报告；本节标题按用户更正为 R3-F。

### 现状与缺口

- 当前 Designer 有课程设计入口、Domain/Pedagogy/Assessment 三个 JSON 文本编辑页和 Release 创建/列表/发布页；Domain Pack 的 ExperimentSchema 有字段说明，草稿支持版本冲突提示与重新载入。当前无专属 Designer 浏览器验收；已有 v2-workspace-contract.test.mjs 仅有一项源码断言。
- 后端已有 CourseRelease manifest 的创建、带版本 PATCH、列表与发布；Designer 可编辑，Teacher/Publisher 可发布。Domain Pack 有图关系、先修环和 EvidenceBinding 发布校验；已发布 Release 不可原地编辑，重复 publish 会回放现有版本。
- 尚缺结构化的三类 Pack 作者流程、Canonical/候选审核、Pedagogy Flow Inspector 与真实学生预览、Assessment 覆盖/Rubric/质量复核、Review、版本 Diff、Gate 明细、Impact 报告、WARNING 理由确认和班级换版/运行版本冻结。Pedagogy 与 Assessment 仍是 JSON manifest 和有限结构检查，不能据此提供真实预览、校准或影响分析。

### 拟修改文件（GO 后）

- web/app/course-design/layout.tsx、page.tsx、domain/page.tsx、pedagogy/page.tsx、assessment/page.tsx、releases/page.tsx；按合同调整 assets/page.tsx 时仅限其 Designer 页面接入。
- web/components/CourseDesignPackEditor.tsx 与新增 Designer 专属 Pack Editor、Preview、Review、Release Wizard 组件。
- 新增 Designer 专属测试（建议 web/tests/course-design-*.test.mjs 与真实 API 浏览器验收脚本）。不改共享 web/lib/course-api.ts、web/lib/api.ts、共享导航/CSS、构建配置或其他窗口组件。
- 上述现有 course-design 页面与 CourseDesignPackEditor.tsx 在准备时均为未跟踪共同基线文件；保留原内容，GO 后先复核逐文件归属，不覆盖或重置。

### 需要主对话处理的共享接口、模型、迁移或 fixture

- 等待 R3-A 提供 Domain API 与 Canonical/候选/审核边界、稳定对象 ID、Evidence 引用及 409 语义。
- 主对话定义并实现 Review、Preview、Diff、Gate、Impact 的 API 响应/权限/错误合同；Publisher 发布命令需明确 WARNING 理由、幂等键、审计与重复调用回执。
- P9-06 需要 CourseReleaseAssignment/班级换版合同，以及运行中 Activity/Assessment 固定旧 Release、新任务使用新 Release、撤回后旧引用重新鉴权的模型/API。涉及字段、ORM、Alembic、路由注册、OpenAPI、公共 fixture 均由主对话统一维护。
- 与 R3-E 的 Assessment 资产编辑、R3-G 的 TeachingAsset Release 绑定划清读写边界；本窗口只消费经确认的接口，不修改对方文件。

### 独立资源需求（只列需求，不自行分配）

- 独立 PostgreSQL 测试库；如浏览器验收需要持久种子，再需独立 E2E 库。
- 独立 Redis logical DB（若 API/异步路径需要）及专属 Celery queue；不得使用共享预览/默认测试 DB 或其他窗口配置。
- 独立 Web 与 API 端口、独立 Next 物理快照与 distDir；不得使用 3000/8000、共享 .next 或其他窗口端口。
- 若真实 Gate/预览读取对象存储，再由主对话分配隔离 bucket。以上为资源需求，不构成分配，也未在本报告中重新核验。

### 风险、依赖和无法确认的事项

- 当前并行状态记录的 R3-F 行仍为 HOLD，GO 总表为 NO；等待 R3-A Domain 合同和主对话 CourseRelease/assignment/发布门禁合同。
- 状态文档登记 HEAD 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04 及指纹 17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72；本窗口先前以 git status -uall 读到 490 项，而登记基线过滤 .pnpm-store/ 后为 226 项，统计口径不同且指纹未由本窗口重算。GO 前需主对话按同一过滤规则复核。
- R3 Next helper 的配置 smoke 7/7 是状态文档记录；物理快照、独立 Next/API proxy、浏览器与生产构建尚未由本窗口验证。资源只在状态文档中预留，需 GO 前现场复核。
- 本阶段没有运行测试、迁移、服务或浏览器验收；没有新的业务功能或端到端证据。建议 HOLD；报告提交不代表 GO，也不代表 V1 整体验收。

## R3-G

检查时间：2026-10-04 20:12 +08:00。结论：**HOLD；只读准备已提交，不代表 GO。** 当前 HEAD 为 `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；并行状态文档记录的共同工作树指纹为 `17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`。本次核对了 HEAD 和 `git status --short --untracked-files=normal`；未独立重算全树指纹。当前工作区含大量 R2/V1 未提交文件，R3-G 相关模块、组件和专属测试均为未跟踪文件，需在 GO 前后保护共同基线与归属。

### 现状与缺口

- **P8-02：** TeachingAsset 有 explanation/comparison/variable_map/table/focus 白名单，后端要求纯文本 `fallback_text` 并拒绝可执行内容；`LearningBlockStream` 对未知模板降级为文字，已知资产可展开纯文本说明，编辑器可编辑并预览 fallback。缺表示规则/降级原因合同；目前没有实际交互表示可供设备切换验收，也没有读屏、窄屏、键盘、减少动画或弱设备的浏览器证据。通用可访问降级机制可用工程 fixture 验证；资产内容对教学目标的等价性须等待获准教材/教案。
- **P8-06：** Mini Lab 服务端有六阶段定义快照、版本化阶段检查点、活动会话恢复、冲突保护、重复完成回放和资格化；前端每阶段等待服务端保存，刷新后恢复服务端快照。后端测试验证接口恢复与完成事件只生成一次，但尚无真实浏览器中断/恢复证据；未保存的当前试次如何呈现、用户主动放弃/作废的操作流程也未闭合。
- 现有 `MiniLabSession.status`/数据库约束已允许 `invalidated`，但没有作废 API；活动查询仅返回 `running`/`completed`。是否复用此状态、作废后如何禁止续写/提交/资格化，需主对话确认。

### 拟修改文件（获 GO 后）

- 后端：`server/app/modules/teaching_assets/service.py`（必要时补资产专属校验测试）；若确认作废合同，再改 `server/app/modules/labs/router.py`、`server/app/modules/labs/schemas.py`，并扩展 `server/tests/test_mini_labs.py`。
- 前端：`web/components/TeachingAssetEditor.tsx`、`web/components/learning/LearningBlockStream.tsx`、`web/design-system/mini-lab.css`、`web/components/StudentMiniLabPanel.tsx`、`web/components/learning/MiniLabRuntime.tsx`、`web/lib/mini-lab-api.ts`、`web/lib/teaching-assets-api.ts`、`web/lib/mini-lab/jspsych-adapter.ts`。
- 专属测试：`server/tests/test_teaching_assets.py`、`server/tests/test_mini_labs.py`、`web/tests/teaching-assets-recovery-contract.test.mjs`，以及获批的 Mini Lab 浏览器验收脚本/专属种子。
- 最近只读状态显示，上述 labs/teaching_assets 模块、前端组件/API helper、CSS 和测试目前均为共同工作树中的未跟踪文件；`web/app/globals.css` 等共享文件已有改动，不能由本窗口修改。清单仅为候选范围，GO 前需再次核对。

### 需要主对话处理的共享接口、模型、迁移或 fixture

1. 请确定 TeachingAsset 表示/降级合同：何时使用 `fallback_text`、学生看到的降级提示如何准确说明原因，以及原因由客户端能力判定还是服务端规则给出。若需要新增字段、表示版本或 API schema，请主对话负责共享模型、迁移与 OpenAPI；若复用现有字段，也请确认该口径。
2. 请确定 Mini Lab 的中断、恢复、放弃/作废语义：建议把 `running` 的已确认检查点作为可恢复数据，未确认试次不进入结果；若采用现有 `invalidated` 状态，作废后应不可续写、提交或产生完成资格事件，重复作废应幂等，并明确并发版本冲突响应。专属 router endpoint 可由获 GO 后实现，但 OpenAPI 导出由主对话统一处理。若要求作废事件或新增状态/原因字段，模型约束、迁移及事件类型均由主对话负责。
3. 目前完成事件以 `lab:{session_id}:completed` 幂等写入，只有完整 Explain/Transfer 经既有 Qualification 才生成独立证据。请主对话确认作废不发出 `lab_trial_completed`，且不改变原有资格化规则。
4. 需要主对话提供/确认可安全迁移的 E2E fixture 与已发布课程/资产创建路径；公共 `conftest.py`、路由注册、共享 models、迁移和 OpenAPI 均不在本窗口范围内。

### 所需独立数据库、Redis 和端口（只列需求）

- 一个仅供 R3-G 后端测试使用的独立 PostgreSQL 数据库；若浏览器流程需独立种子和 API 数据，再提供隔离 E2E 数据库或明确可复用的专属测试库策略。
- 独立 Redis logical DB（或专属实例）及本窗口专属 Celery queue；测试须显式配置连接，不回落到 DB0/DB1/默认测试库。
- Mini Lab 真实浏览器验收需要独立 Web 与 API 端口，并使用 R3 专属物理 Next 源码快照/API proxy/distDir；如需 Worker，使用专属 queue 且无入站端口。
- 主状态文档已有资源预留，但当前报告只列需求；这些资源在 GO 前须重新只读核验可用、数据库为空/版本适配、Redis 隔离、bucket 存在、端口无监听。

### 风险、依赖和无法确认事项

- 并行状态文档目前明确记载 R3-G 为 **HOLD：只读**、所有 R3 GO=NO；本报告不是 GO。R3 Next 配置虽有 helper smoke 记录，物理快照、R3-G 独立 Next 启动/构建尚无证据。
- 真实教材图表和 2—3 个最终实验仍等待获准教材/教案；`attention-cue-basic` 必须保持 `engineering_fixture` 标记。浏览器结果只能证明本地工程恢复行为，不证明实验心理学内容质量或科研效度。
- R3-C 的学生普通页面与 R3-F 的 Course Designer 归属不应扩展到 Mini Lab/资产专属组件；如资产编辑器入口涉及其页面，需主对话明确边界。共享模型、迁移、公共 fixture、OpenAPI、路由注册一律交主对话。
- 当前未运行任何测试或服务，未检查数据库/Redis/端口的最新实况，也未核验真实浏览器证据；必须在自己完整 GO 后先复核基线、文件归属和所有隔离资源。

## R3-E

本只读预审对应 R3-E（P7-01/02/04/06/08）；依据代码和现有交接记录，不表示已获 GO。

### 现状与缺口

- 题目已有不可变 `QuestionVersion`，题库发布要求审核和教材证据；`AssessmentItem` 固定 `question_version_id`。但尚无题目用途资格（练习/正式测评）字段，也无独立 `RubricVersion` 及其显式绑定合同。
- 测评创建可固定已发布题目版本、AI 策略、开放/截止时间和每题分值；发布接口将草稿直接发布。缺完整预览/发布向导及结果可见时间/策略配置。
- 学生独立 Assessment Shell 已实现开考确认、自动保存、刷新恢复、答案版本冲突、标记、截止和提交；已有服务端限制未开放/已关闭测评内容的切片。
- 人工评分已有 `TeacherGradingDecision` 与追加式 `ScoreRecord`、版本冲突、理由、审计和幂等边界。未启用 AI 主观评分建议；全链故障覆盖尚不完整，既有 R2-C 证据不能替代本轮隔离复验。

### 拟修改文件

- 服务端候选排他范围：`server/app/modules/assessments/**`、`server/tests/test_assessment*` 中属于本轮的测评专测。
- 测评专属前端候选：`web/app/student/assessments/**`、`web/app/teacher/assessments/**`、`web/app/teacher/courses/[courseId]/assessments/**`、`web/app/course-design/assessment/**`、`web/components/StudentAssessments.tsx`、`web/components/TeacherAssessments.tsx`、`web/components/TeacherGradingPanel.tsx` 及专属测试。文件归属和基线须在完整 GO 后重核；不改 Tutor、案例或共享导航。

### 需要主对话处理的共享接口、模型、迁移或 fixture

- 若引入用途资格、独立 `RubricVersion`、测评发布快照/结果可见策略或 AI 建议对象，需要主对话审定字段/API 合同并负责 `server/app/db/models.py`、新增 Alembic 迁移、OpenAPI 导出及共享路由/fixture（如受影响）。本窗口只提交需求，不改共享文件。
- 现有交接明确 `RubricVersion`、独立 `AIGradingSuggestion` 等模型/迁移由主对话统一；未经批准的学生答案与模型输入不得伪造或发送给 AI 评分路径。

### 隔离资源需求（只列需求，不自行分配）

- 需要专属空 PostgreSQL 测试库、独立 Redis DB/实例，以及独立 Web/API 端口；浏览器验收还需独立 CDP/DevTools 端口及独立 Next distDir/物理源码快照。
- 当前状态文档为 R3-E 记录了候选值 `psychology_learning_v1_r3_e_20261004`、Redis DB7、bucket `v1-r3-e`、Web/API `3214/8214`。这只是已有资源记录，不视为本报告分配、当前可用性保证或 GO；开工前须由主对话确认并复核，尤其 CDP 端口尚无 R3-E 专属记录。

### 风险、依赖和无法确认事项

- 结果可见策略受机构规则约束；现有材料没有确认统一政策，须由主对话/机构输入决定安全默认值和发布语义。
- 获准处理学生答案的模型、供应商不留存/不训练承诺及用户授权均未提供，因此 AI 评分建议保持禁用；不宣称其完成。
- 若共享模型/API 合同未先确定，前端向导和服务端状态可能产生版本漂移；依赖主对话先审查公共合同。
- 共享状态当前把 R3-E 标为 HOLD、GO 全部为 NO；虽然隔离资源已有记录，仍缺共享合同结论和明确 GO。没有复核实际端口、当前 Git 基线/文件归属（这些应在 GO 到达后检查），也没有运行测试、浏览器或服务。
- 既有本地故障证据不等于生产恢复、机构规则或整个 V1 验收；生产部署/恢复与学习效果不在本轮可宣称范围。
