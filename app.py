import os
import secrets
import string
import hashlib
import logging
from flask import Flask, g, request
from flask_compress import Compress
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Safe to import here: timeutil pulls in nothing but the standard library,
# so it cannot form a cycle with app or models.
from timeutil import now_ist

# Configure logging. DEBUG floods Render's (limited) log retention and risks
# writing request data into logs, so it is opt-in via FLASK_DEBUG rather than
# the default it used to be.
_debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
logging.basicConfig(level=logging.DEBUG if _debug else logging.INFO)

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


# ------------------------------------------------------------------
# Cache-busted static URLs.
#
# The service worker serves /static/ cache-first. Because every asset
# URL was a fixed path, a phone that installed the app in July kept
# serving July's custom.css for months: the calendar's grid rules were
# added in August and simply never reached the device, so the month grid
# rendered as a single column of plain <div>s. Stamping each URL with a
# hash of the file's contents means a changed file is a changed URL, so
# cache-first can only ever return the matching version.
# ------------------------------------------------------------------
_static_versions = {}


def _static_version(filename):
    """Short content hash for a file under static/, computed once per process.

    Hashing the bytes rather than the mtime means a redeploy that does not
    change a file keeps its URL, so phones re-download only what actually
    changed. Each file is read at most once per worker process.
    """
    if filename in _static_versions:
        return _static_versions[filename]
    version = None
    try:
        path = os.path.join(app.static_folder, filename)
        digest = hashlib.sha1()
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
        version = digest.hexdigest()[:10]
    except OSError:
        # A missing file is the caller's problem, not this helper's — fall
        # through with no version rather than breaking the page.
        version = None
    _static_versions[filename] = version
    return version


@app.url_defaults
def _stamp_static_url(endpoint, values):
    if endpoint != 'static' or 'filename' not in values or 'v' in values:
        return
    version = _static_version(values['filename'])
    if version:
        values['v'] = version

# Session cookie hardening. Secure is on only when the app is actually served
# over TLS, so local http development keeps working; Render terminates TLS and
# ProxyFix above makes request.is_secure reflect that.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=not _debug and os.environ.get('RENDER') is not None,
)


@app.before_request
def _csp_nonce():
    """A fresh nonce per request, for this page's own inline <script> blocks.

    The policy below allows no inline script except what carries this value,
    and it is unguessable and never reused, so markup an attacker manages to
    inject cannot carry a nonce that matches.
    """
    g.csp_nonce = secrets.token_urlsafe(16)


@app.context_processor
def _expose_csp_nonce():
    return {'csp_nonce': getattr(g, 'csp_nonce', '')}


# The policy, assembled once. Every library the app uses is vendored under
# /static — Tailwind, Font Awesome, jsPDF, html2canvas — so the only outside
# origin is Google Fonts.
_CSP = "; ".join([
    "default-src 'self'",
    # No 'unsafe-inline' here, which is the whole point: an injected <script>
    # or an onclick= an attacker gets into the page does not run. The app's
    # own inline blocks are allowed by nonce; its event handlers are
    # delegated from static/js/actions.js instead of written as attributes.
    "script-src 'self' 'nonce-{nonce}'",
    # Styles keep 'unsafe-inline'. Tailwind's utilities arrive as a
    # stylesheet, but the app also sets style="" in a couple of dozen places
    # and the day view computes a few widths at runtime. Injected CSS can
    # restyle a page; it cannot execute, which is a different order of risk,
    # and removing it would be a separate piece of work.
    # Google's two hosts were here only for Inter, which is now served
    # from this origin. Dropping them means a stylesheet or a font from
    # anywhere but this app is refused outright, rather than refused
    # everywhere except the two places that happened to be needed.
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    # data: for the QR codes the app draws into <img>; blob: for the canvas
    # the PDF exporter rasterises before handing it to jsPDF.
    "img-src 'self' data: blob: https:",
    # The QR scanner's camera preview. Without this directive media-src
    # falls back to default-src, which is 'self', and a camera stream is
    # neither: an Android WebView renders it into the <video> through a
    # blob: URL, so the policy refused it and the scanner showed a black
    # rectangle with no error. Desktop Chrome attaches the same stream as
    # srcObject, which CSP does not govern at all — which is exactly why
    # it worked in every browser it was tested in and failed in the APK.
    # mediastream: is listed for the WebViews that use that scheme instead.
    "media-src 'self' blob: mediastream:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
])


@app.after_request
def _security_headers(response):
    """The app had none of these. Three were added first; the policy, the
    permissions and HSTS came later, once the interface had been moved off
    inline event handlers and could live without 'unsafe-inline'."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    response.headers.setdefault(
        'Content-Security-Policy',
        _CSP.format(nonce=getattr(g, 'csp_nonce', '')))
    # Nothing in the application uses a camera beyond the QR scanner, which is
    # same-origin, and nothing uses the rest at all.
    response.headers.setdefault(
        'Permissions-Policy',
        'camera=(self), microphone=(), geolocation=(), payment=(), usb=()')
    # Only where TLS is actually terminated — announcing HSTS over plain http
    # on a laptop would lock the developer out of their own dev server.
    if request.is_secure:
        response.headers.setdefault(
            'Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


#: Which commit is actually running. Render sets these on every deploy;
#: read once at import so the probe stays free of work.
#:
#: Worth having because without it nobody can answer "is the new code live?".
#: An APK that showed the old app could mean the phone was serving pages from
#: its cache or that the server had never deployed, and there was no way to
#: tell the two apart — so the first thing anyone did was guess. A commit in
#: the probe turns that into one tap.
#:
#: Both are a public repository's commit and branch, so there is nothing here
#: to keep back, and nothing from the environment is echoed beyond these two.
GIT_COMMIT = (os.environ.get('RENDER_GIT_COMMIT') or '')[:7] or 'unknown'
GIT_BRANCH = os.environ.get('RENDER_GIT_BRANCH') or 'unknown'
STARTED_AT = now_ist()


@app.route('/healthz')
def healthz():
    """Cheap liveness probe for Render — no DB work, no redirect, so a slow
    query can never make the platform think the service is down.

    It also says which commit answered, which is the only way to tell a
    stale page on a phone from a deploy that never happened.
    """
    return {
        'status': 'ok',
        'commit': GIT_COMMIT,
        'branch': GIT_BRANCH,
        'started': STARTED_AT.strftime('%Y-%m-%d %H:%M:%S IST'),
        # Columns that could not be added at startup. Reading a list built
        # during boot, not asking the database — the probe still does no
        # work. Empty is the normal answer and the one to expect.
        'schema_warnings': SCHEMA_PATCH_FAILURES,
    }, 200

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


def _check_database_driver(url):
    """Say which driver is missing, before SQLAlchemy says it in forty lines.

    A URL does not name a driver unless it is written postgresql+something.
    Plain postgresql:// takes whatever SQLAlchemy's default is, and that
    default changed in 2.1 from psycopg2 to psycopg — so a service that had
    run for months died on a redeploy with

        File ".../sqlalchemy/dialects/postgresql/psycopg.py", in import_dbapi
            import psycopg
        ModuleNotFoundError: No module named 'psycopg'

    at the bottom of two full stack traces, with nothing in them saying
    "the driver is not installed" or naming the one to install. This logs
    that sentence and then gets out of the way: the real error still
    follows, because swallowing it would be worse than the traceback.
    """
    try:
        from sqlalchemy.engine.url import make_url
        dialect = make_url(url).get_dialect()
    except Exception:
        return                      # not our business to validate the URL

    # The dialect's own loader, not __import__(dialect.driver). The driver
    # name is SQLAlchemy's label for it and is not always an importable
    # module: SQLite's is "pysqlite" while the module is the standard
    # library's sqlite3, so importing the name raised here and this guard
    # announced a missing driver on every development run. Crying wolf in
    # the logs is worse than the silence it replaced.
    loader = getattr(dialect, 'import_dbapi', None) or getattr(
        dialect, 'dbapi', None)
    if loader is None:
        return
    try:
        loader()
    except ImportError:
        logging.error(
            "The database driver %r is not installed. %s resolves to it, "
            "and requirements.txt must list it — psycopg[binary] for "
            "'psycopg', psycopg2-binary for 'psycopg2'. Note that a plain "
            "postgresql:// URL picks the driver by SQLAlchemy's version, "
            "not by anything written here.",
            getattr(dialect, 'driver', '?'), url.split('://')[0] + '://')
    except Exception:
        # Anything else is not this function's question to answer, and
        # db.init_app is three lines away and will raise it properly.
        return


_check_database_driver(_db_url)

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
        # A worker's own login points at the Worker record it may see.
        ('worker_id', "INTEGER"),
        # Supervisor powers, granted one at a time and off by default.
        ('assigned_worker_ids', "TEXT"),
        ('can_mark_attendance', "BOOLEAN NOT NULL DEFAULT 0"),
        ('can_record_transactions', "BOOLEAN NOT NULL DEFAULT 0"),
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
        # How a worker actually gets paid. The app worked out what each
        # person was owed to the rupee and then had nowhere to send it.
        ('bank_account_name', "VARCHAR(120)"),
        ('bank_account_number', "VARCHAR(34)"),
        ('bank_ifsc', "VARCHAR(11)"),
        ('upi_id', "VARCHAR(100)"),
        ('aadhaar_number', "VARCHAR(12)"),
        ('pan_number', "VARCHAR(10)"),
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
    # Finalised payroll keeps a frozen copy of how it was calculated, so a
    # later change to salary policy cannot rewrite a month that was already
    # paid. Added after release, hence the patch rather than a fresh table.
    'payroll_records': [
        ('breakdown_json', "TEXT"),
        ('policy_json', "TEXT"),
        ('finalized_at', "DATETIME"),
        # How much of the month has actually been handed over. Left NULL on
        # existing rows on purpose: PayrollRecord.settled_amount reads a NULL
        # here together with status='paid' as "the whole net was paid", so
        # months settled before the upgrade do not reopen as unpaid.
        ('paid_amount', "FLOAT"),
    ],
    'worker_transactions': [
        ('payment_mode', "VARCHAR(20)"),
        ('reference_no', "VARCHAR(60)"),
        ('acknowledged_at', "DATETIME"),
        ('acknowledged_by', "INTEGER"),
    ],
    'company_settings': [
        ('dues_allocation', "VARCHAR(20) DEFAULT 'month'"),
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
    'closure_days', 'payroll_records', 'salary_policies', 'salary_policy_audits',
]
for _t in _TENANT_TABLES:
    SCHEMA_PATCHES.setdefault(_t, []).append(('account_id', "INTEGER"))
SCHEMA_PATCHES.setdefault('users', []).extend([
    ('account_id', "INTEGER"),
    ('supabase_uid', "VARCHAR(64)"),
])


def _scope_unique_constraints_to_account():
    """Re-scope globally-unique columns to their workspace.

    workers.worker_id and departments.name were created UNIQUE across the whole
    table, but employee IDs are generated per workspace — so the second
    workspace to add e.g. CI001 failed with an IntegrityError. Replace the
    single-column constraints with composite (account_id, …) unique indexes.

    Postgres only: SQLite cannot drop a column-level UNIQUE without rebuilding
    the table, and dev databases are recreated from the corrected models.
    """
    if not db.engine.url.drivername.startswith('postgresql'):
        return
    steps = [
        'ALTER TABLE workers DROP CONSTRAINT IF EXISTS workers_worker_id_key',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_worker_account_worker_id '
        'ON workers (account_id, worker_id)',
        'ALTER TABLE departments DROP CONSTRAINT IF EXISTS departments_name_key',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_department_account_name '
        'ON departments (account_id, name)',
    ]
    for statement in steps:
        try:
            db.session.execute(text(statement))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logging.info('Unique-constraint migration step skipped: %s (%s)',
                         statement[:60], exc)


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


#: Patch failures, kept so /healthz can report them. A migration that did
#: not apply leaves a feature broken in a way no screen explains, and a
#: line in a log nobody reads is not telling anyone.
SCHEMA_PATCH_FAILURES = []

#: The DDL above is written in SQLite's spelling, which is what development
#: runs on. Postgres, which is what production runs on, disagrees on two
#: points, and both are silent until a column is genuinely missing on a
#: table that already exists — so they survive every fresh database (where
#: create_all builds the columns correctly from the models and no patch
#: runs at all) and only fire on the live one.
#:
#:   DATETIME   Postgres has no such type. It is TIMESTAMP, and the error
#:              is `type "datetime" does not exist`.
#:   DEFAULT 0  A Postgres boolean will not take an integer default:
#:              `column is of type boolean but default expression is of
#:              type integer`.
#:
#: SQLAlchemy already knows this — DateTime() compiles to DATETIME on
#: SQLite and TIMESTAMP WITHOUT TIME ZONE on Postgres — but these patches
#: are hand-written strings and so get none of that.
_POSTGRES_DDL = (
    ('DATETIME', 'TIMESTAMP'),
    ('BOOLEAN NOT NULL DEFAULT 0', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('BOOLEAN NOT NULL DEFAULT 1', 'BOOLEAN NOT NULL DEFAULT TRUE'),
    ('BOOLEAN DEFAULT 0', 'BOOLEAN DEFAULT FALSE'),
    ('BOOLEAN DEFAULT 1', 'BOOLEAN DEFAULT TRUE'),
)


def _portable_ddl(ddl, is_postgres):
    """One column's DDL in the dialect that will actually receive it."""
    if not is_postgres:
        return ddl
    for sqlite_spelling, postgres_spelling in _POSTGRES_DDL:
        if ddl.upper().startswith(sqlite_spelling):
            return postgres_spelling + ddl[len(sqlite_spelling):]
    return ddl


def _apply_schema_patches(inspector):
    is_postgres = db.engine.url.drivername.startswith('postgresql')
    for table, patches in SCHEMA_PATCHES.items():
        if table not in inspector.get_table_names():
            continue
        existing_columns = {col['name'] for col in inspector.get_columns(table)}
        for column, ddl in patches:
            if column in existing_columns:
                continue
            statement = "ALTER TABLE %s ADD COLUMN %s %s" % (
                table, column, _portable_ddl(ddl, is_postgres))
            # One patch that cannot apply must not take the whole service
            # down with it. Before this, a single bad ALTER raised straight
            # out of startup, the worker died, and the platform reported a
            # failed deploy — losing every screen to protect one column.
            # The failure is recorded instead, and /healthz says so.
            try:
                db.session.execute(text(statement))
                db.session.commit()
                logging.info("Added %s column to %s", column, table)
            except Exception as exc:
                db.session.rollback()
                SCHEMA_PATCH_FAILURES.append('%s.%s' % (table, column))
                logging.error("Schema patch failed, continuing without it: "
                              "%s — %s", statement, exc)

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
    _scope_unique_constraints_to_account()
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
