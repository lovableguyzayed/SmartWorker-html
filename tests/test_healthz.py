"""The probe has to say which commit answered it.

Without that, "the app still shows the old version" has two causes that
look identical from outside: the phone is serving pages out of its own
cache, or the server never deployed the new code. Nobody can tell which,
so the first move is always a guess — clear the app, reinstall, wait, try
again. A commit in the probe settles it in one tap.

It also has to stay cheap. Render calls it as the health check, so a
database query here would let a slow query convince the platform the
service is down and restart it.
"""
import ast
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app  # noqa: E402

failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-54s %s' % (label, repr(got)[:26]))
    else:
        failures.append(label)
        print('  FAIL %-54s got=%r want=%r' % (label, got, want))


print('--- locally, with nothing set ---')
with app.test_client() as c:
    r = c.get('/healthz')
    check('it answers 200', r.status_code, 200)
    body = r.get_json()
    check('and says it is alive', body.get('status'), 'ok')
    # Off a developer's machine there is no deploy to name, and the probe
    # must still answer rather than fail or omit the field.
    check('the commit is named, even when unknown',
          'commit' in body, True)
    check('and so is the branch', 'branch' in body, True)
    check('it reports when this process started',
          bool(body.get('started')), True)

print('\n--- on Render, where the deploy sets the environment ---')
# A subprocess because these are read once at import, which is the point:
# the probe does no work per request.
probe = r'''
import json, os, sys
sys.path.insert(0, %r)
from app import app
with app.test_client() as c:
    print('@@' + json.dumps(c.get('/healthz').get_json()))
''' % ROOT
env = dict(os.environ)
env['RENDER_GIT_COMMIT'] = 'd01b2cb8c22984e6a6d4971bc7713220a15c8e6d'
env['RENDER_GIT_BRANCH'] = 'main'
run = subprocess.run([sys.executable, '-c', probe], cwd=ROOT, env=env,
                     capture_output=True, text=True, timeout=300)
line = next((l for l in run.stdout.splitlines() if l.startswith('@@')), None)
check('the subprocess answered', bool(line), True)
if not line:
    print(run.stdout[-1500:])
    print(run.stderr[-1500:])
else:
    body = json.loads(line[2:])
    # Short, because a 40-character hash is unreadable on a phone and the
    # first seven are what `git log --oneline` prints.
    check('the commit is the short form', body.get('commit'), 'd01b2cb')
    check('and the branch comes through', body.get('branch'), 'main')

print('\n--- it must not touch the database ---')
# Render's health check calls this. A query here means a slow database can
# make the platform believe the service is down and restart it, which is
# the opposite of what a liveness probe is for.
#
# Read through ast and with the docstring removed, not by searching the
# text: the docstring explains why there is no query here, and a plain
# substring search found that explanation and called it a query.
source = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
fn = next(n for n in ast.walk(ast.parse(source))
          if isinstance(n, ast.FunctionDef) and n.name == 'healthz')
statements = fn.body[1:] if ast.get_docstring(fn) else fn.body
code = '\n'.join(ast.unparse(s) for s in statements)
check('the handler is one statement', len(statements), 1)
for forbidden in ('query', 'session', 'db.', 'commit('):
    check('its code contains no %r' % forbidden, forbidden in code, False)

print()
if failures:
    print('FAILED %d of the checks above:' % len(failures))
    for label in failures:
        print('  %s' % label)
    sys.exit(1)
print('The probe says which commit is live, and still does no work.')
