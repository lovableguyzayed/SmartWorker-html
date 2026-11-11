# SmartWorker — full app audit, second time (11 November 2026)

Written for the owner, in plain language. This is a fresh audit of the app
**as it is now**, after the first audit's fixes and about 60 changes from
another work session were combined. The first audit is kept in
[APP_AUDIT_REPORT_ROUND1.md](APP_AUDIT_REPORT_ROUND1.md).

How to read the tags: **Verified** = I ran it and saw the result ·
**Code evidence** = read in the code, not run · **Needs phone** = can only
be confirmed on a real phone.

Branch: `claude/keen-curie-wr54kr`. Nothing here is live until a pull
request is merged.

---

## 1. Summary

### What the app is (checked against the code again)

| | |
|---|---|
| **What it does** | Attendance, wages and payroll for small Indian employers: mark attendance (tap or QR scan), work out pay, record advances and wage payments, print payslips, ID cards and worker reports. |
| **Who uses it** | Owner/admin · supervisor (mukadam) for his own team · workers, who can only see their own attendance, payslip and account. |
| **Built with** | Website: Flask + SQLAlchemy (Postgres on Render), English and Hindi. Android: a thin Cordova shell (cordova-android 15, target API 36, min API 24) that opens the website. No iOS app. |
| **Sign-in** | Mobile number + password, or mobile OTP **once an SMS provider is connected** (MSG91 or Twilio code is ready; no provider is connected yet). No Google sign-in. |
| **Payments** | No payment gateway. Nothing is sold in the app. "Payments" means recording wages paid in cash or UPI. So the Play billing rules and the whole "paisa kat gaya" list do not apply. |
| **PDFs** | None bundled. Payslip, ID card and worker report are made on the phone. |
| **New since the first audit** | SMS sending, PF/ESI deductions, minimum-wage floor, Aadhaar (only last 4 digits kept), a backup download, working offline, half-day closing (this round). |

### Verdict

**The app itself is in good shape. It is still not ready for the Play Store,
and the reasons are now almost all things only you can supply** (legal
text, SMS provider, signing key, passwords), not bugs.

What I ran this time, and what came back:

| Check | Result |
|---|---|
| Every button, link and form on 31 screens (636 controls) | **0 broken** — Verified |
| 96 links and 38 form addresses | **0 dead** — Verified |
| 21 screens × 8 screen sizes × 2 languages (336 loads): small phone, tall phone, 7" and 10" tablet, landscape, largest text | **1 problem found, fixed** (R2-03) — Verified |
| Another business trying to read or change business 1's workers, payslips, ID cards, backup | **All refused** — Verified |
| Supervisor and worker logins trying admin screens | **All refused** — Verified |
| Changing data without the security token (CSRF) | **Refused, nothing changed** — Verified |
| Password guessing | **Locked after 8 wrong tries** — Verified |
| "Sign in then get sent to another website" trick | **Refused** — Verified |
| All 8 printable documents, English and Hindi | **0 problems** (no blank pages, no cut lines) — Verified |
| Text contrast, 902 pieces of text | 10 slightly low (1.1%), none unreadable — Verified |
| Page weight | 21–36 KB a screen, payslip 195 KB; pages open in about 0.1 s on this machine — Verified |
| Automatic tests | **64 of 67 pass.** The other 3 fail the same way on the main version with the same test data (R2-10) |

### Top issues this round

| # | ID | Problem | Status |
|---|---|---|---|
| 1 | R2-01 | Opening Attendance from Home put the "Closure days" button on top of the title. Cause: each screen's private styling was never removed when you moved to the next screen, so one screen could restyle another. | **Fixed** at the cause |
| 2 | R2-02 | No way to close the office for half a day without cutting pay. | **Built** (your rules) |
| 3 | COMP-01/02 | Still no Privacy Policy, Terms or "Delete my account". Google Play requires them. | **Needs your decision D3** |
| 4 | SEC-02 | Old passwords and an old database are still in the repository's history. | **Needs your action D2** |
| 5 | AUTH-01 | OTP sign-in stays off until an SMS provider is connected. | **Needs your decision D1** |
| 6 | R2-08 | A special web address can wipe **all** data and rebuild the demo company. It only works while a setting called `SETUP_TOKEN` exists on the server. | **Needs your action**: check it is removed on Render |
| 7 | R2-03 | Workers screen ran 39px off the side at the largest text size. | **Fixed** |
| 8 | R2-04 | English left on the Hindi worker profile (salary section) and month view: 13 phrases. | **Fixed** |
| 9 | R2-05 | One money calculation could use yesterday's date between midnight and 5:30 AM. | **Fixed** |
| 10 | NAT-01 | Save PDF, Share and Print inside the installed Android app. | Built; **Needs phone** |

---

## 2. Inventories (re-counted)

- **Screens:** 31 (21 admin, 5 supervisor/worker, 4 public, 1 one-time setup). All open without script errors in English and Hindi — Verified (`tests/test_no_script_errors.py`).
- **Actions:** 636 visible controls, 29 named actions; none attached to nothing — Verified (`tools/audit/actions.js`, `tools/ux/controls.py`).
- **PDFs:** payslip (picture PDF, 3 pages), payslip (print, 2 pages), ID card (1 page), worker report (print, 2 pages); each in English and Hindi — Verified (`tools/ux/documents.py`).
- **Settings the server reads** (names only): `DATABASE_URL`, `SESSION_SECRET`, `ADMIN_DEFAULT_PASSWORD`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_STORAGE_BUCKET`, `SMS_PROVIDER`, `MSG91_AUTH_KEY`, `MSG91_SENDER`, `MSG91_TEMPLATE_ID`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `SMS_DEV_LOG`, `SUPPORT_WHATSAPP`, `SETUP_TOKEN`, `LEGACY_OWNER_EMAIL`. No secret values are in the code — Verified by search.
- **Could not be run here:** the installed Android app, real SMS, the live server, real phones.

---

## 3. Findings this round

Severity: P0 blocker · P1 critical · P2 major · P3 minor · P4 polish.

| ID | Where | Problem | Who it hits | Sev | Fix | Status |
|---|---|---|---|---|---|---|
| R2-01 | `static/js/app.js` (render), `templates/dashboard.html:10`, `static/css/custom.css:1044` | Screen changes swap the page without a reload, and each screen's own `<style>` was added and never removed. Home's table style `.att-row` landed on the Attendance header of the same name: title cut to a few letters, button on top of it. **Verified** by tapping Home → Attendance. | Everyone, on the most-used screen | P2 | Styles now leave with their screen; header class renamed too. Tests: `test_page_styles.py`, `test_attendance_tab.py`. | **Fixed** |
| R2-02 | `models.py` ClosureDay, `routes.py` pay summary | A closure was always a full day. Sending everyone home at lunch still cut monthly salary for absentees and paid daily workers the half-day rate. | Owner, all workers | P2 | "Closed for: Full day / Half day". Half day: attendance open; monthly salary not cut (absent or unmarked); daily-wage worker who came gets the full day. One new database field (approved). Test: `test_half_day_closure.py`. | **Built** |
| R2-03 | `templates/workers.html:39` | At the largest text size the department filter would not shrink; the screen scrolled sideways by 39px. **Verified** at 360px, 150% text. | Ramesh ji (large text) | P3 | Filter can shrink. | **Fixed** |
| R2-04 | `templates/worker_profile.html:192-334`, `worker_attendance.html:180` | 13 English phrases on Hindi screens ("Company policy", "day(s)", "Check-in"…). **Verified** with `tools/ux/hindi_gaps.py`. | Hindi users | P3 | Translated. | **Fixed** |
| R2-05 | `ledger.py:96` | Fallback date was the server's clock (UTC), which is yesterday until 5:30 AM in India. The callers already pass Indian time, so no wrong figure was seen. **Code evidence.** | Night-shift entries | P3 | Uses Indian time. | **Fixed** |
| R2-06 | `templates/worker_report.html:141` | "Save PDF" was 36px tall on touch screens (44px is the minimum for a thumb). | All | P4 | 44px. | **Fixed** |
| R2-07 | `templates/payroll_slip.html` | A code comment (written in the first audit) carried a person's name to every payslip page. Not shown on screen. | – | P4 | Reworded. | **Fixed** |
| R2-08 | `routes.py` `/__setup/<token>` | This address deletes **every** business's data and rebuilds the demo company. It is off unless `SETUP_TOKEN` is set on the server, needs the token, a typed confirmation and a POST. Safe by design, dangerous if the setting is left in place after first use. **Code evidence.** | Everyone, if misused | P1 (if left on) | Nothing to change in code. | **Your action**: confirm `SETUP_TOKEN` is not set on Render |
| R2-09 | `templates/dues.html:94` | On the Dues screen a worker's name is a link only 24px tall. The same card has a full-size "Open account" link beside it. | Large thumbs | P4 | Leave, or make the whole card tappable. | Open |
| R2-10 | `tests/test_departed_dues.py`, `test_dues_queries.py`, `test_whole_rupees.py` | These 3 tests fail on the main version too, with the same test data. They look tied to particular data, not to a fault in the app, but I have not proven that. | – | P3 | Investigate separately. | Open |
| R2-11 | `app.py` headers | Private pages are sent without "do not store" (`Cache-Control: no-store`). Pages are kept per login (`Vary: Cookie`) and logout was checked in round 1, so no leak was found. **Verified** header missing. | Shared phone | P4 | Add the header if you want belt and braces; it makes Back slightly slower. | Open (your call) |
| R2-12 | Contrast | 10 of 902 texts are a little under the standard: avatar initials on the blue header (2.7:1, large text), "Wages Paid" caption (4.3:1), "Company policy" tag (4.4:1). | Bright sunlight | P4 | Darken slightly. | Open |
| R2-13 | Text size | 137 pieces of text are under 12px in English, mostly the bottom tab labels (11px) and print-only text. | Older eyes | P4 | Already at the smallest that fits five tabs; revisit with S3. | Open |

### Checked and found good (no action)

- **One business cannot see another's data** — 14 read addresses and 6 write addresses tried from a second business: all refused. Verified.
- **Backup download** contains only your own business, leaves out password data, and keeps only the last 4 Aadhaar digits. Verified (download tried from a second business) + code evidence (`backup.py`).
- **Aadhaar** is stored as the last 4 digits only. Code evidence (`routes.py:309`).
- **Worker's own login** reaches only `/me`, their payslip and their account. Verified.
- **OTP after the merge:** code never sits in the browser; 5 wrong codes lock the number; a failed SMS says so. Verified (`test_otp.py`, `test_otp_security.py`).
- **Mobile numbers:** +91, 0, 0091, spaces all accepted. Verified.
- **Offline queue, keyboard, error pages, statutory deductions, minimum wage:** their own tests pass.
- **Android build:** passes on the merged code (CI run 25). The pieces added after that are website-only.

---

## 4. Still open from the first audit

| ID | What | Waiting on |
|---|---|---|
| AUTH-01 / D1 | Real SMS for OTP (MSG91 or Twilio + DLT registration; see `SMS_SETUP.md`) | You |
| SEC-02 / D2 | Make the repository private; change the live admin and supervisor passwords | You |
| COMP-01/02 / D3 | Privacy Policy, Terms, Delete account (screens S3, S4) | Your legal details |
| D4 | Private photo storage | Your OK |
| D5 | Money stored as exact decimals | Later |
| D6 | Google sign-in. Note: Google blocks its sign-in inside app web views, so in the Android app it needs extra native work. | Your decision |
| PERF-01 / D7 | Render free plan sleeps; first open of the day is slow | Your decision (cost) |
| D8 | Play release signing key, developer account, closed test (12 testers × 14 days) | You |
| NAT-01 | Test Save PDF, Share, Print in the installed app | You, on a phone |
| Small | "Absent" vs "Unmarked" counter wording on Attendance; a ½ button for marking a worker half day | Your answer |

---

## 5. What changed on the branch this round

1. Attendance header fixed; screens no longer restyle each other.
2. Half-day closing (one new database field, added automatically, old closures unchanged).
3. Workers screen fits at the largest text.
4. Hindi completed on the worker profile and month view.
5. Indian time in the ledger fallback; Save PDF tap size; comment reworded.
6. New tests: `test_page_styles.py`, `test_half_day_closure.py`; a clash check in `test_attendance_tab.py`.

## 6. What you need to do

1. **Check `SETUP_TOKEN` is not set on Render** (R2-08).
2. **Make the GitHub repository private and change the two passwords** (D2).
3. Decide D1 (SMS) and send the D3 legal details.
4. Test on a phone: payslip Share / PDF / Print, and the half-day closing.
5. Say if you want a pull request for this round's changes.
