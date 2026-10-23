"""The startup migrations have to speak the database they are sent to.

SCHEMA_PATCHES is a table of hand-written ALTER TABLE fragments, and they
were written in SQLite's spelling because SQLite is what development runs
on. Production is Postgres, which disagrees on two points:

    DATETIME      no such type there; it is TIMESTAMP
    DEFAULT 0     a boolean column will not take an integer default

Both are invisible until a column is genuinely missing from a table that
already exists. A fresh database never shows them — create_all builds
every column correctly from the models and no patch runs at all — so they
survive every local run, every test, and every new deployment, and fire
only on the live database that has been there a while. Which is the one
that matters.

And when one did fire it raised straight out of startup: the worker died,
the platform reported a failed deploy, and every screen was lost to
protect one column. So two things are checked here — that the DDL is
translated, and that a patch which cannot apply is survivable.

Neither needs a Postgres server. The translation is a pure function, and
the whole patch table can be run through it and inspected.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app as A  # noqa: E402

failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-56s %s' % (label, repr(got)[:22]))
    else:
        failures.append(label)
        print('  FAIL %-56s got=%r want=%r' % (label, got, want))


print('--- the two spellings Postgres rejects ---')
check('DATETIME becomes TIMESTAMP',
      A._portable_ddl('DATETIME', True), 'TIMESTAMP')
check('a false boolean default becomes FALSE',
      A._portable_ddl('BOOLEAN NOT NULL DEFAULT 0', True),
      'BOOLEAN NOT NULL DEFAULT FALSE')
check('a true one becomes TRUE',
      A._portable_ddl('BOOLEAN NOT NULL DEFAULT 1', True),
      'BOOLEAN NOT NULL DEFAULT TRUE')

print('\n--- and SQLite keeps its own ---')
# Development runs on SQLite and must be left exactly as it was, or this
# fix trades a production break for a local one.
for ddl in ('DATETIME', 'BOOLEAN NOT NULL DEFAULT 0', 'VARCHAR(20)',
            'FLOAT', 'INTEGER DEFAULT 10'):
    check('unchanged: %r' % ddl, A._portable_ddl(ddl, False), ddl)

print('\n--- nothing else is touched ---')
for ddl in ('VARCHAR(64)', 'TEXT', 'FLOAT', 'INTEGER', 'DATE',
            "VARCHAR(20) DEFAULT 'month'", 'FLOAT DEFAULT 0.0'):
    check('unchanged on Postgres too: %r' % ddl,
          A._portable_ddl(ddl, True), ddl)

print('\n--- every patch in the table, as Postgres would receive it ---')
# The real guard. A column added next year in SQLite's spelling is caught
# here rather than by a failed deploy.
bad_type, bad_default = [], []
for table, patches in A.SCHEMA_PATCHES.items():
    for column, ddl in patches:
        out = A._portable_ddl(ddl, True).upper()
        if 'DATETIME' in out:
            bad_type.append('%s.%s -> %s' % (table, column, out))
        if 'BOOLEAN' in out and ('DEFAULT 0' in out or 'DEFAULT 1' in out):
            bad_default.append('%s.%s -> %s' % (table, column, out))

total = sum(len(p) for p in A.SCHEMA_PATCHES.values())
print('  (%d patches across %d tables)' % (total, len(A.SCHEMA_PATCHES)))
check('no DATETIME survives', bad_type, [])
check('no boolean takes an integer default', bad_default, [])

print('\n--- a patch that cannot apply must not end the service ---')
# The handler catches, records and carries on. Checked by reading the
# function rather than by breaking a live database: what matters is that
# the failure path exists at all, because before this there was none.
import ast  # noqa: E402
source = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
fn = next(n for n in ast.walk(ast.parse(source))
          if isinstance(n, ast.FunctionDef) and n.name == '_apply_schema_patches')
handlers = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
check('the ALTER is wrapped', len(handlers) >= 1, True)
body = ast.unparse(fn)
check('a failure is rolled back', 'rollback' in body, True)
check('and recorded where it can be seen',
      'SCHEMA_PATCH_FAILURES' in body, True)
check('the list starts empty', A.SCHEMA_PATCH_FAILURES, [])

print('\n--- and the probe reports it ---')
with A.app.test_client() as c:
    body = c.get('/healthz').get_json()
    check('healthz carries the warnings', 'schema_warnings' in body, True)
    check('and there are none here', body.get('schema_warnings'), [])

print()
if failures:
    print('FAILED %d of the checks above:' % len(failures))
    for label in failures:
        print('  %s' % label)
    sys.exit(1)
print('The migrations speak Postgres, and one bad patch is survivable.')
