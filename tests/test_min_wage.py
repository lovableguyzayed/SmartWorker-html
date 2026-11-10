"""A wage below the notified floor should be said out loud, not refused.

Minimum wages in India are notified by the state government, by skill
category — unskilled, semi-skilled, skilled — and they move twice a year
with the variable dearness allowance. Uttarakhand's unskilled daily rate
is not a number this application can know, and it certainly cannot know
which category a man at a crusher falls into.

So the figure is the employer's to type in, against the position names he
already uses on his own workers, and what the application does with it is
WARN. Never refuse. Three reasons, and the third is the real one:

  * a floor the app enforced would be a floor from the wrong year the
    moment a notification lapsed, and the employer would be locked out of
    saving a correct wage by a stale number;
  * piece rate, apprentices, part days and a man kept on at the old rate
    pending arrears are all real and none of them are a form error;
  * refused, the employer types in a figure he does not mean in order to
    get past the screen — and then the rate on record is a lie. A warning
    he reads and overrides leaves the truth in the database.

What is checked here:

  * no floor set, no warning — nothing until the employer says so
  * a daily rate under the floor warns, and the save still goes through
    with the figure he actually typed
  * a rate at or above the floor says nothing
  * a monthly man is judged by the monthly figure, not the daily one
  * an hourly man is judged on eight hours, and the warning says so
  * project (piece) rate is never judged at all
  * the floor for his own position wins over the catch-all floor
  * a floor left blank checks nothing

Run from the project root:  python3 tests/test_min_wage.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from sqlalchemy import text

from app import app, db
import models as m
import routes  # noqa: F401
import bulk    # noqa: F401

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-60s %r' % ('OK' if ok else 'FAIL', label, got))


app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

MARK = 'ZZMinWage'
made = []


def clear_floors():
    with app.app_context():
        db.session.execute(text('delete from minimum_wages'))
        db.session.commit()


with app.app_context():
    m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
        synchronize_session=False)
    db.session.commit()
    admin = m.User.query.filter_by(role='admin').first()
    account = admin.account_id

    def make(suffix, **kw):
        w = m.Worker(account_id=account, worker_id='ZZMW' + suffix,
                     full_name=MARK + ' ' + suffix, phone='90000009' + suffix,
                     position=kw.pop('position', 'Helper'),
                     department='Civil', employee_type='permanent',
                     join_date=routes.today_ist(), status='active', **kw)
        db.session.add(w)
        db.session.commit()
        made.append(w.id)
        return w.id

    daily_id = make('01', pay_type='daily', daily_rate=400)
    monthly_id = make('02', pay_type='monthly', monthly_salary=9000)
    hourly_id = make('03', pay_type='hourly', hourly_rate=40)
    project_id = make('04', pay_type='project', project_rate=50000)
    skilled_id = make('05', pay_type='daily', daily_rate=600,
                      position='Operator')

clear_floors()


def floor_rows():
    with app.app_context():
        return db.session.execute(text(
            'select category, daily_amount, monthly_amount '
            'from minimum_wages order by id')).fetchall()


try:
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})

        def set_floor(category, daily='', monthly='', hours=''):
            """Set the floor for a category. Setting it again replaces it."""
            return client.post('/settings/minimum_wage', data={
                'category': category, 'hours_per_day': hours,
                'daily_amount': daily, 'monthly_amount': monthly,
            }, follow_redirects=True).get_data(as_text=True)

        def save_worker(worker_id, **fields):
            """Save him unchanged but for what is passed, and return the page."""
            with app.app_context():
                w = db.session.get(m.Worker, worker_id)
                data = {
                    'full_name': w.full_name, 'phone': w.phone,
                    'position': w.position, 'department': w.department,
                    'employee_type': w.employee_type,
                    'join_date': w.join_date.isoformat(),
                    'pay_type': w.pay_type, 'status': 'active',
                    'daily_rate': w.daily_rate or '',
                    'monthly_salary': w.monthly_salary or '',
                    'hourly_rate': w.hourly_rate or '',
                    'project_rate': w.project_rate or '',
                }
            data.update(fields)
            return client.post('/edit_worker/%d' % worker_id, data=data,
                               follow_redirects=True).get_data(as_text=True)

        warned = 'minimum wage you have set'

        # --------------------------------------------------------------
        print('--- nothing until the employer sets a floor ---')
        page = save_worker(daily_id, daily_rate='400')
        check('no floor set, nothing is said', warned in page, False)

        # --------------------------------------------------------------
        print('\n--- a daily rate under the floor is said out loud ---')
        set_floor('', daily='500')
        check('the floor is stored', floor_rows(), [('', 500.0, None)])
        page = save_worker(daily_id, daily_rate='400')
        check('₹400 against a ₹500 floor warns', warned in page, True)
        check('and the warning carries both figures',
              '₹400 a day, below the ₹500 a day' in page, True)
        with app.app_context():
            check('but the rate saved is the one he typed',
                  float(db.session.get(m.Worker, daily_id).daily_rate), 400.0)

        print('\n--- at the floor, and above it, it says nothing ---')
        check('exactly ₹500 is not below it',
              warned in save_worker(daily_id, daily_rate='500'), False)
        check('₹650 is not below it',
              warned in save_worker(daily_id, daily_rate='650'), False)

        # --------------------------------------------------------------
        print('\n--- a monthly man is judged on the monthly figure ---')
        page = save_worker(monthly_id, monthly_salary='9000')
        check('a daily floor alone judges no monthly man',
              warned in page, False)
        set_floor('', daily='500', monthly='13000')
        rows = floor_rows()
        check('setting the same category again replaces it, not adds',
              len(rows), 1)
        check('and it now carries the monthly figure too',
              rows[0][2], 13000.0)
        check('₹9,000 against a ₹13,000 floor warns',
              warned in save_worker(monthly_id, monthly_salary='9000'), True)
        check('₹14,000 does not',
              warned in save_worker(monthly_id, monthly_salary='14000'),
              False)

        # --------------------------------------------------------------
        print('\n--- an hourly man is judged on eight hours ---')
        # ₹40 x 8 = ₹320, under the ₹500 floor.
        page = save_worker(hourly_id, hourly_rate='40')
        check('₹40 an hour warns', warned in page, True)
        check('and the warning says what a day was taken to be',
              'a day of 8 hours' in page, True)
        check('₹70 an hour (₹560 a day) does not',
              warned in save_worker(hourly_id, hourly_rate='70'), False)

        # A crusher that runs a ten-hour shift should be measured against
        # its own day, not somebody else's.
        set_floor('', daily='500', monthly='13000', hours='10')
        check('₹70 an hour over a ten-hour day is ₹700, still fine',
              warned in save_worker(hourly_id, hourly_rate='70'), False)
        check('₹45 an hour over a ten-hour day is ₹450, under the floor',
              warned in save_worker(hourly_id, hourly_rate='45'), True)
        set_floor('', daily='500', monthly='13000')
        check('and back on an eight-hour day ₹45 (₹360) is still under',
              warned in save_worker(hourly_id, hourly_rate='45'), True)
        check('while ₹65 (₹520) is not',
              warned in save_worker(hourly_id, hourly_rate='65'), False)

        # --------------------------------------------------------------
        print('\n--- piece rate is never judged ---')
        check('a project rate is not a daily wage',
              warned in save_worker(project_id, project_rate='1'), False)

        # --------------------------------------------------------------
        print('\n--- his own position beats the catch-all ---')
        set_floor('Operator', daily='800')
        check('two floors now', len(floor_rows()), 2)
        check('an Operator on ₹600 is under the Operator floor',
              warned in save_worker(skilled_id, daily_rate='600'), True)
        check('a Helper on ₹600 is over the catch-all floor',
              warned in save_worker(daily_id, daily_rate='600'), False)
        check('and the Operator floor is matched whatever the case',
              warned in save_worker(skilled_id, daily_rate='600',
                                    position='operator'), True)

        # --------------------------------------------------------------
        print('\n--- a floor left blank checks nothing ---')
        clear_floors()
        set_floor('', daily='', monthly='')
        check('a floor with no figure in it is not stored',
              floor_rows(), [])
        check('and so nothing is said',
              warned in save_worker(daily_id, daily_rate='1'), False)
finally:
    with app.app_context():
        if made:
            m.Worker.query.filter(m.Worker.id.in_(made)).delete(
                synchronize_session=False)
        db.session.execute(text('delete from minimum_wages'))
        db.session.commit()
        print('\n--- and this test leaves nothing behind ---')
        check('its workers are gone',
              m.Worker.query.filter(
                  m.Worker.full_name.like(MARK + '%')).count(), 0)
        check('and no floor of its own remains',
              db.session.execute(
                  text('select count(*) from minimum_wages')).scalar(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The floor is the employer\'s figure, and the app says so rather '
      'than refusing.')
