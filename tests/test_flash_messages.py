"""Flash messages must not fall back to English on a Hindi screen.

This was found by looking at a screenshot, not by any measurement: a Hindi
attendance screen announced "Payroll for October 2026 has already been
generated." The messages are translated where they are shown, so this checks
the translation layer against the messages routes.py can actually raise —
and fails when a new one is added without a translation, which is the only
way this stays fixed.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import i18n  # noqa: E402

failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-56s %s' % (label, repr(got)[:24]))
    else:
        failures.append(label)
        print('  FAIL %-56s got=%r want=%r' % (label, got, want))


# --- the layer itself -----------------------------------------------------
check('English is never rewritten',
      i18n.translate_flash('Password changed successfully', 'en'),
      'Password changed successfully')
check('a plain message translates',
      i18n.translate_flash('Password changed successfully', 'hi'),
      'पासवर्ड बदल गया')
check('a message carrying a name keeps the name',
      i18n.translate_flash('Attendance adjusted for Sunita Devi.', 'hi'),
      'Sunita Devi की हाज़िरी बदल दी गई।')
check('a message carrying money keeps the figure',
      i18n.translate_flash('Advance Salary of ₹1,500.00 added for Sunita Devi.', 'hi'),
      'Sunita Devi के लिए Advance Salary ₹1,500.00 जोड़ा गया।')
check('an unknown message stays English rather than vanishing',
      i18n.translate_flash('Something nobody has translated yet.', 'hi'),
      'Something nobody has translated yet.')
check('empty input is safe', i18n.translate_flash('', 'hi'), '')
check('None is safe', i18n.translate_flash(None, 'hi'), None)

table = i18n.FLASH_MESSAGES['hi']
check('no flash translation is empty',
      [k for k, v in table.items() if not v.strip()], [])
check('no flash translation was left in English',
      [k for k, v in table.items() if v == k], [])

src = open(os.path.join(ROOT, 'i18n.py'), encoding='utf-8').read()
keys = re.findall(r"^\s{8}((?:'[^']*'\s*)+):", src[src.index('FLASH_MESSAGES = {'):
                                                  src.index('_FLASH_PATTERNS_SOURCE')], re.M)
joined = [''.join(re.findall(r"'([^']*)'", k)) for k in keys]
check('no flash key appears twice',
      sorted({k for k in joined if joined.count(k) > 1}), [])

# --- every message routes.py can raise ------------------------------------
routes_src = open(os.path.join(ROOT, 'routes.py'), encoding='utf-8').read()
raised = re.findall(r"flash\(\s*(f?)(['\"])(.*?)\2\s*,", routes_src, re.S)

plain, shaped = set(), set()
for is_f, _q, text in raised:
    text = ' '.join(text.split())
    if not text or '+' in text[-2:]:
        continue
    (shaped if is_f else plain).add(text)

missing_plain = sorted(t for t in plain if t not in table)
check('every plain message routes.py raises has a translation',
      missing_plain, [])

# For the interpolated ones, substitute a placeholder for each {expr} and
# check some pattern claims the result.
def rendered(template):
    # A message split across lines arrives as "...end of part one ' f'start
    # of part two"; that glue is an artefact of reading the source, not part
    # of what the user sees.
    joined = re.sub(r"'\s*f'", '', template)
    return re.sub(r'\{[^{}]*\}', 'X', joined).strip()


uncovered = []
for text in shaped:
    sample = rendered(text)
    if i18n.translate_flash(sample, 'hi') == sample:
        uncovered.append(text[:62])
check('every message carrying a value has a matching shape',
      sorted(uncovered), [])

print('\n%d plain messages, %d shapes, %d failed'
      % (len(table), len(i18n._FLASH_PATTERNS['hi']), len(failures)))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
