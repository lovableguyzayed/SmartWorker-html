"""Every control that changes something is pressed, and the change checked.

`tools/ux/controls.py` proves each control is wired to something and
`links.py` that every href resolves. Neither proves the thing it is wired
to does what the label says. A filter chip that is bound to a form and
reloads the page having filtered nothing is a working control and a broken
feature.

So this presses them and looks at what happened: the filter chips filter,
the search box searches, the pager pages, the fold folds, the selection bar
counts records rather than rows, the mark-all-read marks all read. It is
deliberately about effects, not about bindings.

Written after a session that added a good deal — folded notifications,
counted filter chips, a tinted chip style, a read-only day view, a folded
calendar, a new navigation bar — because every one of those is a control
whose binding was never in doubt and whose behaviour was.
"""
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from playwright.sync_api import sync_playwright

from app import app, db
import models as m
from routes import WORKERS_PER_PAGE

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5109
B = 'http://127.0.0.1:%d' % PORT

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-50s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


def truthy(label, got, why=''):
    ok = bool(got)
    if not ok:
        fails.append((label, got, 'something truthy'))
    print('  %-5s %-50s %s' % ('OK' if ok else 'FAIL', label, why or repr(got)))


with app.app_context():
    WID = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

seeded = []
paged = []
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(B + '/login', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit('could not start a server on %s' % B)

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)[:120]))

        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        # wait_for_url rather than a string predicate: Playwright
        # evaluates those with eval(), which the page's
        # Content-Security-Policy refuses.

        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

        # ---------------------------------------------------------------
        print('--- assignments: the counted chips actually filter ---')
        pg.goto(B + '/assignments', wait_until='domcontentloaded')
        pg.wait_for_timeout(1600)
        rows = lambda: pg.evaluate(
            "() => document.querySelectorAll('[data-ms-item]').length")
        chip = lambda v: pg.evaluate(
            """(v) => {const b=document.querySelector(
                 "button[name='show'][value='"+v+"']");
               return b ? parseInt(b.querySelector('.text-base').textContent) : -1;}""", v)
        all_n, assigned_n, unassigned_n = chip('all'), chip('assigned'), chip('unassigned')
        check('counts add up', assigned_n + unassigned_n, all_n)
        check('"All" shows every worker', rows(), all_n)

        pg.click("button[name='show'][value='assigned']")
        pg.wait_for_timeout(1800)
        check('"Assigned" filters to its own count', rows(), assigned_n)
        check('counts do not change with the filter', chip('all'), all_n)

        pg.click("button[name='show'][value='unassigned']")
        pg.wait_for_timeout(1800)
        check('"Unassigned" filters to its own count', rows(), unassigned_n)

        # ---------------------------------------------------------------
        print('\n--- workers: search, department filter and the pager ---')
        pg.goto(B + '/workers', wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        before = rows()
        name = pg.evaluate(
            "() => document.querySelector('[data-ms-item]').getAttribute('data-ms-label')")
        pg.fill('input[name="search"]', name)
        pg.click('button[aria-label]:has(i.fa-filter), form button[type=submit]')
        pg.wait_for_timeout(1800)
        after = rows()
        truthy('search narrows the roster', 0 < after <= before,
               '%d of %d rows for %r' % (after, before, name))
        shown = pg.evaluate(
            "() => (document.querySelector('[data-ms-item]')||{}).getAttribute"
            " && document.querySelector('[data-ms-item]').getAttribute('data-ms-label')")
        check('and shows the worker searched for', shown, name)

        # The roster holds far fewer than a page, so the pager never renders
        # on the seeded data and went untested for it. Seed past the page
        # size, press it, and take them away again.
        with app.app_context():
            from datetime import date as _date
            acct = m.User.query.filter_by(username='demo').first().account_id
            extra = []
            for i in range(WORKERS_PER_PAGE):
                w = m.Worker(full_name='ZZ Pager Test %02d' % i,
                             worker_id='ZP%03d' % i, phone='90000%05d' % i,
                             position='Helper', department='Civil',
                             employee_type='permanent', pay_type='daily',
                             daily_rate=500, join_date=_date(2025, 1, 1),
                             status='active')
                w.account_id = acct
                db.session.add(w)
                db.session.flush()
                extra.append(w.id)
            db.session.commit()
            paged.extend(extra)

        pg.goto(B + '/workers', wait_until='domcontentloaded')
        pg.wait_for_timeout(1800)
        check('a full page of workers', rows(), WORKERS_PER_PAGE)
        first = pg.evaluate(
            "() => document.querySelector('[data-ms-item]').getAttribute('data-ms-label')")
        truthy('the pager appears once there is a second page',
               pg.evaluate("() => !!document.querySelector("
                           "'nav[aria-label] a[href*=\"page=2\"]')"))
        pg.click('nav[aria-label] a[href*="page=2"]')
        pg.wait_for_timeout(1800)
        second = pg.evaluate(
            "() => document.querySelector('[data-ms-item]').getAttribute('data-ms-label')")
        truthy('Next moves to different workers', first != second,
               '%r -> %r' % (first, second))
        truthy('and offers a way back',
               pg.evaluate("() => !!document.querySelector("
                           "'nav[aria-label] a[href*=\"page=1\"]')"))

        # A page past the end used to render the empty state — "Start by
        # adding your first worker" on a full roster — with the pager inside
        # that same branch, so there was no way back from it.
        pg.goto(B + '/workers?page=9', wait_until='domcontentloaded')
        pg.wait_for_timeout(1600)
        truthy('a page past the end lands on the last real one, not a dead end',
               rows() > 0, '%d rows' % rows())
        truthy('and still shows the pager',
               pg.evaluate("() => !!document.querySelector('nav[aria-label]')"))

        # ---------------------------------------------------------------
        print('\n--- the worker card: its three actions land where they say ---')
        pg.goto(B + '/workers', wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        for label, part in (('Attendance', '/worker_attendance/'),
                            ('ID card', '/id_card/'),
                            ('Open', '/worker/')):
            href = pg.evaluate(
                """(l) => {const a=[...document.querySelectorAll('.worker-action')]
                    .find(e => e.textContent.trim().startsWith(l));
                   return a ? a.getAttribute('href') : null;}""", label)
            truthy('%-11s -> %s' % (label, part), href and part in href, href)

        # ---------------------------------------------------------------
        print('\n--- attendance: the calendar folds and the day view is a report ---')
        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(2400)
        check('calendar starts folded',
              pg.evaluate("() => document.getElementById('cal-fold').open"), False)
        pg.click('.cal-summary')
        pg.wait_for_timeout(600)
        check('and unfolds when pressed',
              pg.evaluate("() => document.getElementById('cal-fold').open"), True)
        check('the day view offers no status buttons',
              pg.evaluate("() => document.querySelectorAll("
                          "'.dv-row button[data-status], .dv-row .dv-pill').length"), 0)
        truthy('but still states each worker\'s state',
               pg.evaluate("() => document.querySelectorAll('.dv-state').length"),
               '%d state badges' % pg.evaluate(
                   "() => document.querySelectorAll('.dv-state').length"))

        # ---------------------------------------------------------------
        print('\n--- notifications: folding, counting and mark-all-read ---')
        with app.app_context():
            from timeutil import now_ist
            from datetime import timedelta
            admin = m.User.query.filter_by(username='demo').first()
            now = now_ist()
            for i, who in enumerate(['Ravi Kumar', 'Suresh Patel', 'Anil Sharma']):
                n = m.Notification(
                    title='%s (W-%03d) — present' % (who, 900 + i),
                    body='Site Supervisor · Dwarka Expressway Package 3',
                    category='attendance')
                n.account_id = admin.account_id
                n.created_at = now - timedelta(minutes=i)
                n.is_read = False
                db.session.add(n)
                db.session.flush()
                seeded.append(n.id)
            db.session.commit()

        pg.goto(B + '/notifications', wait_until='domcontentloaded')
        pg.wait_for_timeout(1800)
        folded = pg.evaluate(
            """() => {const e=[...document.querySelectorAll('[data-ms-item]')]
                .find(x => x.getAttribute('data-ms-item').includes(','));
               return e ? e.getAttribute('data-ms-item') : null;}""")
        truthy('a run from one action folded into one row', folded, folded)
        check('and that row carries all three ids',
              len((folded or '').split(',')), 3)
        truthy('day separators are present',
               pg.evaluate("() => document.querySelectorAll('.notif-day').length"),
               '%d separator(s)' % pg.evaluate(
                   "() => document.querySelectorAll('.notif-day').length"))

        # Long-press the folded row and read the count off the bar.
        box = pg.evaluate(
            """() => {const e=[...document.querySelectorAll('[data-ms-item]')]
                .find(x => x.getAttribute('data-ms-item').includes(','));
               const r=e.getBoundingClientRect();
               return {x:r.x+r.width/2, y:r.y+r.height/2};}""")
        pg.mouse.move(box['x'], box['y'])
        pg.mouse.down()
        pg.wait_for_timeout(800)
        pg.mouse.up()
        pg.wait_for_timeout(500)
        count = pg.evaluate(
            "() => {const c=document.querySelector('[data-ms-count]');"
            " return c ? c.textContent.trim() : null;}")
        check('the bar counts records, not rows', count, '3 notifications selected')
        pg.evaluate("() => {const b=document.querySelector('[data-ms-cancel]');"
                    " if (b) b.click();}")
        pg.wait_for_timeout(400)

        unread_before = pg.evaluate(
            "() => document.querySelectorAll('.bg-accent.rounded-full').length")
        truthy('there are unread notifications to clear', unread_before)
        pg.click('button[title]:has(i.fa-check-double), '
                 'form[action*="mark_read"] button')
        pg.wait_for_timeout(1800)
        check('mark-all-read clears every unread dot',
              pg.evaluate(
                  "() => document.querySelectorAll('.bg-accent.rounded-full').length"), 0)

        # ---------------------------------------------------------------
        print('\n--- the navigation bar reaches every section ---')
        tabs = pg.evaluate(
            """() => [...document.querySelectorAll('.app-bottom-nav a')]
                 .map(a => ({t:a.textContent.trim(), h:a.getAttribute('href')}))""")
        check('six tabs', len(tabs), 6)
        for t in tabs:
            truthy('tab %-11s -> %s' % (t['t'], t['h']), t['h'] and t['h'] != '#')

        # ---------------------------------------------------------------
        print('\n--- the document buttons produce a document ---')
        pg.goto(B + '/payroll/slip/%d' % WID, wait_until='domcontentloaded')
        pg.wait_for_timeout(2000)
        pg.evaluate("""() => {
            window.__pdf = null;
            SmartWorkerSave.blob = function (b) {
                return new Promise(r => { window.__pdf = b.size; r('ok'); });
            };
        }""")
        pg.click('button[data-act="downloadPDF"]')
        # Polled rather than wait_for_function: a string predicate is
        # eval()d in the page, which the CSP blocks.
        for _ in range(240):
            if pg.evaluate("() => window.__pdf !== null"):
                break
            pg.wait_for_timeout(500)
        else:
            raise AssertionError("the PDF never arrived")
        size = pg.evaluate("() => window.__pdf")
        truthy('the payslip PDF button produces a file', size and size > 20000,
               '%d bytes' % (size or 0))

        print('\n--- no script threw while all that happened ---')
        check('page errors', errors, [])
        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)
    with app.app_context():
        if seeded:
            m.Notification.query.filter(m.Notification.id.in_(seeded)).delete(
                synchronize_session=False)
        if paged:
            m.Worker.query.filter(m.Worker.id.in_(paged)).delete(
                synchronize_session=False)
        db.session.commit()

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('All interaction checks passed.')
