"""A rounded daily rate does not divide a salary, and now it need not.

₹23,000 over a 26-day basis is ₹884.6154. Rounded to the whole rupee the
app quotes ₹885, and every month paid as rate x days is then priced off a
figure that is 38 paise too big. Over a full basis month that is

    26 x ₹885 = ₹23,010

ten rupees more than the salary the worker is actually on. It is not a
rounding error in the usual sense — nothing is lost — it is that a whole
number almost never divides a salary, so multiplying it back cannot land on
the salary again. Dividing by 30 does not help: 30 x ₹767 is also ₹23,010.

So where the rounding lands is now a choice, separate from how it rounds:

  'rate'   round the daily rate, then multiply. A whole-rupee figure the
           employer can quote and check by hand. What the app has always
           done, and still the default, because changing a default silently
           re-rates everybody's pay.
  'total'  multiply the exact rate and round the month once, at the end.
           The days add back up to the salary exactly.

What is checked here:

  * the default has not moved. The same worker, the same month, the same
    figure as before this setting existed. This is the check that matters
    most: a payroll engine that quietly changes last month's answer is
    worse than one with a ₹10 gap.

  * on 'total', a full basis month paid as rate x days comes to the salary
    exactly — for a 26-day basis, a 30-day basis, and a real calendar
    month, under every one of the four rounding modes.

  * Javed's August, which is where this started: joined on the 7th, 25 days
    present, paid for attended days. ₹22,125 on 'rate', ₹22,115 on 'total'.

  * the derived deduction rate follows the same choice, so a month cannot
    be paid at one rate and docked at another.

  * an unreadable stored value falls back to 'rate', not to whichever
    branch happens to be first.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import calendar as _cal

import salary

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


class Worker:
    def __init__(self, salary_amount=23000, join=None):
        self.monthly_salary = salary_amount
        self.join_date = join or datetime.date(2025, 1, 1)
        self.monthly_working_days = 26


class Rec:
    def __init__(self, day, status='present'):
        self.date = day
        self.status = status
        self.leave_type = None


def month(year, mon):
    last = _cal.monthrange(year, mon)[1]
    return datetime.date(year, mon, 1), datetime.date(year, mon, last)


def policy(**over):
    p = dict(salary.DEFAULT_POLICY)
    p.update(over)
    return p


def present(start, end, first_day=None):
    day = first_day or start
    out = []
    while day <= end:
        out.append(Rec(day))
        day += datetime.timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
print('--- the default has not moved ---')

check('the default rounds the rate, as it always did',
      salary.DEFAULT_POLICY['rounding_stage'], 'rate')

AUG = month(2026, 8)
javed = Worker(23000, datetime.date(2026, 8, 7))
aug_days = present(AUG[0], AUG[1], datetime.date(2026, 8, 7))
check('25 days of August are on the record', len(aug_days), 25)

on_rate = salary.compute(
    javed, policy(basis_days=26, rounding='nearest', joining_mode='attendance'),
    aug_days, *AUG)
check('Javed August, rounded rate x 25 days', on_rate['net_payable'], 25 * 885.0)
check('and the rate shown is the whole rupee', on_rate['daily_rate'], 885.0)

# The same policy with the setting left out entirely, the way a row saved
# before this column existed comes back from the database.
legacy = policy(basis_days=26, rounding='nearest', joining_mode='attendance')
del legacy['rounding_stage']
check('a policy saved before this setting existed is unchanged',
      salary.compute(javed, legacy, aug_days, *AUG)['net_payable'],
      on_rate['net_payable'])

# ---------------------------------------------------------------------------
print('\n--- on the month, the days add back up to the salary ---')

SEP = month(2026, 9)
old = Worker(23000)
sep_days = present(*SEP)

for basis in (26, 30):
    for mode in salary.ROUNDING:
        p = policy(basis_days=basis, rounding=mode, rounding_stage='total',
                   calculation_method='rate_times_payable_days')
        b = salary.compute(old, p, sep_days, *SEP)
        check('basis %d, rounding %-7s -> the salary itself' % (basis, mode),
              b['net_payable'], 23000.0)

# The real month length, which is the harder case: February divides a
# salary no more evenly than 26 does.
FEB = month(2026, 2)
feb_days = present(*FEB)
for mode in salary.ROUNDING:
    p = policy(salary_basis='calendar', rounding=mode, rounding_stage='total',
               calculation_method='rate_times_payable_days')
    b = salary.compute(old, p, feb_days, *FEB)
    check('a 28-day February, rounding %-7s -> the salary' % mode,
          b['net_payable'], 23000.0)

print('\n       and on the rate, the same month does not:')
for basis in (26, 30):
    b = salary.compute(
        old, policy(basis_days=basis, rounding='nearest', rounding_stage='rate',
                    calculation_method='rate_times_payable_days'),
        sep_days, *SEP)
    print('       basis %d: ₹%s   (salary ₹23,000)' % (basis, b['net_payable']))
    check('basis %d on the rate is over the salary' % basis,
          b['net_payable'] > 23000.0, True)

# ---------------------------------------------------------------------------
print('\n--- Javed, the case this came from ---')

on_total = salary.compute(
    javed, policy(basis_days=26, rounding='nearest', joining_mode='attendance',
                  rounding_stage='total'),
    aug_days, *AUG)
check('exact rate x 25 days, rounded once', on_total['net_payable'], 22115.0)
check('and the payslip quotes the rate it was priced at',
      on_total['daily_rate'], 884.62)
check('the explanation says the month was rounded',
      on_total['explanation'][-1].endswith('(rounded).'), True)

# The account and dues screens are built from the GROSS, not the net
# (ledger.build takes `gross` out of compute_month), so rounding only the
# net left the payslip saying ₹19,167 and the statement saying ₹19,166.67
# for the same month. Both have to be whole rupees, and the net has to be
# the difference of the two as printed.
check('the gross is a whole rupee too, not just the net',
      on_total['gross_eligible_salary'] % 1, 0.0)
check('and so is the deduction', on_total['deduction_amount'] % 1, 0.0)
check('so the final line adds up exactly as printed',
      round(on_total['gross_eligible_salary']
            - on_total['deduction_amount'], 2), on_total['net_payable'])

docked = salary.compute(
    old, policy(basis_days=26, rounding='nearest', rounding_stage='total',
                absence_deduction_enabled=True),
    present(SEP[0], datetime.date(2026, 9, 28))
    + [Rec(datetime.date(2026, 9, 29), 'absent'),
       Rec(datetime.date(2026, 9, 30), 'absent')], *SEP)
check('a month with deductions is whole rupees throughout',
      [docked['gross_eligible_salary'] % 1, docked['deduction_amount'] % 1,
       docked['net_payable'] % 1], [0.0, 0.0, 0.0])

# And "no rounding" still means no rounding: the paise are the point.
raw = salary.compute(
    javed, policy(basis_days=26, rounding='none', joining_mode='attendance',
                  rounding_stage='total'),
    aug_days, *AUG)
check('"no rounding" keeps the paise, on either stage',
      raw['net_payable'], 22115.38)
check('it is still as short as it was',
      len(on_total['explanation']), len(on_rate['explanation']))

# A month that rounds to itself must not claim it was rounded.
clean = salary.compute(
    old, policy(basis_days=26, rounding='nearest', rounding_stage='total'),
    sep_days, *SEP)
check('a figure that did not move is not called rounded',
      'rounded' in clean['explanation'][-1], False)

# ---------------------------------------------------------------------------
print('\n--- what is docked follows what is paid ---')

absent = (present(SEP[0], datetime.date(2026, 9, 28))
          + [Rec(datetime.date(2026, 9, 29), 'absent'),
             Rec(datetime.date(2026, 9, 30), 'absent')])
for stage, want_rate in (('rate', 885.0), ('total', 884.62)):
    b = salary.compute(
        old, policy(basis_days=26, rounding='nearest', rounding_stage=stage,
                    absence_deduction_enabled=True),
        absent, *SEP)
    check('round-on %-5s: 2 absences docked at the same rate' % stage,
          b['deduction_rate'], want_rate)
    check('round-on %-5s: and the net reflects it' % stage,
          b['net_payable'], round(23000.0 - 2 * want_rate, 2)
          if stage == 'rate' else 21231.0)

# ---------------------------------------------------------------------------
print('\n--- an unreadable setting changes nobody\'s pay ---')

odd = salary.normalise_policy({'rounding_stage': 'month-end-ish'})
check('it falls back to rounding the rate', odd['rounding_stage'], 'rate')
check('and it is a value the engine knows',
      odd['rounding_stage'] in salary.ROUNDING_STAGE, True)
check('both choices have a label',
      sorted(salary.LABELS['rounding_stage']), ['rate', 'total'])
check('and describe() names the one in force',
      ('Rounded on', salary.LABELS['rounding_stage']['total'])
      in salary.describe(policy(rounding_stage='total')), True)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The rounding lands where the employer puts it, and the default '
      'has not moved.')
