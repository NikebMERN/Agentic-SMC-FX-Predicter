# Production limitation remediation

## Implemented

- Confirmation transitions commit before emitting a durable event.
- A database-backed notification outbox tracks website, Telegram, and optional
  push delivery independently, with retries and idempotent event keys.
- Telegram `/lot SYMBOL BALANCE RISK_PERCENT` uses current candles, a 1.5 ATR
  stop, instrument contract sizes, and risk-capped lot sizing.
- Data providers retry with backoff, expose provider health and diagnostics,
  validate candles, detect gaps, use exact-timeframe caches, and report every
  failed provider attempt.
- Candlestick and chart structures add bounded supporting evidence only when
  SMC/ICT already supplies a directional signal.
- Admin logs support server-side severity, system, text, and date filtering.
- Render runs API, AI worker, and scheduler as independent services.

## Rollout

1. Apply Alembic migration `005_notification_outbox`.
2. Deploy all services from `render.yaml` with shared MySQL and Redis settings.
3. Configure `PUSH_NOTIFICATION_WEBHOOK` only when a push gateway is available.
4. Configure external monitoring for `/healthz`.
5. Alert when `notification_queue_pending` grows continuously.

## Follow-up phases

- Move candle/model artifacts from ephemeral disks to object storage.
- Replace in-process provider health state with Redis-backed metrics.
- Add distributed job leases before horizontally scaling workers.
- Calibrate pattern weights through walk-forward validation; do not promote
  heuristic patterns to standalone entry signals.
- Add a dedicated Web Push subscription store and VAPID delivery provider.
