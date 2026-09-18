# 《实验心理学》智能体教学平台双主线执行计划

版本：V1.0  
周期：10周  
人员：2名全栈开发者  
目标：完成可供一个班级试用的B/S版本  
依据：《实验心理学课程智能体平台详细技术设计方案-v2》

## 1. 执行结论

项目采用两条业务闭环主线并行开发，不按“一个人前端、一个人后端”拆分。两个人都要对自己主线的页面、接口、数据、测试和文档负责。

- 主线A：课程内容与可信知识线。负责人记为A。
- 主线B：学生学习与智能教学线。负责人记为B。
- 共同基础：项目骨架、身份权限、公共数据结构、API规范、模型网关、测试环境和发布流程，由两人共同确定；确定后按模块归属维护。

10周结束时必须跑通以下班级试用闭环：教师创建课程并上传教材 → 系统解析并构建知识库 → 教师发布资料和题目 → 学生按章节学习 → AI依据教材进行可引用答疑 → 学生完成练习并获得分层提示 → 教师查看学习情况 → 系统能够部署、备份和恢复。

## 2. 分工边界

### 2.1 主线A：课程内容与可信知识线

负责人A对以下模块端到端负责：

1. 课程、班级、成员和教师工作台。
2. 教材、课件和附件的上传、版本、发布与权限。
3. MinerU/Docling解析适配、章节树、页面对象和人工校正。
4. 知识分块、Embedding、BM25、pgvector、混合召回和重排序。
5. Evidence Package、引用卡片数据、教材原页定位和回答依据校验。
6. 题库、题目版本、出题Agent、教师审核与正式发布。
7. 模型配置、异步任务、对象存储、部署、备份和系统健康。

主线A必须向主线B提供稳定的课程、教材、知识证据、题目和引用接口，但不能直接修改主线B的学习状态。

### 2.2 主线B：学生学习与智能教学线

负责人B对以下模块端到端负责：

1. 学生首页、课程空间、章节学习页和教材阅读体验。
2. AI教师状态机、流式对话、分步提示和学习任务恢复。
3. 当前题目悬浮教练、侧边栏分支对话和主线回传。
4. 测验作答、客观题评分、主观题建议、错题和复习任务。
5. 学习事件、L0—L3记忆、过时标记、上下文压缩和循环检测。
6. 学习画像、个人进度和教师可查看的班级统计。
7. 学生端异常恢复、端到端测试、试用反馈和体验修正。

主线B只能通过已定义接口读取课程、题目和证据，不允许绕过接口直接查询主线A的内部表。

### 2.3 共同负责但指定维护人

| 公共事项 | 主维护人 | 另一人责任 |
|---|---|---|
| 仓库结构、代码规范、CI | A | B评审并补充前端/E2E规则 |
| 登录、RBAC和课程成员关系 | A | B负责学生端接入和越权测试 |
| OpenAPI与TypeScript客户端生成 | A | B负责消费端契约测试 |
| UI设计规范与通用组件 | B | A在教师端复用并提出缺口 |
| 模型网关与调用记录 | A | B定义教学流程所需模型能力 |
| 测试数据与演示课程 | B | A提供教材、题目和知识库导入工具 |
| 部署、监控、备份 | A | B负责全流程冒烟与恢复后验证 |
| 版本发布与教师验收 | B | A负责技术检查与故障处置 |

## 3. 工作方式与仓库规则

### 3.1 推荐仓库结构

```text
psychology-learning-platform/
├─ web/                         # Next.js 16前端
│  ├─ app/student/              # B主维护
│  ├─ app/teacher/              # A主维护
│  ├─ app/admin/                # A主维护
│  ├─ components/common/        # B主维护，双方复用
│  └─ lib/api/                  # OpenAPI自动生成客户端，不手写接口类型
├─ server/                      # FastAPI后端
│  ├─ modules/auth/             # A
│  ├─ modules/courses/          # A
│  ├─ modules/materials/        # A
│  ├─ modules/knowledge/        # A
│  ├─ modules/questions/        # A
│  ├─ modules/learning/         # B
│  ├─ modules/tutor/            # B
│  ├─ modules/memory/           # B
│  ├─ modules/analytics/        # B
│  └─ shared/                   # 公共异常、权限、模型网关、事件和日志
├─ contracts/
│  ├─ openapi.json              # 后端生成并纳入版本控制
│  ├─ events.md                 # 内部事件契约
│  └─ examples/                 # 典型请求响应样例
├─ migrations/                  # 数据库迁移；文件名带模块前缀
├─ tests/
│  ├─ contract/                 # 双方共同维护
│  ├─ integration/
│  ├─ e2e/
│  └─ rag-eval/
├─ infra/                       # Docker Compose、Nginx、监控和备份
└─ docs/                        # 设计、接口、运行和验收文档
```

### 3.2 Git协作规则

1. `main`始终保持可运行，不建立长期不合并的A/B大分支。
2. A使用`a/<module>-<task>`，B使用`b/<module>-<task>`短分支，原则上1—3天内合并。
3. 修改公共契约、数据库公共字段、权限规则和通用组件必须由另一人评审。
4. Pull Request必须包含：变更目的、接口变化、迁移影响、测试证据、截图或调用样例、回滚方式。
5. 不允许在同一个PR同时进行大规模重构和功能开发。
6. 未完成功能通过feature flag隐藏，不能让`main`长期处于半成品状态。
7. 每周至少发布一个可运行的集成版本，连续两周不集成视为计划失控。

### 3.3 完成定义（Definition of Done）

任务只有同时满足以下条件才算完成：

- 页面、接口、数据迁移和权限检查均已完成。
- 正常、空数据、无权限、服务失败四类情况有明确表现。
- 单元或集成测试通过，关键流程有E2E或可重复调用样例。
- OpenAPI和前端客户端同步更新，没有手写重复类型。
- 不在日志中输出Token、模型密钥和完整敏感对话。
- 有最小使用说明、验收步骤和回滚说明。
- 另一人已评审并在集成环境验证。

## 4. 共同技术基线

| 项目 | 统一决定 |
|---|---|
| Web | Next.js 16、React、TypeScript、Tailwind CSS、shadcn/ui |
| API | Python 3.11+、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 数据库 | PostgreSQL 16 + pgvector |
| 文件 | MinIO或兼容S3对象存储 |
| 缓存与任务 | Redis + Celery |
| 教材解析 | MinerU主路径；Docling/PaddleOCR作为补充与降级 |
| 检索 | BM25 + pgvector + RRF融合 + Reranker |
| 模型 | OpenAI-compatible网关；LLM、Embedding、Reranker分别配置 |
| 实时返回 | 普通流式回答使用SSE；只有确需双向实时协作时才使用WebSocket |
| 认证 | HttpOnly Secure Cookie + 短期访问会话 + 服务端RBAC |
| 部署 | Docker Compose + Nginx + HTTPS；首期不引入Kubernetes |
| 观测 | 结构化日志、OpenTelemetry、Prometheus/Grafana、错误追踪 |

## 5. API与契约总则

### 5.1 通用规则

- 基础路径统一为`/api/v1`。
- ID统一使用ULID字符串，时间统一使用UTC ISO 8601，前端按用户时区显示。
- 所有写接口接受`Idempotency-Key`，避免重复提交、重复扣费或重复建索引。
- 列表接口统一使用`cursor`和`limit`，不使用不同模块各自发明分页格式。
- 所有对象携带`created_at`、`updated_at`和必要的`version`。
- 资源版本使用不可变记录；发布新版本不覆盖已被测验或引用使用的旧版本。
- API错误统一返回`error.code`、`error.message`、`request_id`和可选的`details`。
- 权限在服务端校验；前端隐藏按钮不等于权限控制。
- 前端类型从OpenAPI自动生成，禁止复制粘贴维护第二套请求响应类型。

### 5.2 通用响应格式

成功响应：

```json
{
  "data": {},
  "meta": {
    "request_id": "01K...",
    "server_time": "2026-09-16T08:00:00Z"
  }
}
```

错误响应：

```json
{
  "error": {
    "code": "KNOWLEDGE_NOT_READY",
    "message": "教材索引尚未完成",
    "details": {"job_id": "01K...", "status": "running"}
  },
  "request_id": "01K..."
}
```

### 5.3 统一状态码

| 状态码 | 使用场景 |
|---|---|
| 200/201 | 查询成功/创建成功 |
| 202 | 已进入异步任务队列 |
| 204 | 删除或无正文操作成功 |
| 400 | 参数不合法或业务规则不满足 |
| 401 | 未登录或会话失效 |
| 403 | 已登录但没有权限 |
| 404 | 当前权限范围内资源不存在 |
| 409 | 版本冲突、重复提交或状态不允许 |
| 422 | 字段校验失败 |
| 429 | 速率、并发或预算超限 |
| 503 | 模型、解析器或依赖服务暂不可用 |

## 6. 提前冻结的核心数据模型

| 模型 | 关键字段 | 归属 |
|---|---|---|
| User | id、email、display_name、status | A |
| Course | id、title、term、owner_id、status | A |
| Enrollment | course_id、user_id、role、status | A |
| Material | id、course_id、type、current_version_id、visibility | A |
| MaterialVersion | id、material_id、version、file_hash、status、published_at | A |
| ParseJob | id、material_version_id、engine、status、progress、error | A |
| KnowledgeObject | id、version_id、type、chapter_path、page、bbox、content | A |
| KnowledgeChunk | id、object_ids、parent_id、text、embedding_version、status | A |
| Evidence | id、chunk_id、source_version、page、anchor、support_level | A |
| Question | id、course_id、current_version_id、status、origin | A |
| QuestionVersion | stem、type、answer、rubric、difficulty、evidence_ids | A |
| Assessment | id、course_id、rules、open_at、close_at、ai_policy | A |
| Attempt | id、assessment_id、student_id、status、started_at、submitted_at | B |
| Answer | attempt_id、question_version_id、response、score、review_status | B |
| ChatSession | id、course_id、student_id、mode、status、summary | B |
| ChatTurn | session_id、role、content、citation_ids、model_call_id | B |
| LearningSession | id、student_id、course_id、goal、state、current_step | B |
| LearningEvent | actor_id、course_id、event_type、object_id、payload、occurred_at | B |
| MemoryEntry | student_id、course_id、layer、type、content、evidence_ids、status | B |
| MasteryState | student_id、knowledge_point_id、level、confidence、algorithm_version | B |
| ReviewTask | student_id、knowledge_point_id、due_at、reason、status | B |
| AuditLog | actor、action、target、before_hash、after_hash、request_id | 共同，A维护 |
| ModelCall | purpose、provider、model、latency、token_usage、status、request_id | 共同，A维护 |

约束：`Evidence`保存的是可定位证据，不保存模型生成结论；`MemoryEntry`不能直接指向没有来源的模型总结；`MasteryState`是推断值，必须带算法版本和置信度。

## 7. 核心接口清单

### 7.1 身份与课程接口（A提供，双方使用）

| 方法与路径 | 用途 | 主要请求 | 主要响应 |
|---|---|---|---|
| POST `/auth/login` | 登录 | email、password | user、session_expires_at |
| POST `/auth/refresh` | 刷新会话 | Cookie | session_expires_at |
| POST `/auth/logout` | 退出 | 无 | 204 |
| GET `/me` | 当前用户 | 无 | user、roles、course_memberships |
| GET/POST `/courses` | 查询/创建课程 | title、term | Course |
| GET/PATCH `/courses/{course_id}` | 课程详情/修改 | version、允许修改字段 | Course |
| GET/POST `/courses/{course_id}/members` | 成员查询/添加 | user_id、role | Enrollment |
| DELETE `/courses/{course_id}/members/{user_id}` | 移除成员 | version | 204 |

### 7.2 教材与知识库接口（A提供，B消费）

| 方法与路径 | 用途 | 主要响应/说明 |
|---|---|---|
| POST `/courses/{course_id}/materials` | 上传资料 | 201 Material；大文件可先申请上传地址 |
| GET `/materials/{material_id}` | 资料与版本状态 | 当前版本、可见范围、处理状态 |
| POST `/materials/{material_id}/versions` | 上传新版本 | 新MaterialVersion，不覆盖旧版本 |
| POST `/material-versions/{version_id}/parse` | 启动解析 | 202 ParseJob |
| GET `/jobs/{job_id}` | 统一查询异步任务 | status、progress、stage、error |
| GET `/material-versions/{version_id}/outline` | 章节树预览 | 标题层级、页码、对象数量 |
| PATCH `/knowledge-objects/{object_id}` | 教师修正对象 | 版本检查后返回新对象版本 |
| POST `/material-versions/{version_id}/publish` | 发布教材版本 | 发布前必须通过最低质量检查 |
| POST `/knowledge/search` | 权限内检索 | query、course_id、chapter_scope、object_types、top_k |
| GET `/evidence/{evidence_id}` | 引用解析 | 原文、页码、bbox、版本、预览地址、授权状态 |
| GET `/materials/{material_id}/pages/{page}` | 教材页预览 | 临时授权地址与高亮坐标 |

`POST /knowledge/search`响应的最低结构：

```json
{
  "data": {
    "query": "自变量和因变量有什么区别？",
    "evidence": [
      {
        "evidence_id": "01K...",
        "material_version_id": "01K...",
        "chapter_path": ["第2章", "2.1 实验变量"],
        "page": 36,
        "anchor": "p36-b12",
        "object_type": "definition",
        "text": "……",
        "score": 0.91,
        "support_level": "candidate"
      }
    ],
    "retrieval_version": "hybrid-rag-v1"
  }
}
```

### 7.3 题库与测验接口（A提供题目，B负责作答）

| 方法与路径 | 负责人 | 用途 |
|---|---|---|
| GET/POST `/courses/{course_id}/questions` | A | 查询/教师录入题目 |
| POST `/courses/{course_id}/question-generation-jobs` | A | 按章节、题型、数量、难度生成候选题 |
| GET `/question-generation-jobs/{job_id}` | A | 查看生成、证据对齐和校验进度 |
| POST `/questions/{question_id}/review` | A | approve、reject或request_changes |
| POST `/questions/{question_id}/publish` | A | 发布指定不可变版本 |
| GET/POST `/courses/{course_id}/assessments` | A | 建立测验及AI使用规则 |
| GET `/assessments/{assessment_id}` | B消费 | 返回学生有权看到的题目，不提前返回答案 |
| POST `/assessments/{assessment_id}/attempts` | B | 创建作答记录 |
| PUT `/attempts/{attempt_id}/answers/{question_id}` | B | 幂等保存草稿答案 |
| POST `/attempts/{attempt_id}/submit` | B | 提交并锁定作答版本 |
| GET `/attempts/{attempt_id}/result` | B | 根据公布规则返回成绩、解析和复核状态 |

题目发布前必须存在：教材证据、标准答案或评分量表、难度说明、审核人和版本号。出题Agent生成结果只能处于`draft`或`review`，不能自动进入`published`。

### 7.4 AI问答与教学接口（B提供，内部调用A的证据接口）

| 方法与路径 | 用途 |
|---|---|
| POST `/chat/sessions` | 创建课程问答、题目教练或复习会话 |
| GET `/chat/sessions/{session_id}` | 恢复会话、摘要和当前状态 |
| POST `/chat/sessions/{session_id}/turns` | 提交学生消息，返回SSE事件流 |
| POST `/learning-sessions` | 创建引导式学习任务 |
| POST `/learning-sessions/{id}/responses` | 提交学生回答并推进状态机 |
| POST `/learning-sessions/{id}/actions` | 请求提示、示例、回到教材、暂停或结束 |
| GET `/learning-sessions/{id}/state` | 获取可恢复状态，不依赖模型猜测 |

SSE事件固定为：

```text
event: state        data: {"state":"diagnose","step":2}
event: delta        data: {"text":"先想一想……"}
event: citation     data: {"evidence_id":"01K...","label":"教材第36页"}
event: action       data: {"type":"wait_for_student"}
event: usage        data: {"input_tokens":1200,"output_tokens":180}
event: done         data: {"turn_id":"01K...","finish_reason":"stop"}
event: error        data: {"code":"MODEL_UNAVAILABLE","retryable":true}
```

模型输出不能直接改变学习状态。后端状态机验证当前允许的动作后再更新`LearningSession.state`。

### 7.5 题目悬浮教练与分支对话接口（B）

| 方法与路径 | 用途 |
|---|---|
| POST `/questions/{question_id}/coach-sessions` | 带入题目版本、当前答案、提示次数和AI规则 |
| POST `/coach-sessions/{id}/turns` | 只针对当前题进行提示或讲解 |
| POST `/chat/sessions/{id}/branches` | 从选中文本创建隔离分支 |
| POST `/branches/{branch_id}/turns` | 分支内问答，不污染主会话摘要 |
| POST `/branches/{branch_id}/merge` | 经学生确认，把结构化结论带回主线 |

分支创建请求必须包含`source_turn_id`、`selected_text`和`selection_offsets`。回传只允许`question`、`confirmed_note`或`unresolved_issue`三种结构化类型，不能把整段分支历史直接拼回主上下文。

### 7.6 学习记忆与画像接口（B）

| 方法与路径 | 用途 |
|---|---|
| GET `/me/courses/{course_id}/memory/overview` | 先返回各层目录、数量和更新时间 |
| GET `/me/courses/{course_id}/memory/entries` | 按layer、type、status分页读取 |
| POST `/memory/candidates` | 内部产生候选记忆，必须附证据 |
| POST `/memory/entries/{id}/confirm` | 学生或规则确认候选条目 |
| POST `/memory/entries/{id}/mark-stale` | 标记过时并默认隐藏 |
| POST `/memory/entries/{id}/correct` | 建立修订版本，保留审计关系 |
| DELETE `/memory/entries/{id}` | 按数据政策执行删除或匿名化 |
| GET `/me/courses/{course_id}/mastery` | 返回知识点状态、置信度、依据和更新时间 |
| GET `/me/courses/{course_id}/review-tasks` | 返回到期复习任务 |

记忆读取顺序固定为“overview → 按需entries”，禁止每轮把所有历史全部加载。`important=true`只表示不自动过时，不能阻止用户依法删除。

### 7.7 学习事件与统计接口（B提供，双方写入）

| 方法与路径 | 用途 |
|---|---|
| POST `/learning-events/batch` | 批量上传经过白名单校验的学习事件 |
| GET `/me/courses/{course_id}/progress` | 学生个人进度、成绩和复习情况 |
| GET `/teacher/courses/{course_id}/analytics/overview` | 班级汇总，不默认返回私密对话 |
| GET `/teacher/courses/{course_id}/analytics/knowledge-points` | 知识点掌握分布和证据量 |
| GET `/teacher/courses/{course_id}/analytics/questions` | 题目正确率、区分情况和常见错误 |

事件类型采用白名单，例如`material.opened`、`chapter.completed`、`attempt.submitted`、`hint.requested`、`citation.opened`和`review.completed`。前端自定义字符串不能直接进入统计主表。

## 8. 跨主线内部事件契约

首期不引入Kafka。使用PostgreSQL Outbox表记录可靠事件，由Celery消费者处理；事件处理必须幂等。

| 事件 | 生产者 | 消费者 | 必要字段 |
|---|---|---|---|
| `material.version.published.v1` | A | B | course_id、material_id、version_id、published_at |
| `knowledge.index.ready.v1` | A | B | version_id、index_version、object_count |
| `question.version.published.v1` | A | B | course_id、question_id、question_version_id |
| `assessment.published.v1` | A | B | assessment_id、rules_version、open_at、close_at |
| `attempt.submitted.v1` | B | A统计/审计 | attempt_id、student_id、assessment_id、submitted_at |
| `answer.graded.v1` | B | A题目质量 | question_version_id、score、max_score、review_status |
| `tutor.turn.completed.v1` | B | B记忆/统计 | session_id、student_id、state、evidence_ids、outcome |
| `memory.entry.changed.v1` | B | B画像 | entry_id、action、source_version、status |

每个事件包含`event_id`、`event_type`、`event_version`、`occurred_at`、`producer`、`trace_id`和`payload`。事件字段发生不兼容变化时升级版本，不能静默改变旧事件含义。

## 9. 10周详细执行计划

### 第1周：共同底座与契约冻结

主线A：

- 建立仓库、FastAPI、PostgreSQL、Redis、MinIO和Docker Compose骨架。
- 建立用户、课程、成员、审计、任务和模型调用基础表。
- 建立登录、`/me`、课程和成员接口。
- 配置Alembic、Ruff、Pytest和OpenAPI导出。

主线B：

- 建立Next.js、角色路由、登录页、学生/教师基础壳和通用组件。
- 建立OpenAPI TypeScript客户端生成流程。
- 建立Playwright、前端单元测试和Mock Service Worker。
- 画出学生学习、AI对话、题目教练的状态转换表。

共同交付：

- 本文第5—8章契约评审通过。
- 本地一条命令启动；两个人机器均可登录并创建课程。
- CI完成格式、类型、单元测试、迁移检查和OpenAPI差异检查。

验收门槛：任何一人拉取新环境后30分钟内启动；学生无法访问教师接口；前端无手写重复DTO。

### 第2周：课程、教材与学生课程空间

主线A：完成课程CRUD、成员管理、资料上传、对象存储、版本表、异步任务框架和教师资料列表。

主线B：完成学生课程列表、课程首页、章节基础结构、空状态、加载状态和无权限页面；接入课程与成员真实接口。

共同联调：教师创建课程并加入学生，学生只能看到已加入课程；上传文件后可查看任务状态。

### 第3周：教材解析、章节树与基础学习

主线A：接入MinerU主解析；定义统一中间格式；保存章节、页面、段落、图表和坐标；完成解析预览、人工修正和发布。

主线B：完成章节目录、教材页阅读、学习进度事件、最近学习位置和移动端基本适配。

集成门槛G1：一份真实教材能够上传、解析、预览、发布；学生可按章节阅读；错误文件不会生成假成功状态。

### 第4周：混合检索与AI对话基础

主线A：实现章节感知分块、Embedding、pgvector、BM25、RRF和检索接口；建立离线检索样例集。

主线B：实现课程问答会话、SSE流式显示、消息持久化、停止生成、失败重试和会话恢复。

共同联调：B通过`/knowledge/search`取得证据，完成第一条带引用的回答；记录trace_id贯通前后端。

### 第5周：Evidence Package与引导式AI教师

主线A：实现父子块补齐、Reranker、证据包、引用解析、页面高亮和主张—证据校验初版。

主线B：实现“目标—诊断—判断—提示—巩固—总结”状态机；模型动作必须经服务端校验；加入循环检测。

集成门槛G2：至少30个教师问题完成离线测试；引用能打开正确页面；无证据问题明确拒答；AI不会在等待学生时自行继续。

### 第6周：题库、测验与当前题目教练

主线A：完成教师录题、题目版本、证据绑定、审核、发布、测验配置和AI使用规则。

主线B：完成测验作答、草稿自动保存、提交锁定、客观题评分、错题展示和悬浮教练。

共同联调：考试关闭AI时教练接口必须服务端拒绝；练习模式下提示次数和题目版本准确传递。

### 第7周：出题Agent、分支对话与复习闭环

主线A：完成出题任务、证据检索、题目生成、答案/评分点、去重、校验和教师审核台。自动生成题只能是候选。

主线B：完成选中文本创建分支、分支问答、结构化回传、错题归因和复习任务初版。

集成门槛G3：教师能从章节生成候选题并审核发布；学生能完成练习、追问陌生概念并进入复习任务；分支不会污染主会话。

### 第8周：记忆、画像、统计与安全

主线A：完善RBAC、资源级权限、模型预算、任务限流、审计查询、系统健康和教师统计所需课程维度。

主线B：完成L0—L3记忆、候选确认、stale、纠正、删除、渐进加载、会话压缩、掌握状态和班级学习分析。

共同安全检查：课程隔离、学生隔离、越权ID替换、日志脱敏、模型密钥、上传文件和心理危机场景。

### 第9周：集成、性能、部署与教师预验收

主线A：完成生产Compose、Nginx、HTTPS配置模板、监控、备份、恢复脚本、索引版本切换和回滚说明。

主线B：完成全流程E2E、可用性修正、断网草稿、错误页、教师预验收脚本和试用反馈表。

集成门槛G4：在独立测试环境从零部署；恢复备份后完成登录、教材阅读、问答、测验和统计冒烟；完成一次教师预验收。

### 第10周：班级试用发布

共同任务：

- 修复阻塞试用的问题，不在本周增加大功能。
- 固定镜像、迁移、模型配置、教材索引和演示数据版本。
- 建立管理员、教师和学生试用账号。
- 执行发布清单、权限检查、备份和恢复点创建。
- 观察错误率、模型延迟、队列、磁盘和费用。
- 收集真实学生与教师反馈，形成下一阶段问题清单。

发布门槛G5：P0/P1问题为零；关键流程通过；备份可恢复；教师确认课程内容；学生数据采集说明已展示。

## 10. 每周固定节奏

| 时间 | 活动 | 输出 |
|---|---|---|
| 周一上午 | 30分钟计划会 | 本周每人3—5个可验收任务、接口变更清单 |
| 每天 | 10分钟同步 | 昨日完成、今日目标、阻塞；不做长汇报 |
| 周三 | 契约与集成检查 | OpenAPI差异、迁移冲突、公共组件变化 |
| 周五上午 | 合并与自动测试 | `main`绿色、测试环境发布 |
| 周五下午 | 共同验收与复盘 | 可运行演示、缺陷、下周依赖和风险 |

接口或数据结构变更必须在编码前写入契约PR；对方确认后再实现。紧急修复可以先处理，但24小时内补齐契约和测试。

## 11. 测试责任矩阵

| 测试 | A负责 | B负责 | 共同门槛 |
|---|---|---|---|
| 单元测试 | 课程、解析、检索、题库、权限 | 教学状态、评分、记忆、画像、统计 | 新增核心规则必须覆盖 |
| 契约测试 | OpenAPI提供端 | TS客户端消费端 | CI检测破坏性变化 |
| 集成测试 | PostgreSQL、MinIO、Redis、模型网关 | 会话、测验、事件、记忆 | 使用真实容器依赖 |
| RAG评测 | 召回、排序、引用、资料外拒答 | 回答结构和学生展示 | 教师样例集固定版本 |
| E2E | 教师上传和发布 | 学生学习完整流程 | 每周五测试环境运行 |
| 安全测试 | RBAC、上传、密钥、审计 | 越权、隐私、危机场景 | 上线前全部通过 |
| 恢复测试 | 备份与服务恢复 | 恢复后业务冒烟 | 第9周至少一次 |

## 12. 风险与应对

| 风险 | 预警信号 | 处理方式 |
|---|---|---|
| 两条主线接口漂移 | 同一字段双方定义不同 | Pydantic/OpenAPI为唯一来源；CI比较契约 |
| A任务过重 | 解析、RAG和部署同时延期 | B在第3、9周支援页面/E2E；先保留单解析器和单检索基线 |
| B等待知识接口 | 连续两天只能用假数据 | A先提供契约和固定样例；B使用契约Mock并建立消费测试 |
| 教材解析效果差 | 章节、表格或图注大量错位 | 教师校正界面优先；保留Docling/OCR降级；不把错误内容发布 |
| RAG回答无依据 | 引用存在但不支持结论 | 加主张—证据校验和拒答；建立教师黄金问题集 |
| 自动出题质量低 | 答案冲突、超纲或重复 | 候选题必须人工审核；首期不自动发布 |
| 记忆误写 | 一次失误被标成长期薄弱 | 候选层、多证据确认、纠正和stale机制 |
| 上线前集中集成 | 第7周仍无法跑通上传到问答 | 第3、5、7周强制集成，不达标就削减后续功能 |
| 模型费用过高 | Token或并发快速上升 | 上下文预算、缓存、限流、模型分级和费用告警 |
| 需求不断增加 | 每周新增功能多于完成 | 新需求进入下一阶段清单；当前周只接受P0问题 |

## 13. 范围控制

10周班级试用版暂不包含：复杂多Agent自治协作、自动发布AI题目、全量知识图谱、Kubernetes、多学校多租户计费、自训练大模型、无人工审核的正式主观题评分、临床心理诊断或危机干预服务。

如果进度落后，按以下顺序降级：

1. 保留课程、教材、基础测验、文字RAG、引用和权限。
2. 保留AI教师基本状态机，减少个性化策略数量。
3. 图文高级解析改为教师手工绑定重点图片。
4. 出题Agent只支持单选与简答候选。
5. 学习画像只用可解释规则，不上复杂算法。
6. 暂缓长期记忆自动写入，但保留学习事件和人工复习。

不能降级的内容：服务端权限、教材版本、引用定位、无依据拒答、题目人工审核、日志脱敏、备份和恢复。

## 14. 最终交付清单

### 主线A交付

- 教师与管理员Web功能。
- 课程、成员、教材、知识库、引用、题库和出题Agent接口。
- 数据库迁移、解析与检索评测集。
- Docker部署、监控、备份、恢复和运维手册。

### 主线B交付

- 学生Web功能和AI学习工作区。
- 教学状态机、题目教练、分支对话、测验、记忆、画像和统计接口。
- E2E测试、试用脚本、用户反馈表和已知问题清单。

### 共同交付

- 可运行源代码与固定依赖版本。
- OpenAPI、事件契约和调用示例。
- 课程演示数据、教师账号和学生账号。
- 测试报告、RAG评测报告、安全检查表和发布记录。
- 数据采集说明、隐私说明、故障处理和回滚方案。

## 15. 开始开发前的最终检查

- 两个人已明确A/B身份和模块归属。
- 已建立仓库、任务看板和共享密码/密钥管理方式。
- 已准备一份合法可用的真实教材样本和教师确认的30个测试问题。
- 已决定试用服务器、域名、模型提供方和预算上限。
- 已确认学生数据的保存期限、教师可见范围和删除流程。
- 已逐条确认第7章接口，未确认的字段不得直接编码。
- 已约定第3、5、7、9周集成门槛不通过时的删减规则。

以上检查完成后，第1周正式开始。
