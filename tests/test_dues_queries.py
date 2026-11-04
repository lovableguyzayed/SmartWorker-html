"""The dues screen asks the database a bounded number of questions.

It walks every active worker's whole employment month by month, because
the outstanding figure has to agree with the payslips it is summarising.
Done naively that is a query per worker per month, and it was: 494 queries
for twelve workers, 41 each, 469ms of wall time against 16ms of SQL. The
database was never the problem — building and issuing the round trips was.
On a hosted database, where every query also pays network latency, those
494 are most of a second on their own.

The helpers that fix it already existed for the payroll screen
(prefetch_period_transactions, prefetch_leave_ledgers) and this screen
never called them. It now loads the whole span in a handful of queries and
fills the same caches the per-worker helpers read first.

Two things are checked, and the second is the one that matters:

  * the query count stays bounded, and in particular does not grow with
    the number of months anybody has been employed. A regression here is
    invisible on a laptop with twelve workers and brutal on a real roster
    over a network, which is exactly how the original went unnoticed.

  * the figures do not move. A faster wrong answer is worth nothing, so
    the whole screen is computed with the prefetch disabled and compared
    row for row against the prefetched one.

The budget below is deliberately loose. This is a guard against the N+1
coming back, not a pin on an exact number, and a count that drifts a
little as the screen grows is not a bug.
"""
import collections
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from sqlalchemy import event

from app import app, db
import models as m
import routes

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, got))


counts = collections.Counter()


def _record(conn, cursor, statement, params, context, executemany):
    table = re.search(r'FROM\s+(\w+)', statement)
    counts[table.group(1) if table else '?'] += 1


def dues(prefetch=True):
    """The whole screen, with the prefetch on or off, and the queries it cost."""
    # A fresh session each time. Without this the second run answers half
    # its questions out of the first one's identity map and reports 38
    # queries where a cold process reports 494 — which would turn the
    # comparison below into a measurement of the cache rather than of the
    # prefetch.
    db.session.remove()
    real = routes._prefetch_dues_months
    if not prefetch:
        routes._prefetch_dues_months = lambda *a, **k: None
    try:
        with app.test_request_context():
            from flask_login import login_user
            import flask
            user = m.User.query.filter_by(role='admin').first()
            login_user(user)
            flask.g.account_id = user.account_id
            counts.clear()
            summary = routes._company_dues()
            return summary, sum(counts.values()), dict(counts)
    finally:
        routes._prefetch_dues_months = real


def comparable(summary):
    """Everything the screen shows, in a form two runs can be compared by."""
    return sorted(
        (r['worker_id'], round(r['earned'], 2), round(r['drawn'], 2),
         round(r['settled'], 2), round(r['outstanding'], 2),
         r['open_months'], r['oldest_open'])
        for r in summary['rows'])


with app.app_context():
    event.listen(db.engine, 'after_cursor_execute', _record)

    workers = m.Worker.query.filter_by(status='active').count()
    oldest = (m.Worker.query.filter_by(status='active')
              .order_by(m.Worker.join_date).first())
    import datetime
    span_months = 0
    if oldest and oldest.join_date:
        today = routes.today_ist()
        span_months = ((today.year - oldest.join_date.year) * 12
                       + today.month - oldest.join_date.month + 1)
    print('  %d active workers, the oldest employed %d months'
          % (workers, span_months))

    # Measured without first, so the prefetched run cannot be credited
    # with anything the unprefetched one happened to leave warm.
    slow, slow_queries, _ = dues(prefetch=False)

    print('\n--- the query count is bounded ---')
    fast, fast_queries, by_table = dues(prefetch=True)
    print('       %d queries: %s' % (fast_queries, ', '.join(
        '%s %d' % (t, c) for t, c in
        sorted(by_table.items(), key=lambda kv: -kv[1]))))

    # Per worker, ledger.build asks for that worker's transactions, their
    # saved payroll rows and their attendance — three questions nobody can
    # ask on anybody's behalf. Everything else is loaded for the whole span
    # at once, so the budget is a small fixed allowance plus those three.
    budget = 20 + 5 * workers
    check('well under a per-worker-per-month budget',
          fast_queries <= budget, True)
    print('       (budget %d for %d workers)' % (budget, workers))

    # The sharpest edge: nothing may be issued once per month. A worker
    # employed for years would otherwise cost more than a whole roster.
    if span_months >= 6:
        check('nothing is queried once per month',
              fast_queries < span_months * 3, True)
        for table, count in by_table.items():
            check('%s is not asked once per month' % table,
                  count < span_months, True)

    print('\n--- and the figures did not move ---')
    print('       without the prefetch: %d queries' % slow_queries)
    check('the prefetch really is doing something',
          slow_queries > fast_queries * 2, True)
    check('every row is identical', comparable(fast), comparable(slow))
    for key in ('total_earned', 'total_drawn', 'total_settled',
                'total_outstanding'):
        check('%s matches' % key,
              round(fast[key], 2), round(slow[key], 2))
    check('the worker order is the same',
          [r['worker_id'] for r in fast['rows']],
          [r['worker_id'] for r in slow['rows']])

    event.remove(db.engine, 'after_cursor_execute', _record)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The dues screen asks a bounded number of questions, for the same answer.')
