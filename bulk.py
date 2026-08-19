"""Bulk actions for the multi-selection UI.

One endpoint — POST /api/bulk/<scope> — serves every selectable list in the
app. The client posts `action` plus repeated `ids` fields; each scope handler
below decides what that means and who is allowed to do it.

Three rules hold for every handler, so they are enforced here rather than
being re-implemented per scope:

  * Ids are never trusted. Every handler re-queries the objects through the
    tenant-scoped session, so an id belonging to another workspace simply
    does not come back and is silently skipped.
  * Permissions are checked server-side. Hiding a button in a template is a
    UX affordance, not a control.
  * Nothing is half-applied. A handler either commits its whole batch or
    raises, and the request rolls back.
"""
from datetime import datetime, timedelta

from flask import jsonify, request
from flask_login import current_user, login_required

from app import app, db
from timeutil import today_ist
from models import (AttendanceRecord, ClosureDay, Department, LeaveAdjustment,
                    Notification, PayrollRecord, Project, ProjectAssignment,
                    Site, User, WorkTask, Worker, WorkerModification,
                    WorkerTransaction)
import routes as R


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _ids():
    """Selected ids as ints, de-duplicated, order-insensitive."""
    out = []
    for raw in request.form.getlist('ids'):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in out:
            out.append(value)
    return out


def _msg(text, category='success'):
    return {'category': category, 'text': text}


def _reply(messages, success=True, **extra):
    payload = {'success': success, 'messages': messages}
    payload.update(extra)
    return jsonify(payload)


def _denied():
    return _reply([_msg('Please contact the Administrator to make changes.',
                        'restricted')], success=False)


def _plural(n, singular, plural=None):
    return singular if n == 1 else (plural or singular + 's')


# --------------------------------------------------------------------------
# scope: attendance — mark many workers at once for one date
# --------------------------------------------------------------------------

def _bulk_attendance(action):
    on_date = R.parse_iso_date(request.form.get('date'))
    if not on_date:
        return _reply([_msg('Invalid date.', 'error')], success=False)

    editable, _reason, block = R._date_editability(on_date)
    if not editable:
        return _reply([_msg(block, 'error')], success=False)

    # Attendance-role users may record attendance, but not reclassify someone
    # as absent/leave after the fact — that is an administrative decision.
    if action not in ('present', 'late', 'close') and not current_user.is_admin:
        return _denied()

    allowed = {w.id: w for w in R._visible_active_workers(on_date)}
    targets = [allowed[i] for i in _ids() if i in allowed]
    if not targets:
        return _reply([_msg('Nothing to update — those workers are not '
                            'available on this date.', 'info')], success=False)

    closures_today = ClosureDay.query.filter_by(date=on_date).all()
    changed = 0
    skipped_locked = 0
    overtime_total = 0

    for worker in targets:
        closure = R.closure_for_worker_on_date(worker, on_date, closures_today)
        if closure and not closure.allow_attendance:
            skipped_locked += 1
            continue

        record = AttendanceRecord.query.filter_by(worker_id=worker.id, date=on_date).first()

        if action == 'close':
            # Bank overtime by checking out an open shift. Not a status change,
            # so attendance users may do it.
            if not (record and record.check_in_time and not record.check_out_time
                    and record.status in ('present', 'late')):
                continue
            record.check_out_time = R._attendance_timestamp(on_date)
            record.overtime_minutes = R.calculate_overtime_minutes_for_record(worker, record)
            record.marked_by = current_user.id
            record.marked_via = 'bulk'
            overtime_total += record.overtime_minutes or 0
            changed += 1
            continue

        previous = record.status if record else None
        if not record:
            record = AttendanceRecord(worker_id=worker.id, date=on_date, status=action)
            db.session.add(record)

        if action in ('present', 'late'):
            start = R._attendance_timestamp(on_date)
            record.check_in_time = record.check_in_time or start
            record.check_out_time = None
            record.late_minutes = record.late_minutes or 0
            record.leave_type = None
        elif action == 'half_day':
            # Half day is not a stored status — it is derived from how long the
            # shift ran (see calculate_daily_wage_for_record). So write a shift
            # of exactly half the scheduled minutes and let the pay engine
            # classify it, instead of inventing a status the rest of the app
            # would not understand.
            scheduled = R.calculate_scheduled_minutes_for_day(worker, on_date) or 480
            if worker.start_time:
                begin = datetime.combine(on_date, worker.start_time)
            else:
                begin = R._attendance_timestamp(on_date)
            record.status = 'present'
            record.check_in_time = begin
            record.check_out_time = begin + timedelta(minutes=int(scheduled / 2))
            record.late_minutes = 0
            record.leave_type = None
            record.overtime_minutes = 0
        elif action in ('absent', 'leave'):
            record.check_in_time = None
            record.check_out_time = None
            record.overtime_minutes = 0
            record.late_minutes = 0
            record.leave_type = (request.form.get('leave_type') or 'casual') if action == 'leave' else None

        if action != 'half_day':
            record.status = action
        record.marked_by = current_user.id
        record.marked_via = 'bulk'

        if previous != record.status:
            R._log_attendance_edit(worker, on_date, 'status', previous, record.status)
        changed += 1

    db.session.commit()

    labels = {'present': 'present', 'absent': 'absent', 'late': 'late',
              'leave': 'on leave', 'half_day': 'half day', 'close': 'checked out'}
    messages = []
    if changed:
        if action == 'close':
            text = f'Checked out {changed} {_plural(changed, "shift")}.'
            if overtime_total:
                text += f' Overtime banked: {overtime_total} minutes.'
        else:
            text = f'Marked {changed} {_plural(changed, "worker")} {labels.get(action, action)}.'
        messages.append(_msg(text))
    else:
        messages.append(_msg('No records needed updating.', 'info'))
    if skipped_locked:
        messages.append(_msg(f'{skipped_locked} skipped — locked by a closure day.', 'warning'))

    note = R._payroll_lock_note(on_date)
    if note and changed:
        messages.append(_msg(note, 'warning'))
    return _reply(messages)


# --------------------------------------------------------------------------
# scope: workers
# --------------------------------------------------------------------------

def _bulk_workers(action):
    if not current_user.is_admin:
        return _denied()
    workers = Worker.query.filter(Worker.id.in_(_ids())).all() if _ids() else []
    if not workers:
        return _reply([_msg('No workers selected.', 'info')], success=False)

    n = len(workers)
    if action in ('activate', 'deactivate'):
        target = 'active' if action == 'activate' else 'inactive'
        touched = 0
        for w in workers:
            if w.status != target:
                w.status = target
                touched += 1
        db.session.commit()
        verb = 'Activated' if action == 'activate' else 'Deactivated'
        return _reply([_msg(f'{verb} {touched} {_plural(touched, "worker")}.'
                            if touched else 'No change — already in that state.',
                            'success' if touched else 'info')])

    if action == 'delete':
        # Mirrors delete_worker() exactly: every table with a NOT NULL
        # worker_id must be cleared first, or SQLAlchemy tries to null the
        # foreign key and the whole batch fails. WorkerModification and
        # LeaveAdjustment were missing here, so deleting any worker who had
        # ever been promoted or had leave adjusted silently did nothing.
        for w in workers:
            AttendanceRecord.query.filter_by(worker_id=w.id).delete()
            PayrollRecord.query.filter_by(worker_id=w.id).delete()
            ProjectAssignment.query.filter_by(worker_id=w.id).delete()
            WorkerModification.query.filter_by(worker_id=w.id).delete()
            LeaveAdjustment.query.filter_by(worker_id=w.id).delete()
            WorkerTransaction.query.filter_by(worker_id=w.id).delete()
            db.session.delete(w)
        db.session.commit()
        return _reply([_msg(f'Deleted {n} {_plural(n, "worker")} and their records.')])

    if action == 'assign':
        site_id = request.form.get('site_id', type=int)
        project_id = request.form.get('project_id', type=int)
        if not site_id and not project_id:
            return _reply([_msg('Choose a site or project first.', 'error')], success=False)
        today = today_ist()
        for w in workers:
            for existing in ProjectAssignment.query.filter_by(worker_id=w.id, status='active').all():
                existing.status = 'transferred'
                existing.end_date = today
            db.session.add(ProjectAssignment(
                worker_id=w.id, site_id=site_id or None, project_id=project_id or None,
                start_date=today, status='active', created_by=current_user.id,
                notes='Bulk assignment'))
        db.session.commit()
        return _reply([_msg(f'Assigned {n} {_plural(n, "worker")}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# scope: payroll
# --------------------------------------------------------------------------

def _bulk_payroll(action):
    if not current_user.is_admin:
        return _denied()
    month = request.form.get('month', type=int)
    year = request.form.get('year', type=int)
    if not month or not year:
        return _reply([_msg('Missing payroll period.', 'error')], success=False)

    worker_ids = _ids()
    workers = Worker.query.filter(Worker.id.in_(worker_ids)).all() if worker_ids else []
    if not workers:
        return _reply([_msg('No records selected.', 'info')], success=False)

    if action == 'generate':
        # Reuse the same builder the single "Generate payroll" button uses, so
        # a bulk run and a full run can never produce different numbers for
        # the same worker and month.
        rows, _totals, _meta = R._build_payroll_rows(month, year)
        wanted = set(worker_ids)
        saved = 0
        for row in rows:
            worker = row['worker']
            if worker.id not in wanted:
                continue
            pay, att = row['pay_summary'], row['att_summary']
            record = PayrollRecord.query.filter_by(
                worker_id=worker.id, month=month, year=year).first()
            fields = dict(
                total_days=att['total_marked_days'],
                present_days=pay['paid_days'],
                overtime_hours=round(pay['overtime_minutes'] / 60.0, 2),
                gross_pay=row['gross_pay'],
                deductions=row['deductions'],
                net_pay=row['net_pay'],
            )
            if record:
                for key, value in fields.items():
                    setattr(record, key, value)
                # Re-generating must not silently un-pay a settled record.
                if record.status != 'paid':
                    record.status = 'pending'
            else:
                db.session.add(PayrollRecord(worker_id=worker.id, month=month,
                                             year=year, status='pending', **fields))
            saved += 1
        db.session.commit()
        return _reply([_msg(f'Generated payroll for {saved} {_plural(saved, "worker")}.')])

    if action in ('paid', 'pending'):
        rows = PayrollRecord.query.filter(
            PayrollRecord.worker_id.in_(worker_ids),
            PayrollRecord.month == month,
            PayrollRecord.year == year).all()
        if not rows:
            return _reply([_msg('Those workers have no saved payroll for this month — '
                                'generate it first.', 'error')], success=False)
        for row in rows:
            row.status = action
        db.session.commit()
        label = 'paid' if action == 'paid' else 'pending'
        return _reply([_msg(f'Marked {len(rows)} {_plural(len(rows), "record")} {label}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# scope: transactions
# --------------------------------------------------------------------------

def _bulk_transactions(action):
    if not current_user.is_admin:
        return _denied()
    rows = WorkerTransaction.query.filter(WorkerTransaction.id.in_(_ids())).all() if _ids() else []
    if not rows:
        return _reply([_msg('No transactions selected.', 'info')], success=False)
    n = len(rows)

    if action == 'cancel':
        touched = 0
        for t in rows:
            if t.status != 'cancelled':
                t.status = 'cancelled'
                touched += 1
        db.session.commit()
        return _reply([_msg(f'Cancelled {touched} {_plural(touched, "transaction")}.'
                            if touched else 'Those are already cancelled.',
                            'success' if touched else 'info')])

    if action == 'restore':
        for t in rows:
            t.status = 'active'
        db.session.commit()
        return _reply([_msg(f'Restored {n} {_plural(n, "transaction")}.')])

    if action == 'delete':
        for t in rows:
            db.session.delete(t)
        db.session.commit()
        return _reply([_msg(f'Deleted {n} {_plural(n, "transaction")}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# scope: assignments
# --------------------------------------------------------------------------

def _bulk_assignments(action):
    if not current_user.is_admin:
        return _denied()
    worker_ids = _ids()
    if not worker_ids:
        return _reply([_msg('No workers selected.', 'info')], success=False)
    today = today_ist()

    if action == 'end':
        rows = ProjectAssignment.query.filter(
            ProjectAssignment.worker_id.in_(worker_ids),
            ProjectAssignment.status == 'active').all()
        if not rows:
            return _reply([_msg('None of those workers has an active assignment.',
                                'info')], success=False)
        for row in rows:
            row.status = 'completed'
            row.end_date = today
        db.session.commit()
        return _reply([_msg(f'Ended {len(rows)} {_plural(len(rows), "assignment")}.')])

    if action == 'assign':
        site_id = request.form.get('site_id', type=int)
        project_id = request.form.get('project_id', type=int)
        task_id = request.form.get('task_id', type=int)
        if not (site_id or project_id):
            return _reply([_msg('Choose a site or project first.', 'error')], success=False)
        workers = Worker.query.filter(Worker.id.in_(worker_ids)).all()
        for w in workers:
            for existing in ProjectAssignment.query.filter_by(worker_id=w.id, status='active').all():
                existing.status = 'transferred'
                existing.end_date = today
            db.session.add(ProjectAssignment(
                worker_id=w.id, site_id=site_id or None, project_id=project_id or None,
                task_id=task_id or None, start_date=today, status='active',
                created_by=current_user.id, notes='Bulk assignment'))
        db.session.commit()
        return _reply([_msg(f'Assigned {len(workers)} {_plural(len(workers), "worker")}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# scope: notifications
# --------------------------------------------------------------------------

def _bulk_notifications(action):
    if not current_user.is_admin:
        return _denied()
    rows = Notification.query.filter(Notification.id.in_(_ids())).all() if _ids() else []
    if not rows:
        return _reply([_msg('No notifications selected.', 'info')], success=False)
    n = len(rows)

    if action in ('read', 'unread'):
        want = (action == 'read')
        for item in rows:
            item.is_read = want
        db.session.commit()
        label = 'read' if want else 'unread'
        return _reply([_msg(f'Marked {n} {_plural(n, "notification")} {label}.')])

    if action == 'delete':
        for item in rows:
            db.session.delete(item)
        db.session.commit()
        return _reply([_msg(f'Deleted {n} {_plural(n, "notification")}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# scope: closures
# --------------------------------------------------------------------------

def _bulk_closures(action):
    if not current_user.is_admin:
        return _denied()
    rows = ClosureDay.query.filter(ClosureDay.id.in_(_ids())).all() if _ids() else []
    if not rows:
        return _reply([_msg('No closure days selected.', 'info')], success=False)
    n = len(rows)

    if action == 'delete':
        for c in rows:
            db.session.delete(c)
        db.session.commit()
        return _reply([_msg(f'Deleted {n} closure {_plural(n, "day")}.')])

    if action in ('lock', 'unlock'):
        for c in rows:
            c.allow_attendance = (action == 'unlock')
        db.session.commit()
        verb = 'Locked' if action == 'lock' else 'Unlocked'
        return _reply([_msg(f'{verb} attendance on {n} closure {_plural(n, "day")}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# scope: settings entities (sites, projects, tasks, departments, users)
# --------------------------------------------------------------------------

_ENTITY_MODELS = {
    'sites': (Site, 'site'),
    'projects': (Project, 'project'),
    'tasks': (WorkTask, 'task'),
    'departments': (Department, 'department'),
}


def _bulk_entities(scope, action):
    if not current_user.is_admin:
        return _denied()
    model, noun = _ENTITY_MODELS[scope]
    rows = model.query.filter(model.id.in_(_ids())).all() if _ids() else []
    if not rows:
        return _reply([_msg(f'No {noun}s selected.', 'info')], success=False)
    n = len(rows)

    if action in ('archive', 'restore'):
        target = 'archived' if action == 'archive' else 'active'
        for row in rows:
            row.status = target
        db.session.commit()
        verb = 'Archived' if action == 'archive' else 'Restored'
        return _reply([_msg(f'{verb} {n} {_plural(n, noun)}.')])

    if action == 'delete':
        for row in rows:
            db.session.delete(row)
        db.session.commit()
        return _reply([_msg(f'Deleted {n} {_plural(n, noun)}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


def _bulk_attendance_users(action):
    if not current_user.is_admin:
        return _denied()
    rows = User.query.filter(
        User.id.in_(_ids()), User.role == 'attendance').all() if _ids() else []
    # Never let an admin lock themselves out through a bulk action.
    rows = [u for u in rows if u.id != current_user.id]
    if not rows:
        return _reply([_msg('No attendance users selected.', 'info')], success=False)
    n = len(rows)

    if action in ('enable', 'disable'):
        target = 'active' if action == 'enable' else 'disabled'
        for u in rows:
            u.status = target
        db.session.commit()
        verb = 'Enabled' if action == 'enable' else 'Disabled'
        return _reply([_msg(f'{verb} {n} {_plural(n, "user")}.')])

    if action == 'delete':
        for u in rows:
            db.session.delete(u)
        db.session.commit()
        return _reply([_msg(f'Deleted {n} {_plural(n, "user")}.')])

    return _reply([_msg('Unknown action.', 'error')], success=False)


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

_HANDLERS = {
    'attendance': _bulk_attendance,
    'workers': _bulk_workers,
    'payroll': _bulk_payroll,
    'transactions': _bulk_transactions,
    'assignments': _bulk_assignments,
    'notifications': _bulk_notifications,
    'closures': _bulk_closures,
    'attendance-users': _bulk_attendance_users,
}


@app.route('/api/bulk/<scope>', methods=['POST'])
@login_required
def bulk_action(scope):
    action = (request.form.get('action') or '').strip()
    if not action:
        return _reply([_msg('No action given.', 'error')], success=False)

    try:
        if scope in _ENTITY_MODELS:
            return _bulk_entities(scope, action)
        handler = _HANDLERS.get(scope)
        if not handler:
            return _reply([_msg('Unknown list.', 'error')], success=False)
        return handler(action)
    except Exception:
        # A partially applied bulk action is worse than none at all.
        db.session.rollback()
        app.logger.exception('Bulk action failed: scope=%s action=%s', scope, action)
        return _reply([_msg('That action could not be completed. Nothing was changed.',
                            'error')], success=False)
