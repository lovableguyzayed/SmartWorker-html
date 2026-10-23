"""The scanner books money as well as attendance, and refuses the rest.

The gate screen used to do one thing: mark somebody present. A mukadam
standing there with a queue in front of him also hands out advances, and
before this he had to leave the camera, find the worker in a list and come
back — which in practice means the advance is written on paper and keyed in
at night, if at all.

So this drives the real screen the way a person does: scan a worker, read
the card, choose what the money is for, type an amount, press the button.
Then it looks at the row that reached the database, because a toast that
says a payment was recorded is not the same thing as a payment.

The second half is the permissions, asked of the endpoint rather than read
off the decorator. The scanner is administrators only today — a worker
login, supervisor or not, is held to its own screens by
`_confine_worker_logins` — and that is checked here rather than assumed,
because the whole point of a deny-by-default allowlist is that it is the
thing that breaks when somebody adds a route.
"""
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

# The app's clock, not the system's. Everything SmartWorker stores is
# naive IST (see timeutil.py), so between 18:30 and midnight UTC a test
# asking the system for its date is a day behind the app and fails on a correct
# answer — which is exactly how this was found.
from timeutil import today_ist

from playwright.sync_api import sync_playwright

from app import app, db
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5113
B = 'http://127.0.0.1:%d' % PORT
NOTE = 'ZZScanPay'

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-48s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


with app.app_context():
    w = m.Worker.query.filter_by(status='active').first()
    other = m.Worker.query.filter(m.Worker.status == 'active',
                                  m.Worker.id != w.id).first()
    CODE, NAME, WID, OTHER_ID = w.worker_id, w.full_name, w.id, other.id
    ACCT = w.account_id
    FOREIGN = m.Worker.query.filter(m.Worker.account_id != ACCT).first()
    FOREIGN_ID = FOREIGN.id if FOREIGN else None
    TXNS_BEFORE = m.WorkerTransaction.query.count()

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

probe_users = []
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
    # Part one: the screen, driven as a person drives it.
    # ------------------------------------------------------------------
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
        # wait_for_url rather than a string predicate: Playwright evaluates
        # those with eval(), which the page's CSP refuses.
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

        print('--- the card after a scan offers both jobs ---')
        pg.goto(B + '/scan', wait_until='domcontentloaded')
        pg.wait_for_timeout(2300)
        hidden = lambda sel: pg.evaluate(
            "(s) => document.querySelector(s).className.includes('hidden')", sel)
        check('payment is not offered before a scan', hidden('#result-pay'), True)

        pg.fill('#manual-id', CODE)
        pg.click('form[data-act="lookupManual"] button[type=submit]')
        pg.wait_for_timeout(1800)

        check('the worker on the card', pg.evaluate(
            "() => document.getElementById('result-name').textContent.trim()"),
            NAME)
        check('attendance is still the first thing', pg.evaluate("""() =>
            [...document.querySelectorAll('.res-actions button')].length > 0"""),
            True)
        check('payment is offered under it', hidden('#result-pay'), False)
        # Three groups, because money moves three different ways here and a
        # single flat list invites picking the wrong one. An advance comes
        # off the month's pay, a bonus is added to it, and wages paid change
        # neither — they settle what is already owed. The third was the
        # whole reason the wage_payment type was added: before it, settling
        # wages had to be entered as an advance, which came off the month as
        # well and made October read as ₹3,000 instead of ₹23,000.
        check('the three directions are separated', pg.evaluate("""() =>
            document.querySelectorAll('#pay-type optgroup').length"""), 3)
        check('and settling wages is the first offered', pg.evaluate("""() =>
            document.querySelector('#pay-type option').value"""),
            'wage_payment')
        # How the money moved, and what it can be matched against in a bank
        # statement. Cash is preselected because at a crusher gate it nearly
        # always is, and a field that must be set every time gets set wrongly.
        check('how it was paid is asked for', pg.evaluate("""() =>
            document.getElementById('pay-mode').value"""), 'cash')
        check('and a reference can be given', pg.evaluate("""() =>
            !!document.getElementById('pay-reference')"""), True)
        check('every type is selectable', pg.evaluate("""() =>
            document.querySelectorAll('#pay-type option').length > 4"""), True)

        print('\n--- pressed with no amount, nothing is booked ---')
        pg.click('#btn-pay')
        pg.wait_for_timeout(600)
        check('it says so instead', pg.evaluate(
            "() => { const t = document.querySelector('#scan-toasts div');"
            " return t ? t.textContent.includes('greater than zero') : false; }"),
            True)

        print('\n--- a real one: an advance of 250 ---')
        pg.evaluate("() => { document.getElementById('scan-toasts').innerHTML = ''; }")
        pg.select_option('#pay-type', 'advance')
        pg.fill('#pay-amount', '250')
        pg.fill('#pay-note', NOTE + ' advance')
        pg.click('#btn-pay')
        pg.wait_for_timeout(2000)
        toasts = pg.evaluate(
            "() => [...document.querySelectorAll('#scan-toasts div')]"
            ".map(t => t.textContent.trim())")
        check('one message, and it names the worker',
              len(toasts) == 1 and NAME in toasts[0], True)
        # Cleared so a second press cannot book the same money twice; the
        # type stays because the next worker usually wants the same thing.
        check('the amount is cleared', pg.evaluate(
            "() => document.getElementById('pay-amount').value"), '')
        check('the type is kept', pg.evaluate(
            "() => document.getElementById('pay-type').value"), 'advance')
        check('the card is still up, camera untouched', hidden('#result-card'),
              False)

        print('\n--- and nothing threw ---')
        check('page errors', errors, [])
        ctx.close()
        br.close()

    print('\n--- what actually reached the database ---')
    with app.app_context():
        rows = m.WorkerTransaction.query.filter(
            m.WorkerTransaction.description.like(NOTE + '%')).all()
        check('exactly one row', len(rows), 1)
        if rows:
            r = rows[0]
            check('against the right worker', r.worker_id, WID)
            check('the right type', r.txn_type, 'advance')
            check('the right amount', float(r.amount), 250.0)
            check('dated today', r.date, today_ist())
            check('stamped with the account', r.account_id, ACCT)
            check('and with who booked it', bool(r.created_by), True)

    # ------------------------------------------------------------------
    # Part two: the permissions, asked of the endpoint.
    # ------------------------------------------------------------------
    def opener():
        cj = http.cookiejar.CookieJar()
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))

    def token(op, path='/login'):
        html = op.open(B + path).read().decode()
        hit = (re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
               or re.search(r'name="csrf-token" content="([^"]+)"', html))
        return hit.group(1) if hit else ''

    def session_for(username, password):
        op = opener()
        op.open(B + '/login', urllib.parse.urlencode(
            {'username': username, 'password': password,
             'csrf_token': token(op)}).encode()).read()
        return op

    def fetch(op, path, data=None):
        """Status and where we were sent, following nothing."""
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        o = urllib.request.build_opener(
            *[h for h in op.handlers
              if isinstance(h, urllib.request.HTTPCookieProcessor)],
            NoRedirect())
        req = urllib.request.Request(
            B + path, urllib.parse.urlencode(data).encode() if data else None)
        try:
            r = o.open(req)
            return r.getcode(), path
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get('Location', '') or path

    def pay(op, who, csrf, **over):
        body = {'csrf_token': csrf, 'worker_id': who, 'txn_type': 'advance',
                'amount': 99, 'date': today_ist().isoformat(),
                'description': NOTE + ' perms'}
        body.update(over)
        return fetch(op, '/api/worker_transaction', body)

    print('\n--- nobody signed in ---')
    anon = opener()
    code, where = fetch(anon, '/scan')
    check('the scanner sends them to sign in', (code, '/login' in where),
          (302, True))
    code, _ = pay(anon, WID, '')
    check('the endpoint will not take a post',
          code in (302, 400, 401, 403), True)

    print('\n--- a worker login made a supervisor, money power granted ---')
    with app.app_context():
        sup = m.User(username='zzscanpay_sup', email='zzscanpay@test.local',
                     full_name='ZZ Scan Pay Supervisor', role='worker')
        sup.account_id = ACCT
        sup.set_password('probe12345')
        sup.worker_id = WID
        sup.can_mark_attendance = True
        sup.can_record_transactions = True
        sup.assigned_worker_ids = '%d,%d' % (WID, OTHER_ID)
        db.session.add(sup)
        db.session.commit()
        probe_users.append(sup.id)
        SUP_ID = sup.id

    sup_op = session_for('zzscanpay_sup', 'probe12345')
    code, where = fetch(sup_op, '/scan')
    check('the scanner opens for them', code, 200)
    code, where = fetch(sup_op, '/me/team')
    check('their own team screen still opens', code, 200)

    # The whole point of giving them the scanner is that it stays inside
    # their own list. The allowlist opened four endpoints; each one is asked
    # about a worker who is not on that list, and about themselves, because
    # a mukadam marking or paying himself is the fraud the design exists to
    # stop.
    sup_csrf = token(sup_op, '/scan')

    def lookup(op, worker_code):
        try:
            r = op.open(B + '/api/worker_lookup?code=' + worker_code)
            return r.getcode(), json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def mark(op, worker_id, csrf):
        """Status, and whether the endpoint says it did anything.

        It answers 200 either way — the refusal is carried in the body, the
        way the day view expects to read it — so the body is what matters.
        """
        body = {'csrf_token': csrf, 'worker_id': worker_id,
                'date': today_ist().isoformat(), 'status': 'present',
                'marked_via': 'qr'}
        try:
            r = op.open(urllib.request.Request(
                B + '/api/mark_attendance', urllib.parse.urlencode(body).encode()))
            return r.getcode(), json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, {}

    with app.app_context():
        mine_code = m.Worker.query.get(OTHER_ID).worker_id
        own_code = m.Worker.query.get(WID).worker_id
        outsider = m.Worker.query.filter(
            m.Worker.account_id == ACCT, m.Worker.status == 'active',
            m.Worker.id.notin_([WID, OTHER_ID])).first()
        out_code, OUT_ID = (outsider.worker_id, outsider.id) if outsider else (None, None)
        total_active = m.Worker.query.filter_by(status='active').count()

    code, said = lookup(sup_op, mine_code)
    check('may look up the worker on their list', code, 200)
    check('and is offered the payment section', said['worker']['can_pay'], True)

    code, said = lookup(sup_op, own_code)
    check('may not look themselves up', code, 404)

    if out_code:
        code, said = lookup(sup_op, out_code)
        check('may not look up a worker off their list', code, 404)
        # The same wording for missing, inactive and out-of-scope, so the
        # endpoint never confirms which employee IDs exist.
        check('and is told nothing about whether that ID exists',
              'No matching worker on your site' in said.get('message', ''), True)
        code, said = mark(sup_op, OUT_ID, sup_csrf)
        check('may not mark a worker off their list',
              said.get('success'), False)
        with app.app_context():
            marked = m.AttendanceRecord.query.filter_by(
                worker_id=OUT_ID, date=today_ist()).first()
            check('and nothing was written for them',
                  marked is None or marked.marked_by != SUP_ID, True)
        code, _ = pay(sup_op, OUT_ID, sup_csrf)
        check('may not pay a worker off their list', code, 403)
    else:
        print('  SKIP  no third worker to stand outside the list')

    code, _ = pay(sup_op, WID, sup_csrf)
    check('may not pay themselves', code, 403)

    # The header counters run off the same visibility rule, so they are the
    # cheapest place to see a scoping mistake: a company-wide number here
    # means a company-wide roster somewhere.
    page = sup_op.open(B + '/scan').read().decode()
    counted = sum(int(n) for n in re.findall(
        r'id="stat-(?:present|late|absent)"[^>]*>(\d+)<', page))
    check('the header counts their list, not the company',
          counted <= 1, True)
    check('(their list holds one worker, the company holds more)',
          total_active > 1, True)
    # The bottom nav's tabs are all screens a worker login may not open, so
    # its presence would be six buttons that throw them back to /me. Looked
    # for by href and not by class name: the class is also a CSS rule in the
    # <style> block, which is on every page either way.
    check('no bottom navigation to screens they cannot open',
          'href="/dashboard"' in page, False)
    check('but a way back to their team', '/me/team' in page, True)

    print('\n--- an administrator, and what even they may not post ---')
    admin_op = session_for('demo@acme.test', 'demo12345')
    csrf = token(admin_op, '/scan')
    check('the scanner carries a csrf token', bool(csrf), True)
    # The other half of the nav check above: an administrator does get the
    # bottom bar, so its absence for a mukadam is the guard working and not
    # the marker having moved.
    check('an administrator still gets the bottom navigation',
          'href="/dashboard"' in admin_op.open(B + '/scan').read().decode(), True)
    code, _ = pay(admin_op, OTHER_ID, csrf)
    check('may record for any worker', code, 200)
    for label, over, want in [
            ('a worker who does not exist', {'worker_id': 99999999}, 403),
            ('no worker at all', {'worker_id': ''}, 403),
            ('an amount of zero', {'amount': 0}, 400),
            ('a negative amount', {'amount': -500}, 400),
            ('a type that is not a type', {'txn_type': 'skim'}, 400),
            ('a date in the future',
             {'date': (today_ist() + timedelta(days=1)).isoformat()}, 400),
            ('no csrf token', {'csrf_token': ''}, 400),
    ]:
        code, _ = pay(admin_op, OTHER_ID, csrf, **over)
        check(label, code, want)

    if FOREIGN_ID:
        code, _ = pay(admin_op, FOREIGN_ID, csrf)
        check('a worker in another company', code, 403)
    else:
        print('  SKIP  no second company in this database')

    # ------------------------------------------------------------------
    # Part three: in Hindi. The gate phone is the likeliest device in the
    # company to be set to Hindi, and these messages are painted by
    # JavaScript — they reach nobody through a template filter, so being in
    # the dictionary is not the same as arriving translated.
    # ------------------------------------------------------------------
    print('\n--- the same screen in Hindi ---')
    hi_op = session_for('demo@acme.test', 'demo12345')
    hi_op.open(B + '/language/hi', urllib.parse.urlencode(
        {'csrf_token': token(hi_op, '/scan')}).encode()).read()

    def devanagari(s):
        return any('ऀ' <= ch <= 'ॿ' for ch in s)

    page = hi_op.open(B + '/scan').read().decode()
    for s in ['Amount must be greater than zero.',
              'Could not record the payment. Please try again.',
              'No connection — the payment was not recorded.',
              'Attendance updated.',
              'Could not update attendance.',
              'No connection — attendance was not saved.',
              # The rest of the screen's script, which was English too:
              # every one of these is a sentence a person at a gate reads
              # when something has gone wrong, and so the worst place for it.
              'Starting camera…',
              'Scanner unavailable',
              "Couldn't load the scanner",
              'Scanner paused',
              'Point the camera at the QR code',
              'Looking up %s',
              'No matching worker.',
              'The server returned an unexpected response.',
              'check your internet and try again']:
        check('no English left in the script: %r' % s[:34], s in page, False)

    # And the lookup's own refusals, which travel as a lone 'message' rather
    # than the 'messages' list the translator used to be the only thing
    # walking.
    for label, query, want in [('an id that belongs to nobody', 'NOSUCHID9', False),
                               ('an empty id', '', False)]:
        try:
            said = json.loads(hi_op.open(
                B + '/api/worker_lookup?code=' + query).read().decode())
        except urllib.error.HTTPError as e:
            said = json.loads(e.read().decode())
        check('refusal is in Hindi: %s' % label,
              devanagari(said.get('message', '')), True)

    hi_csrf = token(hi_op, '/scan')
    code, _ = pay(hi_op, OTHER_ID, hi_csrf)
    check('a Hindi reader may still record', code, 200)
    # Posted through the cookie jar, so the session language applies.
    body = hi_op.open(urllib.request.Request(
        B + '/api/worker_transaction', urllib.parse.urlencode({
            'csrf_token': hi_csrf, 'worker_id': OTHER_ID,
            'txn_type': 'refreshment', 'amount': 120,
            'date': today_ist().isoformat(),
            'description': NOTE + ' hindi'}).encode())).read().decode()
    # jsonify escapes non-ASCII, so the Devanagari is \uXXXX in the wire
    # bytes — read the decoded message, not the body.
    said = ' '.join(m['text'] for m in json.loads(body).get('messages') or [])
    print('        %s' % said)
    check('the confirmation comes back in Hindi', devanagari(said), True)
    check('and not half in English', 'recorded for' in said, False)
    # The type name has a Hindi word of its own; leaving it in English
    # mid-sentence is the thing this checks against.
    check('with the type named in Hindi', 'Refreshment' in said, False)

    # ------------------------------------------------------------------
    # Part four: the rule itself. The mukadam branch of
    # may_record_transaction_for cannot be reached over HTTP while the
    # scanner is outside SUPERVISOR_ENDPOINTS, and an untested branch is how
    # a rule rots between the day it is written and the day it is opened up.
    # ------------------------------------------------------------------
    print('\n--- the rule, called directly ---')
    from routes import may_record_transaction_for as may
    with app.app_context():
        boss = m.User.query.filter_by(username='demo').first()
        mine = m.Worker.query.get(OTHER_ID)
        theirs = m.Worker.query.filter(
            m.Worker.account_id == ACCT,
            m.Worker.id.notin_([WID, OTHER_ID])).first()
        mukadam = m.User(username='zzrule_sup', email='zzrule@test.local',
                         full_name='ZZ Rule Mukadam', role='worker')
        mukadam.account_id = ACCT
        mukadam.set_password('probe12345')
        mukadam.worker_id = WID
        mukadam.can_mark_attendance = True
        mukadam.can_record_transactions = True
        mukadam.assigned_worker_ids = str(OTHER_ID)
        db.session.add(mukadam)
        db.session.commit()
        probe_users.append(mukadam.id)

        check('an administrator, for anyone', may(boss, mine), True)
        check('an administrator, for nobody', may(boss, None), False)
        check('a mukadam, for their own worker', may(mukadam, mine), True)
        if theirs:
            check('a mukadam, for somebody else\'s',
                  may(mukadam, theirs), False)
        else:
            print('  SKIP  no third worker to stand outside the list')
        mukadam.can_record_transactions = False
        db.session.commit()
        check('a mukadam with the power revoked', may(mukadam, mine), False)
finally:
    server.terminate()
    server.wait(timeout=10)
    with app.app_context():
        m.WorkerTransaction.query.filter(
            m.WorkerTransaction.description.like(NOTE + '%')).delete(
                synchronize_session=False)
        m.Notification.query.filter(
            m.Notification.body.like('%ZZ Scan Pay%')).delete(
                synchronize_session=False)
        m.User.query.filter(m.User.username.like('zzscanpay%')).delete(
            synchronize_session=False)
        m.User.query.filter(m.User.username.like('zzrule%')).delete(
            synchronize_session=False)
        if probe_users:
            m.User.query.filter(m.User.id.in_(probe_users)).delete(
                synchronize_session=False)
        db.session.commit()
        check('the database is back where it started',
              m.WorkerTransaction.query.count(), TXNS_BEFORE)
        check('the probe logins are gone',
              m.User.query.filter(m.User.username.like('zz%')).count(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The scanner records payments, and refuses everyone it should.')
