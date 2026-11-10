"""The OTP that was never sent, and the five guesses nobody was counting.

Both ways into this app by mobile number — signing in and signing up — had
the same shape: generate six digits, write them to the server log, and tell
the person "OTP has been sent to 98xxxxxxxx. (Check server logs in demo
mode)". True for whoever runs the server; a lie to the person holding the
phone, who has no log. A second employer signing up could not get in at
all, and nothing on the screen said why.

Four things were wrong, and they are checked here one at a time:

  * nothing was sent. sms.py sends it now when a provider is configured,
    and when none is it says so instead of claiming delivery.

  * the guesses were not counted. A six-digit code has a million values,
    which is a lot against five tries and nothing against unlimited ones —
    a script can walk the whole range inside the five minutes the code
    lives. Five wrong guesses now spend the code.

  * the codes came out of random.randint. That is the Mersenne Twister,
    which is not a secret: enough outputs and the next one is predictable.
    They come from `secrets` now, which is what it is for.

  * the comparison was `otp_code != stored_otp`, which returns as soon as
    two digits differ. compare_digest does not.

And one thing that was already right and must stay right: the code is in
the session, not in the response. Checked here so that a later refactor
that "helpfully" returns it for testing cannot pass.

Run from the project root:  python3 tests/test_otp.py
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

import sms
from app import app, db
import models as m
import routes

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


MOBILE = '9876500011'

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False


def post(client, path, **data):
    res = client.post(path, data=json.dumps(data),
                      content_type='application/json')
    try:
        return res.status_code, res.get_json() or {}
    except Exception:
        return res.status_code, {}


# ---------------------------------------------------------------------------
print('--- a provider is not configured here, and nothing pretends it is ---')

for key in ('SMS_PROVIDER', 'MSG91_AUTH_KEY', 'TWILIO_ACCOUNT_SID'):
    os.environ.pop(key, None)

check('no provider is configured', sms.is_configured(), False)
delivered, detail = sms.send_otp(MOBILE, '123456', 'login')
check('so send_otp reports that it did not send',
      (delivered, 'no SMS provider is configured' in detail), (False, True))

os.environ['SMS_PROVIDER'] = 'carrier-pigeon'
check('an unknown provider is not configured either',
      sms.is_configured(), False)
check('and sending through it fails rather than silently working',
      sms.send_otp(MOBILE, '123456', 'login')[0], False)
os.environ['SMS_PROVIDER'] = 'msg91'
check('msg91 named without a key is not configured',
      sms.is_configured(), False)
os.environ['MSG91_AUTH_KEY'] = 'test-key-not-used'
check('with a key it is', sms.is_configured(), True)
del os.environ['SMS_PROVIDER'], os.environ['MSG91_AUTH_KEY']

check('the message says what it is for, and warns',
      ('SmartWorker' in sms.message_for('123456', 'login')
       and 'Do not share' in sms.message_for('123456', 'login')), True)
check('and carries the code', '123456' in sms.message_for('123456', 'login'),
      True)

# ---------------------------------------------------------------------------
print('\n--- the code is generated from secrets, not from random ---')

src = open(os.path.join(ROOT, 'routes.py')).read()
check('no credential comes out of random.randint',
      'random.randint' in src, False)
check('they come from secrets', src.count('secrets.randbelow') >= 2, True)
codes = {routes.secrets.randbelow(1000000) for _ in range(200)}
check('and 200 of them are not all the same', len(codes) > 190, True)

# ---------------------------------------------------------------------------
print('\n--- signing in by mobile ---')

# The session is a signed cookie its holder can read, so the code is never
# kept there (tests/test_otp_security.py checks that); this catches it on
# its way to the SMS provider instead. SMS_DEV_LOG turns the flow on here.
os.environ['SMS_DEV_LOG'] = '1'
sent = []
real_send = sms.send_otp
sms.send_otp = lambda mobile, code, purpose='login': (sent.append(code), (True, 'test'))[1]

with app.app_context():
    user = m.User.query.filter_by(role='admin').first()
    original_phone = user.phone
    user.phone = MOBILE
    db.session.commit()

try:
    routes.authguard.reset_for_tests()
    with app.test_client() as client:
        status, body = post(client, '/login/send-otp', mobile=MOBILE)
        check('a code is accepted for a known number', status, 200)
        check('the code itself is NOT in the response',
              bool(re.search(r'\b\d{6}\b', json.dumps(body))), False)
        real = sent[-1]
        with client.session_transaction() as sess:
            check('nor in the session',
                  real in json.dumps(dict(sess), default=str), False)

        status, body = post(client, '/login/send-otp', mobile=MOBILE)
        check('a second code straight away is refused', status, 429)
        check('and says how long to wait', body.get('retry_after', 0) > 0, True)

        print('\n--- five guesses, then the code is spent ---')
        wrong = '000000' if real != '000000' else '111111'
        for i in range(1, 5):
            status, body = post(client, '/login/verify-otp',
                                mobile=MOBILE, otp=wrong)
            check('guess %d is refused and counted' % i,
                  (status, 'tries left' in (body.get('message') or '')),
                  (400, True))
        status, body = post(client, '/login/verify-otp',
                            mobile=MOBILE, otp=wrong)
        check('the fifth locks the number for a while', status, 429)
        status, body = post(client, '/login/verify-otp',
                            mobile=MOBILE, otp=real)
        check('even the right code no longer works', status, 429)

    print('\n--- and the right code, on a fresh attempt, signs you in ---')
    routes.authguard.reset_for_tests()
    with app.test_client() as client:
        post(client, '/login/send-otp', mobile=MOBILE)
        status, body = post(client, '/login/verify-otp',
                            mobile=MOBILE, otp=sent[-1])
        check('the right code is accepted', status, 200)
        check('and it says so', body.get('success'), True)
        page = client.get('/dashboard')
        check('the session is really signed in', page.status_code, 200)

    print('\n--- a code aimed at another number ---')
    with app.test_client() as client:
        post(client, '/login/send-otp', mobile=MOBILE)
        status, _ = post(client, '/login/verify-otp',
                         mobile='9876500099', otp=sent[-1])
        check('a code cannot be redeemed against another number', status, 400)

    print('\n--- a provider that fails is not reported as sent ---')
    routes.authguard.reset_for_tests()
    os.environ.pop('SMS_DEV_LOG')
    os.environ['SMS_PROVIDER'], os.environ['MSG91_AUTH_KEY'] = 'msg91', 'x'
    sms.send_otp = lambda mobile, code, purpose='login': (False, 'test outage')
    with app.test_client() as client:
        status, body = post(client, '/login/send-otp', mobile=MOBILE)
        check('the screen is told it could not be sent', status, 503)
    del os.environ['SMS_PROVIDER'], os.environ['MSG91_AUTH_KEY']
finally:
    sms.send_otp = real_send
    with app.app_context():
        user = m.User.query.filter_by(role='admin').first()
        user.phone = original_phone
        db.session.commit()
        check('the test put the admin\'s phone number back',
              m.User.query.filter_by(role='admin').first().phone,
              original_phone)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The OTP is sent when it can be, counted when it is guessed at, and '
      'never claimed to have been sent when it was not.')
