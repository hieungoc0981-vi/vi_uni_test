-- PostgreSQL schema for a dedicated Vi Uni database on Neon.
-- Apply only to an empty database created for this app.

CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wallets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'VND',
    opening_balance BIGINT NOT NULL DEFAULT 0 CHECK (opening_balance >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT wallets_user_name_unique UNIQUE (user_id, name),
    CONSTRAINT wallets_user_id_id_unique UNIQUE (user_id, id)
);

CREATE TABLE IF NOT EXISTS categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT categories_user_name_type_unique UNIQUE (user_id, name, type),
    CONSTRAINT categories_user_id_id_unique UNIQUE (user_id, id),
    CONSTRAINT categories_user_id_id_type_unique UNIQUE (user_id, id, type)
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    wallet_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    amount BIGINT NOT NULL CHECK (amount > 0),
    note TEXT NOT NULL DEFAULT '',
    transaction_date TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'optional'
        CHECK (priority IN ('essential', 'necessary', 'optional')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT transactions_wallet_owner_fk
        FOREIGN KEY (user_id, wallet_id) REFERENCES wallets (user_id, id) ON DELETE RESTRICT,
    CONSTRAINT transactions_category_type_fk
        FOREIGN KEY (user_id, category_id, type)
        REFERENCES categories (user_id, id, type) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS budgets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL,
    month TEXT NOT NULL CHECK (
        length(month) = 7 AND substring(month from 5 for 1) = '-'
        AND substring(month from 6 for 2) BETWEEN '01' AND '12'
    ),
    amount_limit BIGINT NOT NULL CHECK (amount_limit > 0),
    CONSTRAINT budgets_user_category_month_unique UNIQUE (user_id, category_id, month),
    CONSTRAINT budgets_category_owner_fk
        FOREIGN KEY (user_id, category_id) REFERENCES categories (user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS savings_goals (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_amount BIGINT NOT NULL CHECK (target_amount > 0),
    saved_amount BIGINT NOT NULL DEFAULT 0 CHECK (saved_amount >= 0),
    due_date TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Group funds. A new group should also insert its owner into group_members
-- with role='owner' in the same application transaction.
CREATE TABLE IF NOT EXISTS student_groups (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    join_code VARCHAR(24) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id BIGINT NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member'
        CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS group_entries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
    actor_id BIGINT NOT NULL,
    payer_id BIGINT NOT NULL,
    receiver_id BIGINT,
    kind TEXT NOT NULL
        CHECK (kind IN ('contribution', 'fund_expense', 'split', 'settlement')),
    amount BIGINT NOT NULL CHECK (amount > 0),
    note TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'optional'
        CHECK (priority IN ('essential', 'necessary', 'optional')),
    transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    receipt_url TEXT,
    voided BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT group_entries_group_id_id_unique UNIQUE (group_id, id),
    CONSTRAINT group_entries_actor_member_fk
        FOREIGN KEY (group_id, actor_id)
        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT,
    CONSTRAINT group_entries_payer_member_fk
        FOREIGN KEY (group_id, payer_id)
        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT,
    CONSTRAINT group_entries_receiver_member_fk
        FOREIGN KEY (group_id, receiver_id)
        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS group_shares (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL,
    entry_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    amount BIGINT NOT NULL CHECK (amount >= 0),
    CONSTRAINT group_shares_entry_user_unique UNIQUE (entry_id, user_id),
    CONSTRAINT group_shares_entry_group_fk
        FOREIGN KEY (group_id, entry_id)
        REFERENCES group_entries (group_id, id) ON DELETE CASCADE,
    CONSTRAINT group_shares_member_fk
        FOREIGN KEY (group_id, user_id)
        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT audit_logs_group_member_fk
        FOREIGN KEY (group_id, user_id)
        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS transactions_user_date_idx
    ON transactions (user_id, transaction_date);
CREATE INDEX IF NOT EXISTS budgets_user_month_idx
    ON budgets (user_id, month);
CREATE INDEX IF NOT EXISTS group_members_user_id_idx
    ON group_members (user_id);
CREATE INDEX IF NOT EXISTS group_entries_group_date_idx
    ON group_entries (group_id, transaction_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS group_shares_user_id_idx
    ON group_shares (user_id);
CREATE INDEX IF NOT EXISTS audit_logs_group_created_at_idx
    ON audit_logs (group_id, created_at DESC);
