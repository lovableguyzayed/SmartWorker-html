# Audit progress

Resume from here if the session resets. Full findings in
[APP_AUDIT_REPORT.md](APP_AUDIT_REPORT.md); previews in
[mockups/index.html](mockups/index.html).

## How to run things

```sh
pip install -r requirements.txt pytest pymupdf fonttools "playwright==1.63.0"
export DATABASE_URL=sqlite:////tmp/fixture.db UX_CHROME=/path/to/chrome
python tools/make_test_fixture.py          # demo / demo12345, imran / imran12345
for t in tests/test_*.py; do python "$t" || echo "FAILED $t"; done
python main.py                             # the app on :5000
node tools/audit/actions.js http://127.0.0.1:5000 actions.json   # button/link inventory
node docs/audit/mockups/src/render.js http://127.0.0.1:5000      # re-render previews
```

Baseline before any change: 36 of 40 test scripts passed. The 4 known
failures are listed in the report as TEST-02 and LAY-01.

## Phases

- [x] Phase 0: discovery and inventories
- [x] Phase 1: audit (developer, QA personas, UI/UX)
- [x] Phase 2: report written
- [x] Phase 3: fixes (everything not waiting on the owner)
- [x] Phase 4: verify and hand over (MANUAL_TEST_CHECKLIST.md, Play release list)

## Fixes

### Done
- [x] SEC-01 OTP no longer readable from the cookie (P0)
- [x] SEC-04 OTP attempt and send limits, on the server (P1)
- [x] SEC-03 Password guessing limit (P1)
- [x] AUTH-02 One rule for Indian mobile numbers; old rows still match (P1)
- [x] SEC-02 cookies.txt and zipFile.zip removed from the files; seed passwords out of the code (history: D2)
- [x] AUTH-08 Number pad and SMS autofill on OTP fields
- [x] DARK-01 `color-scheme: light only`
- [x] Worker login passwords made with `secrets`, not `random`
- [x] TEST-01 Tests runnable on a fresh checkout

- [x] LAY-01 Worker profile fits 320px (and every other screen)
- [x] AUTH-04 Logout as POST
- [x] REL-01 Shell to cordova-android 15 / API 36: CI build passes (portrait lock kept, REL-02)
- [x] NAT-01 / NAT-02 Native bridge for the live site (needs phone test)
- [x] PERF-02 500 ms delay removed
- [x] PERM-01 Camera asked only when scanning; notification prompt removed
- [x] TEST-02 Stale checks + fixture; suite green
- [x] Batch 1 sign in / sign up, built and screenshot-checked against the mockups
- [x] Phase 4: MANUAL_TEST_CHECKLIST.md with the Play release list

### Waiting for preview approval
- [x] Batch 2: 5 tabs, attendance header, Indian dates, large-text tiles: built and screenshot-checked
- [ ] Payslip and ID card at the largest text (print layouts, +72px / +46px): needs its own preview
- [ ] Batch 3: payslip share, delete account, policy pages (PDF-02, COMP-01/02); needs D3

### Waiting for the owner
- [ ] **D1** SMS provider (interim done: sign-up without OTP)
- [ ] **D2** Make repo private / rewrite history; **change live admin and supervisor passwords**
- [ ] **D3** Legal details for Privacy / Terms / deletion
- [ ] **D4** Private photo storage
- [ ] **D5** Database changes (OTP table, decimal money)
- [ ] **D6** Google sign-in
- [ ] **D7** Render paid plan
- [ ] **D8** Play release signing and account
- [ ] **NAT-01** Owner to test *Save PDF* on a payslip in the installed APK
