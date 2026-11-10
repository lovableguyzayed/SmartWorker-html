"""The corrections made to the app's PDFs stay made.

Found by generating every document and looking at it (tools/ux/documents.py
writes them; docs/audit/review has the before and after):

  * the payslip said "Not Saved" - app jargon - on a document a worker keeps;
  * it printed the salary explanation twice;
  * every line of text in the payslip and ID card PDFs was drawn a few pixels
    low (html2canvas's measurement, spoiled by Tailwind's img rule), which
    put the ID card's text under its own pills and sliced the payslip's
    calendar key at a page break;
  * the ID card's company name ran under its corner badge;
  * Hindi dates printed cut-off months ("अग", "नव");
  * file names could collide between two workers with one name;
  * Print did nothing inside the Android app.

Signs in to the test fixture (tools/make_test_fixture.py).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app  # noqa: E402
import routes  # noqa: E402,F401
import models as m  # noqa: E402
import i18n  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False
failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-66s %s' % (label, repr(got)[:28]))
    else:
        failures.append(label)
        print('  FAIL %-66s got=%r want=%r' % (label, got, want))


def read(*parts):
    return open(os.path.join(ROOT, *parts)).read()


with app.app_context():
    worker = m.Worker.query.filter_by(pay_type='monthly').order_by(m.Worker.id).first()
    wid, code = worker.id, worker.worker_id
    has_record = m.PayrollRecord.query.filter_by(worker_id=wid).first() is not None

with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test', 'password': 'demo12345'})

    print('--- payslip ---')
    slip = c.get('/payroll/slip/%d' % wid).get_data(as_text=True)
    check('no "Not Saved" on a document a worker keeps', 'Not Saved' in slip, False)
    if not has_record:
        check('a month without payroll says it is a draft, in words',
              'slip-draft-note' in slip and 'may still change' in slip, True)
        check('and as a watermark', 'class="slip-watermark"' in slip, True)
    explanation = re.findall(r'Full monthly salary', slip)
    check('the salary explanation is printed once, not twice', len(explanation) <= 1, True)
    name = re.search(r'var PAYSLIP_PDF_NAME = "([^"]+)"', slip)
    check('the payslip file name carries the worker ID',
          bool(name and code in name.group(1)), True)
    check('the PDF has a title', 'pdf.setProperties(PAYSLIP_PDF_META)' in slip, True)

    print('--- ID card ---')
    card = c.get('/id_card/%d' % wid).get_data(as_text=True)
    check('the card file name carries the worker ID',
          "'ID_Card_' + " in card and code in card, True)
    check('the company name keeps clear of the corner badge', 'idc-head' in card, True)
    check('the pills centre their text for the capture', 'idc-pill' in card, True)
    check('Share uses the shared route (works inside the app)',
          'SmartWorkerSave.share(blob' in card and 'navigator.share({' not in card, True)

print('--- what the captures and the app depend on ---')
css = read('static', 'css', 'custom.css')
check('html2canvas measures text with an inline image again',
      'img[src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"]' in css, True)
check('that is the very image html2canvas uses',
      'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7' in read('static', 'vendor', 'html2canvas.min.js'), True)
from datetime import date  # noqa: E402
check('Hindi dates spell the month out',
      i18n.format_date(date(2026, 8, 7), '%d %b %Y', 'hi'), '07 अगस्त 2026')
app_js = read('static', 'js', 'app.js')
java = read('cordova-plugins', 'smartworker-remote-bridge', 'src', 'android', 'RemoteBridge.java')
check('inside the app, Print goes to Android\'s print service',
      "'RemoteBridge', 'print'" in app_js and 'createPrintDocumentAdapter' in java, True)

print()
if failures:
    print('FAILED %d: %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('all document checks passed')
