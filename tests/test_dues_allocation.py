"""Where a payment lands, and what half-settling a month looks like.

Three things are measured here, and they are the same question asked three
ways: when money changes hands on a site, which month does it clear?

  1. 'oldest_first' allocation. A crusher owing August that hands over
     ₹20,000 in October is clearing August. Booking that money against
     October instead leaves August looking untouched and October looking
     nearly settled, which is wrong twice over. The company total must not
     move either way — allocation decides where the money sits, never how
     much there is.

  2. A wage payment is not an advance. Settling wages used to have to be
     entered as an 'advance': right to the rupee, wrong word on the
     payslip, and it also came off the month's net pay, so the month looked
     cheaper than it was.

  3. A month can be half settled. status had two values, so ₹10,000 against
     a ₹23,000 September had nowhere to go.

The figures are Javed's own, because that is the case that prompted all
three: joined 7 August, ₹23,000 a month on a 26-day basis, paid only for
days worked in the joining month, and ₹20,000 handed over on 22 October
with nothing else settled.
"""
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
    print('  %-5s %-52s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


# Javed's months, to the rupee: 25 days of a ₹23,000/26 month, then two
# whole months. Fed in directly so the ledger's allocation is what is being
# measured and not the salary engine, which has its own suite.
AUGUST = 22125.0
WHOLE = 23000.0
EARNED = {(2026, 8): AUGUST, (2026, 9): WHOLE, (2026, 10): WHOLE}
TOTAL = AUGUST + WHOLE + WHOLE          # 68,125


def javed_month(worker, year, month, records):
    gross = EARNED.get((year, month), 0.0)
    return gross, 0.0, gross


UPTO = date(2026, 10, 31)
made = []
with app.app_context():
    acct = m.Account.query.first()
    w = m.Worker(account_id=acct.id, worker_id='ZZALLOC1',
                 full_name='ZZ Alloc Worker', phone='9000000098',
                 position='Operator', department='Civil',
                 employee_type='permanent', join_date=date(2026, 8, 7),
                 pay_type='monthly', monthly_salary=WHOLE, status='active')
    db.session.add(w)
    db.session.commit()
    made.append(w.id)

    def rebuild(mode):
        return ledger.build(w, upto=UPTO, compute_month=javed_month,
                            allocation=mode)

    try:
        print('--- nothing paid: three open months ---')
        st = rebuild('month')
        check('owed is every month', st['outstanding'], TOTAL)
        check('oldest open month is August', st['oldest_open'], 'August 2026')
        check('three months open', st['open_months'], 3)

        print('\n--- ₹20,000 on 22 October, booked against its own month ---')
        pay = m.WorkerTransaction(account_id=acct.id, worker_id=w.id,
                                  txn_type='wage_payment', amount=20000.0,
                                  date=date(2026, 10, 22),
                                  description='ZZ alloc wages',
                                  payment_mode='cash', status='active')
        db.session.add(pay)
        db.session.commit()
        st = rebuild('month')
        check('august still owes all of itself',
              st['rows'][0]['closing'], AUGUST)
        check('october carries the payment', st['rows'][2]['settled'], 20000.0)
        check('and it is not called money drawn', st['rows'][2]['drawn'], 0.0)
        check('owed drops by exactly the payment',
              st['outstanding'], TOTAL - 20000.0)

        print('\n--- the same ₹20,000, oldest dues first ---')
        st = rebuild('oldest_first')
        check('it clears August instead', st['rows'][0]['settled'], 20000.0)
        check('august is left with the remainder',
              st['rows'][0]['closing'], round(AUGUST - 20000.0, 2))
        check('october is untouched', st['rows'][2]['settled'], 0.0)
        check('october owes its whole month',
              st['rows'][2]['closing'], TOTAL - 20000.0)
        # The point of the whole exercise: allocation moves money between
        # months and must never create or destroy any.
        check('the company is owed the same either way',
              st['outstanding'], TOTAL - 20000.0)
        check('august says the money came from a later month',
              st['rows'][0]['draws'][0]['carried'], True)
        check('and names the month it came from',
              st['rows'][0]['draws'][0]['month'], (2026, 10))

        print('\n--- a payment bigger than the oldest month spills forward ---')
        pay.amount = 30000.0
        db.session.commit()
        st = rebuild('oldest_first')
        check('august is cleared', st['rows'][0]['closing'], 0.0)
        check('august took only what it was owed',
              st['rows'][0]['settled'], AUGUST)
        check('september took the rest',
              st['rows'][1]['settled'], round(30000.0 - AUGUST, 2))
        check('september still owes the balance',
              st['rows'][1]['closing'], round(WHOLE - (30000.0 - AUGUST), 2))
        check('owed is the total less the payment',
              st['outstanding'], TOTAL - 30000.0)
        check('august reads as settled', st['rows'][0]['paid'], True)
        check('september does not', st['rows'][1]['paid'], False)
        check('the oldest open month moved on',
              st['oldest_open'], 'September 2026')

        print('\n--- money handed over ahead of the work ---')
        # More than everything earned so far. The surplus cannot clear a
        # month that has not happened, so it sits on the month it was given
        # in and the balance goes negative: the worker has had more than has
        # been earned, and the statement should say so rather than show zero.
        pay.amount = TOTAL + 5000.0
        db.session.commit()
        st = rebuild('oldest_first')
        check('every month is cleared', st['rows'][0]['closing'], 0.0)
        check('and the surplus shows as owed back',
              st['outstanding'], -5000.0)
        pay.amount = 20000.0
        db.session.commit()

        print('\n--- a wage payment must not be counted twice ---')
        # Marking October paid as well records the month's own settlement.
        # Both are real money out, so both reduce the balance — what must not
        # happen is the wage payment being read as a deduction *and* as a
        # settlement.
        st = rebuild('month')
        before = st['outstanding']
        check('settled total equals the one payment', st['settled'], 20000.0)
        check('nothing was booked as drawn', st['drawn'], 0.0)
        check('owed is total less that payment', before, TOTAL - 20000.0)

        print('\n--- half-settling a month ---')
        rec = m.PayrollRecord(account_id=acct.id, worker_id=w.id,
                              month=9, year=2026, total_days=30,
                              present_days=26, gross_pay=WHOLE,
                              deductions=0.0, net_pay=WHOLE,
                              paid_amount=10000.0, status='partial')
        db.session.add(rec)
        db.session.commit()
        check('the month reads as part settled', rec.payment_state, 'partial')
        check('and reports what was handed over', rec.settled_amount, 10000.0)
        st = rebuild('month')
        check('september shows the part payment',
              st['rows'][1]['settled'], 10000.0)
        check('september still owes the rest',
              st['rows'][1]['closing'], round(AUGUST + WHOLE - 10000.0, 2))
        check('owed drops by the part payment',
              st['outstanding'], TOTAL - 30000.0)
        check('september is not marked settled', st['rows'][1]['paid'], False)

        print('\n--- paying the remainder closes it ---')
        rec.paid_amount = WHOLE
        rec.status = 'paid'
        db.session.commit()
        check('now it reads settled', rec.payment_state, 'paid')
        st = rebuild('month')
        check('september closes on what August left',
              st['rows'][1]['closing'], AUGUST)

        print('\n--- a month settled before this column existed ---')
        # paid_amount is NULL on every row written before the upgrade. Read
        # literally that is zero, which would reopen every month a business
        # had already paid and inflate what it owes. status has to be
        # honoured as the older statement of the same fact.
        rec.paid_amount = None
        rec.status = 'paid'
        db.session.commit()
        check('a legacy paid row still reports its net',
              rec.settled_amount, WHOLE)
        check('and still reads as settled', rec.payment_state, 'paid')
        st = rebuild('month')
        check('so September is settled as it was before',
              st['rows'][1]['settled'], WHOLE)

        print('\n--- marking a month paid never clears an older one ---')
        # Even under oldest-dues-first. A payroll settlement is a statement
        # about its own month; letting it drift backwards would mean
        # settling September had quietly closed August.
        st = rebuild('oldest_first')
        check('september carries its own settlement',
              st['rows'][1]['settled'], WHOLE)
        check('august is cleared only by the transaction',
              st['rows'][0]['settled'], 20000.0)
        check('august keeps its own arrears',
              st['rows'][0]['closing'], round(AUGUST - 20000.0, 2))

        print('\n--- a cancelled payment stops counting ---')
        pay.status = 'cancelled'
        db.session.commit()
        st = rebuild('oldest_first')
        check('august owes all of itself again',
              st['rows'][0]['closing'], AUGUST)
        check('owed goes back up', st['outstanding'], TOTAL - WHOLE)

        print('\n--- an unreadable setting falls back to the old behaviour ---')
        pay.status = 'active'
        db.session.commit()
        st = ledger.build(w, upto=UPTO, compute_month=javed_month,
                          allocation='nonsense')
        check('it reports the mode it used', st['allocation'], 'month')
        check('and books the payment on its own month',
              st['rows'][2]['settled'], 20000.0)
    finally:
        db.session.rollback()
        wid = made[0]
        m.WorkerTransaction.query.filter_by(worker_id=wid).delete(
            synchronize_session=False)
        m.PayrollRecord.query.filter_by(worker_id=wid).delete(
            synchronize_session=False)
        m.Worker.query.filter(m.Worker.id.in_(made)).delete(
            synchronize_session=False)
        db.session.commit()
        check('the probe worker is gone',
              m.Worker.query.filter(
                  m.Worker.full_name.like('ZZ Alloc%')).count(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('Payments land where the house rule says they land.')
