# SmartFlow AI Render production deployment

## Implemented topology

`render.yaml` defines four independently supervised services:

| Service | Responsibility | Scaling rule |
|---|---|---|
| `smartflow-api` | Gunicorn/Flask API and immutable React assets | Two or more instances |
| `smartflow-worker` | Market monitoring, confirmation transitions and notification outbox | One instance until jobs use distributed leases |
| `smartflow-telegram` | Dedicated supervised Telegram long polling | Exactly one instance per bot token |
| `smartflow-scheduler` | Singleton APScheduler for alert scans and model retraining | Exactly one instance |
| `smartflow-cache` | Rate limiting, cross-service heartbeats, transient coordination | Managed Key Value |

The API uses `/healthz` as a shallow liveness endpoint and `/readyz` for
database/Redis readiness. Render checks `/readyz`. API requests receive an
`X-Request-ID`; `CF-Ray` is retained in structured logs where available.
Workers publish expiring Redis heartbeats and exit when their critical runtime
cannot start, allowing Render to restart them.

## Render capabilities and limits

Render can continuously run paid web services and background workers, restart
failed processes, perform HTTP health checks for web services, and send
`SIGTERM` before shutdown. It cannot HTTP-health-check a background worker.
Worker health therefore requires Redis heartbeats plus an external alert on
staleness.

Render service filesystems are ephemeral by default. A persistent disk belongs
to only one service, prevents horizontal scaling, and cannot share files with
the API, worker, or scheduler. Do not use a Render disk as shared candle,
dataset, screenshot, backup, or model storage.

The repository currently uses local paths for some candles and ML artifacts.
That is acceptable only as a disposable cache. Before enabling automated
training/promotion across multiple instances, configure S3-compatible object
storage and store artifact metadata/checksums in the database. The active model
must be downloaded atomically by each API/worker process. Without this external
artifact layer, training can run, but a model written by the scheduler is not
guaranteed to become visible to API instances.

## Required environment configuration

Set every `sync: false` value in the Render dashboard. Never put secret values
in `render.yaml` or `.env.example`.

- All services: `DATABASE_URL`, `SECRET_KEY`, `SENTRY_DSN` (optional).
- API: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `CORS_ORIGINS`,
  `SYSTEM_RESTART_WEBHOOK` (optional).
- Worker: `TELEGRAM_BOT_TOKEN`, `OANDA_API_KEY`,
  `ALPHA_VANTAGE_API_KEY`.
- Scheduler: `OANDA_API_KEY`, `ALPHA_VANTAGE_API_KEY`.

Use a managed production database with TLS, automated backups, point-in-time
recovery, connection metrics, and enough connections for:

`instances × Gunicorn workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW)`

Set `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` from that budget. Do not deploy
production with SQLite.

## Logging and monitoring

All Render services emit JSON to stdout. Configure a Render log stream to a
central log platform; local files are deliberately disabled because they are
ephemeral and instance-local. Configure Sentry with `SENTRY_DSN` for uncaught
API and SQLAlchemy errors.

Alert on:

- `/healthz` unavailable from an external region;
- `/readyz` returning non-200;
- `ai-worker` or `scheduler` heartbeat older than 120 seconds;
- notification queue depth/oldest age increasing;
- Redis or database latency/error rate;
- provider failure/fallback rate;
- repeated service restarts;
- market-analysis lag by pair/timeframe.

The admin dashboard is useful for operational diagnosis, but Render logs and
the external error tracker remain the authoritative cross-instance record.

## Graceful deployment and recovery

The API receives up to 60 seconds and workers up to 120 seconds after
`SIGTERM`. Worker loops stop accepting cycles, stop monitors, wait for the
scheduler where appropriate, and dispose database pools.

Use these rollout steps:

1. Apply database migrations with `python run.py migrate` before application traffic moves.
2. Deploy the scheduler and worker with backward-compatible schema changes.
3. Deploy the API and verify `/healthz` and `/readyz`.
4. Verify Redis heartbeats for all three runtime roles.
5. Confirm Telegram polling and enqueue a synthetic notification.
6. Verify one worker drains it exactly once.
7. Confirm external logs, Sentry, and uptime alerts receive test events.

Roll back application images only while the schema remains backward
compatible. Use expand/migrate/contract migrations for destructive changes.

## Capacity path

For thousands of users, keep API instances stateless and scale them
horizontally. Move long-running predictions to a durable broker-backed job
queue, partition analysis by pair/timeframe, apply idempotency keys to every
signal and notification, and use distributed leases before adding worker
replicas. Add object storage/CDN for artifacts and static frontend assets.

The current separated topology prevents web requests, Telegram polling,
schedules, and market analysis from blocking each other. It does not make
in-process APScheduler or local artifact files horizontally scalable; those
constraints must remain explicit during capacity expansion.
