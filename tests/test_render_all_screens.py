"""Every screen, in both languages, must still answer 200.

The i18n pass touched 20 templates; a wrapped string that shadowed a variable
or a filter applied to the wrong type shows up as a 500 here and nowhere else.
"""
import sys
sys.path.insert(0, '/home/user/SmartWorker-html')
from app import app
import routes  # noqa: F401  — registers the routes
import bulk    # noqa: F401  — registers the multi-selection endpoints
import models as m

# The test client cannot produce a CSRF token, and this test is about
# rendering, not about the CSRF guard (which has its own coverage).
app.config['WTF_CSRF_ENABLED'] = False

PATHS = ['/dashboard', '/workers', '/attendance', '/payroll', '/transactions',
         '/closures', '/assignments', '/profile', '/settings', '/scan',
         '/notifications', '/payroll/preview', '/add_worker']

with app.app_context():
    w = m.Worker.query.order_by(m.Worker.id).first()
    PATHS += ['/worker/%d' % w.id, '/worker_attendance/%d' % w.id,
              '/worker/%d/report' % w.id, '/payroll/slip/%d' % w.id,
              '/edit_worker/%d' % w.id, '/id_card/%d' % w.id]

bad = []
for lang in ('en', 'hi'):
    with app.test_client() as c:
        c.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'},
               follow_redirects=True)
        with c.session_transaction() as s:
            s['lang'] = lang
        print('--- %s ---' % lang)
        for path in PATHS:
            r = c.get(path, follow_redirects=False)
            # A redirect here means the login did not stick, which would
            # make the whole sweep vacuous — so only 200 counts.
            ok = r.status_code == 200
            if not ok:
                bad.append((lang, path, r.status_code))
            print('  %-4s %-34s %s' % ('OK' if ok else 'FAIL', path, r.status_code))

print('\n%d paths x 2 languages, %d failed' % (len(PATHS), len(bad)))
for row in bad:
    print('  FAIL', row)
sys.exit(1 if bad else 0)
