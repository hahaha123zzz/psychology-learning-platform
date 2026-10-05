# V1 设计验收矩阵

本矩阵把设计文档中的硬边界转换为可执行验收。没有对应日志、接口响应、数据库记录、截图或浏览器测试的项，不得标记通过。

## 1. 角色与权限

| 编号 | 场景 | 通过条件 | 证据 |
|---|---|---|---|
| AUTH-01 | Student 访问自己的课程、任务、成长 | 返回本人 Scope 内数据 | API + E2E |
| AUTH-02 | Teacher 访问已分配 Course/Class | 只能读写授权课程 | API 权限矩阵 |
| AUTH-03 | Designer 编辑 Draft | 可改 Draft，不能发布 | API 403/审计 |
| AUTH-04 | Publisher 发布 Release | 通过 Gate、Diff、Impact Review 后可发布 | Release 审计 |
| AUTH-05 | 无课程 Scope 的 Admin 读教材/学情/私聊 | 统一 404，不返回正文 | API 回归 |
| AUTH-06 | 移除成员或调班 | 下一次读取立即失去旧 Scope | 权限缓存/E2E |
| AUTH-07 | AI 调用 | AI 无独立权限，继承当前用户和活动 Policy | 服务日志 + API |

## 2. 教材与 Evidence

| 编号 | 场景 | 通过条件 |
|---|---|---|
| EVD-01 | 检索 | 权限/版本过滤发生在召回和排序之前 |
| EVD-02 | 教材外问题 | 按拒答门槛返回不足证据，不编造结论 |
| EVD-03 | 引用点击 | 打开生成时版本、页、对象和 bbox |
| EVD-04 | 撤回/撤权 | 旧票据不能绕过重新鉴权 |
| EVD-05 | Evidence Closure | 图、表、公式或相邻对象未建成时明确降级，不伪造对象 |
| EVD-06 | 教师内容入口 | 普通教师无上传、解析、索引、发布入口，直接 API 也受限 |

## 3. 学习与教学

| 编号 | 场景 | 通过条件 |
|---|---|---|
| LEARN-01 | 刷新任务页 | 恢复相同 task/version，不创建新 Episode |
| LEARN-02 | 单回合 | 一次学生响应最多触发一个 Teaching Action |
| LEARN-03 | 半回合断线 | 不写长期 Memory/Evidence；可按 turn 恢复 |
| LEARN-04 | 一次错误/高分 | 不直接确认 misconception/mastery |
| LEARN-05 | Branch | 未确认内容不进入主线；重复 merge 幂等回放 |
| LEARN-06 | 删除 | 停用会话、删除/匿名化范围、索引和缓存结果可查询 |

## 4. 正式测评与实验

| 编号 | 场景 | 通过条件 |
|---|---|---|
| ASS-01 | Draft/未开放测验发现 | 不泄露题目；草稿或无权统一 404 |
| ASS-02 | Attempt 截止 | 服务端时间锁定，浏览器时钟不能延长 |
| ASS-03 | 自动保存冲突 | answer version 不一致返回 409，不覆盖他人版本 |
| ASS-04 | 重复提交 | 同一 Idempotency-Key 返回同一结果，不重复评分/证据 |
| ASS-05 | AI Policy | `DISABLED/TECHNICAL_ONLY/DIRECTION_ONLY` 在后端强制 |
| ASS-06 | 主观题评分 | AI 建议、教师决定和 ScoreRecord 分离；覆盖有理由和审计 |
| LAB-01 | Mini Lab 中断 | 按规则恢复或作废；不把反应时直接当学习结论 |
| LAB-02 | 实验解释 | Prediction/Explanation/Transfer 才进入 LearningEvidence |

## 5. 发布、可靠性与前端体验

| 编号 | 场景 | 通过条件 |
|---|---|---|
| REL-01 | Release 发布 | Domain/Pedagogy/Assessment 版本冻结，Published 不可原地修改 |
| REL-02 | Gate | ERROR 阻断；WARNING 有理由可继续；INFO 只提示 |
| REL-03 | 失败构建 | 稳定版本保持可运行，失败任务可恢复/重试 |
| UI-01 | Student Home | 5 秒内识别一个当前任务和不超过两个下一步 |
| UI-02 | Teacher Overview | 30 秒内知道问题、原因、动作和此前干预效果 |
| UI-03 | 状态语言 | 不以颜色单独表达；不显示伪精确 Mastery/Confidence |
| UI-04 | 响应式 | 360px、平板、桌面核心路径可用；Drawer 焦点可恢复 |
| UI-05 | 无障碍 | 键盘、focus ring、44px 触控目标、reduced-motion 均通过 |
| UI-06 | 错误恢复 | 局部降级，展示 request_id 和可执行重试；不吞 409 |

## 6. 指标门槛

- 权限泄漏：`0`。
- 外部教材问题拒答：按固定语料达到目标准确率，失败必须可复现。
- 引用：release/page/object/bbox 链路可追溯；不支持时明确降级。
- 任务：重复事件、重复提交、重复消费不产生重复业务结果。
- 性能、容量、生产部署和真实班级验收不属于当前 V1 本地设计完成门槛，必须单独标记为未来阶段。
