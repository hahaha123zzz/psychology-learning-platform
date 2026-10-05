# STUDENT_DEMO_SHARED

> 用途：学生端 Demo Sprint 多窗口唯一共享协作文档  
> 模式：**APPEND ONLY / 只追加，不改写历史事件**  
> 截止：2026-10-06 12:00  
> 主目标：学生端核心学习闭环稳定演示  
> 终止条件：只有 CTRL 追加 `[CTRL→ALL] [STOP]` 后，各窗口才停止。

---

## 固定窗口 ID

- `CTRL`：总控 / 集成
- `UI`：学生端 UI
- `TUTOR`：Tutor + ZIP 微观教学循环
- `EVID`：Evidence / Reader / Figure/Table
- `TEST`：只读测试（可选）

---

## 固定优先级

```text
P0 = 明天 Demo 阻塞
P1 = 有时间必须尽量完成
P2 = 不阻塞 Demo
```

---

## 冻结边界

### 本次核心
- Student Home
- Learn / Reading Studio
- Tutor
- Citation → Reader
- Practice
- Review
- Growth
- Presentation Preference
- Figure/Table 基础解释

### 不主动扩建
- Teacher Workspace
- Course Designer
- Admin
- 高级视觉检索
- ColPali / ColQwen
- 新 BKT/DKT
- 新 Memory
- 新 Retriever
- ZIP 整体后端替换
- AI 生成 Mini Lab 全流程
- 生产部署

---

## 事件格式

```text
- [YYYY-MM-DD HH:mm:ss] [SOURCE→TARGET] [TYPE] TASK-ID | key=value | summary
```

TYPE：

```text
TASK
START
PROGRESS
DONE
BLOCKED
DECISION_REQUEST
DECISION
HANDOFF
MERGE
TEST_PASS
TEST_FAIL
SNAPSHOT
STOP
```

示例：

```text
- [2026-10-05 19:00:00] [CTRL→UI] [TASK] UI-001 | priority=P0 | Student Home 接真实 CurrentTask，并连到 Learn
- [2026-10-05 19:02:00] [UI→ALL] [START] UI-001 | files=...
- [2026-10-05 19:45:00] [UI→CTRL] [DONE] UI-001 | commit=abc1234 | tests=pass | Home→Learn 已跑通
- [2026-10-05 19:50:00] [CTRL→ALL] [MERGE] UI-001 | commit=abc1234 | integration=ok
```

---

## 规则

1. 所有窗口只追加事件，不删除、不改旧事件。
2. 一个任务尽量 30–90 分钟形成一个 commit。
3. 任何公共 contract 改动都先发 `DECISION_REQUEST` 给 CTRL。
4. 只有 CTRL 决定公共 contract。
5. 只有 CTRL 合并到 integration。
6. 工作完成必须写 commit SHA。
7. 被阻塞时先发 `BLOCKED`，然后做不依赖任务。
8. 无其他任务时运行 60 秒轮询；共享文档变化后重新读取。
9. 不得因为“当前任务完成”就关闭窗口。
10. TEST 默认只读。
11. 不得 `reset --hard` 或删除他人工作。
12. 当前代码事实优先于设计假设。

---

# EVENT LOG

- [2026-10-05 00:00:00] [CTRL→ALL] [SNAPSHOT] INIT | shared_doc=ready | 等待 CTRL 写入 DEMO_BASE_SHA、worktree 与第一批 TASK
