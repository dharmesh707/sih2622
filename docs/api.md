# API

Core endpoints:

- `POST /api/v1/projects/{id}/schedule/import`
- `GET /api/v1/projects/{id}/activities`
- `GET /api/v1/activities/{id}`
- `POST /api/v1/reports`
- `GET /api/v1/events/{id}` and `/candidates`
- `GET /api/v1/review-queue`
- `POST /api/v1/events/{id}/confirm` and `/reject`
- `POST /api/v1/projects/{id}/recompute`
- `GET /api/v1/projects/{id}/critical-path`
- `GET /api/v1/analytics/discipline-productivity`
- `GET /api/v1/analytics/delay-causes`
- `GET /api/v1/analytics/variance`
- `GET /api/v1/memory/similar`
- `GET /api/v1/audit`
- `GET /api/v1/terminology-map`
- `POST /api/v1/agent/message`

Report responses include `event`, `match`, and measured `latency_ms`. Candidate responses include every persisted sub-score and evidence mapping.
