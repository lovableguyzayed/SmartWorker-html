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
      'Sunita Devi के लिए पेशगी तनख़्वाह ₹1,500.00 जोड़ा गया।')
# The transaction type is itself translatable — it is the same word the
# dropdown shows — so it is looked up rather than passed through. A type
# with no Hindi name still comes out, in English, rather than vanishing.
check('a type with no Hindi name still comes through',
      i18n.translate_flash('Hardship Top-Up of ₹90.00 added for Sunita Devi.', 'hi'),
      'Sunita Devi के लिए Hardship Top-Up ₹90.00 जोड़ा गया।')
check('the scanner confirmation translates, type and all',
      i18n.translate_flash('Bonus ₹5,000.00 recorded for Sunita Devi.', 'hi'),
      'Sunita Devi के लिए इनाम ₹5,000.00 दर्ज कर लिया गया।')
# A message worded identically to a control falls back to the interface
# table, so there is one Hindi sentence for it rather than two.
check('a message only the interface table knows is still translated',
      i18n.translate_flash('Amount must be greater than zero.', 'hi'),
      'रक़म शून्य से ज़्यादा होनी चाहिए।')
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
# Parsed with ast rather than a regex. A regex over the source kept finding
# its own artefacts and reporting them as missing translations: a message
# built from two adjacent literals arrived glued, and
# flash('a' if x else 'b') arrived as one string containing both.
import ast  # noqa: E402

routes_src = open(os.path.join(ROOT, 'routes.py'), encoding='utf-8').read()
tree = ast.parse(routes_src)

plain, shaped = set(), set()


def literals(node):
    """Every message one flash() argument can produce, as (text, has_value)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [(node.value, False)]
    if isinstance(node, ast.JoinedStr):
        out, interpolated = [], False
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            else:
                out.append('X')
                interpolated = True
        return [(''.join(out), interpolated)]
    if isinstance(node, ast.IfExp):
        return literals(node.body) + literals(node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = literals(node.left), literals(node.right)
        if left and right:
            return [(left[0][0] + right[0][0], left[0][1] or right[0][1])]
    return []


for node in ast.walk(tree):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'flash' and node.args):
        continue
    for text, interpolated in literals(node.args[0]):
        text = ' '.join(text.split())
        if not text:
            continue
        (shaped if interpolated else plain).add(text)

missing_plain = sorted(t for t in plain if t not in table)
check('every plain message routes.py raises has a translation',
      missing_plain, [])

uncovered = sorted(t for t in shaped
                   if i18n.translate_flash(t, 'hi') == t)
check('every message carrying a value has a matching shape', uncovered, [])

print('\n%d plain messages, %d shapes, %d failed'
      % (len(table), len(i18n._FLASH_PATTERNS['hi']), len(failures)))
for f in failures:
    print('  FAIL', f)
sys.exit(1 if failures else 0)
