"""Regression guard: with no policy configured, the new engine must pay
exactly what the old monthly branch paid.

The old branch was:
    base_pay  = monthly_salary
    deduction = leave_balance['chargeable_days'] * leave_deduction_per_day
                (only when leave_policy_enabled and the rate is set)

Re-derived here from the same inputs and compared against the engine for
every monthly worker across several months.
"""
import sys
sys.path.insert(0, '/home/user/SmartWorker-html')
import calendar as _cal
from datetime import date
from app import app
import routes as R, models as m
from flask import g

MONTHS = [(2026, m_) for m_ in (6, 7, 8, 9, 10)]
mismatches = []
intended = []

with app.test_request_context('/'):
    admin = m.User.query.filter_by(username='demo').first()
    g.account_id = admin.account_id
    workers = m.Worker.query.filter_by(pay_type='monthly').all()
    print('monthly workers: %d' % len(workers))

    # The guarantee under test is "before an employer configures anything,
    # pay is unchanged", so the test has to create that state rather than
    # assume it. Any saved policy is lifted out and put back afterwards —
    # without this the test fails as soon as somebody uses the feature.
    from app import db as _db
    saved = m.SalaryPolicy.query.all()
    stashed = [{c.name: getattr(r, c.name) for c in m.SalaryPolicy.__table__.columns}
               for r in saved]
    if stashed:
        print('(temporarily lifting %d saved policy row(s))' % len(stashed))
        for r in saved:
            _db.session.delete(r)
        _db.session.commit()

    try:
      for year, mon in MONTHS:
        last = _cal.monthrange(year, mon)[1]
        s, e = date(year, mon, 1), date(year, mon, last)
        for w in workers:
            recs = m.AttendanceRecord.query.filter(
                m.AttendanceRecord.worker_id == w.id,
                m.AttendanceRecord.date >= s,
                m.AttendanceRecord.date <= e).all()

            # --- what the old code would have produced -------------------
            old_base = float(w.monthly_salary or 0)
            old_ded = 0.0
            if w.leave_policy_enabled and w.leave_deduction_per_day is not None:
                lb = R.calculate_leave_balance(w, s, e)
                old_ded = lb['chargeable_days'] * float(w.leave_deduction_per_day or 0)

            # --- what the engine produces now ----------------------------
            ps = R.calculate_pay_summary(w, recs, s, e)
            new_base = ps['base_pay']
            new_ded = ps['leave_deductions']

            employed_all_period = not w.join_date or w.join_date <= s
            differs = abs(old_base - new_base) > 0.011 or abs(old_ded - new_ded) > 0.011
            if differs and employed_all_period:
                # Someone employed for the whole month must be paid exactly
                # what they were paid before. Anything else is a regression.
                mismatches.append((year, mon, w.full_name, old_base, new_base, old_ded, new_ded))
            elif differs:
                # Joined during or after this month. The old code paid a full
                # salary for months before the worker even started, which is
                # the defect this feature exists to fix, so a difference here
                # is the intended new behaviour.
                intended.append((year, mon, w.full_name, old_base, new_base,
                                 w.join_date))
    finally:
        # Always put the employer's configuration back, including when a
        # check fails or the run is interrupted. A test must never be the
        # reason a live salary policy disappears.
        if stashed:
            for row in stashed:
                row.pop('id', None)
                _db.session.add(m.SalaryPolicy(**row))
            _db.session.commit()
            print('(restored %d policy row(s))' % len(stashed))

print('\n%-4s %-32s %-22s %s' % ('', 'worker', 'base (old -> new)', 'deduction (old -> new)'))
for y, mo, name, ob, nb, od, nd in mismatches:
    print('%4d-%02d %-32s %10.2f -> %-10.2f %10.2f -> %.2f' % (y, mo, name[:32], ob, nb, od, nd))

print('\n--- deliberate changes (worker not employed for the whole month) ---')
for y, mo, name, ob, nb, jd in intended:
    print('%4d-%02d %-26s joined %s   %9.2f -> %.2f' % (y, mo, name[:26], jd, ob, nb))

print('\n%d worker-months compared' % (len(MONTHS) * len(workers)))
print('   %d regressions (must be 0)' % len(mismatches))
print('   %d intended joining-date changes' % len(intended))
sys.exit(1 if mismatches else 0)
