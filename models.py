from datetime import datetime
from timeutil import now_ist, today_ist
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Account(db.Model):
    """A tenant workspace. Every piece of business data belongs to exactly one
    Account. The user who registers owns the account; any staff they invite are
    Users that belong to the same account and share its data. Data is isolated
    between accounts (see tenancy.py)."""
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default='My Workspace')
    # Supabase auth uid (UUID) of the account owner who created it.
    owner_uid = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(20), default='active')  # active, suspended
    created_at = db.Column(db.DateTime, default=now_ist)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    # Supabase Auth is the identity provider. Passwords live in Supabase, so the
    # local hash is now optional (kept for any legacy/local-only accounts).
    password_hash = db.Column(db.String(256), nullable=True)
    # Links this app user to its Supabase Auth user (UUID). Unique when set.
    supabase_uid = db.Column(db.String(64), unique=True, nullable=True, index=True)
    # Workspace this user belongs to. Null only for legacy rows pre-migration.
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='attendance')  # admin, manager, attendance
    # Attendance-user scoping (comma-separated ids). Empty = all sites/projects.
    assigned_site_ids = db.Column(db.Text, nullable=True)
    assigned_project_ids = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, disabled
    profile_image = db.Column(db.Text, nullable=True)  # public URL or static path
    created_at = db.Column(db.DateTime, default=now_ist)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role in ('admin', 'manager')

    @property
    def site_id_list(self):
        raw = (self.assigned_site_ids or '').strip()
        if not raw:
            return []
        ids = []
        for token in raw.split(','):
            token = token.strip()
            if token.isdigit():
                ids.append(int(token))
        return ids

    @property
    def project_id_list(self):
        raw = (self.assigned_project_ids or '').strip()
        if not raw:
            return []
        ids = []
        for token in raw.split(','):
            token = token.strip()
            if token.isdigit():
                ids.append(int(token))
        return ids

class CompanySetting(db.Model):
    """Singleton row holding company identity shown on PDFs and reports."""
    __tablename__ = 'company_settings'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    name = db.Column(db.String(150), default='SmartWorker')
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(150), nullable=True)
    gst_number = db.Column(db.String(50), nullable=True)
    registration_number = db.Column(db.String(50), nullable=True)
    logo = db.Column(db.Text, nullable=True)  # static path or data URI
    updated_at = db.Column(db.DateTime, default=now_ist, onupdate=now_ist)

class Site(db.Model):
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text, nullable=True)
    contact_person = db.Column(db.String(100), nullable=True)
    contact_phone = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, archived
    created_at = db.Column(db.DateTime, default=now_ist)

class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, archived
    created_at = db.Column(db.DateTime, default=now_ist)

class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
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
    created_at = db.Column(db.DateTime, default=now_ist)

    site = db.relationship('Site', backref='projects')

    @property
    def delay_days(self):
        if not self.deadline:
            return 0
        reference = self.completion_date or today_ist()
        return max((reference - self.deadline).days, 0)

class WorkTask(db.Model):
    __tablename__ = 'work_tasks'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    name = db.Column(db.String(150), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, completed, archived
    created_at = db.Column(db.DateTime, default=now_ist)

    project = db.relationship('Project', backref='tasks')

class ProjectAssignment(db.Model):
    __tablename__ = 'project_assignments'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('work_tasks.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, completed, transferred
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=now_ist)

    project = db.relationship('Project', backref='assignments')
    site = db.relationship('Site', backref='assignments')
    task = db.relationship('WorkTask', backref='assignments')

    def worked_days(self, attendance_query=None):
        end = self.end_date or today_ist()
        return max((end - self.start_date).days + 1, 0)

class WorkerModification(db.Model):
    """Permanent audit log of every employment change (promotion, salary, category, etc.)."""
    __tablename__ = 'worker_modifications'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    mod_type = db.Column(db.String(30), nullable=False)
    # promotion, salary_change, category_change, bonus, incentive, leave_grant, profile_edit, other
    field_name = db.Column(db.String(60), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    effective_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=now_ist)

class LeaveAdjustment(db.Model):
    """Manual HR/Admin credit or debit of a worker's accumulated leave balance."""
    __tablename__ = 'leave_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    days = db.Column(db.Float, nullable=False)  # positive = credit, negative = debit
    reason = db.Column(db.Text, nullable=True)
    effective_date = db.Column(db.Date, nullable=True)  # when the adjustment applies; None = from creation date
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=now_ist)

TRANSACTION_EARNING_TYPES = ('bonus', 'extra_payment', 'incentive', 'refreshment')
TRANSACTION_DEDUCTION_TYPES = ('advance', 'loan', 'cash_advance', 'recovery', 'deduction')

class WorkerTransaction(db.Model):
    __tablename__ = 'worker_transactions'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    txn_type = db.Column(db.String(30), nullable=False)
    # advance, loan, cash_advance, recovery, deduction, bonus, extra_payment, incentive, refreshment
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, cancelled
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=now_ist)
    updated_at = db.Column(db.DateTime, default=now_ist, onupdate=now_ist)

    worker = db.relationship('Worker', backref='transactions')

    @property
    def is_earning(self):
        return self.txn_type in TRANSACTION_EARNING_TYPES

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(30), default='attendance')  # attendance, system, sync
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_ist)

class Worker(db.Model):
    __tablename__ = 'workers'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
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
    created_at = db.Column(db.DateTime, default=now_ist)
    updated_at = db.Column(db.DateTime, default=now_ist, onupdate=now_ist)

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
    __table_args__ = (
        db.UniqueConstraint('worker_id', 'date', name='uq_attendance_worker_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
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
    created_at = db.Column(db.DateTime, default=now_ist)

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
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # holiday, site, project, emergency, maintenance
    scope = db.Column(db.String(20), default='company')  # company, site, project
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    allow_attendance = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=now_ist)

    site = db.relationship('Site', backref='closures')
    project = db.relationship('Project', backref='closures')

class PayrollRecord(db.Model):
    __tablename__ = 'payroll_records'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
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
    created_at = db.Column(db.DateTime, default=now_ist)

    worker = db.relationship('Worker', backref='payroll_records')
