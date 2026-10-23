"""A worker with no pay rate must never be invisible.

Saving one is allowed on purpose — the rate may not be agreed yet — but
such a worker earns ₹0 every month, so the save warns and every screen that
shows money marks them. This is the one defect from the audit that costs
real wages if it stays quiet.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
import routes  # noqa: E402,F401
import bulk  # noqa: E402,F401
import models as m  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []
NAME = 'Zero Wage Probe'


def check(label, got, want):
    if got == want:
        print('  PASS %-54s %s' % (label, repr(got)[:26]))
    else:
        failures.append(label)
        print('  FAIL %-54s got=%r want=%r' % (label, got, want))


with app.app_context():
    m.Worker.query.filter_by(full_name=NAME).delete()
    db.session.commit()

with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test', 'password': 'demo12345'},
           follow_redirects=True)

    # Save a daily worker with the rate field left empty.
    r = c.post('/add_worker', data={
        'full_name': NAME, 'phone': '9000000222', 'department': 'Civil',
        'position': 'Helper', 'join_date': '2026-10-01', 'pay_type': 'daily',
        'daily_rate': '', 'employee_type': 'Contract', 'status': 'active',
    }, follow_redirects=True)
    body = r.get_data(as_text=True)

    with app.app_context():
        w = m.Worker.query.filter_by(full_name=NAME).first()
    check('the worker is still saved (the rate may not be agreed yet)',
          bool(w), True)
    check('the rate really is empty', w.daily_rate if w else None, 0.0)
    check('has_pay_rate reports the truth', w.has_pay_rate if w else None, False)
    check('the save warns about it', 'no pay rate yet' in body, True)

    for path, where in (('/workers', 'workers list'),
                        ('/payroll', 'payroll'),
                        ('/payroll/preview', 'payroll preview')):
        page = c.get(path).get_data(as_text=True)
        check('%s marks the worker' % where, 'No pay rate' in page, True)

    # And a worker who does have a rate must not be marked.
    with app.app_context():
        paid = m.Worker.query.filter(m.Worker.full_name != NAME,
                                     m.Worker.status == 'active').first()
        check('a worker with a rate is not marked', paid.has_pay_rate, True)
        check('pay_rate resolves per pay type',
              paid.pay_rate == getattr(paid, m.Worker.PAY_RATE_FIELD[paid.pay_type]),
              True)

    # Every pay type, not just daily.
    with app.app_context():
        for pt, field in m.Worker.PAY_RATE_FIELD.items():
            probe = m.Worker(full_name='x', pay_type=pt, account_id=1)
            setattr(probe, field, 0.0)
            check('%s with 0 has no rate' % pt, probe.has_pay_rate, False)
            setattr(probe, field, 500.0)
            check('%s with 500 has a rate' % pt, probe.has_pay_rate, True)

with app.app_context():
    m.Worker.query.filter_by(full_name=NAME).delete()
    db.session.commit()

print('\n%d failed' % len(failures))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
