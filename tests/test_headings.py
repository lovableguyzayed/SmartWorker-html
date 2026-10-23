"""Every screen names itself, and its outline does not skip a level.

Each screen always showed its name in the navy header, but as a div, so
only the sign-in and payroll-preview screens had an h1 at all; fourteen
started their outline at h3 and four — attendance, transactions,
assignments, notifications — carried no heading element anywhere. Nothing
looked wrong, which is why it survived: it is what a screen reader
announces and where "skip to the heading" lands.

Read off the rendered pages, because a heading can live inside a branch
that only one role ever sees.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app import app
import routes  # noqa: F401
import bulk    # noqa: F401
import models as m

app.config['WTF_CSRF_ENABLED'] = False

PATHS = ['/dashboard', '/workers', '/attendance', '/payroll', '/transactions',
         '/closures', '/assignments', '/profile', '/settings', '/scan',
         '/notifications', '/payroll/preview', '/add_worker']

with app.app_context():
    w = m.Worker.query.order_by(m.Worker.id).first()
    PATHS += ['/worker/%d' % w.id, '/worker_attendance/%d' % w.id,
              '/worker/%d/report' % w.id, '/payroll/slip/%d' % w.id,
              '/edit_worker/%d' % w.id, '/id_card/%d' % w.id]

HEADING = re.compile(r'<h([1-6])\b[^>]*>(.*?)</h\1>', re.S)
fails = []

with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test',
                           'password': 'demo12345'}, follow_redirects=True)
    for path in PATHS:
        html = c.get(path).get_data(as_text=True)
        found = [(int(lv), re.sub(r'<[^>]+>', '', txt).strip()[:28])
                 for lv, txt in HEADING.findall(html)]
        levels = [lv for lv, _ in found]

        problems = []
        if levels.count(1) == 0:
            problems.append('no h1')
        elif levels.count(1) > 1:
            problems.append('%d h1s' % levels.count(1))
        # a jump from h1 straight to h3 leaves a hole in the outline
        for a, b in zip(levels, levels[1:]):
            if b > a + 1:
                problems.append('h%d jumps to h%d' % (a, b))
                break

        title = found[0][1] if found else '-'
        print('  %-4s %-26s h1=%-22s %s'
              % ('OK' if not problems else 'FAIL', path, title,
                 ''.join(str(lv) for lv in levels[:14])))
        if problems:
            fails.append((path, problems))

print('\n%d screens, %d failed' % (len(PATHS), len(fails)))
for path, problems in fails:
    print('   FAIL %-28s %s' % (path, ', '.join(problems)))
sys.exit(1 if fails else 0)
