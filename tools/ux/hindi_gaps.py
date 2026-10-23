"""What is still in English when the interface is set to Hindi.

Half-translated is worse than untranslated: it reads as unfinished. This
renders every screen in Hindi and reports the interface text still in Latin
script, skipping the things that genuinely stay — worker names, site and
project names, employee ids, amounts, dates and the brand.

It reports per screen, worst first, so the next hour of translation work
goes where it shows.
"""
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from app import app
import routes  # noqa: F401
import bulk    # noqa: F401
import models as m

app.config['WTF_CSRF_ENABLED'] = False

SCREENS = ['/dashboard', '/workers', '/attendance', '/payroll',
           '/payroll/preview', '/transactions', '/closures', '/assignments',
           '/scan', '/settings', '/profile', '/notifications', '/add_worker']

with app.app_context():
    w = m.Worker.query.order_by(m.Worker.id).first()
    SCREENS += ['/worker/%d' % w.id, '/edit_worker/%d' % w.id,
                '/worker_attendance/%d' % w.id, '/worker/%d/report' % w.id,
                '/payroll/slip/%d' % w.id, '/id_card/%d' % w.id]
    # Proper nouns in the data are not translation gaps.
    DATA = set()
    for row in m.Worker.query.all():
        DATA |= set(re.findall(r"[A-Za-z][\w'’.-]+", row.full_name or ''))
        DATA |= {row.worker_id or '', row.position or '', row.department or ''}
    for model, field in ((m.Site, 'name'), (m.Project, 'name'),
                         (m.WorkTask, 'name'), (m.Department, 'name')):
        for row in model.query.all():
            DATA |= set(re.findall(r"[A-Za-z][\w'’.-]+", getattr(row, field) or ''))

SKIP = {'SmartWorker', 'QR', 'PDF', 'CSV', 'ID', 'IST', 'UTC', 'AM', 'PM',
        'OT', 'UPI', 'IFSC', 'PAN', 'GST', 'OTP', 'SUN', 'MON', 'TUE', 'WED',
        'THU', 'FRI', 'SAT', 'Munsi'}
SKIP |= {d for d in DATA if d}

TAGS = re.compile(r'<(script|style)[^>]*>.*?</\1>', re.S | re.I)
TEXT = re.compile(r'>([^<>]+)<')
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’]{2,}")

per_screen = defaultdict(set)
with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test',
                           'password': 'demo12345'}, follow_redirects=True)
    with c.session_transaction() as s:
        s['lang'] = 'hi'
    for path in SCREENS:
        html = TAGS.sub(' ', c.get(path).get_data(as_text=True))
        for chunk in TEXT.findall(html):
            chunk = chunk.strip()
            if not chunk or '{{' in chunk:
                continue
            words = [w for w in LATIN_WORD.findall(chunk) if w not in SKIP]
            if words:
                per_screen[path].add(chunk[:60])

total = sum(len(v) for v in per_screen.values())
print('%d run(s) of English text across %d Hindi screens\n'
      % (total, len(per_screen)))
for path, runs in sorted(per_screen.items(), key=lambda kv: -len(kv[1])):
    print('  %-26s %3d' % (path, len(runs)))
    for run in sorted(runs)[:6]:
        print('        %s' % run)
    if len(runs) > 6:
        print('        … and %d more' % (len(runs) - 6))
