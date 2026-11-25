# 接口

- `GET /`：工作台。
- `GET /api/catalog`：阶段、字段和样例。
- `POST /api/stages/{stage}`：按阶段返回处理结果。可选 `run_id`，带上后按该批次的补正重算。
- `POST /api/runs`：执行完整批次并保存草稿。
- `GET /api/runs/{id}`：读取批次。
- `POST /api/runs/{id}/corrections`：提交坏行补正，提交 `fixes`（`[{"line": 行号, "values": {字段: 值}}]`）与 `comment`。返回 `run`、`correction`、`created`。
- `GET /api/runs/{id}/corrections`：读取补正记录及每行的生效状态。
- `POST /api/runs/{id}/review`：签发或暂缓，提交 `decision`、`comment`、`expected_revision`。
- `GET /api/runs/{id}/evidence`：下载已签发证据。
- `GET /api/examples/{profile}`：下载样例。
- `GET /healthz`：健康检查。
