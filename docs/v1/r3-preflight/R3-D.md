# R3-D 交接报告

HANDOFF=COMPLETE; RESUMED=2026-10-05 15:13 +08:00

## 范围与状态

当前授权是 `docs/v1/V1并行启动状态.md` 中 R3-D 的部分 GO：干预 `/effect` 读模型安全化，以及 TeachingActivity/Run/Timeline/Annotation 模块服务与专属测试。P6 其余工作只在表格列明范围内处理；本报告完成后恢复原有限定 GO，不扩大文件权限。主窗口保留根路由聚合和所有共享文件。

P6-01/02：在教师获授权的 class Scope 内提供学情/干预聚合；使用 UTC 半开窗 `[start_at,end_at)`，默认最近 30 天、最多 90 天；唯一学生数 `n<5` 时隐藏精确 count/rate，响应标注 `suppressed_small_sample`。不得返回学生私聊、记忆正文或可反推个人的小组结果。

P6-03：TeachingActivity 为课程 Scope 下版本化定义；Run 固定班级、活动版本、CourseRelease/Assignment、目标摘要和发起人快照。遵循共享状态流 `planned → ready → active/paused → completed/cancelled`，写操作使用 `expected_version` 和幂等键；禁止状态跳跃或复活终态。Planned Timeline 来自计划记录，Actual Timeline 只来自持久业务事件并显示来源/延迟，按时间及稳定 ID 排序。

P6-05：`immediate_check`/`delayed_check` JSON 不是合格复测证据。必须关联至少两项合格、独立、跨情境测量才可展示描述性变化；否则 `not_measured`。非实验设计不得宣称因果效果。

P6-06：TeacherAnnotation 是独立 overlay，不更改原始证据、作答或 canonical；默认教师 Scope 可见，学生可见需显式发布；不记录不必要的敏感心理评断。Course Policy 只消费已发布 CourseRelease 中的不可变策略片段，不新增/修改共享课程发布服务。

## HEAD 与共同基线

- 检查时间：2026-10-05 11:06 +08:00（Asia/Shanghai）。
- HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。
- `scripts/r3-baseline-fingerprint.ps1` 连续两次结果：`IncludedEntries=509`，SHA-256 `1EBB24E36246DAF6B34F56350DDBAF5ECADD073802A2C0C9148010DF0457B256`。
- 主窗口最近记录基线是 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`。当前计数仍为 509，但指纹变化；脚本仅产出全树摘要，不能单凭摘要把差异归给 D。主窗口最新广播允许以当前可复现连续基线继续，不追溯不可归因的旧 hash。此报告写入会改变之后的全树指纹。

## 文件归属

- `server/app/modules/interventions/router.py`：当前 Git 状态为未跟踪；是共同工作树中已有文件，本窗口本次未改动，不将其既有内容认作本窗口增量。
- `server/tests/test_interventions.py`：当前 Git 状态为未跟踪；是共同工作树中已有文件，本窗口本次未改动，不将其既有内容认作本窗口增量。
- `server/app/modules/teaching_activities/**`：现场不存在；尚未新增。
- `server/tests/test_teaching_activities.py`：现场不存在；尚未新增。
- 未修改 `server/app/db/models.py`、Alembic 迁移、`server/tests/conftest.py`、`server/app/api/router.py`、OpenAPI 或共享验收文档；这些归主窗口。
- 本窗口尚无代码改动或新增业务测试；当前 git 状态中的其他模块变化不归属本窗口。

## 0049 合同、API 与共享依赖

0049 已提供 `TeachingActivity`、`TeachingActivityRun`、`TeacherTimelineEvent`、`TeacherAnnotation` 与 `CourseReleaseAssignment` 共享 schema。模块内按合同实现：

- `GET/POST /courses/{course_id}/teaching-activities`；`PATCH /courses/{course_id}/teaching-activities/{activity_version_id}`。
- `POST/GET /courses/{course_id}/classes/{class_id}/teaching-activity-runs`；`POST /courses/{course_id}/classes/{class_id}/teaching-activity-runs/{run_id}/actions`。
- `GET /courses/{course_id}/classes/{class_id}/timeline`；`POST /courses/{course_id}/classes/{class_id}/teacher-annotations`；`PATCH /courses/{course_id}/teacher-annotations/{annotation_id}`。
- 兼容现有 `GET /courses/{course_id}/interventions/{intervention_id}/effect`，只接受 class-bound intervention 且教师具备该 class Scope。

所有新端点先验证课程/班级 Scope，越权按合同返回 404；成功响应使用统一 envelope。主窗口负责在 `server/app/api/router.py` 注册、OpenAPI 导出和公共 fixture。等待根路由注册不阻塞模块内实现/专测，但端到端 API 验收需待主窗口集成。R3-C 学生 Growth/Me/Learning-SSE、R3-E assessments 与 R3-F 只读 Designer 的排他文件不同；当前未发现 D 文件冲突。

## D 专属隔离资源现场

只读核验时间：2026-10-05 11:06 +08:00。

- PostgreSQL `psychology_learning_v1_r3_d_20261004`：使用模块配置的连接凭据，但 URL 显式指向该 D 专属库；事务设置 `READ ONLY`。`alembic_version` 不存在（revision=`none`），public 业务表为 0。未执行迁移或写入。
- Redis `redis://127.0.0.1:6379/6`：`PING=True`，`DBSIZE=0`。
- MinIO bucket `v1-r3-d`：`bucket_exists=True`。
- `netstat -ano -p tcp` 检查 3213、8213、9313：无监听项。未启动服务；未做 bind listener 测试。
- 未使用默认测试库、DB0/DB1/DB9、主预览、其他窗口数据库或 Redis；未清理资源。

## 测试、浏览器与环境证据

- 本窗口未运行 D 专项测试；模块目录及其新专测当前尚不存在。
- 本窗口未运行浏览器验收；R3-D 当前排他范围没有获 GO 的教师前端文件。
- 主窗口记录的共享树后端全量 `313 passed, 2 warnings` 不是 D 专项证据，也不替代 D 的模块测试或浏览器验收。
- 资源探测为只读环境核验；没有启动 Web/API/Worker 或迁移数据库。

恢复工作后的验收计划：补充成功、class Scope 越权、UTC 窗口边界、`n<5` 隐私抑制、重复幂等、乐观锁冲突、非法状态/终态、Annotation 发布可见性及 JSON-only recheck 为 `not_measured` 等模块专测；使用分配的 D 专属 PostgreSQL/Redis。待主窗口注册路由后再做集成/API 验证。没有教师 UI 的本窗口浏览器证据不适用，若后续 GO 扩大 UI 范围再另行规划。

## 未决风险与验收边界

- 基线连续一致，但相对主窗口旧 hash 的全树文件级差异不可由指纹脚本单独归因；不将其作为 D 的文件增量。
- 现有两个 D 路径文件是共同树未跟踪文件，原始作者/全部既有内容无法仅凭 `git status` 确认；本窗口本次没有更改它们。
- 模块/API 尚未实现、模块测试和业务浏览器验收均未运行；TeachingActivity 路由当前未在 OpenAPI 注册。
- 没有真实班级、获准课程内容或独立复测证据；不作真实教学效果、因果或 V1 整体验收声明。
- 本交接确认可以开始表格限定的模块代码与专测；不允许修改模型、迁移、fixture、OpenAPI、根 router 或其他窗口文件。

## 2026-10-05 实施跟进

### 本窗口实际改动

- `server/app/modules/interventions/router.py`：为 `/effect` 加入 class Scope 校验、UTC 半开时间窗与 90 天上限、`n<5` 精确值抑制；仅接受关联且合格的独立复测证据，不把 JSON 自报检查当作证据；样本/证据不足时返回 `not_measured`，固定 `causal_claim=false`。
- `server/tests/test_interventions.py`：为干预派发/完成效果接口补 class Scope 和小样本抑制断言，以及超长时间窗负例。该数据库用例尚未运行。
- 新增 `server/app/modules/teaching_activities/{__init__.py,schemas.py,service.py,router.py}`：实现活动版本草稿/ready、绑定已发布课程版本与班级 roster 快照的 Run、版本与幂等控制的状态动作、持久 Timeline 事件读取、教师 Annotation 与显式发布校验；Timeline 不返回业务 payload。
- 新增 `server/tests/test_teaching_activities.py`：16 项纯逻辑/合同测试已通过；另有一项端到端数据库用例覆盖创建/重放、ready、固定 Run 快照、状态冲突、Annotation 发布门槛、Timeline 与越权，但未运行。
- 本窗口未改共享 models、迁移、fixture、根 router、OpenAPI 或其他窗口文件。

### 共享接手需求与接口

- 0049 中所需 `TeachingActivity`、`TeachingActivityRun`、`TeacherTimelineEvent`、`TeacherAnnotation`、`CourseReleaseAssignment` 字段已存在；本窗口未提出新增模型或迁移需求。
- 主窗口需在 `server/app/api/router.py` 注册 `app.modules.teaching_activities.router`，再导出并审阅 `contracts/openapi.json`；应确认公共 fixture 的 0049 迁移 head 能覆盖新测试使用的课程发布、班级分配与 roster 表。若 fixture 当前未覆盖，仍由主窗口调整。
- 学生读取已发布 Annotation 的 API 不在本轮授权路由合同中；如果产品要求学生实际消费 overlay，请主窗口确定共享 API 路径与权限合同后再排期。本轮只实现教师端写/读范围内校验，没有新增学生入口。
- 当前 R3-D GO 的具体排他项未列教师前端组件，因此本窗口没有新增或修改教师组件；课程只读覆盖层若需要浏览器验收，需主窗口另行明确文件归属/授权。

### 验证与未决风险

- `server/.venv/Scripts/python.exe -m ruff check --no-cache app/modules/interventions/router.py app/modules/teaching_activities tests/test_interventions.py tests/test_teaching_activities.py`：通过。
- `server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider -s -q tests/test_teaching_activities.py -k 'not teaching_activity_run_timeline_annotation_flow'`：`16 passed, 1 deselected, 2 warnings`。仅为不依赖数据库的逻辑/合同测试。
- 现场专属依赖端口 5432/6379/9000/3213/8213/9313 无监听；未迁移、未启动服务，也未连接默认/预览库。因此 `/effect` 数据库用例及完整教学活动 API 集成用例未运行；没有浏览器、环境服务、真实数据或真实教学效果证据。
- 根路由注册、OpenAPI 导出及数据库集成结果仍待主窗口/隔离资源恢复后验收。实现与 0049 模型字段映射、发布 assignment 锁定和并发冲突语义仍需在 D 专属库验证；在此之前不声称模块集成验收完成。

## 2026-10-05 13:42 任务跟进

- 按共享状态文档 13:36 任务入口复核，主窗口已记录 D 根路由注册；当前 D 下一项是补跑 D 专属数据库用例并记录 revision/测试残留，仅修 D 排他文件。
- 本次只读复查本机 5432、6379、9000、3213、8213、9313 均无监听。共享任务同时要求主窗口先核验分配库状态并负责在 D 库执行 `upgrade head` / `alembic check`；因此本窗口未运行数据库/API 用例、未连接替代数据库、未启动服务。
- 非写库验证复跑：D 目标文件 Ruff 通过；教学活动纯逻辑/合同用例 `16 passed, 1 deselected, 2 warnings`。数据库集成、浏览器与真实数据验证仍未完成，等待隔离资源与迁移准备的共享交接。

## 2026-10-05 15:13 修复与 D 专库验收

- 接收共享状态文档 14:06/14:25 D 修复子项 GO 后，先复核工作树范围及连续基线：`HEAD=4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`，531 entries，SHA-256 `132811958DC3B98E7282F818F2F4C67419870A1F9C9BC9C8550637A0A47C8AFF`，连续两次一致。共享 `models.py`、Alembic、fixture、根 router、OpenAPI 仍为其他窗口所有，本窗口未修改。
- D 专属资源现场：数据库 `psychology_learning_v1_r3_d_20261004` 在本窗口测试前为 `0050`、73 张 public 表、无其他会话；Redis DB6 `PING=true/DBSIZE=0`；MinIO bucket `v1-r3-d` 存在。数据库全量只读行数检查仅发现迁移初始化的 `organizations=1`，其余表为空。数据库迁移已由主窗口执行，本窗口未迁移。
- 修复 `server/app/modules/teaching_activities/router.py`：Run action 写入审计、Timeline 与 outbox 后显式 `await db.refresh(run)`，确保响应序列化读取已刷新的数据库行，避免 async ORM 对过期 server timestamp 发起隐式加载并触发 `MissingGreenlet`。
- 在 D 专属数据库/Redis 上运行 `tests/test_teaching_activities.py tests/test_interventions.py`：**22 passed, 2 warnings, 39.74s**。Ruff 目标文件检查通过。覆盖原失败 action 响应路径及指定模块用例。
- 测试后只读复核：数据库仍为 `0050`，无其他会话，唯一非空业务表仍为 `organizations=1`；Redis DB6 仍为 0 keys；MinIO bucket 保留。fixture 已回收课程/用户等测试数据，没有清理共享或隔离存储资源。
- 本轮未启动 API/Web/CDP，没有教师 UI 范围或浏览器验收授权；没有真实课程、复测或学习效果证据。数据库专项工程测试通过不等于真实教学或 V1 验收完成。
