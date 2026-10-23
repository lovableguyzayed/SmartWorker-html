"""The printed payslip and worker report fit on two sheets.

Both documents used to end on a third sheet that was 81-85% empty, and at
one point on one that was entirely blank. Neither was too tall for two
sheets by much — the payslip ran about 9mm over, the report about 10mm —
so this is a margin that a careless change can spend without anyone
noticing until a document comes out of a printer.

Two things are checked. That each document is two pages, in both
languages. And that the saving came from white space rather than from
shrinking the figures: the type sizes are pinned here, because the easy
way to win a page on a document that goes to a worker and to an inspector
is to make the numbers smaller, and that is the one way it must not be
won.

The blank-sheet trap has its own check. base.html declares the bottom-nav
clearance with !important in an inline <style>, and custom.css carried a
print reset for it that could never win on source order — so every printed
screen was padded with 30mm of clearance for a navigation bar that paper
does not have. A copy of that reset in the wrong file looks right and does
nothing, so the test asserts where it lives.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

import pymupdf
from playwright.sync_api import sync_playwright

from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
PORT = 5107
B = 'http://127.0.0.1:%d' % PORT

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-52s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


# ----------------------------------------------------------------------
# The documents themselves.
# ----------------------------------------------------------------------

with app.app_context():
    # Somebody on a monthly salary: that is the worker whose payslip carries
    # the long Salary Calculation table, and the only one that ever ran over.
    WID = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

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

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_printed')
    os.makedirs(out, exist_ok=True)

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844},
                             service_workers='block')
        pg = ctx.new_page()
        pg.goto(B + '/login', wait_until='domcontentloaded')
        pg.wait_for_timeout(700)
        pg.fill('input[name="username"]', 'demo@acme.test')
        pg.fill('input[name="password"]', 'demo12345')
        pg.click('#signin-form button[type="submit"]')
        # wait_for_url rather than a string predicate: Playwright
        # evaluates those with eval(), which the page's
        # Content-Security-Policy refuses.

        pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

        for lang in ('en', 'hi'):
            pg.goto(B + '/profile', wait_until='domcontentloaded')
            pg.wait_for_timeout(700)
            pg.locator('form[action*="/language/%s"] button[type=submit]' % lang
                       ).first.click()
            pg.wait_for_timeout(1400)

            print('\n--- %s ---' % lang)
            for name, url in (('payslip', '/payroll/slip/%d' % WID),
                              ('worker report', '/worker/%d/report' % WID)):
                pg.goto(B + url, wait_until='domcontentloaded')
                pg.wait_for_timeout(2600)
                path = os.path.join(out, '%s-%s.pdf' % (name.split()[0], lang))
                pg.pdf(path=path, format='A4', print_background=True,
                       margin={'top': '12mm', 'bottom': '12mm',
                               'left': '12mm', 'right': '12mm'})
                doc = pymupdf.open(path)
                pages = doc.page_count
                # A sheet carrying only the running header is still a wasted
                # sheet, so check that every page has real content on it.
                thin = [i + 1 for i, pg_ in enumerate(doc)
                        if len(pg_.get_text().strip()) < 150]
                doc.close()
                check('%s is two sheets' % name, pages, 2)
                check('%s has no near-empty sheet' % name, thin, [])
        ctx.close()
        br.close()
finally:
    server.terminate()
    server.wait(timeout=10)

# ----------------------------------------------------------------------
# How the space was won.
# ----------------------------------------------------------------------

print('\n--- the saving came out of white space, not out of the type ---')
slip = open(os.path.join(ROOT, 'templates', 'payroll_slip.html')).read()
report = open(os.path.join(ROOT, 'templates', 'worker_report.html')).read()

# No font-size may be set inside either print stylesheet. Shrinking the
# figures is the one way this must not be won.
for name, text in (('payslip', slip), ('worker report', report)):
    block = re.search(r'@media print\s*\{(.*?)\n\}', text, re.S)
    check('%s print block found' % name, bool(block), True)
    if block:
        check('%s print css sets no font-size' % name,
              'font-size' in block.group(1), False)

# The report's table padding has to out-specify the screen rule declared
# further down the same file, or it silently does nothing.
check('report table padding is scoped past the screen rule',
      '.report-body .report-table td' in report, True)

print('\n--- the bottom-nav clearance is reset where it is declared ---')
base = open(os.path.join(ROOT, 'templates', 'base.html')).read()
custom = open(os.path.join(ROOT, 'static', 'css', 'custom.css')).read()

# base.html sets the clearance with !important in an inline <style> that
# comes after custom.css is linked. A reset anywhere earlier loses.
check('base.html declares the clearance',
      bool(re.search(r'\.has-bottom-nav\s*\{[^}]*padding-bottom:\s*calc', base)), True)
check('base.html resets it for print',
      bool(re.search(r'@media print\s*\{\s*\.has-bottom-nav\s*\{\s*'
                     r'padding-bottom:\s*0', base)), True)
check('custom.css does not carry a reset that cannot win',
      bool(re.search(r'\.has-bottom-nav\s*\{\s*padding-bottom:\s*0', custom)), False)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('All print-pagination checks passed.')
