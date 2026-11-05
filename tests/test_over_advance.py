"""A peshgi bigger than the month, and the ₹4,000 that used to vanish.

Drawing wages in advance is not an edge case at a stone crusher, it is
how the month works. A man asks for money when he needs it and squares up
when there is cash, so a month where he has already taken more than he
earned is ordinary.

Ten days at ₹800 is ₹8,000. He had drawn ₹12,000. The month's net is
therefore **minus ₹4,000**, and the running account was right about it:

    October   earned 8,000   drawn 12,000   closing -4,000
    November  opening -4,000 earned  8,000  closing  4,000

The ₹4,000 is recovered out of November. That part was always correct.

What was not correct is what one tap did to it. "Mark paid" wrote the
month's net into paid_amount — including when that net was negative — and
the running account reads paid_amount as money handed over:

    closing = opening + earned - drawn - settled

With settled = -4,000 the shortfall is ADDED back, so October closed at
zero and the ₹4,000 the man owed was gone. Measured, before the fix:

    before the tap   October closing  -4,000
    after the tap    October closing       0

Javed loses ₹4,000 per worker who does this, silently, by pressing a
button that looks like the right one. The record also ended up with
status='paid' while the badge computed 'pending' — the two disagreeing,
which is the exact thing payment_state exists to prevent.

The fix is in four places, because the money could get in through any of
them:

  * paid_amount is never written negative, at the route or in bulk;
  * settled_amount clamps at zero, so a row already written that way
    cannot go on corrupting the account;
  * the route refuses to mark such a month paid and says why — the
    shortfall is a debt, and a debt belongs in the account, not on a wage
    badge;
  * the badge says "already drawn" rather than "pending", because
    pending promises a wage that is not coming.

Run from the project root:  python3 tests/test_over_advance.py
"""
import datetime
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

import flask
from flask_login import login_user
from sqlalchemy import text

from app import app, db
import models as m
import routes  # noqa: F401
import bulk    # noqa: F401

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, got))


app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

MARK = 'ZZOverAdv'
state = {}

with app.app_context():
    m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
        synchronize_session=False)
    db.session.commit()
    admin = m.User.query.filter_by(role='admin').first()
    account = admin.account_id

    def make(suffix, phone):
        w = m.Worker(account_id=account, worker_id='ZZOA' + suffix,
                     full_name=MARK + ' ' + suffix, phone=phone,
                     position='Helper', department='Civil',
                     employee_type='permanent',
                     join_date=datetime.date(2026, 10, 1), pay_type='daily',
                     daily_rate=800, status='active')
        db.session.add(w)
        db.session.commit()
        # Ten days in October and ten in November: 8,000 each month.
        for month in (10, 11):
            for day in range(1, 11):
                db.session.add(m.AttendanceRecord(
                    account_id=account, worker_id=w.id,
                    date=datetime.date(2026, month, day), status='present'))
        db.session.commit()
        return w.id

    # One for the single tap, one for the bulk action.
    state['one'] = make('01', '9000000771')
    state['two'] = make('02', '9000000772')

    for wid in (state['one'], state['two']):
        db.session.add(m.WorkerTransaction(
            account_id=account, worker_id=wid, txn_type='advance',
            amount=12000, date=datetime.date(2026, 10, 5),
            description='peshgi', created_by=admin.id))
        row = m.PayrollRecord(
            account_id=account, worker_id=wid, year=2026, month=10,
            total_days=31, present_days=10, overtime_hours=0,
            gross_pay=8000, deductions=0, net_pay=-4000, status='pending')
        db.session.add(row)
        db.session.commit()
        state['pr_' + ('one' if wid == state['one'] else 'two')] = row.id


def closing_for(worker_id, upto):
    """October's closing balance in the worker's running account."""
    with app.app_context():
        with app.test_request_context():
            admin = m.User.query.filter_by(role='admin').first()
            login_user(admin)
            flask.g.account_id = admin.account_id
            statement = routes.worker_ledger(
                db.session.get(m.Worker, worker_id), upto=upto)
            return {(r['year'], r['month']): round(r['closing'], 2)
                    for r in statement['rows']}


try:
    print('--- the arithmetic was always right ---')
    rows = closing_for(state['one'], datetime.date(2026, 11, 30))
    check('October closes at minus the shortfall', rows[(2026, 10)], -4000.0)
    check('November opens there and recovers it', rows[(2026, 11)], 4000.0)

    print('\n--- and the month is not a wage anybody can hand over ---')
    with app.app_context():
        row = db.session.get(m.PayrollRecord, state['pr_one'])
        check('the badge does not promise a wage', row.payment_state, 'drawn')
        check('and nothing is recorded as handed over',
              row.settled_amount, 0.0)

    print('\n--- THE BUG: one tap used to swallow the debt ---')
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})
        page = client.post('/payroll/%d/toggle_paid' % state['pr_one'],
                           follow_redirects=True).get_data(as_text=True)
        check('the employer is told there is nothing to hand over',
              'nothing to hand over' in page, True)
        check('and told it comes off next month',
              'comes off next month' in page, True)

    with app.app_context():
        row = db.session.get(m.PayrollRecord, state['pr_one'])
        check('no negative amount was written',
              row.paid_amount, 0.0)
        check('settled stays zero', row.settled_amount, 0.0)
        check('and the status matches the badge rather than fighting it',
              (row.status, row.payment_state), ('drawn', 'drawn'))

    rows = closing_for(state['one'], datetime.date(2026, 11, 30))
    check('THE DEBT SURVIVES THE TAP', rows[(2026, 10)], -4000.0)
    check('and November still recovers it', rows[(2026, 11)], 4000.0)

    print('\n--- the bulk action does not swallow it either ---')
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})
        # The bulk screen selects workers, not payroll rows.
        got = client.post('/api/bulk/payroll', data={
            'action': 'paid', 'ids': str(state['two']),
            'month': '10', 'year': '2026',
        })
        check('the bulk call answers', got.status_code, 200)
        check('and says nothing was handed over for him',
              'already drawn more than the month was worth'
              in got.get_data(as_text=True), True)
    with app.app_context():
        row = db.session.get(m.PayrollRecord, state['pr_two'])
        check('no negative amount written in bulk either',
              (row.paid_amount or 0.0) <= 0.0, True)
        check('and settled is still zero', row.settled_amount, 0.0)
    rows = closing_for(state['two'], datetime.date(2026, 11, 30))
    check('the debt survives the bulk action too',
          rows[(2026, 10)], -4000.0)

    print('\n--- a positive month is untouched by any of this ---')
    with app.app_context():
        admin = m.User.query.filter_by(role='admin').first()
        good = m.PayrollRecord(
            account_id=admin.account_id, worker_id=state['one'],
            year=2026, month=11, total_days=30, present_days=10,
            overtime_hours=0, gross_pay=8000, deductions=0, net_pay=8000,
            status='pending')
        db.session.add(good)
        db.session.commit()
        state['pr_good'] = good.id
        check('it reads as pending to start with', good.payment_state,
              'pending')
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})
        client.post('/payroll/%d/toggle_paid' % state['pr_good'],
                    follow_redirects=True)
    with app.app_context():
        good = db.session.get(m.PayrollRecord, state['pr_good'])
        check('marking a real wage paid still works', good.paid_amount,
              8000.0)
        check('and reads as paid', good.payment_state, 'paid')

    print('\n--- and a row already written negative cannot hurt the account ---')
    with app.app_context():
        row = db.session.get(m.PayrollRecord, state['pr_two'])
        # Exactly what the old code left behind in a live database.
        db.session.execute(text(
            "update payroll_records set paid_amount = -4000, status = 'paid' "
            'where id = :i'), {'i': row.id})
        db.session.commit()
        row = db.session.get(m.PayrollRecord, row.id)
        check('the clamp reads it as nothing handed over',
              row.settled_amount, 0.0)
    rows = closing_for(state['two'], datetime.date(2026, 11, 30))
    check('so the debt is still there', rows[(2026, 10)], -4000.0)
finally:
    with app.app_context():
        ids = [state[k] for k in ('one', 'two') if k in state]
        for table in ('payroll_records', 'worker_transactions',
                      'attendance_records'):
            for wid in ids:
                db.session.execute(
                    text('delete from %s where worker_id = :i' % table),
                    {'i': wid})
        if ids:
            m.Worker.query.filter(m.Worker.id.in_(ids)).delete(
                synchronize_session=False)
        db.session.commit()
        print('\n--- and this test leaves nothing behind ---')
        check('its workers are gone', db.session.execute(text(
            "select count(*) from workers where full_name like 'ZZOverAdv%'"
        )).scalar(), 0)
        check('and its payroll rows', db.session.execute(text(
            'select count(*) from payroll_records where worker_id in '
            '(select id from workers where full_name like :p)'),
            {'p': MARK + '%'}).scalar(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('A peshgi bigger than the month leaves a debt, not a paid wage.')
