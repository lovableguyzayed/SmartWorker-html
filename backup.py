"""Everything in one workspace, as a zip of spreadsheets the owner keeps.

The database this application runs on is a free Render Postgres. Those are
deleted thirty days after they are created, with a fourteen-day grace
period and no backup of any kind. A stone crusher's entire wage record —
who worked which day, what he was paid, what he is still owed — would go
with it, and the men whose money it is would have no way to argue.

So the owner gets to take it himself, whenever he likes, without asking
anybody: one zip, one CSV per table, and a README inside it saying what
the file is and what is not in it. CSV rather than a database dump
because he can open it in a spreadsheet on the phone in his hand, and
because a dump is only useful to somebody who still has the same version
of Postgres.

Three things are deliberately left out:

  * password hashes and the Supabase user ids. A backup is a file that
    ends up being forwarded. Passwords are set again on a restore; they
    are not carried in a file.
  * photographs and QR images. They are stored inline as data URIs and
    would turn a 200 KB file into tens of megabytes over a 2G line.
  * all but the last four digits of an Aadhaar number, which is all the
    application keeps going forward anyway.

What IS in it is still every worker's name, telephone number, bank
account and wage history, so the README says so in both languages.
"""
import csv
import datetime
import io
import zipfile

#: Columns never written to a backup, by table. Secrets and bulk.
OMITTED = {
    'users': ('password_hash', 'supabase_uid', 'profile_image'),
    'workers': ('profile_image', 'qr_code'),
    'accounts': ('owner_uid',),
}

#: Columns written with only their last four characters.
LAST_FOUR = {('workers', 'aadhaar_number')}

README = """SmartWorker backup
==================

Taken: %(taken)s (IST)
Workspace: %(account)s

WHAT THIS IS
    One CSV file for each kind of record this workspace holds: workers,
    attendance, payments, payroll, settings. Open any of them in a
    spreadsheet app.

    This is your copy. Keep it somewhere you will still have it if the
    database behind the application goes away.

WHAT IS NOT IN IT
    - Passwords. These are never put in a file. If this data is ever
      loaded back, every login's password has to be set again.
    - Photographs and QR images, because they would make this file
      enormous. The workers and their details are all here; only the
      pictures are missing.
    - All but the last four digits of any Aadhaar number.

PLEASE READ
    This file holds your workers' names, telephone numbers, bank account
    numbers and everything they have been paid. Treat it the way you
    would treat the wage book itself. Do not forward it.

ROWS
%(counts)s

---

SmartWorker बैकअप
=================

लिया गया: %(taken)s (IST)

यह क्या है
    इस वर्कस्पेस के हर तरह के रिकॉर्ड की एक CSV फ़ाइल — मज़दूर, हाज़िरी,
    भुगतान, तनख़्वाह, सेटिंग्स। किसी भी स्प्रेडशीट ऐप में खोल सकते हैं।

    यह आपकी कॉपी है। इसे वहाँ रखें जहाँ ऐप का डेटाबेस चला जाने के बाद भी
    आपके पास रहे।

इसमें क्या नहीं है
    - पासवर्ड। वे कभी किसी फ़ाइल में नहीं रखे जाते।
    - फ़ोटो और QR तस्वीरें, क्योंकि उनसे फ़ाइल बहुत भारी हो जाती।
    - आधार संख्या के आख़िरी 4 अंकों के अलावा कुछ नहीं।

ध्यान दें
    इस फ़ाइल में आपके मज़दूरों के नाम, फ़ोन नंबर, बैंक खाता और उनकी पूरी
    मज़दूरी का हिसाब है। इसे मज़दूरी के रजिस्टर की तरह ही सँभालें। किसी को
    आगे न भेजें।
"""


def _cell(value):
    """One value, as text a spreadsheet will not mangle."""
    if value is None:
        return ''
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)


def table_rows(model, rows):
    """(columns, rows) for one table, with the omitted columns left out."""
    table = model.__table__.name
    skip = set(OMITTED.get(table, ()))
    columns = [c.name for c in model.__table__.columns if c.name not in skip]
    out = []
    for row in rows:
        line = []
        for name in columns:
            value = _cell(getattr(row, name, None))
            if (table, name) in LAST_FOUR and value:
                value = value[-4:]
            line.append(value)
        out.append(line)
    return columns, out


def build(tables, account_name, taken):
    """Build the zip. ``tables`` is [(filename, model, rows), ...].

    Returns (bytes, {filename: row count}). The caller does the querying,
    so the account scoping stays with the request that knows which
    account it is, and this module cannot read somebody else's rows by
    accident.
    """
    counts = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for filename, model, rows in tables:
            columns, lines = table_rows(model, rows)
            text = io.StringIO(newline='')
            writer = csv.writer(text, lineterminator='\n')
            writer.writerow(columns)
            writer.writerows(lines)
            archive.writestr('%s.csv' % filename, text.getvalue())
            counts[filename] = len(lines)
        listing = '\n'.join('    %-24s %6d' % (name, count)
                            for name, count in sorted(counts.items()))
        archive.writestr('README.txt', README % {
            'taken': taken.strftime('%d %B %Y, %I:%M %p'),
            'account': account_name or 'SmartWorker',
            'counts': listing,
        })
    return buffer.getvalue(), counts
