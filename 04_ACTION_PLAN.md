# Phase 4 — Action Plan
**SmartWorker Employee Management System**
**Audit Date:** June 07, 2026
**Auditor:** Replit Agent (Senior Architect Mode)

> This plan converts the 37 audit findings and 10 gaps into a prioritized, time-boxed implementation roadmap. Tasks are sequenced so each sprint builds on a stable foundation.

---

## Sprint 0 — Security Hardening (1–2 days) 🔴

*These must be done before sharing the app with any real user. They require zero new features.*

### S0-01: Add CSRF Protection
**Gap:** GAP-02 | **Findings:** 1.1  
**Steps:**
1. Add `flask-wtf` to `pyproject.toml`.
2. Set `WTF_CSRF_ENABLED = True` and `WTF_CSRF_TIME_LIMIT = 3600` in `app.py`.
3. Add `{{ csrf_token() }}` as a hidden field to every `<form method="POST">` across all 11 templates.
4. For AJAX JSON requests (OTP endpoints), inject `X-CSRFToken` header from `<meta name="csrf-token">`.
**Files:** `app.py`, `pyproject.toml`, all templates.

---

### S0-02: Remove OTP from HTTP Response
**Gap:** GAP-08 | **Finding:** 1.2  
**Steps (Option A — Disable OTP UI):**
1. In `login.html` and `register.html`, remove or comment out the OTP section.
2. Return `{'success': False, 'message': 'OTP login coming soon'}` from `/login/send-otp` and `/register/send-otp`.
3. Do NOT delete the routes — they may be called by bookmarked Cordova clients.
**OR Option B (if SMS budget exists):** Integrate Fast2SMS API (free tier), remove OTP from response, add env var `SMS_API_KEY`.
**Files:** `routes.py`, `templates/login.html`, `templates/register.html`.

---

### S0-03: Remove Hardcoded Session Secret Fallback
**Gap:** GAP-01 | **Finding:** 1.4  
**Steps:**
1. In `app.py`, change:
   ```python
   # Before
   app.secret_key = os.environ.get('SESSION_SECRET', 'smartworker-secret-key-2024')
   # After
   secret = os.environ.get('SESSION_SECRET')
   if not secret:
       raise RuntimeError("SESSION_SECRET environment variable is required.")
   app.secret_key = secret
   ```
2. Ensure `SESSION_SECRET` is set in Replit Secrets.
**Files:** `app.py`.

---

### S0-04: Randomize Default Admin Password
**Gap:** GAP-01 | **Finding:** 1.3  
**Steps:**
1. Replace hardcoded `admin123` seed with a random password printed to server logs on first boot.
2. Add `ADMIN_DEFAULT_PASSWORD` env variable override for CI/staging use.
```python
import secrets, string
default_pw = os.environ.get('ADMIN_DEFAULT_PASSWORD') or ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
print(f"[SmartWorker] Default admin password: {default_pw}")
admin = User(..., password_hash=generate_password_hash(default_pw))
```
**Files:** `app.py`.

---

### S0-05: Gate Debug Mode on Environment Variable
**Finding:** 1.9  
**Steps:**
1. In `main.py`: `debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'`
2. Remove `debug=True` hardcode.
**Files:** `main.py`.

---

## Sprint 1 — Architecture Foundation (3–5 days) 🟠

*Refactor the codebase into a maintainable shape. All future features will be built on this foundation.*

### S1-01: Decompose routes.py into Flask Blueprints
**Gap:** GAP-03 | **Finding:** 2.1  
**Target structure:**
```
routes/
├── __init__.py        (register all blueprints)
├── auth.py            (login, logout, register, OTP)
├── workers.py         (CRUD, search, ID generation)
├── attendance.py      (mark, bulk, worker view)
├── closures.py        (add, delete)
├── profile.py         (update, password change)
└── export.py          (JSON/CSV export)
```
**Steps:**
1. Create `routes/` directory.
2. Move each handler to the appropriate blueprint. Keep function names identical (Flask-Login `url_for` references are by endpoint name, not function name — verify all template `url_for()` calls still resolve).
3. Import and register all blueprints in `app.py` via `app.register_blueprint(...)`.
4. Delete `routes.py`.
**Files:** New `routes/` directory, `app.py`, `main.py`.

---

### S1-02: Extract Business Logic to Services Layer
**Gap:** GAP-03 | **Finding:** 2.2  
**Target structure:**
```
services/
├── payroll.py         (calculate_wage, generate_payroll_summary)
├── workers.py         (generate_worker_id, generate_qr_code)
└── attendance.py      (process_attendance, bulk_mark)
```
**Steps:**
1. Move `calculate_wage()` to `services/payroll.py`.
2. Move `generate_worker_id()` and `generate_qr_code()` to `services/workers.py`.
3. Move attendance processing logic from `mark_attendance` route to `services/attendance.py`.
4. Update blueprint route handlers to call service functions.
**Files:** New `services/` directory, blueprint files.

---

### S1-03: Migrate to Flask-Migrate (Alembic)
**Gap:** GAP-03 | **Finding:** 2.3  
**Steps:**
1. Add `flask-migrate` to `pyproject.toml`.
2. Initialize: `flask db init` → creates `migrations/` directory.
3. Generate baseline migration: `flask db migrate -m "initial schema"`.
4. Remove all inline `ALTER TABLE` blocks from `app.py`.
5. Add `flask db upgrade` to the startup sequence in `main.py`.
**Files:** `app.py`, `main.py`, new `migrations/` directory.

---

### S1-04: Add DB Indexes
**Finding:** 3.4  
**Steps:**
In `models.py`, add to `AttendanceRecord`:
```python
__table_args__ = (
    UniqueConstraint('worker_id', 'date', name='uq_worker_date'),
    Index('ix_att_date', 'date'),
    Index('ix_att_status', 'status'),
    Index('ix_att_worker_date', 'worker_id', 'date'),
)
```
Add to `Worker`:
```python
__table_args__ = (
    Index('ix_worker_dept', 'department'),
    Index('ix_worker_status', 'status'),
)
```
Generate migration after model changes.
**Files:** `models.py`.

---

### S1-05: Fix DB Queries Inside Templates
**Finding:** 2.5  
**Steps:**
1. In the `profile` route handler in `routes/profile.py`, add:
```python
total_workers = Worker.query.filter_by(status='active').count()
present_today = AttendanceRecord.query.filter_by(date=date.today(), status='present').count()
return render_template('profile.html', total_workers=total_workers, present_today=present_today, ...)
```
2. Remove the `{% set ... = Worker.query... %}` lines from `profile.html`.
**Files:** `routes/profile.py`, `templates/profile.html`.

---

### S1-06: Remove Unused Dependencies
**Finding:** 2.7  
**Steps:**
1. Remove `PyJWT`, `OAuthLib`, `Flask-Dance` from `pyproject.toml`.
2. Run `pip install .` to confirm no import errors.
**Files:** `pyproject.toml`.

---

## Sprint 2 — Data Integrity & Validation (2–3 days) 🟡

### S2-01: Add Server-Side Form Validation
**Gap:** GAP-09 | **Finding:** 5.3  
**Steps:**
1. Add `WTForms` form classes (or manual validation) for:
   - Worker create/edit: phone regex, required fields, numeric rate fields
   - Attendance: date not in future
   - Profile: email format, password length
2. Return validation errors as flash messages with field names.
**Files:** New `forms.py`, blueprint route handlers.

---

### S2-02: Fix Worker ID Race Condition
**Finding:** 2.6  
**Steps:**
1. In `services/workers.py`, wrap ID generation in a `try/except IntegrityError` retry loop:
```python
for attempt in range(5):
    worker_id = f'{prefix}{str(count + 1 + attempt).zfill(3)}'
    if not Worker.query.filter_by(worker_id=worker_id).first():
        return worker_id
raise ValueError("Could not generate unique worker ID. Contact admin.")
```
2. Show friendly error message on the add-worker form if all retries fail.
**Files:** `services/workers.py`, `routes/workers.py`.

---

### S2-03: Add 404 and 500 Error Handlers
**Gap:** GAP-09  
**Steps:**
1. In `app.py`, register error handlers:
```python
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500
```
2. Create minimal `templates/errors/404.html` and `templates/errors/500.html`.
**Files:** `app.py`, new error templates.

---

### S2-04: Prevent Future-Date Attendance
**Finding:** 5.2  
**Steps:**
1. In the `mark_attendance` route, add:
```python
from datetime import date
if attendance_date > date.today():
    flash("Cannot mark attendance for future dates.", "error")
    return redirect(url_for('attendance.attendance', date=date.today().isoformat()))
```
**Files:** `routes/attendance.py`.

---

## Sprint 3 — Core Feature Completion (3–5 days) 🟡

### S3-01: Implement Payroll Report
**Gap:** GAP-06 | **Finding:** 4.1  
**Steps:**
1. Add route `GET /payroll/<worker_id>?month=YYYY-MM` to `routes/workers.py` (or new `routes/payroll.py`).
2. In `services/payroll.py`, add `generate_monthly_summary(worker_id, year, month)`:
   - Fetch attendance records for that month.
   - Calculate: days present, days absent, days late, days leave.
   - Call `calculate_wage()` for each present/late day. Sum totals.
   - Apply leave deductions (monthly workers).
   - Return: `{present, absent, late, leave, gross_pay, deductions, net_pay}`.
3. Create `templates/payroll_report.html` — mobile-styled, printable.
4. Add "Mark as Paid" button that creates/updates a `PayrollRecord`.
5. Fix the "Payroll" button on `worker_profile.html` to link to this route.
**Files:** New `routes/payroll.py`, `services/payroll.py`, `templates/payroll_report.html`, `templates/worker_profile.html`.

---

### S3-02: Add CSV Export
**Gap:** GAP-10 | **Finding:** 5.4  
**Steps:**
1. In `routes/export.py`, add `GET /export_data/csv?from=&to=&department=`:
```python
import csv
import io
output = io.StringIO()
writer = csv.writer(output)
writer.writerow(['Worker ID', 'Name', 'Date', 'Status', 'Check-In', 'Check-Out', 'Wage'])
# ... write filtered records ...
return Response(output.getvalue(), mimetype='text/csv',
    headers={'Content-Disposition': 'attachment; filename=attendance.csv'})
```
2. Add date-range and department query parameters to JSON export too.
3. Add "Export CSV" button to profile page alongside "Export Data".
**Files:** `routes/export.py`, `templates/profile.html`.

---

### S3-03: Fix Bulk Attendance Modal HTML Bug + Add Missing Statuses
**Finding:** 4.2  
**Steps:**
1. In `attendance.html`, fix unclosed `</form>` tag in the absent bulk button section.
2. Add "Mark All Late" and "Mark All Leave" forms in the bulk modal.
**Files:** `templates/attendance.html`.

---

### S3-04: Add Role-Based Access Control
**Gap:** GAP-01  
**Steps:**
1. Create a `@admin_required` decorator:
```python
from functools import wraps
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated
```
2. Apply to: `add_worker`, `edit_worker`, `closures`, `delete_closure`, `register`.
3. Create `templates/errors/403.html`.
**Files:** New decorator in `routes/__init__.py`, blueprint files, new error template.

---

## Sprint 4 — Performance & UX Polish (2–3 days) 🟡

### S4-01: Move Images to File Storage
**Findings:** 1.7, 1.8, 3.2  
**Steps:**
1. Create `static/uploads/workers/` directory.
2. In `add_worker` and `edit_worker` routes: save uploaded files to disk, store relative path in DB (VARCHAR 256 is sufficient).
3. For QR codes: generate on-demand at `/id_card/<id>` — do not store in DB. Or store to disk and serve as a file.
4. Migrate existing base64 images: write a one-time migration script that decodes and saves to disk.
**Files:** `routes/workers.py`, `models.py`, migration script.

---

### S4-02: Move jsPDF/html2canvas to id_card Page Only
**Finding:** 3.3  
**Steps:**
1. In `base.html`, remove jsPDF and html2canvas CDN `<script>` tags.
2. In `id_card.html`, add a `{% block scripts %}` block with those two scripts.
**Files:** `templates/base.html`, `templates/id_card.html`.

---

### S4-03: Switch to Tailwind CLI
**Findings:** 3.5, 8.3  
**Steps:**
1. Create `tailwind.config.js` pointing to all template and static JS files.
2. Add build script: `npx tailwindcss -i static/css/input.css -o static/css/tailwind.css --minify`.
3. Replace `<script src="https://cdn.tailwindcss.com">` in `base.html` with `<link rel="stylesheet" href="/static/css/tailwind.css">`.
4. Add `tailwind.css` to the service worker precache list.
**Files:** New `tailwind.config.js`, `static/css/input.css`, `static/css/tailwind.css`, `templates/base.html`, `static/sw.js`.

---

### S4-04: Add Offline Queue Feedback UI
**Finding:** 4.4  
**Steps:**
1. In `offline-sync.js`, track queue count and expose it.
2. In `base.html`, update the offline indicator to show: "Offline — 3 actions pending sync."
3. On each replay success/failure, show a toast notification.
**Files:** `static/js/offline-sync.js`, `templates/base.html`.

---

### S4-05: Implement Client-Side Worker Search
**Finding:** 4.5  
**Steps:**
1. In `workers.html`, add a `data-search` attribute to each worker card: `data-search="{{ worker.full_name|lower }} {{ worker.worker_id|lower }} {{ worker.phone }}"`.
2. Add JS: filter cards on `input` event without page reload.
3. Keep the department dropdown as a GET filter (server-side is fine for department since it changes the data set).
**Files:** `templates/workers.html`.

---

## Sprint 5 — Testing Foundation (2–3 days) 🟠

### S5-01: Set Up pytest
**Gap:** GAP-04 | **Finding:** 6.1  
**Steps:**
1. Add `pytest`, `pytest-flask` to `pyproject.toml` dev dependencies.
2. Create `tests/conftest.py`:
```python
import pytest
from app import app, db

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
```
3. Create `tests/test_payroll.py` — unit tests for `calculate_wage()` across all 4 pay types + edge cases.
4. Create `tests/test_attendance.py` — test attendance toggle logic.
5. Create `tests/test_auth.py` — test login, logout, CSRF rejection.
**Files:** New `tests/` directory.

---

### S5-02: Fix Remaining UX Stubs
**Finding:** 4.3  
**Steps:**
1. "Forgot Password": Create `/forgot_password` route. Implement email-based reset (generate token, send email via SMTP or Mailgun). If no mailer configured, show: "Contact your admin to reset password."
2. Settings gear: Link to a real settings page (timezone, currency symbol, company name for ID cards).
3. Remove `alert('coming soon')` calls — replace with proper UI feedback.
**Files:** New route, new template, `templates/profile.html`.

---

## Delivery Schedule

| Sprint | Theme | Duration | Outcome |
|---|---|---|---|
| Sprint 0 | Security Hardening | 1–2 days | App safe to share with real users |
| Sprint 1 | Architecture | 3–5 days | Maintainable, scalable codebase |
| Sprint 2 | Data Integrity | 2–3 days | Reliable, validated data |
| Sprint 3 | Core Features | 3–5 days | Payroll, CSV export, RBAC complete |
| Sprint 4 | Performance & UX | 2–3 days | Fast, polished mobile experience |
| Sprint 5 | Testing | 2–3 days | Confidence in every deployment |
| **Total** | | **~2–3 weeks** | **Production-ready SmartWorker v1.0** |

---

## Immediate Next Actions (Today)

1. ✅ `pip install flask-wtf` and add CSRF tokens to all forms (S0-01)
2. ✅ Remove OTP from HTTP response or disable OTP UI (S0-02)
3. ✅ Set `SESSION_SECRET` as a required env var, no fallback (S0-03)
4. ✅ Randomize or env-var-gate the default admin password (S0-04)
5. ✅ Gate `debug=True` on env variable (S0-05)

These five changes take less than 2 hours and eliminate all 4 Critical-severity security findings.

---

*Next: Phase 5 — Implementation (05_IMPLEMENTATION_LOG.md)*
