import os
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash


DEFAULT_CATEGORIES = [
    ("Lương", "income"),
    ("Học bổng", "income"),
    ("Trợ cấp", "income"),
    ("Thu khác", "income"),
    ("Ăn uống", "expense"),
    ("Thuê trọ", "expense"),
    ("Học tập", "expense"),
    ("Di chuyển", "expense"),
    ("Giải trí", "expense"),
    ("Mua sắm", "expense"),
    ("Y tế", "expense"),
    ("Khác", "expense"),
]
PRIORITIES = {"essential", "necessary", "optional"}
load_dotenv()


def create_app():
    """Tạo Flask app; dùng PostgreSQL khi được cấu hình, SQLite cho local."""
    app = Flask(__name__)
    production = os.environ.get("VERCEL") == "1"
    secret_key = os.environ.get("SECRET_KEY")
    if production and not secret_key:
        raise RuntimeError("Vui lòng cấu hình SECRET_KEY trên môi trường triển khai.")
    app.config["SECRET_KEY"] = secret_key or secrets.token_hex(32)
    app.config["VI_UNI_DATABASE_URL"] = os.environ.get("VI_UNI_DATABASE_URL", "").strip()
    if production and not app.config["VI_UNI_DATABASE_URL"]:
        raise RuntimeError("Vui lòng cấu hình VI_UNI_DATABASE_URL trỏ tới Neon riêng của Ví Uni.")
    app.config["DATABASE"] = os.environ.get(
        "VI_UNI_DATABASE", str(Path(app.instance_path) / "vi_uni.sqlite3")
    )
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
    )

    postgres_driver = None
    integrity_error_types = (sqlite3.IntegrityError,)
    if app.config["VI_UNI_DATABASE_URL"]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("Cài psycopg để kết nối PostgreSQL.") from error
        postgres_driver = (psycopg, dict_row)
        integrity_error_types = (sqlite3.IntegrityError, psycopg.IntegrityError)
    else:
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    class ConnectionAdapter:
        def __init__(self, connection, is_postgres):
            self.connection = connection
            self.is_postgres = is_postgres

        def execute(self, statement, parameters=()):
            if self.is_postgres:
                statement = statement.replace("?", "%s")
            return self.connection.execute(statement, parameters)

        def executemany(self, statement, parameters):
            if self.is_postgres:
                statement = statement.replace("?", "%s")
            cursor = self.connection.cursor()
            cursor.executemany(statement, parameters)
            return cursor

        def executescript(self, script):
            if not self.is_postgres:
                return self.connection.executescript(script)
            cursor = None
            for statement in script.split(";"):
                if statement.strip():
                    cursor = self.connection.execute(statement)
            return cursor

        def commit(self):
            self.connection.commit()

        def rollback(self):
            self.connection.rollback()

        def close(self):
            self.connection.close()

    @contextmanager
    def database():
        if postgres_driver:
            psycopg, dict_row = postgres_driver
            raw_connection = psycopg.connect(
                app.config["VI_UNI_DATABASE_URL"],
                row_factory=dict_row,
                connect_timeout=10,
            )
        else:
            raw_connection = sqlite3.connect(app.config["DATABASE"], timeout=10)
            raw_connection.row_factory = sqlite3.Row
            raw_connection.execute("PRAGMA foreign_keys = ON")
        connection = ConnectionAdapter(raw_connection, bool(postgres_driver))
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize_database():
        with database() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'VND',
                    opening_balance INTEGER NOT NULL DEFAULT 0 CHECK (opening_balance >= 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, name)
                );
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, name, type)
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    note TEXT NOT NULL DEFAULT '',
                    transaction_date TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'optional'
                        CHECK (priority IN ('essential', 'necessary', 'optional')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    month TEXT NOT NULL,
                    amount_limit INTEGER NOT NULL CHECK (amount_limit > 0),
                    UNIQUE (user_id, category_id, month)
                );
                CREATE TABLE IF NOT EXISTS savings_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    target_amount INTEGER NOT NULL CHECK (target_amount > 0),
                    saved_amount INTEGER NOT NULL DEFAULT 0 CHECK (saved_amount >= 0),
                    due_date TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS student_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    join_code TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id INTEGER NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT NOT NULL DEFAULT 'member'
                        CHECK (role IN ('owner', 'admin', 'member')),
                    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (group_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS group_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
                    actor_id INTEGER NOT NULL,
                    payer_id INTEGER NOT NULL,
                    receiver_id INTEGER,
                    kind TEXT NOT NULL
                        CHECK (kind IN ('contribution', 'fund_expense', 'split', 'settlement')),
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    note TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'optional'
                        CHECK (priority IN ('essential', 'necessary', 'optional')),
                    transaction_date TEXT NOT NULL DEFAULT CURRENT_DATE,
                    receipt_url TEXT,
                    voided INTEGER NOT NULL DEFAULT 0 CHECK (voided IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (group_id, id),
                    FOREIGN KEY (group_id, actor_id)
                        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT,
                    FOREIGN KEY (group_id, payer_id)
                        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT,
                    FOREIGN KEY (group_id, receiver_id)
                        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS group_shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    entry_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount >= 0),
                    UNIQUE (entry_id, user_id),
                    FOREIGN KEY (group_id, entry_id)
                        REFERENCES group_entries (group_id, id) ON DELETE CASCADE,
                    FOREIGN KEY (group_id, user_id)
                        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id, user_id)
                        REFERENCES group_members (group_id, user_id) ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS transactions_user_date_idx
                    ON transactions(user_id, transaction_date);
                CREATE INDEX IF NOT EXISTS group_members_user_id_idx
                    ON group_members(user_id);
                CREATE INDEX IF NOT EXISTS group_entries_group_date_idx
                    ON group_entries(group_id, transaction_date DESC, id DESC);
                CREATE INDEX IF NOT EXISTS group_shares_user_id_idx
                    ON group_shares(user_id);
                CREATE INDEX IF NOT EXISTS audit_logs_group_created_at_idx
                    ON audit_logs(group_id, created_at DESC);
                """
            )

    def ensure_defaults(user_id):
        with database() as connection:
            connection.execute(
                "INSERT INTO wallets (user_id, name) VALUES (?, 'Ví chính') "
                "ON CONFLICT(user_id, name) DO NOTHING",
                (user_id,),
            )
            connection.executemany(
                "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, name, type) DO NOTHING",
                [(user_id, name, kind) for name, kind in DEFAULT_CATEGORIES],
            )

    # SQLite is created automatically for local development. PostgreSQL is
    # provisioned explicitly from database/schema.sql to avoid touching a
    # Neon database just because the app process starts.
    if not postgres_driver:
        initialize_database()

    def make_csrf_token():
        token = session.get("csrf_token")
        if token is None:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def valid_csrf_token():
        submitted = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        return bool(expected) and secrets.compare_digest(submitted, expected)

    @app.context_processor
    def template_values():
        return {
            "csrf_token": make_csrf_token(),
            "user_name": session.get("user_name", "Sinh viên"),
            "active_view": getattr(g, "active_view", "dashboard"),
            "today": date.today().isoformat(),
            "storage_backend": "PostgreSQL" if app.config["VI_UNI_DATABASE_URL"] else "SQLite",
        }

    @app.template_filter("vnd")
    def format_vnd(value):
        return f"{int(value or 0):,}".replace(",", ".") + " ₫"

    @app.before_request
    def require_login():
        public_endpoints = {"login", "register", "health", "static"}
        if request.endpoint not in public_endpoints and "user_id" not in session:
            return redirect(url_for("login"))

    def require_csrf():
        if not valid_csrf_token():
            flash("Phiên thao tác đã hết hạn. Vui lòng tải lại trang và thử lại.", "error")
            return False
        return True

    def safe_amount(raw_value):
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        return value if 0 < value <= 9_000_000_000_000_000 else None

    def valid_iso_date(value):
        try:
            date.fromisoformat(value)
            return True
        except (TypeError, ValueError):
            return False

    def period_condition(period, date_column="transaction_date"):
        today = date.today()
        if period == "day":
            return f"{date_column} = ?", [today.isoformat()]
        if period == "year":
            return f"{date_column} LIKE ?", [f"{today.year:04d}-%"]
        if period == "all":
            return "1 = 1", []
        return f"{date_column} LIKE ?", [f"{today.year:04d}-{today.month:02d}-%"]

    def base_context(view, title, subtitle):
        g.active_view = view
        return {"page_title": title, "page_subtitle": subtitle}

    def write_group_audit(connection, group_id, user_id, action, details):
        json_value = json.dumps(details, ensure_ascii=False)
        details_placeholder = "?::jsonb" if connection.is_postgres else "?"
        connection.execute(
            f"INSERT INTO audit_logs (group_id,user_id,action,details) VALUES (?,?,?,{details_placeholder})",
            (group_id, user_id, action, json_value),
        )

    def group_member_balances(connection, group_id, members):
        balances = {member["user_id"]: 0 for member in members}
        entries = connection.execute(
            """SELECT id,kind,payer_id,receiver_id,amount FROM group_entries
               WHERE group_id=? AND voided=FALSE AND kind IN ('split','settlement')
               ORDER BY id""",
            (group_id,),
        ).fetchall()
        for entry in entries:
            amount = entry["amount"]
            if entry["kind"] == "split":
                balances[entry["payer_id"]] += amount
                shares = connection.execute(
                    "SELECT user_id,amount FROM group_shares WHERE group_id=? AND entry_id=?",
                    (group_id, entry["id"]),
                ).fetchall()
                for share in shares:
                    balances[share["user_id"]] -= share["amount"]
            else:
                balances[entry["payer_id"]] += amount
                balances[entry["receiver_id"]] -= amount
        return balances

    def suggested_settlements(members, balances):
        names = {member["user_id"]: member["name"] for member in members}
        debtors = [[user_id, -balance] for user_id, balance in balances.items() if balance < 0]
        creditors = [[user_id, balance] for user_id, balance in balances.items() if balance > 0]
        debtors.sort(key=lambda item: item[1], reverse=True)
        creditors.sort(key=lambda item: item[1], reverse=True)
        suggestions = []
        debtor_index = creditor_index = 0
        while debtor_index < len(debtors) and creditor_index < len(creditors):
            debtor_id, owed = debtors[debtor_index]
            creditor_id, due = creditors[creditor_index]
            amount = min(owed, due)
            suggestions.append({
                "from_name": names[debtor_id],
                "to_name": names[creditor_id],
                "amount": amount,
            })
            debtors[debtor_index][1] -= amount
            creditors[creditor_index][1] -= amount
            if debtors[debtor_index][1] == 0:
                debtor_index += 1
            if creditors[creditor_index][1] == 0:
                creditor_index += 1
        return suggestions

    def dashboard_context(period="month"):
        if period not in {"day", "month", "year"}:
            period = "month"
        condition, params = period_condition(period)
        user_id = session["user_id"]
        with database() as connection:
            wallets = connection.execute(
                "SELECT COALESCE(SUM(opening_balance), 0) AS opening FROM wallets WHERE user_id = ?",
                (user_id,),
            ).fetchone()["opening"]
            lifetime = connection.execute(
                """SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE -amount END), 0) AS net
                   FROM transactions WHERE user_id = ?""",
                (user_id,),
            ).fetchone()["net"]
            totals = connection.execute(
                f"""SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income,
                           COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense
                    FROM transactions WHERE user_id = ? AND {condition}""",
                [user_id, *params],
            ).fetchone()
            savings = connection.execute(
                "SELECT COALESCE(SUM(saved_amount), 0) AS total FROM savings_goals WHERE user_id = ?",
                (user_id,),
            ).fetchone()["total"]
            recent = connection.execute(
                """SELECT t.*, c.name AS category_name, w.name AS wallet_name
                   FROM transactions t JOIN categories c ON c.id=t.category_id
                   JOIN wallets w ON w.id=t.wallet_id
                   WHERE t.user_id = ? ORDER BY t.transaction_date DESC, t.id DESC LIMIT 6""",
                (user_id,),
            ).fetchall()
            month = date.today().strftime("%Y-%m")
            budgets = connection.execute(
                """SELECT b.amount_limit, c.name AS category_name,
                          COALESCE((SELECT SUM(t.amount) FROM transactions t
                                    WHERE t.user_id=b.user_id AND t.category_id=b.category_id
                                      AND t.type='expense' AND substr(t.transaction_date,1,7)=b.month), 0) AS spent
                   FROM budgets b JOIN categories c ON c.id=b.category_id
                   WHERE b.user_id=? AND b.month=? ORDER BY c.name""",
                (user_id, month),
            ).fetchall()
        return {
            "period": period,
            "balance": wallets + lifetime,
            "income_total": totals["income"],
            "expense_total": totals["expense"],
            "savings_total": savings,
            "recent_transactions": recent,
            "dashboard_budgets": budgets,
        }

    @app.get("/")
    def index():
        context = base_context("dashboard", "Tổng quan", "Theo dõi tình hình thu chi của bạn.")
        context.update(dashboard_context(request.args.get("period", "month")))
        return render_template("index.html", **context)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error = None
        if request.method == "POST":
            if not require_csrf():
                error = "Phiên đăng ký đã hết hạn."
            else:
                name = request.form.get("name", "").strip()
                email = request.form.get("email", "").strip().lower()
                password = request.form.get("password", "")
                if not name or not email or "@" not in email:
                    error = "Vui lòng nhập họ tên và email hợp lệ."
                elif len(password) < 8 or len(password) > 128:
                    error = "Mật khẩu cần có từ 8 đến 128 ký tự."
                else:
                    try:
                        with database() as connection:
                            cursor = connection.execute(
                                "INSERT INTO users (name,email,password_hash) VALUES (?,?,?) RETURNING id",
                                (name, email, generate_password_hash(password)),
                            )
                            user_id = cursor.fetchone()["id"]
                        session.clear()
                        session["user_id"] = user_id
                        session["user_name"] = name
                        ensure_defaults(user_id)
                        return redirect(url_for("index"))
                    except integrity_error_types:
                        error = "Email này đã được đăng ký."
        return render_template("auth.html", mode="register", error=error)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            if not require_csrf():
                error = "Phiên đăng nhập đã hết hạn."
            else:
                email = request.form.get("email", "").strip().lower()
                with database() as connection:
                    user = connection.execute(
                        "SELECT id,name,password_hash FROM users WHERE email=?", (email,)
                    ).fetchone()
                if user is None or not check_password_hash(
                    user["password_hash"], request.form.get("password", "")
                ):
                    error = "Email hoặc mật khẩu chưa chính xác."
                else:
                    session.clear()
                    session["user_id"] = user["id"]
                    session["user_name"] = user["name"]
                    ensure_defaults(user["id"])
                    return redirect(url_for("index"))
        return render_template("auth.html", mode="login", error=error)

    @app.post("/logout")
    def logout():
        if require_csrf():
            session.clear()
        return redirect(url_for("login"))

    @app.get("/api/health")
    def health():
        return jsonify({"message": "Backend Ví Uni đang hoạt động"})

    @app.route("/transactions", methods=["GET", "POST"])
    def transactions():
        user_id = session["user_id"]
        period = request.args.get("period", "month")
        if period not in {"day", "month", "year", "all"}:
            period = "month"
        error = None
        if request.method == "POST":
            if require_csrf():
                action = request.form.get("action", "create")
                if action == "delete":
                    transaction_id = request.form.get("transaction_id", type=int)
                    with database() as connection:
                        connection.execute(
                            "DELETE FROM transactions WHERE id=? AND user_id=?",
                            (transaction_id, user_id),
                        )
                    flash("Đã xóa giao dịch.", "success")
                    return redirect(url_for("transactions", period=period))

                transaction_type = request.form.get("type")
                amount = safe_amount(request.form.get("amount"))
                transaction_date = request.form.get("transaction_date", "")
                note = request.form.get("note", "").strip()[:500]
                wallet_id = request.form.get("wallet_id", type=int)
                category_id = request.form.get("category_id", type=int)
                priority = request.form.get("priority", "optional")
                transaction_id = request.form.get("transaction_id", type=int)
                if transaction_type not in {"income", "expense"}:
                    error = "Vui lòng chọn khoản thu hoặc chi."
                elif amount is None:
                    error = "Số tiền phải là số nguyên dương."
                elif not valid_iso_date(transaction_date):
                    error = "Ngày giao dịch không hợp lệ."
                elif priority not in PRIORITIES:
                    error = "Mức ưu tiên không hợp lệ."
                else:
                    with database() as connection:
                        wallet = connection.execute(
                            "SELECT id FROM wallets WHERE id=? AND user_id=?", (wallet_id, user_id)
                        ).fetchone()
                        category = connection.execute(
                            "SELECT id FROM categories WHERE id=? AND user_id=? AND type=?",
                            (category_id, user_id, transaction_type),
                        ).fetchone()
                        if not wallet or not category:
                            error = "Ví hoặc danh mục không hợp lệ."
                        elif transaction_id:
                            owned = connection.execute(
                                "SELECT id FROM transactions WHERE id=? AND user_id=?",
                                (transaction_id, user_id),
                            ).fetchone()
                            if not owned:
                                error = "Không tìm thấy giao dịch cần sửa."
                            else:
                                connection.execute(
                                    """UPDATE transactions SET wallet_id=?,category_id=?,type=?,amount=?,note=?,
                                       transaction_date=?,priority=? WHERE id=? AND user_id=?""",
                                    (wallet_id, category_id, transaction_type, amount, note,
                                     transaction_date, priority if transaction_type == "expense" else "optional",
                                     transaction_id, user_id),
                                )
                        else:
                            connection.execute(
                                """INSERT INTO transactions
                                   (user_id,wallet_id,category_id,type,amount,note,transaction_date,priority)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (user_id, wallet_id, category_id, transaction_type, amount, note,
                                 transaction_date, priority if transaction_type == "expense" else "optional"),
                            )
                    if error is None:
                        if transaction_type == "expense":
                            month = transaction_date[:7]
                            with database() as connection:
                                budget = connection.execute(
                                    "SELECT amount_limit FROM budgets WHERE user_id=? AND category_id=? AND month=?",
                                    (user_id, category_id, month),
                                ).fetchone()
                                spent = connection.execute(
                                    """SELECT COALESCE(SUM(amount),0) AS total FROM transactions
                                       WHERE user_id=? AND category_id=? AND type='expense'
                                         AND substr(transaction_date,1,7)=?""",
                                    (user_id, category_id, month),
                                ).fetchone()["total"]
                            if budget and spent >= budget["amount_limit"]:
                                flash("Bạn đã chạm hoặc vượt ngân sách danh mục trong tháng này.", "warning")
                            elif budget and spent >= budget["amount_limit"] * 0.8:
                                flash("Lưu ý: bạn đã sử dụng ít nhất 80% ngân sách danh mục.", "warning")
                        flash("Đã cập nhật giao dịch." if transaction_id else "Đã lưu giao dịch.", "success")
                        return redirect(url_for("transactions", period=period))

        condition, params = period_condition(period)
        with database() as connection:
            rows = connection.execute(
                f"""SELECT t.*,c.name AS category_name,w.name AS wallet_name FROM transactions t
                    JOIN categories c ON c.id=t.category_id JOIN wallets w ON w.id=t.wallet_id
                    WHERE t.user_id=? AND {condition} ORDER BY t.transaction_date DESC,t.id DESC""",
                [user_id, *params],
            ).fetchall()
            categories = connection.execute(
                "SELECT * FROM categories WHERE user_id=? ORDER BY type,name", (user_id,)
            ).fetchall()
            wallets = connection.execute(
                "SELECT * FROM wallets WHERE user_id=? ORDER BY name", (user_id,)
            ).fetchall()
            edit_id = request.args.get("edit", type=int)
            editing = connection.execute(
                "SELECT * FROM transactions WHERE id=? AND user_id=?", (edit_id, user_id)
            ).fetchone() if edit_id else None
        context = base_context("transactions", "Giao dịch", "Thêm, xem và chỉnh sửa các khoản thu chi.")
        context.update({"transactions": rows, "categories": categories, "wallets": wallets,
                        "editing": editing, "period": period, "form_error": error})
        return render_template("index.html", **context)

    @app.post("/transactions/<int:transaction_id>/delete")
    def delete_transaction(transaction_id):
        if require_csrf():
            with database() as connection:
                connection.execute(
                    "DELETE FROM transactions WHERE id=? AND user_id=?",
                    (transaction_id, session["user_id"]),
                )
            flash("Đã xóa giao dịch.", "success")
        return redirect(url_for("transactions"))

    @app.post("/categories")
    def add_category():
        if not require_csrf():
            return redirect(url_for("transactions"))
        name = request.form.get("name", "").strip()[:80]
        kind = request.form.get("type")
        if not name or kind not in {"income", "expense"}:
            flash("Vui lòng nhập tên và loại danh mục hợp lệ.", "error")
        else:
            try:
                with database() as connection:
                    connection.execute(
                        "INSERT INTO categories (user_id,name,type) VALUES (?,?,?)",
                        (session["user_id"], name, kind),
                    )
                flash("Đã thêm danh mục.", "success")
            except integrity_error_types:
                flash("Danh mục cùng tên và loại đã tồn tại.", "error")
        return redirect(url_for("transactions"))

    @app.post("/wallets")
    def add_wallet():
        if not require_csrf():
            return redirect(url_for("transactions"))
        name = request.form.get("name", "").strip()[:80]
        opening_balance = request.form.get("opening_balance", "0")
        try:
            opening_balance = int(opening_balance)
        except (TypeError, ValueError):
            opening_balance = -1
        if not name or opening_balance < 0 or opening_balance > 9_000_000_000_000_000:
            flash("Tên ví không được để trống và số dư mở đầu phải từ 0 trở lên.", "error")
        else:
            try:
                with database() as connection:
                    connection.execute(
                        "INSERT INTO wallets (user_id,name,opening_balance) VALUES (?,?,?)",
                        (session["user_id"], name, opening_balance),
                    )
                flash("Đã thêm ví.", "success")
            except integrity_error_types:
                flash("Tên ví này đã tồn tại.", "error")
        return redirect(url_for("transactions"))

    @app.route("/budgets", methods=["GET", "POST"])
    def budgets():
        user_id = session["user_id"]
        if request.method == "POST" and require_csrf():
            category_id = request.form.get("category_id", type=int)
            amount_limit = safe_amount(request.form.get("amount_limit"))
            month = request.form.get("month", "")
            with database() as connection:
                category = connection.execute(
                    "SELECT id FROM categories WHERE id=? AND user_id=? AND type='expense'",
                    (category_id, user_id),
                ).fetchone()
                valid_month = len(month) == 7 and month[4:5] == "-" and month[:4].isdigit() and month[5:].isdigit() and 1 <= int(month[5:]) <= 12
                if not category or not amount_limit or not valid_month:
                    flash("Danh mục, tháng hoặc hạn mức không hợp lệ.", "error")
                else:
                    connection.execute(
                        """INSERT INTO budgets (user_id,category_id,month,amount_limit) VALUES (?,?,?,?)
                           ON CONFLICT(user_id,category_id,month) DO UPDATE SET amount_limit=excluded.amount_limit""",
                        (user_id, category_id, month, amount_limit),
                    )
                    flash("Đã lưu hạn mức tháng.", "success")
                    return redirect(url_for("budgets", month=month))
        month = request.args.get("month", date.today().strftime("%Y-%m"))
        if len(month) != 7 or month[4:5] != "-" or not month[:4].isdigit() or not month[5:].isdigit() or not 1 <= int(month[5:]) <= 12:
            month = date.today().strftime("%Y-%m")
        with database() as connection:
            categories = connection.execute(
                "SELECT * FROM categories WHERE user_id=? AND type='expense' ORDER BY name", (user_id,)
            ).fetchall()
            rows = connection.execute(
                """SELECT b.*,c.name AS category_name,
                          COALESCE((SELECT SUM(t.amount) FROM transactions t
                                    WHERE t.user_id=b.user_id AND t.category_id=b.category_id
                                      AND t.type='expense' AND substr(t.transaction_date,1,7)=b.month),0) AS spent
                   FROM budgets b JOIN categories c ON c.id=b.category_id
                   WHERE b.user_id=? AND b.month=? ORDER BY c.name""",
                (user_id, month),
            ).fetchall()
        context = base_context("budgets", "Ngân sách", "Đặt hạn mức theo danh mục cho từng tháng.")
        context.update({"categories": categories, "budgets": rows, "month": month})
        return render_template("index.html", **context)

    @app.post("/budgets/<int:budget_id>/delete")
    def delete_budget(budget_id):
        if require_csrf():
            with database() as connection:
                connection.execute("DELETE FROM budgets WHERE id=? AND user_id=?", (budget_id, session["user_id"]))
            flash("Đã xóa hạn mức.", "success")
        return redirect(url_for("budgets"))

    @app.route("/savings", methods=["GET", "POST"])
    def savings():
        user_id = session["user_id"]
        if request.method == "POST" and require_csrf():
            name = request.form.get("name", "").strip()[:100]
            target = safe_amount(request.form.get("target_amount"))
            due_date = request.form.get("due_date", "") or None
            if not name or not target or (due_date and not valid_iso_date(due_date)):
                flash("Tên mục tiêu, số tiền và ngày hoàn thành chưa hợp lệ.", "error")
            else:
                with database() as connection:
                    connection.execute(
                        "INSERT INTO savings_goals (user_id,name,target_amount,due_date) VALUES (?,?,?,?)",
                        (user_id, name, target, due_date),
                    )
                flash("Đã tạo mục tiêu tiết kiệm.", "success")
                return redirect(url_for("savings"))
        with database() as connection:
            goals = connection.execute(
                "SELECT * FROM savings_goals WHERE user_id=? ORDER BY created_at DESC,id DESC", (user_id,)
            ).fetchall()
        context = base_context("savings", "Tiết kiệm", "Theo dõi tiến độ các mục tiêu cá nhân.")
        context.update({"goals": goals})
        return render_template("index.html", **context)

    @app.post("/savings/<int:goal_id>/contribute")
    def contribute_savings(goal_id):
        if require_csrf():
            amount = safe_amount(request.form.get("amount"))
            if amount is None:
                flash("Số tiền cần góp phải là số nguyên dương.", "error")
            else:
                with database() as connection:
                    cursor = connection.execute(
                        "UPDATE savings_goals SET saved_amount=saved_amount+? WHERE id=? AND user_id=?",
                        (amount, goal_id, session["user_id"]),
                    )
                flash("Đã cập nhật số tiền mục tiêu." if cursor.rowcount else "Không tìm thấy mục tiêu.",
                      "success" if cursor.rowcount else "error")
        return redirect(url_for("savings"))

    @app.post("/savings/<int:goal_id>/delete")
    def delete_savings_goal(goal_id):
        if require_csrf():
            with database() as connection:
                connection.execute("DELETE FROM savings_goals WHERE id=? AND user_id=?", (goal_id, session["user_id"]))
            flash("Đã xóa mục tiêu tiết kiệm.", "success")
        return redirect(url_for("savings"))

    @app.route("/groups", methods=["GET", "POST"])
    def groups():
        user_id = session["user_id"]
        if request.method == "POST":
            if not require_csrf():
                return redirect(url_for("groups"))
            name = request.form.get("name", "").strip()[:100]
            if not name:
                flash("Vui lòng nhập tên nhóm.", "error")
                return redirect(url_for("groups"))
            join_code = secrets.token_hex(12).upper()
            try:
                with database() as connection:
                    cursor = connection.execute(
                        "INSERT INTO student_groups (name,owner_id,join_code) VALUES (?,?,?) RETURNING id",
                        (name, user_id, join_code),
                    )
                    group_id = cursor.fetchone()["id"]
                    connection.execute(
                        "INSERT INTO group_members (group_id,user_id,role) VALUES (?,?, 'owner')",
                        (group_id, user_id),
                    )
                    write_group_audit(connection, group_id, user_id, "group_created", {"name": name})
            except integrity_error_types:
                flash("Chưa tạo được nhóm. Vui lòng thử lại.", "error")
                return redirect(url_for("groups"))
            flash("Đã tạo nhóm. Chia sẻ mã tham gia với các thành viên.", "success")
            return redirect(url_for("group_detail", group_id=group_id))

        with database() as connection:
            user_groups = connection.execute(
                """SELECT g.*,gm.role,
                          (SELECT COUNT(*) FROM group_members m WHERE m.group_id=g.id) AS member_count,
                          COALESCE((SELECT SUM(CASE WHEN e.kind='contribution' THEN e.amount
                                                   WHEN e.kind='fund_expense' THEN -e.amount ELSE 0 END)
                                    FROM group_entries e WHERE e.group_id=g.id AND e.voided=FALSE),0) AS fund_balance
                   FROM student_groups g JOIN group_members gm ON gm.group_id=g.id
                   WHERE gm.user_id=? ORDER BY g.created_at DESC,g.id DESC""",
                (user_id,),
            ).fetchall()
        context = base_context("groups", "Quỹ nhóm", "Tạo quỹ chung hoặc tham gia nhóm bằng mã mời.")
        context.update({"user_groups": user_groups})
        return render_template("index.html", **context)

    @app.post("/groups/join")
    def join_group():
        if not require_csrf():
            return redirect(url_for("groups"))
        join_code = request.form.get("join_code", "").strip().upper()
        user_id = session["user_id"]
        with database() as connection:
            group = connection.execute(
                "SELECT id FROM student_groups WHERE join_code=?", (join_code,)
            ).fetchone()
            if group is None:
                flash("Không tìm thấy nhóm với mã này.", "error")
            else:
                member = connection.execute(
                    "SELECT 1 FROM group_members WHERE group_id=? AND user_id=?",
                    (group["id"], user_id),
                ).fetchone()
                if member:
                    flash("Bạn đã là thành viên của nhóm này.", "warning")
                else:
                    connection.execute(
                        "INSERT INTO group_members (group_id,user_id,role) VALUES (?,?, 'member')",
                        (group["id"], user_id),
                    )
                    write_group_audit(connection, group["id"], user_id, "member_joined", {})
                    flash("Đã tham gia nhóm.", "success")
                    return redirect(url_for("group_detail", group_id=group["id"]))
        return redirect(url_for("groups"))

    @app.route("/groups/<int:group_id>", methods=["GET", "POST"])
    def group_detail(group_id):
        user_id = session["user_id"]
        with database() as connection:
            group = connection.execute(
                """SELECT g.*,gm.role FROM student_groups g JOIN group_members gm ON gm.group_id=g.id
                   WHERE g.id=? AND gm.user_id=?""",
                (group_id, user_id),
            ).fetchone()
            if group is None:
                abort(404)
            members = connection.execute(
                """SELECT m.user_id,m.role,m.joined_at,u.name FROM group_members m
                   JOIN users u ON u.id=m.user_id WHERE m.group_id=? ORDER BY m.joined_at,m.user_id""",
                (group_id,),
            ).fetchall()

            if request.method == "POST":
                if not require_csrf():
                    return redirect(url_for("group_detail", group_id=group_id))
                action = request.form.get("action")
                amount = safe_amount(request.form.get("amount"))
                note = request.form.get("note", "").strip()[:500]
                member_ids = {member["user_id"] for member in members}
                entry_id = None

                if amount is None:
                    flash("Số tiền phải là số nguyên dương.", "error")
                elif action == "fund":
                    kind = request.form.get("kind")
                    if kind not in {"contribution", "fund_expense"}:
                        flash("Loại giao dịch quỹ không hợp lệ.", "error")
                    else:
                        fund_balance = connection.execute(
                            """SELECT COALESCE(SUM(CASE WHEN kind='contribution' THEN amount
                                                       WHEN kind='fund_expense' THEN -amount ELSE 0 END),0) AS balance
                               FROM group_entries WHERE group_id=? AND voided=FALSE""",
                            (group_id,),
                        ).fetchone()["balance"]
                        if kind == "fund_expense" and amount > fund_balance:
                            flash("Số dư quỹ không đủ cho khoản chi này.", "error")
                        else:
                            cursor = connection.execute(
                                """INSERT INTO group_entries (group_id,actor_id,payer_id,kind,amount,note)
                                   VALUES (?,?,?,?,?,?) RETURNING id""",
                                (group_id, user_id, user_id, kind, amount, note),
                            )
                            entry_id = cursor.fetchone()["id"]
                            write_group_audit(connection, group_id, user_id, kind,
                                              {"entry_id": entry_id, "amount": amount})
                elif action == "split":
                    payer_id = request.form.get("payer_id", type=int)
                    if payer_id not in member_ids:
                        flash("Người thanh toán không thuộc nhóm này.", "error")
                    else:
                        cursor = connection.execute(
                            """INSERT INTO group_entries (group_id,actor_id,payer_id,kind,amount,note)
                               VALUES (?,?,?,'split',?,?) RETURNING id""",
                            (group_id, user_id, payer_id, amount, note),
                        )
                        entry_id = cursor.fetchone()["id"]
                        base_share, remainder = divmod(amount, len(members))
                        connection.executemany(
                            "INSERT INTO group_shares (group_id,entry_id,user_id,amount) VALUES (?,?,?,?)",
                            [(group_id, entry_id, member["user_id"],
                              base_share + (1 if index < remainder else 0))
                             for index, member in enumerate(members)],
                        )
                        write_group_audit(connection, group_id, user_id, "split_created",
                                          {"entry_id": entry_id, "amount": amount,
                                           "member_count": len(members)})
                elif action == "settlement":
                    payer_id = request.form.get("payer_id", type=int)
                    receiver_id = request.form.get("receiver_id", type=int)
                    if payer_id not in member_ids or receiver_id not in member_ids or payer_id == receiver_id:
                        flash("Chọn hai thành viên khác nhau trong nhóm để quyết toán.", "error")
                    else:
                        balances = group_member_balances(connection, group_id, members)
                        max_settlement = min(-balances.get(payer_id, 0), balances.get(receiver_id, 0))
                        if max_settlement <= 0 or amount > max_settlement:
                            flash("Khoản quyết toán vượt số nợ hiện tại hoặc không đúng chiều thanh toán.", "error")
                        else:
                            cursor = connection.execute(
                                """INSERT INTO group_entries
                                   (group_id,actor_id,payer_id,receiver_id,kind,amount,note)
                                   VALUES (?,?,?,?,'settlement',?,?) RETURNING id""",
                                (group_id, user_id, payer_id, receiver_id, amount, note),
                            )
                            entry_id = cursor.fetchone()["id"]
                            write_group_audit(connection, group_id, user_id, "settlement_recorded",
                                              {"entry_id": entry_id, "payer_id": payer_id,
                                               "receiver_id": receiver_id, "amount": amount})
                else:
                    flash("Thao tác quỹ nhóm không hợp lệ.", "error")

                if entry_id is not None:
                    flash("Đã lưu hoạt động quỹ nhóm.", "success")
                    return redirect(url_for("group_detail", group_id=group_id))

        with database() as connection:
            members = connection.execute(
                """SELECT m.user_id,m.role,m.joined_at,u.name FROM group_members m
                   JOIN users u ON u.id=m.user_id WHERE m.group_id=? ORDER BY m.joined_at,m.user_id""",
                (group_id,),
            ).fetchall()
            fund_balance = connection.execute(
                """SELECT COALESCE(SUM(CASE WHEN kind='contribution' THEN amount
                                           WHEN kind='fund_expense' THEN -amount ELSE 0 END),0) AS balance
                   FROM group_entries WHERE group_id=? AND voided=FALSE""",
                (group_id,),
            ).fetchone()["balance"]
            entries = connection.execute(
                """SELECT e.*,actor.name AS actor_name,payer.name AS payer_name,receiver.name AS receiver_name
                   FROM group_entries e JOIN users actor ON actor.id=e.actor_id
                   JOIN users payer ON payer.id=e.payer_id
                   LEFT JOIN users receiver ON receiver.id=e.receiver_id
                   WHERE e.group_id=? ORDER BY e.transaction_date DESC,e.id DESC LIMIT 100""",
                (group_id,),
            ).fetchall()
            entry_shares = {}
            for entry in entries:
                if entry["kind"] == "split":
                    entry_shares[entry["id"]] = connection.execute(
                        """SELECT s.amount,u.name FROM group_shares s JOIN users u ON u.id=s.user_id
                           WHERE s.group_id=? AND s.entry_id=? ORDER BY u.name""",
                        (group_id, entry["id"]),
                    ).fetchall()
            audits = connection.execute(
                """SELECT a.action,a.created_at,u.name FROM audit_logs a JOIN users u ON u.id=a.user_id
                   WHERE a.group_id=? ORDER BY a.created_at DESC,a.id DESC LIMIT 20""",
                (group_id,),
            ).fetchall()
            balances = group_member_balances(connection, group_id, members)
        member_balances = [
            {"user_id": member["user_id"], "name": member["name"],
             "role": member["role"], "balance": balances.get(member["user_id"], 0)}
            for member in members
        ]
        context = base_context("groups", group["name"], "Sao kê chung và số dư của nhóm.")
        context.update({
            "group": group,
            "members": members,
            "member_balances": member_balances,
            "settlement_suggestions": suggested_settlements(members, balances),
            "group_fund_balance": fund_balance,
            "group_entries": entries,
            "entry_shares": entry_shares,
            "group_audits": audits,
        })
        return render_template("index.html", **context)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("VI_UNI_PORT", "5000")))
