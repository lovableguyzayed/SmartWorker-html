"""Tests for the attendance-based salary engine.

Covers the twelve scenarios the specification lists, plus leap years, month
boundaries and rounding consistency. Pure Python — no server, no database.

    python3 tests/test_salary.py
"""

import os
import sys
import calendar as _cal
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import salary


# --------------------------------------------------------------------------
# minimal stand-ins: the engine only reads these attributes
# --------------------------------------------------------------------------

class W:
    def __init__(self, monthly_salary=22000, join_date=date(2020, 1, 1)):
        self.monthly_salary = monthly_salary
        self.join_date = join_date


class R:
    def __init__(self, d, status):
        self.date = d
        self.status = status


def month(year, mon):
    last = _cal.monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last)


def attendance(start, end, absent_on=(), leave_on=(), skip_before=None):
    """Present every day in the window, except the days named absent/leave."""
    out = []
    day = start
    while day <= end:
        if skip_before and day < skip_before:
            day += timedelta(days=1)
            continue
        if day.day in absent_on:
            out.append(R(day, 'absent'))
        elif day.day in leave_on:
            out.append(R(day, 'leave'))
        else:
            out.append(R(day, 'present'))
        day += timedelta(days=1)
    return out


def policy(**over):
    p = dict(salary.DEFAULT_POLICY)
    p.update(over)
    return p


RESULTS = []


def check(name, got, want, note=''):
    ok = got == want
    RESULTS.append((ok, name, got, want, note))
    print('  %-4s %-58s got=%-12s want=%-12s %s'
          % ('PASS' if ok else 'FAIL', name, got, want, note))


# --------------------------------------------------------------------------

def test_01_joins_first_day():
    s, e = month(2026, 10)
    w = W(join_date=date(2026, 10, 1))
    r = salary.compute(w, policy(absence_deduction_enabled=True), attendance(s, e), s, e)
    check('01 joins on the 1st -> full salary', r['net_payable'], 22000.0)
    check('01 eligible days = whole month', r['eligible_days'], 31)


def test_02_joins_sixth_spec_example():
    """The worked example in the brief, Method B."""
    s, e = month(2026, 10)
    w = W(join_date=date(2026, 10, 6))
    p = policy(salary_basis='fixed', basis_days=30, rounding='up',
               paid_leave_enabled=True, monthly_leave_allowance=2,
               absence_deduction_enabled=True, joining_mode='calendar')
    recs = attendance(s, e, absent_on=(10, 11, 12, 13), skip_before=date(2026, 10, 6))
    r = salary.compute(w, p, recs, s, e)
    check('02 daily rate rounded up', r['daily_rate'], 734.0, '22000/30 = 733.33')
    check('02 exact daily rate kept', round(r['daily_rate_exact'], 2), 733.33)
    check('02 eligible days from the 6th', r['eligible_days'], 26)
    check('02 absences seen', r['absent_days'], 4)
    check('02 chargeable after 2 paid leaves', r['deduction_days'], 2.0)
    check('02 deduction amount', r['deduction_amount'], 1468.0, '2 x 734')
    check('02 gross for 26 eligible days', r['gross_eligible_salary'], 19084.0)
    check('02 net', r['net_payable'], 19084.0 - 1468.0)


def test_03_joins_fifteenth():
    s, e = month(2026, 10)
    w = W(join_date=date(2026, 10, 15))
    p = policy(rounding='up', absence_deduction_enabled=True)
    r = salary.compute(w, p, attendance(s, e, skip_before=date(2026, 10, 15)), s, e)
    check('03 eligible days from the 15th', r['eligible_days'], 17)
    check('03 gross = 17 x 734', r['gross_eligible_salary'], 17 * 734.0)


def test_04_zero_absences():
    s, e = month(2026, 10)
    r = salary.compute(W(), policy(absence_deduction_enabled=True), attendance(s, e), s, e)
    check('04 no absences -> no deduction', r['deduction_amount'], 0.0)
    check('04 no absences -> full salary', r['net_payable'], 22000.0)


def test_05_four_absences_two_paid_leaves():
    s, e = month(2026, 10)
    p = policy(rounding='up', monthly_leave_allowance=2, paid_leave_enabled=True,
               absence_deduction_enabled=True)
    r = salary.compute(W(), p, attendance(s, e, absent_on=(7, 8, 9, 10)), s, e)
    check('05 chargeable days', r['deduction_days'], 2.0)
    check('05 deduction', r['deduction_amount'], 1468.0)
    check('05 net = 22000 - 1468', r['net_payable'], 20532.0, 'the brief"s figure')


def test_06_paid_leave_disabled():
    s, e = month(2026, 10)
    p = policy(rounding='up', monthly_leave_allowance=2, paid_leave_enabled=False,
               absence_deduction_enabled=True)
    r = salary.compute(W(), p, attendance(s, e, absent_on=(7, 8, 9, 10)), s, e)
    check('06 all four absences charged', r['deduction_days'], 4.0)
    check('06 deduction', r['deduction_amount'], 2936.0, '4 x 734')
    check('06 net', r['net_payable'], 22000.0 - 2936.0)


def test_07_rounding_disabled():
    s, e = month(2026, 10)
    p = policy(rounding='none', monthly_leave_allowance=0, absence_deduction_enabled=True)
    r = salary.compute(W(), p, attendance(s, e, absent_on=(7, 8)), s, e)
    check('07 unrounded daily rate', r['daily_rate'], 733.33)
    check('07 deduction uses the exact rate', r['deduction_amount'], 1466.66)


def test_08_rounding_up_and_friends():
    s, e = month(2026, 10)
    for mode, want in (('up', 734.0), ('down', 733.0), ('nearest', 733.0), ('none', 733.33)):
        r = salary.compute(W(), policy(rounding=mode), attendance(s, e), s, e)
        check('08 rounding %-8s' % mode, r['daily_rate'], want)


def test_09_basis_fixed_vs_calendar():
    s, e = month(2026, 10)                       # 31 days
    r_fixed = salary.compute(W(), policy(salary_basis='fixed', basis_days=30,
                                         rounding='none'), attendance(s, e), s, e)
    r_cal = salary.compute(W(), policy(salary_basis='calendar', rounding='none'),
                           attendance(s, e), s, e)
    check('09 fixed-30 basis rate', r_fixed['daily_rate'], 733.33)
    check('09 calendar basis rate (31 days)', r_cal['daily_rate'], 709.68)
    check('09 calendar basis days', r_cal['basis_days'], 31)


def test_10_joins_in_february_and_leap_year():
    for year, length in ((2026, 28), (2028, 29)):
        s, e = month(year, 2)
        w = W(join_date=date(year, 2, 10))
        p = policy(salary_basis='calendar', rounding='none', absence_deduction_enabled=True)
        r = salary.compute(w, p, attendance(s, e, skip_before=date(year, 2, 10)), s, e)
        check('10 Feb %d month length' % year, r['total_calendar_days'], length)
        check('10 Feb %d eligible from the 10th' % year, r['eligible_days'], length - 9)
        check('10 Feb %d basis = month length' % year, r['basis_days'], length)


def test_11_joins_in_a_31_day_month():
    s, e = month(2026, 7)                        # July, 31 days
    w = W(join_date=date(2026, 7, 20))
    p = policy(salary_basis='calendar', rounding='nearest', absence_deduction_enabled=True)
    r = salary.compute(w, p, attendance(s, e, skip_before=date(2026, 7, 20)), s, e)
    check('11 July eligible days', r['eligible_days'], 12)
    check('11 July rate on 31-day basis', r['daily_rate'], 710.0)
    check('11 July gross', r['gross_eligible_salary'], 12 * 710.0)


def test_12_method_a_attendance_based():
    """Method A pays attended days only; absences must not be charged twice."""
    s, e = month(2026, 10)
    w = W(join_date=date(2026, 10, 6))
    p = policy(joining_mode='attendance', rounding='up', absence_deduction_enabled=True,
               monthly_leave_allowance=0)
    recs = attendance(s, e, absent_on=(10, 11, 12, 13), skip_before=date(2026, 10, 6))
    r = salary.compute(w, p, recs, s, e)
    check('12 attended days paid', r['payable_present_days'], 22, '26 eligible - 4 absent')
    check('12 gross = 22 x 734', r['gross_eligible_salary'], 22 * 734.0)
    check('12 no second deduction', r['deduction_amount'], 0.0)


# -------------------------- correctness guards ----------------------------

def test_13_absences_before_joining_never_charged():
    s, e = month(2026, 10)
    w = W(join_date=date(2026, 10, 6))
    p = policy(rounding='up', absence_deduction_enabled=True, monthly_leave_allowance=0)
    # absent on the 2nd and 3rd — before this worker existed in the company
    recs = attendance(s, e, absent_on=(2, 3))
    r = salary.compute(w, p, recs, s, e)
    check('13 pre-joining absences ignored', r['absent_days'], 0)
    check('13 pre-joining records counted separately', r['records_before_joining'], 5)
    check('13 no deduction', r['deduction_amount'], 0.0)


def test_14_absence_deduction_disabled_is_the_old_behaviour():
    s, e = month(2026, 10)
    r = salary.compute(W(), policy(absence_deduction_enabled=False),
                       attendance(s, e, absent_on=(1, 2, 3, 4, 5)), s, e)
    check('14 absences cost nothing when disabled', r['net_payable'], 22000.0)
    check('14 absences still reported', r['absent_days'], 5)


def test_15_approved_leave_not_double_charged():
    s, e = month(2026, 10)
    p = policy(rounding='up', monthly_leave_allowance=2, paid_leave_enabled=True,
               absence_deduction_enabled=True)
    r = salary.compute(W(), p, attendance(s, e, leave_on=(5, 6), absent_on=(7, 8)), s, e)
    check('15 leave consumes the allowance first', r['paid_leave_used'], 2.0)
    check('15 both absences then chargeable', r['deduction_days'], 2.0)
    check('15 deduction', r['deduction_amount'], 1468.0)


def test_16_net_never_negative():
    s, e = month(2026, 10)
    p = policy(rounding='up', absence_deduction_enabled=True, monthly_leave_allowance=0)
    r = salary.compute(W(monthly_salary=5000), p,
                       attendance(s, e, absent_on=tuple(range(1, 32))), s, e)
    check('16 net floored at zero', r['net_payable'], 0.0)


def test_17_joined_after_the_period():
    s, e = month(2026, 10)
    w = W(join_date=date(2026, 11, 3))
    r = salary.compute(w, policy(absence_deduction_enabled=True), [], s, e)
    check('17 not yet employed -> no eligible days', r['eligible_days'], 0)
    check('17 not yet employed -> nothing payable', r['net_payable'], 0.0)


def test_18_carry_forward():
    s, e = month(2026, 10)
    base = policy(rounding='up', monthly_leave_allowance=1, paid_leave_enabled=True,
                  absence_deduction_enabled=True, leave_carry_forward=True)
    recs = attendance(s, e, absent_on=(7, 8, 9))
    with_cf = salary.compute(W(), base, recs, s, e, carried_leave_balance=2)
    without = salary.compute(W(), dict(base, leave_carry_forward=False), recs, s, e,
                             carried_leave_balance=2)
    check('18 carry-forward absorbs more', with_cf['deduction_days'], 0.0)
    check('18 without carry-forward', without['deduction_days'], 2.0)


def test_19_rounding_is_consistent_between_rate_and_deduction():
    """A deduction must be an exact multiple of the rate the report shows."""
    s, e = month(2026, 10)
    bad = []
    for mode in salary.ROUNDING:
        p = policy(rounding=mode, absence_deduction_enabled=True, monthly_leave_allowance=0)
        r = salary.compute(W(), p, attendance(s, e, absent_on=(1, 2, 3)), s, e)
        if round(r['daily_rate'] * r['deduction_days'], 2) != r['deduction_amount']:
            bad.append(mode)
    check('19 deduction == rate x days for every rounding', bad, [])


def test_20_explanation_always_reaches_the_final_figure():
    s, e = month(2026, 10)
    p = policy(rounding='up', monthly_leave_allowance=2, absence_deduction_enabled=True)
    r = salary.compute(W(), p, attendance(s, e, absent_on=(7, 8, 9, 10)), s, e)
    last = r['explanation'][-1]
    # The figure is grouped the Indian way now — the explanation is read by
    # the worker on his payslip, so it carries a rupee like everything else.
    check('20 explanation ends with the payable figure',
          last.startswith('Final payable:') and '₹20,532' in last, True, last)
    check('20 and the explanation prints no bare float',
          [n for n in r['explanation'] if __import__('re').search(r'(?<![\d,.])\d{4,}\.\d', n)],
          [], r['explanation'][-1])


if __name__ == '__main__':
    print('salary engine — specification scenarios\n')
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            print(fn.__doc__.splitlines()[0] if fn.__doc__ else name)
            fn()
            print()
    failed = [r for r in RESULTS if not r[0]]
    print('=' * 72)
    print('%d checks, %d failed' % (len(RESULTS), len(failed)))
    for ok, name, got, want, note in failed:
        print('   FAILED %s: got %r want %r %s' % (name, got, want, note))
    sys.exit(1 if failed else 0)
