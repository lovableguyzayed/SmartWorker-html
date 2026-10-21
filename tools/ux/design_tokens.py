"""What the application's design system actually is, as rendered.

Phase 7 asked whether anything was broken. This asks a different question:
whether the twenty-four screens look like one product. A design system is
only as real as the values that reach the screen, so this reads the
computed styles of every visible element on every screen and counts them.
A type scale with eight sizes is a system; one with forty is an accident.
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
  const out = {type: {}, ink: {}, fill: {}, radius: {}, pad: {},
               buttons: [], gutters: {}, heads: [], controls: []};
  const bump = (bag, key) => { bag[key] = (bag[key] || 0) + 1; };

  const vis = el => {
    if (!el.checkVisibility || !el.checkVisibility()) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // Text that a person actually reads: an element with its own text node.
  const texts = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim().length)
      .map(n => n.textContent.trim()).join(' ');
    if (own) texts.push([el, own]);
  }

  for (const [el, txt] of texts) {
    const s = getComputedStyle(el);
    bump(out.type, `${parseFloat(s.fontSize)}/${s.fontWeight}`);
    bump(out.ink, s.color);
  }

  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (s.backgroundColor !== 'rgba(0, 0, 0, 0)' && r.width > 40 && r.height > 20)
      bump(out.fill, s.backgroundColor);
    const rad = parseFloat(s.borderTopLeftRadius) || 0;
    if (rad && r.width > 40 && r.height > 20) bump(out.radius, String(rad));
    // Card-ish: a block with a radius, a fill and some padding.
    if (rad >= 6 && r.width > 180 && parseFloat(s.paddingTop) > 0)
      bump(out.pad, `${parseFloat(s.paddingTop)}/${parseFloat(s.paddingLeft)}`);
  }

  // Every button and link-button, with the numbers that decide whether it
  // is "the same button" as the one on the previous screen.
  for (const el of document.querySelectorAll(
        'button, a.btn, input[type=submit], [role=button]')) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    out.buttons.push({
      t: (el.innerText || el.value || '').trim().slice(0, 28),
      h: +r.height.toFixed(1), w: +r.width.toFixed(1),
      bg: s.backgroundColor, fg: s.color,
      fs: parseFloat(s.fontSize), fw: s.fontWeight,
      rad: parseFloat(s.borderTopLeftRadius) || 0,
      px: parseFloat(s.paddingLeft), border: s.borderTopWidth
    });
  }

  // Form controls: the other half of a form's feel.
  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (['checkbox', 'radio', 'hidden'].includes(el.type)) continue;
    out.controls.push({
      n: el.name || el.id || el.tagName.toLowerCase(),
      h: +r.height.toFixed(1), fs: parseFloat(s.fontSize),
      rad: parseFloat(s.borderTopLeftRadius) || 0,
      bg: s.backgroundColor, border: s.borderTopWidth + ' ' + s.borderTopColor
    });
  }

  // Headings, in document order, to see the hierarchy the markup claims.
  for (const el of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    out.heads.push({tag: el.tagName, fs: parseFloat(s.fontSize),
                    fw: s.fontWeight, mb: parseFloat(s.marginBottom),
                    mt: parseFloat(s.marginTop),
                    t: el.innerText.trim().slice(0, 40)});
  }

  // The left edge of the content: an inconsistent gutter is the first
  // thing the eye catches when flicking between screens.
  for (const sel of ['main', '#page-content', '.container', '.card',
                     'h1', 'h2']) {
    const el = document.querySelector(sel);
    if (el && vis(el)) out.gutters[sel] = +el.getBoundingClientRect().left.toFixed(1);
  }
  out.scrollH = document.documentElement.scrollHeight;
  return out;
}
"""

ADMIN = [
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

report = {}
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844},
                         is_mobile=True, has_touch=True,
                         service_workers='block')
    pg = ctx.new_page()
    pg.goto(B + '/login', wait_until='domcontentloaded')
    pg.wait_for_timeout(800)
    report['login'] = pg.evaluate(PROBE)
    pg.fill('input[name="username"]', 'demo@acme.test')
    pg.fill('input[name="password"]', 'demo12345')
    pg.click('#signin-form button[type="submit"]')
    pg.wait_for_function("location.pathname !== '/login'", timeout=20000)
    for path, slug in ADMIN:
        pg.goto(B + (path % RICH if '%d' in path else path),
                wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        report[slug] = pg.evaluate(PROBE)
        print('  probed %s' % slug)
    br.close()

with open(os.path.join(OUT, 'design_tokens.json'), 'w') as fh:
    json.dump(report, fh, indent=1)

# ---- what the numbers say ----------------------------------------------

def merge(key):
    bag = Counter()
    where = defaultdict(set)
    for slug, r in report.items():
        for k, n in r[key].items():
            bag[k] += n
            where[k].add(slug)
    return bag, where


print('\n================ TYPE SCALE (size/weight) ================')
bag, where = merge('type')
print('%d distinct size+weight pairs across %d screens' % (len(bag), len(report)))
for k, n in bag.most_common():
    print('  %-12s %5d uses  %2d screens' % (k, n, len(where[k])))

print('\n================ TEXT COLOUR ================')
bag, where = merge('ink')
print('%d distinct text colours' % len(bag))
for k, n in bag.most_common():
    print('  %-26s %5d uses  %2d screens' % (k, n, len(where[k])))

print('\n================ SURFACE FILL ================')
bag, where = merge('fill')
print('%d distinct block background colours' % len(bag))
for k, n in bag.most_common(30):
    print('  %-26s %5d uses  %2d screens' % (k, n, len(where[k])))

print('\n================ CORNER RADIUS ================')
bag, where = merge('radius')
print('%d distinct radii' % len(bag))
for k, n in sorted(bag.items(), key=lambda kv: float(kv[0])):
    print('  %-8s %5d uses  %2d screens' % (k + 'px', n, len(where[k])))

print('\n================ CARD PADDING (top/left) ================')
bag, where = merge('pad')
print('%d distinct padding pairs' % len(bag))
for k, n in bag.most_common(20):
    print('  %-12s %5d uses  %2d screens' % (k, n, len(where[k])))

print('\n================ PRIMARY BUTTON, SCREEN BY SCREEN ================')
shapes = Counter()
for slug, r in report.items():
    for b in r['buttons']:
        shapes['h=%s rad=%s fs=%s fw=%s bg=%s' % (b['h'], b['rad'], b['fs'],
                                                  b['fw'], b['bg'])] += 1
print('%d distinct button shapes' % len(shapes))
for k, n in shapes.most_common(25):
    print('  %3dx  %s' % (n, k))

print('\n================ BUTTON HEIGHTS ================')
h = Counter()
for r in report.values():
    for b in r['buttons']:
        h[round(b['h'])] += 1
for k in sorted(h):
    print('  %3dpx  %4d buttons  %s' % (k, h[k], '' if k >= 44 else '<-- under 44'))

print('\n================ FORM CONTROL HEIGHTS ================')
h = Counter()
for slug, r in report.items():
    for c in r['controls']:
        h[(round(c['h']), c['fs'], c['rad'])] += 1
for k in sorted(h):
    print('  h=%-5s fs=%-5s rad=%-5s  %4d controls' % (k[0], k[1], k[2], h[k]))

print('\n================ PAGE HEADER ================')
for slug, r in report.items():
    heads = r['heads']
    first = heads[0] if heads else None
    tags = ''.join(x['tag'][1] for x in heads[:12])
    print('  %-20s first=%-14s %-18s levels=%s'
          % (slug,
             ('%s %gpx/%s' % (first['tag'], first['fs'], first['fw'])) if first else 'NONE',
             ('"%s"' % first['t'][:16]) if first else '',
             tags or '-'))

print('\n================ CONTENT GUTTER ================')
for slug, r in report.items():
    g = r['gutters']
    print('  %-20s %s' % (slug, '  '.join('%s=%s' % kv for kv in g.items())))
