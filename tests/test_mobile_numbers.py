"""A mobile number written the way Indians write it.

The number is the way into this app: it is what an OTP is sent to, what a
worker's own login is called, and what an employer types when he cannot
remember a username. It was handled by two functions that between them

    kept the digits and stopped, so

        +91 98765 43210  became  919876543210   ->  "No account found"
        09876543210      became  09876543210    ->  "No account found"

    and accepted anything from ten to fifteen digits, so

        0135 2345678     a landline              ->  accepted
        5123456789       cannot exist in India   ->  accepted
        1234567890                               ->  accepted

A '+91' and a leading zero are not typos. They are the same number, and a
person who writes their own number that way — most people do — was told
their account did not exist. That is the kind of thing that gets an app
deleted on the first evening.

Checked here:

  * every way the same number is written reaches the same ten digits.
  * what is not an Indian mobile is turned down: a landline, a number
    starting 0-5, too short, too long, letters.
  * the OTP screen finds the account for any of those spellings, including
    when the row in the database was stored in the OLD shape, because rows
    written before this fix still hold '+91 98765 43210'.
  * the whole 6-9 range is accepted. Jio numbers begin with 6, and a check
    written for "starts with 9" would lock out a good part of the country.

Run from the project root:  python3 tests/test_mobile_numbers.py
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from app import app, db
import models as m
import routes

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


TEN = '9876543210'

SAME_NUMBER = [
    '9876543210',
    '98765 43210',
    '98765-43210',
    '+91 98765 43210',
    '+919876543210',
    '91-98765-43210',
    '919876543210',
    '09876543210',
    '0091 9876543210',
    ' 9876543210 ',
    '(+91) 98765 43210',
]

NOT_A_MOBILE = [
    ('0135 2345678', 'a Dehradun landline'),
    ('5123456789', 'no Indian mobile starts with 5'),
    ('1234567890', 'nobody has this number'),
    ('98765', 'half a number'),
    ('98765432100000', 'too long'),
    ('', 'nothing at all'),
    ('abcdefghij', 'letters'),
    ('0000000000', 'all zeroes'),
]

print('--- one number, however it is written ---')
for written in SAME_NUMBER:
    check('%-20r -> ten digits' % written,
          routes.normalize_mobile_number(written), TEN)
check('and all of them are valid',
      all(routes.is_valid_mobile_number(w) for w in SAME_NUMBER), True)

print('\n--- and what is not a mobile number is turned down ---')
for written, why in NOT_A_MOBILE:
    check('%-16r %s' % (written, why),
          routes.is_valid_mobile_number(written), False)

print('\n--- every operator range, including the 6s ---')
for first in '6789':
    number = first + '123456789'
    check('%s... is accepted' % first,
          routes.is_valid_mobile_number(number), True)
for first in '012345':
    number = first + '123456789'
    check('%s... is not' % first,
          routes.is_valid_mobile_number(number), False)

# ---------------------------------------------------------------------------
print('\n--- the OTP screen finds the account, old row or new ---')

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

STORED_SHAPES = [
    (TEN, 'ten digits, as written today'),
    ('+91 98765 43210', 'the old shape, with +91 and spaces'),
    ('09876543210', 'the old shape, with a leading zero'),
]

with app.app_context():
    user = m.User.query.filter_by(role='admin').first()
    original = user.phone

try:
    for stored, description in STORED_SHAPES:
        with app.app_context():
            user = m.User.query.filter_by(role='admin').first()
            user.phone = stored
            db.session.commit()
        with app.app_context():
            found = routes.find_user_by_mobile('+91 98765 43210')
            check('stored as %-34s -> found' % description,
                  found is not None and found.phone == stored, True)
        with app.test_client() as client:
            res = client.post('/login/send-otp',
                              data=json.dumps({'mobile': '+91 98765 43210'}),
                              content_type='application/json')
            check('and the OTP screen accepts it (%s)' % description,
                  res.status_code, 200)

    with app.app_context():
        check('a number nobody has is still not found',
              routes.find_user_by_mobile('9000000001'), None)
finally:
    with app.app_context():
        user = m.User.query.filter_by(role='admin').first()
        user.phone = original
        db.session.commit()
        check('the test put the phone number back',
              m.User.query.filter_by(role='admin').first().phone, original)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('However the number is written, it is the same number — and an '
      'account written the old way is still found.')
