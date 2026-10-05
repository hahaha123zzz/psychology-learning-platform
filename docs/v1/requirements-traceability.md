# V1 需求追踪矩阵

本矩阵把用户提供的《总体设计文档 V1》和《Frontend Specification V1》映射到实现批次。状态为“基线”表示设计已确认；“待实现”表示代码尚未承诺完成。

| 设计主题 | 目标合同 | 当前依据 | 实施批次 | 验收证据 |
| --- | --- | --- | --- | --- |
| 四工作区 | Student / Teacher / Course Designer / Admin，各自独立导航和 Scope | `web/components/WorkspaceRoleGuard.tsx`、现有 `/student` `/teacher` `/admin` | P1、P5、P6、P9 | 角色路由、资源越权、浏览器 E2E |
| 内置教材 | 普通教师没有上传/解析/索引/发布入口；Course Compiler 受控构建 | `materials/`、`PublicationSnapshot` | P2-01—08 | 固定快照 manifest、发布门禁、旧入口 404/403 |
| 固定证据 | Evidence Pointer 绑定 release、page、object、bbox | `knowledge/`、`materials/artifacts.py` | P2-03、P2-06、P2-07 | 版本引用、坐标变换、撤权后重新鉴权 |
| 有据检索 | 先权限/版本过滤，再 BM25/Dense/Fusion/Closure；不足时拒答 | `knowledge/query.py`、`fusion.py`、`adaptive.py` | P2-05—06 | Recall/NDCG、拒答、permission leak=0 |
| 有限学习任务 | CurrentLearningTask/TeachingSession/Episode，单回合单动作，可暂停恢复 | `LearningSession`、`tutor/service.py` | P4、P5 | 刷新恢复、非法转移、半回合不落长期状态 |
| 学习证据 | Raw Event → Qualification → LearningEvidence → Learner Model | `LearningEvidence`、`memory/service.py` | P3 | 来源、独立性、重复事件、失效重算 |
| 掌握与复习 | Mastery 多证据；ReviewState 独立到期 | `MasteryState`、`ReviewTask` | P3-03—04、P7-07 | 单错/单次高分不得强标签；延迟验证 |
| Memory | 只服务连续性和确认信息，分层、来源、冲突、删除 | `MemoryItem`、privacy router、`PrivacyDeletionRequest` | P3-05—06 | Branch 隔离、跨课程隔离、已删除/保留范围可核验；未完成项明确保留 |
| 专业推理 | IV/DV、操作化、混淆、设计、结果、重设计 | 当前无完整领域模型 | P2-04、P5-04 | 选择与理由共同资格化 |
| 教师闭环 | Attention → Diagnosis → Teaching → Intervention → Re-check | `analytics/router.py` 只有聚合 | P6 | 问题可解释、目标快照、即时/延迟效果 |
| 正式测评 | 独立 Shell、版本冻结、服务端时间、自动保存、AI Policy | `assessments/`、`Attempt` | P7 | 禁用绕过=0、幂等提交、人工成绩 |
| TeachingAsset | 白名单模板/动作、Evidence-bound、fallback、已发布才能运行 | `TeachingAssetVersion`、资产 Contract validator、`LearningBlockStream` 安全降级渲染 | P8—09 | 未发布/未知资产安全降级 |
| Mini Lab | Intro→Predict→Run→Data→Explain→Summary，实验数据与学习证据双轨 | 当前无完整 lab | P8 | 中断作废、RT 不转能力结论 |
| Release | Domain/Pedagogy/Assessment Pack + CourseRelease，Published 不可变 | `PublicationSnapshot` | P1-04、P9-04 | Diff/Gate/Impact、LKG、运行中版本冻结 |
| 审计和隐私 | 高后果动作 append-only；Admin 不继承教学数据 | `AuditLog`、auth dependencies | P1、P3、P7、P9 | 审计查询、日志脱敏、撤权回归 |

## 不可削减的硬门槛

权限前置过滤、版本绑定、Evidence 支持校验、教材外拒答、正式测评后端 AI Policy、Branch 隔离、人工评分、删除可验证性和核心 E2E 必须保留。高级视觉检索、自动偏好推断和复杂图谱不属于首期硬门槛。
