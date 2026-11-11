"""The office shuts at half day, and nobody's pay is cut for it.

A closure day used to be all or nothing: the whole day shut. An employer
who sends everybody home at lunch had no way to say so, and the salary
engine charged for the day as usual - a monthly worker marked absent lost
a day, and a daily-wage worker who worked till lunch got the half-day rate.

A closure can now be "Half day". The owner's rules, checked here:

  * attendance stays open (the office is open for half of it);
  * a monthly salary is not cut for that day - marked absent, or not
    marked at all;
  * a daily-wage worker who came is paid the full day, however short the
    hours; one who did not come is still not paid (no work, no pay);
  * an ordinary working day and a full closure behave as before.

Runs on a throwaway database of its own.
    python3 tests/test_half_day_closure.py
"""
import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
os.environ['DATABASE_URL'] = 'sqlite:///' + _db.name
os.environ.setdefault('SESSION_SECRET', 'half-day-test')
os.environ.setdefault('ADMIN_DEFAULT_PASSWORD', 'half-day-test-admin')

from app import app, db  # noqa: E402
import routes            # noqa: E402
import models as m       # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print('  %-5s %-62s %r' % ('OK' if ok else 'FAIL', label, got))


# A finished month, so "days still to come" never enters into it.
START, END = date(2026, 9, 1), date(2026, 9, 30)
HALF, NORMAL = date(2026, 9, 10), date(2026, 9, 11)


def pay(worker, records):
    from flask import g
    for name in ('_closure_period_cache', '_all_closure_period_cache', '_salary_policy_cache'):
        if hasattr(g, name):
            delattr(g, name)
    return routes.calculate_pay_summary(worker, records, START, END)


def rec(worker, day, status, hours=None):
    r = m.AttendanceRecord(worker_id=worker.id, date=day, status=status,
                           account_id=worker.account_id)
    if hours:
        r.check_in_time = datetime.combine(day, time(9, 0))
        r.check_out_time = r.check_in_time + timedelta(hours=hours)
    db.session.add(r)
    return r


with app.test_request_context():
    admin = m.User.query.filter_by(role='admin').first()
    acc = admin.account_id

    def worker(code, **kw):
        w = m.Worker(worker_id=code, full_name=code, account_id=acc, status='active',
                     phone='9876500000', position='Helper', department='Site',
                     employee_type='permanent', start_time=time(9, 0), end_time=time(18, 0),
                     join_date=date(2026, 1, 1), **kw)
        db.session.add(w)
        db.session.flush()
        return w

    monthly = worker('HD-M', pay_type='monthly', monthly_salary=30000)
    daily = worker('HD-D', pay_type='daily', daily_rate=800, half_day_rate=400,
                   no_work_no_pay=True)
    # Charge absences and unmarked days, or there is nothing to protect.
    db.session.add(m.SalaryPolicy(account_id=acc, worker_id=None,
                                  absence_deduction_enabled=True,
                                  unmarked_days='absent'))
    db.session.commit()

    def month(w, special):
        """Present every day of the month except what `special` says."""
        m.AttendanceRecord.query.filter_by(worker_id=w.id).delete()
        out, day = [], START
        while day <= END:
            status = special.get(day, 'present')
            if status == 'short':
                out.append(rec(w, day, 'present', hours=3))
            elif status:
                out.append(rec(w, day, status, hours=9 if status == 'present' else None))
            day += timedelta(days=1)
        db.session.commit()
        return out

    print('--- an ordinary day: absence costs a day, as before ---')
    full = pay(monthly, month(monthly, {}))['base_pay']
    cut = pay(monthly, month(monthly, {HALF: 'absent'}))
    check('a full month pays the salary', full, 30000.0)
    check('an absent day is charged', cut['leave_deductions'] > 0, True)
    short = pay(daily, month(daily, {HALF: 'short'}))['base_pay']
    check('three hours on a normal day earns the half-day rate',
          short, 29 * 800.0 + 400.0)

    print('\n--- the same month, with that day closed at half day ---')
    with app.test_client() as c:
        c.post('/login', data={'username': admin.username,
                               'password': os.environ['ADMIN_DEFAULT_PASSWORD']})
        page = c.get('/closures').get_data(as_text=True)
        check('the closure form offers Half day', 'value="half"' in page, True)
        c.post('/closures', data={'date': HALF.isoformat(), 'reason': 'Half day for Eid',
                                  'type': 'holiday', 'scope': 'company', 'duration': 'half'})
    clo = m.ClosureDay.query.filter_by(date=HALF).first()
    check('it is saved as a half day', bool(clo and clo.half_day), True)
    check('with attendance left open, even with the switch off',
          bool(clo and clo.allow_attendance), True)

    got = pay(monthly, month(monthly, {HALF: 'absent'}))
    check('monthly, marked absent: nothing is cut', got['leave_deductions'], 0.0)
    check('and the payslip says why',
          'closed at half day' in (got.get('policy_note') or ''), True)
    got = pay(monthly, month(monthly, {HALF: None}))
    check('monthly, not marked at all: nothing is cut', got['leave_deductions'], 0.0)
    got = pay(monthly, month(monthly, {HALF: 'absent', NORMAL: 'absent'}))
    check('an absence on another day is still charged', got['leave_deductions'] > 0, True)
    check('and only that one', got['salary_breakdown']['deduction_days'], 1)

    got = pay(daily, month(daily, {HALF: 'short'}))
    check('daily wage, three hours worked: paid the full day',
          got['base_pay'], 30 * 800.0)
    check('and it is not counted as a half day', got['half_day_days'], 0)
    got = pay(daily, month(daily, {HALF: 'absent'}))
    check('daily wage, did not come: not paid for the day', got['base_pay'], 29 * 800.0)
    got = pay(daily, month(daily, {NORMAL: 'short'}))
    check('a short day that is not a closure is still a half day',
          got['base_pay'], 29 * 800.0 + 400.0)

    print('\n--- a full closure is unchanged ---')
    with app.test_client() as c:
        c.post('/login', data={'username': admin.username,
                               'password': os.environ['ADMIN_DEFAULT_PASSWORD']})
        c.post('/closures', data={'date': NORMAL.isoformat(), 'reason': 'Shut',
                                  'type': 'holiday', 'scope': 'company', 'duration': 'full'})
    full_clo = m.ClosureDay.query.filter_by(date=NORMAL).first()
    check('Full day is not a half day', bool(full_clo.half_day), False)
    check('and is locked when the switch is off', bool(full_clo.allow_attendance), False)

os.unlink(_db.name)
print()
if fails:
    print('FAILED %d: %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('A half-day closure costs nobody their pay.')
