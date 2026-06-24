import os
import qrcode
import io
import base64
import csv
import random
import calendar as _cal
from datetime import datetime, date, timedelta
from flask import render_template, request, redirect, url_for, flash, session, jsonify, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from app import app, db, csrf
from models import User, Worker, AttendanceRecord, ClosureDay, PayrollRecord

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

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

def save_worker_profile_image(file_storage, worker_id):
    filename = secure_filename(file_storage.filename or '')
    if not allowed_image_file(filename):
        raise ValueError('Please upload a valid image (JPG, JPEG, PNG, GIF, or WEBP).')
    
    os.makedirs(WORKER_IMAGE_UPLOAD_DIR, exist_ok=True)
    extension = filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{worker_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.{extension}"
    destination = os.path.join(WORKER_IMAGE_UPLOAD_DIR, unique_filename)
    file_storage.save(destination)
    
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
    if (
        worker.pay_type != 'daily'
        or
        not worker.overtime_enabled
        or not attendance_record
    ):
        return 0

    worked_minutes = calculate_worked_minutes_for_record(attendance_record)
    if worked_minutes <= 0:
        return 0
    scheduled_minutes = calculate_scheduled_minutes_for_day(worker, attendance_record.date)
    return max(worked_minutes - scheduled_minutes, 0)

def calculate_late_minutes_for_record(worker, attendance_record):
    if (
        worker.pay_type != 'daily'
        or
        not attendance_record
        or attendance_record.status != 'late'
        or not attendance_record.check_in_time
        or not worker.start_time
    ):
        return 0

    shift_start = datetime.combine(attendance_record.date, worker.start_time)
    late_minutes = int((attendance_record.check_in_time - shift_start).total_seconds() // 60)
    return max(late_minutes, 0)

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

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        user = User.query.filter(
            db.or_(
                User.username == username,
                User.email == username
            )
        ).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            clear_login_otp_session()
            next_page = request.args.get('next')
            print(f"Login successful for user: {username}")
            return redirect(next_page, code=303) if next_page else redirect(url_for('dashboard'), code=303)
        else:
            flash('Invalid username or password', 'error')
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
    expires_at = datetime.utcnow() + timedelta(minutes=5)

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

    if datetime.utcnow().timestamp() > float(expires_at):
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
        'redirect_url': url_for('dashboard'),
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
    expires_at = datetime.utcnow() + timedelta(minutes=5)

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

    if datetime.utcnow().timestamp() > float(expires_at):
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
        full_name = request.form['full_name']
        mobile = normalize_mobile_number(request.form.get('mobile'))

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')

        if not is_valid_mobile_number(mobile):
            flash('Please enter a valid mobile number', 'error')
            return render_template('register.html')

        otp_verified = session.get('register_otp_verified')
        otp_mobile = session.get('register_otp_mobile')
        otp_expiry = session.get('register_otp_expires_at')
        if (
            not otp_verified
            or otp_mobile != mobile
            or not otp_expiry
            or datetime.utcnow().timestamp() > float(otp_expiry)
        ):
            flash('Please verify your mobile number with OTP before registering', 'error')
            return render_template('register.html')
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('register.html')

        if User.query.filter_by(phone=mobile).first():
            flash('Mobile number already registered', 'error')
            return render_template('register.html')
        
        # Create new user
        user = User()
        user.username = generate_unique_username(full_name, email)
        user.email = email
        user.phone = mobile
        user.full_name = full_name
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        clear_register_otp_session()
        
        flash('Registration successful! Please login using your email or username.', 'success')
        return redirect(url_for('login'))
    
    clear_register_otp_session()
    return render_template('register.html')

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
    today = date.today()
    
    # Get statistics
    total_workers = Worker.query.filter_by(status='active').count()
    present_today = AttendanceRecord.query.filter_by(
        date=today,
        status='present'
    ).count()
    
    # Get recent attendance records
    recent_attendance = db.session.query(AttendanceRecord, Worker).join(
        Worker, AttendanceRecord.worker_id == Worker.id
    ).filter(AttendanceRecord.date == today).limit(10).all()
    
    # Get upcoming closure days
    upcoming_closures = ClosureDay.query.filter(
        ClosureDay.date >= today
    ).order_by(ClosureDay.date).limit(5).all()
    
    return render_template('dashboard.html',
                         total_workers=total_workers,
                         present_today=present_today,
                         attendance_percentage=round((present_today/total_workers*100) if total_workers > 0 else 0, 1),
                         recent_attendance=recent_attendance,
                         upcoming_closures=upcoming_closures)

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
    
    workers_list = query.order_by(Worker.full_name).all()
    departments = db.session.query(Worker.department).distinct().all()
    
    return render_template('workers.html',
                         workers=workers_list,
                         departments=[d[0] for d in departments],
                         search=search,
                         selected_department=department)

@app.route('/worker/<int:worker_id>')
@login_required
def worker_profile(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    
    # Get recent attendance
    recent_attendance = AttendanceRecord.query.filter_by(
        worker_id=worker_id
    ).order_by(AttendanceRecord.date.desc()).limit(30).all()
    
    # Calculate statistics
    this_month = date.today().replace(day=1)
    month_attendance = AttendanceRecord.query.filter(
        AttendanceRecord.worker_id == worker_id,
        AttendanceRecord.date >= this_month,
        AttendanceRecord.status == 'present'
    ).count()
    
    return render_template('worker_profile.html',
                         worker=worker,
                         recent_attendance=recent_attendance,
                         month_attendance=month_attendance)

def generate_worker_id(department):
    """Generate unique worker ID based on department"""
    dept_prefix = department[:2].upper()
    
    # Get the highest existing ID for this department
    existing = Worker.query.filter(
        Worker.worker_id.like(f'{dept_prefix}%')
    ).order_by(Worker.worker_id.desc()).first()
    
    if existing:
        try:
            last_num = int(existing.worker_id[2:])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    
    return f"{dept_prefix}{new_num:03d}"

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

def calculate_pay_summary(worker, attendance_records):
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
    elif worker.pay_type == 'monthly':
        base_pay = float(worker.monthly_salary or 0)
        if worker.leave_policy_enabled and worker.leave_deduction_per_day is not None:
            extra_leave_days = max(0, leave_days - int(worker.allowed_leaves_per_month or 0))
            leave_deductions = extra_leave_days * float(worker.leave_deduction_per_day or 0)
            policy_notes.append('Monthly salary applies leave deduction after allowed leaves.')
        else:
            policy_notes.append('Monthly salary with leave policy disabled.')
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
    if getattr(worker, 'closure_extra_pay_enabled', False) and attendance_records:
        record_dates = [r.date for r in attendance_records]
        month_start = min(record_dates).replace(day=1)
        _, _days = _cal.monthrange(month_start.year, month_start.month)
        month_end = month_start.replace(day=_days)
        closure_day_dates = {
            c.date for c in ClosureDay.query.filter(
                ClosureDay.date >= month_start,
                ClosureDay.date <= month_end,
                ClosureDay.allow_attendance == True,
            ).all()
        }
        if closure_day_dates:
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

            _hourly_base = _daily_base / swh
            _minute_base = _hourly_base / 60.0

            for record in attendance_records:
                if record.date not in closure_day_dates:
                    continue
                if record.status not in ('present', 'late'):
                    continue
                if method == 'daily_percent':
                    if worker.pay_type == 'daily':
                        day_pay, _ = calculate_daily_wage_for_record(worker, record)
                    else:
                        day_pay = _daily_base
                    closure_extra_pay += day_pay * pct
                else:
                    if record.check_in_time and record.check_out_time and record.check_out_time > record.check_in_time:
                        rec_mins = int((record.check_out_time - record.check_in_time).total_seconds() // 60)
                    else:
                        rec_mins = swh * 60
                    if method == 'hourly_percent':
                        closure_extra_pay += (rec_mins / 60.0) * _hourly_base * pct
                    else:
                        closure_extra_pay += rec_mins * _minute_base * pct

            if closure_extra_pay > 0:
                policy_notes.append(
                    f'Closure day extra pay ({getattr(worker, "closure_extra_percentage", 0)}% via {method.replace("_", " ")}) applied.'
                )

    base_pay += closure_extra_pay

    estimated_pay = base_pay + overtime_pay - deductions
    policy_note = ' '.join(policy_notes)
    
    return {
        'pay_type': worker.pay_type,
        'base_pay': round(base_pay, 2),
        'overtime_pay': round(overtime_pay, 2),
        'leave_deductions': round(leave_deductions, 2),
        'late_deductions': round(late_deductions, 2),
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
    }

@app.route('/add_worker', methods=['GET', 'POST'])
@login_required
def add_worker():
    if request.method == 'POST':
        # Generate worker ID
        worker_id = generate_worker_id(request.form['department'])
        
        # Create new worker
        worker = Worker()
        worker.worker_id = worker_id
        worker.full_name = request.form['full_name']
        worker.phone = request.form['phone']
        worker.email = request.form.get('email')
        worker.address = request.form.get('address')
        worker.position = request.form['position']
        worker.department = request.form['department']
        worker.employee_type = request.form['employee_type']
        worker.join_date = datetime.strptime(request.form['join_date'], '%Y-%m-%d').date()
        worker.pay_type = request.form['pay_type']
        
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
            worker.daily_rate = parse_float(request.form.get('daily_rate'))
            if request.form.get('start_time'):
                worker.start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
            if request.form.get('end_time'):
                worker.end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()

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
            worker.monthly_salary = parse_float(request.form.get('monthly_salary'))
            worker.monthly_working_days = parse_int(request.form.get('monthly_working_days'), 26)
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
            worker.allowed_leaves_per_month = parse_int(request.form.get('allowed_leaves'), 2)
            if request.form.get('leave_deduction'):
                worker.leave_deduction_per_day = parse_float(request.form.get('leave_deduction'))
            worker.leave_policy_enabled = 'leave_policy_enabled' in request.form
        elif worker.pay_type == 'hourly':
            worker.hourly_rate = parse_float(request.form.get('hourly_rate'))
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
        elif worker.pay_type == 'project':
            worker.project_rate = parse_float(request.form.get('project_rate'))

        # Closure day extra pay settings (apply for all pay types)
        worker.closure_extra_pay_enabled = 'closure_extra_pay_enabled' in request.form
        raw_method = request.form.get('closure_calculation_method', 'daily_percent')
        worker.closure_calculation_method = raw_method if raw_method in ('daily_percent', 'hourly_percent', 'minute_percent') else 'daily_percent'
        worker.closure_extra_percentage = max(0.0, parse_float(request.form.get('closure_extra_percentage', '0')) or 0.0)

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
        db.session.commit()
        
        flash(f'Worker {worker.full_name} added successfully with ID: {worker_id}', 'success')
        return redirect(url_for('workers'))
    
    return render_template('edit_worker.html', worker=None)

@app.route('/edit_worker/<int:worker_id>', methods=['GET', 'POST'])
@login_required
def edit_worker(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    
    if request.method == 'POST':
        # Update worker details
        worker.full_name = request.form['full_name']
        worker.phone = request.form['phone']
        worker.email = request.form.get('email')
        worker.address = request.form.get('address')
        worker.position = request.form['position']
        worker.department = request.form['department']
        worker.employee_type = request.form['employee_type']
        worker.join_date = datetime.strptime(request.form['join_date'], '%Y-%m-%d').date()
        worker.pay_type = request.form['pay_type']
        
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
            worker.daily_rate = parse_float(request.form.get('daily_rate'))
            if request.form.get('start_time'):
                worker.start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
            if request.form.get('end_time'):
                worker.end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()

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
            worker.monthly_salary = parse_float(request.form.get('monthly_salary'))
            worker.monthly_working_days = parse_int(request.form.get('monthly_working_days'), 26)
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
            worker.allowed_leaves_per_month = parse_int(request.form.get('allowed_leaves'), 2)
            if request.form.get('leave_deduction'):
                worker.leave_deduction_per_day = parse_float(request.form.get('leave_deduction'))
            worker.leave_policy_enabled = 'leave_policy_enabled' in request.form
        elif worker.pay_type == 'hourly':
            worker.hourly_rate = parse_float(request.form.get('hourly_rate'))
            worker.standard_working_hours = parse_int(request.form.get('standard_working_hours'), 8)
        elif worker.pay_type == 'project':
            worker.project_rate = parse_float(request.form.get('project_rate'))

        # Closure day extra pay settings (apply for all pay types)
        worker.closure_extra_pay_enabled = 'closure_extra_pay_enabled' in request.form
        raw_method = request.form.get('closure_calculation_method', 'daily_percent')
        worker.closure_calculation_method = raw_method if raw_method in ('daily_percent', 'hourly_percent', 'minute_percent') else 'daily_percent'
        worker.closure_extra_percentage = max(0.0, parse_float(request.form.get('closure_extra_percentage', '0')) or 0.0)

        # Optional profile photo upload (replaces existing photo)
        profile_image = request.files.get('profile_image')
        if profile_image and profile_image.filename:
            try:
                worker.profile_image = save_worker_profile_image(profile_image, worker.worker_id)
            except ValueError as exc:
                flash(str(exc), 'error')
                return redirect(url_for('edit_worker', worker_id=worker_id))
        
        worker.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Worker {worker.full_name} updated successfully', 'success')
        return redirect(url_for('worker_profile', worker_id=worker_id))
    
    return render_template('edit_worker.html', worker=worker)

@app.route('/attendance')
@login_required
def attendance():
    selected_date = request.args.get('date', date.today().isoformat())
    selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    
    # Get all workers and their attendance for the selected date
    workers = Worker.query.filter_by(status='active').all()
    attendance_data = []
    
    for worker in workers:
        attendance = AttendanceRecord.query.filter_by(
            worker_id=worker.id,
            date=selected_date
        ).first()
        
        # compute wages and overtime for display
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
            'wage': wage,
            'pay_mode': pay_mode,
            'overtime_pay': overtime_pay,
        })
    
    # Check if it's a closure day
    closure = ClosureDay.query.filter_by(date=selected_date).first()
    
    return render_template('attendance.html',
                         attendance_data=attendance_data,
                         selected_date=selected_date,
                         closure=closure,
                         timedelta=timedelta)

@app.route('/closures', methods=['GET', 'POST'])
@login_required
def closures():
    if request.method == 'POST':
        closure_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        reason = request.form['reason'].strip()
        closure_type = request.form.get('type', 'holiday').strip().lower()
        allow_attendance = 'allow_attendance' in request.form
        
        existing = ClosureDay.query.filter_by(date=closure_date).first()
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
            closure.allow_attendance = allow_attendance
            db.session.add(closure)
            flash('Closure day added successfully', 'success')
        
        db.session.commit()
        return redirect(url_for('closures'))
    
    upcoming_closures = ClosureDay.query.filter(
        ClosureDay.date >= date.today()
    ).order_by(ClosureDay.date).all()
    
    return render_template('closures.html', closures=upcoming_closures, date=date)

@app.route('/closures/<int:closure_id>/delete', methods=['POST'])
@login_required
def delete_closure(closure_id):
    closure = ClosureDay.query.get_or_404(closure_id)
    db.session.delete(closure)
    db.session.commit()
    flash('Closure day deleted successfully', 'success')
    return redirect(url_for('closures'))

@app.route('/worker_attendance/<int:worker_id>')
@login_required
def worker_attendance(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    
    # Get month and year from query params
    month = int(request.args.get('month', date.today().month))
    year = int(request.args.get('year', date.today().year))
    
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
    pay_summary = calculate_pay_summary(worker, attendance_records)
    
    return render_template('worker_attendance.html',
                         worker=worker,
                         calendar_data=calendar_data,
                         attendance_summary=attendance_summary,
                         pay_summary=pay_summary,
                         month=month,
                         year=year,
                         start_date=start_date,
                         end_date=end_date,
                         timedelta=timedelta,
                         date=date)

@app.route('/id_card/<int:worker_id>', methods=['GET', 'POST'])
@login_required
def id_card(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    
    if request.method == 'POST':
        if 'regenerate_qr' in request.form:
            # Generate new QR code
            worker.qr_code = generate_qr_code(worker.worker_id)
            worker.updated_at = datetime.utcnow()
            db.session.commit()
            flash('New QR code generated successfully', 'success')
            return redirect(url_for('id_card', worker_id=worker_id))
    
    # Generate QR code if not exists
    if not worker.qr_code:
        worker.qr_code = generate_qr_code(worker.worker_id)
        db.session.commit()
    
    return render_template('id_card.html', worker=worker, date=date, timedelta=timedelta)

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
            
            if not current_user.check_password(current_password):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            elif len(new_password) < 6:
                flash('Password must be at least 6 characters long', 'error')
            else:
                current_user.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully', 'success')
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', Worker=Worker, AttendanceRecord=AttendanceRecord, date=date)

@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    attendance_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    closure = ClosureDay.query.filter_by(date=attendance_date).first()
    
    if closure and not closure.allow_attendance:
        flash(
            f"Attendance is locked on this closure day ({closure.reason}).",
            'error'
        )
        return redirect(url_for('attendance', date=attendance_date.isoformat()))

    if 'bulk_action' in request.form:
        # Bulk attendance marking
        status = request.form['status']
        
        workers = Worker.query.filter_by(status='active').all()
        for worker in workers:
            existing = AttendanceRecord.query.filter_by(
                worker_id=worker.id,
                date=attendance_date
            ).first()
            
            if existing:
                existing.status = status
                if status in ('present', 'late'):
                    existing.check_in_time = datetime.now()
                    existing.overtime_minutes = 0
                    existing.check_out_time = None
                else:
                    existing.check_in_time = None
                    existing.check_out_time = None
                    existing.overtime_minutes = 0
            else:
                attendance = AttendanceRecord()
                attendance.worker_id = worker.id
                attendance.date = attendance_date
                attendance.status = status
                attendance.check_in_time = datetime.now() if status in ('present', 'late') else None
                attendance.check_out_time = None
                attendance.overtime_minutes = 0
                db.session.add(attendance)
        
        db.session.commit()
        flash(f'Bulk attendance marked as {status} for all workers', 'success')
    else:
        # Individual attendance marking
        worker_id = parse_int(request.form.get('worker_id'))
        status = request.form['status']
        feedback_message = None
        feedback_category = 'success'
        
        worker = Worker.query.get_or_404(worker_id)

        # Check if attendance already exists
        existing = AttendanceRecord.query.filter_by(
            worker_id=worker_id,
            date=attendance_date
        ).first()
        
        if existing:
            previous_status = existing.status
            existing.status = status

            if status in ('present', 'late'):
                now = datetime.now()
                if not existing.check_in_time:
                    # First tap acts as check-in.
                    existing.check_in_time = now
                    existing.check_out_time = None
                    existing.overtime_minutes = 0
                    feedback_message = 'Check-in captured successfully.'
                elif existing.check_out_time is None and previous_status == status:
                    # Second tap on same active status acts as check-out/close.
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
                    feedback_message = 'Attendance status updated successfully.'
            else:
                existing.check_in_time = None
                existing.check_out_time = None
                existing.overtime_minutes = 0
                feedback_message = 'Attendance marked successfully.'
        else:
            attendance = AttendanceRecord()
            attendance.worker_id = worker_id
            attendance.date = attendance_date
            attendance.status = status
            attendance.check_in_time = datetime.now() if status in ('present', 'late') else None
            attendance.check_out_time = None
            attendance.overtime_minutes = 0
            db.session.add(attendance)
            feedback_message = 'Check-in captured successfully.' if status in ('present', 'late') else 'Attendance marked successfully.'
        
        db.session.commit()
        if feedback_message:
            flash(feedback_message, feedback_category)
    
    return redirect(url_for('attendance', date=attendance_date.isoformat()))

def _build_payroll_rows(month, year):
    workers = Worker.query.filter_by(status='active').order_by(Worker.full_name).all()
    _, days_in_month = _cal.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    rows = []
    total_gross = 0.0
    total_deductions = 0.0
    total_net = 0.0
    paid_count = 0
    pending_count = 0

    for worker in workers:
        records = AttendanceRecord.query.filter(
            AttendanceRecord.worker_id == worker.id,
            AttendanceRecord.date >= start_date,
            AttendanceRecord.date <= end_date,
        ).all()

        att_summary = calculate_attendance_summary(records)
        pay_summary = calculate_pay_summary(worker, records)

        gross_pay = round(pay_summary['base_pay'] + pay_summary['overtime_pay'], 2)
        deductions = pay_summary['deductions']
        net_pay = pay_summary['estimated_pay']

        existing_record = PayrollRecord.query.filter_by(
            worker_id=worker.id, month=month, year=year
        ).first()

        if existing_record:
            record_status = existing_record.status
            record_id = existing_record.id
        else:
            record_status = 'unsaved'
            record_id = None

        total_gross += gross_pay
        total_deductions += deductions
        total_net += net_pay
        if record_status == 'paid':
            paid_count += 1
        else:
            pending_count += 1

        rows.append({
            'worker': worker,
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


MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


@app.route('/payroll')
@login_required
def payroll():
    today = date.today()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, totals, _ = _build_payroll_rows(month, year)
    years = list(range(2024, today.year + 2))
    months = [(i, MONTH_NAMES[i - 1]) for i in range(1, 13)]

    return render_template(
        'payroll.html',
        rows=rows,
        totals=totals,
        month=month,
        year=year,
        years=years,
        months=months,
        month_name=MONTH_NAMES[month - 1],
    )


@app.route('/payroll/save', methods=['POST'])
@login_required
def payroll_save():
    today = date.today()
    try:
        month = max(1, min(12, int(request.form.get('month', today.month))))
        year = max(2020, min(2099, int(request.form.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, _, _ = _build_payroll_rows(month, year)
    saved = 0

    for row in rows:
        worker = row['worker']
        pay = row['pay_summary']
        att = row['att_summary']

        existing = PayrollRecord.query.filter_by(
            worker_id=worker.id, month=month, year=year
        ).first()

        fields = dict(
            total_days=att['total_marked_days'],
            present_days=pay['paid_days'],
            overtime_hours=round(pay['overtime_minutes'] / 60.0, 2),
            gross_pay=row['gross_pay'],
            deductions=row['deductions'],
            net_pay=row['net_pay'],
        )

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            if existing.status != 'paid':
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
    flash(
        f'Payroll generated for {saved} worker(s) — {MONTH_NAMES[month - 1]} {year}.',
        'success',
    )
    return redirect(url_for('payroll', month=month, year=year))


@app.route('/payroll/<int:record_id>/toggle_paid', methods=['POST'])
@login_required
def payroll_toggle_paid(record_id):
    record = PayrollRecord.query.get_or_404(record_id)
    record.status = 'pending' if record.status == 'paid' else 'paid'
    db.session.commit()
    label = 'Paid' if record.status == 'paid' else 'Pending'
    flash(
        f'{record.worker.full_name} marked as {label} — '
        f'{MONTH_NAMES[record.month - 1]} {record.year}.',
        'success',
    )
    return redirect(url_for('payroll', month=record.month, year=record.year))


@app.route('/payroll/slip/<int:worker_id>')
@login_required
def payroll_slip(worker_id):
    worker = Worker.query.get_or_404(worker_id)
    today = date.today()
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
    pay_summary = calculate_pay_summary(worker, records)

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
        payroll_record=payroll_record,
        timedelta=timedelta,
        date=date,
    )


@app.route('/payroll/export.csv')
@login_required
def payroll_export():
    today = date.today()
    try:
        month = max(1, min(12, int(request.args.get('month', today.month))))
        year = max(2020, min(2099, int(request.args.get('year', today.year))))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    rows, totals, _ = _build_payroll_rows(month, year)
    month_name = MONTH_NAMES[month - 1]

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Worker ID', 'Full Name', 'Department', 'Position',
        'Pay Type', 'Month', 'Year',
        'Total Marked Days', 'Paid Days',
        'Gross Pay (INR)', 'Deductions (INR)', 'Net Payable (INR)',
        'Overtime Minutes', 'Status',
    ])

    for row in rows:
        w = row['worker']
        pay = row['pay_summary']
        att = row['att_summary']
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
            row['status'],
        ])

    writer.writerow([])
    writer.writerow([
        '', 'TOTALS', '', '', '', '', '',
        '', '',
        totals['total_gross'],
        totals['total_deductions'],
        totals['total_net'],
        '',
        f"{totals['paid_count']} paid / {totals['pending_count']} pending",
    ])

    filename = f"payroll_{month_name.lower()}_{year}.csv"
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


@app.route('/export_data')
@login_required
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
        'Status', 'Date', 'Attendance Status', 'Check In', 'Check Out'
    ])
    
    # Write worker and attendance data
    workers = Worker.query.all()
    for worker in workers:
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
                worker.status,
                attendance.date.strftime('%Y-%m-%d'),
                attendance.status,
                attendance.check_in_time.strftime('%H:%M') if attendance.check_in_time else '',
                attendance.check_out_time.strftime('%H:%M') if attendance.check_out_time else ''
            ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=smartworker_data_{date.today().isoformat()}.csv'
    
    return response
