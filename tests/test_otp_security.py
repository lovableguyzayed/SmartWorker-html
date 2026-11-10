"""Nobody signs in as somebody else by knowing their mobile number.

The one-time code used to sit in the session cookie as plain digits. That
cookie is signed, not encrypted, so asking for a code for any number and
base64-decoding your own cookie was enough to sign in as its owner — the
admin included. Nothing counted wrong codes or wrong passwords either.

Runs on a throwaway database of its own, so it needs no fixture.
"""
import base64
import json
import os
import re
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
os.environ['DATABASE_URL'] = 'sqlite:///' + _db.name
os.environ.setdefault('SESSION_SECRET', 'otp-test')
os.environ.setdefault('ADMIN_DEFAULT_PASSWORD', 'otp-test-admin')

from app import app, db  # noqa: E402
import routes  # noqa: E402
import authguard  # noqa: E402
import models as m  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-62s %s' % (label, repr(got)[:30]))
    else:
        failures.append(label)
        print('  FAIL %-62s got=%r want=%r' % (label, got, want))


sent = []
routes._deliver_otp = lambda purpose, mobile, code: sent.append(code)


def cookie_payload(client):
    raw = client.get_cookie('session').value
    compressed = raw.startswith('.')
    body = raw.lstrip('.').split('.')[0]
    body += '=' * (-len(body) % 4)
    data = base64.urlsafe_b64decode(body)
    return (zlib.decompress(data) if compressed else data).decode()


def post(client, path, **body):
    r = client.post(path, data=json.dumps(body), content_type='application/json')
    return r.status_code, r.get_json()


with app.app_context():
    acc = m.Account(name='OTP Co')
    db.session.add(acc)
    db.session.flush()
    owner = m.User(username='owner', email='owner@otp.test', full_name='Owner',
                   role='admin', account_id=acc.id, phone='9876543210')
    owner.set_password('owner-pass-1')
    # An older row, saved before numbers were cleaned: the country code kept.
    legacy = m.User(username='legacy', email='legacy@otp.test', full_name='Legacy',
                    role='admin', account_id=acc.id, phone='919812345678')
    legacy.set_password('legacy-pass-1')
    db.session.add_all([owner, legacy])
    db.session.commit()

print('--- numbers, however they are typed ---')
for typed in ('9876543210', '+91 98765 43210', '+91-98765-43210', '09876543210',
              '919876543210', ' 98765-43210 '):
    check('%r is one number' % typed, authguard.indian_mobile(typed), '9876543210')
for bad in ('12345', '5876543210', '98765432101', '', None, '+1 415 555 0100'):
    check('%r is not an Indian mobile' % (bad,), authguard.indian_mobile(bad), '')

print('--- the code is not in the cookie ---')
authguard.reset_for_tests()
with app.test_client() as c:
    status, body = post(c, '/login/send-otp', mobile='+91 98765 43210')
    check('a code is sent', (status, body['success']), (200, True))
    code = sent[-1]
    payload = cookie_payload(c)
    check('the six digits are nowhere in the cookie', code in payload, False)
    check('no key in the cookie is the old plaintext one',
          bool(re.search(r'"(login|register)_otp"\s*:', payload)), False)

    status, body = post(c, '/login/verify-otp', mobile='9876543210', otp=code)
    check('the right code signs in', (status, body['success']), (200, True))
    check('it signs in the owner of that number',
          c.get('/dashboard').status_code, 200)

print('--- a used code cannot be replayed ---')
authguard.reset_for_tests()
with app.test_client() as c:
    post(c, '/login/send-otp', mobile='9876543210')
    code = sent[-1]
    saved = c.get_cookie('session').value
    post(c, '/login/verify-otp', mobile='9876543210', otp=code)
with app.test_client() as attacker:
    attacker.set_cookie('session', saved)
    status, body = post(attacker, '/login/verify-otp', mobile='9876543210', otp=code)
    check('the same code from a copied cookie is refused', status, 400)
    check('and nobody is signed in', attacker.get('/dashboard').status_code, 302)

print('--- guessing is cut off on the server ---')
authguard.reset_for_tests()
with app.test_client() as c:
    post(c, '/login/send-otp', mobile='9876543210')
    code = sent[-1]
    before = c.get_cookie('session').value
    wrong = '000000' if code != '000000' else '111111'
    codes = [post(c, '/login/verify-otp', mobile='9876543210', otp=wrong)[0] for _ in range(5)]
    check('five wrong codes are each refused', codes, [400] * 5)
    status, _ = post(c, '/login/verify-otp', mobile='9876543210', otp=code)
    check('then even the right code waits', status, 429)
    c.set_cookie('session', before)
    status, _ = post(c, '/login/verify-otp', mobile='9876543210', otp=code)
    check('and replaying the cookie from before does not reset it', status, 429)

print('--- sending is limited too ---')
authguard.reset_for_tests()
with app.test_client() as c:
    check('first send', post(c, '/login/send-otp', mobile='9876543210')[0], 200)
    status, body = post(c, '/login/send-otp', mobile='9876543210')
    check('a second send inside 30 seconds waits', status, 429)
    check('and says how long', body.get('retry_after', 0) > 0, True)
for i in range(2):
    with app.test_client() as c:   # fresh cookies dodge the 30s timer...
        post(c, '/login/send-otp', mobile='9876543210')
with app.test_client() as c:       # ...but not the per-number count
    check('a fourth code for one number in 15 minutes is refused',
          post(c, '/login/send-otp', mobile='9876543210')[0], 429)

print('--- older rows still match ---')
authguard.reset_for_tests()
with app.test_client() as c:
    status, body = post(c, '/login/send-otp', mobile='98123 45678')
    check('a number stored as 91XXXXXXXXXX is found from ten digits', status, 200)
    status, body = post(c, '/register/send-otp', mobile='09812345678')
    check('and cannot be registered a second time', status, 409)

print('--- passwords ---')
authguard.reset_for_tests()
with app.test_client() as c:
    codes = [c.post('/login', data={'username': 'owner', 'password': 'nope%d' % i}).status_code
             for i in range(8)]
    check('eight wrong passwords are each refused', codes, [200] * 8)
    r = c.post('/login', data={'username': 'owner', 'password': 'owner-pass-1'})
    check('the ninth try waits, even with the right password', r.status_code, 429)
authguard.reset_for_tests()
with app.test_client() as c:
    r = c.post('/login', data={'username': 'owner', 'password': 'owner-pass-1'})
    check('the right password works when nobody has been guessing', r.status_code, 303)
    r = c.post('/login', data={'username': '+91 98765 43210', 'password': 'owner-pass-1'})
    check('signing in with the number typed with +91 works', r.status_code, 303)

print('--- signing out ---')
authguard.reset_for_tests()
with app.test_client() as c:
    c.post('/login', data={'username': 'owner', 'password': 'owner-pass-1'})
    check('a plain link to /logout does not sign out',
          (c.get('/logout').status_code, c.get('/dashboard').status_code), (302, 200))
    check('pressing Sign out (a POST) does', c.post('/logout').status_code, 303)
    check('and the dashboard is closed after it', c.get('/dashboard').status_code, 302)

os.unlink(_db.name)
print()
if failures:
    print('FAILED %d: %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('all OTP and password checks passed')
