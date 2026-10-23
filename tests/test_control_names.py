"""A control that shows no word must at least carry a name.

Icons suit this audience — several of the people using it read slowly, and
several read Devanagari or nothing — but an icon with no name is a quiz:
unknowable until you press it and find out what it did. The attendance
status buttons were always the good case, wordless but labelled. The
workers list was the bad one: three mystery glyphs on every card, no text,
no aria-label, no title, repeated down the roster.

This drives the real pages rather than reading the templates, because a
label can be lost to a Jinja branch that only one role ever sees.
"""
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from playwright.sync_api import sync_playwright

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5102
B = 'http://127.0.0.1:%d' % PORT

PROBE = r"""
() => {
  const out = [];
  for (const el of document.querySelectorAll(
        'button, a[href], input[type=submit], [role=button]')) {
    if (!el.checkVisibility || !el.checkVisibility()) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    if ((el.innerText || el.value || '').trim()) continue;   // it says something
    if (el.getAttribute('aria-label') || el.getAttribute('title')) continue;
    const icon = el.querySelector('i, svg');
    out.push({
      icon: icon ? (icon.className.baseVal || icon.className || '').toString() : '-',
      cls: (el.className || '').toString().slice(0, 48)
    });
  }
  return out;
}
"""

PATHS = ['/', '/workers', '/attendance', '/payroll', '/payroll/preview',
         '/transactions', '/closures', '/assignments', '/scan', '/settings',
         '/profile', '/notifications', '/add_worker']

# Strip the interface of anything that supplies text by accident, so each
# control is judged on the name it carries rather than on the demo data.
#
# The dashboard's notification bell is why this exists. It had no
# aria-label at all, and for months it looked labelled: with unread mail
# the badge renders a number, the number counts as text, and the check
# passes. Empty the unread count and the bell is a bare glyph announcing
# nothing. Tests that only fail on certain data are tests that hide things.
from app import app, db          # noqa: E402
import models as m               # noqa: E402

with app.app_context():
    _was_unread = [n.id for n in
                   m.Notification.query.filter_by(is_read=False).all()]
    if _was_unread:
        m.Notification.query.filter(
            m.Notification.id.in_(_was_unread)).update(
                {'is_read': True}, synchronize_session=False)
        db.session.commit()

# main.py hardcodes port 5000, and a test that fights a dev server for a
# port is a test that fails for the wrong reason. Start our own.
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
        server.kill()
        sys.exit('could not start a server on %s' % B)

    from app import app
    import models as m
    with app.app_context():
        w = m.Worker.query.order_by(m.Worker.id).first()
        extra = ['/worker/%d' % w.id, '/edit_worker/%d' % w.id,
                 '/worker_attendance/%d' % w.id, '/worker/%d/login/powers' % w.id]

    naked = []
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(600)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        # wait_for_url rather than a string predicate: Playwright
        # evaluates those with eval(), which the page's
        # Content-Security-Policy refuses.

        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        for path in PATHS + extra:
            pg.goto(B + path, wait_until='domcontentloaded')
            pg.wait_for_timeout(1200)
            rows = pg.evaluate(PROBE)
            print('  %-4s %-30s %d wordless and unnamed'
                  % ('OK' if not rows else 'FAIL', path, len(rows)))
            for r in rows:
                naked.append((path, r['icon'], r['cls']))
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)
    if _was_unread:
        with app.app_context():
            m.Notification.query.filter(
                m.Notification.id.in_(_was_unread)).update(
                    {'is_read': False}, synchronize_session=False)
            db.session.commit()

print('\n%d controls across %d screens show no word and carry no name'
      % (len(naked), len(PATHS) + len(extra)))
for path, icon, cls in naked[:30]:
    print('   %-28s %-28s %s' % (path, icon, cls))
sys.exit(1 if naked else 0)
