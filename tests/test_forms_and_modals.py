"""Every modal opens, and every create form saves.

Two gaps the other sweeps leave.

`tools/ux/controls.py` proves a control is bound to a handler, and that the
handler is defined. It cannot press it. So the eleven modals in the
interface — the transaction editor, the bulk assign picker, the attendance
adjuster, the four on a worker's profile, the ID-card download chooser, the
two on the profile screen — are opened here and checked to actually appear,
with their fields in them.

And `tests/test_bulk_actions.py` creates its throwaway rows straight in the
database, which means the create forms behind every "+" button were never
posted by anything. They are posted here the way a browser posts them,
with a CSRF token, and the row is looked for afterwards. Everything made is
removed again, and the removal is verified rather than assumed.

A note for whoever extends this: when a modal or a picker does not open,
suspect this file first. Writing it turned up three wrong ids and one
wrong opener in the test and none at all in the application — the bulk
picker is `#bulk-assign-picker`, not `#assign-modal`; the attendance
adjuster takes six arguments; the openers are named functions that never
mention the id they open.
"""
import http.cookiejar
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from playwright.sync_api import sync_playwright

from app import app, db
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5110
B = 'http://127.0.0.1:%d' % PORT
MARK = 'ZZSweep'

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-46s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


with app.app_context():
    WID = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id
    AWID = m.Worker.query.filter_by(status='active').first().id

# modal id -> the screen it lives on, and the opener: either the marker
# 'bulkbar' or (function name, arguments). Kept as name-plus-arguments
# rather than a snippet to eval, because the page's own policy forbids
# evaluating a string as code — the test has to play by the same rules.
MODALS = [
    ('/transactions',               'txn-modal',              ('openTxnModal', [])),
    ('/assignments',                'bulk-assign-picker',     'bulkbar'),
    ('/attendance',                 'adjust-modal',
     ('openAdjustModal', [1, 'Test Worker', 'present', '09:00', '18:00', ''])),
    ('/worker/%d' % WID,            'worker-actions-modal',   ('showWorkerActionsModal', [])),
    ('/worker/%d' % WID,            'assign-modal',           ('showAssignModal', [])),
    ('/worker/%d' % WID,            'leave-modal',            ('showLeaveModal', [])),
    ('/worker/%d' % WID,            'modify-modal',           ('showModifyModal', [])),
    ('/worker_attendance/%d' % WID, 'stats-modal',            ('showStatsModal', [])),
    ('/id_card/%d' % WID,           'download-options-modal', ('showDownloadModal', [])),
    ('/profile',                    'edit-profile-modal',     ('showEditModal', [])),
    ('/profile',                    'password-modal',         ('showPasswordModal', [])),
]

VISIBLE = """(id) => {
    const e = document.getElementById(id);
    if (!e) return 'missing';
    return e.checkVisibility() ? 'shown' : 'hidden';
}"""

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

made = {'Site': [], 'Project': [], 'WorkTask': [], 'Department': [],
        'WorkerTransaction': []}
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(B + '/login', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit('could not start a server on %s' % B)

    # ------------------------------------------------------------------
    print('--- every modal opens, with its fields ---')
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

        last = None
        for url, mid, how in MODALS:
            if url != last:
                pg.goto(B + url, wait_until='domcontentloaded')
                pg.wait_for_timeout(2000)
                last = url

            if how == 'bulkbar':
                # It is a picker on the selection bar, so select a row first.
                pg.evaluate("""() => {
                    const e = document.querySelector('[data-ms-item]');
                    if (e) e.scrollIntoView({block: 'center'});
                }""")
                pg.wait_for_timeout(450)
                box = pg.evaluate("""() => {
                    const e = document.querySelector('[data-ms-item]');
                    if (!e) return null;
                    const r = e.getBoundingClientRect();
                    return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }""")
                pg.mouse.move(box['x'], box['y'])
                pg.mouse.down()
                pg.wait_for_timeout(800)
                pg.mouse.up()
                pg.wait_for_timeout(500)
                btn = pg.query_selector('[data-ms-prompt="#%s"]' % mid)
                if btn is None:
                    fails.append((mid, 'no action points at it', '#%s' % mid))
                    print('  FAIL  %-24s no selection-bar action opens it' % mid)
                    continue
                btn.click()
                pg.wait_for_timeout(700)
            else:
                fn, fn_args = how
                # The markup declares data-act="fn" now; inline handlers were
                # removed so that the Content-Security-Policy could forbid
                # them. Same question as before: does any control call this?
                wired = pg.evaluate(
                    """(fn) => [...document.querySelectorAll('[data-act]')]
                         .some(e => e.getAttribute('data-act') === fn)""",
                    fn)
                if not wired:
                    fails.append((mid, '%s is wired to no control' % fn, 'wired'))
                    print('  FAIL  %-24s %s opens it but nothing calls %s'
                          % (mid, fn, fn))
                pg.evaluate(
                    "([f, a]) => window[f].apply(null, a)", [fn, fn_args])
                pg.wait_for_timeout(700)

            state = pg.evaluate(VISIBLE, mid)
            fields = pg.evaluate(
                "(id) => {const e = document.getElementById(id);"
                " return e ? e.querySelectorAll("
                "'input,select,textarea,button').length : 0;}", mid)
            ok = state == 'shown' and fields > 0
            if not ok:
                fails.append((mid, '%s, %d fields' % (state, fields), 'shown'))
            print('  %-5s %-24s %-8s %2d field(s)   %s'
                  % ('OK' if ok else 'FAIL', mid, state, fields, url))

            pg.evaluate("""(id) => {
                const e = document.getElementById(id);
                if (e) { e.classList.add('hidden'); e.hidden = true; }
                document.querySelectorAll('.ms-bar').forEach(b => b.hidden = true);
            }""", mid)
            pg.wait_for_timeout(180)

        check('no script threw while opening them', errors, [])
        ctx.close()
        br.close()

    # ------------------------------------------------------------------
    print('\n--- every create form saves ---')
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    html = op.open(B + '/login').read().decode()
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    op.open(B + '/login', urllib.parse.urlencode(
        {'username': 'demo@acme.test', 'password': 'demo12345',
         'csrf_token': tok}).encode()).read()

    def post(path, data, referer):
        body = op.open(B + referer).read().decode()
        mt = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', body)
        data = dict(data, csrf_token=mt.group(1) if mt else '')
        req = urllib.request.Request(
            B + path, urllib.parse.urlencode(data).encode())
        return op.open(req).getcode()

    for label, path, data, model, key in (
            ('a site', '/settings/site/save',
             {'name': MARK + ' Site', 'location': 'Gurgaon',
              'status': 'active'}, m.Site, 'Site'),
            ('a project', '/settings/project/save',
             {'name': MARK + ' Project', 'status': 'active'},
             m.Project, 'Project'),
            ('a task', '/settings/task/save',
             {'name': MARK + ' Task', 'status': 'active'},
             m.WorkTask, 'WorkTask'),
            ('a department', '/settings/department/save',
             {'name': MARK + ' Dept', 'status': 'active'},
             m.Department, 'Department')):
        code = post(path, data, '/settings')
        with app.app_context():
            row = model.query.filter(model.name == data['name']).first()
        if row:
            made[key].append(row.id)
        check('%s saves' % label, bool(row) and code == 200, True)

    code = post('/transactions/save',
                {'worker_id': AWID, 'txn_type': 'advance', 'amount': '250',
                 'date': date.today().isoformat(),
                 'description': MARK + ' advance'}, '/transactions')
    with app.app_context():
        txn = (m.WorkerTransaction.query
               .filter(m.WorkerTransaction.description == MARK + ' advance')
               .first())
    if txn:
        made['WorkerTransaction'].append(txn.id)
    check('a transaction saves', bool(txn) and code == 200, True)
    check('and saves the amount it was given',
          float(txn.amount) if txn else None, 250.0)

    if made['Site']:
        sid = made['Site'][0]
        post('/settings/site/save',
             {'id': sid, 'name': MARK + ' Site Renamed', 'location': 'Noida',
              'status': 'active'}, '/settings')
        with app.app_context():
            row = m.Site.query.filter_by(id=sid).first()
        check('editing one back changes it',
              row.name if row else None, MARK + ' Site Renamed')
finally:
    server.terminate()
    server.wait(timeout=10)
    with app.app_context():
        for model, key in ((m.WorkerTransaction, 'WorkerTransaction'),
                           (m.Site, 'Site'), (m.Project, 'Project'),
                           (m.WorkTask, 'WorkTask'), (m.Department, 'Department')):
            if made[key]:
                model.query.filter(model.id.in_(made[key])).delete(
                    synchronize_session=False)
        db.session.commit()

with app.app_context():
    left = sum(model.query.filter(model.name.like(MARK + '%')).count()
               for model in (m.Site, m.Project, m.WorkTask, m.Department))
    left += m.WorkerTransaction.query.filter(
        m.WorkerTransaction.description.like(MARK + '%')).count()
print('\n--- and this test leaves nothing behind ---')
check('rows this sweep created that remain', left, 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('All form and modal checks passed.')
