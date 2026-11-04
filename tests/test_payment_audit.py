"""Every worker's money, checked against itself.

The other payment tests each take one mechanism: allocation order
(test_dues_allocation), a part-settled month (test_payment_flow), the saved
figures going stale (test_payroll_staleness). None of them asks the
question an employer actually asks, which is "is every worker's statement
internally consistent, right now, with the data that is really in there".

So this one walks every worker on the roster and checks the arithmetic of
their whole statement, month by month, from the joining date to today. No
fixtures and nothing written: it reads what is there and verifies that it
adds up.

What has to hold, for every worker:

  * the months chain. Each month's closing balance is its opening plus what
    was earned less what was drawn and settled, and the next month opens on
    it. The first month opens at zero.

  * the totals are the months. earned - drawn - settled = outstanding,
    and each total is the sum of its column.

  * no payment is counted twice, and none is invented. Every rupee
    allocated to a month traces back to a transaction, and no transaction
    has more of it allocated than it is worth.

  * no money disappears. A payment dated outside the statement's span —
    before the joining month, or after this month — is allocated nowhere,
    so it would silently vanish from the outstanding figure. There should
    be none; if there are, they are named.

  * a month cannot be settled for more than it was worth, and the Paid /
    Partial / Pending badge agrees with the money behind it.

  * the "paid" flag on a month means what it says: the month was worth
    something, and nothing is left owing on it.

A failure here is not a style problem. It means a worker's outstanding
figure on the dues screen is wrong, which is the one number this
application exists to get right.
"""
import os
import sys
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from app import app, db
import ledger
import models as m
import routes

EPS = 0.02           # two paise: these are floats, not Decimals, on the way out

fails = []
notes = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-62s %r' % ('OK' if ok else 'FAIL', label, got))


def near(label, got, want):
    ok = abs(float(got) - float(want)) <= EPS
    if not ok:
        fails.append((label, got, want))
    return ok


with app.app_context():
    with app.test_request_context():
        from flask_login import login_user
        import flask

        admin = m.User.query.filter_by(role='admin').first()
        login_user(admin)
        flask.g.account_id = admin.account_id

        today = routes.today_ist()
        workers = (m.Worker.query
                   .filter(m.Worker.status.in_(('active', 'inactive')))
                   .order_by(m.Worker.id).all())
        print('  %d worker(s) on the roll, statements to %s'
              % (len(workers), today.isoformat()))

        allocation = routes._dues_allocation()
        print('  allocation mode: %s' % allocation)

        # ------------------------------------------------------------------
        print('\n--- every statement adds up, month by month ---')

        chain_bad = []
        totals_bad = []
        paid_flag_bad = []
        negative_earned = []
        overdrawn = []
        statements = {}

        for w in workers:
            if not w.join_date:
                continue
            st = ledger.build(w, upto=today,
                              compute_month=routes._ledger_month,
                              allocation=allocation)
            statements[w.id] = st

            prev_closing = 0.0
            for i, row in enumerate(st['rows']):
                want_closing = (row['opening'] + row['earned']
                                - row['drawn'] - row['settled'])
                if abs(row['closing'] - want_closing) > EPS:
                    chain_bad.append((w.full_name, row['label'], row['closing'],
                                      round(want_closing, 2)))
                if abs(row['opening'] - prev_closing) > EPS:
                    chain_bad.append((w.full_name, row['label'] + ' opening',
                                      row['opening'], round(prev_closing, 2)))
                prev_closing = row['closing']

                if row['earned'] < -EPS:
                    negative_earned.append((w.full_name, row['label'],
                                            row['earned']))
                should_be_paid = (row['earned'] > EPS
                                  and row['closing'] <= EPS)
                if bool(row['paid']) != should_be_paid:
                    paid_flag_bad.append((w.full_name, row['label'],
                                          row['paid'], should_be_paid))
                if row['closing'] < -EPS:
                    overdrawn.append((w.full_name, row['label'],
                                      row['closing']))

            col_earned = sum(r['earned'] for r in st['rows'])
            col_drawn = sum(r['drawn'] for r in st['rows'])
            col_settled = sum(r['settled'] for r in st['rows'])
            for name, col, total in (('earned', col_earned, st['earned']),
                                     ('drawn', col_drawn, st['drawn']),
                                     ('settled', col_settled, st['settled'])):
                if abs(col - total) > EPS:
                    totals_bad.append((w.full_name, name, total, round(col, 2)))
            if abs((st['earned'] - st['drawn'] - st['settled'])
                   - st['outstanding']) > EPS:
                totals_bad.append((w.full_name, 'outstanding', st['outstanding'],
                                   round(st['earned'] - st['drawn']
                                         - st['settled'], 2)))
            if st['rows'] and abs(st['rows'][-1]['closing']
                                  - st['outstanding']) > EPS:
                totals_bad.append((w.full_name, 'last closing',
                                   st['rows'][-1]['closing'],
                                   st['outstanding']))

        check('the month chain is unbroken for every worker', chain_bad, [])
        check('and the totals are the sum of the months', totals_bad, [])
        check('no month earned a negative amount', negative_earned, [])
        check('the Paid badge on a month matches its balance',
              paid_flag_bad, [])
        if overdrawn:
            notes.append('%d month(s) are overpaid (negative closing): %s'
                         % (len(overdrawn), overdrawn[:4]))
        print('       months with a negative closing (overpaid): %d'
              % len(overdrawn))

        # ------------------------------------------------------------------
        print('\n--- no payment is invented, and none is counted twice ---')

        over_allocated = []
        unknown_txn = []
        for w in workers:
            st = statements.get(w.id)
            if not st:
                continue
            per_txn = {}
            for row in st['rows']:
                for draw in row['draws']:
                    per_txn[draw['txn'].id] = (per_txn.get(draw['txn'].id, 0.0)
                                               + draw['applied'])
            for txn_id, applied in per_txn.items():
                txn = db.session.get(m.WorkerTransaction, txn_id)
                if txn is None:
                    unknown_txn.append((w.full_name, txn_id))
                    continue
                if applied - float(txn.amount or 0) > EPS:
                    over_allocated.append((w.full_name, txn_id, applied,
                                           float(txn.amount)))

        check('every allocated rupee comes from a real transaction',
              unknown_txn, [])
        check('and no transaction is allocated beyond its amount',
              over_allocated, [])

        # ------------------------------------------------------------------
        print('\n--- no money is dated outside its own statement ---')

        # A payment before the joining month, or after this month, falls
        # outside the span ledger.build walks, so nothing would ever be
        # allocated against it and the worker's outstanding figure would be
        # that much too high.
        stranded = []
        payable = (set(ledger.TRANSACTION_DEDUCTION_TYPES)
                   | set(ledger.TRANSACTION_SETTLEMENT_TYPES))
        for w in workers:
            if not w.join_date:
                continue
            span_start = w.join_date.replace(day=1)
            for txn in m.WorkerTransaction.query.filter(
                    m.WorkerTransaction.worker_id == w.id,
                    m.WorkerTransaction.status != 'cancelled').all():
                if txn.txn_type not in payable or not txn.date:
                    continue
                if txn.date < span_start or txn.date > today:
                    stranded.append((w.full_name, txn.id, str(txn.date),
                                     txn.txn_type, float(txn.amount or 0)))

        check('no payment falls outside the months it could pay for',
              stranded, [])

        # ------------------------------------------------------------------
        print('\n--- a saved month cannot be settled for more than it is worth ---')

        over_settled = []
        badge_bad = []
        rows = m.PayrollRecord.query.all()
        for p in rows:
            due = round(float(p.net_pay or 0), 2)
            settled = p.settled_amount
            if settled - due > 0.5:
                over_settled.append((p.worker_id, p.year, p.month, settled, due))
            if settled <= 0.005:
                want = 'pending'
            elif settled + 0.005 >= due:
                want = 'paid'
            else:
                want = 'partial'
            if p.payment_state != want:
                badge_bad.append((p.worker_id, p.year, p.month,
                                  p.payment_state, want))

        print('       %d saved payroll row(s)' % len(rows))
        check('none is settled for more than its net pay', over_settled, [])
        check('and every badge agrees with the money behind it', badge_bad, [])

        # ------------------------------------------------------------------
        print('\n--- the dues screen says the same as the statements ---')

        summary = routes._company_dues()
        by_worker = {r['worker_id']: r for r in summary['rows']}
        mismatched = []
        for wid, st in statements.items():
            row = by_worker.get(wid)
            if row is None:
                continue
            for field in ('earned', 'drawn', 'settled', 'outstanding'):
                if abs(row[field] - st[field]) > EPS:
                    mismatched.append((wid, field, row[field], st[field]))
        check('every row on the dues screen matches its own statement',
              mismatched, [])

        for field in ('earned', 'drawn', 'settled', 'outstanding'):
            col = sum(r[field] for r in summary['rows'])
            check('the dues total for %-11s is the sum of its column' % field,
                  near('total_%s' % field, summary['total_' + field], col), True)

        print('       company outstanding: ₹%s across %d worker(s)'
              % (round(summary['total_outstanding'], 2), len(summary['rows'])))

print()
for note in notes:
    print('NOTE  %s' % note)
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s:\n      got  %r\n      want %r' % (label, got, want))
    sys.exit(1)
print('Every worker\'s money adds up: the months chain, the totals are the '
      'months, and nothing is stranded.')
