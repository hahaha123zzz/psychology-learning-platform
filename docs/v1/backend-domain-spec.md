# V1 后端领域规格草案

## 1. 依赖方向

```text
identity/course_runtime → domain_knowledge → retrieval_evidence
identity/course_runtime → learning_record → learner_model → analytics
domain_knowledge/pedagogy → teaching_runtime
assessment → learning_record → review/learner_model
course_design → release → course_runtime
admin/audit 横切所有高后果命令，但不拥有教学正文读取权
```

模块通过 service/contract 交互。禁止跨模块直接拼接内部表并写入另一个领域的权威状态。

## 2. 权威对象和所有权

| 领域 | 权威对象 | 允许写入者 | 关键不变量 |
| --- | --- | --- | --- |
| Identity | User、RoleAssignment、ResourceScope | 身份/授权服务 | 用户状态、角色和资源 Scope 分开；Admin 不隐式获得 Teacher Scope |
| Course Runtime | Course、Class、Membership、CourseReleaseAssignment | 课程服务/Publisher | 每个运行任务固定 course/class/release；移除成员立即影响查询 |
| Domain Knowledge | TextbookRelease、TextbookObject、KnowledgePoint、Relation、ExperimentSchema、MisconceptionDefinition | Compiler/Designer | Canonical Object 只读；候选必须带 Evidence；已发布不可原地改 |
| Retrieval/Evidence | RetrievalUnit、IndexBuild、EvidencePackage、EvidencePointer、ClaimCheck | 检索/证据服务 | 召回前过滤；Pointer 绑定版本/页/对象/bbox；每次打开重新鉴权 |
| Pedagogy | TeachingStrategy、HintPathway、ActivityTemplate、TeachingAssetVersion | Designer/Publisher | Asset 使用白名单 Contract，必须有 fallback |
| Learning Record | LearningEvent、AttemptEvent、LearningEvidence、Qualification | 业务事实服务 | 只追加；原始事实不能被推断覆盖；客户端不能直接提交评分/状态 |
| Learner Model | KnowledgeState、MisconceptionState、DomainSkillState、ReviewState | 确定性重算服务 | 记录 evidence refs、algorithm_version、confidence；一次事件不能强升级 |
| Memory | MemoryItem、EpisodeSummary、MemoryConflict | Memory 服务/人工确认 | 与 Mastery 分离；跨课程隔离；删除/匿名化有可验证结果 |
| Teaching Runtime | CurrentLearningTask、TeachingSession、TeachingTurn、ActivityRun、Intervention | Runtime/教师命令 | 单回合单动作；活动完成不等于掌握；运行对象固定 Release |
| Assessment | Question、QuestionVersion、RubricVersion、AssessmentRelease、Attempt、ScoreRecord | Designer/Teacher/评分服务 | AI 候选先 Draft；正式发布冻结；建议不等于成绩 |
| Admin/Audit | JobProjection、AuditLog、RecoveryRecord | 管理服务 | 只能操作授权治理命令；高风险动作追加审计 |

## 3. 核心写入链

```text
AttemptSubmitted
  → deterministic scoring / teacher grading
  → LearningEvent + Qualification
  → LearningEvidence
  → LearnerModel recompute
  → ReviewState / Planner candidate
  → Teacher analytics projection
```

事务事实写入 PostgreSQL。需要异步处理的副作用先写同事务 Outbox；消费者使用 `event_id` ledger 幂等。Redis 只做缓存/队列，不是权威事实来源。

## 4. 版本关系

`CourseRelease` 固定引用 `DomainRelease`、`PedagogyPackRelease` 和 `AssessmentPackRelease`。CurrentLearningTask、ActivityRun、Attempt、EvidencePackage 都保存创建时的 release snapshot。新版本发布只影响新任务；已运行任务继续使用旧版本，撤回后访问仍需重新鉴权。

## 5. 失败和回退

构建、索引、Projection 或模型失败时保留 Last Known Good。命令返回明确的 `retryable`、阶段、影响和恢复动作。数据库迁移采用 expand → backfill → verify → switch → contract；不修改历史迁移，不用 downgrade 作为数据回退方案。
