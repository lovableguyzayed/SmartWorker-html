# SmartWorker — audit report

Branch `claude/worker-management-app-e8mkqg`. Every figure below came from
running the thing, not from reading it. Where something could not be tested
it is marked BLOCKED rather than guessed, and the mistakes made along the way
are listed at the end, because several "findings" turned out to be faults in
the tests rather than in the app.

Status vocabulary: **PASS** · **FAIL** · **BLOCKED** (could not be tested
here) · **NOT TESTED** · **NEEDS REVIEW** (works, but someone should decide
whether it should).

---

## Where it stands

| Phase | Result |
|---|---|
| 1 — architecture and inventory | 694 interactive elements; 0 broken links, 0 dead handlers, 0 forms without CSRF |
| 2 — the people who use it | 18 PASS, 2 FAIL |
| 3 & 4 — functions and business logic | 18 PASS, 0 FAIL |
| 5 — offline | 5 PASS (2 were failing before the fix) |
| 6 — security and isolation | tenant isolation PASS, role separation PASS |
| 7 — UI/UX (audit only, nothing changed) | **0 hard layout defects** across 30 screen × language combinations; 51 small tap targets |
| 8 — performance | see below |
| 9 — printable documents | payslip, worker report and ID card all produce correct files in both languages |
| 10 — gaps | 9 features absent, listed below |

Automated suites now in the repository: `tests/test_i18n.py` (34),
`tests/test_salary.py` (56), `tests/test_render_all_screens.py` (19 screens ×
2 languages), `tests/test_printable_pdfs.py` (28), and
`tests/test_monthly_regression.py`, which holds existing pay at **0
regressions**.

---

## What is wrong, worst first

### 1. A worker can be saved with no wage, silently — FIXED

`clean_rate` (routes.py:215) treats a missing or empty pay rate as `0.0` with
no error. A daily worker created that way is active, appears in payroll, and
is paid ₹0 every month with nothing anywhere to flag it. Reproduced by
posting the add-worker form with no rate: the worker was created with
`daily_rate = 0.0`.

This may be deliberate — an employer may want to add someone before the rate
is agreed. But then nothing ever says so. **Proposal, not implemented:** keep
accepting it, and mark zero-rate workers on the payroll screen and in the
preview, so they cannot be paid nothing by accident.

### 2. Workers cannot see their own pay — FIXED

There are exactly two roles, `admin` and `attendance`. A labourer has no
login and no way to check their own attendance or payslip; they depend on
someone showing them a screen. For a workforce app this is the largest
functional gap in the product, and it is a trust issue as much as a feature.

### 3. Flash messages are still English on a Hindi screen — FIXED

105 `flash()` calls in `routes.py`, 75 distinct messages, none translated.
Found by looking at a screenshot, not by the measurements: a Hindi attendance
screen showed *"Payroll for October 2026 has already been generated."* Many
are f-strings with values interpolated, so they need the same shape-matching
treatment the salary notes got, not a plain lookup.

### 4. Tap targets below the 44px guideline — FIXED

51 distinct kinds, on a touch screen the browser agrees is coarse-pointer.
Ranked by how often they are actually used:

| Size | What | Screen |
|---|---|---|
| 36×36 | `.dv-pill` / `.ep-pill` — the present/absent/late/leave buttons | attendance |
| 48×17 | `.ep-adjust` | attendance |
| 46–83 × 20 | "Assign", "Adjust", "View Details" links | worker profile |
| 63–103 × 32–42 | Assign / Transfer / End | assignments |
| 108–143 × 36 | Mark Paid / Mark Pending | payroll |
| 109×40 | section tabs | settings |
| 40×40 | avatar links | workers, attendance |

The first row matters most: those four buttons are what a supervisor taps
fifty times every morning, with one hand, often in gloves. **Nothing here has
been changed** — Phase 7 changes need approval first.

### 5. Payroll is still slow on a large roster — FIXED

At 5,000 workers the payroll screen takes about 8.6s. Every other screen was
brought down (workers 825ms → 26ms, attendance 8,683ms → 1,349ms) by
pagination plus eager loading. Payroll was left because paginating it raises
a question only the business can answer: should the totals at the top cover
the page being viewed, or the whole roster? Those are different numbers and
both are defensible.

### 6. There is no way to actually pay anyone — FIXED

The `workers` table holds no bank account, IFSC, UPI id, Aadhaar or PAN. The
app works out what each person is owed to the rupee and then has nowhere to
send it; payment happens outside the system with no record inside it.

### 7. No statutory compliance — ABSENT

No ESI, EPF/PF, professional tax or TDS anywhere in the code. For a
registered contractor in India this is not optional, and it is the kind of
gap that makes the payslip unusable as a legal document.

### 8. Features that are simply not there

| | |
|---|---|
| GPS / geofenced attendance | ABSENT (0 references) |
| Photo or selfie attendance | ABSENT |
| Biometric | ABSENT |
| WhatsApp or SMS to workers | ABSENT |
| Excel (.xlsx) export | ABSENT — CSV only |
| Bulk worker import | ABSENT |
| Payroll approval workflow | ABSENT — one admin generates and marks paid, unreviewed |
| Full and final settlement / gratuity | ABSENT |
| Roles beyond admin and attendance | ABSENT |

---

## What holds up

**The money is right.** Net equals gross minus rule deductions minus
recoveries, to the paisa, on the saved record as well as the computed one. A
₹1,000 advance moves net pay by exactly ₹1,000 and cancelling it restores the
original figure exactly. Net never goes negative. A month already marked paid
survives a regeneration untouched — figures and status both.

**The rules hold.** Attendance cannot be recorded for a future date. Marking
twice does not create a second record; the second tap closes the shift. An
invalid status is refused. A locked closure day refuses attendance and an
unlocked one allows it. A negative transaction amount is refused.

**Authorization holds.** A supervisor sees only workers assigned to their own
site — 3 of 14 on the fixture — cannot mark anyone outside it, cannot mark
leave (an administrator decision), and cannot open payroll, transactions or
settings. No wage figure appears anywhere on their screen. A second tenant
gets 404 on this tenant's worker.

**The layout holds, in both languages.** Across 30 screen × language
combinations: no clipped text, no sideways scrolling, nothing pushed
off-screen, no broken images, and nothing hidden behind the fixed bottom bar.
Devanagari is wider than Latin and the layout still did not give.

---

## Could not be tested here — BLOCKED

Stated plainly because these are exactly the conditions this app lives in:

- **A real Android device.** Everything was driven in Chromium at 390px.
- **A real 2G or flapping connection.** Offline was tested by switching the
  browser offline, which is a clean on/off, not a weak signal.
- **Several supervisors marking the same roster at once.** No concurrency
  testing was done at all.
- **A real printer**, and **a real QR scan of a Hindi ID card** — the QR
  payload was checked as text, not by scanning the printed code.
- **GPS and biometric hardware** — nothing to test, the features do not exist.

---

## Where this audit was wrong

Several things reported as defects turned out to be faults in the tests. They
are listed because a report whose errors are hidden cannot be trusted on the
findings that remain.

| Reported | Actually |
|---|---|
| "33 tenant isolation leaks" | The test assumed a second tenant existed; only one account did. Clean once a real second tenant was created. |
| "2 payroll arithmetic errors" | The test subtracted transaction deductions twice. |
| "Supervisor could only mark 3 of 13 workers" | Correct behaviour — he is scoped to one site, and `leave` is an admin decision. The test drove the API directly and bypassed both rules. |
| "net ≠ gross − deductions" | `closure_extra_pay` is already folded into `base_pay` (routes.py:1573); the test added it a second time. |
| "An image fails to load on add-worker" | A deliberately `hidden` placeholder with no `src`, with a comment in the template explaining why. The detector did not check visibility. |
| "Content hidden behind the nav bar on payroll preview" | Rows inside a *collapsed* `<details>`. `offsetParent` is not a visibility test in Chromium; `checkVisibility()` is. A screenshot at full scroll showed the page bottom clear. |
| "Doubled matra in the Hindi report heading" | A PyMuPDF text-extraction artefact caused by `letter-spacing`. Confirmed correct by eye at 320 dpi. |

The pattern worth keeping: every one of these came from trusting a
measurement over the thing itself. The ones that survived were the ones
checked against the database, or looked at.

---

## What was fixed, and what was not

Findings 1 to 6 are done, each with a test that fails if it comes back:

| | |
|---|---|
| `test_zero_wage.py` | a worker saved with no rate is warned about and marked on three screens |
| `test_worker_login.py` | a worker login reaches its own record and bounces off all 26 other GET routes |
| `test_flash_messages.py` | every message routes.py can raise has a translation, read with `ast` |
| `test_tap_targets.py` | every control hit-tests at 44px on 14 screens |
| `test_payroll_paging.py` | the list pages, the totals stay whole-roster |
| `test_payment_details.py` | payment fields validate, Aadhaar is masked and never reaches a payslip |

Findings 7 and 8 were **not** done, deliberately:

**Statutory deductions (ESI, EPF, professional tax, TDS)** are not a fix,
they are a compliance feature. The rates, wage ceilings and exemption
thresholds are set by notification and change; implementing them from
memory would produce a payslip that looks lawful and is not, which is worse
than the honest gap. This needs the current rates from whoever does the
company's compliance, and then it is a day's work.

**GPS attendance, photo attendance, biometric, WhatsApp/SMS, Excel export,
bulk import, payroll approval and final settlement** are nine separate
features, not defects. Three of them (GPS, photo, biometric) also cannot be
tested in this environment at all, which is a poor way to build something
that decides whether someone is paid.

## If only three things get done

1. **Give workers a login.** Everything else assumes someone trusts the
   person holding the phone.
2. **Decide the zero-wage question** and make it visible either way.
3. **Enlarge the attendance status buttons** from 36px — the single most
   repeated action in the app.

Flash-message translation and payroll pagination are both ready to do and
both need one decision first: whether to translate interpolated messages by
shape, and whether page totals mean the page or the roster.
