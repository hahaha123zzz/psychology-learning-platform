# V1 状态机目录

状态机是后端权威约束，前端只展示服务端允许的动作。任何未列出的转移都必须拒绝并返回结构化错误。

## 1. TeachingTask

```text
READY → DIAGNOSE → TEACH → CHECK → VERIFY → SUMMARY → COMPLETED
                         └→ REMEDIATE ────────┘
                 任意可暂停节点 → PAUSED → 原节点
```

| 当前状态 | 允许动作 | 成功转移 | 禁止 |
|---|---|---|---|
| READY | `start` | DIAGNOSE | 直接写掌握或记忆 |
| DIAGNOSE | `respond_task` | TEACH/CHECK | 无学生响应自动推进 |
| TEACH | EXPLAIN/EXAMPLE/HINT | CHECK | 输出未注册 Block |
| CHECK | SUBMIT | VERIFY 或 REMEDIATE | 一回合触发多个教学动作 |
| REMEDIATE | 补救、换解释、micro-check | CHECK | 一次错误确认稳定误区 |
| VERIFY | 独立验证/迁移 | SUMMARY 或 REMEDIATE | 直接 `score → mastered` |
| PAUSED | `resume` | 暂停前状态 | 创建新 Episode 替换原任务 |
| SUMMARY | `complete` | COMPLETED | 把活动完成当成掌握 |

SSE 半回合只保存在可恢复的 turn 状态；未完成流不得写长期 Memory/LearningEvidence。

## 2. Progress Decision 与 Learner Model

`READY`：前置和证据足够；`READY_WITH_REVIEW`：可以继续但安排复习；`REMEDIATE_FIRST`：前置问题阻塞；`INSUFFICIENT_EVIDENCE`：证据不足，不能误判薄弱。

KnowledgeState 与 MisconceptionState 分离：

```text
Knowledge: evidence_insufficient | learning | needs_review | mastered
Misconception: candidate | confirmed | improving | resolved
```

单次高分不能升级 `mastered`；单次错误不能升级 `confirmed`。状态必须保留 `algorithm_version`、来源 Evidence refs 和重算依据。

## 3. Formal Assessment / Attempt

```text
NOT_OPEN → AVAILABLE → PRECHECK → IN_PROGRESS
                                  ↓
                       REVIEWING_ATTEMPT → SUBMITTING → SUBMITTED
                                                         ↓
                                               PENDING_GRADING → GRADED
                                                                    ↓
                                                              RESULT_RELEASED
```

异常状态：`CONNECTION_INTERRUPTED`、`RECOVERING`、`TIME_EXPIRED`、`INVALIDATED`。服务端时间锁定截止；过期 Attempt 不能保存或提交。提交必须幂等，重复键回放同一结果。

评分关系固定为：

```text
AIGradingSuggestion ≠ TeacherGradingDecision ≠ ScoreRecord
```

## 4. Release

```text
DRAFT → VALIDATING → READY_TO_PUBLISH → PUBLISHED → DEPRECATED
             └→ ERROR
```

- `ERROR`：阻断发布。
- `WARNING`：要求有理由的人工确认。
- `INFO`：提示，不阻断。
- `PUBLISHED`：不可原地编辑；变更创建新版本。
- 运行中的 Activity/Assessment 固定原 Release，新任务才使用新 Release。

发布必须依次完成：选择内容 → 自动检查 → Impact Preview → Diff → Review → Publish。

## 5. Mini Lab

```text
INTRO → PREDICT → RUN → INSPECT_DATA → EXPLAIN → SUMMARY
```

中断、浏览器离开、版本不一致和数据校验失败进入 `INVALIDATED` 或可恢复的 `RECOVERING`，由服务端判定是否允许继续。`TrialData → DerivedMeasure` 与 `Prediction/Explanation/Transfer → LearningEvidence` 分离。

## 6. Evidence / Job / Deletion

| 对象 | 状态 |
|---|---|
| Evidence ticket | ACTIVE → EXPIRED/REVOKED |
| Compiler/Index job | QUEUED → RUNNING → SUCCEEDED；RUNNING → FAILED/STALE → REQUEUED |
| Privacy deletion | REQUESTED → VERIFYING → RUNNING → COMPLETED；失败为 FAILED 并保留原因 |
| Activity | SCHEDULED → AVAILABLE → IN_PROGRESS → PAUSED/COMPLETED/CANCELLED |

任务重试必须幂等；失败保留阶段、错误、影响和 Last Known Good；删除完成必须有可查询的执行证据，不能用 hidden 字段伪装。
