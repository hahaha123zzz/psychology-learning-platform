# V1 API 与状态契约

## 1. 公共响应

成功响应固定为 `{data, meta}`，`meta` 至少含 `request_id`、`server_time`；列表使用稳定排序和游标。失败响应固定为 `{error:{code,message,details,retryable},request_id}`。资源无权访问统一 404；已识别但策略禁止使用 403；版本/并发冲突 409；验证失败 422。

所有命令显式列出：权限 Scope、资源版本、幂等键、事务副作用、事件类型、可重试性。OpenAPI 由 FastAPI 生成，禁止手工编辑快照。

## 2. 读取 Projection

| Projection | 最小字段 |
| --- | --- |
| StudentHomeProjection | `current_task`、`next_actions[0..2]`、`attention_item[0..1]`、`recent_activity` |
| LearningWorkspaceView | task/version、stream blocks、allowed_actions、context_refs、completion |
| EvidencePointerView | 不可变教材版本、页/对象/retrieval unit、bbox 坐标空间、excerpt SHA-256；访问权限不固化，每次读取重新鉴权 |
| GrowthOverviewView | focus、state summary、attention、domain skills、milestones、explainability refs |
| TeacherOverviewView | course/class context、attention、teaching、interventions、freshness |
| TeacherAnalyticsView | time/sample definition、knowledge/domain states、misconceptions、review、support groups |
| AssessmentShellView | frozen release、availability、server clock、policy、question order、attempt version |

页面不得通过十几个底层接口自行拼 Projection。Projection 失败时局部降级，并返回 freshness/error 状态；不得用静态样例冒充数据。

## 3. 状态机要点

### TeachingTask

```text
READY → DIAGNOSE → TEACH/CHECK → REMEDIATE? → VERIFY → SUMMARY → COMPLETED
                         ↘ PAUSED ↗
```

每个学生响应最多触发一个教学动作。未收到响应不得自动推进；刷新恢复同一个 task/version；SSE 半回合不写长期 Memory/Evidence。

### Knowledge/Misconception

`evidence_insufficient | learning | needs_review | mastered` 与 `candidate | confirmed | improving | resolved` 分开返回。前端显示中文教学语言，不显示 AI confidence 或风险分数。

### Assessment

可用性 `NOT_OPEN | AVAILABLE | CLOSED`、作答 `PRECHECK | IN_PROGRESS | REVIEWING_ATTEMPT | SUBMITTING | SUBMITTED`、评分 `PENDING_GRADING | GRADED`、结果 `RESULT_RELEASED` 分开建模。服务端以 server time 锁定截止时间；保存和提交带 attempt/answer version。

### Release

`DRAFT → VALIDATING → READY_TO_PUBLISH → PUBLISHED → DEPRECATED`。ERROR 阻断，WARNING 要求带理由的人工确认，INFO 只提示。Published 不原地编辑。

### CourseRelease Domain Pack JSON

Domain Pack 使用 `CourseRelease.manifest.domain_pack`，字段由课程服务校验；未知字段拒绝，不能静默保存或执行。

| 字段 | 结构与约束 |
| --- | --- |
| `chapters` | 可选稳定 ID 字符串数组；ID 不得重复。 |
| `knowledge_points` | 可选对象数组，必填 `key`、`title`；可选 `evidence_binding_keys`。 |
| `relations` | 可选对象数组，必填 `source_key`、`target_key`、`relation_type`；可选 `key`、`evidence_binding_keys`。省略 `key` 时以有序端点和关系类型生成稳定身份。 |
| `experiments` | ExperimentSchema 对象数组，必填 `key`、`title`；可选 `research_question`、`hypothesis`、`iv`、`dv`、`operationalization`、`controls`、`confounds`、`design`、`procedure`、`prediction`、`result_pattern`、`interpretation`、`limitations`、`knowledge_point_keys`、`evidence_binding_keys`、`textbook_evidence`。文本字段可省略/留空且最多 4000 字符；`controls`、`confounds` 为最多 50 项、单项最多 1000 字符的字符串数组；`textbook_evidence` 为 EvidenceBinding key 数组，与 `evidence_binding_keys` 兼容等价，同时填写时必须一致。 |
| `misconceptions` | MisconceptionDefinition 对象数组，必填 `key`、`title`；可选 `knowledge_point_keys`、`evidence_binding_keys`。 |
| `evidence_bindings` | 对象数组，必填 `key`、`object_key`、`material_id`、`material_version_id`、`source_object_id`。来源 ID 指向稳定 `KnowledgeObject`，不使用短期 `EvidenceTicket`。 |

所有 Domain Object 共用唯一 `key` 命名空间，类型由所属字段确定。ExperimentSchema 和 MisconceptionDefinition 的 `knowledge_point_keys` 必须指向已声明 KnowledgePoint；ExperimentSchema 只接受总体设计明确列出的研究推理字段，未提供字段保持空，不能自动推断为课程事实；`textbook_evidence` 通过 EvidenceBinding key 关联教材来源。每个 EvidenceBinding 的 `object_key` 必须指向已声明对象，且其 ID 不得重复。当前唯一支持的 Relation 是 `prerequisite`，方向为 KnowledgePoint → KnowledgePoint，且这些边必须构成有向无环图；未纳入词表的关系类型拒绝保存。重复边、自引用、环和悬空端点均返回带路径的 422。

草稿可以暂不绑定 Evidence；发布前每个 KnowledgePoint、ExperimentSchema、MisconceptionDefinition 和 Relation 至少需要一个指向自身的 `evidence_binding_keys`。发布校验会复核 EvidenceBinding 的教材已包含在 Release 中、教材版本等于当前 `PublicationSnapshot`，且 `source_object_id` 对应同一教材版本内已解析的 KnowledgeObject。当前服务不生成 AI Domain 候选；若以后增加，候选不得直接进入此 Canonical Pack，必须另建明确的审核状态和发布门禁。

## 4. 关键命令

| 命令 | 幂等/并发 | 禁止 |
| --- | --- | --- |
| `respond_task` | `client_turn_id` + task version | 直接写 Mastery/Memory |
| `merge_branch` | merge key；重复回放返回原结果 | 未确认内容合并主线 |
| `save_answer` | attempt answer version；冲突 409 | 接受已锁定/过期答案 |
| `submit_attempt` | Idempotency-Key + submission lock | 浏览器时间裁决 |
| `publish_release` | release version + audit | 修改已发布内容 |
| `grade_submission` | grading decision version | AI 建议直接变正式分数 |
| `request_deletion` | caller-generated ULID + caller-generated status credential | 未完成却返回 completed；仅凭可枚举 request id 重签 bearer 凭证 |

隐私删除持久工作单状态为 `queued → running → completed_with_retention`，处理失败进入可重试 `failed`；账号与认证会话在受理事务内立即停用，只有 Worker 的个人数据清除事务提交后才可进入 completed。客户端必须在发送前生成并安全保存 ULID 与 256-bit 查询凭证；服务端只保存凭证哈希。响应丢失后，凭此二值可无登录核验，`/privacy/deletion-status/retry` 允许安全重派发 queued/failed 工作单。错误统一不回显凭证、邮箱、Prompt 或数据库/Redis/broker 细节。

## 5. Streaming

SSE 可传解释文本和教学事件；Question、TeachingAsset、Table、正式测评对象必须以结构化、验证后 block 传输。断线后客户端通过 turn id 恢复；未完成流不显示为已确认结论。
