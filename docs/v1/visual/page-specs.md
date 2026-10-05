# V1 代表页面规格

本文件不是视觉成品图，而是进入 Figma/高保真绘制前必须冻结的页面合同。每页都必须绘制 Desktop（≥1200px）、Tablet（900–1199px）和 Mobile（<640px）三套画板，并覆盖 loading、empty、error、conflict/recovery 四种状态。

## 1. 共用画板规则

| 项目 | Desktop | Tablet | Mobile |
|---|---|---|---|
| 页面骨架 | 固定 Sidebar + Context Bar + Main | Sidebar 可收缩，Context Panel overlay | Bottom/compact navigation，详情为 full-height Sheet |
| 主内容宽度 | 960–1280px | 100% 减 32px | 100% 减 32px |
| Drawer | inline 或 360–520px | overlay 360–440px | full-height，返回键关闭 |
| 主操作 | 每局部区域最多一个 Primary | 保持可见 | 固定底部或靠近表单，不遮挡输入 |
| 失败反馈 | 区域内 Banner + request_id | 同左 | Banner + 可执行按钮，避免只用 Toast |

页面不得放静态假数据。没有 Read Model 时显示原因和下一步，例如“尚未分配课程”“暂无可发布版本”“等待后台任务完成”。

## 2. Student 页面

### 2.1 Student Home

- 目标：5 秒内识别当前任务。
- 首屏：一个 Current Learning Task、最多两个 Next Actions、最多一个 Attention Item、Recent Activity。
- 不放：全局 Chat、Mastery 百分比、风险排行榜、装饰性图表。
- Loading：任务骨架 + 单一进度提示。
- Empty：无课程、无任务、任务已完成分别表达，并给出进入课程/复习/等待安排的动作。
- Error：局部任务读取失败时保留导航，显示 request_id 和重试。
- Recovery：课程切换或任务版本变化时提示“内容已更新”，不保留旧任务操作。

### 2.2 AI Learning Workspace

- Desktop：左 Context Rail 216–248px；中间 Learning Stream；右 Context Panel 默认收起 320–480px。
- Header：课程、当前 Release、任务标题、暂停/退出；Task Bar 显示阶段和允许动作。
- Stream：TutorExplanation、Question、Hint、WorkedExample、TeachingAsset、EvidencePrompt、Feedback、Transition、TaskCompletion。
- Panel：Evidence、Branch、Task Detail 三者互斥；Evidence 点击后定位版本页和 bbox。
- Loading：按 Block 类型显示 skeleton；不能用“AI 正在思考”覆盖所有等待。
- Empty：未有可展示 Block 时显示当前状态和唯一下一步，不显示空白聊天框。
- Error：单 Block 可降级为文本或教材入口；未知 Block 显示“暂不支持此内容”。
- Recovery：SSE 断线按 turn 恢复；半回合不显示为已确认结论。

### 2.3 Experimental Reasoning Case Workspace

- Desktop：Case Canvas 60–65%；Reasoning Panel 35–40%。
- 核心工具：Find Confound、Experiment Decomposer、Design Board、Result Interpreter、Critique/Redesign。
- 选择必须支持点击、触控和键盘；拖拽只是 enhancement。
- 反馈显示依据和下一步，不因点击正确区域立即显示“掌握”。
- Loading：案例结构先呈现，交互区按模块加载。
- Empty：无匹配案例时显示能力缺口和练习入口。
- Error：保存冲突保留学生输入，提示刷新/合并，不静默覆盖。
- Recovery：离开页面恢复同一 CaseSession 和草稿版本。

### 2.4 Growth / Open Learner Model

- Tabs：概览、知识、实验能力、学习轨迹。
- 概览顺序：当前最值得加强 → 课程状态 → 最近注意 → 实验推理 → 最近变化。
- 每个状态带“为什么这样判断？”入口，打开 Evidence/Timeline Drawer。
- Loading：分区骨架；不先显示旧缓存冒充新状态。
- Empty：证据不足、尚无课程、尚无复习任务分别说明。
- Error：单 Tab 失败不阻塞其他 Tab。
- Recovery：证据失效/删除完成后刷新状态，并显示更新时间。

### 2.5 Formal Assessment

- 独立 Assessment Shell，不显示学生常规导航。
- 区域：Assessment Header、Question Navigator、Question Surface、Autosave/Connection 状态、Submit Gate。
- Loading：Precheck 显示服务端时间、Policy、版本和题目加载进度。
- Empty：正式测评不存在或无权时 404 页面，不泄露题目。
- Error：保存冲突、网络中断、时间到分别提供恢复、只读复核或提交结果。
- Recovery：断线进入 RECOVERING；恢复后回到同一 Attempt/version。

### 2.6 Mini Psychology Lab

- 阶段：Intro → Predict → Run → Inspect Data → Explain → Summary。
- Runtime 隐藏 Tutor、Evidence、Branch，避免干扰实验。
- Loading：实验资源、计时和试次状态独立展示。
- Empty：实验定义未发布时进入说明页，不展示假实验。
- Error：试次数据校验失败或中断时说明是否可恢复/作废。
- Recovery：恢复只依据服务端 session；TrialData 与 LearningEvidence 分开呈现。

## 3. Teacher 页面

### 3.1 Teaching Control Center

- 首屏顺序：Primary Teaching Problem → Secondary Attention → Current Teaching → Recent Intervention → Operational Summary。
- Problem Detail：发生了什么 → 为什么判断 → 教学解释 → 建议怎么办。
- 不显示风险排行榜；状态使用需要处理/值得关注/正在改善。
- Empty：无课程、无问题、尚无干预均提供可执行入口。
- Error：聚合部分失败时显示 freshness 和缺失分区，不拼静态数字。
- Recovery：干预提交冲突保留当前表单，要求重新读取目标快照。

### 3.2 Teaching Timeline

- 左侧 Timeline 显示 Planned/Actual；右侧 Activity Inspector。
- Activity 状态：已安排、可开始、正在进行、已暂停、已完成、已取消。
- Intervention 是 Timeline 中的 Activity，不另建“干预管理”页面。
- Loading：按时间线段加载，不阻塞已读内容。
- Empty：尚无活动时显示创建活动或查看推荐的单一主操作。
- Error：单活动详情失败不清空整个时间线。
- Recovery：版本冲突时提示目标 Release/Task 已变化，禁止覆盖。

### 3.3 Analytics / 学情

- Tabs：知识状态、实验能力、易混淆、复习、学生。
- 默认列表/分组视图；Matrix View 为 Advanced View。
- Knowledge Detail 展示六类 Evidence Coverage：记忆、理解、辨析、应用、迁移、保持。
- Student View 先按支持需求分组，再进入学生名单。
- Loading：显示样本口径和时间范围的骨架。
- Empty：无样本、无复习任务、证据不足分别说明。
- Error：查询失败显示结构化条件和重试，不退化成通用聊天。
- Recovery：课程/班级切换后 query key 改变，旧结果不能短暂串入。

### 3.4 Assessment / Grading

- Tabs：概览、题库、正式测验、评分与复核。
- 发布 Wizard：基本信息 → 题目 → 测评设置 → AI/安全策略 → 学生预览 → 锁定发布。
- Grading 三栏：Submission Queue 20% / Student Response 45% / Rubric 35%。
- AI 建议默认折叠，教师决定和 ScoreRecord 独立显示。
- Loading：队列和答案分开加载。
- Empty：无待评分或无候选题时显示下一步。
- Error：评分冲突、Rubric 版本过期和发布 Gate 失败显示不同处理动作。
- Recovery：重复发布/提交返回原结果，不生成第二个 Release/ScoreRecord。

## 4. Course Designer 页面

### 4.1 Domain Workspace

- 三栏：Course Structure / Domain Canvas / Inspector。
- 对象：KnowledgePoint、Relation、ExperimentSchema、MisconceptionDefinition、Evidence Binding。
- Canonical TextbookObject 只读；AI 候选必须带 Evidence，Designer 接受/修改/拒绝。
- Loading：结构树、Canvas、Inspector 分层加载。
- Empty：无 Draft 时显示创建 Draft；无 Evidence 时阻止发布。
- Error：候选校验失败保留草稿并显示字段级错误。
- Recovery：并发编辑返回 409，提供比较和新版本保存，不静默覆盖。

### 4.2 Pedagogy Workspace

- Learning Flow Canvas + Inspector；不演化成 BPMN 编辑器。
- Authoring 顺序：目标 → 白名单模板 → 内容 → 交互 → Evidence → Evidence 规则 → 无障碍 → Fallback → Preview。
- Loading：节点和 Inspector 独立 skeleton。
- Empty：没有 Activity Template 时显示受控模板入口，不允许任意 React 代码。
- Error：缺 Evidence、缺 Fallback、未知交互分别阻止保存或发布。
- Recovery：草稿版本冲突进入 Diff/复制新版本。

### 4.3 Release Workspace

- Wizard：选择内容 → 自动检查 → Impact Preview → Diff → Review → Publish。
- 同时展示 DomainRelease、PedagogyPackRelease、AssessmentPackRelease 和 CourseRelease 绑定。
- ERROR 阻断；WARNING 要求理由；INFO 仅提示。
- Loading：逐阶段显示真实任务状态和当前 LKG。
- Empty：无 Draft 或无可绑定资产时给出创建/返回动作。
- Error：失败构建不替换已发布版本；显示阶段、影响和重试。
- Recovery：发布重试幂等；Published 只能创建新版本。

## 5. Admin 页面

### 5.1 Operations Overview / Jobs

- 只展示后台任务、Projection 延迟、Index Build、Evaluation、健康和 LKG。
- 不展示教学 Analytics 或学生私聊正文。
- 任务失败字段：阶段、错误摘要、影响、稳定版本、重试入口。
- Loading/empty/error/recovery 均显示任务新鲜度和 request_id。

### 5.2 Identity & Access / Course & Class

- Wizard 管理 User、Role、Scope、Membership、Teacher Assignment、CourseRelease Assignment。
- 每次高风险变更显示影响范围和审计结果。
- 不因打开 Admin 页面而自动读取学生薄弱点。

### 5.3 Audit

- Append-only Table：时间、Actor、Action、Object、Result。
- 支持按角色、资源、结果和时间过滤；详情 Drawer 显示最小必要信息。
- 不显示密码、Cookie、完整 Prompt、私聊正文等敏感内容。
