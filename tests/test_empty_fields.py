"""An empty box is empty, not the word "None".

Open a worker who has no email address and the Email box on the edit
screen contained, literally:

    None

Twelve boxes did it: email, address, the monthly salary, the hourly and
project rates, the leave deduction, and six more. The markup said

    {{ worker.email if worker else '' }}

which guards the ADD screen, where there is no worker at all, and never
the far commoner case of a worker who exists with nothing in that box —
Jinja prints None for a null column.

It is not only ugly. The address is a <textarea>, so "None" sat in it as
real text: an employer who opens a worker to change his wage and presses
Save has just set that man's address to the word None. The same for the
email box. The number boxes are quieter, because a browser refuses to
show a non-numeric value in <input type=number>, which is the only
reason this went unnoticed for so long.

Checked on three screens rather than one, because the add screen and the
edit screen share this template and the bug lived in the difference
between them.

Run from the project root:  python3 tests/test_empty_fields.py
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from app import app, db
import models as m
import routes  # noqa: F401
import bulk    # noqa: F401

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, got))


app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

MARK = 'ZZEmptyFields'
made = []

with app.app_context():
    m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
        synchronize_session=False)
    db.session.commit()

    admin = m.User.query.filter_by(role='admin').first()
    # A worker with as little filled in as the form allows: this is what a
    # mukadam typed in at a gate with a name and a daily rate and nothing
    # else, which is most of them.
    bare = m.Worker(
        account_id=admin.account_id, worker_id='ZZEF01',
        full_name=MARK + ' Bare', phone='9000000777',
        position='Helper', department='Civil', employee_type='permanent',
        join_date=routes.today_ist(), pay_type='daily', daily_rate=500,
        status='active')
    db.session.add(bare)
    db.session.commit()
    made.append(bare.id)
    worker_id = bare.id
    check('the fixture really has nothing in those columns',
          [bare.email, bare.address, bare.monthly_salary, bare.hourly_rate,
           bare.project_rate, bare.leave_deduction_per_day],
          [None, None, None, None, None, None])

try:
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})

        print('\n--- no box says "None" ---')
        for path in ('/edit_worker/%d' % worker_id, '/add_worker'):
            html = client.get(path).get_data(as_text=True)
            printed = re.findall(r'value="None"|>None<|>\s*None\s*</textarea>',
                                 html)
            check('%-22s prints it %d time(s)' % (path, len(printed)),
                  printed, [])

        print('\n--- and the boxes really are empty, not missing ---')
        html = client.get('/edit_worker/%d' % worker_id).get_data(as_text=True)
        for name in ('email', 'monthly_salary', 'hourly_rate',
                     'project_rate'):
            hit = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, html) \
                or re.search(r'value="([^"]*)"[^>]*name="%s"' % name, html)
            check('%-16s is there and blank' % name,
                  hit is not None and hit.group(1) == '', True)
        area = re.search(r'name="address"[^>]*>(.*?)</textarea>', html, re.S)
        check('address      is there and blank',
              area is not None and area.group(1).strip() == '', True)

        print('\n--- saving it back does not invent an address ---')
        # The real damage: open a worker to change his wage, press Save,
        # and the word None becomes his address.
        client.post('/edit_worker/%d' % worker_id, data={
            'full_name': MARK + ' Bare', 'phone': '9000000777',
            'position': 'Helper', 'department': 'Civil',
            'employee_type': 'permanent',
            'join_date': routes.today_ist().isoformat(),
            'pay_type': 'daily', 'daily_rate': '550', 'status': 'active',
            'email': '', 'address': '',
        }, follow_redirects=True)
        with app.app_context():
            after = db.session.get(m.Worker, worker_id)
            check('the address is still empty', after.address or '', '')
            check('and the email too', after.email or '', '')
            check('while the wage did change', float(after.daily_rate), 550.0)

        print('\n--- a worker who HAS those details still shows them ---')
        with app.app_context():
            filled = db.session.get(m.Worker, worker_id)
            filled.email = 'ramesh@example.com'
            filled.address = 'Village Road, Haridwar'
            db.session.commit()
        html = client.get('/edit_worker/%d' % worker_id).get_data(as_text=True)
        check('the email is in its box', 'ramesh@example.com' in html, True)
        check('and the address in its own',
              'Village Road, Haridwar' in html, True)
finally:
    with app.app_context():
        if made:
            m.Worker.query.filter(m.Worker.id.in_(made)).delete(
                synchronize_session=False)
        db.session.commit()
        print('\n--- and this test leaves nothing behind ---')
        check('its worker is gone',
              m.Worker.query.filter(
                  m.Worker.full_name.like(MARK + '%')).count(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('An empty box is empty.')
