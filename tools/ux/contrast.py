"""Contrast, measured where the coordinates and the pixels agree.

A full-page screenshot is not the page: Chromium stretches the viewport to
take it, the layout reflows, and every sticky or viewport-sized element
moves out from under the rectangle that was measured at phone height. So
this never takes one. It scrolls the real 390x844 phone a screen at a
time, and at each stop reads the rectangles and photographs the pixels in
the same breath. Only text that sits wholly inside the current screen is
scored, each element once, tagged so a second stop cannot count it twice.

The ink comes from the computed style. The paper is the most common colour
inside the text's own box, which is what is actually behind it; where the
glyphs or a gradient leave no clear majority, the row is reported as
unmeasurable rather than guessed at.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from PIL import Image
from playwright.sync_api import sync_playwright
from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
B = os.environ.get('UX_BASE', 'http://127.0.0.1:5000')
# Results land in tools/ux/out/, which is not tracked.
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)
DSF = 2
VW, VH = 390, 844

TAG = r"""
() => {
  let n = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (!el.dataset.uxid) el.dataset.uxid = 'u' + (n++);
  }
  return document.documentElement.scrollHeight;
}
"""

# Read the runs that sit wholly inside the screen as it is right now.
STEP = r"""
(seen) => {
  const rows = [];
  for (const el of document.querySelectorAll('body *')) {
    if (seen.includes(el.dataset.uxid)) continue;
    if (!el.checkVisibility || !el.checkVisibility()) continue;
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim().length)
      .map(n => n.textContent.trim()).join(' ');
    if (!own) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.top < 0 || r.left < 0) continue;
    if (r.bottom > window.innerHeight || r.right > window.innerWidth) continue;
    const s = getComputedStyle(el);
    rows.push({
      id: el.dataset.uxid, t: own.slice(0, 44),
      fs: parseFloat(s.fontSize), fw: +s.fontWeight, fg: s.color,
      x: r.left, y: r.top, w: r.width, h: r.height,
      cls: (el.className || '').toString().slice(0, 44),
      tag: el.tagName.toLowerCase()
    });
  }
  return rows;
}
"""

SCREENS = [
    ('/',                     'dashboard'),
    ('/workers',              'workers'),
    ('/attendance',           'attendance'),
    ('/payroll',              'payroll'),
    ('/payroll/preview',      'payroll-preview'),
    ('/transactions',         'transactions'),
    ('/closures',             'closures'),
    ('/assignments',          'assignments'),
    ('/scan',                 'scan'),
    ('/settings',             'settings'),
    ('/profile',              'profile'),
    ('/notifications',        'notifications'),
    ('/add_worker',           'add-worker'),
    ('/worker/%d',            'worker-profile'),
    ('/edit_worker/%d',       'edit-worker'),
    ('/worker_attendance/%d', 'worker-attendance'),
    ('/worker/%d/login/powers', 'login-powers'),
]


def lum(c):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def parse(s):
    n = [float(x) for x in re.findall(r'[\d.]+', s)]
    return n[:3], (n[3] if len(n) > 3 else 1.0)


with app.app_context():
    RICH = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

results = defaultdict(list)
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
    ctx = br.new_context(viewport={'width': VW, 'height': VH},
                         device_scale_factor=DSF, is_mobile=True,
                         has_touch=True, service_workers='block')
    pg = ctx.new_page()
    pg.goto(B + '/login', wait_until='domcontentloaded')
    pg.wait_for_timeout(800)
    pg.fill('input[name="username"]', 'demo@acme.test')
    pg.fill('input[name="password"]', 'demo12345')
    pg.click('#signin-form button[type="submit"]')
    pg.wait_for_function("location.pathname !== '/login'", timeout=20000)

    for path, slug in SCREENS:
        pg.goto(B + (path % RICH if '%d' in path else path),
                wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        height = pg.evaluate(TAG)
        seen = []
        y = 0
        while True:
            # #mobile-app is transformed, so window.scrollTo inside the page
            # does not move it; the wheel does.
            pg.evaluate('(y) => window.scrollTo(0, y)', y)
            pg.mouse.move(VW / 2, VH / 2)
            pg.wait_for_timeout(260)
            rows = pg.evaluate(STEP, seen)
            buf = pg.screenshot()
            shot = os.path.join(OUT, '_frame.png')
            with open(shot, 'wb') as fh:
                fh.write(buf)
            img = Image.open(shot).convert('RGB')
            for r in rows:
                x0, y0 = int(r['x'] * DSF), int(r['y'] * DSF)
                x1 = min(img.width, int((r['x'] + r['w']) * DSF))
                y1 = min(img.height, int((r['y'] + r['h']) * DSF))
                if x1 - x0 < 2 or y1 - y0 < 2:
                    continue
                crop = img.crop((x0, y0, x1, y1))
                counts = Counter(crop.getdata())
                bg, n = counts.most_common(1)[0]
                share = n / float(crop.width * crop.height)
                fg, alpha = parse(r['fg'])
                if alpha < 1:
                    fg = [fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3)]
                results[slug].append(dict(
                    r, bg='rgb(%d, %d, %d)' % bg, bgshare=round(share, 2),
                    ratio=round(contrast(fg, list(bg)), 2)))
                seen.append(r['id'])
            if y + VH >= height:
                break
            y = min(y + VH, height - VH)
        print('  %-20s %4d runs scored over %d screens of scroll'
              % (slug, len(results[slug]), round(height / VH)))
    br.close()

with open(os.path.join(OUT, 'contrast2.json'), 'w') as fh:
    json.dump(results, fh, indent=1)


def large(r):
    return r['fs'] >= 18.66 or (r['fs'] >= 14 and r['fw'] >= 700)


allrows = [(s, r) for s, rows in results.items() for r in rows]
solid = [(s, r) for s, r in allrows if r['bgshare'] >= 0.33]
print('\n%d runs scored, %d with a clear background, %d unmeasurable'
      % (len(allrows), len(solid), len(allrows) - len(solid)))

fails = [(s, r) for s, r in solid if r['ratio'] < (3.0 if large(r) else 4.5)]
print('%d below the WCAG AA floor — %.1f%% of what could be measured\n'
      % (len(fails), 100.0 * len(fails) / max(1, len(solid))))

groups = defaultdict(list)
for s, r in fails:
    groups[(r['fg'], r['bg'], r['fs'], r['fw'])].append((s, r))
print('--- by colour pair, most common first ---')
for key, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    fg, bg, fs, fw = key
    scr = sorted({s for s, r in rows})
    print('  %5.2f:1  %-7s w%-3s %-19s on %-19s %3d runs  %d screens'
          % (rows[0][1]['ratio'], '%gpx' % fs, fw, fg, bg, len(rows), len(scr)))
    print('           %r  [%s]  %s' % (rows[0][1]['t'], rows[0][1]['cls'],
                                       ','.join(scr[:4])))

print('\n--- per screen ---')
for slug in results:
    sr = [r for s, r in solid if s == slug]
    sf = [r for s, r in fails if s == slug]
    print('  %-20s %4d measured  %3d fail (%4.1f%%)'
          % (slug, len(sr), len(sf), 100.0 * len(sf) / max(1, len(sr))))
