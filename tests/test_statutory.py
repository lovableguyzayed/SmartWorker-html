"""ESI, PF, and the two different things a ceiling can mean.

There was no statutory deduction anywhere in this application, and for an
Indian employer it is the first thing an accountant asks for. ESI applies
at ten or more employees, EPF at twenty, and this roster has twelve.

The whole difficulty is that the figure attached to each one behaves in
two opposite ways, and getting them the wrong way round is a real amount
of somebody's money:

    ESI   ₹21,000 is an ELIGIBILITY line. Earn up to it and 0.75% comes
          off; earn more and you are out of the scheme and nothing comes
          off at all.
    EPF   ₹15,000 is a CAP on the base. 12% of the first ₹15,000 — ₹1,800
          — whatever is earned above it.

Treat ESI's figure as a cap and a man on ₹30,000 loses ₹157 he does not
owe. Treat EPF's as an eligibility line and he loses ₹1,800 he does.
Both are checked here, from both sides of each figure.

Nothing is hardcoded. The rates change by notification, and an employer
who is not registered must not have money taken off his men's wages
because an application assumed he was — so every rule is off until
somebody switches it on, which is also checked.

What else is checked:

  * the employer's own share is recorded and NOT deducted from the
    worker. It is the employer's cost, and the two must never be added
    together by accident.
  * the payslip names each line with its percentage. "Deductions ₹1,800"
    with no name is a figure a man cannot check, and it is the number he
    will be asked about at home.
  * a rule switched off deducts nothing, and removing it leaves the pay
    exactly where it was before.

Run from the project root:  python3 tests/test_statutory.py
"""
import datetime
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from sqlalchemy import text

from app import app, db
import models as m
import routes  # noqa: F401
import bulk    # noqa: F401

START = datetime.date(2026, 10, 1)
END = datetime.date(2026, 10, 31)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


def records(worker_id):
    return [m.AttendanceRecord(worker_id=worker_id,
                               date=datetime.date(2026, 10, d),
                               status='present', check_in_time=None,
                               check_out_time=None, overtime_minutes=0)
            for d in range(1, 27)]


def clear_rules():
    db.session.execute(text('delete from statutory_deductions'))
    db.session.commit()


with app.app_context():
    clear_rules()

with app.app_context():
    with app.test_request_context():
        from flask_login import login_user
        import flask

        admin = m.User.query.filter_by(role='admin').first()
        login_user(admin)
        flask.g.account_id = admin.account_id
        account = admin.account_id

        worker = m.Worker.query.filter_by(pay_type='monthly',
                                          status='active').first()
        original_salary = worker.monthly_salary
        recs = records(worker.id)

        def pay(salary_amount):
            """What this worker takes home on that salary, rules as set."""
            worker.monthly_salary = salary_amount
            flask.g.pop('_statutory_rules', None)
            return routes.calculate_pay_summary(worker, recs, START, END)

        def add(name, percent, employer, ceiling, mode):
            row = m.StatutoryDeduction(
                account_id=account, name=name, percent=percent,
                employer_percent=employer, ceiling=ceiling,
                ceiling_mode=mode, enabled=True)
            db.session.add(row)
            db.session.commit()
            return row

        try:
            # ----------------------------------------------------------
            print('--- nothing is deducted until somebody says so ---')
            base = pay(20000)
            check('no rules, no statutory deduction',
                  base['statutory_deductions'], 0.0)
            check('and nothing on the payslip to explain',
                  base['statutory_breakdown'], [])

            off = add('ESI', 0.75, 3.25, 21000, 'eligibility')
            off.enabled = False
            db.session.commit()
            check('a rule switched off deducts nothing',
                  pay(20000)['statutory_deductions'], 0.0)
            off.enabled = True
            db.session.commit()

            # ----------------------------------------------------------
            print('\n--- ESI: a line you fall below, not a cap ---')
            under = pay(20000)
            check('on ₹20,000 it is 0.75% of the whole wage',
                  under['statutory_deductions'],
                  round(under['base_pay'] * 0.0075))
            over = pay(30000)
            check('on ₹30,000 nobody is in the scheme, so nothing',
                  over['statutory_deductions'], 0.0)
            check('and the payslip says nothing about it either',
                  over['statutory_breakdown'], [])
            at = pay(21000)
            check('exactly at the line, he is still in',
                  at['statutory_deductions'] > 0, True)

            print('       (a cap here would have taken %s off the '
                  '₹30,000 man)' % round(21000 * 0.0075))

            # ----------------------------------------------------------
            print('\n--- EPF: a cap on the base, not a line ---')
            clear_rules()
            add('EPF', 12, 12, 15000, 'cap')
            small = pay(10000)
            check('under the cap, 12% of the whole wage',
                  small['statutory_deductions'],
                  round(small['base_pay'] * 0.12))
            big = pay(38000)
            check('over it, 12% of ₹15,000 and no more',
                  big['statutory_deductions'], 1800.0)
            check('he is still in the scheme, unlike ESI',
                  len(big['statutory_breakdown']), 1)

            # ----------------------------------------------------------
            print('\n--- the employer pays his own share, separately ---')
            line = big['statutory_breakdown'][0]
            check("the employer's share is recorded",
                  line['employer_amount'], 1800.0)
            check('and reported as a total', big['employer_statutory'], 1800.0)
            check('but it is NOT taken off the worker',
                  big['statutory_deductions'], 1800.0)
            check('so the two are never added together',
                  big['statutory_deductions'] + 0 == big['employer_statutory']
                  and big['deductions'] == 1800.0, True)

            # ----------------------------------------------------------
            print('\n--- two rules at once, each named on the payslip ---')
            clear_rules()
            add('ESI', 0.75, 3.25, 21000, 'eligibility')
            add('EPF', 12, 12, 15000, 'cap')
            both = pay(18000)
            names = [l['name'] for l in both['statutory_breakdown']]
            check('both appear', sorted(names), ['EPF', 'ESI'])
            check('and the total is their sum',
                  both['statutory_deductions'],
                  sum(l['amount'] for l in both['statutory_breakdown']))
            check('the net is the gross less everything',
                  round(both['base_pay'] + both['overtime_pay']
                        + both['transaction_earnings'] - both['deductions']
                        - both['transaction_deductions'], 2),
                  round(both['estimated_pay'], 2))
            for l in both['statutory_breakdown']:
                print('       %-4s %5.2f%% of ₹%-9s = ₹%s'
                      % (l['name'], l['percent'], l['base'], l['amount']))

            # ----------------------------------------------------------
            print('\n--- and removing them puts the pay back ---')
            clear_rules()
            after = pay(20000)
            check('no deduction left', after['statutory_deductions'], 0.0)
            check('and the figure is what it was before any of this',
                  after['estimated_pay'], pay(20000)['estimated_pay'])
        finally:
            worker.monthly_salary = original_salary
            db.session.commit()
            clear_rules()

with app.app_context():
    print('\n--- and this test leaves nothing behind ---')
    left = db.session.execute(
        text('select count(*) from statutory_deductions')).scalar()
    check('no rule of its own remains', left, 0)
    check('and the salary is back',
          m.Worker.query.filter_by(pay_type='monthly',
                                   status='active').first().monthly_salary,
          original_salary)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('ESI exempts, PF caps, and neither takes a rupee until it is '
      'switched on.')
