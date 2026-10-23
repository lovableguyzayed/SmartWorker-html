"""The notifications feed groups by day and folds a run from one action.

A site user marking twelve workers one after another wrote twelve rows that
differed only in the name, each one repeating the worker and the status in
the title and then again in the body, each one stamped with a date the row
below already carried. A hundred of those was the whole screen.

Three things are checked here.

The folding itself: that a run collapses, that it stops folding the moment
anything differs, and that a row the writer did not shape — no outcome after
the dash — is left alone rather than guessed at.

That folding loses nothing. The folded line carries every id behind it, so
"Delete" on it deletes the whole run and not just the first of them. That is
only true if two pieces agree: the line must emit the ids comma-joined, and
bulk.py must split them back apart. Both halves are checked, because either
one alone is worse than neither — a line that posts "12,13,14" to a reader
that only understands "12" deletes nothing, and a reader that splits while
the line emits one id has nothing to split.

And that the count the person is shown is records, not rows. The selection
bar counts what it has selected; if a folded line of six counted as one,
the confirmation would say "Delete 1 notification?" and delete six.
"""
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-48s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


class Row(object):
    """Just enough of a Notification to group."""

    def __init__(self, nid, title, body, when, read=False, category='attendance'):
        self.id = nid
        self.title = title
        self.body = body
        self.created_at = when
        self.is_read = read
        self.category = category


import routes  # noqa: E402  (imports the app; must follow sys.path)
from routes import NOTE_DASH, group_notifications, notification_day_label

TODAY = date(2026, 10, 21)


def at(day, hh, mm):
    return datetime(2026, 10, day, hh, mm)


def mark(nid, name, status, where, day, hh, mm, read=False):
    return Row(nid, '%s (W-%03d)%s%s' % (name, nid, NOTE_DASH, status),
               where, at(day, hh, mm), read)


print('--- day labels ---')
check('today',      notification_day_label(date(2026, 10, 21), TODAY), 'Today')
check('yesterday',  notification_day_label(date(2026, 10, 20), TODAY), 'Yesterday')
check('older',      notification_day_label(date(2026, 10, 14), TODAY), None)

print('\n--- a run from one action folds into one line ---')
WHERE = 'Ramesh Yadav · Dwarka Expressway Package 3'
run = [
    mark(14, 'Ravi Kumar',    'present', WHERE, 21, 9, 12),
    mark(13, 'Suresh Patel',  'present', WHERE, 21, 9, 11),
    mark(12, 'Anil Sharma',   'present', WHERE, 21, 9, 11),
]
groups = group_notifications(run, TODAY)
check('one day',        len(groups), 1)
check('labelled Today', groups[0]['label'], 'Today')
check('one line',       len(groups[0]['rows']), 1)
row = groups[0]['rows'][0]
check('every id kept',  row['ids'], [14, 13, 12])
check('names kept',     row['names'],
      ['Ravi Kumar (W-014)', 'Suresh Patel (W-013)', 'Anil Sharma (W-012)'])
check('outcome',        row['outcome'], 'Present')
check('body once',      row['body'], WHERE)

print('\n--- a long run names a few and counts the rest ---')
# Forty names under one line is the wall the folding was there to remove.
long_run = [mark(100 + i, 'Worker %d' % i, 'present', WHERE, 21, 9, 30)
            for i in range(12)]
row = group_notifications(long_run, TODAY)[0]['rows'][0]
check('all ids kept',   len(row['ids']), 12)
check('names shown',    len(row['shown']), routes.NOTE_NAMES_SHOWN)
check('rest counted',   row['more'], 12 - routes.NOTE_NAMES_SHOWN)
short = group_notifications(run, TODAY)[0]['rows'][0]
check('short run counts nothing', short['more'], 0)
check('and shows them all', len(short['shown']), 3)

print('\n--- folding stops where anything differs ---')
mixed = [
    mark(14, 'Ravi Kumar',   'present', WHERE, 21, 9, 12),
    mark(13, 'Suresh Patel', 'absent',  WHERE, 21, 9, 11),   # other status
    mark(12, 'Anil Sharma',  'absent',  WHERE, 21, 9, 11),
    mark(11, 'Mohan Das',    'absent',  'Ramesh Yadav · Sector 62 Tower B',
         21, 9, 10),                                          # other site
]
rows = group_notifications(mixed, TODAY)[0]['rows']
check('three lines',    len(rows), 3)
check('first alone',    rows[0]['ids'], [14])
check('second folds 2', rows[1]['ids'], [13, 12])
check('third alone',    rows[2]['ids'], [11])

print('\n--- a different day is a different group ---')
twodays = [
    mark(14, 'Ravi Kumar',   'present', WHERE, 21, 9, 12),
    mark(13, 'Suresh Patel', 'present', WHERE, 20, 9, 11),
    mark(12, 'Anil Sharma',  'present', WHERE, 14, 9, 11),
]
groups = group_notifications(twodays, TODAY)
check('three groups',   len(groups), 3)
check('labels', [g['label'] for g in groups], ['Today', 'Yesterday', None])
check('none folded',    [len(g['rows']) for g in groups], [1, 1, 1])

print('\n--- a row the writer did not shape is left alone ---')
# No dash, so there is no outcome to fold on. Guessing one would be worse
# than leaving the row as it was written.
odd = [
    Row(9, 'Payroll finalised for October', 'Anita Verma', at(21, 18, 0)),
    Row(8, 'Payroll finalised for October', 'Anita Verma', at(21, 17, 0)),
]
rows = group_notifications(odd, TODAY)[0]['rows']
check('not folded',     [r['ids'] for r in rows], [[9], [8]])
check('title verbatim', rows[0]['title'], 'Payroll finalised for October')
check('no outcome',     rows[0]['outcome'], '')

print('\n--- unread survives folding ---')
part_read = [
    mark(14, 'Ravi Kumar',   'present', WHERE, 21, 9, 12, read=True),
    mark(13, 'Suresh Patel', 'present', WHERE, 21, 9, 11, read=False),
]
row = group_notifications(part_read, TODAY)[0]['rows'][0]
check('still unread',   row['unread'], True)
all_read = [
    mark(14, 'Ravi Kumar',   'present', WHERE, 21, 9, 12, read=True),
    mark(13, 'Suresh Patel', 'present', WHERE, 21, 9, 11, read=True),
]
check('read when all read',
      group_notifications(all_read, TODAY)[0]['rows'][0]['unread'], False)

print('\n--- a bulk notification already states its count ---')
# bulk.py writes one row for a whole bulk action. The count is in the stored
# English subject, so the reader has to recognise it or the screen prints
# "3 workers" in English next to a Hindi status.
bulky = [Row(5, '6 workers%spresent' % NOTE_DASH,
             'Sita Devi · Sector 62 Tower B · bulk', at(21, 8, 0))]
row = group_notifications(bulky, TODAY)[0]['rows'][0]
check('count read off it', row['count'], 6)
check('one id only',       row['ids'], [5])
check('no names to list',  row['shown'], [])
check('outcome',           row['outcome'], 'Present')
# Two bulk actions in a row must not fold into each other — "6 workers" and
# "4 workers" are not ten.
twice = [Row(5, '6 workers%spresent' % NOTE_DASH, 'Sita Devi · B · bulk', at(21, 8, 0)),
         Row(4, '6 workers%spresent' % NOTE_DASH, 'Sita Devi · B · bulk', at(21, 7, 0))]
check('counts never fold', [r['count'] for r in group_notifications(twice, TODAY)[0]['rows']],
      [6, 6])

print('\n--- a single mark states no count ---')
one = [mark(3, 'Ravi Kumar', 'late', WHERE, 21, 9, 0)]
row = group_notifications(one, TODAY)[0]['rows'][0]
check('count is one',   row['count'], 1)
check('named',          row['names'], ['Ravi Kumar (W-003)'])
check('no name line',   row['shown'], [])

print('\n--- the folded line carries its ids to the server ---')
with open(os.path.join(ROOT, 'templates', 'notifications.html')) as fh:
    tpl = fh.read()
check('emits them joined', "data-ms-item=\"{{ row.ids|join(',') }}\"" in tpl, True)

import bulk  # noqa: E402

from flask import Flask
probe = Flask(__name__)
with probe.test_request_context('/x', method='POST',
                                data={'ids': ['14,13,12', '11']}):
    check('bulk splits them', bulk._ids(), [14, 13, 12, 11])
with probe.test_request_context('/x', method='POST',
                                data={'ids': ['7', '7', 'nonsense', '']}):
    check('still de-duplicates', bulk._ids(), [7])

print('\n--- the count on the bar is records, not rows ---')
with open(os.path.join(ROOT, 'static', 'js', 'multiselect.js')) as fh:
    js = fh.read()
# The three places a number is shown or acted on must all go through tally().
check('bar count',   bool(re.search(r'var n = this\.count\(\);', js)), True)
check('select-all',  bool(re.search(r'var total = this\.tally\(', js)), True)
check('confirm/post', bool(re.search(r'var n = this\.tally\(ids\);', js)), True)
check('tally splits on comma',
      bool(re.search(r"String\(value\)\.split\(','\)\.length", js)), True)

print('\n--- the Hindi for the new words ---')
import i18n  # noqa: E402
for word in ['Today', 'Yesterday', 'workers', 'and %n more', 'Present', 'Absent', 'Late',
             'Leave', 'Half Day', 'Checked Out']:
    hi = i18n.translate(word, 'hi')
    check('hi: %s' % word, hi != word, True)

print('\n--- every stored outcome has a display word ---')
# bulk.py and routes.py write these; each one must map to a key the Hindi
# table knows, or the folded line shows a raw status.
for stored in ['present', 'absent', 'late', 'leave', 'half_day',
               'on leave', 'half day', 'checked out']:
    key = routes.NOTE_OUTCOMES.get(stored)
    check('outcome %r' % stored, bool(key) and i18n.translate(key, 'hi') != key,
          True)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('All notification checks passed.')
