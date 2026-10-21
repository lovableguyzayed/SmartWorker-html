"""How a worker actually gets paid.

The app worked out what each person was owed to the rupee and then had
nowhere to send it — no bank account, UPI id, Aadhaar or PAN anywhere in the
schema. These fields are held so a payment can be made and recorded; none of
them touches a calculation.

Aadhaar is sensitive personal data, so it is shown masked and must never
reach a payslip. That is checked here rather than trusted.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
import routes as R  # noqa: E402
import bulk  # noqa: E402,F401
import models as m  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []
NAME = 'Payment Details Probe'


def check(label, got, want):
    if got == want:
        print('  PASS %-58s %s' % (label, repr(got)[:20]))
    else:
        failures.append(label)
        print('  FAIL %-58s got=%r want=%r' % (label, got, want))


# --- the validators -------------------------------------------------------
good = {'bank_account_name': 'Sunita Devi', 'bank_account_number': '123456789012',
        'bank_ifsc': 'hdfc0001234', 'upi_id': 'sunita@okaxis',
        'aadhaar_number': '1234 5678 9012', 'pan_number': 'abcde1234f'}
values, errors = R.clean_payment_details(good)
check('a good set validates', errors, [])
check('IFSC is upper-cased', values['bank_ifsc'], 'HDFC0001234')
check('PAN is upper-cased', values['pan_number'], 'ABCDE1234F')
check('spaces are stripped from Aadhaar', values['aadhaar_number'], '123456789012')
check('the account holder name keeps its spaces',
      values['bank_account_name'], 'Sunita Devi')

values, errors = R.clean_payment_details({})
check('every field is optional', errors, [])
check('a blank field is stored as nothing, not an empty string',
      set(values.values()), {None})

bad = {'bank_account_number': '12', 'bank_ifsc': 'NOTANIFSC',
       'upi_id': 'no-at-sign', 'aadhaar_number': '123', 'pan_number': '12345'}
values, errors = R.clean_payment_details(bad)
check('each bad field is reported', len(errors), 5)
check('a rejected field is not stored', set(values.values()), {None})

# A near-miss must not slip through.
for field, value in (('bank_ifsc', 'HDFC1001234'),      # 5th char must be 0
                     ('pan_number', 'ABCD12345F'),      # wrong shape
                     ('aadhaar_number', '12345678901'),  # 11 digits
                     ('bank_account_number', '1234567890123456789')):  # 19
    _v, errs = R.clean_payment_details({field: value})
    check('%s rejects %r' % (field, value), len(errs), 1)

# --- masking --------------------------------------------------------------
with app.app_context():
    w = m.Worker(full_name='x', aadhaar_number='123456789012')
    check('Aadhaar is masked to the last four', w.masked_aadhaar, 'XXXX XXXX 9012')
    check('a malformed Aadhaar masks to nothing rather than leaking',
          m.Worker(full_name='x', aadhaar_number='123').masked_aadhaar, None)
    check('no Aadhaar masks to nothing', m.Worker(full_name='x').masked_aadhaar, None)
    check('has_payment_details needs a real route to the money',
          m.Worker(full_name='x').has_payment_details, False)
    check('a UPI id alone counts',
          m.Worker(full_name='x', upi_id='a@b').has_payment_details, True)
    check('an account number without IFSC does not count',
          m.Worker(full_name='x', bank_account_number='1').has_payment_details, False)

# --- round trip through the form -----------------------------------------
with app.app_context():
    m.Worker.query.filter_by(full_name=NAME).delete()
    db.session.commit()

with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test', 'password': 'demo12345'},
           follow_redirects=True)
    c.post('/add_worker', data=dict(
        full_name=NAME, phone='9000000333', department='Civil', position='Helper',
        join_date='2026-10-01', pay_type='daily', daily_rate='700',
        employee_type='Contract', status='active', **good), follow_redirects=True)

    with app.app_context():
        w = m.Worker.query.filter_by(full_name=NAME).first()
    check('the worker saved', bool(w), True)
    check('the account number round-tripped', w.bank_account_number, '123456789012')
    check('the IFSC round-tripped', w.bank_ifsc, 'HDFC0001234')
    check('the UPI id round-tripped', w.upi_id, 'sunita@okaxis')
    check('the PAN round-tripped', w.pan_number, 'ABCDE1234F')

    profile = c.get('/worker/%d' % w.id).get_data(as_text=True)
    check('the profile shows the masked Aadhaar', 'XXXX XXXX 9012' in profile, True)
    check('the profile never shows the full Aadhaar',
          '123456789012' in profile.replace(w.bank_account_number or '', ''), False)

    # The payslip is handed to the worker and sent to banks and contractors.
    slip = c.get('/payroll/slip/%d' % w.id).get_data(as_text=True)
    for label, value in (('Aadhaar', w.aadhaar_number),
                         ('masked Aadhaar', 'XXXX XXXX 9012'),
                         ('PAN', w.pan_number)):
        check('the payslip does not carry the %s' % label, value in slip, False)

    report = c.get('/worker/%d/report' % w.id).get_data(as_text=True)
    check('the worker report does not carry the Aadhaar',
          w.aadhaar_number in report, False)

    # A bad field must not lose the rest of the save.
    c.post('/edit_worker/%d' % w.id, data=dict(
        full_name=NAME, phone='9000000333', department='Civil', position='Helper',
        join_date='2026-10-01', pay_type='daily', daily_rate='700',
        employee_type='Contract', status='active',
        bank_account_number='123456789012', bank_ifsc='RUBBISH',
        upi_id='sunita@okaxis'), follow_redirects=True)
    with app.app_context():
        w = m.Worker.query.filter_by(full_name=NAME).first()
    check('a bad IFSC is dropped', w.bank_ifsc, None)
    check('the good fields around it survive', w.bank_account_number, '123456789012')

    # Deactivating a worker posts a form with no payment fields in it. An
    # earlier version of this change applied the payment details there too,
    # which silently wiped a worker's bank account the moment anyone
    # deactivated them.
    with app.app_context():
        w = m.Worker.query.filter_by(full_name=NAME).first()
        w.bank_ifsc = 'HDFC0001234'
        db.session.commit()
        wid = w.id
    c.post('/worker/%d/deactivate' % wid, follow_redirects=True)
    with app.app_context():
        w = db.session.get(m.Worker, wid)
        check('deactivating a worker keeps their bank account',
              w.bank_account_number, '123456789012')
        check('deactivating a worker keeps their IFSC', w.bank_ifsc, 'HDFC0001234')
        check('deactivating a worker keeps their UPI id', w.upi_id, 'sunita@okaxis')

with app.app_context():
    m.Worker.query.filter_by(full_name=NAME).delete()
    db.session.commit()

print('\n%d failed' % len(failures))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
