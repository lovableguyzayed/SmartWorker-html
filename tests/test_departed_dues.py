"""A man who leaves owing nothing goes. A man who is owed stays.

The dues screen listed workers with status 'active'. That answers "who is
on the roll", and this screen is there to answer a different question:
who is still owed money. On the case that matters most it got it exactly
backwards.

A labourer is let go in the middle of a month holding three months of
arrears. Somebody marks him inactive, which is the correct thing to do —
he is not coming in tomorrow and should not appear on the attendance
roster. His debt vanishes from the one screen in the application that
exists to show debts, and nothing ever mentions it again. The money is
still owed. The man will come back and ask for it, and there will be
nothing on any screen to check him against.

So the screen now walks everybody who has left as well, and drops the
ones who are square. Those cost a statement each and are then thrown
away, which is the price of not forgetting the ones who are not.

What is checked, with two real workers built for it and removed again:

  * a departed worker who is owed appears, and is marked as having left,
    so nobody rings him asking why he is not at the gate.
  * a departed worker who is square does NOT appear, because a list of
    everybody who ever worked here is not a list of who to pay.
  * the company total includes what is owed to the one who left. An
    employer who budgets from that figure is budgeting for a debt he
    actually has.
  * the active roster is untouched: same people, same figures as before.

Run from the project root:  python3 tests/test_departed_dues.py
"""
import datetime
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from app import app, db
import models as m
import routes

MARK = 'ZZDeparted'
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


made = []

with app.app_context():
    with app.test_request_context():
        from flask_login import login_user
        import flask

        admin = m.User.query.filter_by(role='admin').first()
        login_user(admin)
        flask.g.account_id = admin.account_id
        today = routes.today_ist()
        account = admin.account_id

        # Anything a previous run left, before the counts below are taken.
        m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
            synchronize_session=False)
        db.session.commit()

        before = routes._company_dues()
        before_names = {r['full_name'] for r in before['rows']}
        before_total = before['total_outstanding']
        print('  %d worker(s) on the dues screen, ₹%s outstanding'
              % (len(before['rows']), round(before_total, 2)))

        # Two months back, so there is real money on the statement rather
        # than a part month that rounds to nothing.
        joined = (today.replace(day=1) - datetime.timedelta(days=62))

        def build(name, worker_id):
            w = m.Worker(
                account_id=account, worker_id=worker_id,
                full_name='%s %s' % (MARK, name), phone='9000000%s' % worker_id[-3:],
                position='Helper', department='Civil', employee_type='permanent',
                join_date=joined, pay_type='monthly', monthly_salary=20000,
                monthly_working_days=30, standard_working_hours=8,
                status='inactive')
            db.session.add(w)
            db.session.flush()
            made.append(w.id)
            return w

        owed = build('Owed', 'ZD001')
        square = build('Square', 'ZD002')

        # The one who is square was paid everything he earned. The figure
        # comes from the same ledger the screen uses, so this cannot drift
        # from whatever the engine decides a month is worth.
        db.session.commit()
        statement = routes.worker_ledger(square, upto=today)
        if statement['outstanding'] > 0:
            db.session.add(m.WorkerTransaction(
                account_id=account, worker_id=square.id,
                txn_type='wage_payment',
                amount=round(statement['outstanding'], 2),
                date=today, description=MARK + ' settled in full',
                status='active'))
            db.session.commit()

        owed_statement = routes.worker_ledger(owed, upto=today)
        square_statement = routes.worker_ledger(square, upto=today)
        print('  the one who is owed:   ₹%s' % owed_statement['outstanding'])
        print('  the one who is square: ₹%s' % square_statement['outstanding'])
        check('the fixture really is owed something',
              owed_statement['outstanding'] > 1, True)
        check('and the other really is square',
              abs(square_statement['outstanding']) < 1, True)

        # ------------------------------------------------------------------
        print('\n--- the screen, now that both have left ---')

        after = routes._company_dues()
        names = {r['full_name'] for r in after['rows']}
        check('the one who is still owed is listed',
              '%s Owed' % MARK in names, True)
        check('the one who is square is not',
              '%s Square' % MARK in names, False)

        row = next(r for r in after['rows'] if r['full_name'] == MARK + ' Owed')
        check('and he is marked as having left', row['has_left'], True)
        check('with the amount he is owed',
              round(row['outstanding'], 2),
              round(owed_statement['outstanding'], 2))

        check('the company total went up by exactly that',
              round(after['total_outstanding'] - before_total, 2),
              round(owed_statement['outstanding'], 2))

        active_rows = [r for r in after['rows'] if not r['has_left']]
        check('every active worker is still there',
              {r['full_name'] for r in active_rows}, before_names)
        check('and none of their figures moved',
              sorted((r['full_name'], r['outstanding']) for r in active_rows),
              sorted((r['full_name'], r['outstanding'])
                     for r in before['rows']))

        # ------------------------------------------------------------------
        print('\n--- and when he is finally paid, he goes ---')

        db.session.add(m.WorkerTransaction(
            account_id=account, worker_id=owed.id, txn_type='wage_payment',
            amount=round(owed_statement['outstanding'], 2), date=today,
            description=MARK + ' paid off', status='active'))
        db.session.commit()
        final = routes._company_dues()
        check('he is off the screen',
              MARK + ' Owed' in {r['full_name'] for r in final['rows']}, False)
        check('and the total is back where it started',
              round(final['total_outstanding'], 2), round(before_total, 2))

# ---------------------------------------------------------------------------
with app.app_context():
    m.WorkerTransaction.query.filter(
        m.WorkerTransaction.description.like(MARK + '%')).delete(
            synchronize_session=False)
    if made:
        m.PayrollRecord.query.filter(m.PayrollRecord.worker_id.in_(made)).delete(
            synchronize_session=False)
        m.Worker.query.filter(m.Worker.id.in_(made)).delete(
            synchronize_session=False)
    db.session.commit()
    print('\n--- and this test leaves nothing behind ---')
    check('its workers are gone',
          m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).count(), 0)
    check('its transactions are gone',
          m.WorkerTransaction.query.filter(
              m.WorkerTransaction.description.like(MARK + '%')).count(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('A debt does not disappear because the man stopped coming in.')
