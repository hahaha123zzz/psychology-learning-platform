# V1 外部来源与代码复用登记

更新时间：2026-10-04

本登记把“设计借鉴”和“代码复用”分开。设计来源可以影响数据契约、交互和架构；只有经过许可证、版本和安全评审的仓库代码才能进入依赖或复制清单。

## 1. 当前实现原则

1. **优先复用成熟库的稳定边界**：例如 jsPsych 的 Timeline/Trial/Plugin、shadcn/ui 的 primitives，而不是复制整套应用。
2. **许可证先于代码**：MIT/Apache-2.0 可在保留版权和许可证声明后评估复用；GPL/AGPL/自定义附加条件必须单独审批，不能因为“开源”就直接放入本项目。
3. **保留本项目权威边界**：外部项目不能直接写 Mastery、ScoreRecord、Release、权限或长期 Memory。
4. **每次复用必须记录**：仓库 URL、commit/tag、许可证、复制/依赖路径、修改内容、第三方声明和测试。
5. **论文只作为研究支撑**：论文中的效果结论不能替代本项目真实教材、真实学生和真实班级评测。

## 2. 功能—来源—实施策略

| 功能 | 来源（官方入口） | 借鉴/复用策略 | 当前决定 |
|---|---|---|---|
| Learning Block Registry | [OpenTutor](https://github.com/zijinz456/OpenTutor)（MIT） | 借鉴 block-based workspace；自建白名单 registry，不复制其应用代码 | 首批实现 |
| Teaching Orchestrator | [DeepTutor](https://github.com/HKUDS/DeepTutor)（Apache-2.0） | 借鉴统一 orchestrator、Capability/Tool 分层；保留本项目 Policy Engine | 首批按现有 tutor service 改造 |
| Hint/Scaffold | [OATutor-Tooling](https://github.com/CAHLR/OATutor-Tooling)（MIT）及 guidance fading 研究 | 借鉴渐退支持和内容校验思路；不复制其题库或 BKT 参数 | 沿用现有确定性状态机 |
| Course/Scope/RBAC | [Open edX AuthZ/Studio 文档](https://docs.openedx.org/en/latest/developers/references/developer_guide/authentication/index.html) | 借鉴 Role + Scope、Author/Publisher 分离；不嵌入完整 LMS | 已开始实现 |
| TeachingAsset Template | [H5P 文档](https://h5p.org/documentation) 与[许可说明](https://h5p.org/licensing) | 借鉴 Content Type/Instance；只允许自有 Action whitelist 和 fallback | P8 实现 |
| Mini Lab Runtime | [jsPsych](https://www.jspsych.org/v8/developers/plugin-development/) | 优先使用官方 runtime 的 Timeline/Trial/Plugin 约束；raw TrialData 不直接更新学习状态 | P8 技术 Spike |
| Mini Lab Builder | [lab.js](https://lab.js.org/) | 仅作为未来 authoring 参照；V1 不同时引入第二套 runtime | 延后 |
| Question Bank/Quiz | [Moodle Quiz/Question Bank](https://docs.moodle.org/en/Question_bank) | 借鉴题目版本、Flag、Autosave、Attempt Summary；重新实现独立 Assessment Shell | P7 |
| Rubric/Grading | [Open edX ORA](https://docs.openedx.org/en/latest/educators/references/advanced_features/open_response_assessments/index.html) | 借鉴 criterion/options、claim/lock；AI suggestion 与教师决定分离 | P7 |
| ExperimentSchema | 项目总体设计文档 §35（领域模型与实验推理链为项目自有契约） | 字段结构直接按已批准设计落地；只复用实验心理学课程中的研究问题、变量、操作化、设计、预测与解释表达，不复制第三方系统代码；教材未给值时留空 | P2-04 首轮结构合同 |
| 文档解析 | [MinerU](https://github.com/opendatalab/MinerU)、[Docling](https://github.com/docling-project/docling) | 先做本地评测和 adapter；不把最终简单 Word 强行接入重型解析器 | P2 按评测决定 |
| RAG/Evidence | [Lewis et al. RAG](https://doi.org/10.48550/arXiv.2005.11401)、[Late Chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)、[ColPali](https://doi.org/10.48550/arXiv.2407.01449) | 借鉴检索后生成与候选策略；权限、版本、Evidence Closure 属于本项目约束 | 已有本地基线 |
| Design System | [PatternFly](https://www.patternfly.org/)、[Carbon](https://carbondesignsystem.com/)、[shadcn/ui](https://ui.shadcn.com/) | 借鉴 Data List/Drawer/Table/Wizard 和 primitives；视觉 Token 为 PsyLearn 自有 | 已开始实现 |

## 3. 已核验的许可证记录

| 来源 | 核验结论 | 对本项目的限制 |
|---|---|---|
| OpenTutor | GitHub 页面标注 MIT | 如复制代码，保留版权/许可证；当前只借鉴 Block 思路 |
| DeepTutor | GitHub 页面标注 Apache License 2.0 | 复制代码需保留 NOTICE/许可证并核对第三方依赖；当前只借鉴编排边界 |
| OATutor-Tooling | GitHub 页面标注 MIT | 仅可评估工具代码，不能把其教材/题库数据当作本项目内容 |
| H5P | 官方文档说明代码通常 MIT，但部分库/第三方代码可能 GPL；内容另有 CC 许可 | 只借鉴规范；正式集成前做逐包 license 扫描 |
| MinerU | 当前仓库说明为基于 Apache 2.0 的自定义 MinerU Open Source License | 不直接复制或加入运行依赖，先做隔离 Spike 和法律评审 |
| jsPsych | 采用官方 npm 包/文档边界（`jspsych@8.3.0`、`@jspsych/plugin-html-button-response@2.1.0`） | 固定版本、锁文件和插件清单；实验数据接口由本项目包裹 |

## 4. 代码进入仓库的登记模板

```text
Feature:
Source repository / documentation:
Commit or version:
License:
Reuse mode: dependency | adapted snippet | design-only
Files introduced or modified:
Copyright / NOTICE action:
Security and privacy review:
Tests added:
```

当前第一批代码使用 `design-only`：`web/lib/learning-blocks.ts`、`web/components/learning/LearningBlockStream.tsx` 和 `server/app/modules/tutor/service.py` 借鉴 OpenTutor 的 block 思路，但没有复制其源码、UI 资产或数据。jsPsych 运行时采用独立依赖接入，版本已写入本文件和 `package.json`/lockfile。

本批次已接入 jsPsych 运行时适配器：`web/lib/mini-lab/jspsych-adapter.ts` 负责 Intro → Predict → Run → Inspect → Explain → Summary 的白名单 Timeline，`web/components/learning/MiniLabRuntime.tsx` 负责浏览器端动态加载。原始 TrialData 只形成 `mini-lab.v1` 候选结果，不直接写入 Mastery、ScoreRecord 或长期 Memory。

## R2 本地教材输入登记（2026-10-04）

用户指定 `E:\项目\心里\TEXTBOOK\` 作为本轮本地构建/定位测试输入。当前只读取文件名、大小、文件头和 SHA-256，未解析正文、未转换、未索引，也未向任何外部模型或服务发送内容。10 个文件的头均为 OLE Compound File (`D0 CF 11 E0 A1 B1 1A E1`)，据此识别为旧式二进制 Word DOC；须先通过可靠本地工具转换，不能当作 OOXML DOCX 直接解析。源文件保持原路径/字节不变。

| 原始文件（相对 `TEXTBOOK/`） | 字节数 | 原始 SHA-256 | 已核实格式 | 转换状态 |
|---|---:|---|---|---|
| `第1章集合代数(新).doc` | 639556 | `9DD994A9CAC7873236CC5B4FBED8521F3AFE6FD3451240EAE2BFB27C1A62AAD5` | OLE/Word DOC | 未转换：本机无 renderer |
| `第2章两个数学基本原理（新）.doc` | 387649 | `09DB07A607CBD3864692630A6D2B03C77357B3B28D8B49C637B72270DD3AFA8A` | OLE/Word DOC | 未转换：本机无 renderer |
| `第3章 计数（新）.doc` | 1690574 | `4DEEA601332D9A336B2A04DF0652D205342DAB808C7A549D8C36B125D363F064` | OLE/Word DOC | 未转换：本机无 renderer |
| `第4章逻辑代数（新）.doc` | 293376 | `4F24543A5614804677FD4BF152D0BAD9B6FA0315D38ABCA945D0E629CF24153B` | OLE/Word DOC | 未转换：本机无 renderer |
| `第5章逻辑代数（下）（新）.doc` | 196096 | `CEAB38FA01C33A09FCE40228EC8491CCAD6E69C75BB66F9E65E673A81B47BAA7` | OLE/Word DOC | 未转换：本机无 renderer |
| `第6章形式系统（新）.doc` | 196608 | `12A2D776C519BC3F9E97168777DA5D491FC49F23D3119624C06AF5E8A75C12CD` | OLE/Word DOC | 未转换：本机无 renderer |
| `第7章图（新）.doc` | 825344 | `D742D4C98ABAE48B11229C87CB76378167E9C39B6BE187F79BD372CCE0B187A8` | OLE/Word DOC | 未转换：本机无 renderer |
| `第8章特殊图（新）.doc` | 371200 | `09748520200ADD0CB294F2453DFC3AC3F1BD07B81D371FAA3BDD5F99D41AD475` | OLE/Word DOC | 未转换：本机无 renderer |
| `第9章关系（新）.doc` | 517632 | `F620E92FEB4A3C98DA2088FE1BEA8DC9E42161289E762681728DD4A37FF7ABD9` | OLE/Word DOC | 未转换：本机无 renderer |
| `第10章函数（新）.doc` | 386560 | `013989C9A235CD21517700E99B2B23B9FCBD2A80FC2F496E93C78B44CF34A650` | OLE/Word DOC | 未转换：本机无 renderer |

转换来源链的后续记录字段：原始文件 hash → 转换工具/版本及配置 → DOCX 输出 hash → 固定 PDF hash → 页图/对象/索引资产 hash。现有可执行依赖检查未发现 LibreOffice/`soffice`、Microsoft Word、Pandoc、Antiword、Catdoc 或 `wvText`；常见 Office 安装目录不存在。实际转换须在 R2-A 使用受控本地 renderer 后补齐字体/替换记录、页数和定位金标。教材文件名显示主题为数学，可测工程解析/构建路径，不作为实验心理学课程事实或实验选题证据。

R2-A 已实现 DOCX XML 结构抽取、不可变构建 manifest、renderer 能力探测、按 renderer/config 隔离派生资产键，并以固定 PDF 实际抽取的唯一文本串和文本 span union 生成保守对象锚点；重复文本、图片对象、短文本和找不到的对象标记为 unsupported，不伪造页码/bbox。其文本定位调用仓库已有 `PyMuPDF` 依赖（当前环境 `1.28.2`），没有复制第三方源码；该包声明双许可为 AGPL-3.0 或 Artifex 商业许可，任何对外分发/服务化部署前须由项目维护者确认适用许可。DOC/DOCX 固定渲染仍因无本地 LibreOffice/Word renderer 阻塞，实际教材没有转换或上传。

### 2026-10-05 离散数学测试导入尝试

重新核验 `TEXTBOOK/` 的 10 个章节文件，SHA-256 与上表逐项一致；本地签名识别 10/10 为 `legacy_doc`。实际解析器调用 10/10 返回 `parser_unavailable`，没有提取教材正文。专用隔离环境的 51 项材料/解析/编译/检索回归通过，但使用的是测试 fixture，不能替代真实 `.doc` 解析。因为解析不可用，本轮没有创建教材 Material/Version、课程关联、知识对象/分块、索引 Job，也没有上传/发布原始文件。详细隔离资源、命令、结果和阻塞项见 [`离散数学本地测试教材导入核验`](discrete-math-local-import-2026-10-05.md)。
