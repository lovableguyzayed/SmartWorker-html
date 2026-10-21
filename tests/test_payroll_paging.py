"""Payroll pages, and its totals stay whole-roster while it does.

The audit recorded the payroll screen as ~8.6s on a 5,000-worker roster and
left it alone pending a decision about what the totals should mean. Measuring
first changed the answer: the server was never the problem — building every
row costs 320ms for 5,013 workers — but the page came to 11.9MB of HTML,
which is minutes on a site phone over 2G.

So the list pages and the totals do not. "What does this month cost" is the
figure an employer needs; a per-page subtotal would be a different and far
less useful number, and it is cheap to keep the real one.
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
import routes as R  # noqa: E402
import bulk  # noqa: E402,F401
import models as m  # noqa: E402
from timeutil import today_ist  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
TAG = 'PGTEST-'
N = int(os.environ.get('PAYROLL_TEST_WORKERS', 300))
failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-56s %s' % (label, repr(got)[:22]))
    else:
        failures.append(label)
        print('  FAIL %-56s got=%r want=%r' % (label, got, want))


def money(body, label):
    """The figure in the summary tile that carries this label.

    Anchored to the tile, not to the nearest rupee sign: a loose search
    matched whatever ₹ happened to be closest and reported Net Payable and
    Total Deductions as each other's numbers.
    """
    hit = re.search(
        r'<div class="text-2xl font-bold">₹([\d,]+(?:\.\d+)?)</div>\s*'
        r'<div class="text-sm opacity-90">' + re.escape(label) + r'</div>',
        body)
    return hit.group(1).replace(',', '') if hit else None


with app.app_context():
    m.Worker.query.filter(m.Worker.worker_id.like(TAG + '%')).delete(
        synchronize_session=False)
    db.session.commit()
    db.session.bulk_save_objects([
        m.Worker(worker_id='%s%05d' % (TAG, i), full_name='Paging Worker %d' % i,
                 phone='91000%05d' % i, department='Civil', position='Helper',
                 pay_type='daily', daily_rate=600.0, employee_type='Contract',
                 join_date=today_ist().replace(day=1), status='active',
                 account_id=1)
        for i in range(N)])
    db.session.commit()
    roster = m.Worker.query.filter_by(status='active').count()
print('seeded to a roster of %d' % roster)

try:
    with app.test_client() as c:
        c.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'}, follow_redirects=True)

        t0 = time.perf_counter()
        first = c.get('/payroll')
        ms = (time.perf_counter() - t0) * 1000
        body1 = first.get_data(as_text=True)
        kb1 = len(first.get_data()) / 1024
        print('  page 1: %.0f ms, %.0f KB' % (ms, kb1))

        check('the payroll screen still loads', first.status_code, 200)
        check('one page is a fraction of the roster, not all of it',
              body1.count('data-ms-item=') <= R.PAYROLL_PER_PAGE, True)
        check('the page does not balloon with the roster', kb1 < 400, True)

        last = (roster + R.PAYROLL_PER_PAGE - 1) // R.PAYROLL_PER_PAGE
        deep = c.get('/payroll?page=%d' % last)
        body_last = deep.get_data(as_text=True)
        check('a deep page loads', deep.status_code, 200)
        # Compare the worker ids each page carries, not the raw HTML: every
        # page shares the same header and totals, so a prefix comparison
        # says nothing.
        def ids(body):
            return set(re.findall(r'data-ms-item="(\d+)"', body))

        first_ids, last_ids = ids(body1), ids(body_last)
        check('both pages list workers',
              bool(first_ids) and bool(last_ids), True)
        check('a deep page lists different workers',
              first_ids.isdisjoint(last_ids), True)

        # The point of the whole exercise.
        for label in ('Gross Payroll', 'Net Payable', 'Total Deductions'):
            check('%r is the same on page 1 and the last page' % label,
                  money(body1, label), money(body_last, label))

        beyond = c.get('/payroll?page=99999')
        check('a page past the end clamps instead of erroring',
              beyond.status_code, 200)
        junk = c.get('/payroll?page=notanumber')
        check('a junk page number does not 500', junk.status_code, 200)

        # And the totals must be the real ones, not a page subtotal.
        with app.app_context():
            t = today_ist()
            _, totals, _ = R._build_payroll_rows(t.month, t.year)
        shown = money(body_last, 'Gross Payroll')
        check('the totals are the real ones, not a page subtotal',
              shown, '%.0f' % totals['total_gross'])
        print('     (gross shown %s, computed %.2f)' % (shown, totals['total_gross']))
finally:
    with app.app_context():
        n = m.Worker.query.filter(m.Worker.worker_id.like(TAG + '%')).delete(
            synchronize_session=False)
        db.session.commit()
    print('cleaned %d seeded workers' % n)

print('\n%d failed' % len(failures))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
