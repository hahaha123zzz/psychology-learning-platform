# R3-F 只读准备报告

HANDOFF=COMPLETE; RESUMED=2026-10-05 11:09 +08:00（仅只读真实 Release UI 子范围）

检查日期：2026-10-04（只读审计；本报告提交时未获 GO）

## 基线与工作树

- 当前 HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`，与 R3 状态文档登记的 HEAD 相同。
- 主协调窗口登记的共同基线指纹：`17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`（排除 `.pnpm-store/` 与状态/报告文件）。本窗口未独立重算此指纹。
- 本窗口曾以 `git status --porcelain=v1 -uall` 读到 490 项；R3 基线记录使用过滤 `.pnpm-store/` 的 `--untracked-files=normal`，记录 226 项。两种口径不可直接比较，GO 前需按主协调窗口同一命令、过滤规则和快照重新核对哈希与文件归属。
- 当前排他区域已有未跟踪文件：`web/app/course-design/layout.tsx`、`page.tsx`、`domain/page.tsx`、`pedagogy/page.tsx`、`assessment/page.tsx`、`releases/page.tsx`、`assets/page.tsx`、`web/components/CourseDesignPackEditor.tsx`。它们是既有共同基线，不能覆盖或重置。`web/tests/v2-workspace-contract.test.mjs` 已修改且是跨任务文件，不应作为 R3-F 私有测试文件修改；没有发现专属 Designer 浏览器验收。

## 子项与验收边界

- P9-01：Domain Pack 结构化编辑、Canonical 只读/候选证据可追溯、409 保留本地编辑并可恢复。
- P9-02：受限 Pedagogy Flow 与 Inspector、真实 Student Preview；不得执行任意 React/JS，覆盖 fallback、无障碍和证据规则。
- P9-03：Assessment 候选、覆盖、Rubric、质量复核/校准预览；区分 Teacher 班级测评和 Designer 长期资产，不越权共享写入。
- P9-04：Release 选择、Gate、Impact、Diff、Review、发布和旧版弃用；ERROR 阻断、WARNING 需理由、服务端 Publisher 鉴权、重复发布安全回放。
- P9-06：发布/换版后运行中的 Activity/Assessment 固定原 Release；新任务使用新组合；撤回后旧引用仍重新鉴权。

## 当前后端合同与缺项

已有 CourseRelease 创建、带版本 PATCH、列表、发布 API；Domain Pack 有对象关系、EvidenceBinding、先修环及发布前证据/教材版本重验。CourseRelease 发布后不可原地修改；Designer 可编辑，Teacher/Publisher 可发布。三种 Pack 存放于 CourseRelease manifest JSON；Pedagogy/Assessment 目前只有有限结构检查。

缺少真实的 Preview、Review 状态/意见、版本 Diff、Gate 明细、Impact 报告、WARNING 理由确认、CourseReleaseAssignment/班级换版，以及运行中 Activity/Assessment 的 Release 固定与撤回后引用鉴权合同。现有 CourseRelease manifest 不是长期作者资产审批与运行分配合同。没有这些 API/模型合同前，前端不得使用静态数据或 mock 冒充已实现能力。

所需主窗口合同至少包括：

1. Domain API 与候选/审核/Canonical 写入边界（依赖 R3-A）；包括对象稳定 ID、证据引用及版本冲突响应。
2. Review、Preview、Diff、Gate 和 Impact 的请求/响应形状、错误语义、刷新时效与权限。
3. Publisher 发布命令的角色/Scope、WARNING 确认理由、幂等键、审计及重复发布响应。
4. CourseReleaseAssignment 的目标 Scope、版本/幂等/撤销规则，以及运行中 Activity/Assessment 固定旧 Release 的模型与读取行为。
5. 与 R3-E Assessment 编辑边界、R3-G TeachingAsset Release 绑定边界的共享约定。

本窗口不修改知识/测评后端、公共 API client、models.py、迁移、OpenAPI、公共 fixture、路由注册、公共构建配置或总验收文档；新增共享字段/路由交主窗口实现。

## 资源与验证方案

- R3 文档预留：PostgreSQL `psychology_learning_v1_r3_f_20261004`；Redis `redis://127.0.0.1:6379/8`；MinIO bucket `v1-r3-f`；Web/API `3215/8215`；Worker queue `v1-r3-f`（无入站端口）。以上来自状态文档，本窗口本次未重新连接、检查端口或验证 bucket；开工前必须现场复核，发生冲突即 HOLD。
- R3 Next 隔离 helper 的 7/7 配置 smoke 与脚本语法检查是状态文档记录的共享验证；物理源码快照、独立 Next 启动/代理和 production build 尚未实际验证。UI GO 门槛要求先验证隔离快照，不触碰 3000/8000 与共享 `.next`。
- 获完整 GO 后，使用真实 R3 API 做 Designer/Publisher 角色、409、错误/警告 Gate、Review、Impact、Diff、幂等发布、旧/新 Release 分配和运行中版本固定的定向浏览器验收；测试库、Redis、bucket、API/Web 端口均只用本报告所列资源。当前未运行测试、未启动服务。

## 跨任务依赖、阻塞与建议

- 等待 R3-A Domain API 合同，以及主窗口 CourseRelease/assignment、Review、Diff/Gate/Impact、Publisher 发布合同；状态文档明确这两项是 R3-F 依赖。
- R3-E 管理 Assessment 领域实现；R3-G 管理 TeachingAsset/Mini Lab；本窗口只消费双方确认的 Release/权限接口，不改其排他文件。
- R3-F 独立报告已提交，但当前并行状态行仍为 HOLD，且状态文档 GO 总表为 NO。**建议 HOLD，不请求推断式 GO。** 只有主窗口在并行状态文档中登记本窗口报告摘要、确认基线/文件/资源、解决合同依赖并把 R3-F 行明确改为 GO 后，才进入实现。

## R3-F 交接补充（2026-10-05）

### 当前授权范围与状态

并行状态文档给 R3-F 的是**部分 GO**：仅可在 Designer 页面消费现有真实 CourseRelease list/get/update API，展示已加载版本的真实 manifest 和内容 diff；该 diff 必须标注为内容对比，不得称为官方 Gate。排他范围是 web/app/course-design/**、web/components/CourseDesignPackEditor.tsx 及 Designer 专属组件/测试。Review、Publisher、Assignment 写路径和 mock 均不在本次授权内。原始任务 P9-01/02/03/04/06 的完整目标没有因此全部获准或验收。

### 基线与工作树复核

- HEAD 为 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04。
- 并行状态文档 2026-10-05 检查点登记共同基线为 509 项、SHA-256 32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146。本窗口按同一脚本现场复算得到 509 项、SHA-256 4CD799F097D733EBC561AAB8B623D3FCD0BB07FBC71FD1C52946B23F65B99650，两者不一致；本次未尝试归因或覆盖登记值。报告追加本身也会改变后续指纹。主窗口需在任一窗口继续写代码前说明新共同基线/增量的计算时点，并协调同树并发报告写入带来的指纹变化。
- 排他路径当前可见既有未跟踪文件：web/app/course-design/{layout.tsx,page.tsx,domain/page.tsx,pedagogy/page.tsx,assessment/page.tsx,releases/page.tsx,assets/page.tsx} 与 web/components/CourseDesignPackEditor.tsx。本窗口没有创建或改动这些文件；视为共享工作树既有内容，后续不能覆盖或重置。
- 当前 web/tests 未发现 R3-F 专属测试文件。该目录中存在其他窗口/共享测试的修改和新增，均不纳入 F 排他范围。

### 代码与后端能力现状

前端已有 Domain、Pedagogy、Assessment、Assets、Releases 页面及共用 CourseDesignPackEditor 入口；尚无本窗口实际实施或业务浏览器验收记录。R3 状态文档记载：工作区 OpenAPI 148 paths，已包含主窗口实现的 CourseRelease Preview/Diff/Gate/Review/Impact/Assignment 路由；主窗口稳定快照后端 313 passed、Web Node 46/46、typecheck 通过、lint 0 errors/3 个既有 warning。上述是主窗口共享证据，不是 F 页面验收。

源文档存在口径不一致：V1并行启动状态.md 与 2026-10-05 验收记录称相关服务/路由已进入 OpenAPI；implementation-status.md 较早段落仍称这些服务/API 待主窗口实现。请主窗口统一这几份文档并以实际代码/OpenAPI 为准。现有风险仍明确：无请求体 legacy /publish 路径可绕过严格 Gate；Impact 因 LearningEvidence 缺少 assignment/release 版本绑定而是 not_measured。这两项不能由前端呈现为已经解决。

### 拟修改文件（只在后续基线复核且 GO 未被收回后）

- web/app/course-design/domain/page.tsx
- web/app/course-design/pedagogy/page.tsx
- web/app/course-design/assessment/page.tsx
- web/app/course-design/releases/page.tsx
- 视现有组件分工，必要时新增 web/app/course-design/** 下 Designer 专属组件及对应 Designer 专属测试。
- 仅在确认该文件确属 Designer 专属且当前未被他窗/主窗占用时，才考虑修改 web/components/CourseDesignPackEditor.tsx；当前归属细节需主窗口确认。

不会修改共享 web/lib/course-api.ts、后端、共享模型/迁移/OpenAPI/路由注册/fixture/公共构建配置或总验收文档。若实际业务需要缺少的 API/字段，先向主窗口提交精确请求/响应/权限/冲突语义需求，由主窗口统一处理后再消费。

### 资源需求（仅复述分配，不代表现场验活）

| 资源 | R3-F 状态表分配 |
|---|---|
| PostgreSQL | psychology_learning_v1_r3_f_20261004 |
| Redis | redis://127.0.0.1:6379/8 |
| MinIO bucket | v1-r3-f |
| Web / API | 3215 / 8215 |
| Chromium CDP | 9315 |
| 独立队列 | v1-r3-f（无入站端口） |

以上为状态文档分配值；本次没有连接数据库/Redis/MinIO，也没有复核端口占用。开工前需主窗口确认隔离资源仍归本窗且现场无冲突。

### 风险、依赖与证据边界

- Domain Pack 语义/API 依赖 R3-A 的稳定合同；Assessment 编辑还需遵守 R3-E 的 Rubric/用途/结果策略边界；TeachingAsset Release 绑定依赖 R3-G；本窗不能改这些窗口的排他文件。
- 共享合同要求追加式 Review、不可变快照 Diff、确定性 ERROR/WARNING Gate、带理由的 WARNING 确认、Publisher Scope + expected_version + 幂等键，以及 CourseReleaseAssignment 换版和运行中固定旧 Release。虽状态文档记载部分服务已实现，仍需主窗口确认 OpenAPI schema、权限和错误响应可供前端可靠消费。
- 主窗口既有物理快照/build/proxy/Chromium 证据只证明隔离 shell 和代理；本窗口没有运行测试、启动服务或取得 Designer 业务浏览器证据。不得把根 Node 全量测试或根后端全量回归记作 F 业务验收。
- 开工前阻塞：共同基线 hash 不匹配；需主窗口确认本窗报告登记是否足以满足短期交接冻结、是否继续部分 GO；需确认 CourseDesignPackEditor.tsx 的当前实际所有者；需澄清实现状态/验收文档间 Preview 等 API 状态冲突。未解决这些项目时，本窗口只读。
- 本报告未核验运行时数据库版本、真实课程/Release 数据、Publisher 全链路、活动/测评运行中的版本固定或撤回后重新鉴权。局部 UI 与自动化结果均不代表 R3 或整个 V1 完成。

### 本次窗口动作

本次仅更新本 R3-F 报告；没有修改代码/共享状态文档，没有运行写库测试，没有启动服务。报告写入后继续等待明确属于 R3-F 且含一致共同基线、排他文件和完整独立资源信息的 GO/主窗口指示。



### HANDOFF 状态更正（2026-10-05）

HANDOFF=COMPLETE; RESUMED=2026-10-05 11:09 +08:00（仅只读真实 Release UI 子范围）

主窗口在并行状态文档新增交接要求后复核：本报告已列出范围、文件、合同依赖、资源分配和现有证据，但共同基线现场 hash 与登记的 32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146 不一致，因此不能声称相对共同基线的文件增量已确认。隔离资源分配值已列出，但本次未重新连接验证 PostgreSQL revision、Redis key 数、MinIO bucket 和专属端口；当前也没有满足用户要求的 R3-F 完整 GO。状态文档历史记录的物理快照/build/proxy shell 证据不等于本轮重新启动或 F 业务浏览器验收。故 HANDOFF 保持 INCOMPLETE，未恢复施工；代码、写库测试和服务均未运行。待主窗口明确基线对齐/增量口径并在 R3-F 记录完整 GO 后，按新授权复核资源及文件归属。


### 主窗口 HOLD 后只读现场复核（2026-10-05 11:06 +08:00）

- HEAD 仍为 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04。连续两次运行 scripts/r3-baseline-fingerprint.ps1 均为 509 项、SHA-256 1EBB24E36246DAF6B34F56350DDBAF5ECADD073802A2C0C9148010DF0457B256；与状态文档最近登记的 32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146 不同。此次指纹已包含本报告更新，不能当作相对 32DA 的逐文件增量。
- 只读 SQLAlchemy 查询确认专属 PostgreSQL psychology_learning_v1_r3_f_20261004 可连接，public 基表 0 张、alembic_version 不存在（空库，未迁移）。只读 Redis 检查 DB8 PING 成功、0 keys。MinIO 只读 list_buckets 确认 v1-r3-f 存在。5432/6379/9000 TCP 可达；Get-NetTCPConnection 未发现 3215/8215/9315 监听。
- 排他路径 git status 仍显示既有未跟踪 Designer 页面与 CourseDesignPackEditor.tsx；本窗口没有修改这些文件。Designer 专属测试仍未发现；跨窗口 web/tests 文件不认领。
- 状态文档保存了 2026-10-04 在 3215/8215 完成物理快照、production build、proxy stub 和 Chromium shell 的历史证据；这次遵守不启动服务的限制，没有重跑 build/proxy/浏览器。业务 Designer 路径无本窗口浏览器证据。
- 本次只读命令：scripts/r3-baseline-fingerprint.ps1（连续两次）、SQLAlchemy 查询 Alembic 表/公表、Redis PING/DBSIZE、MinIO list_buckets、TCP/监听端口检查、git status。未运行测试、未执行任何写库操作、未启动服务。
- 结论仍为 HANDOFF=INCOMPLETE / 只读 HOLD：资源已现场确认且当前无端口冲突，但共同指纹无法对齐登记值，且按用户当前规则不能在完整 GO 前启动隔离 build/proxy/浏览器验证。请主窗口更新共同基线/增量口径并在 R3-F 写明满足全部隔离信息的完整 GO 后，再进行下一阶段复核。



## HANDOFF 复核完成（2026-10-05 11:09 +08:00）

HANDOFF=COMPLETE; RESUMED=2026-10-05 11:09 +08:00（仅恢复状态表中 R3-F 只读真实 Release UI 子范围）

主窗口最新广播已取消对旧 32DA 指纹的追溯要求，要求各窗提供连续可复现指纹和清晰文件清单。当前共同工作树连续两次基线结果均为 HEAD 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04、510 entries、SHA-256 794B5B792C57DDA61AF9233144CC571A519B0CB8090FD98F4454112ECDB53FA9；该时点快照不包含本段追加内容，报告自身变化列为本窗口报告增量。

只读现场检查已覆盖：R3-F 数据库可连且空（0 张 public 基表、无 alembic_version）；Redis DB8 PING、0 keys；v1-r3-f bucket 存在；3215/8215/9315 无监听。当前排他目录内的七个页面和 CourseDesignPackEditor.tsx 均为既有未跟踪文件，本窗口未修改；没有 F 专属测试。web/.r3-runtime/r3-f-preflight-20261004 物理源码快照及其 .next-r3-f 输出仍在；并行状态文档已有该快照在 3215/8215 完成 production build、proxy stub、Chromium shell 的历史记录。没有在本次报告复核时重新启动服务或浏览器。

因此仅恢复表格所列只读真实 Release UI 工作，不扩大到 Pack 写入之外的其他 UI 写路径、共享 API client 或任何服务端 Review/Publisher/Gate/Impact/Assignment。P9-01/02/03 全量 Pack 编辑与 P9-04/06 发布、换版运行期验收仍未获得该范围授权或证据；若页面实现需要新增 API/字段，先提交主窗口合同请求。


## 已批准的只读 Release UI 设计

用户于 2026-10-05 批准以下设计：

- 页面通过既有 listCourseReleases 读取当前课程的真实 CourseRelease；不调用创建、更新、发布或其他写 API。
- 提供单版本选择用于查看实际返回的 manifest JSON；提供两个已加载版本的选择用于显示字段级内容变化。
- Diff 只比较 manifest，不声称覆盖服务端 Review、Gate、Impact 或发布资格；界面明确显示“内容差异，不是发布门禁”。
- 保留 loading、空列表、读取失败和无可比较版本状态；不使用静态样例或 mock。
- 仅改 web/app/course-design/releases/page.tsx 和确属本功能的 Designer 专属测试；不改共享 API client、CourseDesignPackEditor 或后端。
- 验收关注：从真实列表选版后展示相应 manifest；两个版本的新增/删除/修改字段可辨认；读取失败时不显示虚构内容；写 API 调用数为 0。

自审：范围与 R3-F 部分 GO 一致，数据只来自真实 list 响应；官方审核/发布服务仍由主窗口掌握；没有把静态数据或本地计算冒充正式 Gate。设计已获用户批准。


## R3-F 只读 Release UI 实施进度（2026-10-05 12:13 +08:00）

### 实际文件与共同基线

- 修改既有排他目标 web/app/course-design/releases/page.tsx：移除创建草稿与发布写操作；仅通过真实课程列表和既有 listCourseReleases GET 数据显示课程版本、选中 Release 的真实 manifest，以及两个已加载版本间的递归字段差异。页面包含加载中、空课程/版本、读取错误与重试状态，并明示内容差异不是发布门禁。
- 新增 web/tests/r3-f-release-view.test.mjs：验证递归 diff 的新增/删除/标量/数组项变化、真实 GET API 消费、不含写 API 调用及状态提示。
- 未修改 CourseDesignPackEditor.tsx、共享 API client、后端、其他窗口文件。web/components/TeacherAssessments.tsx 当前由其他窗口修改；F 未改动。
- 实施前复核 HEAD 4c8cc3dbbfbc2c95da26596398e295c9ccc72a04；对当前全树指纹脚本连续两次输出 522 项、SHA-256 0EA1693DAD8BDE0293898147AFD8DF45DA9A8C9C34756D3F5A36C67B1E57823E。该基线对应本段追加前的共享快照，新增本报告段落是之后的已知报告增量；全树指纹不表示 F 独有文件差异。

### 测试与构建证据

- web 目录运行 node --test tests/r3-f-release-view.test.mjs：3 passed、0 failed。
- 对 releases/page.tsx 运行限定文件的 tsc（noEmit、incremental false）：通过；定向 ESLint：通过。
- 新物理源码快照 web/.r3-runtime/r3-f-release-ui-20261005b，独立 .next-r3-f、API rewrite 指向 127.0.0.1:8215；pnpm build 通过，Next TypeScript 检查通过，24/24 静态页生成。
- 早先快照 r3-f-release-ui-20261005a 的 typecheck/build 被当时并发变动的 TeacherAssessments.tsx 中未定义 approveFormalPurpose 阻塞；后续新快照完整 build 成功，旧失败保留为历史，不作为当前 F 页面失败。
- 根 web 目录 pnpm typecheck 因只读工作区无法写入共享 tsconfig.tsbuildinfo 而退出；独立物理快照的 production build 已完成全项目 TypeScript 检查。
- 未运行数据库测试；未启动 API/Web/浏览器服务；没有业务浏览器证据。

### 当前现场与阻塞

只读重验显示 PostgreSQL psychology_learning_v1_r3_f_20261004 可连接，但无 alembic_version 且 public schema 为 0 张基表；Redis DB8 PING、0 keys；MinIO bucket v1-r3-f 存在。3215/8215/9315 当前无监听。虽然依赖 TCP 可达，R3-F 空库尚无 schema，且 8215 没有真实 API，因此无法按“真实 API、零 mock”要求完成浏览器场景。

需要主窗口处理：按统一迁移所有权在 F 专属数据库准备当前共享 schema（不得把该库交给其他窗口）；提供可通过真实 CourseRelease list API 读取的隔离工程 Release/课程数据或明确种子流程，并启动/安排 8215 API。资源和真实只读端点确认后，F 再以 3215/9315 完成浏览器预览/Diff验收。此依赖不授权 F 执行迁移、修改后端/公共 fixture 或使用共享/预览库。

当前已编码、自动化通过和独立 production build 通过；真实业务浏览器仍未验收。Publisher/Review/Gate/Impact/Assignment、P9 完整 Pack 编辑与发布换版运行期验收仍不属于当前 F 受限范围，也未宣称 R3/V1 完成。

## R3-F 真实 Release 页面浏览器验收与交接（2026-10-05 15:32 +08:00）

HANDOFF=COMPLETE; RESUMED=2026-10-05 15:18 +08:00（仅状态表 R3-F 真实只读 Release UI 子项）

### 当前共同基线与文件归属

- 检查时间 15:32 +08:00；HEAD=`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。`scripts/r3-baseline-fingerprint.ps1` 连续两次均为 535 entries、SHA-256 `27548E149B041E607634DB2AE4B8322DE8235C4986C4A87DE8E439596A8619BA`；排除本状态文件与 `.pnpm-store/`。状态文档 14:06 记录的上一共同指纹为 527 entries、`ADCC4DE9291CE3488680987D2D25DDB03863C76E9E1E1AB2E5A0A49F35FF401E`，计数及摘要均不同；其后并行树变化无法仅凭全树哈希归因到 F。按主窗口后续规则，以本次连续可复现快照和下列逐文件归属交接，不重建旧指纹，也不把全树差异称作 F 独有增量。
- `web/app/course-design/releases/page.tsx`、`web/tests/r3-f-release-view.test.mjs`：F 此前已实现的排他目标，均为当前未跟踪文件；本轮未改动。物理快照同名页面 SHA-256 与当前源码相同。
- `docs/v1/r3-preflight/R3-F.md`：本窗口报告，本轮追加本交接段。
- `web/components/CourseDesignPackEditor.tsx` 及 `web/app/course-design/{layout.tsx,page.tsx,domain/page.tsx,pedagogy/page.tsx,assessment/page.tsx,assets/page.tsx}`：状态表可见的共同工作树既有未跟踪文件，本轮未修改、不认领。未改共享 API client、后端、公共模型/迁移/OpenAPI/fixture、根路由、其他窗口文件或总验收文档。浏览器临时脚本保存在系统临时目录，未留在仓库。

### 隔离资源复核

- PostgreSQL 只读连接明确指定 `psychology_learning_v1_r3_f_20261004`，事务只读模式为 `on`；读取到 Alembic `0050`、public base tables 73。没有执行写库测试或修改课程/Release。
- Redis `redis://127.0.0.1:6379/8`：PING 成功，0 keys。
- `5432/6379/9000` TCP 可达；使用本 shell 的 MinIO 凭据只读查询 `v1-r3-f` 返回 `InvalidAccessKeyId`，故本轮无法重新验证 bucket。主窗口 14:22 交接曾确认 bucket 存在；本轮没有创建或修改 bucket，也没有尝试其他凭据。
- 浏览器前现场：3215、9315 空闲；8215 健康 API HTTP 200，由主窗口代管。验收后确认 3215、9315 已关闭/空闲，8215 仍 HTTP 200；只停止了本窗口启动的 Web 与 Edge，没有重启或停止 8215。
- 可复核命令包括：`scripts/r3-baseline-fingerprint.ps1` 连续两次；只读 SQLAlchemy `SHOW transaction_read_only`/Alembic/table count；Redis DB8 `PING`/`DBSIZE`；Python socket 检查隔离端口；`GET http://127.0.0.1:8215/api/v1/health/live`。MinIO 当前凭据不匹配为已知限制。

### 测试与真实浏览器证据

- `node --test tests/r3-f-release-view.test.mjs`：3 passed、0 failed。
- 对排他页面运行 `node .r3-runtime/r3-f-release-ui-20261005b/node_modules/eslint/bin/eslint.js app/course-design/releases/page.tsx`：通过。直接从根目录运行 `pnpm exec eslint` 因该 checkout 没有可调用的 eslint shim 未执行成功；隔离快照依赖下的限定文件 ESLint 已通过。
- 使用隔离快照 `.next-r3-f` 在 3215 提供既有 production build；API rewrite 指向真实 8215。Microsoft Edge 经 CDP 9315 + Playwright 完成真实登录、`/me` 角色检查和 `/course-design/releases` 页面验收。页面真实显示两份不同 manifest 与字段 diff；实际数据为 v2 `published`、v1 `deprecated`（状态文档 14:22 所写“两条均 published”已过时）。比较差异为新增 `domain_pack.chapters[1]` 与 `pedagogy_pack.tasks[1]`。
- 页面阶段捕获 API：`GET /me`、`GET /courses`、两次 `GET /courses/{courseId}/releases`；非 GET/HEAD/OPTIONS 请求 **0**，页面错误 **0**。登录用的 `/auth/login` POST 在开始页面请求计数前完成，是身份认证副作用，不属于 Release 页面写调用。
- 截图：[r3-f-release-page.png](/E:/项目/心里/web/.r3-runtime/r3-f-release-ui-20261005b/evidence/r3-f-release-page.png)；Playwright trace：[r3-f-release-trace.zip](/E:/项目/心里/web/.r3-runtime/r3-f-release-ui-20261005b/evidence/r3-f-release-trace.zip)。该证据来自合成工程课程与 Release，不代表真实课程内容验收。
- Playwright 技能包装器尝试写入只读技能目录而收到 `EPERM`；未改技能目录，改用现有 Playwright 包由 Node 直接执行临时脚本。可见 Edge GPU 子进程在本机报访问拒绝，最终以 `--headless=new --in-process-gpu` 的独立 Edge 会话完成浏览器证据；页面仍由真实浏览器执行，不使用 API mock。

### 剩余依赖与边界

- 登录后的实际落点为 `/courseDesigner`，本次随后直接打开获批页面 `/course-design/releases` 并由页面 guard 验证通过。需主窗口核对登录落点与 Designer 路由命名是否一致；本窗口不改共享登录页或根路由。
- MinIO bucket 的本轮独立只读复核仍待可用的隔离凭据；不阻塞已完成的 Release GET 页面验收，但应在后续依赖 MinIO 的任务前补验。
- 本轮 GO 只覆盖真实 Release 只读 UI。Domain/Pedagogy/Assessment Pack 编辑与写入、Review、官方 Diff/Gate/Impact、Publisher 发布、Assignment 换版和 P9-06 运行期固定/撤回鉴权仍需主窗口提供并验收共享 API/模型合同；不得由 F 用静态样例或 mock 填补，也不得据本轮浏览器结果声称 P9 或 V1 全部完成。

### 并行状态文档现场差异（2026-10-05 15:33 +08:00）

随后读到共享状态文档的 15:20 F 验收补记：该记录称主窗口保留 3215。15:33 本窗口只读 TCP 检查结果为 3215 closed、8215 open、9315 closed，且 `GET /api/v1/health/live` 返回 200。已停止的只有本窗口自己启动的 3215 与 Edge 9315；未对主窗口 API 操作。请主窗口按其进程状态协调文档中的 3215 服务描述。本窗口没有据文档旧状态重启任何服务。

共享状态文档 16:12 更新已将现场更正为 3000/8000/3215/8215 均无监听，且明确 F 浏览器验收已完成、之后需按登记快照/专库重新验证再展示。本窗口不触碰主窗口服务。新增的 CourseRelease manifest snapshot pin 由主窗口在课程路由实现；本页展示真实 manifest 的通用 JSON 与字段差异，无需 F 侧改动。同期新增 GO 属 R3-B 的 Tutor 历史快照读取与 Branch 子会话继承，不属于 F 排他范围，也没有 F 依赖。


