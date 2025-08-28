
# Step 1 — Database & Backend Skeleton (DIY)
This starter gives you:
- MySQL schema (SQL + SQLAlchemy models)
- Env/config loader
- Password hashing helpers
- Risk/lot-size calculator (pip-aware)
- Minimal Flask API (health + register/login stubs)

> Keep your existing repo. Drop these files/folders in as **new additions** so nothing breaks.

## 1) Create DB & user (MySQL)

```sql
-- Adjust credentials as you like
CREATE DATABASE IF NOT EXISTS smc_trader CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'smc_user'@'%' IDENTIFIED BY 'smc_password';
GRANT ALL PRIVILEGES ON smc_trader.* TO 'smc_user'@'%';
FLUSH PRIVILEGES;
```

## 2) Copy `.env.example` → `.env` and fill in values

```bash
cp .env.example .env
```

## 3) Install deps (inside your venv)

```bash
pip install -r requirements.txt
```

## 4) Create tables

```bash
python db/init_db.py
```

You should see: `Tables created. Admin seeded (if provided).`

## 5) Run the minimal API

```bash
python api/app.py
```

Then open http://127.0.0.1:5000/health

---

## What’s included

- **db/models.py** — SQLAlchemy models: Users, TelegramLink, Accounts, Trades, Signals, EquitySnapshot
- **db/session.py** — SQLAlchemy engine + session factory
- **db/init_db.py** — Creates tables and seeds an admin user if `ADMIN_EMAIL` and `ADMIN_PASSWORD` exist in `.env`
- **utils/orm_config.py** — Loads env and builds MYSQL URL (uses `pymysql` dialect)
- **utils/security.py** — Password hashing (Werkzeug)
- **services/risk.py** — Lot size calculation using stop loss pips and pip value per standard lot
- **api/app.py** — Tiny Flask app with `/health`, `/register`, `/login` (simple JSON stubs)

## Next steps (Step 2 preview)

- Wire your **SMC predictor** into a `predict/` service function that returns `{ side, confidence, stop_pips, entry_price }`.
- Add `/trades` endpoints and a protected route for placing/logging trades.
- Create `agent_loop.py` and schedule it (cron/APScheduler) to: fetch → predict → decide → lot calc → notify telegram → log trade → score when closed.
