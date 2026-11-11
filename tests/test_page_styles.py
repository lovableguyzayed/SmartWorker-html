"""A screen's own styles leave with it.

Moving between screens swaps the page body without a reload. Each screen's
<style> blocks used to be added to the page and never taken away, so every
screen visited went on styling every screen after it. The Home screen has
an attendance table whose rows are `.att-row` (a grid); the Attendance
header had a row of the same name. Opened from Home, the header became
that grid: the title shrank to a few letters and the closure-days button
sat on top of it. Opened any other way it was fine, which is why nobody
saw it at a desk.

Checked here in a real browser, by tapping the tabs:

  * Attendance opened from Home has its title whole and the button at the
    far right, exactly as on a direct load;
  * nothing of Home's styling is left on the page afterwards;
  * and Home still has its own styles when you go back to it.

Signs in to the test fixture (tools/make_test_fixture.py).
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5133
B = 'http://127.0.0.1:%d' % PORT
fails = []


def check(label, got, want):
    if got != want:
        fails.append((label, got, want))
    print('  %-5s %-56s %r' % ('OK' if got == want else 'FAIL', label, got))


server = subprocess.Popen(
    [sys.executable, '-c',
     'import sys; sys.path.insert(0, %r);'
     'from app import app; import routes, bulk;'
     'app.run(host="127.0.0.1", port=%d)' % (ROOT, PORT)],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

HEADER = """() => {
    const row = document.querySelector('header .att-toprow');
    if (!row) return null;
    const box = (e) => { const b = e.getBoundingClientRect();
        return [Math.round(b.left), Math.round(b.right)]; };
    const links = row.querySelectorAll('a');
    return { title: box(row.querySelector('h1')), button: box(links[links.length - 1]),
             display: getComputedStyle(row).display };
}"""
# Does any rule on the page still say this?
HAS_RULE = """(needle) => [...document.styleSheets].some((sheet) => {
    try { return [...sheet.cssRules].some((r) => (r.cssText || '').includes(needle)); }
    catch (e) { return false; }
})"""

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
        browser = p.chromium.launch(executable_path=EXE)
        pg = browser.new_context(viewport={'width': 450, 'height': 1000}).new_page()
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        pg.wait_for_timeout(2500)

        print('--- Attendance, loaded directly ---')
        pg.goto(B + '/attendance', wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)
        direct = pg.evaluate(HEADER)
        check('the header row is laid out in a line', direct['display'], 'flex')
        check('the button is right of the title',
              direct['button'][0] >= direct['title'][1], True)

        print('\n--- Attendance, opened from Home by its tab ---')
        pg.goto(B + '/dashboard', wait_until='domcontentloaded')
        pg.wait_for_timeout(1200)
        check('Home has its own table styling', pg.evaluate(HAS_RULE, '.att-headrow'), True)
        pg.click('nav a[href="/attendance"]')
        pg.wait_for_timeout(2000)
        check('we arrived without a reload',
              pg.evaluate("() => performance.getEntriesByType('navigation')[0].name.endsWith('/dashboard')"),
              True)
        check('the header is exactly as on a direct load', pg.evaluate(HEADER), direct)
        check("none of Home's styling is left on the page",
              pg.evaluate(HAS_RULE, '.att-headrow'), False)

        print('\n--- and back to Home ---')
        pg.click('nav a[href="/dashboard"]')
        pg.wait_for_timeout(2000)
        check('Home has its styling again', pg.evaluate(HAS_RULE, '.att-headrow'), True)
        check('once, not once per visit', pg.evaluate(
            """() => [...document.querySelectorAll('head style')]
                   .filter((s) => s.textContent.includes('.att-headrow')).length"""), 1)
        browser.close()
finally:
    server.terminate()

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('Each screen is styled by its own styles and nobody else\'s.')
