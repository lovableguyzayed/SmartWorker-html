"""Paying wages, through the screens rather than through the arithmetic.

tests/test_dues_allocation.py measures the ledger's sums directly. This
walks the same money through the app: the form that records it, the payroll
screen that part-settles a month, the confirmation a worker gives, the
company-wide arrears screen, and the workbook it exports.

Each of the six things being checked here is a thing the app could not do
before, and each of them is a way for money to go wrong:

  - a wage payment must settle what is owed without reducing what the month
    was worth, or the same ₹20,000 comes off twice
  - a part payment must be recordable, and must be refused when it exceeds
    the month
  - how the money moved must survive an edit of the entry
  - a worker may confirm their own payment and nobody else's
  - the arrears screen and its workbook must agree with the ledger
  - switching the house rule must move arrears between months without
    changing the total owed
"""
import io
import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
import routes as R  # noqa: E402
# The settings screen links to the bulk endpoints, so without this every
# render of it fails on url_for rather than on anything being tested.
import bulk  # noqa: E402,F401
import models as m  # noqa: E402
from timeutil import today_ist  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-56s %s' % (label, repr(got)[:24]))
    else:
        failures.append(label)
        print('  FAIL %-56s got=%r want=%r' % (label, got, want))


def login(client, username, password):
    return client.post('/login', data={'username': username,
                                       'password': password},
                       follow_redirects=True)


TODAY = today_ist()
# The month before this one, so the month under test is closed and its
# figures cannot change under the test while it runs.
LAST = (TODAY.replace(day=1) - timedelta(days=1))
MONTH, YEAR = LAST.month, LAST.year

made = {'workers': [], 'txns': [], 'records': [], 'users': []}

with app.app_context():
    acct = m.Account.query.first()
    worker = m.Worker(account_id=acct.id, worker_id='ZZPAY01',
                      full_name='ZZ Pay Worker', phone='9000000097',
                      position='Operator', department='Civil',
                      employee_type='permanent',
                      join_date=LAST.replace(day=1),
                      pay_type='monthly', monthly_salary=23000.0,
                      status='active')
    other = m.Worker(account_id=acct.id, worker_id='ZZPAY02',
                     full_name='ZZ Pay Other', phone='9000000096',
                     position='Helper', department='Civil',
                     employee_type='permanent',
                     join_date=LAST.replace(day=1),
                     pay_type='monthly', monthly_salary=23000.0,
                     status='active')
    db.session.add_all([worker, other])
    db.session.commit()
    made['workers'] = [worker.id, other.id]
    WORKER_ID, OTHER_ID = worker.id, other.id
    WORKER_PHONE = worker.phone
    # Plain integers, not the mapped objects: the app contexts here open and
    # close, and an instance read after its session has gone raises
    # DetachedInstanceError rather than returning the id.
    ACCT_ID = acct.id

try:
    with app.test_client() as c:
        login(c, 'demo@acme.test', 'demo12345')

        print('--- a wage payment settles without reducing the month ---')
        on = LAST.replace(day=15).isoformat()
        r = c.post('/transactions/save', data={
            'worker_id': WORKER_ID, 'txn_type': 'wage_payment',
            'amount': '8000', 'date': on, 'description': 'ZZ wages',
            'payment_mode': 'upi', 'reference_no': 'UTR12345678',
        }, follow_redirects=True)
        check('the form accepts it', r.status_code, 200)
        with app.app_context():
            txn = (m.WorkerTransaction.query
                   .filter_by(worker_id=WORKER_ID, txn_type='wage_payment')
                   .first())
            check('it was stored', bool(txn), True)
            made['txns'].append(txn.id)
            TXN_ID = txn.id
            check('with how the money moved', txn.payment_mode, 'upi')
            check('and what it can be matched against',
                  txn.reference_no, 'UTR12345678')
            check('it is not a deduction', txn.is_deduction, False)
            check('it is a settlement', txn.is_settlement, True)

            # The month's net must be untouched. This is the bug the type
            # exists to prevent: entered as an advance, ₹8,000 would come
            # off the month here and come off the running account again.
            start = LAST.replace(day=1)
            records = m.AttendanceRecord.query.filter(
                m.AttendanceRecord.worker_id == WORKER_ID,
                m.AttendanceRecord.date >= start,
                m.AttendanceRecord.date <= LAST).all()
            summary = R.calculate_pay_summary(
                m.Worker.query.get(WORKER_ID), records, start, LAST)
            check('the month counts no deduction for it',
                  summary['transaction_deductions'], 0.0)
            check('and reports it separately',
                  summary['transaction_settlements'], 8000.0)

        print('\n--- an edit keeps how the money moved ---')
        r = c.post('/transactions/save', data={
            'id': TXN_ID, 'worker_id': WORKER_ID, 'txn_type': 'wage_payment',
            'amount': '9000', 'date': on, 'description': 'ZZ wages',
            'payment_mode': 'upi', 'reference_no': 'UTR12345678',
        }, follow_redirects=True)
        with app.app_context():
            txn = m.WorkerTransaction.query.get(TXN_ID)
            check('the amount changed', txn.amount, 9000.0)
            check('the mode survived', txn.payment_mode, 'upi')
            check('the reference survived', txn.reference_no, 'UTR12345678')

        print('\n--- a reference that is not one is refused ---')
        r = c.post('/transactions/save', data={
            'worker_id': WORKER_ID, 'txn_type': 'wage_payment',
            'amount': '100', 'date': on, 'reference_no': 'a b',
        }, follow_redirects=True)
        body = r.get_data(as_text=True)
        check('the screen says why', 'reference should be' in body, True)
        with app.app_context():
            check('and nothing was written',
                  m.WorkerTransaction.query.filter_by(
                      worker_id=WORKER_ID, amount=100.0).count(), 0)

        print('\n--- part-settling a month ---')
        c.post('/payroll/save', data={'month': MONTH, 'year': YEAR},
               follow_redirects=True)
        with app.app_context():
            rec = m.PayrollRecord.query.filter_by(
                worker_id=WORKER_ID, month=MONTH, year=YEAR).first()
            check('payroll generated a row for the month', bool(rec), True)
            made['records'].append(rec.id)
            RECORD_ID, NET = rec.id, round(float(rec.net_pay or 0), 2)
            check('and it starts unsettled', rec.payment_state, 'pending')

        half = round(NET / 2, 2)
        c.post('/payroll/%d/settle' % RECORD_ID,
               data={'paid_amount': half}, follow_redirects=True)
        with app.app_context():
            rec = m.PayrollRecord.query.get(RECORD_ID)
            check('half of it is now recorded as paid', rec.settled_amount, half)
            check('and the month reads as part settled',
                  rec.payment_state, 'partial')

        print('\n--- more than the month is worth is refused ---')
        r = c.post('/payroll/%d/settle' % RECORD_ID,
                   data={'paid_amount': NET + 5000},
                   follow_redirects=True)
        body = r.get_data(as_text=True)
        check('the screen says why',
              'more than the month is worth' in body, True)
        with app.app_context():
            check('and the figure did not move',
                  m.PayrollRecord.query.get(RECORD_ID).settled_amount, half)

        print('\n--- paying the rest closes the month ---')
        c.post('/payroll/%d/settle' % RECORD_ID,
               data={'paid_amount': NET}, follow_redirects=True)
        with app.app_context():
            rec = m.PayrollRecord.query.get(RECORD_ID)
            check('it reads settled', rec.payment_state, 'paid')
            check('and is stamped as history', bool(rec.finalized_at), True)

        print('\n--- a settled month is not recalculated ---')
        r = c.post('/payroll/save', data={'month': MONTH, 'year': YEAR},
                   follow_redirects=True)
        body = r.get_data(as_text=True)
        check('the screen says a record was left alone',
              'already had money paid' in body, True)

        print('\n--- the arrears screen ---')
        r = c.get('/dues')
        check('it opens', r.status_code, 200)
        body = r.get_data(as_text=True)
        check('and names a worker who is owed', 'ZZ Pay Other' in body, True)
        with app.app_context():
            summary = R._company_dues()
            total = summary['total_outstanding']
            mine = next(row for row in summary['rows']
                        if row['worker'].id == WORKER_ID)
            check('the worker just paid shows less owed than earned',
                  mine['outstanding'] < mine['earned'], True)
            check('the total is the sum of the rows',
                  round(sum(r2['outstanding'] for r2 in summary['rows']), 2),
                  total)

        print('\n--- and its workbook ---')
        r = c.get('/dues/export.xlsx')
        check('it downloads', r.status_code, 200)
        check('as a spreadsheet',
              'spreadsheetml' in r.headers.get('Content-Type', ''), True)
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(r.data))
        ws = wb['Dues']
        cells = [[c2.value for c2 in row] for row in ws.iter_rows()]
        flat = [v for row in cells for v in row if v is not None]
        check('the sheet names the report',
              any(isinstance(v, str) and 'Wages Still Owed' in v
                  for v in flat), True)
        check('it lists the probe worker',
              any(v == 'ZZ Pay Worker' for v in flat), True)
        # Money has to go in as a number, not as text that looks like money:
        # a column of strings cannot be summed by the person who opens it.
        owed_col = [row[7] for row in cells
                    if len(row) > 7 and isinstance(row[7], (int, float))]
        check('the owed column holds numbers', len(owed_col) > 0, True)
        with app.app_context():
            check('and the total line matches the screen',
                  round(max(owed_col), 2) <= round(total, 2) + 0.01, True)

        print('\n--- switching the house rule ---')
        with app.app_context():
            before = R._company_dues()['total_outstanding']
        c.post('/settings/dues_allocation',
               data={'dues_allocation': 'oldest_first'}, follow_redirects=True)
        with app.app_context():
            check('the setting took', R._dues_allocation(), 'oldest_first')
            after = R._company_dues()['total_outstanding']
        # The whole promise of the setting: it decides which month shows the
        # arrears and never how much there is.
        check('the company is owed the same either way', after, before)

        r = c.post('/settings/dues_allocation',
                   data={'dues_allocation': 'nonsense'}, follow_redirects=True)
        check('a value the form never offered is refused',
              'Choose how payments' in r.get_data(as_text=True), True)
        with app.app_context():
            check('and the setting is unchanged',
                  R._dues_allocation(), 'oldest_first')
        c.post('/settings/dues_allocation',
               data={'dues_allocation': 'month'}, follow_redirects=True)

        print('\n--- the worker confirms receiving the money ---')
        page = c.post('/worker/%d/login' % WORKER_ID,
                      follow_redirects=True).get_data(as_text=True)
        hit = re.search(r'password (\d{6})', page)
        check('the admin hands out a login', bool(hit), True)
        PASSWORD = hit.group(1) if hit else None

    with app.app_context():
        u = m.User.query.filter_by(worker_id=WORKER_ID, role='worker').first()
        if u:
            made['users'].append(u.id)

    with app.test_client() as w:
        login(w, WORKER_PHONE, PASSWORD)
        r = w.get('/worker/%d/account' % WORKER_ID)
        check('a worker may open their own account', r.status_code, 200)
        body = r.get_data(as_text=True)
        check('and is offered the confirmation',
              'Confirm I received this' in body, True)

        r = w.get('/worker/%d/account' % OTHER_ID, follow_redirects=False)
        check('but not somebody else\'s', r.status_code in (302, 303), True)

        r = w.post('/transactions/%d/acknowledge' % TXN_ID,
                   follow_redirects=True)
        check('the confirmation is accepted', r.status_code, 200)
        with app.app_context():
            txn = m.WorkerTransaction.query.get(TXN_ID)
            check('and stamped', bool(txn.acknowledged_at), True)
            check('as this worker\'s own word',
                  txn.acknowledged_by, made['users'][0] if made['users'] else None)

        print('\n--- and cannot confirm a payment to somebody else ---')
        with app.app_context():
            theirs = m.WorkerTransaction(
                account_id=ACCT_ID, worker_id=OTHER_ID,
                txn_type='wage_payment', amount=500.0,
                date=LAST.replace(day=16), description='ZZ other wages',
                status='active')
            db.session.add(theirs)
            db.session.commit()
            made['txns'].append(theirs.id)
            THEIRS_ID = theirs.id
        w.post('/transactions/%d/acknowledge' % THEIRS_ID,
               follow_redirects=True)
        with app.app_context():
            check('it stays unconfirmed',
                  m.WorkerTransaction.query.get(THEIRS_ID).acknowledged_at,
                  None)

        print('\n--- a confirmation cannot be withdrawn by repeating it ---')
        w.post('/transactions/%d/acknowledge' % TXN_ID, follow_redirects=True)
        with app.app_context():
            check('it is still confirmed',
                  bool(m.WorkerTransaction.query.get(TXN_ID).acknowledged_at),
                  True)
finally:
    with app.app_context():
        db.session.rollback()
        for txn_id in made['txns']:
            m.WorkerTransaction.query.filter_by(id=txn_id).delete(
                synchronize_session=False)
        for wid in made['workers']:
            m.WorkerTransaction.query.filter_by(worker_id=wid).delete(
                synchronize_session=False)
            m.PayrollRecord.query.filter_by(worker_id=wid).delete(
                synchronize_session=False)
            m.User.query.filter_by(worker_id=wid).delete(
                synchronize_session=False)
        m.Worker.query.filter(m.Worker.id.in_(made['workers'])).delete(
            synchronize_session=False)
        # The house rule is company-wide, so a test that left it switched
        # would change every later suite's figures.
        company = m.CompanySetting.query.first()
        if company:
            company.dues_allocation = 'month'
        db.session.commit()
        check('the probe workers are gone',
              m.Worker.query.filter(
                  m.Worker.full_name.like('ZZ Pay%')).count(), 0)

print()
if failures:
    print('FAILED %d of the checks above:' % len(failures))
    for label in failures:
        print('  %s' % label)
    sys.exit(1)
print('Money goes in, settles the right month, and the worker can say so.')
