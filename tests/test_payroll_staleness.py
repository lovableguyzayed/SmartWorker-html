"""Money recorded mid-month, and whether the pay follows it.

An advance handed over on the 15th has to end up in the pay. It does, and
it always did — the payroll screen recomputes every unsettled row on sight,
so the figure moves the moment the advance is saved, with no generate in
between. Measured here rather than asserted, because the whole question is
whether the number on the screen moved.

What was missing was the truth about the one case where it does not. Once
money has gone out against a month, payroll_save skips that row on purpose
(recalculating could put the net below what was handed over, and the month
would read as overpaid because a rule changed) and _build_payroll_rows
shows the stored figures for the same reason. Recording an advance against
such a month used to answer "Payroll updates automatically" — which is
false there, and is exactly how somebody records money, looks at payroll,
finds nothing, and concludes the feature is broken.

Three states, and all three are checked:

  not generated   the figure is an estimate and follows the advance
  generated,      the stored row is behind, the screen is not, and the
  nothing paid    screen says so and offers the preview
  paid out        the figure is held, and recording money against it says
                  so instead of promising an update

The counts on the banner are over the whole roster, not the page, because
"is this month's payroll right" is not a question about page 2.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright

from app import app, db
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5155
B = 'http://127.0.0.1:%d' % PORT

# A month far enough back that the demo data has no payroll saved for it,
# so this test owns every record in it and cleans them all up.
WHEN = date(2026, 7, 15)
YEAR, MONTH = WHEN.year, WHEN.month

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-54s %r' % ('OK' if ok else 'FAIL', label, str(got)[:28]))


def net_payable(text):
    """The Net Payable on a payroll row, by its label rather than by position.

    Read by name because the row prints Gross, Deduct. and Net Payable in a
    layout that is free to change, and because a net can go negative — an
    advance larger than the month is worth — which a bare ₹ pattern reads
    as positive and silently inverts the assertion.
    """
    found = re.search(r'Net Payable[^₹-]*(-?)₹\s*(-?)([\d,]+(?:\.\d+)?)', text)
    if not found:
        return None
    value = float(found.group(3).replace(',', ''))
    return -value if (found.group(1) or found.group(2)) else value


with app.app_context():
    if m.PayrollRecord.query.filter_by(month=MONTH, year=YEAR).count():
        sys.exit('%d/%d already has saved payroll in the demo data' % (MONTH, YEAR))
    # Chosen by what they earn that month, not by id. Picked by id, this
    # landed on two workers whose July is worth ₹0 — every assertion then
    # measured an advance against nothing, and the "paid out" fixture set
    # paid_amount to 0.0, which is not a settled month at all.
    import routes as _routes
    rows, _totals, _start = _routes._build_payroll_rows(MONTH, YEAR)
    earners = [r for r in rows if r['net_pay'] > 10000]
    if len(earners) < 2:
        sys.exit('need two workers earning in %d/%d; found %d'
                 % (MONTH, YEAR, len(earners)))
    FREE, PAID = earners[0]['worker'], earners[1]['worker']
    FREE_ID, FREE_NAME = FREE.id, FREE.full_name
    PAID_ID, PAID_NAME = PAID.id, PAID.full_name
    FREE_NET = earners[0]['net_pay']

print('  unsettled worker : %s' % FREE_NAME)
print('  paid-out worker  : %s' % PAID_NAME)
print('  month            : %d/%d' % (MONTH, YEAR))

made = {'txns': [], 'records': []}

ROW = """(name) => {
  for (const el of document.querySelectorAll('div,tr')) {
    const t = el.innerText || '';
    if (t.includes(name) && /Net Payable/i.test(t) && t.length < 800) return t;
  }
  return null;
}"""
BANNER = """() => {
  const el = document.querySelector('.bg-amber-50');
  return el ? el.innerText.replace(/\\n+/g, ' | ').trim() : null;
}"""

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d, threaded=True)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(B + '/login', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit('could not start a server on %s' % B)

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 430, 'height': 950},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

        def payroll(who):
            pg.goto(B + '/payroll?month=%d&year=%d' % (MONTH, YEAR),
                    wait_until='domcontentloaded')
            pg.wait_for_timeout(2000)
            return pg.evaluate(ROW, who)

        def add_advance(worker_id, amount):
            """Through the screen a person uses, not straight into the table."""
            pg.goto(B + '/transactions', wait_until='domcontentloaded')
            pg.wait_for_timeout(1600)
            pg.click('[data-act="openTxnModal"]')
            pg.wait_for_timeout(800)
            pg.select_option('select[name="worker_id"]', str(worker_id))
            pg.select_option('select[name="txn_type"]', 'advance')
            pg.fill('input[name="amount"]', str(amount))
            pg.fill('input[name="date"]', WHEN.isoformat())
            pg.locator('form button[type="submit"]').last.click()
            pg.wait_for_timeout(2400)
            # Every alert, not the first: a save against a settled month
            # raises two — the confirmation, and the warning about what it
            # does to the pay — and the one under test is the second.
            said = pg.evaluate(
                "() => [...document.querySelectorAll('.alert')]"
                ".map(a => a.innerText.trim()).join(' | ')")
            with app.app_context():
                t = (m.WorkerTransaction.query
                     .filter_by(worker_id=worker_id, txn_type='advance', date=WHEN)
                     .order_by(m.WorkerTransaction.id.desc()).first())
                if t:
                    made['txns'].append(t.id)
            return said

        # ----------------------------------------------------------------
        print('\n--- nobody has run payroll for this month yet ---')
        before = net_payable(payroll(FREE_NAME))
        said = add_advance(FREE_ID, 1500)
        after = net_payable(payroll(FREE_NAME))
        print('       %s net: %r -> %r' % (FREE_NAME, before, after))
        check('the advance reaches the pay with no generate',
              round(before - after, 2), 1500.0)
        check('and the screen promises exactly that',
              'updates automatically' in (said or ''), True)
        check('with no banner, because nothing is saved to fall behind',
              pg.evaluate(BANNER), None)

        # ----------------------------------------------------------------
        print('\n--- generated, nothing paid: the stored row falls behind ---')
        pg.goto(B + '/payroll?month=%d&year=%d' % (MONTH, YEAR),
                wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        pg.locator('form[action*="payroll/save"] button[type=submit], '
                   'button:has-text("Generate Payroll")').first.click()
        pg.wait_for_timeout(3000)
        with app.app_context():
            made['records'] = [r.id for r in m.PayrollRecord.query
                               .filter_by(month=MONTH, year=YEAR).all()]
        print('       generated %d record(s)' % len(made['records']))
        check('generating leaves no banner behind', pg.evaluate(BANNER), None)

        said = add_advance(FREE_ID, 500)
        after2 = net_payable(payroll(FREE_NAME))
        print('       %s net now %r' % (FREE_NAME, after2))
        check('the screen still follows the money',
              round(after - after2, 2), 500.0)
        banner = pg.evaluate(BANNER) or ''
        check('and now says the saved records are behind',
              'behind' in banner.lower(), True)
        check('and offers the preview that shows what would change',
              'See what would change' in banner, True)
        check('the preview link really goes there', pg.evaluate(
            """() => { const a = document.querySelector('.bg-amber-50 a[href]');
                 return a ? a.getAttribute('href') : null; }"""
            ).startswith('/payroll/preview'), True)

        # ----------------------------------------------------------------
        print('\n--- paid out: the figure is held, and it says so ---')
        with app.app_context():
            rec = m.PayrollRecord.query.filter_by(
                worker_id=PAID_ID, month=MONTH, year=YEAR).first()
            rec.paid_amount = float(rec.net_pay or 0)
            rec.status = 'paid'
            db.session.commit()
            held = float(rec.net_pay or 0)
        print('       %s paid out at ₹%.2f' % (PAID_NAME, held))

        said = add_advance(PAID_ID, 2000)
        print('       app said: %r' % (said or '')[:120])
        check('it does not promise an automatic update',
              'updates automatically' in (said or ''), False)
        check('it says that month has been paid in full',
              'paid in full' in (said or '').lower(), True)
        check('and the figure really is held',
              net_payable(payroll(PAID_NAME)), held)
        banner = pg.evaluate(BANNER) or ''
        check('the banner counts them as already paid',
              'money paid against this month' in banner, True)

        # ----------------------------------------------------------------
        print('\n--- part paid: the screen still moves, the record cannot ---')
        # Half the month handed over. payroll_save skips the row — it tests
        # settled_amount, not the status — but _build_payroll_rows only
        # freezes a row that is fully paid, so the figure on screen keeps
        # recomputing. Saying "that month's figure stays as it is" here
        # would be false, which is why the note has two forms.
        with app.app_context():
            rec = m.PayrollRecord.query.filter_by(
                worker_id=PAID_ID, month=MONTH, year=YEAR).first()
            rec.paid_amount = round(float(rec.net_pay or 0) / 2, 2)
            rec.status = 'pending'
            db.session.commit()
            half = rec.paid_amount
            part_net = float(rec.net_pay or 0)
        print('       %s part paid: ₹%.2f of ₹%.2f' % (PAID_NAME, half, part_net))

        shown_before = net_payable(payroll(PAID_NAME))
        said = add_advance(PAID_ID, 700)
        shown_after = net_payable(payroll(PAID_NAME))
        print('       app said: %r' % (said or '')[:150])
        check('a part-paid row still follows the money on screen',
              round(shown_before - shown_after, 2), 700.0)
        check('so it must not claim the figure is held',
              'stays as it is' in (said or ''), False)
        check('it says the saved record is what will not change',
              'saved record alone' in (said or ''), True)

        print('\n--- and nothing threw ---')
        check('page errors', errs, [])
        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)
    with app.app_context():
        for tid in made['txns']:
            row = db.session.get(m.WorkerTransaction, tid)
            if row:
                db.session.delete(row)
        for rid in made['records']:
            row = db.session.get(m.PayrollRecord, rid)
            if row:
                db.session.delete(row)
        db.session.commit()
    print('\n  removed %d transaction(s) and %d payroll record(s)'
          % (len(made['txns']), len(made['records'])))

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('Money recorded mid-month reaches the pay, and says so when it cannot.')
