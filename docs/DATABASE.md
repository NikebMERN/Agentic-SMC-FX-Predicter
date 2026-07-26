# Database documentation

## Domains

- **Identity/access:** `User`, `RefreshToken`, `PasswordReset`,
  `TelegramLink`, `TelegramLinkCode`.
- **Trading:** `Account`, `Signal`, `Trade`, `PredictionReview`,
  `DetectedSignal`, `SignalOutcome`, `ConfirmationWatch`.
- **Feedback/ML governance:** `UserFeedback`, `MarketVerification`,
  `TrainingRecord`, `DatasetVersion`, `DatasetVersionRecord`, `ModelVersion`,
  `TrainingRun`, `BacktestRun`, `ShadowEvaluation`, `FeedbackSample`.
- **Operations:** `Notification`, `NotificationDelivery`, `AlertRule`,
  `AlertEvent`, `ExportJob`, `PairPerformance`, `EquitySnapshot`, `AdminLog`.
- **Configuration:** `Setting`, `PairThreshold`, `ThresholdVersion`,
  `ThresholdOverride`.

## Transaction boundaries

Confirmation status and outbox creation must commit atomically. Dataset
versions are append-only manifests; promotion changes active metadata without
overwriting history. Model rollback activates an existing prior version.
Notification delivery uses unique event/channel keys and retry state.

## Production operation

Use managed MySQL with TLS, automated backups and point-in-time recovery.
`db/session.py` enables pre-ping, recycle, bounded pools and explicit session
closing. Budget connections across all Gunicorn processes and instances.
Apply migrations before application rollout using expand/migrate/contract
changes. SQLite is test/development only.

## Current risks

Many models still use naive `datetime.utcnow()`; migrate to timezone-aware UTC
without mixing aware/naive columns. Queue claiming is safe only with one
consumer; multiple workers require `SELECT ... FOR UPDATE SKIP LOCKED` or a
durable broker lease. Artifact paths are not durable database content.
