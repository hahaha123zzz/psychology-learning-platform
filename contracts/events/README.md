# 内部事件契约

首期采用PostgreSQL Outbox，不引入Kafka。事件统一包含：

- `event_id`
- `event_type`
- `event_version`
- `occurred_at`
- `producer`
- `trace_id`
- `payload`

消费者必须按`event_id`幂等处理。

课程治理 Outbox 的成员与班级事件由课程 API 与行政治理 API 写入同一业务事务；payload 只包含资源 ID、角色/操作者等必要元数据，不包含学生作答、学习记忆、教材正文或理由文本：

| `event_type` | `event_version` | `producer` | 最小 payload |
|---|---:|---|---|
| `course.class_created` | 1 | `courses.router` 或 `courses.admin_governance` | `class_id`, `course_id`, `created_by` |
| `course.member_added` | 1 | `courses.admin_governance` | `course_id`, `user_id`, `role` |
| `course.member_removed` | 1 | `courses.admin_governance` | `course_id`, `user_id`, `member_id` |
| `course.class_member_added` | 1 | `courses.admin_governance` | `class_id`, `course_id`, `user_id` |
| `course.class_member_removed` | 1 | `courses.admin_governance` | `class_id`, `course_id`, `user_id` |

重试使用相同 `Idempotency-Key` 重放已有响应，不重复创建 Outbox 事件。移除操作为软移除；课程学生移除还会在同事务内关闭其班级成员关系，教师/助教移除会结束该课程下仍 active 的 TeacherAssignment。

