# V3.2：可恢复上传与持久教材任务执行计划

> 状态（2026-09-26）：§1—§6 主体代码与 §7.1—§7.4、§7.6 测试验证已完成；§7.5 的 Worker 真实链路冒烟已完成（分片直传 + Celery 解析连续两次 succeeded），真实“中断续传 + 解析重试”人工冒烟仍待做；前端“暂停”按钮与后台任务区心跳/尝试次数展示尚未实现（当前已有恢复会话提示与总进度）。
>
> 实施中发现并修复的关键问题：Celery 任务此前每次 `asyncio.run()` 会关闭事件循环，全局 async engine 连接池在第二个任务复用已关闭循环上的连接并崩溃；已新增 `app/core/task_loop.py` 持久循环（`materials.parse` / `knowledge.embed` 均改用），并配 `tests/test_task_loop.py` 回归。陈旧任务扫描与安全重派发见 `app/core/job_recovery.py` 与 `scripts/requeue_stale_jobs.py`（支持 `--dry-run`）。

## 1. 依赖与配置

1. 在 Python 项目声明 `boto3`（MinIO Multipart 预签名）和 `celery`。
2. 增加 `TASK_BACKEND`、Celery broker/result URL、上传 Session TTL、分片大小、任务心跳和陈旧阈值配置。
3. 为本地 Docker Compose 增加 worker 服务；Windows 启动脚本增加受管 Worker 进程。
4. 测试环境固定 `TASK_BACKEND=in_process`。

## 2. 数据迁移

1. 新建 `upload_sessions`：文件元数据、临时对象键、upload ID、状态、过期时间、配额预留、最终资料/版本引用。
2. 新建 `upload_parts`：Session、Part 序号、ETag、大小、完成时间，保持唯一性。
3. 扩展 `jobs`：心跳、尝试次数、检查点、执行后端。
4. 为 Session 状态、课程、创建者及 Job 心跳创建索引与约束。

## 3. MinIO Multipart 适配器

1. 封装 create/presign-part/complete/abort/head-object 操作。
2. 仅临时对象使用 Multipart；完成后用同一对象键作为版本源文件或服务端 Copy 到不可变版本键。
3. 完成时流式计算 SHA-256，不把大教材整体读入内存。
4. 失败时中止临时 Multipart，记录可操作错误。

## 4. UploadSession 服务与路由

1. 创建 Session 时进行鉴权、预校验、配额预留和幂等控制。
2. 分片 URL 请求验证范围、过期和 Session 所属教师。
3. 完成分片记录 ETag，不信任浏览器传入的总进度。
4. 完成 Session 时校验连续分片、对象长度、Hash、重复教材和真实配额，创建版本并审计。
5. 取消与过期清理释放预留额度。

## 5. 持久任务派发

1. 新建 `task_dispatcher` 与 Celery 应用。
2. 解析、索引 Router 从直接 `asyncio.create_task` 改为调用派发器。
3. 任务函数更新心跳、检查点、尝试次数和失败可重试信息。
4. 实现陈旧任务扫描与安全重派发命令。
5. 不修改 Chunk/检索构建的原子替换逻辑。

## 6. 前端

1. 以 UploadSession API 替换 XHR 单次上传。
2. 按 8MB 分片上传并显示总进度、Part 重试、暂停、恢复和取消。
3. 本地保存 Session ID，重进页面后发现并恢复未完成上传。
4. 后台任务区显示 Worker 后端、心跳、尝试次数和“可重试”。
5. 明确区分“上传暂停”与“服务端解析任务继续运行”。

## 7. 测试与验证

1. 服务层单元测试 MinIO 适配器和 Hash/配额逻辑。
2. API 测试 Session 生命周期、权限、重复 Part、缺失 Part、取消、过期和最终化。
3. 任务测试 in-process fallback、Celery 任务签名、心跳和陈旧重派发。
4. 前端测试分片协议、恢复提示和状态文案。
5. 在 MinIO/Redis 本地运行 Worker，进行一次真实 PDF 中断续传与解析重试冒烟。
6. 执行迁移、OpenAPI、完整后端测试、前端类型/构建与浏览器验收。
