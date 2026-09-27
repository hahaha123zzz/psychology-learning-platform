# OpenStax《Psychology 2e》本地原生版面对象 V3.3 评测

## 范围

本次仅在本机对 `data/oer-textbooks/openstax-psychology-2e.pdf` 运行 PyMuPDF 原生 PDF 解析；没有上传、发送或调用任何外部生成、嵌入或视觉模型服务。

输入 SHA-256：`2f08113c78127bc684922ad6a819db22bd4705ce9fcf28a07f36a2041b1474e2`。

可复现命令：

```powershell
Set-Location server
.venv\Scripts\python.exe ..\scripts\evaluate_native_pdf_layout.py `
  --pdf ..\data\oer-textbooks\openstax-psychology-2e.pdf `
  --output ..\contracts\rag-eval\openstax-psychology-2e-native-layout-v33-report.json
```

## 结果

| 项目 | 数量 | 带 bbox |
| --- | ---: | ---: |
| 页 | 755 | — |
| chapter | 16 | 0 |
| paragraph | 11,293 | 11,293 |
| figure | 361 | 361 |
| table | 12 | 12 |
| formula | 0 | 0 |
| 图片资产 | 361 | — |

解析器版本：`stub-pdf / native-layout-v3.3`。本轮没有解析告警。

## 结论与边界

1. 段落、真实嵌入图片和原生规则网格表格现在拥有同一 PDF 用户空间坐标合同，可作为后续“点击引用→页码→bbox 高亮”的数据基础。
2. `formula=0` 表示这个保守规则没有在该教材中形成可验证的独立公式对象；它不代表教材不存在公式，也不能表述为公式解析完成。
3. `figure`、`table` 和 `formula` 仍未构建 RetrievalUnit、Embedding 或视觉索引。该报告证明对象与定位资产存在，**不证明视觉检索效果**。
4. 下一步应对图/表对象做人工抽样核验（对象类型、页码、bbox 与裁剪资产），再决定是否在许可允许的测试语料上建立表示或检索实验。
