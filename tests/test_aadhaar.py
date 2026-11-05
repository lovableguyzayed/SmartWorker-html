"""Keep four digits of an Aadhaar, not twelve — and do not lose them.

A full Aadhaar number was being stored for every worker who had one. It
is not needed to pay anybody: a bank account and an IFSC, or a UPI id, is
what moves the money. It was held only so an employer could recognise
which card a man showed him at the gate, and the last four digits do
that. Twelve, if the database ever got out, are somebody's identity — and
this is a free-tier Postgres behind a public repository.

So from here on only the last four are kept. The profile screen already
showed it masked; what it showed masked was a full number sitting in the
database behind it.

The hard part is not the masking. It is that once the form stops echoing
the number back, the Aadhaar box is EMPTY — and an empty box that means
"delete" turns every ordinary save into data loss. Open a worker to
change his wage, press Save, and his Aadhaar is gone. So:

    empty box                  -> leave what is on file
    the remove checkbox        -> and only then, delete it
    twelve digits typed in     -> keep the last four
    four digits typed in       -> keep those four
    anything else              -> say so, and change nothing

Rows saved before this are NOT rewritten. Twelve digits already in the
database stay there until somebody saves that worker again, because
quietly destroying what an employer entered is not this application's
decision to make. Both lengths are therefore checked.

Run from the project root:  python3 tests/test_aadhaar.py
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
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

MARK = 'ZZAadhaar'
made = []

with app.app_context():
    m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
        synchronize_session=False)
    db.session.commit()
    admin = m.User.query.filter_by(role='admin').first()
    worker = m.Worker(
        account_id=admin.account_id, worker_id='ZZAA01',
        full_name=MARK + ' Ramesh', phone='9000000881',
        position='Helper', department='Civil', employee_type='permanent',
        join_date=routes.today_ist(), pay_type='daily', daily_rate=500,
        status='active')
    db.session.add(worker)
    db.session.commit()
    made.append(worker.id)
    worker_id = worker.id


def stored():
    with app.app_context():
        return db.session.get(m.Worker, worker_id).aadhaar_number


def set_stored(value):
    with app.app_context():
        db.session.get(m.Worker, worker_id).aadhaar_number = value
        db.session.commit()


try:
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})

        def save(**fields):
            """Save him, changing only what is passed. Returns the page."""
            with app.app_context():
                w = db.session.get(m.Worker, worker_id)
                data = {
                    'full_name': w.full_name, 'phone': w.phone,
                    'position': w.position, 'department': w.department,
                    'employee_type': w.employee_type,
                    'join_date': w.join_date.isoformat(),
                    'pay_type': 'daily', 'daily_rate': w.daily_rate or '',
                    'status': 'active',
                }
            data.update(fields)
            return client.post('/edit_worker/%d' % worker_id, data=data,
                               follow_redirects=True).get_data(as_text=True)

        # --------------------------------------------------------------
        print('--- twelve digits in, four digits kept ---')
        save(aadhaar_number='123456789012')
        check('only the last four are in the database', stored(), '9012')
        with app.app_context():
            check('and the profile shows it as a card',
                  db.session.get(m.Worker, worker_id).masked_aadhaar,
                  'XXXX XXXX 9012')

        print('\n--- spaces and dashes, as printed on the card ---')
        save(aadhaar_number='2345 6789 0123')
        check('spaces do not defeat it', stored(), '0123')
        save(aadhaar_number='3456-7890-1234')
        check('nor do dashes', stored(), '1234')

        print('\n--- four digits typed in are accepted as they are ---')
        save(aadhaar_number='5678')
        check('the last four is all he has to hand', stored(), '5678')

        # --------------------------------------------------------------
        print('\n--- THE TRAP: an empty box must not delete it ---')
        # The box on the form is empty, because there is no full number
        # left to put in it. An employer who opens a worker to change his
        # wage and presses Save must not lose the Aadhaar by doing so.
        set_stored('4321')
        save(daily_rate='560')
        check('the Aadhaar survives an ordinary save', stored(), '4321')
        with app.app_context():
            check('while the wage did change',
                  float(db.session.get(m.Worker, worker_id).daily_rate),
                  560.0)
        save()
        check('and it survives being saved again', stored(), '4321')

        print('\n--- and removing one has to be said out loud ---')
        save(aadhaar_remove='1')
        check('the checkbox removes it', stored(), None)
        check('and then the profile shows nothing at all',
              None if stored() else 'nothing', 'nothing')

        # --------------------------------------------------------------
        print('\n--- a number that is not a number changes nothing ---')
        set_stored('7777')
        page = save(aadhaar_number='12345')
        check('five digits are refused', stored(), '7777')
        check('and the employer is told why',
              'Aadhaar' in page and '12 digits' in page, True)
        page = save(aadhaar_number='abcd')
        check('letters are refused too', stored(), '7777')

        # --------------------------------------------------------------
        print('\n--- the form never puts a full number back on screen ---')
        set_stored('123456789012')  # a row saved before this change
        html = client.get('/edit_worker/%d' % worker_id).get_data(as_text=True)
        check('the twelve digits are nowhere in the page',
              '123456789012' in html, False)
        box = re.search(r'name="aadhaar_number"[^>]*value="([^"]*)"', html) \
            or re.search(r'value="([^"]*)"[^>]*name="aadhaar_number"', html)
        check('the box is there and empty',
              box is not None and box.group(1) == '', True)
        check('but what is on file is shown, masked',
              'XXXX XXXX 9012' in html, True)
        check('and there is a way to remove it',
              'aadhaar_remove' in html, True)

        print('\n--- a row saved before this is read, not rewritten ---')
        with app.app_context():
            w = db.session.get(m.Worker, worker_id)
            check('twelve digits still mask correctly',
                  w.masked_aadhaar, 'XXXX XXXX 9012')
        check('and merely looking at the screen did not change them',
              stored(), '123456789012')
        save(daily_rate='570')
        check('an ordinary save leaves even a legacy number alone',
              stored(), '123456789012')

        print('\n--- a worker with none has no "on file" line ---')
        set_stored(None)
        html = client.get('/edit_worker/%d' % worker_id).get_data(as_text=True)
        check('no checkbox when there is nothing to remove',
              'aadhaar_remove' in html, False)
        with app.app_context():
            check('and nothing to mask',
                  db.session.get(m.Worker, worker_id).masked_aadhaar, None)
        html = client.get('/add_worker').get_data(as_text=True)
        check('the add screen has an empty box and no checkbox',
              'aadhaar_remove' in html, False)
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
print('Four digits are kept, twelve are not stored, and an empty box '
      'deletes nothing.')
