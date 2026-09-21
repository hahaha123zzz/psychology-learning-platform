# Windows 一键本地开发启动实施计划

1. 新建 `scripts/dev-common.ps1`：集中处理运行目录、PID 记录、端口检测、Docker 健康检查和进程安全停止。
2. 新建 `scripts/dev.ps1`：初始化 `.env`、启动并等待依赖、校验端口、后台启动 API/Web、输出访问与日志信息。
3. 新建 `scripts/dev-stop.ps1`：仅停止具备匹配启动时间记录的受管 API/Web 进程，不停止 Docker。
4. 补充 Pester 结构测试，覆盖资产路径、PID 身份校验、端口冲突语义和停止范围。
5. 更新 README 的日常启动、日志、停止和排障说明。
6. 在不依赖 Docker 的条件下运行 Pester 与 PowerShell 语法解析；Docker 实机启动另行标明环境验证状态。
