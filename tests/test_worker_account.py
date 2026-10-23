"""An unpaid month has to still be visible months later.

Payroll answers "what is this month worth". On a site where wages are
drawn in pieces and settled when there is cash, the question actually
asked is "how much is still mine", and no monthly screen can answer it
once a month has closed without being paid — each month was computed in
isolation, so an August that was never paid appeared nowhere in October.

The arithmetic under test, per month:

    closing = opening + earned - drawn - settled

A month marked Paid must therefore move the balance by exactly zero:
settling a month should leave nothing behind. A month left pending must
carry whatever was not drawn into the next one.
"""
import calendar
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import app, db
import models as m
import ledger

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-48s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


# A stand-in for the payroll calculation, so the ledger's own arithmetic is
# what is being measured rather than the salary engine's.
FLAT = 10000.0


def flat_month(worker, year, month, records):
    return FLAT, 0.0, FLAT


made = []
with app.app_context():
    acct = m.Account.query.first()
    w = m.Worker(account_id=acct.id, worker_id='ZZLEDG1',
                 full_name='ZZ Ledger Worker', phone='9000000099',
                 position='Helper', department='Civil',
                 employee_type='permanent', join_date=date(2026, 8, 1),
                 pay_type='monthly', monthly_salary=FLAT, status='active')
    db.session.add(w)
    db.session.commit()
    made.append(w.id)
    try:
        print('--- three months, nothing paid, nothing drawn ---')
        st = ledger.build(w, upto=date(2026, 10, 31), compute_month=flat_month)
        check('one row per month', len(st['rows']), 3)
        check('earned', st['earned'], 30000.0)
        check('august carries forward', st['rows'][0]['closing'], 10000.0)
        check('september adds to it', st['rows'][1]['closing'], 20000.0)
        check('october too', st['rows'][2]['closing'], 30000.0)
        check('september opens where august closed',
              st['rows'][1]['opening'], st['rows'][0]['closing'])
        check('still owed', st['outstanding'], 30000.0)

        print('\n--- an advance drawn in September ---')
        t = m.WorkerTransaction(account_id=acct.id, worker_id=w.id,
                                txn_type='advance', amount=4000.0,
                                date=date(2026, 9, 15),
                                description='ZZ ledger advance',
                                status='active')
        db.session.add(t)
        db.session.commit()
        st = ledger.build(w, upto=date(2026, 10, 31), compute_month=flat_month)
        check('september shows it', st['rows'][1]['drawn'], 4000.0)
        check('and it is listed by name', len(st['rows'][1]['draws']), 1)
        check('september carries 6000 less', st['rows'][1]['closing'], 16000.0)
        check('october inherits that', st['rows'][2]['opening'], 16000.0)
        check('still owed drops by the advance', st['outstanding'], 26000.0)
        check('august is untouched', st['rows'][0]['closing'], 10000.0)

        print('\n--- a bonus must not be counted as money drawn ---')
        b = m.WorkerTransaction(account_id=acct.id, worker_id=w.id,
                                txn_type='bonus', amount=1500.0,
                                date=date(2026, 9, 20),
                                description='ZZ ledger bonus', status='active')
        db.session.add(b)
        db.session.commit()
        st = ledger.build(w, upto=date(2026, 10, 31), compute_month=flat_month)
        # The bonus belongs inside the month's gross, which the real payroll
        # already adds. Counting it here too would pay it twice.
        check('drawn is still only the advance', st['rows'][1]['drawn'], 4000.0)

        print('\n--- settling August must leave nothing behind ---')
        # total_days/present_days are NOT NULL on this table.
        rec = m.PayrollRecord(account_id=acct.id, worker_id=w.id,
                              month=8, year=2026, total_days=31,
                              present_days=26, gross_pay=FLAT,
                              deductions=0.0, net_pay=FLAT, status='paid')
        db.session.add(rec)
        db.session.commit()
        st = ledger.build(w, upto=date(2026, 10, 31), compute_month=flat_month)
        check('august is marked settled', st['rows'][0]['paid'], True)
        check('and closes at zero', st['rows'][0]['closing'], 0.0)
        check('september now opens at zero', st['rows'][1]['opening'], 0.0)
        check('still owed drops by the month settled',
              st['outstanding'], 16000.0)

        print('\n--- a cancelled draw does not count ---')
        t.status = 'cancelled'
        db.session.commit()
        st = ledger.build(w, upto=date(2026, 10, 31), compute_month=flat_month)
        check('september drawn is back to zero', st['rows'][1]['drawn'], 0.0)
        check('still owed goes back up', st['outstanding'], 20000.0)

        print('\n--- nothing before joining ---')
        st = ledger.build(w, upto=date(2026, 7, 31), compute_month=flat_month)
        check('a date before joining gives no rows', st['rows'], [])
        check('and owes nothing', st['outstanding'], 0.0)
    finally:
        # A failed flush leaves the session needing a rollback before any
        # further query, so cleanup cannot run without this.
        db.session.rollback()
        wid = made[0]
        m.WorkerTransaction.query.filter_by(worker_id=wid).delete(
            synchronize_session=False)
        m.PayrollRecord.query.filter_by(worker_id=wid).delete(
            synchronize_session=False)
        m.Worker.query.filter(m.Worker.id.in_(made)).delete(
            synchronize_session=False)
        db.session.commit()
        left = m.Worker.query.filter(
            m.Worker.full_name.like('ZZ Ledger%')).count()
        check('the probe worker is gone', left, 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The account carries forward correctly.')
