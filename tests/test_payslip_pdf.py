"""The payslip PDF, in both languages, checked on the real output.

This one is worth the cost of a browser. The Hindi payslip has several parts
that break silently and only show up in the finished file:

  * jsPDF's helvetica is Latin-1, so pdf.text() cannot write Devanagari at
    all — the running header and page footer are rasterised instead.
  * a transparent PNG for that chrome made jsPDF store a raw bitmap plus a
    soft mask and took the file from 226KB to 1115KB.
  * html2canvas crops to the element box, and Devanagari matras sit outside
    a tight box, so without slack the header came out sliced flat.

Always starts its own server on its own port rather than reusing one that
happens to be running. Flask caches compiled templates, so a dev server
started before an edit serves the old payslip — this test passed against the
very bug it is here to catch until it stopped borrowing that server.

Run it on its own:  python3 tests/test_payslip_pdf.py
"""
import base64
import os
import re
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EXE = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
HOST, PORT = '127.0.0.1', int(os.environ.get('PDF_TEST_PORT', 5099))
B = 'http://%s:%d' % (HOST, PORT)
DEVA = re.compile(r'[ऀ-ॿ]')
OUT = os.environ.get('PDF_OUT_DIR', '/tmp')
failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-54s %s' % (label, repr(got)[:28]))
    else:
        failures.append(label)
        print('  FAIL %-54s got=%r want=%r' % (label, got, want))


def listening():
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, PORT)) == 0


if listening():
    sys.exit('port %d is already in use; set PDF_TEST_PORT to a free port' % PORT)

print('starting a server on %s …' % B)
env = dict(os.environ, PORT=str(PORT), FLASK_RUN_PORT=str(PORT))
server = subprocess.Popen(
    [sys.executable, '-c',
     'import os,sys; sys.path.insert(0,%r);'
     'from app import app; import routes, bulk;'
     'app.run(host=%r, port=%d)' % (ROOT, HOST, PORT)],
    cwd=ROOT, env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(40):
    time.sleep(0.5)
    if listening():
        break
else:
    server.terminate()
    sys.exit('could not start a server on %s' % B)


def build_pdf(pg, lang, worker_id):
    """Drive the page the way a user does and keep the blob it produces."""
    pg.goto(B + '/login')
    pg.fill('input[name="username"]', 'demo@acme.test')
    pg.fill('input[name="password"]', 'demo12345')
    pg.click('#signin-form button[type="submit"]')
    pg.wait_for_function("location.pathname !== '/login'", timeout=20000)
    pg.goto(B + '/profile', wait_until='domcontentloaded')
    pg.wait_for_timeout(700)
    pg.locator('form[action*="/language/%s"] button[type=submit]' % lang
               ).first.click()
    pg.wait_for_timeout(1500)

    pg.goto(B + '/payroll/slip/%d' % worker_id, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    pg.evaluate("""() => {
        window.__pdf = null;
        SmartWorkerSave.blob = function (blob) {
            return new Promise((resolve) => {
                const r = new FileReader();
                r.onload = () => { window.__pdf = r.result.split(',')[1]; resolve('ok'); };
                r.readAsDataURL(blob);
            });
        };
    }""")
    pg.click('button:has-text("PDF")', timeout=5000)
    pg.wait_for_function("window.__pdf !== null", timeout=120000)
    return base64.b64decode(pg.evaluate("window.__pdf"))


try:
    from playwright.sync_api import sync_playwright
    import pymupdf

    WORKER = 3   # a monthly worker, so the salary-calculation block is present
    sizes = {}

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
        for lang in ('en', 'hi'):
            print('--- %s ---' % lang)
            ctx = br.new_context(viewport={'width': 390, 'height': 844},
                                 service_workers='block')
            pg = ctx.new_page()
            errors = []
            pg.on('pageerror', lambda e: errors.append(str(e)[:160]))

            slip_is_hindi = None
            data = build_pdf(pg, lang, WORKER)
            slip_is_hindi = bool(DEVA.search(pg.inner_text('body')))
            ctx.close()

            check('[%s] slip screen language' % lang, slip_is_hindi, lang == 'hi')
            check('[%s] no javascript error during export' % lang, errors, [])

            path = os.path.join(OUT, 'payslip_%s.pdf' % lang)
            with open(path, 'wb') as fh:
                fh.write(data)
            sizes[lang] = len(data)

            doc = pymupdf.open(path)
            text = ''.join(page.get_text() for page in doc)
            check('[%s] pdf has pages' % lang, doc.page_count > 0, True)
            check('[%s] no page is blank' % lang,
                  [i for i, pg_ in enumerate(doc)
                   if len(set(pg_.get_pixmap(dpi=40).samples[::97])) < 6], [])

            if lang == 'en':
                # English keeps the native-text chrome: sharper and smaller.
                check('[en] native chrome text present', 'Payslip' in text, True)
            else:
                # Devanagari through helvetica would come out as mojibake or
                # nothing; the chrome must have taken the raster path.
                check('[hi] no Latin-1 mojibake from native text',
                      bool(re.search(r'Payslip|Page \d+ of', text)), False)
                imgs = [doc.extract_image(i[0]) for pno in range(doc.page_count)
                        for i in doc[pno].get_images(full=True)]
                check('[hi] chrome is rasterised, so extra images are present',
                      len(imgs) > doc.page_count, True)
                check('[hi] no chrome image carries an alpha channel',
                      [im['ext'] for im in imgs if im.get('smask')], [])
            doc.close()
        br.close()

    # The transparent-PNG bug showed up here and nowhere else: the Hindi file
    # was five times the English one while looking identical.
    ratio = sizes['hi'] / float(sizes['en'])
    print('\n  sizes: en %.0f KB, hi %.0f KB (ratio %.2f)'
          % (sizes['en'] / 1024, sizes['hi'] / 1024, ratio))
    check('hindi pdf is not bloated against english', ratio < 1.5, True)

finally:
    server.terminate()
    server.wait(timeout=10)

print('\n%d failed' % len(failures))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
