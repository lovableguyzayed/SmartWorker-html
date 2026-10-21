"""A mukadam: a worker an administrator has put in charge of a few others.

The thing this design exists to prevent is a worker marking their own
attendance, so that is tested first and from several directions — the
stored list, the computed team, the roster screen, and the write itself.

The rest is the boundary: present and late only, no corrections, no
transactions without the power, and nobody outside the allotted list.
"""
import os
import re
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
import routes as R  # noqa: E402
import bulk  # noqa: E402,F401
import models as m  # noqa: E402
from timeutil import today_ist  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []
TODAY = today_ist()
DAY = TODAY - timedelta(days=1)


def check(label, got, want):
    if got == want:
        print('  PASS %-58s %s' % (label, repr(got)[:20]))
    else:
        failures.append(label)
        print('  FAIL %-58s got=%r want=%r' % (label, got, want))


with app.app_context():
    roster = (m.Worker.query.filter_by(status='active')
              .order_by(m.Worker.id).all())
    BOSS, A, B, OUTSIDER = roster[0], roster[1], roster[2], roster[3]
    IDS = {'boss': BOSS.id, 'a': A.id, 'b': B.id, 'out': OUTSIDER.id}
    NAMES = {k: m.Worker.query.get(v).full_name for k, v in IDS.items()}
    BOSS_PHONE = BOSS.phone
    m.User.query.filter_by(role='worker').delete()
    m.AttendanceRecord.query.filter(m.AttendanceRecord.date == DAY).delete()
    db.session.commit()

# --- an administrator sets it up -----------------------------------------
with app.test_client() as admin:
    admin.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'}, follow_redirects=True)
    page = admin.post('/worker/%d/login' % IDS['boss'],
                      follow_redirects=True).get_data(as_text=True)
    PASSWORD = re.search(r'password (\d{6})', page).group(1)

    # Grant attendance only, and deliberately try to put the supervisor on
    # their own team.
    admin.post('/worker/%d/login/powers' % IDS['boss'], data={
        'can_mark_attendance': '1',
        'team': [str(IDS['a']), str(IDS['b']), str(IDS['boss'])],
    }, follow_redirects=True)

    with app.app_context():
        login = m.User.query.filter_by(worker_id=IDS['boss'], role='worker').first()
        stored = login.worker_id_list
        team = login.supervisor_team_ids
    check('the powers saved', login.can_mark_attendance, True)
    check('transactions stay off until granted', login.can_record_transactions, False)
    check('the supervisor is not even stored on their own team',
          IDS['boss'] in stored, False)
    check('and the computed team excludes them too',
          IDS['boss'] in team, False)
    check('the two real workers are on the team', sorted(team),
          sorted([IDS['a'], IDS['b']]))

# --- the supervisor signs in ---------------------------------------------
with app.test_client() as s:
    s.post('/login', data={'username': BOSS_PHONE, 'password': PASSWORD},
           follow_redirects=True)

    roll = s.get('/me/team?date=%s' % DAY.isoformat())
    body = roll.get_data(as_text=True)
    check('the roll opens', roll.status_code, 200)
    check('it lists an assigned worker', NAMES['a'] in body, True)
    check('it does not list an unassigned worker', NAMES['out'] in body, False)
    check('the supervisor is not on their own roll',
          body.count(NAMES['boss']), 0)

    # mark present
    s.post('/me/team/mark', data={'worker_id': IDS['a'], 'status': 'present',
                                  'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        rec = m.AttendanceRecord.query.filter_by(worker_id=IDS['a'], date=DAY).first()
    check('marking an assigned worker works', bool(rec), True)
    check('it is stamped with who marked it', rec.marked_by if rec else None,
          login.id)
    check('and how', rec.marked_via if rec else None, 'supervisor')

    # a second tap closes the shift rather than being refused
    s.post('/me/team/mark', data={'worker_id': IDS['a'], 'status': 'present',
                                  'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        rec = m.AttendanceRecord.query.filter_by(worker_id=IDS['a'], date=DAY).first()
        rows = m.AttendanceRecord.query.filter_by(worker_id=IDS['a'], date=DAY).count()
    check('a second tap closes the shift', bool(rec.check_out_time), True)
    check('and does not create a second record', rows, 1)

    # --- the wall ---------------------------------------------------------
    # their own attendance, by every route available to them
    for status in ('present', 'late'):
        s.post('/me/team/mark', data={'worker_id': IDS['boss'], 'status': status,
                                      'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        own = m.AttendanceRecord.query.filter_by(worker_id=IDS['boss'], date=DAY).count()
    check('a supervisor cannot mark their own attendance', own, 0)

    # somebody else's worker
    s.post('/me/team/mark', data={'worker_id': IDS['out'], 'status': 'present',
                                  'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        outside = m.AttendanceRecord.query.filter_by(worker_id=IDS['out'],
                                                     date=DAY).count()
    check('nor anyone outside their list', outside, 0)

    # absent and leave are the administrator's
    for status in ('absent', 'leave'):
        s.post('/me/team/mark', data={'worker_id': IDS['b'], 'status': status,
                                      'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        b_rec = m.AttendanceRecord.query.filter_by(worker_id=IDS['b'], date=DAY).first()
    check('a supervisor cannot mark absent or leave', b_rec, None)

    # a correction
    with app.app_context():
        rec = m.AttendanceRecord.query.filter_by(worker_id=IDS['a'], date=DAY).first()
        rec.status = 'late'
        rec.check_out_time = None
        db.session.commit()
    s.post('/me/team/mark', data={'worker_id': IDS['a'], 'status': 'present',
                                  'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        rec = m.AttendanceRecord.query.filter_by(worker_id=IDS['a'], date=DAY).first()
    check('a supervisor cannot change a status that is already set',
          rec.status, 'late')

    # The admin form drops the supervisor from the team, so the check above
    # never exercised the second layer. Put their own id into the stored
    # list directly, the way a direct edit or a future bulk-assign could,
    # and check the guard inside the app still holds.
    with app.app_context():
        tampered = m.User.query.filter_by(worker_id=IDS['boss'], role='worker').first()
        tampered.assigned_worker_ids = '%d,%d' % (IDS['a'], IDS['boss'])
        db.session.commit()
        check('the stored list really does contain them now',
              IDS['boss'] in tampered.worker_id_list, True)
        check('but the team still excludes them',
              IDS['boss'] in tampered.supervisor_team_ids, False)
    roll = s.get('/me/team?date=%s' % DAY.isoformat()).get_data(as_text=True)
    check('and they are still not on their own roll',
          roll.count(NAMES['boss']), 0)
    s.post('/me/team/mark', data={'worker_id': IDS['boss'], 'status': 'present',
                                  'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        own = m.AttendanceRecord.query.filter_by(worker_id=IDS['boss'], date=DAY).count()
    check('and still cannot mark themselves with their id on the list', own, 0)

    # a future date
    s.post('/me/team/mark', data={'worker_id': IDS['a'], 'status': 'present',
                                  'date': (TODAY + timedelta(days=2)).isoformat()},
           follow_redirects=True)
    with app.app_context():
        future = m.AttendanceRecord.query.filter_by(
            worker_id=IDS['a'], date=TODAY + timedelta(days=2)).count()
    check('nor mark a future date', future, 0)

    # money, without the power
    with app.app_context():
        before = m.WorkerTransaction.query.filter_by(worker_id=IDS['a']).count()
    s.post('/me/team/transaction', data={'worker_id': IDS['a'], 'txn_type': 'advance',
                                         'amount': '500', 'date': DAY.isoformat()},
           follow_redirects=True)
    with app.app_context():
        after = m.WorkerTransaction.query.filter_by(worker_id=IDS['a']).count()
    check('no transaction without the power granted', after, before)

    # and everything else in the app
    for path in ('/payroll', '/workers', '/settings', '/transactions',
                 '/attendance', '/payroll/export.csv'):
        check('still cannot reach %s' % path,
              s.get(path, follow_redirects=False).status_code == 200, False)

# --- the administrator grants money powers -------------------------------
with app.test_client() as admin:
    admin.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'}, follow_redirects=True)
    admin.post('/worker/%d/login/powers' % IDS['boss'], data={
        'can_mark_attendance': '1', 'can_record_transactions': '1',
        'team': [str(IDS['a']), str(IDS['b'])],
    }, follow_redirects=True)

with app.test_client() as s:
    s.post('/login', data={'username': BOSS_PHONE, 'password': PASSWORD},
           follow_redirects=True)
    with app.app_context():
        before = m.WorkerTransaction.query.filter_by(worker_id=IDS['a']).count()
    s.post('/me/team/transaction', data={'worker_id': IDS['a'], 'txn_type': 'advance',
                                         'amount': '500', 'date': DAY.isoformat()},
           follow_redirects=True)
    with app.app_context():
        after = m.WorkerTransaction.query.filter_by(worker_id=IDS['a']).count()
        txn = (m.WorkerTransaction.query.filter_by(worker_id=IDS['a'])
               .order_by(m.WorkerTransaction.id.desc()).first())
        TXN_ID = txn.id
    check('now a transaction can be recorded', after, before + 1)
    check('stamped with who recorded it', txn.created_by, login.id)

    # but not unrecorded
    s.post('/transactions/%d/cancel' % TXN_ID, follow_redirects=True)
    s.post('/transactions/%d/delete' % TXN_ID, follow_redirects=True)
    with app.app_context():
        still = db.session.get(m.WorkerTransaction, TXN_ID)
    check('a supervisor cannot cancel it', still.status if still else None,
          'active')
    check('nor delete it', bool(still), True)

    # nor for someone off the list
    s.post('/me/team/transaction', data={'worker_id': IDS['out'], 'txn_type': 'advance',
                                         'amount': '500', 'date': DAY.isoformat()},
           follow_redirects=True)
    with app.app_context():
        outside = m.WorkerTransaction.query.filter_by(
            worker_id=IDS['out'], amount=500.0, date=DAY).count()
    check('nor record one for a worker off their list', outside, 0)

    # a zero or negative amount
    for bad in ('0', '-500'):
        s.post('/me/team/transaction', data={'worker_id': IDS['b'], 'txn_type': 'advance',
                                             'amount': bad, 'date': DAY.isoformat()},
               follow_redirects=True)
    with app.app_context():
        junk = m.WorkerTransaction.query.filter(
            m.WorkerTransaction.worker_id == IDS['b'],
            m.WorkerTransaction.amount <= 0).count()
    check('a zero or negative amount is refused', junk, 0)

# --- a plain worker login must gain nothing from any of this -------------
with app.test_client() as admin:
    admin.post('/login', data={'username': 'demo@acme.test',
                               'password': 'demo12345'}, follow_redirects=True)
    page = admin.post('/worker/%d/login' % IDS['a'],
                      follow_redirects=True).get_data(as_text=True)
    PLAIN_PW = re.search(r'password (\d{6})', page).group(1)
with app.app_context():
    PLAIN_PHONE = db.session.get(m.Worker, IDS['a']).phone

with app.test_client() as plain:
    plain.post('/login', data={'username': PLAIN_PHONE, 'password': PLAIN_PW},
               follow_redirects=True)
    for path in ('/me/team',):
        check('a plain worker cannot open the supervisor roll',
              plain.get(path, follow_redirects=False).status_code == 200, False)
    plain.post('/me/team/mark', data={'worker_id': IDS['b'], 'status': 'present',
                                      'date': DAY.isoformat()}, follow_redirects=True)
    with app.app_context():
        leaked = m.AttendanceRecord.query.filter_by(worker_id=IDS['b'], date=DAY).count()
    check('nor mark anybody', leaked, 0)

with app.app_context():
    m.User.query.filter_by(role='worker').delete()
    m.AttendanceRecord.query.filter(m.AttendanceRecord.date == DAY).delete()
    m.WorkerTransaction.query.filter(m.WorkerTransaction.date == DAY,
                                     m.WorkerTransaction.amount == 500.0).delete()
    db.session.commit()

print('\n%d failed' % len(failures))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
