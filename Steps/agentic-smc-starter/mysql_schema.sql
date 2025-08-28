
-- Raw SQL schema (optional). If you use SQLAlchemy create_all, you don't need this.
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telegram_links (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  chat_id VARCHAR(64) NOT NULL UNIQUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS accounts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  name VARCHAR(64) NOT NULL,
  balance DOUBLE DEFAULT 0,
  base_risk_pct DOUBLE DEFAULT 0.01,
  leverage INT DEFAULT 100,
  is_default BOOLEAN DEFAULT FALSE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_user_account_name (user_id, name),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS signals (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  symbol VARCHAR(16) NOT NULL,
  timeframe VARCHAR(8) DEFAULT '1h',
  side VARCHAR(4),
  confidence DOUBLE DEFAULT 0,
  entry_price DOUBLE,
  stop_pips DOUBLE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_signals_symbol_time (symbol, timeframe, created_at),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS trades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  account_id INT NOT NULL,
  symbol VARCHAR(16) NOT NULL,
  side VARCHAR(4) NOT NULL,
  status ENUM('OPEN','CLOSED','SKIPPED') DEFAULT 'OPEN',
  entry_price DOUBLE NOT NULL,
  stop_loss DOUBLE NOT NULL,
  take_profit DOUBLE NULL,
  lot_size DOUBLE NOT NULL,
  confidence DOUBLE DEFAULT 0,
  opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  closed_at DATETIME NULL,
  pnl DOUBLE NULL,
  outcome_score INT NULL,
  INDEX ix_trades_user_symbol_time (user_id, symbol, opened_at),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  account_id INT NOT NULL,
  balance DOUBLE NOT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);
