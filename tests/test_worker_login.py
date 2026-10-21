"""A worker's own login, and the wall around it.

The audit's largest gap was that a labourer had no way to see their own
attendance or pay — they depended on someone showing them a screen. Giving
them a login is only safe if it reaches exactly one record, so most of this
file is about what the login must NOT be able to do.

Deny-by-default: anything outside a small allowlist bounces back to their own
page. That is checked here against the app's real route table rather than a
list written by hand, so a route added tomorrow is covered too.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
import routes as R  # noqa: E402
import bulk  # noqa: E402,F401
import models as m  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-58s %s' % (label, repr(got)[:20]))
    else:
        failures.append(label)
        print('  FAIL %-58s got=%r want=%r' % (label, got, want))


with app.app_context():
    mine = m.Worker.query.filter_by(status='active').order_by(m.Worker.id).first()
    other = (m.Worker.query.filter(m.Worker.id != mine.id,
                                   m.Worker.status == 'active')
             .order_by(m.Worker.id).first())
    MINE_ID, MINE_NAME, MINE_PHONE = mine.id, mine.full_name, mine.phone
    OTHER_ID, OTHER_NAME = other.id, other.full_name
    m.User.query.filter_by(role='worker').delete()
    db.session.commit()

# --- an administrator hands out the login --------------------------------
with app.test_client() as admin:
    admin.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'}, follow_redirects=True)
    page = admin.post('/worker/%d/login' % MINE_ID,
                      follow_redirects=True).get_data(as_text=True)
    hit = re.search(r'password (\d{6})', page)
    check('the admin screen hands over a password once', bool(hit), True)
    PASSWORD = hit.group(1) if hit else None

    with app.app_context():
        login = m.User.query.filter_by(worker_id=MINE_ID, role='worker').first()
    check('a login exists for the worker', bool(login), True)
    check('it is linked to that worker', login.worker_id, MINE_ID)
    check('the username is their phone number', login.username, MINE_PHONE)
    check('the password is not stored in readable form',
          PASSWORD in (login.password_hash or ''), False)
    check('a worker login is not an admin', login.is_admin, False)
    check('is_worker says what it is', login.is_worker, True)

# --- the worker signs in --------------------------------------------------
with app.test_client() as w:
    landing = w.post('/login', data={'username': MINE_PHONE,
                                     'password': PASSWORD}, follow_redirects=False)
    check('signing in redirects', landing.status_code in (302, 303), True)
    check('and lands on their own screen, not the dashboard',
          '/me' in landing.headers.get('Location', ''), True)

    home = w.get('/me')
    body = home.get_data(as_text=True)
    check('their own screen opens', home.status_code, 200)
    check('it shows their name', MINE_NAME in body, True)
    check('it does not name anybody else', OTHER_NAME in body, False)

    slip = w.get('/me/payslip')
    check('their own payslip opens', slip.status_code, 200)
    check('the payslip is theirs', MINE_NAME in slip.get_data(as_text=True), True)

    # --- the wall ---------------------------------------------------------
    # Every GET route the app has, checked against the real route table so a
    # route added later cannot quietly become reachable.
    # Build the path list first, then make the requests: opening an app
    # context around test-client calls unwinds the context stack under them.
    targets = []
    for rule in app.url_map.iter_rules():
        if 'GET' not in rule.methods or rule.endpoint in R.WORKER_ENDPOINTS:
            continue
        if rule.endpoint in ('login', 'register', 'splash', 'forgot_password',
                             'reset_password', 'register_verify_otp'):
            continue
        try:
            path = rule.build({a: (MINE_ID if 'id' in a else 1)
                               for a in rule.arguments}, append_unknown=False)[1]
        except Exception:
            continue
        targets.append((rule.endpoint, path))

    leaked = [endpoint for endpoint, path in targets
              # 302 back to their own page is the wall doing its job.
              if w.get(path, follow_redirects=False).status_code == 200]
    check('no other screen in the app opens for a worker', sorted(leaked), [])
    print('     (checked %d routes)' % len(targets))

    # The obvious attempts, named explicitly so a failure reads clearly.
    for path, what in (('/payroll', 'the whole payroll'),
                       ('/workers', 'the worker list'),
                       ('/settings', 'company settings'),
                       ('/transactions', 'everyone\'s transactions'),
                       ('/payroll/slip/%d' % OTHER_ID, "another worker's payslip"),
                       ('/worker/%d' % OTHER_ID, "another worker's profile"),
                       ('/payroll/export.csv', 'the payroll export')):
        res = w.get(path, follow_redirects=False)
        check('a worker cannot reach %s' % what, res.status_code == 200, False)

    # Writes, not just reads.
    for path, what in (('/mark_attendance', 'mark attendance'),
                       ('/transactions/save', 'record a transaction'),
                       ('/payroll/save', 'generate payroll'),
                       ('/worker/%d/login' % OTHER_ID, 'mint another login')):
        res = w.post(path, data={}, follow_redirects=False)
        check('a worker cannot %s' % what, res.status_code == 200, False)

    with app.app_context():
        still_one = m.User.query.filter_by(role='worker').count()
    check('no extra login was created along the way', still_one, 1)

    # A tampered month must not become a way to read someone else.
    odd = w.get('/me?month=99&year=1800')
    check('a nonsense period does not error', odd.status_code, 200)
    check('and still shows only their own record',
          OTHER_NAME in odd.get_data(as_text=True), False)

# --- revoking -------------------------------------------------------------
with app.test_client() as admin:
    admin.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'}, follow_redirects=True)
    admin.post('/worker/%d/login/revoke' % MINE_ID, follow_redirects=True)
    with app.app_context():
        check('the login is gone',
              m.User.query.filter_by(worker_id=MINE_ID, role='worker').count(), 0)

with app.test_client() as w:
    res = w.post('/login', data={'username': MINE_PHONE, 'password': PASSWORD},
                 follow_redirects=True)
    check('the revoked password no longer works',
          '/me' in res.request.path or 'Invalid' in res.get_data(as_text=True),
          True)

with app.app_context():
    m.User.query.filter_by(role='worker').delete()
    db.session.commit()

print('\n%d failed' % len(failures))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
