# 离散数学本地测试教材导入核验

日期：2026-10-05  
结论：**本地解析/检索管线回归通过；用户提供的离散数学原始教材尚未导入。** 阻塞点是输入为旧式 Word `.doc`，而当前运行树只注册 PDF/DOCX 解析器；本机本地 LibreOffice/Word renderer 不可用。没有转换、上传、索引、发布或向任何外部服务发送教材内容。

## 输入来源与文件确认

- 来源目录：`E:\项目\心里\TEXTBOOK\`。项目来源台账记录该目录为用户指定的本地构建/定位测试输入；原始文件保留原路径，未写入、覆盖或删除。
- 共 10 个文件，按文件名为第 1—10 章连续章节：集合代数、两个数学基本原理、计数、逻辑代数（上/下）、形式系统、图、特殊图、关系、函数。未发现另一组离散数学候选教材；据连续章次将其视为同一套分章教材。
- 10/10 文件头均匹配 OLE Compound File，扩展名与签名一致，格式为旧式二进制 Word DOC（非 DOCX）。文件名、字节数及逐文件 SHA-256 见 [`source-ledger.md`](source-ledger.md) 的 R2 本地教材输入登记。本次重算的 10 个 SHA 均与该台账一致且互不相同。
- 本地逐个调用真实格式识别与 `get_parser("application/msword")`：格式识别 `legacy_doc` 10/10；解析结果 `parser_unavailable` 10/10，10 个空占位对象、0 个非空对象。首文件解析前后 SHA-256 不变。

## 导入流程与安全边界

- 普通运行时 `MATERIAL_LEGACY_AUTHORING_API_ENABLED=false`。本地旧教师上传/解析/索引接口不是正式教师导入工作台；测试运行由 `server/tests/conftest.py` 仅在 pytest 子进程中显式打开此开关。没有全局开启开关。
- 当前 `get_parser()` 只对 `application/pdf` 和 OOXML DOCX 注册解析器；旧 DOC 会进入 `UnsupportedTypeParser`。材料服务因此无法为这些源生成真实知识对象/分块。质量门禁将 `parser_unavailable` 作为阻塞问题，索引入口也会因未解决的阻塞问题拒绝构建。
- `probe_local_renderer()` 实测 `available=false`、原因 `local_libreoffice_not_installed`。本机未检测到可用 LibreOffice/Word；本次不下载/安装转换器，不调用 OCR、外部文档处理、LLM 或 Embedding 服务。
- 没有启动 API 预览服务或 Celery Worker。pytest 通过 `TASK_BACKEND=in_process`；测试进程中的 Celery broker/result 显式指向隔离 Redis DB2，未向 DB1 共享队列派发任务。LLM provider 为 `internal`，LLM/Embedding 外部 URL 与 key 均为空。

## 隔离资源与实际使用

| 资源 | 实际值 | 开始前现场 | 测试后现场 |
|---|---|---|---|
| PostgreSQL | `psychology_learning_discrete_import_20261005` | 精确库名在 `postgres` 系统目录中不存在 | pytest 建库并迁移至 `0051`；73 张业务表；课程、材料、版本、知识对象、分块、Job 均 0 行；`alembic check`：`No new upgrade operations detected` |
| Redis | `127.0.0.1:6379/2` | PING 成功、0 keys、0 个 DB2 客户端；只用独立逻辑 DB，不占 DB0/DB1 | PING 成功、0 keys、0 个 DB2 客户端。未启动/消费 Worker |
| MinIO | `127.0.0.1:9000`，bucket `v1-discrete-math-import-20261005` | bucket 不存在 | 为本轮隔离测试新建；测试后有 22 个测试产物，全部保留，未执行清理 |

该 Redis 是项目本地 Redis 服务中的专属逻辑 DB，并非新启的独立 Redis 进程。测试没有使用 `.env` 中的默认材料 bucket `course-materials`、共享预览库 `psychology_learning_privacy_target`、预览 Redis DB0 或 Celery DB1，也没有对它们执行迁移/写入。

## 可复现命令与结果

从仓库根目录进入 `server/`，使用以下隔离变量运行本地回归（其余 LLM/Embedding URL、key、model 显式置空；pytest 夹具把作者 API 开关设在当前进程，并固定 `in_process`）：

```powershell
$env:PSYCHOLOGY_TEST_DB='psychology_learning_discrete_import_20261005'
$env:PSYCHOLOGY_TEST_REDIS_URL='redis://127.0.0.1:6379/2'
$env:DATABASE_URL='postgresql+asyncpg://psychology:change-me@127.0.0.1:5432/psychology_learning_discrete_import_20261005'
$env:REDIS_URL='redis://127.0.0.1:6379/2'
$env:MINIO_BUCKET='v1-discrete-math-import-20261005'
$env:APP_ENV='test'
$env:TASK_BACKEND='in_process'
$env:CELERY_BROKER_URL='redis://127.0.0.1:6379/2'
$env:CELERY_RESULT_BACKEND='redis://127.0.0.1:6379/2'
$env:LLM_PROVIDER='internal'
$env:LLM_BASE_URL=''
$env:LLM_API_KEY=''
$env:LLM_MODEL=''
$env:EMBEDDING_BASE_URL=''
$env:EMBEDDING_API_KEY=''
$env:EMBEDDING_MODEL=''
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q `
  tests/test_docx_parser.py `
  tests/test_materials.py `
  tests/test_unpaged_document_ingestion.py `
  tests/test_material_compiler.py `
  tests/test_material_authoring_policy.py `
  tests/test_search.py
```

结果：**51 passed、2 warnings，231.64 秒**。两条 warning 是现有 Starlette/httpx 与 AnyIO 弃用提示。隔离库迁移后 `alembic current` 为 `0051 (head)`；`alembic check` 退出码 0。该回归使用测试 DOCX/PDF fixture，证明既有格式的材料、解析、索引/检索 API 路径可运行；不能计作离散数学 `.doc` 已导入或已命中。

## 验收矩阵

| 验收项 | 结果 | 证据/限制 |
|---|---|---|
| 源文件定位、格式、数量、来源和 hash | 通过 | 唯一连续 10 章 `.doc` 集合；OLE/Word DOC；SHA 与来源台账 10/10 一致 |
| 原始文件保留 | 通过 | 未转换/上传/写入；首文件读取前后 hash 相同 |
| 原文件解析 | **未通过/受阻** | `parser_unavailable` 10/10，0 个非空对象；没有伪造文本、页码或知识对象 |
| 实际知识对象、分块及索引任务 | **未执行** | 解析阻塞时不触发索引；专库中该教材无 Material/Version/Object/Chunk/Job 记录 |
| 对实际离散数学内容的检索命中 | **未通过/未执行** | 没有生成可检索索引；仅 `test_search.py` 对合成 fixture 回归通过 |
| 重复上传幂等/同课程内容去重 | 合成回归通过，实际教材范围未验 | `test_materials.py` 的 fixture 覆盖同一幂等键回放和重复内容拒绝；原教材未通过 API 导入 |
| 无关课程/越权课程拒绝读取 | 未完整验证 | `test_search.py` 有未知课程 404 fixture；本轮没有建立第二个已存在课程并验证课程间隔离，也没有可供读取的真实教材版本 |
| 失败时保留原件/既有数据 | 部分通过 | 原文件未变；没有对任何已有课程/已发布版本写入。隔离库为本轮新建，实际导入失败事务未执行，因此未证明“已有发布数据”恢复路径 |
| 正式课程关联、版本、发布及真实教学验收 | 未完成 | 没有课程/材料版本关联，没有正式发布；数学类工程输入不作为实验心理学课程证据 |
| 浏览器 E2E | 未运行 | 当前阻塞发生在本地输入格式/解析器边界，未启动浏览器或预览服务 |

## 后续解除条件

请提供由本地 Word/LibreOffice 导出的 10 章 `.docx`（或固定 PDF）文件，保持原始 `.doc` 不变；也可在本机具备受控本地 LibreOffice renderer 后重新执行。新输入仍需逐文件记录来源链与 hash，再在新的专属 DB/Redis/bucket 中通过解析、对象/分块、索引、真实命中、异课 404、重复上传幂等和失败保全验收。此报告不表示已导入离散数学教材，也不代表正式教师发布或 V1 整体验收完成。
