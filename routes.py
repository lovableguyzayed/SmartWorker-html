import os
import qrcode
import io
import base64
import csv
import json
import random
import re
import calendar as _cal
from datetime import datetime, date, timedelta
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, session, jsonify, make_response, g, get_flashed_messages, has_app_context
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload, joinedload
from werkzeug.utils import secure_filename
from PIL import Image as PILImage, ImageOps as PILImageOps
from app import app, db, csrf
from timeutil import IST, now_ist, today_ist, ISTDate
import storage
import supabase_auth
import tenancy
import salary
import i18n
import money
from models import (
    Account, User, Worker, AttendanceRecord, ClosureDay, PayrollRecord,
    CompanySetting, Department, Site, Project, WorkTask, ProjectAssignment,
    WorkerModification, LeaveAdjustment, WorkerTransaction, Notification,
    SalaryPolicy, SalaryPolicyAudit,
    TRANSACTION_EARNING_TYPES, TRANSACTION_DEDUCTION_TYPES,
)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


@app.before_request
def _pin_tenant_account():
    # Pin the current request to the logged-in user's workspace so every
    # tenant query/insert is automatically isolated (see tenancy.py).
    tenancy.set_request_account()


def _provision_from_supabase(supa_user, full_name=None, phone=None,
                             make_account=False, account_name=None):
    """Find or create the local User row backing a Supabase auth user.

    Idempotent. A brand-new user (or a legacy/local user with the same email)
    becomes the owner/admin of a workspace Account; that is also how the
    designated admin 'claims' the migrated legacy data on first Supabase login.
    """
    uid = supa_user.get('id')
    email = (supa_user.get('email') or '').lower()

    user = User.query.filter_by(supabase_uid=uid).first()
    if not user and email:
        user = User.query.filter_by(email=email).first()

    def _new_account():
        acc = Account(name=account_name or full_name or (email.split('@')[0] if email else 'My Workspace'),
                      owner_uid=uid)
        db.session.add(acc)
        db.session.flush()
        return acc

    if user:
        # Link the local row to Supabase and ensure it has a workspace.
        user.supabase_uid = uid
        if user.account_id is None:
            user.account_id = _new_account().id
        db.session.commit()
        return user

    # Brand-new: create the workspace + its owner/admin user.
    acc = _new_account()
    user = User(
        username=generate_unique_username(full_name, email),
        email=email,
        phone=phone,
        full_name=full_name or (email or 'User'),
        role='admin',
        supabase_uid=uid,
        account_id=acc.id,
        status='active',
    )
    db.session.add(user)
    db.session.commit()
    return user

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
WORKER_IMAGE_UPLOAD_DIR = os.path.join(app.static_folder, 'uploads', 'workers')
REGISTER_OTP_SESSION_KEYS = (
    'register_otp',
    'register_otp_mobile',
    'register_otp_expires_at',
    'register_otp_verified',
)
LOGIN_OTP_SESSION_KEYS = (
    'login_otp',
    'login_otp_mobile',
    'login_otp_expires_at',
    'login_otp_user_id',
)

def allowed_image_file(filename):
    if not filename or '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS

def _compress_image(file_storage, max_px=640, quality=80, preserve_alpha=False):
    """Resize + recompress an uploaded image before storing it.

    - Fixes phone-camera EXIF rotation (photos otherwise appear sideways).
    - Shrinks multi-megabyte camera photos to a web-sized JPEG/PNG so pages
      load fast and Supabase uploads don't time out.
    Returns (bytes, mimetype, extension). On any decode failure it falls back
    to the original bytes so a valid-but-unusual file is never lost.
    """
    try:
        data = file_storage.read()
        img = PILImage.open(io.BytesIO(data))
        img = PILImageOps.exif_transpose(img)  # honor camera orientation
        has_alpha = img.mode in ('RGBA', 'LA', 'PA') or (
            img.mode == 'P' and 'transparency' in img.info
        )
        if preserve_alpha and has_alpha:
            img = img.convert('RGBA')
            if max(img.size) > max_px:
                img.thumbnail((max_px, max_px), PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format='PNG', optimize=True)
            return buf.getvalue(), 'image/png', 'png'
        img = img.convert('RGB')
        if max(img.size) > max_px:
            img.thumbnail((max_px, max_px), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        return buf.getvalue(), 'image/jpeg', 'jpg'
    except Exception:
        try:
            file_storage.seek(0)
            raw = file_storage.read()
        except Exception:
            raw = b''
        ext = (file_storage.filename or '').rsplit('.', 1)[-1].lower() or 'jpg'
        return raw, (file_storage.mimetype or 'application/octet-stream'), ext


def save_worker_profile_image(file_storage, worker_id):
    filename = secure_filename(file_storage.filename or '')
    if not allowed_image_file(filename):
        raise ValueError('Please upload a valid image (JPG, JPEG, PNG, GIF, or WEBP).')

    image_data, image_mime, image_ext = _compress_image(file_storage, max_px=640)
    unique_filename = f"{worker_id}_{now_ist().strftime('%Y%m%d%H%M%S%f')}.{image_ext}"

    # Supabase Storage when configured (persists across Render deploys);
    # local static/uploads fallback otherwise. A storage/network failure is
    # surfaced as a friendly ValueError instead of a 500 crash.
    if storage.storage_enabled():
        try:
            return storage.upload_image(f'acc{current_user.account_id}/workers/{unique_filename}', image_data, image_mime)
        except Exception as exc:
            app.logger.warning('Supabase image upload failed: %s', exc)
            raise ValueError('Could not upload the image right now. Please try again.')

    os.makedirs(WORKER_IMAGE_UPLOAD_DIR, exist_ok=True)
    destination = os.path.join(WORKER_IMAGE_UPLOAD_DIR, unique_filename)
    with open(destination, 'wb') as fh:
        fh.write(image_data)
    return url_for('static', filename=f'uploads/workers/{unique_filename}')

def parse_float(value, default=0.0):
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def parse_int(value, default=0):
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# Column widths from models.Worker. SQLite ignores VARCHAR limits, but the
# production database is Postgres, which rejects an over-long value outright —
# so a 300-character name saves fine in dev and 500s in production. Trim to the
# column width at the boundary instead.
WORKER_TEXT_LIMITS = {
    'full_name': 100, 'phone': 20, 'email': 120,
    'position': 100, 'department': 50, 'employee_type': 30,
}

# A pay rate above this is certainly a typo (a mis-keyed extra digit), and a
# negative one would produce negative payroll.
MAX_PAY_RATE = 10_000_000


def clean_text(value, field, required=False):
    """Trim, collapse whitespace and cut to the column width."""
    text = ' '.join((value or '').split())
    limit = WORKER_TEXT_LIMITS.get(field)
    if limit:
        text = text[:limit]
    return text if (text or not required) else ''


# --- payment details ------------------------------------------------------
# Format checks only. A correctly shaped account number can still be the
# wrong account, so these catch typing mistakes, not fraud.
IFSC_RE = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
PAN_RE = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
UPI_RE = re.compile(r'^[\w.\-]{2,60}@[A-Za-z]{2,20}$')
ACCOUNT_RE = re.compile(r'^\d{9,18}$')
AADHAAR_RE = re.compile(r'^\d{12}$')


def clean_payment_details(form):
    """Read the payment fields off a form. Returns (values, errors).

    Every field is optional — an employer may know a worker's UPI id long
    before their bank details, and refusing the whole save over a blank
    field would just mean nobody fills any of them in.
    """
    def squash(name, upper=False):
        raw = (form.get(name) or '').strip()
        raw = re.sub(r'[\s-]', '', raw) if name != 'bank_account_name' else raw
        return raw.upper() if upper and raw else raw

    values = {
        'bank_account_name': (form.get('bank_account_name') or '').strip()[:120],
        'bank_account_number': squash('bank_account_number'),
        'bank_ifsc': squash('bank_ifsc', upper=True),
        'upi_id': (form.get('upi_id') or '').strip(),
        'aadhaar_number': squash('aadhaar_number'),
        'pan_number': squash('pan_number', upper=True),
    }
    errors = []
    checks = (
        ('bank_account_number', ACCOUNT_RE, 'Bank account number should be 9 to 18 digits.'),
        ('bank_ifsc', IFSC_RE, 'IFSC should look like HDFC0001234.'),
        ('upi_id', UPI_RE, 'UPI id should look like name@bank.'),
        ('aadhaar_number', AADHAAR_RE, 'Aadhaar number should be 12 digits.'),
        ('pan_number', PAN_RE, 'PAN should look like ABCDE1234F.'),
    )
    for field, pattern, message in checks:
        if values[field] and not pattern.match(values[field]):
            errors.append(message)
            values[field] = None
    # An empty string and "not provided" are the same thing here; storing ''
    # would make "has details" checks lie.
    return {k: (v or None) for k, v in values.items()}, errors


def apply_payment_details(worker, form):
    """Copy validated payment details onto a worker. Returns any errors."""
    values, errors = clean_payment_details(form)
    for field, value in values.items():
        setattr(worker, field, value)
    return errors


def clean_rate(value):
    """Non-negative, sanely bounded money. Returns (amount, error_or_None)."""
    if value is None or str(value).strip() == '':
        return 0.0, None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0, 'Enter a valid number for the pay rate.'
    if amount < 0:
        return 0.0, 'Pay rate cannot be negative.'
    if amount > MAX_PAY_RATE:
        return 0.0, f'Pay rate looks wrong — it cannot exceed {MAX_PAY_RATE:,}.'
    return amount, None


def parse_date_or(value, default=None):
    """Parse an ISO date, falling back instead of raising.

    Every date that reaches a view comes from a query string or a form field,
    so it is user input and can be anything. Calling datetime.strptime on it
    directly turns a typo or a stale bookmark into a 500.
    """
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError, AttributeError):
        return default

def parse_time_or(value, default=None):
    """Same contract as parse_date_or, for HH:MM shift times."""
    try:
        return datetime.strptime((value or '').strip(), '%H:%M').time()
    except (TypeError, ValueError, AttributeError):
        return default

def calculate_scheduled_minutes_for_day(worker, attendance_date):
    if not worker.start_time or not worker.end_time:
        return 0

    start_at = datetime.combine(attendance_date, worker.start_time)
    end_at = datetime.combine(attendance_date, worker.end_time)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return max(int((end_at - start_at).total_seconds() // 60), 0)

def calculate_worked_minutes_for_record(attendance_record):
    if (
        not attendance_record
        or not attendance_record.check_in_time
        or not attendance_record.check_out_time
        or attendance_record.check_out_time <= attendance_record.check_in_time
    ):
        return 0
    return int((attendance_record.check_out_time - attendance_record.check_in_time).total_seconds() // 60)

def get_half_day_grace_minutes(worker):
    grace = parse_int(getattr(worker, 'half_day_grace_minutes', 20), 20)
    return min(max(grace, 15), 25)

def calculate_daily_wage_for_record(worker, attendance_record):
    daily_rate = float(worker.daily_rate or 0)
    half_day_rate = float(
        worker.half_day_rate
        if worker.half_day_rate is not None
        else (daily_rate / 2.0 if daily_rate else 0)
    )

    if not attendance_record or attendance_record.status not in ('present', 'late'):
        return 0.0, 'none'

    scheduled_minutes = calculate_scheduled_minutes_for_day(worker, attendance_record.date)
    worked_minutes = calculate_worked_minutes_for_record(attendance_record)

    if scheduled_minutes <= 0 or worked_minutes <= 0:
        return daily_rate, 'full_day'

    half_day_limit = (scheduled_minutes / 2.0) + get_half_day_grace_minutes(worker)
    if worked_minutes <= half_day_limit:
        return half_day_rate, 'half_day'

    if worked_minutes >= scheduled_minutes:
        return daily_rate, 'full_day'

    # After grace window, pay should follow exact minute-based pro-rata.
    prorated_pay = (worked_minutes / float(scheduled_minutes)) * daily_rate
    return prorated_pay, 'pro_rata'

def is_half_day_record(worker, attendance_record):
    if worker.pay_type != 'daily':
        return False

    _, pay_mode = calculate_daily_wage_for_record(worker, attendance_record)
    return pay_mode == 'half_day'

def calculate_overtime_minutes_for_record(worker, attendance_record):
    if not worker.overtime_enabled or not attendance_record:
        return 0

    worked_minutes = calculate_worked_minutes_for_record(attendance_record)
    if worked_minutes <= 0:
        return 0
    scheduled_minutes = calculate_scheduled_minutes_for_day(worker, attendance_record.date)
    if scheduled_minutes <= 0:
        # No shift configured — fall back to standard working hours
        scheduled_minutes = int(worker.standard_working_hours or 8) * 60
    return max(worked_minutes - scheduled_minutes, 0)

def get_late_grace_minutes(worker):
    return max(parse_int(getattr(worker, 'late_grace_minutes', 10), 10), 0)

def calculate_late_minutes_for_record(worker, attendance_record):
    if (
        not attendance_record
        or attendance_record.status not in ('present', 'late')
        or not attendance_record.check_in_time
        or not worker.start_time
    ):
        return 0

    shift_start = datetime.combine(attendance_record.date, worker.start_time)
    late_minutes = int((attendance_record.check_in_time - shift_start).total_seconds() // 60)
    return max(late_minutes, 0)

def is_late_check_in(worker, attendance_date, check_in_time):
    """True when a check-in falls after shift start plus grace time."""
    if not worker.start_time or not check_in_time:
        return False
    shift_start = datetime.combine(attendance_date, worker.start_time)
    return check_in_time > shift_start + timedelta(minutes=get_late_grace_minutes(worker))

def _months_in_range(start_date, end_date):
    """Whole months from start_date's month through end_date's month, inclusive."""
    if end_date < start_date:
        return 0
    return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1

def _leave_adjustment_window(period_end):
    """Adjustments that count towards a period ending on period_end.

    A NULL effective_date means "applies from creation", so those rows are
    bounded by created_at instead — otherwise an adjustment entered later
    leaks backwards into an already-closed payroll month.
    """
    period_end_ts = datetime.combine(period_end, datetime.max.time())
    return db.or_(
        db.and_(
            LeaveAdjustment.effective_date == None,
            LeaveAdjustment.created_at <= period_end_ts,
        ),
        LeaveAdjustment.effective_date <= period_end,
    )


def prefetch_leave_ledgers(worker_ids, period_start, period_end):
    """Three grouped queries for the whole roster instead of three per worker.

    calculate_leave_balance reads this cache when it is primed and falls back
    to its own per-worker queries when it is not, so the numbers are produced
    by the same expressions either way.
    """
    if not has_app_context():
        return
    cache = getattr(g, '_leave_ledger_cache', None)
    if cache is None:
        cache = g._leave_ledger_cache = {}

    ledgers = {wid: {'manual_adjustment': 0.0, 'used_before': 0, 'used_this_month': 0}
               for wid in worker_ids}
    if worker_ids:
        rows = db.session.query(
            LeaveAdjustment.worker_id,
            func.coalesce(func.sum(LeaveAdjustment.days), 0.0),
        ).filter(
            LeaveAdjustment.worker_id.in_(worker_ids),
            _leave_adjustment_window(period_end),
        ).group_by(LeaveAdjustment.worker_id).all()
        for worker_id, total in rows:
            ledgers[worker_id]['manual_adjustment'] = float(total or 0.0)

        leave_counts = db.session.query(
            AttendanceRecord.worker_id,
            func.count(AttendanceRecord.id),
        ).filter(
            AttendanceRecord.worker_id.in_(worker_ids),
            AttendanceRecord.status == 'leave',
            AttendanceRecord.date < period_start,
        ).group_by(AttendanceRecord.worker_id).all()
        for worker_id, count in leave_counts:
            ledgers[worker_id]['used_before'] = int(count)

        month_counts = db.session.query(
            AttendanceRecord.worker_id,
            func.count(AttendanceRecord.id),
        ).filter(
            AttendanceRecord.worker_id.in_(worker_ids),
            AttendanceRecord.status == 'leave',
            AttendanceRecord.date >= period_start,
            AttendanceRecord.date <= period_end,
        ).group_by(AttendanceRecord.worker_id).all()
        for worker_id, count in month_counts:
            ledgers[worker_id]['used_this_month'] = int(count)

    cache[(period_start, period_end)] = ledgers


def _leave_ledger_for(worker_id, period_start, period_end):
    """One worker's leave counters, from the prefetch cache when it holds them."""
    if has_app_context():
        cached = getattr(g, '_leave_ledger_cache', {}).get((period_start, period_end))
        if cached is not None and worker_id in cached:
            return cached[worker_id]

    manual_adjustment = db.session.query(
        func.coalesce(func.sum(LeaveAdjustment.days), 0.0)
    ).filter(
        LeaveAdjustment.worker_id == worker_id,
        _leave_adjustment_window(period_end),
    ).scalar() or 0.0

    used_before = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker_id,
        AttendanceRecord.status == 'leave',
        AttendanceRecord.date < period_start,
    ).count()

    used_this_month = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker_id,
        AttendanceRecord.status == 'leave',
        AttendanceRecord.date >= period_start,
        AttendanceRecord.date <= period_end,
    ).count()

    return {
        'manual_adjustment': float(manual_adjustment),
        'used_before': used_before,
        'used_this_month': used_this_month,
    }


def calculate_leave_balance(worker, period_start, period_end):
    """Full leave ledger from the joining date through the given payroll month.

    Unused monthly quota accumulates automatically. Extra leaves first consume
    the accumulated balance; only leaves beyond quota + accumulated balance are
    chargeable against salary. Manual HR adjustments (LeaveAdjustment) are
    credited/debited on top."""
    quota = int(worker.allowed_leaves_per_month or 0)
    join_date = worker.join_date or period_start

    months_total = _months_in_range(join_date, period_end)
    months_before = max(months_total - 1, 0)
    accrued_before = months_before * quota
    accrued_total = months_total * quota

    ledger = _leave_ledger_for(worker.id, period_start, period_end)
    manual_adjustment = ledger['manual_adjustment']
    used_before = ledger['used_before']
    used_this_month = ledger['used_this_month']

    balance_before = accrued_before + manual_adjustment - used_before
    available_this_month = max(balance_before, 0) + quota
    chargeable_days = max(used_this_month - available_this_month, 0)
    balance_after = balance_before + quota - used_this_month

    return {
        'monthly_quota': quota,
        'months_accrued': months_total,
        'accrued_total': accrued_total,
        'manual_adjustment': round(manual_adjustment, 2),
        'used_before': used_before,
        'used_this_month': used_this_month,
        'balance_before': round(balance_before, 2),
        'available_this_month': round(available_this_month, 2),
        'chargeable_days': chargeable_days,
        'balance_after': round(balance_after, 2),
    }

def prefetch_period_transactions(worker_ids, period_start, period_end):
    """Load one period's transactions for a whole roster in a single query.

    Payroll asks for these worker by worker; priming this cache first lets
    get_period_transactions answer from memory instead of re-querying.
    """
    if not has_app_context():
        return
    cache = getattr(g, '_txn_period_cache', None)
    if cache is None:
        cache = g._txn_period_cache = {}
    bucket = {wid: [] for wid in worker_ids}
    if worker_ids:
        for txn in WorkerTransaction.query.filter(
            WorkerTransaction.worker_id.in_(worker_ids),
            WorkerTransaction.status == 'active',
            WorkerTransaction.date >= period_start,
            WorkerTransaction.date <= period_end,
        ).order_by(WorkerTransaction.date).all():
            bucket[txn.worker_id].append(txn)
    cache[(period_start, period_end)] = bucket


def get_period_transactions(worker, period_start, period_end):
    if has_app_context():
        bucket = getattr(g, '_txn_period_cache', {}).get((period_start, period_end))
        if bucket is not None and worker.id in bucket:
            return bucket[worker.id]
    return WorkerTransaction.query.filter(
        WorkerTransaction.worker_id == worker.id,
        WorkerTransaction.status == 'active',
        WorkerTransaction.date >= period_start,
        WorkerTransaction.date <= period_end,
    ).order_by(WorkerTransaction.date).all()

def calculate_delay_penalty(worker, period_start, period_end):
    """Per-day project delay penalty for project-based workers. Only overdue
    days falling inside this payroll period are charged, so a delay spanning
    months is never double-billed."""
    if worker.pay_type != 'project':
        return 0.0, []
    penalty_total = 0.0
    breakdown = []
    seen_projects = set()
    for assignment in worker.assignments:
        assignment_start = assignment.start_date
        assignment_end = assignment.end_date or period_end
        if assignment_start > period_end or assignment_end < period_start:
            continue
        project = assignment.project
        if not project or project.id in seen_projects:
            continue
        seen_projects.add(project.id)
        if not project.deadline or project.penalty_type not in ('fixed', 'percent'):
            continue
        if not project.penalty_value:
            continue
        overdue_start = project.deadline + timedelta(days=1)
        overdue_end = project.completion_date or period_end
        charge_start = max(overdue_start, period_start, assignment_start)
        charge_end = min(overdue_end, period_end, assignment_end)
        if charge_end < charge_start:
            continue
        days = (charge_end - charge_start).days + 1
        if project.penalty_type == 'fixed':
            per_day = float(project.penalty_value)
        else:
            per_day = (float(project.penalty_value) / 100.0) * float(worker.project_rate or 0)
        amount = round(days * per_day, 2)
        if amount > 0:
            penalty_total += amount
            breakdown.append({
                'project': project.name,
                'days': days,
                'per_day': round(per_day, 2),
                'amount': amount,
            })
    return round(penalty_total, 2), breakdown

def normalize_mobile_number(value):
    return ''.join(char for char in (value or '') if char.isdigit())

def is_valid_mobile_number(value):
    return 10 <= len(normalize_mobile_number(value)) <= 15

def clear_register_otp_session():
    for key in REGISTER_OTP_SESSION_KEYS:
        session.pop(key, None)

def clear_login_otp_session():
    for key in LOGIN_OTP_SESSION_KEYS:
        session.pop(key, None)

def generate_unique_username(full_name, email):
    base_source = (email.split('@')[0] if email else full_name or 'user').strip().lower()
    normalized = ''.join(char if char.isalnum() else '_' for char in base_source).strip('_')
    base = (normalized or 'user')[:24]

    candidate = base
    index = 1
    while User.query.filter_by(username=candidate).first():
        candidate = f"{base}{index:02d}"
        index += 1
    return candidate

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Everything a worker's own login may reach. Deny-by-default on purpose:
# the alternative is auditing every one of the app's routes and hoping none
# is missed now or later, and the cost of a miss here is one labourer seeing
# the whole company's wages.
WORKER_ENDPOINTS = frozenset({
    'worker_home',          # their own attendance and pay
    'worker_payslip',       # their own payslip
    'worker_logout_note',   # the "what can I do here" page
    'logout',
    'set_language',
    'static',
})

# Opened only for a worker an administrator has made a supervisor. Kept
# separate from the set above so the plain worker login stays read-only by
# construction rather than by remembering to check a flag in each view.
SUPERVISOR_ENDPOINTS = frozenset({
    'supervisor_team',
    'supervisor_mark',
    'supervisor_transaction',
    # The gate scanner, which is four endpoints and not one: the screen, the
    # lookup behind a scan, and the two things the card can then do. Every
    # one of them scopes to the mukadam's own list through
    # worker_visible_to_user / may_record_transaction_for — adding a name
    # here does not grant anything on its own, but it does mean those checks
    # are now the only thing standing between a mukadam and the roster.
    'scan',
    'api_worker_lookup',
    'api_mark_attendance',
    'api_worker_transaction',
})


@app.before_request
def _confine_worker_logins():
    """Hold a worker login inside its own screens.

    A worker is not a cut-down admin: there is exactly one record they may
    see. Anything outside the allowlist goes back to their own page rather
    than 403ing, because a worker who taps a stale bookmark has not done
    anything wrong.
    """
    if not current_user.is_authenticated or not getattr(current_user, 'is_worker', False):
        return None
    endpoint = request.endpoint
    if endpoint is None or endpoint in WORKER_ENDPOINTS:
        return None
    if endpoint in SUPERVISOR_ENDPOINTS and current_user.can_mark_attendance:
        return None
    return redirect(url_for('worker_home'))


def worker_login_required(view):
    """A view only a worker's own login may open."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_worker or not current_user.worker_id:
            return redirect(url_for('dashboard'))
        return view(*args, **kwargs)
    return wrapped


def home_for(user):
    """Where this login belongs after signing in.

    One rule in one place: there are three ways into the app (password, OTP
    and registration) and a worker must not land on the company dashboard
    from any of them. The before_request guard would bounce them anyway, but
    a redirect that lands correctly first time is not the same as one that
    corrects itself.
    """
    if getattr(user, 'is_worker', False):
        return url_for('worker_home')
    return url_for('dashboard')


def admin_required(view):
    """Restrict a view to admin/manager accounts. Authorized attendance users
    are bounced back with the standard contact-administrator popup."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash('Please contact the Administrator to make changes.', 'restricted')
            return redirect(url_for('attendance'))
        return view(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_globals():
    # Only load workspace-scoped company settings for an authenticated user;
    # on public pages (login/splash) there is no account context, and querying
    # would otherwise expose another workspace's company row.
    company = None
    unread = 0
    if current_user.is_authenticated:
        company = CompanySetting.query.first()
        if current_user.is_admin:
            unread = Notification.query.filter_by(is_read=False).count()
    return dict(company=company, unread_notifications=unread)

def roster_query(status='active'):
    """Workers with their assignments (and each assignment's site/project/task)
    already loaded.

    Every roster screen walks `worker.assignments` and then reads
    `assignment.site` / `.project` / `.task`, so a plain query costs four extra
    round-trips per worker. Loading them up front turns that into four queries
    for the whole page.
    """
    return (
        Worker.query.filter_by(status=status)
        .options(
            selectinload(Worker.assignments).options(
                joinedload(ProjectAssignment.site),
                joinedload(ProjectAssignment.project),
                joinedload(ProjectAssignment.task),
            )
        )
        .order_by(Worker.full_name)
    )


def assignment_active_on(assignment, on_date):
    if assignment.start_date and assignment.start_date > on_date:
        return False
    if assignment.end_date and assignment.end_date < on_date:
        return False
    if not assignment.end_date and assignment.status not in ('active',):
        # Ended assignments without an explicit end date only cover their start day
        return assignment.start_date == on_date
    return True

def closure_applies_to_worker(closure, worker, on_date=None):
    """Company closures hit everyone; site/project closures only workers
    assigned to that site/project on the closure date."""
    if closure.scope in (None, '', 'company'):
        return True
    check_date = on_date or closure.date
    for assignment in worker.assignments:
        if not assignment_active_on(assignment, check_date):
            continue
        if closure.scope == 'site' and closure.site_id and assignment.site_id == closure.site_id:
            return True
        if closure.scope == 'project' and closure.project_id and assignment.project_id == closure.project_id:
            return True
    return False

def closure_for_worker_on_date(worker, on_date, closures=None):
    if closures is None:
        closures = ClosureDay.query.filter_by(date=on_date).all()
    applicable = [c for c in closures if closure_applies_to_worker(c, worker, on_date)]
    if not applicable:
        return None
    # A locked closure takes precedence over an attendance-allowed one
    locked = [c for c in applicable if not c.allow_attendance]
    return locked[0] if locked else applicable[0]

def worker_visible_to_user(worker, user, on_date=None):
    """Attendance users only see workers assigned to their sites/projects.

    Args:
        worker: Worker to check
        user: User to check access for
        on_date: Date context for historical assignment lookup. If None, uses current assignment.
    """
    if user.is_admin:
        return True

    # A worker login is scoped by name, not by site: a mukadam is given a
    # list of people, and a plain labourer is given nobody. This has to come
    # before the site rule below, which reads an empty site list as "no
    # restriction" and would otherwise hand a mukadam the whole company —
    # harmless while worker logins could not reach any screen that asks this
    # question, and not harmless the moment one can.
    if user.is_worker:
        return worker.id in set(user.supervisor_team_ids)

    site_ids = user.site_id_list
    project_ids = user.project_id_list
    if not site_ids and not project_ids:
        return True

    if on_date:
        assignment = next((a for a in worker.assignments if assignment_active_on(a, on_date)), None)
    else:
        assignment = worker.current_assignment

    if not assignment:
        return False
    if site_ids and assignment.site_id in site_ids:
        return True
    if project_ids and assignment.project_id in project_ids:
        return True
    return False

def notify_admin(title, body, category='attendance'):
    db.session.add(Notification(title=title, body=body, category=category))

def safe_redirect_target(value, fallback):
    """Only allow same-app relative paths; reject external/protocol-relative URLs."""
    if value and value.startswith('/') and not value.startswith('//') and '\\' not in value:
        return value
    return fallback

# ------------------------------------------------------------------
# Tenant-safe primary-key lookups.
#
# tenancy.py's automatic filter (with_loader_criteria) rewrites SELECT
# queries, but it does NOT apply to Query.get()/get_or_404() — SQLAlchemy
# documents that get() consults the identity map / issues an unfiltered
# PK lookup regardless of loader criteria. Every by-id lookup of a tenant
# model MUST go through these helpers instead of .get()/.get_or_404(),
# or a user could reach another workspace's row just by knowing its id.
# ------------------------------------------------------------------
from werkzeug.exceptions import abort as _abort


def tenant_get_or_404(model, entity_id):
    account_id = tenancy.current_account_id()
    return model.query.filter_by(id=entity_id, account_id=account_id).first() or _abort(404)


def tenant_get(model, entity_id):
    if entity_id is None:
        return None
    account_id = tenancy.current_account_id()
    return model.query.filter_by(id=entity_id, account_id=account_id).first()

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['username'].strip()
        password = request.form['password']

        # Resolve any local user matching the identifier (username/email/phone).
        normalized_phone = normalize_mobile_number(identifier)
        local = User.query.filter(
            db.or_(
                User.username == identifier,
                User.email == identifier.lower(),
                User.phone == normalized_phone,
            )
        ).first()

        # Supabase is the identity provider for owner/admin accounts (anyone
        # with a Supabase uid) and for logging in by email. Local-only staff
        # (attendance users created by an admin) keep their local password.
        use_supabase = supabase_auth.enabled() and (local is None or local.supabase_uid)

        if use_supabase:
            email = local.email if local else identifier.lower()
            result = supabase_auth.sign_in(email, password)
            if not result['ok']:
                flash(result.get('error') or 'Invalid email or password', 'error')
                return render_template('login.html')
            user = _provision_from_supabase(result['user'])
        else:
            user = local if (local and local.check_password(password)) else None
            if not user:
                flash('Invalid username or password', 'error')
                return render_template('login.html')

        if (user.status or 'active') != 'active':
            flash('This account has been disabled. Please contact the Administrator.', 'error')
            return render_template('login.html')
        login_user(user, remember=True)
        clear_login_otp_session()
        next_page = safe_redirect_target(request.args.get('next'), home_for(user))
        return redirect(next_page, code=303)
    else:
        clear_login_otp_session()

    return render_template('login.html')

@app.route('/login/send-otp', methods=['POST'])
@csrf.exempt
def login_send_otp():
    payload = request.get_json(silent=True) or request.form
    mobile = normalize_mobile_number(payload.get('mobile'))

    if not is_valid_mobile_number(mobile):
        return jsonify({
            'success': False,
            'message': 'Please enter a valid mobile number.'
        }), 400

    user = User.query.filter_by(phone=mobile).first()
    if not user:
        return jsonify({
            'success': False,
            'message': 'No account found with this mobile number.'
        }), 404

    otp_code = f"{random.randint(0, 999999):06d}"
    expires_at = now_ist() + timedelta(minutes=5)

    clear_login_otp_session()
    session['login_otp'] = otp_code
    session['login_otp_mobile'] = mobile
    session['login_otp_expires_at'] = expires_at.timestamp()
    session['login_otp_user_id'] = user.id
    session.modified = True

    app.logger.info("Login OTP for %s: %s", mobile, otp_code)

    return jsonify({
        'success': True,
        'message': f'OTP has been sent to {mobile}. (Check server logs in demo mode)',
        'expires_in': 300,
    })

@app.route('/login/verify-otp', methods=['POST'])
@csrf.exempt
def login_verify_otp():
    payload = request.get_json(silent=True) or request.form
    mobile = normalize_mobile_number(payload.get('mobile'))
    otp_code = str(payload.get('otp', '')).strip()

    stored_mobile = session.get('login_otp_mobile')
    stored_otp = session.get('login_otp')
    expires_at = session.get('login_otp_expires_at')
    user_id = session.get('login_otp_user_id')

    if not stored_mobile or not stored_otp or not expires_at or not user_id:
        return jsonify({
            'success': False,
            'message': 'OTP expired. Please request a new OTP.'
        }), 400

    if now_ist().timestamp() > float(expires_at):
        clear_login_otp_session()
        return jsonify({
            'success': False,
            'message': 'OTP expired. Please request a new OTP.'
        }), 400

    if mobile != stored_mobile:
        return jsonify({
            'success': False,
            'message': 'Please verify OTP for the same mobile number.'
        }), 400

    if otp_code != stored_otp:
        return jsonify({
            'success': False,
            'message': 'Invalid OTP. Please try again.'
        }), 400

    user = User.query.get(user_id)
    if not user:
        clear_login_otp_session()
        return jsonify({
            'success': False,
            'message': 'Account not found for this OTP.'
        }), 404

    login_user(user, remember=True)
    clear_login_otp_session()

    return jsonify({
        'success': True,
        'message': 'OTP verified. Login successful.',
        'redirect_url': home_for(user),
    })

@app.route('/register/send-otp', methods=['POST'])
@csrf.exempt
def register_send_otp():
    payload = request.get_json(silent=True) or request.form
    mobile = normalize_mobile_number(payload.get('mobile'))

    if not is_valid_mobile_number(mobile):
        return jsonify({
            'success': False,
            'message': 'Please enter a valid mobile number.'
        }), 400

    otp_code = f"{random.randint(0, 999999):06d}"
    expires_at = now_ist() + timedelta(minutes=5)

    clear_register_otp_session()
    session['register_otp'] = otp_code
    session['register_otp_mobile'] = mobile
    session['register_otp_expires_at'] = expires_at.timestamp()
    session['register_otp_verified'] = False
    session.modified = True

    app.logger.info("Registration OTP for %s: %s", mobile, otp_code)

    return jsonify({
        'success': True,
        'message': f'OTP has been sent to {mobile}. (Check server logs in demo mode)',
        'expires_in': 300,
    })

@app.route('/register/verify-otp', methods=['POST'])
@csrf.exempt
def register_verify_otp():
    payload = request.get_json(silent=True) or request.form
    mobile = normalize_mobile_number(payload.get('mobile'))
    otp_code = str(payload.get('otp', '')).strip()

    stored_mobile = session.get('register_otp_mobile')
    stored_otp = session.get('register_otp')
    expires_at = session.get('register_otp_expires_at')

    if not stored_mobile or not stored_otp or not expires_at:
        return jsonify({
            'success': False,
            'message': 'OTP expired. Please request a new OTP.'
        }), 400

    if now_ist().timestamp() > float(expires_at):
        clear_register_otp_session()
        return jsonify({
            'success': False,
            'message': 'OTP expired. Please request a new OTP.'
        }), 400

    if mobile != stored_mobile:
        return jsonify({
            'success': False,
            'message': 'Please verify the same mobile number used for OTP.'
        }), 400

    if otp_code != stored_otp:
        return jsonify({
            'success': False,
            'message': 'Invalid OTP. Please try again.'
        }), 400

    session['register_otp_verified'] = True
    session.modified = True

    return jsonify({
        'success': True,
        'message': 'Mobile number verified successfully.'
    })

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form['full_name'].strip()
        workspace = request.form.get('business_name', '').strip()
        mobile = normalize_mobile_number(request.form.get('mobile'))

        if not full_name:
            flash('Please enter your full name', 'error')
            return render_template('register.html')
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('register.html')
        if not is_valid_mobile_number(mobile):
            flash('Please enter a valid mobile number', 'error')
            return render_template('register.html')

        # Mobile OTP verification gate (unchanged from the legacy flow).
        otp_verified = session.get('register_otp_verified')
        otp_mobile = session.get('register_otp_mobile')
        otp_expiry = session.get('register_otp_expires_at')
        if (
            not otp_verified
            or otp_mobile != mobile
            or not otp_expiry
            or now_ist().timestamp() > float(otp_expiry)
        ):
            flash('Please verify your mobile number with OTP before registering', 'error')
            return render_template('register.html')

        if User.query.filter_by(phone=mobile).first():
            flash('Mobile number already registered', 'error')
            return render_template('register.html')

        account_name = workspace or f"{full_name}'s Workspace"

        if supabase_auth.enabled():
            # Supabase owns credentials, email verification and recovery.
            result = supabase_auth.sign_up(email, password, full_name)
            if not result['ok']:
                flash(result.get('error') or 'Could not complete registration. Please try again.', 'error')
                return render_template('register.html')

            # Create the local workspace + owner/admin row (idempotent).
            user = _provision_from_supabase(
                result['user'], full_name=full_name, phone=mobile or None,
                make_account=True, account_name=account_name,
            )
            clear_register_otp_session()

            if result.get('needs_confirmation'):
                flash('Registration successful! Check your email to confirm your account, then log in.', 'success')
                return redirect(url_for('login'))
            # Confirmation disabled → Supabase returned a session; log in now.
            login_user(user, remember=True)
            return redirect(home_for(user), code=303)

        # ---- Legacy local fallback (Supabase Auth not configured) ----
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('register.html')
        acc = Account(name=account_name)
        db.session.add(acc)
        db.session.flush()
        user = User()
        user.username = generate_unique_username(full_name, email)
        user.email = email
        user.phone = mobile or None
        user.full_name = full_name
        user.role = 'admin'
        user.account_id = acc.id
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        clear_register_otp_session()
        flash('Registration successful! Please login using your email.', 'success')
        return redirect(url_for('login'))

    clear_register_otp_session()
    return render_template('register.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if supabase_auth.enabled() and email:
            redirect_to = url_for('reset_password', _external=True)
            supabase_auth.send_recovery(email, redirect_to)
        # Always report success so we never reveal which emails are registered.
        flash('If an account exists for that email, a password reset link has been sent.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password', methods=['GET'])
def reset_password():
    # The recovery link lands here with the token in the URL fragment; the
    # page's JS reads it and posts the new password to reset_password_submit.
    return render_template('reset_password.html')


@app.route('/reset-password', methods=['POST'])
@csrf.exempt
def reset_password_submit():
    data = request.get_json(silent=True) or request.form
    token = (data.get('access_token') or '').strip()
    new_password = data.get('password', '')
    if not token or len(new_password) < 8:
        return jsonify({'success': False, 'message': 'Invalid link or password too short (min 8 characters).'}), 400
    if not supabase_auth.enabled():
        return jsonify({'success': False, 'message': 'Password recovery is not available.'}), 400
    result = supabase_auth.update_password(token, new_password)
    if not result['ok']:
        return jsonify({'success': False, 'message': result.get('error') or 'Could not reset password. The link may have expired.'}), 400
    return jsonify({'success': True, 'message': 'Password updated. You can now log in.'})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Main Routes
@app.route('/')
def splash():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'), code=303)
    return render_template('splash.html')

@app.route('/dashboard')
@login_required
def dashboard():
    today = today_ist()
    
    # Get statistics
    total_workers = Worker.query.filter_by(status='active').count()
    present_today = AttendanceRecord.query.filter_by(
        date=today,
        status='present'
    ).count()
    
    # Today's attendance, most recent check-in first (absent/no-time rows last)
    recent_attendance = db.session.query(AttendanceRecord, Worker).join(
        Worker, AttendanceRecord.worker_id == Worker.id
    ).filter(AttendanceRecord.date == today).order_by(
        AttendanceRecord.check_in_time.desc().nullslast()
    ).limit(10).all()
    
    # Get upcoming closure days
    upcoming_closures = ClosureDay.query.filter(
        ClosureDay.date >= today
    ).order_by(ClosureDay.date).limit(5).all()
    
    return render_template('dashboard.html',
                         total_workers=total_workers,
                         present_today=present_today,
                         attendance_percentage=round((present_today/total_workers*100) if total_workers > 0 else 0, 1),
                         recent_attendance=recent_attendance,
                         upcoming_closures=upcoming_closures,
                         today=today)

@app.route('/workers')
@login_required
def workers():
    search = request.args.get('search', '')
    department = request.args.get('department', '')
    
    query = Worker.query.filter_by(status='active')
    
    if search:
        query = query.filter(
            db.or_(
                Worker.full_name.contains(search),
                Worker.worker_id.contains(search),
                Worker.phone.contains(search)
            )
        )
    
    if department:
        query = query.filter_by(department=department)
    
    # Paged. Rendering the whole roster produced a 15.8MB page at 5,000
    # workers and took 825ms server-side before the phone had drawn anything;
    # a supervisor scrolling for one name does not need the other 4,999.
    # Site-restricted users are filtered after the query, so the page is
    # filled to size rather than trusting the database count.
    page = max(1, parse_int(request.args.get('page'), 1))
    visible = []
    scanned = 0
    batch = WORKERS_PER_PAGE * 4
    ordered = query.order_by(Worker.full_name)
    while True:
        chunk = ordered.limit(batch).offset(scanned).all()
        if not chunk:
            break
        scanned += len(chunk)
        visible.extend(w for w in chunk if worker_visible_to_user(w, current_user))
        if len(visible) >= page * WORKERS_PER_PAGE + 1:
            break
        if len(chunk) < batch:
            break

    # A page past the end used to render the "No Workers Found" empty state —
    # "Start by adding your first worker to the system" on a roster of 58 —
    # and the pager is inside that same branch, so there was no Previous
    # link and no way back. Reachable by a stale bookmark, or by deleting
    # enough workers while standing on the last page. Land on the last real
    # page instead; somebody asking for page 9 of 2 wants the workers.
    if page > 1 and visible and (page - 1) * WORKERS_PER_PAGE >= len(visible):
        page = (len(visible) + WORKERS_PER_PAGE - 1) // WORKERS_PER_PAGE

    start = (page - 1) * WORKERS_PER_PAGE
    workers_list = visible[start:start + WORKERS_PER_PAGE]
    has_next = len(visible) > start + WORKERS_PER_PAGE
    departments = db.session.query(Worker.department).distinct().all()

    return render_template('workers.html',
                         workers=workers_list,
                         departments=[d[0] for d in departments],
                         search=search,
                         selected_department=department,
                         page=page,
                         has_next=has_next,
                         has_prev=page > 1,
                         shown_from=start + 1 if workers_list else 0,
                         shown_to=start + len(workers_list))

@app.route('/worker/<int:worker_id>')
@login_required
def worker_profile(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)

    if not worker_visible_to_user(worker, current_user):
        flash('Please contact the Administrator to make changes.', 'restricted')
        return redirect(url_for('attendance'))

    # Get recent attendance
    recent_attendance = AttendanceRecord.query.filter_by(
        worker_id=worker_id
    ).order_by(AttendanceRecord.date.desc()).limit(30).all()

    # Calculate statistics
    today = today_ist()
    this_month = today.replace(day=1)
    month_attendance = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker_id,
        AttendanceRecord.date >= this_month,
        AttendanceRecord.status == 'present'
    ).count()

    # Leave ledger (salaried workers)
    _, month_days = _cal.monthrange(today.year, today.month)
    leave_balance = None
    if worker.pay_type == 'monthly' and worker.leave_policy_enabled:
        leave_balance = calculate_leave_balance(worker, this_month, this_month.replace(day=month_days))

    recent_transactions = WorkerTransaction.query.filter_by(
        worker_id=worker_id, status='active'
    ).order_by(WorkerTransaction.date.desc()).limit(10).all()

    projects = Project.query.filter(Project.status != 'archived').order_by(Project.name).all()
    sites = Site.query.filter_by(status='active').order_by(Site.name).all()
    tasks = WorkTask.query.filter(WorkTask.status != 'archived').order_by(WorkTask.name).all()

    # Salary policy pane: only meaningful for a fixed monthly salary, and the
    # screen needs to say whether this worker departs from the company rule.
    salary_override = SalaryPolicy.query.filter_by(worker_id=worker.id).first()
    effective_policy = resolve_salary_policy(worker)
    salary_preview = None
    if worker.pay_type == 'monthly':
        _today = today_ist()
        _ps = date(_today.year, _today.month, 1)
        _pe = date(_today.year, _today.month,
                   _cal.monthrange(_today.year, _today.month)[1])
        _recs = AttendanceRecord.query.filter(
            AttendanceRecord.worker_id == worker.id,
            AttendanceRecord.date >= _ps, AttendanceRecord.date <= _pe).all()
        _bal = calculate_leave_balance(worker, _ps, _pe)
        salary_preview = salary.compute(worker, effective_policy, _recs, _ps, _pe,
                                        carried_leave_balance=_bal['balance_before'])

    return render_template('worker_profile.html',
                         worker=worker,
                         worker_login=User.query.filter_by(
                             worker_id=worker.id, role='worker').first(),
                         salary_override=salary_override,
                         effective_policy=effective_policy,
                         effective_policy_rows=salary.describe(effective_policy),
                         salary_preview=salary_preview,
                         salary_labels=salary.LABELS,
                         recent_attendance=recent_attendance,
                         month_attendance=month_attendance,
                         leave_balance=leave_balance,
                         recent_transactions=recent_transactions,
                         projects=projects,
                         sites=sites,
                         tasks=tasks,
                         txn_earning_types=TRANSACTION_EARNING_TYPES,
                         txn_deduction_types=TRANSACTION_DEDUCTION_TYPES)

def generate_worker_id(department):
    """Next free employee ID for this department, within this workspace.

    IDs are unique per workspace (see the composite constraint on Worker), so
    the scan below runs through the tenant filter and two workspaces can both
    hold a CI001. Malformed legacy IDs are skipped rather than resetting the
    sequence to 1 and colliding.
    """
    dept_prefix = (department or 'GN')[:2].upper()
    taken = {
        w.worker_id for w in
        Worker.query.filter(Worker.worker_id.like(f'{dept_prefix}%')).all()
    }

    next_num = 1
    for worker_id in taken:
        try:
            next_num = max(next_num, int(worker_id[2:]) + 1)
        except (ValueError, TypeError):
            continue

    candidate = f"{dept_prefix}{next_num:03d}"
    while candidate in taken:
        next_num += 1
        candidate = f"{dept_prefix}{next_num:03d}"
    return candidate

def generate_qr_code(worker_id):
    """Generate QR code for worker"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(f"SMARTWORKER:{worker_id}")
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 string
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def calculate_attendance_summary(attendance_records):
    summary = {
        'present_days': 0,
        'absent_days': 0,
        'late_days': 0,
        'leave_days': 0,
        'total_marked_days': 0,
    }
    for record in attendance_records:
        if record.status == 'present':
            summary['present_days'] += 1
        elif record.status == 'absent':
            summary['absent_days'] += 1
        elif record.status == 'late':
            summary['late_days'] += 1
        elif record.status == 'leave':
            summary['leave_days'] += 1
    summary['total_marked_days'] = (
        summary['present_days']
        + summary['absent_days']
        + summary['late_days']
        + summary['leave_days']
    )
    return summary

def _attendance_closures_in_period(period_start, period_end):
    """Closure days that still allow attendance, cached per request.

    Payroll asks for this once per worker with the same month boundaries every
    time, so the cache turns a per-worker query into a single one.
    """
    cache = getattr(g, '_closure_period_cache', None)
    if cache is None:
        cache = g._closure_period_cache = {}
    key = (period_start, period_end)
    if key not in cache:
        cache[key] = ClosureDay.query.filter(
            ClosureDay.date >= period_start,
            ClosureDay.date <= period_end,
            ClosureDay.allow_attendance == True,
        ).all()
    return cache[key]


def resolve_salary_policy(worker):
    """The salary policy in force for one worker, cached per request.

    Company default plus any per-worker override. Payroll asks for this once
    per worker, and the company row is the same for all of them, so both
    lookups are cached for the life of the request.
    """
    if not has_app_context():
        return salary.normalise_policy(None)

    cache = getattr(g, '_salary_policy_cache', None)
    if cache is None:
        cache = g._salary_policy_cache = {}

    if 'company' not in cache:
        # One query loads the company default and every per-worker override at
        # once. Looking each override up on demand cost one query per monthly
        # worker, which measured as 179 queries on a 500-worker payroll run.
        cache['company'] = None
        for row in SalaryPolicy.query.all():
            if row.worker_id is None:
                cache['company'] = row
            else:
                cache[('worker', row.worker_id)] = row

    key = ('worker', worker.id)
    override = cache.get(key)

    company = cache['company']
    if company is None:
        # No company policy configured yet: start from what this worker's own
        # record already says, so switching the feature on does not re-rate
        # anybody. Once an employer saves a company policy, that wins.
        base = salary.seed_from_worker(worker)
    else:
        base = company
    return salary.resolve_policy(worker, base, override)


def calculate_pay_summary(worker, attendance_records, period_start=None, period_end=None):
    # Derive the payroll month when the caller doesn't pass it explicitly.
    if period_start is None or period_end is None:
        if attendance_records:
            anchor = min(r.date for r in attendance_records)
        else:
            anchor = today_ist()
        period_start = anchor.replace(day=1)
        _, _pdays = _cal.monthrange(period_start.year, period_start.month)
        period_end = period_start.replace(day=_pdays)

    attendance_summary = calculate_attendance_summary(attendance_records)
    present_days = attendance_summary['present_days']
    absent_days = attendance_summary['absent_days']
    late_days = attendance_summary['late_days']
    leave_days = attendance_summary['leave_days']
    paid_days = present_days + late_days
    
    overtime_minutes = sum(max(record.overtime_minutes or 0, 0) for record in attendance_records)
    overtime_units = 0.0
    overtime_pay = 0.0
    if worker.overtime_enabled and worker.overtime_rate and overtime_minutes > 0:
        if worker.overtime_type == 'minute':
            overtime_units = float(overtime_minutes)
        else:
            overtime_units = overtime_minutes / 60.0
        overtime_pay = overtime_units * float(worker.overtime_rate)
    
    worked_minutes = 0
    late_minutes = 0
    for record in attendance_records:
        if record.status not in ('present', 'late'):
            continue
        if not record.check_in_time or not record.check_out_time:
            continue
        if record.check_out_time <= record.check_in_time:
            continue
        worked_minutes += int((record.check_out_time - record.check_in_time).total_seconds() // 60)
        late_minutes += calculate_late_minutes_for_record(worker, record)
    
    base_pay = 0.0
    deductions = 0.0
    leave_deductions = 0.0
    late_deductions = 0.0
    late_units = 0.0
    late_unit_label = 'day'
    half_day_days = 0
    full_day_days = 0
    prorated_days = 0
    paid_absent_days = 0
    extra_leave_days = 0
    policy_notes = []
    
    if worker.pay_type == 'daily':
        daily_rate = float(worker.daily_rate or 0)
        grace_minutes = get_half_day_grace_minutes(worker)

        for record in attendance_records:
            if record.status not in ('present', 'late'):
                continue

            day_pay, pay_mode = calculate_daily_wage_for_record(worker, record)
            base_pay += day_pay

            if pay_mode == 'half_day':
                half_day_days += 1
            elif pay_mode == 'pro_rata':
                prorated_days += 1
            else:
                full_day_days += 1

        if not worker.no_work_no_pay and absent_days > 0:
            paid_absent_days = absent_days
            base_pay += daily_rate * absent_days
            policy_notes.append('Absent days are paid because no-work-no-pay is disabled.')
        elif absent_days > 0:
            policy_notes.append('No-work-no-pay applied for absent days.')

        if half_day_days > 0:
            policy_notes.append(
                f'Half-day rate applied for {half_day_days} day(s) '
                f'(half-shift + {grace_minutes} min grace window).'
            )
        if prorated_days > 0:
            policy_notes.append(
                f'Pro-rata minute-based daily wage applied for {prorated_days} day(s) after grace window.'
            )
    leave_balance = None
    if worker.pay_type == 'monthly' and worker.leave_policy_enabled:
        leave_balance = calculate_leave_balance(worker, period_start, period_end)

    salary_breakdown = None
    if worker.pay_type == 'monthly':
        # The configurable engine in salary.py owns this calculation now. It
        # derives a daily rate from the salary, honours the joining date, and
        # applies the employer's own absence and paid-leave rules. With the
        # default policy (absence deduction off) it pays the full monthly
        # salary, which is what this branch did before, so no existing
        # worker's pay changes until an employer turns a rule on.
        policy = resolve_salary_policy(worker)
        carried = leave_balance['balance_before'] if leave_balance else 0.0
        salary_breakdown = salary.compute(
            worker, policy, attendance_records, period_start, period_end,
            carried_leave_balance=carried)

        base_pay = salary_breakdown['gross_eligible_salary']
        leave_deductions = salary_breakdown['deduction_amount']
        extra_leave_days = salary_breakdown['deduction_days']
        policy_notes.extend(salary_breakdown['explanation'])
    elif worker.pay_type == 'hourly':
        base_pay = (worked_minutes / 60.0) * float(worker.hourly_rate or 0)
        policy_notes.append('Hourly wage is based on check-in/check-out duration.')
    elif worker.pay_type == 'project':
        base_pay = float(worker.project_rate or 0)
        policy_notes.append('Project rate is fixed for the period.')

    if worker.late_policy_enabled and worker.late_deduction_per_day is not None:
        late_deduction_type = (worker.late_deduction_type or 'day').lower()
        if late_deduction_type == 'minute':
            late_units = float(late_minutes)
            late_unit_label = 'minute'
        elif late_deduction_type == 'hour':
            late_units = late_minutes / 60.0
            late_unit_label = 'hour'
        else:
            late_units = float(late_days)
            late_unit_label = 'day'

        late_deductions = late_units * float(worker.late_deduction_per_day or 0)
        if late_deductions > 0:
            policy_notes.append(f'Late policy deduction applied per {late_unit_label}.')

    deductions = leave_deductions + late_deductions
    if overtime_pay > 0:
        policy_notes.append('Overtime policy added extra pay.')

    # Closure day extra pay
    closure_extra_pay = 0.0
    closure_day_breakdown = []  # [{'date': date, 'reason': str, 'amount': float}]
    if getattr(worker, 'closure_extra_pay_enabled', False) and attendance_records:
        closure_records_list = _attendance_closures_in_period(period_start, period_end)
        closure_day_info = {
            c.date: c.reason for c in closure_records_list
            if closure_applies_to_worker(c, worker)
        }
        if closure_day_info:
            pct = float(getattr(worker, 'closure_extra_percentage', 0) or 0) / 100.0
            method = (getattr(worker, 'closure_calculation_method', 'daily_percent') or 'daily_percent')
            mwd = int(getattr(worker, 'monthly_working_days', 26) or 26) or 26
            swh = int(getattr(worker, 'standard_working_hours', 8) or 8) or 8

            if worker.pay_type == 'daily':
                _daily_base = float(worker.daily_rate or 0)
            elif worker.pay_type == 'monthly':
                _daily_base = float(worker.monthly_salary or 0) / mwd
            elif worker.pay_type == 'hourly':
                _daily_base = float(worker.hourly_rate or 0) * swh
            else:
                _daily_base = 0.0

            _hourly_base = _daily_base / swh if swh else 0.0
            _minute_base = _hourly_base / 60.0

            for record in attendance_records:
                if record.date not in closure_day_info:
                    continue
                if record.status not in ('present', 'late'):
                    continue
                day_bonus = 0.0
                if method == 'daily_percent':
                    if worker.pay_type == 'daily':
                        day_pay, _ = calculate_daily_wage_for_record(worker, record)
                    else:
                        day_pay = _daily_base
                    day_bonus = day_pay * pct
                else:
                    if record.check_in_time and record.check_out_time and record.check_out_time > record.check_in_time:
                        rec_mins = int((record.check_out_time - record.check_in_time).total_seconds() // 60)
                    else:
                        rec_mins = swh * 60
                    if method == 'hourly_percent':
                        day_bonus = (rec_mins / 60.0) * _hourly_base * pct
                    else:
                        day_bonus = rec_mins * _minute_base * pct
                if day_bonus > 0:
                    closure_extra_pay += day_bonus
                    closure_day_breakdown.append({
                        'date': record.date,
                        'reason': closure_day_info[record.date],
                        'amount': round(day_bonus, 2),
                    })

            if closure_extra_pay > 0:
                policy_notes.append(
                    f'Closure day extra pay ({getattr(worker, "closure_extra_percentage", 0)}% via {method.replace("_", " ")}) applied.'
                )

    base_pay += closure_extra_pay

    # Transactions (advances, loans, bonuses, recoveries, ...) for this period
    period_transactions = get_period_transactions(worker, period_start, period_end)
    transaction_earnings = sum(t.amount for t in period_transactions if t.is_earning)
    transaction_deductions = sum(t.amount for t in period_transactions if not t.is_earning)
    if transaction_earnings > 0:
        policy_notes.append('Bonus/extra payment transactions added to pay.')
    if transaction_deductions > 0:
        policy_notes.append('Advance/loan/deduction transactions recovered from pay.')

    # Project delay penalty
    delay_penalty, delay_breakdown = calculate_delay_penalty(worker, period_start, period_end)
    if delay_penalty > 0:
        policy_notes.append('Project delay penalty applied.')

    deductions = leave_deductions + late_deductions + delay_penalty
    estimated_pay = base_pay + overtime_pay + transaction_earnings - deductions - transaction_deductions
    policy_note = ' '.join(policy_notes)

    return {
        'pay_type': worker.pay_type,
        'base_pay': round(base_pay, 2),
        'overtime_pay': round(overtime_pay, 2),
        'leave_deductions': round(leave_deductions, 2),
        'late_deductions': round(late_deductions, 2),
        'delay_penalty': delay_penalty,
        'delay_breakdown': delay_breakdown,
        'transaction_earnings': round(transaction_earnings, 2),
        'transaction_deductions': round(transaction_deductions, 2),
        'transactions': period_transactions,
        'leave_balance': leave_balance,
        'salary_breakdown': salary_breakdown,
        'deductions': round(deductions, 2),
        'estimated_pay': round(estimated_pay, 2),
        'paid_days': paid_days,
        'full_day_days': full_day_days,
        'half_day_days': half_day_days,
        'prorated_days': prorated_days,
        'paid_absent_days': paid_absent_days,
        'half_day_grace_minutes': get_half_day_grace_minutes(worker),
        'worked_minutes': worked_minutes,
        'overtime_minutes': overtime_minutes,
        'overtime_units': round(overtime_units, 2),
        'late_minutes': late_minutes,
        'late_units': round(late_units, 2),
        'late_unit_label': late_unit_label,
        'leave_days': leave_days,
        'extra_leave_days': extra_leave_days,
        'policy_note': policy_note,
        'closure_extra_pay': round(closure_extra_pay, 2),
        'closure_day_breakdown': closure_day_breakdown,
    }

@app.route('/add_worker', methods=['GET', 'POST'])
@admin_required
def add_worker():
    if request.method == 'POST':
        # Generate worker ID
        worker_id = generate_worker_id(request.form.get('department') or 'GEN')
        
        # Create new worker
        worker = Worker()
        worker.worker_id = worker_id
        worker.full_name = clean_text(request.form.get('full_name'), 'full_name')
        worker.phone = clean_text(request.form.get('phone'), 'phone')
        worker.email = clean_text(request.form.get('email'), 'email') or None
        worker.address = (request.form.get('address') or '').strip() or None
        worker.position = clean_text(request.form.get('position'), 'position')
        worker.department = clean_text(request.form.get('department'), 'department')
        worker.employee_type = clean_text(request.form.get('employee_type'), 'employee_type')
        missing = [label for label, value in (
            ('name', worker.full_name), ('phone', worker.phone),
            ('position', worker.position), ('department', worker.department)) if not value]
        if missing:
            flash('Please fill in the ' + ', '.join(missing) + '.', 'error')
            return redirect(request.url)
        join_date = parse_date_or(request.form.get('join_date'))
        if not join_date:
            flash('Enter a valid joining date.', 'error')
            return redirect(request.url)
        worker.join_date = join_date
        worker.pay_type = request.form.get('pay_type') or 'daily'
        
        # Reset policy fields before applying selected pay-type policy.
        worker.daily_rate = None
        worker.monthly_salary = None
        worker.hourly_rate = None
        worker.project_rate = None
        worker.start_time = None
        worker.end_time = None
        worker.break_duration = 0
        worker.allowed_leaves_per_month = 2
        worker.leave_deduction_per_day = None
        worker.leave_policy_enabled = False
        worker.overtime_enabled = False
        worker.overtime_rate = None
        worker.overtime_type = 'hour'
        worker.late_policy_enabled = False
        worker.late_deduction_per_day = None
        worker.late_deduction_type = 'day'
        worker.no_work_no_pay = True
        worker.half_day_rate = None
        worker.half_day_grace_minutes = 20
        
        # Set payment details based on pay type
        if worker.pay_type == 'daily':
            worker.daily_rate, rate_error = clean_rate(request.form.get('daily_rate'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)
            # Both fields were reset to None above, so an absent or
            # unparseable time simply leaves the shift unset rather
            # than raising.
            worker.start_time = parse_time_or(request.form.get('start_time'))
            worker.end_time = parse_time_or(request.form.get('end_time'))

            worker.overtime_enabled = 'overtime_enabled' in request.form
            if worker.overtime_enabled and request.form.get('overtime_rate'):
                worker.overtime_rate = parse_float(request.form.get('overtime_rate'))
                worker.overtime_type = request.form.get('overtime_type', 'hour')

            worker.late_policy_enabled = 'late_policy_enabled' in request.form
            if worker.late_policy_enabled and request.form.get('late_deduction'):
                worker.late_deduction_per_day = parse_float(request.form.get('late_deduction'))
            selected_late_type = request.form.get('late_deduction_type', 'day')
            worker.late_deduction_type = selected_late_type if selected_late_type in ('day', 'hour', 'minute') else 'day'
            worker.no_work_no_pay = 'no_work_no_pay' in request.form
            if request.form.get('half_day_rate'):
                worker.half_day_rate = parse_float(request.form.get('half_day_rate'))
            else:
                worker.half_day_rate = parse_float(worker.daily_rate) / 2.0 if worker.daily_rate else 0.0
            worker.half_day_grace_minutes = min(max(parse_int(request.form.get('half_day_grace_minutes'), 20), 15), 25)
        elif worker.pay_type == 'monthly':
            worker.monthly_salary, rate_error = clean_rate(request.form.get('monthly_salary'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)
            worker.monthly_working_days = parse_int(request.form.get('monthly_working_days'), 26)
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
            worker.allowed_leaves_per_month = parse_int(request.form.get('allowed_leaves'), 2)
            if request.form.get('leave_deduction'):
                worker.leave_deduction_per_day = parse_float(request.form.get('leave_deduction'))
            worker.leave_policy_enabled = 'leave_policy_enabled' in request.form
            # Both fields were reset to None above, so an absent or
            # unparseable time simply leaves the shift unset rather
            # than raising.
            worker.start_time = parse_time_or(request.form.get('start_time'))
            worker.end_time = parse_time_or(request.form.get('end_time'))
            worker.no_work_no_pay = 'no_work_no_pay' in request.form
            if request.form.get('half_day_rate'):
                worker.half_day_rate = parse_float(request.form.get('half_day_rate'))
            worker.half_day_grace_minutes = min(max(parse_int(request.form.get('half_day_grace_minutes'), 20), 15), 25)
            worker.overtime_enabled = 'overtime_enabled' in request.form
            if worker.overtime_enabled and request.form.get('overtime_rate'):
                worker.overtime_rate = parse_float(request.form.get('overtime_rate'))
                worker.overtime_type = request.form.get('overtime_type', 'hour')
            worker.late_policy_enabled = 'late_policy_enabled' in request.form
            if worker.late_policy_enabled and request.form.get('late_deduction'):
                worker.late_deduction_per_day = parse_float(request.form.get('late_deduction'))
            selected_late_type = request.form.get('late_deduction_type', 'day')
            worker.late_deduction_type = selected_late_type if selected_late_type in ('day', 'hour', 'minute') else 'day'
            # Closure day extra pay settings (monthly only)
            worker.closure_extra_pay_enabled = 'closure_extra_pay_enabled' in request.form
            raw_method = request.form.get('closure_calculation_method', 'daily_percent')
            worker.closure_calculation_method = raw_method if raw_method in ('daily_percent', 'hourly_percent', 'minute_percent') else 'daily_percent'
            worker.closure_extra_percentage = max(0.0, parse_float(request.form.get('closure_extra_percentage', '0')) or 0.0)
        elif worker.pay_type == 'hourly':
            worker.hourly_rate, rate_error = clean_rate(request.form.get('hourly_rate'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
        elif worker.pay_type == 'project':
            worker.project_rate, rate_error = clean_rate(request.form.get('project_rate'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)

        # Optional profile photo upload
        profile_image = request.files.get('profile_image')
        if profile_image and profile_image.filename:
            try:
                worker.profile_image = save_worker_profile_image(profile_image, worker_id)
            except ValueError as exc:
                flash(str(exc), 'error')
                return redirect(url_for('add_worker'))
        
        # Generate QR code
        worker.qr_code = generate_qr_code(worker_id)
        
        db.session.add(worker)

        # Payment details: optional, format-checked. A bad format is
        # reported and that one field left unset rather than losing the
        # whole save.
        for payment_error in apply_payment_details(worker, request.form):
            flash(payment_error, 'error')
        db.session.commit()
        
        flash(f'Worker {worker.full_name} added successfully with ID: {worker_id}', 'success')
        # A worker with no rate is accepted on purpose (the rate may not be
        # agreed yet) but they would earn nothing, so say so rather than
        # letting it pass in silence.
        if not worker.has_pay_rate:
            flash(f'{worker.full_name} has no pay rate yet, so payroll will '
                  f'show ₹0 for them until one is set.', 'warning')

        return redirect(url_for('workers'))
    
    return render_template('edit_worker.html', worker=None)

WORKER_TRACKED_FIELDS = (
    ('position', 'Designation'),
    ('department', 'Department'),
    ('employee_type', 'Worker Category'),
    ('pay_type', 'Pay Type'),
    ('daily_rate', 'Daily Rate'),
    ('monthly_salary', 'Monthly Salary'),
    ('hourly_rate', 'Hourly Rate'),
    ('project_rate', 'Project Rate'),
    ('allowed_leaves_per_month', 'Allowed Leaves / Month'),
)

def log_worker_changes(worker, before_values):
    """Write a permanent WorkerModification row for each tracked field change."""
    for field, label in WORKER_TRACKED_FIELDS:
        old = before_values.get(field)
        new = getattr(worker, field)
        if str(old if old is not None else '') == str(new if new is not None else ''):
            continue
        if field in ('pay_type', 'employee_type'):
            mod_type = 'category_change'
        elif field == 'position':
            mod_type = 'promotion' if before_values.get('position') else 'profile_edit'
        elif field in ('daily_rate', 'monthly_salary', 'hourly_rate', 'project_rate'):
            mod_type = 'salary_change'
        else:
            mod_type = 'profile_edit'
        db.session.add(WorkerModification(
            worker_id=worker.id,
            mod_type=mod_type,
            field_name=label,
            old_value=str(old) if old is not None else None,
            new_value=str(new) if new is not None else None,
            description=f'{label} changed',
            effective_date=today_ist(),
            created_by=current_user.id,
        ))

@app.route('/edit_worker/<int:worker_id>', methods=['GET', 'POST'])
@admin_required
def edit_worker(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)

    if request.method == 'POST':
        before_values = {field: getattr(worker, field) for field, _ in WORKER_TRACKED_FIELDS}
        # Update worker details
        worker.full_name = clean_text(request.form.get('full_name'), 'full_name')
        worker.phone = clean_text(request.form.get('phone'), 'phone')
        worker.email = clean_text(request.form.get('email'), 'email') or None
        worker.address = (request.form.get('address') or '').strip() or None
        worker.position = clean_text(request.form.get('position'), 'position')
        worker.department = clean_text(request.form.get('department'), 'department')
        worker.employee_type = clean_text(request.form.get('employee_type'), 'employee_type')
        missing = [label for label, value in (
            ('name', worker.full_name), ('phone', worker.phone),
            ('position', worker.position), ('department', worker.department)) if not value]
        if missing:
            flash('Please fill in the ' + ', '.join(missing) + '.', 'error')
            return redirect(request.url)
        join_date = parse_date_or(request.form.get('join_date'))
        if not join_date:
            flash('Enter a valid joining date.', 'error')
            return redirect(request.url)
        worker.join_date = join_date
        worker.pay_type = request.form.get('pay_type') or 'daily'
        
        # Reset policy fields before applying selected pay-type policy.
        worker.daily_rate = None
        worker.monthly_salary = None
        worker.hourly_rate = None
        worker.project_rate = None
        worker.start_time = None
        worker.end_time = None
        worker.break_duration = 0
        worker.allowed_leaves_per_month = 2
        worker.leave_deduction_per_day = None
        worker.leave_policy_enabled = False
        worker.overtime_enabled = False
        worker.overtime_rate = None
        worker.overtime_type = 'hour'
        worker.late_policy_enabled = False
        worker.late_deduction_per_day = None
        worker.late_deduction_type = 'day'
        worker.no_work_no_pay = True
        worker.half_day_rate = None
        worker.half_day_grace_minutes = 20
        
        # Update payment details based on pay type
        if worker.pay_type == 'daily':
            worker.daily_rate, rate_error = clean_rate(request.form.get('daily_rate'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)
            # Both fields were reset to None above, so an absent or
            # unparseable time simply leaves the shift unset rather
            # than raising.
            worker.start_time = parse_time_or(request.form.get('start_time'))
            worker.end_time = parse_time_or(request.form.get('end_time'))

            worker.overtime_enabled = 'overtime_enabled' in request.form
            if worker.overtime_enabled and request.form.get('overtime_rate'):
                worker.overtime_rate = parse_float(request.form.get('overtime_rate'))
                worker.overtime_type = request.form.get('overtime_type', 'hour')

            worker.late_policy_enabled = 'late_policy_enabled' in request.form
            if worker.late_policy_enabled and request.form.get('late_deduction'):
                worker.late_deduction_per_day = parse_float(request.form.get('late_deduction'))
            selected_late_type = request.form.get('late_deduction_type', 'day')
            worker.late_deduction_type = selected_late_type if selected_late_type in ('day', 'hour', 'minute') else 'day'
            worker.no_work_no_pay = 'no_work_no_pay' in request.form
            if request.form.get('half_day_rate'):
                worker.half_day_rate = parse_float(request.form.get('half_day_rate'))
            else:
                worker.half_day_rate = parse_float(worker.daily_rate) / 2.0 if worker.daily_rate else 0.0
            worker.half_day_grace_minutes = min(max(parse_int(request.form.get('half_day_grace_minutes'), 20), 15), 25)
        elif worker.pay_type == 'monthly':
            worker.monthly_salary, rate_error = clean_rate(request.form.get('monthly_salary'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)
            worker.monthly_working_days = parse_int(request.form.get('monthly_working_days'), 26)
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
            worker.allowed_leaves_per_month = parse_int(request.form.get('allowed_leaves'), 2)
            if request.form.get('leave_deduction'):
                worker.leave_deduction_per_day = parse_float(request.form.get('leave_deduction'))
            worker.leave_policy_enabled = 'leave_policy_enabled' in request.form
            # Both fields were reset to None above, so an absent or
            # unparseable time simply leaves the shift unset rather
            # than raising.
            worker.start_time = parse_time_or(request.form.get('start_time'))
            worker.end_time = parse_time_or(request.form.get('end_time'))
            worker.no_work_no_pay = 'no_work_no_pay' in request.form
            if request.form.get('half_day_rate'):
                worker.half_day_rate = parse_float(request.form.get('half_day_rate'))
            worker.half_day_grace_minutes = min(max(parse_int(request.form.get('half_day_grace_minutes'), 20), 15), 25)
            worker.overtime_enabled = 'overtime_enabled' in request.form
            if worker.overtime_enabled and request.form.get('overtime_rate'):
                worker.overtime_rate = parse_float(request.form.get('overtime_rate'))
                worker.overtime_type = request.form.get('overtime_type', 'hour')
            worker.late_policy_enabled = 'late_policy_enabled' in request.form
            if worker.late_policy_enabled and request.form.get('late_deduction'):
                worker.late_deduction_per_day = parse_float(request.form.get('late_deduction'))
            selected_late_type = request.form.get('late_deduction_type', 'day')
            worker.late_deduction_type = selected_late_type if selected_late_type in ('day', 'hour', 'minute') else 'day'
            # Closure day extra pay settings (monthly only)
            worker.closure_extra_pay_enabled = 'closure_extra_pay_enabled' in request.form
            raw_method = request.form.get('closure_calculation_method', 'daily_percent')
            worker.closure_calculation_method = raw_method if raw_method in ('daily_percent', 'hourly_percent', 'minute_percent') else 'daily_percent'
            worker.closure_extra_percentage = max(0.0, parse_float(request.form.get('closure_extra_percentage', '0')) or 0.0)
        elif worker.pay_type == 'hourly':
            worker.hourly_rate, rate_error = clean_rate(request.form.get('hourly_rate'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
        elif worker.pay_type == 'project':
            worker.project_rate, rate_error = clean_rate(request.form.get('project_rate'))
            if rate_error:
                flash(rate_error, 'error')
                return redirect(request.url)

        # Optional profile photo upload (replaces existing photo)
        profile_image = request.files.get('profile_image')
        if profile_image and profile_image.filename:
            try:
                worker.profile_image = save_worker_profile_image(profile_image, worker.worker_id)
            except ValueError as exc:
                flash(str(exc), 'error')
                return redirect(url_for('edit_worker', worker_id=worker_id))
        
        worker.updated_at = now_ist()

        log_worker_changes(worker, before_values)

        # Payment details: optional, format-checked. A bad format is
        # reported and that one field left unset rather than losing the
        # whole save.
        for payment_error in apply_payment_details(worker, request.form):
            flash(payment_error, 'error')
        db.session.commit()
        flash(f'Worker {worker.full_name} updated successfully', 'success')
        # A worker with no rate is accepted on purpose (the rate may not be
        # agreed yet) but they would earn nothing, so say so rather than
        # letting it pass in silence.
        if not worker.has_pay_rate:
            flash(f'{worker.full_name} has no pay rate yet, so payroll will '
                  f'show ₹0 for them until one is set.', 'warning')

        return redirect(url_for('worker_profile', worker_id=worker_id))

    return render_template('edit_worker.html', worker=worker)

@app.route('/attendance')
@login_required
def attendance():
    # A bad ?date= (stale bookmark, hand-edited URL) must not take the screen
    # down — fall back to today rather than raising.
    selected_date = parse_date_or(request.args.get('date'), today_ist())
    site_filter = parse_int(request.args.get('site'), 0)
    marker_filter = parse_int(request.args.get('marked_by'), 0)
    search = (request.args.get('search') or '').strip().lower()

    # Get all workers and their attendance for the selected date.
    # Paged: rendering every worker took 8.6s on a 5,000-worker roster. The
    # counters above come from _scan_stats, which works over the whole
    # visible set, so paging the list below does not change any number the
    # user reads — and bulk actions run server-side over everyone, not over
    # the page.
    page = max(1, parse_int(request.args.get('page'), 1))
    workers = roster_query().all()
    closures_today = ClosureDay.query.filter_by(date=selected_date).all()

    # One query for the whole day's records instead of one per worker.
    records_today = {}
    if workers:
        records_today = {
            r.worker_id: r
            for r in AttendanceRecord.query.filter(
                AttendanceRecord.date == selected_date,
                AttendanceRecord.worker_id.in_([w.id for w in workers]),
            ).all()
        }

    attendance_data = []
    visible_rows = []

    for worker in workers:
        # Attendance users only see workers on their assigned sites/projects
        if not worker_visible_to_user(worker, current_user, on_date=selected_date):
            continue

        # Resolve the assignment active on the viewed date so historical
        # filtering/display reflects where the worker was then, not today.
        assignment = next((a for a in worker.assignments if assignment_active_on(a, selected_date)), None)
        if site_filter and (not assignment or assignment.site_id != site_filter):
            continue

        if search and search not in worker.full_name.lower() and search not in worker.worker_id.lower():
            continue

        attendance = records_today.get(worker.id)

        if marker_filter and (not attendance or attendance.marked_by != marker_filter):
            continue

        # Only the filters run for every worker. Wage, overtime and the
        # status line are worked out after the slice below, so a 5,000-worker
        # roster costs fifty calculations rather than five thousand.
        visible_rows.append((worker, attendance, assignment))

    total_rows = len(visible_rows)
    start = (page - 1) * ATTENDANCE_PER_PAGE
    page_rows = visible_rows[start:start + ATTENDANCE_PER_PAGE]

    for worker, attendance, assignment in page_rows:
        wage = 0.0
        pay_mode = 'none'
        overtime_pay = 0.0
        if attendance:
            wage, pay_mode = calculate_daily_wage_for_record(worker, attendance)
            # calculate overtime pay if any
            if worker.overtime_enabled and worker.overtime_rate and attendance.overtime_minutes:
                if worker.overtime_type == 'minute':
                    units = float(attendance.overtime_minutes)
                else:
                    units = attendance.overtime_minutes / 60.0
                overtime_pay = units * float(worker.overtime_rate)

        attendance_data.append({
            'worker': worker,
            'attendance': attendance,
            'assignment': assignment,
            'closure': closure_for_worker_on_date(worker, selected_date, closures_today),
            'wage': wage,
            'pay_mode': pay_mode,
            'overtime_pay': overtime_pay,
            # Single combined status line, built by the same helper the API
            # uses, so server render and in-place updates can't drift.
            'meta': attendance_row_meta(worker, attendance),
        })

    # Company-wide closure banner (per-worker closures shown inline)
    closure = next((c for c in closures_today if c.scope in (None, '', 'company')), None)

    sites = Site.query.filter_by(status='active').order_by(Site.name).all()
    attendance_users = User.query.filter(User.role == 'attendance', User.account_id == current_user.account_id).order_by(User.full_name).all()

    # Month grid for the interactive calendar, keyed by day-of-month like the
    # other calendar hosts. Records/closures for the *whole* month, not just
    # the selected day, so the grid is colour-coded before anything is clicked.
    month_start = selected_date.replace(day=1)
    month_end = date(selected_date.year, selected_date.month,
                     _cal.monthrange(selected_date.year, selected_date.month)[1])
    visible_ids = [w.id for w in _visible_active_workers(selected_date)]
    # The grid only needs one status per day, and the partial reads nothing
    # but `.status` off it. Loading every record to work that out meant
    # hydrating 155,000 ORM objects on a 5,000-worker month — which was the
    # single biggest cost on this screen. Let the database reduce it instead:
    # at most one row per (day, status).
    _priority = {'present': 3, 'late': 2, 'leave': 1, 'absent': 0}
    calendar_data = {}
    if visible_ids:
        day_statuses = db.session.query(
            AttendanceRecord.date, AttendanceRecord.status
        ).filter(
            AttendanceRecord.date >= month_start,
            AttendanceRecord.date <= month_end,
            AttendanceRecord.worker_id.in_(visible_ids),
        ).group_by(AttendanceRecord.date, AttendanceRecord.status).all()

        best_rank = {}
        for rec_date, status in day_statuses:
            rank = _priority.get(status, -1)
            if rec_date.day not in best_rank or rank > best_rank[rec_date.day]:
                best_rank[rec_date.day] = rank
                calendar_data[rec_date.day] = CalendarDay(status)
    closure_days = {
        c.date.day: c for c in ClosureDay.query.filter(
            ClosureDay.date >= month_start, ClosureDay.date <= month_end).all()
    }

    return render_template('attendance.html',
                         attendance_data=attendance_data,
                         page=page,
                         has_prev=page > 1,
                         has_next=start + ATTENDANCE_PER_PAGE < total_rows,
                         shown_from=start + 1 if attendance_data else 0,
                         shown_to=start + len(attendance_data),
                         total_rows=total_rows,
                         selected_date=selected_date,
                         today=today_ist(),
                         stats=_scan_stats(selected_date),
                         calendar_data=calendar_data,
                         closure_days=closure_days,
                         month_start=month_start,
                         closure=closure,
                         sites=sites,
                         attendance_users=attendance_users,
                         site_filter=site_filter,
                         marker_filter=marker_filter,
                         search=search,
                         timedelta=timedelta)

@app.route('/closures', methods=['GET', 'POST'])
@admin_required
def closures():
    if request.method == 'POST':
        closure_date = parse_date_or(request.form.get('date'))
        if not closure_date:
            flash('Enter a valid closure date.', 'error')
            return redirect(url_for('closures'))
        reason = request.form['reason'].strip()
        closure_type = request.form.get('type', 'holiday').strip().lower()
        allow_attendance = 'allow_attendance' in request.form
        scope = request.form.get('scope', 'company')
        if scope not in ('company', 'site', 'project'):
            scope = 'company'
        site_id = parse_int(request.form.get('site_id'), 0) or None
        project_id = parse_int(request.form.get('project_id'), 0) or None
        if scope == 'site' and not site_id:
            scope = 'company'
        if scope == 'project' and not project_id:
            scope = 'company'
        if scope != 'site':
            site_id = None
        if scope != 'project':
            project_id = None

        existing = ClosureDay.query.filter_by(
            date=closure_date, scope=scope, site_id=site_id, project_id=project_id
        ).first()
        if existing:
            existing.reason = reason
            existing.type = closure_type
            existing.allow_attendance = allow_attendance
            flash('Closure day updated successfully', 'success')
        else:
            closure = ClosureDay()
            closure.date = closure_date
            closure.reason = reason
            closure.type = closure_type
            closure.scope = scope
            closure.site_id = site_id
            closure.project_id = project_id
            closure.allow_attendance = allow_attendance
            db.session.add(closure)
            flash('Closure day added successfully', 'success')

        db.session.commit()
        return redirect(url_for('closures'))

    upcoming_closures = ClosureDay.query.filter(
        ClosureDay.date >= today_ist()
    ).order_by(ClosureDay.date).all()

    sites = Site.query.filter_by(status='active').order_by(Site.name).all()
    projects = Project.query.filter(Project.status != 'archived').order_by(Project.name).all()

    return render_template('closures.html', closures=upcoming_closures, date=ISTDate,
                           sites=sites, projects=projects)

@app.route('/worker/<int:worker_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_worker(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    if worker.status == 'active':
        worker.status = 'inactive'
        msg = f'{worker.full_name} has been deactivated.'
    else:
        worker.status = 'active'
        msg = f'{worker.full_name} has been reactivated.'
    db.session.commit()
    flash(msg, 'success')
    return redirect(url_for('worker_profile', worker_id=worker_id))

@app.route('/worker/<int:worker_id>/delete', methods=['POST'])
@admin_required
def delete_worker(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    name = worker.full_name
    AttendanceRecord.query.filter_by(worker_id=worker_id).delete()
    PayrollRecord.query.filter_by(worker_id=worker_id).delete()
    ProjectAssignment.query.filter_by(worker_id=worker_id).delete()
    WorkerModification.query.filter_by(worker_id=worker_id).delete()
    LeaveAdjustment.query.filter_by(worker_id=worker_id).delete()
    WorkerTransaction.query.filter_by(worker_id=worker_id).delete()
    db.session.delete(worker)
    db.session.commit()
    flash(f'{name} has been permanently deleted.', 'success')
    return redirect(url_for('workers'))

@app.route('/closures/<int:closure_id>/delete', methods=['POST'])
@admin_required
def delete_closure(closure_id):
    closure = tenant_get_or_404(ClosureDay, closure_id)
    db.session.delete(closure)
    db.session.commit()
    flash('Closure day deleted successfully', 'success')
    return redirect(url_for('closures'))

@app.route('/worker_attendance/<int:worker_id>')
@admin_required
def worker_attendance(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    
    # Month and year from the query string. Clamped the same way every other
    # month view clamps them: ?month=0&year=0 used to reach date(0, 0, 1) and
    # take the screen down with a 500, and ?month=abc crashed in int().
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year
    
    # Get attendance records for the month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    attendance_records = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date
    ).order_by(AttendanceRecord.date).all()
    
    # Create calendar data
    calendar_data = {}
    for record in attendance_records:
        calendar_data[record.date.day] = record
    
    attendance_summary = calculate_attendance_summary(attendance_records)
    pay_summary = calculate_pay_summary(worker, attendance_records, start_date, end_date)

    # Closure days for the month — keyed by day-of-month for easy template lookup
    closure_days_list = ClosureDay.query.filter(
        ClosureDay.date >= start_date,
        ClosureDay.date <= end_date,
    ).all()
    closure_days = {
        c.date.day: c for c in closure_days_list
        if closure_applies_to_worker(c, worker)
    }

    return render_template('worker_attendance.html',
                         worker=worker,
                         calendar_data=calendar_data,
                         attendance_summary=attendance_summary,
                         pay_summary=pay_summary,
                         closure_days=closure_days,
                         month=month,
                         year=year,
                         start_date=start_date,
                         end_date=end_date,
                         timedelta=timedelta,
                         date=ISTDate)

@app.route('/id_card/<int:worker_id>', methods=['GET', 'POST'])
@admin_required
def id_card(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    
    if request.method == 'POST':
        if 'regenerate_qr' in request.form:
            # Generate new QR code
            worker.qr_code = generate_qr_code(worker.worker_id)
            worker.updated_at = now_ist()
            db.session.commit()
            flash('New QR code generated successfully', 'success')
            return redirect(url_for('id_card', worker_id=worker_id))
    
    # Generate QR code if not exists
    if not worker.qr_code:
        worker.qr_code = generate_qr_code(worker.worker_id)
        db.session.commit()
    
    return render_template('id_card.html', worker=worker, date=ISTDate, timedelta=timedelta)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            current_user.full_name = request.form['full_name']
            current_user.email = request.form['email']
            db.session.commit()
            flash('Profile updated successfully', 'success')
            
        elif action == 'change_password':
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
            elif len(new_password) < 8:
                flash('Password must be at least 8 characters long', 'error')
            elif current_user.supabase_uid and supabase_auth.enabled():
                # Supabase owns this user's credentials. Re-authenticate with the
                # current password to obtain a fresh access token, then use it to
                # set the new one — this doubles as the "current password" check.
                verify = supabase_auth.sign_in(current_user.email, current_password)
                if not verify['ok']:
                    flash('Current password is incorrect', 'error')
                else:
                    result = supabase_auth.update_password(
                        verify['session']['access_token'], new_password)
                    if result['ok']:
                        flash('Password changed successfully', 'success')
                    else:
                        flash(result.get('error') or 'Could not change password. Please try again.', 'error')
            elif current_user.check_password(current_password):
                current_user.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully', 'success')
            else:
                flash('Current password is incorrect', 'error')
        
        return redirect(url_for('profile'))

    return render_template('profile.html', Worker=Worker, AttendanceRecord=AttendanceRecord, date=ISTDate)

USER_AVATAR_UPLOAD_DIR = os.path.join(app.static_folder, 'uploads', 'avatars')


def save_user_avatar(file_storage, user_id):
    """Compress + store a user's profile photo (Supabase or local)."""
    filename = secure_filename(file_storage.filename or '')
    if not allowed_image_file(filename):
        raise ValueError('Please upload a valid image (JPG, JPEG, PNG, GIF, or WEBP).')
    image_data, image_mime, image_ext = _compress_image(file_storage, max_px=256)
    unique_filename = f"user{user_id}_{now_ist().strftime('%Y%m%d%H%M%S%f')}.{image_ext}"
    if storage.storage_enabled():
        try:
            return storage.upload_image(f'acc{current_user.account_id}/avatars/{unique_filename}', image_data, image_mime)
        except Exception as exc:
            app.logger.warning('Avatar upload failed: %s', exc)
            raise ValueError('Could not upload the photo right now. Please try again.')
    os.makedirs(USER_AVATAR_UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(USER_AVATAR_UPLOAD_DIR, unique_filename), 'wb') as fh:
        fh.write(image_data)
    return url_for('static', filename=f'uploads/avatars/{unique_filename}')


@app.route('/profile/avatar', methods=['POST'])
@login_required
def profile_upload_avatar():
    photo = request.files.get('avatar')
    if not photo or not photo.filename:
        flash('Please choose an image to upload.', 'error')
        return redirect(url_for('profile'))
    try:
        current_user.profile_image = save_user_avatar(photo, current_user.id)
        db.session.commit()
        flash('Profile photo updated.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('profile'))


@app.route('/profile/avatar/remove', methods=['POST'])
@login_required
def profile_remove_avatar():
    current_user.profile_image = None
    db.session.commit()
    flash('Profile photo removed.', 'success')
    return redirect(url_for('profile'))

VALID_ATTENDANCE_STATUSES = ('present', 'absent', 'late', 'leave')

def _attendance_timestamp(attendance_date):
    """Wall-clock time anchored to the selected attendance date, so backdated
    entries never mix today's date into check-in/out timestamps."""
    return datetime.combine(attendance_date, now_ist().time())

@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    attendance_date = parse_date_or(request.form.get('date'))
    if not attendance_date:
        flash('Invalid attendance date.', 'error')
        return redirect(url_for('attendance'))
    closures_today = ClosureDay.query.filter_by(date=attendance_date).all()
    marked_via = request.form.get('marked_via', 'manual')
    redirect_target = safe_redirect_target(request.form.get('redirect_to'), url_for('attendance', date=attendance_date.isoformat()))

    if request.form.get('status') not in VALID_ATTENDANCE_STATUSES:
        flash('Invalid attendance status.', 'error')
        return redirect(redirect_target)

    # A date the client believes is "today" is not evidence. Attendance can
    # never be recorded ahead of the IST calendar day.
    if attendance_date > today_ist():
        flash('That date is in the future — attendance cannot be marked yet.', 'error')
        return redirect(redirect_target)

    # Authorized attendance users only record check-ins/check-outs; absent and
    # leave classifications are administrator decisions.
    if not current_user.is_admin and request.form.get('status') not in ('present', 'late'):
        flash('Please contact the Administrator to mark absences or leaves.', 'restricted')
        return redirect(redirect_target)

    company_lock = next(
        (c for c in closures_today if c.scope in (None, '', 'company') and not c.allow_attendance),
        None,
    )
    if company_lock:
        flash(
            f"Attendance is locked on this closure day ({company_lock.reason}).",
            'error'
        )
        return redirect(redirect_target)

    if 'bulk_action' in request.form:
        if not current_user.is_admin:
            flash('Please contact the Administrator to make changes.', 'restricted')
            return redirect(url_for('attendance', date=attendance_date.isoformat()))
        # Bulk attendance marking
        status = request.form['status']

        workers = Worker.query.filter_by(status='active').all()
        for worker in workers:
            worker_closure = closure_for_worker_on_date(worker, attendance_date, closures_today)
            if worker_closure and not worker_closure.allow_attendance:
                continue
            existing = AttendanceRecord.query.filter_by(
                worker_id=worker.id,
                date=attendance_date
            ).first()

            # site_id must reflect the assignment active on the marked date
            assignment = next((a for a in worker.assignments if assignment_active_on(a, attendance_date)), None)
            if existing:
                existing.status = status
                existing.marked_by = current_user.id
                existing.marked_via = 'bulk'
                if status in ('present', 'late'):
                    existing.check_in_time = _attendance_timestamp(attendance_date)
                    existing.overtime_minutes = 0
                    existing.late_minutes = 0
                    existing.check_out_time = None
                else:
                    existing.check_in_time = None
                    existing.check_out_time = None
                    existing.overtime_minutes = 0
                    existing.late_minutes = 0
            else:
                attendance = AttendanceRecord()
                attendance.worker_id = worker.id
                attendance.date = attendance_date
                attendance.status = status
                attendance.check_in_time = _attendance_timestamp(attendance_date) if status in ('present', 'late') else None
                attendance.check_out_time = None
                attendance.overtime_minutes = 0
                attendance.marked_by = current_user.id
                attendance.marked_via = 'bulk'
                attendance.site_id = assignment.site_id if assignment else None
                db.session.add(attendance)

        db.session.commit()
        flash(f'Bulk attendance marked as {status} for all workers', 'success')
    else:
        # Individual attendance marking
        worker_id = parse_int(request.form.get('worker_id'))
        status = request.form['status']
        leave_type = request.form.get('leave_type') or None
        feedback_message = None
        feedback_category = 'success'

        worker = tenant_get_or_404(Worker, worker_id)

        if not worker_visible_to_user(worker, current_user, on_date=attendance_date):
            flash('Please contact the Administrator to make changes.', 'restricted')
            return redirect(url_for('attendance', date=attendance_date.isoformat()))

        worker_closure = closure_for_worker_on_date(worker, attendance_date, closures_today)
        if worker_closure and not worker_closure.allow_attendance:
            flash(
                f"Attendance is locked for {worker.full_name} on this closure day ({worker_closure.reason}).",
                'error'
            )
            return redirect(redirect_target)

        # Check if attendance already exists
        existing = AttendanceRecord.query.filter_by(
            worker_id=worker_id,
            date=attendance_date
        ).first()

        # Authorized attendance users may check workers in/out, but may not
        # modify a completed record or change an existing status. 'present' and
        # 'late' are the same active shift state (auto-late conversion).
        if existing and not current_user.is_admin:
            is_simple_checkout = (
                existing.status in ('present', 'late')
                and status in ('present', 'late')
                and existing.check_in_time is not None
                and existing.check_out_time is None
            )
            if not is_simple_checkout:
                flash('Please contact the Administrator to make changes.', 'restricted')
                return redirect(redirect_target)

        if existing:
            previous_status = existing.status
            existing.status = status
            existing.marked_by = current_user.id
            existing.marked_via = marked_via
            existing.leave_type = leave_type if status == 'leave' else None

            if status in ('present', 'late'):
                now = _attendance_timestamp(attendance_date)
                same_active_state = (
                    previous_status in ('present', 'late') and status in ('present', 'late')
                )
                if not existing.check_in_time:
                    # First tap acts as check-in.
                    existing.check_in_time = now
                    existing.check_out_time = None
                    existing.overtime_minutes = 0
                    # Grace-time aware auto-late detection
                    if status == 'present' and is_late_check_in(worker, attendance_date, now):
                        existing.status = 'late'
                    existing.late_minutes = calculate_late_minutes_for_record(worker, existing)
                    if existing.status == 'late' and existing.late_minutes > 0:
                        feedback_message = f'Check-in captured — {existing.late_minutes} min late.'
                    else:
                        feedback_message = 'Check-in captured successfully.'
                elif existing.check_out_time is None and same_active_state:
                    # Second tap on an active shift acts as check-out/close.
                    # Preserve the auto-detected late status through checkout.
                    existing.status = previous_status
                    existing.check_out_time = now
                    existing.overtime_minutes = calculate_overtime_minutes_for_record(worker, existing)

                    overtime_pay = 0.0
                    overtime_units = 0.0
                    if worker.overtime_enabled and worker.overtime_rate and existing.overtime_minutes > 0:
                        if worker.overtime_type == 'minute':
                            overtime_units = float(existing.overtime_minutes)
                        else:
                            overtime_units = existing.overtime_minutes / 60.0
                        overtime_pay = overtime_units * float(worker.overtime_rate)

                    if existing.overtime_minutes > 0:
                        feedback_message = (
                            f'Shift closed. Overtime: {existing.overtime_minutes} minutes '
                            f'(₹{round(overtime_pay, 2)}).'
                        )
                    else:
                        feedback_message = 'Shift closed successfully.'

                    _, pay_mode = calculate_daily_wage_for_record(worker, existing)
                    if pay_mode == 'half_day':
                        base_message = feedback_message or 'Shift closed successfully.'
                        feedback_message = (
                            f'{base_message} Half-day rate will apply '
                            f'(includes {get_half_day_grace_minutes(worker)} min grace window).'
                        )
                    elif pay_mode == 'pro_rata':
                        base_message = feedback_message or 'Shift closed successfully.'
                        feedback_message = (
                            f'{base_message} Minute-based pro-rata daily wage will apply '
                            f'(after {get_half_day_grace_minutes(worker)} min grace window).'
                        )
                else:
                    # Re-open attendance when status changes.
                    existing.check_out_time = None
                    existing.overtime_minutes = 0
                    existing.late_minutes = calculate_late_minutes_for_record(worker, existing)
                    feedback_message = 'Attendance status updated successfully.'
            else:
                existing.check_in_time = None
                existing.check_out_time = None
                existing.overtime_minutes = 0
                existing.late_minutes = 0
                feedback_message = 'Attendance marked successfully.'
        else:
            # site_id must reflect the assignment active on the marked date
            assignment = next((a for a in worker.assignments if assignment_active_on(a, attendance_date)), None)
            attendance = AttendanceRecord()
            attendance.worker_id = worker_id
            attendance.date = attendance_date
            attendance.status = status
            attendance.check_in_time = _attendance_timestamp(attendance_date) if status in ('present', 'late') else None
            attendance.check_out_time = None
            attendance.overtime_minutes = 0
            attendance.leave_type = leave_type if status == 'leave' else None
            attendance.marked_by = current_user.id
            attendance.marked_via = marked_via
            attendance.site_id = assignment.site_id if assignment else None
            if status == 'present' and is_late_check_in(worker, attendance_date, attendance.check_in_time):
                attendance.status = 'late'
            attendance.late_minutes = calculate_late_minutes_for_record(worker, attendance)
            db.session.add(attendance)
            if attendance.status == 'late' and attendance.late_minutes > 0:
                feedback_message = f'Check-in captured — {attendance.late_minutes} min late.'
            elif status in ('present', 'late'):
                feedback_message = 'Check-in captured successfully.'
            else:
                feedback_message = 'Attendance marked successfully.'

        # Notify admins when a site attendance user records attendance
        if not current_user.is_admin:
            site = worker.current_site
            # The title said the worker and the status; the body then said
            # the worker and the status again, with the date that the
            # timestamp underneath already carries. The body now holds only
            # what the title does not: who marked it, where, and how.
            where = [current_user.full_name]
            if site:
                where.append(site.name)
            if marked_via != 'manual':
                where.append(marked_via.replace('_', ' '))
            notify_admin(
                f'{worker.full_name} ({worker.worker_id}){NOTE_DASH}{status}',
                ' · '.join(where),
            )

        db.session.commit()
        if feedback_message:
            flash(feedback_message, feedback_category)

    return redirect(redirect_target)

def _build_payroll_rows(month, year):
    workers = roster_query().all()
    _, days_in_month = _cal.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    # The month's attendance and any saved payroll rows, fetched once for the
    # whole roster instead of twice per worker.
    worker_ids = [w.id for w in workers]
    records_by_worker = {w.id: [] for w in workers}
    saved_by_worker = {}
    if worker_ids:
        for record in AttendanceRecord.query.filter(
            AttendanceRecord.worker_id.in_(worker_ids),
            AttendanceRecord.date >= start_date,
            AttendanceRecord.date <= end_date,
        ).order_by(AttendanceRecord.date).all():
            records_by_worker[record.worker_id].append(record)
        saved_by_worker = {
            p.worker_id: p
            for p in PayrollRecord.query.filter(
                PayrollRecord.worker_id.in_(worker_ids),
                PayrollRecord.month == month,
                PayrollRecord.year == year,
            ).all()
        }
        prefetch_period_transactions(worker_ids, start_date, end_date)
        prefetch_leave_ledgers(worker_ids, start_date, end_date)

    rows = []
    total_gross = 0.0
    total_deductions = 0.0
    total_net = 0.0
    paid_count = 0
    pending_count = 0

    for worker in workers:
        records = records_by_worker.get(worker.id, [])

        att_summary = calculate_attendance_summary(records)
        pay_summary = calculate_pay_summary(worker, records, start_date, end_date)

        gross_pay = round(
            pay_summary['base_pay'] + pay_summary['overtime_pay'] + pay_summary['transaction_earnings'],
            2,
        )
        deductions = round(pay_summary['deductions'] + pay_summary['transaction_deductions'], 2)
        net_pay = pay_summary['estimated_pay']

        existing_record = saved_by_worker.get(worker.id)

        if existing_record:
            record_status = existing_record.status
            record_id = existing_record.id
        else:
            record_status = 'unsaved'
            record_id = None

        # A finalised month shows what was actually paid, not what today's
        # rules would produce. Without this, changing a salary policy
        # rewrote the figures on months that had already been settled.
        frozen = record_status == 'paid' and existing_record is not None
        if frozen:
            gross_pay = float(existing_record.gross_pay or 0)
            deductions = float(existing_record.deductions or 0)
            net_pay = float(existing_record.net_pay or 0)
            if existing_record.breakdown_json:
                try:
                    pay_summary = dict(pay_summary)
                    pay_summary['salary_breakdown'] = json.loads(existing_record.breakdown_json)
                except (TypeError, ValueError):
                    pass

        total_gross += gross_pay
        total_deductions += deductions
        total_net += net_pay
        if record_status == 'paid':
            paid_count += 1
        else:
            pending_count += 1

        rows.append({
            'worker': worker,
            'frozen': frozen,
            'att_summary': att_summary,
            'pay_summary': pay_summary,
            'gross_pay': gross_pay,
            'deductions': deductions,
            'net_pay': net_pay,
            'status': record_status,
            'record_id': record_id,
        })

    return rows, {
        'total_gross': round(total_gross, 2),
        'total_deductions': round(total_deductions, 2),
        'total_net': round(total_net, 2),
        'paid_count': paid_count,
        'pending_count': pending_count,
        'worker_count': len(rows),
    }, start_date


#: Workers shown per page. Large enough that a small employer never sees
#: a pager at all, small enough that a 5,000-worker roster stays usable.
WORKERS_PER_PAGE = 50
#: Payroll pages at the same size; the totals above the list stay
#: whole-roster regardless of which page is open.
PAYROLL_PER_PAGE = 50

#: Attendance rows per page. The counters and bulk actions still cover the
#: whole roster; only the list is paged.
ATTENDANCE_PER_PAGE = 50

MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


@app.route('/payroll')
@admin_required
def payroll():
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, totals, _ = _build_payroll_rows(month, year)

    # The totals stay whole-roster on purpose: "what does this month cost" is
    # the figure an employer needs, and a per-page subtotal would be a
    # different and much less useful number. Computing them is cheap — 341ms
    # for 5,000 workers, measured — so only the list is paged. What was
    # actually slow was the page itself: 5,000 rows came to 11.9MB of HTML,
    # which is minutes on a site phone.
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    total_rows = len(rows)
    last_page = max(1, (total_rows + PAYROLL_PER_PAGE - 1) // PAYROLL_PER_PAGE)
    page = min(page, last_page)
    start = (page - 1) * PAYROLL_PER_PAGE
    page_rows = rows[start:start + PAYROLL_PER_PAGE]

    years = list(range(2024, today.year + 2))
    # Built in the interface language — i18n already holds the table
    # format_date uses, and an English month in a Hindi dropdown was
    # the last obviously untranslated thing on the payroll screen.
    months = [(i, i18n.month_name(i, _current_lang())) for i in range(1, 13)]

    return render_template(
        'payroll.html',
        rows=page_rows,
        totals=totals,
        month=month,
        year=year,
        years=years,
        months=months,
        month_name=MONTH_NAMES[month - 1],
        page=page,
        has_prev=page > 1,
        has_next=start + PAYROLL_PER_PAGE < total_rows,
        shown_from=start + 1 if total_rows else 0,
        shown_to=min(start + PAYROLL_PER_PAGE, total_rows),
        total_rows=total_rows,
    )


@app.route('/payroll/save', methods=['POST'])
@admin_required
def payroll_save():
    today = today_ist()
    try:
        month = max(1, min(12, int(request.form.get('month', today.month))))
        year = max(2020, min(2099, int(request.form.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, _, _ = _build_payroll_rows(month, year)
    saved = 0
    frozen = 0

    for row in rows:
        worker = row['worker']
        pay = row['pay_summary']
        att = row['att_summary']

        existing = PayrollRecord.query.filter_by(
            worker_id=worker.id, month=month, year=year
        ).first()

        # A month that has been paid is history. It used to be recalculated
        # and overwritten on every save, so editing a salary rule silently
        # restated what someone had already been paid. Leave it alone.
        if existing and existing.status == 'paid':
            frozen += 1
            continue

        fields = dict(
            total_days=att['total_marked_days'],
            present_days=pay['paid_days'],
            overtime_hours=round(pay['overtime_minutes'] / 60.0, 2),
            gross_pay=row['gross_pay'],
            deductions=row['deductions'],
            net_pay=row['net_pay'],
        )

        # Freeze how the figure was reached alongside the figure itself, so a
        # payslip reprinted next year shows the rules that were in force then.
        breakdown = pay.get('salary_breakdown')
        if breakdown:
            fields['breakdown_json'] = json.dumps(breakdown, default=str)
            fields['policy_json'] = json.dumps(breakdown['policy'], default=str)

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            existing.status = 'pending'
        else:
            record = PayrollRecord(
                worker_id=worker.id,
                month=month,
                year=year,
                status='pending',
                **fields,
            )
            db.session.add(record)

        saved += 1

    db.session.commit()
    message = f'Payroll generated for {saved} worker(s) — {MONTH_NAMES[month - 1]} {year}.'
    if frozen:
        message += (f' {frozen} already-paid record(s) were left untouched.')
    flash(message, 'success')
    return redirect(url_for('payroll', month=month, year=year))


@app.route('/payroll/<int:record_id>/toggle_paid', methods=['POST'])
@admin_required
def payroll_toggle_paid(record_id):
    record = tenant_get_or_404(PayrollRecord, record_id)
    record.status = 'pending' if record.status == 'paid' else 'paid'
    # Stamp the moment it became history. Re-opening a record clears the stamp
    # so the next save is free to recalculate it.
    record.finalized_at = now_ist() if record.status == 'paid' else None
    db.session.commit()
    label = 'Paid' if record.status == 'paid' else 'Pending'
    flash(
        f'{record.worker.full_name} marked as {label} — '
        f'{MONTH_NAMES[record.month - 1]} {record.year}.',
        'success',
    )
    return redirect(url_for('payroll', month=record.month, year=record.year))


@app.route('/payroll/slip/<int:worker_id>')
@admin_required
def payroll_slip(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    _, days_in_month = _cal.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    records = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker.id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date,
    ).order_by(AttendanceRecord.date).all()

    calendar_data = {r.date.day: r for r in records}
    att_summary = calculate_attendance_summary(records)
    pay_summary = calculate_pay_summary(worker, records, start_date, end_date)

    payroll_record = PayrollRecord.query.filter_by(
        worker_id=worker.id, month=month, year=year
    ).first()

    return render_template(
        'payroll_slip.html',
        worker=worker,
        month=month,
        year=year,
        month_name=MONTH_NAMES[month - 1],
        start_date=start_date,
        end_date=end_date,
        days_in_month=days_in_month,
        calendar_data=calendar_data,
        att_summary=att_summary,
        pay_summary=pay_summary,
        salary_basis_label=salary.LABELS['salary_basis'].get(
            (pay_summary.get('salary_breakdown') or {}).get('salary_basis', 'fixed'), 'Fixed days'),
        payroll_record=payroll_record,
        timedelta=timedelta,
        date=ISTDate,
    )


# ============================================================
# A worker's own login
# ============================================================

def _worker_slip_context(worker, month, year):
    """Everything payroll_slip.html needs, for one worker and month."""
    _, days_in_month = _cal.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)
    records = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker.id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date,
    ).order_by(AttendanceRecord.date).all()
    pay_summary = calculate_pay_summary(worker, records, start_date, end_date)
    return dict(
        worker=worker, month=month, year=year,
        month_name=MONTH_NAMES[month - 1],
        start_date=start_date, end_date=end_date, days_in_month=days_in_month,
        calendar_data={r.date.day: r for r in records},
        att_summary=calculate_attendance_summary(records),
        pay_summary=pay_summary,
        salary_basis_label=salary.LABELS['salary_basis'].get(
            (pay_summary.get('salary_breakdown') or {}).get('salary_basis', 'fixed'),
            'Fixed days'),
        payroll_record=PayrollRecord.query.filter_by(
            worker_id=worker.id, month=month, year=year).first(),
        timedelta=timedelta, date=ISTDate,
    )


def _requested_month(default_date):
    try:
        month = max(1, min(12, int(request.args.get('month', default_date.month))))
        year = max(2020, min(2099, int(request.args.get('year', default_date.year))))
    except (TypeError, ValueError):
        month, year = default_date.month, default_date.year
    return month, year


@app.route('/worker/<int:worker_id>/login', methods=['POST'])
@admin_required
def worker_create_login(worker_id):
    """Give a worker a login of their own, or reset its password.

    The username is their phone number, because that is the one thing a
    labourer reliably knows and can be told over the phone. The password is
    generated and shown once — there is no email to send it to, and storing
    a readable copy to show again later would be worse than reissuing it.
    """
    worker = tenant_get_or_404(Worker, worker_id)
    if not worker.phone:
        flash('Add a mobile number for this worker before creating a login.', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))

    clash = User.query.filter(
        User.username == worker.phone,
        or_(User.worker_id.is_(None), User.worker_id != worker.id),
    ).first()
    if clash:
        flash('That mobile number is already used by another login.', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))

    password = '%06d' % random.randint(100000, 999999)
    login = User.query.filter_by(worker_id=worker.id, role='worker').first()
    if not login:
        login = User(
            username=worker.phone,
            # users.email is NOT NULL and a labourer has no email address.
            # .invalid is reserved by RFC 2606 for exactly this, so the
            # placeholder can never collide with or be mistaken for a real
            # address, and nothing is ever sent to it.
            email='%s@worker.invalid' % worker.phone,
            full_name=worker.full_name,
            phone=worker.phone,
            role='worker',
            worker_id=worker.id,
            account_id=worker.account_id,
            status='active',
        )
        db.session.add(login)
    else:
        # Keep the login pointed at the worker's current number.
        login.username = worker.phone
        login.email = '%s@worker.invalid' % worker.phone
        login.phone = worker.phone
        login.full_name = worker.full_name
    login.set_password(password)
    db.session.commit()

    # Shown once, in a flash, and never stored in readable form.
    flash(f'Login ready for {worker.full_name}. '
          f'Username {worker.phone}, password {password}. '
          f'Write it down — it cannot be shown again.', 'success')
    return redirect(url_for('worker_profile', worker_id=worker_id))


@app.route('/worker/<int:worker_id>/login/revoke', methods=['POST'])
@admin_required
def worker_revoke_login(worker_id):
    """Take a worker's login away."""
    worker = tenant_get_or_404(Worker, worker_id)
    removed = User.query.filter_by(worker_id=worker.id, role='worker').delete()
    db.session.commit()
    flash('Login removed.' if removed else 'This worker had no login.',
          'success' if removed else 'info')
    return redirect(url_for('worker_profile', worker_id=worker_id))


@app.route('/worker/<int:worker_id>/login/powers', methods=['GET', 'POST'])
@admin_required
def worker_login_powers(worker_id):
    """Grant a worker's login the powers of a mukadam, and allot them a roll.

    Both powers are off until an administrator turns them on, so creating a
    login never quietly hands anyone authority over other people's wages.
    """
    worker = tenant_get_or_404(Worker, worker_id)
    login = User.query.filter_by(worker_id=worker.id, role='worker').first()
    if not login:
        flash('Create a login for this worker first.', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))

    if request.method == 'POST':
        login.can_mark_attendance = 'can_mark_attendance' in request.form
        login.can_record_transactions = 'can_record_transactions' in request.form
        chosen = {parse_int(v, 0) for v in request.form.getlist('team')}
        # Self-marking is the fraud this design exists to prevent, so the
        # supervisor is dropped here as well as in supervisor_team_ids —
        # the stored list should not even contain them.
        chosen.discard(worker.id)
        valid = {w.id for w in roster_query().all()}
        login.assigned_worker_ids = ','.join(
            str(i) for i in sorted(chosen & valid)) or None
        db.session.commit()
        flash('Powers saved.', 'success')
        return redirect(url_for('worker_profile', worker_id=worker_id))

    team = [w for w in roster_query().all() if w.id != worker.id]
    return render_template('worker_login_powers.html',
                           worker=worker, login=login, team=team,
                           chosen=set(login.worker_id_list))


def supervisor_required(view):
    """A view only a worker who has been made a supervisor may open."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (current_user.is_worker and current_user.can_mark_attendance
                and current_user.worker_id):
            return redirect(url_for('worker_home'))
        return view(*args, **kwargs)
    return wrapped


def _supervisor_team(user):
    """The workers this supervisor may touch, as Worker rows.

    Goes through supervisor_team_ids, which drops the supervisor's own id.
    Every read and every write comes through here, so there is one place
    that decides who is in scope and it already excludes self-marking.
    """
    ids = user.supervisor_team_ids
    if not ids:
        return []
    return (Worker.query.filter(Worker.id.in_(ids), Worker.status == 'active')
            .order_by(Worker.full_name).all())


def _supervisor_may_touch(user, worker_id):
    return worker_id in set(user.supervisor_team_ids)


@app.route('/me/team')
@supervisor_required
def supervisor_team():
    """The roll a mukadam marks."""
    today = today_ist()
    try:
        on_date = parse_date_or(request.args.get('date')) or today
    except (TypeError, ValueError):
        on_date = today
    if on_date > today:
        on_date = today

    team = _supervisor_team(current_user)
    existing = {}
    if team:
        existing = {
            r.worker_id: r
            for r in AttendanceRecord.query.filter(
                AttendanceRecord.worker_id.in_([w.id for w in team]),
                AttendanceRecord.date == on_date).all()
        }
    return render_template(
        'supervisor_team.html',
        team=team, on_date=on_date, today=today, existing=existing,
        can_record_transactions=current_user.can_record_transactions,
        txn_types=TRANSACTION_TYPE_LABELS,
    )


@app.route('/me/team/mark', methods=['POST'])
@supervisor_required
def supervisor_mark():
    """Mark one worker present or late.

    Absent and leave are deliberately not here: both cut wages, and that is
    an administrator's decision, not a mukadam's. Nor can an existing
    status be changed — a correction goes to the administrator. The one
    thing a second tap may do is close an open shift, which is not a
    correction but the other half of the same day's work.
    """
    worker_id = parse_int(request.form.get('worker_id'), 0)
    status = request.form.get('status', '')
    on_date = parse_date_or(request.form.get('date')) or today_ist()
    back = url_for('supervisor_team', date=on_date.isoformat())

    if not _supervisor_may_touch(current_user, worker_id):
        flash('That worker is not on your list.', 'error')
        return redirect(back)
    if status not in ('present', 'late'):
        flash('Please contact the Administrator to mark absences or leaves.',
              'restricted')
        return redirect(back)
    if on_date > today_ist():
        flash('That date is in the future — attendance cannot be marked yet.',
              'error')
        return redirect(back)

    worker = tenant_get_or_404(Worker, worker_id)
    closure = next((c for c in ClosureDay.query.filter_by(date=on_date).all()
                    if c.scope in (None, '', 'company') and not c.allow_attendance), None)
    if closure:
        flash(f'Attendance is locked on this closure day ({closure.reason}).', 'error')
        return redirect(back)

    record = AttendanceRecord.query.filter_by(
        worker_id=worker.id, date=on_date).first()
    stamp = _attendance_timestamp(on_date)

    if record:
        closing = (record.status in ('present', 'late')
                   and record.check_in_time is not None
                   and record.check_out_time is None)
        if not closing:
            flash('Please contact the Administrator to make changes.', 'restricted')
            return redirect(back)
        record.check_out_time = stamp
        record.marked_by = current_user.id
    else:
        assignment = next((a for a in worker.assignments
                           if assignment_active_on(a, on_date)), None)
        record = AttendanceRecord(
            worker_id=worker.id, date=on_date, status=status,
            check_in_time=stamp, marked_by=current_user.id,
            marked_via='supervisor', account_id=worker.account_id,
            site_id=assignment.site_id if assignment else None,
        )
        db.session.add(record)
    db.session.commit()
    flash(f'Attendance adjusted for {worker.full_name}.', 'success')
    return redirect(back)


@app.route('/me/team/transaction', methods=['POST'])
@supervisor_required
def supervisor_transaction():
    """Record an advance or a payment for someone on the roll.

    Recording only. Cancelling or editing one is an administrator's job,
    because a transaction a mukadam can both create and erase is a way to
    take wages off someone quietly. The worker sees it on their own screen
    either way, which is the real check.
    """
    if not current_user.can_record_transactions:
        flash('Please contact the Administrator to make changes.', 'restricted')
        return redirect(url_for('supervisor_team'))

    worker_id = parse_int(request.form.get('worker_id'), 0)
    txn_type = request.form.get('txn_type', '')
    amount = parse_float(request.form.get('amount'), 0.0)
    on_date = parse_date_or(request.form.get('date')) or today_ist()
    back = url_for('supervisor_team', date=on_date.isoformat())

    if not _supervisor_may_touch(current_user, worker_id):
        flash('That worker is not on your list.', 'error')
        return redirect(back)
    if txn_type not in TRANSACTION_TYPE_LABELS:
        flash('Please choose a valid transaction type.', 'error')
        return redirect(back)
    if amount <= 0:
        flash('Transaction amount must be greater than zero.', 'error')
        return redirect(back)

    worker = tenant_get_or_404(Worker, worker_id)
    label = TRANSACTION_TYPE_LABELS[txn_type]
    db.session.add(WorkerTransaction(
        worker_id=worker.id, txn_type=txn_type, amount=amount, date=on_date,
        description=(request.form.get('description') or '').strip() or label,
        created_by=current_user.id, account_id=worker.account_id,
    ))
    db.session.commit()
    flash(f'{label} of ₹{amount:,.2f} added for {worker.full_name}.', 'success')
    return redirect(back)


@app.route('/me')
@worker_login_required
def worker_home():
    """A worker's own attendance and pay for a month.

    Reads from current_user.worker_id and never from the URL: a worker has
    one record to look at, so there is nothing for a tampered id to select.
    """
    worker = Worker.query.filter_by(id=current_user.worker_id).first()
    if not worker:
        logout_user()
        flash('This login is not linked to a worker record. '
              'Please contact the Administrator.', 'error')
        return redirect(url_for('login'))

    today = today_ist()
    month, year = _requested_month(today)
    context = _worker_slip_context(worker, month, year)
    # Built in the interface language — i18n already holds the table
    # format_date uses, and an English month in a Hindi dropdown was
    # the last obviously untranslated thing on the payroll screen.
    months = [(i, i18n.month_name(i, _current_lang())) for i in range(1, 13)]
    return render_template(
        'worker_home.html',
        years=list(range(max(2024, (worker.join_date or today).year), today.year + 1)),
        months=months,
        today=today,
        **context,
    )


@app.route('/me/payslip')
@worker_login_required
def worker_payslip():
    """The same payslip an administrator sees, for this worker only."""
    worker = Worker.query.filter_by(id=current_user.worker_id).first()
    if not worker:
        return redirect(url_for('worker_home'))
    month, year = _requested_month(today_ist())
    return render_template('payroll_slip.html', **_worker_slip_context(worker, month, year))


@app.route('/payroll/export.csv')
@admin_required
def payroll_export():
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, totals, _ = _build_payroll_rows(month, year)
    month_name = MONTH_NAMES[month - 1]

    output = io.StringIO()
    writer = csv.writer(output)

    # The salary columns are blank for daily, hourly and project workers:
    # they have no derived daily rate, no basis and no joining-date
    # proration, so a figure there would be meaningless rather than zero.
    writer.writerow([
        'Worker ID', 'Full Name', 'Department', 'Position',
        'Pay Type', 'Month', 'Year',
        'Total Marked Days', 'Paid Days',
        'Gross Pay (INR)', 'Deductions (INR)', 'Net Payable (INR)',
        'Overtime Minutes', 'Closure Bonus (INR)', 'Status',
        'Joining Date', 'Monthly Salary (INR)', 'Salary Basis', 'Basis Days',
        'Daily Salary Exact (INR)', 'Daily Salary Rounded (INR)',
        'Total Calendar Days', 'Eligible Days',
        'Present Days', 'Absent Days',
        'Paid Leave Allowance', 'Paid Leave Used', 'Unpaid Leave',
        'Deduction Days', 'Deduction Rate (INR)', 'Salary Deduction (INR)',
        'Gross Eligible Salary (INR)', 'Net Payable Salary (INR)',
    ])

    total_closure_bonus = 0.0
    for row in rows:
        w = row['worker']
        pay = row['pay_summary']
        att = row['att_summary']
        closure_bonus = pay.get('closure_extra_pay', 0.0)
        total_closure_bonus += closure_bonus
        writer.writerow([
            w.worker_id,
            w.full_name,
            w.department,
            w.position,
            w.pay_type,
            month_name,
            year,
            att['total_marked_days'],
            pay['paid_days'],
            row['gross_pay'],
            row['deductions'],
            row['net_pay'],
            pay['overtime_minutes'],
            f"{closure_bonus:.2f}" if closure_bonus else '',
            row['status'],
            *_salary_csv_columns(w, pay.get('salary_breakdown')),
        ])

    writer.writerow([])
    writer.writerow([
        '', 'TOTALS', '', '', '', '', '',
        '', '',
        totals['total_gross'],
        totals['total_deductions'],
        totals['total_net'],
        '',
        f"{total_closure_bonus:.2f}" if total_closure_bonus else '',
        f"{totals['paid_count']} paid / {totals['pending_count']} pending",
        *[''] * 18,
    ])

    filename = f"payroll_{month_name.lower()}_{year}.csv"
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


@app.route('/export_data')
@admin_required
def export_data():
    # Create CSV response
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Worker ID', 'Full Name', 'Department', 'Position', 'Phone', 'Email',
        'Employee Type', 'Join Date', 'Pay Type', 'Daily Rate', 'Monthly Salary',
        'Hourly Rate', 'Project Rate', 'No Work No Pay', 'Half Day Rate', 'Half Day Grace Minutes',
        'Overtime Enabled', 'Overtime Rate', 'Overtime Type',
        'Late Policy Enabled', 'Late Deduction Rate', 'Late Deduction Type',
        'Leave Policy Enabled', 'Allowed Leaves/Month', 'Leave Deduction/Day',
        # The salary policy actually in force for this worker — company
        # default with any per-worker override already applied, so the export
        # says what the worker is paid by rather than what was configured
        # where.
        'Salary Basis', 'Basis Days', 'Daily Rate Rounding', 'Mid-Month Joining',
        'Paid Leave Enabled', 'Leave Allowance/Month', 'Leave Carry Forward',
        'Absence Deduction Enabled', 'Deduction Rate/Day', 'Calculation Method',
        'Status', 'Date', 'Attendance Status', 'Check In', 'Check Out'
    ])
    
    # Write worker and attendance data
    workers = Worker.query.all()
    for worker in workers:
        pol = resolve_salary_policy(worker) if worker.pay_type == 'monthly' else None
        for attendance in worker.attendance_records:
            writer.writerow([
                worker.worker_id,
                worker.full_name,
                worker.department,
                worker.position,
                worker.phone,
                worker.email or '',
                worker.employee_type,
                worker.join_date.strftime('%Y-%m-%d'),
                worker.pay_type,
                worker.daily_rate or '',
                worker.monthly_salary or '',
                worker.hourly_rate or '',
                worker.project_rate or '',
                worker.no_work_no_pay,
                worker.half_day_rate or '',
                worker.half_day_grace_minutes or '',
                worker.overtime_enabled,
                worker.overtime_rate or '',
                worker.overtime_type or '',
                worker.late_policy_enabled,
                worker.late_deduction_per_day or '',
                worker.late_deduction_type or '',
                worker.leave_policy_enabled,
                worker.allowed_leaves_per_month or '',
                worker.leave_deduction_per_day or '',
                *_salary_policy_csv_columns(pol),
                worker.status,
                attendance.date.strftime('%Y-%m-%d'),
                attendance.status,
                attendance.check_in_time.strftime('%H:%M') if attendance.check_in_time else '',
                attendance.check_out_time.strftime('%H:%M') if attendance.check_out_time else ''
            ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=smartworker_data_{today_ist().isoformat()}.csv'
    
    return response


# ============================================================
# Company Settings & Master Data Management (Admin)
# ============================================================

COMPANY_LOGO_UPLOAD_DIR = os.path.join(app.static_folder, 'uploads', 'company')

@app.route('/settings')
@admin_required
def settings():
    company = CompanySetting.query.first()
    sites = Site.query.order_by(Site.status, Site.name).all()
    projects = Project.query.order_by(Project.status, Project.name).all()
    tasks = WorkTask.query.order_by(WorkTask.status, WorkTask.name).all()
    departments = Department.query.order_by(Department.status, Department.name).all()
    attendance_users = User.query.filter_by(role='attendance', account_id=current_user.account_id).order_by(User.full_name).all()

    # Company-wide salary policy, plus the workers who depart from it, so the
    # settings screen can say how many people a change will actually affect.
    policy_row = SalaryPolicy.query.filter_by(worker_id=None).first()
    salary_policy = salary.normalise_policy(policy_row)
    overridden = SalaryPolicy.query.filter(SalaryPolicy.worker_id.isnot(None)).count()
    monthly_worker_count = Worker.query.filter_by(pay_type='monthly', status='active').count()
    policy_audit = (SalaryPolicyAudit.query
                    .order_by(SalaryPolicyAudit.created_at.desc()).limit(12).all())

    # Whether uploaded photos will still exist tomorrow. The app already
    # logs this at startup, but a warning in Render's log is not somewhere
    # an administrator looks, and the symptom — a photo that shows once and
    # is gone after the next restart — looks like a bug in the app rather
    # than a setting nobody was told about.
    photo_storage = {
        'permanent': storage.storage_enabled(),
        'bucket': storage.BUCKET,
        'hosted': bool(os.environ.get('RENDER')),
    }

    return render_template('settings.html',
                           photo_storage=photo_storage,
                           company=company,
                           sites=sites,
                           projects=projects,
                           tasks=tasks,
                           departments=departments,
                           attendance_users=attendance_users,
                           salary_policy=salary_policy,
                           salary_policy_saved=policy_row is not None,
                           salary_overrides=overridden,
                           monthly_worker_count=monthly_worker_count,
                           salary_labels=salary.LABELS,
                           policy_audit=policy_audit,
                           date=ISTDate)

@app.route('/settings/company', methods=['POST'])
@admin_required
def settings_company():
    company = CompanySetting.query.first()
    if not company:
        company = CompanySetting()
        db.session.add(company)
    company.name = request.form.get('name', 'SmartWorker').strip() or 'SmartWorker'
    company.address = request.form.get('address', '').strip() or None
    company.phone = request.form.get('phone', '').strip() or None
    company.email = request.form.get('email', '').strip() or None
    company.website = request.form.get('website', '').strip() or None
    company.gst_number = request.form.get('gst_number', '').strip() or None
    company.registration_number = request.form.get('registration_number', '').strip() or None

    logo = request.files.get('logo')
    if logo and logo.filename:
        filename = secure_filename(logo.filename)
        if not allowed_image_file(filename):
            flash('Please upload a valid logo image (JPG, JPEG, PNG, GIF, or WEBP).', 'error')
            return redirect(url_for('settings'))
        # Logos keep transparency (PNG); compressed to a small square.
        logo_data, logo_mime, logo_ext = _compress_image(logo, max_px=256, quality=85, preserve_alpha=True)
        unique_filename = f"logo_{now_ist().strftime('%Y%m%d%H%M%S')}.{logo_ext}"
        try:
            if storage.storage_enabled():
                company.logo = storage.upload_image(f'acc{current_user.account_id}/company/{unique_filename}', logo_data, logo_mime)
            else:
                os.makedirs(COMPANY_LOGO_UPLOAD_DIR, exist_ok=True)
                with open(os.path.join(COMPANY_LOGO_UPLOAD_DIR, unique_filename), 'wb') as fh:
                    fh.write(logo_data)
                company.logo = url_for('static', filename=f'uploads/company/{unique_filename}')
        except Exception as exc:
            app.logger.warning('Logo upload failed: %s', exc)
            flash('Could not upload the logo right now. Other settings were saved.', 'warning')

    db.session.commit()
    flash('Company settings saved. They will appear on all PDFs and reports.', 'success')
    return redirect(url_for('settings'))

def _save_entity(model, entity_label):
    """Shared add/edit handler for sites, projects, tasks and departments."""
    entity_id = parse_int(request.form.get('id'), 0)
    if entity_id:
        entity = tenant_get_or_404(model, entity_id)
    else:
        entity = model()
        db.session.add(entity)

    entity.name = request.form.get('name', '').strip()
    if not entity.name:
        flash(f'{entity_label} name is required.', 'error')
        db.session.rollback()
        return redirect(url_for('settings'))

    if model is Site:
        entity.address = request.form.get('address', '').strip() or None
        entity.contact_person = request.form.get('contact_person', '').strip() or None
        entity.contact_phone = request.form.get('contact_phone', '').strip() or None
    elif model is Project:
        entity.description = request.form.get('description', '').strip() or None
        entity.site_id = parse_int(request.form.get('site_id'), 0) or None
        for field in ('start_date', 'end_date', 'deadline', 'completion_date'):
            raw = request.form.get(field)
            setattr(entity, field, parse_date_or(raw))
        penalty_type = request.form.get('penalty_type', 'none')
        entity.penalty_type = penalty_type if penalty_type in ('none', 'fixed', 'percent') else 'none'
        entity.penalty_value = max(parse_float(request.form.get('penalty_value'), 0.0), 0.0)
        requested_status = request.form.get('status', entity.status or 'active')
        if requested_status in ('active', 'completed', 'archived'):
            entity.status = requested_status
        if entity.completion_date and entity.status == 'active':
            entity.status = 'completed'
    elif model is WorkTask:
        entity.project_id = parse_int(request.form.get('project_id'), 0) or None
        entity.category = request.form.get('category', '').strip() or None

    db.session.commit()
    flash(f'{entity_label} saved successfully.', 'success')
    return redirect(url_for('settings'))

def _toggle_entity_archive(model, entity_id, entity_label):
    entity = tenant_get_or_404(model, entity_id)
    entity.status = 'active' if entity.status == 'archived' else 'archived'
    db.session.commit()
    state = 'restored' if entity.status == 'active' else 'archived'
    flash(f'{entity_label} {state} successfully.', 'success')
    return redirect(url_for('settings'))

def _entity_references(model, entity):
    """Count live references to a master-data row so deletion never orphans
    assignments, closures, projects, tasks, or worker records."""
    refs = []
    if model is Site:
        refs = [
            ('assignment', ProjectAssignment.query.filter_by(site_id=entity.id).count()),
            ('project', Project.query.filter_by(site_id=entity.id).count()),
            ('closure', ClosureDay.query.filter_by(site_id=entity.id).count()),
            ('attendance record', AttendanceRecord.query.filter_by(site_id=entity.id).count()),
        ]
    elif model is Project:
        refs = [
            ('assignment', ProjectAssignment.query.filter_by(project_id=entity.id).count()),
            ('task', WorkTask.query.filter_by(project_id=entity.id).count()),
            ('closure', ClosureDay.query.filter_by(project_id=entity.id).count()),
        ]
    elif model is WorkTask:
        refs = [
            ('assignment', ProjectAssignment.query.filter_by(task_id=entity.id).count()),
        ]
    elif model is Department:
        refs = [
            ('worker', Worker.query.filter_by(department=entity.name).count()),
        ]
    return [(label, count) for label, count in refs if count]

def _delete_entity(model, entity_id, entity_label):
    entity = tenant_get_or_404(model, entity_id)
    used_by = _entity_references(model, entity)
    if used_by:
        usage = ', '.join(f'{count} {label}{"s" if count != 1 else ""}' for label, count in used_by)
        flash(
            f'Cannot delete this {entity_label.lower()} — it is referenced by {usage}. '
            f'Archive it instead to keep history intact.',
            'error'
        )
        return redirect(url_for('settings'))
    db.session.delete(entity)
    db.session.commit()
    flash(f'{entity_label} deleted successfully.', 'success')
    return redirect(url_for('settings'))

@app.route('/settings/site/save', methods=['POST'])
@admin_required
def settings_site_save():
    return _save_entity(Site, 'Site')

@app.route('/settings/site/<int:entity_id>/archive', methods=['POST'])
@admin_required
def settings_site_archive(entity_id):
    return _toggle_entity_archive(Site, entity_id, 'Site')

@app.route('/settings/site/<int:entity_id>/delete', methods=['POST'])
@admin_required
def settings_site_delete(entity_id):
    return _delete_entity(Site, entity_id, 'Site')

@app.route('/settings/project/save', methods=['POST'])
@admin_required
def settings_project_save():
    return _save_entity(Project, 'Project')

@app.route('/settings/project/<int:entity_id>/archive', methods=['POST'])
@admin_required
def settings_project_archive(entity_id):
    return _toggle_entity_archive(Project, entity_id, 'Project')

@app.route('/settings/project/<int:entity_id>/delete', methods=['POST'])
@admin_required
def settings_project_delete(entity_id):
    return _delete_entity(Project, entity_id, 'Project')

@app.route('/settings/task/save', methods=['POST'])
@admin_required
def settings_task_save():
    return _save_entity(WorkTask, 'Task')

@app.route('/settings/task/<int:entity_id>/archive', methods=['POST'])
@admin_required
def settings_task_archive(entity_id):
    return _toggle_entity_archive(WorkTask, entity_id, 'Task')

@app.route('/settings/task/<int:entity_id>/delete', methods=['POST'])
@admin_required
def settings_task_delete(entity_id):
    return _delete_entity(WorkTask, entity_id, 'Task')

@app.route('/settings/department/save', methods=['POST'])
@admin_required
def settings_department_save():
    return _save_entity(Department, 'Department')

@app.route('/settings/department/<int:entity_id>/archive', methods=['POST'])
@admin_required
def settings_department_archive(entity_id):
    return _toggle_entity_archive(Department, entity_id, 'Department')

@app.route('/settings/department/<int:entity_id>/delete', methods=['POST'])
@admin_required
def settings_department_delete(entity_id):
    return _delete_entity(Department, entity_id, 'Department')

# ============================================================
# Authorized Attendance Users (Admin)
# ============================================================

@app.route('/settings/attendance_user/save', methods=['POST'])
@admin_required
def settings_attendance_user_save():
    user_id = parse_int(request.form.get('id'), 0)
    full_name = request.form.get('full_name', '').strip()
    mobile = normalize_mobile_number(request.form.get('mobile'))
    password = request.form.get('password', '')
    site_ids = ','.join(request.form.getlist('site_ids'))
    project_ids = ','.join(request.form.getlist('project_ids'))

    if not full_name:
        flash('Full name is required for an attendance user.', 'error')
        return redirect(url_for('settings'))
    if not is_valid_mobile_number(mobile):
        flash('Please enter a valid mobile number for the attendance user.', 'error')
        return redirect(url_for('settings'))

    duplicate = User.query.filter(User.phone == mobile, User.id != user_id).first()
    if duplicate:
        flash('This mobile number is already registered to another account.', 'error')
        return redirect(url_for('settings'))

    if user_id:
        user = User.query.filter_by(id=user_id, account_id=current_user.account_id).first_or_404()
        if user.role != 'attendance':
            flash('Only attendance users can be edited here.', 'error')
            return redirect(url_for('settings'))
    else:
        if not password or len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('settings'))
        user = User()
        user.username = generate_unique_username(full_name, f"{mobile}@attendance.local")
        user.email = f"{mobile}@attendance.local"
        user.role = 'attendance'
        user.created_by = current_user.id
        # Staff belong to the creating admin's workspace and share its data.
        user.account_id = current_user.account_id
        db.session.add(user)

    user.full_name = full_name
    user.phone = mobile
    user.assigned_site_ids = site_ids or None
    user.assigned_project_ids = project_ids or None
    if password:
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            db.session.rollback()
            return redirect(url_for('settings'))
        user.set_password(password)

    db.session.commit()
    flash(f'Attendance user {full_name} saved. They can log in with their mobile number.', 'success')
    return redirect(url_for('settings'))

@app.route('/settings/attendance_user/<int:user_id>/toggle', methods=['POST'])
@admin_required
def settings_attendance_user_toggle(user_id):
    user = User.query.filter_by(id=user_id, account_id=current_user.account_id).first_or_404()
    if user.role != 'attendance':
        flash('Only attendance users can be managed here.', 'error')
        return redirect(url_for('settings'))
    user.status = 'disabled' if (user.status or 'active') == 'active' else 'active'
    db.session.commit()
    flash(f'{user.full_name} is now {user.status}.', 'success')
    return redirect(url_for('settings'))

@app.route('/settings/attendance_user/<int:user_id>/delete', methods=['POST'])
@admin_required
def settings_attendance_user_delete(user_id):
    user = User.query.filter_by(id=user_id, account_id=current_user.account_id).first_or_404()
    if user.role != 'attendance':
        flash('Only attendance users can be deleted here.', 'error')
        return redirect(url_for('settings'))
    db.session.delete(user)
    db.session.commit()
    flash('Attendance user deleted.', 'success')
    return redirect(url_for('settings'))

# ============================================================
# Transactions Module (Admin)
# ============================================================

TRANSACTION_TYPE_LABELS = {
    'advance': 'Advance Salary',
    'loan': 'Loan',
    'cash_advance': 'Cash Advance',
    'recovery': 'Recovery',
    'deduction': 'Deduction',
    'bonus': 'Bonus',
    'extra_payment': 'Extra Payment',
    'incentive': 'Incentive',
    'refreshment': 'Refreshment Allowance',
}

@app.route('/transactions')
@admin_required
def transactions():
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year
    worker_filter = parse_int(request.args.get('worker'), 0)

    _, days_in_month = _cal.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    query = WorkerTransaction.query.filter(
        WorkerTransaction.date >= start_date,
        WorkerTransaction.date <= end_date,
    )
    if worker_filter:
        query = query.filter(WorkerTransaction.worker_id == worker_filter)
    txns = query.order_by(WorkerTransaction.date.desc(), WorkerTransaction.id.desc()).all()

    total_earnings = sum(t.amount for t in txns if t.status == 'active' and t.is_earning)
    total_deductions = sum(t.amount for t in txns if t.status == 'active' and not t.is_earning)

    workers = Worker.query.filter_by(status='active').order_by(Worker.full_name).all()
    years = list(range(2024, today.year + 2))
    # Built in the interface language — i18n already holds the table
    # format_date uses, and an English month in a Hindi dropdown was
    # the last obviously untranslated thing on the payroll screen.
    months = [(i, i18n.month_name(i, _current_lang())) for i in range(1, 13)]

    return render_template('transactions.html',
                           transactions=txns,
                           workers=workers,
                           month=month,
                           year=year,
                           years=years,
                           months=months,
                           month_name=MONTH_NAMES[month - 1],
                           worker_filter=worker_filter,
                           total_earnings=round(total_earnings, 2),
                           total_deductions=round(total_deductions, 2),
                           type_labels=TRANSACTION_TYPE_LABELS,
                           earning_types=TRANSACTION_EARNING_TYPES,
                           deduction_types=TRANSACTION_DEDUCTION_TYPES,
                           today=today)

@app.route('/transactions/save', methods=['POST'])
@admin_required
def transactions_save():
    txn_id = parse_int(request.form.get('id'), 0)
    worker_id = parse_int(request.form.get('worker_id'), 0)
    txn_type = request.form.get('txn_type', '')
    amount = parse_float(request.form.get('amount'), 0.0)
    txn_date_raw = request.form.get('date')
    description = request.form.get('description', '').strip() or None
    redirect_to = safe_redirect_target(request.form.get('redirect_to'), url_for('transactions'))

    worker = tenant_get_or_404(Worker, worker_id)
    if txn_type not in TRANSACTION_TYPE_LABELS:
        flash('Please choose a valid transaction type.', 'error')
        return redirect(redirect_to)
    if amount <= 0:
        flash('Transaction amount must be greater than zero.', 'error')
        return redirect(redirect_to)
    try:
        txn_date = datetime.strptime(txn_date_raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        txn_date = today_ist()

    if txn_id:
        txn = tenant_get_or_404(WorkerTransaction, txn_id)
    else:
        txn = WorkerTransaction()
        txn.created_by = current_user.id
        db.session.add(txn)

    txn.worker_id = worker.id
    txn.txn_type = txn_type
    txn.amount = amount
    txn.date = txn_date
    txn.description = description
    db.session.commit()

    label = TRANSACTION_TYPE_LABELS[txn_type]
    flash(f'{label} of ₹{amount:,.2f} saved for {worker.full_name}. Payroll updates automatically.', 'success')
    return redirect(redirect_to)

@app.route('/transactions/<int:txn_id>/cancel', methods=['POST'])
@admin_required
def transactions_cancel(txn_id):
    txn = tenant_get_or_404(WorkerTransaction, txn_id)
    txn.status = 'cancelled' if txn.status == 'active' else 'active'
    db.session.commit()
    state = 'cancelled' if txn.status == 'cancelled' else 'restored'
    flash(f'Transaction {state}. Payroll updates automatically.', 'success')
    return redirect(safe_redirect_target(request.form.get('redirect_to'), url_for('transactions')))

@app.route('/transactions/<int:txn_id>/delete', methods=['POST'])
@admin_required
def transactions_delete(txn_id):
    txn = tenant_get_or_404(WorkerTransaction, txn_id)
    db.session.delete(txn)
    db.session.commit()
    flash('Transaction deleted permanently.', 'success')
    return redirect(safe_redirect_target(request.form.get('redirect_to'), url_for('transactions')))

# ============================================================
# Worker Modification, Promotion & Leave Adjustment (Admin)
# ============================================================

@app.route('/worker/<int:worker_id>/modify', methods=['POST'])
@admin_required
def worker_modify(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    mod_type = request.form.get('mod_type', 'other')
    description = request.form.get('description', '').strip() or None
    effective_raw = request.form.get('effective_date')
    try:
        effective_date = datetime.strptime(effective_raw, '%Y-%m-%d').date() if effective_raw else today_ist()
    except ValueError:
        effective_date = today_ist()

    if mod_type == 'promotion':
        new_position = request.form.get('new_position', '').strip()
        new_salary = parse_float(request.form.get('new_salary'), 0.0)
        old_position = worker.position
        changes = []
        if new_position and new_position != worker.position:
            worker.position = new_position
            changes.append(f'Designation: {old_position} → {new_position}')
            db.session.add(WorkerModification(
                worker_id=worker.id, mod_type='promotion', field_name='Designation',
                old_value=old_position, new_value=new_position,
                description=description or 'Promotion',
                effective_date=effective_date, created_by=current_user.id,
            ))
        if new_salary > 0:
            field_map = {
                'daily': 'daily_rate', 'monthly': 'monthly_salary',
                'hourly': 'hourly_rate', 'project': 'project_rate',
            }
            field = field_map.get(worker.pay_type, 'monthly_salary')
            old_salary = getattr(worker, field)
            setattr(worker, field, new_salary)
            changes.append(f'Salary: {old_salary or 0:g} → {new_salary:g}')
            db.session.add(WorkerModification(
                worker_id=worker.id, mod_type='salary_change', field_name=field.replace('_', ' ').title(),
                old_value=str(old_salary) if old_salary is not None else None,
                new_value=str(new_salary),
                description=description or 'Salary revision with promotion',
                effective_date=effective_date, created_by=current_user.id,
            ))
        if not changes:
            flash('Nothing to update — enter a new designation and/or salary.', 'warning')
            return redirect(url_for('worker_profile', worker_id=worker.id))
        worker.updated_at = now_ist()
        db.session.commit()
        flash(f'Promotion recorded for {worker.full_name}: ' + '; '.join(changes), 'success')

    elif mod_type == 'salary_change':
        new_salary = parse_float(request.form.get('new_salary'), 0.0)
        if new_salary <= 0:
            flash('Please enter the new salary amount.', 'error')
            return redirect(url_for('worker_profile', worker_id=worker.id))
        field_map = {
            'daily': 'daily_rate', 'monthly': 'monthly_salary',
            'hourly': 'hourly_rate', 'project': 'project_rate',
        }
        field = field_map.get(worker.pay_type, 'monthly_salary')
        old_salary = getattr(worker, field)
        setattr(worker, field, new_salary)
        worker.updated_at = now_ist()
        db.session.add(WorkerModification(
            worker_id=worker.id, mod_type='salary_change', field_name=field.replace('_', ' ').title(),
            old_value=str(old_salary) if old_salary is not None else None,
            new_value=str(new_salary),
            description=description or 'Salary increment',
            effective_date=effective_date, created_by=current_user.id,
        ))
        db.session.commit()
        flash(f'Salary updated for {worker.full_name}. Payroll recalculates automatically.', 'success')

    elif mod_type in ('bonus', 'incentive', 'refreshment', 'extra_payment'):
        amount = parse_float(request.form.get('amount'), 0.0)
        if amount <= 0:
            flash('Please enter the payment amount.', 'error')
            return redirect(url_for('worker_profile', worker_id=worker.id))
        db.session.add(WorkerTransaction(
            worker_id=worker.id, txn_type=mod_type, amount=amount,
            date=effective_date, description=description,
            created_by=current_user.id,
        ))
        db.session.add(WorkerModification(
            worker_id=worker.id, mod_type=mod_type, field_name='Payment',
            new_value=f'₹{amount:,.2f}',
            description=description or TRANSACTION_TYPE_LABELS.get(mod_type, mod_type).title(),
            effective_date=effective_date, created_by=current_user.id,
        ))
        db.session.commit()
        flash(f'{TRANSACTION_TYPE_LABELS.get(mod_type, mod_type).title()} of ₹{amount:,.2f} added for {worker.full_name}.', 'success')

    elif mod_type == 'leave_grant':
        days = parse_float(request.form.get('days'), 0.0)
        if days == 0:
            flash('Please enter the number of leave days to credit or debit.', 'error')
            return redirect(url_for('worker_profile', worker_id=worker.id))
        db.session.add(LeaveAdjustment(
            worker_id=worker.id, days=days,
            reason=description or 'Manual leave adjustment',
            effective_date=effective_date,
            created_by=current_user.id,
        ))
        db.session.add(WorkerModification(
            worker_id=worker.id, mod_type='leave_grant', field_name='Leave Balance',
            new_value=f'{days:+g} day(s)',
            description=description or 'Manual leave balance adjustment',
            effective_date=effective_date, created_by=current_user.id,
        ))
        db.session.commit()
        flash(f'Leave balance adjusted by {days:+g} day(s) for {worker.full_name}.', 'success')

    else:
        db.session.add(WorkerModification(
            worker_id=worker.id, mod_type='other', field_name=None,
            description=description or 'Record note',
            effective_date=effective_date, created_by=current_user.id,
        ))
        db.session.commit()
        flash('Modification note recorded.', 'success')

    return redirect(url_for('worker_profile', worker_id=worker.id))

# ============================================================
# Project / Site Assignment (Admin)
# ============================================================

@app.route('/worker/<int:worker_id>/assign', methods=['POST'])
@admin_required
def worker_assign(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    project_id = parse_int(request.form.get('project_id'), 0) or None
    site_id = parse_int(request.form.get('site_id'), 0) or None
    task_id = parse_int(request.form.get('task_id'), 0) or None
    notes = request.form.get('notes', '').strip() or None
    start_raw = request.form.get('start_date')
    try:
        start_date = datetime.strptime(start_raw, '%Y-%m-%d').date() if start_raw else today_ist()
    except ValueError:
        start_date = today_ist()

    if not project_id and not site_id:
        flash('Choose a project and/or a site for the assignment.', 'error')
        return redirect(safe_redirect_target(request.form.get('redirect_to'),
                                             url_for('worker_profile', worker_id=worker.id)))

    # Close the previous active assignment as a transfer. Assignment ranges are
    # inclusive, so the old assignment ends the day before the new one starts —
    # otherwise both count as active on the transfer day in closures/payroll.
    previous = worker.current_assignment
    if previous:
        previous.status = 'transferred'
        if not previous.end_date:
            handover = start_date - timedelta(days=1)
            previous.end_date = max(handover, previous.start_date)

    assignment = ProjectAssignment(
        worker_id=worker.id,
        project_id=project_id,
        site_id=site_id,
        task_id=task_id,
        start_date=start_date,
        notes=notes,
        created_by=current_user.id,
    )
    db.session.add(assignment)

    target = []
    if project_id:
        project = tenant_get(Project, project_id)
        if project:
            target.append(f'project {project.name}')
    if site_id:
        site = tenant_get(Site, site_id)
        if site:
            target.append(f'site {site.name}')
    db.session.add(WorkerModification(
        worker_id=worker.id, mod_type='assignment', field_name='Assignment',
        old_value=None, new_value=' / '.join(target) or None,
        description=notes or ('Assigned to ' + ' and '.join(target) if target else 'Assignment'),
        effective_date=start_date, created_by=current_user.id,
    ))
    db.session.commit()
    flash(f'{worker.full_name} assigned to ' + ' and '.join(target) + '.', 'success')
    return redirect(safe_redirect_target(request.form.get('redirect_to'),
                                         url_for('worker_profile', worker_id=worker.id)))

@app.route('/assignments')
@admin_required
def assignments():
    """Dedicated screen to assign, transfer and manage workers across
    sites/projects/tasks without opening each profile individually."""
    site_filter = parse_int(request.args.get('site'), 0)
    project_filter = parse_int(request.args.get('project'), 0)
    search = (request.args.get('search') or '').strip().lower()
    show = request.args.get('show', 'all')  # all | assigned | unassigned

    workers = roster_query().all()
    rows = []
    # Counted over everything the site, project and search filters allow, and
    # before the assigned/unassigned filter — these numbers sit on the chips
    # that apply that filter, so counting after it made each chip report the
    # answer you would get by pressing the other one. Filtering to Assigned
    # showed "Unassigned 0".
    counts = {'all': 0, 'assigned': 0, 'unassigned': 0}
    for worker in workers:
        assignment = worker.current_assignment
        if site_filter and (not assignment or assignment.site_id != site_filter):
            continue
        if project_filter and (not assignment or assignment.project_id != project_filter):
            continue
        if search and search not in worker.full_name.lower() and search not in worker.worker_id.lower():
            continue
        counts['all'] += 1
        counts['assigned' if assignment else 'unassigned'] += 1
        if show == 'assigned' and not assignment:
            continue
        if show == 'unassigned' and assignment:
            continue
        rows.append({'worker': worker, 'assignment': assignment})

    sites = Site.query.order_by(Site.name).all()
    projects = Project.query.order_by(Project.name).all()
    tasks = WorkTask.query.order_by(WorkTask.name).all()
    return render_template('assignments.html', rows=rows, sites=sites,
                           projects=projects, tasks=tasks,
                           site_filter=site_filter, project_filter=project_filter,
                           search=request.args.get('search', ''), show=show,
                           counts=counts, today=today_ist())

@app.route('/worker/<int:worker_id>/assignment/<int:assignment_id>/end', methods=['POST'])
@admin_required
def worker_assignment_end(worker_id, assignment_id):
    assignment = tenant_get_or_404(ProjectAssignment, assignment_id)
    if assignment.worker_id != worker_id:
        flash('Assignment does not belong to this worker.', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))
    assignment.status = 'completed'
    assignment.end_date = today_ist()
    db.session.commit()
    flash('Assignment marked as completed.', 'success')
    return redirect(safe_redirect_target(request.form.get('redirect_to'),
                                         url_for('worker_profile', worker_id=worker_id)))

# ============================================================
# Attendance time adjustment (Admin only)
# ============================================================

@app.route('/attendance/<int:record_id>/adjust', methods=['POST'])
@admin_required
def attendance_adjust(record_id):
    record = tenant_get_or_404(AttendanceRecord, record_id)
    worker = tenant_get_or_404(Worker, record.worker_id)

    status = request.form.get('status', record.status)
    if status in ('present', 'absent', 'late', 'leave'):
        record.status = status

    def _parse_time_field(name):
        raw = (request.form.get(name) or '').strip()
        if not raw:
            return None
        try:
            parsed = datetime.strptime(raw, '%H:%M').time()
        except ValueError:
            return None
        return datetime.combine(record.date, parsed)

    if record.status in ('present', 'late'):
        check_in = _parse_time_field('check_in_time')
        check_out = _parse_time_field('check_out_time')
        record.check_in_time = check_in
        record.check_out_time = check_out
        if check_in and check_out and check_out <= check_in:
            # Overnight shift — checkout lands on the next day
            record.check_out_time = check_out + timedelta(days=1)
        if record.status == 'present' and check_in and is_late_check_in(worker, record.date, check_in):
            record.status = 'late'
        record.late_minutes = calculate_late_minutes_for_record(worker, record)
        record.overtime_minutes = (
            calculate_overtime_minutes_for_record(worker, record)
            if record.check_out_time else 0
        )
    else:
        record.check_in_time = None
        record.check_out_time = None
        record.overtime_minutes = 0
        record.late_minutes = 0
        record.leave_type = request.form.get('leave_type') or record.leave_type

    record.notes = request.form.get('notes', '').strip() or record.notes
    record.marked_by = current_user.id
    db.session.commit()
    flash(f'Attendance adjusted for {worker.full_name}.', 'success')
    return redirect(safe_redirect_target(request.form.get('redirect_to'), url_for('attendance', date=record.date.isoformat())))

# ============================================================
# Service worker (served from root so its scope covers the whole app)
# ============================================================

@app.route('/sw.js')
def service_worker():
    """Serve the service worker from the site root.

    A service worker can only control pages at or below the path it is served
    from. When it was served from /static/sw.js its scope was /static/, so it
    never intercepted navigations to /dashboard, /workers, etc. — the page
    cache did nothing and every screen hit the network. Serving it here with
    Service-Worker-Allowed: / lets it control the entire origin, so cached
    pages open instantly and offline works for real screens."""
    response = make_response(app.send_static_file('sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# ============================================================
# QR Scanner & Manual Employee ID attendance
# ============================================================

def _fmt_clock(value):
    """12-hour display time without a leading zero (e.g. 8:58 AM)."""
    return value.strftime('%I:%M %p').lstrip('0') if value else None


def _attendance_state(record):
    """Today's attendance for one worker, as the scanner UI consumes it."""
    return {
        'status': record.status if record else None,
        'check_in': _fmt_clock(record.check_in_time) if record else None,
        'check_out': _fmt_clock(record.check_out_time) if record else None,
        'overtime_minutes': (record.overtime_minutes or 0) if record else 0,
        'late_minutes': (record.late_minutes or 0) if record else 0,
        'can_check_in': not record or not record.check_in_time,
        'can_check_out': bool(record and record.check_in_time and not record.check_out_time
                              and record.status in ('present', 'late')),
        'shift_open': bool(record and record.check_in_time and not record.check_out_time),
    }


def attendance_row_meta(worker, record):
    """The single muted line under a worker's name on the entry panel.

    Examples:
        CO001 · 8:58 AM · shift open
        CO002 · 9:04 AM → 6:12 PM · +52m
        CO005 · not marked
    """
    parts = [worker.worker_id]
    if not record:
        parts.append('not marked')
        return ' · '.join(parts)

    if record.check_in_time:
        clock = _fmt_clock(record.check_in_time)
        if record.check_out_time:
            clock += ' → ' + _fmt_clock(record.check_out_time)
        parts.append(clock)
        if record.late_minutes and record.late_minutes > 0:
            parts.append(f'{record.late_minutes}m late')
        if record.check_out_time:
            if record.overtime_minutes and record.overtime_minutes > 0:
                parts.append(f'+{record.overtime_minutes}m')
        else:
            parts.append('shift open')
    else:
        # absent / leave carry no clock times
        parts.append(record.status)
    return ' · '.join(parts)


def _scan_stats(on_date):
    """Live counters for the scanner header, over the workers this user may see.

    'open' is the count of shifts checked in but not yet checked out. Workers
    with no record at all count as absent, matching the attendance screen.
    """
    # Same worker set as the day panel and bulk actions, so site/project
    # scoping and the join-date rule apply to the counters as well.
    worker_ids = [w.id for w in _visible_active_workers(on_date)]

    records = []
    if worker_ids:
        records = AttendanceRecord.query.filter(
            AttendanceRecord.date == on_date,
            AttendanceRecord.worker_id.in_(worker_ids),
        ).all()

    counts = {}
    open_shifts = 0
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.check_in_time and not record.check_out_time:
            open_shifts += 1

    return {
        'present': counts.get('present', 0),
        'late': counts.get('late', 0),
        # Explicitly-absent plus everyone not marked yet.
        'absent': counts.get('absent', 0) + (len(worker_ids) - len(records)),
        'open': open_shifts,
    }


@app.route('/scan')
@login_required
def scan():
    today = today_ist()
    # The payment picker's options. Grouped the way the transactions screen
    # groups them, because "Advance" taking money off a wage and "Bonus"
    # adding to it are opposite acts that read alike in a flat list.
    return render_template(
        'scan.html', today=today, stats=_scan_stats(today),
        deduction_types=TRANSACTION_DEDUCTION_TYPES,
        earning_types=TRANSACTION_EARNING_TYPES,
        type_labels=TRANSACTION_TYPE_LABELS)

@app.route('/api/worker_lookup')
@login_required
def api_worker_lookup():
    """Resolve a QR payload or manually typed employee ID to a worker."""
    code = (request.args.get('code') or '').strip()
    if code.upper().startswith('SMARTWORKER:'):
        code = code.split(':', 1)[1].strip()
    if not code:
        return jsonify({'success': False, 'message': 'Enter or scan an employee ID.'}), 400

    worker = Worker.query.filter(func.upper(Worker.worker_id) == code.upper()).first()
    today = today_ist()

    # Scoped attendance users get one generic failure for missing, inactive and
    # out-of-scope workers so the endpoint doesn't confirm which IDs exist.
    if not current_user.is_admin:
        if (not worker or worker.status != 'active'
                or not worker_visible_to_user(worker, current_user, on_date=today)):
            return jsonify({
                'success': False,
                'message': 'No matching worker on your site. Check the ID or contact the Administrator.',
            }), 404
    else:
        if not worker:
            return jsonify({'success': False, 'message': f'No worker found for ID {code}.'}), 404
        if worker.status != 'active':
            return jsonify({'success': False, 'message': f'{worker.full_name} is inactive.'}), 403
    record = AttendanceRecord.query.filter_by(worker_id=worker.id, date=today).first()
    assignment = worker.current_assignment
    closure = closure_for_worker_on_date(worker, today)

    return jsonify({
        'success': True,
        'worker': {
            'id': worker.id,
            'worker_id': worker.worker_id,
            'name': worker.full_name,
            'position': worker.position,
            'department': worker.department,
            'photo': worker.profile_image,
            'profile_url': url_for('worker_profile', worker_id=worker.id),
            'site': assignment.site.name if assignment and assignment.site else None,
            'project': assignment.project.name if assignment and assignment.project else None,
            # Whether to offer the payment section at all. Checked per worker,
            # not per user: a mukadam may book money for their own list and
            # nobody else's, so the answer can differ between two scans.
            'can_pay': may_record_transaction_for(current_user, worker),
        },
        'attendance': _attendance_state(record),
        'closure': {
            'reason': closure.reason,
            'locked': not closure.allow_attendance,
        } if closure else None,
    })


def _visible_active_workers(on_date):
    """Workers this user may act on for this date.

    Single enforcement point for two rules, so every caller (day payload,
    bulk actions, counters) inherits them:
      * attendance-role users only see their assigned sites/projects
      * a worker hired after the date was not employed then, so they are
        excluded entirely rather than counted as absent
    """
    workers = roster_query().all()
    return [
        w for w in workers
        if worker_visible_to_user(w, current_user, on_date=on_date)
        and not (w.join_date and w.join_date > on_date)
    ]


def _attendance_rows(on_date):
    """Roster state for in-place updates after a bulk action."""
    workers = _visible_active_workers(on_date)
    records = {}
    if workers:
        records = {
            r.worker_id: r
            for r in AttendanceRecord.query.filter(
                AttendanceRecord.date == on_date,
                AttendanceRecord.worker_id.in_([w.id for w in workers]),
            ).all()
        }
    closures = ClosureDay.query.filter_by(date=on_date).all()

    rows = []
    for worker in workers:
        record = records.get(worker.id)
        closure = closure_for_worker_on_date(worker, on_date, closures)
        rows.append({
            'id': worker.id,
            'status': record.status if record else None,
            'meta': attendance_row_meta(worker, record),
            'locked': bool(closure and not closure.allow_attendance),
        })
    return rows


def parse_iso_date(value):
    """Server-side date parsing. The client never decides what today is."""
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _date_editability(on_date):
    """Whether attendance may be written for this date, and why not.

    Returns (editable, reason, message). 'reason' is machine-readable so the
    panel can style itself; 'message' is what the user reads.
    """
    if on_date > today_ist():
        return False, 'future', 'This date is in the future — attendance cannot be marked yet.'
    company_lock = ClosureDay.query.filter_by(date=on_date).filter(
        ClosureDay.scope.in_(('company', '', None))
    ).filter(ClosureDay.allow_attendance.is_(False)).first()
    if company_lock:
        return False, 'closure_locked', f'Attendance is locked on this closure day ({company_lock.reason}).'
    return True, 'ok', ''


def _payroll_lock_note(on_date):
    """Warn when editing a month whose payroll has already been generated."""
    saved = PayrollRecord.query.filter_by(month=on_date.month, year=on_date.year).first()
    if not saved:
        return None
    return (f'Payroll for {MONTH_NAMES[on_date.month - 1]} {on_date.year} has already been '
            f'generated. Re-generate it so this change is reflected in pay.')


def _log_attendance_edit(worker, on_date, field, old_value, new_value):
    """Audit trail for edits to a past date.

    WorkerModification already carries old/new value, effective date and author,
    so attendance edits live there rather than in a second log table.
    """
    if on_date >= today_ist():
        return
    db.session.add(WorkerModification(
        worker_id=worker.id,
        mod_type='attendance_edit',
        field_name=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        description=f'Attendance {field} edited for {on_date.isoformat()}',
        effective_date=on_date,
        created_by=current_user.id,
    ))


def _day_payload(on_date):
    """Everything the day panel renders, for one date.

    Every write endpoint returns this so the panel refreshes from a single
    response instead of re-fetching.
    """
    editable, reason, message = _date_editability(on_date)
    closures = ClosureDay.query.filter_by(date=on_date).all()
    workers = _visible_active_workers(on_date)
    worker_ids = [w.id for w in workers]

    records = {}
    if worker_ids:
        records = {
            r.worker_id: r for r in AttendanceRecord.query.filter(
                AttendanceRecord.date == on_date,
                AttendanceRecord.worker_id.in_(worker_ids),
            ).all()
        }

    counts = {'present': 0, 'late': 0, 'absent': 0, 'leave': 0, 'not_marked': 0}
    rows = []
    for worker in workers:
        record = records.get(worker.id)
        worker_closure = closure_for_worker_on_date(worker, on_date, closures)
        assignment = next(
            (a for a in worker.assignments if assignment_active_on(a, on_date)), None)

        if record and record.status in counts:
            counts[record.status] += 1
        elif not record:
            counts['not_marked'] += 1

        where = None
        if assignment:
            parts = [p for p in (
                assignment.site.name if assignment.site else None,
                assignment.project.name if assignment.project else None,
            ) if p]
            where = ' · '.join(parts) or None

        rows.append({
            'id': worker.id,
            'name': worker.full_name,
            'worker_id': worker.worker_id,
            'department': worker.department,
            'status': record.status if record else None,
            'check_in': _fmt_clock(record.check_in_time) if record else None,
            'check_out': _fmt_clock(record.check_out_time) if record else None,
            # 24h values for the time inputs, which need HH:MM
            'check_in_value': record.check_in_time.strftime('%H:%M') if record and record.check_in_time else '',
            'check_out_value': record.check_out_time.strftime('%H:%M') if record and record.check_out_time else '',
            'shift_open': bool(record and record.check_in_time and not record.check_out_time),
            'worked_minutes': record.worked_minutes if record else 0,
            'overtime_minutes': (record.overtime_minutes or 0) if record else 0,
            'late_minutes': (record.late_minutes or 0) if record else 0,
            'where': where,
            'locked': bool(worker_closure and not worker_closure.allow_attendance),
            'meta': attendance_row_meta(worker, record),
        })

    transactions = []
    if worker_ids:
        for txn in WorkerTransaction.query.filter(
            WorkerTransaction.date == on_date,
            WorkerTransaction.worker_id.in_(worker_ids),
        ).order_by(WorkerTransaction.id).all():
            transactions.append({
                'id': txn.id,
                'worker': txn.worker.full_name if txn.worker else '',
                # Built into markup by the day view's own JS, so it has to
                # arrive in the interface language.
                'type': i18n.translate(
                    TRANSACTION_TYPE_LABELS.get(
                        txn.txn_type, txn.txn_type.replace('_', ' ').title()),
                    _current_lang()),
                'amount': round(txn.amount, 2),
                'is_earning': txn.is_earning,
                'status': txn.status,
                'description': txn.description or '',
            })

    return {
        'date': on_date.isoformat(),
        # The day view builds its own markup in JS, so these two land on the
        # screen verbatim — they have to come back in the interface language.
        'date_label': _ldate(on_date, '%d %B %Y'),
        'weekday': _ldate(on_date, '%A'),
        'is_today': on_date == today_ist(),
        'editable': editable,
        'reason': reason,
        'message': message,
        'payroll_note': _payroll_lock_note(on_date),
        'closures': [{
            'id': c.id,
            'reason': c.reason,
            'type': c.type,
            'scope': c.scope or 'company',
            'allow_attendance': bool(c.allow_attendance),
        } for c in closures],
        'counts': counts,
        'rows': rows,
        'transactions': transactions,
    }


@app.route('/api/attendance/day/<day>')
@login_required
def api_attendance_day(day):
    """Everything the day panel shows for one date."""
    on_date = parse_iso_date(day)
    if not on_date:
        return jsonify({'success': False, 'message': 'Invalid date.'}), 400
    # stats/rows travel with the day so selecting a date can re-point the whole
    # screen — including the entry panel — at it in one request. Without this
    # the entry panel keeps writing to the date the page was rendered with.
    return jsonify({
        'success': True,
        'day': _day_payload(on_date),
        'stats': _scan_stats(on_date),
        'rows': _attendance_rows(on_date),
    })


@app.route('/api/attendance/times', methods=['POST'])
@login_required
def api_attendance_times():
    """Edit check-in / check-out for one worker on one date.

    Worked, overtime and late minutes are recomputed from the saved times by
    the same helpers the normal marking path uses.
    """
    on_date = parse_iso_date(request.form.get('date'))
    if not on_date:
        return jsonify({'success': False, 'message': 'Invalid date.'}), 400

    editable, _reason, message = _date_editability(on_date)
    if not editable:
        return jsonify({'success': False, 'messages': [{'category': 'error', 'text': message}],
                        'day': _day_payload(on_date)}), 200

    worker = tenant_get_or_404(Worker, parse_int(request.form.get('worker_id')))
    if not worker_visible_to_user(worker, current_user, on_date=on_date):
        return jsonify({'success': False,
                        'messages': [{'category': 'restricted',
                                      'text': 'Please contact the Administrator to make changes.'}],
                        'day': _day_payload(on_date)}), 200
    if worker.join_date and worker.join_date > on_date:
        return jsonify({'success': False,
                        'messages': [{'category': 'error',
                                      'text': f'{worker.full_name} had not joined on this date.'}],
                        'day': _day_payload(on_date)}), 200

    worker_closure = closure_for_worker_on_date(worker, on_date)
    if worker_closure and not worker_closure.allow_attendance:
        return jsonify({'success': False,
                        'messages': [{'category': 'error',
                                      'text': f'Attendance is locked for {worker.full_name} on this closure day.'}],
                        'day': _day_payload(on_date)}), 200

    def _combine(raw):
        raw = (raw or '').strip()
        if not raw:
            return None
        try:
            return datetime.combine(on_date, datetime.strptime(raw, '%H:%M').time())
        except ValueError:
            return None

    check_in = _combine(request.form.get('check_in'))
    check_out = _combine(request.form.get('check_out'))
    if check_out and not check_in:
        return jsonify({'success': False,
                        'messages': [{'category': 'error',
                                      'text': 'A check-out needs a check-in time as well.'}],
                        'day': _day_payload(on_date)}), 200
    if check_in and check_out and check_out <= check_in:
        return jsonify({'success': False,
                        'messages': [{'category': 'error',
                                      'text': 'Check-out must be later than check-in.'}],
                        'day': _day_payload(on_date)}), 200

    # Upsert: one record per worker per date (models.py uq_attendance_worker_date)
    record = AttendanceRecord.query.filter_by(worker_id=worker.id, date=on_date).first()
    if not record:
        assignment = next(
            (a for a in worker.assignments if assignment_active_on(a, on_date)), None)
        record = AttendanceRecord(
            worker_id=worker.id, date=on_date,
            status='present' if check_in else 'absent',
            marked_by=current_user.id, marked_via='manual',
            site_id=assignment.site_id if assignment else None,
        )
        db.session.add(record)

    _log_attendance_edit(worker, on_date, 'check_in',
                         _fmt_clock(record.check_in_time), _fmt_clock(check_in))
    _log_attendance_edit(worker, on_date, 'check_out',
                         _fmt_clock(record.check_out_time), _fmt_clock(check_out))

    record.check_in_time = check_in
    record.check_out_time = check_out
    record.marked_by = current_user.id
    if check_in and record.status not in ('present', 'late'):
        record.status = 'present'
    record.late_minutes = calculate_late_minutes_for_record(worker, record) if check_in else 0
    record.overtime_minutes = (
        calculate_overtime_minutes_for_record(worker, record) if check_in and check_out else 0)
    db.session.commit()

    messages = [{'category': 'success', 'text': f'Times updated for {worker.full_name}.'}]
    note = _payroll_lock_note(on_date)
    if note:
        messages.append({'category': 'warning', 'text': note})
    return jsonify({'success': True, 'messages': messages, 'day': _day_payload(on_date)})


@app.route('/api/attendance/transaction', methods=['POST'])
@admin_required
def api_attendance_transaction():
    """Add a transaction dated to the selected day, from the day panel."""
    on_date = parse_iso_date(request.form.get('date'))
    if not on_date:
        return jsonify({'success': False, 'message': 'Invalid date.'}), 400

    worker = tenant_get_or_404(Worker, parse_int(request.form.get('worker_id')))
    txn_type = request.form.get('txn_type', '')
    amount = parse_float(request.form.get('amount'), 0.0)

    if txn_type not in TRANSACTION_TYPE_LABELS:
        return jsonify({'success': False,
                        'messages': [{'category': 'error', 'text': 'Choose a valid transaction type.'}],
                        'day': _day_payload(on_date)}), 200
    if amount <= 0:
        return jsonify({'success': False,
                        'messages': [{'category': 'error', 'text': 'Amount must be greater than zero.'}],
                        'day': _day_payload(on_date)}), 200

    txn = WorkerTransaction(
        worker_id=worker.id, txn_type=txn_type, amount=amount, date=on_date,
        description=request.form.get('description', '').strip() or None,
        created_by=current_user.id,
    )
    db.session.add(txn)
    db.session.commit()

    messages = [{'category': 'success',
                 'text': f'{TRANSACTION_TYPE_LABELS[txn_type]} of ₹{amount:.2f} added for {worker.full_name}.'}]
    note = _payroll_lock_note(on_date)
    if note:
        messages.append({'category': 'warning', 'text': note})
    return jsonify({'success': True, 'messages': messages, 'day': _day_payload(on_date)})


@app.route('/api/attendance/closure', methods=['POST'])
@admin_required
def api_attendance_closure():
    """Add or remove a company-scope closure on the selected day."""
    on_date = parse_iso_date(request.form.get('date'))
    if not on_date:
        return jsonify({'success': False, 'message': 'Invalid date.'}), 400

    action = request.form.get('action', 'add')
    if action == 'remove':
        closure = tenant_get(ClosureDay, parse_int(request.form.get('closure_id')))
        if not closure or closure.date != on_date:
            return jsonify({'success': False,
                            'messages': [{'category': 'error', 'text': 'Closure not found for this date.'}],
                            'day': _day_payload(on_date)}), 200
        db.session.delete(closure)
        db.session.commit()
        return jsonify({'success': True,
                        'messages': [{'category': 'success', 'text': 'Closure removed.'}],
                        'day': _day_payload(on_date)})

    reason = request.form.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False,
                        'messages': [{'category': 'error', 'text': 'A closure needs a reason.'}],
                        'day': _day_payload(on_date)}), 200
    closure_type = request.form.get('type', 'holiday').strip().lower()
    if closure_type not in ('holiday', 'site', 'project', 'emergency', 'maintenance'):
        closure_type = 'holiday'

    db.session.add(ClosureDay(
        date=on_date, reason=reason, type=closure_type, scope='company',
        allow_attendance=request.form.get('allow_attendance') == 'true',
    ))
    db.session.commit()
    return jsonify({'success': True,
                    'messages': [{'category': 'success', 'text': f'Closure added for {on_date.strftime("%d %b %Y")}.'}],
                    'day': _day_payload(on_date)})


@app.route('/api/attendance/bulk', methods=['POST'])
@login_required
def api_attendance_bulk():
    """Bulk actions for the entry panel: mark everyone present/absent, or close
    every open shift at once.

    'close' is the action that had no equivalent anywhere in the app: shifts
    must be checked out for overtime to be banked, and until now that meant
    tapping every worker individually. It mirrors the check-out branch of
    mark_attendance - same timestamp helper, same overtime calculation - and
    is available to attendance users too, since closing a shift is a check-out
    rather than an administrative reclassification.
    """
    on_date = parse_iso_date(request.form.get('date'))
    if not on_date:
        return jsonify({'success': False, 'message': 'Invalid date.'}), 400
    action = request.form.get('action')

    # 'present'/'absent' inherit mark_attendance's guards; 'close' writes
    # directly, so it needs the same future/closure check applied here.
    editable, _reason, block_message = _date_editability(on_date)
    if not editable:
        return jsonify({'success': False,
                        'messages': [{'category': 'error', 'text': block_message}],
                        'stats': _scan_stats(on_date),
                        'rows': _attendance_rows(on_date),
                        'day': _day_payload(on_date)}), 200

    if action in ('present', 'absent'):
        # Reuse mark_attendance's bulk branch verbatim (it reads request.form,
        # which already carries bulk_action + status from the client).
        mark_attendance()
        messages = [{'category': c, 'text': t}
                    for c, t in get_flashed_messages(with_categories=True)]
    elif action == 'close':
        closures_today = ClosureDay.query.filter_by(date=on_date).all()
        closed = 0
        overtime_total = 0
        for worker in _visible_active_workers(on_date):
            worker_closure = closure_for_worker_on_date(worker, on_date, closures_today)
            if worker_closure and not worker_closure.allow_attendance:
                continue
            record = AttendanceRecord.query.filter_by(worker_id=worker.id, date=on_date).first()
            if not (record and record.check_in_time and not record.check_out_time
                    and record.status in ('present', 'late')):
                continue
            record.check_out_time = _attendance_timestamp(on_date)
            record.overtime_minutes = calculate_overtime_minutes_for_record(worker, record)
            record.marked_by = current_user.id
            record.marked_via = 'bulk'
            overtime_total += record.overtime_minutes or 0
            closed += 1
        db.session.commit()
        if closed:
            text_msg = f'Closed {closed} shift{"s" if closed != 1 else ""}.'
            if overtime_total:
                text_msg += f' Overtime banked: {overtime_total} minutes.'
            messages = [{'category': 'success', 'text': text_msg}]
        else:
            messages = [{'category': 'info', 'text': 'No open shifts to close.'}]
    else:
        return jsonify({'success': False,
                        'messages': [{'category': 'error', 'text': 'Unknown action.'}]}), 400

    succeeded = not any(m['category'] in ('error', 'restricted') for m in messages)
    return jsonify({
        'success': succeeded,
        'messages': messages,
        'stats': _scan_stats(on_date),
        'rows': _attendance_rows(on_date),
        # Full day state so the day panel refreshes from this one response.
        'day': _day_payload(on_date),
    })


def may_record_transaction_for(user, worker):
    """Who may book money against this worker, and on what terms.

    One place for a rule that already existed in two: an administrator may
    record for anyone, and a mukadam only for the people on their own list,
    and only if that power was granted to their login. Recording only —
    editing or cancelling stays administrative, because a transaction
    somebody can both create and erase is a way to take wages off a worker
    quietly.

    In practice the scanner is administrators only today, because
    `_confine_worker_logins` holds a worker login to WORKER_ENDPOINTS and
    SUPERVISOR_ENDPOINTS and `scan` is in neither; a mukadam books money on
    their team screen instead. The mukadam branch stays here so that opening
    the scanner to them later is one line in that set and not a new rule.
    """
    if not worker:
        return False
    if user.is_admin:
        return True
    if (user.is_worker and user.can_record_transactions
            and _supervisor_may_touch(user, worker.id)):
        return True
    return False


@app.route('/api/worker_transaction', methods=['POST'])
@login_required
def api_worker_transaction():
    """Record an advance or a payment from the scanner, without navigating.

    The scanner's whole design is that marking a worker never tears down the
    camera — a page load costs about a second of black preview, and there is
    a queue at the gate. Money has to work the same way, so this answers in
    JSON like /api/mark_attendance does, and the existing form posts at
    /transactions/save and /supervisor/transaction are left exactly as they
    are for the screens that can afford to redirect.
    """
    worker = tenant_get(Worker, parse_int(request.form.get('worker_id'), 0))
    messages = []

    if not may_record_transaction_for(current_user, worker):
        # The same wording a site user gets anywhere else they are stopped,
        # and deliberately no hint about whether the worker exists.
        return jsonify({'success': False, 'messages': [
            {'category': 'restricted',
             'text': 'Please contact the Administrator to make changes.'}]}), 403

    txn_type = request.form.get('txn_type', '')
    if txn_type not in TRANSACTION_TYPE_LABELS:
        messages.append({'category': 'error',
                         'text': 'Choose a valid transaction type.'})

    amount = parse_float(request.form.get('amount'), 0.0)
    if amount <= 0:
        messages.append({'category': 'error',
                         'text': 'Amount must be greater than zero.'})

    on_date = parse_date_or(request.form.get('date')) or today_ist()
    if on_date > today_ist():
        messages.append({'category': 'error', 'text': 'That date is in the future.'})

    if messages:
        return jsonify({'success': False, 'messages': messages}), 400

    label = TRANSACTION_TYPE_LABELS[txn_type]
    note = (request.form.get('description') or '').strip() or label
    db.session.add(WorkerTransaction(
        worker_id=worker.id, txn_type=txn_type, amount=amount, date=on_date,
        description=note, created_by=current_user.id,
        account_id=worker.account_id,
    ))

    # Money booked by somebody who is not an administrator should be visible
    # to one without their having to go looking, the same way attendance
    # marked at a site is.
    if not current_user.is_admin:
        notify_admin(
            f'{worker.full_name} ({worker.worker_id}){NOTE_DASH}{label}',
            f'{current_user.full_name} · {money.money(amount)} · scanner',
            category='transaction',
        )

    db.session.commit()
    return jsonify({
        'success': True,
        'messages': [{'category': 'success',
                      'text': f'{label} {money.money(amount)} recorded for '
                              f'{worker.full_name}.'}],
        'transaction': {
            'type': txn_type,
            'label': label,
            'amount': amount,
            'amount_text': money.money(amount),
            'date': on_date.isoformat(),
        },
    })


@app.route('/api/mark_attendance', methods=['POST'])
@login_required
def api_mark_attendance():
    """JSON wrapper around mark_attendance for the scanner screen.

    Posting the normal form would navigate, and a screen swap tears down the
    camera stream (roughly a second of black preview per worker). This reuses
    the exact same validation/persistence path — it just reports the outcome as
    JSON, along with refreshed header counts and the worker's new state, so the
    scanner can update in place and stay live.
    """
    mark_attendance()  # validates, persists and flashes; its redirect is unused
    messages = [{'category': category, 'text': text}
                for category, text in get_flashed_messages(with_categories=True)]
    succeeded = not any(m['category'] in ('error', 'restricted') for m in messages)

    # Mirror the date the mark was actually applied to, so backdated marking
    # from the roster refreshes the row the user is looking at.
    try:
        on_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (KeyError, ValueError):
        on_date = today_ist()

    worker_id = parse_int(request.form.get('worker_id'))
    record = None
    worker = None
    if worker_id:
        record = AttendanceRecord.query.filter_by(worker_id=worker_id, date=on_date).first()
        worker = tenant_get(Worker, worker_id)

    return jsonify({
        'success': succeeded,
        'messages': messages,
        'stats': _scan_stats(on_date),
        'attendance': _attendance_state(record),
        'row': {
            'id': worker_id,
            'status': record.status if record else None,
            'meta': attendance_row_meta(worker, record) if worker else None,
        },
        # Full day state so the day panel refreshes from this one response.
        'day': _day_payload(on_date),
    })

# ============================================================
# Notifications (Admin)
# ============================================================

# The dash that separates the subject of a notification from its outcome —
# "Ravi Kumar (W-014) — present". Folding a run depends on being able to tell
# the two apart, so the writer and the reader share one constant.
NOTE_DASH = ' — '

# Stored outcomes are the raw attendance statuses. These are the display keys
# that the Hindi table knows; anything not listed is shown as stored.
NOTE_OUTCOMES = {
    'present': 'Present',
    'absent': 'Absent',
    'late': 'Late',
    'leave': 'Leave',
    'on leave': 'Leave',
    'half_day': 'Half Day',
    'half day': 'Half Day',
    'checked out': 'Checked Out',
}

# How many names a folded line spells out before it starts counting.
NOTE_NAMES_SHOWN = 4

# bulk.py writes one notification for a whole bulk action, so its subject is
# already a count rather than a name: "6 workers — present". Recognising that
# lets the reader rebuild the sentence in the interface language instead of
# printing the stored English noun — the count is the same shape as a folded
# run, so it takes the same branch.
NOTE_COUNT_SUBJECT = re.compile(r'^(\d+)\s+workers?$', re.I)


def notification_day_label(day, today):
    """"Today", "Yesterday", or the date itself."""
    delta = (today - day).days
    if delta == 0:
        return 'Today'
    if delta == 1:
        return 'Yesterday'
    return None          # the template formats the date through ldate


def group_notifications(items, today):
    """Group the feed by day and fold a run from one action into one line.

    Rows arrive newest first. A site user marking six workers one after
    another writes six rows that differ only in the name, and reading them
    meant reading the same sentence six times. A folded line is still every
    one of those rows: it carries all their ids, so selecting it selects the
    whole run, and it names the workers underneath rather than hiding them.

    Only an unbroken run of rows sharing the same category, the same body and
    the same outcome folds. Anything the writer did not shape that way — an
    older row, a row from somewhere else in the app — has no outcome to match
    on and stays a line of its own.
    """
    groups = []
    for item in items:
        day = item.created_at.date()
        if not groups or groups[-1]['date'] != day:
            groups.append({
                'date': day,
                'label': notification_day_label(day, today),
                'rows': [],
            })
        rows = groups[-1]['rows']

        subject, dash, outcome = (item.title or '').partition(NOTE_DASH)
        outcome = outcome.strip()
        key = (item.category, item.body or '', outcome) if dash and outcome else None

        previous = rows[-1] if rows else None
        if key and previous and previous['key'] == key:
            previous['ids'].append(item.id)
            previous['names'].append(subject.strip())
            previous['unread'] = previous['unread'] or not item.is_read
            continue


        subject = subject.strip()
        already_counted = NOTE_COUNT_SUBJECT.match(subject) if key else None
        rows.append({
            'key': None if already_counted else key,   # never fold a count
            'ids': [item.id],
            'names': [] if (already_counted or not key) else [subject],
            'stated': int(already_counted.group(1)) if already_counted else 0,
            'title': item.title,
            'outcome': NOTE_OUTCOMES.get(outcome.lower(), outcome),
            'body': item.body or '',
            'category': item.category,
            'created_at': item.created_at,
            'unread': not item.is_read,
        })

    for group in groups:
        for row in group['rows']:
            # What the line stands for: the records folded into it, or the
            # number a bulk notification already states.
            row['count'] = row['stated'] or len(row['ids'])
            # The names line says who is behind a folded line. An unfolded
            # row already has its name in the title, so listing it underneath
            # would print the same name twice. Forty names is the wall the
            # folding was meant to remove, so name enough to recognise the
            # run and count the rest.
            names = row['names'] if len(row['ids']) > 1 else []
            row['shown'] = names[:NOTE_NAMES_SHOWN]
            row['more'] = max(0, len(names) - NOTE_NAMES_SHOWN)
    return groups


@app.route('/notifications')
@admin_required
def notifications():
    items = Notification.query.order_by(Notification.created_at.desc()).limit(100).all()
    return render_template('notifications.html',
                           notifications=items,
                           groups=group_notifications(items, today_ist()))

@app.route('/notifications/mark_read', methods=['POST'])
@admin_required
def notifications_mark_read():
    Notification.query.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return redirect(url_for('notifications'))

# ============================================================
# Professional Worker PDF Report
# ============================================================

@app.route('/worker/<int:worker_id>/report')
@admin_required
def worker_report(worker_id):
    worker = tenant_get_or_404(Worker, worker_id)
    today = today_ist()

    # Attendance summary for the last 6 months
    monthly_history = []
    for offset in range(5, -1, -1):
        anchor_month = (today.month - offset - 1) % 12 + 1
        anchor_year = today.year + ((today.month - offset - 1) // 12)
        m_start = date(anchor_year, anchor_month, 1)
        _, m_days = _cal.monthrange(anchor_year, anchor_month)
        m_end = date(anchor_year, anchor_month, m_days)
        if m_end < worker.join_date:
            continue
        records = AttendanceRecord.query.filter(
            AttendanceRecord.worker_id == worker.id,
            AttendanceRecord.date >= m_start,
            AttendanceRecord.date <= m_end,
        ).all()
        att = calculate_attendance_summary(records)
        pay = calculate_pay_summary(worker, records, m_start, m_end)
        monthly_history.append({
            'label': f'{MONTH_NAMES[anchor_month - 1]} {anchor_year}',
            'att': att,
            'pay': pay,
        })

    _, month_days = _cal.monthrange(today.year, today.month)
    leave_balance = None
    if worker.pay_type == 'monthly' and worker.leave_policy_enabled:
        leave_balance = calculate_leave_balance(
            worker, today.replace(day=1), today.replace(day=month_days)
        )

    all_transactions = WorkerTransaction.query.filter_by(
        worker_id=worker.id
    ).order_by(WorkerTransaction.date.desc()).all()

    payroll_history = PayrollRecord.query.filter_by(
        worker_id=worker.id
    ).order_by(PayrollRecord.year.desc(), PayrollRecord.month.desc()).limit(12).all()

    # Salary policy and this month's derived figures. Only meaningful for a
    # fixed monthly salary — a daily or hourly worker has no derived daily
    # rate, no basis and no joining-date proration to report.
    salary_breakdown = None
    salary_policy_rows = None
    if worker.pay_type == 'monthly':
        _ps = today.replace(day=1)
        _pe = today.replace(day=month_days)
        _recs = AttendanceRecord.query.filter(
            AttendanceRecord.worker_id == worker.id,
            AttendanceRecord.date >= _ps, AttendanceRecord.date <= _pe).all()
        _bal = calculate_leave_balance(worker, _ps, _pe)
        salary_breakdown = salary.compute(
            worker, resolve_salary_policy(worker), _recs, _ps, _pe,
            carried_leave_balance=_bal['balance_before'])
        salary_policy_rows = salary.describe(salary_breakdown['policy'])

    return render_template('worker_report.html',
                           worker=worker,
                           monthly_history=monthly_history,
                           salary_breakdown=salary_breakdown,
                           salary_policy_rows=salary_policy_rows,
                           salary_basis_label=salary.LABELS['salary_basis'].get(
                               (salary_breakdown or {}).get('salary_basis', 'fixed'), 'Fixed days'),
                           leave_balance=leave_balance,
                           all_transactions=all_transactions,
                           payroll_history=payroll_history,
                           type_labels=TRANSACTION_TYPE_LABELS,
                           month_names=MONTH_NAMES,
                           today=today,
                           date=ISTDate)


# ============================================================
# Salary calculation policy
# ============================================================

def _salary_policy_from_form(form, prefix=''):
    """Read a policy out of posted form fields.

    Returns a plain dict; validation and clamping happen once in
    salary.normalise_policy rather than being repeated here.
    """
    def field(name, default=None):
        return form.get(prefix + name, default)

    raw = {
        'salary_basis': field('salary_basis'),
        'basis_days': field('basis_days'),
        'rounding': field('rounding'),
        'joining_mode': field('joining_mode'),
        'paid_leave_enabled': field('paid_leave_enabled') == 'on',
        'monthly_leave_allowance': field('monthly_leave_allowance'),
        'leave_carry_forward': field('leave_carry_forward') == 'on',
        'absence_deduction_enabled': field('absence_deduction_enabled') == 'on',
        'calculation_method': field('calculation_method'),
    }
    rate = (field('deduction_rate') or '').strip()
    # Blank means "derive it from the salary"; the engine reads None that way.
    raw['deduction_rate'] = rate if rate else None
    return salary.normalise_policy(raw)


def _save_salary_policy(worker_id, new_policy, actor_id):
    """Write a policy row and record what changed.

    worker_id None is the company-wide default. The audit rows are what make
    a later question like "who turned absence deduction on in March"
    answerable.
    """
    row = SalaryPolicy.query.filter_by(worker_id=worker_id).first()
    before = salary.normalise_policy(row) if row else salary.normalise_policy(None)

    if not row:
        row = SalaryPolicy(worker_id=worker_id)
        db.session.add(row)

    for field_name in salary.POLICY_FIELDS:
        setattr(row, field_name, new_policy[field_name])
    row.updated_by = actor_id

    for field_name, old, new in salary.policy_differences(before, new_policy):
        db.session.add(SalaryPolicyAudit(
            worker_id=worker_id, field=field_name,
            old_value=str(old)[:60], new_value=str(new)[:60],
            changed_by=actor_id,
        ))
    return row


@app.route('/settings/salary-policy', methods=['POST'])
@admin_required
def settings_salary_policy():
    """Company-wide salary calculation policy."""
    policy = _salary_policy_from_form(request.form)
    _save_salary_policy(None, policy, current_user.id)
    db.session.commit()
    flash('Salary calculation policy saved. Payroll already marked paid is not affected.',
          'success')
    return redirect(url_for('settings') + '#section-salary')


@app.route('/worker/<int:worker_id>/salary-policy', methods=['POST'])
@admin_required
def worker_salary_policy(worker_id):
    """Per-worker override, or clearing it to fall back to the company rule."""
    worker = tenant_get_or_404(Worker, worker_id)

    if request.form.get('clear_override') == '1':
        row = SalaryPolicy.query.filter_by(worker_id=worker.id).first()
        if row:
            db.session.add(SalaryPolicyAudit(
                worker_id=worker.id, field='override',
                old_value='set', new_value='cleared', changed_by=current_user.id))
            db.session.delete(row)
            db.session.commit()
        flash(f'{worker.full_name} now follows the company salary policy.', 'success')
        return redirect(url_for('worker_profile', worker_id=worker.id))

    policy = _salary_policy_from_form(request.form)
    _save_salary_policy(worker.id, policy, current_user.id)
    db.session.commit()
    flash(f'Salary policy saved for {worker.full_name}.', 'success')
    return redirect(url_for('worker_profile', worker_id=worker.id))


@app.route('/api/salary-preview/<int:worker_id>')
@admin_required
def api_salary_preview(worker_id):
    """What this worker would be paid under a policy, before anything is saved.

    Takes the policy from the query string so the settings screen can show the
    effect of a change the employer has not committed yet.
    """
    worker = tenant_get_or_404(Worker, worker_id)
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    start = date(year, month, 1)
    end = date(year, month, _cal.monthrange(year, month)[1])

    if request.args.get('salary_basis'):
        policy = _salary_policy_from_form(request.args)
    else:
        policy = resolve_salary_policy(worker)

    records = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker.id,
        AttendanceRecord.date >= start,
        AttendanceRecord.date <= end,
    ).all()
    balance = calculate_leave_balance(worker, start, end)
    breakdown = salary.compute(worker, policy, records, start, end,
                               carried_leave_balance=balance['balance_before'])

    breakdown['worker_name'] = worker.full_name
    breakdown['worker_code'] = worker.worker_id
    breakdown['join_date'] = worker.join_date.isoformat() if worker.join_date else None
    breakdown['period'] = f'{MONTH_NAMES[month - 1]} {year}'
    return jsonify(breakdown)


@app.route('/payroll/preview')
@admin_required
def payroll_preview():
    """What generating payroll would produce, before it is generated.

    Payroll could previously only be inspected by running it. This computes
    the same rows and sets each against whatever is already saved, so an
    employer can see what a policy change does to every worker — and which
    rows a generate would leave alone because they are already paid — before
    committing to it.
    """
    today = today_ist()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, totals, _ = _build_payroll_rows(month, year)
    saved = {
        p.worker_id: p
        for p in PayrollRecord.query.filter_by(month=month, year=year).all()
    }

    preview = []
    changed = 0
    frozen = 0
    for row in rows:
        worker = row['worker']
        record = saved.get(worker.id)

        if record and record.status == 'paid':
            # Already settled: a generate skips it, so there is nothing to
            # compare — show it as locked.
            state, delta = 'frozen', 0.0
            frozen += 1
        elif record:
            delta = round(row['net_pay'] - float(record.net_pay or 0), 2)
            state = 'changed' if abs(delta) > 0.009 else 'same'
            if state == 'changed':
                changed += 1
        else:
            state, delta = 'new', row['net_pay']

        preview.append({
            'worker': worker,
            'state': state,
            'delta': delta,
            'saved_net': float(record.net_pay) if record else None,
            'net_pay': row['net_pay'],
            'gross_pay': row['gross_pay'],
            'deductions': row['deductions'],
            'breakdown': row['pay_summary'].get('salary_breakdown'),
            'policy_rows': (salary.describe(row['pay_summary']['salary_breakdown']['policy'])
                            if row['pay_summary'].get('salary_breakdown') else None),
        })

    return render_template(
        'payroll_preview.html',
        preview=preview,
        totals=totals,
        month=month,
        year=year,
        month_name=MONTH_NAMES[month - 1],
        changed_count=changed,
        frozen_count=frozen,
        new_count=sum(1 for p in preview if p['state'] == 'new'),
    )


def _salary_csv_columns(worker, breakdown):
    """The salary-calculation columns for one CSV row.

    Returns blanks rather than zeros when the worker is not on a fixed
    monthly salary: a zero daily rate reads as a real figure, a blank cell
    reads as "does not apply".
    """
    if not breakdown:
        return [''] * 18
    b = breakdown
    return [
        worker.join_date.isoformat() if worker.join_date else '',
        f"{b['monthly_salary']:.2f}",
        salary.LABELS['salary_basis'].get(b['salary_basis'], b['salary_basis']),
        b['basis_days'],
        f"{b['daily_rate_exact']:.4f}",
        f"{b['daily_rate']:.2f}",
        b['total_calendar_days'],
        b['eligible_days'],
        b['present_days'] + b['late_days'],
        b['absent_days'],
        f"{b['leave_allowance']:g}",
        f"{b['paid_leave_used']:g}",
        f"{b['unpaid_leave_days']:g}",
        f"{b['deduction_days']:g}",
        f"{b['deduction_rate']:.2f}",
        f"{b['deduction_amount']:.2f}",
        f"{b['gross_eligible_salary']:.2f}",
        f"{b['net_payable']:.2f}",
    ]


def _salary_policy_csv_columns(policy):
    """The salary-policy columns for one export row.

    Blank for anyone not on a fixed monthly salary — the rules below simply
    do not apply to a daily or hourly worker.
    """
    if not policy:
        return [''] * 10
    return [
        salary.LABELS['salary_basis'].get(policy['salary_basis'], policy['salary_basis']),
        policy['basis_days'],
        salary.LABELS['rounding'].get(policy['rounding'], policy['rounding']),
        salary.LABELS['joining_mode'].get(policy['joining_mode'], policy['joining_mode']),
        'Yes' if policy['paid_leave_enabled'] else 'No',
        f"{policy['monthly_leave_allowance']:g}",
        'Yes' if policy['leave_carry_forward'] else 'No',
        'Yes' if policy['absence_deduction_enabled'] else 'No',
        ('' if policy['deduction_rate'] is None
         else f"{policy['deduction_rate']:.2f}"),
        salary.LABELS['calculation_method'].get(policy['calculation_method'],
                                                policy['calculation_method']),
    ]


class CalendarDay:
    """A day's dominant attendance status, for the month grid.

    The calendar partial reads only `.status`, so this stands in for a full
    AttendanceRecord and lets the month colours be derived from a grouped
    query rather than from every record in the month.
    """
    __slots__ = ('status',)

    def __init__(self, status):
        self.status = status


# ============================================================
# Interface language
# ============================================================

def _current_lang():
    """The chosen language, or English if nothing valid is in the session."""
    lang = session.get('lang', i18n.DEFAULT_LANGUAGE)
    return lang if lang in i18n.LANGUAGES else i18n.DEFAULT_LANGUAGE


@app.context_processor
def _inject_language():
    """Make _() and the language list available to every template.

    Beware: `{% set _ = list.append(x) %}` in a template shadows _() with
    None for the rest of that block. tests/test_i18n.py fails if any template
    does it — use a differently named throwaway.
    """
    lang = _current_lang()
    return {
        '_': lambda text: i18n.translate(text, lang),
        'current_lang': lang,
        'languages': i18n.LANGUAGES,
        'weekdays_short': i18n.weekday_names(lang, short=True),
    }


@app.template_filter('ldate')
def _ldate(value, fmt='%d %b %Y'):
    """strftime with the day and month names in the interface language."""
    return i18n.format_date(value, fmt, _current_lang())


# One way to write a rupee, everywhere. See money.py for why there were four.
app.add_template_filter(money.money, 'money')
app.add_template_filter(money.money0, 'money0')
app.add_template_filter(money.money2, 'money2')


@app.template_filter('lnote')
def _lnote(value):
    """One salary note, translated on its way to the screen.

    The English prose stays in the payroll snapshot as the audit record; only
    the displayed copy is translated, so a payslip saved months ago reads in
    whichever language the person viewing it chose.
    """
    return i18n.translate_note(value, _current_lang())


@app.template_filter('lnotes')
def _lnotes(value):
    """A run of salary notes joined into one paragraph, translated."""
    return i18n.translate_notes(value, _current_lang())


@app.template_filter('lpolicy')
def _lpolicy(value):
    """One value out of salary.describe(), translated for display."""
    return i18n.translate_policy(value, _current_lang())


@app.after_request
def _translate_json_messages(response):
    """Translate the notices a screen paints from JSON.

    The attendance day view and the scanner build their own markup in
    JavaScript, so a message in a JSON body lands on the screen verbatim and
    never passes through a template filter. Doing it here rather than at each
    jsonify() site keeps the English in routes.py as the one canonical
    wording, and covers any message added later.

    Messages a screen raises *itself*, without asking the server — 'No
    connection — the payment was not recorded.' — cannot come through here;
    the template hands those to the script already translated. See
    docs/language.md.
    """
    if _current_lang() == i18n.DEFAULT_LANGUAGE:
        return response
    if not response.is_json or response.direct_passthrough:
        return response
    try:
        payload = response.get_json(silent=True)
    except Exception:
        return response
    if not isinstance(payload, dict):
        return response

    changed = False
    for item in payload.get('messages') or []:
        if isinstance(item, dict) and item.get('text'):
            translated = _lflash(item['text'])
            if translated != item['text']:
                item['text'] = translated
                changed = True
    # The worker lookup answers with one message rather than a list, and the
    # scanner prints it as the status line under the camera.
    if isinstance(payload.get('message'), str) and payload['message']:
        translated = _lflash(payload['message'])
        if translated != payload['message']:
            payload['message'] = translated
            changed = True
    day = payload.get('day')
    if isinstance(day, dict) and day.get('payroll_note'):
        translated = _lflash(day['payroll_note'])
        if translated != day['payroll_note']:
            day['payroll_note'] = translated
            changed = True
    if changed:
        response.set_data(json.dumps(payload))
    return response


@app.template_filter('lflash')
def _lflash(value):
    """One flash message, translated where it is shown.

    Translating at the point of display rather than the point of flash()
    means none of the 105 call sites in this file had to change, and a
    message already sitting in the session still arrives in the reader's
    language.
    """
    return i18n.translate_flash(value, _current_lang())


@app.template_filter('lmonth')
def _lmonth(value):
    """'October 2026' -> the month name in the interface language.

    The six-month history labels are composed server-side from MONTH_NAMES,
    so they arrive here already joined to the year.
    """
    if not value:
        return value
    parts = str(value).split(' ', 1)
    return ' '.join([i18n.translate(parts[0], _current_lang())] + parts[1:])


@app.route('/language/<lang>', methods=['POST'])
def set_language(lang):
    """Switch the interface language and come back where we were.

    Stored in the session rather than on the user, so a shared site phone
    can be set to Hindi without changing it for the office. Deliberately not
    login-required: someone who only reads Hindi has to be able to switch
    before they can read the login screen. It writes one whitelisted value
    into the session and reads nothing, so there is nothing here to protect.
    """
    if lang in i18n.LANGUAGES:
        session['lang'] = lang
        session.permanent = True
    return redirect(safe_redirect_target(request.form.get('redirect_to'),
                                         url_for('profile')))
