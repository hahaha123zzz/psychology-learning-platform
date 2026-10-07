# 学生端 V1.2 实施追踪

更新时间：2026-10-06。本文把《实验心理学智能学习平台-学生端完整设计文档-V1.2.md》的实施优先级转换成持续验收台账；需求含糊或与现行代码冲突时，先记录差异，再由 CTRL 冻结最小兼容合同。

当前集成状态：集成 HEAD 已含 0052，EvidencePointer 对新域检索结果固定 publication snapshot/index job/domain release，Reader 与 Tutor 按精确 pin 复验；旧三字段全空指针兼容，部分 pin fail closed。专属学生 Demo DB 已升至 0052，alembic check 无差异；OpenAPI 为 156 paths，导出快照与应用语义一致。完整后端基线回归 390 passed（早于 TUTOR-011 与学生搜索 Release pin）；新变更的 TUTOR 路由 5/5、搜索 Release pin 1/1 已在集成树干净退出，全仓 Ruff 通过。前端 Node 92/92、TypeScript、ESLint（0 error/2 既有 warning）、production build 24/24 均通过。合成 seed 可重复创建三名独立学生，三条 Home/Guided/Learn、TableExplain/Citation/Reader、五题 Practice/Review、Growth/Preference 与 Figure 位置-only 演示链已通过。UI-012 精确 pin Reader context 浏览器也已通过；测试诊断顺手收窄 Figure closure 关系为 previous/next，防止错误关系触发定位入口。V1.2 仍未关闭：Hint/Correction/Repair 策略闭环、通用 selection handoff、Claim/学习证据闭环、Mini Lab/资产与学习记忆来源/失效语义还需逐项审计实现。

## 完成口径

每个可实施条目依次核对设计、现有契约、后端、前端、迁移、自动化测试、浏览器证据和可重复隔离数据。已有代码或局部测试不等于端到端关闭。真实教材/学生数据、外部模型调用、真实班级/学习效果和生产运行须有单独授权及验收；未获授权的工作保持禁用或标为外部阻塞，不以虚构 fixture 代替。

## 实施主线

| 顺序 | 设计章节 / 能力 | 当前集成判断 | 关闭所需证据 |
|---|---|---|---|
| 1 | §5–8 Home、双模式 Learning、Reading Studio、SelectionContext | 部分；三个独立 synthetic task 的 Home→Guided→Learn→返回 3/3，零业务写入；方案 2 的持久会话入口已接入；UI-012 精确 Reader context live harness 通过 | 通用 text selection→持久 pointer→Tutor/Practice 的端到端合同、深链刷新/切课恢复、键盘与窄屏 Reader/SelectionContext |
| 2 | §9–14 Tutor Runtime、Policy、Preference、LearningResponse、Block Registry | 部分；固定 Release 下 TableExplain→Citation→Reader 三轮通过，SSE 丢 done 幂等和精确 pin 回归通过；course_qa 的偏好→SSE 通过；Guided mode 偏好仅改变展示（TUTOR-010）已集成 | EXPLAIN/HINT/EXAMPLE/MICRO_CHECK/MISCONCEPTION_REPAIR 的策略路由/质量拒答/多轮状态闭环；正式测评隔离 |
| 3 | §15–20 QuestionBlock、Practice、Assessment 隔离、Review、错题/误区 | 五题交互 UI/API 和三轮错答→到期 Review 完成；新题型为 single/multiple/true_false/short_answer/essay；错题使用固定题目版本 | Hint/Correction/Repair 闭环、错题来源/调度解释的完整投影、 Assessment Policy 全面防泄题与重复并发端到端 |
| 4 | §21–23 Growth、我的、甲方需求映射 | 部分；Growth/Preference/Notification 已接入，报告仍缺完整证据解释闭环 | 每项学生状态显示来源、时间、支持证据与失效语义；学生隐私范围；无伪精确分数或稳定人格标签；课程间 Scope 浏览器负例 |
| 5 | §24–30 Supplementary Resource、Projection、对象模型、Evidence、Workflow、Tool Registry | 部分；0052 以精确 snapshot/index/domain pin 固定新 pointer，Reader GET/page-image 和 Tutor 按 pin 校验；撤权负例覆盖 | ContentEvidence/LearningEvidence 分轨审计、Claim 四态与有界补检索、对象关系/Workflow/Tool 权限、caption/nearby text citation closure |
| 6 | §26–28 Figure/Table/Equation 与基础图文 QA | 基础对象闭环通过三轮；native Table 经固定 Reader pointer 可解释，Figure 无语义时只给定位与降级提示 | Caption/nearby-text 指针与 Citation 测试；无公式/视觉臆断；高级视觉仍需评测基线，不在当前合成 Demo 宣称内 |
| 7 | §31–34 Mini Lab、TeachingAsset、Student Model、Learning Memory | 部分；通用六阶段 Lab、资产白名单、Mastery/Memory 基础存在 | 任务恢复/作废规则；资产发布版本和 Evidence；多知识/误区/技能状态的来源、冲突、衰减；HintDependency 仅以合格多轮证据形成；记忆分层/删除测试 |
| 8 | §35–38 Contract、SSE、Release pin、权限 | 持续审计；0052 EvidencePointer pin 已集成，TUTOR-011 新 Guided session 与普通学生 Learn search 均使用 active assignment 的精确 CourseRelease/PublicationSnapshot/IndexJob/DomainRelease；集成树对应路由 6/6 通过 | session/run 固定 Release、Material/Question/Asset 版本的全矩阵；Branch 继承与幂等 merge；SSE 恢复；撤权后重鉴权；OpenAPI/迁移/并发回归 |
| 9 | §42–48 黄金链、seed、优先级、页面改造、测试策略 | 三轮独立合成学生链已通过并在 runbook 记录；seed 连续重跑复用课程、Release、班级与三项 Home task ID | 从专属空库重新准备的最后一次复验、完整回归结束后归档报告与复现命令 |
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
| EvidencePointer 精确发布 pin 与 Reader/Tutor 复验 | `3d95fe9` | EVID-010 源提交 `ff5cdc3`；0052 migration、OpenAPI typed GET、search pointer pin 持久化、历史 snapshot/partial pin 和 Table/Figure 授权 guard；集成树选定 7 项 pytest 通过 |
| Practice 五种交互题和独立 Review 完成路径 | `0db3c38` + 当前 CTRL 工作树 | seed 新建不可变五题 assessment/release；Practice 页面支持单选、多选、判断、简答、论述保存恢复；三学生均用错误单选生成并完成 due Review |
| 三轮 V1.2 合成学习闭环 | 当前 CTRL 工作树 | 三个隔离学生各自完成 Home/Guided/Learn、Table Tutor/Citation/Reader、Practice/Review、Growth/Preference、Figure 位置-only；详见本手册“本轮验收记录” |
| Home 与三次 Table 浏览器闭环 | 当前 CTRL 工作树 | UI-010 Home task restore 只读浏览器 PASS；UI-007 使用三个独立 synthetic session 连续 3/3；Practice/Review、Growth/Preference、Figure 分别 1 次，不代表三轮完整 §42 链 |
| V1.2 合成 seed 的 CourseRelease/班级绑定 | `0db3c38` + CTRL 工作树 | 专属 DB 连续运行 2 次，复用 course/material/assessment/release/class IDs；浏览器实践链基于绑定 Release 验证 |
| UI-012 Reader context closure 与 Release search pin 整合 | 4bd1e3a | TUTOR-011 5/5 + assigned search 1/1；Web 92/92、TypeScript、build、live synthetic UI-012 PASS；Figure previous/next 过滤修复已提交 |


## 当前进行中

| 任务 | 负责人 | 目标 | 状态 |
|---|---|---|---|
| UI-013 | UI | §8.2–8.4/§45.2/§48.3 键盘/窄屏 Reader 与持久 pointer 返回 Learn handoff | 已派发；只传 server-owned pointer ID，不新增自由文本 API/schema |
| TUTOR-012 | TUTOR | §11/§13–14/§20/§29 Hint→回答→Correction/Repair 与学习证据边界 | 已派发；确定性策略、合成回归、无 schema/provider 变化 |
| EVID-012 | EVID | §13/§27–30/§33–34 ContentEvidence/LearningEvidence 与 Claim 边界负例 | 已派发；优先补现有 contract 边界测试，DB13 串行排队 |

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

## 2026-10-06 16:40 +08:00 集成续记

当前集成 HEAD：`cece51de434ff8b8a0cbb4ea5b19fc01e24e3bdc`（demo/student-integration）。本轮集成：

- `0070459` EVID-013：Growth overview/tabs 只投影同学生/同课程、同知识点的最新有效 LearningEvidence metadata；仅当最新 evidence ID 与 MasteryState.last_evidence_id 精确匹配时返回五字段，否则 null。source 与集成 route tests 通过。
- `4d491a3` UI-014：Reader SelectionContext 以 sessionStorage 仅保存 `{course_id,evidence_pointer_id}`；按课程恢复，切课/清除时清理；重开 Reader 重新走授权 GET。集成 mock browser 验收通过。
- `cece51d` TUTOR-013：Branch assignment 轮换后 child Claim 仍验证父会话原 CourseRelease/PublicationSnapshot/IndexJob/DomainRelease pins；保留越权和撤权拒绝。
- `234ae54` CTRL：三轮合成 seed 的 pin/idempotency 固定；纠正 Tutor route test 对 request state_version 的断言；补齐 Learn 从 Reader 重开所选来源入口。

验证：DB14 全后端 `399 passed, 2 warnings`；Growth metadata route 定向 `1 passed`；Branch pin route 定向 `1 passed`；全仓 Ruff 通过；专属 Demo DB `alembic check` 无差异；OpenAPI 语义匹配 156 paths；Web Node `100/100`、TypeScript 通过、ESLint 0 errors/2 existing warnings、生产 build 24/24；UI-014 mock browser 刷新恢复/重新 GET/切课清理/零业务写入通过。服务端 pytest warnings 是上游 Starlette/httpx、anyio deprecation；定向 Growth run 另有 pytest cache 写权限 warning，不影响 exit 0。

未关闭项继续按 §44、§49 逐项派发：Guided Tutor policy/Hint/Repair 多轮资格、成长元数据 UI 投影、Mini Lab/TeachingAsset 来源和版本失效语义；之后再复核 Student Model / Learning Memory 的来源、冲突、衰减、删除与正式测评隔离。真实教材/真实学生、真实班级、外部模型和生产验收仍不在本 Demo 授权范围。

- `5f6b32c` UI-015（2026-10-06）：Growth 焦点与知识点列表只显示后端提供的最近有效证据 source/time/dimension/independence；`null`/缺字段显示原因未知，不推断；skills 继续明确为空。Node、TypeScript、ESLint source tests 通过；集成后完整构建/浏览器验证待本轮总回归。

- `9ddaf76` TUTOR-014 + `f441819` CTRL 测试预期修正（2026-10-06）：Event payload 只在服务调用前捕获的 `response_state` 为 check/practice 时进入证据资格化；hint/repair/show-example fail-closed。逐回合资格 worker 测试通过。一个延迟 worker 测试第一次因版本变更而得到 session_version_mismatch、非其写死的 response_not_evidence_bearing；已修正为断言所有状态 rejected 且无 Evidence/Mastery 副作用，集成 route tests 最终 2 passed。
- `6c1617f` EVID-014（2026-10-06）：MiniLab qualification 锁定服务端 session，并要求 server-derived measure 为 pending；已 qualified session 的不同 event_id 不能二次投影 LearningEvidence/Mastery。校验 owner/course/status/measure/invalidation/replay 与客户端 mastery 伪造边界。定向 DB tests 3 passed；不绑定 TeachingAssetVersion，因为当前 LAB_CATALOG 是独立 engineering_fixture。
- `f441819` UI-015 浏览器补验：集成 production build 的 Growth 证据元数据 mock browser 通过（有效元数据、null fail-closed、无私密文本、不推导技能、零写入）；测试文件已纳入 Node suite。
