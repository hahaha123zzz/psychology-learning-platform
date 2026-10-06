# 学生端 V1.2 实施追踪

更新时间：2026-10-06。本文把《实验心理学智能学习平台-学生端完整设计文档-V1.2.md》的实施优先级转换成持续验收台账；需求含糊或与现行代码冲突时，先记录差异，再由 CTRL 冻结最小兼容合同。

当前集成状态：V0.9 合成 seed 已补齐 V1.2 必需的独立课程审核、不可变 CourseRelease、班级成员和 Release assignment。隔离 API/Web 已运行。全量后端 385/385、前端 Node 85/85、TypeScript、ESLint、OpenAPI 156 paths 语义比较、Alembic check 均通过；EVID/TUTOR 两个新增定向用例集成后 2/2 通过。TUTOR-009 的偏好影响 SSE 回归在任务分支 1/1 通过并已集成，尚待 schema 变更完成后重跑集成树。Home→任务恢复 1 次、TableExplain→Citation→Reader 使用 3 个独立空 session 连续通过 3 次；Practice→Review、Growth/Preference、Figure 位置-only 各通过 1 次。以上仍是分段验收：§42 的 5 道题、Hint/Correction/Repair、三轮全链路尚未闭合，不得据此关闭全计划。

## 完成口径

每个可实施条目依次核对设计、现有契约、后端、前端、迁移、自动化测试、浏览器证据和可重复隔离数据。已有代码或局部测试不等于端到端关闭。真实教材/学生数据、外部模型调用、真实班级/学习效果和生产运行须有单独授权及验收；未获授权的工作保持禁用或标为外部阻塞，不以虚构 fixture 代替。

## 实施主线

| 顺序 | 设计章节 / 能力 | 当前集成判断 | 关闭所需证据 |
|---|---|---|---|
| 1 | §5–8 Home、双模式 Learning、Reading Studio、SelectionContext | 部分；UI-010 合成 Home→Current Task→Learn 精确 restore 浏览器 1/1；UI-011 正在审偏好回流与 SelectionContext | 本人课程 Scope 的 API+浏览器闭环；深链刷新/切课恢复；对象选择仅发送服务端持久 ID；键盘/响应式回归 |
| 2 | §9–14 Tutor Runtime、Policy、Preference、LearningResponse、Block Registry | 部分；固定 Release 下 TableExplain→Citation→Reader 3/3；TUTOR-008 回放用例与集成重跑覆盖提交后丢 done、精确引用、幂等和失效 pin；TUTOR-009 偏好 SSE 路由测试 1/1 已集成 | 策略对 EXPLAIN/HINT/EXAMPLE/MICRO_CHECK/MISCONCEPTION_REPAIR 的确定性路由、质量/拒答、集成偏好回归重跑、正式测评隔离 |
| 3 | §15–20 QuestionBlock、Practice、Assessment 隔离、Review、错题/误区 | 部分；Practice→Review 单题浏览器链 1 次通过；V0.9 已修正未来 due 任务行为 | 四题型/五交互题 Practice Session API+UI；WrongAnswerTrace→Review 的来源与调度解释；Hint/Correction/Repair 闭环；Assessment Policy 不泄题；到期/未到期与重复提交端到端覆盖 |
| 4 | §21–23 Growth、我的、甲方需求映射 | 部分；Growth/Preference/Notification 已接入，报告仍缺完整证据解释闭环 | 每项学生状态显示来源、时间、支持证据与失效语义；学生隐私范围；无伪精确分数或稳定人格标签；课程间 Scope 浏览器负例 |
| 5 | §24–30 Supplementary Resource、Projection、对象模型、Evidence、Workflow、Tool Registry | 部分；发布版本、EvidencePointer、PDF Reader、检索基础已实现；Reader GET 返回已鉴权 pointer 的 course_id，撤权负例已覆盖；EVID-010 正在实现精确 snapshot/index/domain pin | ContentEvidence/LearningEvidence 分轨；Claim 四态与有界补检索；对象关系与可恢复 Workflow/工具权限；caption/nearby text citation 与同一发布/材料版本 |
| 6 | §26–28 Figure/Table/Equation 与基础图文 QA | 部分；原生 Table 本地解释 3 次并经同一 Reader 指针引用，Figure 空表示为位置-only；高级视觉未实现 | Table caption/nearby text 可追溯回答；无公式或视觉语义臆断；合成对象 API+浏览器闭环和明确降级覆盖 |
| 7 | §31–34 Mini Lab、TeachingAsset、Student Model、Learning Memory | 部分；通用六阶段 Lab、资产白名单、Mastery/Memory 基础存在 | 任务恢复/作废规则；资产发布版本和 Evidence；多知识/误区/技能状态的来源、冲突、衰减；HintDependency 仅以合格多轮证据形成；记忆分层/删除测试 |
| 8 | §35–38 Contract、SSE、Release pin、权限 | 持续审计；迁移 0051 与现行服务已有多个切片 | session/run 固定 Release、Material/Question/Asset 版本；Branch 继承与幂等 merge；SSE 恢复；撤权后重鉴权；OpenAPI/迁移/并发回归 |
| 9 | §42–48 黄金链、seed、优先级、页面改造、测试策略 | 部分；可重复本地 seed 已含固定 Release 与班级指派，运行环境已就绪 | 从专属空库可重复准备数据；脚本隔离核验；前后端 gate；连续三轮真实本地浏览器演示并保存报告 |
| 10 | §56 后续路线：实验心理学工作流→高级多模态 | 部分/分期实施；通用 Case、Mini Lab 在先；真实实验内容待输入 | 实验工具 Schema/校验和人工审核闭环；至少 2–3 个获准模板才做课程内容验收；高级视觉路线先有可复现评测集和基线再决策，不把候选模型视为已交付 |

## 本轮已集成的增量

| 能力 | 集成提交 | 验证与剩余限制 |
|---|---|---|
| Practice 未到期 Review 项呈现与安全浏览器脚本 | `590d929`、`fbe2f67`、`edda2f9` | Node、TypeScript、lint、build、脚本语法通过；业务浏览器受隔离 API/数据库/Redis/MinIO 未运行阻塞 |
| Growth 按课程过滤 Review、Preference UI 修改/恢复脚本 | `2d9b606`、`f20ace2` | 静态与全前端检查通过；真实持久化浏览器受服务不可用阻塞 |
| Reader→Learn 原生 Table 指针 handoff 和 Tutor 本地 TableExplain | `d419afc`、`c716cbe`、`6a89bcf`、`69a3fea`、`651d3be` | 静态/API schema 检查通过；Tutor 数据库 route test 与真实浏览器受服务不可用阻塞；Figure 仍为位置提示 |
| Figure Reader 的位置-only UI 合同断言 | `56bd770` | 定向测试 4/4 通过；未做 live 浏览器 |
| Tutor 精确 pinned table_cells IndexJob 鉴权与安全重放标记 | `5672332` | 合成 Tutor 测试 7/7；TableExplain→Citation→Reader 浏览器 1 次通过；真实教材未访问 |
| Growth skill 状态不再伪装 KnowledgeState | 当前 CTRL 工作树 | 专项隔离 DB 测试 1/1；skills 暂为空，直到存在独立 DomainSkillState 来源 |
| Reader 固定指针恢复包含服务端鉴权后的 course_id | 当前 CTRL 工作树 | Reader/Search API 测试 2/2；绑定 Release 合成会话浏览器闭环通过 |
| Reader metadata 撤权负例 | `2d4588a` | EVID-009 源提交 `d69422d`；撤权前 GET 200、撤权后 GET 404；与 pointer `course_id` scope assertion 一同集成，定向用例在集成树通过 |
| Tutor Table turn 丢失 done 后的安全重放 | `748fef9` | TUTOR-008 源提交 `f0870aa`；答案/引用/TableExplain/turn_id 重放一致、只写一对 ChatTurn、内容冲突 409、dangling snapshot 404；与 Reader 负例合并后定向 2/2 |
| Home 与三次 Table 浏览器闭环 | 当前 CTRL 工作树 | UI-010 Home task restore 只读浏览器 PASS；UI-007 使用三个独立 synthetic session 连续 3/3；Practice/Review、Growth/Preference、Figure 分别 1 次，不代表三轮完整 §42 链 |
| V1.2 合成 seed 的 CourseRelease/班级绑定 | 当前 CTRL 工作树 | 专属 DB 连续运行 2 次，复用 course/material/assessment/release/class IDs；浏览器实践链基于绑定 Release 验证 |

## 当前进行中

| 任务 | 负责人 | 目标 | 状态 |
|---|---|---|---|
| UI-009/010 | UI | §5–8 Home→Learn 连续性审计与 Home CTA 实测 | UI-009 源码审计无代码；UI-010 脚本 live PASS，静态 Node 测试并入前端 suite |
| EVID-009 | EVID | §24–28 Reader pointer metadata 撤权负例 | DONE 源 `d69422d`，集成 `2d4588a`；定向 1/1，集成后 2/2 |
| TUTOR-008 | TUTOR | §9/11/13/36 固定 Release 下 SSE 幂等回放与中断边界 | DONE 源 `f0870aa`，集成 `748fef9`；定向 1/1，集成后 2/2 |
| UI-011 | UI | §5–8/42 Home、SelectionContext 与偏好回流审查 | 进行中；只允许合成数据，不改 API/schema/provider/migration |
| EVID-010 | EVID | §24–30/42 对象来源、caption/nearby text 与 Reader 版本闭环 | 进行中；先审计最小缺口，合同变化等 CTRL 决策 |
| TUTOR-009 | TUTOR | §9–14/42 偏好对服务端 Tutor 展示策略的确定性影响 | DONE，源 `da26d89` / 集成 `1c5795a`；saved preference→SSE 1/1、block 纯函数 7/7；集成树路由回归待迁移完成后重跑 |
| CTRL-PRACTICE-SEED-001 | CTRL | §42 五题 Practice 与错答→Review 合成闭环 | 已冻结 seed 合同；新增不可变五题 Assessment/CourseRelease，旧版本不变；仅内部确定性评分 |

## 明确的未来/输入门槛

- 未获逐项授权的教材正文、图像、表格不得发往外部模型；当前 V1.2 Demo 固定使用本地合成资料与 internal provider。
- 真实课程教材/实验教案、机构对学生隐私与成绩的可见/保留政策、获准 AI 评分答案及供应商条款均等待输入。
- 生产部署、监控告警、备份恢复、容量/性能、真实教师/班级和学习效果验证按当前项目指示保留为未来范围。
- OCR、扫描 PDF、MinerU/Docling 全集成、复杂表格恢复、可靠公式恢复、Visual Embedding、ColPali/ColQwen 不因基础 Figure/Table 工作而自动纳入本轮已完成范围。

## 后续控制规则

1. CTRL 按本表拆为可审查的 30–90 分钟增量，独立 worktree 提交后逐项审查和集成。
2. 每个 DONE 同时写源 SHA、改动范围、测试、未运行的验证和原因；合并后对集成树重跑受影响测试。
3. 若发现合同缺口，先由 CTRL 追加 DECISION，再让窗口实现；不可隐式改变 API、数据或状态语义。
4. 直到所有可实施条目达到代码/迁移/契约/测试/浏览器/隔离数据所需证据，且所有外部输入和明确未来范围被准确记录后，才能关闭本目标；这不等同于宣称 V1 全系统、真实班级或生产验收通过。
