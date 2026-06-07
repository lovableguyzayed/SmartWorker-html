# Phase 1 — Deep Discovery & Research

> Generated: 2026-06-07

---

## 1. Project Structure Map

```
/workspace
├── app.py                     ← Flask app factory + DB init + schema patching
├── main.py                    ← Entry point (runs Flask dev server)
├── models.py                  ← SQLAlchemy ORM models (4 models)
├── routes.py                  ← All routes + business logic (1,293 lines)
├── pyproject.toml             ← Python dependencies (uv/pip)
├── package.json               ← Capacitor/Cordova JS deps
├── capacitor.config.json      ← Capacitor mobile wrapper config
├── config.xml                 ← Cordova mobile wrapper config
├── replit.md                  ← Project README + user preferences
├── ANDROID_BUILD_GUIDE.md     ← Cordova APK build instructions
│
├── static/
│   ├── css/custom.css         ← Custom CSS (307 lines)
│   ├── js/app.js              ← Frontend JS utility library (488 lines)
│   ├── js/offline-sync.js     ← IndexedDB offline queue + auto-sync
│   ├── sw.js                  ← Service Worker (PWA caching)
│   ├── manifest.json          ← PWA manifest
│   ├── images/
│   │   ├── logo.png
│   │   └── logo.svg
│   └── uploads/workers/       ← Worker profile photo uploads
│
├── templates/
│   ├── base.html              ← Master layout (nav, head, offline bar)
│   ├── splash.html            ← Landing / splash screen
│   ├── login.html             ← Login (username/email + OTP flow)
│   ├── register.html          ← Registration with mobile OTP
│   ├── dashboard.html         ← Main dashboard
│   ├── workers.html           ← Workers list + search/filter
│   ├── worker_profile.html    ← Individual worker profile
│   ├── edit_worker.html       ← Add / Edit worker form (shared)
│   ├── edit_daily_worker.html ← Legacy/alternate daily worker form
│   ├── attendance.html        ← Daily attendance marking
│   ├── worker_attendance.html ← Per-worker monthly attendance + payroll
│   ├── id_card.html           ← Digital ID card + QR code
│   ├── closures.html          ← Closure/holiday day management
│   └── profile.html           ← User account settings
│
├── www/index.html             ← Cordova app loader (splash → server URL)
└── instance/smartworker.db    ← SQLite dev database
```

**Entry Points:**
- `main.py` → `app.py` → `routes.py` (dev server)
- Production: Gunicorn serving `app:app`

**Structure type:** Single-project monolith (Flask MPA — Multi-Page Application)

---

## 2. Tech Stack Detection

### Backend
| Component | Technology | Version |
|---|---|---|
| Framework | Flask | 3.1.1 |
| ORM | SQLAlchemy + Flask-SQLAlchemy | 2.0.41 / 3.1.1 |
| Auth | Flask-Login | 0.6.3 |
| Password hashing | Werkzeug | 3.1.3 |
| WSGI server | Gunicorn | 23.0.0 |
| QR code generation | qrcode + Pillow | 8.2 / 11.2.1 |
| DB (dev) | SQLite | built-in |
| DB (prod) | PostgreSQL via psycopg2-binary | 2.9.10 |
| JWT | PyJWT | 2.10.1 |
| OAuth | OAuthLib / Flask-Dance | 3.3.0 / 7.1.0 |

### Frontend
| Component | Technology |
|---|---|
| CSS Framework | Tailwind CSS (CDN — not built) |
| Icons | Font Awesome 6 (CDN) |
| Typography | Google Fonts — Inter |
| Templating | Jinja2 (server-rendered HTML) |
| JS | Vanilla JS (no framework) |
| PWA | Service Worker + Web Manifest |
| Offline sync | IndexedDB (custom implementation) |

### Mobile Wrapping
| Tool | Config File |
|---|---|
| Capacitor | `capacitor.config.json` |
| Cordova | `config.xml` |

### No third-party integrations present:
- ❌ No payment gateway
- ❌ No SMS/OTP gateway (OTP is simulated — printed to logs)
- ❌ No email service
- ❌ No cloud file storage
- ❌ No analytics
- ❌ No error tracking

---

## 3. Purpose & Functionality

**What it does:** SmartWorker is a mobile-first HR management web application designed specifically for managing daily wage and contract workers in India. It allows business owners or managers to maintain a digital record of workers, mark attendance daily, track working hours (check-in/check-out), calculate wages automatically based on configurable pay policies (daily/monthly/hourly/project rates), generate printable ID cards with QR codes, manage holiday/closure days, and export attendance + payroll data to CSV.

**Target users:** Small business owners, site supervisors, HR managers overseeing a workforce of daily wage laborers (construction, manufacturing, services).

**Main features today:**
1. Secure login (username/password + mobile OTP — OTP is currently simulated)
2. Worker registration and profile management (photo, department, pay policy)
3. Daily attendance marking (individual + bulk) with check-in/check-out and overtime tracking
4. Per-worker monthly attendance calendar + payroll summary
5. Digital ID card generation with QR code (PDF-printable)
6. Closure/holiday day management
7. CSV data export
8. PWA installable / Cordova APK wrapper
9. Offline form queueing with auto-sync on reconnection

**Main user flows:**
1. Login → Dashboard → Mark attendance for today → View per-worker shift summary
2. Login → Workers → Add Worker → Configure pay policy → Generate ID card
3. Login → Worker profile → Worker attendance (monthly) → View payroll calculation
4. Login → Closures → Add holiday → Attendance is locked on that day
5. Login → Profile → Change password / update account info

---

## 4. Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENT (Browser / Cordova APK)       │
│                                                         │
│  Jinja2 HTML templates + Tailwind CSS + Vanilla JS      │
│  ├── Service Worker (PWA caching)                       │
│  └── offline-sync.js (IndexedDB queue → auto-sync)     │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP (multipage form posts)
                    ▼
┌─────────────────────────────────────────────────────────┐
│           FLASK APPLICATION (Gunicorn / Dev server)      │
│                                                         │
│  app.py          → app factory, DB config, schema patch │
│  routes.py       → ALL routes + business logic          │
│  models.py       → ORM models                          │
│  Flask-Login     → session auth                         │
│  ProxyFix        → reverse proxy header handling        │
└───────────────────┬─────────────────────────────────────┘
                    │ SQLAlchemy ORM
                    ▼
┌─────────────────────────────────────────────────────────┐
│           DATABASE                                       │
│  Dev:  SQLite (instance/smartworker.db)                 │
│  Prod: PostgreSQL (DATABASE_URL env var)                │
└─────────────────────────────────────────────────────────┘
```

---

## 5. API Routes (Complete List)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | No | Splash screen (redirects to dashboard if logged in) |
| GET/POST | `/login` | No | Username/email + password login |
| POST | `/login/send-otp` | No | Send OTP to mobile (JSON) |
| POST | `/login/verify-otp` | No | Verify OTP and log in (JSON) |
| GET/POST | `/register` | No | New user registration |
| POST | `/register/send-otp` | No | Send registration OTP (JSON) |
| POST | `/register/verify-otp` | No | Verify registration OTP (JSON) |
| GET | `/logout` | Yes | Logout + redirect to login |
| GET | `/dashboard` | Yes | Dashboard with today's stats |
| GET | `/workers` | Yes | Workers list (search + filter) |
| GET | `/worker/<id>` | Yes | Worker profile + recent attendance |
| GET/POST | `/add_worker` | Yes | Add new worker form |
| GET/POST | `/edit_worker/<id>` | Yes | Edit existing worker |
| GET | `/attendance` | Yes | Daily attendance marking page |
| POST | `/mark_attendance` | Yes | Mark/update attendance (individual or bulk) |
| GET | `/worker_attendance/<id>` | Yes | Monthly attendance + payroll for one worker |
| GET/POST | `/closures` | Yes | Holiday/closure day management |
| POST | `/closures/<id>/delete` | Yes | Delete a closure day |
| GET/POST | `/id_card/<id>` | Yes | Worker ID card + QR code regeneration |
| GET/POST | `/profile` | Yes | User profile + change password |
| GET | `/export_data` | Yes | Download all data as CSV |

**Total routes:** 21 (17 authenticated, 4 public)

---

## 6. Data Models

### `users` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| username | String(80) UNIQUE | |
| email | String(120) UNIQUE | |
| phone | String(20) | nullable, added via schema patch |
| password_hash | String(256) | Werkzeug hash |
| full_name | String(100) | |
| role | String(20) | 'admin' or 'manager' (role column exists, not enforced) |
| created_at | DateTime | |

### `workers` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| worker_id | String(20) UNIQUE | auto-generated e.g. CO001 |
| full_name | String(100) | |
| phone | String(20) | |
| email | String(120) | nullable |
| address | Text | nullable |
| position | String(100) | |
| department | String(50) | |
| employee_type | String(30) | Daily Wage, Full Time, etc. |
| join_date | Date | |
| pay_type | String(20) | daily/monthly/hourly/project |
| daily_rate | Float | nullable |
| monthly_salary | Float | nullable |
| hourly_rate | Float | nullable |
| project_rate | Float | nullable |
| start_time / end_time | Time | nullable |
| break_duration | Integer | minutes |
| overtime_enabled | Boolean | |
| overtime_rate | Float | nullable |
| overtime_type | String(10) | hour/minute |
| late_policy_enabled | Boolean | |
| late_deduction_per_day | Float | nullable |
| late_deduction_type | String(10) | day/hour/minute |
| no_work_no_pay | Boolean | |
| half_day_rate | Float | nullable |
| half_day_grace_minutes | Integer | 15–25 min |
| allowed_leaves_per_month | Integer | |
| leave_deduction_per_day | Float | nullable |
| leave_policy_enabled | Boolean | |
| status | String(20) | active/inactive |
| profile_image | Text | file URL |
| qr_code | Text | base64 PNG data URI |
| created_at / updated_at | DateTime | |

### `attendance_records` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| worker_id | FK → workers.id | |
| date | Date | |
| check_in_time | DateTime | nullable |
| check_out_time | DateTime | nullable |
| status | String(20) | present/absent/late/leave |
| overtime_minutes | Integer | |
| notes | Text | nullable |
| created_at | DateTime | |

### `closure_days` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| date | Date UNIQUE | |
| reason | String(200) | |
| type | String(20) | holiday/maintenance/etc. |
| allow_attendance | Boolean | lock attendance on this day |
| created_at | DateTime | |

### `payroll_records` table
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| worker_id | FK → workers.id | |
| month / year | Integer | |
| total_days / present_days | Integer | |
| overtime_hours | Float | |
| gross_pay / deductions / net_pay | Float | |
| status | String(20) | pending/paid |
| created_at | DateTime | |

> **Note:** `payroll_records` table exists in the model and schema but is **never written to or read from** in routes.py. It is a dead table.

---

## Summary

SmartWorker is a well-scoped, single-developer Flask application with a clear purpose. The core attendance + payroll calculation engine (routes.py lines 70–725) is the most complex and most valuable part of the codebase. The app is functional for its core use case but has significant gaps in security, code organization, and production readiness that will be documented in Phase 2.
