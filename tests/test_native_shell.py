"""The app has to behave like an app, not like a site that loads pages.

Four properties, each one measured before it was fixed and each one a thing
people read without noticing they are reading it:

  * the tab bar outlives the screen — a bar that is rebuilt on every swap
    blinks, restarts its press animation, and arrives already lit instead
    of lighting up;
  * Back puts you where you were — a list scrolled half way down and then
    scrolled again after a glance at one row is the clearest tell of all;
  * screens arrive from the side they came from, so the direction says
    whether you went somewhere or came back;
  * a tap never takes a readable screen away. Swaps were measured at
    106-287ms against a 150ms skeleton, so almost every tap covered the
    screen in shimmer for a tenth of a second. There is no skeleton any
    more at any delay — a hairline says the tap was heard, and the screen
    you are on stays up until the next one is ready.

Keeping the bar alive is only an improvement if its highlight still moves,
so that is checked hardest: a persistent bar lighting the wrong tab would
be worse than one that blinks.
"""
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PORT = 5119
B = 'http://127.0.0.1:%d' % PORT
EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')

from playwright.sync_api import sync_playwright

srv = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0,%r); from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d, threaded=True)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-46s %r' % ('OK' if ok else 'FAIL', label, got))


try:
    for _ in range(40):
        try:
            urllib.request.urlopen(B + '/login', timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:140]))
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(800)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        pg.wait_for_timeout(1500)

        lit = lambda: pg.evaluate("""() =>
            [...document.querySelectorAll('nav.app-bottom-nav a[href]')]
              .filter(a => a.className.includes('-active'))
              .map(a => a.getAttribute('href'))""")

        print('--- the highlight still moves on the bar we kept ---')
        pg.goto(B + '/dashboard', wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)
        check('on the dashboard', lit(), ['/dashboard'])
        pg.evaluate("() => { document.querySelector('nav').__kept = true; }")
        for path in ['/workers', '/attendance', '/payroll', '/profile']:
            pg.click('a[href="%s"]' % path)
            pg.wait_for_timeout(1100)
            check('after going to %s' % path, lit(), [path])
        check('and it was the same bar throughout', pg.evaluate(
            "() => !!document.querySelector('nav').__kept"), True)

        print('\n--- Back puts you where you were ---')
        pg.goto(B + '/workers', wait_until='domcontentloaded')
        pg.wait_for_timeout(1300)
        tall = pg.evaluate("() => document.body.scrollHeight")
        check('the list is long enough for this to matter', tall > 1200, True)
        pg.evaluate("() => window.scrollTo(0, 400)")
        pg.wait_for_timeout(350)
        row = pg.evaluate("""() => { const a =
            [...document.querySelectorAll('a[href^="/worker/"]')][0];
            return a ? a.getAttribute('href') : null; }""")
        if row:
            pg.click('a[href="%s"]' % row)
            pg.wait_for_timeout(1200)
            check('the screen you open starts at the top',
                  pg.evaluate("() => window.scrollY"), 0)
            pg.go_back()
            pg.wait_for_timeout(1300)
            back_to = pg.evaluate("() => window.scrollY")
            check('and coming back returns you to where you were',
                  abs(back_to - 400) < 50, True)
        else:
            print('  SKIP  no worker rows to open')

        print('\n--- a screen that lights a tab it is not itself ---')
        pg.goto(B + '/workers', wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)
        href = pg.evaluate("""() => { const a =
            [...document.querySelectorAll('a[href^="/worker/"]')][0];
            return a ? a.getAttribute('href') : null; }""")
        if href:
            pg.click('a[href="%s"]' % href)
            pg.wait_for_timeout(1200)
            check('a worker profile keeps Workers lit', lit(), ['/workers'])

        print('\n--- which way the screen comes from ---')
        anim = lambda: pg.evaluate(
            "() => getComputedStyle(document.getElementById('mobile-app')).animationName")
        pg.goto(B + '/dashboard', wait_until='domcontentloaded')
        pg.wait_for_timeout(1000)
        pg.click('a[href="/attendance"]')
        pg.wait_for_timeout(900)
        check('forward pushes in from the right', anim(), 'screenPush')
        pg.go_back()
        pg.wait_for_timeout(1100)
        check('back pops in from the left', anim(), 'screenPop')

        print('\n--- what is shown while waiting ---')
        pg.goto(B + '/dashboard', wait_until='domcontentloaded')
        pg.wait_for_timeout(1000)
        pg.evaluate("""() => {
            window.__saw = { bar: 0, skeleton: 0 };
            new MutationObserver((recs) => {
                recs.forEach(r => [...r.addedNodes].forEach(n => {
                    if (n.id === 'nav-progress') window.__saw.bar++;
                    if (n.id === 'skeleton-overlay') window.__saw.skeleton++;
                }));
            }).observe(document.body, { childList: true });
        }""")
        pg.click('a[href="/payroll"]')
        pg.wait_for_timeout(1500)
        saw = pg.evaluate("() => window.__saw")
        print('  progress bar appeared  :', saw['bar'], 'time(s)')
        check('an ordinary tap never blanks the screen', saw['skeleton'], 0)
        check('and nothing is left behind afterwards', pg.evaluate(
            "() => !!document.getElementById('nav-progress')"), False)

        print('\n--- a slow screen keeps the one you are on ---')
        # A real wait is exactly when replacing readable content with grey
        # bars helps least, so there is nothing to replace it with any more:
        # the hairline, and the screen you were already reading.
        pg.route('**/closures', lambda route: (time.sleep(0.9), route.continue_()))
        pg.goto(B + '/dashboard', wait_until='domcontentloaded')
        pg.wait_for_timeout(1000)
        pg.evaluate("""() => {
            window.__slow = { bar: 0, overlay: 0 };
            new MutationObserver((recs) => {
                recs.forEach(r => [...r.addedNodes].forEach(n => {
                    if (n.id === 'nav-progress') window.__slow.bar++;
                    if (n.id === 'skeleton-overlay') window.__slow.overlay++;
                }));
            }).observe(document.body, { childList: true });
        }""")
        # Sampled by a timer inside the page, not from here: the route
        # handler above sleeps on the Python side, which blocks this client,
        # so a wait_for_timeout here would run after the screen had already
        # arrived and would report on the wrong moment.
        pg.evaluate("""() => {
            window.__mid = null;
            setTimeout(() => { window.__mid = {
                hairline: !!document.getElementById('nav-progress'),
                old_screen: !!document.querySelector('nav.app-bottom-nav'),
                grey: !!document.getElementById('skeleton-overlay'),
            }; }, 350);
            NativeShell.visit('/closures');
        }""")
        pg.wait_for_timeout(2200)
        mid = pg.evaluate("() => window.__mid")
        check('a moment mid-wait was actually captured', bool(mid), True)
        check('the screen you were on is still up', mid and mid['old_screen'], True)
        check('the hairline says the tap was heard', mid and mid['hairline'], True)
        check('and nothing grey is over it', mid and mid['grey'], False)
        slow = pg.evaluate("() => window.__slow")
        check('no overlay at any point in the wait', slow['overlay'], 0)
        check('it did arrive', pg.evaluate("() => location.pathname"), '/closures')
        check('and the hairline is gone', pg.evaluate(
            "() => !!document.getElementById('nav-progress')"), False)

        print('\n--- and nothing threw ---')
        check('page errors', errs, [])
        ctx.close()
        br.close()
finally:
    srv.terminate()
    srv.wait(timeout=10)

print()
if fails:
    print('FAILED %d:' % len(fails))
    for a, g, w in fails:
        print('   %s: got %r, want %r' % (a, g, w))
    sys.exit(1)
print('Every screen behaves like a screen, not a page.')
