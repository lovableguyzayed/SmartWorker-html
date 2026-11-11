# SmartWorker — full app audit

**Date:** 10 November 2026 · **Branch:** `claude/keen-curie-wr54kr` · **Checklist:** [PROGRESS.md](PROGRESS.md)

Written for the owner, in plain language. Every finding names the file and
line it comes from and carries one of three tags:

- **Verified** — I ran it and saw it happen.
- **Code evidence** — I read it in the code but could not run it here.
- **Needs real-device test** — only a real phone can settle it.

Severity: **P0** blocker · **P1** critical · **P2** major · **P3** minor · **P4** polish.

---

## 1. Summary

### What the app is (worked out from the code)

| | |
|---|---|
| **Name** | SmartWorker |
| **What it does** | Attendance, wages and payroll for small Indian employers with daily-wage, monthly and contract labour — stone crushers, sites, workshops. Marks attendance (by tap or QR scan), works out pay to the paisa, records advances and wage payments (cash or UPI with UTR), and prints payslips, ID cards and worker reports. |
| **Who uses it** | 1) The owner/admin. 2) A *mukadam* (supervisor) who marks his own team. 3) Workers themselves, read-only: their own attendance, payslip and running account. |
| **Platforms** | A website (Flask, on Render's **free** plan) and an Android app. The app is a **thin shell** that opens the website inside the phone, not a separate native app. No iOS app. |
| **Languages** | English and Hindi, switchable on every screen. |
| **Sign-in** | Username/email + password (Supabase handles email accounts when configured). There is also a mobile-OTP screen, but **no SMS is ever sent** (see AUTH-01). **No Google sign-in.** |
| **Payments** | **No payment gateway.** Nothing is sold in the app. "Payments" means *recording* wages paid to workers in cash or by UPI. |
| **PDFs** | None bundled. Three are generated on the phone: payslip, worker report, ID card. |

### Release-readiness verdict

**Not ready for the Play Store, and not safe to keep live without the fixes on this branch.**

The everyday screens are in good shape. All 31 open without errors at phone
size, 645 buttons and links all lead somewhere, and earlier work made the
pay maths exact. The problems are in **sign-in**, **what the public repository
gives away**, and the **Android shell**:

### Top 10 issues

| # | ID | Problem | Status |
|---|---|---|---|
| 1 | SEC-01 | Anyone who knew a user's mobile number could sign in as them, admin included. The OTP was readable from the browser's own cookie. | **Fixed** |
| 2 | AUTH-01 | No SMS is ever sent. OTPs went only to the server log, so **nobody could sign up** on the live site (sign-up required OTP). | **Fixed for now**: sign-up works without OTP; real SMS still needs D1 |
| 3 | SEC-02 | The GitHub repository is **public** and held an old database with real-looking names, phones and password hashes, plus login cookies, plus the demo admin password (which equals a phone number). | **Partly fixed**: removed from the files; still in history |
| 4 | REL-01 | The app targeted Android 14 (API 34). Since 31 Aug 2026 Google Play accepts new apps and updates **only at API 36**. | **Fixed**: API 36 build passes in CI |
| 5 | SEC-03 | Unlimited password guessing: 40 wrong tries, then the right one still worked. | **Fixed** |
| 6 | NAT-01 | Inside the Android app, **Save PDF / Excel / CSV probably did nothing**, and Back skipped "press again to exit". The website never loaded Cordova's bridge. | **Fixed in code**; needs a real-phone test |
| 7 | PERF-01 | Render's free plan sleeps after ~15 min idle, so the first open of the day shows a spinner for up to a minute. | **Needs your decision** (cost) |
| 8 | COMP-01/02 | No Privacy Policy, no Terms (the two links on sign-up do nothing), no "Delete my account". Play requires the last two. | **Needs your decision** (legal text) |
| 9 | A11Y-01 | At the large text size many older users choose, 15 screens spill sideways and the bottom tabs shrink to "H…", "Wo…". | **Fixed** (batches 2 and 3): no screen runs off the side at 150% text or at 320px |
| 10 | AUTH-02 | A number typed as `+91 98765 43210` at sign-up was saved differently from `9876543210`, so OTP login later said "no account". Any 10–15 digits were accepted. | **Fixed** |

---

## 2. Inventories

### 2.1 Screens

Every screen was opened in a real browser at 360×800 (a common budget-phone
size), at 320×568 (small/old phones), and at 150% text (close to Android's
largest font setting). "Spill" means the page became wider than the phone
and scrolled sideways.

| Screen | Route | Who | Purpose | File | Status | 320px | 150% text |
|---|---|---|---|---|---|---|---|
| Splash / welcome | `/` | public | Intro, then Sign in | templates/splash.html | Working | ok | ok |
| Sign in | `/login` | public | Password or OTP sign-in | templates/login.html | Partly working: OTP has no SMS | ok | ok |
| Create account | `/register` | public | New business owner sign-up | templates/register.html | Was **broken in production** (OTP never arrived). **Fixed**: 5 fields, no OTP until SMS exists | ok | ok |
| Forgot password | `/forgot-password` | public | Email reset link (Supabase only) | templates/forgot_password.html | Partly working: email only | ok | ok |
| Reset password | `/reset-password` | public | Set new password from email link | templates/reset_password.html | Working (Supabase only) | – | – |
| Home / dashboard | `/dashboard` | admin | Today's numbers, quick actions | templates/dashboard.html | Working | ok | spills 30px |
| Workers | `/workers` | admin | List, search, filter | templates/workers.html | Working | ok | spills 77px |
| Worker profile | `/worker/<id>` | admin | One worker: details, pay, actions | templates/worker_profile.html | Working | **spills 16px** | **spills 143px** |
| Add / edit worker | `/add_worker`, `/edit_worker/<id>` | admin | Worker form | templates/edit_worker.html | Working | ok | ok |
| Worker calendar | `/worker_attendance/<id>` | admin | Month calendar for one worker | templates/worker_attendance.html | Working | ok | ok |
| Worker report | `/worker/<id>/report` | admin | Printable full report → PDF | templates/worker_report.html | Working | ok | spills 27px |
| ID card | `/id_card/<id>` | admin | ID card with QR → PNG/PDF/Share | templates/id_card.html | Working (Share: see PDF-02) | ok | spills 46px |
| Worker account | `/worker/<id>/account` | admin, worker | Running account: earned, paid, owed | templates/worker_account.html | Working | ok | ok |
| Worker login powers | `/worker/<id>/login/powers` | admin | Make a worker a supervisor | templates/worker_login_powers.html | Working | ok | ok |
| Attendance | `/attendance` | admin, attendance user | Mark the day for everyone | templates/attendance.html | Working | ok | **spills 115px** |
| Scan QR | `/scan` | admin, supervisor | Camera scan of ID cards | templates/scan.html | Working (camera: needs real device) | ok | ok |
| Payroll | `/payroll` | admin | Month's pay, mark paid, export | templates/payroll.html | Working | ok | spills 26px |
| Payroll preview | `/payroll/preview` | admin | Check before generating | templates/payroll_preview.html | Working | ok | ok |
| Payslip | `/payroll/slip/<id>`, `/me/payslip` | admin, worker | Payslip → PDF | templates/payroll_slip.html | Working | ok | spills 72–82px |
| Transactions | `/transactions` | admin | Advances, bonuses, payments | templates/transactions.html | Working | ok | spills 8px |
| Wages owed | `/dues` | admin | Who is owed what | templates/dues.html | Working | ok | spills 14px |
| Closure days | `/closures` | admin | Holidays / shutdowns | templates/closures.html | Working | ok | ok |
| Assignments | `/assignments` | admin | Who works at which site/project | templates/assignments.html | Working | ok | spills 9px |
| Settings | `/settings` | admin | Company, sites, departments, users, pay rules | templates/settings.html | Working | ok | ok |
| Notifications | `/notifications` | admin | Alerts list | templates/notifications.html | Working | ok | spills 6px |
| Profile | `/profile` | everyone | Own account, password, language, export | templates/profile.html | Working | ok | spills 82px |
| Worker home | `/me` | worker | Own attendance and pay | templates/worker_home.html | Working | ok | ok |
| My team | `/me/team` | supervisor | Mark own team | templates/supervisor_team.html | Working | ok | ok |
| One-time setup | `/__setup/<token>` | owner, once | First-run setup | templates/one_time_setup.html | Not crawled (token-gated) | – | – |

**Modals and sheets** (opened by buttons, not routes): attendance edit,
adjust times, bulk action prompts, transaction add, closure add, worker
modify/assign, site/project/department/task editors, attendance-user editor,
photo picker, delete confirmations. The existing test
`tests/test_forms_and_modals.py` drives these. One of its checks
(`adjust-modal`) fails because the check reads an older way of wiring
buttons. The button is wired through `data-act`
(templates/attendance.html:481) and only appears for already-marked rows.
**Code evidence**, P3, the test needs updating rather than the app.

### 2.2 Actions (buttons, links, forms)

Generated by `tools/audit/actions.js`, which opens every screen as the admin,
as the supervisor and logged out, and checks each visible control:

- **645 controls across 31 screens.**
- **0 links leading to an error page.** Every same-origin link was fetched.
- **0 buttons calling a function that does not exist.**
- **2 dead buttons:** "Terms of Service" and "Privacy Policy" on
  sign-up (templates/register.html:146–147) do nothing, because the pages do
  not exist. → COMP-01. **Verified.**

The full list (each control, its label, where it goes and the result) can
be regenerated any time:
`node tools/audit/actions.js http://127.0.0.1:5000 actions.json`.

### 2.3 PDFs

No PDF file is bundled, downloaded or stored anywhere. Three are
**generated on the phone** by photographing the screen (html2canvas) and
putting the image on an A4 page (jsPDF):

| PDF | Made from | File name | Status |
|---|---|---|---|
| Payslip | templates/payroll_slip.html:965–998 | `<Name>_Payslip_<Month>_<Year>.pdf` | Works in a browser (**Verified**, tests/test_printable_pdfs.py). In the Android app: see NAT-01. |
| Worker report | templates/worker_report.html (browser print) | browser's choice | Works; real text, Hindi correct (**Verified**) |
| ID card | templates/id_card.html:354–374 | `<card>.pdf` | Works in a browser (**Verified**). In the Android app: see NAT-01. |

Because payslip and ID card are pictures of the screen, ₹ and Devanagari
always look right (no font problem). The cost is that the text cannot be
selected or searched, and the files are larger than a text PDF.
→ PDF-01, P3.

### 2.4 Configuration and services (locations only, no values)

| What | Where |
|---|---|
| Server secrets | Render dashboard: `SESSION_SECRET` (generated), `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` (render.yaml:17–29). None are in the code. ✔ |
| Supabase Auth | supabase_auth.py, on when `SUPABASE_URL` + `SUPABASE_ANON_KEY` are set |
| Supabase Storage (photos, logo) | storage.py, bucket `smartworker-media`, **public** (storage.py:48–71) |
| Supabase row security | supabase/rls_policies.sql (tenant isolation on every table) |
| Android shell | config.xml, www/index.html. App id `com.smartworker.app`, minSdk 24, **targetSdk 34**, portrait-locked |
| APK build | .github/workflows/build-apk.yml. **Debug** build, published as a GitHub release; no release signing |
| Firebase / Google OAuth / SMS / payment keys | **None exist** |
| Environments | One live (Render) + local SQLite. No staging. |

### 2.5 What could and could not be run here

- **Ran:** the website, in a real Chromium browser at phone sizes; all 41
  test scripts (after rebuilding their missing test data, see TEST-01);
  security probes against a local copy.
- **Could not run:** the Android app itself (no emulator here), real SMS,
  a real camera, real slow networks, Xiaomi force-dark. Those findings are
  tagged **Needs real-device test**.
- **I did not touch the live site.** Every probe ran against a local copy.

---

## 3. Issues

### 3.1 Sign-in and accounts

| ID | Where | Problem | Who it hurts | Sev | Fix | Effort | Status |
|---|---|---|---|---|---|---|---|
| SEC-01 | routes.py:962–966 (before) | The OTP was stored as plain digits in Flask's session cookie, which is signed but **not encrypted**. Ask for an OTP for any number, decode your own cookie, sign in as that person. I signed into the admin dashboard this way in 3 requests. **Verified.** | Everyone | P0 | Cookie now holds only a keyed hash (authguard.py). Each OTP works once. | S | **Fixed**: tests/test_otp_security.py |
| SEC-04 | routes.py:980–1030 (before) | Unlimited wrong OTPs and unlimited OTP requests (OTP-bombing; SMS cost once SMS is live). Any counter kept in the cookie could be reset by replaying an older cookie. **Verified.** | Everyone | P1 | Server-side limits: 5 wrong OTPs/number/15 min, 3 sends/number/15 min, 30 s resend timer, per-IP caps. | S | **Fixed** |
| SEC-03 | routes.py:897–941 | Unlimited password guessing. **Verified:** 40 wrong, then right → signed in. | Everyone | P1 | 8 wrong per login / 30 per IP per 15 min, then "try again in N minutes" (Hindi too). | S | **Fixed** |
| AUTH-02 | routes.py:630–634 (before) | Numbers saved exactly as typed (10–15 digits). `+91 98765 43210` at sign-up, then `9876543210` at login → "No account found". Also accepted numbers that cannot be Indian mobiles. **Verified.** | Ramesh ji, shared phone | P1 | Every form becomes 10 digits starting 6–9; old rows saved with 91/0 still match. | S | **Fixed** |
| AUTH-01 | routes.py `_deliver_otp`, `sms_enabled` | **No SMS provider.** The OTP only goes to the server log, and sign-up refuses to continue without OTP, so **no new business can sign up** on the live site unless someone reads them the code from Render's logs. **Verified** (no SMS code anywhere). | Every new customer | P0 | Choose an SMS provider (with TRAI DLT registration), **or** make phone verification optional until then. | M | **Interim fix done**: OTP turns itself off without a provider; password sign-up needs no OTP. SMS provider: **D1** |
| AUTH-03 | templates/register.html:88; routes.py forgot_password | Email is **required** to sign up, and "Forgot password" works **only by email** (and only when Supabase is configured). | Ramesh ji (rarely uses email) | P1 | Email optional; reset by mobile OTP (needs D1). | M | **Email optional: done.** Reset by OTP comes with D1 |
| AUTH-04 | routes.py:1296 `/logout` | Logout is a plain link (GET), so any other website can sign the user out. | All | P3 | Make logout a POST. | S | **Fixed** |
| AUTH-05 | – | No Google sign-in. | Priya, Amit | P3 | Needs Google Cloud project, OAuth client and SHA-1 + SHA-256 fingerprints. For a business tool, mobile OTP matters more. | M | **Needs decision D6** |
| AUTH-06 | routes.py `_deliver_otp` | Until SMS exists, every OTP is written to the server log in plain text. | All | P2 | OTP is off on the live server until SMS exists, so no codes are logged. | S | **Fixed** |
| AUTH-07 | authguard.py | The new limits live in server memory: two Render workers ⇒ up to 2× the allowance, and a restart clears them. | All | P3 | A small `otp_attempts` table makes it exact (database change). | S | **Needs decision D5** |
| AUTH-08 | templates/login.html:143–170, register.html:98–112 | OTP boxes opened the full letter keyboard; no SMS autofill. | Ramesh ji | P3 | Number pad + `autocomplete="one-time-code"` (Android/iOS offer the code from the SMS). | S | **Fixed** |
| COMP-02 | – | No **Delete my account**, in the app or on the web. Google Play requires both for apps with accounts. | – | P1 | Delete screen (with clear notice of what is kept for wage records) + public web form. | M | **Needs decision D3** + mockup |
| AUTH-09 | templates/login.html | OTP screen has no resend countdown, no "change number", and two buttons (Send / Verify) side by side. | Ramesh ji | P2 | One field at a time, 30 s countdown, change-number link, tries left. | M | **Built** (batch 1, approved); switches on with D1 |

### 3.2 Repository and data exposure

| ID | Where | Problem | Sev | Fix | Status |
|---|---|---|---|---|---|
| SEC-02a | zipFile.zip (28 MB) | An old backup of the app inside the **public** repo, with a database of 4 user accounts (names, phones, emails, password hashes) and 7 workers (names, phones, addresses), plus 3 worker photos. **Verified** (counted rows only, printed no values). | P0 | Removed from the current files; `*.zip`, `*.db` now ignored. **Still in git history.** | Partly fixed; **D2** |
| SEC-02b | cookies.txt | Saved login cookies (`session`, `remember_token`) committed to the public repo. | P1 | Removed; ignored. | Partly fixed; **D2** |
| SEC-02c | tools/seed_uttaranchal.py:39–40 | The demo admin password was written in the script, and it is the admin's own phone number. The supervisor's was `imran12345`. | P0 | Passwords now come from env vars or are random. **If this script was ever run on the live site, change those passwords now.** | Fixed in code; **owner action** |
| SEC-05 | storage.py:48–71 | Worker photos and the logo are in a **public** storage bucket: anyone with the link sees the photo. | P2 | Private bucket + short-lived signed links. | **D4** |
| – | app.py:94–96 | Session cookie: HttpOnly, SameSite=Lax, Secure on Render. | – | – | ✔ Good |
| – | static/sw.js | Concern checked: does the offline cache show the last user's payroll after logout on a shared phone? **No.** **Verified**: pages are cached per login (`Vary: Cookie`). | – | – | ✔ Good |
| – | tests (earlier audit) | Another company's worker → 404; supervisor sees only own site. | – | – | ✔ Good (earlier, still passing) |

### 3.3 Payments (wage records)

There is **no payment gateway** and **nothing is sold in the app**, so Google
Play's billing rules (Play Billing / user-choice billing) **do not apply**.
Physical-world wages recorded by an employer are outside that policy. If you
ever sell subscriptions *inside* the Android app, that changes: tell me
first.

| ID | Where | Problem | Sev | Fix | Status |
|---|---|---|---|---|---|
| PAY-01 | models.py:200–650 (`db.Float` columns) | Money is stored in float columns. The pay engine and display convert to exact `Decimal` and round half-up (money.py, salary.py), and tests show **0 paisa drift**, so today this is a risk, not a bug. | P3 | Move to `Numeric(12,2)` (database migration). | **D5** |
| PAY-02 | – | Earlier audit: no ESI / EPF / PT / TDS. A payslip without them is not a statutory payslip. | P2 | Needs current rates from your accountant. | Earlier decision, still open |
| – | money.py | Indian digit grouping (₹1,25,000) everywhere. | – | – | ✔ Good |

### 3.4 PDFs

| ID | Where | Problem | Sev | Fix | Status |
|---|---|---|---|---|---|
| NAT-01 | static/js/filesave.js:21–23, 80–86; templates/base.html (no `cordova.js`) | Inside the APK, `window.cordova` never exists on the website's pages, so "Save PDF/Excel/CSV" falls back to a browser download, which Android's WebView ignores. The code's own comment (filesave.js:4–8) describes exactly this "spinner finishes, no file" bug. **Code evidence. Needs real-device test**: please try *Save PDF* on a payslip in your installed app. | P1 | The app now marks its user agent; the server then loads `cordova.js` from the APK, and a 15-line plugin (`cordova-plugins/smartworker-remote-bridge`) lets the live site, and only it, use the bridge. Cordova by default allows only its launch page (`PluginManager.shouldAllowBridgeAccess`). | **Fixed in code**, API 36 build passes; **needs your phone test** |
| PDF-02 | templates/id_card.html:380–405 | Share uses the web Share feature, which Android's WebView does not support; payslips have no Share at all. WhatsApp is how payslips actually travel. | P2 | Share bar on the payslip: browser share sheet, Android share sheet in the app (bridge plugin), WhatsApp text otherwise. | **Built** (batch 3, S1); needs a phone test |
| PDF-01 | templates/payroll_slip.html:965–998 | Payslip PDF is a photo of the screen: not searchable, bigger, slightly soft when zoomed. | P3 | Text PDF later; fine for now. | Backlog |
| – | – | No PDF is missing, broken or orphaned, because none are stored. | – | – | ✔ |

#### PDF corrections (after "correct every PDF")

Every PDF was generated in English and Hindi and read page by page. The
before/after is in [review/SmartWorker_PDF_Corrections.pdf](review/SmartWorker_PDF_Corrections.pdf),
and the corrected samples are in [review/pdfs/](review/pdfs/).

| ID | Problem | Status |
|---|---|---|
| PDF-03 | Print did nothing inside the Android app, so the worker report could not be printed or saved on a phone | **Fixed in code**: Android print service with Save as PDF; needs a phone test |
| PDF-04 | Text in the payslip and ID card PDFs was drawn a few pixels low (labels under their pills; calendar key cut at a page break) | **Fixed** (html2canvas measurement, custom.css) |
| PDF-05 | Payslip printed "Not Saved" | **Fixed**: DRAFT badge, notice and watermark |
| PDF-06 | Payslip printed the salary explanation twice | **Fixed** |
| PDF-07 | ID card: name under the corner badge, footer run together | **Fixed** |
| PDF-08 | Hindi dates with cut-off months ("अग") | **Fixed**: full months everywhere |
| PDF-09 | File names could collide between two workers with one name; no PDF title | **Fixed**: worker ID in names; title/author set |
| PDF-01 | Picture payslip is 3 pages and not searchable | **Kept**: 9 pt legibility floor; Print → Save as PDF gives 2 searchable pages |

### 3.5 Screen sizes, text size, dark mode

| ID | Where | Problem | Who | Sev | Fix | Status |
|---|---|---|---|---|---|---|
| A11Y-01 | 15 screens (table 2.1) | At 150% text the pages spill sideways (worst: worker profile 143px, attendance 115px). The attendance header fills the whole first screen with no worker visible. Android's WebView follows the phone's font size. **Verified** (simulated in Chromium); **needs real-device test**. | Ramesh ji | P1 | Let headers wrap, shrink fixed widths, cap header height. | **Fixed** (batch 3, S2): every screen fits; the payslip reads in stacked rows |
| NAV-01 | templates/base.html:311–360 | **6** bottom tabs; each only 35px wide (minimum is 44–48). At big text the labels become "H…", "Wo…", "P…". **Verified.** | Ramesh ji | P2 | 5 tabs: Home · Workers · Scan (centre) · Attendance · Payroll. Profile is the button in Home's header. | **Fixed** (batch 2) |
| LAY-01 | templates/worker_profile.html | Worker profile is 336px wide on a 320px phone. **Verified** (also in tests/test_narrow_screens.py). | old phones | P3 | Long words in label/value rows may wrap. Every screen now fits at 320px. | **Fixed** |
| DARK-01 | templates/base.html | No dark design and no "light only" declaration, so Xiaomi/Redmi force-dark could invert colours unreadably. | Priya | P3 | Declared `color-scheme: light only`. **Needs real-device test** on MIUI. | **Fixed** |
| DATE-01 | dashboard.html:120, attendance.html:327, supervisor_team.html:13 | Dates read "Tuesday, November 10, 2026" (US order). | everyone | P4 | "Tue, 10 Nov 2026" / "मंगल, 10 नवंबर 2026". | **Fixed** (batch 2) |
| REL-02 | config.xml:61 | Portrait lock. Android 16 ignores it on tablets/foldables once the app targets API 36. Layouts already reach 1024px (tests/test_wide_screens.py passes). | tablet users | P3 | Kept for phones; Android 16 already ignores it on large screens, and the layouts reach 1024px. Re-check on a tablet (checklist). | Kept, on purpose |

### 3.6 Native feel and speed

| ID | Where | Problem | Sev | Fix | Status |
|---|---|---|---|---|---|
| REL-01 | config.xml:43; build-apk.yml (cordova-android@12) | targetSdk 34. Play needs **API 36** for new apps and updates since 31 Aug 2026; existing apps need 35+ to stay visible to new users on new phones. cordova-android **15** targets 36. | P0 (for Play) | cordova-android 15.1, SDK 36, build-tools 36, Gradle 8.14.2. The old status-bar plugin is dropped (Cordova 15 does it itself). Test builds of a branch no longer replace the public APK link. | **Fixed**: CI build passes; edge-to-edge needs a phone check |
| PERF-01 | render.yaml:5 `plan: free` | Free Render services sleep when idle; the first visit wakes them (often 30–60 s). The shell waits up to 60 s (config.xml `LoadUrlTimeoutValue`). | P1 | Paid plan (about $7/month), or a keep-awake ping. | **D7** |
| PERF-02 | www/index.html:92 | An artificial 500 ms wait before loading. | P3 | Removed. | **Fixed** |
| PERM-01 | www/index.html:80–86 | Camera permission is asked the moment the app first opens, with no reason given. | P2 | Cordova 15.1 asks when the scanner first opens the camera, so the start-up request and its plugin are gone. The web app's notification-permission prompt (static/js/app.js, it never sends notifications) is gone too. | **Fixed**; needs a phone check |
| NAT-02 | static/js/app.js:805–850 | The custom Back handling (close dialog first, "press back again to exit") never runs in the APK for the same reason as NAT-01. Android falls back to "go back a page, or close the app". | P2 | Fixed together with NAT-01; Back is taken over after `deviceready`. | **Fixed in code**; needs your test |
| REL-03 | build-apk.yml | Only a **debug** APK is built. Play needs a signed release bundle (AAB), and the 16 KB page-size rule applies (this shell has no native .so files of its own; plugins need checking). | P1 (for Play) | Release signing in CI with a key you keep. | **D8** |
| – | static/js/app.js | Screen changes without a white flash, tab bar kept, scroll restored, no zoom/selection on UI. | – | ✔ Good (tests/test_native_shell.py passes) |

### 3.7 Compliance (Play policy, DPDP Act)

| ID | Problem | Sev | Status |
|---|---|---|---|
| COMP-01 | No Privacy Policy, no Terms. Sign-up asks you to agree to them, but the links are dead (register.html:146–147). Play requires a privacy policy link. | P1 | **D3**: I will not write legal text without you |
| COMP-02 | No account deletion (see 3.1). | P1 | **D3** |
| COMP-03 | DPDP gaps: no consent notice listing what is collected (worker names, phones, addresses, photos, bank/UPI, masked Aadhaar) and why; no way for a worker to ask for a correction or erasure; no named grievance contact; no breach plan. Workers' data is entered *by the employer*, so the notice is mostly the employer's duty, but the app should make it easy. | P2 | **D3** |
| COMP-04 | Play Data Safety form must list: name, phone, email, photos, financial info (wages, UPI/bank), approximate location? (none collected ✔), camera use (QR). | P2 | Owner action at release |

### 3.8 Broken, half-built, dead

- **Dead:** Terms / Privacy buttons (COMP-01). No TODO/FIXME, "coming soon",
  lorem ipsum or mock data anywhere in the app code. **Verified** by search.
- **Half-built:** mobile OTP (AUTH-01); Google sign-in absent.
- **Test debt:** TEST-01, see below.

| ID | Problem | Sev | Status |
|---|---|---|---|
| TEST-01 | The 40 test scripts expected a database that only ever existed on one machine, and a browser path that is not there on a fresh checkout. **No browser test could run on a fresh clone.** | P2 | **Fixed**: `tools/make_test_fixture.py`; browser path via `UX_CHROME` |
| TEST-02 | 3 pre-existing test failures: `test_bulk_actions` (seed has no active assignment to end), `test_forms_and_modals` (stale check, see 2.1), `test_printable_pdfs` (2 checks expect IDs from the old fixture: `CI002…`). | P3 | **Fixed**: fixture builder adds today's attendance and an assignment; two stale checks updated |

---

## 4. QA walk-through as real users

| Persona | Where they get stuck today | Issue IDs |
|---|---|---|
| **Ramesh ji, 52, kirana shop, Redmi 3 GB, Android 11, max font, Hindi** | Cannot sign up: OTP never arrives. If he types `+91…` the number is saved oddly. Email is mandatory. At max font the attendance screen shows only the header and the tabs read "H…", "Wo…". Forgot password = email only. | AUTH-01, AUTH-02 ✔, AUTH-03, A11Y-01, NAV-01 |
| **Priya, 21, Realme, Hinglish, Google, dark mode, WhatsApp** | No Google sign-in. Force-dark could invert colours (now declared light-only). Can't share a payslip to WhatsApp from the app. | AUTH-05, DARK-01 ✔, PDF-02 |
| **Amit, 34, OnePlus, impatient** | First open of the day: a long white spinner while Render wakes up. Save PDF in the APK may do nothing. | PERF-01, NAT-01 |
| **Shared family phone, dual SIM** | Logout leaves no other user's data behind (**Verified** ✔). Number on SIM 2: typing it any way now works ✔. Switching accounts = logout + login (no account switcher). | AUTH-02 ✔ |

**Timezone:** dates and "today" use IST throughout (timeutil.py). Attendance
for 12:00–5:30 AM IST lands on the right day (night-shift handling is
covered by the existing salary tests). ✔

**Words that scare:** sign-in messages were English-only on the Hindi
screen. All OTP and lock-out messages now have Hindi. Remaining jargon to
simplify in the mockups: "Authenticate", "Invalid credentials" (not used ✔),
"Payroll" (→ "तनख़्वाह/Salary").

**Tap counts:** mark one worker present = 1 tap ✔; mark everyone = 2 taps ✔;
payslip PDF = 4 taps (Payroll → worker → Payslip → Save) ✔; sign-up = 9
fields + OTP ✗ (aim: 3 fields).

---

## 5. Missing features

**Must-have (for Play / for trust):** SMS OTP that actually arrives (D1) ·
Privacy Policy + Terms pages (D3) · Delete account, in the app and on the
web (D3) · target API 36 (REL-01) · signed release build (D8) · Save/Share
PDF working in the APK (NAT-01).

**Should-have:** help / WhatsApp support link · reset password by mobile
OTP · 5-tab navigation and big-font layouts · statutory deductions
(ESI/EPF/PT) · crash reporting · private photo storage.

**Nice-to-have:** Google sign-in · text-based (searchable) payslip PDFs ·
account switcher for shared phones · rate-the-app prompt.

---

## 6. Needs your decision

| # | Question | My recommendation |
|---|---|---|
| **D1** | **SMS for OTP.** Choose a provider (MSG91, Fast2SMS, 2Factor, Twilio…; all need TRAI DLT sender ID + template, about ₹0.15–0.25 per SMS) **or** let people sign up without verifying the phone until then. | Short term: allow sign-up without OTP (email or phone + password) so customers aren't turned away. Then MSG91 or 2Factor with DLT. |
| **D2** | **Clean the public repo's history** (zipFile.zip, cookies.txt, seed password). This rewrites history and needs a force-push, which breaks other clones. Alternative: make the repository **private**. | Make it private now (one click in GitHub settings). Rewrite history afterwards if you want. **Either way, change the live admin and supervisor passwords.** |
| **D3** | **Privacy Policy, Terms, Delete-account rules.** I need: business legal name, contact email/phone, grievance officer name, and how long wage records must be kept after a worker leaves or an owner deletes their account. | I'll draft the screens; you or a lawyer supply the text. |
| **D4** | Make photo storage private (signed links). | Yes. Small change, but touches Supabase settings. |
| **D5** | Database changes: (a) a table for OTP attempt limits (exact limits); (b) money columns from float to exact decimal. | (a) yes, when SMS goes live. (b) later; no drift today. |
| **D6** | Add Google sign-in? Needs a Google Cloud project and the app's SHA-1 / SHA-256 fingerprints. | Not now. Mobile OTP first. |
| **D7** | Render paid plan (~$7/month) so the app opens instantly. | Yes, if you have real users daily. |
| **D8** | Play Store release: create a release signing key (you must keep it safe forever), Play developer account; a new personal account needs a closed test (12 testers × 14 days). | Decide once REL-01 is done. |

---

## 7. Changes made on this branch

| Commit | What |
|---|---|
| OTP/password protection | authguard.py; routes.py sign-in endpoints; Hindi messages in i18n.py; tests/test_otp_security.py (33 checks) |
| Indian mobile numbers | One rule for every form of a number (`authguard.indian_mobile`) |
| Repo exposure | Removed cookies.txt, zipFile.zip; seed passwords from env; .gitignore |
| Keyboard and autofill | Number pad + SMS code autofill on OTP; phone autofill on mobile fields |
| Force-dark | `color-scheme: light only` |
| Tests runnable anywhere | tools/make_test_fixture.py; tools/audit/actions.js |

### Round 2 (after "OK, do the remaining")

| Commit | What |
|---|---|
| Sign out only on a real button press | AUTH-04 |
| Let long emails and names wrap | LAY-01; worker profile at largest text 143px → 17px over |
| Test fixture + two stale checks | TEST-02; the whole suite passes on a fresh fixture |
| Android shell | NAT-01 bridge plugin, API 36, camera asked only when scanning, notification prompt removed, 500 ms delay removed |
| APK build with cordova-android 15 | REL-01; CI build passes; publishing only from `main` |
| New sign-in and sign-up (batch 1) | AUTH-01 interim, AUTH-03, AUTH-06, AUTH-09; OTP switches on by itself once an SMS provider is set (`SMS_DEV_LOG=1` tries it locally) |

Interpretation used: "Ok" was taken as approval of batch 1 and of the
recommended interim for D1 (sign-up without OTP until SMS exists). It is a
code-only switch and can be reversed. No other decision was assumed.

Before/after previews for the visual changes are in
[mockups/index.html](mockups/index.html), batch by batch. What still has
to be checked by hand is in [MANUAL_TEST_CHECKLIST.md](MANUAL_TEST_CHECKLIST.md).
