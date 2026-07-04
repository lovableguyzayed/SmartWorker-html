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
    role = db.Column(db.String(20), default='admin')  # admin, manager, attendance
    # Attendance-user scoping (comma-separated ids). Empty = all sites/projects.
    assigned_site_ids = db.Column(db.Text, nullable=True)
    assigned_project_ids = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, disabled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return (self.role or 'admin') in ('admin', 'manager')

    @property
    def site_id_list(self):
        raw = (self.assigned_site_ids or '').strip()
        if not raw:
            return []
        return [int(x) for x in raw.split(',') if x.strip().isdigit()]

    @property
    def project_id_list(self):
        raw = (self.assigned_project_ids or '').strip()
        if not raw:
            return []
        return [int(x) for x in raw.split(',') if x.strip().isdigit()]

class CompanySetting(db.Model):
    """Singleton row holding company identity shown on PDFs and reports."""
    __tablename__ = 'company_settings'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), default='SmartWorker')
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(150), nullable=True)
    gst_number = db.Column(db.String(50), nullable=True)
    registration_number = db.Column(db.String(50), nullable=True)
    logo = db.Column(db.Text, nullable=True)  # static path or data URI
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Site(db.Model):
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text, nullable=True)
    contact_person = db.Column(db.String(100), nullable=True)
    contact_phone = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    deadline = db.Column(db.Date, nullable=True)
    completion_date = db.Column(db.Date, nullable=True)
    # Delay penalty configuration (applies to project-based workers)
    penalty_type = db.Column(db.String(10), default='none')  # none, fixed, percent
    penalty_value = db.Column(db.Float, default=0.0)  # per delayed day: amount or % of project rate
    status = db.Column(db.String(20), default='active')  # active, completed, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    site = db.relationship('Site', backref='projects')

    @property
    def delay_days(self):
        if not self.deadline:
            return 0
        from datetime import date as _date
        reference = self.completion_date or _date.today()
        return max((reference - self.deadline).days, 0)

class WorkTask(db.Model):
    __tablename__ = 'work_tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, completed, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref='tasks')

class ProjectAssignment(db.Model):
    __tablename__ = 'project_assignments'

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('work_tasks.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, completed, transferred
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref='assignments')
    site = db.relationship('Site', backref='assignments')
    task = db.relationship('WorkTask', backref='assignments')

    def worked_days(self, attendance_query=None):
        from datetime import date as _date
        end = self.end_date or _date.today()
        return max((end - self.start_date).days + 1, 0)

class WorkerModification(db.Model):
    """Permanent audit log of every employment change (promotion, salary, category, etc.)."""
    __tablename__ = 'worker_modifications'

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    mod_type = db.Column(db.String(30), nullable=False)
    # promotion, salary_change, category_change, bonus, incentive, leave_grant, profile_edit, other
    field_name = db.Column(db.String(60), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    effective_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LeaveAdjustment(db.Model):
    """Manual HR/Admin credit or debit of a worker's accumulated leave balance."""
    __tablename__ = 'leave_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    days = db.Column(db.Float, nullable=False)  # positive = credit, negative = debit
    reason = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

TRANSACTION_EARNING_TYPES = ('bonus', 'extra_payment', 'incentive', 'refreshment')
TRANSACTION_DEDUCTION_TYPES = ('advance', 'loan', 'cash_advance', 'recovery', 'deduction')

class WorkerTransaction(db.Model):
    __tablename__ = 'worker_transactions'

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    txn_type = db.Column(db.String(30), nullable=False)
    # advance, loan, cash_advance, recovery, deduction, bonus, extra_payment, incentive, refreshment
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, cancelled
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    worker = db.relationship('Worker', backref='transactions')

    @property
    def is_earning(self):
        return self.txn_type in TRANSACTION_EARNING_TYPES

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(30), default='attendance')  # attendance, system, sync
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    late_grace_minutes = db.Column(db.Integer, default=10)

    # Daily wage absence policy
    no_work_no_pay = db.Column(db.Boolean, default=True)
    half_day_rate = db.Column(db.Float, nullable=True)
    half_day_grace_minutes = db.Column(db.Integer, default=20)

    # Monthly worker rate derivation helpers
    monthly_working_days = db.Column(db.Integer, default=26)
    standard_working_hours = db.Column(db.Integer, default=8)

    # Closure day payment settings
    closure_extra_pay_enabled = db.Column(db.Boolean, default=False)
    closure_calculation_method = db.Column(db.String(20), default='daily_percent')
    closure_extra_percentage = db.Column(db.Float, default=0.0)

    # Leave policy (for salaried employees)
    allowed_leaves_per_month = db.Column(db.Integer, default=2)
    leave_deduction_per_day = db.Column(db.Float, nullable=True)
    leave_policy_enabled = db.Column(db.Boolean, default=True)

    # Status and metadata
    status = db.Column(db.String(20), default='active')  # active, inactive
    profile_image = db.Column(db.Text, nullable=True)
    qr_code = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    attendance_records = db.relationship('AttendanceRecord', backref='worker', lazy=True)
    assignments = db.relationship('ProjectAssignment', backref='worker', lazy=True,
                                  order_by='ProjectAssignment.start_date.desc()')
    modifications = db.relationship('WorkerModification', backref='worker', lazy=True,
                                    order_by='WorkerModification.created_at.desc()')
    leave_adjustments = db.relationship('LeaveAdjustment', backref='worker', lazy=True,
                                        order_by='LeaveAdjustment.created_at.desc()')

    @property
    def current_assignment(self):
        for assignment in self.assignments:
            if assignment.status == 'active':
                return assignment
        return None

    @property
    def current_site(self):
        assignment = self.current_assignment
        return assignment.site if assignment else None

    @property
    def current_project(self):
        assignment = self.current_assignment
        return assignment.project if assignment else None

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=True)
    check_out_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False)  # present, absent, late, leave
    overtime_minutes = db.Column(db.Integer, default=0)
    late_minutes = db.Column(db.Integer, default=0)
    leave_type = db.Column(db.String(30), nullable=True)  # casual, sick, paid, unpaid, other
    shift = db.Column(db.String(30), nullable=True)
    site_id = db.Column(db.Integer, nullable=True)
    marked_by = db.Column(db.Integer, nullable=True)  # user id who marked it
    marked_via = db.Column(db.String(15), default='manual')  # manual, qr, worker_id, bulk
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def worked_minutes(self):
        if not self.check_in_time or not self.check_out_time:
            return 0
        if self.check_out_time <= self.check_in_time:
            return 0
        return int((self.check_out_time - self.check_in_time).total_seconds() // 60)

class ClosureDay(db.Model):
    __tablename__ = 'closure_days'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # holiday, site, project, emergency, maintenance
    scope = db.Column(db.String(20), default='company')  # company, site, project
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    allow_attendance = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    site = db.relationship('Site', backref='closures')
    project = db.relationship('Project', backref='closures')

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
