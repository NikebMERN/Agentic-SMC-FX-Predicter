# Deploying SmartFlow AI from Cursor

Cursor is the development environment, not the hosting runtime. SmartFlow AI is deployed from the repository to Render using the Blueprint in `render.yaml`.

## One-time setup

1. Open the repository root in Cursor.
2. Install Python 3.12, Node.js 22, Git, and Docker.
3. Create a local virtual environment and install `requirements-dev.txt`.
4. Copy `.env.example` to `.env` only for local development. Never place Render production secrets in that file.
5. Connect the repository to GitHub.
6. In Render, create a Blueprint from the repository and review the services before applying it.

The Blueprint creates:

- `smartflow-api`: Flask/Gunicorn web API and both React applications.
- `smartflow-worker`: continuous trading and AI work.
- `smartflow-scheduler`: scheduled market analysis.
- `smartflow-telegram`: dedicated Telegram polling process.
- `smartflow-cache`: Redis-compatible queue, rate-limit, and runtime state storage.

## Required Render values

Enter every `sync: false` value in the Render dashboard. Use the same `DATABASE_URL` and `SECRET_KEY` for all application services. Set the production Telegram token only on services that require it. Configure:

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `CORS_ORIGINS`
- `TELEGRAM_BOT_TOKEN`
- `OANDA_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `SENTRY_DSN`
- `SYSTEM_RESTART_WEBHOOK` when remote restart control is enabled

Do not add `VITE_*` secrets. Any frontend variable is public after compilation.

## Release workflow

1. Run `python run.py migrate` against a disposable local database.
2. Run `pytest tests/ -v`.
3. Run `npm ci && npm run build` in `smc-frontend`.
4. Run `npm ci && npm run build` in `admin-frontend`.
5. Build the production container with `docker build -t smartflow-ai:release .`.
6. Commit and push to the protected `main` branch.
7. Wait for all GitHub checks to pass. Render uses `autoDeployTrigger: checksPass`.
8. Confirm the Render pre-deploy migration succeeds before the new API instances start.

## Post-deployment checks

- `GET /healthz` returns a live response.
- `GET /readyz` reports the database and required dependencies ready.
- The API, AI worker, scheduler, and Telegram worker show fresh heartbeats in Admin monitoring.
- A test `WAIT_CONFIRMATION` prediction can become `CONFIRMED`, and website and Telegram delivery records complete.
- User History and My Feedback load without server errors.
- Admin Models & Data, ML Operations, and Training Records load.
- A Telegram `/lot EURUSD 1000 1%` request returns a validated calculation.

## Rollback

Use Render's rollback for the affected service. If the release includes a database migration, verify that the previous application remains compatible with the new schema before rolling back. Dataset and model versions are immutable; use the admin promotion/rollback controls rather than replacing artifacts in place.
