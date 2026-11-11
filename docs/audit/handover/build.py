"""Builds SmartWorker_Screens_Before_After.pdf: every screen of the app,
the original beside what is live now.

    python docs/audit/handover/build.py

screens/ holds the pictures (390px phone, top of each screen), taken from
the app before the audit (commit 8ae7a6d) and from main after pull request
24, on the same test data. pdfs/ holds every PDF the app makes.
"""
import html
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {
    '/': 'Welcome', '/login': 'Sign in', '/register': 'Create account',
    '/forgot-password': 'Forgot password', '/dashboard': 'Home',
    '/workers': 'Workers', '/attendance': 'Mark attendance', '/payroll': 'Payroll',
    '/payroll/preview': 'Payroll preview', '/transactions': 'Transactions',
    '/closures': 'Closure days', '/assignments': 'Assignments',
    '/profile': 'Profile', '/settings': 'Settings', '/scan': 'Scan QR',
    '/notifications': 'Notifications', '/add_worker': 'Add worker',
    '/dues': 'Wages owed', '/worker/1': 'Worker profile',
    '/worker_attendance/1': 'Worker month view', '/worker/1/report': 'Worker report',
    '/payroll/slip/1': 'Payslip', '/worker/1/account': 'Worker account',
    '/edit_worker/1': 'Edit worker', '/id_card/1': 'ID card',
    '/worker/7/login/powers': 'Supervisor powers', '/me': 'Worker home',
    '/me/team': 'My team', '/me/payslip': 'My payslip', '/worker/7/account': 'My account',
}
WHO = {'public': 'Before sign-in', 'admin': 'Owner / admin', 'sup': 'Supervisor (mukadam)'}
# What to look for. Screens not listed changed only in the shared parts:
# the five-tab bar, Indian dates, large-text fit and Hindi.
NOTES = {
    '/login': 'Mobile number first, one way in for new and old users, password as the other tab. OTP shows only when SMS is connected.',
    '/register': 'Five fields instead of nine; email optional; show-password eye instead of typing it twice.',
    '/dashboard': 'Five tabs with Scan in the centre (was six).',
    '/attendance': 'Shorter header with the date as one big button; marking and the worker list first; calendar moved below the list.',
    '/closures': 'New choice: Closed for Full day / Half day.',
    '/payroll/slip/1': 'Share (WhatsApp), PDF and Print in one bar fixed at the bottom of the phone (below this picture); DRAFT notice instead of "Not Saved"; explanation printed once.',
    '/id_card/1': 'Text sits inside its pills; company name clear of the badge; Share works in the app.',
    '/workers': 'Add Worker is a full-size button; fits at the largest text size.',
    '/profile': 'Sign out is a real button (cannot be triggered by another website).',
    '/settings': 'New sections: PF/ESI deductions, minimum wage, backup download.',
    '/worker/1': 'Salary section fully in Hindi when Hindi is chosen; Aadhaar shown as last 4 digits.',
    '/dues': 'New screen detail: wages owed, with export.',
}

meta = json.load(open(os.path.join(HERE, 'screens.json')))
parts = ['''
<section class="page cover">
  <div class="brand"><span class="mark">SW</span>SmartWorker</div>
  <h1>Every screen, before and after</h1>
  <p class="sub">All 30 screens of the app on a phone: the original on the left, what is live now on the right</p>
  <p class="meta">11 November 2026 · after pull requests 23 and 24 · same test data on both sides</p>
  <h3>How to read it</h3>
  <ul>
    <li><b>Before</b> is the app as it was when the audit started.</li>
    <li><b>After</b> is the app now, with the audit's fixes and the other session's features (PF/ESI, minimum wage, backup, SMS).</li>
    <li>Each picture shows the top of the screen at a 390px-wide phone. Long screens are cut at about two and a half phone-heights.</li>
    <li>The names and numbers are test data, not your real workers.</li>
  </ul>
  <h3>Changes you will see on almost every screen</h3>
  <ul>
    <li>Bottom bar: five tabs with Scan in the centre, instead of six.</li>
    <li>Dates the Indian way (Wed, 11 Nov 2026).</li>
    <li>Nothing runs off the side at small phones or the largest text size.</li>
  </ul>
  <h3>The PDFs</h3>
  <p>Every PDF the app makes is in the <code>pdfs</code> folder beside this file: payslip (Save PDF and Print), ID card and worker report, each in English and Hindi.</p>
</section>''']

n = 0
for who in ('public', 'admin', 'sup'):
    for key, pair in meta.items():
        w, path = key.split('|')
        if w != who:
            continue
        n += 1
        note = NOTES.get(path, 'Shared changes only: tab bar, dates, large-text fit, Hindi.')
        figs = ''
        for tag, label in (('before', 'Before'), ('after', 'After')):
            p = pair[tag]
            cut = ' <span class="cut">(top part of a long screen)</span>' if p['cut'] else ''
            figs += ('<figure><figcaption><span class="tag %s">%s</span>%s</figcaption>'
                     '<img src="screens/%s"></figure>' % (tag, label, cut, p['file']))
        parts.append('<section class="page"><h2><span class="num">%d</span>%s <small>%s · %s</small></h2>'
                     '<p class="intro">%s</p><div class="row">%s</div></section>'
                     % (n, html.escape(NAMES.get(path, path)), WHO[who], path, html.escape(note), figs))

css = '''
@font-face { font-family: Inter; src: url(../../../static/vendor/inter/inter-latin-var.woff2) format('woff2'); font-weight: 100 900; }
@page { size: A4; margin: 10mm; }
* { box-sizing: border-box; }
body { font-family: Inter, 'Noto Sans Devanagari', system-ui, sans-serif; color: #0f172a; margin: 0; font-size: 10pt; line-height: 1.45; }
.page { page-break-after: always; break-after: page; }
.page:last-child { page-break-after: auto; }
.brand { display: flex; align-items: center; gap: 3mm; font-weight: 800; font-size: 13pt; color: #001F3F; }
.mark { width: 10mm; height: 10mm; border-radius: 50%; background: linear-gradient(135deg, #001F3F, #007BFF); color: #fff; display: grid; place-items: center; font-size: 9pt; }
h1 { font-size: 24pt; color: #001F3F; margin: 5mm 0 1mm; }
h2 { font-size: 14pt; color: #001F3F; margin: 0 0 1.5mm; padding-bottom: 1.5mm; border-bottom: 2px solid #007BFF; }
h2 small { font-size: 8.5pt; font-weight: 500; color: #64748b; margin-left: 2mm; }
.num { display: inline-block; min-width: 7mm; margin-right: 2mm; color: #007BFF; }
h3 { font-size: 11.5pt; color: #001F3F; margin: 6mm 0 1.5mm; }
.sub { font-size: 12pt; color: #334155; margin: 0; } .meta { color: #64748b; }
.intro { color: #334155; margin: 0 0 3mm; font-size: 9.5pt; }
li { margin-bottom: 1.2mm; }
code { background: #f1f5f9; padding: 0.2mm 1mm; border-radius: 1mm; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; }
figure { margin: 0; text-align: center; }
figure img { max-width: 100%; max-height: 236mm; border: 1px solid #cbd5e1; border-radius: 2mm; }
figcaption { font-size: 8.5pt; color: #475569; margin-bottom: 1.5mm; text-align: left; }
.tag { display: inline-block; font-size: 8pt; font-weight: 700; padding: 0.4mm 2.2mm; border-radius: 3mm; margin-right: 1.5mm; }
.tag.before { background: #fee2e2; color: #991b1b; } .tag.after { background: #dcfce7; color: #166534; }
.cut { color: #94a3b8; }
'''
doc = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>SmartWorker screens, before and after</title>'
       '<style>%s</style></head><body>%s</body></html>' % (css, ''.join(parts)))
src = os.path.join(HERE, 'screens_before_after.html')
open(src, 'w').write(doc)
pdf = os.path.join(HERE, 'SmartWorker_Screens_Before_After.pdf')
js = ('const {chromium}=require("playwright");(async()=>{const b=await chromium.launch();'
      'const p=await b.newPage();await p.goto("file://%s",{waitUntil:"networkidle"});'
      'await p.evaluate(()=>document.fonts.ready);'
      'await p.pdf({path:"%s",format:"A4",printBackground:true,displayHeaderFooter:true,'
      'headerTemplate:"<span></span>",footerTemplate:\'<div style="font-size:7pt;color:#94a3b8;width:100%%;text-align:center">SmartWorker screens, before and after · page <span class=pageNumber></span> of <span class=totalPages></span></div>\','
      'margin:{top:"10mm",bottom:"13mm",left:"10mm",right:"10mm"}});await b.close();})();' % (src, pdf))
env = dict(os.environ)
env.setdefault('NODE_PATH', subprocess.run(['npm', 'root', '-g'], capture_output=True, text=True).stdout.strip())
subprocess.run(['node', '-e', js], check=True, env=env, cwd='/tmp')
print(pdf)
