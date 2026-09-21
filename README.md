# 实验心理学智能学习平台

面向《实验心理学》课程的B/S智能教学平台。当前仓库处于基础框架阶段，采用模块化单体结构，为后续教材解析、可信RAG、AI教师、题目教练和学习记忆提供统一底座。

## 目录

```text
web/          Next.js浏览器端
server/       FastAPI服务端
contracts/    OpenAPI与跨模块事件契约
infra/        Nginx、监控和部署配置
scripts/      Windows开发脚本
docs/         设计与执行计划
```

## 本地启动

在 Windows PowerShell 中运行：

```powershell
.\scripts\dev.ps1
```

该命令首次自动创建 `.env`，启动并等待 PostgreSQL、Redis、MinIO，然后在后台启动 API 和 Web。若未安装全局 pnpm，会通过 Node.js 自带的 Corepack 在项目临时目录中准备锁定的 pnpm 版本。访问前端 `http://localhost:3000`，API 文档 `http://localhost:8000/docs`。

- 查看日志：`Get-Content .\logs\dev\api.err.log -Wait` 或 `Get-Content .\logs\dev\web.err.log -Wait`
- 停止 API/Web：`.\scripts\dev-stop.ps1`（不会停止 Docker 依赖或删除数据）
- 排障时可分别运行 `scripts\dev-api.ps1`、`scripts\dev-web.ps1`，或执行 `docker compose ps`

## G0 冒烟验收

新环境初始化后运行以下命令，应在30分钟内全部通过：

```text
docker compose up -d
server\.venv\Scripts\python.exe scripts\g0_smoke.py
```

脚本依次执行：数据库迁移、迁移与模型一致性检查（alembic check）、OpenAPI契约漂移检查、演示数据种子、API核心业务流（登录→幂等建课→版本冲突→me→登出）。

演示账号（由种子脚本创建）：

- 教师：`teacher@demo.edu` / `demo-password-123`
- 学生：`student@demo.edu` / `demo-password-123`

## 当前可用能力

- Next.js学生、教师和管理员工作区骨架。
- FastAPI统一配置、请求ID、`data/meta`响应封套和`error{code,details,retryable}`错误体。
- 用户、认证会话、课程、课程成员、审计日志、幂等记录数据模型与Alembic迁移。
- 平台账号登录/刷新/登出/me，HttpOnly Cookie，登录失败按账号+IP限流。
- RBAC课程权限：教师建课、成员管理、越权统一404防资源枚举。
- 课程创建幂等键、更新乐观锁（409带版本详情）、成员变更全量审计。
- PostgreSQL、Redis、MinIO本地开发依赖；GitHub Actions双端CI。
- Pytest后端契约测试与Node前端基础测试。
- G0冒烟脚本（迁移检查、契约漂移、演示数据、业务流）。

教材上传与解析、RAG检索、AI教师等能力将按执行手册在后续任务中实现。
