"""One worker's running account, month by month.

Payroll answers "what is this month worth". It does not answer the
question a labourer actually asks, which is "how much is still mine".

Those are different questions whenever a month closes without being paid —
and on a site that is most months. Wages are drawn in pieces as they are
needed and settled when there is cash, so an unpaid August has to still be
visible in October, and every amount taken since has to count against it.
Before this, each month was computed in isolation: an August that was never
paid appeared nowhere afterwards, and the only way to know what a worker
was owed was to add up the months by hand.

The arithmetic, per month:

    closing = opening + earned - drawn - settled

  earned   what the month was worth, bonuses included — gross, before any
           advance, because an advance is money received and not a change
           in what the work was worth
  drawn    advances, loans and recoveries taken that month, which are cash
           already in the worker's hand
  settled  the month's wages actually handed over, which is what marking a
           payroll month Paid means

A month marked Paid therefore moves the balance by earned - drawn - (earned
- drawn) = zero, which is the point: settling a month should leave nothing
behind. A month left pending adds whatever was not drawn.
"""
import calendar as _cal
from datetime import date

import models
from models import (AttendanceRecord, PayrollRecord, WorkerTransaction,
                    TRANSACTION_DEDUCTION_TYPES)


def _month_range(year, month):
    return (date(year, month, 1),
            date(year, month, _cal.monthrange(year, month)[1]))


def months_between(start, end):
    """Every (year, month) from start's month to end's month, inclusive."""
    y, mth = start.year, start.month
    while (y, mth) <= (end.year, end.month):
        yield y, mth
        mth += 1
        if mth > 12:
            y, mth = y + 1, 1


def build(worker, upto=None, compute_month=None):
    """The worker's statement, oldest month first, plus the totals.

    `compute_month(worker, year, month, records)` returns this month's
    (gross, deductions, net). It is passed in rather than imported so this
    module stays free of the request-scoped payroll code, and so a test can
    hand it known figures.
    """
    if not worker or not worker.join_date:
        return {'rows': [], 'earned': 0.0, 'drawn': 0.0, 'settled': 0.0,
                'outstanding': 0.0}

    upto = upto or date.today()
    if worker.join_date > upto:
        return {'rows': [], 'earned': 0.0, 'drawn': 0.0, 'settled': 0.0,
                'outstanding': 0.0}

    first, last = _month_range(worker.join_date.year, worker.join_date.month)
    _, span_end = _month_range(upto.year, upto.month)

    records = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker.id,
        AttendanceRecord.date >= first,
        AttendanceRecord.date <= span_end,
    ).order_by(AttendanceRecord.date).all()
    by_month = {}
    for r in records:
        by_month.setdefault((r.date.year, r.date.month), []).append(r)

    # Only the deduction kinds are "drawn": a bonus is already inside the
    # month's gross, and counting it here as well would pay it twice.
    txns = WorkerTransaction.query.filter(
        WorkerTransaction.worker_id == worker.id,
        WorkerTransaction.date >= first,
        WorkerTransaction.date <= span_end,
        WorkerTransaction.status != 'cancelled',
    ).order_by(WorkerTransaction.date).all()
    drawn_by_month = {}
    draws_by_month = {}
    for t in txns:
        if t.txn_type not in TRANSACTION_DEDUCTION_TYPES:
            continue
        key = (t.date.year, t.date.month)
        drawn_by_month[key] = drawn_by_month.get(key, 0.0) + float(t.amount or 0)
        draws_by_month.setdefault(key, []).append(t)

    paid = {(p.year, p.month): p for p in PayrollRecord.query.filter(
        PayrollRecord.worker_id == worker.id,
        PayrollRecord.status == 'paid').all()}

    rows = []
    balance = 0.0
    earned_total = drawn_total = settled_total = 0.0
    for year, month in months_between(worker.join_date, upto):
        key = (year, month)
        gross, _deductions, _net = compute_month(
            worker, year, month, by_month.get(key, []))
        gross = round(float(gross or 0), 2)
        drawn = round(drawn_by_month.get(key, 0.0), 2)

        record = paid.get(key)
        # What was handed over when the month was settled. Read from the
        # saved row rather than recomputed, so a later policy change cannot
        # rewrite a month that is already closed.
        settled = round(float(record.net_pay or 0), 2) if record else 0.0

        opening = balance
        balance = round(opening + gross - drawn - settled, 2)
        earned_total += gross
        drawn_total += drawn
        settled_total += settled

        rows.append({
            'year': year, 'month': month,
            'label': '%s %d' % (_cal.month_name[month], year),
            'opening': round(opening, 2),
            'earned': gross,
            'drawn': drawn,
            'draws': draws_by_month.get(key, []),
            'settled': settled,
            'paid': record is not None,
            'closing': balance,
        })

    return {
        'rows': rows,
        'earned': round(earned_total, 2),
        'drawn': round(drawn_total, 2),
        'settled': round(settled_total, 2),
        'outstanding': round(balance, 2),
    }
