"""The policy must survive the service worker, which every test blocks.

Pages are cached and replayed cache-first, so a screen can be served from
disk minutes later. The nonce in that HTML only works if the
Content-Security-Policy header replayed alongside it names the same one —
a cached body paired with a fresh header, or the reverse, and every inline
block on the screen is refused.

Nothing else exercises this: the browser contexts in tests/ all pass
service_workers='block', which is right for them and leaves this path
untested. So it is checked here, with the worker on.
"""
import subprocess
import sys
import time
import urllib.request

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PORT = 5116
B = 'http://127.0.0.1:%d' % PORT
EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')

from playwright.sync_api import sync_playwright

srv = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0,%r); from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
bad = []
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(B + '/login', timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        # Service worker deliberately NOT blocked.
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        errs = []
        pg.on('console', lambda m: errs.append(m.text[:110])
              if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append('THREW: ' + str(e)[:110]))

        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        pg.wait_for_timeout(2500)

        reg = pg.evaluate(
            "() => navigator.serviceWorker "
            "? navigator.serviceWorker.controller ? 'controlling' : 'registered'"
            " : 'unsupported'")
        print('  service worker:', reg)

        for screen in ('/workers', '/attendance', '/payroll', '/settings'):
            # First visit populates the cache.
            errs.clear()
            pg.goto(B + screen, wait_until='domcontentloaded')
            pg.wait_for_timeout(2200)
            first = [e for e in errs if 'favicon' not in e]

            # Second visit should come back from the worker's cache.
            errs.clear()
            pg.goto(B + screen, wait_until='domcontentloaded')
            pg.wait_for_timeout(2200)
            second = [e for e in errs if 'favicon' not in e]

            nonce_ok = pg.evaluate("""() => {
                const s = [...document.querySelectorAll('script:not([src])')]
                            .find(x => x.nonce);
                return !!(s && s.nonce);
            }""")
            ok = not first and not second and nonce_ok
            if not ok:
                bad.append((screen, first, second, nonce_ok))
            print('  %-5s %-14s first=%d second=%d errors, nonce live=%s'
                  % ('OK' if ok else 'FAIL', screen, len(first), len(second),
                     nonce_ok))
            for e in (first + second)[:3]:
                print('        %s' % e)
        ctx.close()
        br.close()
finally:
    srv.terminate()
    srv.wait(timeout=10)

print('\n%d screen(s) broken through the service worker' % len(bad))
if bad:
    print('\nFAILED:')
    for screen, first, second, nonce_ok in bad:
        print('  %-14s nonce live=%s' % (screen, nonce_ok))
        for e in first + second:
            print('      %s' % e)
    sys.exit(1)
print('The policy survives the service worker.')
