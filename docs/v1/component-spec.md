# V1 前端组件 Contract

## 1. 分层

```text
Design Tokens → Primitive UI → Domain Components → Page Patterns
```

页面只组合领域组件。未知 Block 安全降级为可读的“暂不支持此内容”，不得执行任意 HTML/JSX。

## 2. 基础约束

| 项目 | Contract |
| --- | --- |
| 状态颜色 | 必须同时有文字或图标；支持 `prefers-reduced-motion` |
| 交互 | Card/Row/Citation/Asset 使用语义元素；键盘 Enter/Space 可完成主要动作 |
| Drawer | Evidence、Branch、Task Detail 共用 ContextDrawer；不嵌套 Drawer；移动端 full-height Sheet |
| 主操作 | 每个局部区域最多一个 Primary；危险动作需确认和结果反馈 |
| 数据 | Server Truth 不放入仅前端 local state；query key 必须包含 course/class/task/release scope |
| 加载 | Inline/Skeleton/Progress 按时长选择；不用“AI 正在思考”覆盖所有等待 |
| 空态 | 解释为空的原因，并给出下一步；不得放静态假指标 |
| 错误 | 局部降级优先；展示 request_id/可重试动作，不吞掉 409 |

## 3. Learning Block Registry

| Block | 必需输入 | 允许动作 | 失败降级 |
| --- | --- | --- | --- |
| TutorExplanation | block id、text、claim checks、evidence refs | OPEN_EVIDENCE、ASK_FOLLOWUP | 只显示已验证文本/依据不足提示 |
| Question | question version、prompt、dimension、response contract | SUBMIT、REQUEST_HINT | 恢复上一版输入；不接受未知题型 |
| Hint | level、remaining budget、support reason | REVEAL_NEXT | 预算用尽时转人工/教材入口 |
| WorkedExample | example version、evidence refs | COMPARE、TRY_SIMILAR | 静态文本 |
| TeachingAsset | published asset version、template、fallback | 白名单 SHOW/HIGHLIGHT/REVEAL/FOCUS/COMPARE/PLAY/PAUSE/RESET | Interactive→Static→Text |
| Feedback | qualification summary、next action | CONTINUE、OPEN_EVIDENCE | 只显示资格结果，不直写掌握 |
| Transition | next task/action、reason | START、REVIEW_LATER | 保留当前任务 |
| TaskCompletion | completion criteria、evidence summary | NEXT、REVIEW | 明确“活动完成”与“学习状态”分开 |

## 4. 核心页面 Contract

Student Home 在首屏只出现一个当前任务、最多两个下一步和一个关注项。Learning Workspace 固定 `Learning Header + Task Bar + Rail + Stream + Context Panel`。Teacher Overview 固定 `Primary Problem → Attention → Current Teaching → Intervention → Operational`。Formal Assessment 使用独立 layout；Mini Lab 运行期间隐藏 Tutor、Evidence、Branch。

## 5. 可观察性

前端事件（如 `learning_task_started`、`evidence_opened`、`branch_merged`、`assessment_submitted`）只用于产品可靠性和审计辅助。它们必须经后端 Qualification 后才可能成为 LearningEvidence。
