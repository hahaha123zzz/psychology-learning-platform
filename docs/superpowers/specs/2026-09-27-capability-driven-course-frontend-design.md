# 课程导向前端重设计：能力驱动规格

## 目标与范围

本规格把当前“单页工作台”渐进改造成课程导向的教师与学生界面。核心目标是让教师管理课程，让学生完成学习；浏览器页面只能呈现服务端已经实现、当前角色有权执行的能力。

本轮不实现新的教材解析、视觉检索、题目能力或业务 API；不展示 RAG、向量、模型、任务队列、对象坐标等工程术语；不为未实现能力放置灰色按钮或静态样例。

## 已确认的实施策略

采用渐进式重构而非整体替换。先创建课程级路由和共用 Shell，再迁移教师教材工作流，最后依次迁移学生学习、练习成长和教师其余模块。旧地址保留为安全跳转，直至对应的新页面经过验证。

## 信息架构

### 教师

```text
/teacher/courses                              课程列表
/teacher/courses/[courseId]                   课程概览
/teacher/courses/[courseId]/materials         教材列表与上传
/teacher/courses/[courseId]/materials/[id]    教材详情与流程
/teacher/courses/[courseId]/materials/[id]/issues  教材问题
/teacher/courses/[courseId]/questions         题库
/teacher/courses/[courseId]/assessments       测验
/teacher/courses/[courseId]/analytics         学情
/teacher/courses/[courseId]/members           成员
```

教师 Shell 固定显示“返回我的课程”、当前课程名、课程级导航和账号入口。后台任务为右上角 Drawer，只列出当前课程真实运行或失败的解析/索引任务；点击任务回到对应教材，而非做独立技术控制台。

### 学生

```text
/student/courses                              我的学习（课程列表）
/student/courses/[courseId]                   首页
/student/courses/[courseId]/learn             学习
/student/courses/[courseId]/practice          练习
/student/courses/[courseId]/growth            成长
/student/courses/[courseId]/me                我的
```

学生 Shell 只显示首页、学习、练习、成长、我的。学生不能看到后台任务、教材发布、题库、成员、教师学情或未发布资料。移动端使用底部导航；学习页的助手变为可开关抽屉。

## 组件边界

```text
CourseShell
├── CourseIdentity（课程名、返回课程列表）
├── CourseNavigation（根据角色渲染）
├── TaskDrawer（教师专用）
└── 页面内容

MaterialWorkspace
├── MaterialList
├── UploadPanel
├── MaterialDetail
│   ├── ProcessStepper
│   ├── NextActionCard
│   └── MaterialTaskSummary
└── MaterialIssues
```

公共原子组件包括 `PageHeader`、`StatusBadge`、`EmptyState`、`ErrorState`、`TaskProgress`、`ProcessStepper`、`MetricCard` 与 `EvidenceCitation`。组件不拥有业务真相：状态、下一操作、进度和错误都来自现有 API。

## 真实数据与交互映射

| 用户页面 | 已有服务端接口 | 页面行为 |
|---|---|---|
| 课程列表 | `GET /courses` | 展示真实可访问课程；空列表指向当前可执行动作 |
| 教材列表/上传 | `GET /courses/{id}/materials`、可恢复上传会话接口 | 显示真实版本状态与上传进度；中断后继续同一文件 |
| 教材详情 | `GET /material-versions/{id}/workflow` | 按服务端 `allowed_actions` 显示唯一主操作 |
| 教材问题 | `GET /material-versions/{id}/review-issues` | 只允许服务端确实支持的处理与重试操作 |
| 后台任务 | `GET /courses/{id}/material-jobs` | 轮询运行任务，展示阶段、进度、失败原因与可重试性 |
| 教师概览/学情 | `GET /courses/{id}/analytics/overview` | 聚合口径，不显示私聊或记忆正文 |
| 学生学习 | 已发布资料、`POST /knowledge/search`、SSE 问答 | 正文/检索/有据问答只面向已发布教材 |
| 练习与成长 | 测验、复习、掌握度、记忆/隐私接口 | 只展示学生本人且服务端允许的数据 |

## 教师教材体验

教材列表的用户状态仅使用：草稿、上传中、处理中、需要处理、准备发布、已发布、失败。技术阶段在文案中转译为“上传、解析、审核、准备学习资料、发布”。每一状态只有一个主动作：例如上传完成后“开始解析”，存在审核问题时“查看问题”，可发布时“发布给学生”。

上传卡片保留可恢复分片上传，并用“已上传大小/百分比/可继续上传”说明状态。上传、解析或索引运行期间允许离开当前页面；回到教材详情后基于真实任务数据恢复显示。失败卡片必须给出服务器返回的原因和是否可重试。

## 学生体验

学生首页先给出可继续学习、待复习和开放测验；没有已发布教材时展示明确空状态。学习页以教材正文和检索结果为中心，AI 回答显示现有证据标签与“查看原文”动作；在可验证的精确定位能力接通前，不承诺图片/表格/公式的前端回跳。练习聚合测验与复习；成长展示服务端掌握度和复习状态；“我的”只展示本人记忆摘要和隐私删除请求。

## 权限与迁移

所有新路由位于现有 `WorkspaceRoleGuard` 之后；前端导航不能代替服务端授权。教师/学生访问错误角色路线时仍按 `/me` 的有效工作区跳转。旧 `/teacher`、`/student` 以及各现有子页在对应新页面完成后，重定向到默认课程或给出真实的“未选择课程”状态，不能加载另一角色的页面。

开发冒烟课程保留数据，但课程列表以标题约定显示“测试课程”分组并默认收起；不自动删除任何已有课程或教材。

## 错误、加载与可访问性

所有初始加载、提交、SSE 生成和后台任务均有显式加载反馈；错误采用 API 的可操作文案，保留 retryable 信息。空状态、失败状态和禁用状态不伪装完成。按钮具有可见焦点、语义标签和最小点击区域；动画仅用于进度和抽屉状态变换，并遵从 `prefers-reduced-motion`。

## 验收与非目标

P0/P1 验收：教师能进入课程、管理教材、上传、查看真实进度/问题、执行服务端允许操作、发布，并从 Drawer 找回后台任务；非技术用户不需理解实现术语。学生端不显示教师能力或未发布资源。

本轮非目标：扫描/OCR 工作台、可视检索、人工 bbox 编辑、图表/公式智能问答、模型设置、复杂 BI 与生产部署。
