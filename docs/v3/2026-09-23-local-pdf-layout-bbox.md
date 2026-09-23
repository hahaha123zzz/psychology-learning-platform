# 本地 PDF 段落 bbox 验证

`StubPdfParser` 现使用本地 PyMuPDF 读取原生文本 PDF 的文本块坐标，并转换为项目既有的 PDF 用户空间格式 `[left, bottom, right, top]`。该过程不调用外部 API，也不上传教材。

## OpenStax 抽样结果

- 输入：本地 `data/oer-textbooks/openstax-psychology-2e.pdf`
- 页数：755
- 章节数：16（与既有章节边界一致）
- 段落对象：11,293
- 带 bbox 的段落：11,293
- 解析告警：无

该坐标来自 PDF 的原生文本布局，可用于段落级跳转与高亮。当前仍没有可靠的 `figure`、`table` 或 `formula` 对象、其 bbox、图片裁剪或视觉索引；它们继续保持不可评测状态，不能由段落 bbox 替代。

## 运行边界

后续重新解析同一教材版本会改变段落对象边界和索引规模，必须随后重建索引并重新生成对象级评测运行记录。已发布版本不可原地重解析。
