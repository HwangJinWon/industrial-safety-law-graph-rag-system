# Watch and Dashboard API

The same FastAPI server hosts Graph-RAG and operations APIs, but watch data is stored only in `data/watch_data.db`.

## Base URL

- Emulator on the same PC: `http://10.0.2.2:8000`
- Physical watch on the same Wi-Fi: `http://<SERVER_PC_IP>:8000`
- Never use `127.0.0.1` on the watch; that address means the watch itself.

For the shared staging server, send the key provided by the backend owner with every functional API request:

```http
X-API-Key: <staging key>
```

## Data sent to the server

### Equipment status

`POST /api/equipment/status`

```json
{"equipment_id":"press-01","status":"RUNNING","production_count":750,"defect_rate":5.2,"measured_at":"2026-07-01T14:30:00Z"}
```

Allowed status values: `RUNNING`, `IDLE`, `WARNING`, `STOPPED`.

### Heart rate

`POST /api/watch/heart-rate`

```json
{"worker_id":"worker-001","heart_rate":92,"measured_at":"2026-07-01T14:30:00Z"}
```

### Attendance and break actions

`POST /api/watch/attendance`

```json
{"worker_id":"worker-001","action":"CLOCK_IN","occurred_at":"2026-07-01T13:00:00Z"}
```

Actions must occur in this order: `CLOCK_IN` -> optional `BREAK_START` -> `BREAK_END` -> `CLOCK_OUT`.
The server calculates working time after subtracting breaks.

### Broadcast emergency

`POST /api/watch/emergency`

```json
{"worker_id":"worker-001","type":"HUMAN_ACCIDENT","message":"Operator needs help","occurred_at":"2026-07-01T14:31:00Z"}
```

Suggested types: `HUMAN_ACCIDENT`, `EQUIPMENT_FAILURE`, `OTHER`, `SOS`.

## Data read by a watch

- `GET /api/watch/work-status/worker-001`
- `GET /api/watch/notifications?worker_id=worker-002&after_id=0`
- `POST /api/watch/notifications/1/ack` with `{"worker_id":"worker-002"}`

For the prototype, each watch should call the notifications endpoint every 2-5 seconds. Save the largest received `alert_id` and send it as the next `after_id`. An emergency is returned to every worker except the sender.

## Data read by the dashboard

- `GET /api/dashboard/equipment`
- `GET /api/dashboard/workers`
- `GET /api/dashboard/attendance`
- `GET /api/dashboard/alerts`
- `GET /api/dashboard/overview` (all sections at once)

## Kotlin request rule

Send JSON with `Content-Type: application/json`. Use ISO-8601 UTC time such as `2026-07-01T14:30:00Z`. Retrofit can use the paths and JSON bodies above directly.
