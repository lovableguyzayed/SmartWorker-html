"""Every control on every screen reaches something.

actions.js is a lookup: `var fn = VERBS[name] || window[name];` followed by
`if (typeof fn !== 'function') return;`. A data-act naming something that
does not exist on that screen is a button that silently does nothing — no
error in the console, no mark on the page, nothing to tell anyone it is
broken. That is the first thing measured here, over every screen at once,
because the failure is invisible by construction.

The second is narrower and is where the real bug was. `window.print()`
resolves to a function everywhere, so the lookup above says the control is
fine; but an Android WebView does not implement printing — it goes through
the native PrintManager, which nothing in a page can reach. The app ships
as a Cordova WebView. So the worker report's only control, a button reading
"Save PDF" with a PDF icon, called window.print() and did nothing at all on
the one platform the app runs on, while working perfectly in every browser
it was ever tested in.

The rule that replaces it: a screen offering to print must be able to
produce the document some other way, and inside the app that is the way
taken. Both halves are checked — that each such screen defines downloadPDF,
and that pressing the print control with Cordova present really produces a
file.

Third, native controls are left to draw their own furniture. An
<input type="date"> renders a picker icon of its own, so a decorative
calendar glyph in front of one puts two calendars on one box, of which
only the browser's does anything. ("Calendar me do do icon kyu.")
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright

from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5153
B = 'http://127.0.0.1:%d' % PORT

# The verbs actions.js answers itself; every other name is looked up on
# window. Read out of the file rather than listed here, so a verb added
# there does not read as a dead control.
VERBS = re.findall(r"^\s*'([a-z-]+)':\s*function",
                   open(os.path.join(ROOT, 'static/js/actions.js')).read(),
                   re.M)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, str(got)[:30]))


with app.app_context():
    WID = m.Worker.query.filter_by(status='active').first().id

SCREENS = ['/dashboard', '/workers', '/attendance', '/payroll', '/transactions',
           '/dues', '/profile', '/settings', '/scan', '/notifications',
           '/closures', '/assignments', '/add_worker',
           '/worker/%d' % WID, '/edit_worker/%d' % WID,
           '/worker_attendance/%d' % WID, '/worker/%d/report' % WID,
           '/id_card/%d' % WID, '/payroll/slip/%d' % WID,
           '/worker/%d/account' % WID]

# Screens whose print control must have a document to fall back on.
PRINTABLE = ['/worker/%d/report' % WID, '/payroll/slip/%d' % WID]

RESOLVES = """(verbs) => {
  const dead = [];
  for (const el of document.querySelectorAll('[data-act]')) {
    const name = el.getAttribute('data-act');
    if (verbs.indexOf(name) === -1 && typeof window[name] !== 'function') {
      dead.push(name + ' on <' + el.tagName.toLowerCase() + ' ' +
                (el.getAttribute('aria-label') || el.textContent || '')
                  .trim().slice(0, 24) + '>');
    }
  }
  return dead;
}"""

# A glyph drawn on top of a native date field. getBoundingClientRect rather
# than reading the markup: what matters is whether two icons land on one
# box, however the overlap was written.
DOUBLED = """() => {
  const bad = [];
  for (const input of document.querySelectorAll('input[type=date]')) {
    const box = input.getBoundingClientRect();
    for (const icon of document.querySelectorAll('i[class*=fa-]')) {
      const r = icon.getBoundingClientRect();
      if (!r.width) continue;
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      if (cx >= box.left && cx <= box.right && cy >= box.top && cy <= box.bottom) {
        bad.push(icon.className);
      }
    }
  }
  return bad;
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
                             service_workers='block', accept_downloads=True)
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

        print('--- every data-act reaches a function ---')
        dead, doubled, missing = [], [], []
        for path in SCREENS:
            resp = pg.goto(B + path, wait_until='domcontentloaded')
            pg.wait_for_timeout(1400)
            if resp and resp.status >= 400:
                fails.append((path, 'HTTP %d' % resp.status, 'HTTP 200'))
                print('  FAIL  %-50s HTTP %d' % (path, resp.status))
                continue
            for name in pg.evaluate(RESOLVES, VERBS):
                dead.append('%s: %s' % (path, name))
            for cls in pg.evaluate(DOUBLED):
                doubled.append('%s: %s' % (path, cls))
            if path in PRINTABLE:
                if pg.evaluate("() => typeof window.downloadPDF") != 'function':
                    missing.append(path)
        print('  (%d screens)' % len(SCREENS))
        check('no control names a function that is not there', dead, [])

        print('\n--- a native control draws its own furniture ---')
        check('no glyph sits on top of a date field', doubled, [])

        print('\n--- a screen that offers to print can make the document ---')
        check('each printable screen defines downloadPDF', missing, [])

        for path in PRINTABLE:
            pg.goto(B + path, wait_until='domcontentloaded')
            pg.wait_for_timeout(2400)
            # Pretend to be inside the APK. filesave.js and the print verb
            # both key off window.cordova.file, and in the real app the file
            # is written with cordova-plugin-file and handed to a viewer;
            # here the browser path runs instead and a download appears,
            # which is the same proof that a document was produced.
            pg.evaluate("() => { window.cordova = { file: {} }; }")
            sel = ('[data-act="print"], [data-act="printSlip"]')
            got = None
            try:
                with pg.expect_download(timeout=60000) as dl:
                    pg.locator(sel).first.click()
                got = dl.value.suggested_filename
            except Exception as err:
                got = 'nothing happened (%s)' % str(err)[:40]
            check('%s prints a file rather than nothing' % path,
                  bool(got and got.endswith('.pdf')), True)
            print('        %s' % got)

        print('\n--- and nothing threw ---')
        check('page errors', errs, [])
        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('Every control reaches something, on a phone and in the app.')
