# Developer onboarding

## Setup

1. Install Python 3.12, Node 22, MySQL and Redis.
2. Copy `.env.example` to `.env`; use development-only credentials.
3. Run `python -m pip install -r requirements-dev.txt`.
4. Run `npm ci` in `smc-frontend` and `admin-frontend`.
5. Run migrations with `python run.py migrate`.
6. Run tests with `python -m pytest -q`.
7. Run user lint/build with `npm run lint` and `npm run build`.
8. Run admin build with `npm run build`.

## Repository map

- `app.py`: public/user API and runtime health.
- `admin_panel.py`: protected administrative API.
- `engine/`: market data, SMC/ICT rules, patterns, scoring and risk.
- `ml/`: feature schema, training, calibration, backtests and promotion.
- `services/`: workflows spanning engine, database and integrations.
- `db/`: SQLAlchemy models/session.
- `alembic/versions/`: ordered schema migrations.
- `bot.py`: Telegram commands and polling application.
- `run.py`: local commands, workers and scheduler.
- `render.yaml`, `Dockerfile`, `deploy/`: production processes.
- `tests/`: unit, scenario, API and deployment regression tests.

## Engineering rules

- Rule-based SMC/ICT logic is the source of truth; ML never creates or reverses
  a trade.
- Preserve idempotency for predictions, confirmations and notifications.
- Never make external calls inside an uncommitted database transaction.
- Add Alembic migrations for schema changes; never edit production tables
  manually.
- Use timezone-aware UTC for new persistence code.
- Add historical scenario tests for trading changes and API authorization tests
  for new routes.
- Treat local files as caches, not production persistence.

## Pull-request gate

Require 210+ Python tests passing, both frontend builds, user lint, dependency
audits, migration review, secret scanning, and a rollback note.
