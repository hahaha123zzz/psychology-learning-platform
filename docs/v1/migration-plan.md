# V1 数据与路由迁移方案

## 1. 迁移原则

历史迁移只读；所有新结构新增向前迁移。每批采用 expand → backfill → verify → switch → contract。先关闭新入口，再清理旧实现；不删除 MaterialVersion、PublicationSnapshot、历史作答、原始证据或引用。

## 2. 结构迁移批次

| 批次 | 新结构 | 旧结构处理 | 切换条件 |
| --- | --- | --- | --- |
| M1 | RoleAssignment、Scope、Class、ClassMember、Outbox、Pack/CourseRelease | CourseMember 保留并建立映射 | 授权回归和双读对账通过 |
| M2 | CompilerManifest、固定快照、EvidencePointer、Domain 对象 | MaterialVersion/KnowledgeObject 继续作为底层来源 | 固定页和引用抽检通过 |
| M3 | LearningEvent、Qualification、Evidence 维度、LearnerModel、ReviewState；Mastery 按独立证据和跨情境门槛回算（迁移 `0028/0034`） | 旧 LearningEvidence/Mastery 只按可证明字段映射；旧 mastered/proficient 不满足新门槛时降级为 learning，并记录算法版本/理由 | 重放结果与原记录对账；受提示答对不冒充独立证据 |
| M4 | Task/Episode/Policy/Activity/Intervention | LearningSession 适配读取 | 新任务可暂停恢复 |
| M5 | RubricVersion、AssessmentRelease、ScoreRecord | 旧 Assessment 保留兼容读取 | 正式测评全链通过 |
| M6 | TeachingAsset/Lab/Designer Draft | 无同义旧对象时全新建模 | Contract validator 和发布 Gate 通过 |

## 3. 旧数据处理

旧 `correct_ratio` 不直接转换为 `mastered`。缺少证据维度、独立性或来源时映射为 `evidence_insufficient` 或保留 legacy 状态并不参与新晋升。旧材料发布记录不伪造新的 `CourseRelease`；只有新 Compiler 成功构建后建立绑定。

旧路由在权限校验后做有意义的适配：已有 Task、Branch、Attempt、Citation 不能一律跳首页。教师材料页面逐步转为只读内置教材入口；直接上传/解析/索引命令在 P2-08 关闭。

## 4. 回退与清理

回退优先关闭 feature flag、切回 Last Known Good 和兼容读模型。数据库不使用 destructive downgrade。删除只对明确授权范围执行：停用会话、删除或不可逆匿名化个人记忆、清理索引/cache，并写入可核验的删除任务/回执；机构依法保留的成绩/审计单独最小化保存。当前首切片只同步清理有明确删除边界的数据，并把待机构决定的学习证据列为保留，不能据回执宣称完整删除。

## 5. 迁移对账

每次 backfill 输出：记录数、主键映射数、孤儿数、重复 hash、跨课程引用、release/version 绑定和失败样本。对账失败时停在 verify，不切换新读写路径。运行中的任务和正式测评必须在迁移期间固定原 release。
