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
    from app import app, db
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
        print('fixture ready: demo / demo12345 (admin), imran / %s (supervisor)'
              % env['SEED_SUPERVISOR_PASSWORD'])


if __name__ == '__main__':
    main()
