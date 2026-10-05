# 实验心理学智能学习平台 V1 设计交付包

更新时间：2026-10-02

本目录是两份 V1 原始设计文档的工程化配套交付包。原始文档仍是产品语义的最高来源；本目录把其中需要交给设计、前端、后端和验收人员执行的内容拆成可检查的合同。

## 设计基线

| 文档 | 用途 | 处理方式 |
|---|---|---|
| 《总体设计文档 V1》 | 产品范围、教学逻辑、领域模型、证据、权限、发布和评测 | 保留为总体语义基线 |
| 《Frontend Specification V1》 | 四工作区、页面、组件、响应式、无障碍和前端验收 | 保留为交互基线 |
| `docs/执行计划/06-V1总体迁移与实施执行计划-2026-10-02.md` | 分阶段实施、迁移、验证和依赖 | 作为实施顺序，不替代产品设计 |

## 本目录文件

- [requirements-traceability.md](./requirements-traceability.md)：需求、现状、实施批次和验收证据追踪。
- [backend-domain-spec.md](./backend-domain-spec.md)：领域边界、所有权、依赖方向和写入链。
- [api-state-contract-spec.md](./api-state-contract-spec.md)：公共响应、Projection、状态机和流式约束。
- [component-spec.md](./component-spec.md)：前端组件 Contract、Block Registry 和降级规则。
- [migration-plan.md](./migration-plan.md)：数据、路由、版本和回退迁移策略。
- [api-contract-catalog.md](./api-contract-catalog.md)：按工作区整理的 API/Read Model 目录，标明目标接口与当前实现差异。
- [state-machine-catalog.md](./state-machine-catalog.md)：教学任务、测评、发布、作答和证据状态的完整转移表。
- [acceptance-matrix.md](./acceptance-matrix.md)：按角色、硬边界、质量门槛和 E2E 路径的验收矩阵。
- [source-ledger.md](./source-ledger.md)：功能、开源项目/论文来源、许可证和代码复用登记。
- [visual/page-specs.md](./visual/page-specs.md)：11 组代表页面的高保真前置规格和四类页面状态。
- [implementation-status.md](./implementation-status.md)：截至当前工作区的已落地、已验证和未完成事项。

## 阅读顺序

1. 先读总体设计文档和 Frontend Specification，确认产品语义。
2. 再读需求追踪矩阵和后端领域规格，确认责任边界。
3. 读 API、状态机和组件合同，确认实现输入输出。
4. 读视觉页面规格和验收矩阵，确认设计与测试交付物。
5. 最后按迁移方案和详细执行计划实施。

## 状态标记

- **基线**：来自原始设计文档，实施必须遵守。
- **目标**：计划实现但当前代码可能尚未具备。
- **已实现**：已有代码、迁移或测试可直接证明。
- **待验证**：已有实现方向，但需要数据库、浏览器或真实教材环境验证。
- **明确不做**：V1 范围内禁止实现或不作为验收条件。

“已实现”不等于“生产就绪”；完成汇报必须同时说明代码、测试、环境、真实数据和生产验证层级。
