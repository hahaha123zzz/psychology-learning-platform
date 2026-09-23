# V3 最小 Evidence Closure 实施记录

## 目标

在不改变现有检索排序、不伪造对象关系和不引入外部模型调用的前提下，为命中的文本对象补齐最少的相邻教材证据。该能力用于后续 `GenerationUnit` 组装，当前只扩展检索响应，不直接生成回答。

## 设计边界

1. 解析持久化后，按同章节的确定阅读顺序生成双向 `previous` / `next` 关系；章节对象不参与相邻关系。
2. 仅 `review_status=approved` 的关系可以参与闭包。被拒绝、未确认或跨版本关系一律忽略。
3. 一个检索命中最多附带 4 个闭包对象；闭包对象带 `object_id`、页码、锚点、类型、bbox 与原始文本，但不作为新的排序候选或 Evidence Ticket。
4. `POST /api/v1/knowledge/search` 的 `include_neighbors` 已接入服务层；设为 `false` 时返回空 `closure`，不会读取关系。
5. 当前 `StubPdfParser` 无图、表、公式与 Caption 关系，故图题不会因本改造被错误标记为图片命中；这些关系留待可验证版面解析器产生。

## 验收

- 成功路径：命中首段时返回其已确认的 `next` 段落。
- 开关路径：`include_neighbors=false` 时不返回闭包。
- 安全路径：将关系标为 `rejected` 后不返回闭包。
- 版本路径：查询限定 `MaterialVersion`，目标对象必须属于允许版本。

## 当前状态

代码和单项 API 测试已通过。完整数据库回归待 Docker Desktop 的 Linux Engine 恢复后执行；在该验证完成前，本记录不表示 V3 证据闭包已完成真实教材验收。
