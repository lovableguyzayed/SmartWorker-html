"""Does any screen throw while it loads, in either language?

A screen can answer 200 and still be broken. `test_render_all_screens.py`
asks the server for every page and checks the status, which proves the
route works and nothing about the page: if a script throws on load, every
icon on that screen which depends on it silently does nothing, and the
status is still 200.

So this opens each screen in a real browser and listens — for a thrown
exception, for an error on the console, and for a request that failed to
come back. Both languages, because a Hindi string reaching a script that
expects a number is exactly the kind of thing this catches.

The service worker and the favicon are ignored: neither is the page.
"""
import subprocess
import sys
import time
import urllib.request

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PORT = 5115
B = 'http://127.0.0.1:%d' % PORT
EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')

from app import app
import models as m
from playwright.sync_api import sync_playwright

with app.app_context():
    WID = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

SCREENS = [
    '/', '/dashboard', '/workers', '/attendance', '/payroll',
    '/payroll/preview', '/transactions', '/closures', '/assignments',
    '/scan', '/settings', '/profile', '/notifications', '/add_worker',
    '/worker/%d' % WID, '/edit_worker/%d' % WID,
    '/worker_attendance/%d' % WID, '/worker/%d/report' % WID,
    '/payroll/slip/%d' % WID, '/id_card/%d' % WID,
    '/worker/%d/login/powers' % WID,
]

srv = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0,%r); from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
problems = []
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
        bucket = []
        pg.on('pageerror', lambda e: bucket.append(('throw', str(e)[:130])))
        pg.on('console', lambda msg: bucket.append(('console', msg.text[:130]))
              if msg.type == 'error' else None)
        pg.on('requestfailed', lambda r: bucket.append(
            ('request', '%s %s' % (r.failure, r.url[-70:]))))

        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_function("location.pathname !== '/login'", timeout=20000)

        for lang in ('en', 'hi'):
            pg.goto(B + '/profile', wait_until='domcontentloaded')
            pg.wait_for_timeout(700)
            pg.locator('form[action*="/language/%s"] button[type=submit]' % lang
                       ).first.click()
            pg.wait_for_timeout(1400)
            print('--- %s ---' % lang)
            for path in SCREENS:
                bucket.clear()
                pg.goto(B + path, wait_until='domcontentloaded')
                pg.wait_for_timeout(2200)
                # anything still arriving after the page settled
                noisy = [b for b in bucket
                         if 'favicon' not in b[1] and 'sw.js' not in b[1]]
                if noisy:
                    problems.append((lang, path, noisy))
                    print('  FAIL %-28s %d issue(s)' % (path, len(noisy)))
                    for kind, text in noisy[:3]:
                        print('        %-8s %s' % (kind, text))
                else:
                    print('  OK   %-28s clean' % path)
        ctx.close()
        br.close()
finally:
    srv.terminate()
    srv.wait(timeout=10)

print('\n%d screen loads checked, %d with problems'
      % (len(SCREENS) * 2, len(problems)))
if problems:
    print('\nFAILED:')
    for lang, path, noisy in problems:
        for kind, text in noisy:
            print('  [%s] %-28s %-8s %s' % (lang, path, kind, text))
    sys.exit(1)
print('Every screen loaded clean in both languages.')
