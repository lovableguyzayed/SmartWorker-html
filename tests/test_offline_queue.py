"""A phone with no signal must not lose what was done on it.

Attendance is marked and wages are handed over at a gate, which is exactly
where there is no network. The app queues those writes in IndexedDB and
replays them when the signal returns — and until now nothing tested that
it did. The queue could have been broken for months without a single
suite going red, which is the worst way to hold a feature that only
matters on the day the network is down.

Walked here end to end, against a real server and a real browser:

    online   -> a payment reaches the database
    offline  -> the same payment reaches the queue and NOT the database,
                and the caller is told it was stored, not that it worked
    online   -> the queue drains, the row appears, the queue is empty

The last step is the one that matters. A queue that fills and never
empties loses the data just as completely as having no queue, and takes
longer to notice.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright

from app import app, db
import models as m
from timeutil import today_ist

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5171
B = 'http://127.0.0.1:%d' % PORT

fails = []


def check(label, got, want):
    if got == want:
        print('  PASS %-52s %s' % (label, repr(got)[:24]))
    else:
        fails.append(label)
        print('  FAIL %-52s got=%r want=%r' % (label, got, want))


NOTE_ONLINE = 'ZZ offline test online'
NOTE_QUEUED = 'ZZ offline test queued'


def count(note):
    with app.app_context():
        return m.WorkerTransaction.query.filter_by(description=note).count()


with app.app_context():
    worker = m.Worker.query.filter_by(status='active').order_by(
        m.Worker.id).first()
    WID = worker.id
    # Nothing from a previous run may be left behind, or the counts below
    # measure the wrong thing.
    m.WorkerTransaction.query.filter(
        m.WorkerTransaction.description.in_([NOTE_ONLINE, NOTE_QUEUED])
    ).delete(synchronize_session=False)
    db.session.commit()

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d, threaded=True)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(B + '/login', timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit('could not start a server on %s' % B)

    POST = """async (args) => {
        const fd = new URLSearchParams();
        fd.set('worker_id', args.wid);
        fd.set('txn_type', 'wage_payment');
        fd.set('amount', args.amount);
        fd.set('date', args.today);
        fd.set('description', args.note);
        fd.set('payment_mode', 'cash');
        fd.set('csrf_token', document.querySelector(
            'meta[name=csrf-token]').getAttribute('content'));
        const r = await fetch('/api/worker_transaction', {
            method: 'POST', body: fd, credentials: 'same-origin'});
        let body = null;
        try { body = await r.json(); } catch (e) {}
        return {status: r.status, body: body};
    }"""

    QUEUE_LEN = """async () => {
        return await new Promise((resolve) => {
            const req = indexedDB.open('smartworker-offline');
            req.onsuccess = () => {
                const dbh = req.result;
                if (!dbh.objectStoreNames.contains('sync-queue'))
                    return resolve(0);
                const tx = dbh.transaction('sync-queue', 'readonly');
                const c = tx.objectStore('sync-queue').count();
                c.onsuccess = () => resolve(c.result);
                c.onerror = () => resolve(-1);
            };
            req.onerror = () => resolve(-1);
        });
    }"""

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        pg.goto(B + '/scan', wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)

        args = {'wid': WID, 'today': today_ist().isoformat()}

        print('--- with a signal, it goes straight to the server ---')
        res = pg.evaluate(POST, dict(args, amount='111', note=NOTE_ONLINE))
        check('the server answered', res['status'], 200)
        check('and said it worked', res['body'] and res['body']['success'],
              True)
        check('the row is in the database', count(NOTE_ONLINE), 1)
        check('and nothing was queued', pg.evaluate(QUEUE_LEN), 0)

        print('\n--- with no signal, it goes to the phone ---')
        ctx.set_offline(True)
        pg.evaluate("() => window.dispatchEvent(new Event('offline'))")
        pg.wait_for_timeout(400)
        check('the browser agrees it is offline',
              pg.evaluate('() => navigator.onLine'), False)

        res = pg.evaluate(POST, dict(args, amount='222', note=NOTE_QUEUED))
        # 202, not 200: it has not happened yet, and saying otherwise would
        # be handing somebody a receipt for a payment the server never saw.
        check('the caller gets "accepted", not "done"', res['status'], 202)
        check('and is told it is only stored',
              res['body'] and res['body']['queued'], True)
        check('it does not claim success',
              res['body'] and res['body']['success'], False)
        check('the message names a payment, not attendance',
              res['body'] and res['body']['message'],
              'Payment saved on this phone')
        check('it is in the queue', pg.evaluate(QUEUE_LEN), 1)
        check('and NOT in the database', count(NOTE_QUEUED), 0)

        print('\n--- the signal comes back ---')
        ctx.set_offline(False)
        pg.evaluate("() => window.dispatchEvent(new Event('online'))")
        # The drain is a fetch per queued item; give it room on a slow box.
        for _ in range(40):
            if count(NOTE_QUEUED):
                break
            pg.wait_for_timeout(250)
        check('the payment reached the database', count(NOTE_QUEUED), 1)
        check('exactly once', count(NOTE_QUEUED), 1)
        check('and the queue is empty again', pg.evaluate(QUEUE_LEN), 0)

        print('\n--- what must never be queued ---')
        # A queued acknowledgement would point at an id the server has not
        # issued yet, and a replayed cancel or payroll run would act on a
        # decision made against state that is hours stale by then.
        never = pg.evaluate("""() => {
            const paths = ['/api/transaction_ack/7', '/transactions/7/cancel',
                           '/payroll/save', '/transactions/7/delete'];
            return paths.filter(p => OFFLINE_QUEUEABLE.indexOf(p) !== -1);
        }""")
        check('none of the dangerous paths are queueable', never, [])

        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)
    with app.app_context():
        m.WorkerTransaction.query.filter(
            m.WorkerTransaction.description.in_([NOTE_ONLINE, NOTE_QUEUED])
        ).delete(synchronize_session=False)
        db.session.commit()
        check('the probe rows are gone',
              count(NOTE_ONLINE) + count(NOTE_QUEUED), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label in fails:
        print('  %s' % label)
    sys.exit(1)
print('Nothing done on a dead network is lost, and nothing is sent twice.')
