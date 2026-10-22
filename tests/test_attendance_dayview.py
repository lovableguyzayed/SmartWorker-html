"""The attendance screen marks in one place and reports in the other.

It used to list the same twelve workers twice: a day view at y=1,139 with
four status buttons, two check-in boxes and a Save on every row, and an
entry panel three thousand pixels below with the same four buttons again.
A mukadam who marked the roll at the top and kept scrolling met the same
twelve names in a different layout and had no way to know he was not
looking at a second day's work.

The day view is now a report. Two things have to hold for that to be worth
having:

  * it offers nothing to press — no status buttons, no time boxes, no Save
  * it follows what the panel does, immediately, without a reload

The second matters more than it sounds. A stale report is worse than none:
it would say "Not marked" against a man who has just been marked, and
invite marking him twice.
"""
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from playwright.sync_api import sync_playwright

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5103
B = 'http://127.0.0.1:%d' % PORT

READ = r"""
(name) => {
  for (const el of document.querySelectorAll('.dv-name')) {
    if ((el.innerText || '').trim().startsWith(name)) {
      const row = el.closest('.dv-row');
      const badge = row ? row.querySelector('.dv-state') : null;
      return {badge: badge ? badge.innerText.trim() : null,
              code: (row.querySelector('.dv-sub') || {innerText: ''})
                      .innerText.split('·')[0].trim()};
    }
  }
  return {badge: null, code: null};
}
"""

fails = []


def check(label, got, want):
    if got != want:
        fails.append((label, got, want))
    print('  %-5s %-46s %r' % ('OK' if got == want else 'FAIL', label, got))


server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
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

    from app import app, db
    import models as m

    with app.app_context():
        # Somebody with no record today, so "Not marked" is the real state.
        today = date.today()
        marked = {r.worker_id for r in m.AttendanceRecord.query.filter_by(date=today)}
        who = next((w for w in m.Worker.query.filter_by(status='active')
                    .order_by(m.Worker.id) if w.id not in marked), None)
        if who is None:
            sys.exit('every active worker is already marked today; nothing to test')
        WHO, WHO_ID = who.full_name, who.id
    print('  using %s, who has no record for %s' % (WHO, today))

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        # wait_for_url rather than a string predicate: Playwright
        # evaluates those with eval(), which the page's
        # Content-Security-Policy refuses.

        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(2600)

        check('the report offers no status buttons',
              pg.evaluate("document.querySelectorAll('.dv-pill').length"), 0)
        check('no inline check-in boxes',
              pg.evaluate("document.querySelectorAll('.dv-row input[type=time]').length"), 0)
        check('no per-row Save',
              pg.evaluate("document.querySelectorAll('.dv-times').length"), 0)
        check('the roster is still listed',
              pg.evaluate("document.querySelectorAll('.dv-row').length") > 0, True)
        check('and the panel below is still the editor',
              pg.evaluate("document.querySelectorAll('.ep-pill').length") > 0, True)

        before = pg.evaluate(READ, WHO)
        check('before: the report says he is unmarked', before['badge'], 'Not marked')

        pg.fill('#ep-quick-id', before['code'])
        pg.click('#ep-quick-btn')
        pg.wait_for_timeout(2600)
        check('after: the report followed, with no reload',
              pg.evaluate(READ, WHO)['badge'], 'Present')

        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_timeout(2600)
        check('and the server agrees after a reload',
              pg.evaluate(READ, WHO)['badge'], 'Present')
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)
    # Leave the demo data exactly as it was found.
    from app import app, db
    import models as m
    with app.app_context():
        gone = m.AttendanceRecord.query.filter_by(
            worker_id=WHO_ID, date=date.today()).delete()
        db.session.commit()
        print('\n  cleaned up %d record(s) this test created' % gone)

print('\n%d failed' % len(fails))
for row in fails:
    print('   FAIL', row)
sys.exit(1 if fails else 0)
