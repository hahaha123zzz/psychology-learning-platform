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

1. 复制`.env.example`为`.env`并修改本地密码。
2. 启动依赖：`docker compose up -d postgres redis minio`。
3. 后端：运行`scripts/dev-api.ps1`。
4. 前端：运行`scripts/dev-web.ps1`。
5. 访问前端`http://localhost:3000`，API文档`http://localhost:8000/docs`。

## 当前可用能力

- Next.js学生、教师和管理员工作区骨架。
- FastAPI统一配置、请求ID、错误格式和健康检查。
- PostgreSQL、Redis、MinIO本地开发依赖。
- Pytest后端测试与Node前端基础测试。
- OpenAPI导出脚本和契约目录。

真实账号、课程、教材和AI能力将在后续任务中按执行手册逐步实现。

