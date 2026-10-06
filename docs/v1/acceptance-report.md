# V1 本地实施验收报告

更新时间：2026-10-06

## 2026-10-06 学生核心页面 P0-04 局部复核

- **结果：** 学生 Home、Tutor Learn、课程首页、Reader、Practice、Growth、Preference 共 7 个路由，在 Chromium production build 下按 360/393/768 CSS px 检查，21 个组合均无横向溢出或页面异常；所有页面 Tab 首焦点可见，系统 `prefers-reduced-motion: reduce` 生效。`/student/learning` 顶栏与 Practice Mini Lab 选择框的窄屏溢出已修复。
- **键盘增量：** UI-002 对 Home、Growth、Preference 三页的 9 个“路由 × 视口”组合完成 Tab/Shift+Tab 全序遍历，正反顺序互逆、焦点指示可见且无溢出；Growth 标签改为单一 Tab 停靠点，并验证方向键循环及 Home/End。UI-003 又对 Learn、Practice 六个“路由 × 视口”组合完成相同正反向浏览器检查，均无溢出或页面异常；Reader Drawer 因 Learn 尚无已恢复的保存回合引用卡片，未在此项键盘检查中打开。
- **自动化：** Web Node 58/58、TypeScript 通过、ESLint 0 errors/2 existing warnings、production build 24/24 routes。逐项记录见 [`学生核心页面本地可访问性复核`](student-core-local-accessibility-review-2026-10-06.md)。
- **追踪状态：** Acceptance matrix 的 UI-04/UI-05 仅有学生核心 7 路由的布局、首焦点和 reduced-motion 子集证据；键盘全页正反向遍历、Drawer 焦点恢复、44px 触控、读屏器、缩放、颜色对比、其余 11 组代表页和目标稿视觉签收仍未验收。记为 **P0-04 partial**，不可外推为 WCAG 或 V1 完成。
- **引用恢复进展：** UI-004 已集成（`496b6e0`、`f64f32a`、`ff4c083`、`fbb53cf`；来源 `18037007`、`b20ef57`、`bb4329e`、`67d6347`）。Learn 仅在 URL 显式包含 `session_id` 时调用现有 GET，校验会话 ID、课程与 `course_qa` 模式后恢复已保存 turns 和 EvidencePointer；无效/错课程会话失败关闭，不自动搜索或创建会话/回合。普通新会话创建后以 `history.replaceState` 保存会话 ID 并保留其他 query 参数。切换课程时以 `courseId` key 卸载整份 Learn 状态，避免上一课程 turns/citations、session、搜索结果或 pending turn 留存。集成后 Web Node **64/64**、TypeScript 通过、ESLint **0 errors/2 existing warnings**；最终隔离 worktree production build **24/24 routes**，浏览器脚本语法检查通过。
- **浏览器验收阻塞：** UI-004 实际保存会话 → Citation → Reader 固定版本/页 → refresh/back 链路尚未复验：API `8001` refused，PostgreSQL `5432`、Redis `6379`、MinIO `9000` 均不可连，API 在 MinIO startup check 失败。没有 seed、迁移或创建新演示数据；EVID-005 保持等待环境恢复。不得将静态测试或已有 EVID-004 的直接 Reader GET 误记为 UI 点击链路通过。
- **Practice→Review due 状态：** UI-005 集成提交 `590d929`、`fbe2f67`、`edda2f9`（来源 `8932b86`、`3e8c60e`、`89b391a`）。服务端错答复习任务默认次日到期，未到期 `/verify` 返回 409；学生页现在保留预定任务，但禁用验证按钮并将到期说明关联到答案控件。Web Node **68/68**、TypeScript 通过、ESLint **0 errors/2 existing warnings**、隔离 production build **24/24 routes**、浏览器脚本语法通过。专用浏览器脚本只针对合成练习写入一次错答；仅在已有同题到期合成任务时才验证一次正确复习答案，否则确认新任务保持 pending 且不可提前验证。
- **UI-005 浏览器状态：** 实际 Practice→Review 浏览器脚本尚未运行，API/DB/Redis/MinIO 的隔离环境仍不可用；未 seed、迁移或修改 Demo 数据。不能把脚本静态检查记为端到端验收。
- **范围：** 使用本地合成学生数据；未读取或发送教材正文、图像、表格。此工程可用性抽查不代表真实课程、真实班级或生产验收。

本报告只覆盖当前工作树已经编码并能在本机复现的结果。真实教材效果、外部模型质量和生产运行能力不在本报告中虚构。

> **2026-10-05 17:26 最新复核：** 全量后端在新库 `psychology_learning_v1_r3_root_final_20261005b`、Redis DB11、新 MinIO bucket 完成 **364 passed、2 warnings，1472.29 秒**；DB `0051 (head)`、`alembic check` 无新差异，全仓 Ruff 通过。第一轮全量发现快照错误码回归后，主窗口修复 DomainRelease mismatch 分类，材料发布 + Release 套件复跑 **22 passed**，再跑完整全量通过。OpenAPI 两次导出稳定为 **156 paths**、SHA-256 `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`；前端 Node **56/56**、TypeScript 通过、ESLint 0 errors/2 warnings；物理源码快照 production build 成功且 **24/24** 静态页生成。演示预览使用新隔离 DB `psychology_learning_v1_preview_20261005`（0051）、Redis DB2、MinIO bucket `psych-preview-root-20261005`；API `8000` live/ready 200，网页 `3000` 首页/login 200、同源代理到 API 200，合成教师登录成功且课程列表 1 项。未触碰 `.env` 指向的旧 `psychology_learning` DB（只读查到 0038），也未迁移旧预览库。R3-B 历史 superseded snapshot 正向 Claim、Branch child pin 等仍未交付/未验，故 R3/V1 整体不宣告完成。

> **2026-10-05 离散数学本地测试教材核验：** `TEXTBOOK/` 10 个 `.doc` 的本地格式识别通过，真实解析均被现有 `UnsupportedTypeParser` 阻断（`parser_unavailable`）；没有生成材料版本/知识对象/索引，也没有课程检索命中。独立隔离环境的材料、解析、编译、检索专项 **51 passed、2 warnings**，但使用合成测试 fixture。原始 `.doc` 保持不变；此项记录为“未导入/等待本地 DOCX 或固定 PDF”，详见 [`离散数学导入核验`](discrete-math-local-import-2026-10-05.md)。

## 分层结论

| 层级 | 结论 | 证据 |
|---|---|---|
| L1 代码 | 已落地主要课程、学习、测评、复习、干预、案例、Mini Lab、TeachingAsset、运行时聚合、Reader 多页锚点和治理切片；仍有策略/内容/设计工作台缺口，不等于全 V1 完成 | `server/app/`、`web/`、Alembic `0015`—`0051`、`implementation-status.md` 与 P0—P10 剩余清单 |
| L2 自动化验证 | 共同树静止快照的后端、前端静态与生产构建均通过；不能推导真实业务或 V1 完成 | 后端 **364 passed、2 warnings**（新隔离 root DB，24:32）；DB `0051` + `alembic check` 通过；全仓 Ruff 通过。OpenAPI **156 paths**，SHA `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`；Node **56/56**、TypeScript 通过，ESLint 0 errors/2 warnings；物理源码隔离 production build 24/24 静态页。早先 360/1 是错误分类修复前快照；修后相关模块套件 22 passed，最终全量 364 passed。 |
| L3 本地环境 | 合成演示环境已运行；仅工程开发验收，不是实际课程/生产验收 | Web `3000` 与 API `8000` 可访问；API live/ready 200，Web 同源 API proxy 200，合成教师登录成功、课程列表 1 项。API 使用新隔离 DB `psychology_learning_v1_preview_20261005` (0051)、Redis DB2 和 bucket `psych-preview-root-20261005`。未迁移 `.env` 指向的 `psychology_learning`（只读查到 0038）或旧演示库。Docker CLI 对 Engine named pipe 仍 permission denied，容器管理面状态不宣称已核验。R2-A/B/C 与 R3 子窗口的隔离浏览器证据保留；不代表全 V1 业务验收。 |
| L4 真实内容/模型 | 未完成 | 当前使用自编 fixture 与确定性替身；开放教材只用于本地评测，未发送外部模型 |
| L5 真实班级浏览器验收 | 未完成 | P10-02 使用本地隔离数据库和演示角色，不是实际班级；跨设备/网络恢复缺口见浏览器记录 |
| L6 生产验证 | 未完成且不属于本轮授权范围 | 监控、备份恢复、HTTPS、容量和滚动发布仍待后续专项 |

## R2 最新复核（2026-10-04）

- P2-08 旧教师教材写入口：默认关闭配置及活跃/兼容页面只读；上传、分片上传、解析、索引、知识修正、发布和归档经 Scope 检查后统一拒绝普通教师写入；本人取消自己的未完成分片仍允许清理。隔离资料/上传/发布回归 **43 passed**。替代的 Course Content Admin 构建、审核和发布工作台尚未实现。
- R2-A：固定页映射遵循“不知道就不伪造”规则；隔离 Chromium 用合成 PDF 验证已持久化多锚点、翻页/highlight、键盘缩放/旋转；无页码 DOCX 只给文字快照降级。机器缺可靠 Word/LibreOffice renderer；`TEXTBOOK/` 10 个 OLE DOC 未转换。2026-10-05 又以本地解析器逐个核验，10/10 返回 `parser_unavailable`，没有索引/教材命中；隔离材料/解析/编译/检索 fixture 回归 51 passed、2 warnings。详见离散数学本地导入报告；真实教材固定分页/检索金标仍未通过。
- R2-B：真实浏览器五入口及授权、班级、成员、任课关系命令读写通过，含撤权后的 active 列表变化与审计；目标账号 `/me` 未验（没有可用口令）。验收库出现旧记录和 18:12—18:16 来源不明的并发写入，均未清理/覆盖，因此只认每次命令即时状态、服务端回执和审计证据。
- R2-C：真实 TCP 两个 SSE 断点同 ID 重试未重复写入；双标签/离线/截止测评恢复通过；独立 Celery Worker 在删除事务中断后由 Redis late-ack 重投完成幂等处理，Redis 暂失返回 retryable 失败。真实教材 Worker/MinIO 故障、生产 broker 和生产灾备仍未测。
- Next 隔离：`web/.r2-runtime/r2-root-final-b` 为当前树物理副本，Next build 输出在副本内，未覆写预览 `.next`；API rewrite 可按 origin 隔离，ESLint 排除隔离输出。窗口自启 Web/API 已关闭，R2-C Redis 6381 按约保留；未清理数据库、bucket、源码副本或用户数据。
- 以上自动化/浏览器均使用本地合成/演示账号和隔离数据。它们不能推出真实教师验收、真实班级适用性、心理学习效果、教材许可/引用质量、机构保留策略或生产就绪。

## 已验证闭环

1. 教师课程与成员 Scope → 教材/Release → 题库审核发布 → 学生测验与服务端评分。
2. Tutor/教材引用的持久 EvidencePointer → 读取时重新鉴权 → 从来源 PDF 生成固定页图 → 按 PDF 用户空间到像素空间变换叠加引用框；该路径有后端页图集成测试与前端合同测试，DOCX 固定分页和真实教材人工定位仍未验收。
3. 学生学习会话 → Tutor 状态机 → 原始事件 → Qualification → LearningEvidence/Mastery。
4. 案例推理、Tutor 检查回合、到期复习验证和 Mini Lab 完整解释/迁移回合均从服务端权威快照生成证据；新学习会话同步创建当前任务、教学会话和学习片段聚合，并返回可恢复 runtime refs。
5. 学生首页按当前课程成员 Scope 汇总进行中/暂停任务和所有授权课程的到期复习；任务可从首页进入 Tutor 路由并按任务 ID 恢复。
6. 掌握晋升同时满足正确率、证据量、独立证据数和跨情境数；状态投影保存算法版本与可读理由，证据失效后重算。
7. Tutor 安全门区分学术语境中的危机相关术语与个人/他人现实风险；明确风险信号仍优先进入支持回复，学术问题继续受教材证据门禁约束。
8. 教师观察、干预派发、执行实例、效果 Read Model 和证据失效重算保持独立，不覆盖学生原始作答。
9. TeachingAsset 草稿 → 白名单 Contract → 已发布 CourseRelease 绑定 → 学生 Scope 读取；未知内容前端安全降级。Course Designer 已有真实编辑入口。
10. 正式测评当前尝试 → 普通 Tutor/历史/证据/复习/分支入口 fail-closed；题目质量反馈最小化记录并按版本失效；Mini Lab 六阶段可由服务端检查点恢复。
11. 教师观察异议保持独立 pending；只有观察后、独立且跨情境的正式资格化证据可关联再验证，不直接改写掌握度。

## 未宣称完成的边界

- 隐私删除已改为本地持久工作单：调用方提交前生成并展示 ULID 与 256-bit 状态凭证，服务端只保存凭证哈希；受理时在事务内停用/去标识账号、撤销会话并创建 queued 工作单，然后尝试派发删除 Worker。凭预先保存的凭证可无登录查询状态和重派 queued/failed 单据，工作事务成功提交后才报告 `completed_with_retention`；敏感作答/成绩、审计和课程资产仍按保留边界留存。P3-06 隔离测试 **9/9** 覆盖响应丢失、派发失败、事务失败、重试和完成任务重复调用；R2-C 又验证真实本地 Celery Worker 事务中断回滚、Redis late-ack 重投及完成态重复任务无副作用。机构保留策略、备份/生产索引擦除及不可逆匿名化未验证，不能称生产删除完成。旧 0042/0043 回执没有可恢复凭证，仍按 404 隐藏。
- TeachingAsset 仍只有通用白名单模板和文本 fallback，未绑定最终教材的图表、公式和固定页面对象。
- Mini Lab 的 `attention-cue-basic` 是工程 fixture，不代表教材实验或科研效度；尚未交付最终教材要求的 2—3 个实验。
- P4/P5 已通过 `0033` 为新旧会话补齐 `CurrentLearningTask/TeachingSession/Episode` 聚合，并同步暂停/恢复/回合状态；首页已展示可恢复任务队列，复杂优先级调度仍未完成。
- Domain Pack 已有对象/关系引用、证据绑定和先修环校验；ExperimentSchema 已按总体设计字段扩展并进行服务端类型/大小验证，未提供字段保持为空，`textbook_evidence` 使用稳定 EvidenceBinding key。MisconceptionDefinition 的扩展模型与 EvidenceBinding 的坐标精度策略仍需正式契约，未定义的 Relation 类型仍拒绝。Admin 已支持有理由、有幂等键的同机构平台/课程授权授予与撤销、受控任务重试，以及同机构且限课程成员的班级任课分配/结束入口；完整 IAM/课程班级治理工作台仍是缺口。
- 正式测评独立路由及单选/多选/判断/短答/论述 UI 已接入；多选按数组、判断按布尔值保存，并支持进行中刷新恢复。R2-C 双标签真实浏览器验证离线保存错误/恢复、答案版本冲突、截止时两标签封存与重复提交事件保护；真实自动提交策略和跨设备断网续传仍未全面验收。SSE 相同 `client_turn_id` 可重放已保存结果，未收到 `done(saved=true)` 时恢复输入、撤销临时回合；除 ASGI 用例外，R2-C 已真实断开两类 TCP 时点并验证同 ID 重试不重复写入。`direction_only` 在缺少可验证受限生成器时按 fail-closed 禁用处理。
- 案例读取已避免向学生投影标准答案字段，草稿按版本保存并由服务端快照确定性评分；当前评分只衡量回答字段完整性，不代表实验设计语义质量，未完成案例工作区浏览器 E2E。
- 当前 API 8000 热重载工作区代码，路由数为 133；实际预览数据库 `psychology_learning_privacy_target` 仍是 0044，而代码为 0047。Web/API 使用的是本地环境，不等于真实班级或生产迁移；本轮未对预览库升级，也不应调用需要新 schema 的端点。
- 全仓 ESLint 已通过（0 errors、3 个既有 `react-hooks/exhaustive-deps` warnings）；ESLint 排除了物理快照与 `.next-r2-*` 输出。Next production build 在独立物理源码快照中通过，没有覆写正在服务预览的 `.next`。

## R3 主协调最新检查点（2026-10-04 23:24 +08:00）

- **复核基线：** HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；工作区保留旧 V1/R2 与全部 R3 窗口改动。旧 R3 指纹不可重建，使用 `scripts/r3-baseline-fingerprint.ps1` 重建新的共同指纹；精确项数/hash 记于 `V1并行启动状态.md` 文末。没有清理或重置。
- **后端回归：** 全量运行 `python -m pytest -p no:cacheprovider -q` 使用专属 PostgreSQL `psychology_learning_v1_r3_release_tests_20261004`、Redis DB11 和 MinIO bucket `v1-r3-root-tests-20261004`，结果 **302 passed、7 failed**（1102.02 秒、2 warnings）。1 条 Memory 汇总失败由主窗口在 root-owned `memory/router.py` 修复各课程 Scope 聚合；剩余 6 条是旧题库集成测试要求进行中 `/result` 为 200，与当前 fail-closed 结果策略冲突，现已改为核验 403/`ASSESSMENT_RESULT_NOT_RELEASED`。主窗口修复后相应 Memory + 6 组定向用例 **7 passed**（59.19 秒）。全量期间 `assessments/router.py` 仍有写入时间戳，故 302/7 为运行树变动时的快照，不作为稳定全量基线；需窗口完成交接、暂停代码写入后重跑全量。
- **共享验证：** 当前 OpenAPI 导出为 **148 paths**，SHA-256 `EAF93FEEC24BF1116508A57534889CBB125936C2CD295EFCDA4DA7CC5FA6DC61`；root shared PostgreSQL `psychology_learning_v1_r3_shared_20261004` 为 `0049`，`alembic check` 无差异；全仓 Ruff 通过。Node 46/46、typecheck 通过、ESLint 0 errors/3 个既有 warning。窗口交付报告仍为空，R3 全范围未验收。
- **环境隔离：** 主预览 Web PID 36428/API PID 81684 在线，3000/8000 HTTP 200；数据库 `psychology_learning_privacy_target` 仍是 0044，与代码 0049 不同，未迁移。A/B/C/E 测试数据库 0049/72 张业务表；root shared/root-test 均 0049/72；D/F/G 分配数据库没有 Alembic 版本表/业务表。Redis DB3/4/5/6/7/8/10/11 均 PING 且 0 keys；MinIO A—G 与 root 测试 bucket 存在。仅监听预览端口 3000/8000，R3 API/Web/CDP 分配端口空闲。Docker Engine 未核验。
- **结果可见语义：** `/attempts/{id}/result` 只在锁定的测评策略许可后提供结果；进行中尝试即使没有评分/解析也返回 `ASSESSMENT_RESULT_NOT_RELEASED`。学生进行中恢复使用 Assessment attempt start/resume API，不依赖 result endpoint。此合同的 6 种聊天绕过组合已改为明确断言拒绝；需在 E 交接后核对其页面和浏览器流程仍不受影响。
- **未通过/未验收：** R3 全量后端稳定复跑、C Growth/Me/SSE 业务浏览器、D Activity API 集成与少样本边界、E 业务结果策略浏览器、F Preview/Review/Publisher/Assignment Designer 流程、G 正式获准内容均未验收。CourseRelease 旧无请求体发布路径仍可能绕过新审核 Gate；Impact 目前因缺版本绑定学习证据而明确 `not_measured`。基础 UI shell build/proxy 证据不等于业务验收。

## R3 主窗口稳定快照（2026-10-05）

- **全量后端：** 在专属测试数据库 `psychology_learning_v1_r3_release_tests_20261004`、Redis DB11、MinIO bucket `v1-r3-root-tests-20261004` 执行 `python -m pytest -p no:cacheprovider -q`，最新结果 **315 passed、2 warnings，1144.22 秒**。其前 312/2 的失败来自未同步的旧课程发布测试合同，已补测试 helper 并复跑全量。当前结果不代表窗口已交付或 V1 所有业务场景已验收。
- **共享契约：** 工作区迁移 head `0049`；OpenAPI 重导出为 **149 paths**，SHA-256 `7F0CF080423A0875564A7075C25BC681507F1FF4F56A8E64603C4085E18ABFFB`；发布操作要求请求体（OpenAPI `requestBody.required=true`），无请求体调用返回 `422 RELEASE_PUBLISH_REQUEST_REQUIRED`；root shared DB 执行 `alembic check` 得到 `No new upgrade operations detected`；全仓 Ruff `All checks passed`。
- **前端自动化：** `pnpm test` **46/46**，`pnpm typecheck` 通过；`pnpm lint` 0 errors、3 个既有 `react-hooks/exhaustive-deps` warnings。没有重跑共享 `.next` production build，避免干扰正在运行的预览。
- **预览与依赖：** Web/API 3000/8000，Web 首页及 API live/ready 均 HTTP 200；PostgreSQL 5432、Redis 6379、MinIO 9000 TCP 可连接。Docker CLI 查询 Engine named pipe 返回 permission denied，故未把容器状态记为已确认。预览库 `psychology_learning_privacy_target` 仍为 `0044`；未迁移、未写入，继续禁止调用依赖 `0045+` schema 的管理/隐私端点。
- **窗口交接与业务验收：** R3-A—G 仍是共享状态表内受限 GO；共享工作树可见其代码改动，但尚无 A—G 完整最终交接报告。C Growth/Me/SSE、D Activity API、E 结果策略浏览器、F Designer 发布链路、G 正式内容均未完成业务验收。无请求体 Release publish 绕过路径已关闭；Impact 因缺版本绑定学习证据仍为 `not_measured`。R3/V1 未整体验收完成。

## R3 主窗口 Branch 学生 UI 与 OpenAPI 复核（2026-10-05）

- **已编码：** `/student/branches` 路由现挂载 Branch 专用真实 API 工作台，不再误用案例工作台。分支需引用学生本人回合中实际存在的连续原文；合并显式提交 `confirmed=true`、`merge_key` 和学生说明，重复提交沿用相同幂等键。
- **自动化证据：** Branch 页面合同 **3/3 passed**；Web 全量 Node **49/49 passed**、TypeScript 通过、ESLint 0 errors/3 个既有 warnings。
- **尚未验收：** 本次检查时服务端依赖和端口不可达，未运行 Branch 后端隔离测试、API 服务或浏览器操作；不得把静态合同标为业务浏览器通过。恢复专属资源后需核验创建、越权、明确合并、幂等回放与异 payload 冲突。
- **OpenAPI：** Mini Lab invalidate 请求体 schema 正确且 required，重复导出稳定为 149 paths、SHA-256 `7F0CF080423A0875564A7075C25BC681507F1FF4F56A8E64603C4085E18ABFFB`；成功响应暂为空 schema `{}`，已要求 R3-G 在其排他模块范围补契约，主窗口未手改 OpenAPI。
- 本段只记录前端代码和自动化层级；R3、V1 总体验收仍未完成。

## 复现命令

## R3 主窗口最新集成检查（2026-10-05 13:32 +08:00）

- 当前共同 Web checkout：`pnpm test` **55/55 passed**，`pnpm typecheck` 通过，`pnpm lint` **0 errors / 3 warnings**（三条既有 React Hook 依赖 warning）。这比本报告上方 49/49 的 Branch 检查包含更多并行合同用例；未包含独立全站生产构建或完整业务浏览器验收。
- D 模块路由由主窗口注册至 API 聚合器；OpenAPI exporter 连续两次稳定为 **156 paths**、SHA-256 `02241A429DD2284E20C409B8C4436121277C3D6F207F8C753DE85028FF216900`。TeachingActivity 新增两个路由；Mini Lab invalidate 的 `200` 响应已引用 `MiniLabResponse`，请求体仍为 required。
- 共享 Ruff 对 API router 与 TeachingActivity 模块通过；D 非数据库逻辑/合同测试 `16 passed, 1 deselected, 2 warnings`。TeachingActivity 数据库集成用例未运行；本轮没有全量后端测试或 `alembic check`。
- 13:30 只读端口检查确认 5432/6379/9000、共享预览 3000/8000 可连接，R3 A—G 专属 3210—3216/8210—8216/9310—9316 无监听。未据此判断各隔离库 revision、bucket 或服务健康；未写入预览库。
- 最新窗口分项、HOLD 边界与历史 315 项全量后端回归的适用范围见 `V1并行启动状态.md` 最新 13:32 检查点。当前工作树全量后端静止快照回归仍待执行；R3/V1 不作整体完成结论。

## R3 Domain 发布快照定向验收与 D 集成缺陷（2026-10-05 13:57 +08:00）

- **验收通过（隔离工程数据）：** CourseRelease 与教材发布/索引固定同一 DomainRelease 的主窗口接线已在专属 root 测试库完成；材料发布与 Release workflow 两组 **21 passed**，覆盖快照/Job/RetrievalUnit ID 一致、规范 Pack 继承、错配拒绝、更新换版和 Gate 负例。Alembic `check` 无新操作；相关 Ruff、compileall 通过。该结果只证明当前合成 fixture 下的定向工程行为，不是正式课程内容验收。
- **共享契约：** 当前 OpenAPI 连续导出为 **156 paths**，SHA-256 `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`；包含 DomainRelease 发布绑定字段、教材发布 query、D TeachingActivity routes 与 MiniLab 成功响应 schema。
- **未通过项及负责人：** D 模块合并后测试为 **21 passed、1 failed**。唯一失败为 D `teaching_activities/router.py` Run action 提交后序列化 `updated_at` 触发 `MissingGreenlet`；已在共享状态明确要求 D 在其排他文件修复并提供重跑证据，主窗口未代改。
- **未验收：** 本次未运行当前共同树完整后端、全仓 Ruff、全前端 build/浏览器验收。CourseReleaseAssignment 到实际运行 Scope 的固定、历史 Release 对应索引快照回读、Tutor Claim 持久化仍待实施；Release Impact 因缺少版本化证据仍 `not_measured`。不得据此宣称 R3 或 V1 完成。

## R3 主窗口 0050 运行指派快照底座验收（2026-10-05 14:06 +08:00）

- **迁移/模型：** 新增 `0050_bind_learning_runs_to_release_assignments.py`，仅在三类既有表上追加 nullable assignment/release 外键、配对检查约束与索引；没有删除/重写历史行。root 专库 `psychology_learning_v1_r3_root_assignment_20261005a` 由测试夹具从不存在状态创建并迁移至 `0050 (head)`；另一保留旧测试数据的 root 专库从 `0049` 正向升级至 `0050` 成功。
- **自动化：** `tests/test_r3_release_workflow.py` **5 passed、2 warnings、24.69 秒**；`alembic check` 为 `No new upgrade operations detected`；models 与 0050 migration Ruff 和 compileall 通过。MinIO bucket 现场确认不存在，测试未创建或调用该 bucket；使用 PostgreSQL、Redis DB13（PING、0 keys）。
- **验收边界：** 本次验证 schema 与已有 Release workflow，不证明 B/E 已将运行记录接入新列；B/E 共享工作区施工要求已写入并行状态。Impact 仍 `not_measured`，历史数据不回填；没有执行当前工作树全量后端、全前端、业务浏览器或真实课程验证。

## R3-F 隔离真实 Release API 准备（2026-10-05 14:22 +08:00）

- **环境：** F 专属 PostgreSQL `psychology_learning_v1_r3_f_20261004` 从空库由主窗口迁移至 `0050 (head)`，`alembic check` 无差异；Redis DB8 仍隔离，MinIO `v1-r3-f` 保留原状态。
- **合成数据/API：** `server/tests/r3_f_browser_seed.py` 经 FastAPI 正常写入流程准备两个不同且已发布的合成 Release（material_ids 均为空）。F API 8215 的 live/login/course list/Release list 均已从真实运行服务得到 200；课程下真实读取到两版不同 manifest。8215 由主窗口保留运行，供 F 浏览器调用。
- **验收边界：** 这是环境与隔离合成工程数据验证；F 页面真实 Chromium、manifest 展示、Diff 交互、写请求数为零尚未由窗口验收。未触碰 3000/8000 主预览和正式教材数据。

## 当前共同树前端/契约复核（2026-10-05 14:22 +08:00）

- **共享静态/Node 门：** 全仓 Ruff 通过；Web `pnpm test` **56/56 passed**、`pnpm typecheck` 通过、`pnpm lint` 0 errors/2 warnings；`git diff --check` 无空白错误（保留 3 条 CRLF 转换提示）。
- **OpenAPI：** 连续 exporter 输出 **156 paths**、SHA-256 `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`。
- **未验收：** 没有执行全项目 `pnpm build` 或当前共同树完整后端回归；R3-F 真实页面 Chromium 待其窗口执行。当前本地静态通过与接口契约稳定不等于 R3/V1 全面验收。

## R3-C/D 隔离环境恢复与迁移准备（2026-10-05 14:25 +08:00）

- C 专库从 `0049` 正向迁移到 `0050 (head)`，原有表/数据保留；D 空库迁移到 `0050 (head)`。两库 `alembic check` 均无新升级操作。
- 资源现场：C/D 各自 Redis DB5/6 PING 且 0 keys、MinIO 专属 bucket 存在、Web/API/CDP 端口空闲。未启动服务，未运行可能截表的模块 pytest。此项只解除依赖环境 HOLD，不是 C/D 业务或浏览器验收。

## R3-F Designer 浏览器身份最终准备（2026-10-05 14:33 +08:00）

- 为通过前端 `courseDesigner` workspace guard，seed helper 通过真实、审计化的 admin 角色授权 API 建立 platform `course_designer`；没有直接伪造 `/me` 响应。当前账号实际 `/me` 返回角色 `student, teacher, course_designer` 和 `course_design=true`，且 8215 实际登录、课程列表、双 Release 列表持续返回 200。
- 该补正完善真实隔离浏览器前置条件，但 F 的 manifest/Diff 浏览器操作、零写请求证明、截图/trace 仍未验收。

## R3-G 隔离迁移准备（2026-10-05 14:36 +08:00）

- G 数据库迁移前实际 revision 为 `0049`（本次前置只读查询连接到 PostgreSQL admin DB，因此未据其错误输出判断 G 空库）；确认 G 库无其他连接后，主窗口执行 0049→0050、`alembic current` 和 `alembic check`，结果 `0050 (head)` 且无新操作。该迁移是向前追加字段/约束/索引，未清除既有记录。Redis DB10 PING/0 keys、G bucket 存在、3216/8216/9316 空闲。
- 此项只为 G 服务依赖测试解除 schema 准备门槛；未运行 G pytest/API/Chromium。A 的 PublicationSnapshot 响应字段子项已独立 GO，等待其模块测试。

## 复现命令

```powershell
docker compose up -d postgres redis minio
server\.venv\Scripts\python.exe -m pytest server/tests -q
server\.venv\Scripts\python.exe -m ruff check server
Set-Location server
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
Set-Location ..
server\.venv\Scripts\python.exe scripts/export_openapi.py
server\.venv\Scripts\python.exe scripts/g0_smoke.py
Set-Location web
pnpm test
pnpm typecheck
pnpm build
```

## R3 主窗口协调验证（2026-10-04）

- **代码/迁移：** 当前 head 为 `0049_r3_teacher_activity_assessment_release.py`。R3-A 隔离库实测 `0048 (head)` 且 `alembic check` 通过；新的主窗口隔离库 `psychology_learning_v1_r3_shared_20261004` 从全历史 0001 成功 `upgrade head` 至 `0049 (head)`，随后 `alembic check` 返回 `No new upgrade operations detected`。校验中发现并补齐一个 Assessment assignment index 元数据差异后复跑通过。SQLAlchemy 对 pgvector 的类型识别警告仍在。一次错误 DSN 驱动别名连接失败（未执行建库），更正后只创建不存在的专属共享库；预览库未连接/升级。
- **静态检查/契约：** `ruff check app/db/models.py` 及 0048/0049 两条迁移通过；快照/基线 PowerShell AST 解析通过；根级 `git diff --check` 通过（仅有 3 条既存 CRLF 转换提示）。OpenAPI 当前仍 133 paths；0049 无新增路由，导出快照 hash 为 `615D6C248AC69A5780262088C6B0C8BBE466C88FAA916D3A06CE7ABF45CCF9AE`。基线按 UTF-8、Ordinal 路径顺序计算工作树 status+文件 SHA-256 指纹。
- **隔离环境：** 资源现场复核时 PostgreSQL A—G 可连接；A 后升至 0048，其余数据库状态可能随窗口 GO 后测试变化；Redis DB3/4/5/6/7/8/10、七个 buckets 与专属端口的初始核验记录见并行状态文件。新 root shared DB 独立用于验证 0049。Docker Engine 未核验，不能写作通过。主预览 PID Web 36428/API 81684，HTTP 200；API 133 paths。预览 DB `psychology_learning_privacy_target` 只读仍为 0044，与代码 0049 不一致，未升级。
- **前端物理隔离：** C/G/E/F 均使用业务源码物理副本（仅 `node_modules` 为 junction）、各自 distDir production build 成功；API proxy 返回对应隔离 stub。Chromium 访问 3212/3214/3215/3216 首页均 200，代理请求均 200，375px viewport 下 scrollWidth=375，无页面 JS 错误。该结果只验证基础 shell/toolchain/proxy，不等于真实业务页面验收。临时 API stub 和 Next 服务已停。
- **契约/GO：** 0048/0049 shared schema 的用途、Scope、API 草案与错误语义见 `R3-shared-contract-decisions-2026-10-04.md`。R3-A—G 均获得表内受限子范围 GO；D/E 可实现其模块 API，F 的共享 Preview/Review/Gate/Publisher/Assignment 服务仍待主窗口。GO 与窗口局部报告不构成业务验收。
- **尚未运行：** R3 新增业务测试、全量后端回归、OpenAPI 导出漂移、全量前端 Node/typecheck/lint 与业务 E2E 尚未运行。没有真实心理学教材/教案、机构评分可见/保留政策、获准学生答案 AI 评分输入或生产数据；这些层级未验收，不能声明 V1 完成。

## R3 Tutor ChatSession 发布版本绑定底座（2026-10-05 15:00）

- **实现：** 主窗口增加 `0051_bind_chat_sessions_to_course_releases.py`，为 ChatSession 新增两个成对 nullable 发布绑定列、FK(RESTRICT)、索引与 check constraint。保持旧会话 NULL，不回填猜测值。代码及迁移位于共享所有者范围。
- **实际验证：** B 隔离数据库从 `0050` 正向迁移至 `0051 (head)`；`alembic check` 返回 `No new upgrade operations detected`。全新隔离 root DB `psychology_learning_v1_r3_root_session_20261005a` 执行 Release workflow **5 passed、2 warnings**，显式目标库 `current=0051` 且 `alembic check` 通过；模型与迁移 Ruff 通过。
- **未验收：** B 尚未交付 ChatSession 创建时 assignment/release 固定、SSE turn 固定检索 Scope 与 Claim adapter 完整接线；尚无 Tutor Domain Claim SSE 数据库/API/browser 端到端结果。0051 是该项的必要 schema 前置，不代表业务闭环已完成。新绑定代码/全迁移尚未在静止共同树跑全量后端。
- **环境说明：** PostgreSQL、Redis、MinIO 和目标 TCP 服务当前可达；Docker CLI 管理管道访问受限，未依赖容器状态推断。任何窗口库迁移均须先确认精确库名、当前 revision 和无并发连接；主预览库 0044 绝不迁移。
