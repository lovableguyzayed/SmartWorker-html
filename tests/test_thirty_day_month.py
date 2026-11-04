"""A month is a month: a monthly salary is divided by 30, not by the calendar.

The employer's rule, in his words: "mahina chahe 31 ka chahe 30 ka, salary
monthly calculation 30 din se hi rahegi salary walo ke liye."

The app did not do that, and the reason was not the salary policy — that
already said 30. It was a field on the worker: "Monthly Working Days",
which the add-worker form fills in with 26 before anybody types anything.
Until an employer saves a company salary policy, `seed_from_worker` read
that field as the salary basis, so a ₹23,000 worker was priced at

    23000 / 26 = ₹884.62 a day

and a man who joined on the 7th of August was paid 25 x ₹885 = ₹22,125 for
a month nobody had set up any rule for. ₹766.67 was the figure the
employer expected, and it was in the defaults all along.

So the per-worker field no longer prices a salary. It still means what it
says for counting shifts — a closure bonus is a day's pay, and a day's pay
has to come from somewhere — but the basis is a rule in Settings now,
where it can be read, and not a number on a form that nobody chose.

What is checked:

  * the daily rate is salary/30 in February, April and August alike, so
    the month's length cannot change what a day is worth.
  * a worker carrying the old 26 is priced at 30 anyway, with no company
    policy saved. This is the regression that started it.
  * an employer who genuinely wants 26 still gets it, by saving it as a
    policy. The rule did not become unchangeable, it moved somewhere
    visible.
  * 'calendar' basis still exists and still follows the month, for an
    employer who wants that instead.
  * the closure bonus prices a day off the same basis as the payroll, so
    one worker cannot be worth two different amounts on one day.
  * nothing on the add-worker form says 26 any more.
"""
import datetime
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

import salary

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


class Worker:
    """A worker as the add-worker form leaves them: 26 in the days field."""

    def __init__(self, join=None, days=26):
        self.monthly_salary = 23000
        self.join_date = join or datetime.date(2025, 1, 1)
        self.monthly_working_days = days
        self.pay_type = 'monthly'
        self.allowed_leaves_per_month = None
        self.leave_policy_enabled = True
        self.leave_deduction_per_day = None


class Rec:
    def __init__(self, day, status='present'):
        self.date = day
        self.status = status
        self.leave_type = None


def whole_month(year, mon, first=1):
    import calendar
    last = calendar.monthrange(year, mon)[1]
    start, end = datetime.date(year, mon, 1), datetime.date(year, mon, last)
    days = [Rec(datetime.date(year, mon, d)) for d in range(first, last + 1)]
    return start, end, days


# ---------------------------------------------------------------------------
print('--- the month\'s length does not change a day\'s worth ---')

for mon, name, length in ((2, 'February', 28), (4, 'April', 30),
                          (8, 'August', 31)):
    start, end, _ = whole_month(2026, mon)
    exact, rounded = salary.daily_rate(23000, salary.DEFAULT_POLICY, start, end)
    check('%s (%d days) pays the same daily rate' % (name, length),
          float(exact.quantize(salary.Decimal('0.01'))), 766.67)

check('because the default basis is a fixed 30',
      (salary.DEFAULT_POLICY['salary_basis'],
       salary.DEFAULT_POLICY['basis_days']), ('fixed', 30))

# ---------------------------------------------------------------------------
print('\n--- a worker carrying the old 26 is still priced at 30 ---')

seeded = salary.seed_from_worker(Worker(days=26))
check('the worker\'s own days field is not read as the basis',
      seeded['basis_days'], 30)
check('nor is a 24 somebody typed in by hand',
      salary.seed_from_worker(Worker(days=24))['basis_days'], 30)
check('and the rest of the legacy seeding still works',
      seeded['leave_carry_forward'], True)

AUG_START, AUG_END, _ = whole_month(2026, 8)
javed = Worker(join=datetime.date(2026, 8, 7))
aug = [Rec(datetime.date(2026, 8, d)) for d in range(7, 32)]
policy = dict(salary.seed_from_worker(javed))
policy.update(joining_mode='attendance', rounding_stage='total')
b = salary.compute(javed, policy, aug, AUG_START, AUG_END)
check('Javed: 25 attended days at the 30-day rate',
      (b['daily_rate'], b['net_payable']), (766.67, 19167.0))

# ---------------------------------------------------------------------------
print('\n--- an employer who wants 26 still gets 26 ---')

explicit = dict(salary.DEFAULT_POLICY)
explicit.update(basis_days=26, joining_mode='attendance',
                rounding_stage='total')
b26 = salary.compute(javed, explicit, aug, AUG_START, AUG_END)
check('saved as a policy, 26 is honoured',
      (b26['daily_rate'], b26['net_payable']), (884.62, 22115.0))

cal = dict(salary.DEFAULT_POLICY)
cal.update(salary_basis='calendar', joining_mode='attendance',
           rounding_stage='total')
feb_start, feb_end, _ = whole_month(2026, 2)
check('and the calendar basis still follows the month',
      salary.compute(Worker(), cal, [], feb_start, feb_end)['basis_days'], 28)
check('a 31-day month on the calendar basis',
      salary.compute(Worker(), cal, [], AUG_START, AUG_END)['basis_days'], 31)

# ---------------------------------------------------------------------------
print('\n--- one worker, one daily rate ---')

src = open(os.path.join(ROOT, 'routes.py')).read()
closure = src[src.index('# Closure day extra pay'):]
closure = closure[:closure.index('\n    deductions =') if '\n    deductions ='
                  in closure else 4000]
check('the closure bonus prices a day off the policy basis',
      "salary_breakdown['basis_days']" in closure, True)
check('and not off the worker\'s own days field',
      bool(re.search(r"monthly_salary or 0\) / mwd", closure)), False)

# ---------------------------------------------------------------------------
print('\n--- nothing offers 26 any more ---')

form = open(os.path.join(ROOT, 'templates/edit_worker.html')).read()
field = form[form.index('name="monthly_working_days"'):][:600]
check('the add-worker form defaults to 30', 'else 30 }}' in field, True)
check('and says what the field is actually for',
      'The salary basis is in Settings' in field, True)
check('the two save handlers default to 30',
      len(re.findall(r"monthly_working_days'\), 30\)", src)), 2)
check('and neither still defaults to 26',
      "monthly_working_days'), 26)" in src, False)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('A month is a month: the salary is divided by 30, whatever the '
      'calendar says.')
