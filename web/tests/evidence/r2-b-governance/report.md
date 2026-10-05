# R2-B 管理员治理验收记录

日期：2026-10-04  
环境：`psychology_learning_v1_r2_b_test`、`psychology_learning_v1_r2_b_e2e`、Redis DB9、Web `3202`、API `8202`；浏览器使用可见 Chrome。E2E 账号、班级和任务均为隔离库中的合成数据。

## 验收结果

- 后端管理员治理与权限回归：`19 passed, 3 warnings`（3 条为 Starlette/httpx 弃用及 pytest cache 写入告警）。
- 前端 Node 测试：`41 passed, 0 failed`；TypeScript `pnpm typecheck` 通过；治理改动涉及文件的 ESLint 通过。
- 真实浏览器 E2E：`11/11` 检查通过，报告见同目录 `result.json`。通过真实 API 覆盖概览读取、loading、请求中断后重试、管理员资料读取边界、跨机构 404、窄屏只读、双会话 IAM 409、IAM 授予、创建班级、课程/班级成员、任课分配、任务版本化重试、审计查询与无数据、非管理员 403。唯一网络故障注入是在浏览器端延迟/中断一次 API 请求；恢复请求仍到达真实 API，没有用 API 响应 mock 替代验收。
- E2E 最终库状态核验：班级/课程成员和任课关系均为 active；失败任务经受控重试转为 `queued`、版本 4；写操作可在审计日志中查询。

截图：`01-overview-live.png` 至 `11-audit-empty-state.png`。报告保留预期的 404、409、403 作为权限与冲突验收证据。

## 待主窗口交接的问题

真实浏览器先复现了一个超出 R2-B 前端所有权的共享后端故障：同一 `RoleAssignment` 撤销后再次授予，`POST /api/v1/admin/role-assignments` 返回 500 `MissingGreenlet`。堆栈落在 `memory/router.py` 的 `_role_assignment_data` 序列化读取 `assignment.updated_at`；重激活路径更新并 flush 记录后，该属性已 expired，序列化触发了同步隐式加载。

复核当前工作树后，该失效序列仍在 `server/app/modules/memory/router.py` 的 1183–1187 行，现有 `server/tests/test_admin_governance.py` 未覆盖撤销后重授。建议在异步 flush 后显式 `await db.refresh(assignment)` 再序列化，并新增回归：撤销后以同一 Scope 重授返回 201、版本递增；相同幂等键重放不新增授权和审计，已有效授权的第二次新操作返回 409。

R2-B 没有修改共享后端路由、模型、迁移、OpenAPI 或公共测试配置。修复需要主窗口交接 `server/app/modules/memory/router.py` 及相应后端回归测试的文件所有权。此缺口关闭前，不把 IAM 撤销后重新授予场景报告为验收通过。
