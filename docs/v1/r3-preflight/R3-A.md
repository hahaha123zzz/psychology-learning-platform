# R3-A 只读准备报告

> 下方首段为 GO 前的历史只读准备记录，其中“尚未获得 GO/HOLD”的判断已被 2026-10-04 的 R3-A 限定 GO 取代；最终实施交接以本文末尾的“R3-A 最终交接补充”小节为准。

状态：已提交只读报告，建议继续 HOLD；尚未获得 GO。本报告仅记录只读检查与依赖，不表示实施开始。

- 检查时间：2026-10-04 19:57 +08:00。
- 确认 HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`，与并行状态文档的 R3 基线 HEAD 一致。
- 共同基线指纹：并行状态文档记录 `17AFD369D9389C3DA5B3BA41A0B7E6A3235915C255298896B6C9554D97554C72`（排除 `.pnpm-store/` 与状态文档自身）。本次只确认 HEAD，并查看当前 `git status`；没有从状态文档历史快照独立重建其 696 条记录的指纹。GO 前请主窗口按当前共同工作树重新核基线。
- 拟修改的精确文件及当前状态：GO 后候选范围为 `server/app/modules/knowledge/**`，预期新增领域实现文件并视集成合同调整 knowledge 的检索/Evidence 服务。当前 `server/app/modules/knowledge/router.py`、`service.py` 已有未提交修改；`server/tests/test_domain_pack_graph.py`、`test_domain_pack_validation.py` 当前为未跟踪文件，`test_search.py` 已有修改。全部视为既存基线，开工前逐文件核对归属，不覆盖现有内容。预计新增/调整的定向测试仅限 Domain Pack、检索与 Evidence 领域专测；Tutor 集成测试需与 R3-B/主窗口协调。
- P2-04/05/06 子项与验收标准：
  - P2-04：补全 MisconceptionDefinition 的结构化定义、证据绑定与候选/审核/Canonical 发布边界；无证据或未审核候选不得进入已发布域包；非法字段/引用和并发版本冲突应有确定性错误。
  - P2-05：建立不可变 DomainRelease 与索引 manifest 的版本绑定，固定其域包摘要/版本、教材 PublicationSnapshot 或版本、索引任务及 Embedding 版本；域包或索引替换后旧版本引用可追溯，发布/回退不能混用版本，Scope 必须在召回前生效。
  - P2-06：Claim 状态使用 `supported`、`partially-supported`、`contradicted`、`unknown` 四态；无证据不误报支持，方向/数值/条件矛盾能被识别；补检索最多一次且绑定原用户权限、课程与发布版本，记录初次/补充证据和决策；超预算或仍未知时明确降级/拒答。
- 所需模型/API/迁移/路由/事件字段：现有 `CourseRelease.manifest` 已保存 Domain Pack，`PublicationSnapshot` 保存教材版本、索引任务和 Embedding 版本，但当前没有 DomainRelease 实体/标识，也没有将域版本摘要写入索引快照的字段。请主窗口决定采用新增 DomainRelease 表，还是在现有 Release/Publication manifest 中增加不可变的 `domain_release_id`/`domain_pack_sha256` 与索引绑定字段；如需数据库字段/约束则由主窗口新增向前迁移。Misconception 的审核者、审核时间、状态及候选来源/Evidence 引用需要明确字段合同。Claim 输出可先用现有 `TutorTurn.verification` JSON 承载四态与证据/尝试摘要，但持久审计若需独立表/字段由主窗口评估迁移。草稿审核 API、错误码/409 语义、发布门禁及新增路由由主窗口统一定契约、注册并导出 OpenAPI。
- 与其他 R3 窗口的冲突或依赖：R3-B 持有 `tutor/**`，需消费本窗口稳定的 Claim 校验/有界补检索接口；需先协商函数/API 的输入输出与调用预算，不得由 A 改 Tutor 文件。R3-F 的 Designer 等待 Domain API 与 CourseRelease/发布门禁合同。共享模型、Alembic、公共 fixture、路由聚合、OpenAPI、总验收文档均由主窗口处理。
- PostgreSQL / Redis DB / MinIO / Web、API 端口只读核验：`psychology_learning_v1_r3_a_20261004` 可连接，`public` schema 业务表数为 0；Redis `127.0.0.1:6379/3` `PING=True`、`DBSIZE=0`；MinIO bucket `v1-r3-a` 存在；Web 3210、API 8210 均无监听。以上是本次只读现场结果，不等于已验证业务运行。Worker 无入站端口，待 GO 后使用登记的 `v1-r3-a` queue。
- 测试、浏览器与 Worker 方案：GO 后先复核基线、文件归属及 DB/Redis/bucket/端口；纯校验可运行 Domain Pack 专项单测，集成测试仅用分配的数据库与 Redis DB3；索引发布/回退测试使用该隔离库；Worker 若需验证使用独立 `v1-r3-a` queue。A 本身不计划浏览器验收；Tutor API/SSE 集成由 R3-B/主窗口接手。未获 GO 前未运行任何测试、迁移或服务。
- 阻塞：并行状态目前仍写明 R3-A 为 `HOLD：只读`、所有 GO 为 NO；共同指纹需主窗口在当前工作树复核；P2-04/05 的字段/实体和 P2-06 与 Tutor 的接口合同待主窗口确认。知识模块文件存在既存修改，必须先做 GO 后复核归属。真实教材语义评测还受获准教材输入限制；合成 fixture 只能证明工程规则。
- 建议：**HOLD**。只读准备报告已提交；待主窗口在并行状态文档核收报告、确认共同基线、复核共享模型/API合同，并将 R3-A 行明确改为 GO 后再实施。

## R3-A 最终交接补充（2026-10-05）

- **交接状态与范围：** R3-A 按 `docs/v1/V1并行启动状态.md` 中 2026-10-04 的限定 GO 实施 P2-04/05/06，范围仅为 `server/app/modules/knowledge/**` 及 Domain Pack、检索、Claim 专测。主窗口 2026-10-05 广播进入短期集成交接/测试冻结；本补充只提交报告，不继续代码、迁移或服务写入。
- **基线：** HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。主窗口记录的共同基线为 509 项、指纹 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`。本次只读运行 `scripts/r3-baseline-fingerprint.ps1` 得到 509 项、指纹 `4CD799F097D733EBC561AAB8B623D3FCD0BB07FBC71FD1C52946B23F65B99650`；这是更新本交接报告之前读取到的工作树指纹，包含并行状态文档之外的当时未提交内容，不代表我改动了 509 项。历史增量无法仅凭当前树重建；未重置、清理或覆盖文件。
- **本窗口实际改动文件：** `server/app/modules/knowledge/router.py`、`server/app/modules/knowledge/service.py`（这两者在 GO 前已有共享工作区修改，我只在核定的 knowledge 子范围内增量改动）；新增 `server/app/modules/knowledge/domain.py`、`server/app/modules/knowledge/domain_router.py`、`server/tests/test_knowledge_domain_claims.py`。`server/tests/test_search.py`、`server/tests/test_domain_pack_graph.py`、`server/tests/test_domain_pack_validation.py` 在 GO 前已存在改动/未跟踪内容，作为基线保留，不列作本窗口新建文件。未改共享模型、迁移、fixture、OpenAPI、路由聚合、Tutor 或总验收文档。
- **已编码：** DomainRelease 子路由支持创建、读取/修改、审核和发布；审核决定追加保存，作者不能审核自己的版本，内容摘要变化会使旧审核失效，并有幂等与审计处理。误区定义包含结构化内容及条件/证据引用，只有已审核且发布的 Canonical 内容进入发布包。检索/索引路径可绑定 DomainRelease 与索引任务版本，发布快照作用域内的查询解析对应索引；学生查询要求与当前 PublicationSnapshot 的 domain 绑定一致。Claim helper 给出 `supported`、`partially-supported`、`contradicted`、`unknown` 四态，并限制至多一次补检索，向补检索回调传递原作用域和快照，返回初检/补检证据及尝试记录。
- **测试与证据：** 使用分配的 PostgreSQL `psychology_learning_v1_r3_a_20261004` 和 Redis DB3（`127.0.0.1:6379/3`）运行专属后端测试；`tests/test_knowledge_domain_claims.py tests/test_domain_pack_graph.py tests/test_domain_pack_validation.py tests/test_search.py` 得到 **47 passed、2 warnings**（Starlette/FastAPI 弃用警告）。后续 Claim 参数调整后再次运行 `tests/test_knowledge_domain_claims.py`：**6 passed、2 warnings**。`ruff check --no-cache app/modules/knowledge tests/test_knowledge_domain_claims.py` 通过；`git diff --check -- server/app/modules/knowledge` 无输出。没有启动浏览器、API 服务或 Worker，也没有独立执行迁移命令；pytest 使用分配的隔离测试配置。以上是代码与自动化测试证据，不是浏览器、真实教材或生产验证。
- **共享依赖交主窗口：** 0048/0049 已含 DomainRelease/DomainReviewDecision、CourseRelease/PublicationSnapshot/RetrievalUnit 所需存储字段，A 未新增迁移。课程 Release 工作流仍需由主窗口在 `courses/**` 中选定并校验已发布 `domain_release_id`，并将同一 ID 传入实际 PublicationSnapshot 和索引任务；需同步共享 schema/API、路由注册及 OpenAPI 导出。Tutor 的 Claim 回合消费及持久化属于 R3-B/主窗口：调用本窗口 `classify_claim` / `verify_claim_with_bounded_retrieval`，并保存四态、作用域、初次/补充证据与补检索次数。不得由 A 修改这些共享文件。R3-F 依赖稳定的 Domain/CourseRelease 合同。
- **专属环境：** GO 分配为 PostgreSQL `psychology_learning_v1_r3_a_20261004`、Redis DB3、MinIO bucket `v1-r3-a`、Web/API 端口 3210/8210、CDP 9310、队列 `v1-r3-a`。本窗口测试只使用分配的 PostgreSQL 与 Redis；没有启动服务/Worker 或浏览器，因此端口仅是 GO 中分配值，不在此声称已重新验活。
- **未验收项、风险与阻塞：** 尚未完成 DomainRelease→CourseRelease→PublicationSnapshot/实际索引的端到端发布绑定；尚未完成 TutorTurn 调用与持久 Claim 证据回放；没有 OpenAPI 更新、真实教材语义评测或浏览器验收。当前 Claim 判定/补检索 helper 的工程规则测试通过不等同于教学语义有效。主窗口需完成共享合同接线并在冻结结束后整合回归；其后才能判断发布链与跨模块验收。R3-A 局部结果不代表 V1 整体完成。

### 资源复核与接续资格（2026-10-05 10:57 +08:00）

- **共同基线复核：** 连续两次运行 `scripts/r3-baseline-fingerprint.ps1`，均为 HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、509 项、指纹 `4203B758B3C39B0BBD23A61585184CD5EF2FF0359EF3A4EEDD84E64993B1F83B`。相对主窗口记录的 509 项/`32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`，当前树指纹已变化；本报告本身已更新，无法把全部变化精确归因到该报告或重建逐文件共同增量。R3-A 实际文件增量按上文精确列出。没有改动状态文档。
- **文件边界复核：** `git status --short -- server/app/modules/knowledge server/tests/test_search.py server/tests/test_domain_pack_graph.py server/tests/test_domain_pack_validation.py server/tests/test_knowledge_domain_claims.py` 仅列出本报告所述 knowledge 与专测文件；没有发现本窗口排他范围与其他窗口报告的目录冲突。保留 GO 前已有的 `test_search.py`、`test_domain_pack_graph.py`、`test_domain_pack_validation.py` 变化。
- **隔离资源只读现场：** 使用应用配置建立只读 DB 连接并查询数据库名、`alembic_version` 与 `public` 表数：数据库 `psychology_learning_v1_r3_a_20261004` 可连，当前 revision `0049`，73 张 base table（含 `alembic_version`）；Redis DB3 `PING=True`、`DBSIZE=0`；MinIO `v1-r3-a` bucket 存在。`Get-NetTCPConnection -State Listen` 检查 3210、8210、9310 均无监听。此前 GO 记录的 DB revision 为 0048；当前已由主窗口共享工作树推进到 0049，记录此变化，不在本轮执行迁移或写库测试。没有使用预览库或其他窗口资源。
- **接续标记：** `HANDOFF=COMPLETE; RESUMED=2026-10-05 10:57 +08:00`。以上只满足主窗口交接广播并确认恢复原受限 GO；若继续工作仍限于 knowledge 与对应专测。共享 CourseRelease/PublicationSnapshot 接线和 Tutor Claim 消费继续由主窗口/R3-B 负责；本窗口不越界补改。

## R3-A 后续工作增量（2026-10-05 12:09 +08:00）

- **本轮改动：** `server/app/modules/knowledge/domain.py` 将补检索门槛改为完整 retrieval scope 与 required scope 严格相等，并深拷贝 scope，避免回调修改嵌套版本列表后污染审计快照；`server/tests/test_knowledge_domain_claims.py` 增加 scope 多字段不完整时不检索、嵌套快照隔离、补检索仍无证据时显式拒答、四态合同外 evaluator 状态拒绝，以及未审核 DomainRelease 不得用于 `/knowledge/search` 的负例。没有改共享 Courses/Tutor/models/迁移/fixture/OpenAPI/根路由。
- **最新测试：** 按 A 分配的 PostgreSQL `psychology_learning_v1_r3_a_20261004` 和 Redis DB3 执行：`tests/test_knowledge_domain_claims.py tests/test_domain_pack_graph.py tests/test_domain_pack_validation.py tests/test_search.py`，结果 **50 passed、2 warnings，160.60 秒**。`ruff check --no-cache app/modules/knowledge tests/test_knowledge_domain_claims.py` 最终通过；初次静态检查发现并已修复 `domain.py` 的 import 排序。`git diff --check -- server/app/modules/knowledge server/tests/test_search.py` 无输出。未启动 API/Web/Worker 或浏览器。
- **给主窗口的绑定合同样例：** CourseRelease 发布前在服务事务中，以 `course_id + domain_release_id + status='published'` 查询并锁定 DomainRelease；找不到或课程不符时 fail closed。将同一个 `DomainRelease.id` 固定在 `CourseRelease.domain_release_id`，发布中的 Domain Pack 内容应与该 DomainRelease 的 manifest 相符；版本摘要从不可变的 `DomainRelease.pack_sha256` 读取，不复制成可漂移的第二事实。对应每个教材版本发索引任务时传 `POST /api/v1/material-versions/{version_id}/embed?domain_release_id={id}`，其 Job payload 保存 `material_version_id/domain_release_id`，索引 RetrievalUnit 保存相同 `domain_release_id`，`build_version` 含 `job.id`。创建 PublicationSnapshot 时将同一 ID 与该快照实际采用的 `material_version_id`、`index_job_id`、`embedding_version` 一起写入；CourseReleaseAssignment/学生检索从固定的 CourseRelease 读取该 ID，并将其传给 `/api/v1/knowledge/search` 的 `domain_release_id`。查询侧用 `PublicationSnapshot.domain_release_id` 匹配并使用同一快照的 `index_job_id`，不得从“最新可用索引”替代。

```python
domain_release = await db.scalar(
    select(DomainRelease)
    .where(
        DomainRelease.id == release.domain_release_id,
        DomainRelease.course_id == release.course_id,
        DomainRelease.status == "published",
    )
    .with_for_update()
)
if domain_release is None:
    raise ApiError(409, "RELEASE_DOMAIN_SNAPSHOT_INVALID", "DomainRelease 未发布或课程不匹配")
# CourseRelease、Job.payload、PublicationSnapshot 必须沿用这个 domain_release.id。
```

- **Claim helper 使用合同：** `classify_claim(...)` 负责四态初判；`contradicted` 仅在调用方确认反证与对象、命题极性和条件范围一致时设置 `counterevidence_scope_matches=True`。`verify_claim_with_bounded_retrieval(...)` 的 `retrieval_scope` 与 `required_scope` 必须是完全相同的快照，至少覆盖 `user_id`、`organization_id`、`course_id`、固定 `domain_release_id`、`publication_snapshot_id`、教材版本集合、`index_job_id` 与 `embedding_version`。`retrieve_once(scope_snapshot)` 最多调用一次；结果包含四态、`initial_evidence`、`supplemental_evidence`、`supplemental_retrieval_attempts` 和 scope。返回 unknown 时按 `refusal_reason` 降级/拒答；调用方负责把结果持久化到 TutorTurn，A 不改 Tutor。
- **基线与并行变动：** HEAD 仍为 `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。两次紧邻 fingerprint 读取分别为 521 项/`1B09C80501BEBFF1B1B38286E078960A389726ED7B4F8E25D0E081752DCE969A` 与 521 项/`053F4A65105229F2C060FB5F8671EF9E57CDE4F8ABF1A920DE1600A7DC18076A`，说明共享树当时仍在变化；同时读到主窗口正在改 `courses/router.py` 做 DomainRelease 绑定校验。A 的文件归属检查未发现 knowledge 范围冲突；不把不稳定的全树 fingerprint 伪报为稳定共同基线。
- **尚未验证：** 尚未在真实发布数据上验证 CourseRelease→PublicationSnapshot→索引任务端到端绑定，也未验证学生 assignment 固定的 Release ID 如何注入检索请求；TutorTurn 持久化、浏览器链路和真实教材语义仍由主窗口/R3-B及获准材料验证。当前新增测试验证 helper 与 draft-release fail-closed 规则，不宣称跨模块集成已通过。

### 最终复核（2026-10-05 12:11 +08:00）

- 在上述 scope 完整相等合同的最终代码上重跑 `tests/test_knowledge_domain_claims.py`：**9 passed、2 warnings，8.41 秒**；最终 `ruff check --no-cache app/modules/knowledge tests/test_knowledge_domain_claims.py` 通过。前述 4 文件套件 **50 passed** 是本轮同一逻辑实现的完整定向回归；此前历史 **47+6** 仅记录旧快照，不作为本轮证据或额外计数。
- 主窗口当前 `courses/router.py` 已出现同课程、已发布 DomainRelease 校验及 manifest 一致性门禁；本窗口只读核对后在上方提供索引/PublicationSnapshot 后续绑定样例，没有改该共享文件。仍待主窗口接线与跨模块测试。

## R3-A 新广播响应字段合同与交接时间（2026-10-05 13:52 +08:00）

- **函数签名：** `classify_claim(*, supported_subclaims: list[str] | None = None, unsupported_subclaims: list[str] | None = None, contradicted_subclaims: list[str] | None = None, counterevidence_scope_matches: bool = False) -> dict[str, Any]`；`verify_claim_with_bounded_retrieval(*, claim: str, initial_evidence: list[Any], evaluate: Callable[[str, list[Any]], dict[str, Any]], retrieve_once: Callable[[dict[str, Any]], Awaitable[list[Any]]], retrieval_scope: dict[str, Any], required_scope: dict[str, Any]) -> dict[str, Any]`。
- **返回字段：** `classify_claim` 始终返回 `status`、`supported_subclaims`、`unsupported_subclaims`、`contradicted_subclaims`、`evidence_ids`、`supplemental_retrieval_attempts`。`verify_claim_with_bounded_retrieval` 保留 evaluator 的结果字段，并保证返回 `status`、`initial_evidence`、`supplemental_evidence`、`supplemental_retrieval_attempts`（只可能为 0/1）、`scope`；可选 `refusal_reason` 为 `retrieval_scope_changed` 或 `insufficient_evidence`。状态值仅 `supported`、`partially-supported`、`contradicted`、`unknown`；未知/不完整证据不会升级为 supported，反证必须同一完整 Scope。
- **Scope 调用样例：** 由调用方从已授权、不可变的检索上下文构造同一快照，并将其同时交给两参数；多一个、少一个或任意值变化均拒绝补检索：

```python
scope = {
    "user_id": user_id,
    "organization_id": organization_id,
    "course_id": course_id,
    "domain_release_id": course_release.domain_release_id,
    "publication_snapshot_id": snapshot.id,
    "material_version_ids": [snapshot.material_version_id],
    "index_job_id": snapshot.index_job_id,
    "embedding_version": snapshot.embedding_version,
}
result = await verify_claim_with_bounded_retrieval(
    claim=claim,
    initial_evidence=initial_evidence,
    evaluate=evaluate_claim,
    retrieve_once=retrieve_with_scope,
    retrieval_scope=scope,
    required_scope=dict(scope),
)
```

- **负例与证据：** 本轮新增 scope 多字段不完整即不补检索、补检索回调不能改写原始嵌套版本列表、无补充证据仍拒答、未知 Claim 状态拒绝、draft DomainRelease 搜索返回 `DOMAIN_RELEASE_NOT_FOUND`。本轮 4 文件套件 **50 passed**；最终 Claim 专测 **9 passed**；Ruff 通过。未重复使用旧快照的 47+6 作为当前结果。
- **交接时间：** `HANDOFF=COMPLETE; RESUMED=2026-10-05 13:52 +08:00`，替代先前 10:57 的恢复记录时间。继续仅限 `knowledge/**`、A 专测和本报告；共享 CourseRelease/PublicationSnapshot、Tutor 持久接线及真实发布端到端验证仍由主窗口/R3-B负责。

## DomainRelease 索引隔离回归与当前交接（2026-10-05 14:05 +08:00）

- **新增知识检索回归：** `test_domain_release_search_uses_only_its_bound_index_job` 使用同课程、同教材版本的两个 DomainRelease，给其中一个构建独立索引并将该 job 绑定到 PublicationSnapshot。教师检索返回该 release 的 index job 与 RetrievalUnit；学生检索使用 PublicationSnapshot 中相同的 `index_job_id` 且不返回教师分数；另一个没有绑定快照/索引的 DomainRelease 返回空结果，证明不混用另一个版本的索引。测试直接构造已发布 DomainRelease 和 PublicationSnapshot，验证 knowledge 搜索边界，不替代实际 CourseRelease 发布流程验收。
- **最新验证：** 四文件 knowledge 套件 `tests/test_knowledge_domain_claims.py tests/test_domain_pack_graph.py tests/test_domain_pack_validation.py tests/test_search.py`：**51 passed、2 warnings，130.99 秒**；单独该索引隔离用例 **1 passed、2 warnings，8.43 秒**；Claim 专测最终版为 **9 passed、2 warnings，8.41 秒**。最新 Ruff 检查通过；`git diff --check -- server/app/modules/knowledge server/tests/test_search.py` 无输出。
- **当前交接：** `HANDOFF=COMPLETE; RESUMED=2026-10-05 14:05 +08:00`，替代先前 13:52 时间。实际 CourseRelease 选择与发布、真实材料 PublicationSnapshot 创建、TutorTurn 证据持久化仍由主窗口/R3-B 接线；A 仅负责知识侧 DomainRelease 与索引/搜索隔离契约及 A 专测。

## R3-A publication_snapshots 响应与权限过滤（2026-10-05 15:17 +08:00）

- **实现：** `/api/v1/knowledge/search` 在 `domain_release` 对象内增加 `publication_snapshots`。每项严格包含 `material_id`、`material_version_id`、`publication_snapshot_id`、`index_job_id`、`embedding_version`、`domain_release_id` 六字段，数据只来自同课程、指定 DomainRelease 的真实 PublicationSnapshot 行。Teacher/assistant 可在知识预览中使用成功 Job 的索引，但成功 Job 没有对应 PublicationSnapshot 时不会被伪造进此数组；原 `index_job_ids` 仅为索引选择信息，不替代快照身份。
- **学生过滤：** 查询只保留 `Material.status='active'`、`visibility='published'`、版本仍为 `current_version_id` 且 `superseded_at IS NULL` 的快照，并继续要求用户具备该课程 Scope。历史快照仅能出现在具备课程 staff 权限的结果中。
- **专测覆盖：** 扩展 `test_domain_release_search_uses_only_its_bound_index_job`：同课程两个 DomainRelease 分别有索引；实际快照绑定其中一者；教师可看到指定 Release 的当前与历史真实快照；学生仅看到当前未撤销快照；另一个 Release 即使有成功索引 Job 但没有 PublicationSnapshot，staff 的 `publication_snapshots` 仍为空、student 既看不到快照也无命中；跨课程 Release ID 返回 404。测试通过 ORM 工程 fixture 构造快照，验证知识搜索响应与过滤边界，不替代 CourseRelease/材料发布 API 的真实端到端联调。
- **验证：** `tests/test_knowledge_domain_claims.py tests/test_domain_pack_graph.py tests/test_domain_pack_validation.py tests/test_search.py`：**51 passed、2 warnings，141.49 秒**。`ruff check --no-cache app/modules/knowledge tests/test_search.py tests/test_knowledge_domain_claims.py` 通过；`git diff --check -- server/app/modules/knowledge server/tests/test_search.py` 无输出。
- **接续状态：** `HANDOFF=COMPLETE; RESUMED=2026-10-05 15:17 +08:00`。未改 shared models/Alembic/CourseRelease/materials/Tutor/路由聚合/OpenAPI/fixture。历史 CourseReleaseAssignment 按固定运行版本回放、实际材料发布生成 DomainRelease 绑定 PublicationSnapshot、TutorTurn 持久 Claim 证据仍由主窗口/R3-B 完成与验收；R3-A 局部工程测试不代表 V1 完成。
