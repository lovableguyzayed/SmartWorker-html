"""Controls that carry no word at all.

The people this application is for do not all read fluently, and several of
them read Devanagari or nothing. An icon with a label is a kindness; an
icon alone is a quiz. This counts every control on every screen that shows
no text, and says whether it at least carries a name for a screen reader or
a long-press tooltip — because a control with neither is unknowable until
you press it and find out what it did.
"""
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

PROBE = r"""
() => {
  const out = [];
  const sel = 'button, a[href], input[type=submit], [role=button], label.tap-target';
  for (const el of document.querySelectorAll(sel)) {
    if (!el.checkVisibility || !el.checkVisibility()) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const text = (el.innerText || el.value || '').trim();
    if (text) continue;                       // it says something: fine
    const icon = el.querySelector('i, svg');
    out.push({
      icon: icon ? (icon.className.baseVal || icon.className || '').toString()
                     .split(' ').filter(c => c.startsWith('fa-')).join(' ')
                 : '(no icon either)',
      aria: el.getAttribute('aria-label') || '',
      title: el.getAttribute('title') || '',
      cls: (el.className || '').toString().slice(0, 36),
      w: Math.round(r.width), h: Math.round(r.height)
    });
  }
  return out;
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

found = {}
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
    for path, slug in SCREENS:
        pg.goto(B + (path % RICH if '%d' in path else path),
                wait_until='domcontentloaded')
        pg.wait_for_timeout(1400)
        found[slug] = pg.evaluate(PROBE)
    br.close()

total = sum(len(v) for v in found.values())
named = sum(1 for v in found.values() for c in v if c['aria'] or c['title'])
print('%d wordless controls across %d screens; %d carry a name, %d carry nothing'
      % (total, len(found), named, total - named))

print('\n--- per screen ---')
for slug, rows in found.items():
    anon = [c for c in rows if not (c['aria'] or c['title'])]
    print('  %-20s %3d wordless, %3d of them unnamed' % (slug, len(rows), len(anon)))

print('\n--- which icons, and are they named? ---')
by = defaultdict(lambda: [0, 0, set()])
for slug, rows in found.items():
    for c in rows:
        e = by[c['icon']]
        e[0] += 1
        if c['aria'] or c['title']:
            e[1] += 1
        e[2].add(slug)
for icon, (n, nm, scr) in sorted(by.items(), key=lambda kv: -kv[1][0]):
    print('  %-34s %3d uses, %3d named, %2d screens  %s'
          % (icon or '(none)', n, nm, len(scr), ','.join(sorted(scr)[:3])))
