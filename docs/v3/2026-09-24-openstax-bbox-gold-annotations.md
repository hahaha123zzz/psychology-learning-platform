# OpenStax 段落 bbox 最小人工金标

此文件记录 `openstax-psychology-2e-local-v2.json` 中两条 bbox 的独立标注来源，供 V3 的 bbox IoU 指标使用。

## 标注方法

1. 从 Git 忽略的本地 `Psychology2e_WEB.pdf` 以 144 DPI 渲染物理页。
2. 仅根据页面可见文本的外接范围标注，不读取解析器、数据库或运行结果中的 bbox。
3. 使用 PDF 用户空间坐标 `[left, bottom, right, top]`；144 DPI 渲染图坐标按 2:1 转换，并以约 1 PDF point 的视觉边界余量记录。

## 金标对象

| 对象 | 物理页 | 可见文本 | bbox |
| --- | ---: | --- | --- |
| `openstax-p066-variables` | 66 | “An independent variable is manipulated or controlled …” | `[71, 639, 540, 735]` |
| `openstax-p262-memory-model` | 262 | “Sensory Memory, Short-Term Memory, and finally Long-Term Memory …” | `[71, 580, 534, 648]` |

## 边界

这不是图片、表格或公式的金标。古典条件反射案例的目标是图片对象，而当前 parser/index 尚未产生图片对象，不能用图注段落坐标替代。后续扩展金标必须保持同样的独立渲染审查流程，并记录标注者和版本。
