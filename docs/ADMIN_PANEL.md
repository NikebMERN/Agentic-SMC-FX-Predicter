# Admin panel explanation

The React admin SPA uses protected `/admin/api/*` endpoints. It provides user
approval/ban/quota controls, signals/trades, thresholds, prediction reviews,
feedback governance, datasets, models, backtests, performance analytics,
notifications, logs and system operations.

Monitoring pages expose application/API/trading/Telegram/worker/scheduler/ML
log categories, severity/search/date filters, database/Redis health, CPU/RAM,
queue depth, service heartbeats, training history, model versions, promotion
history, feature importance, confusion metrics and market/pair/timeframe
performance.

Restart control invokes a configured deployment webhook; it is not direct
process control. Render/external log aggregation remains authoritative because
local files are instance-local and ephemeral. Every privileged mutation must
write an `AdminLog`.
