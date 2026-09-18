# 内部事件契约

首期采用PostgreSQL Outbox，不引入Kafka。事件统一包含：

- `event_id`
- `event_type`
- `event_version`
- `occurred_at`
- `producer`
- `trace_id`
- `payload`

消费者必须按`event_id`幂等处理。

