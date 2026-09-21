# Windows 一键本地开发启动设计

## 目标

将 Windows PowerShell 下的日常本地开发启动收敛为一条命令：

```powershell
.\scripts\dev.ps1
```

该命令启动 PostgreSQL、Redis、MinIO、FastAPI 和 Next.js，并给出可访问地址、日志位置和停止方式。

## 范围与边界

- 仅支持 Windows PowerShell；不新增 macOS/Linux 兼容层。
- 保留 `scripts/dev-api.ps1`、`scripts/dev-web.ps1` 作为单服务排障入口。
- Docker 仍只承载 PostgreSQL、Redis、MinIO；API 与 Web 保持宿主机热更新开发方式。
- 自动创建缺失的 `.env`，来源固定为 `.env.example`，不改写已有 `.env`。
- 不运行迁移、种子或 G0 冒烟；它们仍应由开发者显式执行，避免一键启动产生不可预期的数据写入。

## 组件与数据流

### `scripts/dev.ps1`

1. 确认 Docker、Python、pnpm 可用；缺失时以诊断信息退出。
2. 当 `.env` 缺失时复制 `.env.example`；已有文件不修改。
3. 执行 `docker compose up -d postgres redis minio`，并按 Compose 健康检查轮询至可用或超时。
4. 调用既有 `dev-api.ps1`、`dev-web.ps1` 所使用的安装约定：后端虚拟环境缺失时初始化，前端 `node_modules` 缺失时安装。
5. 对 8000、3000 检查占用状态：若已由本启动器管理则复用；若被未知进程占用则明确失败，避免静默连接错误服务。
6. 在后台启动 API 与 Web，PID 写入 `tmp/dev/`，标准输出和错误输出写入 `logs/dev/`；启动器退出后服务继续运行。
7. 输出 URL、状态、日志路径和停止命令。

### `scripts/dev-stop.ps1`

- 只读取并终止 `tmp/dev/` 中由 `dev.ps1` 写入的 PID。
- PID 记录缺失、进程已经退出或 PID 被复用时给出提示并安全跳过。
- 默认不停止 Docker Compose 依赖，不删除卷、不清理数据库数据。

## 失败语义

- Docker 未启动、依赖健康检查超时、端口冲突、依赖安装失败时，`dev.ps1` 非零退出，并指明下一步排查命令。
- 后台 API/Web 在启动后立刻退出时，保留日志并输出具体日志路径。
- 脚本不记录或打印 `.env` 中的密码、Token 或连接串。

## 验证

- 用 Pester 或等效的 PowerShell 结构测试覆盖：`.env` 不覆盖、命令构造、PID 文件隔离、未知端口冲突拒绝、停止脚本不触碰 Docker。
- 在具备 Docker 的 Windows 开发机进行一次手工验收：首次启动、重复启动、查看日志、停止 API/Web、再启动。
- README 将日常启动命令更新为一条命令，同时保留拆分启动说明。

## 不在本次范围

- 生产部署、Docker 化 API/Web、跨平台启动器、自动迁移/种子、删除容器/卷、修改现有服务的监听端口。
