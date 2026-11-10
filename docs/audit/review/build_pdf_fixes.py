"""Builds SmartWorker_PDF_Corrections.pdf: every PDF the app makes, before
and after the corrections, page by page.

    python docs/audit/review/build_pdf_fixes.py

Page images come from pdfimg/ (rendered from tools/ux/out/documents before
and after the fixes); the corrected PDFs themselves are in pdfs/.
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
I = 'pdfimg/'


def fig(src, cap, tag):
    t = {'before': '<span class="tag before">Before</span>',
         'after': '<span class="tag after">After</span>',
         'same': '<span class="tag same">Unchanged</span>'}[tag]
    return '<figure><img src="%s"><figcaption>%s %s</figcaption></figure>' % (src, t, cap)


def section(title, intro, rows, cls=''):
    body = ''.join('<div class="row %s">%s</div>' % (r[0], ''.join(r[1:])) for r in rows)
    return '<section class="page %s"><h2>%s</h2><p class="intro">%s</p>%s</section>' % (cls, title, intro, body)


parts = ['''
<section class="page">
  <div class="brand"><span class="mark">SW</span>SmartWorker</div>
  <h1>PDF corrections</h1>
  <p class="sub">Every PDF the app makes — payslip, ID card, worker report — checked page by page, in English and Hindi, and corrected</p>
  <p class="meta">10 November 2026 · branch <code>claude/keen-curie-wr54kr</code> · not yet live</p>
  <h3>The three documents</h3>
  <table>
    <tr><th>PDF</th><th>How it is made</th><th>Result</th></tr>
    <tr><td><b>Payslip</b> — Save PDF / Share</td><td>A picture of the payslip, cut into A4 pages at safe places</td><td>3 pages, ~480 KB, ₹ and Hindi always right</td></tr>
    <tr><td><b>Payslip</b> — Print / Save as PDF</td><td>The page's own print layout</td><td>2 pages, ~230 KB, real searchable text</td></tr>
    <tr><td><b>ID card</b> — PDF / PNG / Share</td><td>A picture of the card on A4</td><td>1 page, ~200 KB</td></tr>
    <tr><td><b>Worker report</b> — Print / Save as PDF</td><td>The page's own print layout</td><td>2 pages, real searchable text</td></tr>
  </table>
  <h3>What was wrong, and what was done</h3>
  <table>
    <tr><th>#</th><th>Problem</th><th>Correction</th></tr>
    <tr><td>1</td><td><b>Print did nothing inside the Android app.</b> The worker report could not be printed or saved on the phone at all.</td><td>Print now opens Android's own print screen, which also has <b>Save as PDF</b> (real text). Needs a phone test.</td></tr>
    <tr><td>2</td><td>Every line of text in the picture PDFs was drawn a few pixels low: ID card text under its own labels, the payslip's colour key cut in half at a page break.</td><td>Fixed at the cause (html2canvas's text measurement); text now sits where it does on screen.</td></tr>
    <tr><td>3</td><td>Payslip said <b>"Not Saved"</b> — app jargon — on a document a worker keeps.</td><td><b>DRAFT</b> badge, a notice ("figures may still change") and a faint watermark until payroll is generated.</td></tr>
    <tr><td>4</td><td>Payslip printed the salary explanation <b>twice</b>.</td><td>Printed once.</td></tr>
    <tr><td>5</td><td>ID card: company name ran under the corner badge; footer lines ran together.</td><td>Laid out clear of each other.</td></tr>
    <tr><td>6</td><td>Hindi dates used cut-off months: "07 अग 2026", "10 नव 2026".</td><td>Full months everywhere: "07 अगस्त 2026".</td></tr>
    <tr><td>7</td><td>Two workers with the same name overwrote each other's files.</td><td>Worker ID in every file name: <code>Payslip_USC001_Javed_Nov-2026.pdf</code>, <code>ID_Card_USC001_Javed.pdf</code>.</td></tr>
    <tr><td>8</td><td>PDFs had no title.</td><td>Title and author set (shown in file managers and PDF viewers).</td></tr>
    <tr><td>9</td><td>ID card Share did not work inside the app.</td><td>Same Share route as the payslip.</td></tr>
  </table>
  <p class="note">Kept on purpose: the picture payslip stays at 3 pages so its smallest text is 9 pt, the legibility floor (2 pages would mean 6.7 pt). For a compact, searchable payslip use Print → Save as PDF (page 6).</p>
</section>''']

parts.append(section('ID card', 'Before: labels drawn under their pills, the name under the badge, the footer run together. After: all in place, in both languages.', [
    ('two', fig(I + 'card_before_p1.jpg', 'English', 'before'), fig(I + 'card_after_p1.jpg', 'English', 'after')),
]))
parts.append(section('ID card — Hindi', 'Hindi months in full: "07 अगस्त 2026", "10 नवंबर 2026".', [
    ('two', fig(I + 'cardhi_before_p1.jpg', 'Hindi: "07 अग 2026"', 'before'), fig(I + 'cardhi_after_p1.jpg', 'Hindi: "07 अगस्त 2026"', 'after')),
]))
parts.append(section('Payslip — page 1', 'Before: "Not Saved" on the slip, and the colour key under the calendar cut by the page edge. After: a clear Draft notice and badge; the key whole.', [
    ('two', fig(I + 'slip_before_p1.jpg', 'Page 1', 'before'), fig(I + 'slip_after_p1.jpg', 'Page 1', 'after')),
]))
parts.append(section('Payslip — pages 2 and 3', 'After: a faint DRAFT watermark behind the figures until payroll is generated, and the explanation printed once (before, it appeared again under the net pay).', [
    ('four', fig(I + 'slip_before_p2.jpg', 'Page 2', 'before'), fig(I + 'slip_before_p3.jpg', 'Page 3: explanation twice', 'before'),
     fig(I + 'slip_after_p2.jpg', 'Page 2, watermark', 'after'), fig(I + 'slip_after_p3.jpg', 'Page 3, once', 'after')),
]))
parts.append(section('Print → Save as PDF', 'The compact, searchable versions. In a browser, Print offers Save as PDF; inside the Android app it now does too. The worker report was already correct and is unchanged.', [
    ('four', fig(I + 'slipprint_p1.jpg', 'Payslip p1', 'after'), fig(I + 'slipprint_p2.jpg', 'Payslip p2', 'after'),
     fig(I + 'report_p1.jpg', 'Worker report p1', 'same'), fig(I + 'report_p2.jpg', 'Worker report p2', 'same')),
]))

css = '''
@font-face { font-family: Inter; src: url(../../../static/vendor/inter/inter-latin-var.woff2) format('woff2'); font-weight: 100 900; }
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: Inter, 'Noto Sans Devanagari', system-ui, sans-serif; color: #0f172a; margin: 0; font-size: 9.5pt; line-height: 1.45; }
.page { page-break-after: always; break-after: page; }
.page:last-child { page-break-after: auto; }
.brand { display: flex; align-items: center; gap: 3mm; font-weight: 800; font-size: 13pt; color: #001F3F; }
.mark { width: 10mm; height: 10mm; border-radius: 50%; background: linear-gradient(135deg, #001F3F, #007BFF); color: #fff; display: grid; place-items: center; font-size: 9pt; }
h1 { font-size: 24pt; color: #001F3F; margin: 4mm 0 1mm; }
h2 { font-size: 15pt; color: #001F3F; margin: 0 0 2mm; padding-bottom: 2mm; border-bottom: 2px solid #007BFF; }
h3 { font-size: 11pt; color: #001F3F; margin: 4mm 0 1.5mm; }
.sub { font-size: 11.5pt; color: #334155; margin: 0; } .meta { color: #64748b; }
.intro { color: #334155; margin: 0 0 4mm; }
code { font-size: 8.5pt; background: #f1f5f9; padding: 0.2mm 1mm; border-radius: 1mm; }
table { width: 100%; border-collapse: collapse; font-size: 8.8pt; }
th, td { text-align: left; padding: 1.2mm 2mm; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
th { background: #f1f5f9; color: #001F3F; }
.note { background: #eff6ff; color: #1e3a8a; padding: 2.5mm 3mm; border-radius: 2mm; margin-top: 4mm; }
.row { display: grid; gap: 5mm; }
.row.two { grid-template-columns: 1fr 1fr; }
.row.four { grid-template-columns: repeat(4, 1fr); gap: 3mm; }
figure { margin: 0; }
figure img { width: 100%; border: 1px solid #cbd5e1; border-radius: 1.5mm; display: block; }
figcaption { font-size: 8pt; color: #475569; margin-top: 1.2mm; }
.tag { display: inline-block; font-size: 7pt; font-weight: 700; padding: 0.3mm 1.6mm; border-radius: 3mm; margin-right: 1mm; }
.tag.before { background: #fee2e2; color: #991b1b; } .tag.after { background: #dcfce7; color: #166534; } .tag.same { background: #e2e8f0; color: #334155; }
'''

doc = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>SmartWorker PDF corrections</title>'
       '<style>%s</style></head><body>%s</body></html>' % (css, ''.join(parts)))
src = os.path.join(HERE, 'pdf_corrections.html')
open(src, 'w').write(doc)
pdf = os.path.join(HERE, 'SmartWorker_PDF_Corrections.pdf')
js = ('const {chromium}=require("playwright");(async()=>{const b=await chromium.launch();'
      'const p=await b.newPage();await p.goto("file://%s",{waitUntil:"networkidle"});'
      'await p.evaluate(()=>document.fonts.ready);'
      'await p.pdf({path:"%s",format:"A4",printBackground:true,displayHeaderFooter:true,'
      'headerTemplate:"<span></span>",footerTemplate:\'<div style="font-size:7pt;color:#94a3b8;width:100%%;text-align:center">SmartWorker PDF corrections · page <span class=pageNumber></span> of <span class=totalPages></span></div>\','
      'margin:{top:"12mm",bottom:"14mm",left:"12mm",right:"12mm"}});await b.close();})();' % (src, pdf))
env = dict(os.environ)
env.setdefault('NODE_PATH', subprocess.run(['npm', 'root', '-g'], capture_output=True, text=True).stdout.strip())
subprocess.run(['node', '-e', js], check=True, env=env, cwd='/tmp')
print(pdf)
