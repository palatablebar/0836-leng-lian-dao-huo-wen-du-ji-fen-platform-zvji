# 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| `batch_id` | text | 业务字段 |
| `sensor_id` | text | 业务字段 |
| `segment_start` | datetime | 主键 |
| `segment_end` | datetime | 业务字段 |
| `temp_c` | decimal | 业务字段 |
| `unit` | text | 业务字段 |
| `probe_offset` | decimal_optional | 业务字段 |

空字符串、`-`、`NA`、`null` 和 `未提供` 按空值处理。金额字段在整理层转为整数分或整数最小单位；日期按 ISO 日期解析；带时间的字段按本地时间解析。标识字段保持为文本，前导零不会被去除。
