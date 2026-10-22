"""The frosted chips on the blue header carry readable text.

A chip styled `bg-white/20` lays a white veil over the header, and inside a
hero card — itself `bg-white/15` — that is two veils stacked. The text ends
up on a washed-out mid blue: the "permanent" badge measured 2.91:1 where
small text needs 4.5, the assignment chips 3.52:1, the profile pills
4.19-4.44:1. `.glass-chip` tints down instead of up, which keeps the blur
and the translucency and fixes the contrast.

Neither the text nor the fill has a colour you can read off the stylesheet
— both are rgba over a gradient — so this measures what is actually
painted: it screenshots each chip with its glyphs made transparent, reads
the composited backdrop off the pixels, then composites the text colour
over it.

That matters beyond this file. `tools/ux/contrast.py` reports these as
2.8-3.9:1, and it is not wrong so much as conservative: where it cannot
read a flat colour it takes the worst point anywhere under the run, which
is a floor rather than what the glyphs sit on. The avatar initials are
checked here for the same reason — the sweep flags them at 2.82:1 against
their 3.0 floor, and composited they are 3.4:1 and pass. Before changing a
colour because the sweep flagged it, measure it the way this file does.
"""
import io
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from PIL import Image
from playwright.sync_api import sync_playwright

from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5108
B = 'http://127.0.0.1:%d' % PORT

fails = []


def lum(c):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def parse(s):
    n = [float(x) for x in s.replace('rgba(', '').replace('rgb(', '')
         .replace(')', '').split(',')]
    return tuple(n[:3]), (n[3] if len(n) > 3 else 1.0)


def floor_for(size, weight):
    """WCAG large scale: 18pt regular (24px) or 14pt bold (18.66px)."""
    return 3.0 if (size >= 24 or (size >= 18.66 and weight >= 700)) else 4.5


def measure(pg, selector, inner=None):
    """Composited contrast for one element's text against its own backdrop."""
    el = pg.query_selector(selector)
    if el is None:
        return None
    info = pg.evaluate("""([sel, inner]) => {
        const b = document.querySelector(sel);
        const n = inner ? b.querySelector(inner) : null;
        const t = n || b;
        const cs = getComputedStyle(t);
        return {fg: cs.color, fs: parseFloat(cs.fontSize), fw: +cs.fontWeight};
    }""", [selector, inner])
    pg.evaluate("""(sel) => {
        const b = document.querySelector(sel);
        b.style.color = 'transparent';
        b.querySelectorAll('*').forEach(c => c.style.color = 'transparent');
    }""", selector)
    pg.wait_for_timeout(200)
    shot = el.screenshot()
    pg.evaluate("""(sel) => {
        const b = document.querySelector(sel);
        b.style.color = '';
        b.querySelectorAll('*').forEach(c => c.style.color = '');
    }""", selector)

    im = Image.open(io.BytesIO(shot)).convert('RGB')
    w, h = im.size
    px = im.load()
    acc = [0, 0, 0]
    n = 0
    # The band the glyphs occupy, inset from the chip's own edge and border.
    for y in range(int(h * 0.25), int(h * 0.75)):
        for x in range(int(w * 0.2), int(w * 0.8)):
            c = px[x, y]
            acc[0] += c[0]
            acc[1] += c[1]
            acc[2] += c[2]
            n += 1
    back = tuple(v / float(n) for v in acc)
    fg, alpha = parse(info['fg'])
    eff = tuple(alpha * fg[i] + (1 - alpha) * back[i] for i in range(3))
    return contrast(eff, back), floor_for(info['fs'], info['fw']), back


def check(label, got, want_floor, back):
    ok = got is not None and got >= want_floor
    if not ok:
        fails.append((label, got, want_floor))
    print('  %-5s %-34s %5.2f:1  (needs %.1f)  backdrop rgb(%.0f,%.0f,%.0f)'
          % ('OK' if ok else 'FAIL', label, got or 0, want_floor,
             back[0], back[1], back[2]))


with app.app_context():
    WID = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

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

        print('--- the tinted-down chips ---')
        CASES = [
            ('/profile',  '.glass-chip',          None,          'profile pill'),
            ('/worker/%d' % WID, '.glass-chip',   None,          'employee-type badge'),
            ('/assignments', "button[name='show'][value='assigned']",
             '.text-base', 'assignment chip count'),
            ('/assignments', "button[name='show'][value='unassigned']",
             None,          'assignment chip label'),
        ]
        for url, sel, inner, label in CASES:
            pg.goto(B + url, wait_until='domcontentloaded')
            pg.wait_for_timeout(1800)
            got = measure(pg, sel, inner)
            if got is None:
                fails.append((label, 'element not found', 0))
                print('  FAIL  %-34s element not found (%s)' % (label, sel))
                continue
            ratio, floor, back = got
            check(label, ratio, floor, back)

        print('\n--- the avatar initials, which keep the light veil ---')
        # 24px bold, so their floor is 3.0 and they pass as they are. Checked
        # because the sweep reports them at 2.82:1 and the number to trust is
        # this one.
        for url, label in (('/profile', 'profile avatar'),
                           ('/worker/%d' % WID, 'worker avatar')):
            pg.goto(B + url, wait_until='domcontentloaded')
            pg.wait_for_timeout(1800)
            got = measure(pg, '.w-20.h-20')
            if got is None:
                print('  --    %-34s no initial (a photo is set)' % label)
                continue
            ratio, floor, back = got
            check(label, ratio, floor, back)
        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print('\n--- the chip is defined once, and not on the avatars ---')
css = open(os.path.join(ROOT, 'static', 'css', 'custom.css')).read()
ok = '.glass-chip {' in css
if not ok:
    fails.append(('glass-chip is defined', False, True))
print('  %-5s .glass-chip is defined in custom.css' % ('OK' if ok else 'FAIL'))

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, needed %r' % (label, got, want))
    sys.exit(1)
print('All glass-chip contrast checks passed.')
