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

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    db.create_all()
    
    # Lightweight schema patch for existing DBs.
    inspector = inspect(db.engine)
    if 'users' in inspector.get_table_names():
        user_columns = {col['name'] for col in inspector.get_columns('users')}
        if 'phone' not in user_columns:
            db.session.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN phone VARCHAR(20)"
                )
            )
            db.session.commit()
            logging.info("Added phone column to users")

    if 'closure_days' in inspector.get_table_names():
        closure_columns = {col['name'] for col in inspector.get_columns('closure_days')}
        if 'allow_attendance' not in closure_columns:
            db.session.execute(
                text(
                    "ALTER TABLE closure_days "
                    "ADD COLUMN allow_attendance BOOLEAN NOT NULL DEFAULT 1"
                )
            )
            db.session.commit()
            logging.info("Added allow_attendance column to closure_days")
    
    if 'workers' in inspector.get_table_names():
        worker_columns = {col['name'] for col in inspector.get_columns('workers')}
        if 'project_rate' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN project_rate FLOAT"
                )
            )
            db.session.commit()
            logging.info("Added project_rate column to workers")
        if 'late_policy_enabled' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN late_policy_enabled BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            db.session.commit()
            logging.info("Added late_policy_enabled column to workers")
        if 'late_deduction_per_day' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN late_deduction_per_day FLOAT"
                )
            )
            db.session.commit()
            logging.info("Added late_deduction_per_day column to workers")
        if 'late_deduction_type' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN late_deduction_type VARCHAR(10) DEFAULT 'day'"
                )
            )
            db.session.commit()
            logging.info("Added late_deduction_type column to workers")
        if 'no_work_no_pay' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN no_work_no_pay BOOLEAN NOT NULL DEFAULT 1"
                )
            )
            db.session.commit()
            logging.info("Added no_work_no_pay column to workers")
        if 'half_day_rate' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN half_day_rate FLOAT"
                )
            )
            db.session.commit()
            logging.info("Added half_day_rate column to workers")
        if 'half_day_grace_minutes' not in worker_columns:
            db.session.execute(
                text(
                    "ALTER TABLE workers "
                    "ADD COLUMN half_day_grace_minutes INTEGER NOT NULL DEFAULT 20"
                )
            )
            db.session.commit()
            logging.info("Added half_day_grace_minutes column to workers")
    
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
