# API documentation

## Authentication

Bearer JWT access tokens protect user routes; refresh tokens are persisted and
revocable. Administrative routes require an admin token and audit privileged
actions. Production requires restricted CORS, Redis-backed rate limits, strong
secrets and HTTPS.

## Public and identity

- `POST /register`, `/login`, `/refresh`, `/logout`
- `POST /forgot-password`, `/reset-password`, `/change-password`
- `GET /healthz` for liveness; `GET /readyz` for database/Redis readiness
- `GET /pairs`

## Trading and account

- Account CRUD under `/accounts/*`
- `POST /analyze` and `POST /predict/<account_id>`
- `POST /calculator`
- `GET /data`, `/signals`, `/trades`
- `POST /close-trade/<trade_id>`
- Live quote/stream under `/api/market/live/*` and `/api/market/stream/*`

## Reviews, confirmations and notifications

- `GET /my/reviews`, `/my/history`
- `POST /my/reviews/<id>/feedback`
- `GET/POST /my/confirmations/<id>/*`
- `GET/PATCH/POST /notifications/*`
- `POST /telegram/link-code`

## Administration

`/admin/api/*` covers users, trades, signals, thresholds, datasets, feedback
governance, model versions, retraining, backtests, performance, logs, health,
jobs, restart requests and audit records. See route definitions in
`admin_panel.py`; the Postman collection provides example legacy requests.

## Error contract

Unexpected failures return a generic error and `request_id`; responses include
`X-Request-ID`. Validation and authorization failures use 4xx codes. Clients
must not retry unsafe POST operations unless they carry an application
idempotency key.
