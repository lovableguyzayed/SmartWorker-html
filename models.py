from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='admin')  # admin, manager
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Worker(db.Model):
    __tablename__ = 'workers'
    
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    position = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    employee_type = db.Column(db.String(30), nullable=False)  # Daily Wage, Full Time, etc.
    join_date = db.Column(db.Date, nullable=False)
    
    # Payment settings
    pay_type = db.Column(db.String(20), nullable=False)  # daily, monthly, hourly, project
    daily_rate = db.Column(db.Float, nullable=True)
    monthly_salary = db.Column(db.Float, nullable=True)
    hourly_rate = db.Column(db.Float, nullable=True)
    project_rate = db.Column(db.Float, nullable=True)
    
    # Working hours (for daily workers)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    break_duration = db.Column(db.Integer, default=60)  # minutes
    
    # Overtime settings
    overtime_enabled = db.Column(db.Boolean, default=True)
    overtime_rate = db.Column(db.Float, nullable=True)
    overtime_type = db.Column(db.String(10), default='hour')  # hour, minute

    # Late policy settings
    late_policy_enabled = db.Column(db.Boolean, default=False)
    late_deduction_per_day = db.Column(db.Float, nullable=True)
    late_deduction_type = db.Column(db.String(10), default='day')  # day, hour, minute

    # Daily wage absence policy
    no_work_no_pay = db.Column(db.Boolean, default=True)
    half_day_rate = db.Column(db.Float, nullable=True)
    half_day_grace_minutes = db.Column(db.Integer, default=20)
    
    # Leave policy (for salaried employees)
    allowed_leaves_per_month = db.Column(db.Integer, default=2)
    leave_deduction_per_day = db.Column(db.Float, nullable=True)
    leave_policy_enabled = db.Column(db.Boolean, default=True)
    
    # Status and metadata
    status = db.Column(db.String(20), default='active')  # active, inactive
    profile_image = db.Column(db.String(200), nullable=True)
    qr_code = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    attendance_records = db.relationship('AttendanceRecord', backref='worker', lazy=True)

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=True)
    check_out_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False)  # present, absent, late, leave
    overtime_minutes = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ClosureDay(db.Model):
    __tablename__ = 'closure_days'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    reason = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # holiday, maintenance, etc.
    allow_attendance = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PayrollRecord(db.Model):
    __tablename__ = 'payroll_records'
    
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_days = db.Column(db.Integer, nullable=False)
    present_days = db.Column(db.Integer, nullable=False)
    overtime_hours = db.Column(db.Float, default=0)
    gross_pay = db.Column(db.Float, nullable=False)
    deductions = db.Column(db.Float, default=0)
    net_pay = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, paid
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    worker = db.relationship('Worker', backref='payroll_records')
