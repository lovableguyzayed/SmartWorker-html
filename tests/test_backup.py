"""The owner can take his own wage record out, and only his own.

The database this runs on is a free Render Postgres. Those are deleted
thirty days after they are created, with a fourteen-day grace period and
no backup of any kind. A stone crusher's whole wage record — who worked
which day, what he was paid, what he is still owed — would go with it,
and the men whose money it is would have nothing to argue from.

So there is a button. One zip, one CSV per table, and a README inside it
in both languages saying what the file is.

Four things have to be true, and the second is the one that would do real
damage if it were wrong:

  * it is complete. Every worker, every attendance mark, every rupee paid.
    A backup missing a table is worse than none, because it is trusted.
  * it is ONE ACCOUNT'S data. ``users`` and ``accounts`` are deliberately
    left out of the automatic tenant filter — the login layer scopes them
    itself — and a backup is exactly where that exception would quietly
    become one employer downloading another employer's workers and their
    bank accounts.
  * no password hash, Supabase id or photograph goes in. A backup is a
    file that gets forwarded; a password hash in it is a password hash on
    somebody's phone, and the images would make it tens of megabytes on a
    2G line.
  * only the last four digits of an Aadhaar, the same as the application
    now keeps.

And a supervisor cannot take one at all. He can mark attendance; he
cannot walk out with the whole wage book.

Run from the project root:  python3 tests/test_backup.py
"""
import io
import os
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from sqlalchemy import text

from app import app, db
import models as m
import routes  # noqa: F401
import bulk    # noqa: F401

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

MARK = 'ZZBackup'
made = []

with app.app_context():
    m.Worker.query.filter(m.Worker.full_name.like(MARK + '%')).delete(
        synchronize_session=False)
    db.session.commit()

    admin = m.User.query.filter_by(role='admin').first()
    account = admin.account_id

    # Somebody else's worker, in somebody else's workspace. Raw SQL on the
    # way in and out, because the tenant filter hides other accounts from
    # the ORM and the whole point here is to look past it.
    other = db.session.execute(text(
        'select id from accounts where id <> :mine limit 1'),
        {'mine': account}).scalar()
    if other is None:
        db.session.execute(text(
            "insert into accounts (name, status) values ('ZZOther Co', "
            "'active')"))
        db.session.commit()
        other = db.session.execute(text(
            "select id from accounts where name = 'ZZOther Co'")).scalar()

    db.session.execute(text(
        'insert into workers (account_id, worker_id, full_name, phone, '
        'position, department, employee_type, join_date, pay_type, '
        'daily_rate, status, bank_account_number) values (:acc, '
        "'ZZOTHER1', :name, '9000000992', 'Helper', 'Civil', 'permanent', "
        ":d, 'daily', 500, 'active', '999988887777')"),
        {'acc': other, 'name': MARK + ' Somebody Elses Man',
         'd': routes.today_ist()})
    db.session.commit()
    foreign_id = db.session.execute(text(
        "select id from workers where worker_id = 'ZZOTHER1'")).scalar()

    # And one of ours, with an Aadhaar, so there is something to check.
    mine = m.Worker(
        account_id=account, worker_id='ZZBK01',
        full_name=MARK + ' Ours', phone='9000000991',
        position='Helper', department='Civil', employee_type='permanent',
        join_date=routes.today_ist(), pay_type='daily', daily_rate=500,
        status='active', aadhaar_number='123456789012')
    db.session.add(mine)
    db.session.commit()
    made.append(mine.id)
    expected_workers = m.Worker.query.filter(
        m.Worker.account_id == account).count()
    password_hashes = [row[0] for row in db.session.execute(text(
        'select password_hash from users')).fetchall() if row[0]]

try:
    with app.test_client() as client:
        client.post('/login', data={'username': 'demo@acme.test',
                                    'password': 'demo12345'})
        response = client.get('/settings/backup')

        print('--- it is a zip file, and the browser saves it ---')
        check('it comes back', response.status_code, 200)
        check('as a zip', response.headers.get('Content-Type'),
              'application/zip')
        check('with a date in the filename',
              'attachment; filename="smartworker-backup-' in
              response.headers.get('Content-Disposition', ''), True)

        archive = zipfile.ZipFile(io.BytesIO(response.data))
        check('and it is not corrupt', archive.testzip(), None)
        names = sorted(archive.namelist())
        whole = b'\n'.join(archive.read(n) for n in names).decode(
            'utf-8', 'replace')

        print('\n--- it is complete ---')
        for needed in ('workers.csv', 'attendance.csv', 'transactions.csv',
                       'payroll.csv', 'company_settings.csv',
                       'statutory_deductions.csv', 'minimum_wages.csv',
                       'README.txt'):
            check('%-26s is in it' % needed, needed in names, True)
        workers_csv = archive.read('workers.csv').decode().strip()
        rows = workers_csv.splitlines()
        check('every one of our workers is a row',
              len(rows) - 1, expected_workers)
        check('and our own man by name',
              MARK + ' Ours' in workers_csv, True)

        print('\n--- and it is OUR data, nobody else\'s ---')
        check("the other workspace's man is not in it",
              'ZZOTHER1' in whole, False)
        check('nor is his name', 'Somebody Elses Man' in whole, False)
        check('nor his bank account', '999988887777' in whole, False)
        accounts_csv = archive.read('workspace.csv').decode()
        check('only one workspace row', len(accounts_csv.strip().splitlines()),
              2)
        logins = archive.read('logins.csv').decode()
        check('and every login in it belongs to this account',
              all(line.split(',')[4] == str(account)
                  for line in logins.strip().splitlines()[1:]), True)

        print('\n--- no secrets, no bulk ---')
        check('no password hash anywhere',
              sum(1 for h in password_hashes if h and h in whole), 0)
        for column in ('password_hash', 'supabase_uid', 'profile_image',
                       'qr_code'):
            check('%-16s is not even a column' % column,
                  column in whole, False)

        print('\n--- and four digits of an Aadhaar, not twelve ---')
        check('the full number is not in the file',
              '123456789012' in whole, False)
        check('the last four are', ',9012,' in workers_csv, True)

        print('\n--- the README says what the file is ---')
        readme = archive.read('README.txt').decode()
        check('it says what is not in it', 'Passwords' in readme, True)
        check('it says to look after it', 'wage book' in readme, True)
        check('and it says it in Hindi too', 'बैकअप' in readme, True)
        check('it counts the rows it carried', 'workers' in readme, True)

        print('\n--- a supervisor cannot take one ---')
    with app.test_client() as client:
        with app.app_context():
            sup = m.User.query.filter(m.User.role != 'admin').first()
        if sup is None:
            print('       (no non-admin login in this database to try)')
        else:
            with client.session_transaction() as s:
                s['_user_id'] = str(sup.id)
            got = client.get('/settings/backup', follow_redirects=False)
            check('he is turned away', got.status_code in (302, 403), True)
            check('and gets no zip file',
                  got.headers.get('Content-Type') == 'application/zip',
                  False)
finally:
    with app.app_context():
        if made:
            m.Worker.query.filter(m.Worker.id.in_(made)).delete(
                synchronize_session=False)
        db.session.execute(text(
            "delete from workers where worker_id = 'ZZOTHER1'"))
        db.session.execute(text("delete from accounts where name = 'ZZOther Co'"))
        db.session.commit()
        print('\n--- and this test leaves nothing behind ---')
        check('its workers are gone', db.session.execute(text(
            "select count(*) from workers where full_name like 'ZZBackup%'"
        )).scalar(), 0)
        check('and its workspace too', db.session.execute(text(
            "select count(*) from accounts where name = 'ZZOther Co'"
        )).scalar(), 0)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('His own wage record, all of it, and nobody else\'s.')
