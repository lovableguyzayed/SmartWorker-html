import os
import secrets
import string
import logging
from flask import Flask
from flask_compress import Compress
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
_db_url = os.environ.get("DATABASE_URL", "sqlite:///smartworker.db")
# Supabase/Heroku style URLs use the legacy postgres:// scheme SQLAlchemy 2.x rejects
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
# Supabase requires TLS; add sslmode when the URL doesn't specify one
if _db_url.startswith("postgresql") and "supabase.co" in _db_url and "sslmode=" not in _db_url:
    _db_url += ("&" if "?" in _db_url else "?") + "sslmode=require"
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit

# initialize the app with the extensions
db.init_app(app)
csrf.init_app(app)

# Gzip/Brotli-compress every response (HTML, CSS, JS, JSON, fonts) — the
# 144KB of vendored CSS shrinks to ~30KB on the wire. COMPRESS_STREAMS
# covers static files (served in streaming passthrough mode) and the
# streaming algorithm list includes gzip for older Android WebViews.
app.config['COMPRESS_STREAMS'] = True
app.config['COMPRESS_ALGORITHM_STREAMING'] = ['br', 'gzip', 'deflate']
Compress(app)

# Columns added after the initial release. Applied with ALTER TABLE so existing
# databases upgrade in place without losing data.
SCHEMA_PATCHES = {
    'users': [
        ('phone', "VARCHAR(20)"),
        ('role', "VARCHAR(20) DEFAULT 'attendance'"),
        ('assigned_site_ids', "TEXT"),
        ('assigned_project_ids', "TEXT"),
        ('created_by', "INTEGER"),
        ('status', "VARCHAR(20) DEFAULT 'active'"),
        ('profile_image', "TEXT"),
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
    'leave_adjustments': [
        ('effective_date', "DATE"),
    ],
}

# Multi-tenant migration: every business table gains an account_id, and the
# users table gains supabase_uid (Supabase Auth link) + account_id. Applied via
# ALTER TABLE ADD COLUMN so existing databases upgrade in place. Idempotent:
# _apply_schema_patches skips columns that already exist.
_TENANT_TABLES = [
    'company_settings', 'sites', 'departments', 'projects', 'work_tasks',
    'project_assignments', 'worker_modifications', 'leave_adjustments',
    'worker_transactions', 'notifications', 'workers', 'attendance_records',
    'closure_days', 'payroll_records',
]
for _t in _TENANT_TABLES:
    SCHEMA_PATCHES.setdefault(_t, []).append(('account_id', "INTEGER"))
SCHEMA_PATCHES.setdefault('users', []).extend([
    ('account_id', "INTEGER"),
    ('supabase_uid', "VARCHAR(64)"),
])


def _relax_password_not_null():
    """Supabase-authenticated users have no local password, so users.password_hash
    must be nullable. Existing Postgres databases created it NOT NULL; drop that.
    (SQLite dev databases only use the local-password path, which always sets it.)"""
    if not db.engine.url.drivername.startswith('postgresql'):
        return
    try:
        db.session.execute(text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.info("password_hash NOT NULL relax skipped: %s", e)


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
    blocks site/project-scoped closures sharing a date. Rebuild the table once.

    pysqlite implicitly commits around DDL, so the rename/create/copy/drop can
    never be one true transaction. Instead every step is idempotent and
    resumable: if a previous attempt crashed midway, the leftover
    closure_days_old is detected on the next startup and the copy completes
    without losing rows (INSERT OR IGNORE keys on the preserved primary key)."""
    if not db.engine.url.drivername.startswith('sqlite'):
        return
    tables = inspector.get_table_names()
    resuming = 'closure_days_old' in tables
    if not resuming:
        if 'closure_days' not in tables:
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
    else:
        logging.info("Resuming interrupted closure_days rebuild")
    try:
        if not resuming:
            db.session.execute(text("ALTER TABLE closure_days RENAME TO closure_days_old"))
        fresh = inspect(db.engine)
        if 'closure_days' not in fresh.get_table_names():
            db.metadata.tables['closure_days'].create(bind=db.session.connection())
        old_columns = {col['name'] for col in fresh.get_columns('closure_days_old')}
        common = [c.name for c in db.metadata.tables['closure_days'].columns if c.name in old_columns]
        column_list = ', '.join(common)
        db.session.execute(text(
            f"INSERT OR IGNORE INTO closure_days ({column_list}) SELECT {column_list} FROM closure_days_old"
        ))
        db.session.execute(text("DROP TABLE closure_days_old"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error("closure_days rebuild interrupted (will resume on next startup): %s", e)
        raise

def _enable_supabase_rls():
    """Supabase exposes public-schema tables through its auto-generated REST
    API. This app never uses that API (all access goes through Flask, which
    connects as the table owner and therefore bypasses RLS), so lock every
    table down: RLS enabled with no policies = deny-all for anon/authenticated
    API roles. Idempotent; runs only against Supabase hosts."""
    if 'supabase.co' not in str(db.engine.url):
        return
    for table in db.metadata.tables:
        try:
            db.session.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        except Exception as e:
            logging.warning("Could not enable RLS on %s: %s", table, e)
    db.session.commit()
    logging.info("Row Level Security enabled on all tables (Supabase API locked down)")

def _backfill_multitenant():
    """Assign all pre-migration rows to one legacy workspace so nothing is
    orphaned when isolation turns on. The owner is the user matching
    LEGACY_OWNER_EMAIL, else the existing admin. Runs outside a request context,
    so tenant filtering is inactive and every row is visible. Idempotent: only
    rows/users whose account_id is still NULL are touched."""
    import models as m

    tenant_tables = list(_TENANT_TABLES)
    unowned_users = m.User.query.filter(m.User.account_id.is_(None)).all()
    has_unowned_rows = any(
        db.session.execute(
            text(f"SELECT 1 FROM {t} WHERE account_id IS NULL LIMIT 1")
        ).first() is not None
        for t in tenant_tables
    )
    if not unowned_users and not has_unowned_rows:
        return

    legacy_email = (os.environ.get('LEGACY_OWNER_EMAIL') or '').strip().lower() or None
    owner = None
    if legacy_email:
        owner = m.User.query.filter_by(email=legacy_email).first()
    if not owner:
        owner = (m.User.query.filter_by(role='admin').first()
                 or m.User.query.first())

    account = m.Account(
        name=(f"{owner.full_name}'s Workspace" if owner and owner.full_name else 'Legacy Workspace'),
        owner_uid=(owner.supabase_uid if owner else None),
    )
    db.session.add(account)
    db.session.flush()

    for u in unowned_users:
        u.account_id = account.id
    for t in tenant_tables:
        db.session.execute(
            text(f"UPDATE {t} SET account_id = :aid WHERE account_id IS NULL"),
            {'aid': account.id},
        )
    db.session.commit()
    logging.info("Multi-tenant backfill: assigned legacy data to account %s (%s)",
                 account.id, account.name)


with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    import tenancy
    db.create_all()

    inspector = inspect(db.engine)
    _apply_schema_patches(inspector)
    _relax_password_not_null()
    _drop_closure_date_unique_constraint(inspector)
    _enable_supabase_rls()

    # Wire automatic per-account data isolation (SELECT filter + INSERT stamp).
    tenancy.register(db)

    # Move any images still on the local filesystem into Supabase Storage
    # (no-op unless SUPABASE_URL + SUPABASE_SERVICE_KEY are configured).
    import storage as _storage
    _storage.migrate_local_uploads(app, db)

    if not _storage.storage_enabled() and os.environ.get('RENDER'):
        logging.warning(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set. Uploaded images "
            "are being written to Render's EPHEMERAL disk and will be lost on "
            "the next deploy or restart. Set the Supabase Storage env vars to "
            "make uploads permanent.")

    # Rows can point at /static/uploads files that no longer exist (uploaded
    # while Supabase Storage was unconfigured, then wiped by a redeploy). Clear
    # those references so the UI shows its clean initial-letter fallback instead
    # of a broken image, and a fresh upload fully replaces them.
    def _clear_dead_image_paths():
        marker = '/static/uploads/'

        def _dead(local_url):
            if not local_url or marker not in local_url:
                return False
            rel = local_url.split(marker, 1)[1]
            return not os.path.isfile(os.path.join(app.static_folder, 'uploads', *rel.split('/')))

        cleared = 0
        for worker in models.Worker.query.filter(models.Worker.profile_image.like(f'%{marker}%')).all():
            if _dead(worker.profile_image):
                worker.profile_image = None
                cleared += 1
        for user in models.User.query.filter(models.User.profile_image.like(f'%{marker}%')).all():
            if _dead(user.profile_image):
                user.profile_image = None
                cleared += 1
        company_rows = models.CompanySetting.query.filter(models.CompanySetting.logo.like(f'%{marker}%')).all()
        for company in company_rows:
            if _dead(company.logo):
                company.logo = None
                cleared += 1
        if cleared:
            db.session.commit()
            logging.warning("Cleared %d image reference(s) whose files were lost "
                            "on an earlier redeploy — re-upload those photos.", cleared)

    _clear_dead_image_paths()

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

    # Seed a company settings row if none exists yet (legacy/first-run).
    if not models.CompanySetting.query.first():
        db.session.add(models.CompanySetting(name='SmartWorker'))
        db.session.commit()
        logging.info("Default company settings created")

    # Assign all pre-migration rows (and the default admin) to a workspace so
    # data isolation has an owner for existing data. Must run last, after the
    # admin/company rows exist.
    _backfill_multitenant()
