# SmartFlow AI architecture

## System boundaries

SmartFlow AI is a Flask API with two React single-page applications, a
rule-first SMC/ICT trading engine, an ML quality-adjustment layer, SQLAlchemy
persistence, Redis coordination, Telegram integration, and separate continuous
worker and scheduler processes.

Production roles:

- **API:** Gunicorn serves Flask, `/app`, `/admin`, REST endpoints, WebSockets,
  and immutable frontend assets.
- **AI worker:** scans confirmations/outcomes, processes the notification
  outbox, supervises Telegram polling, and publishes Redis heartbeats.
- **Scheduler:** singleton APScheduler process for alert scans and governed
  retraining.
- **Database:** authoritative users, predictions, feedback, model metadata,
  notifications, audit, and operational state.
- **Redis:** rate limiting, heartbeats, health and transient coordination.

## Main data flows

### Signal generation

1. A website, Telegram, alert, or admin request selects pair, timeframe,
   strategy and account.
2. `engine.data` requests validated candles from configured providers, retries,
   falls back, records provider health, and can use cached history.
3. `engine.topdown` synchronizes higher and execution timeframes.
4. `engine.smc`, `engine.ict`, and `engine.institutional` detect structure,
   liquidity, order-flow and session evidence.
5. `engine.patterns` adds low-weight supporting candlestick/chart evidence.
6. `engine.confluence` and `engine.scoring` resolve contradictions and produce
   `BUY_BIAS`, `SELL_BIAS`, `WAIT_FOR_CONFIRMATION`, or `NO_TRADE`.
7. `engine.risk_calc` validates entry, stop, target, RR, lot and position size.
8. `engine.ml_gate` may reduce/adjust confidence but cannot reverse the rule
   engine decision.
9. The response and review evidence are persisted and returned.

### Confirmation and notification

`WAIT_FOR_CONFIRMATION` creates a `ConfirmationWatch`. The AI worker replays
the rule pipeline. A valid confirmation atomically updates the watch, creates
the confirmed review, and inserts one `NotificationDelivery` per channel.
The outbox delivers website, Telegram and push payloads with retries,
attempt counts, next-attempt timestamps and final status.

### Feedback and learning

User trade-entry/outcome feedback is stored separately from market truth.
Historical candles, duration, SL/TP traversal, duplicate hashes and consistency
checks create `MarketVerification` and governed `TrainingRecord` rows.
Administrators approve, reject, edit, flag or mark institutional examples.
Immutable dataset manifests produce pending, approved, rejected and gold
versions. Retraining requires quality, sample, market and strategy diversity.
Candidate models run shadow/backtest evaluation and promotion gates. Active
model metadata supports rollback to a prior version.

## Reliability model

Database transactions own durable state; Redis is not authoritative. All
external delivery is retried through the outbox. API readiness requires
database and configured Redis connectivity. Workers publish expiring
heartbeats, respond to `SIGTERM`, close monitors and dispose database pools.

## Known scaling boundary

Local candle/model files are disposable and not shareable across Render
instances. Horizontal worker scaling requires distributed leases and a durable
broker. Model, dataset, screenshot and export artifacts require S3-compatible
object storage with checksums and atomic download/promotion.
