# SmartFlow AI — Agentic SMC/ICT Forex Predictor

A Python platform that predicts forex market direction by aggregating
**only valid** Smart Money Concepts (SMC) and Inner Circle Trader (ICT)
signals, blended with a machine-learning model that is **retrained on the
pair's freshest data at every prediction request**.

## One command to run everything

```bash
pip install -r requirements.txt
copy .env.example .env        # then fill in your keys (strong SECRET_KEY required)
```

**Windows:** double-click `start.bat` or run:

```bash
python run.py
# same as:  python run.py start
```

**Linux/macOS:** `./start.sh` or `python run.py start`

**Development** (React admin with hot reload on port 5174):

```bash
python run.py dev
# Admin UI → http://127.0.0.1:5174/admin/
# User app → http://127.0.0.1:5173/
# API      → http://127.0.0.1:5000
```

With `APP_ENV=development` in `.env`, `python run.py` also starts **both** Vite dev
servers (user :5173 + admin :5174) and rebuilds frontends on each launch.

**Production** (`APP_ENV=production`): serves built SPAs from Flask only — no Vite
subprocesses. User app at `/app/`, admin at `/admin/`.

`python run.py` / `python run.py start` builds the React admin panel and user app, then starts in one process:

1. Creates the MySQL tables (non-fatal if the DB is down — prediction still works),
2. Serves the REST API with waitress (production WSGI) on `API_HOST:API_PORT`,
3. Serves the **React admin UI** at `/admin` and **user app** at `/app` (production builds),
4. Runs the user Vite dev server on `:5173` when using `python run.py dev`,
5. Runs outcome + health monitors and the Telegram bot in background threads (if configured).

Other entry points:

```bash
python run.py build-admin            # build React admin only
python run.py predict EURUSD           # one-off prediction in the terminal
python run.py predict EURUSD --no-fetch
python run.py api                      # API only
python run.py bot                      # Telegram bot only
python run.py refresh                  # refresh CSVs + models for all pairs
python run.py backup                   # database backup to backups/
python run.py backtest EURUSD          # walk-forward backtest (or 'all')
```

## What happens on a prediction request

Whether it comes from the API (`POST /predict/<account_id>` or `POST /analyze`),
the Telegram bot, or the CLI, every request runs the same pipeline
([engine/pipeline.py](engine/pipeline.py)):

1. **Pull the latest CSV** for that pair — **OANDA v20** first (real
   broker mid-price candles, up to 2000 per request, free practice-account
   token; UTC timestamps normalised to New York time so kill zones stay
   correct), falling back to Alpha Vantage (`FX_INTRADAY`, then
   `TIME_SERIES_INTRADAY`), falling back to the cached CSV when no
   provider is reachable. Configure with `OANDA_API_KEY` /
   `ALPHA_VANTAGE_API_KEY` / `DATA_PROVIDER` in `.env`.
2. **Detect valid signals only** on that data:
   - **SMC** ([engine/smc.py](engine/smc.py)): close-confirmed BOS/CHoCH
     (body close beyond the swing, wick pokes don't count), order blocks
     that actually caused a structure break (life-cycle tracked:
     fresh → mitigated → invalidated; invalidated blocks are never entry
     zones), displacement-created fair value gaps with the correct
     3-candle definition (fully filled gaps discarded), and equal-high /
     equal-low liquidity pools with swept-state tracking.
   - **ICT** ([engine/ict.py](engine/ict.py)): kill-zone session timing,
     liquidity sweeps (wick through a pool with a close back inside —
     accepted breakouts are never counted as sweeps), displacement,
     premium/discount of the current dealing range (longs only valid in
     discount, shorts only in premium), OTE (61.8–79% retracement) and
     breaker blocks (failed OBs that flipped after a sweep).
3. **Train the pair's model on that same data**
   ([engine/model_trainer.py](engine/model_trainer.py)): every candle is
   a sample (SMC/ICT state features → forward-move label), validated on
   a time-ordered holdout, refit on the full history, saved to
   `model/{SYMBOL}_{interval}.joblib`.
4. **Aggregate both strategies** ([engine/confluence.py](engine/confluence.py)):
   each valid signal votes bullish/bearish with a weight, hard vetoes
   enforce validity at the trade level (minimum 2 confluences, no longs
   in extreme premium / shorts in extreme discount, minimum score gap,
   ML contradiction check), and the result is **BUY / SELL / NO_TRADE**
   with confidence, structure-based Stop Loss (beyond the protective
   OB/swept level/swing), Take Profit at the nearest opposing liquidity
   (minimum RR 1.5) and a full human-readable reasoning trail.

## Admin panel (React)

The admin UI lives in [`admin-frontend/`](admin-frontend/) (Vite + React + Tailwind).
It is built to `static/admin/` and served by Flask at **`http://localhost:5000/admin`**.

Requires **Node.js/npm** for the first build (`python run.py` runs `npm ci && npm run build` automatically).

Set `ADMIN_EMAIL` + `ADMIN_PASSWORD` in `.env` — the admin account is created on startup.
Everything is controlled from the panel:

- **Dashboard** — user/signal/trade totals, system health (DB, data API
  key, bot), per-pair CSV freshness.
- **Users** — search, promote/demote admins, ban/unban (bans block
  login immediately), delete.
- **Signals** — full list plus manual signal creation (override the AI).
- **Trades** — all trades, force-close any open one.
- **Models & Data** — per-pair model metrics (samples, validation
  accuracy, trained-at), fetch + retrain any pair, refresh all pairs in
  the background, delete models.
- **Predict** — run the full pipeline for any pair from the browser and
  read the decision with its complete reasoning trail.
- **Settings** — supported pairs and the confidence floor, stored in
  the DB and applied immediately to the bot, CLI, API and engine.
- **Logs** — live tail of the application log.
- **Audit** — admin action history.

**Sign-in security:** password fields have show/hide toggles, and
"Forgot password?" runs a full reset flow — a hashed, single-use 6-digit
code (15-minute expiry, 5 attempts) is emailed via SMTP (`SMTP_*` in
`.env`; Gmail needs an App Password). Without SMTP the code is written
to `logs/smartflow.log` so the server operator can still recover access.
Logged-in admins can also change their password from the Settings tab.

## Tests, Docker, CI

```bash
pip install -r requirements-dev.txt
pytest tests/            # unit + API tests

docker compose up -d     # MySQL + Redis + API + worker + Caddy (HTTPS when DOMAIN set) + daily DB backups
```

CI runs the suite on every push (`.github/workflows/ci.yml`).

### Production checklist

Before going live, set in `.env`:

| Variable | Production value |
| --- | --- |
| `APP_ENV` | `production` |
| `SECRET_KEY` | long random hex string |
| `CORS_ORIGINS` | your HTTPS origin(s), not `*` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | strong bootstrap credentials |
| `DATABASE_URL` or `MYSQL_*` | MySQL (not SQLite) |
| `SMTP_*` | working mail server for password reset |
| `DOMAIN` | public hostname for Docker/Caddy automatic HTTPS |
| `OANDA_API_KEY` or `ALPHA_VANTAGE_API_KEY` | at least one data provider |
| `RATELIMIT_STORAGE_URI` | Redis, not `memory://` |

On startup in production, `run.py` now refuses to boot if required production settings are unsafe (CORS `*`, missing SMTP, SQLite DB, weak admin password, memory-only rate limits, or no live data provider key unless `ALLOW_CACHE_ONLY_PRODUCTION=true` is explicitly set).

### HTTPS (Docker)

With `DOMAIN=your-domain.com` in `.env`, Caddy terminates TLS and proxies to the app container. Without `DOMAIN`, Caddy serves HTTP on port 80 for LAN testing. The app container is not published directly — only Caddy exposes 80/443.

The Docker stack runs the HTTP API and background jobs separately: `app` serves Flask only, while `worker` runs monitors, scheduled retraining, alert scans, and the Telegram supervisor.

### Database backup & restore

**Manual backup:**

```bash
python run.py backup          # writes backups/smartflow_YYYYMMDD_HHMMSS.sql or .db
```

**Docker:** the `db-backup` service runs `mysqldump` daily at 03:00 into `./backups/` (7-day rotation).

**Restore (MySQL):**

```bash
mysql -h HOST -u USER -p DATABASE < backups/smartflow_YYYYMMDD_HHMMSS.sql
```

**Restore (SQLite):** stop the app, replace the database file with the backup copy.

### User web app

| Mode | URL |
| --- | --- |
| Development | `http://127.0.0.1:5173/` (Vite, proxied to API) |
| Production | `http://host:5000/app/` (built SPA served by Flask) |

## API highlights

| Endpoint | Description |
| --- | --- |
| `GET /pairs` | Supported pairs + interval |
| `POST /analyze` | `{ "symbol": "EURUSD" }` → full prediction JSON (no trade opened) |
| `POST /predict/<account_id>` | SSE stream: fetch → retrain → decision → signal + risk-sized trade |
| `POST /register`, `POST /login` | JWT auth |
| `/accounts/*`, `/trades`, `/signals` | Account, trade and signal management |

All protected routes take `Authorization: Bearer <token>`.

## Project layout

```
engine/            AI engine (data, smc, ict, confluence, features, model_trainer, pipeline, backtest)
admin-frontend/    React admin UI (Vite) → built to static/admin/
smc-frontend/      React user app (Vite) → built to static/app/
static/admin/      Production admin SPA (Flask /admin)
static/app/        Production user SPA (Flask /app)
app.py             Flask REST API
admin_panel.py     Admin API + SPA routes
user_panel.py      User SPA routes (/app)
bot.py             Telegram bot
run.py             single entry point for everything
main.py            interactive terminal client
batch_fetch.py     refresh all pairs' CSVs + models
deploy/            Caddy reverse proxy config (Docker HTTPS)
services/, db/     accounts, trades, signals, models
utils/             config (env-driven), logging, security, mailer
logs/              rotating application logs
data/              cached pair CSVs
model/             per-pair joblib models
```

> **Security note:** If credentials were ever stored in `Secured.txt` (removed
> from the repo), rotate those secrets — old git history may still contain them.

## Configuration

Everything is environment-driven — see [.env.example](.env.example).
Nothing rewrites source files at runtime anymore; the symbol is a
parameter throughout the engine.

> Signals are informational only — not financial advice.
