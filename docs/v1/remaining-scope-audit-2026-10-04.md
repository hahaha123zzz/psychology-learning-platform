# V1 P0—P10 剩余范围审计（R2 历史基线 / R3 持续更新，2026-10-04）

本清单按《06-V1总体迁移与实施执行计划》逐阶段复核；状态不由阶段首切片推导。证据以代码、迁移、自动化测试、本地 API/浏览器和来源输入为准。本文件记录本地工程范围，不扩大到真实班级、生产运行或学习效果。

状态含义：**有证据**=本阶段指定能力已有可复现证据；**部分**=已有切片但仍有本表缺口；**进行中**=R2 当前任务尚未交付/验收；**等待输入**=缺许可教材或外部业务策略；**明确排除**=用户已明确留到未来范围。

## 阶段总览

| 阶段 | 当前判断 | 已有依据 | 仍需完成/下一步 |
|---|---|---|---|
| P0 规格、契约与视觉 | 部分 | 需求矩阵、后端领域/API 状态/组件/迁移规格和 11 组页面状态说明已存在 | 需求矩阵还不是逐个 P0—P10 子任务到代码/测试的完整追踪；P0-04 的视觉稿和可访问性人工审阅记录尚未形成完整签收；R01—R08 的兼容结论需逐条挂到迁移/授权门禁。 |
| P1 权限、公共模型与前端基础 | 部分 | 显式 RoleAssignment、课程/班级/任课、Outbox、CourseRelease、工作区守卫和设计系统已有迁移/测试；R2-B 课程/班级/成员 API 与 Admin 浏览器操作已联调；0049 与 ReleaseAssignment GET/PUT 现已编码并有隔离回归 | 新 Study/Assessment/Activity Run 固定 assignment/release 尚未接齐；四 Shell/缓存 Scope/真实端到端覆盖不完整。 |
| P2 内置教材、Domain、Evidence | 进行中 | Course Compiler manifest、OOXML parser、固定 PDF 文本 span 映射、持久 EvidencePointer、多页锚点与 PDF Reader 合同已编码；R2-A 合成 PDF Reader 浏览器切片通过；P2-08 旧教师教材写入口在默认关闭下经 43 项隔离回归通过，教师活动页改为只读 | DOC/DOCX 固定渲染受本机缺少 LibreOffice/Word 阻塞；TEXTBOOK/ 10 个文件是数学主题旧 DOC，只登记 hash，未解析/转换。MisconceptionDefinition/审核边界、DomainRelease—索引绑定、Claim 四态/一次有界补检索及 Course Content Admin 替代构建工作台仍缺。 |
| P3 Learning Record、Learner Model、Memory | 部分 | 事件资格化、掌握规则/失效重算、ReviewState、隐私删除工作单已有代码和定向测试；R2-C 隔离真实 Worker 回滚、Redis late-ack 重投、凭证状态回执已验 | 多知识/DomainSkill/误区模型，以及 Memory 来源等级、冲突/时效/替代合同仍缺。生产擦除、机构保留政策和备份索引擦除是未来范围。 |
| P4 Teaching Runtime、Policy、Planner | 部分 | CurrentLearningTask/TeachingSession/Episode、状态恢复、Safety 语境规则和 SSE 同键恢复已有测试 | effective Policy 跨入口统一执行、固定 Action/support gradient、Branch structured merge、Planner 先修图/预算/fallback 尚未形成完整业务合同。R2-C TCP SSE 两类中断通过，不等于 P4 全项完成。 |
| P5 学生主链与实验推理 | 部分 | Home 任务队列、学习空间、偏好/通知、案例服务与工作台已有首切片 | 五类案例当前主要校验字段完整度，不是实验推理语义评分；scaffold 渐退、完整成长四 Tab 与可解释反馈/状态失效刷新、360px/键盘/焦点系统验收仍缺。 |
| P6 教师诊断、教学与干预 | 部分 | 班级聚合、TeacherObservation、干预运行/再验证与 Scope 测试已有 | TeachingActivity/Run、Planned/Actual Timeline、Course Policy 和覆盖层尚缺；教师分析需补样本口径/更新时间/少样本边界的浏览器呈现。 |
| P7 题库、正式测评、评分、复习 | 进行中 | 版本化题库/测评、后端 AI Policy、独立 Assessment Shell、人工评分与质量反馈有测试；R2-C 双标签、离线输入保留、冲突、刷新恢复、截止及提交事件真实浏览器通过；R3-E 新增 Rubric/用途/结果策略路由，主窗口复核 `/result` 对进行中尝试按策略拒绝，7 个相关定向测试通过 | P7-01/02 端到端资格/结果策略与发布 Wizard 仍缺；P7-06 AI 评分建议因无获准模型/学生答案输入而不启用；R3 全量时测评相关旧集成断言已与 fail-closed 合同同步，仍须静止快照全量回归和结果策略业务浏览器验收。 |
| P8 TeachingAsset、Mini Lab | 部分 | 白名单 TeachingAsset、fallback、六阶段 Mini Lab、检查点和资格化已实现；R3-G 仅有通用工程范围 GO，现场数据库尚未迁移 | 2—3 个最终教材支持实验、真实教材图表/公式资产和正式设备/无障碍替代需要获准内容；不以 attention-cue-basic 工程 fixture 冒充课程实验或科研效度。实验跨设备浏览器验收仍缺。 |
| P9 Designer/Admin | 进行中 | Admin 首批治理和 R2-B 隔离浏览器切片已验；主窗口现有真实 Preview/Diff/Gate/Review/Impact/受控 Publisher/Assignment API；无请求体 legacy `/publish` 已关闭（422），OpenAPI 明确请求体必需；前端 Node **46/46**、typecheck、lint 通过 | Preview 仍是安全 JSON manifest 投影；Impact 因缺少证据到 assignment 绑定而 `not_measured`；Course Designer 审核/Publisher 业务浏览器与运行版本固定仍未验。 |
| P10 本地验收、文档与交接 | 进行中 | OpenStax/R2 浏览器与故障实测记录可复现；R3 当前共同树全量后端 **315 passed、2 warnings**；root shared migration `alembic check`、全仓 Ruff、前端 Node **46/46**/typecheck 通过，lint 0 errors/3 个既有 warning；OpenAPI **149 paths** | 各窗口最终交接和业务浏览器范围仍缺，迁移历史对账、端到端评测失败集和 P0—P10 全需求追踪仍缺；不可把全量自动测试通过宣称为整体验收。 |

## 尚未关闭的子任务登记

| 原任务 | 审计结果 / 风险 | 当前归属与可验收的下一步 |
|---|---|---|
| P0-01/02/03/05/06 | 文档资产已存在，但需求行与 API/状态/测试的双向映射、领域依赖图、状态非法路径、迁移 R01—R08 逐项证据还未统一审计。 | 主窗口在最终集成时将本清单连接到 traceability 与 acceptance matrix；不把文档“存在”视为业务完成。 |
| P0-04 | 11 组页面规格存在；目标稿的视觉确认、键盘焦点、窄屏/减少动画人工记录未完整。 | 本地工作范围内补有限人工可用性检查；用户未要求本轮真实教师预验收。 |
| P1-02/P1-04 | CourseReleaseAssignment 已有 0049 schema 与 `GET/PUT .../release-assignment`，支持 expected_version、幂等、关闭旧指派/新指派 supersedes 链。 | Activity/Assessment/Study 运行开始时固定 assignment 与 release 尚未接齐；做跨模块旧版本运行回归。 |
| P1-03/P10-03 | Outbox 有事务/去重/重试单测；真实进程崩溃/消息确认模糊结果与旧数据对账覆盖不足。 | 本地可扩充隔离 Worker 实验；生产代理、备份/恢复验证按用户指示排除。 |
| P2-01/02/03 | Compiler manifest/保守定位适配器已编码；10 个 TEXTBOOK 输入仍是未处理 OLE DOC。缺受控本地渲染器，不能给出固定 PDF、字体替代/页数稳定或人工定位金标。 | 现有源文档和 hash 保留；缺 renderer 前不伪造转换链、不安装/下载未批准二进制、不使用外部模型。等待可用本地 Office/LibreOffice 输入。 |
| P2-04 | 当前 Domain Pack 支持 KnowledgePoint、ExperimentSchema、Relation、EvidenceBinding 的类型/引用/先修环/发布前绑定校验；MisconceptionDefinition 完整字段、审核状态与 Canonical 候选边界不足。 | 主窗口先固定 Misconception 与候选—审核—发布状态合同，再决定是否需迁移。 |
| P2-05 | RetrievalUnit/对象映射和过滤前检索已存在；DomainRelease 与索引 manifest 的不可变绑定及闭环发布尚未完成。 | 主窗口补域版本与教材/Embedding 索引版本关联的服务合同、替换/回退测试。 |
| P2-06/07 | EvidencePointer 持久恢复、多锚点 PDF Reader 和重新鉴权存在；Claim 的 supported/partially-supported/contradicted/unknown 四态、最多一次有界补检索及 DOCX 固定页面仍缺。 | R2-A 浏览器只验证合成 PDF 的详情/页图路径；待 A 交付集成后标注真实教材边界，不扩写为 DOCX 验收。 |
| P2-08 | 普通教师单次/分片上传、解析、索引、知识修订、发布与归档旧接口仍保留在代码中；产品默认 `MATERIAL_LEGACY_AUTHORING_API_ENABLED=false`。真实课程 Scope 先校验，越权返回 404、已授权旧写请求返回 410；仅允许创建者取消自己的遗留上传；教师教材活动页只读。新隔离库专项 **43 passed**。 | 旧教师写能力退出门槛已满足；Course Content Admin 的替代构建/审核发布工作台尚未实现，对新增内容流程需提示联系内容管理员，不可称替代链路闭环。 |
| P3-03/05 | KnowledgePoint 掌握状态有版本化理由和证据数，但技能/误区状态未独立建模；Memory 来源、冲突解决、保质期、替代字段已有 0048 与 R3-B 工作树实现，尚未交付验证。主窗口已修正 `/me/memory` 与 `/me/memory/items` 的无课程参数聚合，保留本人各课程 Scope。 | B 交接后核验来源/时效/冲突/Branch 规则与错误路径；用户级汇总用 `test_memory_summary_and_weakness_candidates` 复归通过，不代表 Memory 子域整体验收。 |
| P4-02/03/05/06 | Assessment AI Policy 与 Safety 已覆盖部分入口；统一 effective Policy、动作 schema/support gradient、已确认的 structured Branch merge、Planner 四态与可解释候选预算不足。 | 主窗口在新状态合同明确后逐切片实现；不得把生成输出直接设定业务状态。 |
| P5-04/05/06/07 | 案例工作台和偏好/通知有首切片；语义评分、scaffold、成长解释/反馈、响应式/键盘全链及隐私透明面未齐。 | 保持评分局限标示；补来源可追踪的学生浏览器任务与键盘矩阵。 |
| P6-01/02/03/05/06 | 学情聚合、观察、干预存在；教学活动时间线、课程内容只读覆盖层/收藏、少样本统计、诊断—活动—复测浏览器闭环未齐。 | 主窗口根据教师授权边界继续实现，不提供私聊/记忆正文或风险榜。 |
| P7-01/02/06/08 | 测评保存、截止、人工评分切片存在；R3-E 当前工作树增添 Rubric/用途/结果可见路由，但未见交付报告或业务浏览器验收。进行中 Attempt 的 `/result` 现 fail-closed，旧集成断言已按合同更新且对应 6 组组合通过。 | 无合规模型输入前只做确定性 Rubric/教师决定合同；AIGradingSuggestion 保持 disabled。R2-C 本地恢复证据不外推生产级别；静止共同树全量回归仍须完成。 |
| P8-02/05/06 | 通用 asset/lab 运行时存在；最终实验内容无授权输入。设备替代说明、真实实验中断与资格化浏览器验收不完整。 | 保留 `engineering_fixture` 标识；实验内容状态为“等待获准最终教材/教案”，不编造内容。 |
| P9-01/02/03/04/06 | 主窗口在工作树实现真实 Release Preview/Diff/Gate/Review/Impact/Assignment API，严格 Publisher 请求要求发布者、期望版本、幂等键和当前版本审核；专项回归验证审核失效、幂等与 assignment 换版。 | 旧无请求体 `/publish` 兼容分支尚能绕开新 Gate；课程设计业务页尚未接 Review/Impact/Assignment，Impact 不测量版本效果，且旧任务固定版本未联调。R3-F 只读 UI 子项需据此实施并做浏览器验收。 |
| P9-05 | Admin 后端新增同机构课程/班级/成员治理与列表游标。R2-B 隔离浏览器实际读取概览、IAM、课程/班级/成员、任务、审计；执行授权授予/撤销、软移除两类成员、创建班级和任课分配/结束，收到 201/200 与版本递增，撤权后活动列表不含目标。目标账号 `/me` 因无已知口令未验证；E2E 库还含来源未完全归因的旧授权/班级和并发写记录，均保留。 | R2-B 真实治理操作切片已验；撤权目标登录验证仍缺。不要泛化为完整 IAM 或 Designer/Publisher。 |
| P10-01/02/03/04/05 | 存在 OpenStax 历史本地评测、旧 P10-02 记录和 R2-A/B/C 浏览器/真实 TCP/Worker/Redis 证据；尚非完整 E1—E9 版本化数据集/人工金标/历史迁移对账/演示审阅包。 | 当前树隔离全回归和本地构建已通过；下一步按需求表补双向追踪、历史迁移对账和可复现失败集，不扩大到用户明确排除的生产/真实班级/学习效果验证。 |

## 外部输入与明确边界

- `TEXTBOOK/` 10 个 `.doc` 已识别为 OLE Compound File，sha256 与来源登记一致；原文件不改动。本机未检测到 LibreOffice/Word/Pandoc/Antiword/Catdoc/wvText；实际转换状态为“未转换”。主题为数学，只可用于工程压力与 parser 管线测试，不可冒充实验心理学教材证据。
- 真实实验心理学教材许可与 2—3 个最终实验选题、机构评分可见/保留策略、获准学生答案 AI 评分输入均未提供；这些缺口继续记录为等待输入/不启用，不得编造。
- 用户已明确不考虑生产部署、生产监控/告警、备份恢复、性能/容量、真实教师预验收、小范围试用与学习效果验证；均属未来范围，不因本地通过而关闭。

## 本轮验收保护线

窗口局部测试、mock 浏览器和 API health check 仅能证明对应边界；不等于全部 V1。只有代码、迁移、OpenAPI、前后端回归、真实本地关键路径、文档和故障证据一致后，才更新相应子任务状态。最新迁移 head、路径数、全量回归结果和预览数据库 revision 以 `V1并行启动状态.md` 与 `acceptance-report.md` 最新 checkpoint 为准。

## R3 责任与当前施工拆分（2026-10-04）

| 范围 | 当前责任/状态 | 可关闭条件与边界 |
|---|---|---|
| 共享迁移 `0048/0049` | 主窗口已实现；0048 在 R3-A 库通过 upgrade/check，0049 在新 root shared DB 从 0001 全历史升级并通过 check | 仅证明 schema 可迁移；Domain/Memory/Branch/Lab/Activity/Assessment 服务、API、OpenAPI 与用例仍需分别实现 |
| P2-04/05/06 | R3-A GO：knowledge Pack、审核/版本绑定、Claim 四态/有界补检索 | Tutor 回合接入归 B/主窗口；真实心理学语义需获准教材，合成夹具只验工程规则 |
| P3-03/05、P4-02/03/05/06 | R3-B 部分 GO：非 Domain 的 Memory 规则、有效策略/Tutor、Branch 幂等与非 Domain Planner | `memory/router.py`、隐私删除/管理员审计测试归主窗口；Domain skill/misconception/planner 等 A 接口就绪再接 |
| P5-04/05/06/07 | R3-C 部分 GO：案例、实际 Growth/Me 页面、学习/SSE页面 | Growth 不伪造未建模技能/误区；浏览器业务验收和窄屏/键盘矩阵待实施；案例字段检查不等同语义评分 |
| P6-01/02/03/05/06 | R3-D 对现有 intervention `/effect` 读模型与 0049 后的新 TeachingActivity/Run/Timeline/Annotation 模块服务取得限定 GO | 根 router aggregation/API 导出由主窗口处理；干预效果要求班级 Scope、UTC 半开窗默认 30 天/最长 90 天、`n<5` 隐藏精确统计；未满足双重独立复测时 `not_measured`，不作因果宣称 |
| P7-01/02/04/06/08 | R3-E 对确定性 Rubric/用途资格/结果可见 API 与 P7-08 可靠性取得限定 GO，底层 schema 已由 0049 提供 | `AIGradingSuggestion` 关闭；无机构许可、答案/教材授权和供应商承诺不得启用或外发；正式结果策略服务端 fail-closed |
| P9-01/02/03/04/06 | R3-F 对真实 CourseRelease 数据只读 Designer 子项取得限定 GO；主窗口已实现 Preview/Diff/Review/Gate/Impact/Assignment 与受控 Publisher 请求；legacy 无请求体发布现返回 422，UI 与运行版本联动未验 | Preview 是真实 JSON manifest 投影；Diff 只比较已发布快照；ERROR 阻断、WARNING 有理由审计；Impact 因缺绑定明确 `not_measured`；Assignment 换版不覆盖历史；禁止静态 mock 冒充链路 |
| P8-02/06 | R3-G 部分 GO：通用 fallback、作废/恢复与资格隔离 | 已知 checkpoint 才可恢复，作废永不可续写/资格化；最终实验和教材资产等待获准教材/教案 |
| P10 | 主窗口统一基线、跨模块 OpenAPI/迁移/回归、状态/验收同步 | R3 共享工作树基线采用新可复现脚本；窗口 GO、局部测试和基础 UI proxy/build 证据均非 V1 总验收 |

主窗口仍持有所有 models/Alembic/conftest/OpenAPI/router aggregation/共享 UI build 配置与总验收文档。GO 范围及资源证据以 `V1并行启动状态.md` 为准；完整规则以 `R3-shared-contract-decisions-2026-10-04.md` 为准。外部教材/教案、机构保留/可见性政策、获准答案与供应商条款集中记录，不阻塞其他不依赖的工程施工。

### 2026-10-05 16:12 主窗口追加差距

- **CourseRelease 固定资料版本：** 主窗口在 create/explicit material reselect 时写 `material_version_ids` 与有序 `publication_snapshots`（snapshot/index Job/embedding/domain ID），meta-only PATCH 保留原值；新发布 Gate 检查 pin 未过期且仍为当前发布快照。root 专项 6 passed；未增加迁移/OpenAPI schema。尚未覆盖完整生产材料发布 API 到 Tutor 历史索引正向读取。
- **Tutor 历史固定与 Branch 继承（R3-B 子范围已在共享状态明确 GO）：** Tutor 仍按当前 Material/DomainRelease 状态过滤，旧 assignment 会安全拒答但无法正向使用其固定 snapshot；Branch child ChatSession 尚未确认继承父版本。需以真实工程材料发布流程生成 snapshot/index/RetrievalUnit 做正向和撤权负例，不能用直接 ORM 伪造作为唯一证据。
- **当前共同树验证：** 357 passed 属修改前运行快照，且期间存在窗口写入；不作为现行完整测试证据。主窗口已完成新 Release 专项与相关 Ruff/diff；完整后端、Web test/typecheck/lint/build、OpenAPI 双导出及 migration check 应在跨窗改动冻结后重跑。
- **服务/浏览器：** 16:12 时主预览 3000/8000、F 3215/8215 均无监听。F 曾以真实隔离 API/合成数据完成只读浏览器验收（历史证据保留），但不是当前可访问服务。Docker CLI 管理接口仍 permission denied；不得报告容器状态已核验。
- **不属于本地“一口气完成”的外部/未来输入：** 10 个 `.doc` 原始教材仍未因本次工作转换或发送；最终教材/实验教案、机构隐私/成绩/保留政策、获准答案与 AI 评分授权/供应商承诺、用户明确排除的生产部署监控备份性能及真实教师/学生效果均继续列入外部或未来验收，不可自拟、不可据工程 fixture 宣称完成。

### 2026-10-05 17:26 最终本地复验

- **P10 工程质量门：** 后端隔离全量在 `psychology_learning_v1_r3_root_final_20261005b`、Redis DB11、新 MinIO bucket **364 passed、2 warnings、24:32**；migration `0051 (head)`、`alembic check` 无差异、全仓 Ruff 通过。最初全量发现一个新 pin 校验错误码不兼容，修正后发布/Release 相关整套 **22 passed**，最终全量 clean pass。Web `pnpm test` **56/56**、`typecheck` 通过、`lint` 0 error/2 warnings；物理源码隔离 `pnpm build` 成功、24/24 页面。OpenAPI 双导出稳定：156 paths / SHA-256 `A7E85EF6A81C2D2CEF673E87EEB2D54C7D63C29C28975B737DFC46B155322743`。
- **可查看服务：** API 8000 使用独立 `psychology_learning_v1_preview_20261005`、Redis DB2、`psych-preview-root-20261005` bucket；从 0001 全迁移至 0051 并 check。`/health/live`、`/health/ready`、Web 首页与 `/login` 均 200，Web 同源 API proxy 到 8000 返回健康 `ok`；合成演示教师登录 200，可见 1 门合成课程。没有连接/迁移 `.env` 指向的旧 `psychology_learning`（revision 0038）或其他旧预览库。Web 3000 在启动 API 后已发现为既有监听（其旧 `tmp/dev/web.json` PID 与现场 listener 不同），本窗口未停止/覆盖该进程；以页面/proxy 即时验活为准。
- **还不能关项：** R3-B 历史 superseded PublicationSnapshot 的 positive Claim 检索及 Branch child pin 尚未交付；课程设计写工作台、Release Impact 合格证据端到端、C/D/G 业务浏览器等仍按窗口报告待验。最终教材/实验教案和机构隐私、成绩可见、保留政策、AI 评分许可及供应商承诺是外部输入；真实班级与生产/效果验证按用户要求排除，不能算成本地完成。
- **整体判断：** P10 当前工程验收可标为“本地自动化/构建通过，但跨模块业务验收仍部分”，V1 计划不得标记全部完成。

### 2026-10-05 15:00 主窗口增量审计

- **P1/P2 Tutor Claim 持久化新增共享前置：** 已编码 migration `0051`，ChatSession 可空固定 CourseReleaseAssignment/Release，历史不回填；B 的 Tutor 路由仍需完成会话创建时绑定与 turn 检索/Claim 接线。验收分层：共享 schema 已经隔离迁移验证；模块 API/数据库/浏览器闭环未验收。
- **历史 Release Search：** A 当前测试证明 DomainRelease 与直接绑定 PublicationSnapshot/IndexJob 隔离，但尚未证明真实材料发布生成的快照能从对应历史 assignment 读取；用户当前 assignment 换版不得使旧会话/运行悄然切到新索引。由主窗口集成测试与 A/B 接线继续闭环。
- **共同回归：** root 新专库 `psychology_learning_v1_r3_root_session_20261005a` 的 Release 专项 5/5、0051 schema check 通过；当前完整共同树后端、全前端生产 build/浏览器矩阵仍待窗口交付稳定后重跑。A 库有活动连接，未在该库执行 migration。

### 2026-10-04 23:24 主窗口最新复核

- 历史全量后端回归曾在共享工作树仍有窗口写入期间得到 302 passed、7 failed；失败为用户级记忆端点未聚合课程 Scope，以及进行中 `/result` 旧断言与当前测评结果 fail-closed 策略不符。之后一次全量为 312 passed、2 failed，发现两项旧测试仍直接依赖无请求体课程发布。主窗口关闭该兼容旁路、同步旧测试 helper 后，2026-10-05 当前树全量回归 **315 passed、2 warnings，1144.22 秒**；该结果更新自动化回归状态，但不代替 A—G 交接或业务浏览器验收。
- 当前 OpenAPI **149 paths**，SHA-256 `7F0CF080423A0875564A7075C25BC681507F1FF4F56A8E64603C4085E18ABFFB`；0049 shared DB `alembic check` 与全仓 Ruff 通过；Web Node 46/46、typecheck 通过，lint 0 errors/3 个既有 warnings。受控发布 API 的 OpenAPI requestBody 为 required；无请求体旧请求返回 422。主预览数据库仍为 0044，未升级；R3 专属资源与端口现场以并行状态文件最新检查点为准。

### 2026-10-05 14:06 主窗口共享运行快照更新

- **P1-02/P1-04：部分推进。** 新迁移 `0050` 为 LearningSession、Assessment Attempt、LearningEvidence 增加 nullable CourseReleaseAssignment/CourseRelease 成对绑定、FK/索引和配对检查；旧数据不猜测回填。独立新库已到 0050 且 `alembic check` 通过，Release workflow 5/5 通过。B/E 模块接线已明确 GO，但尚未交付；故“运行开始时固定 assignment/release”仍未关闭。
- **P2-05：服务链部分推进。** CourseRelease、PublicationSnapshot 与 material embed Job/RetrievalUnit 当前绑定同一 DomainRelease，发布/审核 Gate 定向测试通过；A 搜索响应的 publication snapshot 列表以及旧 Release/Assignment 按历史 snapshot 搜索仍待接线，不能标为完整历史版本检索。
- **P6/P9 Impact：仍 `not_measured`。** Evidence 表已有归因字段 schema，但 B/E 尚未写入来源链，也未验证合格事件、独立复测、时间窗及 n<5 抑制的端到端口径；不以新增空字段计算影响。
- **D 集成：仍有 1 个失败。** 主窗口注册 D router 后在隔离 root DB 的 activity/intervention 组合为 21 passed、1 failed；Run action 响应访问未刷新的 `updated_at` 触发 `MissingGreenlet`，精确修复和 D 专库重跑已交 D。
- **P10 当前验证限制：** 最新 OpenAPI 156 paths、重复导出稳定；当前迁移 0050/Release workflow 定向验证通过。之前 315 passed、2 warnings 的全量后端和 Web 46 项快照早于本轮改动，仅为历史结果。当前共同树全量后端、全前端构建/浏览器、真实心理学课程内容与生产数据均未验收。

### 2026-10-05 14:25 隔离窗口数据库准备

- C 原 0049 数据库与 D 空数据库均由主窗口按统一迁移所有权到 `0050 (head)`，check 通过；C 数据未清理。Redis DB5/6、bucket 与专属端口复核可用后，C 的服务依赖验收 HOLD 已解除，D 可复现其一项集成失败。两窗尚未提交新测试/浏览器结果，不能关闭 P5/P6 子项。
