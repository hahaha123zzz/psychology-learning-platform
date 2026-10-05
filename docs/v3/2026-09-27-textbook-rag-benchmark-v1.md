# Textbook RAG Benchmark v1 提案

更新时间：2026-09-27。本文是 `docs/v3/2026-09-22-oer-test-corpus.md` 语料清单的超集扩展建议：保留首批/第二批心理学语料，新增统计、数学、物理、生物、计算机、中文、超长、复杂版式与扫描类教材，构成可长期回归的教材 RAG 基准。

事实核实说明：许可与下载信息均于 2026-09-27 通过官方页面或仓库核实；页数标注"约"者以下载实测为准。本文不是法律意见；接入任何一本书之前，以官方页面当日许可声明为准。

## Part 1：推荐教材总表

核心 14 本（一本可兼任多个角色）：

| # | 建议 ID | 教材 | 角色类型 | 语言 | 页数（约） | 格式 | 许可 | 外部模型 API |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `openstax-psychology-2e` | Psychology 2e | B 心理学主基准（已在库） | 英 | ~745 | PDF/网页 | CC BY-NC-SA + AI 禁令 | **禁止** |
| 2 | `research-methods-psychology-4e` | Research Methods in Psychology, 4e | A 标准版式 + 研究方法（已在库） | 英 | ~400（实测） | Pressbooks PDF/网页/EPUB | CC BY-NC-SA 4.0 | 未批准；本地 |
| 3 | `openstax-introductory-statistics-2e` | Introductory Statistics 2e | C 统计表格/数值 | 英 | ~900 | PDF/网页 | CC BY-NC-SA + AI 禁令 | **禁止** |
| 4 | `openintro-statistics-4e` | OpenIntro Statistics, 4e | C 统计（外部可用对照） | 英 | ~430 | PDF/Leanpub | CC BY-SA 3.0 | 可 |
| 5 | `active-calculus-single-2e` | Active Calculus (Single Variable), 2e | D 公式密集 | 英 | ~600（实测） | PDF + PreTeXt HTML | CC BY-SA 4.0 | 可 |
| 6 | `openstax-college-physics-2e` | College Physics 2e | E 综合压力 | 英 | ~1,400 | PDF/网页 | CC BY-NC-SA + AI 禁令 | **禁止** |
| 7 | `openstax-biology-2e` | Biology 2e | F 图 | 英 | ~1,578 | PDF/网页 | CC BY-NC-SA + AI 禁令 | **禁止** |
| 8 | `openstax-aandp-2e` | Anatomy and Physiology 2e | F 图 + I 超长 | 英 | ~1,600 | PDF/网页 | CC BY-NC-SA + AI 禁令 | **禁止** |
| 9 | `py4e` | Python for Everybody | G 代码 + A 纯文本 | 英 | ~250 | HTML/PDF/EPUB | CC BY 4.0 | 可 |
| 10 | `systemsapproach-computer-networks` | Computer Networks: A Systems Approach 6.x | G 图文 | 英 | ~900（实测） | HTML/PDF（源码构建） | CC BY 4.0 | 可 |
| 11 | `d2l-en` | Dive into Deep Learning | G 代码 + J 复杂版式 | 英 | ~1,000 | HTML/PDF（构建） | 正文 CC BY-SA 4.0；代码 MIT | 可 |
| 12 | `d2l-zh-pytorch-2e` | 《动手学深度学习（PyTorch版）》v2.0.0 | H 中文 + G 代码 | 中 | ~800（实测） | PDF（GitHub Release）/HTML | Apache 2.0（开源版） | 可 |
| 13 | `hello-algo-zh` | 《Hello 算法》 | H 中文 + 图 + 代码 | 中 | ~600（实测） | PDF/EPUB（Release）/HTML | CC BY-NC-SA 4.0 | 灰区；默认本地 |
| 14 | `james-principles-1890-scan` | The Principles of Psychology (1890, Vol.1) | K 扫描（未来 OCR） | 英 | ~700（扫描） | 扫描 PDF/JP2 | 公有领域 | 无限制 |

可选补充（不进核心矩阵）：`titchener-experimental-psychology-1901`（K 类第二本，主题恰好是"实验心理学"）；已有第二批心理学清单（认知/社会/导论）继续作为泛化语料；NOBA 项目单模块（CC BY-NC-SA 4.0，短文，用于快速冒烟）。

类型覆盖核对：心理学 2（1、2 兼）、研究方法 1（2）、统计/数学 3（3、4、5）、物理 1（6）、生物/医学 2（7、8）、计算机 3（9、10、11）、中文 2（12、13）、超长 1（8 兼）、复杂版式 1（11 兼）、扫描 1（14）。

## Part 2：每本教材详细分析

### 1. OpenStax Psychology 2e（B 类主基准，已在库）

- 学科：心理学导论；作者：Spielman 等人，Rice University OpenStax。
- 语言：英文；PDF/网页免费；约 745 页；许可 CC BY-NC-SA（OpenStax 全库当前声明）。
- 官方来源：https://openstax.org/details/books/psychology-2e （PDF 直链已在语料清单）。
- 已完成本地 `hybrid-v1→v4` 基线：4,160 Chunk、页级 Recall@5=1.0、教材外拒答=1.0（见 2026-09-23/24 基线文档）。
- 测试价值：平台锚点。第 2 章覆盖自变量/因变量、混淆变量、随机分配、信度/效度等实验心理学核心术语对；相似概念密度高（reliability vs validity、independent vs dependent、random sample vs random assignment），是语义检索与概念消歧的金矿；图题、表格与跨章引用均衡。
- 风险：官方逐页声明禁止摄入 LLM/生成式 AI 服务 → 仅本地离线；不得进入任何外部生成/嵌入调用路径，也不得进入演示或生产内容库。

### 2. Research Methods in Psychology, 4th ed.（A + 研究方法，已在库）

- 学科：心理学研究方法；作者：Price、Jhangiani、Chiang 等（KPU Pressbooks）。
- 语言：英文；Pressbooks 提供 PDF/网页/EPUB；许可 CC BY-NC-SA 4.0。
- 官方来源：https://kpu.pressbooks.pub/psychmethods4e/open/download?type=pdf （已在语料清单）。
- 测试价值：版式最"标准"的文本流（Pressbooks 输出），适合做 A 类基线：章节识别、Paragraph 解析、Reading Order、纯文本 BM25/Dense 对照。内容与实验心理学课程直接对口：实验设计、被试间/被试内设计、效度/信度、抽样、伦理，出题最贴合本平台最终用户。
- 风险：NC-SA；外部模型未批准，本阶段仅本地。

### 3. OpenStax Introductory Statistics 2e（C 类）

- 学科：统计导论；OpenStax；英文；PDF/网页；约 900 页。
- 官方来源：https://openstax.org/details/books/introductory-statistics-2e 。
- 测试价值：表格最密集的候选之一（正态分布表、t 表、卡方表等附录大表）+ 大量数值、公式与步骤化例题。专测：Table Parser、数字是否被错误切分、"表格-正文关系"（例题引用表值）、数值型问题的 grading（需要 numeric tolerance）、跨表格跨章节引用。
- 风险：OpenStax 同款 AI 禁令 → 仅本地。

### 4. OpenIntro Statistics 4e（C 类，外部可用对照）

- 学科：统计导论（含因果推断、回归）；作者 Diez、Çetinkaya-Rundel、Lehr；2019 年第 4 版（2022 更新）。
- 语言：英文；免费 PDF；约 430 页；许可 CC BY-SA 3.0；源码在 GitHub。
- 官方来源：https://www.openintro.org/book/os/ 。
- 测试价值：与第 3 本形成"同题材、不同版式、不同许可"的对照对：OpenIntro 有页边注、练习框、图表（散点/直方图）与数据附录，版式更复杂；且它是少数**允许发送外部 Embedding API** 的统计教材——真实 Embedding 选型实验应优先在它和 `active-calculus`、`py4e`、`d2l-en`、`d2l-zh` 上做，OpenStax 结果只做本地对照。
- 风险：SA 传染性要求衍生数据集同样开放；外部调用时仍选不留存承诺的供应商。

### 5. Active Calculus (Single Variable) 2e（D 类）

- 学科：微积分；作者 Matthew Boelkins（GVSU）；PreTeXt 编写。
- 语言：英文；免费 HTML（MathJax 渲染公式）+ 免费 PDF；许可 CC BY-SA 4.0；源码 GitHub。
- 官方来源：https://activecalculus.org （2e PDF：activecalculus.org 下载页）。
- 测试价值：全项目公式密度上限。行内公式、独立公式、上下标、希腊字母、积分/极限符号全部以原生 TeX 排版——且 **HTML 版的 MathJax 源是公式的可信 ground truth**，可以拿 PDF 解析结果与 HTML 版逐节对照，评"公式 LaTeX 恢复可靠性"。测：Formula Object、公式 bbox、Chunk 是否切断公式、公式上下文检索（"导数的极限定义在什么条件下存在？"）。
- 风险：无特殊限制；SA 同上。

### 6. OpenStax College Physics 2e（E 类综合压力）

- 学科：大学物理（代数基础）；OpenStax；英文；PDF/网页；约 1,400 页。
- 官方来源：https://openstax.org/details/books/college-physics-2e 。
- 测试价值：单一文档内同时含正文、公式、单位、矢量图、数据表、例题计算与章末习题——是最接近"全能力综合压力测试"的一本。测：图文混排阅读顺序、单位符号（m/s²）切词、例题框、有效数字、以及"accuracy vs precision"这类物理语境概念对。
- 风险：OpenStax AI 禁令 → 仅本地。

### 7. OpenStax Biology 2e（F 类）

- 学科：生物学导论；OpenStax；英文；PDF/网页；1,578 页。
- 官方来源：https://openstax.org/details/books/biology-2e 。
- 测试价值：图约占全书三分之一：示意图、显微照片、图题、图内文字、正文显式引用（"如图 X 所示"）。测：figure 对象与 caption 关联、图文引用消解、页级 ObjectAsset 完整性；为未来视觉 RAG/ColPali 预留标准问题集（图内标注问题 → 现阶段必须 `EXPECTED_REFUSAL`）。
- 风险：OpenStax AI 禁令 → 仅本地。

### 8. OpenStax Anatomy and Physiology 2e（F + I 类超长）

- 学科：解剖与生理学；OpenStax；英文；PDF/网页；约 1,600 页、大体积 PDF。
- 官方来源：https://openstax.org/details/books/anatomy-and-physiology-2e 。
- 测试价值：核心矩阵里的"超长教材"：Multipart Upload、SHA-256 校验、断点续传、Celery 长任务、页级 checkpoint、Worker 崩溃恢复、索引构建时长、大语料检索延迟全部一次覆盖；同时它也是图片密度顶级（解剖图）的 F 类书。
- 风险：OpenStax AI 禁令 → 仅本地；解析耗时，建议先在测试库验证 checkpoint 恢复再全量跑。

### 9. Python for Everybody（G 类，许可最干净）

- 学科：Python 编程入门；作者 Charles R. Severance（Dr. Chuck）。
- 语言：英文；py4e.com 免费 HTML/EPUB/PDF；许可 CC BY 4.0（站点页脚声明）。
- 官方来源：https://www.py4e.com/book 。
- 测试价值：Code Block 为主的入门教材：短代码块、行内代码、控制台输出块与英文正文混排。测：代码块完整性（不能把 `for` 循环从中间切断）、代码上下文检索、纯文本 Chunk 边界。CC BY 4.0 无 NC 限制，可放心进外部 Embedding 选型实验。
- 风险：无特殊限制。

### 10. Computer Networks: A Systems Approach 6.x（G 类图文）

- 学科：计算机网络；作者 Peterson、Davie；开源 6.2-dev。
- 语言：英文；在线 HTML（Sphinx）；PDF 可从 GitHub 源码构建；许可 CC BY 4.0。
- 官方来源：https://book.systemsapproach.org ；https://github.com/SystemsApproach/book 。
- 测试价值：大量协议示意图 + 正文交叉引用（"见第 X 章"）+ 伪代码块 + 表格（协议头字段表）。测：跨章引用检索（跨章节问题类型的理想素材）、图题关联、Sphinx 生成版式解析。
- 风险：无特殊限制；注意"衍生作品"条款在 README 中要求先与作者沟通，直接本地解析与检索测试不受影响。

### 11. Dive into Deep Learning（d2l-en，G + J 复杂版式）

- 学科：深度学习；作者 Zhang、Lipton、Li、Smola。
- 语言：英文；免费 HTML + 可构建 PDF；正文 CC BY-SA 4.0，示例代码 modified MIT。
- 官方来源：https://D2L.ai ；https://github.com/d2l-ai/d2l-en 。
- 测试价值：核心矩阵里的"复杂版式"担当：Sphinx 排版带来的侧边栏、讨论提示框、高亮代码块、行间公式、大量图表与交叉链接，是 Parser 边界测试的理想对象（页眉页脚、提示框归属、代码块-正文边界）。内容与深度学习术语英文标准表述强相关，适合技术术语消歧（"attention"在三本书语境下含义不同）。
- 风险：SA 对衍生标注的传染性；外部调用选不留存供应商。

### 12. 《动手学深度学习（PyTorch版）》（d2l-zh，H 类中文 + G 类）

- 学科：深度学习（中文）；作者阿斯顿·张等；GitHub 开源。
- 语言：简体中文（大量英文术语）；PDF 26.1 MB 随 v2.0.0 Release 发布；开源版仓库 License 为 **Apache 2.0**（d2l-zh 仓库 LICENSE；注意纸质书由人民邮电出版社出版、版权另算，本基准只用开源版 PDF）。
- 官方来源：https://zh.d2l.ai ；https://github.com/d2l-ai/d2l-zh/releases （`d2l-zh-pytorch-2.0.0.pdf`）。
- 测试价值：中文 RAG 首选：中英术语混排（"注意力机制（attention）"）、全角/半角标点、中文分句与 Chunk 边界、中文 BM25 分词策略、中文 Embedding。同时继承 d2l 的代码+公式+图复杂度。
- 风险：开源版 Apache 2.0 允许外部调用；务必在 manifest 记录使用的是 Release 固定版本，避免与纸质书内容混淆。

### 13. 《Hello 算法》（hello-algo，H 类中文 + 图 + 代码）

- 学科：数据结构与算法（中文）；作者 krahets 与社区；GitHub 129k+ stars。
- 语言：简体中文；PDF/EPUB 随 Release 发布（1.3.0），另有在线版 hello-algo.com；全仓库（文字、代码、图片）CC BY-NC-SA 4.0。
- 官方来源：https://www.hello-algo.com ；https://github.com/krahets/hello-algo/releases 。
- 测试价值：图驱动讲解（每个数据结构一张原创插图）、12 种语言代码块、中文正文——测"中文图文混排"与"图题-正文-代码三者关系"的最佳样本；概念辨析题素材多（数组 vs 链表、哈希冲突解决、堆 vs 二叉搜索树）。
- 风险：NC-SA → 外部 API 属灰区：内部非商业测试可用，但发送给商业供应商前需确认其数据政策；默认仅本地。NC 限制也意味着平台商业化后此书不能进入对外内容库。

### 14. The Principles of Psychology, Vol.1（1890，K 类扫描）

- 学科：心理学经典（实验心理学奠基之作）；作者 William James；纽约 Henry Holt 1890 年版。
- 语言：英文（古籍排印）；Internet Archive 多个扫描版本（Google/大学馆藏数字化），约 700 页/卷，已带 ABBYY OCR 层可做对照；版权状态 NOT_IN_COPYRIGHT（公有领域）。
- 官方来源：https://archive.org/details/principlesofpsyc1890jame （另有 Harvard/多伦多大学扫描版）。
- 测试价值：未来 OCR Benchmark 的标准样本：image-only 扫描、古籍字体、页边注、脚注、流水页码不规则；主题恰好落在实验心理学，与平台课程语境一致。可用 Archive 自带 OCR 层作为"OCR 基线对照"，评我们自建 OCR 的 CER/WER。
- 风险：无版权限制；仅注意 Internet Archive 的批量抓取技术条款（单本人工下载无碍）。备选/第二本：Titchener《Experimental Psychology: A Manual of Laboratory Practice》(1901)（https://archive.org/details/experimentalpsyc01titcuoft ，同样公有领域）。

## Part 3：教材测试矩阵

★★★★★ 非常适合；★★★★ 适合；★★★ 一般；★★ 较少；★ 几乎没有；— 不适用。

| 教材 | Text | 中文 | Figure | Table | Formula | Code | 长文档 | 复杂版式 | OCR（未来） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Psychology 2e | ★★★★★ | — | ★★★ | ★★ | ★ | — | ★★★ | ★★ | — |
| Research Methods 4e | ★★★★★ | — | ★★ | ★★★ | ★★ | — | ★★ | ★ | — |
| Introductory Statistics 2e | ★★★★ | — | ★★★ | ★★★★★ | ★★★★ | — | ★★★★ | ★★ | — |
| OpenIntro Statistics 4e | ★★★★ | — | ★★★★ | ★★★★★ | ★★★★ | — | ★★★ | ★★★（页边注） | — |
| Active Calculus 2e | ★★★★ | — | ★★★ | ★★ | ★★★★★ | — | ★★★ | ★★ | — |
| College Physics 2e | ★★★★ | — | ★★★★★ | ★★★ | ★★★★★ | — | ★★★★ | ★★★ | — |
| Biology 2e | ★★★★★ | — | ★★★★★ | ★★★ | ★ | — | ★★★★★ | ★★★ | — |
| A&P 2e | ★★★★★ | — | ★★★★★ | ★★★ | ★★ | — | ★★★★★ | ★★★ | — |
| Python for Everybody | ★★★★ | — | ★ | ★★ | ★ | ★★★★ | ★★ | ★ | — |
| Computer Networks | ★★★★ | — | ★★★★ | ★★★ | ★★ | ★★★ | ★★★★ | ★★ | — |
| D2L（英文） | ★★★★ | — | ★★★★ | ★★★ | ★★★★ | ★★★★★ | ★★★★ | ★★★★★ | — |
| 动手学深度学习（中） | ★★★★ | ★★★★★ | ★★★★ | ★★★ | ★★★★ | ★★★★★ | ★★★★ | ★★★★ | — |
| Hello 算法 | ★★★★ | ★★★★★ | ★★★★★ | ★★★ | ★★ | ★★★★★ | ★★★ | ★★★ | — |
| James《心理学原理》扫描版 | ★★★★（OCR 后） | — | ★ | ★★ | ★ | — | ★★★ | ★★★（古籍） | ★★★★★ |

读法：横看一本书承担哪些测试面；竖看某一能力（如 Table）应优先在哪些书上测。例如：表格能力 → Introductory Statistics 2e + OpenIntro；公式 → Active Calculus + College Physics 2e；中文 → d2l-zh + hello-algo；超长上传 → A&P 2e；复杂版式 → d2l-en；拒答与概念消歧 → Psychology 2e + Research Methods 4e。

J 类补充：开放教材普遍单栏。双栏/脚注/跨栏图边界建议用 CC BY 4.0 的期刊长文（PLOS/PeerJ 综述）或 OmniDocBench 内的教科书/报纸样本补充，单独归入 `j-layout-extra` 子集，不与教材基准混算。

## Part 4：官方下载来源

统一入库方式沿用 `scripts/fetch_oer_test_corpus.py`：文件存 Git 忽略的 `data/oer-textbooks/`，`manifest.json` 记录 URL、许可、下载时间、大小与 SHA-256；教材二进制与提取原文永不提交入库。

| 书 | 官方获取 |
| --- | --- |
| Psychology 2e | https://openstax.org/details/books/psychology-2e （PDF 直链见语料清单） |
| Research Methods 4e | https://kpu.pressbooks.pub/psychmethods4e/open/download?type=pdf |
| Introductory Statistics 2e | https://openstax.org/details/books/introductory-statistics-2e |
| OpenIntro Statistics 4e | https://www.openintro.org/book/os/ （免费 PDF；Leanpub 可选） |
| Active Calculus 2e | https://activecalculus.org （HTML 与 PDF 免费；PDF 直链在官网下载区） |
| College Physics 2e | https://openstax.org/details/books/college-physics-2e |
| Biology 2e | https://openstax.org/details/books/biology-2e |
| A&P 2e | https://openstax.org/details/books/anatomy-and-physiology-2e |
| Python for Everybody | https://www.py4e.com/book （HTML/EPUB/PDF 免费入口） |
| Computer Networks | https://book.systemsapproach.org （在线版；PDF 从 https://github.com/SystemsApproach/book 源码构建） |
| D2L 英文 | https://D2L.ai （HTML；PDF 从仓库构建） |
| 动手学深度学习（中） | https://github.com/d2l-ai/d2l-zh/releases → `d2l-zh-pytorch-2.0.0.pdf` |
| Hello 算法 | https://github.com/krahets/hello-algo/releases → PDF/EPUB；在线版 https://www.hello-algo.com |
| James 1890 扫描 | https://archive.org/details/principlesofpsyc1890jame |
| Titchener 1901（可选） | https://archive.org/details/experimentalpsyc01titcuoft |

建议给 `fetch_oer_test_corpus.py` 增加 `--source batch3-stats-math --source batch4-cs-chinese --source batch5-long-scan` 分批开关，逐批下载、逐批接题，不要一次性全量接入。

## Part 5：版权与 AI 使用限制（红线）

1. **OpenStax 全库（Psychology 2e、College Physics 2e、Biology 2e、A&P 2e、Introductory Statistics 2e）**：许可为 CC BY-NC-SA；且官方在每本书页面底部声明："This book may not be used in the training of large language models or otherwise be ingested into large language models or generative AI offerings without OpenStax's permission."（2026-09-27 核实）。→ 这五本**只能本地离线解析与检索评测**：禁止发送任何外部生成/嵌入 API，禁止进入演示、生产、真实课程数据路径。本项目现有约定与此一致。
2. **NC 许可通用含义**（OpenStax、Research Methods 4e、Hello 算法、NOBA）：内部非商业测试可用；平台商业化后不得进入对外服务内容库；发给商业供应商 API 属灰区，默认仅本地。
3. **CC BY-SA / CC BY / Apache 2.0**（OpenIntro、Active Calculus、Py4e、Computer Networks、D2L、d2l-zh 开源版）：允许外部调用与商用，但必须署名；SA/Apache 对衍生内容有对应义务。外部调用仍建议选择承诺不留存、不用于训练的供应商，并把"调用了哪本书、哪个供应商"记录进评测工件。
4. **公有领域扫描件**（James 1890、Titchener 1901）：无版权限制；注意 Archive 站点的批量抓取技术条款。
5. 原则重申：**公开下载 ≠ 可以送外部 AI**。OpenStax 是本项目最重要的反例。评测中凡涉及"外部 Embedding/生成"对比，只用第 4/9/10/11/12 号书；涉及 LLM judge 打分时同理——OpenStax 派生的问题与答案不要发给外部 judge，可用确定性指标或本地模型。
6. 教材 PDF、提取正文、图片、表格数据不得提交 Git；标注与运行结果可以入库（与现有规则一致）。

## Part 6：RAG Benchmark 问题设计

每本核心书 8–12 题，总规模约 100–150 题；本节给出代表性样题与设计规则。题目先落 `contracts/rag-eval/` 数据集（沿用 `rag-eval/v3` 的 `cases` 形态），页码/章节/对象金标人工标注后填充。

题型标签（10 类）：`fact` 精确事实 / `semantic` 语义（问题不含原文关键词）/ `cross_chunk` 跨段落 / `cross_chapter` 跨章节 / `table` 表格 / `figure` 图片 / `formula` 公式 / `out_of_book` 教材外 / `ambiguous` 歧义 / `confusable` 相似概念。

### Psychology 2e（锚点书）

1. `fact`：操作性定义（operational definition）的作用是什么？——第 2 章单段可答。
2. `confusable`：信度（reliability）与效度（validity）的区别？两者能否独立成立？——测概念混淆。
3. `confusable`：随机分配（random assignment）与随机取样（random sampling）分别影响什么？
4. `semantic`："为什么实验里要设置控制组，而不是只测实验组前后差异？"——原文未必出现"控制组的作用"字面表述，测 Dense 通道。
5. `cross_chunk`/`cross_chapter`：经典条件反射中的"泛化"与"辨别"分别指什么，各举一例？
6. `figure`：条件反射习得曲线图的横纵轴是什么？→ `EXPECTED_REFUSAL`（当前无图片 RetrievalUnit；只能以图注段落命中，不得宣称图片检索成功）。
7. `ambiguous`："What is a confounding variable, and give an example from this book?"（跨研究设计与统计章节）。
8. `out_of_book`："行为主义如何解释光的双缝干涉现象？"→ `should_refuse: true`。

### Research Methods 4e（研究方法 + 标准版式基线）

1. `fact`：被试内设计中练习效应（practice effect）如何威胁内部效度？
2. `confusable`：内部效度 vs 外部效度；单盲 vs 双盲。
3. `semantic`："如果被试知道自己在被观察，行为会改变吗？"——对应霍桑效应/需求特征（原文关键词不同）。
4. `table`：书中研究设计类型对照表：哪种设计适合因果推断？
5. `cross_chapter`：抽样方法（概率/非概率）与统计推断的关系？
6. `out_of_book`："1960 年代著名的米尔格拉姆实验具体数据是多少？"（若书未含该细节则拒答；标注时核实）。

### Introductory Statistics 2e / OpenIntro 4e（统计对）

1. `table`：查正态分布表：z=1.96 对应的尾部概率是多少？——必须允许 numeric grading。
2. `table`：t 分布表：自由度 10、双尾 0.05 的临界值？
3. `formula`/`semantic`："两组均值差异什么时候用 t 分布而不是正态分布？"（σ 未知/小样本）。
4. `fact`：第一类错误与第二类错误的定义及关系。
5. `cross_chunk`：中心极限定理对样本均值的分布意味着什么？条件是什么？
6. `confusable`/`ambiguous`："standard deviation 和 standard error 有什么区别？"（跨章出现）。
7. `out_of_book`："2023 年美国 GDP 是多少？"→ 拒答。
8. OpenIntro 专属 `cross_chapter`： observational study 能否支持因果结论？与第 1 章实验设计呼应。

### Active Calculus 2e（公式）

1. `formula`：导数的极限定义是什么？在什么条件下不存在？
2. `formula`：链式法则的公式形式及其适用条件。
3. `semantic`："瞬时变化率和割线斜率是什么关系？"——测语义通道（不出现 "derivative definition" 字样）。
4. `cross_chapter`：微积分基本定理把微分与积分如何连接？
5. `fact`：泰勒多项式的截断误差含义。
6. `out_of_book`："如何用微积分计算柳树的基因组大小？"→ 拒答。

### College Physics 2e（综合）

1. `formula`：匀加速直线运动的三个运动学公式及适用条件。
2. `confusable`：accuracy 与 precision 的区别（测量章）。
3. `table`：常用单位换算表：1 马力等于多少瓦？
4. `figure`：自由落体实验图的装置组成？→ `EXPECTED_REFUSAL`。
5. `cross_chunk`：牛顿第三定律与动量守恒的关系。
6. `out_of_book`："薛定谔的猫在书中的哪个实验出现？"（书非量子教材细节 → 拒答/低置信）。

### Biology 2e（图）

1. `fact`：线粒体的功能（正文段）。
2. `figure`：细胞膜流动镶嵌模型图中标注的蛋白质名称？→ `EXPECTED_REFUSAL`（图内文字）。
3. `semantic`："植物如何把光能变成化学能中间载体？"——对应光反应（原文无同义字面）。
4. `cross_chapter`：孟德尔分离定律与减数分裂的联系。
5. `table`：碱基配对规则表。
6. `out_of_book`："PCR 引物 Tm 值怎么算？"（书未覆盖该细节 → 拒答；标注时核实）。

### Python for Everybody（代码）

1. `fact`：Python 中 `try/except` 的执行顺序。
2. `code`：书里解析 JSON 的标准代码模式是什么？
3. `semantic`："怎么防止程序在读文件崩溃？"→ 对应异常处理章。
4. `cross_chunk`：函数、参数与返回值的组合规则。
5. `out_of_book`："如何用 asyncio 写并发爬虫？"（书不覆盖 → 拒答）。

### Computer Networks（图文）

1. `fact`：TCP 与 UDP 的核心区别。
2. `figure`：三层交换架构图的箭头含义？→ `EXPECTED_REFUSAL`。
3. `cross_chapter`：可靠传输机制如何分布在多层（链路重传 vs TCP 重传）？
4. `table`：以太网帧格式字段表：类型字段的作用？
5. `out_of_book`："5G NR 的调度算法细节？"→ 拒答。

### D2L 英文（复杂版式 + 代码）

1. `code`：书中实现 softmax 的代码片段用了什么数值稳定技巧？
2. `formula`：注意力机制 Q/K/V 缩放点积公式。
3. `semantic`："训练时为什么要把一部分神经元随机置零？"→ dropout。
4. `cross_chapter`：CNN 与 RNN 在参数共享方式上的差异。
5. `fact`：批量归一化在训练与推理阶段的差异。
6. `out_of_book`："如何微调 GPT-5？"→ 拒答。

### 动手学深度学习（中文）

1. `fact`：多层感知机为什么要用非线性激活函数？
2. `semantic`："模型在训练集越来越好、验证集变差，书中给的方法叫什么？"→ 过拟合与权重衰减（字面不同）。
3. `code`：书里 DataLoader 的 num_workers 参数作用（中文正文 + 代码混排）。
4. `confusable`：L2 正则化与 Dropout 的区别。
5. `cross_chapter`：注意力机制与 RNN 的关系。
6. `ambiguous`："epoch 是什么？"（中文术语表 + 正文多处）。
7. `out_of_book`："如何在鸿蒙系统上部署模型？"→ 拒答。

### Hello 算法（中文）

1. `fact`：时间复杂度 O(n log n) 的含义。
2. `confusable`：数组与链表的优缺点对比（图 + 表 + 正文三方）。
3. `semantic`："字典这个结构在书中怎么实现的，冲突了怎么办？"→ 哈希表（避免"哈希"字面出现）。
4. `figure`：快速排序分治动画图的哨兵划分过程？→ `EXPECTED_REFUSAL`（图内容）。
5. `cross_chapter`：动态规划与前缀和/记忆化搜索的关系。
6. `out_of_book`："如何用 Rust 写操作系统内核？"→ 拒答。

### 跨书专项（独立子集）

- `ambiguous`："variance 是什么？"——在统计书（方差）与 Physics（无）/Psych（统计学基础）语境下的答案差异，测 Query Analyzer 章节过滤。
- `ambiguous`："power 是什么？"——统计功效 vs 物理功率（两本书）。
- `confusable`："significant 在统计里的含义与日常语义差异"。
- `cross_book`（可选，v2 再启用）：同一概念在不同书的表述差异。

## Part 7：Gold Standard Schema

用户提议的字段（question_id、book_id、question、question_type、expected_answer、expected_chapter、expected_section、expected_page、expected_object_id、expected_bbox、allowed_pages、negative_pages、should_refuse、notes）**方向正确**，但建议做如下修正与扩展，并尽量演进现有 `contracts/rag-eval/v3-dataset.schema.json`（已有 `documents/objects/cases`、`relevant_object_ids`、`allowed_evidence_ids`、`expected_refusal`、`answer_points`），而不是另起一套：

| 字段 | 评价 | 建议 |
| --- | --- | --- |
| question_id / book_id / question / question_type | 合理 | 增加 `language`、`difficulty`、`expected_channel`（bm25/dense/hybrid/visual-future） |
| expected_answer | 合理但不够 | 拆为 `answer_points`（已有）+ `gold_aliases`（同义答案）+ `grading_mode`（exact/contains/keywords/numeric/semantic）+ `numeric_tolerance` + `units`；统计与物理题必须支持数值容差 |
| expected_chapter / section | 合理 | 用稳定章节对象 ID（平台已有章节对象），不要用渲染标题文本 |
| expected_page / allowed_pages | 合理 | `allowed_pages` 参与页级 Recall；`expected_page` 仅作首选标注 |
| expected_object_id / expected_bbox | **需修正** | 单对象不够。改为 `evidence: [{object_key, retrieval_unit_hint, page, quote, quote_start_offset}]` 数组；对象引用用**不可变资产键**而非数据库 ULID（重新解析会重建对象）；bbox 不静态存储，由 quote 在当前解析结果上重投影（沿用"无真实坐标保持 null"的现有约定） |
| negative_pages | 可选 | 标为可选并要求填写理由，避免标注成本失控 |
| should_refuse | 合理 | 细化为 `refusal_policy: hard_out_of_corpus / low_confidence` + `expected_refusal_reason`；图片/表格/公式类问题当前统一 `EXPECTED_REFUSAL` 并注明"待视觉/结构索引后解锁" |
| notes | 合理 | 保留 |

新增字段（平台治理对齐）：

- `schema_version`、`corpus_version`：数据集自身版本化，与 `book_edition`、`publication_snapshot_id`/`textbook_version_id` 绑定——题目金标只对特定教材版本有效。
- `answer_source`、`annotator`、`review_state`：区分"模型候选 + 人工复核"与"纯人工"，呼应平台"候选 ≠ 已审核"约定。
- `parser_assumptions`：该题金标基于哪种解析假设（如 Pressbooks 纯文本流），Parser 大改后提示复核。

建议物理组织为两个文件层：`questions.jsonl`（题目 + 答案金标 + 评测方式）与 `gold_evidence.jsonl`（检索目标），这样检索指标可以在生成指标之前独立跑（现有 runner 已是分层思路）。

## Part 8：评测指标

| 类别 | 指标 | 当前阶段（文本 RAG） | 后续阶段 |
| --- | --- | --- | --- |
| 检索 | Recall@1/3/5（chunk/page/chapter） | ✅ 已有页级；扩展 chunk/chapter | — |
| 检索 | MRR、NDCG@5 | ✅ 现有 NDCG@5；补 MRR | — |
| 检索 | Page Recall、Chapter Recall | ✅ 页级已有；Chapter 补 | — |
| 检索 | Object Recall | ✅ 段落对象已有（v4=0.625） | 扩展到 figure/table/formula 对象 |
| 检索 | Evidence Precision（首条相关率） | ✅ 建议（对应现有"首项页准确率"） | — |
| 检索 | bbox IoU | ⚠️ 有 PyMuPDF 段落级能力与金标（v4 首项 0.480661），继续采样评测 | 非文本对象 bbox IoU |
| Grounding | Citation Accuracy（票据→来源可解析且属于允许集合） | ✅ 建议（Evidence Ticket 已有） | — |
| Grounding | Page Accuracy、Citation Faithfulness | ✅ 建议 | — |
| 生成 | Answer Correctness | ✅ 确定性 grading（answer_points + 数值容差）优先；LLM judge 只用于无 NC 限制的书 | judge 规模化 |
| 生成 | Faithfulness / Unsupported Answer Rate | ✅ 建议（对照 RAGTruth 思路做词级/句级标注抽样） | — |
| 拒答 | Out-of-book Rejection Accuracy、False Refusal Rate | ✅ 已有拒答准确率；补 False Refusal | — |
| 解析 | Paragraph/Figure/Table/Formula Recall | ⚠️ 每书抽 5–10 页人工清点对象数量做采样金标 | 全量 |
| 解析 | Reading Order Accuracy | ⚠️ 采样人工评估（J 类重点） | 全量 |
| 上传 | Upload/Resume Success Rate、Hash Validation、Duplicate Detection | ✅ 已有集成测试，固化为指标输出 | — |
| 视觉 | 非文本 Object Recall、视觉检索 nDCG（ViDoRe 式） | — | 引入 ColPali/视觉索引后 |
| OCR | CER/WER（对照 Archive OCR 层） | — | K 类单独基准 |

运行与回归规则：每次运行记录 `corpus_version + 配置哈希（parser_version、chunk 算法、embedding 版本、融合参数）`，工件按现有命名存 `contracts/rag-eval/<book_id>-<config>-{run,report}.json`；把"页级 Recall@5 不回退、拒答准确率=1.0"等设为 regression gate，Parser/Chunk/Embedding/RRF 任何改动前后必须跑 Tier1（见 Part 11）。

## Part 9：GitHub Benchmark 参考项目

| 项目 | 可借鉴点 |
| --- | --- |
| opendatalab/OmniDocBench（CVPR 2025） | 文档解析评测金标准：9 类来源（含教科书、报纸）、19 版面类目、端到端 + 分项指标；借它的"来源×版面类目×指标"矩阵设计与标注格式，直接用于 Parser 对比 |
| beir-cellar/beir | 检索评测数据组织三件套 `corpus.jsonl / queries.jsonl / qrels.tsv`；我们的 questions/gold_evidence 拆分可对齐此惯例 |
| AI2 TQA（TextbookQA）+ opentqa（XTQA 仓库） | 教材多模态 QA 的数据结构：essay/diagram/问题三态、diagram 题型分离——与我们"图题先拒答"的策略同源 |
| NYU QuALITY | 长文档 MCQ：标注者通读全文出题、区分"速读可答/需细读"；长文档题（A&P 2e）可参考其分层难度 |
| DUDE / MP-DocVQA（Hi-VT5 仓库） | 多页文档 QA：页级金标、answer 类型分类、跨页证据——视觉 RAG 阶段的页级评测模板 |
| facebookresearch/KILT | provenance 指标（R-precision）：引用定位准确率的现成定义，直接映射 Citation Accuracy |
| explodinggradients/ragas | faithfulness / context precision / context recall 的可复用实现；注意 LLM judge 的版权边界（Part 5.5） |
| truera/trulens（RAG Triad） | groundedness/context relevance/answer relevance 三元评测框架，适合做平台内健康面板 |
| chen700564/RGB（RGB 论文配套） | 噪声鲁棒 / 负拒答 / 信息整合 / 反事实四测床；其"负拒答"子集直接对应教材外拒答，且含中文 |
| THUDM/LongBench | 双语（英/中）长上下文统一格式；中文子集可与 d2l-zh/hello-algo 结果互校 |
| doc-analysis/DocBank、IBM DocLayNet | token/bbox 级版面标注格式，Parser 布局输出的对照标准 |
| RAGTruth corpus | 词级幻觉标注规范，用于标定 Unsupported Answer Rate 的抽样集 |

## Part 10：相关论文（arXiv ID 已核验，标注★者为本次直接确认）

- Lewis et al., *RAG*, NeurIPS 2020 — arXiv:2005.11401 ★（奠基框架）
- Petroni et al., *KILT*, NAACL 2021 — arXiv:2009.02252 ★（provenance 评测）
- Thakur et al., *BEIR*, 2021 — arXiv:2104.08663（零样检索基准；ID 以 arXiv 页为准）
- Pang et al., *QuALITY*, NAACL 2022 — arXiv:2112.08608 ★（长文档出题方法：标注者通读 + 难度分层）
- Liu et al., *Lost in the Middle*, TACL 2023 — arXiv:2307.03172 ★（长上下文位置偏差 → 评估 Chunk 位置敏感性）
- Chen et al., *Dense X Retrieval*, 2023 — arXiv:2312.06648 ★（检索粒度=命题级 → Chunk 粒度决策依据）
- Chen et al., *RGB*, AAAI 2024 — arXiv:2309.01431 ★（RAG 四能力基准，含中文、负拒答）
- Niu et al., *RAGTruth*, 2024 — arXiv:2401.00396 ★（词级幻觉标注）
- Bai et al., *LongBench*, ACL 2024 — arXiv:2308.14508 ★（双语长上下文；v2：arXiv:2412.15204）
- Kembhavi et al., *TQA*, CVPR 2017 — 教材多模态 QA 数据集（AI2 发布；arXiv 版未在本次检索确认，引用以 AI2 官方页为准）；span 级解释后续工作：*XTQA* — arXiv:2011.12662 ★、*ISAAQ* — arXiv:2010.00562 ★
- Van Landeghem et al., *DUDE*, ICCV 2023 — arXiv:2305.08455 ★（多页文档 QA）
- Tito et al., *MP-DocVQA*, 2022 — arXiv:2212.05935 ★（页级金标）
- Cho et al., *M3DocRAG*, 2024 — arXiv:2411.04952 ★（多模态多页 RAG；视觉阶段参考）
- Faysse et al., *ColPali*, ICLR 2025 — arXiv:2407.01449 ★（视觉文档检索 + ViDoRe 基准；未来视觉 Embedding 选型必读）
- Ouyang et al., *OmniDocBench*, CVPR 2025 — arXiv:2412.07626 ★（解析评测标准）
- Wang et al., *MinerU*, 2024 — arXiv:2409.18839 ★（开源解析方案；其 *MinerU-Popo* 后处理 — arXiv:2605.24973 — 处理跨页段落/表格恢复与标题层级，与本项目解析器演进直接相关）
- Li et al., *DocBank*, COLING 2020 — arXiv:2006.01038 ★；Pfitzmann et al., *DocLayNet*, KDD 2022 — arXiv:2206.01062 ★（版面标注）

## Part 11：Benchmark v1 落地方案

**分层接入**（避免一次全量）：

- Tier 1（立即，回归门禁）：Psychology 2e + Research Methods 4e（已在库）+ Introductory Statistics 2e + OpenIntro 4e。先覆盖 B/C 两类与"外部可用对照"，题量约 40。
- Tier 2（中文 + 长文档）：d2l-zh + hello-algo + A&P 2e。中文与超长上传/解析链路。题量约 35。
- Tier 3（版式与图）：Active Calculus + College Physics 2e + Biology 2e + d2l-en。公式、综合压力、figure 对象、复杂版式。题量约 45。
- Tier 4（独立轨道，不与文本基准混算）：James 1890 扫描件（OCR）与 J 类期刊双栏补充。

**执行件**：

1. `fetch_oer_test_corpus.py` 增加批次开关，逐批下载并更新 `manifest.json`（含 SHA-256）。
2. 语料登记沿用 `2026-09-22-oer-test-corpus.md` 格式扩展第三/四批；每本书接题前先跑一次解析冒烟，记录对象清单告警。
3. 题集落 `contracts/rag-eval/<book_id>/questions.jsonl` + `gold_evidence.jsonl`，schema 按 Part 7 演进；金标页码/对象人工标注，模型只产候选并标记 `review_state`。
4. Runner 扩展为多书：输出 `<book_id>-<config>-run/report.json`；指标含 Part 8 当前阶段列。
5. Regression gate（Tier 1）：页级 Recall@5、NDCG@5、教材外拒答准确率、首项页准确率、首项 bbox IoU——任一显著回退即阻塞，与现有 hybrid-v4 基线数值对齐。

**明确不宣称**：本方案不含外部供应商模型效果结论（OpenStax 不可外发；其余书的真实 Embedding 选型在获得合规供应商前仅作计划）；视觉、bbox 引用与生成指标在相应能力落地前一律不报告"已完成"。每次系统修改后重跑 Benchmark，即可判断解析与 RAG 变好还是变坏。
