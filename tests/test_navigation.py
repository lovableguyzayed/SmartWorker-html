"""The bar says where you are, on every screen, and says it once.

Payroll — the money screen, opened every month-end — had no tab of its own
and lit "Transactions" instead, so the bar named somewhere else while you
stood on it. Assignments and Notifications lit nothing and the bar went
blank. And the scanner in the middle wore a filled navy on every screen, so
on the dashboard the Home tab was lit *and* the scanner looked filled in:
two things both claiming to be where you are.

Six tabs cannot hold a dozen screens, so a secondary screen lights the
section it belongs to — closures under Attendance, transactions under
Payroll, assignments under Workers. What must hold is that every screen
lights exactly one, and that it is the right one.
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

# path -> the tab that should be lit
EXPECTED = {
    '/dashboard':        'Home',
    '/workers':          'Workers',
    '/add_worker':       'Workers',
    '/assignments':      'Workers',
    '/attendance':       'Attendance',
    '/closures':         'Attendance',
    '/scan':             'Scan QR',
    '/payroll':          'Payroll',
    '/payroll/preview':  'Payroll',
    '/transactions':     'Payroll',
    '/profile':          'Profile',
    '/settings':         'Profile',
    '/notifications':    'Profile',
}

with app.app_context():
    w = m.Worker.query.order_by(m.Worker.id).first()
    EXPECTED['/worker/%d' % w.id] = 'Workers'
    EXPECTED['/edit_worker/%d' % w.id] = 'Workers'
    EXPECTED['/worker_attendance/%d' % w.id] = 'Attendance'
    EXPECTED['/payroll/slip/%d' % w.id] = 'Payroll'

ITEM = re.compile(
    r'<a[^>]*class="([^"]*app-nav-(?:item|fab)[^"]*)"[^>]*>(.*?)</a>', re.S)
LABEL = re.compile(r'app-nav-label[^>]*>(.*?)<', re.S)

fails = []
with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test',
                           'password': 'demo12345'}, follow_redirects=True)
    for path, want in EXPECTED.items():
        html = c.get(path).get_data(as_text=True)
        lit = []
        labels = []
        for cls, body in ITEM.findall(html):
            label = LABEL.search(body)
            label = re.sub(r'<[^>]+>', '', label.group(1)).strip() if label else '?'
            labels.append(label)
            if 'app-nav-item-active' in cls or 'app-nav-fab-active' in cls:
                lit.append(label)

        problems = []
        if len(lit) != 1:
            problems.append('%d tabs lit (%s)' % (len(lit), ', '.join(lit) or 'none'))
        elif lit[0] != want:
            problems.append('lit %r, expected %r' % (lit[0], want))
        if want not in labels:
            problems.append('no %r tab in the bar' % want)

        print('  %-4s %-26s lit=%-12s bar=%s'
              % ('OK' if not problems else 'FAIL', path,
                 lit[0] if len(lit) == 1 else repr(lit), '|'.join(labels)))
        if problems:
            fails.append((path, problems))

# The dashboard's Quick Actions must not offer a second route to a tab.
with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test',
                           'password': 'demo12345'}, follow_redirects=True)
    html = c.get('/dashboard').get_data(as_text=True)
    section = re.search(r'Quick Actions(.*?)</section>', html, re.S)
    body = section.group(1) if section else ''
    dupes = [name for name, url in [('Mark Attendance', '/attendance'),
                                    ('QR Scanner', '/scan')]
             if ('href="%s"' % url) in body]
    print('\n  %-4s Quick Actions repeats nothing the bar carries  %s'
          % ('OK' if not dupes else 'FAIL', dupes or ''))
    if dupes:
        fails.append(('/dashboard quick actions', dupes))

print('\n%d screens, %d failed' % (len(EXPECTED), len(fails)))
for path, problems in fails:
    print('   FAIL %-28s %s' % (path, '; '.join(problems)))
sys.exit(1 if fails else 0)
