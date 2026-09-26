# V3.2：可恢复上传与持久教材任务设计

## 目标

将教材处理从“浏览器单次请求 + FastAPI 进程内 `asyncio` 任务”升级为：

```text
浏览器分片直传 MinIO
→ UploadSession 持久化上传状态
→ 完整性验收并创建 MaterialVersion
→ Celery Worker 执行解析/索引
→ PostgreSQL 记录心跳、重试与阶段检查点
```

目标是解决断网、切页、浏览器关闭和 API 服务重启导致的上传或后台任务丢失。教材正文仍只存 MinIO；数据库只存状态、校验信息和对象键。

## 非目标

- 不引入 OCR、Docling、MinerU 或视觉检索。
- 不修改教材知识对象、Chunk 或 RAG 的现有契约。
- 不承诺 PDF 页级断点恢复。现有解析器一次接收完整字节并在内存内解析；真正页级恢复需要新的逐页 Parser Adapter，列入 V3.3。
- 不把 MinIO 密钥暴露给浏览器。

## 上传设计

### UploadSession

新增持久对象，状态为：

```text
created → uploading → uploaded → verifying → completed
                         ↘ failed / cancelled / expired
```

字段包括课程、教师、资料元数据、文件总大小、分片大小、MinIO multipart upload ID、临时对象键、SHA-256、已完成分片及失效时间。

### 安全边界

1. 教师请求创建 Session，后端验证课程权限、文件名、允许类型、文件上限和课程配额预留。
2. 后端通过 S3-compatible MinIO Multipart API 创建临时上传，并只为指定 Part 签发短期预签名 URL。
3. 浏览器直接 PUT 单一分片到 MinIO；不获得永久密钥或 Bucket 列表权限。
4. 浏览器提交分片 ETag 后，后端记录 `UploadPart`。
5. 后端在完成时重新核验完整分片序列、对象大小和 SHA-256；验收通过才原子创建 `Material` / `MaterialVersion`。

取消或过期会终止 MinIO Multipart Upload，并释放数据库的配额预留。

### 前端恢复

浏览器将未完成 Session ID 记录在本地。重新进入教师工作台时读取未完成 Session，向后端取得已完成分片，续传缺失 Part。页面可以切换；浏览器关闭后可从 Session 继续。不会伪造“后台上传”：只有浏览器仍在运行时才会继续传输。

## 持久任务设计

### 任务派发

开发和生产均可配置：

```text
TASK_BACKEND=celery | in_process
```

- `celery`：API 创建数据库 Job 后发送 Celery 任务，Redis 作为 broker/result backend，独立 Worker 执行。
- `in_process`：保留给自动化测试和无 Worker 的离线开发；不可被描述为可恢复任务模式。

统一派发器隐藏两种模式，业务 Router 不直接依赖 Celery。

### Job 状态与恢复

扩展既有 `Job`：

- `last_heartbeat_at`
- `attempt_count`
- `checkpoint` JSON
- `worker_backend`

Worker 进入每个阶段更新心跳和检查点。Worker 异常后任务标记失败并可重试；应用启动或管理命令可重新派发超时的 queued/running Job。重试总是从 MinIO 的不可变版本源文件重新执行，保证幂等，不覆盖已发布版本。

解析和索引保持当前的“先完整构建新结果，成功后替换旧索引”语义。

## 本期接口

- `POST /courses/{course_id}/upload-sessions`
- `GET /upload-sessions/{session_id}`
- `POST /upload-sessions/{session_id}/parts/{part_number}/url`
- `POST /upload-sessions/{session_id}/parts/{part_number}/complete`
- `POST /upload-sessions/{session_id}/complete`
- `POST /upload-sessions/{session_id}/cancel`
- `GET /courses/{course_id}/upload-sessions?status=...`

现有直接上传接口保留兼容，但教师前端切换到 UploadSession 协议。现有解析、索引 API 不变。

## 验收

- 20MB 以上文件可被人为中断后恢复，不重复上传已完成分片。
- 无权教师、学生和跨课程用户不能读取或完成其他人的 Session。
- 无效 Part、缺失 ETag、错误总大小、过期 Session 都不能创建教材版本。
- 完整上传后仅创建一个不可变版本，并保留 SHA-256 重复检测。
- Celery 模式下 API 重启不取消已派发任务；任务心跳与重试信息对教师端可见。
- `in_process` 测试模式维持现有测试稳定性。
