# Phase 1 — Deep Discovery Report
**SmartWorker Employee Management System**
**Audit Date:** June 07, 2026
**Auditor:** Replit Agent (Senior Architect Mode)

---

## 1. Project Identity

| Field | Value |
|---|---|
| Application Name | SmartWorker |
| Type | Mobile-first Flask PWA / Cordova-ready APK |
| Target Users | HR admins, managers of daily-wage workforces |
| Primary Language | Python 3 (Flask) + Vanilla JS + Jinja2 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Deployment | Replit Autoscale + Gunicorn |
| Version | v1.0 (initial, June 2025) |

---

## 2. Codebase Structure

```
/
├── main.py                   # Entry point — imports app + routes, binds port
├── app.py                    # Flask factory, DB init, inline migrations, admin seed
├── models.py                 # 5 SQLAlchemy models
├── routes.py                 # All 22 route handlers (1293 lines)
├── pyproject.toml            # Dependencies
├── config.xml                # Apache Cordova config
├── ANDROID_BUILD_GUIDE.md    # Cordova APK build instructions
│
├── templates/
│   ├── base.html             # Base layout: bottom nav, offline indicator, SW registration
│   ├── login.html            # Login + OTP flow
│   ├── register.html         # Registration + OTP flow
│   ├── dashboard.html        # Stats, quick actions, recent attendance, upcoming closures
│   ├── workers.html          # Worker list with search + department filter
│   ├── edit_worker.html      # Add/Edit worker form (shared template, 458 lines)
│   ├── worker_profile.html   # Worker detail view + attendance summary
│   ├── worker_attendance.html# Per-worker attendance calendar
│   ├── attendance.html       # Daily attendance marking + bulk actions
│   ├── closures.html         # Holiday/closure day management
│   ├── id_card.html          # Digital ID card with QR + PDF export
│   └── profile.html          # User account settings
│
├── static/
│   ├── manifest.json         # PWA manifest
│   ├── sw.js                 # Service worker (offline caching)
│   ├── images/logo.png       # App logo
│   ├── css/custom.css        # Page-slide animations
│   └── js/
│       ├── app.js            # NavProgress bar, SmartWorker init
│       └── offline-sync.js   # IndexedDB offline queue + auto-replay
│
└── www/
    └── index.html            # Cordova shell (redirects to app URL)
```

---

## 3. Technology Stack Inventory

### Backend
| Library | Version | Purpose |
|---|---|---|
| Flask | 3.1.1 | Web framework |
| SQLAlchemy | 2.0.41 | ORM |
| Flask-SQLAlchemy | 3.1.1 | Flask integration |
| Flask-Login | 0.6.3 | Session/auth management |
| Werkzeug | 3.1.3 | Password hashing, ProxyFix |
| Gunicorn | 23.0.0 | WSGI production server |
| psycopg2-binary | 2.9.10 | PostgreSQL adapter |
| QRCode | 8.2 | QR code generation |
| Pillow | 11.2.1 | Image processing |
| PyJWT | 2.10.1 | JWT (imported, unused in current routes) |
| OAuthLib | 3.3.0 | OAuth (imported, unused in current routes) |
| Flask-Dance | 7.1.0 | OAuth provider (imported, unused) |
| Email-Validator | 2.2.0 | Email validation |

### Frontend (CDN-loaded — no build step)
| Resource | Source |
|---|---|
| Tailwind CSS | CDN (play.tailwindcss.com) |
| Font Awesome 6 | CDN (kit.fontawesome.com) |
| Inter Font | Google Fonts CDN |
| jsPDF | CDN |
| html2canvas | CDN |

---

## 4. Database Schema

### `users` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| username | String(80) UNIQUE | |
| email | String(120) UNIQUE | |
| password_hash | String(256) | Werkzeug pbkdf2 |
| full_name | String(100) | |
| role | String(20) | 'admin' or 'manager' |
| phone | String(20) | OTP login target |
| is_active | Boolean | default True |
| created_at | DateTime | |

### `workers` table (30+ columns)
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| worker_id | String UNIQUE | Dept prefix + 3-digit seq (e.g. CO001) |
| full_name | String(100) | |
| phone | String(20) | |
| email | String(120) | nullable |
| address | Text | nullable |
| position | String(100) | |
| department | String(100) | |
| employee_type | String(50) | Daily Wage / Full Time / etc. |
| status | String(20) | active / inactive |
| join_date | Date | |
| pay_type | String(20) | daily / monthly / hourly / project |
| daily_rate | Float | nullable |
| monthly_salary | Float | nullable |
| hourly_rate | Float | nullable |
| project_rate | Float | nullable |
| start_time | Time | nullable |
| end_time | Time | nullable |
| break_duration | Integer | minutes |
| overtime_enabled | Boolean | |
| overtime_rate | Float | nullable |
| overtime_type | String(20) | hour / day |
| late_policy_enabled | Boolean | |
| late_deduction_per_day | Float | nullable |
| late_grace_minutes | Integer | |
| late_mark_after_minutes | Integer | |
| half_day_enabled | Boolean | |
| half_day_hours | Float | nullable |
| leave_policy_enabled | Boolean | |
| allowed_leaves_per_month | Integer | |
| leave_deduction_per_day | Float | nullable |
| qr_code | Text | base64 PNG (large) |
| profile_image | Text | base64 image (large) |
| notes | Text | nullable |
| allow_attendance | Boolean | |
| created_at | DateTime | |

### `attendance_records` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| worker_id | Integer FK → workers.id | |
| date | Date | |
| status | String(20) | present / absent / late / leave |
| check_in_time | DateTime | nullable |
| check_out_time | DateTime | nullable |
| notes | Text | nullable |
| overtime_hours | Float | |
| created_at | DateTime | |
| UniqueConstraint | — | (worker_id, date) |

### `closure_days` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| date | Date UNIQUE | |
| reason | String(200) | |
| type | String(50) | holiday / national / company / maintenance / other |
| allow_attendance | Boolean | |
| created_at | DateTime | |

### `payroll_records` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| worker_id | Integer FK | |
| period_start | Date | |
| period_end | Date | |
| total_days | Integer | |
| present_days | Integer | |
| total_amount | Float | |
| status | String(20) | |
| created_at | DateTime | |

---

## 5. Route Map

| Method | URL | Handler | Auth | Description |
|---|---|---|---|---|
| GET/POST | `/` | `index` | No | Redirect to dashboard or login |
| GET/POST | `/login` | `login` | No | Username + password login |
| POST | `/login/send-otp` | `login_send_otp` | No | Fake OTP generation |
| POST | `/login/verify-otp` | `login_verify_otp` | No | OTP verification |
| GET/POST | `/register` | `register` | No | New user registration |
| POST | `/register/send-otp` | `register_send_otp` | No | Fake OTP for register |
| POST | `/register/verify-otp` | `register_verify_otp` | No | OTP verification |
| GET | `/logout` | `logout` | Yes | Clears session |
| GET | `/dashboard` | `dashboard` | Yes | Stats overview |
| GET | `/workers` | `workers` | Yes | Worker list + search/filter |
| GET | `/worker/<id>` | `worker_profile` | Yes | Worker detail view |
| GET/POST | `/add_worker` | `add_worker` | Yes | Create worker |
| GET/POST | `/edit_worker/<id>` | `edit_worker` | Yes | Edit worker |
| GET | `/attendance` | `attendance` | Yes | Daily attendance view |
| POST | `/mark_attendance` | `mark_attendance` | Yes | Mark/update attendance |
| GET/POST | `/closures` | `closures` | Yes | Closure day management |
| POST | `/closures/<id>/delete` | `delete_closure` | Yes | Delete closure |
| GET | `/worker_attendance/<id>` | `worker_attendance` | Yes | Per-worker calendar view |
| GET | `/id_card/<id>` | `id_card` | Yes | Digital ID card |
| GET/POST | `/profile` | `profile` | Yes | User profile settings |
| GET | `/export_data` | `export_data` | Yes | JSON export of all data |

---

## 6. Authentication & Security Model

### Login Methods
1. **Username + Password**: Standard form POST. Werkzeug `check_password_hash`. Flash messages on failure.
2. **OTP Login (FAKE)**: Mobile number → server generates 6-digit OTP → **returns OTP in JSON response** (no SMS gateway). OTP stored in Flask session with 10-min expiry.
3. **OTP Registration (FAKE)**: Same fake mechanism.

### Session Management
- Flask-Login with `@login_required` on all protected routes.
- Permanent session (`remember=True`).
- Session secret from `SESSION_SECRET` env var (fallback: hardcoded `'smartworker-secret-key-2024'`).

### Default Credentials
- Username: `admin` / Password: `admin123` — seeded in `app.py` on every startup if no admin exists.

### CSRF Protection
- **None.** No CSRF tokens on any form. All POST routes accept requests from any origin.

### Input Sanitization
- No explicit sanitization. Jinja2 auto-escapes HTML (XSS protection). SQLAlchemy ORM prevents SQL injection.

---

## 7. Business Logic Summary

### Worker ID Generation
- Pattern: first 2 chars of department (uppercased) + sequential 3-digit number (e.g., `CO001`, `IT002`).
- Sequence: counts existing workers with same dept prefix, adds 1. **No collision check on concurrent adds.**

### QR Code Generation
- On worker create/edit: generates QR encoding `"WORKER:{worker_id}:{full_name}"`.
- Stored as base64 PNG in TEXT column (can be 20–80KB per worker row).

### Wage Calculation (`calculate_wage` function in routes.py)
- **Daily**: `daily_rate`. If check-in/out recorded → overtime hours calculated. OT pay = `overtime_rate × overtime_hours`.
- **Monthly**: `monthly_salary / working_days_in_month`. Late deduction applied if `late_policy_enabled`. Leave deduction if `leave_policy_enabled`.
- **Hourly**: `hourly_rate × hours_worked` (check-in/out delta minus break).
- **Project**: flat `project_rate` per present day.
- **Half-day**: if hours_worked < `half_day_hours` threshold → half pay.

### Attendance Marking Logic
- Single worker: upserts attendance record for (worker_id, date). **On second tap of same status (present/late) → records `check_out_time = now`** (smart toggle).
- Bulk: marks all active workers with given status for that date.
- Closure days with `allow_attendance=False` → both bulk and individual marking are blocked.

### Inline Schema Migration
- On startup, `app.py` runs raw `ALTER TABLE` SQL to add missing columns if they don't exist.
- This approach works but is fragile and does not version or roll back migrations.

---

## 8. Offline / PWA Architecture

### Service Worker (`static/sw.js`)
- Cache-first for static assets, network-first for dynamic routes.

### Offline Sync (`static/js/offline-sync.js`)
- Intercepts form POST submissions when `!navigator.onLine`.
- Stores request (URL, method, body) in IndexedDB queue (`smartworker_offline_queue`).
- On `online` event → replays queued requests sequentially via `fetch`.

### PWA Manifest
- `display: standalone`, `theme_color: #1e3a5f`, icons configured.

### Cordova Shell
- `www/index.html` + `config.xml` wrap the live app URL for Android APK packaging.

---

## 9. Known Stubs & Placeholder Features

| Feature | Status |
|---|---|
| OTP SMS delivery | FAKE — OTP returned in API JSON response body |
| Profile photo upload (admin) | `alert('coming soon')` stub |
| Settings modal | `alert('coming soon')` stub |
| Payroll button on worker profile | Non-functional (no route linked) |
| "Remember me" checkbox | UI only, not wired to backend |
| "Forgot Password" button | No handler, no route |
| JWT / OAuth (PyJWT, OAuthLib, Flask-Dance) | Imported as deps, unused |
| Last Backup date on profile page | Hardcoded to `date.today()` |
| Notification bell on dashboard | No handler |
| `PayrollRecord` model | Defined in models.py, no routes or UI |
| Bulk attendance modal | Only "Present" and "Absent" options (missing "Late" and "Leave") |

---

## 10. Infrastructure & Deployment

| Aspect | Configuration |
|---|---|
| WSGI Server | Gunicorn (`gunicorn main:app`) |
| Dev Server | `python main.py` (Flask debug, port 5000) |
| DB Connection Pooling | `pool_recycle=300`, `pool_pre_ping=True` |
| Proxy Handling | `ProxyFix(app, x_proto=1, x_host=1)` |
| Env Variables | `DATABASE_URL`, `SESSION_SECRET` |
| Host Binding | `0.0.0.0:5000` |

---

## 11. Discovery Summary

SmartWorker is a feature-rich, well-styled mobile-first Flask app with thoughtfully designed UI and solid business logic (wage calculation, overtime, half-day, late deductions). The codebase is single-file-heavy (`routes.py` at 1,293 lines), relies on fragile inline schema migrations, and contains multiple stubs and security gaps (no CSRF, fake OTP, hardcoded admin credentials). The PWA/offline layer and Cordova shell are well-structured additions. The foundation is solid but requires structured refactoring and security hardening before safe production use.
