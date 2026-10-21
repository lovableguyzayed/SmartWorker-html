"""Can this be read on a building site, in sunlight, by someone who reads slowly?

Two measurements, both objective. First the size of every piece of visible
text, because 10px Devanagari is not small-but-fine, it is a guess at what
the word probably says. Then the contrast of that text against whatever is
actually behind it, walking up the ancestors until something opaque is
found, scored by the WCAG formula. Both languages, because a matra needs
vertical room that a Latin x-height does not.
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from playwright.sync_api import sync_playwright
from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
B = os.environ.get('UX_BASE', 'http://127.0.0.1:5000')
# Results land in tools/ux/out/, which is not tracked.
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)

PROBE = r"""
() => {
  const rows = [];
  const vis = el => el.checkVisibility && el.checkVisibility();
  const rgb = s => {
    const m = s.match(/[\d.]+/g);
    return m ? m.slice(0, 3).map(Number).concat([m[3] === undefined ? 1 : +m[3]]) : null;
  };
  // What is actually behind this text: the nearest opaque ancestor fill.
  const behind = el => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = rgb(getComputedStyle(n).backgroundColor);
      if (c && c[3] >= 0.95) return c;
      n = n.parentElement;
    }
    return [255, 255, 255, 1];
  };
  const lum = c => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92
                                : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };

  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim().length)
      .map(n => n.textContent.trim()).join(' ');
    if (!own) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const s = getComputedStyle(el);
    const fg = rgb(s.color);
    let bg = behind(el);
    if (fg[3] < 1) {  // blend a translucent ink onto its backdrop
      for (let i = 0; i < 3; i++) fg[i] = fg[i] * fg[3] + bg[i] * (1 - fg[3]);
    }
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    rows.push({
      t: own.slice(0, 44),
      fs: parseFloat(s.fontSize),
      fw: +s.fontWeight,
      ratio: +ratio.toFixed(2),
      fg: s.color, bg: `rgb(${bg.slice(0, 3).join(', ')})`,
      w: +r.width.toFixed(0), h: +r.height.toFixed(0),
      cls: (el.className || '').toString().slice(0, 50)
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

with app.app_context():
    RICH = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

data = {}
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
    for lang in ('en', 'hi'):
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        if lang == 'hi':
            pg.locator('form[action*="/language/hi"] button[type=submit]').first.click()
            pg.wait_for_timeout(1200)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_function("location.pathname !== '/login'", timeout=20000)
        for path, slug in SCREENS:
            pg.goto(B + (path % RICH if '%d' in path else path),
                    wait_until='domcontentloaded')
            pg.wait_for_timeout(1400)
            data['%s:%s' % (lang, slug)] = pg.evaluate(PROBE)
        print('  %s done' % lang)
        ctx.close()
    br.close()

with open(os.path.join(OUT, 'legibility.json'), 'w') as fh:
    json.dump(data, fh, indent=1)

flat = defaultdict(list)
for key, rows in data.items():
    lang, slug = key.split(':')
    flat[lang].extend((slug, r) for r in rows)

for lang in ('en', 'hi'):
    rows = flat[lang]
    print('\n################ %s — %d visible text runs ################'
          % (lang.upper(), len(rows)))

    small = [(s, r) for s, r in rows if r['fs'] < 12]
    mid = [(s, r) for s, r in rows if 12 <= r['fs'] < 14]
    print('  under 12px: %4d (%4.1f%%)   12-14px: %4d (%4.1f%%)   14px+: %4d'
          % (len(small), 100 * len(small) / len(rows),
             len(mid), 100 * len(mid) / len(rows),
             len(rows) - len(small) - len(mid)))

    by = Counter()
    for s, r in small:
        by[(r['fs'], r['cls'].split()[0] if r['cls'] else '-')] += 1
    print('  --- the sub-12px text, by size and class ---')
    for (fs, cls), n in by.most_common(14):
        ex = next(r['t'] for s, r in small
                  if r['fs'] == fs and (r['cls'].split()[0] if r['cls'] else '-') == cls)
        print('    %-7s %-22s %4d  e.g. %r' % ('%gpx' % fs, cls, n, ex))

    # Contrast. 4.5:1 is the normal-text floor; large/bold text may use 3:1.
    def large(r):
        return r['fs'] >= 18.66 or (r['fs'] >= 14 and r['fw'] >= 700)
    fails = [(s, r) for s, r in rows
             if r['ratio'] < (3.0 if large(r) else 4.5)]
    print('  --- contrast ---')
    print('  %d of %d runs below the WCAG AA floor (%4.1f%%)'
          % (len(fails), len(rows), 100 * len(fails) / len(rows)))
    worst = Counter()
    for s, r in fails:
        worst[(r['fg'], r['bg'], r['ratio'], r['fs'])] += 1
    for (fg, bg, ratio, fs), n in worst.most_common(14):
        ex = next(r['t'] for s, r in fails
                  if r['fg'] == fg and r['bg'] == bg and r['fs'] == fs)
        scr = sorted({s for s, r in fails if r['fg'] == fg and r['bg'] == bg})
        print('    %5.2f:1  %-7s %-22s on %-18s %3d runs, %2d screens  e.g. %r'
              % (ratio, '%gpx' % fs, fg, bg, n, len(scr), ex))

# How much longer is the Hindi?
print('\n################ HINDI vs ENGLISH ################')
for path, slug in SCREENS:
    e = data['en:%s' % slug]
    h = data['hi:%s' % slug]
    en_chars = sum(len(r['t']) for r in e)
    hi_chars = sum(len(r['t']) for r in h)
    # Text that wraps to more lines than its line-height allows for.
    def tall(rows):
        return sum(1 for r in rows if r['h'] > r['fs'] * 2.2)
    print('  %-20s runs %4d/%4d   chars %5d/%5d (%+5.0f%%)   multi-line %3d/%3d'
          % (slug, len(e), len(h), en_chars, hi_chars,
             100 * (hi_chars - en_chars) / max(1, en_chars), tall(e), tall(h)))
