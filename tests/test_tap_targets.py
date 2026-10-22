"""No control on a touch screen may be under 44px tall to hit.

Measured by hit-testing, not by box size. Box size is the wrong measure: the
attendance pills grow their hit area with an ::after overlay, so they read as
36px by the box and are not. It also catches the opposite mistake — an
overlay that is supposed to buy 44px but is eaten by a neighbour's overlay,
which is what was actually happening here (the pills won 40-43px, not 44).

Starts its own server on its own port: Flask caches compiled templates, so
borrowing a dev server started before an edit tests the old CSS.
"""
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EXE = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
HOST = '127.0.0.1'
PORT = int(os.environ.get('TAP_TEST_PORT', 5098))
B = 'http://%s:%d' % (HOST, PORT)

SCREENS = ['/', '/workers', '/attendance', '/payroll', '/payroll/preview',
           '/transactions', '/closures', '/assignments', '/settings',
           '/profile', '/scan', '/worker/3', '/worker_attendance/3',
           '/add_worker']

PROBE = r"""() => {
  const sel = 'a, button, [role=button], input[type=submit], select';
  const vis = (el) => el.checkVisibility
      ? el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})
      : !!el.offsetParent;
  const bad = [];
  for (const el of document.querySelectorAll(sel)) {
    if (!vis(el)) continue;
    if (el.parentElement && el.parentElement.closest(sel)) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (r.top < 0 || r.bottom > window.innerHeight) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const owns = (x, y) => {
      const hit = document.elementFromPoint(x, y);
      return !!hit && (hit === el || el.contains(hit) || hit.closest(sel) === el);
    };
    let up = 0, down = 0, left = 0, right = 0;
    while (up < 30 && owns(cx, r.top - up - 1)) up++;
    while (down < 30 && owns(cx, r.bottom + down + 1)) down++;
    while (left < 30 && owns(r.left - left - 1, cy)) left++;
    while (right < 30 && owns(r.right + right + 1, cy)) right++;
    const hitH = Math.round(r.height + up + down);
    const hitW = Math.round(r.width + left + right);
    if (hitH < 44 || hitW < 24) {
      bad.push({cls: (el.className || '').toString().slice(0, 40),
                t: (el.textContent || '').trim().slice(0, 24)
                   || el.getAttribute('aria-label') || el.tagName,
                hitW, hitH});
    }
  }
  return bad;
}"""


def listening():
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, PORT)) == 0


if listening():
    sys.exit('port %d is in use; set TAP_TEST_PORT to a free port' % PORT)

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host=%r, port=%d)' % (ROOT, HOST, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(40):
    time.sleep(0.5)
    if listening():
        break
else:
    server.terminate()
    sys.exit('could not start a server on %s' % B)

offenders = {}
try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        # is_mobile/has_touch so (pointer: coarse) applies, which is the only
        # place the 44px rules live — a mouse keeps the compact design.
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        pg.goto(B + '/login')
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        # wait_for_url rather than a string predicate: Playwright
        # evaluates those with eval(), which the page's
        # Content-Security-Policy refuses.

        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        coarse = pg.evaluate("matchMedia('(pointer: coarse)').matches")
        if not coarse:
            sys.exit('the browser does not report a coarse pointer; '
                     'the 44px rules would not apply and this test would be vacuous')

        for path in SCREENS:
            pg.goto(B + path, wait_until='domcontentloaded')
            pg.wait_for_timeout(1200)
            found = []
            for _ in range(8):
                found += pg.evaluate(PROBE)
                pg.mouse.wheel(0, 700)
                pg.wait_for_timeout(200)
            for b in found:
                offenders.setdefault((b['cls'], b['hitW'], b['hitH']),
                                     set()).add(path)
            print('  %-4s %-22s %d small' % ('FAIL' if found else 'PASS', path,
                                             len({(b['cls'], b['hitH']) for b in found})))
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print('\n%d control kinds under 44px' % len(offenders))
for (cls, w, h), paths in sorted(offenders.items(), key=lambda kv: kv[0][2]):
    print('   %3dx%-3d %-40s %s' % (w, h, cls, ','.join(sorted(paths))[:40]))
sys.exit(1 if offenders else 0)
