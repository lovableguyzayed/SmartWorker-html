"""Builds SmartWorker_Design_Review.pdf from the audit's screenshots.

    python docs/audit/review/build.py

Reads screens.json (every screen of the running app, made by the crawler)
and the before / preview / built images in ../mockups, writes
design_review.html beside this file, then prints it to A4 PDF with the
pre-installed Chromium.
"""
import html
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M = '../mockups/'

NAMES = {
    '/': 'Welcome', '/login': 'Sign in', '/register': 'Create account',
    '/forgot-password': 'Forgot password', '/dashboard': 'Home',
    '/workers': 'Workers', '/attendance': 'Attendance', '/payroll': 'Payroll',
    '/payroll/preview': 'Payroll preview', '/transactions': 'Transactions',
    '/closures': 'Closure days', '/assignments': 'Assignments',
    '/profile': 'Profile', '/settings': 'Settings', '/scan': 'Scan QR',
    '/notifications': 'Notifications', '/add_worker': 'Add worker',
    '/dues': 'Wages owed', '/worker/1': 'Worker profile',
    '/worker_attendance/1': 'Worker calendar', '/worker/1/report': 'Worker report',
    '/payroll/slip/1': 'Payslip', '/worker/1/account': 'Worker account',
    '/edit_worker/1': 'Edit worker', '/id_card/1': 'ID card',
    '/worker/7/login/powers': 'Supervisor powers', '/me': 'Worker home',
    '/me/team': 'My team', '/me/payslip': 'My payslip', '/worker/7/account': 'My account',
}
WHO = {'public': 'Anyone', 'admin': 'Owner / admin', 'sup': 'Supervisor (mukadam)'}


def fig(src, cap, tag=None):
    t = {'before': '<span class="tag before">Before</span>',
         'preview': '<span class="tag preview">Approved preview</span>',
         'built': '<span class="tag built">Built</span>',
         'suggest': '<span class="tag suggest">Suggested</span>'}.get(tag, '')
    return ('<figure><img src="%s"><figcaption>%s%s</figcaption></figure>'
            % (src, t, html.escape(cap)))


def row(*figs, cls='three'):
    return '<div class="row %s">%s</div>' % (cls, ''.join(figs))


def page(title, intro, body, cls=''):
    return ('<section class="page %s"><h2>%s</h2>%s%s</section>'
            % (cls, title, ('<p class="intro">%s</p>' % intro) if intro else '', body))


def build():
    screens = json.load(open(os.path.join(HERE, 'screens.json')))
    parts = []

    # ---- cover -----------------------------------------------------------
    parts.append('''
<section class="page cover">
  <div class="brand"><span class="mark">SW</span>SmartWorker</div>
  <h1>Design review</h1>
  <p class="sub">The app as built, in the approved design, and the corrections still suggested</p>
  <div class="meta">10 November 2026 · branch <code>claude/keen-curie-wr54kr</code> · not yet live</div>
  <div class="summary">
    <div><b>2</b><span>batches approved and built<br>(sign in · tabs, attendance, dates)</span></div>
    <div><b>32</b><span>screens checked<br>at phone size</span></div>
    <div><b>5</b><span>corrections suggested<br>(batch 3, for your OK)</span></div>
    <div><b>42/42</b><span>automatic test scripts<br>passing</span></div>
  </div>
  <h3>How to read this</h3>
  <ul class="legend">
    <li><span class="tag before">Before</span> the app as it was when the audit began</li>
    <li><span class="tag preview">Approved preview</span> the mockup you said OK to</li>
    <li><span class="tag built">Built</span> a screenshot of the real app now, on this branch</li>
    <li><span class="tag suggest">Suggested</span> a correction I recommend, not built yet</li>
  </ul>
  <h3>Design rules used everywhere</h3>
  <ul>
    <li>Your brand is kept: navy <span class="sw" style="background:#001F3F"></span> #001F3F, blue <span class="sw" style="background:#007BFF"></span> #007BFF, the Inter font, the same icons.</li>
    <li>Every button at least 44–48 px, the size of a thumb; one main action per screen.</li>
    <li>Works at the phone's largest text size, on a small 320 px phone, and on tablets.</li>
    <li>Hindi on every screen; dates day-first (Tue, 10 Nov 2026); money in lakh grouping (₹1,25,000).</li>
    <li>Plain words: say what went wrong and what to do next ("3 tries left", not "Invalid").</li>
  </ul>
</section>''')

    # ---- batch 1 -----------------------------------------------------------
    b1 = ''.join([
        row(fig(M + 'B1-AUTH_login_before.png', 'Sign in before: two forms, OTP that never arrived', 'before'),
            fig(M + 'B1-AUTH_login_after.png', 'One way in: the mobile number', 'preview'),
            fig(M + 'B1-AUTH_login_built.png', 'With SMS connected', 'built')),
        row(fig(M + 'B1-AUTH_otp_after.png', '6 boxes, SMS autofill, 30 s resend', 'preview'),
            fig(M + 'B1-AUTH_otp_wrong_built.png', 'Wrong code says how many tries are left', 'built'),
            fig(M + 'B1-AUTH_newuser_built.png', 'First time only: a name', 'built')),
    ])
    parts.append(page('Batch 1 — Sign in and sign up', 'Approved and built. Until an SMS provider is connected, the live site shows the password version (next page); the OTP screens switch on by themselves once one is set.', b1))
    b1b = ''.join([
        row(fig(M + 'B1-AUTH_register_before.png', 'Sign-up before: 9 fields, email required', 'before'),
            fig(M + 'B1-AUTH_login_built_nosms.png', 'Today, no SMS: password first', 'built'),
            fig(M + 'B1-AUTH_register_built_nosms.png', 'Sign-up now: 5 fields, 2 optional', 'built')),
        row(fig(M + 'B1-AUTH_login_built_hindi.png', 'Hindi', 'built'),
            fig(M + 'B1-AUTH_login_built_bigfont.png', 'Largest text: nothing cut off', 'built'),
            fig(M + 'B1-AUTH_register_built_error.png', 'A mistake keeps what was typed', 'built')),
    ])
    parts.append(page('Batch 1 — as it works today', None, b1b))

    # ---- batch 2 -----------------------------------------------------------
    b2 = ''.join([
        row(fig(M + 'B2-NAV_attendance_before.png', 'Before: 6 tabs of 35 px, header fills the screen', 'before'),
            fig(M + 'B2-NAV_attendance_after.png', '5 tabs, one date row', 'preview'),
            fig(M + 'B2-NAV_attendance_built.png', 'As built', 'built')),
        row(fig(M + 'B2-NAV_attendance_before_bigfont.png', 'Largest text before: "H…", "Wo…", no worker', 'before'),
            fig(M + 'B2-NAV_attendance_built_bigfont.png', 'Largest text now: tabs readable, no sideways scroll', 'built'),
            fig(M + 'B2-NAV_attendance_built_hindi.png', 'Hindi: मंगल, 10 नवंबर 2026', 'built')),
    ])
    parts.append(page('Batch 2 — Tabs, attendance, dates', 'Approved and built. Profile left the tab bar for the round button at the top right of Home; Scan moved to the centre, where the thumb rests.', b2))

    # ---- every screen ------------------------------------------------------
    for i in range(0, len(screens), 8):
        chunk = screens[i:i + 8]
        figs = ''.join(fig(s['img'], '%s · %s' % (NAMES.get(s['path'], s['path']), WHO[s['who']]))
                       for s in chunk)
        parts.append(page('Every screen, as built%s' % (' (continued)' if i else ''),
                          'Real screenshots of this branch at 360 × 800, a common budget-phone size, with demo data.' if not i else None,
                          '<div class="row four">%s</div>' % figs, 'gallery'))

    # ---- suggested corrections --------------------------------------------
    sug = [
        ('S1 · Share a payslip on WhatsApp',
         'Payslips travel by WhatsApp, but there is no Share button today, and the ID card\'s Share does not work inside the Android app. Suggested: a bar at the foot of the payslip with <b>Share</b> first, then Save PDF and Print, and a short "Saved to …" note after saving. Needs the native file plugins (done this round) to share the real PDF.',
         row(fig('screens/admin_payroll_slip_1.jpg', 'Payslip today: Save and Print hide in the header', 'before'),
             fig(M + 'B3-SUG_payslip_share_after.png', 'Share leads, at thumb height', 'suggest'), cls='two')),
        ('S2 · Payslip readable at the largest text',
         'The payslip and ID card are laid out like an A4 sheet, so at the largest text they still scroll sideways (+72 px, +46 px). Suggested: on the phone, show the payslip as stacked rows (label left, amount right) with the month calendar compact below; keep the A4 layout for the PDF and printing.',
         row(fig(M + 'B3-SUG_payslip_after_bigfont.png', 'Stacked rows at the largest text', 'suggest'), cls='two')),
        ('S3 · Help, legal and account in Profile',
         'There is no help, no Privacy Policy or Terms (the sign-up links do nothing), and no way to delete an account. Google Play requires the policy link and account deletion. Suggested: three short groups at the foot of Profile. <b>Needs your details (D3)</b>: support WhatsApp number, policy text.',
         row(fig('screens/admin_profile.jpg', 'Profile today', 'before'),
             fig(M + 'B3-SUG_profile_help_after.png', 'Help · Legal · Account', 'suggest'), cls='two')),
        ('S4 · Delete my account',
         'Says plainly what is deleted now and what must be kept by law, then asks for a typed DELETE and the password, so it cannot happen by accident. A web page with the same form is also required by Play. <b>Needs from you</b>: how many years wage records are kept (the [__] below).',
         row(fig(M + 'B3-SUG_delete_account_after.png', 'Clear before it is final', 'suggest'), cls='two')),
        ('S5 · Attendance at the largest text: workers first',
         'At the largest text the first worker is still one scroll down, because the month calendar and day summary sit above the list. Suggested: when a day is open, put the workers still to mark first, with large P / A buttons, and fold the calendar below them.',
         row(fig(M + 'B2-NAV_attendance_built_bigfont.png', 'Now: calendar first', 'built'),
             fig(M + 'B3-SUG_attendance_workers_first_bigfont.png', 'Workers first', 'suggest'), cls='two')),
    ]
    for title, why, figs in sug:
        parts.append(page(title, why, figs, 'suggest-page'))

    # ---- decisions -----------------------------------------------------------
    parts.append('''
<section class="page">
  <h2>What I need from you</h2>
  <table>
    <tr><th>#</th><th>Decision</th><th>My recommendation</th></tr>
    <tr><td>OK</td><td>Batch 3 (S1–S5 above)</td><td>OK S1, S2, S5 now; S3 and S4 once D3 is answered</td></tr>
    <tr><td>D1</td><td>SMS provider for OTP</td><td>MSG91 or 2Factor with TRAI DLT; sign-up already works without it</td></tr>
    <tr><td>D2</td><td>The public repository held passwords and personal data</td><td>Make it private today, and change the live admin and supervisor passwords</td></tr>
    <tr><td>D3</td><td>Privacy Policy, Terms, deletion rules</td><td>Send business name, contact, grievance officer, years wage records are kept</td></tr>
    <tr><td>D4</td><td>Worker photos are in public storage</td><td>Make storage private (signed links)</td></tr>
    <tr><td>D7</td><td>Render free plan sleeps (slow first open)</td><td>Paid plan, about $7/month, if used daily</td></tr>
    <tr><td>D8</td><td>Play Store release</td><td>Create a release signing key and keep it safe forever</td></tr>
  </table>
  <h3>Please test on a real phone</h3>
  <p>Install the API 36 test APK (GitHub → Actions → latest <i>Build Android APK</i> run on this branch → Artifacts), open any payslip and tap <b>Save PDF</b>. That is the one big fix that could not be checked without a phone. The full list is in <code>docs/audit/MANUAL_TEST_CHECKLIST.md</code>.</p>
</section>''')

    css = '''
@font-face { font-family: Inter; src: url(../../../static/vendor/inter/inter-latin-var.woff2) format('woff2'); font-weight: 100 900; }
@page { size: A4; margin: 12mm 12mm 14mm; }
* { box-sizing: border-box; }
body { font-family: Inter, 'Noto Sans Devanagari', system-ui, sans-serif; color: #0f172a; margin: 0; font-size: 10.5pt; line-height: 1.45; }
.page { page-break-after: always; break-after: page; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 34pt; margin: 30mm 0 4mm; color: #001F3F; line-height: 1.1; }
h2 { font-size: 16pt; color: #001F3F; margin: 0 0 3mm; padding-bottom: 2mm; border-bottom: 2px solid #007BFF; }
h3 { font-size: 11.5pt; color: #001F3F; margin: 7mm 0 2mm; }
.intro { color: #334155; margin: 0 0 4mm; }
.cover .brand { display: flex; align-items: center; gap: 3mm; font-weight: 800; font-size: 14pt; color: #001F3F; }
.cover .mark { width: 11mm; height: 11mm; border-radius: 50%; background: linear-gradient(135deg, #001F3F, #007BFF); color: #fff; display: grid; place-items: center; font-size: 10pt; }
.cover .sub { font-size: 13pt; color: #334155; margin: 0; }
.cover .meta { color: #64748b; margin-top: 3mm; }
.summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin: 10mm 0 4mm; }
.summary div { border: 1px solid #e2e8f0; border-radius: 4mm; padding: 4mm; background: #f8fafc; }
.summary b { display: block; font-size: 20pt; color: #007BFF; }
.summary span { font-size: 8.5pt; color: #475569; }
.legend { list-style: none; padding: 0; } .legend li { margin: 1.5mm 0; }
.sw { display: inline-block; width: 3mm; height: 3mm; border-radius: 1mm; vertical-align: -0.3mm; }
code { font-size: 9pt; background: #f1f5f9; padding: 0.3mm 1.2mm; border-radius: 1mm; }
.row { display: grid; gap: 4mm; margin-bottom: 4mm; break-inside: avoid; }
.row.three { grid-template-columns: repeat(3, 1fr); }
.row.two { grid-template-columns: repeat(2, 60mm); justify-content: center; gap: 10mm; }
.row.four { grid-template-columns: repeat(4, 1fr); gap: 3mm 4mm; }
figure { margin: 0; break-inside: avoid; }
figure img { width: 100%; border-radius: 3mm; border: 1px solid #cbd5e1; display: block; max-height: 98mm; object-fit: cover; object-position: top; }
.gallery figure img { max-height: 86mm; }
.suggest-page figure img { max-height: 200mm; }
figcaption { font-size: 8pt; color: #475569; margin-top: 1.2mm; line-height: 1.3; }
.tag { display: inline-block; font-size: 7pt; font-weight: 700; padding: 0.3mm 1.6mm; border-radius: 3mm; margin-right: 1.2mm; vertical-align: 0.2mm; }
.tag.before { background: #fee2e2; color: #991b1b; } .tag.preview { background: #e0e7ff; color: #3730a3; }
.tag.built { background: #dcfce7; color: #166534; } .tag.suggest { background: #fef3c7; color: #92400e; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
th, td { text-align: left; padding: 2mm; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
th { background: #f1f5f9; color: #001F3F; }
'''
    doc = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>SmartWorker design review</title>'
           '<style>%s</style></head><body>%s</body></html>' % (css, ''.join(parts)))
    out = os.path.join(HERE, 'design_review.html')
    with open(out, 'w') as fh:
        fh.write(doc)
    return out


def to_pdf(src):
    pdf = os.path.join(HERE, 'SmartWorker_Design_Review.pdf')
    js = ('const {chromium}=require("playwright");(async()=>{const b=await chromium.launch();'
          'const p=await b.newPage();await p.goto("file://%s",{waitUntil:"networkidle"});'
          'await p.evaluate(()=>document.fonts.ready);'
          'await p.pdf({path:"%s",format:"A4",printBackground:true,'
          'displayHeaderFooter:true,headerTemplate:"<span></span>",'
          'footerTemplate:\'<div style="font-size:7pt;color:#94a3b8;width:100%%;text-align:center">SmartWorker design review · page <span class=pageNumber></span> of <span class=totalPages></span></div>\','
          'margin:{top:"12mm",bottom:"14mm",left:"12mm",right:"12mm"}});await b.close();})();'
          % (src, pdf))
    env = dict(os.environ)
    env.setdefault('NODE_PATH', subprocess.run(['npm', 'root', '-g'], capture_output=True,
                                               text=True).stdout.strip())
    subprocess.run(['node', '-e', js], check=True, env=env, cwd='/tmp')
    return pdf


if __name__ == '__main__':
    print(to_pdf(build()))
    sys.exit(0)
