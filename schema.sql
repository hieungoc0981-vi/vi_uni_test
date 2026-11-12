-- Ví Uni / MySQL 8.0.16+ (recommended 8.4 LTS)
-- Structure only. No accounts, sample transactions, credentials or DROP commands.
CREATE DATABASE IF NOT EXISTS vi_uni CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE vi_uni;


CREATE TABLE IF NOT EXISTS login_attempts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	bucket VARCHAR(64) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_login_attempts_bucket ON login_attempts (bucket);

CREATE INDEX ix_login_attempts_created_at ON login_attempts (created_at);

CREATE TABLE IF NOT EXISTS users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	full_name VARCHAR(100) NOT NULL, 
	email VARCHAR(191) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	student_id VARCHAR(50) NOT NULL, 
	school VARCHAR(150) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS categories (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	type VARCHAR(10) NOT NULL, 
	icon VARCHAR(16) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, name, type), 
	CONSTRAINT ck_category_type CHECK (type IN ('income','expense')), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_categories_user_id ON categories (user_id);

CREATE TABLE IF NOT EXISTS goals (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	target BIGINT NOT NULL, 
	deadline DATE NOT NULL, 
	auto_percent INTEGER NOT NULL, 
	archived BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_goal_target CHECK (target > 0), 
	CONSTRAINT ck_goal_auto CHECK (auto_percent BETWEEN 5 AND 20), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_goals_user_id ON goals (user_id);

CREATE TABLE IF NOT EXISTS request_keys (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	`key` VARCHAR(80) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	response TEXT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, `key`), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS student_groups (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	owner_id INTEGER NOT NULL, 
	join_code VARCHAR(24) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	UNIQUE (join_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wallets (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	initial_balance BIGINT NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_wallet_initial CHECK (initial_balance >= 0), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_wallets_user_id ON wallets (user_id);

CREATE TABLE IF NOT EXISTS audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id INTEGER, 
	user_id INTEGER NOT NULL, 
	action VARCHAR(100) NOT NULL, 
	details TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(group_id) REFERENCES student_groups (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_audit_logs_group_id ON audit_logs (group_id);

CREATE TABLE IF NOT EXISTS budgets (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	category_id INTEGER, 
	amount_limit BIGINT NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	warning_threshold INTEGER NOT NULL, 
	alerts_enabled BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_budget_amount CHECK (amount_limit > 0), 
	CONSTRAINT ck_budget_dates CHECK (end_date >= start_date), 
	CONSTRAINT ck_budget_threshold CHECK (warning_threshold BETWEEN 1 AND 100), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_budgets_user_id ON budgets (user_id);

CREATE TABLE IF NOT EXISTS group_entries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	payer_id INTEGER NOT NULL, 
	receiver_id INTEGER, 
	kind VARCHAR(20) NOT NULL, 
	amount BIGINT NOT NULL, 
	note VARCHAR(500) NOT NULL, 
	priority VARCHAR(15) NOT NULL, 
	transaction_date DATE NOT NULL, 
	receipt_name VARCHAR(80), 
	receipt_mime VARCHAR(30), 
	receipt_data BLOB(5242880), 
	voided BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_group_amount CHECK (amount > 0), 
	CONSTRAINT ck_group_kind CHECK (kind IN ('contribution','fund_expense','split','settlement')), 
	FOREIGN KEY(group_id) REFERENCES student_groups (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(payer_id) REFERENCES users (id), 
	FOREIGN KEY(receiver_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_group_entries_group_id ON group_entries (group_id);

CREATE TABLE IF NOT EXISTS group_members (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	`role` VARCHAR(10) NOT NULL, 
	joined_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (group_id, user_id), 
	FOREIGN KEY(group_id) REFERENCES student_groups (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_group_members_group_id ON group_members (group_id);

CREATE TABLE IF NOT EXISTS transactions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	wallet_id INTEGER NOT NULL, 
	category_id INTEGER NOT NULL, 
	amount BIGINT NOT NULL, 
	type VARCHAR(10) NOT NULL, 
	transaction_date DATE NOT NULL, 
	payment_method VARCHAR(30) NOT NULL, 
	priority VARCHAR(15) NOT NULL, 
	note VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transaction_amount CHECK (amount > 0), 
	CONSTRAINT ck_transaction_type CHECK (type IN ('income','expense')), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(wallet_id) REFERENCES wallets (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_transactions_transaction_date ON transactions (transaction_date);

CREATE INDEX ix_transactions_user_id ON transactions (user_id);

CREATE TABLE IF NOT EXISTS group_shares (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	entry_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (entry_id, user_id), 
	CONSTRAINT ck_share_amount CHECK (amount >= 0), 
	FOREIGN KEY(entry_id) REFERENCES group_entries (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_group_shares_entry_id ON group_shares (entry_id);

CREATE TABLE IF NOT EXISTS saving_entries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	goal_id INTEGER NOT NULL, 
	wallet_id INTEGER NOT NULL, 
	transaction_id INTEGER, 
	amount BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_saving_amount CHECK (amount != 0), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(goal_id) REFERENCES goals (id), 
	FOREIGN KEY(wallet_id) REFERENCES wallets (id), 
	FOREIGN KEY(transaction_id) REFERENCES transactions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX ix_saving_entries_user_id ON saving_entries (user_id);


-- Optional read-only reconciliation view. Requires CREATE VIEW when importing.
-- CurrentBalance is derived from committed ledger rows; never manually update it.
CREATE OR REPLACE VIEW wallet_balances AS
SELECT w.id AS WalletID, w.user_id AS UserID, w.name AS WalletName,
       w.initial_balance AS InitialBalance, w.currency AS Currency,
       w.initial_balance + COALESCE(t.flow, 0) - COALESCE(s.reserved, 0) AS CurrentBalance
FROM wallets w
LEFT JOIN (SELECT wallet_id, SUM(CASE WHEN type = 'income' THEN amount ELSE -amount END) AS flow
           FROM transactions GROUP BY wallet_id) t ON t.wallet_id = w.id
LEFT JOIN (SELECT wallet_id, SUM(amount) AS reserved
           FROM saving_entries GROUP BY wallet_id) s ON s.wallet_id = w.id;
