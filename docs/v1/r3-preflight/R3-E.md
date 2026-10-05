# R3-E 窗口交接报告

HANDOFF=COMPLETE; RESUMED=2026-10-05 10:58:18 +08:00

更新时间：2026-10-05。依据 `V1并行启动状态.md` 中 R3-E 的部分 GO 与主窗口 2026-10-05 稳定回归检查点整理。仅报告 R3-E 排他范围；不代表 P7-06 获批或 V1 整体验收。

## 恢复前现场复核（2026-10-05 10:58 +08:00）

- 按 `scripts/r3-baseline-fingerprint.ps1` 连续运行两次，均为 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、509 entries、指纹 `637905FA569A17DC3285823DC96B25610B02B9BE98BF5427CE471C6D1B98C907`。主窗口最近基线为 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`。单一全树摘要没有逐文件历史清单，不能从摘要推导所有窗口差异；R3-E 当前可见增量是下列 E 排他文件状态及本报告，未把共享文件或其他窗口文件归为 E。指纹脚本包含本报告，故此次补记本身会使下一次摘要变化；本值是本次恢复前连续一致的共同快照。
- `git status --short` 的 R3-E 范围：修改 `server/app/modules/assessments/router.py`、`schemas.py`、`web/components/StudentAssessments.tsx`、`web/components/TeacherAssessments.tsx`；新增 `server/app/modules/assessments/service.py`、`policy.py`、`server/tests/test_assessment_quality.py`、`server/tests/test_assessment_reliability.py`、`web/tests/assessment-timeout-contract.test.mjs`、本报告。未在 `models.py`、Alembic、`conftest.py`、`app/api/router.py` 或 OpenAPI 中登记 R3-E 改动。
- PostgreSQL：显式将 `DATABASE_URL` 指向 `psychology_learning_v1_r3_e_20261004` 后执行 `python -m alembic current`，结果 `0049 (head)`。该命令只读，没有迁移或测试清理。
- Redis：`redis.Redis.from_url('redis://127.0.0.1:6379/7')` 的 `PING=True`、`DBSIZE=0`。MinIO：配置 endpoint `127.0.0.1:9000` 上只读 `bucket_exists('v1-r3-e')=True`。
- Web/API/CDP：`Get-NetTCPConnection -State Listen` 过滤 3214、8214、9314 无监听；未启动服务。3000/8000 未用于本轮检查或测试。
- 当前树与主窗口稳定回归基线一致于代码/测试快照；没有发现 R3-E 与 C/D/F 排他文件的路径冲突。R3-E 只恢复表格许可子范围，主窗口仍唯一维护共享模型/迁移/OpenAPI/fixture/路由注册。

## 范围与共同基线

- 共同 HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。主窗口检查点记录本状态文档更新前共同树指纹为 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`（509 项）。本报告未重算逐窗口增量，不能把全树指纹解释为 R3-E 独有差异。
- 当前 R3-E 授权范围：P7-01/02/04/08，AIGradingSuggestion 保持 disabled。P7-06 人工评分边界不在本次 GO 内；本报告不扩展该范围。
- 后端目标文件：`server/app/modules/assessments/router.py`、`schemas.py`、新增 `service.py`、`policy.py`；专测 `server/tests/test_assessment_reliability.py`、`server/tests/test_assessment_quality.py`。前端目标文件：`web/components/TeacherAssessments.tsx`、`web/components/StudentAssessments.tsx`、`web/tests/assessment-timeout-contract.test.mjs`。这些文件在当前共享树呈修改或未跟踪状态；其余窗口文件不属于 E。

## 实现摘要

- 增加 Rubric 版本创建/查询/审批 API，要求主观题、标准项分值总和一致、key 与证据引用不重复；审批需课程教师且作者不得自审，并记录审计。正式测评发布门禁检查题目 formal 用途批准、主观题 Rubric 批准及其题目版本绑定。
- 增加测评预览与服务端发布门禁；创建向导配置用途、开放/截止时间、AI 策略和结果可见策略，预览通过后才建草稿，发布仍需单独确认。结果策略包含练习即时、截止后、评分后、教师手动发布；未知/缺失策略 fail-closed。学生结果端点在策略未满足时返回 `403 ASSESSMENT_RESULT_NOT_RELEASED`，提交响应不泄漏未开放分数；手动发布使用版本检查和幂等回放。
- 提交故障回归覆盖事务回滚后重试；另有版本冲突、截止时间、跨课程权限、提交/人工评分幂等、formal 用途、截止后结果和手动发布回归。
- 学生进行中恢复继续通过 attempt start/resume 与逐题保存路径；`/result` 对未开放成绩 fail-closed。该 API 行为尚无本轮业务浏览器证据确认不会破坏真实恢复交互。

## 共享依赖与接口

- 工作区 `0049` 已含 `RubricVersion`、`QuestionPurposeApproval`、Assessment purpose/result policy、`AssessmentItem.rubric_version_id`、`results_released_at` 等字段；R3-E 未提出新增共享模型或迁移。
- OpenAPI 快照由主窗口统一导出。主窗口稳定检查点记录 148 paths 与稳定 SHA-256 `EAF93FEEC24BF1116508A57534889CBB125936C2CD295EFCDA4DA7CC5FA6DC61`；E 不修改 OpenAPI、共享路由注册或 fixture。
- `course_release_assignment_id` 当前未接入测评工作流；与 Release assignment 的正式绑定需主窗口定义共享接口后另行处理。
- 与 C 的普通学生测评页面边界以状态表为准；D 的 Activity API 和 F 的 Release/Assignment 工作流归各自/主窗口，本报告没有改动这些范围。

## 隔离环境与验证证据

- 分配资源：PostgreSQL `psychology_learning_v1_r3_e_20261004`、Redis `redis://127.0.0.1:6379/7`、MinIO bucket `v1-r3-e`、Web/API 3214/8214、CDP 9314、queue `v1-r3-e`。这组值是 GO 记录中的分配；本次补交时没有重新连接数据库、清理 Redis、启动服务或重新核验 bucket。
- 本窗口先前在分配数据库/Redis 环境执行的测评定向后端套件记录为 12 passed、2 条框架弃用警告；其后代码有变更，因此该数字不单独作为当前快照证据。
- 主窗口 2026-10-05 稳定共同树全量后端回归为隔离 root 库 **313 passed、2 warnings**（1082.31 秒）；前端 Node **46/46**、typecheck 通过、lint 0 errors/3 个既有 warnings。主窗口还记录 root 全仓 Ruff 通过。这些是共同树集成证据，不代替 R3-E 独立业务浏览器验收。
- 本会话最新可执行的前端 timeout 合同测试为 **2/2 passed**。本地 Ruff 尝试因只读沙箱无法创建 `.ruff_cache` 临时文件而失败，未产生代码修改。
- Chromium 证据仅覆盖 E 的物理快照、独立构建、代理 stub 和基础 shell；没有覆盖 Rubric 作者/审核、formal 门禁、结果延迟开放、手动发布或学生结果恢复的真实业务浏览器流程。

## 未决问题、风险与交接请求

- `service.py` 当前检查 Rubric evidence refs 非空且去重，但未确认每个引用属于对应 `QuestionVersion.evidence_ids`；Rubric criteria 的评分锚点也未见完整数值范围/边界覆盖验证。需窗口恢复后补服务端约束与负例测试。
- `TeacherAssessments.tsx` 可审批 formal 用途并选择已批准 Rubric，但尚无 Rubric 编辑/创建与审核队列 UI；教师需经 API 或其他入口准备 Rubric。
- 正式结果披露规则目前按实现默认策略运行，机构级评分可见政策仍属外部输入；不得将工程默认值视为机构批准。
- AI 主观评分建议没有启用、伪造或发送学生答案给外部模型。没有获准数据与供应商不留存/不训练承诺时继续保持 disabled。
- 需主窗口确认下一步状态：本报告补齐后是否解除短期共同树冻结，以及 R3-E 是否继续保持受限 GO 或转 HOLD。解冻前不新增代码、测试写库或启动业务服务。

## 总体验收边界

本报告不宣称 R3-E 已完成，也不宣称整个 V1 完成。Rubric 引用/锚点校验及手动发布结果浏览器路径已有本窗口定向证据；仍待正式用途审批浏览器验收、Rubric 编辑/审核 UI，以及主窗口统一 OpenAPI、静态和集成验收。当前 production build 仍受 R3-G 的 TypeScript 错误阻塞。

## 最新实现与验收补记（2026-10-05 11:25 +08:00）

- 本轮修正并扩展 Rubric 校验：evidence refs 必须是当前 `QuestionVersion.evidence_ids` 子集；标准项 points 与总分必须为有限正值且求和匹配；anchors 必须是有限且唯一的数值分，覆盖 0 到该标准项满分。审批时再次校验已存 Rubric。测试新增外部证据引用和缺 0 端点锚点两条负例，并断言拒绝时没有创建 Rubric。
- 实际课程测验页面路由原来仍调用旧 `TeacherCourseSupportPages`，页面没有结果发布按钮。已将排他页面 `web/app/teacher/courses/[courseId]/assessments/page.tsx` 接到 `TeacherAssessments` 测评向导，并增加 embedded/course ID 参数，避免实际课程页面继续展示旧实现。只改了此测评专属页面和 `web/components/TeacherAssessments.tsx`。
- 本轮后端命令：显式 `DATABASE_URL`/`PSYCHOLOGY_TEST_DB=psychology_learning_v1_r3_e_20261004`、Redis DB7、E 专属 Celery URL/queue、`MINIO_BUCKET=v1-r3-e` 后执行 `python -B -m pytest -s -p no:cacheprovider -q tests/test_assessment_reliability.py tests/test_assessment_quality.py`，**13 passed、2 warnings、108.90 秒**；Ruff `python -B -m ruff check --no-cache app/modules/assessments tests/test_assessment_reliability.py tests/test_assessment_quality.py` **通过**。Web timeout 合同 Node 测试 **2/2 passed**，新增浏览器脚本 `node --check` 通过。`pnpm exec eslint` 本机未能启动（shell 未识别 eslint 命令），不记为通过。
- 浏览器业务验收：快照 `r3-e-result-policy-ui-20261005` 的 Next production build 编译成功，但全项目 TypeScript 阶段被 R3-G 文件 `StudentMiniLabPanel.tsx:167` 的 `MiniLabSession.invalidation_reason` 类型错误阻断；未修改该越界文件。为完成实际路由验收，在同一隔离物理快照用 `next dev` 启动 Web 3214，API 8214 连接 E 数据库/Redis DB7/bucket，Edge CDP 9314；完成合成教师/学生、课程和测评操作。结果：学生提交响应无分数；发布前 `/attempts/{id}/result` 为 403 `ASSESSMENT_RESULT_NOT_RELEASED` 且学生 UI 显示延迟开放提示；教师从实际课程测验页面手动发布后，学生重新打开测验可读取同一 attempt，结果为 HTTP 200、分数 1。**该浏览器脚本真实通过**，截图 `C:\Users\free\AppData\Local\Temp\r3-e-assessment-result-policy\student-result-after-release.png`。服务、浏览器均已停止，3214/8214/9314 监听已释放；截图和测试合成数据保留，不清理。
- 当前共同基线复采（代码与验证修改完成、更新本段之前）按 `scripts/r3-baseline-fingerprint.ps1` 连续两次一致：HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、513 entries、`3932596CB19676819F2FA5561B735AA3EC7683D62DD08ABC6AEE97F568F4D8C5`。主窗口基线 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146` 没有逐文件 manifest，不能仅凭全树 digest 归因所有历史差异；本段报告更新自身会改变下一次全树 digest。此刻 E 的精确变更集合为：`server/app/modules/assessments/router.py`、`schemas.py`、`service.py`、`policy.py`；`server/tests/test_assessment_reliability.py`、`test_assessment_quality.py`；`web/components/StudentAssessments.tsx`、`TeacherAssessments.tsx`、`web/app/teacher/courses/[courseId]/assessments/page.tsx`、`web/tests/assessment-timeout-contract.test.mjs`、新增 `assessment-result-policy-browser.mjs`；本报告。隔离运行快照保留于 `web/.r3-runtime/r3-e-result-policy-20261005` 和 `r3-e-result-policy-ui-20261005`，是工具生成的未跟踪源码/构建证据，不属于共享源码或其他窗口文件。
- 未修改主窗口拥有的 `models.py`、0049 或其他迁移、`conftest.py`、`app/api/router.py`、OpenAPI；当前这些文件虽在 Git 工作树显示共享改动/未跟踪迁移，均为主窗口既有工作，不归 R3-E。未触碰 C/D/F 文件。主窗口稳定树全量 313 passed 是集成证据，不计作本窗口专项；本窗口专项证据是上列 13 passed 和浏览器结果策略全链。
- 尚未验收：Rubric 编辑/审核队列的完整教师 UI；正式用途审批的独立浏览器流程；机构级结果可见规则输入；Next production build 的最终成功（被并行 R3-G 的非 E TypeScript 错误挡住）。Rubric E2E 与当前 R3-E 学生结果策略浏览器路径已覆盖。P7-06 仍不在本轮授权内，AIGradingSuggestion 继续 disabled。

## 最新 build 与环境状态补记（2026-10-05 11:54 +08:00）

- 按主窗口 11:51 广播，R3-G 已修复此前的 `MiniLabSession.invalidation_reason` 类型问题；此前 11:25 记录的 E build 失败是旧快照/旧工作树结果，不再作为当前 build 状态。通过 `scripts/prepare-r3-web-runtime.ps1 -Window e -SnapshotName r3-e-final-build-20261005` 创建新的 E 物理源码快照；在该快照设置 `PSYCHOLOGY_API_PROXY_TARGET=http://127.0.0.1:8214`、`PSYCHOLOGY_NEXT_DIST_DIR=.next-r3-e` 后运行 `pnpm build`。Next 16.3.5 production build 成功：编译、TypeScript、页面数据收集和 24/24 静态页生成通过，完整测评和工作区路由清单正常。构建产物仅写入该隔离快照。
- 首次 build 调用使用未登记的 `.next-r3-e-final` distDir，在加载 Next 配置阶段按白名单拒绝；没有进入编译。改用已登记的 `.next-r3-e` 后成功。此为命令参数修正，不是代码失败。
- 11:31 对分配的 E 环境做只读监听复核：5432、6379、9000、3214、8214、9314 均无 listener。遵从 11:30 共享现场要求，未启动依赖服务、未运行写库测试或重新运行浏览器。先前在 E 隔离环境通过的结果策略浏览器链证据仍按其原运行时间记录，不冒充当前环境在线验证。
- 尚待资源恢复后重新核验 E 专属 DB revision、Redis DB/key、MinIO bucket、3214/8214/9314，再决定是否重跑写库专项与结果策略浏览器链。仍未验收正式用途审批业务浏览器流程、Rubric 编辑/审核队列完整 UI 和机构评分可见规则；P7-06 仍不在授权范围，AIGradingSuggestion 保持 disabled。生产 build 的新通过证据已补齐，但不代表 R3-E 或 V1 整体验收完成。

## 12:10 质量门修复与 Rubric/用途 UI 补齐（2026-10-05 12:14:43 +08:00）

- 对照主窗口 12:08/12:10 广播，`TeacherAssessments.tsx` 中悬空的 `approveFormalPurpose` 按钮回调已在 E 排他文件内移除；formal 决议统一通过下方用途复核区提交，并要求明确填写不少于 8 个字符的理由，可批准或撤销。服务端仍负责作者自审拒绝和审计。
- 测评页新增 Rubric 草稿版本编辑：证据只能从当前 `QuestionVersion.evidence_ids` 选择；支持多评分项、每项正分值、标准说明、0 分/满分文字锚点；`max_score` 由评分项分值求和。草稿版本按题目版本列出；审批理由不少于 8 字，批准调用现有 `/rubrics/{id}/approve` 服务端接口。向导仅允许选择 `approved` Rubric。页面明确 Rubric 只供教师人工评分，不自动评分且不产生 AI 评分建议；未触碰 P7-06/AIGradingSuggestion。
- 新增 E 专属 Node 合同 `web/tests/assessment-rubric-ui-contract.test.mjs`（3 项）：证据/题目版本绑定、显式复核理由/API、人工评分边界。与既有 timeout 合同一起运行 `node --test tests/assessment-rubric-ui-contract.test.mjs tests/assessment-timeout-contract.test.mjs`，**5 passed**。新增隔离浏览器脚本 `web/tests/assessment-rubric-purpose-browser.mjs`，覆盖题目作者 formal 自审拒绝、Rubric 作者自审拒绝、独立教师审批、正式测评预览门禁通过；`node --check tests/assessment-rubric-purpose-browser.mjs` 通过。需要独立 `R3_E_REVIEWER_EMAIL` 课程教师账号。当前资源不可用，因此脚本未运行。
- 首次含新 UI 的快照 build 在 TypeScript 阶段发现旧按钮仍引用已移除处理器（TS2304）；移除该旧按钮后，以 `scripts/prepare-r3-web-runtime.ps1 -Window e -SnapshotName r3-e-rubric-ui-final-20261005` 新建 E 物理快照，再使用白名单 `PSYCHOLOGY_NEXT_DIST_DIR=.next-r3-e` 执行 `pnpm build`，Next production build、TypeScript、页面数据收集和 **24/24** 静态页生成通过。该是 E 隔离快照证据；按主窗口 12:10 要求，共享 checkout 的 `pnpm typecheck`/`pnpm lint` 应由主窗口在窗口更新后统一复跑。尝试在快照执行 `pnpm exec eslint components/TeacherAssessments.tsx` 因 shell 找不到 `eslint` 可执行命令失败，不计通过。
- 12:13 只读复核分配资源监听：5432/6379/9000/3214/8214/9314 均无监听。没有运行数据库测试、启动服务或真实浏览器。需待服务恢复后重验 E 的 DB revision、Redis DB/key、bucket、专属端口，再重跑测评/Rubric 后端套件及两条 E2E 浏览器脚本。
- 当前 E 变更清单另新增上述 `web/tests/assessment-rubric-ui-contract.test.mjs`、`web/tests/assessment-rubric-purpose-browser.mjs`；其余 E 文件/共享文件边界不变。仍待 Rubric/用途真实浏览器、结果策略浏览器在资源恢复后的复验、机构级评分可见规则输入；不宣称 R3-E 或 V1 整体验收完成。
## 隔离服务复验与当前交付补记（2026-10-05 13:46 +08:00）

- **隔离资源复核：** `psychology_learning_v1_r3_e_20261004` 当前 Alembic revision `0049`、73 张 public 表；Redis `127.0.0.1:6379/7` PING 成功、`DBSIZE=0`；MinIO `127.0.0.1:9000` 的 `v1-r3-e` bucket 存在。R3-E 专属端口 3214/8214/9314 在测试前空闲。本轮结束后由 PID/命令行核对并停止自己启动的服务进程树，三个端口现已释放；Redis 仍为 0 keys。测试和 E2E 合成用户/课程/题目/作答等记录留在 E 专属库中，未清理。没有访问共享预览库。
- **基线与文件归属：** 测试前 `git status` 中 E 变更仍仅为本报告列出的 assessments 模块、测评页面和 E 专测；没有编辑共享 models、迁移、conftest、OpenAPI 或根路由。共同 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；回归后基线脚本连续两次得到 525 entries、指纹 `D1C241D5657FEF741E22FCBE6B5F04B4A373D5C4E15A9D8FBB043DBFF23735B0`。该指纹为共享树快照，不归因给 E 单窗。
- **后端回归：** 在显式 `PSYCHOLOGY_TEST_DB=psychology_learning_v1_r3_e_20261004`、Redis DB7、`TASK_BACKEND=in_process` 下重跑 `test_assessment_reliability.py` 与 `test_assessment_quality.py`，**13 passed、2 warnings、87.46 秒**。覆盖乐观锁/答案版本冲突、attempt 恢复可见范围、提交及人工评分幂等、课程成员权限、服务端时间和终态、formal 用途/结果门禁、批准 Rubric 冻结、证据归属与 0/满分锚点负例、提交故障事务回滚重试、手动发布版本与学生重开同一结果。E 范围 Ruff `ruff check --no-cache app/modules/assessments tests/test_assessment_reliability.py tests/test_assessment_quality.py` 通过。
- **Node 合同：** `assessment-rubric-ui-contract.test.mjs` 与 `assessment-timeout-contract.test.mjs` 合计 **5 passed**；包含证据/题目版本绑定、显式审批理由、人工评分边界/AI suggestion disabled、截止自动提交和关闭后恢复既有 attempt。
- **真实隔离浏览器：** 使用物理快照 `web/.r3-runtime/r3-e-rubric-ui-final-20261005` 的 production build、API 8214、Web 3214 和 Edge CDP 9314。`assessment-result-policy-browser.mjs` 通过：提交响应没有分数；教师发布前学生 UI 延迟提示且结果 API 为 403 `ASSESSMENT_RESULT_NOT_RELEASED`；教师手动发布后同一 attempt 的结果为 200、score=1。截图：[student-result-after-release.png](C:/Users/free/AppData/Local/Temp/r3-e-assessment-result-policy/student-result-after-release.png)。`assessment-rubric-purpose-browser.mjs` 通过：题目作者 formal 自审与 Rubric 作者自审均被拒，另一位课程教师审批两者后正式测评预览门禁通过。首个浏览器尝试使用 `.test` 地址而被 `EmailStr` 在 HTTP 422 拒绝；改用合成 `example.com` 地址后两条脚本均通过，属于测试输入格式修正，不是业务链路失败。
- **当前共享质量门引用：** 主窗口 13:32 记录共同 Web `pnpm test` 55/55、typecheck 通过、lint 0 errors/3 warnings。该项是主窗口共享 checkout 的快照结果；E 独立 production build 仍按 11:54 的物理快照记录为通过，不把本轮运行表述成新 build。
- **边界与未决项：** 本轮不包含 P7-06；AIGradingSuggestion 继续 disabled，Rubric 只支持教师人工评分。机构级评分可见/保留政策仍待外部确认；`course_release_assignment_id` 与正式 Release Assignment 的绑定仍需主窗口共享接口决策。真实教材/课程数据、正式班级教学等价性未验证。R3-E 当前有后端/Node/隔离浏览器证据，但 V1 整体静止树全量回归与全局验收仍由主窗口完成。
## 最终 UI 质量门与浏览器 trace 补记（2026-10-05 13:56 +08:00）

- **E 页面警告修复：** 将 `TeacherAssessments` 的 `load` 回调改为按 `courseId` 稳定化，并让加载 effect 依赖该回调。`web/components/TeacherAssessments.tsx` 定向 ESLint 现为 **0 errors / 0 warnings**；E Node 合同仍 **5 passed**。`tsc --noEmit --incremental false` 通过。普通 `pnpm typecheck` 在本机只读沙箱尝试写 `web/tsconfig.tsbuildinfo` 时收到 `EPERM`，因此不把该命令记作通过。
- **最终隔离 build：** 由修正后当前源码新建物理快照 `web/.r3-runtime/r3-e-final-contract-fix-20261005`；白名单 `.next-r3-e` 下 production build 成功，Next 编译、TypeScript、page data、**24/24** 静态页生成通过。两条业务浏览器脚本均在此最终快照上复跑通过。
- **Reviewer 与证据文件：** 独立课程审核教师合成账号 `assessment-reviewer-20261005054309@example.com`（本地脚本默认测试口令；只存在于 E 隔离库）。Rubric/用途审批结果截图：[rubric-purpose-approved.png](C:/Users/free/AppData/Local/Temp/r3-e-assessment-rubric-purpose/rubric-purpose-approved.png)；Edge CDP trace：[rubric-purpose-trace.json](C:/Users/free/AppData/Local/Temp/r3-e-assessment-rubric-purpose/rubric-purpose-trace.json)，JSON 有效、4310 events、1,039,378 bytes。结果披露截图：[student-result-after-release.png](C:/Users/free/AppData/Local/Temp/r3-e-assessment-result-policy/student-result-after-release.png)。这些是合成账号/合成测评的隔离工程证据。
- **最终共同基线：** 代码/浏览器验收后、更新本段前连续两次运行基线脚本，HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、526 entries、指纹 `54A105A61840186D27E24FB74BD3F1A8D615F5FCD1ABD96EED5A55DEB87965CB`。指纹属于共享树摘要，不能将所有变化都归属 E。
- **当前文件差异补充：** 在此前 E 文件清单上，`web/components/TeacherAssessments.tsx` 增加 `useCallback` 依赖修复，`web/tests/assessment-rubric-purpose-browser.mjs` 增加截图与 CDP trace 输出；未更改共享文件。所有本轮启动进程树已停止，E 端口 3214/8214/9314 只读复查均空闲。合成测试数据依前述记录保留在 E DB，未清理。
- **依赖与剩余验收：** 主窗口共享回归、OpenAPI/root integration 和全量静止后端回归仍由主窗口执行。机构评分可见/保留政策、答案授权和生产供应商承诺没有外部输入；因此 AIGradingSuggestion/P7-06 仍 disabled，也未发送答案到模型。V1 整体不据本窗口结果宣称完成。
## 0050 Attempt 运行版本绑定子范围（共享 GO 2026-10-05 14:06 +08:00）

- **授权与边界：** 主窗口已明确允许 E 在 `server/app/modules/assessments/**` 与 E 专测中，为新建 Attempt 固定适用的 `CourseReleaseAssignment`/`CourseRelease`；恢复既有进行中 Attempt 必须复用原绑定，不随之后换版漂移。禁止跨 class 读取。仍不得改 `models.py`、Alembic、conftest、根路由、OpenAPI 或总文档。
- **共享 schema 合同：** 主窗口迁移 `0050_bind_learning_runs_to_release_assignments.py` 给 `attempts` 增加 nullable `course_release_assignment_id` 与 `course_release_id`、外键/索引及成对空值约束；历史行保持 NULL，不回填。assessment 当前有可选 `course_release_assignment_id`；当前 attempt start 没有显式 class context，创建路径只写 `assessment_id`/`user_id` 并先返回已有进行中 Attempt。E 的服务实现须先核验当前用户真实 active `ClassMember` Scope、同课程 active Assignment 和对应可运行 CourseRelease；Assignment 若绑定到 assessment，则必须与该学生班级匹配。适用指派唯一时新 Attempt 同事务写入 assignment/release 双 ID；无可适用 assignment 保留旧兼容 NULL；多班级产生多个可适用指派且请求未给 class context 时按合同 fail closed（建议 `409 COURSE_RELEASE_CONTEXT_AMBIGUOUS`）。最终精确筛选/错误语义在编码前需与本节合同保持一致，不能选第一条或跨班借用。
- **测试合同：** E 专测需覆盖 assignment/release 同事务成对写入、同课越权/非成员/跨 class 拒绝、多班级歧义、无 assignment 的 NULL 兼容、assignment/deprecated 状态边界、已有 attempt 恢复保持旧 ID、后续换版不漂移，以及 pair 字段成对约束。现有 0050 是主窗口共享迁移，不提出新增模型/迁移/fixture；若测试需要 class 发布 fixture，应仅在 E 专测内创建并走实际只读课程服务合同，不改公共 fixture。
- **硬性验证前置条件：** 主窗口 14:06 明确要求先在 root 专用库执行 `alembic upgrade head` + `alembic check`，并将真实 revision 记录回 `V1并行启动状态.md`；在其满足前，E 不得在自有 `psychology_learning_v1_r3_e_20261004` 上升级到 0050、运行依赖新列的写库测试或启动相关浏览器链。E 库最近现场 revision 是 0049；DB7/bucket/端口此前可用并不替代此 root migration gate。本节仅更新授权/准备记录，未实施新绑定代码或迁移。
- **准备时基线：** 最新一次 E 文件范围 `git status` 与既有 E 清单一致；主窗口广播共同 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、527 entries、`ADCC4DE9291CE3488680987D2D25DDB03863C76E9E1E1AB2E5A0A49F35FF401E` 后，本轮又现场连续两次取得 528 entries、`45D814505945ACE9A7120AE32D8DA94DD79BE8B91E6D660123A788A241AC7B12`。两者是不同时间的共享树摘要；当前值不把并行共享差异归因给 E。
- **外部合同依赖/风险：** 目前 `POST /assessments/{assessment_id}/attempts` 无 class context，而主合同要求不能跨班并对多匹配 fail closed；保留该 endpoint 形状并在多匹配时返回 409 可满足默认安全规则，但多班学生要从具体班级启动时，若产品需要支持必须先由主窗口确认是否加显式 `class_id` 输入并负责导出 OpenAPI。Release Assignment/旧 Release 的历史 Search 固定版本仍未端到端，Attempt 绑定不等于历史教材检索已验收，也不能据此把 Impact 置为 measured。

## 0050 Attempt 绑定实现与最终隔离回归（2026-10-05 14:40 +08:00）

- **实现：** `POST /assessments/{assessment_id}/attempts` 创建新 Attempt 时，仅从该学生当前有效的课程/班级成员关系查找 active `CourseReleaseAssignment` 和同课程的已发布 `CourseRelease`，唯一匹配则在 Attempt 同事务写入成对 ID。测评本身固定 assignment 时只接受学生有权访问的那个班级指派。没有可适用指派时保留旧行兼容 NULL；仍有 active assignment 但没有可运行 Release 时拒绝启动；多个班级均有可运行指派时返回 `409 COURSE_RELEASE_CONTEXT_AMBIGUOUS`，不返回班级/学生额外信息。
- **恢复与读取范围：** 已有进行中 Attempt 在任何新解析之前返回原 Attempt，不重算/漂移 Release 绑定；其 assignment 已换版后仍保留原 ID。带绑定的 Attempt 所有者访问、续作和结果读取要求仍属于绑定班级，否则统一 404。旧 NULL 绑定 Attempt 沿用旧兼容行为。
- **回归覆盖：** 新增 E 专测验证唯一指派时成对写入；同一班级后续切换到新 Release 后恢复仍返回旧 Attempt/旧 ID；两个班级指向同一仍发布 Release 时 fail closed；退出绑定班级后续作和结果读取均 404。修正了最初歧义用例把第二个课程 Release 发布后退役第一个的夹具问题，最终测试使用两个班级指派同一个已发布 Release。
- **隔离数据库与迁移：** 仅访问 `psychology_learning_v1_r3_e_20261004`。升级前只读确认 E DB revision `0049` 且无其他连接；执行 `alembic upgrade head` 后为 `0050 (head)`，`alembic check` 输出 `No new upgrade operations detected`（含既有 pgvector type warning）。Redis 仅用 `127.0.0.1:6379/7`，测试前 `PING=true/DBSIZE=0`；MinIO 仅确认 E bucket `v1-r3-e` 存在。最终回归后 Redis DB7 为 0 keys。没有接入预览数据库或 Redis DB0。
- **最终后端/静态专测：** `tests/test_assessment_reliability.py tests/test_assessment_quality.py` 在 E 库 **16 passed、2 个 Starlette/httpx 弃用 warning，119.07 秒**；新增三项绑定专项单独 **3 passed**。E 范围 Ruff 通过；测评 rubric UI/timeout Node 合同 **5/5**、两个浏览器脚本 `node --check` 通过。先前一次完整试跑为 14 passed/1 failed，唯一失败是当时歧义测试用了已退役 Release；修正测试夹具后核心用例与最终全套均通过。
- **真实浏览器复验：** 使用 E API 8214、物理 production build 快照 `web/.r3-runtime/r3-e-final-contract-fix-20261005` 的 Web 3214、Edge CDP 9314，三条服务均在本轮结束后停止，端口释放。结果策略脚本最终通过：提交响应无分数、教师手动发布前结果 API 403 `ASSESSMENT_RESULT_NOT_RELEASED`、发布后同一 Attempt 结果 200/score=1；截图：[student-result-after-release.png](C:/Users/free/AppData/Local/Temp/r3-e-assessment-result-policy/student-result-after-release.png)。formal/Rubric 脚本最终通过：两类作者自审均拒绝、独立教师批准后正式用途预览门禁开放；截图：[rubric-purpose-approved.png](C:/Users/free/AppData/Local/Temp/r3-e-assessment-rubric-purpose/rubric-purpose-approved.png)，Edge trace JSON 有效、4417 events、1,074,154 bytes：[rubric-purpose-trace.json](C:/Users/free/AppData/Local/Temp/r3-e-assessment-rubric-purpose/rubric-purpose-trace.json)。均为合成账号和测评。
- **前端质量门：** `assessment-rubric-ui-contract.test.mjs` + `assessment-timeout-contract.test.mjs` 最终 5/5；最终 E 快照中直接运行 `node_modules/typescript/bin/tsc --noEmit --incremental false` 通过。此前最终快照 `.next-r3-e` 的 production build 通过，24/24 路由生成；本段后没有改前端源码。当前共享 checkout 直接 `pnpm exec tsc` 未能启动，原因是其工作目录没有可解析的 `tsc` 命令；不据此宣称共享 checkout 全局 typecheck 新通过。共享构建/全局质量门仍由主窗口统一验收。
- **最终范围/基线：** E 当前专属文件差异为 `server/app/modules/assessments/router.py`、`schemas.py`、`service.py`、`policy.py`，`server/tests/test_assessment_reliability.py`、`test_assessment_quality.py`，测评专属 `web/components/StudentAssessments.tsx`、`TeacherAssessments.tsx`、`web/app/teacher/courses/[courseId]/assessments/page.tsx`、四个 `web/tests/assessment-*` 文件，以及本报告。没有改 models/Alembic/conftest/根路由/OpenAPI/共享构建配置或其他窗口文件。代码验收完成、更新本段前，基线脚本两次一致：HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、531 entries、指纹 `F99A8367F82352BCB81A9C6EDBF0D22605BC92DFA9689318E06091C1BC6E7399`；这是共同工作树摘要，不把所有差异归给 E。
- **接口/迁移需求与剩余阻塞：** 使用主窗口已交付 0050，无新增共享模型/迁移/fixture/OpenAPI 要求，Attempt start 请求形状保持不变。没有 `class_id` 输入，多班学生当前按合同收到 409；若产品要求显式选择班级，需要主窗口先确认并统一扩展请求/OpenAPI。真实机构结果可见/保留政策、答案使用授权与供应商承诺仍未提供；AIGradingSuggestion/P7-06 继续 disabled，Rubric 只作教师人工评分。本窗口证据不替代历史 Release 的 Search 固定版本验收、Impact 测量或 V1 静止树整体验收。
- **与主窗口 14:22 会话提醒对齐：** 该广播提到 E DB 当时有 1 个其他 PostgreSQL 会话并要求解除前暂停写库。当前浏览器/API/Web 已全部停止；最新只读查询确认 E 库 `0050`、其他会话 `0`，Redis DB7 `PING=true/DBSIZE=0`，E 端口 3214/8214/9314 全部释放。E 已在本窗口隔离库完成增量 upgrade/check 和授权专项；请主窗口以后续本报告记录的实际 revision/空闲状态为准，不要再按 0049 迁移该库。
