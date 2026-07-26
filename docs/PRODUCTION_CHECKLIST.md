# Production readiness checklist

## Application

- [x] Trading, confirmation, feedback, Telegram, admin and deployment critical tests pass.
- [x] API liveness/readiness endpoints exist.
- [x] Both frontends build; user frontend lint passes.
- [x] Route-level lazy loading and loading fallbacks are enabled.
- [ ] Complete post-upgrade 210-test CI run finishes without timeout.
- [ ] React Router high-severity audit findings are resolved.

## Render and operations

- [x] API, AI worker, singleton scheduler and Redis are separate services.
- [x] API has multiple instances, Gunicorn and readiness checks.
- [x] Workers support SIGTERM, heartbeats and database-pool disposal.
- [x] Secrets use `sync: false`; safe examples contain placeholders only.
- [ ] Confirm every real Render secret/variable against `.env.example`.
- [ ] Configure and test log drain, Sentry, uptime and stale-heartbeat alerts.
- [ ] Complete 72-hour soak, restart and provider-failure exercises.

## Data and scale

- [x] Database pooling, pre-ping, recycle and migrations are configured.
- [x] Notification deliveries are durable, idempotent and retryable.
- [ ] Add object storage for models, datasets, screenshots and exports.
- [ ] Add distributed queue leases before running multiple AI workers.
- [ ] Validate MySQL migration/restore against a production-like clone.
- [ ] Prove capacity with load tests and provider quota simulations.

## Security

- [x] Python packages with known audit fixes were upgraded.
- [x] Production startup rejects unsafe database, CORS, secret and rate-limit configuration.
- [x] JWT authorization, admin authorization, request IDs and generic 500 responses exist.
- [ ] Resolve all high/critical npm findings.
- [ ] Run CI secret scanning, SAST and container image scanning.
- [ ] Verify payment and external integration credentials only in Render.
