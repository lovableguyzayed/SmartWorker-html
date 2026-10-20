# Salary Calculation Policies

How a fixed monthly salary becomes a payable amount. Applies to workers whose
pay type is **monthly**; daily, hourly and project workers are unaffected.

The rules live in `salary.py` as a pure, Decimal-based module. Nothing in it
touches the database or the request, which is why the whole policy matrix can
be tested without a server (`tests/test_salary.py`).

---

## Where a policy comes from

Three layers, most specific wins:

1. **Per-worker override** — a `salary_policies` row with a `worker_id`.
   Only the fields it actually sets take precedence, so one rule can be
   changed for one person without restating the rest.
2. **Company default** — the `salary_policies` row with `worker_id = NULL`.
3. **The worker's own record** — used only while no company policy has been
   saved. The engine seeds itself from `allowed_leaves_per_month`,
   `leave_deduction_per_day` and `monthly_working_days`, so turning this
   feature on changes nobody's pay until an employer edits a rule on purpose.

Every change is written to `salary_policy_audits` with the old value, the new
value and who made it.

---

## The settings

### 1. Monthly salary basis
What the salary is divided by to get a daily rate.

| Value | Meaning |
|---|---|
| `fixed` | A constant number of days, set by `basis_days` (default 30). What most site payrolls use. |
| `calendar` | The real length of the month — 28, 29, 30 or 31. February then produces a higher daily rate than March. |

### 2. Daily salary rounding
Applied to `salary ÷ basis`. The unrounded figure is kept and shown alongside
it, so ₹733.33 and ₹734 both appear on the report.

| Value | ₹22,000 ÷ 30 |
|---|---|
| `none` | ₹733.33 |
| `nearest` | ₹733 |
| `up` | ₹734 |
| `down` | ₹733 |

### 3. Mid-month joining
Only matters when the joining date falls inside the payroll month.

| Value | Method | Result |
|---|---|---|
| `calendar` | Brief's Method B | Pro-rate by eligible calendar days from the joining date, then apply deductions. |
| `attendance` | Brief's Method A | Pay only days actually attended since joining. No separate absence deduction — an unattended day is already unpaid, and charging it again would deduct it twice. |

**Days before the joining date are never paid and never deducted.** Attendance
dated before it is discarded in one place (`eligible_window` / `split_attendance`),
so no later rule can reintroduce it. The report counts those records separately
under "records before joining".

### 4. Paid monthly leave
- `paid_leave_enabled` — on or off.
- `monthly_leave_allowance` — days covered each month.
- `leave_carry_forward` — unused allowance accumulates.

The allowance covers **approved leave first, then absences**. An approved paid
leave therefore cannot also be charged as an unpaid absence.

### 5. Absence deduction
- `absence_deduction_enabled` — on or off. **Off by default**, which reproduces
  the behaviour the app had before this feature: absences are recorded and
  reported but cost nothing.
- `deduction_rate` — rupees per chargeable day. Blank means *derive it from the
  salary* (the rounded daily rate), which is what the specification asks for. It
  is populated rather than blank for workers configured before this engine
  existed, so their deductions keep the rate already on their record.

### 6. Salary calculation method

| Value | Formula |
|---|---|
| `salary_minus_deductions` | Full monthly salary − deductions |
| `rate_times_payable_days` | Rounded daily rate × basis days, then deductions |

### 7. Scope
Company-wide default, or a per-worker override. See *Where a policy comes from*.

---

## Worked example (the brief's)

| Input | Value |
|---|---|
| Monthly salary | ₹22,000 |
| Basis | Fixed, 30 days |
| Rounding | Round up |
| Joining date | 6 October |
| Paid leave allowance | 2 days |
| Absences | 4 |
| Absence deduction | Enabled |

```
daily rate        22000 / 30 = 733.33  ->  734   (round up)
eligible days     6 Oct to 31 Oct      =  26 of 31
gross             26 x 734             =  19,084
allowance         2 days cover 2 of the 4 absences
chargeable        4 - 2                =  2 days
deduction         2 x 734              =  1,468
net payable       19,084 - 1,468       =  17,616
```

For a worker employed the whole month the same policy gives
`22,000 − 1,468 = 20,532`, which is the figure in the brief.

---

## Previewing before you commit

`/payroll/preview?month=&year=` shows what generating payroll would produce,
without producing it. Each worker is set against whatever is already saved:

| State | Meaning |
|---|---|
| **New** | No saved record for this month yet. |
| **Changed** | The figure would move. Shows `saved -> new` and the difference. |
| **No change** | Recalculating would produce the same amount. |
| **Locked** | Already marked Paid. A generate skips it entirely. |

Each row carries the derived daily rate, eligible days, deducted days and the
sentences explaining the figure, so the effect of a policy change can be read
worker by worker before anything is written. The Generate button on this
screen posts to the same endpoint as the one on the payroll screen.

`/api/salary-preview/<worker_id>` does the same for a single worker and takes
a policy in the query string, so an unsaved policy can be judged too.

---

## Where the salary figures appear

| Place | What it carries |
|---|---|
| Worker profile | Daily rate, eligible days, deduction, net payable for this month, plus the explanation and the policy in force. |
| Payroll preview | Every worker's rate, eligible days and deducted days, against what is already saved. |
| Payslip (screen and PDF) | The full eighteen-field report and the explanation. |
| Worker report (screen and print/PDF) | The same table, for the current month, with the policy listed beneath it. |
| Payroll CSV export | Eighteen extra columns, from joining date through to net payable salary. |
| Full data export CSV | The ten policy columns actually in force for each worker. |

Both exports leave these columns **blank** for daily, hourly and project
workers rather than writing zeros: there is no derived daily rate for them,
and a zero would read as a real figure.

The payslip PDF is produced by rasterising the page, so its salary block is
part of the image rather than selectable text. The worker report is a print
document, so its PDF carries real text.

---

## What is frozen, and what is not

A payroll month marked **Paid** is history:

- Generating payroll **skips** records already marked paid.
- Those rows carry a JSON snapshot of the breakdown (`breakdown_json`) and of
  the policy that produced it (`policy_json`).
- The payroll screen and the payslip read the snapshot instead of
  recalculating.

So changing a rule never restates a month that has been settled. Re-opening a
record (marking it Pending) clears `finalized_at` and allows the next save to
recalculate it.

---

## Data model

| Table | Purpose |
|---|---|
| `salary_policies` | One row per scope. `worker_id NULL` = company default. Unique on (account_id, worker_id). |
| `salary_policy_audits` | Field-level history of policy changes. |
| `payroll_records.breakdown_json` | Frozen breakdown of a finalised month. |
| `payroll_records.policy_json` | The policy that produced it. |
| `payroll_records.finalized_at` | When it became history. |

All are tenant-scoped through the existing `account_id` mechanism, and the
columns are added by the in-place `SCHEMA_PATCHES` migration in `app.py`, so an
existing database upgrades without losing data.

---

## Money handling

Every amount is `Decimal`, converted from `str` so float noise never enters the
arithmetic — `22000/30` cannot be held exactly as a float, and a 0.004 error
repeated across a few hundred workers is a real discrepancy. Values become
floats only at the boundary where the rest of the app stores and renders them.

A deduction is always an exact multiple of the rate shown on the report; test
19 asserts this for all four rounding modes.

---

## Tests

```
python3 tests/test_salary.py              # 56 checks, all 12 brief scenarios
python3 tests/test_monthly_regression.py  # existing pay must not move
```

`test_salary.py` covers each required scenario plus: absences before the
joining date, absence deduction disabled, approved leave not double-charged,
net never negative, joining after the period, carry-forward, rounding
consistency, and that the written explanation always arrives at the figure
shown.

`test_monthly_regression.py` re-derives what the old monthly branch would have
paid and compares it against the engine for every monthly worker across five
months. It must report **0 regressions**. It reports separately the cases where
the figure *did* change — workers who joined mid-month or had not joined at
all, which the old code paid a full salary for.
