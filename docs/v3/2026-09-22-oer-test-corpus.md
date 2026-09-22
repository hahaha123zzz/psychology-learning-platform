# V3 开放教材测试语料

更新时间：2026-09-22。此清单记录教材来源及其在本项目中的允许用途；它不是对第三方许可的法律解释。

## 首批

| ID | 教材 | 官方数字版 | 许可 | V3 用途 | 外部模型 |
| --- | --- | --- | --- | --- | --- |
| `research-methods-psychology-4e` | *Research Methods in Psychology*, 4th ed. | <https://kpu.pressbooks.pub/psychmethods4e/open/download?type=pdf> | CC BY-NC-SA 4.0（页面也出现旧版本来源说明，以当前书籍的 License 区为准） | 主基准；研究设计、测量、统计、实验方法 | 未批准；本阶段仅本地 |
| `openstax-psychology-2e` | *Psychology 2e* | <https://assets.openstax.org/oscms-prodcms/media/documents/Psychology2e_WEB.pdf> | CC BY-NC-SA 4.0 | 泛化与图表/章节规模对照 | **禁止**。官方页面禁止摄入 LLM 或生成式 AI 服务；仅本地离线 |

## 第二批（首批稳定后加入）

| ID | 教材 | 官方数字版 | 许可 | 用途 |
| --- | --- | --- | --- | --- |
| `intro-psychology-canadian-1e` | *Introduction to Psychology – 1st Canadian Edition* | <https://opentextbc.ca/introductiontopsychology/open/download?type=pdf> | CC BY-NC-SA 4.0 | 普通心理学泛化、研究方法章节 |
| `essentials-cognitive-psychology-2e` | *Essentials of Cognitive Psychology*, v2.0 | <https://una.pressbooks.pub/essentials-cognitive-psychology/open/download?type=pdf> | CC BY-NC-SA 4.0 | 认知/记忆概念关系与章节检索 |
| `principles-social-psychology-2e` | *Principles of Social Psychology*, 2nd ed. | <https://wsu.pressbooks.pub/social-psychology/open/download?type=pdf> | CC BY-NC-SA 4.0 | 社会心理学的跨领域泛化 |

## 下载与使用规则

运行 `server\.venv\Scripts\python.exe scripts\fetch_oer_test_corpus.py --source first-batch --accept-licenses` 下载首批文件。文件会保存到 Git 忽略的 `data/oer-textbooks/`，并生成含 URL、许可、下载时间、大小与 SHA-256 的 `manifest.json`。

评测标注、运行结果可以进入仓库；教材 PDF、提取出的原文、图片和表格数据不能提交。无真实坐标的 PDF 对象必须保留 `bbox: null` 或等价的不可用状态，不能为追求视觉演示虚构 bbox。
