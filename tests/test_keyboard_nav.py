"""The bottom bar steps aside while the keyboard is up.

What the employer saw: open any box you can type into and the navigation
bar climbs up the screen with the keyboard and sits on the keys.

Nothing was animating it. The bar is `position: fixed; bottom: 0`, and
Android's WebView opens the keyboard with windowSoftInputMode=adjustResize,
which shortens the viewport by the height of the keyboard. "The bottom"
moves up, so the bar moves up — exactly where it was told to be, which
happens to be across the field being typed into.

A soft keyboard cannot be summoned in a headless browser, so what is
checked here is the mechanism that hides the bar, on the real page, with
real focus events:

  * focusing a text box hides the bar, and blurring it brings the bar back.
  * the same for a textarea, a number box and a date box — the four kinds
    actually on these screens.
  * a <select> does NOT hide it. That opens a picker, not a keyboard, and
    losing the bar for it would be a flicker with no cause.
  * moving from one field to the next on the same form does not flash the
    bar back between them. This is why focusout is deferred and then asks
    what actually has focus.
  * changing screens clears it. The SPA replaces document.body.innerHTML,
    so the class on <body> would otherwise outlive the keyboard.
  * the clearance padding under the content does NOT change, so the page
    does not reflow and move the field out from under the cursor.

Run from the project root:  python3 tests/test_keyboard_nav.py
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
PORT = 5131
B = 'http://127.0.0.1:%d' % PORT

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if ok else 'FAIL', label, got))


NAV_SHOWN = """() => {
    const nav = document.querySelector('nav.app-bottom-nav');
    if (!nav) return 'no-nav';
    return nav.checkVisibility() ? 'shown' : 'hidden';
}"""

server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
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

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             is_mobile=True, has_touch=True,
                             service_workers='block')
        pg = ctx.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)[:120]))

        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(600)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
        pg.wait_for_timeout(1200)

        # ------------------------------------------------------------------
        print('--- a text box hides it, blurring brings it back ---')

        # The attendance screen: the employee-ID box is the one the employer
        # types into most, and the bar sat on top of it.
        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(1500)
        check('the bar is there to begin with', pg.evaluate(NAV_SHOWN), 'shown')

        box = pg.query_selector('#ep-scan-input') or pg.query_selector(
            'input[type="text"], input[type="search"]')
        check('the screen has a box to type in', box is not None, True)
        if box:
            box.focus()
            pg.wait_for_timeout(250)
            check('focusing it hides the bar', pg.evaluate(NAV_SHOWN), 'hidden')
            check('and the body says why',
                  pg.evaluate("() => document.body.classList.contains('kb-open')"),
                  True)
            pg.evaluate("() => document.activeElement.blur()")
            pg.wait_for_timeout(250)
            check('blurring brings it back', pg.evaluate(NAV_SHOWN), 'shown')

        # ------------------------------------------------------------------
        print('\n--- every kind of field on these screens ---')

        # Built on the live page rather than hunting for one of each: what is
        # being checked is the rule, not which screen happens to carry a
        # month box this week.
        # Each field is focused, then a turn of the event loop is awaited
        # before reading the bar. Written synchronously at first, which
        # reported that a <button> hid the bar: focusout is deliberately
        # deferred (see app.js), so a synchronous loop reads the state left
        # by the PREVIOUS field and the whole probe measures nothing.
        kinds = pg.evaluate("""async () => {
            const out = {};
            const tick = () => new Promise(r => setTimeout(r, 30));
            const host = document.createElement('div');
            host.id = 'kb-probe';
            document.body.appendChild(host);
            const make = (html) => { host.innerHTML = html;
                                     return host.firstElementChild; };
            const shown = () => {
                const n = document.querySelector('nav.app-bottom-nav');
                return n ? n.checkVisibility() : null;
            };
            for (const [name, html] of [
                    ['text',     '<input type="text">'],
                    ['number',   '<input type="number">'],
                    ['date',     '<input type="date">'],
                    ['password', '<input type="password">'],
                    ['textarea', '<textarea></textarea>'],
                    ['select',   '<select><option>a</option></select>'],
                    ['checkbox', '<input type="checkbox">'],
                    ['button',   '<button type="button">x</button>']]) {
                const el = make(html);
                el.focus();
                await tick();
                out[name] = shown() ? 'shown' : 'hidden';
                el.blur();
                await tick();
            }
            host.remove();
            return out;
        }""")
        pg.wait_for_timeout(250)

        for name in ('text', 'number', 'date', 'password', 'textarea'):
            check('%-8s is typed into, so the bar hides' % name,
                  kinds.get(name), 'hidden')
        for name in ('select', 'checkbox', 'button'):
            check('%-8s opens no keyboard, so the bar stays' % name,
                  kinds.get(name), 'shown')
        check('and the bar is back after the probe',
              pg.evaluate(NAV_SHOWN), 'shown')

        # ------------------------------------------------------------------
        print('\n--- two fields on one form do not flash it back ---')

        flicker = pg.evaluate("""() => new Promise((resolve) => {
            const host = document.createElement('div');
            host.innerHTML = '<input id="kb-a" type="text">'
                           + '<input id="kb-b" type="text">';
            document.body.appendChild(host);
            const nav = document.querySelector('nav.app-bottom-nav');
            let reappeared = false;
            const watch = new MutationObserver(() => {
                if (!document.body.classList.contains('kb-open')) {
                    reappeared = true;
                }
            });
            document.getElementById('kb-a').focus();
            watch.observe(document.body, {attributes: true,
                                          attributeFilter: ['class']});
            document.getElementById('kb-b').focus();
            setTimeout(() => {
                watch.disconnect();
                const hidden = nav ? !nav.checkVisibility() : null;
                document.activeElement.blur();
                host.remove();
                resolve({reappeared, hidden});
            }, 120);
        })""")
        check('the bar never came back between the two boxes',
              flicker['reappeared'], False)
        check('and it is still hidden on the second one',
              flicker['hidden'], True)
        pg.wait_for_timeout(250)

        # ------------------------------------------------------------------
        print('\n--- the content does not reflow under the cursor ---')

        pad = pg.evaluate("""() => {
            const app = document.getElementById('mobile-app');
            const read = () => getComputedStyle(app).paddingBottom;
            const before = read();
            const host = document.createElement('div');
            host.innerHTML = '<input id="kb-c" type="text">';
            document.body.appendChild(host);
            document.getElementById('kb-c').focus();
            const during = read();
            document.activeElement.blur();
            host.remove();
            return {before, during};
        }""")
        check('the clearance padding is unchanged while typing',
              pad['during'], pad['before'])
        print('       (%s both before and during)' % pad['before'])

        # ------------------------------------------------------------------
        print('\n--- changing screens clears it ---')

        # Two things, because they clear it by different routes and both
        # have to work. A real tap on a link blurs the field first, so that
        # path exercises the blur handler; the SPA's own page:load is what
        # catches a screen change that never blurred anything — the Android
        # back button, or a redirect after a save.
        pg.evaluate("""() => {
            const host = document.createElement('div');
            host.id = 'kb-d-host';
            host.innerHTML = '<input id="kb-d" type="text">';
            document.body.appendChild(host);
            document.getElementById('kb-d').focus();
        }""")
        pg.wait_for_timeout(250)
        check('hidden while the box has focus', pg.evaluate(NAV_SHOWN), 'hidden')

        check('page:load alone clears it',
              pg.evaluate("""() => {
                  document.dispatchEvent(new Event('page:load'));
                  return document.body.classList.contains('kb-open');
              }"""), False)
        pg.evaluate("() => document.getElementById('kb-d-host').remove()")

        # And the same thing the employer actually does: type, then tap a
        # link. NativeShell is not on window — it is module-scoped in
        # app.js — so this goes through the delegated click handler, which
        # is the real path anyway.
        pg.evaluate("""() => {
            const host = document.createElement('div');
            host.innerHTML = '<input id="kb-e" type="text">';
            document.body.appendChild(host);
            document.getElementById('kb-e').focus();
        }""")
        pg.wait_for_timeout(250)
        # A link in the CONTENT, not in the bar: the bar is hidden at this
        # point, which is the whole point, and Playwright refuses to click
        # what cannot be seen. The employer taps a worker's name the same
        # way.
        link = pg.query_selector('#mobile-app a[href^="/worker/"]') \
            or pg.query_selector('#mobile-app a[href^="/"]')
        check('there is a link to tap', link is not None, True)
        if link:
            link.click()
            pg.wait_for_timeout(2500)
            check('and shown again on the next screen',
                  pg.evaluate(NAV_SHOWN), 'shown')
            check('with the class gone',
                  pg.evaluate(
                      "() => document.body.classList.contains('kb-open')"),
                  False)

        check('no script threw during any of it', errors, [])
        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('The bottom bar steps aside for the keyboard, and comes back after.')
