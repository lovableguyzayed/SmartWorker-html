"""Interface language: the translation table, date formatting, and the two
mistakes that are easy to make and invisible until a Hindi user hits them.

Run from the project root:  python3 tests/test_i18n.py
"""
import ast
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'templates')
failures = []


def check(label, got, want):
    if got != want:
        failures.append((label, got, want))
        print('  FAIL %-58s got=%r want=%r' % (label, got, want))
    else:
        print('  PASS %-58s %r' % (label, str(got)[:40]))


# --- the table itself ----------------------------------------------------
check('Hindi is offered', 'hi' in i18n.LANGUAGES, True)
check('English is the default', i18n.DEFAULT_LANGUAGE, 'en')
check('English passes through untouched',
      i18n.translate('Mark Attendance', 'en'), 'Mark Attendance')
check('a known string translates',
      i18n.translate('Mark Attendance', 'hi'), 'हाज़िरी लगाएँ')
check('an unknown string falls back to English',
      i18n.translate('Quarterly EBITDA', 'hi'), 'Quarterly EBITDA')
check('an unknown language falls back to English',
      i18n.translate('Mark Attendance', 'ta'), 'Mark Attendance')
check('empty input is safe', i18n.translate('', 'hi'), '')
check('None is safe', i18n.translate(None, 'hi'), None)

hindi = i18n.TRANSLATIONS['hi']
check('every translation is non-empty',
      [k for k, v in hindi.items() if not v.strip()], [])
check('no translation was left in English',
      [k for k, v in hindi.items() if v == k and not k.isupper()], [])
check('no translation carries a stray quote that would break inline JS',
      [k for k, v in hindi.items() if "'" in v or '"' in v], [])

# A repeated key in the dict literal is legal Python — the later one silently
# wins — so a well-meant addition can change an unrelated screen's wording.
# Read the key literals out of the source rather than trusting the parsed
# dict, which has already lost the duplicate.
#
# With ast and not a regex: a regex for single-quoted keys skips every key
# written with double quotes (there are several, because the English contains
# an apostrophe) and a skipped key is exactly what this is meant to catch.
_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'i18n.py'), encoding='utf-8').read()
_assign = next(n for n in ast.parse(_src).body
               if isinstance(n, ast.Assign)
               and getattr(n.targets[0], 'id', None) == 'TRANSLATIONS')
# Per language, not across all of them: the same English key in 'hi' and in
# a second language is the point, not a duplicate.
_hi_literal = next(v for k, v in zip(_assign.value.keys, _assign.value.values)
                   if isinstance(k, ast.Constant) and k.value == 'hi')
_joined = [k.value for k in _hi_literal.keys
           if isinstance(k, ast.Constant) and isinstance(k.value, str)]
check('no key appears twice in the Hindi table',
      sorted({k for k in _joined if _joined.count(k) > 1}), [])
check('the duplicate check actually found the table',
      len(_joined) > 150, True)
check('and found the keys the old regex skipped',
      "Scan a worker's ID card to mark attendance" in _joined, True)

# --- dates ----------------------------------------------------------------
d = date(2026, 10, 20)   # a Tuesday
check('English dates are untouched',
      i18n.format_date(d, '%A, %B %d, %Y', 'en'), 'Tuesday, October 20, 2026')
check('Hindi dates use Hindi names and Hindi word order',
      i18n.format_date(d, '%A, %B %d, %Y', 'hi'), '20 अक्टूबर 2026, मंगलवार')
check('short Hindi dates work', i18n.format_date(d, '%d %b %Y', 'hi'), '20 अक्तू 2026')
check('a format with no names is unchanged',
      i18n.format_date(d, '%Y-%m-%d', 'hi'), '2026-10-20')
check('None formats to empty', i18n.format_date(None, '%d %b', 'hi'), '')
check('an untranslated language keeps English names',
      i18n.format_date(d, '%A', 'ta'), 'Tuesday')
check('weekday lists are Monday-first and seven long',
      (len(i18n.weekday_names('hi')), i18n.weekday_names('hi')[d.weekday()]),
      (7, 'मंगलवार'))
check('short weekday list is seven long', len(i18n.weekday_names('hi', short=True)), 7)
check('month names cover the year', len(i18n.MONTHS['hi']), 12)

# --- salary notes ---------------------------------------------------------
# The engine stores its working out as English prose in the payroll snapshot
# (that is the audit record), and it is translated on the way to the screen.
check('an engine note translates with its numbers intact',
      i18n.translate_note('Full monthly salary 38000.0 applies.', 'hi'),
      'पूरी महीने की तनख़्वाह ₹38000.0 लागू है।')
check('the final line translates',
      i18n.translate_note('Final payable: 38000.0 - 1266.67 = 36733.33.', 'hi'),
      'देने योग्य रक़म: ₹38000.0 − ₹1266.67 = ₹36733.33।')
check('a leave-allowance note translates',
      i18n.translate_note(
          'Paid leave allowance 2 day(s) covered 3 absence(s) and 0 leave(s).', 'hi'),
      '2 दिन की मिलने वाली छुट्टी से 3 ग़ैरहाज़िरी और 0 छुट्टी भर गई।')
check('a route note translates',
      i18n.translate_note('Overtime policy added extra pay.', 'hi'),
      'ओवरटाइम के नियम से अतिरिक्त रक़म जुड़ी।')
check('an unrecognised note is left in English, not dropped',
      i18n.translate_note('Some note the engine grew later.', 'hi'),
      'Some note the engine grew later.')
check('English is never rewritten',
      i18n.translate_note('Full monthly salary 38000.0 applies.', 'en'),
      'Full monthly salary 38000.0 applies.')
check('a joined paragraph splits on sentences, not on decimal points',
      i18n.translate_notes(
          'No-work-no-pay applied for absent days. Overtime policy added extra pay.',
          'hi'),
      'ग़ैरहाज़िर दिनों की मज़दूरी नहीं जोड़ी गई। '
      'ओवरटाइम के नियम से अतिरिक्त रक़म जुड़ी।')
check('a decimal inside a sentence does not split it',
      i18n.translate_notes('Full monthly salary 38000.0 applies.', 'hi'),
      'पूरी महीने की तनख़्वाह ₹38000.0 लागू है।')

# Every note shape the engine and the payroll route can emit should be
# covered — an uncovered one silently stays English on a Hindi payslip.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
emitted = set()
for fname, needle in (('salary.py', 'explanation.append'),
                      ('routes.py', 'policy_notes.append')):
    body = open(os.path.join(ROOT, fname), encoding='utf-8').read()
    for m in re.finditer(re.escape(needle) + r'\(\s*((?:\'[^\']*\'\s*)+)',
                         body):
        emitted.add(''.join(re.findall(r"'([^']*)'", m.group(1))))
# Reduce each emitted template to the regexes that could match it: the
# patterns are anchored, so compare on the literal prefix before the first
# format placeholder.
uncovered = []
for template in sorted(emitted):
    prefix = re.split(r'%[sdg%]', template)[0].strip()
    if not prefix:
        continue
    hit = any(p.pattern.lstrip('^').startswith(re.escape(prefix[:12])[:12])
              or prefix[:12] in p.pattern
              for p, _r in i18n._NOTE_PATTERNS['hi'])
    if not hit:
        uncovered.append(template[:60])
check('every note the code emits has a Hindi pattern', uncovered, [])

# --- the two template traps ----------------------------------------------
# 1. `{% set _ = list.append(x) %}` is a common Jinja throwaway, and it
#    shadows the _() translation helper with None for the rest of the block.
#    That took out the whole attendance screen with a 500 once already.
shadowed = []
for name in sorted(os.listdir(TEMPLATES)):
    if not name.endswith('.html'):
        continue
    body = open(os.path.join(TEMPLATES, name), encoding='utf-8').read()
    if re.search(r'\{%-?\s*set\s+_\s*=', body):
        shadowed.append(name)
check('no template shadows _() with {% set _ = ... %}', shadowed, [])

# 2. _() inside an inline <script> is rendered straight into a JS string
#    literal, so a translation containing a quote would break the script. The
#    table is already checked above for quotes; this checks the templates use
#    the safe form, so one slip in the table cannot take a screen down.
def _unguarded_in_scripts(body):
    """Every `_()` inside a <script> that is not piped through |tojson.

    Scans for the closing paren rather than matching the whole call with a
    regex, because a long message is written as several adjacent literals and
    a regex for that kept missing one form or another.
    """
    out = []
    for script in re.findall(r'<script\b[^>]*>(.*?)</script>', body,
                             re.S | re.I):
        for start in (m.start() for m in re.finditer(r'\b_\(', script)):
            i, quote = start + 2, None
            while i < len(script):
                ch = script[i]
                if quote:
                    if ch == quote:
                        quote = None
                elif ch in '\'"':
                    quote = ch
                elif ch == ')':
                    break
                i += 1
            if not re.match(r'\s*\|\s*tojson', script[i + 1:]):
                out.append(script[start:i + 1].replace('\n', ' ')[:48])
    return out


# Every template, not just the scanner: the trap is the same wherever a
# translated string is rendered into JavaScript, and the one that broke a
# screen was found by hand.
unguarded = []
for name in sorted(os.listdir(TEMPLATES)):
    if name.endswith('.html'):
        unguarded += [(name, call) for call in _unguarded_in_scripts(
            open(os.path.join(TEMPLATES, name), encoding='utf-8').read())]
check('every _() inside a <script> is JSON-encoded for JS', unguarded, [])
check('and the check is actually looking at the scanner',
      len(_unguarded_in_scripts(
          open(os.path.join(TEMPLATES, 'scan.html'), encoding='utf-8').read()
          .replace('|tojson', ''))) > 10, True)

# 3. salary.py now writes the amount inside a note as a proper rupee, while
#    notes stored before that carry a bare float. The Hindi replacement
#    supplies a ₹ for the old shape, so the new shape meets it as ₹₹ unless
#    translate_note collapses it. Both shapes are checked, because fixing
#    one by hand broke the other once already.
doubled, unsigned, untranslated = [], [], []
for note in ['Full monthly salary ₹38,000 applies.',
             'Final payable: ₹22,000 - ₹1,468 = ₹20,532.',
             'Deduction: 2 day(s) x ₹400 = ₹800.',
             'Daily rate ₹1,462 x 26 day(s) basis = ₹38,012.']:
    hi = i18n.translate_note(note, 'hi')
    if '₹₹' in hi:
        doubled.append(hi)
    if hi == note:
        untranslated.append(note)
check('a note written today does not double the rupee', doubled, [])
check('and it still matches its pattern', untranslated, [])

for note in ['Full monthly salary 38000.0 applies.',
             'Final payable: 38000.0 - 1266.67 = 36733.33.']:
    hi = i18n.translate_note(note, 'hi')
    if '₹' not in hi:
        unsigned.append(hi)
check('a note stored before today still gets its rupee', unsigned, [])

print('\n%d checks, %d failed' % (37, len(failures)))
sys.exit(1 if failures else 0)
