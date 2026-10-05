# 学生核心页面本地可访问性复核

日期：2026-10-06  
范围：V0.9 本地合成学生 Demo；Chromium 生产模式构建，API 代理到隔离演示 API `127.0.0.1:8011`。未读取或发送教材正文、图像、表格。

## 检查范围

路由在 360、393、768 CSS px 三档视口逐页检查：

- `/student`：学生 Home
- `/student/learning`：Tutor 引导学习
- `/student/courses/{courseId}`：课程首页
- `/student/courses/{courseId}/learn`：课程 Learn / Reader
- `/student/courses/{courseId}/practice`：Practice / Review
- `/student/courses/{courseId}/growth`：Growth
- `/student/courses/{courseId}/me`：Preference

## 结果

- 共 21 个“路由 × 视口”组合；页面横向 `scrollWidth` 均未超过可视 `clientWidth`，浏览器页面异常为 0。
- 键盘 Tab 首焦点在所有页面均进入应用链接并匹配 `:focus-visible`。
- 系统 `prefers-reduced-motion: reduce` 在所有页面均生效；实测最大 animation/transition 时长为 `0.00001s`（0.01ms）。
- 修复 `/student/learning` 顶栏在 360px 下因品牌、返回链接和标题挤压而超出视口的问题；品牌文字在窄屏可截断显示。
- 修复 Practice 内 Mini Lab 选择框按最长选项扩张到容器外的问题；选择框现在限制在卡片宽度内。
- Web Node 测试 **58/58 passed**，TypeScript 通过，ESLint **0 errors / 2 existing hook warnings**，Next production build **24/24 routes** 成功。

## 边界

这是学生核心页面的工程可用性抽查，不构成完整 P0-04 或 WCAG 验收。尚未覆盖 11 组代表页的逐组视觉签收、读屏器、浏览器缩放、颜色对比、真实设备/输入法，以及教师/管理员等工作区。
