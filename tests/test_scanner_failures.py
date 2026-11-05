"""The scanner, when the camera does not open and the card will not read.

At a gate, in the sun, with men waiting, the screen said:

    Camera unavailable (NotAllowedError: Permission denied by system).
    Allow camera access in Settings, or enter the Employee ID below.

Three things wrong with that, and none of them is the camera.

  * the half after the bracket was never translated, so a Hindi screen
    ended in English in the one sentence that tells somebody what to do.
  * the advice was the same whatever happened. "Allow camera access" is
    no use on a phone with no camera, and no use when WhatsApp has the
    camera open — which, at a site, it does.
  * NotAllowedError is developer text. The man holding the phone cannot
    act on it, and it tells him nothing he could not already see.

Each cause now gets the advice that fits it, the exception goes to the
console where it belongs, and the cursor lands in the ID box so the work
can still be done.

And the card itself: the library's error callback fires on nearly every
frame, even when all is well, so nothing can be said on it. But a card
six months in a trouser pocket is scratched and dusty, and sometimes a
photocopy. After twelve seconds of not reading — an ordinary scan takes
two — the screen offers the way out.

Driven with Chromium's fake camera, so the failures are real failures
rather than stubs: --use-fake-device-for-media-stream gives a camera that
exists and shows a test pattern no QR will ever decode, and denying the
camera permission through the browser context produces a genuine
NotAllowedError from getUserMedia.

Run from the project root:  python3 tests/test_scanner_failures.py
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5142
B = 'http://127.0.0.1:%d' % PORT

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, got))


STATUS = "() => (document.getElementById('scanner-status') || {}).textContent"

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d, threaded=True)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sign_in(page):
    page.goto(B + '/login', wait_until='domcontentloaded')
    page.wait_for_timeout(500)
    page.fill('input[name="username"]', 'demo@acme.test')
    page.fill('input[name="password"]', 'demo12345')
    page.click('#signin-form button[type="submit"]')
    page.wait_for_url(lambda u: '/login' not in u, timeout=20000)


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
        # ------------------------------------------------------------------
        print('--- the camera is refused ---')

        # A camera that EXISTS (the fake device) with the permission
        # withheld, which is what a refused prompt looks like. Without the
        # fake device this machine has no camera at all and the browser
        # raises NotFoundError instead — a different failure with
        # different advice, checked separately below.
        browser = p.chromium.launch(
            executable_path=EXE,
            args=['--no-sandbox', '--use-fake-device-for-media-stream'])
        ctx = browser.new_context(viewport={'width': 390, 'height': 844},
                                  is_mobile=True, has_touch=True,
                                  service_workers='block')
        ctx.grant_permissions([])
        page = ctx.new_page()
        warnings = []
        page.on('console', lambda m: warnings.append(m.text)
                if m.type == 'warning' else None)
        sign_in(page)
        page.goto(B + '/scan', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)

        said = page.evaluate(STATUS) or ''
        print('       screen says: %s' % said[:72])
        check('it says the permission was refused',
              'permission was refused' in said.lower(), True)
        check('it offers the box instead',
              'type the id below' in said.lower(), True)
        check('and the exception is not on the screen',
              'NotAllowedError' in said or 'Error' in said, False)
        check('it went to the console instead',
              any('camera failed' in w for w in warnings), True)
        check('the cursor is in the ID box',
              page.evaluate("() => document.activeElement &&"
                            " document.activeElement.id"), 'manual-id')
        ctx.close()
        browser.close()

        # ------------------------------------------------------------------
        print('\n--- a phone with no camera at all ---')

        browser = p.chromium.launch(executable_path=EXE,
                                    args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 390, 'height': 844},
                                  is_mobile=True, has_touch=True,
                                  service_workers='block',
                                  permissions=['camera'])
        page = ctx.new_page()
        sign_in(page)
        page.goto(B + '/scan', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        said = page.evaluate(STATUS) or ''
        print('       screen says: %s' % said[:72])
        check('it does not blame the permission',
              'permission' in said.lower(), False)
        check('it says there is no camera',
              'no camera' in said.lower(), True)
        check('and still offers the box',
              'type the id below' in said.lower(), True)
        ctx.close()
        browser.close()

        # ------------------------------------------------------------------
        print('\n--- a camera that works, on a card that will not read ---')

        browser = p.chromium.launch(
            executable_path=EXE,
            args=['--no-sandbox',
                  '--use-fake-ui-for-media-stream',
                  '--use-fake-device-for-media-stream'])
        ctx = browser.new_context(viewport={'width': 390, 'height': 844},
                                  is_mobile=True, has_touch=True,
                                  service_workers='block',
                                  permissions=['camera'])
        page = ctx.new_page()
        sign_in(page)
        page.goto(B + '/scan', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)

        said = page.evaluate(STATUS) or ''
        check('it starts by asking for the card',
              'QR' in said or 'camera' in said.lower(), True)
        check('and says nothing about trouble yet',
              'Not reading' in said, False)

        # Twelve seconds, plus room for a slow box.
        page.wait_for_timeout(12000)
        said = page.evaluate(STATUS) or ''
        print('       after twelve seconds: %s' % said[:72])
        check('then it offers a way out', 'Not reading' in said, True)
        check('which is the ID box', 'type the ID below' in said, True)

        # And it stops nagging the moment something reads.
        page.evaluate("() => { onScanSuccess('CO001'); }")
        page.wait_for_timeout(400)
        check('the hint is cancelled once a card reads',
              page.evaluate("() => struggleTimer === null"), True)
        ctx.close()
        browser.close()

    # ----------------------------------------------------------------------
    print('\n--- every one of those sentences has Hindi ---')
    import i18n
    MESSAGES = [
        'Camera permission was refused. Allow the camera in your phone '
        'settings, or type the ID below.',
        'No camera this app can use. Type the ID below instead.',
        'Another app is using the camera. Close it and try again, or type '
        'the ID below.',
        'That camera could not be opened. Try the other camera, or type '
        'the ID below.',
        'The camera only works on a secure connection. Type the ID below '
        'instead.',
        'The camera could not be started. Type the ID below instead.',
        'Not reading? Wipe the card and hold it still — or type the ID '
        'below.',
    ]
    check('none of them is left in English',
          [m for m in MESSAGES if i18n.translate(m, 'hi') == m], [])

    source = open(os.path.join(ROOT, 'templates/scan.html')).read()
    missing = [m for m in MESSAGES
               if ' '.join(m.split()) not in ' '.join(source.split())]
    check('and every one of them is really in the screen', missing, [])
finally:
    server.terminate()
    server.wait(timeout=10)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('A camera that will not open, and a card that will not read, both '
      'say what to do about it.')
