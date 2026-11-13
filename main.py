"""Ví Uni — Flask + MySQL. See README.md for setup and accounting rules."""
import csv
import hashlib
import io
import ipaddress
import json
import os
import re
import secrets
import ssl
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
db = SQLAlchemy()
TZ = ZoneInfo('Asia/Ho_Chi_Minh')
PRIORITIES = ('essential', 'necessary', 'optional')
DEFAULT_CATEGORIES = [('Ăn uống', 'expense', '🍜'), ('Thuê trọ', 'expense', '🏠'),
    ('Học tập', 'expense', '📚'), ('Di chuyển', 'expense', '🚌'),
    ('Giải trí', 'expense', '🎮'), ('Mua sắm', 'expense', '🛍️'),
    ('Lương làm thêm', 'income', '💼'), ('Gia đình hỗ trợ', 'income', '💚'),
    ('Học bổng', 'income', '🎓'), ('Thu nhập khác', 'income', '✨')]


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today():
    return datetime.now(TZ).date()


@event.listens_for(Engine, 'connect')
def sqlite_foreign_keys(connection, _):
    if connection.__class__.__module__.startswith('sqlite3'):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=10000')


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(191), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    student_id = db.Column(db.String(50), nullable=False, default='')
    school = db.Column(db.String(150), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class Wallet(db.Model):
    __tablename__ = 'wallets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    initial_balance = db.Column(db.BigInteger, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default='VND')
    __table_args__ = (CheckConstraint('initial_balance >= 0', name='ck_wallet_initial'),)


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    icon = db.Column(db.String(16), nullable=False, default='🏷️')
    __table_args__ = (UniqueConstraint('user_id', 'name', 'type'),
                     CheckConstraint("type IN ('income','expense')", name='ck_category_type'))


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    type = db.Column(db.String(10), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    payment_method = db.Column(db.String(30), nullable=False, default='cash')
    priority = db.Column(db.String(15), nullable=False, default='necessary')
    note = db.Column(db.String(500), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (CheckConstraint('amount > 0', name='ck_transaction_amount'),
                     CheckConstraint("type IN ('income','expense')", name='ck_transaction_type'))


class Budget(db.Model):
    __tablename__ = 'budgets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    amount_limit = db.Column(db.BigInteger, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    warning_threshold = db.Column(db.Integer, nullable=False, default=80)
    alerts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (CheckConstraint('amount_limit > 0', name='ck_budget_amount'),
        CheckConstraint('end_date >= start_date', name='ck_budget_dates'),
        CheckConstraint('warning_threshold BETWEEN 1 AND 100', name='ck_budget_threshold'))


class Goal(db.Model):
    __tablename__ = 'goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    target = db.Column(db.BigInteger, nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    auto_percent = db.Column(db.Integer, nullable=False, default=10)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint('target > 0', name='ck_goal_target'),
                     CheckConstraint('auto_percent BETWEEN 5 AND 20', name='ck_goal_auto'))


class SavingEntry(db.Model):
    __tablename__ = 'saving_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    goal_id = db.Column(db.Integer, db.ForeignKey('goals.id'), nullable=False)
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallets.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=True)
    amount = db.Column(db.BigInteger, nullable=False)  # + into jar, - out of jar
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (CheckConstraint('amount != 0', name='ck_saving_amount'),)


class Group(db.Model):
    __tablename__ = 'student_groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    join_code = db.Column(db.String(24), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class Member(db.Model):
    __tablename__ = 'group_members'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('student_groups.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False, default='member')
    joined_at = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (UniqueConstraint('group_id', 'user_id'),)


class GroupEntry(db.Model):
    __tablename__ = 'group_entries'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('student_groups.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    kind = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    note = db.Column(db.String(500), nullable=False, default='')
    priority = db.Column(db.String(15), nullable=False, default='necessary')
    transaction_date = db.Column(db.Date, nullable=False)
    receipt_name = db.Column(db.String(80), nullable=True)
    receipt_mime = db.Column(db.String(30), nullable=True)
    receipt_data = db.Column(db.LargeBinary(length=5 * 1024 * 1024), nullable=True)
    voided = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (CheckConstraint('amount > 0', name='ck_group_amount'),
        CheckConstraint("kind IN ('contribution','fund_expense','split','settlement')", name='ck_group_kind'))


class Share(db.Model):
    __tablename__ = 'group_shares'
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('group_entries.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (UniqueConstraint('entry_id', 'user_id'), CheckConstraint('amount >= 0', name='ck_share_amount'))


class Audit(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('student_groups.id'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class RequestKey(db.Model):
    __tablename__ = 'request_keys'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    key = db.Column(db.String(80), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    response = db.Column(db.Text, nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'key'),)


class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    id = db.Column(db.Integer, primary_key=True)
    bucket = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def fail(message, status=400):
    raise ApiError(message, status)


def data():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        fail('Dữ liệu gửi lên phải là một đối tượng JSON.')
    return payload


def string(payload, key, maximum=100, required=True):
    value = payload.get(key, '')
    if not isinstance(value, str):
        fail(f'{key}: nội dung không hợp lệ.')
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        fail(f'{key}: cần từ {1 if required else 0} đến {maximum} ký tự.')
    return value


def integer(value, label='Số tiền', minimum=1, maximum=10**12):
    if isinstance(value, bool) or not re.fullmatch(r'-?\d+', str(value)):
        fail(f'{label} phải là số nguyên (VND, không có dấu phân cách).')
    result = int(value)
    if not minimum <= result <= maximum:
        fail(f'{label} phải từ {minimum:,} đến {maximum:,}.')
    return result


def parsed_date(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        fail('Ngày phải có định dạng YYYY-MM-DD.')


def owned(model, item_id):
    item = db.session.get(model, integer(item_id, 'Mã'))
    if item is None or item.user_id != session['uid']:
        fail('Không tìm thấy dữ liệu thuộc tài khoản của bạn.', 404)
    return item


def audit(action, details, group_id=None):
    db.session.add(Audit(user_id=session['uid'], group_id=group_id,
                         action=action, details=json.dumps(details, ensure_ascii=False)))


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('uid') or not db.session.get(User, session['uid']):
            fail('Vui lòng đăng nhập để tiếp tục.', 401)
        return fn(*args, **kwargs)
    return wrapped


def mutation(fn):
    """Serialize mutations per user; group operations additionally lock their group.

    The response and request key commit in the SAME DB transaction as ledger writes.
    Clients retain the key across network retries. SQLite is for local trial only.
    """
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        uid = session['uid']
        db.session.execute(select(User).where(User.id == uid).with_for_update()).scalar_one()
        key = request.headers.get('Idempotency-Key', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', key):
            fail('Thiếu khóa chống lưu trùng. Hãy tải lại trang và thử lại.')
        if request.mimetype == 'multipart/form-data':
            # Multipart boundaries change on retries; fingerprint the actual file content.
            files = {}
            for name, upload in request.files.items():
                files[name] = hashlib.sha256(upload.read()).hexdigest()
                upload.seek(0)
            raw = json.dumps({'form': request.form.to_dict(), 'files': files}, sort_keys=True).encode()
        else:
            raw = request.get_data()
        digest = hashlib.sha256(request.method.encode() + request.path.encode() + raw).hexdigest()
        old = db.session.scalar(select(RequestKey).where(RequestKey.user_id == uid, RequestKey.key == key))
        if old:
            if old.fingerprint != digest:
                fail('Khóa lưu trùng đã được dùng cho nội dung khác.', 409)
            return jsonify(json.loads(old.response))
        result = fn(*args, **kwargs) or {'ok': True}
        db.session.flush()
        # Derived ledgers must never become negative, including edits/deletes.
        for wallet in Wallet.query.filter_by(user_id=uid):
            if wallet_balance(wallet) < 0:
                fail(f'Ví {wallet.name} không đủ tiền. Hãy kiểm tra giao dịch hoặc hũ tiết kiệm.')
        for goal in Goal.query.filter_by(user_id=uid):
            if goal_balance(goal.id) < 0:
                fail('Khoản trích lập này đã được sử dụng. Không thể thay đổi giao dịch gốc.')
        db.session.add(RequestKey(user_id=uid, key=key, fingerprint=digest,
                                  response=json.dumps(result, ensure_ascii=False)))
        db.session.commit()
        return jsonify(result)
    return wrapped


def wallet_balance(wallet):
    rows = db.session.query(Transaction.type, db.func.sum(Transaction.amount)).filter_by(wallet_id=wallet.id).group_by(Transaction.type).all()
    sums = dict(rows)
    reserved = db.session.query(db.func.coalesce(db.func.sum(SavingEntry.amount), 0)).filter_by(wallet_id=wallet.id).scalar()
    return wallet.initial_balance + int(sums.get('income', 0)) - int(sums.get('expense', 0)) - int(reserved)


def goal_balance(goal_id):
    return int(db.session.query(db.func.coalesce(db.func.sum(SavingEntry.amount), 0)).filter_by(goal_id=goal_id).scalar())


def tx_dict(row):
    cat = db.session.get(Category, row.category_id)
    wallet = db.session.get(Wallet, row.wallet_id)
    return {'id': row.id, 'amount': row.amount, 'type': row.type, 'date': row.transaction_date.isoformat(),
            'category_id': cat.id, 'category': cat.name, 'icon': cat.icon, 'wallet_id': wallet.id,
            'wallet': wallet.name, 'priority': row.priority, 'payment_method': row.payment_method, 'note': row.note}


def budget_dict(b):
    q = Transaction.query.filter(Transaction.user_id == b.user_id, Transaction.type == 'expense',
                                  Transaction.transaction_date.between(b.start_date, b.end_date))
    if b.category_id:
        q = q.filter_by(category_id=b.category_id)
    spent = sum(t.amount for t in q)
    category = db.session.get(Category, b.category_id) if b.category_id else None
    return {'id': b.id, 'category_id': b.category_id, 'name': category.name if category else 'Tổng chi tiêu',
        'limit': b.amount_limit, 'spent': spent, 'remaining': b.amount_limit - spent,
        'percent': round(spent * 100 / b.amount_limit, 1), 'threshold': b.warning_threshold,
        'alerts_enabled': b.alerts_enabled, 'start': b.start_date.isoformat(), 'end': b.end_date.isoformat()}


def current_warnings():
    result = []
    for b in Budget.query.filter(Budget.user_id == session['uid'], Budget.start_date <= today(), Budget.end_date >= today()):
        item = budget_dict(b)
        if b.alerts_enabled and item['percent'] >= b.warning_threshold:
            result.append(item)
    return result


def filtered_transactions():
    q = Transaction.query.filter_by(user_id=session['uid'])
    if request.args.get('start'):
        q = q.filter(Transaction.transaction_date >= parsed_date(request.args['start']))
    if request.args.get('end'):
        q = q.filter(Transaction.transaction_date <= parsed_date(request.args['end']))
    if request.args.get('type') in ('income', 'expense'):
        q = q.filter_by(type=request.args['type'])
    if request.args.get('category'):
        q = q.filter_by(category_id=integer(request.args['category'], 'Danh mục'))
    if request.args.get('q'):
        term = request.args['q'][:100].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        q = q.join(Category).filter(db.or_(Transaction.note.ilike(f'%{term}%', escape='\\'), Category.name.ilike(f'%{term}%', escape='\\')))
    return q


def group_access(gid, admin=False, lock=False):
    query = select(Group).where(Group.id == gid)
    if lock:
        query = query.with_for_update()
    group = db.session.scalar(query)
    member = Member.query.filter_by(group_id=gid, user_id=session['uid']).first()
    if not group or not member:
        fail('Bạn không có quyền truy cập nhóm này.', 404)
    if admin and member.role != 'admin':
        fail('Thao tác này chỉ dành cho trưởng nhóm.', 403)
    return group, member


def group_accounting(gid):
    members = Member.query.filter_by(group_id=gid).order_by(Member.user_id).all()
    balances = {m.user_id: 0 for m in members}
    contributions = {m.user_id: 0 for m in members}
    paid = {m.user_id: 0 for m in members}
    cash, expense = 0, 0
    for e in GroupEntry.query.filter_by(group_id=gid, voided=False):
        if e.kind == 'contribution':
            cash += e.amount
            contributions[e.payer_id] += e.amount
        elif e.kind == 'fund_expense':
            cash -= e.amount
            expense += e.amount
        elif e.kind == 'split':
            expense += e.amount
            paid[e.payer_id] += e.amount
            balances[e.payer_id] += e.amount
            for share in Share.query.filter_by(entry_id=e.id):
                balances[share.user_id] -= share.amount
        elif e.kind == 'settlement':
            balances[e.payer_id] += e.amount
            balances[e.receiver_id] -= e.amount
    return members, balances, contributions, paid, cash, expense


def settlement_plan(balances):
    debtors = [[uid, -value] for uid, value in sorted(balances.items()) if value < 0]
    creditors = [[uid, value] for uid, value in sorted(balances.items()) if value > 0]
    result = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1])
        result.append({'from': debtors[i][0], 'to': creditors[j][0], 'amount': amount})
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if not debtors[i][1]:
            i += 1
        if not creditors[j][1]:
            j += 1
    return result


def create_app(config=None):
    app = Flask(__name__)
    config = config or {}
    on_vercel = os.environ.get('VERCEL') == '1'
    secret = config.get('SECRET_KEY') or os.environ.get('SECRET_KEY')
    database_uri = config.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL', 'sqlite:///vi_uni.db')
    if database_uri.startswith(('postgresql://', 'postgres://')):
        database_uri = 'postgresql+psycopg://' + database_uri.split('://', 1)[1]
    if on_vercel:
        # Functions have no shared persistent disk. Never create a local secret or DB.
        if not secret or len(secret) < 32 or secret in ('REPLACE_WITH_A_RANDOM_SECRET', 'THAY_BANG_CHUOI_NGAU_NHIEN'):
            raise RuntimeError('Vercel: set SECRET_KEY to a random string of at least 32 characters in Environment Variables, then redeploy.')
        try:
            database_url = make_url(database_uri)
        except Exception:
            raise RuntimeError('Vercel: DATABASE_URL must be a valid MySQL or PostgreSQL connection URL.') from None
        if database_url.drivername not in ('mysql+pymysql', 'postgresql+psycopg') or not database_url.host or not database_url.database:
            raise RuntimeError('Vercel: set DATABASE_URL to an external MySQL or PostgreSQL database. Local SQLite is not persistent.')
        host = database_url.host.lower()
        local_host = host == 'localhost' or host.endswith('.localhost') or host in ('0.0.0.0', '::')
        try:
            local_host = local_host or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if local_host:
            raise RuntimeError('Vercel: DATABASE_URL cannot use localhost or a loopback address. Use the external hostname supplied by your database provider.')
    if not secret:
        # Persistent local key: restarting the server does not invalidate every session.
        key_path = Path(app.instance_path) / 'secret.key'
        key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with key_path.open('x') as handle:
                os.chmod(key_path, 0o600)
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = key_path.read_text().strip()
    app.config.update(SECRET_KEY=secret,
        SQLALCHEMY_DATABASE_URI=database_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=on_vercel or os.environ.get('COOKIE_SECURE', '0') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        RECEIPT_MAX_MB=3 if on_vercel else 5,
        MAX_CONTENT_LENGTH=(4 if on_vercel else 8) * 1024 * 1024)
    if config:
        app.config.update(config)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('mysql'):
        # A read before a row lock must not leave later ledger reads on an old snapshot.
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            **app.config['SQLALCHEMY_ENGINE_OPTIONS'], 'isolation_level': 'READ COMMITTED'}
        connect_args = {'connect_timeout': 10, 'read_timeout': 20, 'write_timeout': 20}
        if os.environ.get('DB_SSL', '1' if on_vercel else '0') == '1':
            ca = os.environ.get('DB_SSL_CA')
            context = ssl.create_default_context(cadata=ca.replace('\\n', '\n') if ca else None)
            connect_args['ssl'] = context
        app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args'] = connect_args
        if on_vercel:
            app.config['SQLALCHEMY_ENGINE_OPTIONS'].update(
                pool_size=2, max_overflow=0, pool_timeout=10, pool_recycle=280)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        pg_url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
        connect_args = {'connect_timeout': 10}
        if on_vercel and 'sslmode' not in pg_url.query:
            connect_args['sslmode'] = 'require'
        app.config['SQLALCHEMY_ENGINE_OPTIONS'].update(
            isolation_level='READ COMMITTED', connect_args=connect_args,
            pool_size=2, max_overflow=0, pool_timeout=10, pool_recycle=280)
    if on_vercel:
        app.config['SESSION_COOKIE_SECURE'] = True
    db.init_app(app)

    @app.before_request
    def csrf_guard():
        if request.path.startswith('/api/') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            expected = session.get('csrf', '')
            supplied = request.headers.get('X-CSRF-Token', '')
            if not expected or not secrets.compare_digest(expected, supplied):
                fail('Phiên bảo mật đã hết hạn. Hãy tải lại trang.', 403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.errorhandler(ApiError)
    def api_error(error):
        db.session.rollback()
        return jsonify(error=error.message), error.status

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return jsonify(error='Dữ liệu trùng hoặc đang được sử dụng. Vui lòng kiểm tra và thử lại.'), 409

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error=f"Hóa đơn quá lớn. Vui lòng chọn tệp tối đa {app.config['RECEIPT_MAX_MB']} MB."), 413

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/auth')
    def auth_state():
        session.setdefault('csrf', secrets.token_hex(32))
        u = db.session.get(User, session.get('uid')) if session.get('uid') else None
        return jsonify(csrf=session['csrf'], user=user_dict(u) if u else None)

    def user_dict(u):
        return {'id': u.id, 'name': u.full_name, 'email': u.email, 'school': u.school, 'student_id': u.student_id}

    @app.post('/api/register')
    def register():
        p = data()
        name, email, password = string(p, 'name'), string(p, 'email', 191).lower(), string(p, 'password', 128)
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            fail('Địa chỉ email không hợp lệ.')
        if len(password) < 8:
            fail('Mật khẩu phải có ít nhất 8 ký tự.')
        u = User(full_name=name, email=email, password_hash=generate_password_hash(password, method='scrypt'))
        db.session.add(u)
        db.session.flush()
        db.session.add_all(Category(user_id=u.id, name=n, type=t, icon=i) for n, t, i in DEFAULT_CATEGORIES)
        db.session.add(Wallet(user_id=u.id, name='Tiền mặt', initial_balance=0))
        db.session.commit()
        session.clear()
        session.update(uid=u.id, csrf=secrets.token_hex(32))
        session.permanent = True
        return jsonify(user=user_dict(u), csrf=session['csrf'])

    @app.post('/api/login')
    def login():
        p = data()
        email, password = string(p, 'email', 191).lower(), string(p, 'password', 128)
        # DB-backed per-account and per-IP limits work across waitress workers.
        buckets = [hashlib.sha256(('email:' + email).encode()).hexdigest(),
                   hashlib.sha256(('ip:' + (request.remote_addr or '')).encode()).hexdigest()]
        cutoff = now() - timedelta(minutes=15)
        db.session.query(LoginAttempt).filter(LoginAttempt.created_at < cutoff).delete()
        for bucket, limit in zip(buckets, (8, 60)):
            if LoginAttempt.query.filter(LoginAttempt.bucket == bucket, LoginAttempt.created_at >= cutoff).count() >= limit:
                db.session.commit()
                fail('Đăng nhập sai quá nhiều lần. Hãy thử lại sau 15 phút.', 429)
        u = User.query.filter_by(email=email).first()
        dummy = app.config.setdefault('DUMMY_PASSWORD_HASH', generate_password_hash(secrets.token_hex(16)))
        valid = check_password_hash(u.password_hash if u else dummy, password)
        if not u or not valid:
            db.session.add_all(LoginAttempt(bucket=b) for b in buckets)
            db.session.commit()
            fail('Email hoặc mật khẩu chưa đúng.', 401)
        db.session.query(LoginAttempt).filter(LoginAttempt.bucket == buckets[0]).delete()
        db.session.commit()
        session.clear()
        session.update(uid=u.id, csrf=secrets.token_hex(32))
        session.permanent = True
        return jsonify(user=user_dict(u), csrf=session['csrf'])

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.patch('/api/profile')
    @mutation
    def profile():
        p, u = data(), db.session.get(User, session['uid'])
        u.full_name = string(p, 'name')
        u.school = string(p, 'school', 150, False)
        u.student_id = string(p, 'student_id', 50, False)
        if p.get('new_password'):
            if not check_password_hash(u.password_hash, str(p.get('current_password', ''))):
                fail('Mật khẩu hiện tại chưa đúng.')
            password = string(p, 'new_password', 128)
            if len(password) < 8:
                fail('Mật khẩu mới cần ít nhất 8 ký tự.')
            u.password_hash = generate_password_hash(password, method='scrypt')
        return {'user': user_dict(u)}

    @app.get('/api/state')
    @login_required
    def state():
        uid = session['uid']
        month = request.args.get('month', today().strftime('%Y-%m'))
        start = parsed_date(month + '-01')
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        rows = Transaction.query.filter(Transaction.user_id == uid, Transaction.transaction_date.between(start, end)).all()
        wallets = [{'id': w.id, 'name': w.name, 'initial_balance': w.initial_balance, 'balance': wallet_balance(w), 'currency': w.currency} for w in Wallet.query.filter_by(user_id=uid)]
        goals = [{'id': g.id, 'name': g.name, 'target': g.target, 'saved': goal_balance(g.id), 'deadline': g.deadline.isoformat(), 'auto_percent': g.auto_percent} for g in Goal.query.filter_by(user_id=uid, archived=False)]
        cats = [{'id': c.id, 'name': c.name, 'type': c.type, 'icon': c.icon} for c in Category.query.filter_by(user_id=uid)]
        budgets = [budget_dict(b) for b in Budget.query.filter(Budget.user_id == uid, Budget.start_date <= end, Budget.end_date >= start)]
        groups = []
        for m in Member.query.filter_by(user_id=uid):
            group = db.session.get(Group, m.group_id)
            *_, cash, expense = group_accounting(group.id)
            groups.append({'id': group.id, 'name': group.name, 'role': m.role, 'cash': cash, 'expense': expense,
                           'members': Member.query.filter_by(group_id=group.id).count()})
        trend = []
        cursor = start
        for _ in range(6):
            last = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            period = Transaction.query.filter(Transaction.user_id == uid, Transaction.transaction_date.between(cursor, last)).all()
            trend.append({'month': cursor.strftime('%Y-%m'), 'income': sum(t.amount for t in period if t.type == 'income'),
                          'expense': sum(t.amount for t in period if t.type == 'expense')})
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        return jsonify(wallets=wallets, categories=cats, goals=goals, budgets=budgets, groups=groups,
            balance=sum(w['balance'] for w in wallets), saved=sum(g['saved'] for g in goals),
            income=sum(t.amount for t in rows if t.type == 'income'), expense=sum(t.amount for t in rows if t.type == 'expense'),
            recent=[tx_dict(t) for t in sorted(rows, key=lambda t: (t.transaction_date, t.id), reverse=True)[:5]],
            trend=trend[::-1], warnings=current_warnings(), today=today().isoformat(), receipt_max_mb=app.config['RECEIPT_MAX_MB'])

    @app.post('/api/wallets')
    @mutation
    def add_wallet():
        p = data()
        w = Wallet(user_id=session['uid'], name=string(p, 'name', 80), initial_balance=integer(p.get('initial_balance', 0), minimum=0))
        db.session.add(w)
        return {'ok': True}

    @app.patch('/api/wallets/<int:wid>')
    @mutation
    def rename_wallet(wid):
        owned(Wallet, wid).name = string(data(), 'name', 80)

    @app.delete('/api/wallets/<int:wid>')
    @mutation
    def delete_wallet(wid):
        w = owned(Wallet, wid)
        if Transaction.query.filter_by(wallet_id=wid).first() or SavingEntry.query.filter_by(wallet_id=wid).first() or wallet_balance(w):
            fail('Chỉ có thể xóa ví trống, chưa có giao dịch.')
        if Wallet.query.filter_by(user_id=session['uid']).count() <= 1:
            fail('Bạn cần giữ ít nhất một ví.')
        db.session.delete(w)

    @app.route('/api/categories', methods=['POST'])
    @app.route('/api/categories/<int:cid>', methods=['PATCH', 'DELETE'])
    @mutation
    def categories(cid=None):
        c = owned(Category, cid) if cid else Category(user_id=session['uid'])
        if request.method == 'DELETE':
            if Transaction.query.filter_by(category_id=cid).first() or Budget.query.filter_by(category_id=cid).first():
                fail('Danh mục đang có giao dịch hoặc ngân sách. Hãy chuyển dữ liệu sang danh mục khác trước.')
            db.session.delete(c)
        else:
            p = data()
            c.name, c.icon = string(p, 'name', 80), string(p, 'icon', 16)
            kind = p.get('type')
            if kind not in ('income', 'expense'):
                fail('Loại danh mục chưa hợp lệ.')
            if cid and c.type != kind and (Transaction.query.filter_by(category_id=cid).first() or Budget.query.filter_by(category_id=cid).first()):
                fail('Không thể đổi loại danh mục đang được sử dụng.')
            c.type = kind
            db.session.add(c)

    @app.get('/api/transactions')
    @login_required
    def transactions():
        page = integer(request.args.get('page', 1), 'Trang', maximum=100000)
        query = filtered_transactions()
        count = query.count()
        rows = query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).offset((page - 1) * 15).limit(15).all()
        return jsonify(items=[tx_dict(t) for t in rows], total=count, page=page, pages=max(1, (count + 14) // 15))

    @app.route('/api/transactions', methods=['POST'])
    @app.route('/api/transactions/<int:tid>', methods=['PATCH', 'DELETE'])
    @mutation
    def save_transaction(tid=None):
        t = owned(Transaction, tid) if tid else Transaction(user_id=session['uid'])
        if tid:
            for entry in SavingEntry.query.filter_by(transaction_id=tid):
                db.session.delete(entry)
            db.session.flush()
        if request.method == 'DELETE':
            audit('transaction.delete', tx_dict(t))
            db.session.delete(t)
            db.session.flush()
            return {'ok': True, 'warnings': current_warnings()}
        p = data()
        wallet, category = owned(Wallet, p.get('wallet_id')), owned(Category, p.get('category_id'))
        if p.get('type') != category.type:
            fail('Danh mục không khớp loại thu/chi.')
        t.wallet_id, t.category_id, t.type = wallet.id, category.id, category.type
        t.amount = integer(p.get('amount'))
        t.transaction_date = parsed_date(p.get('date'))
        if t.transaction_date > today():
            fail('Chưa thể ghi nhận giao dịch trong tương lai.')
        t.note = string(p, 'note', 500, False)
        t.priority = p.get('priority', 'necessary')
        t.payment_method = p.get('payment_method', 'cash')
        if t.priority not in PRIORITIES or t.payment_method not in ('cash', 'bank', 'ewallet'):
            fail('Mức ưu tiên hoặc phương thức thanh toán không hợp lệ.')
        db.session.add(t)
        db.session.flush()
        allocations = p.get('allocations', [])
        if not isinstance(allocations, list) or len(allocations) > 100:
            fail('Danh sách trích lập không hợp lệ.')
        if allocations and t.type != 'income':
            fail('Chỉ trích lập tự động từ khoản thu.')
        total = 0
        seen = set()
        for allocation in allocations:
            if not isinstance(allocation, dict):
                fail('Khoản trích lập không hợp lệ.')
            goal = owned(Goal, allocation.get('goal_id'))
            if goal.archived:
                fail('Hũ tiết kiệm này đã được đóng.')
            amount = integer(allocation.get('amount'))
            if goal.id in seen:
                fail('Mỗi hũ chỉ được xuất hiện một lần.')
            seen.add(goal.id)
            total += amount
            db.session.add(SavingEntry(user_id=session['uid'], wallet_id=wallet.id, goal_id=goal.id, transaction_id=t.id, amount=amount))
        if total > t.amount:
            fail('Tổng trích lập vượt quá số tiền thu nhập.')
        audit('transaction.update' if tid else 'transaction.create', tx_dict(t))
        db.session.flush()
        return {'ok': True, 'id': t.id, 'warnings': current_warnings()}

    @app.route('/api/budgets', methods=['POST'])
    @app.route('/api/budgets/<int:bid>', methods=['PATCH', 'DELETE'])
    @mutation
    def budgets(bid=None):
        b = owned(Budget, bid) if bid else Budget(user_id=session['uid'])
        if request.method == 'DELETE':
            db.session.delete(b)
        else:
            p = data()
            category = owned(Category, p['category_id']) if p.get('category_id') else None
            if category and category.type != 'expense':
                fail('Ngân sách chỉ dùng cho danh mục chi tiêu.')
            b.category_id = category.id if category else None
            b.amount_limit = integer(p.get('limit'))
            b.start_date, b.end_date = parsed_date(p.get('start')), parsed_date(p.get('end'))
            b.warning_threshold = integer(p.get('threshold', 80), 'Ngưỡng cảnh báo', maximum=100)
            if not isinstance(p.get('alerts_enabled', True), bool):
                fail('Cài đặt thông báo không hợp lệ.')
            b.alerts_enabled = p.get('alerts_enabled', True)
            if b.end_date < b.start_date:
                fail('Ngày kết thúc phải từ ngày bắt đầu trở đi.')
            # No overlapping envelopes for the same category; total and category envelopes may coexist.
            overlap = Budget.query.filter(Budget.user_id == session['uid'], Budget.category_id == b.category_id,
                Budget.start_date <= b.end_date, Budget.end_date >= b.start_date)
            if bid:
                overlap = overlap.filter(Budget.id != bid)
            if overlap.first():
                fail('Đã có ngân sách cùng danh mục trùng khoảng thời gian.')
            db.session.add(b)
        db.session.flush()
        return {'ok': True, 'warnings': current_warnings()}

    @app.route('/api/goals', methods=['POST'])
    @app.route('/api/goals/<int:gid>', methods=['PATCH', 'DELETE'])
    @mutation
    def goals(gid=None):
        g = owned(Goal, gid) if gid else Goal(user_id=session['uid'])
        if gid and g.archived:
            fail('Hũ tiết kiệm này đã được đóng.')
        if request.method == 'DELETE':
            if goal_balance(gid):
                fail('Hãy rút hết tiền trong hũ trước khi xóa.')
            # Keep transfers, including transfers between different wallets, in the ledger.
            g.archived = True
        else:
            p = data()
            g.name = string(p, 'name')
            g.target = integer(p.get('target'))
            g.deadline = parsed_date(p.get('deadline'))
            g.auto_percent = integer(p.get('auto_percent', 10), 'Tỷ lệ gợi ý', minimum=5, maximum=20)
            db.session.add(g)

    @app.post('/api/goals/<int:gid>/transfer')
    @mutation
    def transfer(gid):
        goal = owned(Goal, gid)
        if goal.archived:
            fail('Hũ tiết kiệm này đã được đóng.')
        p = data()
        wallet = owned(Wallet, p.get('wallet_id'))
        amount = integer(p.get('amount'))
        if p.get('direction') not in ('deposit', 'withdraw'):
            fail('Hướng chuyển tiền không hợp lệ.')
        amount *= 1 if p['direction'] == 'deposit' else -1
        if goal_balance(gid) + amount < 0:
            fail('Hũ không đủ tiền để rút.')
        db.session.add(SavingEntry(user_id=session['uid'], goal_id=goal.id, wallet_id=wallet.id, amount=amount))
        audit('saving.' + p['direction'], {'goal': gid, 'wallet': wallet.id, 'amount': amount})

    @app.get('/api/goals/<int:gid>/history')
    @login_required
    def goal_history(gid):
        owned(Goal, gid)
        rows = SavingEntry.query.filter_by(goal_id=gid).order_by(SavingEntry.id.desc()).limit(100).all()
        return jsonify(items=[{'id': e.id, 'amount': e.amount, 'wallet': db.session.get(Wallet, e.wallet_id).name,
            'time': e.created_at.isoformat() + 'Z', 'automatic': bool(e.transaction_id)} for e in rows])

    @app.get('/api/reports')
    @login_required
    def reports():
        rows = filtered_transactions().order_by(Transaction.transaction_date).all()
        period = request.args.get('period', 'day')
        if period not in ('day', 'week', 'month', 'year'):
            fail('Kỳ thống kê không hợp lệ.')
        timeline, categories, priorities = {}, {}, {}
        for t in rows:
            d = t.transaction_date
            key = (d - timedelta(days=d.weekday())).isoformat() if period == 'week' else d.strftime({'day': '%Y-%m-%d', 'month': '%Y-%m', 'year': '%Y'} .get(period, '%Y-%m-%d'))
            timeline.setdefault(key, {'label': key, 'income': 0, 'expense': 0})[t.type] += t.amount
            if t.type == 'expense':
                c = db.session.get(Category, t.category_id)
                categories.setdefault(c.id, {'name': c.name, 'icon': c.icon, 'amount': 0})['amount'] += t.amount
                priorities[t.priority] = priorities.get(t.priority, 0) + t.amount
        income = sum(t.amount for t in rows if t.type == 'income')
        expense = sum(t.amount for t in rows if t.type == 'expense')
        return jsonify(income=income, expense=expense, net=income-expense, count=len(rows),
            timeline=list(timeline.values()), categories=sorted(categories.values(), key=lambda c: c['amount'], reverse=True), priorities=priorities,
            top=[tx_dict(t) for t in sorted((t for t in rows if t.type == 'expense'), key=lambda t: t.amount, reverse=True)[:10]])

    @app.get('/api/export')
    @login_required
    def export():
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['Ngày', 'Loại', 'Danh mục', 'Ví', 'Số tiền VND', 'Ưu tiên', 'Ghi chú'])
        for t in filtered_transactions().order_by(Transaction.transaction_date.desc()):
            c, w = db.session.get(Category, t.category_id), db.session.get(Wallet, t.wallet_id)
            safe = lambda text: "'" + text if str(text).startswith(('=', '+', '-', '@', '\t', '\r')) else text
            writer.writerow([t.transaction_date.isoformat(), t.type, safe(c.name), safe(w.name), t.amount, t.priority, safe(t.note)])
        return send_file(io.BytesIO(('\ufeff' + out.getvalue()).encode('utf-8')), mimetype='text/csv; charset=utf-8', as_attachment=True, download_name='vi-uni-giao-dich.csv')

    @app.post('/api/groups')
    @mutation
    def create_group():
        group = Group(name=string(data(), 'name'), owner_id=session['uid'], join_code=secrets.token_hex(6).upper())
        db.session.add(group)
        db.session.flush()
        db.session.add(Member(group_id=group.id, user_id=session['uid'], role='admin'))
        audit('group.create', {'name': group.name}, group.id)
        return {'ok': True, 'id': group.id}

    @app.post('/api/groups/join')
    @mutation
    def join_group():
        code = string(data(), 'code', 24).upper()
        group = db.session.scalar(select(Group).where(Group.join_code == code).with_for_update())
        if not group:
            fail('Mã tham gia không tồn tại hoặc đã được đổi.')
        if Member.query.filter_by(group_id=group.id, user_id=session['uid']).first():
            fail('Bạn đã là thành viên nhóm này.')
        db.session.add(Member(group_id=group.id, user_id=session['uid'], role='member'))
        audit('group.join', {}, group.id)
        return {'ok': True, 'id': group.id}

    @app.post('/api/groups/<int:gid>/code')
    @mutation
    def rotate_code(gid):
        group, _ = group_access(gid, admin=True, lock=True)
        group.join_code = secrets.token_hex(6).upper()
        audit('group.rotate_code', {}, gid)
        return {'ok': True, 'code': group.join_code}

    @app.get('/api/groups/<int:gid>')
    @login_required
    def group_detail(gid):
        group, member = group_access(gid, lock=True)
        members, balances, contributions, paid, cash, expense = group_accounting(gid)
        people = {m.user_id: db.session.get(User, m.user_id).full_name for m in members}
        entries = []
        for e in GroupEntry.query.filter_by(group_id=gid).order_by(GroupEntry.id.desc()).limit(200):
            entries.append({'id': e.id, 'actor': people[e.actor_id], 'actor_id': e.actor_id,
                'payer_id': e.payer_id, 'payer': people[e.payer_id], 'receiver_id': e.receiver_id,
                'receiver': people.get(e.receiver_id, ''), 'amount': e.amount, 'kind': e.kind, 'note': e.note,
                'priority': e.priority, 'date': e.transaction_date.isoformat(), 'time': e.created_at.isoformat() + 'Z',
                'voided': e.voided, 'receipt': bool(e.receipt_name),
                'shares': [{'user_id': s.user_id, 'name': people[s.user_id], 'amount': s.amount} for s in Share.query.filter_by(entry_id=e.id)]})
        logs = [{'actor': people[a.user_id], 'action': a.action, 'details': json.loads(a.details), 'time': a.created_at.isoformat()+'Z'} for a in Audit.query.filter_by(group_id=gid).order_by(Audit.id.desc()).limit(100)]
        return jsonify(id=gid, name=group.name, role=member.role, code=group.join_code,
            cash=cash, expense=expense, members=[{'id': m.user_id, 'name': people[m.user_id], 'role': m.role,
            'balance': balances[m.user_id], 'contribution': contributions[m.user_id], 'paid': paid[m.user_id]} for m in members],
            settlements=settlement_plan(balances), entries=entries, audit=logs)

    @app.post('/api/groups/<int:gid>/entries')
    @mutation
    def group_entry(gid):
        _, member = group_access(gid, lock=True)
        p = data()
        kind = p.get('kind')
        if kind not in ('contribution', 'fund_expense', 'split', 'settlement'):
            fail('Loại giao dịch nhóm không hợp lệ.')
        if member.role != 'admin' and kind in ('contribution', 'fund_expense', 'settlement'):
            fail('Trưởng nhóm cần xác nhận nộp quỹ, chi quỹ và thanh toán nợ.', 403)
        people = [m.user_id for m in Member.query.filter_by(group_id=gid).order_by(Member.user_id)]
        payer = integer(p.get('payer_id', session['uid']), 'Người thanh toán')
        if payer not in people or (member.role != 'admin' and payer != session['uid']):
            fail('Bạn chỉ được ghi khoản mình ứng tiền.', 403)
        amount = integer(p.get('amount'))
        day = parsed_date(p.get('date'))
        if day > today():
            fail('Không thể ghi giao dịch tương lai.')
        priority = p.get('priority', 'necessary')
        if priority not in PRIORITIES:
            fail('Mức ưu tiên không hợp lệ.')
        e = GroupEntry(group_id=gid, actor_id=session['uid'], payer_id=payer, kind=kind,
            amount=amount, note=string(p, 'note', 500, True), priority=priority, transaction_date=day)
        if kind == 'fund_expense' and group_accounting(gid)[4] < amount:
            fail('Quỹ nhóm không đủ tiền.')
        if kind == 'settlement':
            receiver = integer(p.get('receiver_id'), 'Người nhận')
            balances = group_accounting(gid)[1]
            if receiver not in people or payer == receiver or balances[payer] >= 0 or balances[receiver] <= 0:
                fail('Người trả phải đang nợ, người nhận phải đang được nhận tiền.')
            if amount > min(-balances[payer], balances[receiver]):
                fail('Số tiền vượt dư nợ hiện tại.')
            e.receiver_id = receiver
        db.session.add(e)
        db.session.flush()
        if kind in ('split', 'fund_expense'):
            participants = p.get('participants', people)
            if not isinstance(participants, list) or not participants or any(type(x) is not int or x not in people for x in participants) or len(set(participants)) != len(participants):
                fail('Danh sách thành viên chia tiền không hợp lệ.')
            participants = sorted(participants)
            quotient, remainder = divmod(amount, len(participants))
            for index, uid in enumerate(participants):
                db.session.add(Share(entry_id=e.id, user_id=uid, amount=quotient + (1 if index < remainder else 0)))
        audit('group.entry.create', {'id': e.id, 'kind': kind, 'amount': amount, 'payer_id': payer, 'note': e.note}, gid)
        return {'ok': True, 'id': e.id}

    @app.post('/api/groups/<int:gid>/entries/<int:eid>/void')
    @mutation
    def void_group_entry(gid, eid):
        group_access(gid, admin=True, lock=True)
        e = db.session.get(GroupEntry, eid)
        if not e or e.group_id != gid or e.voided:
            fail('Giao dịch không tồn tại hoặc đã hủy.', 404)
        reason = string(data(), 'reason', 300)
        e.voided = True
        db.session.flush()
        if group_accounting(gid)[4] < 0:
            fail('Không thể hủy khoản nộp đã được chi. Hãy hủy khoản chi liên quan trước.')
        # Settlements are actual payments. Reversal can create new net debts, kept visible.
        audit('group.entry.void', {'id': eid, 'amount': e.amount, 'kind': e.kind, 'reason': reason}, gid)

    @app.post('/api/groups/<int:gid>/entries/<int:eid>/receipt')
    @mutation
    def upload_receipt(gid, eid):
        _, member = group_access(gid, lock=True)
        e = db.session.get(GroupEntry, eid)
        if not e or e.group_id != gid or e.voided:
            fail('Không tìm thấy giao dịch.', 404)
        if member.role != 'admin' and e.actor_id != session['uid']:
            fail('Bạn không được thêm hóa đơn cho giao dịch này.', 403)
        if e.receipt_name:
            fail('Hóa đơn đã được lưu. Không thể ghi đè chứng từ.')
        f = request.files.get('receipt')
        if not f:
            fail('Chưa chọn hóa đơn.')
        limit = app.config['RECEIPT_MAX_MB'] * 1024 * 1024
        raw = f.read(limit + 1)
        if len(raw) > limit:
            fail(f"Hóa đơn tối đa {app.config['RECEIPT_MAX_MB']} MB.")
        if raw.startswith(b'\x89PNG\r\n\x1a\n'):
            ext, mime = 'png', 'image/png'
        elif raw.startswith(b'\xff\xd8\xff'):
            ext, mime = 'jpg', 'image/jpeg'
        elif raw.startswith(b'%PDF-'):
            ext, mime = 'pdf', 'application/pdf'
        else:
            fail('Chỉ chấp nhận hóa đơn PNG, JPEG hoặc PDF hợp lệ.')
        e.receipt_name, e.receipt_mime, e.receipt_data = f'hoa-don-{eid}.{ext}', mime, raw
        audit('group.receipt.add', {'entry_id': eid, 'sha256': hashlib.sha256(raw).hexdigest()}, gid)

    @app.get('/api/groups/<int:gid>/entries/<int:eid>/receipt')
    @login_required
    def download_receipt(gid, eid):
        group_access(gid)
        e = db.session.get(GroupEntry, eid)
        if not e or e.group_id != gid or not e.receipt_data:
            abort(404)
        return send_file(io.BytesIO(e.receipt_data), mimetype=e.receipt_mime, as_attachment=True, download_name=e.receipt_name)

    @app.cli.command('init-db')
    def init_db():
        db.create_all()
        click.echo('Đã tạo các bảng. Tài khoản mới sẽ bắt đầu với số dư 0.')

    return app


app = create_app()

if __name__ == '__main__':
    from waitress import serve
    with app.app_context():
        db.create_all()
    print('Ví Uni: http://127.0.0.1:5000 (Ctrl+C để dừng)')
    serve(app, host=os.environ.get('HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '5000')))
