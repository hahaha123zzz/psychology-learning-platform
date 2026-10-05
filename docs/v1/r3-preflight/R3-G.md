HANDOFF=COMPLETE; RESUMED=2026-10-05 11:04:42 +08:00

# R3-G 交接报告：Mini Lab 中断/恢复与 TeachingAsset fallback

## R3-G 执行回报（2026-10-05）

交接状态：`HANDOFF=COMPLETE; RESUMED=2026-10-05 11:04:42 +08:00`。按主窗口原部分 GO 完成通用工程范围；没有验收真实教材、正式实验内容或教学等价性。

### 当前共同基线与文件归属

- 检查时间：2026-10-05 11:36（Asia/Shanghai；写入本次报告更新之前）；HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。`scripts/r3-baseline-fingerprint.ps1` 连续两次为 `IncludedEntries=514`、SHA-256 `696E3F9D73CD0F198196516F8935052E6A5617037A90599797A590FCF5353269`。指纹会纳入本报告，因此报告更新自身会改变全树哈希；该记录固定的是代码/测试最终快照。此前本窗口开工前读数为 510 entries / `3B5E9A58330EAF2DE0B2E1DB232A8ED4CAD40B693862AC5FA732E3EC105CBB9C`；当前全树指纹还包含并行窗口及测试证据变化，不能把差值统归给 G。主窗口旧基线 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146` 缺少可重建清单。
- 本轮 G 修改的代码/测试文件：`server/app/modules/labs/router.py`、`server/app/modules/labs/schemas.py`、`server/app/modules/teaching_assets/service.py`、`server/tests/test_mini_labs.py`、`server/tests/test_teaching_assets.py`、`server/tests/r3_g_browser_seed.py`、`web/components/StudentMiniLabPanel.tsx`、`web/components/learning/MiniLabRuntime.tsx`、`web/components/learning/LearningBlockStream.tsx`、`web/design-system/mini-lab.css`、`web/lib/mini-lab-api.ts`、`web/lib/teaching-assets-api.ts`、`web/tests/teaching-assets-recovery-contract.test.mjs`、`web/tests/r3-g-mini-lab-browser.mjs`。浏览器证据新增 `web/tests/r3-g-evidence/mini-lab-invalidated.png`。
- `web/components/TeachingAssetEditor.tsx`、`server/app/modules/teaching_assets/router.py` 与 `schemas.py` 只读检查，未修改。没有修改 `server/app/db/models.py`、Alembic、`server/tests/conftest.py`、`server/app/api/router.py`、`contracts/openapi.json`、`web/app/globals.css`、C 窗口学习页或其他共享文件。以上代码文件原先均处在共同工作树的未跟踪状态；列表只声明本轮实际编辑，不认领共同树中其他既有文件。

### 工程改动

- Mini Lab 新增 `POST /student/labs/{session_id}/invalidate`：只接受 `running`，按 `expected_version` 做乐观锁，`idempotency_key` 与规范化请求体哈希保证同 key/同 payload 重放原收据、异 payload 返回 409。作废写入 0048 已有收据字段，进入不可恢复的 `invalidated` 终态；已有阶段快照保留，作废不创建 `lab_trial_completed` 或资格事件。活动查询可返回最近终态，前端显示作废状态并卸载运行时；网络错误保留重试幂等键。checkpoint 保存失败时明确显示该试次“未保存”，不会当作结果或资格。
- TeachingAsset 服务端拒绝 fallback 中的 HTML 标记及既有可执行 URL/脚本内容；前端用 React 文本节点输出，不使用 HTML 注入。前端模板/内容白名单降级有稳定 `data-fallback-reason`（`template_unsupported`、`device_capability_unavailable`、`content_unavailable`）和规定的 `role=status` 提示；白名单资产仍提供语义标题、段落/列表与键盘可操作的 `<details>/<summary>` 纯文本说明。当前模板均为静态语义内容，不需要专属设备能力；没有实际屏幕阅读器或真实设备兼容验收。
- 无新增共享模型或迁移需求：0048 已含 `MiniLabSession` 作废 key/hash、用户、时间和理由字段。`labs` 路由原已注册，未改根 router。**需主窗口生成/审阅 OpenAPI 快照**，因为 endpoint 增加请求 schema，MiniLab 响应增加 `invalidation_reason` / `invalidated_at`；G 未编辑 OpenAPI。

### 测试与浏览器证据

- 后端专项：设置 `PSYCHOLOGY_TEST_DB=psychology_learning_v1_r3_g_20261004`、`PSYCHOLOGY_TEST_REDIS_URL=redis://127.0.0.1:6379/10`、Celery broker/result 同 DB10、`MINIO_BUCKET=v1-r3-g`、`PORT=8216` 后，执行 `python -m pytest -p no:cacheprovider -q tests/test_mini_labs.py tests/test_teaching_assets.py`：**5 passed，2 条现有 FastAPI/Starlette 弃用警告，39.19 秒**。覆盖版本冲突、幂等重放、终态禁止续写/提交、完成会话禁止作废、没有完成事件/资格化，以及 fallback HTML 标记拒绝。
- 前端合同：`node --test tests/teaching-assets-recovery-contract.test.mjs`：**2/2 passed**。静态检查：G 后端文件 `ruff check --no-cache ...` 通过；Web `tsc --noEmit --incremental false` 通过；G 前端文件 ESLint 通过；`node --check tests/r3-g-mini-lab-browser.mjs` 通过。
- 物理快照 `web/.r3-runtime/r3-g-mini-lab-20261005b` 在 `.next-r3-g` 构建通过；浏览器运行时 Next 警告 standalone 模式应通过 standalone server 启动，但本地 `next start` 实测 Web HTTP 200、API proxy `/api/v1/health/live` HTTP 200。API/Web 分别使用 8216/3216，Edge CDP 使用 9316；测试后本窗口进程已停止。
- 浏览器：`node tests/r3-g-mini-lab-browser.mjs` 最终 **passed**。Chromium/Edge 场景包含中断第一次 checkpoint POST、核对服务端无该试次、恢复并保存、刷新后恢复正确阶段、作废、同请求幂等回放及终态拒绝续写。截图：`web/tests/r3-g-evidence/mini-lab-invalidated.png`。首几次仅测试脚手架导入/等待条件失败，修正后最终完整场景通过。
- 本次自动化环境初次默认沙箱执行因无法创建临时文件失败，按工具审批在 G 隔离资源范围内重跑通过；没有使用默认测试库或预览库。

### 隔离资源与剩余事项

- 结束后只读复核：PostgreSQL `psychology_learning_v1_r3_g_20261004` 为 Alembic `0049`，`mini_lab_sessions=2`；这些是 G 测试留下的数据，未清理或重置。Redis DB10 `PING` 成功、0 keys；MinIO bucket `v1-r3-g` 存在。3216/8216/9316 均不可连接，G 启动的 API/Web/Edge 已停止。
- 正式心理学实验、获准教材/教案中的 2—3 个实验及图表/公式资产仍缺外部输入，不能做真实内容或科研效度验收。TeachingAsset 降级已由服务端与前端合同覆盖，未做真实设备矩阵、键盘/焦点逐项浏览器检查或读屏器检查；Mini Lab 浏览器证据是本地工程 fixture，不是真实课程/班级验收。
- 主窗口接手 OpenAPI 导出与共享全量回归。不得据本轮局部测试宣称 P8 全完成、R3 全完成或 V1 完成。

## R3-G 后续收敛补记（2026-10-05 12:11 +08:00）

按 11:50 广播继续补足键盘/焦点/窄屏验收准备，并复核 Mini Lab OpenAPI：

- 在 G 排他文件 `web/design-system/mini-lab.css` 增加作废控件、jsPsych 原生按钮及 TeachingAsset `<summary>` 的 `:focus-visible` 轮廓；Mini Lab 运行容器设 `min-width: 0`，按钮组使用可换行网格并约束按钮宽度，保留既有 560px 单列布局。
- 在 `web/tests/teaching-assets-recovery-contract.test.mjs` 增加上述焦点和窄屏 CSS 合同断言。执行 `node --test tests/teaching-assets-recovery-contract.test.mjs`：**2/2 passed**。`git diff --check` 对本次文件无 whitespace error。
- 浏览器验收本轮仍受资源阻塞：R3-G 专属 3216/8216/9316 TCP 检查均失败；Playwright skill 的服务探测只发现 3000/8000/9000（共享预览/依赖端口），未使用这些端口，也未启动服务。因而焦点顺序、键盘实际操作、窄屏无溢出等仍未取得真实浏览器证据；CSS/Node 结果不能替代该验收。
- OpenAPI 只读核对当前 `contracts/openapi.json`：`POST /api/v1/student/labs/{session_id}/invalidate` 已存在，`MiniLabInvalidate` 请求体正确列出必填 `expected_version`、`idempotency_key`、`reason`（长度约束分别为 1+、1–128、1–500）；但 200 响应 schema 为 `{}`，且没有 `MiniLabOut` schema，无法从快照确认响应字段 `invalidation_reason` / `invalidated_at`。这是共享 OpenAPI/响应 envelope 所有权事项，请主窗口依据 exporter 输出决定类型化响应合同并重新生成快照；G 未改 `contracts/openapi.json`。
- 直接运行本地 TypeScript 二进制 `node node_modules/typescript/bin/tsc --noEmit --incremental false` 失败于排他范围外的 `components/TeacherAssessments.tsx(87,814): TS2304 Cannot find name 'approveFormalPurpose'`。该文件不归 G，不作修改。`pnpm exec tsc` 在当前 checkout 未解析到 `tsc`。G 的组件代码未报本轮新增类型错误，但全 Web typecheck 仍未通过。
- 当前 HEAD 仍为 `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`。执行基线脚本两次的摘要均为 521 entries，但 SHA 分别为 `E10A8AB7E738DF77FC016A280AFA655033245B527CCDD6F6F091C1FADA56EA98` 和 `5130D5EC152FC603ECDFB91DC9AF06B509B170DF7C5C46A0F3EC6973E92FDAAF`，没有得到连续稳定共同快照；不把全树差异归属给 G。`git status` 显示本补记新增的代码/测试变更仅为上述两个文件，OpenAPI 仍有主窗口的并行改动。
- 尚待：资源恢复后对真实 Mini Lab/TeachingAsset 页面逐项做 Tab/Shift+Tab、Enter/Space、焦点可见和窄屏宽度浏览器验收；主窗口确认类型化 OpenAPI 200 响应及快照；全 Web typecheck 需在 E 修复后或静止共同树重跑。无新增模型/迁移需求；正式教材/实验内容和真实设备/读屏器验证仍受外部输入与验收范围阻塞。

## R3-G 成功响应合同补记（2026-10-05 12:16 +08:00）

响应主窗口 12:02 广播（请 G 在原范围提供 invalidate 成功响应合同与模块测试）：

- `server/app/modules/labs/schemas.py` 新增 `MiniLabResponseMeta`（`request_id`、`server_time`）和 `MiniLabResponse`（`data: MiniLabOut`、`meta`）；`server/app/modules/labs/router.py` 的 invalidate endpoint 改为声明 `response_model=schemas.MiniLabResponse`。没有改共享 `app/core/response.py` 或其它窗口文件。
- 扩充 `server/tests/test_mini_labs.py` 的作废成功集成用例，断言顶层 `{data, meta}`、meta 字段及 data 中的作废理由/时间/版本。该测试写数据库，本轮隔离 PostgreSQL/Redis 与 API 服务不可用，未运行。
- 只读调用 `app.openapi()`（内存生成，不写 `contracts/openapi.json`）验证 200 schema ref 为 `#/components/schemas/MiniLabResponse`，`MiniLabOut` 暴露 `invalidation_reason` / `invalidated_at`，Meta 暴露 `request_id` / `server_time`。该检查时共享快照尚待主窗口导出；主窗口后续已在 13:32 记录 156 paths，并确认 MiniLab response schema 已导出。G 未手改共享快照。
- `python -m ruff check --no-cache app/modules/labs/router.py app/modules/labs/schemas.py tests/test_mini_labs.py`：通过。`node --test tests/teaching-assets-recovery-contract.test.mjs`：**2/2 passed**。直接调用 ESLint 对 G 前端组件/合同文件检查通过。此前 `pnpm exec tsc` 仍受 E 的 `approveFormalPurpose` 错误阻断；不属于 G 范围。此前完整后端 5 项和浏览器 Mini Lab 流程证据仍是 11:36/11:39 记录，本次没有因资源中断而重跑或改写其时间范围。
- 报告本次修改前，HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04` 的 `scripts/r3-baseline-fingerprint.ps1` 连续两次得到 524 entries、相同 SHA-256 `7A98CB1A347D770AFE7BC9DFF9D46D0486EFB3F770176388D3C7293773FE390E`；指纹输入含报告/并行窗口文件，不能把全树增量归属给 G。
- 仍需隔离资源恢复后运行 G 后端专项，验证路由实际 envelope；主窗口重新导出 OpenAPI；G 专属 3216/8216/9316 恢复后再完成焦点/键盘/窄屏真实浏览器验收。

## R3-G 13:36 施工收敛回报（2026-10-05 14:14 +08:00）

按主窗口 13:36 最新逐窗要求补跑 G 后端专测并完成键盘/焦点/窄屏浏览器验收：

- **浏览器通过：** 在新 G 物理快照 `web/.r3-runtime/r3-g-a11y-20261005` 的独立 `.next-r3-g` production build 上，API 8216、Web 3216、Edge CDP 9316 验收通过；API health 与 Next API proxy 均返回 200。`node tests/r3-g-mini-lab-browser.mjs` 最终通过，覆盖 Mini Lab checkpoint 请求中断、恢复、刷新恢复、作废、幂等重放、终态拒绝续写，以及真实键盘 Tab/Shift+Tab 在理由框与作废按钮间移动和 2px `:focus-visible` 轮廓。Mini Lab 控件内部在 375 CSS px 下无横向溢出。
- TeachingAsset 浏览器部分对学习任务 endpoint 使用 CDP 合成 `engineering_fixture` 响应（不是正式课程内容），页面通过真实 React/浏览器 renderer 显示未知模板纯文本 fallback、稳定 `template_unsupported` reason 与 `role=status` 提示；卡片/受支持资产 disclosure 在 393 CSS px 下无内部横向溢出。受支持模板的 `<summary>` 获得焦点后 Enter 与 Space 均切换原生 `<details>`。截图：[mini-lab-a11y-393px-20261005.png](/E:/项目/心里/web/tests/r3-g-evidence/mini-lab-a11y-393px-20261005.png)。报告/代码保留既有截图，另存本轮新图。
- 该浏览器截图还显示宿主 `/student/learning` 顶栏文字在窄屏右缘有裁切；该页由 R3-C 持有（`StudentLearningSession.tsx`/共享壳），G 未修改。请主窗口转交 C/统一检查，不能据 G 组件内部无溢出认定整页窄屏验收通过。
- 快照构建：`pnpm build` 于新物理副本成功，TypeScript、24/24 静态页通过，输出只在 `.next-r3-g`。G Node 合同 **2/2 passed**、浏览器脚本 `node --check`、G Ruff 检查均通过。OpenAPI 已由主窗口导出为 156 paths（共享状态 13:32 记录的 SHA `02241A429DD2284E20C409B8C4436121277C3D6F207F8C753DE85028FF216900`），包含 G `MiniLabResponse`。
- **后端集成测试未运行（保留数据的安全阻塞）：** G 指定 DB `psychology_learning_v1_r3_g_20261004` 为 `0049`，本次开始前已有 2 条 Mini Lab 会话。R3 共用 `server/tests/conftest.py` 的每个 `client` fixture teardown 会执行 `TRUNCATE TABLE users CASCADE`，会清除该库现有用户关联业务记录；本报告两组后端文件里的所有测试都依赖 `client`。不运行这些用例，避免毁掉既有数据，也不修改主窗口持有的 conftest 或自建/自分配测试库。浏览器只在该库追加合成数据；只读结束核验为 11 个 Mini Lab sessions、13 个 courses，全部保留。需要主窗口分配一个新的 G 独立空测试库，或提供不清理现存数据的统一测试 fixture 后，才能执行后端专测。
- **资源收尾：** PostgreSQL 库名/0049 revision 匹配；Redis DB10 PING 成功、0 keys；MinIO bucket `v1-r3-g` 存在。浏览器后停止本窗口启动的 API/Web，netstat 确认 3216/8216/9316 无 LISTENING；未使用 3000/8000、未清理数据库/Redis/bucket/快照。
- 报告更新前的共同基线脚本两次一致：HEAD `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`、530 entries、SHA-256 `219489CA9F708899CC46D27B3595E665DF7BA27F9BAC41F413A58F808E91FA74`。指纹涵盖并行树，不能把全树增量归属 G。
- **仍未验收：** G 后端写库专项等待新分配的安全测试库；屏幕阅读器、真实设备矩阵、正式教材/实验内容及教学等价性无外部输入，均未验收。不得宣称整个 P8、R3 或 V1 完成。

以下为 2026-10-05 10:56 的开工前准备快照；当时未修改业务代码、未运行测试或启动服务。当前实施状态、文件增量、测试及资源结果以上方“R3-G 执行回报”为准。R3-G 部分 GO 始终限于并行状态表中的通用工程子范围。

- 检查时间：2026-10-05 10:56（Asia/Shanghai）
- HEAD：`4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`
- 当前可复现共同基线：`scripts/r3-baseline-fingerprint.ps1` 连续两次得到 `IncludedEntries=509`、SHA-256 `349C165897A66ABC8E8CD77E178257DA84175A835C48722BD994EC5B73FC1209`。相对主窗口此前的 `32DA80390F42EA63DB321B68D0A1DC5572C131BC2348D0C7F9EF381839CAC146`，当前指纹已变化；旧指纹没有逐文件清单可供重建，故以本次连续一致的当前基线继续，不将全树变化冒充为 G 独有改动。前一稳定检查为 `4CD799F097D733EBC561AAB8B623D3FCD0BB07FBC71FD1C52946B23F65B99650`，本次没有可归属到 G 业务代码的增量；本报告写入是该基线后的唯一 G 专属变更。
- 文件归属：以下排他候选文件当前均为未跟踪文件，已由 R3-G 表格范围和此前准备清单识别；本窗口尚未修改其中任何代码或测试。

## P8-02：TeachingAsset 通用 fallback/无障碍

拟改精确文件：

- `server/app/modules/teaching_assets/service.py`
- `server/tests/test_teaching_assets.py`
- `web/components/TeachingAssetEditor.tsx`
- `web/components/learning/LearningBlockStream.tsx`
- `web/design-system/mini-lab.css`（仅专属规则；不改共享 `web/app/globals.css`）
- `web/lib/teaching-assets-api.ts`
- `web/tests/teaching-assets-recovery-contract.test.mjs`

验收标准：仅允许名单内模板；`fallback_text` 永远按纯文本渲染，不执行 HTML/JS/表达式。未知模板或当前设备不能呈现时安全切换纯文本，并给出稳定、非敏感 reason code 和明确提示：“当前设备/模板无法呈现交互内容，已切换纯文本说明”。不宣称文本与交互等价。业务浏览器检查键盘操作、焦点顺序、语义/读屏可感知提示、窄屏布局；保留 `engineering_fixture` 标识。无许可教材/教案时只验通用工程行为，不验内容或教学等价性。

## P8-06：Mini Lab 中断、恢复、作废与资格化

拟改精确文件：

- `server/app/modules/labs/router.py`
- `server/app/modules/labs/schemas.py`
- `server/tests/test_mini_labs.py`
- `web/components/StudentMiniLabPanel.tsx`
- `web/components/learning/MiniLabRuntime.tsx`
- `web/lib/mini-lab-api.ts`
- `web/lib/mini-lab/jspsych-adapter.ts`

验收标准：刷新/中断后仅恢复服务端确认的阶段 checkpoint；未确认试次显示“未保存”，不得纳入结果或资格化。作废只允许 `running` session，要求 `expected_version`、幂等 key 和理由；同 key+payload 重放原回执，异 payload 或并发版本冲突为 409。`completed` 不可作废；`invalidated` 为终态，不得恢复、续写、提交或资格化。作废不产生 `lab_trial_completed` 或其他完成资格事件；既有完整 Explain/Transfer 资格规则保持不变。浏览器覆盖已确认阶段后刷新、保存中断、未确认试次、恢复、作废、重复提交、版本冲突和资格事件检查。

## 共享合同与协作边界

- 主窗口迁移 `0048` 已给 `MiniLabSession` 提供作废幂等 key/hash、作废者/时间/理由字段；目前不需要新增共享模型或迁移。若实施发现必须新增字段/事件，先停并交主窗口决定。
- G 可改本地模块 router/schema/service 和专属测试；`server/app/api/router.py` 路由聚合、OpenAPI 导出与共享 fixture 归主窗口。本报告不申请新增公共 fixture。
- R3-C 独占普通学生学习/SSE 与 Growth/Me 页面：G 不改 `StudentCourseSupportPages.tsx`、`StudentLearnPage.tsx`、`StudentLearningSession.tsx`、共享 API client、导航或全局 CSS。
- R3-F 独占 `web/app/course-design/**` 与 Designer 页面：G 不改 Course Designer 页面。若需要把 `TeachingAssetEditor` 接入 Designer，先由主窗口协调两窗口。

## 专属环境现场核验

- PostgreSQL `psychology_learning_v1_r3_g_20261004`：可连接；只读查询返回库名匹配，`alembic_version` 表不存在，当前为空库。未迁移或写入。
- Redis `redis://127.0.0.1:6379/10`：`PING` 成功，`DBSIZE=0`；专属 queue `v1-r3-g`。未启动 Worker。
- MinIO bucket `v1-r3-g`：存在；未上传或改动对象。
- Web/API/CDP 端口 `3216/8216/9316`：当前均无监听；本次未启动服务。
- 主窗口共享状态记录的 R3-G 物理源码快照、独立 production build、API proxy stub 与 Chromium 基础 shell 检查已通过。这只是隔离构建/代理证据，不代表 TeachingAsset 或 Mini Lab 业务浏览器验收。

## 测试证据与剩余阻塞

- 本次交接未运行测试或浏览器业务验收，遵守主窗口短期写入/测试冻结。当前没有 R3-G 专项业务测试结果、浏览器截图或 trace 可报告。
- 冻结解除后，拟运行上述专属后端和前端用例，并在 R3-G 物理快照及 Chromium 中验收中断/恢复/fallback。命令需显式绑定本报告列出的 DB、Redis DB10、MinIO bucket、queue 和 3216/8216；不得使用预览库、默认测试库或其他窗口资源。
- 最终 2—3 个实验、教材图表及教学目标等价性仍等待获准教材/教案。不得伪造实验内容或宣称真实内容验收；本地工程验收不代表实验效度、生产恢复或整个 V1 完成。

## R3-G 0050 后浏览器复验（2026-10-05 15:18 +08:00）

- 按并行状态文档 14:36 的 G 专属环境 GO 复核资源与文件归属后继续。共同 HEAD 为 `4c8cc3dbbfbc2c95da26596398e295c9ccc72a04`；`git status` 显示 G 的实际文件仍限于前述模块、前端组件/API 和专测，其他并行窗口文件保持原状。指纹脚本在当前 Windows PowerShell 启动方式下因脚本编码解析失败，未据此报告新指纹；旧指纹不能代表本次快照。
- 只读确认 G PostgreSQL 为 `psychology_learning_v1_r3_g_20261004`、revision `0050`，启动前 11 个 MiniLab session、13 个 course 且无其他连接；Redis DB10 `PING`、0 keys；MinIO `v1-r3-g` 存在；3216/8216/9316 无监听。默认 API 配置指向 revision 0038 的 `psychology_learning`，因此本次 API 以显式 `DATABASE_URL` 绑定 G 专库后在 8216 启动。Health 与 Web API proxy 均 HTTP 200。
- 使用既有物理快照 `web/.r3-runtime/r3-g-a11y-20261005` 及 `.next-r3-g` build，在 3216 启动 Web；Edge CDP 使用 9316。浏览器脚本最终 **passed**：未确认试次、checkpoint 请求中断与服务端确认状态、恢复及刷新恢复、作废、幂等重放、终态拒绝续写、375px Mini Lab 控件布局与 Tab/Shift+Tab 可见焦点；TeachingAsset 使用带 `engineering_fixture` 标识的合成任务响应，验证未知模板纯文本 fallback / `role=status` / `template_unsupported`、393px 布局、`<summary>` 焦点与 Enter/Space 切换。页面视口/文档宽度均为 393px，fallback 卡片为 321/321px。新截图：[mini-lab-a11y-393px-20261005b.png](/E:/项目/心里/web/tests/r3-g-evidence/mini-lab-a11y-393px-20261005b.png)。此前截图保留未覆盖。宿主学习页窄屏顶栏需继续由 C/主窗口检查，不归 G。
- 本次增加 `R3_G_SCREENSHOT_NAME` 可选环境变量，避免浏览器复验覆盖既有证据；只改 G 专属浏览器脚本。Node TeachingAsset/recovery 合同 **2/2 passed**，浏览器脚本 `node --check` 通过；G Python 专项文件 Ruff 检查通过。
- 服务已停止。结束后只读复核 revision 仍为 `0050`，MiniLab sessions `12`、courses `14`（只追加本次合成验收记录，未清理既有数据）；无其他 PostgreSQL 连接；Redis DB10 仍 0 keys，bucket 存在；3216/8216/9316 无 LISTENING。
- **后端 pytest 仍未运行：** G DB 保有既有业务数据，公共 `client` fixture teardown 会执行 `TRUNCATE TABLE users CASCADE`，会级联删除用户相关记录。不得在该库运行，也不得改主窗口的 `conftest.py` 或自分配数据库。请主窗口提供新的 G 专用空测试库或安全 fixture 后再补 `test_mini_labs.py` 与 `test_teaching_assets.py`。浏览器工程验收不能替代后端测试。
- 教材/教案授权输入、正式实验内容/教学等价性、屏幕阅读器与真实设备矩阵仍未验收；不宣称 P8、R3 或 V1 整体完成。
