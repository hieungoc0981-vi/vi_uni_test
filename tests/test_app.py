"""Integration tests. TEST_DATABASE_URL must point to a disposable *_test database."""
import io
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import (create_app, db, User, Transaction, SavingEntry, Goal,
                  GroupEntry, Share, RequestKey, Audit, today)


@pytest.fixture
def app(tmp_path):
    uri = os.environ.get('TEST_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    if uri.startswith('mysql'):
        assert uri.split('?')[0].endswith('_test'), 'Use a disposable database whose name ends in _test.'
    app = create_app({'TESTING': True, 'SECRET_KEY': 'integration-tests-only', 'SQLALCHEMY_DATABASE_URI': uri})
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


class Client:
    def __init__(self, app, name='An', email=None):
        self.app = app
        self.c = app.test_client()
        self.csrf = self.c.get('/api/auth').json['csrf']
        self.email = email or f'{uuid.uuid4().hex}@example.com'
        response = self.c.post('/api/register', json={'name': name, 'email': self.email, 'password': 'password123'}, headers={'X-CSRF-Token': self.csrf})
        assert response.status_code == 200, response.json
        self.csrf = response.json['csrf']
        self.uid = response.json['user']['id']

    def get(self, path):
        return self.c.get('/api' + path)

    def write(self, path, payload=None, method='POST', key=None):
        return self.c.open('/api' + path, method=method, json=payload,
            headers={'X-CSRF-Token': self.csrf, 'Idempotency-Key': key or uuid.uuid4().hex})

    def state(self):
        r = self.get('/state')
        assert r.status_code == 200, r.json
        return r.json

    def tx(self, amount, kind='income', **kwargs):
        s = self.state()
        payload = {'amount': amount, 'type': kind, 'wallet_id': s['wallets'][0]['id'],
            'category_id': next(c['id'] for c in s['categories'] if c['type'] == kind),
            'date': today().isoformat(), 'priority': 'necessary', 'note': 'Giao dịch kiểm thử'}
        payload.update(kwargs)
        return self.write('/transactions', payload)

    def group(self):
        r = self.write('/groups', {'name': 'Phòng 302'})
        assert r.status_code == 200, r.json
        gid = r.json['id']
        return gid, self.get(f'/groups/{gid}').json['code']

    def entry(self, gid, kind, amount, **extra):
        return self.write(f'/groups/{gid}/entries', {'kind': kind, 'amount': amount,
            'payer_id': self.uid, 'date': today().isoformat(), 'note': 'Bữa tối', **extra})


def test_empty_new_account_and_password(app):
    a = Client(app)
    state = a.state()
    assert state['balance'] == state['income'] == state['expense'] == state['saved'] == 0
    assert state['recent'] == state['goals'] == state['groups'] == []
    assert len(state['categories']) == 10
    with app.app_context():
        u = db.session.get(User, a.uid)
        assert u.password_hash != 'password123'
        assert check_password_hash(u.password_hash, 'password123')


def test_persistence_after_restart_and_login(app):
    a = Client(app)
    assert a.tx(2500000).status_code == 200
    a.write('/logout')
    assert a.get('/state').status_code == 401
    restarted = create_app({'TESTING': True, 'SECRET_KEY': 'integration-tests-only', 'SQLALCHEMY_DATABASE_URI': app.config['SQLALCHEMY_DATABASE_URI']})
    c = restarted.test_client()
    token = c.get('/api/auth').json['csrf']
    r = c.post('/api/login', json={'email': a.email, 'password': 'password123'}, headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    assert c.get('/api/state').json['balance'] == 2500000


def test_csrf_and_login_throttle(app):
    a = Client(app)
    assert a.c.post('/api/wallets', json={'name': 'Bad'}).status_code == 403
    a.write('/logout')
    a.csrf = a.get('/auth').json['csrf']
    for _ in range(8):
        assert a.write('/login', {'email': a.email, 'password': 'wrongpass'}).status_code == 401
    assert a.write('/login', {'email': a.email, 'password': 'password123'}).status_code == 429


def test_user_isolation(app):
    a, b = Client(app), Client(app)
    tid = a.tx(1000000).json['id']
    state = a.state()
    assert b.state()['balance'] == 0
    assert b.write(f'/transactions/{tid}', method='DELETE').status_code == 404
    assert b.write('/transactions', {'type': 'income', 'amount': 10,
        'wallet_id': state['wallets'][0]['id'], 'category_id': state['categories'][0]['id']}).status_code == 404
    assert b.write('/wallets/'+str(state['wallets'][0]['id']), {'name': 'Hack'}, method='PATCH').status_code == 404
    gid, _ = a.group()
    assert b.get(f'/groups/{gid}').status_code == 404
    assert b.entry(gid, 'split', 1000).status_code == 404


def test_income_expense_edit_delete_and_reports(app):
    a = Client(app)
    assert a.tx(5000000).status_code == 200
    expense = a.tx(45000, 'expense', note='Bữa trưa')
    assert expense.status_code == 200
    tid = expense.json['id']
    original = next(t for t in a.get('/transactions').json['items'] if t['id'] == tid)
    assert a.write('/transactions/'+str(tid), {**original, 'amount': 70000}, method='PATCH').status_code == 200
    assert a.state()['balance'] == 4930000
    assert a.get('/transactions?q=trưa').json['total'] == 1
    assert a.get('/transactions?type=expense').json['total'] == 1
    report = a.get('/reports').json
    assert (report['income'], report['expense'], report['net']) == (5000000, 70000, 4930000)
    assert a.write('/transactions/'+str(tid), method='DELETE').status_code == 200
    assert a.state()['balance'] == 5000000
    assert a.get('/reports').json['expense'] == 0


def test_idempotency_and_conflicting_payload(app):
    a = Client(app)
    key = uuid.uuid4().hex
    one = a.tx(100000)
    assert one.status_code == 200
    p = {'name': 'Ngân hàng', 'initial_balance': 1000}
    assert a.write('/wallets', p, key=key).status_code == 200
    assert a.write('/wallets', p, key=key).status_code == 200
    assert len(a.state()['wallets']) == 2
    assert a.write('/wallets', {**p, 'initial_balance': 2000}, key=key).status_code == 409


@pytest.mark.parametrize('amount', [0, -1, 0.5, True, '1e6', '45000.0', 10**12+1])
def test_invalid_money_is_rejected(app, amount):
    a = Client(app)
    assert a.tx(amount).status_code == 400
    assert a.state()['balance'] == 0


def test_atomic_rollback_no_overspend(app):
    a = Client(app)
    a.tx(100000)
    assert a.tx(100001, 'expense').status_code == 400
    with app.app_context():
        assert Transaction.query.count() == 1
    assert a.state()['balance'] == 100000
    assert a.tx(100000, date=(today()+timedelta(days=1)).isoformat()).status_code == 400


def make_goal(a, name='Laptop'):
    assert a.write('/goals', {'name': name, 'target': 10000000, 'deadline': (today()+timedelta(days=100)).isoformat(), 'auto_percent': 10}).status_code == 200
    return a.state()['goals'][-1]['id']


def test_saving_allocation_reversal_and_no_double_expense(app):
    a = Client(app)
    gid = make_goal(a)
    r = a.tx(1000000, allocations=[{'goal_id': gid, 'amount': 100000}])
    assert r.status_code == 200
    s = a.state()
    assert (s['balance'], s['saved'], s['income'], s['expense']) == (900000, 100000, 1000000, 0)
    assert a.write('/transactions/'+str(r.json['id']), method='DELETE').status_code == 200
    assert a.state()['balance'] == a.state()['saved'] == 0


def test_allocation_validation_and_spent_savings_cannot_reverse(app):
    a, b = Client(app), Client(app)
    gid, other = make_goal(a), make_goal(b)
    assert a.tx(100, allocations=[{'goal_id': other, 'amount': 10}]).status_code == 404
    assert a.tx(100, allocations=[{'goal_id': gid, 'amount': 101}]).status_code == 400
    assert a.tx(100, allocations=[{'goal_id': gid, 'amount': 5}, {'goal_id': gid, 'amount': 5}]).status_code == 400
    income = a.tx(1000, allocations=[{'goal_id': gid, 'amount': 100}])
    assert income.status_code == 200
    wid = a.state()['wallets'][0]['id']
    assert a.write(f'/goals/{gid}/transfer', {'wallet_id': wid, 'amount': 100, 'direction': 'withdraw'}).status_code == 200
    assert a.write('/transactions/'+str(income.json['id']), method='DELETE').status_code == 400
    assert a.state()['income'] == 1000


def test_archive_empty_goal_preserves_transfers_between_wallets(app):
    a = Client(app)
    a.tx(1000)
    a.write('/wallets', {'name': 'Ngân hàng', 'initial_balance': 0})
    gid = make_goal(a)
    w1, w2 = [w['id'] for w in a.state()['wallets']]
    assert a.write(f'/goals/{gid}/transfer', {'wallet_id': w1, 'amount': 600, 'direction': 'deposit'}).status_code == 200
    assert a.write(f'/goals/{gid}', method='DELETE').status_code == 400
    assert a.write(f'/goals/{gid}/transfer', {'wallet_id': w2, 'amount': 600, 'direction': 'withdraw'}).status_code == 200
    assert a.write(f'/goals/{gid}', method='DELETE').status_code == 200
    assert [w['balance'] for w in a.state()['wallets']] == [400, 600]
    assert a.state()['goals'] == []
    assert a.write(f'/goals/{gid}/transfer', {'wallet_id': w1, 'amount': 1, 'direction': 'deposit'}).status_code == 400


def test_budget_warning_updates_and_overlap(app):
    a = Client(app)
    a.tx(10000)
    p = {'limit': 1000, 'start': today().isoformat(), 'end': today().isoformat(), 'threshold': 80}
    assert a.write('/budgets', p).status_code == 200
    assert a.write('/budgets', p).status_code == 400
    r = a.tx(800, 'expense')
    assert r.status_code == 200 and r.json['warnings'][0]['percent'] == 80
    a.tx(201, 'expense')
    assert a.state()['warnings'][0]['remaining'] == -1
    budget = a.state()['budgets'][0]
    assert a.write('/budgets/'+str(budget['id']), {**p, 'alerts_enabled': False}, method='PATCH').status_code == 200
    assert a.state()['warnings'] == []
    assert a.write('/transactions/'+str(r.json['id']), method='DELETE').status_code == 200
    assert a.state()['budgets'][0]['spent'] == 201


def three_members(app):
    a, b, c = Client(app, 'An'), Client(app, 'Bình'), Client(app, 'Chi')
    gid, code = a.group()
    assert b.write('/groups/join', {'code': code}).status_code == 200
    assert c.write('/groups/join', {'code': code}).status_code == 200
    return a, b, c, gid


def test_group_exact_split_and_net_debt_settlement(app):
    a, b, c, gid = three_members(app)
    assert a.entry(gid, 'split', 10001).status_code == 200
    g = a.get(f'/groups/{gid}').json
    assert sorted(s['amount'] for s in g['entries'][0]['shares']) == [3333, 3334, 3334]
    assert sum(s['amount'] for s in g['entries'][0]['shares']) == 10001
    assert sum(m['balance'] for m in g['members']) == 0
    assert g['cash'] == 0 and g['expense'] == 10001
    for plan in g['settlements']:
        assert a.entry(gid, 'settlement', plan['amount'], payer_id=plan['from'], receiver_id=plan['to']).status_code == 200
    assert a.get(f'/groups/{gid}').json['settlements'] == []


def test_group_permissions_and_fund_is_separate_from_debts(app):
    a, b, c, gid = three_members(app)
    assert b.entry(gid, 'contribution', 100).status_code == 403
    assert b.entry(gid, 'fund_expense', 100).status_code == 403
    assert b.entry(gid, 'split', 100, payer_id=a.uid).status_code == 403
    assert b.entry(gid, 'split', 100).status_code == 200
    assert a.entry(gid, 'contribution', 1000).status_code == 200
    assert a.entry(gid, 'fund_expense', 1001).status_code == 400
    assert a.entry(gid, 'fund_expense', 600).status_code == 200
    g = a.get(f'/groups/{gid}').json
    assert g['cash'] == 400 and g['expense'] == 700
    assert a.state()['balance'] == 0  # group books never silently debit a personal wallet
    assert sum(m['contribution'] for m in g['members']) == 1000
    assert sum(m['balance'] for m in g['members']) == 0


def test_group_void_immutable_audit_and_rotate_invitation(app):
    a, b, c, gid = three_members(app)
    contribution = a.entry(gid, 'contribution', 1000).json['id']
    expense = a.entry(gid, 'fund_expense', 500).json['id']
    assert a.write(f'/groups/{gid}/entries/{contribution}/void', {'reason': 'Nhầm'}).status_code == 400
    assert b.write(f'/groups/{gid}/entries/{expense}/void', {'reason': 'Nhầm'}).status_code == 403
    assert a.write(f'/groups/{gid}/entries/{expense}/void', {'reason': 'Ghi sai hóa đơn'}).status_code == 200
    g = a.get(f'/groups/{gid}').json
    assert g['cash'] == 1000 and g['expense'] == 0
    assert len(g['entries']) == 2 and any(e['voided'] for e in g['entries'])
    assert any(x['details'].get('reason') == 'Ghi sai hóa đơn' for x in g['audit'])
    old = g['code']
    assert a.write(f'/groups/{gid}/code').status_code == 200
    outsider = Client(app)
    assert outsider.write('/groups/join', {'code': old}).status_code == 400


def test_receipt_access_signature_and_idempotent_multipart(app):
    a, b, c, gid = three_members(app)
    outsider = Client(app)
    eid = a.entry(gid, 'split', 100).json['id']
    url = f'/api/groups/{gid}/entries/{eid}/receipt'
    key = uuid.uuid4().hex
    headers = {'X-CSRF-Token': a.csrf, 'Idempotency-Key': key}
    for _ in range(2):
        r = a.c.post(url, data={'receipt': (io.BytesIO(b'%PDF-1.4 test receipt'), 'receipt.pdf')}, headers=headers)
        assert r.status_code == 200, r.json
    assert b.c.get(url).status_code == 200
    assert outsider.c.get(url).status_code == 404
    assert b.c.get(url).data == b'%PDF-1.4 test receipt'
    eid2 = a.entry(gid, 'split', 200).json['id']
    r = a.c.post(f'/api/groups/{gid}/entries/{eid2}/receipt', data={'receipt': (io.BytesIO(b'<script>bad</script>'), 'fake.png')},
        headers={'X-CSRF-Token': a.csrf, 'Idempotency-Key': uuid.uuid4().hex})
    assert r.status_code == 400


def test_reports_date_periods_csv_and_literal_search(app):
    a = Client(app)
    a.tx(10000)
    a.tx(100, 'expense', note='=HYPERLINK("bad")')
    a.tx(50, 'expense', note='Khuyến mại 10%')
    assert a.get('/transactions?q=%25').json['total'] == 1
    for period in ('day', 'week', 'month', 'year'):
        r = a.get('/reports?period='+period)
        assert r.status_code == 200
        assert r.json['expense'] == 150
    future = (today()+timedelta(days=1)).isoformat()
    assert a.get('/reports?start='+future).json['count'] == 0
    csv_data = a.get('/export').data.decode('utf-8-sig')
    assert "'=HYPERLINK" in csv_data
    assert a.get('/export').headers['Content-Disposition'].startswith('attachment;')


def test_concurrent_duplicate_and_no_overdraft_mysql(app):
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('mysql'):
        pytest.skip('Row locking/concurrency is guaranteed on MySQL; SQLite is for local trial.')
    a = Client(app)
    a.tx(100)
    s = a.state()
    payload = {'amount': 80, 'type': 'expense', 'wallet_id': s['wallets'][0]['id'],
        'category_id': next(c['id'] for c in s['categories'] if c['type'] == 'expense'), 'date': today().isoformat()}
    cookie = a.c.get_cookie('session').value
    shared_key = uuid.uuid4().hex
    def submit(key):
        c = app.test_client()
        c.set_cookie('session', cookie)
        return c.post('/api/transactions', json=payload, headers={'X-CSRF-Token': a.csrf, 'Idempotency-Key': key})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [shared_key, shared_key]))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json['id'] == results[1].json['id']
    assert a.state()['balance'] == 20
    assert a.tx(100).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [uuid.uuid4().hex, uuid.uuid4().hex]))
    assert sorted(r.status_code for r in results) == [200, 400]
    assert a.state()['balance'] == 40
