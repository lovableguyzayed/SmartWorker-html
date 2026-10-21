"""Every bulk action, run for real, checked against the database.

Press and hold a row and a bar offers what can be done to everything you
have picked. Thirty-five actions across eleven lists reach one endpoint,
POST /api/bulk/<scope>. A screenshot proves the bar opens; it proves
nothing about whether the button under your thumb changes anything.

So each action is run against real rows and the database is read back
afterwards to see whether it did what its label promises. Every change is
undone before the next one, and the deletes run against rows made for the
purpose, because a delete that works is a delete that destroys something.

The action ids are not written out here. They are read from the bar the
application renders, so a button that exists in the interface and not on
the server — or the reverse — shows up as a missing pair rather than
quietly going untested.
"""
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app import app, db
import routes  # noqa: F401
import bulk    # noqa: F401
import models as m
from timeutil import today_ist

# The CSRF guard has its own coverage; this is about what the actions do.
app.config['WTF_CSRF_ENABLED'] = False

ACCOUNT = 1
results = []     # (scope, action, ok, note)


def safely(fn, *a, **kw):
    """One scope falling over must not take the rest of the sweep with it."""
    try:
        fn(*a, **kw)
    except Exception as err:
        with app.app_context():
            db.session.rollback()
        record(getattr(fn, '__name__', '?'), '(crashed)', False,
               '%s: %s' % (type(err).__name__, str(err)[:90]))


def record(scope, action, ok, note):
    results.append((scope, action, ok, note))
    print('  %-4s %-16s %-10s %s' % ('OK' if ok else 'FAIL', scope, action, note))


def rendered_actions(client):
    """What the interface actually offers, scope by scope."""
    pages = ['/workers', '/attendance', '/payroll', '/transactions',
             '/assignments', '/closures', '/notifications', '/settings']
    out = {}
    for path in pages:
        html = client.get(path).get_data(as_text=True)
        marks = [(mo.start(), mo.group(1))
                 for mo in re.finditer(r'data-ms-bar="([^"]+)"', html)]
        for i, (pos, scope) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
            body = html[pos:end]
            out.setdefault(scope, []).extend(
                re.findall(r'data-ms-action="([^"]+)"', body))
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def run(client, scope, action, ids, **extra):
    data = {'action': action}
    for i in ids:
        data.setdefault('ids', []).append(str(i))
    data.update(extra)
    r = client.post('/api/bulk/%s' % scope, data=data)
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {}


# ----------------------------------------------------------------------
# each scope: set up rows, run the action, read the database back, undo
# ----------------------------------------------------------------------

def check_workers(c, actions):
    with app.app_context():
        ws = m.Worker.query.filter_by(status='active').order_by(m.Worker.id).limit(2).all()
        ids = [w.id for w in ws]
        before = {w.id: w.status for w in ws}

    for action, want in (('deactivate', 'inactive'), ('activate', 'active')):
        if action not in actions:
            continue
        code, body = run(c, 'workers', action, ids)
        with app.app_context():
            now = {w.id: w.status for w in m.Worker.query.filter(m.Worker.id.in_(ids))}
        ok = code == 200 and all(v == want for v in now.values())
        record('workers', action, ok, '%d workers -> %s' % (len(ids), set(now.values())))

    with app.app_context():
        for wid, st in before.items():
            m.Worker.query.filter_by(id=wid).update({'status': st})
        db.session.commit()

    if 'delete' in actions:
        with app.app_context():
            tmp = m.Worker(account_id=ACCOUNT, worker_id='ZZTMP1',
                           full_name='Temporary — bulk delete test',
                           phone='9000000001', position='Helper',
                           department='Civil', employee_type='temporary',
                           status='active', join_date=today_ist(),
                           pay_type='daily', daily_rate=500)
            db.session.add(tmp)
            db.session.commit()
            tid = tmp.id
        code, body = run(c, 'workers', 'delete', [tid])
        with app.app_context():
            gone = m.Worker.query.filter_by(id=tid).first() is None
            if not gone:
                m.Worker.query.filter_by(id=tid).delete()
                db.session.commit()
        record('workers', 'delete', code == 200 and gone,
               'a throwaway worker was created and is %s' % ('gone' if gone else 'STILL THERE'))


def check_attendance(c, actions):
    when = today_ist()
    cols = [col.name for col in m.AttendanceRecord.__table__.columns]
    with app.app_context():
        snap = [{col: getattr(r, col) for col in cols}
                for r in m.AttendanceRecord.query.filter_by(date=when).all()]
        ids = [w.id for w in m.Worker.query.filter_by(status='active')
               .order_by(m.Worker.id).limit(3).all()]

    try:
        for action in ('present', 'late', 'absent', 'leave', 'half_day', 'close'):
            if action not in actions:
                continue
            code, body = run(c, 'attendance', action, ids, date=when.isoformat())
            with app.app_context():
                rows = m.AttendanceRecord.query.filter(
                    m.AttendanceRecord.date == when,
                    m.AttendanceRecord.worker_id.in_(ids)).all()
                got = {r.worker_id: r.status for r in rows}
                closed = sum(1 for r in rows if r.check_out_time)
            if action == 'close':
                ok = code == 200
                note = '%d shift(s) carry a check-out time' % closed
            elif action == 'half_day':
                # Half day is derived from how long the shift ran, not stored
                # as a status, so the check is that a record now exists.
                ok = code == 200 and len(got) == len(ids)
                note = 'a shift of half the scheduled minutes was written'
            else:
                ok = code == 200 and all(v == action for v in got.values())
                note = '%d workers -> %s' % (len(ids), set(got.values()) or 'nothing')
            record('attendance', action, ok, note)
    finally:
        with app.app_context():
            m.AttendanceRecord.query.filter_by(date=when).delete()
            db.session.commit()
            for row in snap:
                db.session.add(m.AttendanceRecord(**row))
            db.session.commit()
            back = m.AttendanceRecord.query.filter_by(date=when).count()
        record('attendance', '(restore)', back == len(snap),
               'the day is back to its %d original record(s)' % len(snap))


def check_payroll(c, actions):
    when = today_ist()
    with app.app_context():
        ids = [w.id for w in m.Worker.query.filter_by(status='active')
               .order_by(m.Worker.id).limit(2).all()]
        existing = {r.worker_id: r.status for r in m.PayrollRecord.query.filter(
            m.PayrollRecord.worker_id.in_(ids),
            m.PayrollRecord.month == when.month,
            m.PayrollRecord.year == when.year)}
        made_now = []

    if 'generate' in actions:
        code, body = run(c, 'payroll', 'generate', ids,
                         month=str(when.month), year=str(when.year))
        with app.app_context():
            rows = m.PayrollRecord.query.filter(
                m.PayrollRecord.worker_id.in_(ids),
                m.PayrollRecord.month == when.month,
                m.PayrollRecord.year == when.year).all()
            made_now = [r.id for r in rows if r.worker_id not in existing]
            ok = code == 200 and len(rows) == len(ids)
        record('payroll', 'generate', ok,
               '%d payroll record(s) for %02d/%d' % (len(rows), when.month, when.year))

    for action, want in (('paid', 'paid'), ('pending', 'pending')):
        if action not in actions:
            continue
        code, body = run(c, 'payroll', action, ids,
                         month=str(when.month), year=str(when.year))
        with app.app_context():
            got = {r.worker_id: r.status for r in m.PayrollRecord.query.filter(
                m.PayrollRecord.worker_id.in_(ids),
                m.PayrollRecord.month == when.month,
                m.PayrollRecord.year == when.year)}
        ok = code == 200 and got and all(v == want for v in got.values())
        record('payroll', action, ok, 'status -> %s' % (set(got.values()) or 'nothing'))

    with app.app_context():
        if made_now:
            m.PayrollRecord.query.filter(m.PayrollRecord.id.in_(made_now)).delete(
                synchronize_session=False)
        for wid, st in existing.items():
            m.PayrollRecord.query.filter(
                m.PayrollRecord.worker_id == wid,
                m.PayrollRecord.month == when.month,
                m.PayrollRecord.year == when.year).update({'status': st})
        db.session.commit()
    record('payroll', '(restore)', True,
           'removed %d generated record(s), put %d status(es) back'
           % (len(made_now), len(existing)))


def check_transactions(c, actions):
    with app.app_context():
        txns = m.WorkerTransaction.query.order_by(m.WorkerTransaction.id).limit(2).all()
        ids = [t.id for t in txns]
        before = {t.id: t.status for t in txns}

    for action, want in (('cancel', 'cancelled'), ('restore', 'active')):
        if action not in actions or not ids:
            continue
        code, body = run(c, 'transactions', action, ids)
        with app.app_context():
            got = {t.id: t.status for t in m.WorkerTransaction.query.filter(
                m.WorkerTransaction.id.in_(ids))}
        ok = code == 200 and all(v == want for v in got.values())
        record('transactions', action, ok, 'status -> %s' % set(got.values()))

    with app.app_context():
        for tid, st in before.items():
            m.WorkerTransaction.query.filter_by(id=tid).update({'status': st})
        db.session.commit()

    if 'delete' in actions:
        with app.app_context():
            wid = m.Worker.query.filter_by(status='active').first().id
            tmp = m.WorkerTransaction(account_id=ACCOUNT, worker_id=wid,
                                      txn_type='advance', amount=1,
                                      date=today_ist(), status='active',
                                      description='Temporary — bulk delete test')
            db.session.add(tmp)
            db.session.commit()
            tid = tmp.id
        code, body = run(c, 'transactions', 'delete', [tid])
        with app.app_context():
            gone = m.WorkerTransaction.query.filter_by(id=tid).first() is None
            if not gone:
                m.WorkerTransaction.query.filter_by(id=tid).delete()
                db.session.commit()
        record('transactions', 'delete', code == 200 and gone,
               'a throwaway transaction is %s' % ('gone' if gone else 'STILL THERE'))


def check_assignments(c, actions):
    with app.app_context():
        site = m.Site.query.filter_by(status='active').first()
        project = m.Project.query.filter(m.Project.status != 'archived').first()
        # Somebody with no current assignment, so assigning is a real change.
        assigned = {a.worker_id for a in m.ProjectAssignment.query.filter_by(status='active')}
        free = [w.id for w in m.Worker.query.filter_by(status='active')
                .order_by(m.Worker.id) if w.id not in assigned][:1]
        site_id, project_id = site.id, (project.id if project else None)

    if 'assign' in actions and free:
        code, body = run(c, 'assignments', 'assign', free,
                         site_id=str(site_id),
                         project_id=str(project_id or ''),
                         start_date=today_ist().isoformat())
        with app.app_context():
            rows = m.ProjectAssignment.query.filter(
                m.ProjectAssignment.worker_id.in_(free),
                m.ProjectAssignment.status == 'active').all()
            made = [r.id for r in rows]
            ok = code == 200 and bool(rows)
        record('assignments', 'assign', ok,
               '%d assignment(s) created' % len(made))
        with app.app_context():
            if made:
                m.ProjectAssignment.query.filter(
                    m.ProjectAssignment.id.in_(made)).delete(synchronize_session=False)
                db.session.commit()
    elif 'assign' in actions:
        record('assignments', 'assign', False,
               'every worker is already assigned; nothing to test against')

    if 'end' in actions:
        cols = [col.name for col in m.ProjectAssignment.__table__.columns]
        with app.app_context():
            a = m.ProjectAssignment.query.filter_by(status='active').first()
            snap = {col: getattr(a, col) for col in cols} if a else None
            wid = a.worker_id if a else None
        if snap:
            code, body = run(c, 'assignments', 'end', [wid],
                             end_date=today_ist().isoformat())
            with app.app_context():
                after = m.ProjectAssignment.query.filter_by(id=snap['id']).first()
                ended = after is None or after.status != 'active' or after.end_date
            record('assignments', 'end', code == 200 and bool(ended),
                   'the assignment is %s' % ('ended' if ended else 'STILL ACTIVE'))
            with app.app_context():
                m.ProjectAssignment.query.filter_by(id=snap['id']).delete()
                db.session.commit()
                db.session.add(m.ProjectAssignment(**snap))
                db.session.commit()
            record('assignments', '(restore)', True, 'the assignment is back as it was')
        else:
            record('assignments', 'end', False, 'no active assignment to end')


def check_notifications(c, actions):
    with app.app_context():
        ns = m.Notification.query.order_by(m.Notification.id).limit(2).all()
        ids = [n.id for n in ns]
        before = {n.id: n.is_read for n in ns}

    for action, want in (('read', True), ('unread', False)):
        if action not in actions or not ids:
            continue
        code, body = run(c, 'notifications', action, ids)
        with app.app_context():
            got = {n.id: bool(n.is_read) for n in m.Notification.query.filter(
                m.Notification.id.in_(ids))}
        ok = code == 200 and all(v == want for v in got.values())
        record('notifications', action, ok, 'is_read -> %s' % set(got.values()))

    with app.app_context():
        for nid, was in before.items():
            m.Notification.query.filter_by(id=nid).update({'is_read': was})
        db.session.commit()

    if 'delete' in actions:
        with app.app_context():
            tmp = m.Notification(account_id=ACCOUNT, title='Temporary',
                                 body='bulk delete test', category='attendance')
            db.session.add(tmp)
            db.session.commit()
            nid = tmp.id
        code, body = run(c, 'notifications', 'delete', [nid])
        with app.app_context():
            gone = m.Notification.query.filter_by(id=nid).first() is None
            if not gone:
                m.Notification.query.filter_by(id=nid).delete()
                db.session.commit()
        record('notifications', 'delete', code == 200 and gone,
               'a throwaway notification is %s' % ('gone' if gone else 'STILL THERE'))


ENTITY = {'sites': (lambda: m.Site, dict(name='Temporary site')),
          'projects': (lambda: m.Project, dict(name='Temporary project')),
          'tasks': (lambda: m.WorkTask, dict(name='Temporary task')),
          'departments': (lambda: m.Department, dict(name='Temporary dept'))}


def check_entity(c, scope, actions):
    model_of, seed = ENTITY[scope]
    with app.app_context():
        model = model_of()
        rows = model.query.order_by(model.id).limit(2).all()
        ids = [r.id for r in rows]
        before = {r.id: r.status for r in rows}

    for action, want in (('archive', 'archived'), ('restore', 'active')):
        if action not in actions or not ids:
            continue
        code, body = run(c, scope, action, ids)
        with app.app_context():
            model = model_of()
            got = {r.id: r.status for r in model.query.filter(model.id.in_(ids))}
        ok = code == 200 and all(v == want for v in got.values())
        record(scope, action, ok, 'status -> %s' % set(got.values()))

    with app.app_context():
        model = model_of()
        for rid, st in before.items():
            model.query.filter_by(id=rid).update({'status': st})
        db.session.commit()

    if 'delete' in actions:
        with app.app_context():
            model = model_of()
            tmp = model(account_id=ACCOUNT, status='active', **seed)
            db.session.add(tmp)
            db.session.commit()
            tid = tmp.id
        code, body = run(c, scope, 'delete', [tid])
        with app.app_context():
            model = model_of()
            gone = model.query.filter_by(id=tid).first() is None
            if not gone:
                model.query.filter_by(id=tid).delete()
                db.session.commit()
        record(scope, 'delete', code == 200 and gone,
               'a throwaway row is %s' % ('gone' if gone else 'STILL THERE'))


def check_attendance_users(c, actions):
    with app.app_context():
        u = m.User(account_id=ACCOUNT, username='tmp-bulk-user',
                   email='tmp-bulk@worker.invalid', full_name='Temporary user',
                   role='attendance', status='active')
        u.set_password('tmp12345') if hasattr(u, 'set_password') else None
        db.session.add(u)
        db.session.commit()
        uid = u.id

    # The handler writes 'disabled', not 'inactive'. The first version of
    # this expected the wrong word and called the application broken.
    for action, want in (('disable', 'disabled'), ('enable', 'active')):
        if action not in actions:
            continue
        code, body = run(c, 'attendance-users', action, [uid])
        with app.app_context():
            got = m.User.query.filter_by(id=uid).first()
            now = got.status if got else None
        record('attendance-users', action, code == 200 and now == want,
               'status -> %s' % now)

    if 'delete' in actions:
        code, body = run(c, 'attendance-users', 'delete', [uid])
        with app.app_context():
            gone = m.User.query.filter_by(id=uid).first() is None
        record('attendance-users', 'delete', code == 200 and gone,
               'the throwaway user is %s' % ('gone' if gone else 'STILL THERE'))
    with app.app_context():
        m.User.query.filter_by(id=uid).delete()
        db.session.commit()


def check_closures(c):
    """The closures list is empty unless a closure is still ahead of today."""
    with app.app_context():
        made = []
        for days, reason in ((7, 'Temporary — bulk test A'),
                             (9, 'Temporary — bulk test B')):
            cd = m.ClosureDay(account_id=ACCOUNT, date=today_ist() + timedelta(days=days),
                              reason=reason, type='holiday', scope='company',
                              allow_attendance=False)
            db.session.add(cd)
            made.append(cd)
        db.session.commit()
        ids = [cd.id for cd in made]

    html = c.get('/closures').get_data(as_text=True)
    marks = [(mo.start(), mo.group(1))
             for mo in re.finditer(r'data-ms-bar="([^"]+)"', html)]
    acts = []
    for i, (pos, scope) in enumerate(marks):
        if scope == 'closures':
            end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
            acts = re.findall(r'data-ms-action="([^"]+)"', html[pos:end])
    record('closures', '(bar renders)', bool(acts), 'offers %s' % (acts or 'nothing'))

    # The bar offers unlock/lock, not allow/lock — read off what it
    # renders rather than what seemed likely.
    for action, want in (('unlock', True), ('lock', False)):
        if action not in acts:
            continue
        code, body = run(c, 'closures', action, ids)
        with app.app_context():
            got = {cd.id: bool(cd.allow_attendance)
                   for cd in m.ClosureDay.query.filter(m.ClosureDay.id.in_(ids))}
        ok = code == 200 and all(v == want for v in got.values())
        record('closures', action, ok, 'allow_attendance -> %s' % set(got.values()))

    if 'delete' in acts:
        code, body = run(c, 'closures', 'delete', ids)
        with app.app_context():
            left = m.ClosureDay.query.filter(m.ClosureDay.id.in_(ids)).count()
        record('closures', 'delete', code == 200 and left == 0,
               '%d of the throwaway closures remain' % left)

    with app.app_context():
        m.ClosureDay.query.filter(m.ClosureDay.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


# ----------------------------------------------------------------------

with app.test_client() as client:
    client.post('/login', data={'username': 'demo@acme.test',
                                'password': 'demo12345'}, follow_redirects=True)
    offered = rendered_actions(client)
    print('the interface offers %d actions across %d lists:'
          % (sum(len(v) for v in offered.values()), len(offered)))
    for scope, acts in sorted(offered.items()):
        print('   %-18s %s' % (scope, ' '.join(acts)))
    print()

    safely(check_workers, client, offered.get('workers', []))
    safely(check_attendance, client, offered.get('attendance', []))
    safely(check_payroll, client, offered.get('payroll', []))
    safely(check_transactions, client, offered.get('transactions', []))
    safely(check_assignments, client, offered.get('assignments', []))
    safely(check_notifications, client, offered.get('notifications', []))
    for scope in ('sites', 'projects', 'tasks', 'departments'):
        safely(check_entity, client, scope, offered.get(scope, []))
    safely(check_attendance_users, client, offered.get('attendance-users', []))
    safely(check_closures, client)

bad = [r for r in results if not r[2]]
print('\n%d checks, %d failed' % (len(results), len(bad)))
for scope, action, ok, note in bad:
    print('   FAIL %-18s %-12s %s' % (scope, action, note))
sys.exit(1 if bad else 0)
