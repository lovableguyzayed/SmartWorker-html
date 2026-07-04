import os
import secrets
import string
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
csrf = CSRFProtect()

# create the app
app = Flask(__name__)

# Session secret — required, no insecure fallback
_secret = os.environ.get("SESSION_SECRET")
if not _secret:
    logging.warning("SESSION_SECRET not set — generating a random key (sessions will reset on restart). Set SESSION_SECRET in environment variables for production.")
    _secret = secrets.token_hex(32)
app.secret_key = _secret

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smartworker.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit

# initialize the app with the extensions
db.init_app(app)
csrf.init_app(app)

# Columns added after the initial release. Applied with ALTER TABLE so existing
# databases upgrade in place without losing data.
SCHEMA_PATCHES = {
    'users': [
        ('phone', "VARCHAR(20)"),
        ('assigned_site_ids', "TEXT"),
        ('assigned_project_ids', "TEXT"),
        ('created_by', "INTEGER"),
        ('status', "VARCHAR(20) DEFAULT 'active'"),
    ],
    'closure_days': [
        ('allow_attendance', "BOOLEAN NOT NULL DEFAULT 1"),
        ('scope', "VARCHAR(20) DEFAULT 'company'"),
        ('site_id', "INTEGER"),
        ('project_id', "INTEGER"),
    ],
    'workers': [
        ('project_rate', "FLOAT"),
        ('late_policy_enabled', "BOOLEAN NOT NULL DEFAULT 0"),
        ('late_deduction_per_day', "FLOAT"),
        ('late_deduction_type', "VARCHAR(10) DEFAULT 'day'"),
        ('late_grace_minutes', "INTEGER DEFAULT 10"),
        ('no_work_no_pay', "BOOLEAN NOT NULL DEFAULT 1"),
        ('half_day_rate', "FLOAT"),
        ('half_day_grace_minutes', "INTEGER NOT NULL DEFAULT 20"),
        ('monthly_working_days', "INTEGER DEFAULT 26"),
        ('standard_working_hours', "INTEGER DEFAULT 8"),
        ('closure_extra_pay_enabled', "BOOLEAN NOT NULL DEFAULT 0"),
        ('closure_calculation_method', "VARCHAR(20) DEFAULT 'daily_percent'"),
        ('closure_extra_percentage', "FLOAT DEFAULT 0.0"),
    ],
    'attendance_records': [
        ('late_minutes', "INTEGER DEFAULT 0"),
        ('leave_type', "VARCHAR(30)"),
        ('shift', "VARCHAR(30)"),
        ('site_id', "INTEGER"),
        ('marked_by', "INTEGER"),
        ('marked_via', "VARCHAR(15) DEFAULT 'manual'"),
    ],
}

def _apply_schema_patches(inspector):
    for table, patches in SCHEMA_PATCHES.items():
        if table not in inspector.get_table_names():
            continue
        existing_columns = {col['name'] for col in inspector.get_columns(table)}
        for column, ddl in patches:
            if column in existing_columns:
                continue
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            db.session.commit()
            logging.info("Added %s column to %s", column, table)

def _drop_closure_date_unique_constraint(inspector):
    """Legacy SQLite databases created closure_days.date with UNIQUE, which
    blocks site/project-scoped closures sharing a date. Rebuild the table once."""
    if not db.engine.url.drivername.startswith('sqlite'):
        return
    if 'closure_days' not in inspector.get_table_names():
        return
    unique_indexes = [
        idx for idx in inspector.get_indexes('closure_days')
        if idx.get('unique') and idx.get('column_names') == ['date']
    ]
    has_auto_unique = any(
        'date' in (constraint.get('column_names') or [])
        for constraint in inspector.get_unique_constraints('closure_days')
    )
    if not unique_indexes and not has_auto_unique:
        return
    logging.info("Rebuilding closure_days to drop UNIQUE(date) constraint")
    db.session.execute(text("ALTER TABLE closure_days RENAME TO closure_days_old"))
    db.session.commit()
    db.metadata.tables['closure_days'].create(db.engine)
    old_columns = {col['name'] for col in inspector.get_columns('closure_days_old')}
    common = [c.name for c in db.metadata.tables['closure_days'].columns if c.name in old_columns]
    column_list = ', '.join(common)
    db.session.execute(text(
        f"INSERT INTO closure_days ({column_list}) SELECT {column_list} FROM closure_days_old"
    ))
    db.session.execute(text("DROP TABLE closure_days_old"))
    db.session.commit()

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    db.create_all()

    inspector = inspect(db.engine)
    _apply_schema_patches(inspector)
    _drop_closure_date_unique_constraint(inspector)

    logging.info("Database tables created")

    # Initialize admin user if not exists
    if not models.User.query.filter_by(username='admin').first():
        default_pw = os.environ.get('ADMIN_DEFAULT_PASSWORD')
        if not default_pw:
            default_pw = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
            logging.warning("=" * 60)
            logging.warning("DEFAULT ADMIN PASSWORD: %s", default_pw)
            logging.warning("Change this immediately via Profile > Change Password")
            logging.warning("Set ADMIN_DEFAULT_PASSWORD env var to control this.")
            logging.warning("=" * 60)
        admin = models.User()
        admin.username = 'admin'
        admin.email = 'admin@smartworker.com'
        admin.full_name = 'System Administrator'
        admin.role = 'admin'
        admin.set_password(default_pw)
        db.session.add(admin)
        db.session.commit()
        logging.info("Default admin user created")

    # Seed the singleton company settings row
    if not models.CompanySetting.query.first():
        db.session.add(models.CompanySetting(name='SmartWorker'))
        db.session.commit()
        logging.info("Default company settings created")
