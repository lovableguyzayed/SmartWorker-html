"""Whatever Postgres URL the host is configured with has to have a driver.

This is the test that was missing. Production died on a redeploy with

    File ".../sqlalchemy/dialects/postgresql/psycopg.py", in import_dbapi
        import psycopg
    ModuleNotFoundError: No module named 'psycopg'

and no commit of ours was near it. requirements.txt pinned sqlalchemy only
as >=2.0.41, a fresh install on the host resolved 2.1, and 2.1 changed what
a plain postgresql:// URL means: under 2.0 it loaded psycopg2, under 2.1 it
loads psycopg (v3). The app never said which it wanted, so the answer came
from whichever version pip happened to resolve that day.

Nothing local could catch it. Development is SQLite and loads no Postgres
driver at all, so every suite stayed green while the one configuration that
matters could not import its own database.

So the check here is deliberately not "is psycopg2 installed". It is: for
every URL shape this app can be handed, resolve the driver the way
SQLAlchemy will at runtime, and import it. That question survives the
library changing its mind again.
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy.engine.url import make_url  # noqa: E402
import sqlalchemy  # noqa: E402

import app as A  # noqa: E402

failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-54s %s' % (label, repr(got)[:24]))
    else:
        failures.append(label)
        print('  FAIL %-54s got=%r want=%r' % (label, got, want))


print('running against SQLAlchemy %s' % sqlalchemy.__version__)

# Every form the host might be configured with. The first is the one that
# broke: it names no driver, so it takes the library default.
URLS = [
    'postgresql://user:pw@host:5432/db',
    'postgresql+psycopg://user:pw@host:5432/db',
    'postgresql+psycopg2://user:pw@host:5432/db',
    # What app.py rewrites a Heroku/Supabase-style URL into.
    'postgresql://user:pw@db.abcdefgh.supabase.co:5432/postgres?sslmode=require',
]

print('\n--- the driver each URL resolves to is installed ---')
for url in URLS:
    dialect = make_url(url).get_dialect()
    driver = dialect.driver
    try:
        importlib.import_module(driver)
        ok = True
    except ImportError:
        ok = False
    check('%-38s -> %s' % (url.split('@')[0][:38], driver), ok, True)

print('\n--- requirements.txt lists both, and bounds SQLAlchemy ---')
# Listing them is what makes the above true on a host, where this test does
# not run. Reading the file is the only way to assert it from here.
req = open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8').read()
lines = [l.strip() for l in req.splitlines()
         if l.strip() and not l.strip().startswith('#')]
check('psycopg (v3) is required',
      any(l.startswith('psycopg[') or l == 'psycopg' or
          l.startswith('psycopg>') for l in lines), True)
check('psycopg2 is still required',
      any(l.startswith('psycopg2') for l in lines), True)
# An unbounded dependency is how a default changed under a running service.
check('sqlalchemy has an upper bound',
      any(l.startswith('sqlalchemy') and '<' in l for l in lines), True)

print('\n--- a missing driver is named, not just traced ---')
# The guard logs one sentence saying which module to install. It must never
# raise on the way past: it runs at import, before anything is serving.
for url in URLS + ['sqlite:///x.db', 'not a url at all', '']:
    try:
        A._check_database_driver(url)
        ok = True
    except Exception as exc:
        ok = 'raised %s' % type(exc).__name__
    check('survives %r' % url[:34], ok, True)

print('\n--- and it does not cry wolf ---')
# The first version of this guard did __import__(dialect.driver). SQLite's
# driver is named "pysqlite" and the module is the standard library's
# sqlite3, so it logged a missing driver on every development run — a false
# alarm in the logs is worse than the silence it replaced, because the next
# real one is read as noise.
import logging  # noqa: E402


class Catcher(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


catcher = Catcher()
logging.getLogger().addHandler(catcher)
try:
    for url in ['sqlite:///smartworker.db', 'sqlite://'] + URLS:
        A._check_database_driver(url)
finally:
    logging.getLogger().removeHandler(catcher)
check('nothing is logged when every driver is present',
      [r.getMessage()[:60] for r in catcher.records
       if r.levelno >= logging.ERROR], [])

print()
if failures:
    print('FAILED %d of the checks above:' % len(failures))
    for label in failures:
        print('  %s' % label)
    sys.exit(1)
print('Every URL this app can be given has a driver behind it.')
