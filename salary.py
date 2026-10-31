"""Attendance-based salary calculation for fixed monthly-salary workers.

Why this module exists
----------------------
The payroll engine in routes.py paid a monthly worker their full salary and
deducted only for *leave* days beyond quota. An absent day cost nothing, and a
worker who joined on the 6th was paid the whole month. Employers need to set
their own policy, so the rules live here as configuration rather than as
assumptions baked into the pay run.

Design notes
------------
* Everything is a pure function of (worker, policy, attendance). No database
  access, no request context — which is what makes the whole policy matrix
  testable without a server.
* Money is Decimal end to end. Floats cannot hold 22000/30 exactly, and a
  0.004 error repeated across a 200-worker payroll is a real discrepancy.
  Decimal values only become floats at the boundary, where the rest of the
  app expects them.
* Nothing here is deducted for a day before the worker joined. That rule is
  enforced in one place — `eligible_days` — rather than at each call site.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from money import money as _rupees   # one way to write an amount

# ---------------------------------------------------------------------------
# Policy vocabulary. Stored as these exact strings, so changing one is a
# migration, not an edit.
# ---------------------------------------------------------------------------

SALARY_BASIS = ('fixed', 'calendar')          # fixed N days, or the real month length
ROUNDING = ('none', 'nearest', 'up', 'down')
JOINING_MODE = ('calendar', 'attendance')     # spec's Method B and Method A
CALC_METHOD = ('salary_minus_deductions', 'rate_times_payable_days')

#: What a day with no attendance row at all is worth.
#:
#: 'paid'   the day costs nothing. Only a day somebody marked Absent is
#:          deducted. This is what the app has always done, and it is a
#:          real policy — plenty of employers pay the salary and dock only
#:          what they deliberately record.
#: 'absent' a past day nobody marked is charged like any other absence.
#:
#: The difference is not small and it is silent: a month with five days
#: nobody got round to marking paid out in full, measured at ₹23,000
#: against ₹20,345 for the same five days marked Absent. Default stays
#: 'paid' so no existing account's figures move until an employer picks
#: the other one.
UNMARKED_DAYS = ('paid', 'absent')

#: Applied when neither the worker nor the company has configured anything.
#: Chosen to reproduce the behaviour the app had before this module existed:
#: absence deduction off, so no existing worker's pay changes until an
#: employer turns it on deliberately.
DEFAULT_POLICY = {
    'salary_basis': 'fixed',
    'basis_days': 30,
    'rounding': 'nearest',
    'joining_mode': 'calendar',
    'paid_leave_enabled': True,
    'monthly_leave_allowance': 0.0,
    'leave_carry_forward': False,
    'absence_deduction_enabled': False,
    'calculation_method': 'salary_minus_deductions',
    'unmarked_days': 'paid',
    #: Rupees deducted per chargeable day. None = derive it from the salary
    #: (salary / basis, rounded by the policy), which is what the
    #: specification asks for. It is not None by default because workers
    #: configured before this engine existed carry their own
    #: leave_deduction_per_day, and silently re-rating their deductions to
    #: the derived figure would change what people are paid. seed_from_worker
    #: carries that value across; an employer clearing it opts into the
    #: derived rate.
    'deduction_rate': None,
}

_TWOPLACES = Decimal('0.01')


def _dec(value) -> Decimal:
    """Money as Decimal, via str so float noise never enters the arithmetic."""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal) -> float:
    """Decimal out to the float the rest of the app stores and renders."""
    return float(value.quantize(_TWOPLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Policy resolution
# ---------------------------------------------------------------------------

POLICY_FIELDS = tuple(DEFAULT_POLICY.keys())


def normalise_policy(raw) -> dict:
    """Coerce a stored row, a dict, or None into a complete, valid policy.

    Unknown or missing values fall back to the default rather than raising:
    a payroll run must not fail because one dropdown holds something
    unexpected.
    """
    policy = dict(DEFAULT_POLICY)
    if raw is None:
        return policy

    get = raw.get if isinstance(raw, dict) else lambda k, d=None: getattr(raw, k, d)
    for field in POLICY_FIELDS:
        value = get(field, None)
        if value is None:
            continue
        policy[field] = value

    if policy['salary_basis'] not in SALARY_BASIS:
        policy['salary_basis'] = DEFAULT_POLICY['salary_basis']
    if policy['rounding'] not in ROUNDING:
        policy['rounding'] = DEFAULT_POLICY['rounding']
    if policy['joining_mode'] not in JOINING_MODE:
        policy['joining_mode'] = DEFAULT_POLICY['joining_mode']
    if policy['calculation_method'] not in CALC_METHOD:
        policy['calculation_method'] = DEFAULT_POLICY['calculation_method']
    if policy['unmarked_days'] not in UNMARKED_DAYS:
        policy['unmarked_days'] = DEFAULT_POLICY['unmarked_days']

    try:
        policy['basis_days'] = max(1, min(31, int(policy['basis_days'])))
    except (TypeError, ValueError):
        policy['basis_days'] = DEFAULT_POLICY['basis_days']
    try:
        policy['monthly_leave_allowance'] = max(0.0, float(policy['monthly_leave_allowance']))
    except (TypeError, ValueError):
        policy['monthly_leave_allowance'] = 0.0
    if policy['deduction_rate'] is not None:
        try:
            policy['deduction_rate'] = max(0.0, float(policy['deduction_rate']))
        except (TypeError, ValueError):
            policy['deduction_rate'] = None

    for flag in ('paid_leave_enabled', 'leave_carry_forward', 'absence_deduction_enabled'):
        policy[flag] = bool(policy[flag])
    return policy


# ---------------------------------------------------------------------------
# The pieces of the calculation
# ---------------------------------------------------------------------------

def basis_days_for(policy: dict, period_start: date, period_end: date) -> int:
    """Days the monthly salary is considered to cover.

    'calendar' uses the real length of the month, so February pays the same
    monthly salary over 28 (or 29) days and a daily rate is correspondingly
    higher. 'fixed' divides by a constant — usually 30 — which is what most
    Indian site payrolls do.
    """
    if policy['salary_basis'] == 'calendar':
        return _cal.monthrange(period_start.year, period_start.month)[1]
    return int(policy['basis_days'])


def daily_rate(monthly_salary, policy: dict, period_start: date, period_end: date):
    """Return (exact_rate, rounded_rate) as Decimals.

    The exact rate is kept so the report can show both — the employer wants to
    see that 22000/30 is 733.33 before the policy rounds it to 734.
    """
    basis = basis_days_for(policy, period_start, period_end)
    exact = _dec(monthly_salary) / Decimal(basis)

    mode = policy['rounding']
    if mode == 'none':
        rounded = exact.quantize(_TWOPLACES, rounding=ROUND_HALF_UP)
    elif mode == 'up':
        rounded = exact.quantize(Decimal('1'), rounding=ROUND_CEILING)
    elif mode == 'down':
        rounded = exact.quantize(Decimal('1'), rounding=ROUND_FLOOR)
    else:                                    # 'nearest'
        rounded = exact.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return exact, rounded


def eligible_window(worker_join_date, period_start: date, period_end: date):
    """The slice of the payroll period the worker was actually employed for.

    Returns (start, end, eligible_days). A worker who joined after the period
    ends gets zero days, and one who joined before it started gets the whole
    period — the joining date never *adds* days.
    """
    start = period_start
    if worker_join_date and worker_join_date > period_start:
        start = worker_join_date
    if start > period_end:
        return start, period_end, 0
    return start, period_end, (period_end - start).days + 1


def split_attendance(records, window_start: date, window_end: date) -> dict:
    """Count attendance inside the eligible window only.

    Anything dated before the worker joined is ignored outright, which is the
    single rule that stops a pre-joining absence from being deducted.
    """
    counts = {'present': 0, 'late': 0, 'absent': 0, 'leave': 0,
              'before_joining': 0, 'outside_period': 0}
    for rec in records:
        if rec.date < window_start:
            if rec.date >= window_start.replace(day=1):
                counts['before_joining'] += 1
            else:
                counts['outside_period'] += 1
            continue
        if rec.date > window_end:
            counts['outside_period'] += 1
            continue
        if rec.status in counts:
            counts[rec.status] += 1
    counts['payable_present'] = counts['present'] + counts['late']
    return counts


def apply_leave_allowance(absent_days: int, leave_days: int, policy: dict,
                          carried_balance: float = 0.0) -> dict:
    """Decide how many absent days are actually chargeable.

    The spec treats the monthly allowance as covering *absences*: with an
    allowance of 2 and 4 absences, 2 are deducted. Days already recorded as
    approved leave consume the same allowance first, because an approved paid
    leave must not also be charged — otherwise the same day is deducted twice,
    once as leave and once as absence.
    """
    if not policy['paid_leave_enabled']:
        return {
            'allowance': 0.0,
            'carried_in': 0.0,
            'available': 0.0,
            'leave_covered': 0.0,
            'absence_covered': 0.0,
            'chargeable_absences': float(absent_days),
            'chargeable_leaves': float(leave_days),
            'unused_allowance': 0.0,
        }

    allowance = float(policy['monthly_leave_allowance'])
    carried_in = float(carried_balance) if policy['leave_carry_forward'] else 0.0
    available = allowance + max(carried_in, 0.0)

    leave_covered = min(float(leave_days), available)
    available -= leave_covered

    absence_covered = min(float(absent_days), available)
    available -= absence_covered

    return {
        'allowance': allowance,
        'carried_in': carried_in,
        'available': allowance + max(carried_in, 0.0),
        'leave_covered': leave_covered,
        'absence_covered': absence_covered,
        'chargeable_absences': float(absent_days) - absence_covered,
        'chargeable_leaves': float(leave_days) - leave_covered,
        'unused_allowance': available,
    }


# ---------------------------------------------------------------------------
# The whole calculation
# ---------------------------------------------------------------------------

def compute(worker, policy, records, period_start: date, period_end: date,
            carried_leave_balance: float = 0.0,
            unmarked_days: int = 0) -> dict:
    """Full monthly salary breakdown for one worker.

    Every number the report needs is returned, along with `explanation`: the
    ordered sentences that say how the figure was reached. The report renders
    those rather than re-deriving the arithmetic, so the explanation can never
    drift from the calculation.

    `unmarked_days` is how many days of this period are in the past, fall
    inside this worker's employment, are not a closure, and carry no
    attendance row at all. It is counted by the caller and passed in, not
    worked out here, for the reason the rest of this module keeps its
    distance: today's date and the closure calendar are request-scoped, and
    a test has to be able to hand this function known figures. It is used
    only when the policy says unmarked days are absences; the default
    policy ignores it entirely.
    """
    policy = normalise_policy(policy)
    monthly_salary = _dec(getattr(worker, 'monthly_salary', 0) or 0)

    total_calendar_days = _cal.monthrange(period_start.year, period_start.month)[1]
    basis = basis_days_for(policy, period_start, period_end)
    exact_rate, rounded_rate = daily_rate(monthly_salary, policy, period_start, period_end)

    join_date = getattr(worker, 'join_date', None)
    win_start, win_end, eligible_days = eligible_window(join_date, period_start, period_end)
    joined_midway = bool(join_date and period_start < join_date <= period_end)

    counts = split_attendance(records, win_start, win_end)

    # Days nobody marked, charged as absences when the employer has asked
    # for that. Added before the leave allowance rather than after, so a
    # forgotten day is covered by the month's paid leave exactly like a day
    # somebody typed Absent into — otherwise the allowance would protect
    # the deliberate absence and not the accidental one, which is backwards.
    #
    # Ignored for a joining month under joining_mode 'attendance': that
    # branch pays only for attended days, so a day with no row is already
    # unpaid and charging it again would deduct it twice.
    charge_unmarked = (policy['unmarked_days'] == 'absent'
                       and unmarked_days > 0
                       and not (policy['joining_mode'] == 'attendance' and joined_midway))
    absent_for_allowance = counts['absent'] + (unmarked_days if charge_unmarked else 0)

    leave_info = apply_leave_allowance(absent_for_allowance, counts['leave'], policy,
                                       carried_leave_balance)

    # Absence deduction can be switched off entirely; when it is, absences are
    # recorded in the report but cost nothing.
    if policy['absence_deduction_enabled']:
        deduction_days = _dec(leave_info['chargeable_absences']) + _dec(leave_info['chargeable_leaves'])
    else:
        deduction_days = _dec(leave_info['chargeable_leaves'])

    explanation = []

    # --- gross eligible salary -------------------------------------------
    if eligible_days <= 0:
        # Joined after this period closed, so there is no employment to pay
        # for. Checked before everything else: without this the fall-through
        # branch below paid a full month's salary to someone who had not
        # started yet.
        gross = Decimal('0')
        deduction_days = Decimal('0')
        explanation.append(
            'Joining date %s falls after this period, so no salary is payable.'
            % (join_date.strftime('%d %b %Y') if join_date else '-')
        )
    elif policy['joining_mode'] == 'attendance' and joined_midway:
        # Method A: pay only for days actually worked since joining.
        payable_days = _dec(counts['payable_present'])
        gross = rounded_rate * payable_days
        explanation.append(
            'Joined %s. Paid for %g attended day(s) from the joining date at '
            '%s/day.' % (join_date.strftime('%d %b %Y'), float(payable_days),
                         _rupees(rounded_rate))
        )
        # Absences are already excluded by only paying attended days; charging
        # them again would deduct the same day twice.
        deduction_days = Decimal('0')
    elif joined_midway:
        # Method B: pro-rate the month by eligible calendar days, then deduct.
        gross = rounded_rate * Decimal(eligible_days)
        explanation.append(
            'Joined %s, so %d of %d day(s) are eligible: %d x %s = %s.'
            % (join_date.strftime('%d %b %Y'), eligible_days, total_calendar_days,
               eligible_days, _rupees(rounded_rate),
               _rupees(rounded_rate * Decimal(eligible_days)))
        )
    elif policy['calculation_method'] == 'rate_times_payable_days':
        payable_days = Decimal(basis) - deduction_days
        gross = rounded_rate * Decimal(basis)
        explanation.append(
            'Daily rate %s x %d day(s) basis = %s.'
            % (_rupees(rounded_rate), basis, _rupees(gross))
        )
    else:
        gross = monthly_salary
        explanation.append('Full monthly salary %s applies.'
                           % _rupees(monthly_salary))

    # --- deductions --------------------------------------------------------
    # A configured rate wins over the derived one, so a worker set up before
    # this engine existed keeps being deducted at the figure their record
    # already carries.
    if policy['deduction_rate'] is not None:
        deduction_rate = _dec(policy['deduction_rate'])
    else:
        deduction_rate = rounded_rate
    deduction_amount = deduction_rate * deduction_days
    if deduction_days > 0:
        explanation.append(
            'Deduction: %g day(s) x %s = %s.'
            % (float(deduction_days), _rupees(deduction_rate),
               _rupees(deduction_amount))
        )
    if policy['paid_leave_enabled'] and leave_info['allowance']:
        explanation.append(
            'Paid leave allowance %g day(s) covered %g absence(s) and %g leave(s).'
            % (leave_info['allowance'], leave_info['absence_covered'],
               leave_info['leave_covered'])
        )
    if not policy['absence_deduction_enabled'] and counts['absent']:
        explanation.append(
            'Absence deduction is switched off, so %d absent day(s) were not charged.'
            % counts['absent']
        )
    # Said either way round, because a day nobody marked is worth knowing
    # about whichever answer the employer has chosen for it.
    if charge_unmarked:
        explanation.append(
            '%d day(s) of this month were never marked and are charged as '
            'absences.' % unmarked_days
        )
    elif unmarked_days:
        explanation.append(
            '%d day(s) of this month were never marked. They are paid, '
            'because unmarked days are set to count as paid.' % unmarked_days
        )
    if counts['before_joining']:
        explanation.append(
            '%d attendance record(s) before the joining date were ignored.'
            % counts['before_joining']
        )

    net = gross - deduction_amount
    if net < 0:
        net = Decimal('0')
        explanation.append('Deductions exceeded the eligible salary; net floored at 0.')
    explanation.append('Final payable: %s - %s = %s.'
                       % (_rupees(gross), _rupees(deduction_amount), _rupees(net)))

    return {
        # identity / inputs
        'monthly_salary': _money(monthly_salary),
        'salary_basis': policy['salary_basis'],
        'basis_days': basis,
        'rounding': policy['rounding'],
        'join_date': join_date,
        'joined_midway': joined_midway,
        'period_start': period_start,
        'period_end': period_end,
        # rates
        'daily_rate_exact': float(exact_rate.quantize(Decimal('0.0001'))),
        'daily_rate': _money(rounded_rate),
        'deduction_rate': _money(deduction_rate),
        'deduction_rate_is_derived': policy['deduction_rate'] is None,
        # days
        'total_calendar_days': total_calendar_days,
        'eligible_days': eligible_days,
        'present_days': counts['present'],
        'late_days': counts['late'],
        'payable_present_days': counts['payable_present'],
        'absent_days': counts['absent'],
        'leave_days': counts['leave'],
        # Days of this period with no attendance row at all, and how many of
        # them this policy charged for. Both are reported whatever the
        # policy says, so the payslip can show "6 days were never marked"
        # on an account that pays for them as readily as on one that does
        # not — the count is a fact about the month either way.
        'unmarked_days': unmarked_days,
        'charged_unmarked_days': unmarked_days if charge_unmarked else 0,
        'unmarked_days_policy': policy['unmarked_days'],
        'records_before_joining': counts['before_joining'],
        # leave
        'leave_allowance': leave_info['allowance'],
        'leave_carried_in': leave_info['carried_in'],
        'paid_leave_used': leave_info['leave_covered'] + leave_info['absence_covered'],
        'unpaid_leave_days': leave_info['chargeable_leaves'],
        'unused_leave_allowance': leave_info['unused_allowance'],
        # money
        'deduction_days': float(deduction_days),
        'deduction_amount': _money(deduction_amount),
        'gross_eligible_salary': _money(gross),
        'net_payable': _money(net),
        # provenance
        'policy': policy,
        'explanation': explanation,
    }


# ---------------------------------------------------------------------------
# Database-facing helpers. Kept at the bottom so everything above stays a pure
# function of its arguments and remains testable without an app context.
# ---------------------------------------------------------------------------

def resolve_policy(worker, company_policy=None, worker_policy=None) -> dict:
    """Layer worker override over company default over the built-in default.

    Only fields the override actually sets take precedence; an override row
    that leaves a field as None inherits the company value, so an employer can
    change one rule for one person without restating the whole policy.
    """
    base = normalise_policy(company_policy)
    if worker_policy is None:
        return base
    merged = dict(base)
    for field in POLICY_FIELDS:
        value = getattr(worker_policy, field, None)
        if value is not None:
            merged[field] = value
    return normalise_policy(merged)


def policy_differences(before: dict, after: dict):
    """(field, old, new) for each rule that changed — the audit log's input."""
    before = normalise_policy(before)
    after = normalise_policy(after)
    return [(f, before[f], after[f]) for f in POLICY_FIELDS if before[f] != after[f]]


#: Labels for the settings screen and the report, so the stored value and the
#: words the employer reads can never drift apart.
LABELS = {
    'salary_basis': {'fixed': 'Fixed days', 'calendar': 'Actual calendar days'},
    'rounding': {'none': 'No rounding', 'nearest': 'Nearest rupee',
                 'up': 'Always round up', 'down': 'Always round down'},
    'joining_mode': {'calendar': 'Calendar days from joining date',
                     'attendance': 'Actual attendance since joining'},
    'calculation_method': {'salary_minus_deductions': 'Monthly salary minus deductions',
                           'rate_times_payable_days': 'Daily rate x payable days'},
    'unmarked_days': {'paid': 'Paid, like a normal working day',
                      'absent': 'Counted as absent'},
}


def describe(policy: dict) -> list:
    """Policy as (label, value) pairs for display."""
    p = normalise_policy(policy)
    basis = LABELS['salary_basis'][p['salary_basis']]
    if p['salary_basis'] == 'fixed':
        basis = '%s (%d)' % (basis, p['basis_days'])
    return [
        ('Salary basis', basis),
        ('Daily rate rounding', LABELS['rounding'][p['rounding']]),
        ('Mid-month joining', LABELS['joining_mode'][p['joining_mode']]),
        ('Paid leave', ('%g day(s) per month' % p['monthly_leave_allowance'])
                       if p['paid_leave_enabled'] else 'Disabled'),
        ('Leave carry-forward', 'On' if p['leave_carry_forward'] else 'Off'),
        ('Absence deduction', 'On' if p['absence_deduction_enabled'] else 'Off'),
        ('Calculation method', LABELS['calculation_method'][p['calculation_method']]),
        ('Days nobody marked', LABELS['unmarked_days'][p['unmarked_days']]),
    ]


def seed_from_worker(worker) -> dict:
    """Policy implied by a worker's own pre-existing fields.

    Workers configured before salary policies existed already carry a leave
    quota and a per-day deduction. Using those as the starting point means
    turning this feature on changes nobody's pay until an employer edits a
    rule on purpose.
    """
    seeded = dict(DEFAULT_POLICY)
    allowance = getattr(worker, 'allowed_leaves_per_month', None)
    if allowance is not None:
        seeded['monthly_leave_allowance'] = float(allowance or 0)
    seeded['paid_leave_enabled'] = bool(getattr(worker, 'leave_policy_enabled', True))
    # The behaviour this replaces accrued unused quota from the joining date
    # and spent it before charging anything, so a legacy worker keeps that.
    # A company policy saved by the employer overrides it.
    seeded['leave_carry_forward'] = True
    rate = getattr(worker, 'leave_deduction_per_day', None)
    if rate:
        seeded['deduction_rate'] = float(rate)
    basis = getattr(worker, 'monthly_working_days', None)
    if basis:
        seeded['basis_days'] = int(basis)
    return seeded
