"""The one-time setup link, and the four things standing in front of it.

A route that empties the database is worth having — the owner of a hosted
deployment has no shell to run the seeding script from, and setting up their
own company is the first thing they need to do. It is also the single most
dangerous thing in the app, so what is actually tested here is that it
refuses:

  1. nothing at all happens unless SETUP_TOKEN is set in the environment
  2. a wrong token is a 404 and not a 403, so the route does not announce
     itself to somebody guessing
  3. a short token does not count as set, so a placeholder like "changeme"
     cannot open it
  4. GET never writes, however many times it is called
  5. POST without the exact typed phrase never writes

The one case that does write is proved against a throwaway SQLite file in
a subprocess, never against this database: running it here would delete the
fixture every other suite logs in with.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app  # noqa: E402
import routes as R  # noqa: E402
import bulk  # noqa: E402,F401
import models as m  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []

GOOD = 'a-token-long-enough-to-be-one'


def check(label, got, want):
    if got == want:
        print('  PASS %-56s %s' % (label, repr(got)[:24]))
    else:
        failures.append(label)
        print('  FAIL %-56s got=%r want=%r' % (label, got, want))


def counts():
    with app.app_context():
        return (m.Account.query.count(), m.Worker.query.count(),
                m.AttendanceRecord.query.count())


BEFORE = counts()
print('this database holds %d account(s), %d worker(s), %d attendance row(s)'
      % BEFORE)

print('\n--- with no token in the environment ---')
os.environ.pop('SETUP_TOKEN', None)
with app.test_client() as c:
    check('the route is not there at all',
          c.get('/__setup/%s' % GOOD).status_code, 404)
    check('and POSTing to it is no different',
          c.post('/__setup/%s' % GOOD,
                 data={'confirm': R.SETUP_CONFIRM}).status_code, 404)
check('nothing was touched', counts(), BEFORE)

print('\n--- with a token too short to be one ---')
# A deployment where somebody set SETUP_TOKEN=changeme has not opted in to
# anything; a guessable token is the same as no protection.
os.environ['SETUP_TOKEN'] = 'changeme'
with app.test_client() as c:
    check('a short token does not open it',
          c.get('/__setup/changeme').status_code, 404)
check('nothing was touched', counts(), BEFORE)

print('\n--- with a real token, but the wrong one ---')
os.environ['SETUP_TOKEN'] = GOOD
with app.test_client() as c:
    check('a wrong guess is a 404, not a 403',
          c.get('/__setup/%s' % (GOOD + 'x')).status_code, 404)
    # The prefix case matters: it is what a timing attack walks character
    # by character, and what a `startswith` would have let through.
    check('nor does a matching prefix get in',
          c.get('/__setup/%s' % GOOD[:10]).status_code, 404)
check('nothing was touched', counts(), BEFORE)

print('\n--- with the right token: the page, which must not write ---')
with app.test_client() as c:
    r = c.get('/__setup/%s' % GOOD)
    check('the page opens', r.status_code, 200)
    body = r.get_data(as_text=True)
    check('it says what will be deleted',
          'This deletes everything first' in body, True)
    check('it shows the real counts',
          str(BEFORE[1]) in body, True)
    check('it names the company it would build',
          'Uttaranchal Stone Crusher' in body, True)
    check('and asks for the phrase', R.SETUP_CONFIRM in body, True)
    # Three times, because a page that writes on GET is a page a link
    # preview or a browser prefetch can fire.
    c.get('/__setup/%s' % GOOD)
    c.get('/__setup/%s' % GOOD)
check('three GETs wrote nothing', counts(), BEFORE)

print('\n--- the right token, the wrong confirmation ---')
with app.test_client() as c:
    for typed in ('', 'yes', 'wipe and setup', R.SETUP_CONFIRM + ' please',
                  ' WIPE AND SETUP x'):
        r = c.post('/__setup/%s' % GOOD, data={'confirm': typed})
        check('refused: %r' % typed, r.status_code, 400)
        check('   and says so',
              'Nothing has been deleted' in r.get_data(as_text=True), True)
check('still nothing touched', counts(), BEFORE)

os.environ.pop('SETUP_TOKEN', None)

print('\n--- and the case that does write, on a throwaway database ---')
# In a subprocess with DATABASE_URL pointed at a scratch file. Running it
# in this process would delete the fixture every other suite logs in with,
# which is how a morning was lost once already.
probe = r'''
import json, os, sys
sys.path.insert(0, %r)
from app import app
import routes as R
import bulk
import models as m

app.config['WTF_CSRF_ENABLED'] = False
os.environ['SETUP_TOKEN'] = %r
out = {}
with app.test_client() as c:
    r = c.post('/__setup/' + %r, data={'confirm': R.SETUP_CONFIRM})
    out['status'] = r.status_code
    body = r.get_data(as_text=True)
    out['says_done'] = 'Setup complete' in body
    out['says_remove_token'] = 'SETUP_TOKEN' in body
with app.app_context():
    out['accounts'] = m.Account.query.count()
    out['workers'] = m.Worker.query.count()
    out['attendance'] = m.AttendanceRecord.query.count()
    setting = m.CompanySetting.query.first()
    out['company'] = setting.name if setting else None
    out['allocation'] = setting.dues_allocation if setting else None
    admin = m.User.query.filter_by(role='admin').first()
    out['admin'] = admin.username if admin else None
    # The money that prompted all of this: wages paid, not an advance.
    wage = m.WorkerTransaction.query.filter_by(txn_type='wage_payment').all()
    out['wage_payments'] = sorted(t.amount for t in wage)
    out['modes'] = sorted({t.payment_mode or '' for t in wage})
print('@@' + json.dumps(out))
''' % (ROOT, GOOD, GOOD)

with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ)
    env['DATABASE_URL'] = 'sqlite:///%s/probe.db' % tmp
    env.pop('SETUP_TOKEN', None)
    run = subprocess.run([sys.executable, '-c', probe], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=600)
    line = next((l for l in run.stdout.splitlines() if l.startswith('@@')),
                None)
    check('the subprocess reported back', bool(line), True)
    if not line:
        print(run.stdout[-2000:])
        print(run.stderr[-2000:])
    else:
        got = json.loads(line[2:])
        check('the setup ran', got['status'], 200)
        check('and says it is done', got['says_done'], True)
        check('and tells the owner to remove the token',
              got['says_remove_token'], True)
        check('one company', got['accounts'], 1)
        check('and it is the right one', got['company'],
              'Uttaranchal Stone Crusher')
        check('the administrator login', got['admin'], 'Javed')
        check('eleven workers', got['workers'], 11)
        check('attendance was built', got['attendance'] > 500, True)
        # ₹20,000 handed over on 22 October, and a part payment by UPI.
        check('the wages paid are recorded as wages',
              got['wage_payments'], [9000.0, 20000.0])
        check('with how the money moved', got['modes'], ['cash', 'upi'])
        # This business had settled nothing since August, so money handed
        # over clears the oldest month. The column default stays 'month'
        # everywhere else; this account is set deliberately.
        check('and payments clear the oldest month first',
              got['allocation'], 'oldest_first')

check('this database is where it started', counts(), BEFORE)

print()
if failures:
    print('FAILED %d of the checks above:' % len(failures))
    for label in failures:
        print('  %s' % label)
    sys.exit(1)
print('The setup link refuses everything it should, and works once it must.')
