# 接口契约

`openapi.json`由FastAPI应用生成，是前端请求类型的唯一来源，禁止手工修改。

导出命令：

```powershell
python scripts/export_openapi.py
```

跨模块事件契约将在`events/`下按版本维护。破坏性字段变更必须升级事件版本。

