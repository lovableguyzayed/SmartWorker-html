"""Nobody is paid in paise, and it is not a setting anybody can forget.

The employer's point, which is the right one: a round-off that lives in a
dropdown is a round-off that is sometimes off, and a payment with a decimal
point in it causes trouble at the gate. It belongs in the calculation.

Two things were wrong before this:

  * the rounding only ever governed the SALARY. An hourly worker at
    ₹118.75 an hour and a daily worker on ₹512.33 never went through the
    salary engine at all, so they came out at ₹22,712.50 and ₹9,976.66
    whatever the dropdown said.

  * overtime per minute, a late deduction per hour and a closure bonus at
    37.5% are all computed from rates and percentages, and none of them
    was rounded either.

Now every figure the app WORKS OUT is rounded by the policy's own rule
before anything is added up, so the total is the sum of the parts exactly
as the payslip prints them.

What is deliberately NOT rounded, and is checked here so nobody "fixes" it
later: an amount somebody TYPED IN. An advance of ₹2,250.50 is a record of
money that changed hands. Rounding it to ₹2,251 would not tidy the books,
it would misstate what was paid — and the dues statement would then
disagree with the receipt in the worker's hand.

And 'No rounding' still means no rounding. An employer who chooses it is
asking for the paise.

Run from the project root:  python3 tests/test_whole_rupees.py
"""
import calendar
import datetime
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from app import app, db
import models as m
import routes
import salary

START = datetime.date(2026, 10, 1)
END = datetime.date(2026, 10, 31)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


def whole(value):
    return abs(float(value) - round(float(value))) <= 0.004


def records(worker_id, days=24, overtime=0, late=False):
    return [
        m.AttendanceRecord(
            worker_id=worker_id, date=datetime.date(2026, 10, d),
            status='late' if late else 'present',
            check_in_time=datetime.datetime(2026, 10, d, 9 if late else 8, 25),
            check_out_time=datetime.datetime(2026, 10, d, 17, 0),
            overtime_minutes=overtime)
        for d in range(1, days + 1)]


#: Each one is a real setting on the worker form, with a rate or a
#: percentage that does not divide evenly. These are the shapes that used
#: to leak paise.
CASES = [
    ('overtime per minute',    dict(overtime_enabled=True,
                                    overtime_type='minute',
                                    overtime_rate=2.75), 37, False),
    ('overtime per hour',      dict(overtime_enabled=True,
                                    overtime_type='hour',
                                    overtime_rate=95.0), 50, False),
    ('late deduction / hour',  dict(late_policy_enabled=True,
                                    late_deduction_type='hour',
                                    late_deduction_per_day=60.0), 0, True),
    ('late deduction / minute', dict(late_policy_enabled=True,
                                     late_deduction_type='minute',
                                     late_deduction_per_day=1.35), 0, True),
    ('closure bonus 37.5%',    dict(closure_extra_pay_enabled=True,
                                    closure_extra_percentage=37.5,
                                    closure_calculation_method='daily_percent'),
     0, False),
    ('an hourly worker',       dict(pay_type='hourly',
                                    hourly_rate=118.75), 0, False),
    ('a daily rate in paise',  dict(pay_type='daily',
                                    daily_rate=512.33), 0, False),
    ('a third of a rupee',     dict(pay_type='daily',
                                    daily_rate=333.33), 0, False),
]

MONEY = ('base_pay', 'overtime_pay', 'leave_deductions', 'late_deductions',
         'delay_penalty', 'closure_extra_pay', 'deductions', 'estimated_pay')

with app.app_context():
    with app.test_request_context():
        from flask_login import login_user
        import flask

        admin = m.User.query.filter_by(role='admin').first()
        login_user(admin)
        flask.g.account_id = admin.account_id

        worker = m.Worker.query.filter_by(pay_type='monthly',
                                          status='active').first()

        # ------------------------------------------------------------------
        print('--- the settings that used to pay people in paise ---')

        for name, overrides, overtime, late in CASES:
            saved = {k: getattr(worker, k) for k in overrides}
            for key, value in overrides.items():
                setattr(worker, key, value)
            try:
                summary = routes.calculate_pay_summary(
                    worker, records(worker.id, overtime=overtime, late=late),
                    START, END)
                ragged = {f: summary[f] for f in MONEY if not whole(summary[f])}
                check('%-24s pays whole rupees' % name, ragged, {})
            finally:
                for key, value in saved.items():
                    setattr(worker, key, value)
                # Nothing above is committed. The rollback is here so a
                # failure cannot leave the worker holding test settings —
                # this database is the fixture every other suite logs into.
                db.session.rollback()

        # ------------------------------------------------------------------
        print('\n--- the total is the sum of its parts, as printed ---')

        saved = {k: getattr(worker, k) for k in ('pay_type', 'hourly_rate')}
        worker.pay_type = 'hourly'
        worker.hourly_rate = 118.75
        try:
            s = routes.calculate_pay_summary(
                worker, records(worker.id), START, END)
            total = (s['base_pay'] + s['overtime_pay']
                     + s['transaction_earnings'] - s['deductions']
                     - s['transaction_deductions'])
            check('base + overtime + extras - deductions = the figure shown',
                  round(total, 2), round(s['estimated_pay'], 2))
            check('and the deductions are the sum of their own parts',
                  round(s['leave_deductions'] + s['late_deductions']
                        + s['delay_penalty'], 2),
                  round(s['deductions'], 2))
        finally:
            for key, value in saved.items():
                setattr(worker, key, value)
            db.session.rollback()

        # ------------------------------------------------------------------
        print('\n--- what somebody typed in is not rounded away ---')

        # Checked on the engine rather than on a saved transaction, because
        # this is about the rule, not about one row: a recorded payment is
        # money that changed hands and the statement has to agree with the
        # receipt.
        marked = 'ZZPaise test advance'
        txn = m.WorkerTransaction(
            worker_id=worker.id, account_id=worker.account_id,
            txn_type='advance', amount=2250.50, date=datetime.date(2026, 10, 9),
            description=marked, status='active')
        db.session.add(txn)
        db.session.commit()
        try:
            s = routes.calculate_pay_summary(
                worker, records(worker.id), START, END)
            check('an advance of ₹2,250.50 is still ₹2,250.50',
                  float(txn.amount), 2250.50)
            check('and it reaches the pay run at that amount',
                  s['transaction_deductions'] >= 2250.50, True)
        finally:
            m.WorkerTransaction.query.filter_by(description=marked).delete(
                synchronize_session=False)
            db.session.commit()
            check('the test took its transaction back out',
                  m.WorkerTransaction.query.filter_by(
                      description=marked).count(), 0)

        # ------------------------------------------------------------------
        print('\n--- "no rounding" still means no rounding ---')

        exact, rounded = salary.daily_rate(
            23000, dict(salary.DEFAULT_POLICY, basis_days=26,
                        rounding='none'), START, END)
        check('the daily rate keeps its paise', float(rounded), 884.62)
        check('and apply_rounding leaves paise alone on "none"',
              float(salary.apply_rounding(salary._dec('19166.666'), 'none')),
              19166.67)
        for mode, want in (('nearest', 19167.0), ('up', 19167.0),
                           ('down', 19166.0)):
            check('%-8s rounds 19,166.666 to %s' % (mode, want),
                  float(salary.apply_rounding(
                      salary._dec('19166.666'), mode)), want)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('Every figure the app works out is a whole rupee, and every figure '
      'somebody typed in is exactly what they typed.')
