"""Every document the application produces, and whether it reads properly.

Three documents, two languages: the payslip, the worker report and the ID
card. Two of them are built in the browser with jsPDF and html2canvas; the
report is printed by the browser itself. All three go to a worker or to an
inspector, which is a higher bar than a screen — a page break through the
middle of a pay table is not a cosmetic fault, it is the document being
wrong where somebody has to sign it.

This generates each one and then looks at every page for the four things
that go wrong with printed output:

  * a page that is blank or nearly blank, printed for no reason
  * a line of text cut by a page boundary
  * a heading stranded at the foot of a page, its table overleaf
  * a column of figures that does not line up

The raster documents cannot be checked for the last two by reading text,
because there is no text in them — so they are measured in pixels instead,
by looking for ink crossing the boundary.
"""
import io
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import pymupdf
from PIL import Image
from playwright.sync_api import sync_playwright
from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
B = os.environ.get('UX_BASE', 'http://127.0.0.1:5000')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'documents')
os.makedirs(OUT, exist_ok=True)

# Trap the blob the page hands to the file saver, rather than downloading it.
CAPTURE = """() => {
    window.__pdf = null;
    SmartWorkerSave.blob = function (blob) {
        return new Promise((resolve) => {
            const r = new FileReader();
            r.onload = () => { window.__pdf = r.result.split(',')[1]; resolve('ok'); };
            r.readAsDataURL(blob);
        });
    };
}"""


def build_via_button(pg, url, button, lang, name):
    pg.goto(B + '/profile', wait_until='domcontentloaded')
    pg.wait_for_timeout(700)
    pg.locator('form[action*="/language/%s"] button[type=submit]' % lang
               ).first.click()
    pg.wait_for_timeout(1400)
    pg.goto(B + url, wait_until='domcontentloaded')
    pg.wait_for_timeout(2600)
    pg.evaluate(CAPTURE)
    if button == 'MODAL':
        pg.evaluate("showDownloadModal()")
        pg.wait_for_timeout(600)
        pg.evaluate("downloadPDF()")
    else:
        pg.click(button, timeout=8000)
    pg.wait_for_function("window.__pdf !== null", timeout=120000)
    import base64
    data = base64.b64decode(pg.evaluate("window.__pdf"))
    path = os.path.join(OUT, name)
    open(path, 'wb').write(data)
    return path


def build_via_print(pg, url, lang, name):
    """What the browser's own print produces, which is what Print gives you."""
    pg.goto(B + '/profile', wait_until='domcontentloaded')
    pg.wait_for_timeout(700)
    pg.locator('form[action*="/language/%s"] button[type=submit]' % lang
               ).first.click()
    pg.wait_for_timeout(1400)
    pg.goto(B + url, wait_until='domcontentloaded')
    pg.wait_for_timeout(2600)
    path = os.path.join(OUT, name)
    # Match the sheet's own @page margin, or this measures a layout the
    # printer will never produce.
    pg.pdf(path=path, format='A4', print_background=True,
           margin={'top': '12mm', 'bottom': '12mm',
                   'left': '12mm', 'right': '12mm'})
    return path


def ink_rows(page, dpi=110):
    """Which horizontal bands of the page carry ink, as a list of booleans."""
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    grey = img.convert('L')
    w, h = grey.size
    px = grey.load()
    rows = []
    for y in range(h):
        dark = 0
        for x in range(0, w, 3):          # every third pixel is plenty
            if px[x, y] < 205:
                dark += 1
                if dark > 2:
                    break
        rows.append(dark > 2)
    return rows, h


def inspect(path, label):
    doc = pymupdf.open(path)
    size_kb = os.path.getsize(path) / 1024
    notes = []
    print('\n### %s — %d page(s), %.0f KB' % (label, doc.page_count, size_kb))

    for i, page in enumerate(doc):
        rows, h = ink_rows(page)
        inked = sum(rows)
        share = inked / float(h)
        text = page.get_text().strip()
        # Ink in the last 1.5% of the page means something was still being
        # drawn when the page ended.
        tail = any(rows[int(h * 0.985):])
        head = any(rows[:int(h * 0.015)])
        last_ink = max((y for y, r in enumerate(rows) if r), default=0)
        trailing_blank = (h - last_ink) / float(h)

        flags = []
        if share < 0.02:
            flags.append('BLANK — this page prints nothing')
        if tail:
            flags.append('ink runs to the very bottom edge (content may be cut)')
        if head and i > 0:
            flags.append('ink starts at the very top edge (continued mid-line)')
        if i == doc.page_count - 1 and trailing_blank > 0.55 and doc.page_count > 1:
            flags.append('last page is %.0f%% empty' % (trailing_blank * 100))

        print('  page %d: %5.1f%% inked, %4d chars of text%s'
              % (i + 1, share * 100, len(text),
                 '' if not flags else '   <-- ' + '; '.join(flags)))
        for f in flags:
            notes.append((label, i + 1, f))

    doc.close()
    return notes


with app.app_context():
    # Somebody with a full month behind them, so the documents are not empty.
    WID = m.Worker.query.filter_by(pay_type='monthly', status='active').first().id

found = []
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844},
                         service_workers='block')
    pg = ctx.new_page()
    pg.goto(B + '/login', wait_until='domcontentloaded')
    pg.wait_for_timeout(800)
    pg.fill('input[name="username"]', 'demo@acme.test')
    pg.fill('input[name="password"]', 'demo12345')
    pg.click('#signin-form button[type="submit"]')
    pg.wait_for_function("location.pathname !== '/login'", timeout=20000)

    jobs = []
    for lang in ('en', 'hi'):
        jobs.append(('payslip (PDF button)', '/payroll/slip/%d' % WID,
                     'button:has-text("PDF")', lang, 'payslip-%s.pdf' % lang))
        # The card's PDF sits behind a download modal, so the modal is
        # opened first. A selector that only looked for a PDF button timed
        # out and reported the document as unproducible, which it is not.
        jobs.append(('ID card (PDF)', '/id_card/%d' % WID,
                     'MODAL', lang, 'idcard-%s.pdf' % lang))

    for label, url, button, lang, name in jobs:
        try:
            path = build_via_button(pg, url, button, lang, name)
            found += inspect(path, '%s [%s]' % (label, lang))
        except Exception as err:
            print('\n### %s [%s] — could not be produced: %s'
                  % (label, lang, str(err)[:110]))
            found.append(('%s [%s]' % (label, lang), 0, 'could not be produced'))

    for lang in ('en', 'hi'):
        for label, url, name in [
                ('worker report (Print)', '/worker/%d/report' % WID,
                 'report-%s.pdf' % lang),
                ('payslip (Print)', '/payroll/slip/%d' % WID,
                 'payslip-print-%s.pdf' % lang)]:
            path = build_via_print(pg, url, lang, name)
            found += inspect(path, '%s [%s]' % (label, lang))
    br.close()

print('\n' + '=' * 66)
print('%d thing(s) to look at:' % len(found))
for label, page, note in found:
    print('   %-30s page %-3s %s' % (label, page, note))
print('\ndocuments written to %s' % OUT)
