"""The month calendar is folded away, and remembers whether you unfolded it.

It sat above the roster and cost about 600px, so the first worker started a
screen and a half down on the one screen the application exists for. Marking
today never needs it: the date field and its day arrows in the header
already move between days. It is for looking back over a month.

The remembering is the part that has to work. The month arrows are ordinary
links, so stepping back a month reloads the page — and a calendar that
folded itself shut on every month change would be worse than one that never
folded at all.

Browser storage can throw outright in a private window or with site data
blocked, so the page must still work when nothing can be remembered. That is
checked here too, by denying storage and loading the screen again.
"""
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from playwright.sync_api import sync_playwright

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5104
B = 'http://127.0.0.1:%d' % PORT

fails = []


def check(label, got, want):
    if got != want:
        fails.append((label, got, want))
    print('  %-5s %-52s %r' % ('OK' if got == want else 'FAIL', label, got))


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

    OPEN = "() => document.getElementById('cal-fold').open"
    # _calendar.html renders a div grid, not a table.
    GRID = ("() => { const g = document.querySelector('#cal-fold .cal-grid');"
            " return !!(g && g.checkVisibility && g.checkVisibility()); }")
    FIRST = ("() => { const n = document.querySelector('.dv-name');"
             " return n ? Math.round(n.getBoundingClientRect().top + window.scrollY) : -1; }")

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
        pg.wait_for_function("location.pathname !== '/login'", timeout=20000)

        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(2400)
        check('folded on a first visit', pg.evaluate(OPEN), False)
        check('and the grid really is hidden', pg.evaluate(GRID), False)
        folded_at = pg.evaluate(FIRST)
        check('the summary control is a 44px target',
              pg.evaluate("() => Math.round(document.querySelector('.cal-summary')"
                          ".getBoundingClientRect().height) >= 44"), True)

        pg.click('.cal-summary')
        pg.wait_for_timeout(700)
        check('unfolds when tapped', pg.evaluate(OPEN), True)
        check('and the grid is on screen', pg.evaluate(GRID), True)
        open_at = pg.evaluate(FIRST)
        check('unfolding pushes the roster down', open_at > folded_at, True)
        print('       first worker: %dpx folded, %dpx unfolded (%d saved)'
              % (folded_at, open_at, open_at - folded_at))

        # Stepping back a month is a link, so this is a real page load.
        pg.click('[aria-label="Previous month"], [aria-label="पिछला महीना"]')
        pg.wait_for_timeout(2400)
        check('still unfolded after changing month', pg.evaluate(OPEN), True)

        pg.click('.cal-summary')
        pg.wait_for_timeout(600)
        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(2400)
        check('folded again, and that is remembered too', pg.evaluate(OPEN), False)
        ctx.close()

        # With storage denied the page must still render and still fold.
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        ctx.add_init_script("""
            Object.defineProperty(window, 'localStorage', {
                get() { throw new Error('storage blocked'); }
            });
        """)
        pg = ctx.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)[:120]))
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(600)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_function("location.pathname !== '/login'", timeout=20000)
        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(2400)
        check('with storage blocked it still renders folded',
              pg.evaluate(OPEN), False)
        pg.click('.cal-summary')
        pg.wait_for_timeout(600)
        check('and still unfolds', pg.evaluate(OPEN), True)
        check('with no uncaught error', [e for e in errors if 'storage blocked' in e], [])
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print('\n%d failed' % len(fails))
for row in fails:
    print('   FAIL', row)
sys.exit(1 if fails else 0)
