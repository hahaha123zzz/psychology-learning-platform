# V1 视觉基准交付清单

高保真视觉稿按 Frontend Specification §27 交付 11 个代表页：Student Home、Learning Workspace、Experimental Reasoning、Growth、Teacher Overview、Teacher Analytics、Teacher Teaching、Teacher Assessment/Grading、Course Designer Domain/Pedagogy、Formal Assessment、Mini Lab。

每页必须同时给出桌面、平板、手机，以及 loading、empty、error、conflict/recovery 状态。视觉基准只决定布局和交互语言，不产生静态业务数据。视觉审阅通过后再把组件字段冻结到 `component-spec.md` 和 API Read Model。页面级布局与状态合同见 [page-specs.md](./page-specs.md)。

## 共用画面规则

- Calm / Academic / Structured / Evidence-first；避免渐变、玻璃拟态、AI 紫和卡片海。
- 页面层级使用背景、边框、留白和排版；阴影只用于 Drawer/Popover/Dialog。
- Evidence 和 Branch 同一 Context Panel 互斥打开。
- 图表只允许 Horizontal Bar、Simple Line、Stacked Bar、Sparkline，并显示时间范围、样本口径和文字解释。
- 状态不只依靠颜色；所有可点击对象有清晰 focus ring 和键盘路径。
