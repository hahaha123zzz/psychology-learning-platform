# R3-C 只读准备报告

检查时间：2026-10-04 19:48 +08:00（只读准备；未获 GO）

## 状态与基线

- 建议：**HOLD**。并行状态文档目前将 R3-C 标为 HOLD，且声明全部 GO 为 NO。资源预留不等于启动授权。
- 当前 Git HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`，与并行状态文档记录一致。
- 文档记录的共同工作树指纹：`17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`（排除 `.pnpm-store/` 与本状态文件）。未在本次重新计算全树指纹；文档说明先前状态扫描有缓存路径消失，获 GO 前仍须复算并确认。
- 当前排他候选文件已有工作区状态：`server/app/modules/cases/`、`server/tests/test_cases.py`、`web/components/StudentCaseWorkbench.tsx`、`StudentHomeDashboard.tsx`、`StudentNotificationsPanel.tsx`、`StudentPreferencesPanel.tsx` 和 `web/tests/case-workbench-contract.test.mjs` 为未跟踪；`web/components/StudentProfile.tsx` 为已修改；`web/tests/privacy-deletion-recovery.test.mjs` 为未跟踪。它们属于当前共同基线中的既有改动，必须保留，不能按 HEAD 内容覆盖。

## 任务与候选文件

- P5-04：案例服务/工作台与案例专测。目标是区分选择与文字推理证据、改进理由/设计评分的可解释边界、补 scaffold 渐退与鼠标/触控/键盘等价验收。
- P5-05：Growth 状态来源、解释与失效刷新；避免将正确率等同掌握。当前 Growth 页面实际位于 `web/components/StudentCourseSupportPages.tsx`，该文件不在 R3-C 排他清单，需主窗口确认是否加入，否则无法完整处理此项。
- P5-06：接通真实 Me/偏好/通知入口，呈现个人数据透明信息并覆盖保存、刷新恢复和错误状态。`StudentProfile.tsx` 导入偏好/通知面板，但活动的课程 Me 页由 `StudentCourseSupportPages.tsx` 的 `StudentMePage` 提供；需先明确该文件所有权与接入范围。
- P5-07：拟在已分配学生个人/学习专属页面中做 360px、键盘焦点、大字/减少动画和弱网恢复验收。学习输入/SSE恢复还涉及 `StudentLearnPage.tsx`、`StudentLearningSession.tsx`，当前未列为 R3-C 排他文件；需主窗口确认范围及与 R3-B 的客户端边界。测评页面、分支会话、共享导航/CSS 均不触碰。
- 可写候选清单仍以并行状态文档 R3-C 行为准：`server/app/modules/cases/**`、`server/tests/test_cases.py`、`StudentCaseWorkbench.tsx`、`StudentHomeDashboard.tsx`、`StudentProfile.tsx`、`StudentPreferencesPanel.tsx`、`StudentNotificationsPanel.tsx` 及学生专测。

## 共享合同/迁移需求

- 现有 `CaseSession`、`LearningEvent`、`UserPreference` 与成长/隐私接口可作当前基线；初步未发现必须由 R3-C 自行提出的模型或迁移。
- 若案例资格化事件、Growth 投影、Me/隐私 API 需新增字段、状态、事件或端点，交主窗口统一定合同并处理模型、迁移、路由注册、OpenAPI 与公共 fixture。R3-C 只消费真实接口。
- 主窗口状态表记载其他窗口的共享依赖：R3-A 的 Domain/Claim 与索引合同；R3-B 的 Memory 来源/时效、策略/Planner 合同（部分依赖 A）；R3-D 的 Activity/Run、Course Policy、Timeline 模型与路由；R3-E 的 RubricVersion/AIGradingSuggestion；R3-F 依赖 A 和 CourseRelease/assignment；R3-G 正式教材/实验内容受外部输入阻塞。以上均非 R3-C 可修改范围。

## 隔离环境与验证计划

- 分配记录：PostgreSQL `psychology_learning_v1_r3_c_20261004`；Redis `redis://127.0.0.1:6379/5`；MinIO bucket `v1-r3-c`；Web/API `3212/8212`；Worker 使用 queue `v1-r3-c` 且无入站端口。
- 并行状态文档记录 DB 可连接且无业务表、Redis PING 且 0 keys、bucket 存在、端口空闲。本窗口本次未连接环境/启动服务；开工前必须重新只读核验这些资源和端口，并明确配置 DATABASE_URL、测试库、Redis、broker/result、bucket 与端口，不回落到共享默认值。
- R3 Web 隔离 helper 的 Node smoke 已由协调记录为 7/7，PowerShell 脚本语法解析通过；物理快照启动、R3-C API proxy/distDir 实际运行及构建尚未验证。UI 实施/浏览器前须按独立快照与 3212/8212 做受控验证。
- 获得明确 GO 后才运行案例专测/学生前端定向测试和隔离浏览器流程；浏览器场景至少覆盖案例草稿恢复/冲突/提交锁定、四类 Growth 数据与解释状态、偏好保存刷新、窄屏溢出、键盘完整操作与焦点、减少动画/大字、断网/恢复及课程切换不串任务。当前没有新增测试、测试通过或浏览器证据。

## 阻塞

1. 当前 R3-C 为 HOLD；不改代码、不运行写数据库测试、不启动 API/Web/Worker。
2. 当前排他文件没有包含活动 Growth/Me 的 `StudentCourseSupportPages.tsx`，也没有包含 P5-07 可能涉及的 `StudentLearnPage.tsx`、`StudentLearningSession.tsx`；需主窗口确认加入或调整任务验收边界。
3. 共同基线指纹、目标资源和端口需开工前复核；Next 物理快照实际构建仍未验证。

只读审计已在本对话提交。该报告只用于协调，不构成 GO；等待主窗口在并行状态文档中明确更新 R3-C 状态。

## R3-C 实现后交接补充（2026-10-05）

### 范围与精确文件

按当前 `V1并行启动状态.md` 的 R3-C 行，本窗口拥有 cases、实际 Growth/Me、普通学习/SSE 页面与学生专属 route wrappers/tests；测评、Branch、`web/lib/api.ts`、共享导航和 CSS 均不在范围。本窗口本轮实际改动：

- 案例后端与专测：`server/app/modules/cases/router.py`、`server/tests/test_cases.py`。
- 学生案例入口/工作台：`web/app/student/cases/page.tsx`、`web/components/StudentCaseWorkbench.tsx`、`web/components/StudentHomeDashboard.tsx`。
- Growth/Me/偏好/通知：`web/components/StudentCourseSupportPages.tsx`、`web/components/StudentPreferencesPanel.tsx`、`web/components/StudentNotificationsPanel.tsx`。
- 学习/SSE：`web/components/StudentLearnPage.tsx`、`web/components/StudentLearningSession.tsx`。
- 前端定向测试：`web/tests/case-workbench-contract.test.mjs`、`web/tests/r3-c-student-experience.test.mjs`。

`StudentProfile.tsx`、测评页面、`web/app/student/branches/page.tsx`、共享 API/CSS/导航、本轮其他窗口的代码均未由 C 修改。

### 已编码与接口需求

案例提交结果仅描述推理完成度，不判断选项或解释的正确性/质量；学生页面明确说明该评分边界。Growth 页面展示现有掌握证据、算法版本和更新时间；未建模技能或未确认误区不作为已证实状态呈现。Me 展示个人记忆类别、内容、层级、来源、证据引用数、置信度和时效字段；偏好/通知入口接入活动页面。学习/SSE 错误和冲突时保留当前输入，并提供重试。

本轮未修改共享模型、迁移、OpenAPI、公共 fixture、路由注册或共享 UI 配置；未发现必须由 C 提出的迁移。若要显示真实技能/误区，需主窗口先提供共享模型/API 语义及来源、置信度、时效合同。`/student/branches` 仍使用案例工作台，属于 Branch 范围，本轮没有改动。

### 基线与隔离资源

- HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。
- 2026-10-05 报告更新前指纹连续两次稳定：509 entries，SHA-256 `4203B758B3C39B0BBD23A61585184CD5EF2FF0359EF3A4EEDD84E64993B1F83B`。主窗口 2026-10-05 状态记录为 `32DA8039…`；两者不一致，且缺少可逐项对照的旧快照清单，不能可靠归因具体增量。此报告更新本身会改变工作树指纹，建议主窗口在各窗口材料收齐后统一重算。
- 分配值仍为 PostgreSQL `psychology_learning_v1_r3_c_20261004`、Redis `redis://127.0.0.1:6379/5`、MinIO `v1-r3-c`、Web/API `3212/8212`、CDP `9312`、queue `v1-r3-c`。
- 本次只读现场检查时，5432、6379、9000 及 3212、8212、9312 均无监听。因此数据库、Redis 和 MinIO 当前无法现场复核；不得据分配值称其已可用。本轮 API/Web 已停止。浏览器验证期间的独立数据库留下 1 个合成学生、1 个合成课程和 1 个案例会话；Redis DB5 当时为 0 keys，MinIO bucket 未使用。未启动或迁移任何依赖服务。
- 已有隔离 UI 证据：R3-C 物理源码快照及独立 distDir production build 成功，API proxy 指向专属 stub，Chromium 基础代理检查通过。案例最终构建目录为 `web/.r3-runtime/r3-c-case-completeness-final-20261004`；当前共享资源离线，未重启复验。

### 验证证据

- 后端 `pytest tests/test_cases.py`：3 passed、2 warnings。
- 前端定向 Node 合同/体验套件：7 passed。
- C 隔离 production build 与 TypeScript typecheck 通过。
- Chromium 业务检查：案例工作台用键盘选择并提交有效但语义错误的样例选项，页面只显示完成度；中断请求后输入保留并可重试；Growth、Me 和偏好保存路径可见；375px 案例视口无横向溢出、JS 页面错误为 0；Me 移动视口宽 360px、内容宽未超 375px。测试后关闭服务。截图留在本机临时目录，未纳入仓库。
- 上述是本窗口定向测试和合成数据浏览器证据，不等于主窗口全量回归、真实课程资料/SSE 验收或真实学生数据验证。

### 遗留项与阻塞

1. 当前无法连接分配的 PostgreSQL/Redis/MinIO；相关资源监听均关闭，需主窗口恢复独立依赖后再做环境复核。不得回退到预览库或其他窗口资源。
2. 未用真实已发布课程资料验证案例检索/SSE；Growth 技能/误区解释依赖共享合同和数据；隐私删除、保留政策与真实数据验证不在本轮证据内。
3. `/student/branches` 的案例工作台路由归 Branch 边界；本窗口未修改。R3 全量回归 313 passed 属主窗口共同树证据，不表示本窗口浏览器/真实数据验收或整个 V1 完成。
4. `docs/v1/V1并行启动状态.md` 要求短期冻结以取得静止快照；本补充仅更新本窗口报告，未改代码、总状态、验收文档或其他窗口文件。

### 主窗口交接清单复核（2026-10-05 10:59 +08:00）

**逐文件状态（当前工作树 `git status --short` 只读核对）：**

- R3-C 新增：`server/app/modules/cases/router.py`、`server/tests/test_cases.py`、`web/app/student/cases/page.tsx`、`web/components/StudentCaseWorkbench.tsx`、`web/components/StudentHomeDashboard.tsx`、`web/components/StudentPreferencesPanel.tsx`、`web/components/StudentNotificationsPanel.tsx`、`web/tests/case-workbench-contract.test.mjs`、`web/tests/r3-c-student-experience.test.mjs`。
- R3-C 修改：`web/components/StudentCourseSupportPages.tsx`、`web/components/StudentLearnPage.tsx`、`web/components/StudentLearningSession.tsx`。
- 虽在工作树显示修改、但非本窗口改动/不认领：`web/components/StudentProfile.tsx`、`web/app/student/branches/page.tsx`、`web/components/StudentAssessments.tsx`、`web/app/student/assessments/page.tsx`、`web/lib/api.ts`、`web/app/globals.css`、`web/components/V2Navigation.tsx`。其余同树文件也不因 `git status` 而归 C 所有。
- C 未改 models/Alembic/conftest、OpenAPI、root router aggregation、公共 UI 配置、Branch 或测评文件。

**复核命令与结果：**

- 基线：`scripts/r3-baseline-fingerprint.ps1` 连续两次一致，HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`，509 entries，指纹 `4203B758B3C39B0BBD23A61585184CD5EF2FF0359EF3A4EEDD84E64993B1F83B`。与主窗口记载的 `32DA8039…` 不同；没有旧快照逐文件清单，不能准确归因差异。
- 端口：PowerShell `Get-NetTCPConnection -State Listen -LocalPort <port>` 只读检查 5432、6379、9000、3212、8212、9312，均无监听。DB revision、Redis PING/key count、MinIO bucket 的本次直接核验未运行，因为相应服务端口不可达；未启动容器/服务，也未连接预览资源。
- 专项测试/build/browser 的历史结果见上节；保留证据只记录了日期与结果，未保留每条命令的精确墙钟时间。主窗口 `313 passed` 是共同树全量结果，不计入 C 专项测试。

`HANDOFF=INCOMPLETE; RESUMED=NO（2026-10-05 10:59 +08:00）`。材料和文件归属已补；但隔离 DB/Redis/MinIO 当前不可达，且共同基线指纹与主窗口记录不一致，故不满足主窗口要求的“资源仍独占且可用、当前共同树无未解释冲突”。只暂停需要访问这些资源或依赖新共同基线的 C 子项；不得自行启动依赖。主窗口恢复独立资源并协调整树基线后，再按新现场更新本节状态。

### R3-C 依赖与连续基线再核验（2026-10-05 11:05 +08:00）

按主窗口广播执行只读检查，未启动服务：

- `Get-NetTCPConnection -State Listen -LocalPort <port>` 对 5432/6379/9000 与 C 专属 3212/8212/9312 均返回无监听。因此无法直接连接 PostgreSQL `psychology_learning_v1_r3_c_20261004` 查询 revision、无法对 Redis DB5 执行 PING/DBSIZE、也无法列查 MinIO `v1-r3-c` bucket；这些项目本次结果是“不可达/未核验”，不是通过。未使用预览端口或其他窗口资源。
- `scripts/r3-baseline-fingerprint.ps1` 连续两次结果一致：HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、509 entries、SHA-256 `9DB92A967FBB746D57D131A959D4A4DC65DF42126587A85A7AD0F11B2BD9FB51`。与本报告上一节 `4203B758…` 不同，HEAD/entries 数未变；没有当时的文件快照，无法安全归因具体变化或声称该差异只属于 C。需主窗口协调共同树基线。

`HANDOFF=INCOMPLETE; RESUMED=NO（2026-10-05 11:05 +08:00）`。这是明确的环境阻塞，不是 C 的 GO 撤销。等主窗口/环境恢复 C 独立依赖后，再只读核验 DB revision、Redis DB5 key count、bucket 与端口；同时由主窗口确认共同基线变化。条件满足前不启动服务、不运行写库测试、不恢复依赖这些资源的 C 工作。

### 跨窗口边界更新（2026-10-05 11:28 +08:00）

主窗口根据 R3-B 交接明确：`web/app/student/branches/page.tsx` 不属于 B 或 C 的排他范围；Branch 页面归属与端到端验收由主窗口协调/接手。R3-C 不修改该页面；其当前工作树 `M` 状态不代表 C 改动。该结论与本报告此前的边界一致，只补充归属责任，不解除依赖环境 HOLD。R3-E 的 MiniLab 类型错误由 G 按其范围处理，不属于 C。

## R3-C 无服务子项进展（2026-10-05 12:08 +08:00）

依据主窗口 12:00 左右启动规则，在服务依赖保持 HOLD 时继续纯前端弱网/可恢复性工作。

- **编码：** `web/components/StudentLearningSession.tsx` 恢复服务端学习会话失败时不再清除 `sessionStorage` 中的 `student-learning-task`；保留任务 ID 并展示键盘可操作的“重试恢复学习”按钮。提示文本只承诺读取服务端已保存进度，不声称未提交输入已持久化。
- **合同测试：** 在 `web/tests/r3-c-student-experience.test.mjs` 增加恢复失败保留任务 ID、提供重试入口和进度来源文案断言。`node --test web/tests/r3-c-student-experience.test.mjs web/tests/case-workbench-contract.test.mjs`：7 passed，0 failed。
- **类型检查：** 尝试 `pnpm exec tsc --noEmit --incremental false`；当前 checkout 未解析到本地 `tsc` 可执行文件（`'tsc' is not recognized`），因此本次无 TypeScript 编译结论。未安装依赖或启动服务。
- **边界：** 本次仅改 C 已归属的 `StudentLearningSession.tsx` 与 R3-C 专测；没有改共享 API、CSS、导航、测评、Branch 或其他窗口文件。Branch 页面责任仍由主窗口接手。
- **资源与基线：** 12:08 复核 PostgreSQL/Redis/MinIO 与 3212/8212/9312 均无监听，数据库 revision、Redis key count、bucket 仍不可核验。连续执行两次 `scripts/r3-baseline-fingerprint.ps1` 均为 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、518 entries，但指纹先后为 `492A351370D55805416DF4728D59A511AFCFCDC93FAD75A2C9690F5E2A09FB3C` 与 `5861D694C691EC90C51C7A8DE9C52C29BFEA08FEA5D03787C0938F84866B1D8C`。同轮结果不一致，说明共享工作树仍有并行写入；不能声称共同基线稳定或把差异归属到 C。报告追加也会改变全树指纹，待主窗口协调后重算。

`HANDOFF=INCOMPLETE; RESUMED=NO` 继续适用于服务依赖子项；按主窗口广播，纯前端/合同范围可继续。当前剩余项：服务资源恢复后复核 DB/Redis/MinIO 和专属端口；稳定共同基线后重跑纯静态检查/必要构建；需要真实课程材料和 API 的案例检索、Growth/SSE 端到端仍未验收。

### 无服务子项复核与 lint 跟进（2026-10-05 12:13 +08:00）

- 主窗口 12:10 即时检查曾将 `StudentLearningSession.tsx` 的 `setRecoveryTaskId(saved)` 报为 effect 同步状态更新。本窗口已改成 `queueMicrotask` 调度，并以稳定的 `useCallback` 回调配合 effect 依赖；定向 Node 合同仍 **7/7 passed**。本地尝试 `pnpm exec eslint components/StudentLearningSession.tsx` 和 `pnpm exec tsc --noEmit --incremental false` 均因 checkout 找不到本地 `eslint`/`tsc` 命令而无法验证。因此不宣称主窗口 lint 项已关闭，待可用工具环境由主窗口复查。
- 12:13 只读现场再次显示 5432/6379/9000、3212/8212/9312 均无监听；服务依赖子项继续 HOLD，无启动/写库测试。
- 本次代码更新后的 `scripts/r3-baseline-fingerprint.ps1` 连续两次稳定：HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、523 entries、SHA-256 `3B8978B83D3C8273577A448F77B5CF32888B2F7F8CDE2AAF83533BAFBB0E75BA`。该值记录在本报告更新前；报告写入本身会改变指纹。旧共同基线 `32DA8039…` 与后续中间结果仍无法逐项归因，后续应以主窗口协调后的连续稳定快照为准。

纯前端无服务工作可继续；没有服务资源核验时，`HANDOFF=INCOMPLETE; RESUMED=NO` 仍适用于需 DB/Redis/MinIO/API/浏览器的范围。

### R3-C 最新无服务回归（2026-10-05 12:15 +08:00）

- `pnpm test`（`web/`）在当前共同树 **55 passed、0 failed**；这是 Node 前端合同套件，不连接数据库或启动浏览器/API。主窗口 12:10 的 52/52 为较早快照，本次快照包含并行新增的 Branch/R3 用例。
- `StudentLearningSession.tsx` 的 effect 同步 state 更新已改为 `queueMicrotask` + 稳定 `useCallback`，但本机 `pnpm exec eslint components/StudentLearningSession.tsx`、`pnpm exec tsc --noEmit --incremental false` 均找不到本地二进制。不得据代码结构推断 lint/typecheck 已通过；请主窗口在其可用依赖环境复核。
- 本报告更新前的连续基线为 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、523 entries、SHA-256 `4AC7F9BF1D62775453C35FE67FFB66DE13C68DD141ABB752175018BD81FF7396`。该结果连续两次稳定；本次报告追加会改变指纹。
- 12:13 最新 C 环境检查仍是 PostgreSQL/Redis/MinIO 与 3212/8212/9312 无监听。服务依赖测试、浏览器业务验收和真实课程资料验证仍未运行；不得将 Node 通过外推到这些层级。

纯前端代码/合同范围继续按共享表施工；`HANDOFF=INCOMPLETE; RESUMED=NO` 仍仅标记服务依赖验收未恢复。

### R3-C 收到环境恢复 GO 与资源现场（2026-10-05 15:12 +08:00）

- 已阅读主窗口 14:25 `R3-C HOLD解除 / GO`。只在 C 专属 DB/Redis/bucket 与 3212/8212/9312 上继续；不触碰主预览、F 的 8215 或其他窗口资源。
- 15:11 只读复核：DB `psychology_learning_v1_r3_c_20261004` 当前 `0050`、73 张 public 表、0 个其他连接；Redis DB5 `PING` 成功、0 keys；MinIO `v1-r3-c` 存在；3212/8212/9312 空闲。
- 当前共同树 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、531 entries；指纹连续两次稳定为 `44C4D38B38F5CABEE75F1C8E840A4C7EB30630C4B39E84DE91D32F4815831B95`（记录于本段写入之前）。
- C 案例 pytest fixture 会在每例后 `TRUNCATE courses/users ... CASCADE`。测试前只读行数发现 `learning_events=1`、`outbox_events=1`、`audit_logs=2`、`course_members=2`、`courses=1`、`auth_sessions=2`、`users=2`、`case_sessions=1` 等既有数据；为保护 GO 明确要求保留的 C 原数据，暂不运行该破坏性 fixture。请求主窗口为 C 专项测试提供空的隔离目标或允许的非破坏性 fixture 方案。Node 合同不访问这些资源。

### R3-C 收到环境 GO 后实施与验收交接（2026-10-05 15:40 +08:00）

#### 本轮完成范围

- 案例工作台首次读取目录/已有会话改为分别保留成功响应；任一请求失败时不展示“开始案例”，避免因会话列表未读到而创建重复案例。新增带 `role="alert"` 的恢复说明和键盘可操作的重试读取。
- 案例理由/设计输入在组件内明确纵向排列、限制最小宽度并占满容器可用宽度，修复 375px 截图中的标签与输入框拥挤。未改共享 CSS。
- 学习恢复请求失败时保留 `sessionStorage` 中的任务 ID，并提供可键盘操作的恢复重试入口；前端专测覆盖恢复文案与任务 ID 保留。
- 未修改共享 `models.py`、Alembic、`conftest.py`、OpenAPI、路由注册、公共构建配置、总验收/状态文档；未改测评、Branch、共享 API、导航或 CSS。现有契约足以完成本轮 UI/案例范围，当前无新增模型、迁移或 OpenAPI 请求。

#### 实际改动文件归属

本轮新增差异仅在 C 排他文件：

- `web/components/StudentCaseWorkbench.tsx`
- `web/tests/case-workbench-contract.test.mjs`

此前同一 R3-C 范围的实现文件仍见本报告 2026-10-05 交接清单；不能把共同工作树其他未提交文件归到 C。

#### 测试与浏览器证据

- `web/` 全量 `pnpm test`：56 passed、0 failed；案例/学生体验定向 Node 测试：8 passed、0 failed。
- `server/` `ruff check app\modules\cases tests\test_cases.py`：All checks passed。
- C 物理源码快照 `web/.r3-runtime/r3-c-case-20261005` 的独立 `.next-r3-c` production build 通过，Next 编译、TypeScript 与 24 个静态页面生成均通过。
- 隔离 Web 启动日志提示 `next start` 与 `output: standalone` 配置的运行方式不匹配；本次 `/login`、代理健康检查及上述 Chromium 页面流程实际通过，但 standalone 产物的标准启动命令仍未单独验收。
- C 专属 API/Web 使用 PostgreSQL `psychology_learning_v1_r3_c_20261004`、Redis DB5、MinIO bucket `v1-r3-c` 与端口 8212/3212；Chromium 使用合成工程账号和课程。案例页面验证键盘 radio、草稿保存与刷新恢复、首个会话列表 GET 故障后 alert/重试恢复、375/1280px 无横向溢出、0 page errors；Growth/Me 页面验证键盘 tabs、未建模状态的真实边界、115% 字号偏好保存并刷新恢复、通知空状态、375/1280px 无横向溢出、0 page errors。浏览器检查通过后已停止本窗口 API/Web，9312 CDP 端口未占用。
- 截图/trace 保存在本机临时目录，未加入仓库：`%TEMP%\r3-c-case-375.png`、`%TEMP%\r3-c-case-trace.zip`、`%TEMP%\r3-c-growth-me-375.png`、`%TEMP%\r3-c-growth-me-trace.zip`。

#### 层级、依赖和剩余阻塞

- **已编码：** 上述 cases 首读安全恢复和窄屏表单样式，以及既有学习恢复重试。
- **自动化已通过：** 前端 Node 合同、cases Ruff、物理快照 production build/TypeScript。
- **环境与合成浏览器验证已通过：** C 隔离 DB/API/Web、合成身份和浏览器路径；这不代表真实学生、真实课程材料或效果验证。
- **后端 cases pytest 未运行：** 当前 `server/tests/conftest.py` 的测试 fixture 每例 `TRUNCATE ... CASCADE`，而 C 专库中已有由主窗口/隔离浏览器保留的合成课程、用户、成员、会话及审计/事件数据。清空这些数据会违背 GO 的数据保留要求。因此需要主窗口提供专用空测试库（仅本模块测试使用）或批准的安全 fixture 方案；C 不修改公共 `conftest.py`，在此之前不运行该测试。
- Growth 技能/误区目前只显示已建模并有服务端数据支撑的状态；不臆造未建模状态。若以后要展示技能/误区的真实解释，需主窗口统一提供稳定对象 ID、来源/证据、置信度、时效及失效语义；不要求 C 修改共享模型或迁移。
- 未以正式心理学教材、获准真实学生材料或真实学生账号验证案例/SSE/学习效果；没有生产级弱网或真实数据验证，也未验收 V1 整体。真实内容和相关外部输入仍是阻塞。
