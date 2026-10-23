"""Set up Uttaranchal Stone Crusher as the only account, for a live demo.

Run it against whichever database the app is pointed at:

    python tools/seed_uttaranchal.py            # shows what it would do
    python tools/seed_uttaranchal.py --apply    # does it

It DELETES every existing account, user, worker and record first. That is
the point of it — the demo has to be one clean company — but it is also why
nothing happens without --apply.

What it builds:
  * one company, Uttaranchal Stone Crusher, with an admin login
  * that admin also on the payroll as a monthly-salaried employee
  * ten more workers, one of every pay type and employment type the app
    supports, so each screen has something real to show
  * attendance from the joining date to yesterday, a closure day, a night
    shift changeover, and one advance payment
"""
import argparse
import os
import sys
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import app, db
import models as m

# ---------------------------------------------------------------- the facts
COMPANY = 'Uttaranchal Stone Crusher'
ADMIN_USER = 'Javed'
ADMIN_PASS = '7906030129'
ADMIN_EMAIL = 'javed@uttaranchalstonecrusher.in'
ADMIN_PHONE = '7906030129'

YEAR = 2026
JOINED = date(YEAR, 8, 7)          # 7 August
CLOSURE = date(YEAR, 10, 19)       # day and night both off
NIGHTS_FROM = date(YEAR, 10, 21)   # on nights from here
PAID_ON = date(YEAR, 10, 22)       # ₹20,000 handed over
PAID_AMOUNT = 20000.0
TODAY = date(YEAR, 10, 23)         # the day the demo is given
# Two of the crew are deliberately left unmarked today, so there is
# something real to scan in front of an audience. The rest are marked, so
# the dashboard opens on a working day rather than on ten absences.
UNMARKED_TODAY = ('USC006', 'USC009')

DAY_IN, DAY_OUT = time(8, 0), time(20, 0)
NIGHT_IN, NIGHT_OUT = time(20, 0), time(8, 0)

MONTHLY_SALARY = 23000.0
LEAVES_PER_MONTH = 2

# A stone crusher's actual roll: every pay type the app supports, so the
# payroll screen shows each calculation path rather than twelve copies of
# the same one.
CREW = [
    # (id, name, position, dept, type, pay_type, rate field + value, status)
    ('USC002', 'Rakesh Negi', 'Crusher Operator', 'Crushing',
     'permanent', 'monthly', ('monthly_salary', 18000), 'active'),
    ('USC003', 'Mohan Singh Rawat', 'Weighbridge Clerk', 'Admin',
     'permanent', 'monthly', ('monthly_salary', 15000), 'active'),
    ('USC004', 'Dinesh Kumar', 'JCB Driver', 'Loading',
     'permanent', 'daily', ('daily_rate', 850), 'active'),
    ('USC005', 'Suresh Lal', 'Loader Operator', 'Loading',
     'contract', 'daily', ('daily_rate', 700), 'active'),
    ('USC006', 'Pappu Yadav', 'Helper', 'Crushing',
     'temporary', 'daily', ('daily_rate', 500), 'active'),
    ('USC007', 'Imran Ali', 'Mukadam', 'Crushing',
     'permanent', 'daily', ('daily_rate', 900), 'active'),
    ('USC008', 'Vikram Bisht', 'Electrician', 'Maintenance',
     'contract', 'hourly', ('hourly_rate', 180), 'active'),
    ('USC009', 'Harish Chandra', 'Fitter', 'Maintenance',
     'contract', 'hourly', ('hourly_rate', 150), 'active'),
    ('USC010', 'Ramesh Thapa', 'Blasting Contractor', 'Crushing',
     'contract', 'project', ('project_rate', 45000), 'active'),
    ('USC011', 'Gopal Das', 'Security Guard', 'Security',
     'permanent', 'monthly', ('monthly_salary', 12000), 'inactive'),
]

DEPARTMENTS = ['Crushing', 'Loading', 'Maintenance', 'Admin', 'Security']


def wipe():
    """Everything goes. Children first, so no foreign key is left dangling."""
    for Model in (m.AttendanceRecord, m.WorkerTransaction, m.PayrollRecord,
                  m.SalaryPolicyAudit, m.SalaryPolicy, m.LeaveAdjustment,
                  m.WorkerModification, m.ProjectAssignment, m.Notification,
                  m.ClosureDay, m.WorkTask, m.Project, m.Site,
                  m.Department, m.CompanySetting, m.Worker, m.User,
                  m.Account):
        n = Model.query.delete()
        print('   cleared %-22s %d row(s)' % (Model.__name__, n))
    db.session.commit()


def working_days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build():
    acct = m.Account(name=COMPANY, status='active')
    db.session.add(acct)
    db.session.flush()

    db.session.add(m.CompanySetting(
        account_id=acct.id, name=COMPANY,
        address='Kotdwar Road, Haridwar, Uttarakhand',
        phone=ADMIN_PHONE, email=ADMIN_EMAIL))

    for name in DEPARTMENTS:
        db.session.add(m.Department(account_id=acct.id, name=name,
                                    status='active'))
    site = m.Site(account_id=acct.id, name='Crusher Plant — Haridwar',
                  address='Kotdwar Road, Haridwar', contact_person=ADMIN_USER,
                  contact_phone=ADMIN_PHONE, status='active')
    db.session.add(site)
    db.session.flush()
    project = m.Project(account_id=acct.id, name='Aggregate Supply 2026-27',
                        description='Crushed stone supply contract',
                        site_id=site.id, start_date=date(YEAR, 4, 1),
                        status='active')
    db.session.add(project)
    db.session.flush()
    for t in ('Crushing', 'Screening', 'Loading & Dispatch'):
        db.session.add(m.WorkTask(account_id=acct.id, name=t,
                                  project_id=project.id, status='active'))

    # --- the owner, who is also on the payroll -------------------------
    me = m.Worker(
        account_id=acct.id, worker_id='USC001', full_name='Javed',
        phone=ADMIN_PHONE, email=ADMIN_EMAIL, position='Plant Incharge',
        department='Admin', employee_type='permanent', join_date=JOINED,
        pay_type='monthly', monthly_salary=MONTHLY_SALARY,
        start_time=DAY_IN, end_time=DAY_OUT,
        allowed_leaves_per_month=LEAVES_PER_MONTH, leave_policy_enabled=True,
        status='active')
    db.session.add(me)
    db.session.flush()

    admin = m.User(username=ADMIN_USER, email=ADMIN_EMAIL, full_name='Javed',
                   role='admin')
    admin.account_id = acct.id
    admin.set_password(ADMIN_PASS)
    db.session.add(admin)
    db.session.flush()

    # The company-wide salary rule, and the one that matters for Javed:
    # joining_mode 'attendance' pays only the days actually worked since
    # joining, which is both "paid from 7 August" and "no leave system in
    # the joining month" — a leave day that month simply is not a paid day.
    db.session.add(m.SalaryPolicy(
        account_id=acct.id, worker_id=None,
        salary_basis='fixed', basis_days=30, rounding='nearest',
        joining_mode='attendance', paid_leave_enabled=True,
        monthly_leave_allowance=LEAVES_PER_MONTH, leave_carry_forward=False,
        absence_deduction_enabled=True,
        calculation_method='salary_minus_deductions',
        updated_by=admin.id))

    # --- the rest of the crew ------------------------------------------
    workers = [me]
    for wid, name, pos, dept, etype, pay, (field, rate), status in CREW:
        w = m.Worker(account_id=acct.id, worker_id=wid, full_name=name,
                     phone='90000%05d' % (int(wid[-3:]) + 10000),
                     position=pos, department=dept, employee_type=etype,
                     join_date=date(YEAR, 4, 1), pay_type=pay,
                     start_time=DAY_IN, end_time=DAY_OUT,
                     allowed_leaves_per_month=LEAVES_PER_MONTH,
                     leave_policy_enabled=(pay == 'monthly'),
                     status=status)
        setattr(w, field, float(rate))
        db.session.add(w)
        workers.append(w)
    db.session.flush()

    # The mukadam gets a worker login with the powers an admin would grant.
    mukadam = next(w for w in workers if w.worker_id == 'USC007')
    team = [w.id for w in workers if w.worker_id in
            ('USC004', 'USC005', 'USC006')]
    sup = m.User(username='imran', email='imran@uttaranchalstonecrusher.in',
                 full_name=mukadam.full_name, role='worker')
    sup.account_id = acct.id
    sup.set_password('imran12345')
    sup.worker_id = mukadam.id
    sup.can_mark_attendance = True
    sup.can_record_transactions = True
    sup.assigned_worker_ids = ','.join(str(i) for i in team)
    db.session.add(sup)

    # --- 19 October: day and night both off ----------------------------
    db.session.add(m.ClosureDay(
        account_id=acct.id, date=CLOSURE,
        reason='Plant maintenance — day and night shift both closed',
        type='closure', scope='company', allow_attendance=False))

    # --- attendance -----------------------------------------------------
    # Javed: every day from joining to yesterday, no leave, on days until
    # 20 October and on nights from the 21st.
    for d in working_days(JOINED, TODAY):
        if d == CLOSURE:
            continue                       # the plant was shut
        night = d >= NIGHTS_FROM
        # check_in_time/check_out_time are DATETIME, not TIME: a night shift
        # clocks in at 20:00 and out at 08:00 the NEXT morning, and storing
        # only the clock time would make every night shift look like minus
        # twelve hours.
        if night:
            in_at = datetime.combine(d, NIGHT_IN)
            out_at = datetime.combine(d + timedelta(days=1), NIGHT_OUT)
        else:
            in_at = datetime.combine(d, DAY_IN)
            out_at = datetime.combine(d, DAY_OUT)
        db.session.add(m.AttendanceRecord(
            account_id=acct.id, worker_id=me.id, date=d, status='present',
            check_in_time=in_at, check_out_time=out_at,
            shift='night' if night else 'day',
            site_id=site.id, marked_by=admin.id, marked_via='manual'))

    # The crew: a believable roll for the current month, so the attendance
    # and payroll screens have range in them rather than a column of
    # identical ticks.
    import random
    random.seed(7)                        # same demo every time it is run
    pattern = {'USC002': 0.97, 'USC003': 0.95, 'USC004': 0.92,
               'USC005': 0.88, 'USC006': 0.80, 'USC007': 0.98,
               'USC008': 0.75, 'USC009': 0.70, 'USC010': 0.60}
    for w in workers:
        if w.worker_id == 'USC001' or w.status != 'active':
            continue
        p = pattern.get(w.worker_id, 0.9)
        for d in working_days(date(YEAR, 8, 1), TODAY):
            if d == CLOSURE:
                continue
            if d == TODAY and w.worker_id in UNMARKED_TODAY:
                continue                   # left for the live scan
            roll = 0.0 if d == TODAY else random.random()
            if roll < p:
                status = 'present'
            elif roll < p + 0.04:
                status = 'late'
            elif roll < p + 0.07:
                status = 'leave'
            else:
                status = 'absent'
            rec = m.AttendanceRecord(
                account_id=acct.id, worker_id=w.id, date=d, status=status,
                shift='day', site_id=site.id, marked_by=admin.id,
                marked_via='qr')
            if status in ('present', 'late'):
                rec.check_in_time = datetime.combine(
                    d, time(8, 12) if status == 'late' else DAY_IN)
                rec.check_out_time = datetime.combine(d, DAY_OUT)
                if status == 'late':
                    rec.late_minutes = 12
            if status == 'leave':
                rec.leave_type = 'casual'
            db.session.add(rec)

    # --- the ₹20,000 handed over on 22 October --------------------------
    db.session.add(m.WorkerTransaction(
        account_id=acct.id, worker_id=me.id, txn_type='advance',
        amount=PAID_AMOUNT, date=PAID_ON,
        description='Advance paid in cash (night shift)',
        status='active', created_by=admin.id))
    # A couple more so the transactions screen is not a single row.
    db.session.add(m.WorkerTransaction(
        account_id=acct.id,
        worker_id=next(w.id for w in workers if w.worker_id == 'USC004'),
        txn_type='advance', amount=3000.0, date=date(YEAR, 10, 10),
        description='Advance against wages', status='active',
        created_by=admin.id))
    db.session.add(m.WorkerTransaction(
        account_id=acct.id,
        worker_id=next(w.id for w in workers if w.worker_id == 'USC002'),
        txn_type='bonus', amount=2500.0, date=date(YEAR, 10, 15),
        description='Target bonus — October despatch', status='active',
        created_by=admin.id))

    db.session.commit()
    return acct, admin, me, workers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='actually delete and rebuild; without it, nothing '
                         'is written')
    args = ap.parse_args()

    with app.app_context():
        uri = app.config['SQLALCHEMY_DATABASE_URI']
        shown = uri.split('@')[-1] if '@' in uri else uri
        print('database : %s' % shown)
        print('counts now: %d account(s), %d user(s), %d worker(s), '
              '%d attendance row(s)'
              % (m.Account.query.count(), m.User.query.count(),
                 m.Worker.query.count(), m.AttendanceRecord.query.count()))
        if not args.apply:
            print('\nThis would DELETE all of the above and rebuild the '
                  'database as\n%s with %d workers.'
                  % (COMPANY, len(CREW) + 1))
            print('Nothing has been written. Re-run with --apply to do it.')
            return
        print('\nwiping:')
        wipe()
        print('\nbuilding:')
        acct, admin, me, workers = build()
        print('   company           %s (account %d)' % (COMPANY, acct.id))
        print('   admin login       %s / %s' % (ADMIN_USER, ADMIN_PASS))
        print('   mukadam login     imran / imran12345')
        print('   workers           %d' % m.Worker.query.count())
        print('   attendance rows   %d' % m.AttendanceRecord.query.count())
        print('   transactions      %d' % m.WorkerTransaction.query.count())
        print('\nDone.')


if __name__ == '__main__':
    main()
