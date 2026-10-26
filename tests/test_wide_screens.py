"""The column is the device, at every width anyone actually holds.

base.html wrapped every screen in #mobile-app with max-w-sm — 24rem, a
flat 384px — and centred it. 384px was a 2017 phone. Nothing since is
384px wide, so every device showed a 384px app with grey either side:

    393px phone     384px    98%
    430px phone     384px    89%
    600px tablet    384px    64%    108px of grey each side
    820px tablet    384px    47%

The 600px row is the one that was reported, and 600px is not an unusual
tablet — a 1200x1920 panel at 2x density reports exactly 600 CSS px. An
earlier pass at this widened 820px and 1280px behind a min-width:768px
query and so sailed straight over the commonest tablet width of all,
which stayed at 384px. That is the trap this file exists to close: the
table below runs from 360px to 1280px without a gap big enough to hide a
real device in.

Two things are measured at each width:

  1. the column is min(44rem at that root size, the screen) — i.e. the
     device below ~800px, and a centred column above it
  2. nothing overflows sideways, and the bottom bar is exactly as wide
     as the content above it

A 384px bar under a 792px column is the thing that looks broken even
when the widths are each technically fine, so (2) is checked on every
screen rather than once.

What is deliberately NOT tested: that the layout is *good* on a tablet.
It is roomier, not re-laid-out — the grids are still two across. A real
tablet layout is a separate job.
"""
import os
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
PORT = 5147
B = 'http://127.0.0.1:%d' % PORT

# (label, width, root font size, the cap in px at that root size)
#
# The cap is 44rem everywhere, so each of these is 44 x the root size —
# 44 x 16 = 704, 44 x 17 = 748, 44 x 18 = 792, 44 x 20 = 880. They are
# written out rather than computed so a change to either number has to be
# made deliberately here too. Below ~800px the cap is larger than the
# screen, so the column is simply the device; the min() at the comparison
# does that arithmetic.
VIEWS = [
    ('small phone 360', 360, 16, 704),
    ('phone 390', 390, 16, 704),
    ('large phone 430', 430, 16, 704),
    ('tablet portrait 600', 600, 17, 748),     # 1200x1920 at 2x — the common one
    ('tablet portrait 768', 768, 18, 792),
    ('tablet portrait 820', 820, 18, 792),
    ('tablet landscape 1280', 1280, 20, 880),
]

fails = []


def check(label, got, want):
    if got == want:
        print('  PASS %-52s %s' % (label, repr(got)[:24]))
    else:
        fails.append(label)
        print('  FAIL %-52s got=%r want=%r' % (label, got, want))


with app.app_context():
    WID = m.Worker.query.filter_by(status='active').first().id

SCREENS = ['/dashboard', '/workers', '/payroll', '/attendance', '/transactions',
           '/dues', '/settings', '/worker/%d/account' % WID]

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
        for label, width, root_px, want_px in VIEWS:
            print('\n--- %s ---' % label)
            ctx = br.new_context(viewport={'width': width, 'height': 900},
                                 is_mobile=width < 768, has_touch=True,
                                 service_workers='block')
            pg = ctx.new_page()
            pg.goto(B + '/login', wait_until='domcontentloaded')
            pg.wait_for_timeout(700)
            pg.fill('input[name="username"]', 'demo@acme.test')
            pg.fill('input[name="password"]', 'demo12345')
            pg.click('#signin-form button[type="submit"]')
            pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

            wrong, over, nav_mismatch, roots = [], [], [], set()
            for path in SCREENS:
                pg.goto(B + path, wait_until='domcontentloaded')
                pg.wait_for_timeout(700)
                r = pg.evaluate("""() => {
                    const el = document.getElementById('mobile-app');
                    const nav = document.querySelector('.app-bottom-nav');
                    const d = document.documentElement;
                    return {
                        app: el ? Math.round(el.getBoundingClientRect().width) : 0,
                        nav: nav ? Math.round(nav.getBoundingClientRect().width) : null,
                        over: d.scrollWidth > d.clientWidth + 1,
                        root: getComputedStyle(d).fontSize,
                    };
                }""")
                roots.add(r['root'])
                # min(): at 390px the viewport is the limit, not the cap.
                if r['app'] != min(want_px, width):
                    wrong.append('%s is %dpx' % (path, r['app']))
                if r['over']:
                    over.append(path)
                # A 384px bar under a 792px column is the thing that looks
                # broken even when the widths are technically "fine".
                if r['nav'] is not None and r['nav'] != r['app']:
                    nav_mismatch.append('%s nav %dpx vs app %dpx'
                                        % (path, r['nav'], r['app']))

            # The root size is the whole mechanism: everything in this app is
            # in rem, so this one number is what scales type, padding, gaps,
            # radii and the column's own cap together.
            check('the root font size is %dpx' % root_px,
                  sorted(roots), ['%dpx' % root_px])
            check('every screen is %dpx wide' % min(want_px, width), wrong, [])
            check('nothing runs off the side', over, [])
            check('the bottom bar matches the column', nav_mismatch, [])
            ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label in fails:
        print('  %s' % label)
    sys.exit(1)
print('The app fills a tablet, and a phone is exactly as it was.')
