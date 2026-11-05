"""Paid for a month nobody marked him in, and nothing said about it.

Days nobody marked count as paid. That is deliberate and it is the
employer's own setting: a Sunday the mukadam never marked should not cost
a man his wage, and the alternative — treating silence as absence —
docks people for the application not being used.

But it has a degenerate case that costs the employer instead. A monthly
man whom NOBODY MARKED ONCE, all month, draws his full salary:

    daily    Rs 800 a day,  no marks  ->  Rs 0
    hourly   Rs 100 an hour, no marks ->  Rs 0
    monthly  Rs 23,000,      no marks ->  Rs 23,000

The three pay types are each right on their own terms — a daily wage is
earned by days and a monthly salary is unconditional until somebody
records an absence. What was wrong is that the figure arrives looking
exactly like an ordinary month, with nothing on the screen to say that
not one attendance mark exists behind it.

Two ways that empties a real pocket:

  * the first month of using this, before anybody is in the habit of
    marking. On the demo roster that is three monthly workers drawing
    Rs 18,000, Rs 25,000 and Rs 30,000 — Rs 73,000 paid out with no
    attendance recorded at all.
  * a man who stopped coming and whose status nobody changed. He keeps
    drawing a salary every month until somebody notices.

So this is a WARNING and not a change to the arithmetic. The employer
chose that days nobody marked are paid; overriding his setting would be
the application deciding his policy for him. What it owes him is the one
fact he cannot see from the figures.

Checked here:

  * a monthly man with no marks is flagged, and still paid in full
  * one single mark anywhere in the month clears the flag
  * a daily or hourly man with no marks is NOT flagged, because nothing
    is being paid, so there is nothing to warn about
  * a man who joined after the month is not flagged either
  * the screen says it once at the top, with a count, before Generate is
    tapped — not only on whichever rows get scrolled past

Run from the project root:  python3 tests/test_never_marked.py
"""
import datetime
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

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
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

MARK = 'ZZNeverMarked'
made = {}

with app.app_context():
    m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
        synchronize_session=False)
    db.session.commit()
    admin = m.User.query.filter_by(role='admin').first()
    account = admin.account_id

    def make(suffix, phone, joined=datetime.date(2026, 1, 1), **kw):
        w = m.Worker(account_id=account, worker_id='ZZNV' + suffix,
                     full_name=MARK + ' ' + suffix, phone=phone,
                     position='Helper', department='Civil',
                     employee_type='permanent', join_date=joined,
                     status='active', **kw)
        db.session.add(w)
        db.session.commit()
        made[suffix] = w.id
        return w.id

    make('MONTH', '9000000911', pay_type='monthly', monthly_salary=23000)
    make('DAILY', '9000000912', pay_type='daily', daily_rate=800)
    make('HOURLY', '9000000913', pay_type='hourly', hourly_rate=100)
    make('MARKED', '9000000914', pay_type='monthly', monthly_salary=23000)
    # Joined after the month being looked at: not employed, not flagged.
    make('LATER', '9000000915', joined=datetime.date(2026, 12, 1),
         pay_type='monthly', monthly_salary=23000)

    # One single mark, on one day, for the one who has any.
    db.session.add(m.AttendanceRecord(
        account_id=account, worker_id=made['MARKED'],
        date=datetime.date(2026, 10, 7), status='present'))
    db.session.commit()


def rows_for(month=10, year=2026):
    """The payroll rows the screen builds, keyed by worker name suffix."""
    with app.app_context():
        with app.test_request_context():
            import flask
            from flask_login import login_user
            admin = m.User.query.filter_by(role='admin').first()
            login_user(admin)
            flask.g.account_id = admin.account_id
            rows, totals, _start = routes._build_payroll_rows(month, year)
            out = {}
            for row in rows:
                name = row['worker'].full_name
                if name.startswith(MARK):
                    out[name.rsplit(' ', 1)[-1]] = row
            return out, totals


try:
    print('--- the figures themselves are right for each pay type ---')
    rows, totals = rows_for()
    check('a monthly man with no marks is paid in full',
          rows['MONTH']['net_pay'], 23000.0)
    check('a daily man with no marks earns nothing',
          rows['DAILY']['net_pay'], 0.0)
    check('nor does an hourly man', rows['HOURLY']['net_pay'], 0.0)

    print('\n--- and the one that is paid for nothing is flagged ---')
    check('the monthly man is flagged', rows['MONTH']['never_marked'], True)
    check('the daily man is not, because nothing is being paid',
          rows['DAILY']['never_marked'], False)
    check('nor the hourly man', rows['HOURLY']['never_marked'], False)
    check('one single mark clears it', rows['MARKED']['never_marked'], False)
    check('and a man who had not joined yet is not flagged',
          rows['LATER']['never_marked'], False)

    print('\n--- the arithmetic is NOT touched: it is his own setting ---')
    check('the flagged man still draws his whole salary',
          rows['MONTH']['net_pay'], 23000.0)
    check('and the marked man draws his too',
          rows['MARKED']['net_pay'], 23000.0)

    print('\n--- said once at the top, with a count ---')
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})
        page = client.get('/payroll?month=10&year=2026').get_data(as_text=True)
        found = re.search(
            r'(\d+) worker\(s\) are being paid with no attendance marked',
            page)
        check('the banner is there', found is not None, True)
        counted = int(found.group(1)) if found else -1
        check('and its count matches the rows',
              counted, totals['never_marked_count'])
        check('the count includes our man and is at least one',
              counted >= 1 and totals['never_marked_count'] >= 1, True)
        check('it says whose setting this is',
              'which is your setting' in page, True)
        check('and the flagged row carries its own badge',
              'Attendance never marked' in page, True)

    print('\n--- a month everybody was marked in says nothing ---')
    with app.app_context():
        admin = m.User.query.filter_by(role='admin').first()
        for suffix in ('MONTH', 'DAILY', 'HOURLY'):
            db.session.add(m.AttendanceRecord(
                account_id=admin.account_id, worker_id=made[suffix],
                date=datetime.date(2026, 10, 9), status='present'))
        db.session.commit()
    rows, totals = rows_for()
    check('nobody of ours is flagged now',
          [s for s in ('MONTH', 'DAILY', 'HOURLY', 'MARKED')
           if rows[s]['never_marked']], [])
finally:
    with app.app_context():
        ids = list(made.values())
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
            "select count(*) from workers where full_name like 'ZZNeverMarked%'"
        )).scalar(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('A salary paid for a month nobody marked is said out loud, and '
      'still paid.')
