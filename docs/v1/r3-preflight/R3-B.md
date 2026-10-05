# R3-B 交接报告

HANDOFF=COMPLETE; RESUMED=2026-10-05 16:12 +08:00

## 负责范围与当前状态

R3-B 负责 P3-03/05、P4-02/03/05/06 的非 Domain 子范围：Memory 来源/时效/冲突服务、统一教学策略与 Tutor 状态机、Branch 结构化幂等合并、非 Domain Planner。本报告补齐主窗口要求的文件清单、合同、基线增量、资源现场与冲突核查。按主窗口恢复规则，仅恢复表格原有部分 GO；不扩大目录或接口范围，不据此宣称 R3 或 V1 整体验收。

- 检查日期：2026-10-05
- HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`
- **指纹增量记录：** 主窗口广播基线为 509 项、SHA-256 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`。首次补交本报告后，连续两次指纹均为 509 项、`4203B758B3C39B0BBD23A61585184CD5EF2FF0359EF3A4EEDD84E64993B1F83B`。相对广播基线，本窗口的明确增量是 `docs/v1/r3-preflight/R3-B.md` 交接内容。资源核验为只读；补充资源结果与恢复标记后，报告本身作为共同树的一个文档增量。
- 迁移 head：`0049_r3_teacher_activity_assessment_release.py`；本范围没有提出新增模型或迁移需求。

## 实际文件

本窗口的实现涉及以下排他范围文件：

- `server/app/modules/memory/service.py`
- `server/app/modules/tutor/policy.py`（新增）
- `server/app/modules/tutor/planner.py`
- `server/app/modules/tutor/service.py`
- `server/app/modules/tutor/router.py`
- `server/app/modules/question_agent/router.py`
- `server/tests/test_question_agent_branches.py`
- `server/tests/test_tutor.py`
- `server/tests/test_r3_memory_policy.py`（新增）

当前工作树还显示 `server/app/modules/question_agent/service.py` 已修改；不能据此归因于本次交接，且本次未编辑它。所有 R3-B 范围文件均落在状态文档分配给 B 的 Memory service、Tutor、question_agent 与专属测试范围。主窗口拥有的 `memory/router.py`、`tests/test_mastery_memory.py)、models、迁移、conftest、OpenAPI 和根路由注册未触碰；未发现与其他窗口排他路径冲突。

## 合同与行为

- **Memory 来源及时效：** 仅把有已完成来源回合、有效来源/证据引用且未过有效期的内容作为候选；展示来源、证据引用、有效期及复核信息。稳定弱点需要至少两次独立尝试，并保留证据及复核时间；不会因一次错误或自评自动晋升掌握等级。
- **Memory 冲突：** 开放冲突保留双方内容和来源，不覆盖任一侧；仅冲突所有者或具课程权限的教师可解决，并记录审计。过期或已解决内容不继续作为有效候选。用户级跨课程汇总由主窗口维护，本窗口没有修改其 router。
- **统一教学策略：** 将课程发布策略、当前干预策略、测评约束和用户偏好合成为有效策略，限制取交集；记录策略版本、来源及哈希。未知或格式错误的限制 fail closed。Tutor 回合和学习状态校验动作与提示预算，并保存策略元数据。
- **Branch 合并：** 要求学生明确确认并提供幂等键；对规范化 JSON 内容计算哈希，检查来源学生回合、选择、当前课程权限、分支所有者/模式/父子关系。相同键和内容可安全回放；同键异内容冲突。只把学生明确选择和附注写入学生回合，不合并 Tutor 结论。
- **Planner：** 只读、有界地生成最多五项 continue/review/practice 建议，使用已发布课程资料、到期复习和有效学习证据；输入不足、异常或超时时降级。Domain 技能/误区引用、规范化晋升及 Domain Planner 接入等待 R3-A 稳定共享合同。

## 共享依赖与其他窗口

- 0048 已提供本实现所需的 Memory 与 Branch 字段；无新增模型、迁移或 OpenAPI 需求。
- Tutor 策略读取现有 CourseRelease manifest、Intervention plan、Assessment purpose 和 UserPreference 策略字段；不需要新的共享 fixture 或路由。
- 主窗口负责 Memory 跨课程汇总与 `memory/router.py`，以及 P3-06 删除、管理员审计。
- 依赖 R3-A 的 Domain skill/misconception 生命周期、Claim helper 和稳定引用接口；合同稳定前不做跨模块耦合。
- R3-C 的 Growth/Me 页面应只消费真实 API，不在前端生成技能/误区状态。Branch 服务限制在本窗口 question_agent 范围。
- 发现其他窗口合同依赖时，按主窗口统筹；本次未改动对方文件。

## 独立资源现场（2026-10-05，只读核验）

- PostgreSQL：`psychology_learning_v1_r3_b_20261004`，只读连接成功；`alembic_version=0049`，public schema 有 73 张 base tables。
- Redis：`redis://127.0.0.1:6379/4`，PING 成功，DB size 为 0。
- MinIO：`127.0.0.1:9000` 上 bucket `v1-r3-b` 存在。
- Web/API/CDP：3211、8211、9311 当前没有监听进程；本次没有启动服务。无监听仅表示检查时空闲。
- Worker：queue `v1-r3-b`，无入站端口；本次没有启动 Worker。
- 上述核验没有写入数据库、Redis 或对象存储；没有运行写库测试。

## 测试与浏览器证据

历史专项验证（不是本次复跑）：

- `pytest -p no:cacheprovider -q tests/test_r3_memory_policy.py tests/test_question_agent_branches.py tests/test_learning_blocks.py tests/test_tutor.py`：22 passed，2 条弃用警告。
- 增加课程成员读取校验后，`pytest -p no:cacheprovider -q tests/test_question_agent_branches.py tests/test_tutor.py`：14 passed，2 条弃用警告。
- Ruff 对本范围文件及 `git diff --check` 通过。
- 主窗口 2026-10-05 在 root 专用测试数据库、Redis DB11 和 root bucket 对当前共同树运行全量后端回归：313 passed、2 warnings。该结果由主窗口记录，本窗口没有执行这次全量回归。
- 未做本窗口业务浏览器验收、真实学生/课程数据验证或 Worker/真实 Redis 故障验证。

## 未决事项与范围边界

- 当前仅恢复表格列出的 Memory service、Tutor、Branch、非 Domain Planner 受限 GO；未取得扩大范围的授权。
- 等待 R3-A 确认 Domain 引用、审核及晋升合同，再评估 Domain Planner 接入；该项目前保持 HOLD。
- Memory 保留/删除与测评结果可见的机构政策仍由主窗口统一确定。
- 不据受限 GO 或局部测试通过宣称 R3/V1 整体验收。


## 恢复后的最新复核（2026-10-05 11:25 +08:00）

- 当前共同基线复核前后：HEAD 仍为 `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。连续两次指纹均为 513 项、SHA-256 `C210F8CC6EF7F1CB660A4532B5597F01E718F3A7E00D0F1E2D4450656478B57F`；包含同期其他窗口已登记的文件，指纹脚本仅排除共享状态文件和 `.pnpm-store/`。
- 复核自身文件分配：Memory service、Tutor、question_agent 与 R3-B 专测仍在 B 表格范围；当前没有发现其他窗口对这些排他路径的新增归属。主窗口的 `memory/router.py`、隐私删除、管理员审计和共享文件仍排除在 B 范围外。
- 已在 R3-B 专属 PostgreSQL `psychology_learning_v1_r3_b_20261004`、Redis DB4 重跑：`PSYCHOLOGY_TEST_DB=psychology_learning_v1_r3_b_20261004 PSYCHOLOGY_TEST_REDIS_URL=redis://127.0.0.1:6379/4 python -m pytest -p no:cacheprovider -q tests/test_r3_memory_policy.py tests/test_question_agent_branches.py tests/test_learning_blocks.py tests/test_tutor.py`，**22 passed、2 warnings、130.03 秒**。数据库迁移仍为 0049；测试后 Redis DB4 仍为 PING/0 keys。端口 3211/8211/9311 未监听。测试只访问指定隔离资源；未启动 API/Web/Worker。
- **业务浏览器验收阻塞/主窗口依赖：** Playwright 自动探测仅找到主预览 3000/8000/9000，按隔离约束未使用。只读检查发现 `web/app/student/branches/page.tsx` 目前渲染 `StudentCaseWorkbench`，`StudentLearnPage.tsx`、`StudentLearningSession.tsx` 中也没有 Branch 请求；B 的排他清单只有 Memory/Tutor/question_agent 服务与专测，不含这些 Web 文件。当前已用 ASGI 专项测试覆盖 Branch 创建、确认合并、幂等回放和冲突，但无法在不越界改 C/共享 UI 的情况下做真实 Branch 产品页面浏览器验收。请主窗口协调 C 或自行接手 UI 消费端，再安排独立浏览器验收；在此之前将其标为未验收，不把 ASGI 测试记成浏览器证据。
- 本次专项测试后复查 DB/Redis/端口均未发现资源污染；未运行其他测试或启动服务。


## 范围内负例补充（2026-10-05 11:55 +08:00）

主窗口 11:51 指令要求继续 B 原部分 GO，并在资源不可用时先做静态检查并报告阻塞。只读状态仍记录 5432/6379/9000 无监听，故本次未跑数据库测试、未启动服务。

本次在 B 排他范围内增加：

- `server/tests/test_r3_memory_policy.py` 的策略负例：未知教学动作与布尔型 `max_hints` 同时出现时保持 fail-closed，动作收窄至 pause/handoff，提示与支持梯度为 0。
- `server/app/modules/memory/service.py` 的专测：inferred Memory 缺少 evidence refs 时，在任何数据库写入前拒绝。
- `server/app/modules/question_agent/router.py`：BranchMerge 对说明文本 trim 后校验非空；只含空白的合并说明会在请求校验阶段拒绝。
- `server/tests/test_question_agent_branches.py` 的纯请求模型负例：空白合并说明产生 ValidationError。

Ruff 对 `question_agent/router.py`、`test_r3_memory_policy.py`、`test_question_agent_branches.py` 运行 `python -m ruff check --no-cache`，通过。新增 pytest 用例与 Branch API 路由负例尚未执行；资源恢复后需在 R3-B 专属 DB/Redis 上重跑四个定向文件。

Branch 路由负例已补入 `test_question_agent_branches.py`：跨会话来源、来源中不存在的选区和未确认合并均应拒绝。尚未执行，待专属服务恢复后复验。真实产品 Branch 页面由主窗口接手，B 不修改页面。

纯逻辑补充复核：以 `python -B` 直接执行无数据库校验，策略未知动作/布尔上限 fail-closed、推断记忆缺证据前置拒绝、空白 BranchMerge 说明校验 **3 项通过**；没有连接 DB、Redis 或 MinIO。pytest 集成文件与 API 路由负例仍待专属服务恢复后复验。


## 继续施工与当前复验（2026-10-05 12:10 +08:00）

### 共同基线、归属与资源

- 在本节写入前连续两次运行 scripts/r3-baseline-fingerprint.ps1：HEAD 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04，均为 520 项、SHA-256 421BC426AD2079B0761318BB33CF7E04C0995F55C23EE1B4453312B39C145655。该指纹含共同工作树其他窗口的增量，不能归因给 B；自己的路径增量仍按本报告上文和本节文件清单辨认。
- 当前 B 路径核查仍限于 memory/service.py、tutor/**、question_agent/** 与专测；没有触碰主窗口所有的 memory/router.py、隐私删除/审计、共享文件或 Branch 页面。主窗口状态已将 web/app/student/branches/page.tsx、web/components/StudentBranches.tsx 和 Branch 前端合同测试列为主窗口所有；本窗口未修改或启动其 UI。
- 测试前只读核验：PostgreSQL psychology_learning_v1_r3_b_20261004，revision 0049，73 张 public base tables；Redis DB4 PING=True / DBSIZE=0；MinIO bucket v1-r3-b 存在。3211/8211/9311 没有监听者。测试后再次只读核验相同 DB/revision/table count，Redis DB4 仍为 0 keys，bucket 仍存在。全程未启动 API、Web、CDP 或 Worker。

### 本次工作与证据

- 针对共享计划中“剩余负例/冲突测试”在 B 专属 PostgreSQL、Redis DB4、MinIO bucket 上复跑四文件：tests/test_r3_memory_policy.py、tests/test_question_agent_branches.py、tests/test_learning_blocks.py、tests/test_tutor.py，结果 26 passed，2 条 Starlette/FastAPI 弃用警告，145.42 秒。此次覆盖 inferred Memory 缺少 evidence refs 时写前拒绝、未知策略动作/布尔型提示上限 fail-closed、BranchMerge 空白说明校验，以及跨会话来源/无效选区/未确认合并负例；此前 22 passed 为历史复跑，本次 26 passed 是当前结果。
- 对 Memory、Tutor、question_agent 实现及四个定向测试文件运行 Ruff：All checks passed!；对同一 B 路径运行 git diff --check，无输出/通过。
- 无浏览器、真实学生或真实课程内容验证。本地 ASGI/pytest 证据不替代 Branch 产品页面浏览器验收。

### A Claim 消费合同需求与阻塞

- 只读查看 knowledge/domain.py 与 R3-A.md：A 当前暴露 classify_claim(supported_subclaims, unsupported_subclaims, contradicted_subclaims, counterevidence_scope_matches) 和 async verify_claim_with_bounded_retrieval(claim, initial_evidence, evaluate, retrieve_once, retrieval_scope, required_scope)。结果状态为 supported / partially-supported / contradicted / unknown，含初始/补充 evidence、supplemental_retrieval_attempts、检索 scope 与可选 refusal reason；helper 将补检索限制为一次，并要求 retrieval_scope == required_scope。
- B 的 Tutor 消费还需要主窗口/A 明确并稳定以下跨模块约定：required_scope 的规范字段（user、course、已发布 DomainRelease ID/摘要、对应 PublicationSnapshot/索引版本）；initial_evidence 中哪些 Evidence 字段/ID 可安全持久化；evaluate 是否由确定性校验实现以及矛盾态所需的同范围反证形状；补检索回调返回对象和失败/超时错误语义。TutorTurn 现有 verification 可作为候选持久化位置，但最终快照标识和值域必须随主窗口 CourseRelease/PublicationSnapshot 接线确认。
- A 报告当前仍把 DomainRelease→CourseRelease→PublicationSnapshot/实际索引绑定列作共享未完成项；因此本轮只列消费需求，不把现有 Tutor 文本重叠校验伪称为 A Claim 四态集成，不接 Domain Planner。由主窗口/A 确认 scope/evidence/error contract 并接通发布快照后，B 再按获批稳定签名补 Tutor 消费和 Domain Planner 专测。
- Branch UI 浏览器验收由主窗口负责；当前 B API/服务与专测已通过，但本报告不提供页面浏览器证据。仍无真实学生/课程内容验证、Worker/故障恢复验证或生产验证。

### 进度分层

- 已编码：本报告前述 Memory provenance/有效期/冲突处理、Tutor effective policy 与 Planner、Branch 结构化幂等合并，以及补入的负例校验。
- 专项测试通过：本次四文件 26 passed。
- 隔离环境验证：专属 DB 0049、Redis DB4、bucket 及测试后清理状态均现场核验；未启动应用服务。
- 业务浏览器 / 真实内容 / 生产验证：尚未由 B 验收。Branch 页由主窗口承接；Domain Planner/Tutor A-Claim 消费等共享发布版本合同接稳定后再接续。
## Tutor Claim 消费增量（2026-10-05 14:02 +08:00）

### 实现与测试

- 新增 DomainClaimContext 及 verify_domain_claim_for_tutor，在 Tutor 服务层调用 A 的 verify_claim_with_bounded_retrieval。完整校验并复制 Scope，要求包含 user、organization、course、DomainRelease、PublicationSnapshot、教材版本集合、index Job 与 embedding version；检索侧与要求侧由 A helper 严格比较。检索回调只接收隔离副本。
- 把 helper 结果规范为可放入既有 ChatTurn.verification JSON 的 domain_claim 字段：四态、supported/unsupported/contradicted 子项、完整预期与实际 Scope、初始/补充 evidence ID、0/1 补检索次数和拒答原因。证据正文不写入该记录。状态不为 supported 时，注入该上下文的 Tutor 回合以固定拒答语降级。
- run_turn_stream 增加可选 Domain Claim context 参数；目前 /chat/sessions/{id}/turns 路由尚未构造/传入它，因为主窗口的学生 CourseReleaseAssignment 到 Tutor 检索 Scope 注入仍未完成。未注入 context 的既有非 Domain 路径行为保持不变；Domain 检索不会因此提前启用。
- 在 tests/test_r3_memory_policy.py 增加 7 项纯逻辑测试，覆盖 supported/partial/contradicted/unknown 四态、完整 Scope 快照和回调变更隔离、证据正文不持久化、Scope 不一致拒绝补检索、最多一次补检索、补检索仍未知时的拒答原因及不完整 Scope 拒绝。
- 本次 B 四文件回归使用分配的 DB psychology_learning_v1_r3_b_20261004、Redis DB4、bucket v1-r3-b，结果 33 passed、2 warnings、120.16 秒。测试前后 DB 为 revision 0049 / 73 张 public base tables，Redis DB4 为 0 keys，bucket 存在；3211/8211/9311 均未启动服务。Ruff 与 git diff --check 对 B 范围通过。
- 本节写入前连续指纹为 HEAD 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04、527 项、SHA-256 8119FC62FA7DAA1100CBD1862F718463382D75AA72C2E02E9974AE0BD3F68FD1。该指纹含其他并行窗口修改，不代表 B 独有增量。

### 当前依赖与验收边界

- 主窗口 13:57 广播已记录 DomainRelease → CourseRelease → PublicationSnapshot → Job payload → RetrievalUnit 同 ID 绑定，并在 root 隔离库完成 21 项材料/发布/Release 定向测试；该进展有助于后续接通，但主窗口仍将 CourseReleaseAssignment 到学生实际检索/运行 Scope 注入列为未完成。
- B 服务 adapter 已实现并有纯逻辑测试；活动聊天路由尚未传入已验证的 assigned Release 和完整 snapshot context，因此 TutorTurn 中的 Domain Claim 还没有真实 API 落库证据。需等主窗口确认学生 assignment 到不可变 snapshot 的稳定调用合同，再由 B 在 Tutor router 内构造 DomainClaimContext、限定检索到同一版本并补 API/数据库测试。Domain Planner 的 Domain 查询继续保持 HOLD。
- 未做 Tutor Claim 业务浏览器、真实课程/教材语义或生产验证；Branch 页面验收仍由主窗口。此前非 Domain 部分与本次 adapter 的自动化通过不代表 R3/V1 整体验收完成。
## 0050 共享合同接收与数据库现场（2026-10-05 14:14 +08:00）

- 已于 2026-10-05 14:14 +08:00 读取共享状态中“主窗口运行快照绑定实施交接”及 R3-B 明确 GO 条款，接收 0050 合同后继续本窗范围。
- 0050 为 LearningSession、Attempt、LearningEvidence 增加成对 nullable 的 course_release_assignment_id / course_release_id 与外键/check/index；旧行保留空值。本窗口只使用此共享 schema，不修改 models、Alembic 或其他共享文件。
- 前一轮四文件 pytest 使用隔离配置，conftest 自动运行 upgrade head；测试后只读发现 B 专库 revision 已从 0049 升到 0050、public base tables 仍为 73。这个自动迁移发生在本窗口读取本条 14:06 广播之前；测试没有调用新字段或以其行为为通过条件。之后才读取合同并登记接收。本窗口不会 downgrade 或清理 B 库。
- 本窗口接收后两次共同指纹均为 HEAD 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04、529 项、SHA-256 D127A66A6C0392FE10188548845634E550BA8CE38CF8625E653D45AB0B33C920；该指纹含所有并行窗口已登记增量，不归因于 B。
- 本窗口获准在 tutor/** 与 memory/service.py 处理：新 LearningSession 绑定唯一活动 CourseReleaseAssignment/CourseRelease；多班级歧义拒绝；会话恢复及后续证据保留创建时来源；不匹配 assignment/material/release 时 fail closed；保留已有空值会话兼容。仍不改共享文件及 learning_events 模块。

## 0050 运行快照绑定实施与复验（2026-10-05）

- **实现：** 在 `tutor/service.py` 解析学生的活动班级成员和活动 CourseReleaseAssignment；无活动 assignment 时沿用成对空值，多于一个时返回 `COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS`，Release 不可用或资料不在其 manifest 时 fail closed。`tutor/router.py` 仅在创建新学生 LearningSession 时写入绑定；恢复/回应按原 `course_release_id` 加载有效教学策略。`memory/service.py` 对来源 LearningSession 的新 LearningEvidence 继承同一 assignment/release，并拒绝用户/课程不匹配、半空绑定或与来源不一致的显式绑定。未修改 `learning_events/**`、共享模型、迁移、OpenAPI、fixture 或 Branch UI。
- **新增验收：** 在 `test_tutor.py` 覆盖唯一活动 assignment 创建时固定、assignment 换版并将旧 Release 标记 deprecated 后恢复/回应仍不漂移、LearningEvidence 继承来源、材料不属于 assigned Release 时拒绝、Evidence 显式来源冲突拒绝，以及学生多班级活动指派时拒绝创建。旧无 assignment 路径仍由既有学习状态机用例覆盖。
- **隔离现场（复验时间：本节写入前）：** B 专库 `psychology_learning_v1_r3_b_20261004` revision `0050`；数据库无其他活动会话；Redis `127.0.0.1:6379/4` PING 成功、DBSIZE 为 0；MinIO bucket `v1-r3-b` 存在；3211/8211/9311 无监听。未启动 API、Web、CDP 或 Worker。测试后再次读取 DB/Redis/bucket/端口，结果相同；未触碰预览资源或其他窗口资源。
- **基线与文件边界：** `HEAD=4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；`scripts/r3-baseline-fingerprint.ps1` 连续两次为 531 entries、SHA-256 `B52BCD6D6130A3B04FCC2199F18DF1FEF4BF89DCE50C95D47ABFDCBB2F201B31`。当前 B 变更路径仍为 `memory/service.py`、`tutor/**`、`question_agent/**` 与 B 专测；此共同指纹包含其他窗口增量，不归因于 B。
- **验证证据：** 在上述 B 专用数据库、Redis DB4 和 bucket 上运行四文件定向套件 `tests/test_r3_memory_policy.py tests/test_question_agent_branches.py tests/test_learning_blocks.py tests/test_tutor.py`：**36 passed、2 warnings，111.43 秒**。随后补充两个负例后，重新运行 `tests/test_tutor.py -k 'pins_unique_course_release_assignment or rejects_ambiguous_release_assignment'`：**2 passed、2 warnings，15.61 秒**。对全部 B 模块和相关专测运行 Ruff（`--no-cache`）：All checks passed；`git diff --check` 通过。默认 Ruff cache 写入因只读文件系统权限失败一次，使用 `--no-cache` 复验通过；pytest 默认捕获器也因不可写临时目录失败一次，关闭捕获（`-s`）后在同一隔离 DB 成功运行。数据库检查期间未发现其他会话，未使用临时或共享数据库替代。
- **进度与未决：** 0050 绑定已编码；上述自动化专项通过；隔离环境现场通过。未做 Branch 业务浏览器、真实学生/课程内容、正式教学或生产验证。Branch 页面归主窗口。Domain Claim 的活动聊天路由消费仍等待主窗口把 CourseReleaseAssignment 接入同版本 PublicationSnapshot/检索 Scope；Domain Planner 查询继续 HOLD。Memory 保留/删除和结果可见政策仍由主窗口统一决定；不据此宣称 R3/V1 整体验收完成。

## 0051 Tutor ChatSession 固定课程版本与 Claim SSE（2026-10-05）

### 实现与复验

- 按共享状态 15:00 的 R3-B 专项 GO，在 `tutor/service.py`、`tutor/router.py` 与 Tutor 专测中接入 0051 ChatSession 绑定。新学生会话从真实 active ClassMember、active CourseClass、同课程 active CourseReleaseAssignment 和 published CourseRelease 解析唯一 Scope；多班歧义返回 `COURSE_RELEASE_ASSIGNMENT_AMBIGUOUS`；已绑定会话后续按原 assignment/release 复验成员权限，移出班级/撤权返回 404。未绑定历史会话保留原非 Domain 兼容路径。
- 活动绑定会话的 Tutor turn 读取固定 Release，不重新选择当前 assignment；通过 `prepare_bound_chat_retrieval` 校验 manifest 内材料及版本 pin、同 DomainRelease 的 PublicationSnapshot、索引任务与 Embedding Scope，再调用 A 的 `verify_claim_with_bounded_retrieval`。只允许 0/1 次同 Scope 检索；四态、Scope、稳定 evidence IDs、检索次数及 refusal reason 写入既有 `ChatTurn.verification`，不保存证据正文。缺版本 pin、缺 DomainRelease 或快照不匹配时记录 `unknown` 并拒答，不回退到当前版本或未绑定搜索。
- `run_turn_stream` 接收会话用户机构信息；路由在恢复/创建 turn 时传入绑定 Scope。新增 Tutor API 专测覆盖：创建时固定、课程版本轮换后仍保持原绑定、当前快照缺失时拒答且 0 次补检索、同 `client_turn_id` 重放、班级成员撤销后 404、多活动班级歧义 409。拒答/快照缺失覆盖了安全降级，不代表有真实教材支持 Claim 的成功检索验收。
- 使用专属环境运行四文件回归：`PSYCHOLOGY_TEST_DB=psychology_learning_v1_r3_b_20261004`、Redis DB4、MinIO bucket `v1-r3-b`；命令为 `pytest -s -p no:cacheprovider -q tests/test_r3_memory_policy.py tests/test_question_agent_branches.py tests/test_learning_blocks.py tests/test_tutor.py`，结果 **39 passed、2 warnings、172.24 秒**。B 文件 Ruff（`--no-cache`）通过，`git diff --check` 通过。
- 测试后只读复核：DB host `127.0.0.1`、revision `0051`、其他会话 0；Redis DB4 PING 成功、0 keys/0 clients；bucket `v1-r3-b` 存在；3211/8211/9311 均无监听。本轮未启动 API、Web、CDP 或 Worker。
- 本节记录前连续两次共同树指纹一致：HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`，535 entries，SHA-256 `9D68C3718E4A5CC4A38831DAE88619AA670A05BE1C2C759AC90D654FA234ED0D`。共同工作树指纹包含并行窗口增量，不能归因给 B。复核时 `git status` 显示共享模型、0051 迁移、知识/课程/材料、根路由、OpenAPI 等其他窗口文件处于修改或新增状态；本轮未编辑这些文件。

### 主窗口共享合同需求与阻塞

- **CourseRelease 需要不可变材料版本 pin。** 当前课程发布 manifest 实际只有 `materials`（Material ID），没有 `material_version_ids`。0051 Tutor 合同要求从不可变 Release manifest 得到确切材料版本；B 已对缺失版本 pin fail closed。请主窗口在共享 CourseRelease 发布合同/服务中写入并校验 `material_version_ids`，确保每项与发布时 PublicationSnapshot 的 `material_id`、`material_version_id` 一致，并纳入版本化 manifest hash。B 不修改 `courses/**`、`materials/**`、共享模型或迁移。
- **历史快照读取未闭环。** A 的搜索响应已有经权限过滤的 `publication_snapshots` 合同；当前合同与状态说明明确其面向当前有效发布快照。已绑定的旧 assignment/`deprecated` Release 若其快照被 supersede，B 现在安全拒答。主窗口/A 需提供按旧 Release manifest 中固定 snapshot ID 的授权读取/检索语义或明确旧版本不可继续检索的产品规则，再做历史 Release 正向数据验收。
- **Branch ChatSession 是否继承绑定需要主窗口裁定。** 当前 0051 精确 GO 只授权 `tutor/**`、`memory/service.py`、B 专测和本报告，不包括 `question_agent/router.py`；Branch 创建仍由该路由创建子 ChatSession，尚未复制 parent 的 assignment/release ID。若 Branch SSE 必须继承父会话发布版本，请主窗口补充其排他范围或自行接手接线，并定义 parent/child 权限和历史恢复一致性；B 本轮没有越界修改该路由。
- 业务浏览器和真实学生/教材验证未做；本轮只证明隔离 API/数据库用例和静态检查。此前 Branch 页面仍由主窗口负责。共享 CourseRelease pin、历史快照读取与 Branch 继承合同具备后，需补正向真实 PublicationSnapshot/IndexJob 数据的跨模块 Claim 落库测试，并由主窗口按静止共同树运行跨模块回归。以上不代表 R3 或 V1 整体验收完成。

## 16:12 GO：CourseRelease 历史快照正向读取与 Branch 绑定继承（2026-10-05）

### 共同基线、文件归属与隔离现场

- 阅读共享状态 16:12 的两项 R3-B GO 和共享合同“CourseRelease 固定教材发布快照补充”，并重读本报告 0051 最后一节后施工。该 GO 仅允许 `tutor/**`、`question_agent/**`、B 专测和本报告；禁止 shared models/migrations、courses/knowledge/materials、root router、OpenAPI、conftest、隐私 router、Branch UI。此前 `git status` 显示 `courses/**`、`knowledge/**`、`materials/**`、models 与迁移在其他窗口有改动；本轮没有编辑这些文件。
- 本轮共同基线前后复核 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；连续两次脚本指纹均为 535 entries、SHA-256 `5D6900158E68A3ED37B3707A815E5943D74B74EE6D6AC4801DD1498582AD9E6`。该指纹为代码编辑前值，包含并行窗口工作树，不能归因于 B。
- B 专属 PostgreSQL `psychology_learning_v1_r3_b_20261004`，测试前后均为 revision `0051`；测试后无其他活动连接。Redis DB4 测试后 PING 成功、0 keys/0 clients；MinIO bucket `v1-r3-b` 存在；3211/8211/9311 测试后均无监听。未启动 API、Web、CDP 或 Worker，也未使用预览资源。

### 实际改动与合同

- `server/app/modules/tutor/service.py`：绑定会话现按 CourseRelease manifest 的六字段 `publication_snapshots` pin 精确取 snapshot、material version、index job 和 embedding/domain 版本；允许被 supersede 的 PublicationSnapshot 与 `deprecated` DomainRelease，只要求 Material 仍 active/published、MaterialVersion 仍 parsed、IndexJob 为成功且 payload 指向同版本/DomainRelease，并存在该 Job build version 下 ready RetrievalUnit。移除对 `Material.current_version_id` 和 `superseded_at IS NULL` 的运行期过滤，检索仍通过固定 material version、DomainRelease 与 index build 限定。快照/Job/RetrievalUnit 缺失或不一致、材料撤回均生成 `unknown` 拒答，不查询最新版本替代。
- `server/app/modules/question_agent/router.py`：创建 Branch child ChatSession 时原样复制 parent 的 assignment/release pair；parent 是历史 NULL 就继续 NULL，不解析当前指派。创建和合并时重新验证已绑定的父/子成员权限；merge 要求两边的 pair 完全一致，避免分支在不同发布版本间合并。
- 本子项实际代码/测试增量文件：`server/app/modules/tutor/service.py`、`server/app/modules/question_agent/router.py`、`server/tests/test_tutor.py`、`server/tests/test_question_agent_branches.py`。未修改 memory/service、Tutor router、question_agent service、共享模型/迁移或跨模块路由。

### 测试证据与验收分层

- 新增历史快照正向 API/DB 用例：通过现有真实 upload、parse、embed、material publish API 生成旧 PublicationSnapshot、成功 IndexJob 和 RetrievalUnit；通过 CourseRelease API 固定 snapshot 并受控发布，创建旧 assignment 与 ChatSession；再对同一材料版本执行新的 Domain 绑定索引/发布，使旧 snapshot superseded、旧 DomainRelease deprecated，发布 Release 2 并切换 assignment。旧会话随后创建 Tutor turn，断言 Claim Scope 仍指向 Release 1，并把实际 EvidenceTicket → EvidencePointer → RetrievalUnit 反查到旧 IndexJob build version。随后将 Material 归档，下一回合 `unknown/publication_snapshot_unavailable`；移除 ClassMember 后会话读取 404。
- 上述正向测试的材料解析、Domain 索引任务与材料发布走真实 API/任务处理；DomainRelease 1/2 的测试状态记录由测试直接写 ORM，不是 DomainRelease 发布 API 的端到端验收。CourseRelease 创建/审核发布走真实接口；班级 assignment 换版由隔离测试夹具在事务中切换。
- Branch 测试覆盖：绑定 parent 创建 child 后轮换 assignment，child 恢复与 Tutor turn Scope 仍指向 parent 原 assignment/release，merge 成功且绑定不漂移；其他用户创建分支时 parent 404；成员撤权后 child 读取与 merge 均 404。另测历史 NULL parent 在后来出现新 assignment 时创建的 child 仍保持成对 NULL。
- 三条新增关键用例定向运行：**3 passed、2 warnings、31.27 秒**。四文件完整 B 回归（`tests/test_r3_memory_policy.py`、`tests/test_question_agent_branches.py`、`tests/test_learning_blocks.py`、`tests/test_tutor.py`）：**42 passed、2 warnings、248.80 秒**。B 相关 Ruff（`--no-cache`）与 `git diff --check` 通过。
- 已编码：历史 Release 精确快照检索、材料撤回拒答与 Branch pair 继承/复验。测试通过：上述 42 项仅是 B 专项隔离回归。环境验证：B 专属 DB/Redis/MinIO/端口在测试后现场复核通过。浏览器、真实学生/获授权课程材料、真实 DomainRelease 发布工作流及生产验证未完成；仍需主窗口静止共同树跨模块回归。本轮不宣称整个 R3 或 V1 完成。
