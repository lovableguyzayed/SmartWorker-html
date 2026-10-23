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
  drawn    advances, loans and recoveries applied to this month, which are
           cash already in the worker's hand
  settled  wages handed over against this month: what marking a payroll
           month paid records, plus any wage_payment transaction

Where a payment lands
---------------------
`allocation` decides, and the two answers differ:

  'month'        a payment belongs to the month it is dated in. A crusher
                 that pays a month at a time works this way.
  'oldest_first' a payment clears the oldest month still owed and spills
                 forward into the next. A crusher that owes August and
                 hands over ₹20,000 in October is clearing August, and
                 showing that money against October instead leaves August
                 looking untouched while October looks nearly settled —
                 both wrong, and wrong in opposite directions.

Only money handed over is allocated. What a month *earned* is fixed by the
attendance in it and never moves.

A month whose closing balance reaches zero is settled, and the statement
says so from the figures rather than from a status column — a badge that
can disagree with the numbers printed beside it is worse than no badge.
"""
import calendar as _cal
from datetime import date

from models import (AttendanceRecord, PayrollRecord, WorkerTransaction,
                    TRANSACTION_DEDUCTION_TYPES, TRANSACTION_SETTLEMENT_TYPES)

#: The two house rules. 'month' is what the app did before the choice
#: existed, so it stays the default everywhere.
ALLOCATION_MODES = ('month', 'oldest_first')

#: Floats to two decimal places: ₹23,000 settled against ₹22,999.999999 is
#: settled. Everything that asks "is this month clear" uses this.
EPSILON = 0.005


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


def _empty():
    return {'rows': [], 'earned': 0.0, 'drawn': 0.0, 'settled': 0.0,
            'outstanding': 0.0, 'allocation': 'month',
            'oldest_open': None, 'open_months': 0}


def build(worker, upto=None, compute_month=None, allocation='month'):
    """The worker's statement, oldest month first, plus the totals.

    `compute_month(worker, year, month, records)` returns this month's
    (gross, deductions, net). It is passed in rather than imported so this
    module stays free of the request-scoped payroll code, and so a test can
    hand it known figures.
    """
    if not worker or not worker.join_date:
        return _empty()
    if allocation not in ALLOCATION_MODES:
        # An unreadable setting must not change anybody's figures.
        allocation = 'month'

    upto = upto or date.today()
    if worker.join_date > upto:
        return dict(_empty(), allocation=allocation)

    first, _ = _month_range(worker.join_date.year, worker.join_date.month)
    _, span_end = _month_range(upto.year, upto.month)

    records = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker.id,
        AttendanceRecord.date >= first,
        AttendanceRecord.date <= span_end,
    ).order_by(AttendanceRecord.date).all()
    by_month = {}
    for r in records:
        by_month.setdefault((r.date.year, r.date.month), []).append(r)

    # Deductions and wage payments are both money handed over, and both are
    # allocated. Earnings are not: a bonus is already inside the month's
    # gross, and counting it here as well would pay it twice.
    txns = WorkerTransaction.query.filter(
        WorkerTransaction.worker_id == worker.id,
        WorkerTransaction.date >= first,
        WorkerTransaction.date <= span_end,
        WorkerTransaction.status != 'cancelled',
    ).order_by(WorkerTransaction.date, WorkerTransaction.id).all()
    payments = [t for t in txns
                if t.txn_type in TRANSACTION_DEDUCTION_TYPES
                or t.txn_type in TRANSACTION_SETTLEMENT_TYPES]

    payroll = {(p.year, p.month): p for p in PayrollRecord.query.filter(
        PayrollRecord.worker_id == worker.id).all()}

    # Pass one: what each month was worth. Fixed by its attendance, so it is
    # settled before any money is allocated against it.
    span = list(months_between(worker.join_date, upto))
    earned = {}
    for year, month in span:
        gross, _deductions, _net = compute_month(
            worker, year, month, by_month.get((year, month), []))
        earned[(year, month)] = round(float(gross or 0), 2)

    # Marking a payroll month paid is a statement about that month, so it is
    # never re-aimed at another one. Read from the saved row rather than
    # recomputed, so a later policy change cannot rewrite a closed month.
    from_payroll = {k: p.settled_amount for k, p in payroll.items()
                    if k in earned}

    applied = _allocate(span, earned, from_payroll, payments, allocation)

    rows = []
    balance = 0.0
    earned_total = drawn_total = settled_total = 0.0
    for key in span:
        year, month = key
        hit = applied[key]
        drawn = round(hit['drawn'], 2)
        settled = round(hit['settled'], 2)
        gross = earned[key]

        opening = balance
        balance = round(opening + gross - drawn - settled, 2)
        earned_total += gross
        drawn_total += drawn
        settled_total += settled

        record = payroll.get(key)
        rows.append({
            'year': year, 'month': month,
            'label': '%s %d' % (_cal.month_name[month], year),
            'opening': round(opening, 2),
            'earned': gross,
            'drawn': drawn,
            'settled': settled,
            # Each payment by name, date and the part of it that landed here.
            'draws': hit['draws'],
            'from_payroll': round(from_payroll.get(key, 0.0), 2),
            'record': record,
            # Clear when nothing is left owing and the month was worth
            # something. A month with no attendance at all is neither paid
            # nor owed, and calling it settled would be a lie by badge.
            'paid': gross > EPSILON and balance <= EPSILON,
            'closing': balance,
        })

    open_rows = [r for r in rows if r['closing'] > EPSILON]
    return {
        'rows': rows,
        'earned': round(earned_total, 2),
        'drawn': round(drawn_total, 2),
        'settled': round(settled_total, 2),
        'outstanding': round(balance, 2),
        'allocation': allocation,
        # What an employer wants at a glance: how far back the arrears go.
        'oldest_open': open_rows[0]['label'] if open_rows else None,
        'open_months': len(open_rows),
    }


def _allocate(span, earned, from_payroll, payments, allocation):
    """Decide which month each payment lands on.

    Returns {month_key: {'drawn': x, 'settled': y, 'draws': [...]}} where a
    draw entry is {'txn', 'applied', 'month'} and 'month' is the month the
    payment was dated in — which is not this one when it was carried back to
    an older debt, and the statement says so.
    """
    hits = {k: {'drawn': 0.0, 'settled': 0.0, 'draws': []} for k in span}
    index = {k: i for i, k in enumerate(span)}

    def land(txn, shares):
        """Book one payment, which may have been split across months.

        Accumulated per month first and booked once, so a payment that part
        cleared August and part spilled into September shows as two lines
        and not as four.
        """
        for key, amount in shares.items():
            if amount <= EPSILON:
                continue
            bucket = hits[key]
            if txn.txn_type in TRANSACTION_SETTLEMENT_TYPES:
                bucket['settled'] += amount
            else:
                bucket['drawn'] += amount
            dated = (txn.date.year, txn.date.month)
            bucket['draws'].append({
                'txn': txn, 'applied': round(amount, 2),
                'month': dated,
                # True when the money was handed over in a later month than
                # the one it is clearing, which the statement spells out
                # rather than leaving the reader to spot the dates.
                'carried': dated != key,
            })

    # A month's own payroll settlement is applied to that month in both
    # modes. It is already aimed: letting it drift to an older month would
    # mean marking September paid had quietly closed August.
    for key in span:
        hits[key]['settled'] += from_payroll.get(key, 0.0)

    if allocation != 'oldest_first':
        for t in payments:
            key = (t.date.year, t.date.month)
            # A payment dated outside the statement's span cannot be placed.
            # The query already bounds it, so this only guards a caller that
            # passes payments in by hand.
            if key in hits:
                land(t, {key: float(t.amount or 0)})
        return hits

    # Oldest first. Keep a remaining balance per month and send every payment
    # to the earliest month that still owes something.
    remaining = {k: round(earned[k] - from_payroll.get(k, 0.0), 2)
                 for k in span}

    for t in payments:
        left = float(t.amount or 0)
        dated = (t.date.year, t.date.month)
        start = index.get(dated, len(span) - 1)
        shares = {}
        # Only months up to and including the one the money was handed over
        # in can be cleared by it. Paying in October cannot settle a November
        # that has not happened yet; that money is an advance against work
        # still to come, and stays on the month it was given in.
        for key in span[:start + 1]:
            if left <= EPSILON:
                break
            if remaining[key] <= EPSILON:
                continue
            take = min(left, remaining[key])
            shares[key] = shares.get(key, 0.0) + take
            remaining[key] = round(remaining[key] - take, 2)
            left = round(left - take, 2)
        if left > EPSILON:
            # Nothing older is owed, so the rest is money ahead of the work.
            # It belongs to the month it was handed over in and pushes that
            # month's balance negative, which is the honest reading: the
            # worker has had more than has been earned so far.
            key = span[start]
            shares[key] = shares.get(key, 0.0) + left
            remaining[key] = round(remaining[key] - left, 2)
        land(t, shares)

    return hits
