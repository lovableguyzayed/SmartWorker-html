"""Build the database the test suite signs in to, from nothing.

The suites sign in as demo@acme.test / demo12345 and expect a seeded roster,
but that database only ever existed on one machine: a fresh checkout could
not run a single browser test. This builds an equivalent one.

    DATABASE_URL=sqlite:////tmp/fixture.db python tools/make_test_fixture.py

then run any test with the same DATABASE_URL. Point UX_CHROME at a Chromium
binary if the one the tests default to is not installed.

It refuses to touch anything but SQLite, so it cannot be aimed at the live
Postgres database by accident.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith('sqlite:///'):
        sys.exit('Set DATABASE_URL to a sqlite:/// file. This tool will not '
                 'run against any other database.')
    env = dict(os.environ)
    env.setdefault('SESSION_SECRET', 'fixture')
    env.setdefault('ADMIN_DEFAULT_PASSWORD', 'fixture-admin')
    # Known passwords: this database is for tests and is never deployed.
    env.setdefault('SEED_ADMIN_PASSWORD', 'fixture-javed')
    env.setdefault('SEED_SUPERVISOR_PASSWORD', 'imran12345')
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'seed_uttaranchal.py'),
                    '--apply', '--force'], check=True, env=env, cwd=ROOT)

    os.environ.update(env)
    sys.path.insert(0, ROOT)
    from datetime import datetime, time, timedelta
    from app import app, db
    from timeutil import today_ist
    import models as m
    with app.app_context():
        if not m.User.query.filter_by(username='demo').first():
            account = m.Account.query.order_by(m.Account.id).first()
            demo = m.User(username='demo', email='demo@acme.test',
                          full_name='Demo Admin', role='admin',
                          account_id=account.id)
            demo.set_password('demo12345')
            db.session.add(demo)
            db.session.commit()
        account_id = m.User.query.filter_by(username='demo').first().account_id
        today = today_ist()
        workers = (m.Worker.query.filter_by(status='active')
                   .order_by(m.Worker.id).all())

        # Something marked today: the attendance screen opens on today, and
        # its edit and adjust controls only exist for rows already marked.
        if not m.AttendanceRecord.query.filter_by(date=today).first():
            for w in workers[:3]:
                db.session.add(m.AttendanceRecord(
                    account_id=account_id, worker_id=w.id, date=today,
                    status='present', marked_via='manual',
                    check_in_time=datetime.combine(today, time(9, 0))))

        # One current assignment, so ending an assignment has something to end.
        if not m.ProjectAssignment.query.filter_by(status='active').first():
            site = m.Site.query.filter_by(status='active').first()
            if site and workers:
                db.session.add(m.ProjectAssignment(
                    account_id=account_id, worker_id=workers[-1].id,
                    site_id=site.id, start_date=today - timedelta(days=30),
                    status='active'))
        db.session.commit()

        print('fixture ready: demo / demo12345 (admin), imran / %s (supervisor)'
              % env['SEED_SUPERVISOR_PASSWORD'])


if __name__ == '__main__':
    main()
