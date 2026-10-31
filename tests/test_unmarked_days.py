"""A day nobody marked, and a night that is not twelve hours of lateness.

Both came out of one question about one worker: Javed is on ₹23,000 a month
on a 26-day basis, and his three months read

    August    25 days marked   ₹22,125
    September 30 days marked   ₹23,000
    October   22 days marked   ₹23,000

Fewer days in October than August and more money, and three different
implied day rates. Two separate things were behind it.

1. A day with no attendance row at all costs nothing. Measured on a
   finished September: 30 days marked paid ₹23,000; deleting five of those
   rows still paid ₹23,000; marking the same five Absent paid ₹20,345. So
   forgetting to mark was free, and only a deliberate Absent was ever
   deducted.

   That is a real policy and plenty of employers want it, so it is now a
   setting rather than a correction. The default is what the app always
   did, and this file's first job is to prove the default moves nobody's
   money. The second is the other setting, and the three kinds of day it
   must never charge for: days still to come, days before joining, and
   days the plant was shut.

2. Lateness was measured against the worker's one shift whatever shift
   was worked. Javed moved to nights on 21 October, clocking in at 20:00
   against an 08:00 start, so every night came out 720 minutes late and
   October read 2,160. It cost nothing only because his late policy was
   off; with late deduction set per hour the same month lost ₹1,800.

The arithmetic is checked against the engine rather than against numbers
typed in here, except where a figure is the whole point — ₹885 a day, and
what a charged day costs.
"""
import os
import sys
from datetime import date, datetime, time, timedelta

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

import salary

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, got))


class FakeWorker:
    """Javed, as the seeder builds him."""
    def __init__(self, join_date=date(2026, 8, 7)):
        self.monthly_salary = 23000.0
        self.join_date = join_date
        self.start_time = time(8, 0)
        self.end_time = time(20, 0)


class FakeRecord:
    def __init__(self, day, status='present', check_in=None, check_out=None,
                 shift=None):
        self.date = day
        self.status = status
        self.check_in_time = check_in
        self.check_out_time = check_out
        self.shift = shift


POLICY = {
    'salary_basis': 'fixed', 'basis_days': 26, 'rounding': 'nearest',
    'joining_mode': 'attendance', 'paid_leave_enabled': True,
    'monthly_leave_allowance': 2.0, 'leave_carry_forward': False,
    'absence_deduction_enabled': True,
    'calculation_method': 'salary_minus_deductions',
}

SEP = (date(2026, 9, 1), date(2026, 9, 30))


def september(worker, marked_days, unmarked, policy_extra=None):
    policy = dict(POLICY)
    policy.update(policy_extra or {})
    records = [FakeRecord(date(2026, 9, d)) for d in marked_days]
    return salary.compute(worker, policy, records, SEP[0], SEP[1],
                          unmarked_days=unmarked)


print('--- the default pays for a day nobody marked, exactly as before ---')
w = FakeWorker()
full = september(w, range(1, 31), 0)
check('a fully marked September', full['net_payable'], 23000.0)
gap = september(w, [d for d in range(1, 31) if not 10 <= d <= 14], 5)
check('five days nobody marked costs nothing', gap['net_payable'], 23000.0)
check('and the setting says why', gap['unmarked_days_policy'], 'paid')
check('the days are still counted and reported', gap['unmarked_days'], 5)
check('but none of them was charged', gap['charged_unmarked_days'], 0)
# Deliberately NOT said on the payslip. The explanation is how the figure
# was reached, and on this setting these days did not reach it; saying so
# anyway added a sixth line to a block tuned for five and took every slip
# to a third, nearly empty sheet (tests/test_print_pages.py).
check('the payslip does not explain a day that cost nothing',
      any('never marked' in line for line in gap['explanation']), False)

print('\n--- the same five marked Absent, for the comparison ---')
marked_absent = [FakeRecord(date(2026, 9, d)) for d in range(1, 31)
                 if not 10 <= d <= 14]
marked_absent += [FakeRecord(date(2026, 9, d), status='absent')
                  for d in range(10, 15)]
absent = salary.compute(w, POLICY, marked_absent, SEP[0], SEP[1])
# Five absences, two covered by the month's paid leave, three charged at
# the ₹885 rounded daily rate.
check('three chargeable days at ₹885', absent['deduction_amount'], 2655.0)
check('which is what the old behaviour produced', absent['net_payable'], 20345.0)

print('\n--- switched on, an unmarked day costs what an absent one costs ---')
charged = september(w, [d for d in range(1, 31) if not 10 <= d <= 14], 5,
                    {'unmarked_days': 'absent'})
check('the same five days now cost the same money',
      charged['net_payable'], absent['net_payable'])
check('all five were charged', charged['charged_unmarked_days'], 5)
check('the paid leave allowance covers them like any absence',
      charged['paid_leave_used'], 2.0)
check('and the payslip says they were charged',
      any('never marked' in line and 'charged' in line
          for line in charged['explanation']), True)

print('\n--- a joining month under attendance mode is left alone ---')
# That branch already pays only for attended days, so charging an
# unmarked day again would deduct it twice.
joiner = FakeWorker(join_date=date(2026, 9, 7))
j = salary.compute(joiner, dict(POLICY, unmarked_days='absent'),
                   [FakeRecord(date(2026, 9, d)) for d in range(7, 31)],
                   SEP[0], SEP[1], unmarked_days=4)
check('nothing is charged twice', j['charged_unmarked_days'], 0)
check('and the pay is the attended days at ₹885', j['net_payable'], 24 * 885.0)

print('\n--- an unreadable setting changes nobody\'s pay ---')
odd = september(w, [d for d in range(1, 31) if not 10 <= d <= 14], 5,
                {'unmarked_days': 'nonsense-from-a-bad-migration'})
check('it falls back to paid', odd['net_payable'], 23000.0)
check('not to charging people', odd['charged_unmarked_days'], 0)

print('\n--- the days that must never be counted ---')
# These three are the caller's job (routes.count_unmarked_days), so they
# are checked against it rather than against the engine.
import routes  # noqa: E402
from app import app  # noqa: E402


class FakeClosure:
    def __init__(self, day, allow):
        self.date = day
        self.allow_attendance = allow
        self.scope = 'company'
        self.site_id = None
        self.project_id = None


with app.app_context():
    import flask
    ctx = app.test_request_context()
    ctx.push()
    today = routes.today_ist()
    # A month that is still running, so "days still to come" is real.
    start = today.replace(day=1)
    end = date(today.year, today.month,
               __import__('calendar').monthrange(today.year, today.month)[1])

    worker = FakeWorker(join_date=start)
    flask.g._all_closure_period_cache = {(start, end): []}
    none_marked = routes.count_unmarked_days(worker, [], start, end)
    check('only days up to today are ever counted',
          none_marked, (today - start).days + 1)

    # Asked of a month that has not happened yet, rather than of this one:
    # run this on the 31st and "the rest of the month" is empty, so the
    # check passed or failed on the calendar rather than on the code.
    nxt = (end + timedelta(days=1))
    nxt_end = date(nxt.year, nxt.month,
                   __import__('calendar').monthrange(nxt.year, nxt.month)[1])
    flask.g._all_closure_period_cache[(nxt, nxt_end)] = []
    check('a month still to come is charged nothing at all',
          routes.count_unmarked_days(worker, [], nxt, nxt_end), 0)

    # Joined halfway through: the days before are not this worker's.
    midway = FakeWorker(join_date=start + timedelta(days=5))
    check('days before joining are not counted',
          routes.count_unmarked_days(midway, [], start, end),
          (today - (start + timedelta(days=5))).days + 1)

    # A day the plant was shut with attendance locked.
    shut_day = start + timedelta(days=1)
    flask.g._all_closure_period_cache = {(start, end): [FakeClosure(shut_day, False)]}
    check('a day the plant was shut is not counted',
          routes.count_unmarked_days(worker, [], start, end), none_marked - 1)

    # A closure that still allowed attendance is an ordinary working day.
    flask.g._all_closure_period_cache = {(start, end): [FakeClosure(shut_day, True)]}
    check('a closure that still allowed work is counted',
          routes.count_unmarked_days(worker, [], start, end), none_marked)

    print('\n--- a night is not twelve hours of lateness ---')
    night = FakeRecord(start, check_in=datetime.combine(start, time(20, 0)),
                       check_out=datetime.combine(start + timedelta(days=1), time(8, 0)),
                       shift='night')
    check('a night shift reports no lateness',
          routes.calculate_late_minutes_for_record(worker, night), 0)
    unflagged = FakeRecord(start, check_in=datetime.combine(start, time(20, 0)),
                           check_out=datetime.combine(start + timedelta(days=1), time(8, 0)))
    check('even with nothing in the shift column',
          routes.calculate_late_minutes_for_record(worker, unflagged), 0)
    check('and a 20:00 start is not flagged Late at the gate',
          routes.is_late_check_in(worker, start,
                                  datetime.combine(start, time(20, 0))), False)

    print('\n--- a real latecomer is still caught ---')
    late = FakeRecord(start, check_in=datetime.combine(start, time(9, 30)),
                      check_out=datetime.combine(start, time(20, 0)))
    check('09:30 against an 08:00 shift is 90 minutes late',
          routes.calculate_late_minutes_for_record(worker, late), 90)
    check('and it is flagged Late',
          routes.is_late_check_in(worker, start, late.check_in_time), True)
    on_time = FakeRecord(start, check_in=datetime.combine(start, time(8, 0)),
                         check_out=datetime.combine(start, time(20, 0)))
    check('08:00 is not late', routes.calculate_late_minutes_for_record(worker, on_time), 0)
    ctx.pop()

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('A forgotten day is a choice now, and a night shift is not a late arrival.')
