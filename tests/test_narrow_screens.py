"""Nothing may run off the side of a cheap phone.

320px is a budget Android in portrait — the device this app is actually
used on at a site office, not the 390px iPhone a layout gets designed
against. Horizontal scroll there is the most ordinary layout bug there is,
and it is invisible at every width anyone develops at.

Three screens failed when this was first run: the scanner's manual-ID row
pushed its search button 37px off, the attendance date picker pushed its
day arrows 22px off, and a long worker name pushed the employment-type
badge 2px past the edge of its card. All three were the same cause — a
flex item will not shrink below its content's intrinsic width unless
min-width is released, and an <input> carries a ~20-character intrinsic
width whatever you set flex to.
"""
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from playwright.sync_api import sync_playwright

from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5123
B = 'http://127.0.0.1:%d' % PORT
WIDTHS = (320, 360, 390)

fails = []

with app.app_context():
    WID = m.Worker.query.filter_by(status='active').first().id

SCREENS = ['/dashboard', '/workers', '/attendance', '/payroll', '/transactions',
           '/assignments', '/closures', '/settings', '/profile', '/scan',
           '/notifications', '/add_worker', '/worker/%d' % WID,
           '/worker_attendance/%d' % WID, '/worker/%d/report' % WID]

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
        for width in WIDTHS:
            ctx = br.new_context(viewport={'width': width, 'height': 720},
                                 is_mobile=True, has_touch=True,
                                 service_workers='block')
            pg = ctx.new_page()
            pg.goto(B + '/login', wait_until='domcontentloaded')
            pg.wait_for_timeout(700)
            pg.fill('input[name="username"]', 'demo@acme.test')
            pg.fill('input[name="password"]', 'demo12345')
            pg.click('#signin-form button[type="submit"]')
            pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

            over = []
            for path in SCREENS:
                pg.goto(B + path, wait_until='domcontentloaded')
                pg.wait_for_timeout(850)
                r = pg.evaluate("""() => { const d = document.documentElement;
                    return { over: d.scrollWidth > d.clientWidth + 1,
                             w: d.scrollWidth, c: d.clientWidth }; }""")
                if r['over']:
                    over.append('%s (%dpx of content in %dpx)'
                                % (path, r['w'], r['c']))
            ok = not over
            if not ok:
                fails.append((width, over))
            print('  %-5s %3dpx  %d of %d screens fit'
                  % ('OK' if ok else 'FAIL', width,
                     len(SCREENS) - len(over), len(SCREENS)))
            for line in over:
                print('          runs off the side: %s' % line)
            ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print()
if fails:
    print('FAILED at %d width(s):' % len(fails))
    for width, over in fails:
        print('  %dpx: %s' % (width, ', '.join(over)))
    sys.exit(1)
print('Every screen fits every phone tested.')
