# 教师端与学生端 AI 图稿提示词（第一轮）

> 使用方式：每段提示词单独生成一张图，不要把多个方向拼在同一画布。建议先生成教师端 3 张、学生端 3 张，再分别选定一个方向。图稿只决定视觉与布局，不改变后端权限、审核、版本、引用和拒答规则。

## 统一设计底座

- 产品：面向《实验心理学》课程的可信 AI 学习平台，桌面 Web 应用。
- 画幅：1440 × 1024，不带浏览器外框，不带设备模型。
- 语言：所有界面文案使用清晰、自然、可辨认的简体中文；API 名、文件名可保留英文。
- 现有色彩：页面背景 `#F4F7F8`，主表面 `#FFFFFF`，正文 `#18324A`，次要文字 `#667785`，主色 `#2F6B93`，边框 `#D8E1E6`，成功色 `#236A45`。
- 字体：中文无衬线，接近 Microsoft YaHei / Noto Sans SC；正文 14–16px，最多两种字体。
- 风格：克制、可信、学术但不压抑；通过留白、对齐、字号和细分隔线建立层级，少用阴影，不使用玻璃拟态、霓虹、3D、渐变大背景。
- 结构：不要把整个应用包在居中的“大卡片”里；不要卡片套卡片；普通列表使用连续表面和行分隔线。
- 图标：使用统一的线性产品图标，不使用 emoji，不使用装饰性插画。
- 数据日期：以 2026 年 9 月 21 日为当前日期。
- 真实性：只展示本提示词明确要求的能力，不虚构社交、排行榜、直播、消息通知、日历或复杂协作功能。

---

## 教师端：教材发布工作台

### 教师方向 A：原件优先的三栏审核台

```text
Create a realistic, production-quality desktop SaaS UI screenshot for a Chinese “Experimental Psychology” trusted AI learning platform.

Target: 1440 × 1024 desktop web app, no browser chrome, no device frame. All visible UI copy must be legible Simplified Chinese.

The focused screen is “教材发布工作台 / 解析审核”, used by a university teacher to compare the original textbook with parsed objects, resolve quality issues, build the candidate index, and publish only after review.

Use this visual system exactly: page background #F4F7F8, white surfaces, primary text #18324A, muted text #667785, primary blue #2F6B93, border #D8E1E6, success green #236A45. Chinese sans-serif typography similar to Microsoft YaHei or Noto Sans SC, body 14–16px. Restrained academic product style, generous whitespace, thin separators, almost no shadows.

Layout:
- A compact top product bar with product name “实验心理学智能学习平台”, course switcher “2026 秋 · 实验心理学”, and teacher identity “陈老师”.
- A narrow left navigation with only: 课程概览、教材资料（active）、题库与测验、班级学情.
- Main workspace uses three functional columns, not cards inside cards.
- Left column: textbook outline for “《实验心理学》第三版.pdf”, chapter rows with page ranges and review state. “第三章 实验设计” is selected. Above it show pipeline stages 上传完成 → 解析完成 → 抽样审核中 → 待构建索引 → 待发布.
- Large center column: faithful PDF page preview, physical page 42, with realistic Chinese textbook typography. Draw one translucent blue bbox highlight around a paragraph and one amber bbox around a figure caption. Include zoom controls and page navigation “42 / 386”.
- Right column: selected object inspector titled “段落对象 · p42”, showing parsed text, object type, chapter assignment, confidence 0.87, review status, and a compact edit area. Below it show two quality issues: one warning “图注与图片关系待确认”, one resolved “章节标题已修正”.
- Sticky bottom action bar: secondary “保存修正”, secondary “标记重处理”, primary action disabled “构建候选索引”; explain disabled reason in one line: “还剩 1 个抽样问题待确认”. Do not show a publish button as enabled before indexing.

Hierarchy: the PDF and selected bbox are the visual focus. Quality status is visible but not alarmist. The screen should feel like a professional document review tool, not an analytics dashboard.

Do not add decorative charts, fake AI scores, chat windows, kanban boards, excessive badges, rounded floating panels, or unrelated admin controls.
```

### 教师方向 B：流程优先的发布控制台

```text
Design one production-quality desktop UI screenshot for a Chinese university teacher managing the release of an Experimental Psychology textbook.

Canvas 1440 × 1024, app content only, Simplified Chinese, no browser or device frame. Use #F4F7F8 background, #FFFFFF surfaces, #18324A text, #667785 muted text, #2F6B93 primary blue, #D8E1E6 dividers, #236A45 success. Noto Sans SC / Microsoft YaHei style typography, restrained academic SaaS aesthetic, minimal shadow.

Primary user goal: confidently move one immutable textbook version through upload, parsing, review, candidate indexing, and teacher publication without losing sight of blocking problems.

Composition:
- Left product navigation is narrow and quiet; 教材资料 is active.
- Main header: “《实验心理学》第三版” with version “v1”, filename, PDF icon, upload date 2026-09-21, and a clear draft label.
- Directly below, a prominent horizontal release pipeline with five stages: 1 上传, 2 解析, 3 教师抽检, 4 候选索引, 5 发布. Stages 1–2 are green completed, stage 3 is blue active, stages 4–5 are neutral locked.
- The central workspace is a large split view. Left 62% shows page 42 original preview with exact bbox highlights for a paragraph, figure, table, and formula using subtle category colors. Right 38% is a review queue grouped by “阻塞 0 / 警告 2 / 已处理 7”. Selecting “表格第 2 列疑似错位” reveals the extracted table under the queue with editable cells and source coordinates.
- A slim status strip above the workspace shows “已抽检 10 / 10 页”, “图片 3 / 3”, “表格 2 / 2”, “公式 2 / 2”; present these as compact text, not four decorative cards.
- Bottom right primary action “确认抽检并构建索引”. Nearby explanatory copy: “索引完成后才可发布给学生”.

Make the workflow state and next safe action unmistakable. Avoid dashboard chart collections, large hero headings, marketing copy, glassmorphism, gradients, excessive pills, or fictional collaboration features.
```

### 教师方向 C：问题队列优先的专业校对台

```text
Create a realistic 1440 × 1024 desktop web-app screen for a Chinese “实验心理学智能学习平台”. This is a teacher-facing parsing review and publication screen, all UI text in legible Simplified Chinese, no browser chrome.

Visual language: quiet editorial workspace. Background #F4F7F8, white work surfaces, navy text #18324A, muted #667785, blue #2F6B93, border #D8E1E6, green #236A45. Use strong alignment, typographic hierarchy, lightweight row dividers and almost no shadow. Do not use cards for every row.

Build a focused issue-triage layout:
- Top bar names the course and document: “实验心理学 / 《实验心理学》第三版 / v1”. Show an immutable version indicator and “草稿”.
- Left 320px pane is a searchable quality issue queue. Tabs: 待处理 2, 已处理 7, 全部 9. Rows include page, object type, concise issue, severity, confidence. Selected issue: “p42 · 图片 · 图注关联待确认”.
- Center pane is the dominant original page viewer. Show page 42 with one figure bbox and its caption bbox linked by a thin line. Include exact coordinates in a small inspector chip: “[92, 214, 516, 489]”.
- Right 360px pane compares “解析结果” and “教师修正”. It includes object type selector, caption text, chapter “第三章 实验设计”, related object, review decision, and an audit note field. Make raw content visibly read-only and corrected content editable.
- A compact footer summarizes publication readiness: “阻塞问题 0 · 待确认警告 1 · 当前索引未构建”. Primary action “确认本项”, secondary “请求重处理”. Publish remains unavailable.

The screen should feel like professional proofreading software adapted to textbook evidence. Do not add chat, charts, student data, AI assistant avatars, decorative illustrations, or unsupported batch collaboration.
```

---

## 学生端：教材阅读与 AI 学习空间

### 学生方向 A：阅读优先的证据学习台

```text
Create a production-quality desktop web-app screenshot for a Chinese student learning Experimental Psychology from a teacher-published textbook with an evidence-grounded AI tutor.

Target 1440 × 1024, app UI only, no browser frame. All UI copy must be clear Simplified Chinese. Use background #F4F7F8, surfaces #FFFFFF, text #18324A, muted #667785, primary #2F6B93, border #D8E1E6, success #236A45. Calm academic atmosphere, readable 14–16px Chinese sans-serif, minimal shadows.

The primary task is reading the textbook while asking a grounded question and verifying the exact source without leaving the learning flow.

Layout:
- Compact top bar: product name, course “2026 秋 · 实验心理学”, learning progress “第三章 · 42%”, student identity.
- Narrow left outline pane with chapters and current section “3.2 被试间设计”. Include a small “本节学习中” marker, not a gamified badge collection.
- Dominant center pane is the textbook page viewer, page 42 / 386. Show realistic Chinese textbook content and a blue highlighted paragraph bbox. A small anchored citation label “[1]” sits beside the highlighted paragraph.
- Right learning pane titled “AI 教师”. Show a short conversation: student asks “被试间设计为什么更容易受个体差异影响？”, AI answer begins “根据教材：” and cites “[1] 第42页”. Under the answer show two actions only: “查看原文” and “继续追问”. Include a subtle verification line “教材证据已核对”.
- At the far right edge, show a slim collapsed rail titled “局部追问 1”. It represents a side branch created from selected text; it must not replace or redirect the main conversation.
- Bottom of AI pane has a concise input with placeholder “围绕当前教材提问…”, send action, and a visible note “证据不足时会明确说明”.

The page preview and answer-to-source relationship are the visual focus. Do not add streaks, leaderboards, cartoon tutors, decorative charts, social feeds, or answers without citations.
```

### 学生方向 B：学习步骤优先的 AI 教师空间

```text
Design one realistic 1440 × 1024 desktop UI screenshot for a Chinese Experimental Psychology learning platform. No device frame or browser chrome; use legible Simplified Chinese.

Use the existing product palette: #F4F7F8 background, white surfaces, #18324A text, #667785 secondary text, #2F6B93 primary, #D8E1E6 border, #236A45 success. Quiet, credible educational SaaS; typography and spacing carry hierarchy, with few borders and almost no shadow.

Focused scenario: a student is completing a guided chapter session. The AI follows diagnose → teach → check → hint → practice → summary and must stay grounded in the published textbook.

Composition:
- Left navigation contains only 当前学习, 教材, 测验, 复习. 当前学习 is active.
- Main center column is a spacious guided lesson titled “3.2 被试间设计”. At top, a horizontal learning stepper shows 诊断 completed, 讲解 completed, 理解检查 active, 练习 and 小结 upcoming.
- The central prompt asks one clear check question: “请用自己的话解释：为什么随机分配能降低个体差异的影响？” Beneath it is a large answer field and primary “提交回答”. Secondary action “这里还不懂”.
- Above the prompt, show a concise AI explanation with two inline citation markers “[1]”“[2]”. Avoid a long chat transcript; this is a structured learning task, not a generic chatbot.
- Right evidence pane shows two source excerpts from “《实验心理学》第三版”, pages 42 and 43, with chapter path and tiny page thumbnails. The first excerpt is selected and contains “定位到原文” action.
- A narrow slide-out drawer is open over the rightmost area titled “局部追问”. It contains selected phrase “随机分配” and one short independent Q&A. Clearly show action “带回主对话”, while the main lesson remains visible and unchanged behind it.

Do not add points, levels, leaderboards, mascots, generic productivity widgets, or fabricated mastery claims. The active step and textbook evidence must be obvious.
```

### 学生方向 C：原文与问答并重的沉浸分屏

```text
Create a polished desktop UI concept at 1440 × 1024 for a Chinese university student using an evidence-grounded AI tutor for Experimental Psychology. Output only the app interface, no browser frame, no device mockup. All interface text in legible Simplified Chinese.

Visual style: editorial reading tool meets modern learning workspace. Background #F4F7F8, surfaces #FFFFFF, text #18324A, muted #667785, blue #2F6B93, dividers #D8E1E6, success #236A45. Use generous whitespace, precise grid, long-form reading line length under 65 Chinese characters, minimal radius and shadow.

Create a balanced 60/40 split screen:
- Left 60% is a distraction-free textbook reader for “第三章 实验设计”, physical page 42. A selected paragraph is highlighted with an exact translucent bbox. A compact floating selection toolbar contains “解释这段”“局部提问”“加入笔记”; “局部提问” is active.
- Right 40% is the persistent main learning conversation. Header shows “主学习对话 · 3.2 被试间设计” and status “教材约束”. The latest AI response contains a concise explanation and two citations with page numbers. Include a small refusal example lower in the thread: “当前教材证据不足，无法确认这一点。” styled neutrally, not as an error alarm.
- A secondary drawer slides in from the right inside the conversation region, occupying about 320px, titled “局部追问：随机分配”. It shows the selected source sentence at top, a short branch Q&A, and actions “保存为待复习问题” and “带回主对话”. The main conversation remains partially visible and is not replaced.
- Bottom utility bar on the reader shows page 42 / 386, zoom, and “引用定位已开启”.

Make source selection, branch isolation, citations, and exact return-to-bbox behavior visually understandable. Do not add analytics dashboards, gamification, cartoon AI, social features, unrelated study tools, or decorative illustrations.
```

---

## 选定方向后的状态图补充提示词

把选中的主图作为视觉参考图上传给生图 AI，再附加下面这段；不要只靠文字重新生成，否则容易漂移。

```text
Using the attached selected UI screenshot as the strict visual source, create a single 1440 × 1024 component-state board for the same product. Preserve its exact palette, typography, spacing, navigation, panel proportions, icon language, border radius and density.

Show only six labeled states of the core workflow, each as a clean cropped product region rather than six full app screens:
1. 默认状态
2. 加载中：使用骨架屏，布局不跳动
3. 空状态：说明为什么为空，并给一个明确下一步
4. 可重试错误：保留用户输入，显示重试动作与 request_id
5. 权限或质量门禁阻塞：解释原因，不显示不可执行的成功状态
6. 成功状态：清楚显示已保存/已发布/已定位，但不使用庆祝插画或彩纸

All text must be legible Simplified Chinese. Do not redesign the source, invent new navigation, add dashboards, or change the information architecture.
```

## 图稿回传要求

请保留原始分辨率，按以下名称回传，至少各选一张：

- `teacher-A/B/C.png`
- `student-A/B/C.png`

收到选定图稿后，再冻结组件、路由、接口字段、交互状态、响应式和无障碍实现规格。
